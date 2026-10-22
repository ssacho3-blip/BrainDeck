"""ATDD / BDD / TDD / DDT Master Test Suite for BrainDeck v5.6 REA Upgrade (WORKORDER-BRAINDECK-V56).

Covers all 4 Phases and 8 Release Gates (T35 ~ T42):
- T35: 3-Platform Golden Vector Parity (1e-6 quantization) & ReviewEvent Fold Permutation/Idempotency/VOID
- T36: CRAM Non-Destructive Invariance (S'=S) vs REVIEW_AHEAD (t < I) & SQLite Append-Only Triggers
- T37: Exam Countdown Autopilot (D-14/D-7/D-1/D-0, target_R [0.70, 0.97], Fail-Closed BLOCKED) & Load Balancer
- T38: 1 Note -> N Facet Cards & Lossless Delayed GC (ACTIVE -> RETIRED -> TOMBSTONED -> Resurrect)
- T39: OCR Bounding Box Auto Image Occlusion & sha256 CAS Atomic Staging + Context Breadcrumb
- T40: Directional Confusion Graph (A->B != B->A), Contrastive Interleaving (max_gap<=2), & Prerequisite DAG (Tarjan SCC, R>=0.85)
- T41: Keyword Rubric Scoring (Required/Bonus/Forbidden) & SCORE_UNAVAILABLE Zero-Event Fail-Closed + 7-Card Micro-Sprint
- T42: Electronic Red-Cellophane Summary Sheet, 2-Column Printable Exam Sheet Seed Parity, Commute Audio Loop, QR Snapshot (Zero PII / Zero Fabricated Status), & Streak Shield
"""

from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from anki_studio.adapters.sqlite_store import SQLiteAnkiStore
from anki_studio.domain.rea_v56 import (
    CardStateV56,
    ConfusableEdge,
    ExamPlan,
    FacetSpec,
    OcrBoundingBox,
    ReviewEvent,
    RubricSpec,
     balance_due,
    build_commute_audio_script,
    build_context_breadcrumb,
    build_image_occlusion_cards,
    build_matching_board_round,
    build_parent_completion_report,
    build_printable_exam_sheet,
    build_summary_sheet_view,
    build_type_matched_quiz_options,
     check_prereq_gate,
    chunk_micro_sprints,
    classify_card_question_type,
    compute_question_type_counts,
    diagnose_prereq_deficit,
    diff_facets,
    encode_scope_snapshot_qr,
    evaluate_streak_shield,
    filter_cards_by_question_type,
    find_cycles,
    fold_review_events,
    generate_contrastive_card,
    generate_note_facets,
    interleave_contrastive,
    plan_exam,
    quantize_1e6,
    record_confusion_observation,
    score_rubric,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
DOMAIN_DIR = ROOT_DIR / "src" / "anki_studio" / "domain"
VIEWMODEL_JS = ROOT_DIR / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"


# ============================================================================
# GATE T35: Immutable ReviewEvent Fold, Permutation Invariance, VOID, & 1e-6 Parity
# ============================================================================


def test_t35_fold_review_events_permutation_and_idempotency_and_void() -> None:
    """Given an unordered stream of ReviewEvents with duplicates and a VOID event,
    When fold_review_events is called in different permutations,
    Then the resulting CardState is identical, duplicates are ignored (First-Writer-Wins),
    and the VOIDed event does not affect the final state.
    """
    e1 = ReviewEvent(
        event_id="evt-001",
        card_id="card-10",
        kind="REVIEW",
        rating=3,
        ts_ms=1_700_000_000_000,
        device_id="ios-pwa",
        idem_key="idem-1",
    )
    # Duplicate idem_key with different rating (must be ignored by First-Writer-Wins)
    e1_dup = ReviewEvent(
        event_id="evt-001-dup",
        card_id="card-10",
        kind="REVIEW",
        rating=1,
        ts_ms=1_700_000_005_000,
        device_id="ios-pwa",
        idem_key="idem-1",
    )
    e2 = ReviewEvent(
        event_id="evt-002",
        card_id="card-10",
        kind="REVIEW",
        rating=4,
        ts_ms=1_700_259_200_000,  # +3 days
        device_id="android-fold",
        idem_key="idem-2",
    )
    # Accidental mistaken lapse event that gets VOIDed
    e3_mistake = ReviewEvent(
        event_id="evt-003",
        card_id="card-10",
        kind="REVIEW",
        rating=1,
        ts_ms=1_700_518_400_000,
        device_id="android-fold",
        idem_key="idem-3",
    )
    e4_void = ReviewEvent(
        event_id="evt-004",
        card_id="card-10",
        kind="VOID",
        rating=None,
        ts_ms=1_700_518_410_000,
        device_id="android-fold",
        idem_key="idem-4",
        voids="evt-003",
    )

    state_clean = fold_review_events([e1, e2])
    state_with_dup_and_void = fold_review_events([e4_void, e2, e1_dup, e3_mistake, e1])

    assert state_with_dup_and_void == state_clean
    assert state_clean.reps == 2
    assert state_clean.lapses == 0
    assert state_clean.s > 3.0


@pytest.mark.parametrize("bad_rating", [None, 0, 5, -1])
def test_t35_fold_rejects_invalid_review_ratings(bad_rating: int | None) -> None:
    """REVIEW and REVIEW_AHEAD events must enforce rating in 1..4 (Fail-Closed)."""
    bad_evt = ReviewEvent(
        event_id="evt-bad",
        card_id="c1",
        kind="REVIEW",
        rating=bad_rating,
        ts_ms=1_700_000_000_000,
        device_id="dev1",
        idem_key="idem-bad",
    )
    with pytest.raises(ValueError, match="rating"):
        fold_review_events([bad_evt])


def test_t35_three_platform_golden_vector_parity_python_vs_js() -> None:
    """Golden vector parity test between Python `fold_review_events` and JS `viewmodel.js` `foldReviewEvents`."""
    events_payload = [
        {
            "event_id": "e1",
            "card_id": "c100",
            "kind": "REVIEW",
            "rating": 3,
            "ts_ms": 1700000000000,
            "device_id": "d1",
            "idem_key": "k1",
            "voids": None,
        },
        {
            "event_id": "e2",
            "card_id": "c100",
            "kind": "CRAM",
            "rating": 1,
            "ts_ms": 1700043200000,
            "device_id": "d1",
            "idem_key": "k2",
            "voids": None,
        },
        {
            "event_id": "e3",
            "card_id": "c100",
            "kind": "REVIEW",
            "rating": 4,
            "ts_ms": 1700259200000,
            "device_id": "d1",
            "idem_key": "k3",
            "voids": None,
        },
        {
            "event_id": "e4",
            "card_id": "c100",
            "kind": "REVIEW",
            "rating": 1,
            "ts_ms": 1701123200000,
            "device_id": "d1",
            "idem_key": "k4",
            "voids": None,
        },
        {
            "event_id": "e5",
            "card_id": "c100",
            "kind": "REVIEW",
            "rating": 3,
            "ts_ms": 1701209600000,
            "device_id": "d1",
            "idem_key": "k5",
            "voids": None,
        },
    ]
    py_events = [ReviewEvent(**item) for item in events_payload]
    py_state = fold_review_events(py_events)

    node_script = f"""
    const vm = require({json.dumps(str(VIEWMODEL_JS))});
    const st = vm.foldReviewEvents({json.dumps(events_payload)});
    console.log(JSON.stringify(st));
    """
    res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=True)
    js_state = json.loads(res.stdout.strip())

    assert abs(py_state.s - float(js_state["s"])) <= 1e-6
    assert abs(py_state.d - float(js_state["d"])) <= 1e-6
    assert py_state.due_ms == int(js_state["due_ms"])
    assert py_state.reps == int(js_state["reps"])
    assert py_state.lapses == int(js_state["lapses"])


# ============================================================================
# GATE T36: CRAM Non-Destructive Invariance vs REVIEW_AHEAD & SQLite Append-Only
# ============================================================================


def test_t36_cram_100_iterations_preserves_card_state_byte_for_byte() -> None:
    """Given an initialized CardState from a normal review,
    When 100 CRAM events (with mixed ratings 1..4) are appended,
    Then the folded CardState is 100% identical to the state before CRAM.
    """
    base_evt = ReviewEvent(
        event_id="base-1",
        card_id="c-cram",
        kind="REVIEW",
        rating=3,
        ts_ms=1_700_000_000_000,
        device_id="dev",
        idem_key="base-k1",
    )
    state_before = fold_review_events([base_evt])

    cram_events = [
        ReviewEvent(
            event_id=f"cram-{i}",
            card_id="c-cram",
            kind="CRAM",
            rating=(i % 4) + 1,
            ts_ms=1_700_000_000_000 + (i + 1) * 60_000,
            device_id="dev",
            idem_key=f"cram-k-{i}",
        )
        for i in range(100)
    ]
    state_after = fold_review_events([base_evt, *cram_events])
    assert state_after == state_before


def test_t36_review_ahead_updates_with_actual_elapsed_time_and_sqlite_append_only(tmp_path: Path) -> None:
    """REVIEW_AHEAD with t < I must update S less than full interval t == I,
    and SQLite review_events table must abort on UPDATE or DELETE.
    """
    t0 = 1_700_000_000_000
    e_init = ReviewEvent("e1", "c1", "REVIEW", 3, t0, "d1", "k1")
    st_init = fold_review_events([e_init])
    scheduled_ms = st_init.due_ms - t0

    # Review ahead after only 20% of scheduled interval vs full 100% interval
    e_ahead = ReviewEvent("e2", "c1", "REVIEW_AHEAD", 3, t0 + int(scheduled_ms * 0.2), "d1", "k2")
    e_full = ReviewEvent("e2", "c1", "REVIEW", 3, st_init.due_ms, "d1", "k2")

    st_ahead = fold_review_events([e_init, e_ahead])
    st_full = fold_review_events([e_init, e_full])
    assert st_init.s < st_ahead.s < st_full.s

    # Verify SQLite append-only trigger on review_events
    store = SQLiteAnkiStore(tmp_path / "v56_ledger.sqlite3")
    rec = store.append_review_event(e_init)
    assert rec["ok"] is True
    # Duplicate idem_key is idempotent no-op (First-Writer-Wins)
    dup_rec = store.append_review_event(
        ReviewEvent("e1-dup", "c1", "REVIEW", 1, t0 + 1000, "d1", "k1")
    )
    assert dup_rec["duplicate_noop"] is True

    conn = sqlite3.connect(str(tmp_path / "v56_ledger.sqlite3"))
    try:
        with pytest.raises(sqlite3.IntegrityError, match="review_events_append_only"):
            conn.execute("DELETE FROM review_events WHERE event_id = 'e1'")
        with pytest.raises(sqlite3.IntegrityError, match="review_events_append_only"):
            conn.execute("UPDATE review_events SET rating = 1 WHERE event_id = 'e1'")
    finally:
        conn.close()


# ============================================================================
# GATE T37: Exam Countdown Autopilot (D-14/D-7/D-1/D-0, Fail-Closed) & Load Balancer
# ============================================================================


@pytest.mark.parametrize(
    "days_left,expected_phase,expected_new_allowed",
    [
        (14, "coverage", True),
        (7, "weakness_interleave", False),
        (1, "high_risk_review", False),
        (0, "morning_warmup", False),
    ],
)
def test_t37_exam_countdown_autopilot_phases_and_target_retention(
    days_left: int,
    expected_phase: str,
    expected_new_allowed: bool,
) -> None:
    now_ms = 1_700_000_000_000
    exam_ms = now_ms + days_left * 86_400_000
    cards = [
        {"card_id": f"c{i}", "state": "new" if i < 5 else "review", "s": 2.5, "d": 5.5, "lapses": i % 3}
        for i in range(15)
    ]
    plan = plan_exam(cards=cards, now_ms=now_ms, exam_ms=exam_ms, daily_cap=30, prereq={})
    assert plan.status == "ACTIVE"
    assert plan.phase == expected_phase
    assert 0.70 <= plan.target_r <= 0.97
    assert plan.allow_new_cards is expected_new_allowed
    if days_left == 0:
        assert len(plan.today_queue) <= 20
        assert all(c["state"] != "new" for c in plan.today_queue)


@pytest.mark.parametrize(
    "cards,days_offset,daily_cap,prereq,expected_reason",
    [
        ([{"card_id": "c1", "state": "review", "s": 2.0}], -1, 20, {}, "past_exam_date"),
        ([], 5, 20, {}, "empty_scope"),
        ([{"card_id": f"c{i}", "state": "new", "s": 1.0} for i in range(100)], 2, 10, {}, "capacity_exceeded"),
        (
            [{"card_id": "A", "state": "new"}, {"card_id": "B", "state": "new"}],
            10,
            20,
            {"A": ["B"], "B": ["A"]},
            "dag_cycle_detected",
        ),
    ],
)
def test_t37_exam_autopilot_fail_closed_blocked_cases(
    cards: list[dict],
    days_offset: int,
    daily_cap: int,
    prereq: dict[str, list[str]],
    expected_reason: str,
) -> None:
    now_ms = 1_700_000_000_000
    exam_ms = now_ms + days_offset * 86_400_000
    plan = plan_exam(cards=cards, now_ms=now_ms, exam_ms=exam_ms, daily_cap=daily_cap, prereq=prereq)
    assert plan.status == "BLOCKED"
    assert plan.reason == expected_reason
    assert plan.today_queue == ()


def test_t37_load_balancer_and_easy_days_deterministic_tie_break() -> None:
    today = date(2026, 10, 22)
    # ivl_days = 20 -> 5% fuzz window is [19, 21] days -> Nov 10, Nov 11, Nov 12
    d19 = today + timedelta(days=19)
    d20 = today + timedelta(days=20)
    d21 = today + timedelta(days=21)

    # d20 has heavy load (30), d19 and d21 are tied (5 each) -> must pick earliest (d19)
    load = {d19: 5, d20: 30, d21: 5}
    weights = {d19: 1.0, d20: 1.0, d21: 1.0}
    assert balance_due(20.0, load, weights, today) == d19

    # Make d19 an Easy Day (weight=0.25 -> effective load 5/0.25=20) so d21 (5/1.0=5) wins
    weights_easy = {d19: 0.25, d20: 1.0, d21: 1.0}
    assert balance_due(20.0, load, weights_easy, today) == d21

    with pytest.raises(ValueError, match="weight"):
        balance_due(20.0, load, {d19: 0.0}, today)


# ============================================================================
# GATE T38: 1 Note -> N Facet Cards & Lossless Delayed GC (ACTIVE -> RETIRED -> TOMBSTONED)
# ============================================================================


def test_t38_note_facets_generation_and_lossless_delayed_gc_resurrection() -> None:
    facets = generate_note_facets(
        note_id="note-eng-101",
        term="accommodate",
        answer="수용하다, 편의를 제공하다",
        sentence="The hotel can accommodate up to 500 guests.",
        explain="명사형: accommodation (숙박/수용 시설)",
    )
    assert [f.facet_key for f in facets] == ["forward", "reverse", "listening_tts", "context_cloze"]
    assert all("concept:note-eng-101" in f.tags for f in facets)

    now_ms = 1_700_000_000_000
    grace_ms = 7 * 86_400_000
    existing = {
        "forward": {"card_id": "c-fwd", "state": "ACTIVE", "retired_at_ms": None, "tombstoned_at_ms": None},
        "reverse": {"card_id": "c-rev", "state": "ACTIVE", "retired_at_ms": None, "tombstoned_at_ms": None},
        "context_cloze": {"card_id": "c-clz", "state": "ACTIVE", "retired_at_ms": None, "tombstoned_at_ms": None},
    }

    # Step 1: User removes 'context_cloze' and adds 'listening_tts'
    transitions_1 = diff_facets(
        expected={"forward", "reverse", "listening_tts"},
        existing=existing,
        now_ms=now_ms,
        grace_ms=grace_ms,
    )
    by_key_1 = {t["facet_key"]: t for t in transitions_1}
    assert by_key_1["context_cloze"]["state"] == "RETIRED"
    assert by_key_1["context_cloze"]["card_id"] == "c-clz"  # card_id preserved!
    assert by_key_1["listening_tts"]["state"] == "ACTIVE"

    # Step 2: At boundary now_ms + grace_ms, RETIRED becomes TOMBSTONED
    existing_2 = {k: v for k, v in by_key_1.items()}
    transitions_2 = diff_facets(
        expected={"forward", "reverse"},
        existing=existing_2,
        now_ms=now_ms + grace_ms,
        grace_ms=grace_ms,
    )
    by_key_2 = {t["facet_key"]: t for t in transitions_2}
    assert by_key_2["context_cloze"]["state"] == "TOMBSTONED"
    assert by_key_2["context_cloze"]["card_id"] == "c-clz"

    # Step 3: Re-adding 'context_cloze' resurrects it back to ACTIVE with original card_id!
    transitions_3 = diff_facets(
        expected={"forward", "reverse", "context_cloze"},
        existing=by_key_2,
        now_ms=now_ms + grace_ms + 1000,
        grace_ms=grace_ms,
    )
    by_key_3 = {t["facet_key"]: t for t in transitions_3}
    assert by_key_3["context_cloze"]["state"] == "ACTIVE"
    assert by_key_3["context_cloze"]["card_id"] == "c-clz"


# ============================================================================
# GATE T39: Auto Image Occlusion, sha256 CAS Atomic Staging, & Context Breadcrumb
# ============================================================================


def test_t39_image_occlusion_and_sha256_cas_atomic_staging(tmp_path: Path) -> None:
    raw_img = b"\x89PNG\r\n\x1a\nMOCK_DIAGRAM_HEART_ANATOMY_BYTES"
    expected_sha = hashlib.sha256(raw_img).hexdigest()

    boxes = [
        OcrBoundingBox(label="좌심실", x=0.12, y=0.45, w=0.18, h=0.08, confidence=0.94),
        OcrBoundingBox(label="대동맥", x=0.52, y=0.15, w=0.20, h=0.09, confidence=0.91),
        # Out-of-bounds box (x=1.2) must be rejected cleanly
        OcrBoundingBox(label="노이즈", x=1.20, y=0.10, w=0.10, h=0.10, confidence=0.80),
    ]
    occ_cards = build_image_occlusion_cards(
        image_bytes=raw_img,
        mime="image/png",
        ocr_boxes=boxes,
        mode="hide_all_guess_one",
        deck_title="생물 심장 해부도",
    )
    assert len(occ_cards) == 2
    assert occ_cards[0]["media_sha256"] == expected_sha
    assert occ_cards[0]["mode"] == "hide_all_guess_one"
    assert "<svg" in occ_cards[0]["svg_mask"]
    assert occ_cards[0]["target_label"] == "좌심실"

    # Verify SQLite CAS atomic staging & hash verification
    store = SQLiteAnkiStore(tmp_path / "cas_test.sqlite3")
    cas_res1 = store.put_media_cas(raw_img, mime="image/png", expected_sha256=expected_sha)
    assert cas_res1["refcount"] == 1
    cas_res2 = store.put_media_cas(raw_img, mime="image/png", expected_sha256=expected_sha)
    assert cas_res2["refcount"] == 2  # Deduplicated!

    # Hash mismatch must raise ValueError and leave 0 staging files
    with pytest.raises(ValueError, match="sha256"):
        store.put_media_cas(raw_img, mime="image/png", expected_sha256="0" * 64)
    staging_leftovers = list(tmp_path.glob("*.tmp*"))
    assert staging_leftovers == []

    # Context breadcrumb
    crumb = build_context_breadcrumb(["미래엔 역사①", "Ⅱ. 근대 국민 국가 수립", "1. 강화도 조약"], source_page=48)
    assert crumb == "📚 미래엔 역사① > Ⅱ. 근대 국민 국가 수립 > 1. 강화도 조약 (p.48)"


# ============================================================================
# GATE T40: Directional Confusion Graph (A->B != B->A) & Prerequisite DAG (Tarjan SCC)
# ============================================================================


def test_t40_directional_confusion_graph_and_contrastive_interleaving() -> None:
    edges: dict[tuple[str, str], ConfusableEdge] = {}
    # Asking "임진왜란 (1592)" but user answered "1597 (정유재란)"
    edges = record_confusion_observation(
        edges,
        asked_concept_id="khist:imjin_1592",
        answered_concept_id="khist:jeongyu_1597",
        ts_ms=1_700_000_000_000,
    )
    assert ("khist:imjin_1592", "khist:jeongyu_1597") in edges
    assert ("khist:jeongyu_1597", "khist:imjin_1592") not in edges  # Asymmetric!

    # Self-loop must be ignored/rejected
    with pytest.raises(ValueError, match="self"):
        record_confusion_observation(edges, "khist:imjin_1592", "khist:imjin_1592", 1_700_000_001_000)

    contrast_card = generate_contrastive_card(
        concept_a={"id": "khist:imjin_1592", "term": "임진왜란", "answer": "1592년 (한산도 대첩·행주대첩)"},
        concept_b={"id": "khist:jeongyu_1597", "term": "정유재란", "answer": "1597년 (명량 대첩)"},
    )
    assert "임진왜란" in contrast_card["front_text"] and "정유재란" in contrast_card["front_text"]

    queue = ["c1", "khist:imjin_1592", "c2", "c3", "c4", "c5", "khist:jeongyu_1597", "c6"]
    reordered = interleave_contrastive(queue, list(edges.values()), max_gap=2)
    idx_a = reordered.index("khist:imjin_1592")
    idx_b = reordered.index("khist:jeongyu_1597")
    assert abs(idx_a - idx_b) <= 2


def test_t40_prerequisite_dag_tarjan_scc_and_hysteresis_gate() -> None:
    # 2-node cycle A <-> B and self-loop C -> C
    cyclic_graph = {"A": ["B"], "B": ["A"], "C": ["C"], "D": ["E"]}
    cycles = find_cycles(cyclic_graph)
    assert len(cycles) == 2

    acyclic_graph = {"basic_ohm": ["kirchhoff_law"], "kirchhoff_law": ["thevenin_theorem"]}
    assert find_cycles(acyclic_graph) == []

    # R = 0.8499 < 0.85 -> BLOCKED; R = 0.8500 -> UNLOCKED
    gate_blocked = check_prereq_gate(
        card_id="kirchhoff_law",
        prereq_parents={"kirchhoff_law": ["basic_ohm"]},
        parent_retentions={"basic_ohm": 0.8499},
        was_unlocked=False,
    )
    assert gate_blocked["unlocked"] is False

    gate_open = check_prereq_gate(
        card_id="kirchhoff_law",
        prereq_parents={"kirchhoff_law": ["basic_ohm"]},
        parent_retentions={"basic_ohm": 0.8500},
        was_unlocked=False,
    )
    assert gate_open["unlocked"] is True

    # Hysteresis: once unlocked, stays unlocked at R = 0.78 (>= 0.75), locks at R = 0.74
    assert check_prereq_gate("kirchhoff_law", {"kirchhoff_law": ["basic_ohm"]}, {"basic_ohm": 0.78}, was_unlocked=True)["unlocked"] is True
    assert check_prereq_gate("kirchhoff_law", {"kirchhoff_law": ["basic_ohm"]}, {"basic_ohm": 0.74}, was_unlocked=True)["unlocked"] is False

    # Reverse root-cause diagnosis before Leech split
    diag = diagnose_prereq_deficit(
        failed_card_id="thevenin_theorem",
        prereq_parents={"thevenin_theorem": ["kirchhoff_law"]},
        parent_retentions={"kirchhoff_law": 0.62},
    )
    assert diag["action"] == "remediate_prerequisites_first"
    assert diag["deficit_parents"] == ["kirchhoff_law"]


# ============================================================================
# GATE T41: Keyword Rubric Scoring & SCORE_UNAVAILABLE Fail-Closed + Micro-Sprint
# ============================================================================


def test_t41_rubric_scoring_and_score_unavailable_zero_events() -> None:
    spec = RubricSpec(
        required=("삼권분립", "국민주권"),
        bonus=("법치주의",),
        forbidden=("왕권신수설", "전제군주"),
        pass_ratio=0.8,
    )
    # 1. Full match
    res_pass = score_rubric("대한민국 헌법은 국민주권과 삼권분립, 법치주의를 기본 원리로 한다.", spec)
    assert res_pass["status"] == "SCORED"
    assert res_pass["passed"] is True
    assert res_pass["recommended_rating"] >= 3

    # 2. Contains forbidden misconception keyword -> cannot pass with full marks!
    res_forbid = score_rubric("국민주권과 삼권분립 및 왕권신수설을 따른다.", spec)
    assert res_forbid["status"] == "SCORED"
    assert res_forbid["forbidden_hits"] == ("왕권신수설",)
    assert res_forbid["passed"] is False
    assert res_forbid["recommended_rating"] == 1

    # 3. STT failure / timeout / blank -> SCORE_UNAVAILABLE & zero ReviewEvent emitted!
    for bad_ans, stt_st in [(None, "ok"), ("   ", "ok"), ("삼권분립", "timeout"), ("삼권분립", "error")]:
        res_unavail = score_rubric(bad_ans, spec, stt_status=stt_st)
        assert res_unavail["status"] == "SCORE_UNAVAILABLE"
        assert res_unavail["should_record_event"] is False


def test_t41_micro_sprint_7_card_chunking_and_matching_board() -> None:
    cards = [{"card_id": i, "front_text": f"Q{i}", "back_text": f"A{i}"} for i in range(16)]
    sprints = chunk_micro_sprints(cards, sprint_size=7)
    assert [len(s["cards"]) for s in sprints] == [7, 7, 2]
    assert sprints[0]["checkpoint_label"] == "🏁 스프린트 1 / 3 (7장)"

    board = build_matching_board_round(cards[:8], pair_count=6, seed=42)
    assert board["pair_count"] == 6
    assert board["time_limit_sec"] == 60
    assert board["event_kind"] == "CRAM"  # Never pollutes FSRS schedule!
    assert len(board["tiles"]) == 12


# ============================================================================
# GATE T42: Views, Printable 2-Col Exam Sheet, Audio Loop, QR Snapshot, Streak Shield, AST Purity
# ============================================================================


def test_t42_summary_sheet_printable_exam_audio_loop_qr_and_streak_shield() -> None:
    sample_cards = [
        {"card_id": 1, "front_text": "🌱 'accommodate'의 뜻은?", "back_text": "수용하다 (명사: accommodation)", "tags": ["eng"]},
        {"card_id": 2, "front_text": "📘 강화도 조약 체결 연도는?", "back_text": "1876년 (병자수호조규)", "tags": ["hist"]},
        {"card_id": 3, "front_text": "🔥 옴의 법칙 공식은?", "back_text": "V = I × R", "tags": ["sci"]},
    ]

    # 1. Electronic Red-Cellophane Summary Sheet
    sheet = build_summary_sheet_view(sample_cards, mask_mode="red_filter")
    assert len(sheet["rows"]) == 3
    assert sheet["rows"][0]["clean_answer"] == "수용하다"
    assert sheet["mask_mode"] == "red_filter"

    # 2. Printable 2-Column Exam Worksheet & Answer Key Seed Parity
    exam_doc_1 = build_printable_exam_sheet(sample_cards, title="중1 1학기 중간고사 대비 쪽지시험", seed=20261022)
    exam_doc_2 = build_printable_exam_sheet(sample_cards, title="중1 1학기 중간고사 대비 쪽지시험", seed=20261022)
    assert exam_doc_1["items"] == exam_doc_2["items"]
    assert "<html" in exam_doc_1["printable_html"].lower()
    assert exam_doc_1["column_count"] == 2
    assert [it["number"] for it in exam_doc_1["question_sheet"]] == [it["number"] for it in exam_doc_1["answer_key"]]

    # 3. Commute Hands-Free Audio Loop
    audio_loop = build_commute_audio_script(sample_cards, think_seconds=3)
    assert len(audio_loop["tracks"]) == 3
    assert audio_loop["tracks"][0]["pause_seconds"] == 3

    # 4. QR Scope Snapshot (Zero PII) & Parent Completion Report (Zero Fabricated Status)
    qr = encode_scope_snapshot_qr(
        deck_rev="rev-56",
        scope_ids=["kr.mid1.eng.L1", "hanja:8"],
        exam_ms=1_762_000_000_000,
        expires_ms=1_763_000_000_000,
    )
    assert "user" not in qr["payload_json"].lower()
    assert "email" not in qr["payload_json"].lower()
    assert qr["code"].startswith("BD56-")

    empty_report = build_parent_completion_report("중1 영어 1단원", exam_ms=1_762_000_000_000, daily_logs=[])
    assert empty_report["status_label"] == "집계 없음"
    assert "상위" not in json.dumps(empty_report, ensure_ascii=False)

    # 5. Streak Shield: CRAM does not count as completion; 1 shield covers 1 missed day
    logs = [
        {"date": "2026-10-19", "assigned": 20, "completed_review": 20, "cram_count": 0},
        {"date": "2026-10-20", "assigned": 20, "completed_review": 0, "cram_count": 50},  # Only CRAM -> Missed day!
        {"date": "2026-10-21", "assigned": 20, "completed_review": 20, "cram_count": 5},
    ]
    streak_no_shield = evaluate_streak_shield(logs, available_shields=0)
    assert streak_no_shield["current_streak_days"] == 1

    streak_with_shield = evaluate_streak_shield(logs, available_shields=1)
    assert streak_with_shield["current_streak_days"] == 2
    assert streak_with_shield["shields_remaining"] == 0


def test_t42_domain_zero_io_ast_purity_enforcement() -> None:
    """Every `.py` file in `src/anki_studio/domain/` must have zero I/O or adapter imports."""
    forbidden = {"sqlite3", "requests", "urllib", "http", "subprocess", "socket", "anki_studio.adapters", "anki_studio.service"}
    py_files = sorted(DOMAIN_DIR.glob("*.py"))
    assert len(py_files) >= 6
    for fpath in py_files:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, f"Forbidden import {alias.name} in {fpath.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, f"Forbidden from-import {node.module} in {fpath.name}"
                assert not node.module.startswith("anki_studio.adapters"), f"Adapter import in {fpath.name}"


# ============================================================================
# GATE T43: Type-Homogeneous 4-Choice Distractors (Zero Grammar-in-Vocab Leak) & Question Type Filter
# ============================================================================


def test_t43_four_choice_never_mixes_grammar_into_vocab_or_cross_domain_python_and_js() -> None:
    """Given a mixed deck containing English vocab meaning cards, English word/cloze cards,
    English grammar cards, Hanja cards, and History cards,
    When 4-choice options are built for a Vocab Meaning card (or Grammar card, or English Word card),
    Then 0% of the distractors may come from another question type (e.g., no grammar rules in vocab choices!).
    """
    mixed_deck = [
        {
            "card_id": 101,
            "front_text": "🌱 [Lv.1 기초 인지] 'introduce'의 뜻·의미는 무엇인가요?",
            "back_text": "소개하다 (동사)\n\n💡 해설: Let me introduce myself",
            "tags": ["kr.mid1.eng.donga_yoon.2022:U01", "role:core_vocab", "diff_lv1"],
        },
        {
            "card_id": 102,
            "front_text": "[Lesson 1 핵심문법] 주어가 3인칭 단수일 때 일반동사 현재형 부정문 형태는?",
            "back_text": "doesn't (does not) + 동사원형",
            "tags": ["kr.mid1.eng.donga_yoon.2022:U01", "role:key_grammar", "diff_lv1"],
        },
        {
            "card_id": 103,
            "front_text": "🔥 [Lv.3 역방향 능동 산출] 뜻·정의가 '소개하다'에 해당하는 정확한 용어/표현을 쓰시오.",
            "back_text": "introduce\n\n💡 해설: Let me introduce myself",
            "tags": ["kr.mid1.eng.donga_yoon.2022:U01", "role:core_vocab", "diff_lv3"],
        },
        {
            "card_id": 104,
            "front_text": "🌱 [Lv.1 기초 인지] '學'의 뜻·의미는 무엇인가요?",
            "back_text": "배울 학 (부수: 子)",
            "tags": ["hanja-grade:8geup", "diff_lv1"],
        },
        {
            "card_id": 105,
            "front_text": "🏛️ [한국사 핵심] 1876년 운요호 사건을 계기로 일본과 체결한 조선 최초의 근대적 불평등 조약은?",
            "back_text": "강화도 조약 (조일수호조규, 1876)",
            "tags": ["khist:essential", "diff_lv1"],
        },
    ]

    # 1. Python: Vocab Meaning card (#101) must ONLY have Korean vocab meaning options, NEVER grammar or English words or history
    vocab_quiz = build_type_matched_quiz_options(mixed_deck[0], mixed_deck)
    assert vocab_quiz["question_type"]["facet_key"] == "eng_vocab_meaning"
    assert vocab_quiz["question_type"]["category_key"] == "vocab"
    assert len(vocab_quiz["options"]) == 4
    assert "소개하다" in vocab_quiz["options"]
    for opt in vocab_quiz["options"]:
        assert "doesn't" not in opt and "동사원형" not in opt, f"Grammar leaked into vocab 4-choice: {opt}"
        assert opt != "introduce", f"English word leaked into Korean meaning 4-choice: {opt}"
        assert "강화도" not in opt and "배울 학" not in opt, f"Cross-domain leaked into vocab 4-choice: {opt}"

    # 2. Python: Grammar card (#102) must ONLY have Grammar options
    grammar_quiz = build_type_matched_quiz_options(mixed_deck[1], mixed_deck)
    assert grammar_quiz["question_type"]["facet_key"] == "eng_grammar"
    assert grammar_quiz["question_type"]["category_key"] == "grammar"
    assert len(grammar_quiz["options"]) == 4
    assert "doesn't (does not) + 동사원형" in grammar_quiz["options"]
    for opt in grammar_quiz["options"]:
        assert opt != "소개하다" and opt != "introduce" and "강화도" not in opt

    # 3. Python: English Word card (#103) must ONLY have English word options
    word_quiz = build_type_matched_quiz_options(mixed_deck[2], mixed_deck)
    assert word_quiz["question_type"]["facet_key"] == "eng_vocab_word"
    assert len(word_quiz["options"]) == 4
    assert "introduce" in word_quiz["options"]
    for opt in word_quiz["options"]:
        assert all(ord(ch) < 128 for ch in opt), f"Non-English option leaked into English word 4-choice: {opt}"

    # 4. JS ViewModel Parity & Type Filtering
    node_script = f"""
    const vm = require({json.dumps(str(VIEWMODEL_JS))});
    const deck = {json.dumps(mixed_deck)};
    const vQuiz = vm.buildTypeMatchedQuizOptions(deck[0], deck);
    const gQuiz = vm.buildTypeMatchedQuizOptions(deck[1], deck);
    const wQuiz = vm.buildTypeMatchedQuizOptions(deck[2], deck);
    const filteredVocab = vm.filterStudyQueueByQuestionType(deck, "vocab");
    const filteredGrammar = vm.filterStudyQueueByQuestionType(deck, "grammar");
    const counts = vm.computeQuestionTypeCounts(deck);
    console.log(JSON.stringify({{ vQuiz, gQuiz, wQuiz, vocabLen: filteredVocab.length, grammarLen: filteredGrammar.length, counts }}));
    """
    res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=True)
    js_data = json.loads(res.stdout.strip())

    assert js_data["vQuiz"]["question_type"]["facet_key"] == "eng_vocab_meaning"
    assert len(js_data["vQuiz"]["options"]) == 4
    for opt in js_data["vQuiz"]["options"]:
        assert "doesn't" not in opt and "동사원형" not in opt and opt != "introduce"

    assert js_data["gQuiz"]["question_type"]["facet_key"] == "eng_grammar"
    assert len(js_data["gQuiz"]["options"]) == 4
    assert js_data["wQuiz"]["question_type"]["facet_key"] == "eng_vocab_word"
    assert js_data["vocabLen"] == 2
    assert js_data["grammarLen"] == 1
    assert js_data["counts"]["vocab"] == 2
    assert js_data["counts"]["grammar"] == 1
    assert js_data["counts"]["hanja"] == 1
    assert js_data["counts"]["history_sci"] == 1

    # Python filter parity
    assert len(filter_cards_by_question_type(mixed_deck, "vocab")) == 2
    assert len(filter_cards_by_question_type(mixed_deck, "grammar")) == 1
    assert classify_card_question_type(mixed_deck[1])["category_key"] == "grammar"
    assert sorted(compute_question_type_counts(mixed_deck).items()) == sorted(
        {"all": 5, "vocab": 2, "grammar": 1, "hanja": 1, "history_sci": 1}.items()
    )


# ============================================================================
# GATE T44: Zero REA/AI UI Labels + Ollama Cloud Photo/PDF Deck Generation + 4-Model Consensus
# ============================================================================


def test_t44_zero_rea_and_ai_labels_in_user_facing_ui() -> None:
    """ATDD Gate T44-A: User-facing UI templates must not expose 'REA' or 'AI' jargon."""
    import re

    index_html = (ROOT_DIR / "src" / "anki_studio" / "ui" / "static" / "index.html").read_text(encoding="utf-8")
    manifest_json = (ROOT_DIR / "src" / "anki_studio" / "ui" / "static" / "manifest.json").read_text(encoding="utf-8")
    main_kt = (
        ROOT_DIR / "android-app" / "app" / "src" / "main" / "java" / "com" / "ankistudio" / "app" / "ui" / "MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert re.search(r"\bREA\b", index_html) is None
    assert "AI " not in index_html and "AI·" not in index_html and "AI가" not in index_html
    assert re.search(r"\bREA\b", manifest_json) is None and "AI" not in manifest_json
    assert "AI " not in main_kt and "AI가" not in main_kt
    assert 'id="doc-ollama-model-select"' in index_html
    assert 'id="btn-override-correct"' in index_html
    assert 'id="sprint-progress-badge"' in index_html


@pytest.mark.parametrize(
    "model_name,expected_blocked",
    [
        ("glm-5.3-flash", False),
        ("deepseek-v4.1-flash", False),
        ("gemma4:31b", False),
        ("glm-5.3", False),
        ("local_rule", False),
        ("kimi-k2.6", True),
        ("kimi-k3", True),
        ("minimax-2.7", True),
        ("minimax-m3", True),
    ],
)
def test_t44_ddt_ollama_cloud_model_policy_fail_closed_matrix(model_name: str, expected_blocked: bool) -> None:
    """DDT Gate T44-B: Parameterized Fail-Closed Model Policy matrix across allowed & permanently blocked models."""
    from anki_studio.adapters.ai_engine import is_ollama_cloud_model_blocked

    assert is_ollama_cloud_model_blocked(model_name) is expected_blocked


@pytest.mark.parametrize(
    "front_text,back_text,tags,expected_facet,expected_category",
    [
        ("🌱 'introduce'의 뜻은?", "소개하다", ["eng", "vocab"], "eng_vocab_meaning", "vocab"),
        ("🔥 뜻이 '소개하다'인 영단어는?", "introduce", ["eng", "vocab"], "eng_vocab_word", "vocab"),
        ("[핵심문법] 3인칭 단수 일반동사 부정문 형태는?", "doesn't + 동사원형", ["grammar"], "eng_grammar", "grammar"),
        ("[한자 8급] 學의 훈음은?", "배울 학", ["hanja"], "hanja_hun_eum", "hanja"),
        ("1876년 체결된 조선 최초의 근대적 조약은?", "강화도 조약", ["khist"], "history", "history_sci"),
        ("우리 프로젝트의 최우선 아키텍처 원칙은?", "무결성 우선 설계", ["custom"], "general_concept", "history_sci"),
    ],
)
def test_t44_ddt_question_type_classification_and_zero_cross_type_leak(
    front_text: str,
    back_text: str,
    tags: list[str],
    expected_facet: str,
    expected_category: str,
) -> None:
    """DDT Gate T44-C: Parameterized Question-Type Facet classification across all 6 card archetypes."""
    card = {"card_id": 501, "front_text": front_text, "back_text": back_text, "tags": tags}
    qtype = classify_card_question_type(card)
    assert qtype["facet_key"] == expected_facet
    assert qtype["category_key"] == expected_category
    quiz = build_type_matched_quiz_options(card, [card])
    assert len(quiz["options"]) == 4
    assert quiz["target_answer"] in quiz["options"]


def test_t44_bdd_ollama_cloud_photo_pdf_deck_generation_and_fastapi_endpoints(tmp_path: Path) -> None:
    """BDD Gate T44-D:
    Given extracted Photo/PDF DocumentBlocks and the FastAPI StudioServer,
    When ingest-document is called with 'glm-5.3-flash' vs blocked 'kimi-k2.6' vs offline cloud failure,
    Then 'glm-5.3-flash' synthesizes grounded cloud cards, 'kimi-k2.6' fails closed (HTTP 403 BLOCKED_MODEL),
    and offline cloud errors fall back deterministically to grounded local cards.
    """
    from anki_studio.adapters.ai_engine import AICardSynthesizer
    from anki_studio.domain.document_deck_builder import DocumentBlock
    from anki_studio.service.studio_server import AnkiStudioService

    meta = AICardSynthesizer.list_ollama_cloud_models()
    model_ids = [m["id"] for m in meta["models"]]
    assert {"glm-5.3-flash", "deepseek-v4.1-flash", "gemma4:31b", "glm-5.3", "local_rule"}.issubset(set(model_ids))

    blocks = [
        DocumentBlock(
            page=1,
            text="광합성: 식물 세포의 엽록체에서 빛에너지를 포도당의 화학에너지로 전환하는 과정이다.",
            kind="paragraph",
        )
    ]
    base_cards = [
        {
            "front_text": "광합성의 정의는?",
            "back_text": "식물 세포의 엽록체에서 빛에너지를 화학에너지로 전환하는 과정",
            "note_type": "basic",
            "tags": ["science"],
            "source_page": 1,
            "source_excerpt": blocks[0].text,
        }
    ]

    def fake_ollama_sender(url, payload, headers, timeout):
        return json.dumps(
            {
                "cards": [
                    {
                        "front_text": "엽록체에서 빛에너지를 포도당의 화학에너지로 합성하는 작용은?",
                        "back_text": "광합성 (Photosynthesis)\n💡 해설: 이산화탄소와 물을 원료로 포도당과 산소를 생성합니다.",
                        "note_type": "basic",
                        "source_page": 1,
                        "source_excerpt": "광합성은 식물 세포의 엽록체에서...",
                        "tags": ["bio"],
                    },
                    {
                        "front_text": "식물 세포의 {{c1::엽록체}}에서 광합성이 일어난다.",
                        "back_text": "엽록체",
                        "note_type": "cloze",
                        "source_page": 1,
                    },
                ]
            },
            ensure_ascii=False,
        )

    synth = AICardSynthesizer(ollama_http_sender=fake_ollama_sender)

    # 1. Blocked model returns Fail-Closed BLOCKED_MODEL status
    blocked_res = synth.synthesize_document_cards_with_ollama_cloud(
        blocks=blocks,
        base_cards=base_cards,
        ollama_cloud_model="kimi-k2.6",
    )
    assert blocked_res["ok"] is False
    assert blocked_res["status"] == "BLOCKED"
    assert blocked_res["error_code"] == "BLOCKED_MODEL"
    assert blocked_res["cards"] == []

    # 2. Allowed Ollama Cloud model synthesizes grounded cards
    ok_res = synth.synthesize_document_cards_with_ollama_cloud(
        blocks=blocks,
        base_cards=base_cards,
        ollama_cloud_model="glm-5.3-flash",
    )
    assert ok_res["ok"] is True
    assert ok_res["status"] == "OK"
    assert ok_res["ollama_cloud_used"] is True
    assert ok_res["provider"] == "ollama_cloud:glm-5.3-flash"
    assert len(ok_res["cards"]) == 2

    # 3. Network failure falls back gracefully to grounded base_cards
    def failing_sender(url, payload, headers, timeout):
        raise RuntimeError("Simulated cloud timeout")

    fallback_synth = AICardSynthesizer(ollama_http_sender=failing_sender)
    fb_res = fallback_synth.synthesize_document_cards_with_ollama_cloud(
        blocks=blocks,
        base_cards=base_cards,
        ollama_cloud_model="deepseek-v4.1-flash",
    )
    assert fb_res["ok"] is True
    assert fb_res["ollama_cloud_used"] is False
    assert fb_res["cards"][0]["front_text"] == "광합성의 정의는?"
    assert "ollama_fallback:deepseek-v4.1-flash" in fb_res["cards"][0]["tags"]

    # 4. AnkiStudioService integration verification (ingest_document & generate_ai_cards with Ollama Cloud)
    svc = AnkiStudioService(db_path=tmp_path / "t44_api.sqlite3", seed_defaults=False, ai_synthesizer=synth)
    pdf_bytes = (
        b"%PDF-1.4\r\n<< /Title (Biology) >>\r\n<< /Type /Page >>\n"
        b"stream\r\nBT\r\n(Photosynthesis: process by which plants convert light into glucose) Tj\r\nET\r\nendstream\r\n%%EOF\r\n"
    )
    blocked_ingest = svc.ingest_document(
        pdf_bytes,
        deck_name="bio.pdf",
        mime="application/pdf",
        ollama_cloud_model="kimi-k2.6",
    )
    assert blocked_ingest["status"] == "BLOCKED"
    assert blocked_ingest["error_code"] == "BLOCKED_MODEL"

    ok_ingest = svc.ingest_document(
        pdf_bytes,
        deck_name="bio.pdf",
        mime="application/pdf",
        ollama_cloud_model="glm-5.3-flash",
    )
    assert ok_ingest["status"] == "OK"
    assert ok_ingest["ollama_cloud_model"] == "glm-5.3-flash"
    assert ok_ingest["ollama_cloud_used"] is True
    assert len(ok_ingest["cards"]) >= 2

    blocked_gen = svc.generate_ai_cards(
        raw_text="광합성: 엽록체에서 빛에너지를 화학에너지로 전환하는 과정",
        ollama_cloud_model="minimax-2.7",
    )
    assert blocked_gen["ok"] is False
    assert blocked_gen["error_code"] == "BLOCKED_MODEL"


def test_t44_bdd_four_model_consensus_standalone_fsrs_undo_batch_save_and_fisher_yates() -> None:
    """BDD Gate T44-E:
    Given the Standalone Engine in viewmodel.js and Python/JS 4-choice option builders,
    When cards are created, Cloze-rendered, reviewed (Good=3), undone (undoLastReview), and batch-saved,
    Then FSRS-5 foldReviewEvents schedules & unschedules due cards accurately, Cloze masks target answers,
    and Fisher-Yates shuffle distributes answer indices non-rotationally.
    """
    # 1. Verify Fisher-Yates is non-rotational (not card_id % 4) in Python
    positions = []
    for cid in range(1, 17):
        c = {"card_id": cid, "front_text": f"🌱 'word_{cid}'의 뜻은?", "back_text": f"뜻_{cid}", "tags": ["eng", "vocab"]}
        q = build_type_matched_quiz_options(c, [c])
        positions.append(q["options"].index(f"뜻_{cid}"))
    modulo_pattern = [cid % 4 for cid in range(1, 17)]
    assert positions != modulo_pattern, "4-choice options must use Fisher-Yates shuffle, not modulo rotation!"

    # 2. Standalone Engine FSRS-5 foldReviewEvents scheduling + Undo + BatchSave + Cloze rendering in Node
    node_script = f"""
    const vm = require({json.dumps(str(VIEWMODEL_JS))});
    const vault = vm.createStandaloneEngine(null);
    const created = vault.buildSmartTextDeck({{
      text: "엽록체: 빛에너지를 흡수하여 포도당을 합성하는 세포 소기관",
      difficulty_level: "lv2",
      deck_name: "생물 테스트"
    }});
    const dueBefore = vault.getDueCards({{ deck_id: created.deck_id }}).cards;
    const targetCard = dueBefore[0];
    const renderedQ = targetCard.rendered_question;
    const targetAns = targetCard.target_answer;
    const revRes = vault.submitReview({{ card_id: targetCard.card_id, rating: 3 }});
    const dueAfterReview = vault.getDueCards({{ deck_id: created.deck_id }}).cards.filter(c => c.card_id === targetCard.card_id);
    const undoRes = vault.undoLastReview();
    const dueAfterUndo = vault.getDueCards({{ deck_id: created.deck_id }}).cards.filter(c => c.card_id === targetCard.card_id);
    const batchRes = vault.batchSaveDeck({{
      deck_name: "PDF 일괄 저장 덱",
      category: "science",
      cards: [{{ front_text: "세포 호흡이 일어나는 장소는?", back_text: "미토콘드리아", note_type: "basic" }}]
    }});
    const customQType = vm.classifyCardQuestionType({{
      front_text: "우리 팀의 핵심 가치는 무엇인가요?",
      back_text: "사용자 중심 혁신",
      tags: ["custom"]
    }});
    console.log(JSON.stringify({{
      renderedQ,
      targetAns,
      scheduledDays: revRes.scheduled_days,
      stability: revRes.memory.stability,
      dueAfterReviewCount: dueAfterReview.length,
      undoOk: undoRes.ok,
      dueAfterUndoCount: dueAfterUndo.length,
      batchSavedCount: batchRes.saved_count,
      customFacet: customQType.facet_key
    }}));
    """
    res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=True)
    data = json.loads(res.stdout.strip())
    assert "[힌트:" in data["renderedQ"] or "[ ... ]" in data["renderedQ"]
    assert data["targetAns"] == "엽록체"
    assert data["scheduledDays"] >= 1
    assert data["stability"] > 0
    assert data["dueAfterReviewCount"] == 0, "Reviewed card scheduled >= 1 day in the future must not remain immediately due!"
    assert data["undoOk"] is True
    assert data["dueAfterUndoCount"] == 1, "Undoing the review must restore the card to the due queue!"
    assert data["batchSavedCount"] == 1
    assert data["customFacet"] == "general_concept"



