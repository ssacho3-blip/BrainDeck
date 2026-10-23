"""TDD / BDD / DDT Test Suite for Anki v3 Study Planner & Power Features (`anki_study_planner.py`).

Covers:
1. Anki Study Plan & D-Day Pacing Algorithm (`compute_anki_study_plan`):
   - Daily new card quota pacing with consolidation buffer before D-Day
   - 30-day FSRS review cascade workload projection & time budget estimation
   - Feasibility classification (`FEASIBLE`, `TIGHT_SCHEDULE`, `OVERLOAD_WARNING`)
2. Anki v3 Daily Queue Scheduler (`build_anki_v3_daily_queue`):
   - `new_per_day` & `max_reviews_per_day` caps (with uncapped learning/relearning)
   - Filtering of `suspended` and `buried` cards
   - Automatic Sibling Burying (`concept:<id>`) across new and review queues
   - Review sort orders (`retrievability_asc`, `retrievability_desc`, `due_date_asc`, `difficulty_desc`)
   - New/Review mix modes (`mix`, `reviews_first`, `new_first`)
3. Backlog Catch-Up Planner (`plan_backlog_catchup`)
4. Leech Detection & Auto-Suspension (`evaluate_leech_status`)
5. Anki Card Browser/Reviewer Actions (`apply_anki_card_action`: suspend, bury, flag 0..7, forget_reset, set_due_days)
6. Anki Custom Study / Filtered Deck Session Builder (`build_custom_study_session`)
7. End-to-End `AnkiStudioService` + Web ViewModel parity
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from anki_studio.domain.anki_study_planner import (
    ANKI_FLAG_LABELS,
    AnkiDeckOptions,
    apply_anki_card_action,
    build_anki_v3_daily_queue,
    build_custom_study_session,
    compute_anki_study_plan,
    evaluate_leech_status,
    plan_backlog_catchup,
)
from anki_studio.service import AnkiStudioService


# ============================================================================
# 1. BDD + DDT: Anki Study Plan & D-Day Pacing (`compute_anki_study_plan`)
# ============================================================================


@pytest.mark.parametrize(
    "total_cards,new_count,learning_count,review_due_count,target_days,daily_minutes_budget,expected_status",
    [
        # 1,200-card deck over 30 days with 45 min/day budget -> comfortable FEASIBLE plan
        (1200, 1000, 20, 80, 30, 45, "FEASIBLE"),
        # 1,200-card deck over 20 days with 25 min/day budget -> TIGHT_SCHEDULE
        (1200, 1000, 20, 80, 20, 25, "TIGHT_SCHEDULE"),
        # 1,200-card deck crammed into 5 days with 15 min/day budget -> OVERLOAD_WARNING
        (1200, 1000, 30, 100, 5, 15, "OVERLOAD_WARNING"),
    ],
)
def test_compute_anki_study_plan_dday_pacing_and_feasibility(
    total_cards: int,
    new_count: int,
    learning_count: int,
    review_due_count: int,
    target_days: int,
    daily_minutes_budget: int,
    expected_status: str,
) -> None:
    plan = compute_anki_study_plan(
        total_cards=total_cards,
        new_count=new_count,
        learning_count=learning_count,
        review_due_count=review_due_count,
        target_days=target_days,
        daily_minutes_budget=daily_minutes_budget,
        desired_retention=0.90,
    )
    assert plan["status"] == expected_status
    assert plan["total_cards"] == total_cards
    assert plan["new_count"] == new_count
    assert plan["target_days"] == target_days
    assert plan["consolidation_days"] >= (2 if target_days >= 7 else 0)
    assert plan["recommended_daily_new"] >= 1
    # Sum of new cards introduced across the forecast must cover all `new_count` before consolidation phase
    forecast = plan["daily_forecast"]
    assert len(forecast) == target_days
    total_planned_new = sum(day["new_cards"] for day in forecast)
    assert total_planned_new == new_count
    # Consolidation phase at the tail must have 0 new cards so learner only reviews before D-Day
    if plan["consolidation_days"] > 0:
        for tail_day in forecast[-plan["consolidation_days"] :]:
            assert tail_day["new_cards"] == 0
            assert tail_day["phase"] == "consolidation_review"
    assert plan["peak_daily_minutes"] > 0
    assert len(plan["recommendations"]) >= 1


def test_compute_anki_study_plan_fails_closed_on_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="target_days"):
        compute_anki_study_plan(
            total_cards=1000,
            new_count=1000,
            learning_count=0,
            review_due_count=0,
            target_days=0,
        )
    with pytest.raises(ValueError, match="desired_retention"):
        compute_anki_study_plan(
            total_cards=1000,
            new_count=1000,
            learning_count=0,
            review_due_count=0,
            target_days=30,
            desired_retention=0.50,
        )


# ============================================================================
# 2. BDD + DDT: Anki v3 Daily Queue Scheduler (`build_anki_v3_daily_queue`)
# ============================================================================


def _sample_deck_cards_for_v3_scheduler() -> list[dict]:
    return [
        # Learning & Relearning cards (always prioritized, uncapped by max_reviews_per_day)
        {"card_id": "learn_1", "state": "learning", "s": 0.5, "d": 6.0, "elapsed_days": 0.0, "due_days": 0, "lapses": 1, "tags": ["concept:c_learn_1"]},
        {"card_id": "relearn_1", "state": "relearning", "s": 1.2, "d": 7.5, "elapsed_days": 0.2, "due_days": 0, "lapses": 3, "tags": ["concept:c_relearn_1"]},
        # Due Review cards with varying Retrievability R(t, S) and siblings
        {"card_id": "rev_urgent", "state": "review", "s": 5.0, "d": 6.5, "elapsed_days": 15.0, "due_days": -10, "lapses": 2, "tags": ["concept:c_rev_1"]},
        {"card_id": "rev_sibling_of_urgent", "state": "review", "s": 6.0, "d": 6.0, "elapsed_days": 8.0, "due_days": -2, "lapses": 0, "tags": ["concept:c_rev_1"]},
        {"card_id": "rev_moderate", "state": "review", "s": 10.0, "d": 5.0, "elapsed_days": 11.0, "due_days": -1, "lapses": 0, "tags": ["concept:c_rev_2"]},
        {"card_id": "rev_easy", "state": "review", "s": 30.0, "d": 3.5, "elapsed_days": 30.0, "due_days": 0, "lapses": 0, "tags": ["concept:c_rev_3"]},
        # New cards (including a sibling of rev_moderate and two new siblings)
        {"card_id": "new_sib_of_rev2", "state": "new", "s": 0.0, "d": 5.0, "elapsed_days": 0.0, "due_days": 0, "lapses": 0, "tags": ["concept:c_rev_2"]},
        {"card_id": "new_1a", "state": "new", "s": 0.0, "d": 4.0, "elapsed_days": 0.0, "due_days": 0, "lapses": 0, "tags": ["concept:c_new_1"]},
        {"card_id": "new_1b_sibling", "state": "new", "s": 0.0, "d": 4.0, "elapsed_days": 0.0, "due_days": 0, "lapses": 0, "tags": ["concept:c_new_1"]},
        {"card_id": "new_2", "state": "new", "s": 0.0, "d": 7.0, "elapsed_days": 0.0, "due_days": 0, "lapses": 0, "tags": ["concept:c_new_2"]},
        {"card_id": "new_3", "state": "new", "s": 0.0, "d": 3.0, "elapsed_days": 0.0, "due_days": 0, "lapses": 0, "tags": ["concept:c_new_3"]},
        # Suspended & Buried cards (must never enter daily queue)
        {"card_id": "sus_1", "state": "suspended", "s": 4.0, "d": 5.0, "elapsed_days": 10.0, "due_days": -5, "lapses": 8, "tags": ["concept:c_sus", "leech"]},
        {"card_id": "buried_1", "state": "review", "s": 4.0, "d": 5.0, "elapsed_days": 10.0, "due_days": -5, "lapses": 0, "tags": ["concept:c_bur", "buried_today"]},
    ]


def test_build_anki_v3_daily_queue_sibling_burying_and_sort_order() -> None:
    cards = _sample_deck_cards_for_v3_scheduler()
    opts = AnkiDeckOptions(
        new_per_day=2,
        max_reviews_per_day=10,
        review_sort_order="retrievability_asc",
        new_review_mix_mode="reviews_first",
        bury_new_siblings=True,
        bury_review_siblings=True,
    )
    res = build_anki_v3_daily_queue(cards, options=opts)
    q_ids = [c["card_id"] for c in res["queue"]]

    # Suspended and pre-buried cards must be excluded
    assert "sus_1" not in q_ids
    assert "buried_1" not in q_ids

    # Sibling burying: rev_sibling_of_urgent shares concept:c_rev_1 with rev_urgent -> buried!
    assert "rev_urgent" in q_ids
    assert "rev_sibling_of_urgent" not in q_ids
    assert "rev_sibling_of_urgent" in res["buried_sibling_ids"]

    # Sibling burying across review -> new: new_sib_of_rev2 shares concept:c_rev_2 with rev_moderate -> buried!
    assert "rev_moderate" in q_ids
    assert "new_sib_of_rev2" not in q_ids
    assert "new_sib_of_rev2" in res["buried_sibling_ids"]

    # Sibling burying within new: new_1a and new_1b_sibling share concept:c_new_1 -> only new_1a enters!
    assert "new_1a" in q_ids
    assert "new_1b_sibling" not in q_ids
    assert "new_1b_sibling" in res["buried_sibling_ids"]

    # Check review ordering: retrievability_asc puts rev_urgent (t=15, s=5) before rev_moderate (t=11, s=10) before rev_easy (t=30, s=30)
    rev_positions = [q_ids.index("rev_urgent"), q_ids.index("rev_moderate"), q_ids.index("rev_easy")]
    assert rev_positions == sorted(rev_positions)

    # In "reviews_first" mode, all due reviews appear before new cards
    assert q_ids.index("rev_easy") < q_ids.index("new_1a")
    assert res["counts"]["learning"] == 2
    assert res["counts"]["review"] == 3
    assert res["counts"]["new"] == 2


@pytest.mark.parametrize("mix_mode", ["mix", "reviews_first", "new_first"])
def test_build_anki_v3_daily_queue_mix_modes(mix_mode: str) -> None:
    cards = _sample_deck_cards_for_v3_scheduler()
    opts = AnkiDeckOptions(
        new_per_day=2,
        max_reviews_per_day=3,
        new_review_mix_mode=mix_mode,
    )
    res = build_anki_v3_daily_queue(cards, options=opts)
    non_learning = [c for c in res["queue"] if c["state"] not in ("learning", "relearning")]
    states = [c["state"] for c in non_learning]
    if mix_mode == "reviews_first":
        assert states == ["review", "review", "review", "new", "new"]
    elif mix_mode == "new_first":
        assert states == ["new", "new", "review", "review", "review"]
    else:
        # "mix" interleaves review and new cards so new cards are not all bunched at one end
        assert states[0] == "review"
        assert "new" in states[:3]


# ============================================================================
# 3. BDD: Backlog Catch-Up Planner (`plan_backlog_catchup`)
# ============================================================================


def test_plan_backlog_catchup_distributes_overdue_by_retrievability() -> None:
    overdue_cards = [
        {"card_id": f"ov_{i}", "state": "review", "s": float(5 + (i % 10)), "d": 6.0, "elapsed_days": float(20 + i), "lapses": i % 4}
        for i in range(70)
    ]
    plan = plan_backlog_catchup(
        overdue_cards=overdue_cards,
        catchup_days=7,
        regular_daily_reviews=80,
        max_safe_daily_reviews=120,
    )
    assert plan["overdue_total"] == 70
    assert plan["catchup_days"] == 7
    assert plan["daily_backlog_quota"] == 10
    assert plan["projected_daily_total"] == 90
    assert plan["within_safe_cap"] is True
    assert len(plan["day_buckets"]) == 7
    assert sum(len(b["card_ids"]) for b in plan["day_buckets"]) == 70
    # Day 1 must contain the most urgent (lowest retrievability) cards
    assert plan["day_buckets"][0]["avg_retrievability"] <= plan["day_buckets"][-1]["avg_retrievability"]


# ============================================================================
# 4. BDD + DDT: Leech Detection & Handling (`evaluate_leech_status`)
# ============================================================================


@pytest.mark.parametrize(
    "lapses,threshold,action,expected_is_leech,expected_just_triggered,expected_suspended",
    [
        (3, 8, "suspend", False, False, False),
        (8, 8, "tag_only", True, True, False),
        (8, 8, "suspend", True, True, True),
        (10, 8, "suspend", True, False, False),  # 10 is between 8 and 12 (8 + 4)
        (12, 8, "suspend", True, True, True),    # re-triggers every threshold // 2 = 4 lapses
    ],
)
def test_evaluate_leech_status_anki_rules(
    lapses: int,
    threshold: int,
    action: str,
    expected_is_leech: bool,
    expected_just_triggered: bool,
    expected_suspended: bool,
) -> None:
    res = evaluate_leech_status(
        lapses=lapses,
        leech_threshold=threshold,
        leech_action=action,
        existing_tags=("eng_vocab",),
    )
    assert res["is_leech"] is expected_is_leech
    assert res["just_triggered"] is expected_just_triggered
    assert res["should_suspend"] is expected_suspended
    if expected_is_leech:
        assert "leech" in res["tags"]
        assert "거머리 카드(Leech)" in res["coaching_message"]


# ============================================================================
# 5. BDD + DDT: Anki Card Browser/Reviewer Actions (`apply_anki_card_action`)
# ============================================================================


def test_apply_anki_card_action_suspend_bury_flag_reset_and_set_due() -> None:
    card = {
        "card_id": "c_101",
        "state": "review",
        "s": 14.5,
        "d": 6.2,
        "reps": 7,
        "lapses": 2,
        "due_days": 10,
        "flag": 0,
        "tags": ["eng_vocab", "concept:c_101"],
    }

    # 1) Flag Red (1)
    flagged = apply_anki_card_action(card, action="set_flag", flag=1)
    assert flagged["flag"] == 1
    assert flagged["flag_label"] == ANKI_FLAG_LABELS[1]
    assert "flag:1" in flagged["tags"]

    # 2) Suspend & Unsuspend
    suspended = apply_anki_card_action(flagged, action="suspend")
    assert suspended["suspended"] is True
    assert "suspended" in suspended["tags"]
    unsuspended = apply_anki_card_action(suspended, action="unsuspend")
    assert unsuspended["suspended"] is False
    assert "suspended" not in unsuspended["tags"]

    # 3) Bury & Unbury
    buried = apply_anki_card_action(unsuspended, action="bury")
    assert buried["buried_today"] is True
    assert "buried_today" in buried["tags"]
    unburied = apply_anki_card_action(buried, action="unbury")
    assert unburied["buried_today"] is False
    assert "buried_today" not in unburied["tags"]

    # 4) Set Due Date (Anki reschedule to N days)
    rescheduled = apply_anki_card_action(unburied, action="set_due_days", due_days=3)
    assert rescheduled["due_days"] == 3
    assert rescheduled["state"] == "review"

    # 5) Forget / Reset Progress (Anki restore to brand-new)
    reset_card = apply_anki_card_action(rescheduled, action="forget_reset")
    assert reset_card["state"] == "new"
    assert reset_card["reps"] == 0
    assert reset_card["lapses"] == 0
    assert reset_card["s"] == 0.0
    assert reset_card["d"] == 0.0


# ============================================================================
# 6. BDD + DDT: Anki Custom Study / Filtered Deck (`build_custom_study_session`)
# ============================================================================


def test_build_custom_study_session_all_5_anki_presets() -> None:
    cards = [
        {"card_id": "lapsed_1", "state": "relearning", "s": 1.0, "d": 8.0, "due_days": 0, "lapses": 9, "last_rating": 1, "flag": 1, "tags": ["leech", "flag:1"]},
        {"card_id": "lapsed_2", "state": "review", "s": 2.0, "d": 7.0, "due_days": 1, "lapses": 4, "last_rating": 1, "flag": 2, "tags": ["flag:2"]},
        {"card_id": "ahead_1", "state": "review", "s": 5.0, "d": 5.0, "due_days": 2, "lapses": 0, "last_rating": 3, "flag": 0, "tags": []},
        {"card_id": "ahead_2", "state": "review", "s": 12.0, "d": 4.5, "due_days": 10, "lapses": 0, "last_rating": 4, "flag": 0, "tags": []},
        {"card_id": "new_1", "state": "new", "s": 0.0, "d": 0.0, "due_days": 0, "lapses": 0, "last_rating": None, "flag": 0, "tags": []},
        {"card_id": "new_2", "state": "new", "s": 0.0, "d": 0.0, "due_days": 0, "lapses": 0, "last_rating": None, "flag": 0, "tags": []},
    ]

    # Preset 1: forgotten_recent
    s_forgotten = build_custom_study_session(cards, preset="forgotten_recent", limit=10)
    assert [c["card_id"] for c in s_forgotten["cards"]] == ["lapsed_1", "lapsed_2"]
    assert s_forgotten["event_kind"] == "REVIEW"

    # Preset 2: review_ahead (within 3 days)
    s_ahead = build_custom_study_session(cards, preset="review_ahead", days_ahead=3, limit=10)
    assert "ahead_1" in [c["card_id"] for c in s_ahead["cards"]]
    assert "ahead_2" not in [c["card_id"] for c in s_ahead["cards"]]
    assert s_ahead["event_kind"] == "REVIEW_AHEAD"

    # Preset 3: preview_new (non-destructive CRAM)
    s_preview = build_custom_study_session(cards, preset="preview_new", limit=1)
    assert len(s_preview["cards"]) == 1
    assert s_preview["cards"][0]["state"] == "new"
    assert s_preview["event_kind"] == "CRAM"
    assert s_preview["reschedule"] is False

    # Preset 4: cram_flagged_or_leech
    s_clinic = build_custom_study_session(cards, preset="cram_flagged_or_leech", limit=10)
    assert [c["card_id"] for c in s_clinic["cards"]] == ["lapsed_1", "lapsed_2"]

    # Preset 5: increase_new_quota
    s_new_boost = build_custom_study_session(cards, preset="increase_new_quota", extra_new=2)
    assert [c["card_id"] for c in s_new_boost["cards"]] == ["new_1", "new_2"]
    assert s_new_boost["reschedule"] is True


# ============================================================================
# 7. End-to-End Service Integration (`AnkiStudioService`)
# ============================================================================


def test_service_anki_study_plan_custom_study_and_card_actions() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = AnkiStudioService(db_path=Path(tmpdir) / "planner_e2e.sqlite3", seed_defaults=True)
        decks = svc.list_decks()["decks"]
        assert len(decks) >= 1
        deck_id = decks[0]["id"]

        # 1) Generate 30-day study plan for a 1,000+ card deck
        plan_res = svc.get_anki_study_plan(
            deck_id=deck_id,
            target_days=30,
            daily_minutes_budget=35,
            desired_retention=0.90,
        )
        assert plan_res["ok"] is True
        assert plan_res["plan"]["total_cards"] >= 1000
        assert plan_res["plan"]["recommended_daily_new"] >= 20
        assert len(plan_res["plan"]["daily_forecast"]) == 30

        # 2) Apply Anki card action (flag=1, suspend, unsuspend) on a real card in SQLite
        due_cards = svc.get_due_cards(deck_id=deck_id, limit=5)["cards"]
        first_card_id = due_cards[0]["id"]
        flag_res = svc.apply_card_anki_action(card_id=first_card_id, action="set_flag", flag=1)
        assert flag_res["ok"] is True
        assert flag_res["card"]["flag"] == 1

        # 3) Build custom study session ("cram_flagged_or_leech") and verify the flagged card is returned
        custom_res = svc.build_anki_custom_study(
            deck_id=deck_id,
            preset="cram_flagged_or_leech",
            limit=20,
        )
        assert custom_res["ok"] is True
        assert any(c["id"] == first_card_id for c in custom_res["cards"])

        # 4) Verify BuryToday expires automatically on next-day rollover (`buried_until_date`)
        svc.store.apply_anki_card_action(
            card_id=first_card_id,
            action="bury",
            as_of_iso="2026-10-23T12:00:00+00:00",
        )
        due_same_day = svc.store.get_due_cards(deck_id=deck_id, as_of_iso="2026-10-23T18:00:00+00:00")
        assert all(c["id"] != first_card_id for c in due_same_day)
        due_next_day = svc.store.get_due_cards(deck_id=deck_id, as_of_iso="2026-10-24T09:00:00+00:00")
        assert any(c["id"] == first_card_id for c in due_next_day)


def test_viewmodel_js_anki_planner_and_power_features_parity() -> None:
    """Verify Web/PWA ViewModel (`viewmodel.js` & `docs/viewmodel.js`) exports and executes Anki v3 planner & card actions."""
    import json
    import subprocess

    root_dir = Path(__file__).resolve().parents[1]
    static_vm = root_dir / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    docs_vm = root_dir / "docs" / "viewmodel.js"
    assert static_vm.read_bytes() == docs_vm.read_bytes()

    script = f"""
    const vm = require({json.dumps(str(static_vm))});
    const plan = vm.computeAnkiStudyPlan({{
      total_cards: 1200,
      new_count: 1000,
      learning_count: 20,
      review_due_count: 80,
      target_days: 30,
      daily_minutes_budget: 45,
      desired_retention: 0.90
    }});
    if (plan.status !== "FEASIBLE") throw new Error("Expected FEASIBLE, got " + plan.status);
    if (plan.daily_forecast.length !== 30) throw new Error("Expected 30 forecast days");

    const q = vm.buildAnkiV3DailyQueue([
      {{ card_id: "c1", state: "review", due_days: -2, s: 2.0, d: 6.0, tags: ["concept:g1"] }},
      {{ card_id: "c2", state: "new", due_days: 0, s: 0.0, d: 5.0, tags: ["concept:g1"] }},
      {{ card_id: "c3", state: "new", due_days: 0, s: 0.0, d: 5.0, tags: ["concept:g2"] }}
    ], {{ new_per_day: 10, max_reviews_per_day: 50, bury_new_siblings: true }});
    if (!q.buried_sibling_ids.includes("c2")) throw new Error("Expected c2 buried as sibling of c1");

    const flagged = vm.applyAnkiCardAction({{ card_id: "c1", state: "review", tags: [] }}, "set_flag", {{ flag: 1 }});
    if (flagged.flag !== 1 || !flagged.tags.includes("flag:1")) throw new Error("Expected flag:1");

    const custom = vm.buildCustomStudySession([flagged], {{ preset: "cram_flagged_or_leech", limit: 10 }});
    if (custom.count !== 1 || custom.reschedule !== false) throw new Error("Expected 1 non-rescheduling cram card");

    const kBury = vm.mapKeyboardShortcut("-", false, false, "teen");
    const kSusp = vm.mapKeyboardShortcut("@", false, false, "teen");
    const kFlag = vm.mapKeyboardShortcut("f", false, false, "teen");
    if (!kBury || kBury.action !== "bury") throw new Error("Expected bury shortcut");
    if (!kSusp || kSusp.action !== "suspend") throw new Error("Expected suspend shortcut");
    if (!kFlag || kFlag.action !== "cycle_flag") throw new Error("Expected cycle_flag shortcut");
    console.log("VM_ANKI_PLANNER_OK");
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    assert "VM_ANKI_PLANNER_OK" in proc.stdout

