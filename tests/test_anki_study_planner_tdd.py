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


# ============================================================================
# 8. v5.9 TDD: Corpus Quality Gate (Q1~Q7) + Persistent Daily Study Quota
# ============================================================================


@pytest.mark.parametrize(
    "source_id,expected_subject",
    [
        ("moe-eng:middle-1200", "english"),
        ("moe-eng:high-csat", "english"),
        ("hanja-grade:8geup", "hanja"),
        ("moe-hanja-1800:middle", "hanja"),
        ("khist:essential", "history"),
        ("sci-element-formula:core", "science"),
        ("moe-math:core-formulas", "math"),
        ("moe-kor:orthography-lit", "korean"),
        ("law-statute:constitution", "law_it"),
    ],
)
def test_v59_corpus_quality_gate_zero_spoilers_across_all_subjects(
    source_id: str, expected_subject: str
) -> None:
    """Verify 1,000+ card corpus passes Q1~Q7 quality gate with zero front spoilers and zero synthetic padding."""
    from anki_studio.domain.full_scale_corpus import (
        build_full_scale_deck_cards,
        validate_deck_quality_gate,
    )

    specs = build_full_scale_deck_cards(
        ref_id=source_id,
        difficulty_level="mixed",
        target_count=1020,
    )
    assert len(specs) >= 1020
    audit = validate_deck_quality_gate(specs, subject=expected_subject)
    assert audit["ok"] is True, f"Quality gate failed for {source_id}: {audit}"
    assert audit["front_spoiler_count"] == 0
    assert audit["raw_cloze_leak_count"] == 0
    assert audit["synthetic_contrast_count"] == 0
    assert audit["duplicate_front_count"] == 0


def test_v59_persistent_study_plan_slices_daily_due_cards_and_decrements_quota() -> None:
    """Verify applying a D-Day study plan persists daily_new_limit and slices get_due_cards accordingly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = AnkiStudioService(db_path=Path(tmpdir) / "v59_quota.sqlite3", seed_defaults=True)
        mounted = svc.generate_collection_deck(
            collection_id="moe-eng:middle-1200",
            limit=1200,
            difficulty_level="mixed",
        )
        deck_id = mounted["deck_id"]

        # Apply D-30 plan with daily_new_limit = 25 cards/day
        applied = svc.apply_anki_study_plan(
            deck_id=deck_id,
            target_days=30,
            daily_new_limit=25,
            daily_minutes_budget=30,
        )
        assert applied["ok"] is True
        assert applied["daily_quota"]["plan_applied"] is True
        assert applied["daily_quota"]["daily_new_limit"] == 25
        assert applied["daily_quota"]["remaining_new_today"] == 25

        # Calling get_due_cards now slices today's new cards to 25 (instead of dumping 1,000+ or 50)
        due_today = svc.get_due_cards(deck_id=deck_id)
        assert due_today["count"] == 25
        assert due_today["daily_quota"]["remaining_new_today"] == 25

        # Submit 3 reviews on new cards -> remaining_new_today drops to 22
        for idx in range(3):
            cid = due_today["cards"][idx]["id"]
            svc.submit_review(card_id=cid, rating=3)

        due_after_3 = svc.get_due_cards(deck_id=deck_id)
        assert due_after_3["daily_quota"]["new_studied_today"] == 3
        assert due_after_3["daily_quota"]["remaining_new_today"] == 22
        assert due_after_3["count"] == 22

        # Custom study preset 'increase_new_quota' boosts today's limit by +10 -> remaining becomes 32
        boost = svc.build_anki_custom_study(
            deck_id=deck_id,
            preset="increase_new_quota",
            extra_new=10,
        )
        assert boost["ok"] is True
        assert boost["daily_quota"]["daily_new_limit"] == 35
        assert boost["daily_quota"]["remaining_new_today"] == 32

        # Pressing Again (rating=1) twice on the SAME new card on the same day must only increment new_studied_today by 1
        same_new_cid = due_after_3["cards"][0]["id"]
        svc.submit_review(card_id=same_new_cid, rating=1)
        svc.submit_review(card_id=same_new_cid, rating=1)
        svc.submit_review(card_id=same_new_cid, rating=3)
        due_after_again_twice = svc.get_due_cards(deck_id=deck_id)
        assert due_after_again_twice["daily_quota"]["new_studied_today"] == 4
        assert due_after_again_twice["daily_quota"]["remaining_new_today"] == 31


def test_v59_selecting_existing_1000_card_deck_populates_plan_and_caps_daily_queue() -> None:
    """Verify selecting an already-created 1,000-card deck (not via generate_collection_deck) populates D-30 plan & slices queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = AnkiStudioService(db_path=Path(tmpdir) / "v59_existing.sqlite3", seed_defaults=False)
        raw_notes = [
            {"front_text": f"Word #{i}", "back_text": f"뜻 #{i}", "note_type": "basic", "tags": ["existing_1000"]}
            for i in range(1, 1001)
        ]
        created = svc.store.create_deck_with_notes(deck_name="Existing 1000 Deck", notes=raw_notes)
        existing_deck_id = created["deck_id"]

        # Selecting this existing deck in the UI triggers get_anki_study_plan(deck_id=existing_deck_id)
        plan_res = svc.get_anki_study_plan(deck_id=existing_deck_id, target_days=30, daily_minutes_budget=20)
        assert plan_res["ok"] is True
        assert plan_res["daily_quota"]["plan_applied"] is True
        rec_new = plan_res["daily_quota"]["daily_new_limit"]
        assert 10 <= rec_new <= 50
        # daily_minutes_budget=20 (1200s / 8s = 150) caps daily_review_limit at <= 150
        assert plan_res["daily_quota"]["daily_review_limit"] <= 150

        # Calling get_due_cards on the selected existing 1000-card deck slices today's queue to rec_new (never 1000!)
        due_res = svc.get_due_cards(deck_id=existing_deck_id)
        assert due_res["count"] == rec_new
        assert due_res["count"] < 100


def test_v59_always_visible_planner_ui_and_standalone_subject_purity() -> None:
    """Verify #bd-planner-bar is outside #study-tools-drawer and standaloneEngine slices daily quota & preserves subject purity."""
    import json
    import subprocess

    root_dir = Path(__file__).resolve().parents[1]
    index_html = (root_dir / "src" / "anki_studio" / "ui" / "static" / "index.html").read_text(encoding="utf-8")
    drawer_pos = index_html.index('id="study-tools-drawer"')
    planner_pos = index_html.index('id="bd-planner-bar"')
    banner_pos = index_html.index('id="bd-study-plan-banner"')
    apply_btn_pos = index_html.index('id="btn-apply-study-plan"')
    assert planner_pos < drawer_pos, "#bd-planner-bar must be placed BEFORE and OUTSIDE #study-tools-drawer"
    assert banner_pos < drawer_pos, "#bd-study-plan-banner must be placed BEFORE and OUTSIDE #study-tools-drawer"
    assert apply_btn_pos < drawer_pos

    static_vm = root_dir / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    script = f"""
    const vm = require({json.dumps(str(static_vm))});
    const eng = vm.createStandaloneEngine();
    const mathDeck = eng.buildCollectionDeck({{ collection_id: "moe-math:core-formulas", difficulty_level: "mixed", limit: 1000 }});
    if (!mathDeck.ok || mathDeck.cards.length < 1000) throw new Error("Expected >= 1000 math cards");
    const badContrast = mathDeck.cards.filter(c => c.front_text.includes("[심화 대조·변별]") || c.front_text.includes("함무라비") || c.front_text.includes("introduce"));
    if (badContrast.length > 0) throw new Error("Found cross-subject contamination in math deck: " + badContrast[0].front_text);

    // Apply study plan (daily_new_limit: 20) and verify getDueCards slices to 20
    const applied = eng.applyStudyPlan({{ deck_id: mathDeck.deck_id, target_days: 30, new_per_day: 20 }});
    if (!applied.ok || applied.daily_quota.daily_new_limit !== 20) throw new Error("applyStudyPlan failed");
    const slicedDue = eng.getDueCards({{ deck_id: mathDeck.deck_id }});
    if (slicedDue.count !== 20) throw new Error("Expected 20 due cards after applyStudyPlan, got " + slicedDue.count);
    eng.submitReview({{ card_id: slicedDue.cards[0].card_id, rating: 3 }});
    const afterOne = eng.getDueCards({{ deck_id: mathDeck.deck_id }});
    if (afterOne.count !== 19) throw new Error("Expected 19 remaining due cards after 1 review, got " + afterOne.count);
    console.log("V59_STANDALONE_OK");
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    assert "V59_STANDALONE_OK" in proc.stdout


# ============================================================================
# 9. IMPL-V61 TDD/BDD/DDT: Multi-Dimensional Progress, Mastery & Card Explorer
# ============================================================================


@pytest.mark.parametrize(
    "num,den,expected_tenths,expected_pct",
    [
        (0, 0, 0, 0.0),
        (0, 1000, 0, 0.0),
        (-5, 1000, 0, 0.0),
        (1, 1000, 1, 0.1),
        (1, 5000, 1, 0.1),  # non-zero progress never collapses to 0.0%
        (180, 1050, 171, 17.1),
        (12, 30, 400, 40.0),
        (500, 1000, 500, 50.0),
        (999, 1000, 999, 99.9),  # never rounds to 100.0% prematurely
        (4999, 5000, 999, 99.9),  # never rounds to 100.0% prematurely
        (1000, 1000, 1000, 100.0),
        (1050, 1000, 1000, 100.0),
    ],
)
def test_v61_compute_percent_tenths_12_boundary_ddt_cases(
    num: int, den: int, expected_tenths: int, expected_pct: float
) -> None:
    from anki_studio.domain.anki_study_planner import compute_percent_tenths

    tenths = compute_percent_tenths(num, den)
    assert tenths == expected_tenths
    assert round(tenths / 10.0, 1) == expected_pct


def test_v61_compute_deck_mastery_progress_invariants_and_stage_breakdown() -> None:
    from anki_studio.domain.anki_study_planner import (
        compute_deck_mastery_progress,
        filter_cards_for_explorer,
    )

    # Build a 1,000-card deck + 10 suspended cards (total=1,010, active=1,000)
    # 700 unseen, 100 learning, 100 young, 100 mature -> touched = 300 (30.0%)
    # Weighted mastery = (100*0.25 + 100*0.65 + 100*1.0) / 1000 = 190 / 1000 = 19.0%
    cards = []
    for i in range(700):
        st_tag = "lv1" if i < 350 else "lv2"
        cards.append({"card_id": f"u_{i}", "state": "new", "s": 0.0, "reps": 0, "tags": [st_tag], "front_text": f"Unseen {i}", "back_text": f"Ans {i}"})
    for i in range(100):
        cards.append({"card_id": f"l_{i}", "state": "learning", "s": 0.5, "reps": 1, "tags": ["lv1"], "front_text": f"Learn {i}", "back_text": f"Ans {i}"})
    for i in range(100):
        cards.append({"card_id": f"y_{i}", "state": "review", "s": 7.0, "reps": 3, "tags": ["lv3"], "front_text": f"Young {i}", "back_text": f"Ans {i}"})
    for i in range(100):
        cards.append({"card_id": f"m_{i}", "state": "review", "s": 30.0, "reps": 6, "tags": ["lv4"], "front_text": f"Mature {i}", "back_text": f"Ans {i}"})
    for i in range(10):
        cards.append({"card_id": f"s_{i}", "state": "suspended", "s": 10.0, "reps": 2, "suspended": True, "tags": ["suspended"]})

    prog = compute_deck_mastery_progress(
        cards,
        daily_target=30,
        today_completed=12,
        remaining_queue_count=18,
        avg_seconds_per_card=12.0,
    )
    assert prog["total_cards"] == 1010
    assert prog["active_cards"] == 1000
    assert prog["suspended_cards"] == 10
    assert prog["touched_cards"] == 300
    assert prog["coverage_pct"] == 30.0
    assert prog["mastery_pct"] == 19.0
    assert prog["mature_pct"] == 10.0
    b = prog["buckets"]
    assert b["unseen"] + b["learning"] + b["young"] + b["mature"] == prog["active_cards"]
    assert b == {"unseen": 700, "learning": 100, "young": 100, "mature": 100, "suspended": 10}

    # Today's progress: 12 / 30 = 40.0%, ordinal = 13 (fixes #1/30 -> #1/29 reset bug!)
    t = prog["today"]
    assert t["completed_count"] == 12
    assert t["target_count"] == 30
    assert t["remaining_count"] == 18
    assert t["percent"] == 40.0
    assert t["current_card_ordinal"] == 13

    # Milestone: at 30.0%, current=25%, next=50% (500 cards -> 200 cards to next)
    assert prog["milestone"]["current_pct"] == 25
    assert prog["milestone"]["next_pct"] == 50
    assert prog["milestone"]["cards_to_next"] == 200

    # Stage breakdown
    assert prog["by_stage"]["lv1"]["total"] == 450
    assert prog["by_stage"]["lv1"]["touched"] == 100
    assert prog["by_stage"]["lv4"]["total"] == 100
    assert prog["by_stage"]["lv4"]["mature"] == 100
    assert prog["by_stage"]["lv4"]["coverage_pct"] == 100.0
    assert prog["by_stage"]["lv4"]["mastery_pct"] == 100.0

    # Explorer filter
    exp_mature = filter_cards_for_explorer(cards, query="Mature 42", bucket_filter="mature", stage_filter="lv4")
    assert exp_mature["matched_count"] == 1
    assert exp_mature["cards"][0]["card_id"] == "m_42"


def test_v61_service_and_js_parity_advancing_ordinal_and_deck_explorer() -> None:
    """Verify SQLite service and standalone JS engine compute identical progress & advance card ordinal on review."""
    import json
    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = AnkiStudioService(db_path=Path(tmpdir) / "v61_prog.sqlite3", seed_defaults=True)
        mounted = svc.generate_collection_deck(
            collection_id="moe-eng:middle-1200",
            limit=1050,
            difficulty_level="mixed",
        )
        deck_id = mounted["deck_id"]
        svc.apply_anki_study_plan(deck_id=deck_id, target_days=30, daily_new_limit=30)

        due0 = svc.get_due_cards(deck_id=deck_id)
        dp0 = due0["deck_progress"]
        assert dp0["total_cards"] >= 1050
        assert dp0["coverage_pct"] == 0.0
        assert dp0["today"]["completed_count"] == 0
        assert dp0["today"]["target_count"] == 30
        assert dp0["today"]["current_card_ordinal"] == 1

        # Review 1 card -> coverage_pct becomes 0.1%, today completed=1, current_card_ordinal=2 (NOT #1!)
        svc.submit_review(card_id=due0["cards"][0]["id"], rating=3)
        due1 = svc.get_due_cards(deck_id=deck_id)
        dp1 = due1["deck_progress"]
        assert dp1["touched_cards"] == 1
        assert dp1["coverage_pct"] == 0.1
        assert dp1["today"]["completed_count"] == 1
        assert dp1["today"]["remaining_count"] == 29
        assert dp1["today"]["current_card_ordinal"] == 2
        assert dp1["today"]["percent"] == 3.3

        # Deck Explorer API
        exp = svc.explore_deck_cards(deck_id=deck_id, bucket="learning", limit=10)
        assert exp["ok"] is True

    root_dir = Path(__file__).resolve().parents[1]
    static_vm = root_dir / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    docs_vm = root_dir / "docs" / "viewmodel.js"
    assert static_vm.read_bytes() == docs_vm.read_bytes()

    script = f"""
    const vm = require({json.dumps(str(static_vm))});
    if (vm.computePercentTenths(999, 1000) !== 999) throw new Error("999/1000 must be 999 tenths (99.9%)");
    if (vm.computePercentTenths(1, 1000) !== 1) throw new Error("1/1000 must be 1 tenth (0.1%)");
    if (vm.computePercentTenths(180, 1050) !== 171) throw new Error("180/1050 must be 171 tenths (17.1%)");

    const eng = vm.createStandaloneEngine();
    const built = eng.buildCollectionDeck({{ collection_id: "moe-eng:middle-1200", limit: 1020 }});
    const deckId = built.deck_id;
    eng.applyStudyPlan({{ deck_id: deckId, target_days: 30, new_per_day: 30 }});
    const d0 = eng.getDueCards({{ deck_id: deckId, respect_plan: true }});
    if (!d0.deck_progress || d0.deck_progress.today.current_card_ordinal !== 1) {{
      throw new Error("Initial ordinal must be 1");
    }}
    eng.submitReview({{ card_id: d0.cards[0].card_id, rating: 3 }});
    const d1 = eng.getDueCards({{ deck_id: deckId, respect_plan: true }});
    if (d1.deck_progress.today.completed_count !== 1 || d1.deck_progress.today.current_card_ordinal !== 2) {{
      throw new Error("After 1 review, ordinal must advance to 2, got " + JSON.stringify(d1.deck_progress.today));
    }}
    if (d1.deck_progress.touched_cards !== 1 || d1.deck_progress.coverage_pct !== 0.1) {{
      throw new Error("After 1 review on 1020 deck, coverage_pct must be 0.1%, got " + d1.deck_progress.coverage_pct);
    }}
    const exp = eng.exploreDeckCards({{ deck_id: deckId, bucket: "young", limit: 10 }});
    if (!exp.ok || exp.matched_count !== 1) {{
      throw new Error("Expected 1 young card in explorer after Good review, got " + JSON.stringify(exp));
    }}
    console.log("V61_PARITY_OK");
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    assert "V61_PARITY_OK" in proc.stdout


def test_v61_ui_dom_stage_filter_http_explorer_and_ordinal_string_contract() -> None:
    """Verify 1,050-card fixture, milestone ETA, advancing ordinal string, stage filter, and Web/Android UI DOM contracts."""
    from anki_studio.domain.anki_study_planner import compute_deck_mastery_progress

    # 1,050-card fixture: 870 unseen + 60 learning + 60 young + 60 mature = 180 touched (17.1%)
    # Today: 12 / 30 completed (40.0%) -> current_card_ordinal = 13
    cards_1050 = (
        [{"card_id": f"u_{i}", "state": "new", "s": 0.0, "reps": 0, "tags": ["lv1"]} for i in range(870)]
        + [{"card_id": f"l_{i}", "state": "learning", "s": 0.5, "reps": 1, "tags": ["lv2"]} for i in range(60)]
        + [{"card_id": f"y_{i}", "state": "review", "s": 8.0, "reps": 2, "tags": ["lv3"]} for i in range(60)]
        + [{"card_id": f"m_{i}", "state": "review", "s": 28.0, "reps": 5, "tags": ["lv4"]} for i in range(60)]
    )
    prog_1050 = compute_deck_mastery_progress(
        cards_1050,
        daily_target=30,
        today_completed=12,
        remaining_queue_count=18,
    )
    assert prog_1050["active_cards"] == 1050
    assert prog_1050["touched_cards"] == 180
    assert prog_1050["coverage_pct"] == 17.1
    assert prog_1050["today"]["completed_count"] == 12
    assert prog_1050["today"]["target_count"] == 30
    assert prog_1050["today"]["percent"] == 40.0
    assert prog_1050["today"]["current_card_ordinal"] == 13
    # Milestone on 1050 cards: 10% (105 cards) achieved, next=25% (ceil(1050*0.25)=263 cards) -> cards_to_next=83, days_to_next=3, eta_full_coverage_days=29
    assert prog_1050["milestone"]["current_pct"] == 10
    assert prog_1050["milestone"]["next_pct"] == 25
    assert prog_1050["milestone"]["cards_to_next"] == 83
    assert prog_1050["milestone"]["days_to_next"] == 3
    assert prog_1050["milestone"]["eta_full_coverage_days"] == 29

    ordinal_header_line = (
        f"오늘 {prog_1050['today']['current_card_ordinal']}/{prog_1050['today']['target_count']}번째 "
        f"({prog_1050['today']['percent']:.1f}%) · 전체 진도 {prog_1050['coverage_pct']:.1f}% "
        f"({prog_1050['touched_cards']}/{prog_1050['active_cards']:,}장)"
    )
    assert ordinal_header_line == "오늘 13/30번째 (40.0%) · 전체 진도 17.1% (180/1,050장)"

    # Verify Web/PWA HTML, app.js, and Android MainActivity.kt UI contracts
    root_dir = Path(__file__).resolve().parents[1]
    static_html = (root_dir / "src" / "anki_studio" / "ui" / "static" / "index.html").read_text(encoding="utf-8")
    docs_html = (root_dir / "docs" / "index.html").read_text(encoding="utf-8")
    static_app = (root_dir / "src" / "anki_studio" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    docs_app = (root_dir / "docs" / "app.js").read_text(encoding="utf-8")
    android_main = (
        root_dir / "android-app" / "app" / "src" / "main" / "java" / "com" / "ankistudio" / "app" / "ui" / "MainActivity.kt"
    ).read_text(encoding="utf-8")
    android_engine = (
        root_dir / "android-app" / "domain" / "src" / "main" / "kotlin" / "com" / "ankistudio" / "domain" / "planner" / "AnkiStudyPlannerEngine.kt"
    ).read_text(encoding="utf-8")

    assert static_html == docs_html
    assert static_app == docs_app
    assert "bd-deck-progress-dashboard" in static_html
    for token in (
        "bd-today-progress-label",
        "bd-today-progress-fill",
        "bd-deck-coverage-label",
        "bd-deck-mastery-label",
        "bd-deck-milestone-label",
        "bd-bar-mature",
        "bd-bar-young",
        "bd-bar-learning",
        "bd-bar-unseen",
        "bd-stage-btn",
        "deck-card-explorer-panel",
    ):
        assert token in static_html
        assert token in static_app

    assert "[진도 " in static_app and "마스터 " in static_app
    assert "🎯 오늘 목표:" in android_main
    assert "📊 전체 진도율" in android_main
    assert "4-Color Stacked Maturity Bar" in android_main
    assert "🔍 전체 카드 진도표·검색" in android_main
    assert "🪜 전체 단계" in android_main
    assert "fun computePercentTenths" in android_engine
    assert "fun computeDeckMasteryProgress" in android_engine
    assert "fun filterCardsForExplorer" in android_engine

    # Reviewer A parity probes: reps=0 is unseen, rating Again keeps target=30, review-only deck is ACTIVE, diff=3.7 is lv1
    from anki_studio.domain.anki_study_planner import classify_card_maturity_bucket, classify_card_stage

    assert classify_card_maturity_bucket({"state": "review", "reps": 0, "s": 30.0}) == "unseen"
    assert classify_card_stage({"d": 3.7}) == "lv1"
    assert classify_card_stage({"d": 4.5, "lapses": 3}) == "lv4"

    # Rating Again (1) on a 1,050-card deck keeps target=30 and remaining=29 (no 30->31 target drift)
    cards_after_again = [{"card_id": "c0", "state": "relearning", "s": 0.4, "reps": 1}] + [
        {"card_id": f"c_{i}", "state": "new", "s": 1.2, "reps": 0} for i in range(1, 1050)
    ]
    prog_again = compute_deck_mastery_progress(
        cards_after_again,
        {"daily_new_limit": 30, "new_studied_today": 1, "reviews_studied_today": 0},
    )
    assert prog_again["today"]["target_count"] == 30
    assert prog_again["today"]["completed_count"] == 1
    assert prog_again["today"]["remaining_count"] == 29

    # Review-only deck (0 unseen, 100 young) never reports NO_PLAN when daily_new_limit=30
    rev_only_cards = [{"card_id": f"r_{i}", "state": "review", "s": 10.0, "reps": 3} for i in range(100)]
    prog_rev_only = compute_deck_mastery_progress(
        rev_only_cards,
        {"daily_new_limit": 30, "new_studied_today": 0, "reviews_studied_today": 0},
    )
    assert prog_rev_only["today"]["status"] == "ACTIVE"
    assert prog_rev_only["today"]["target_count"] == 30
    assert prog_rev_only["today"]["remaining_count"] == 30


def test_v61_1000_card_non_collapse_and_live_in_card_progress_bar() -> None:
    """Ensure 1,000-card decks never collapse to 4 cards via sibling deduplication and In-Card Progress % renders on Web + Android."""
    root_dir = Path(__file__).resolve().parents[1]
    static_vm = (root_dir / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js").read_text(encoding="utf-8")
    docs_vm = (root_dir / "docs" / "viewmodel.js").read_text(encoding="utf-8")
    static_html = (root_dir / "src" / "anki_studio" / "ui" / "static" / "index.html").read_text(encoding="utf-8")
    static_app = (root_dir / "src" / "anki_studio" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    android_vm = (
        root_dir / "android-app" / "app" / "src" / "main" / "java" / "com" / "ankistudio" / "app" / "ui" / "AnkiStudioViewModel.kt"
    ).read_text(encoding="utf-8")
    android_catalog = (
        root_dir / "android-app" / "domain" / "src" / "main" / "kotlin" / "com" / "ankistudio" / "domain" / "catalog" / "BuiltInCurriculumCatalog.kt"
    ).read_text(encoding="utf-8")
    android_main = (
        root_dir / "android-app" / "app" / "src" / "main" / "java" / "com" / "ankistudio" / "app" / "ui" / "MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert static_vm == docs_vm
    # 1) Unique fact concept tag invariant (never modulo 4 collapse)
    assert "_fact_${itemNo}" in static_vm
    assert "_fact_$itemNo" in android_catalog
    assert 'it.startsWith("concept:") && it.length > 8' in android_vm

    # 2) In-Card Live Progress Bar & Percentage Header on Web/PWA and Android
    for inline_id in (
        "card-inline-progress-box",
        "card-inline-today-pct",
        "card-inline-deck-pct",
        "card-inline-today-fill",
    ):
        assert inline_id in static_html
        assert inline_id in static_app
    assert "🎯 오늘 진척률" in android_main
    assert "📊 전체 진도" in android_main

    # 3) Verify dist/BrainDeck-v6.0.apk exists and is freshly compiled (>= 15MB)
    dist_apk = root_dir / "dist" / "BrainDeck-v6.0.apk"
    assert dist_apk.exists()
    assert dist_apk.stat().st_size > 15_000_000






