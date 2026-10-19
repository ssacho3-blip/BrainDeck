"""Comprehensive ATDD / BDD / DDT Test Suite for Anki Studio 2.0 (FSRS-5 + AI Active Recall)."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request
import zipfile

import pytest

from anki_studio.adapters.ai_engine import AICardSynthesizer
from anki_studio.adapters.sqlite_store import AnkiStudioStore
from anki_studio.domain.ai_learning import (
    decompose_leech_card,
    evaluate_free_recall,
    extract_smart_cards_deterministic,
    generate_socratic_hint,
    parse_ai_generated_cards,
)
from anki_studio.domain.fsrs_math import (
    CardMemoryState,
    Rating,
    compute_next_interval,
    compute_retrievability,
    detect_leech_severity,
    extract_cloze_ordinals,
    forecast_forgetting_curve,
    plan_backlog_decompression,
    preview_all_ratings,
    render_cloze_card,
    step_fsrs,
)
from anki_studio.service.studio_server import AnkiStudioService, create_http_server


# 1. Architecture Boundary Test (Zero External I/O in ALL Pure Domain Modules)
@pytest.mark.parametrize("module_name", ["fsrs_math.py", "ai_learning.py"])
def test_domain_modules_have_zero_io_imports(module_name: str) -> None:
    domain_file = Path(__file__).resolve().parents[1] / "src" / "anki_studio" / "domain" / module_name
    tree = ast.parse(domain_file.read_text(encoding="utf-8"))
    forbidden = {"sqlite3", "urllib", "http", "socket", "subprocess", "requests", "zipfile", "pathlib", "os"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden), f"Forbidden I/O modules in {module_name}: {imported & forbidden}"


# 2. FSRS-5 Mathematical Invariants (DDT)
@pytest.mark.parametrize("stability", [1.0, 3.173, 15.69, 90.0, 365.0])
def test_forgetting_curve_calibrated_at_90_percent_when_elapsed_equals_stability(stability: float) -> None:
    assert compute_retrievability(0.0, stability) == pytest.approx(1.0, abs=1e-9)
    assert compute_retrievability(stability, stability) == pytest.approx(0.90, abs=1e-6)
    assert compute_retrievability(stability * 2.0, stability) < 0.90


@pytest.mark.parametrize(
    "rating_a,rating_b",
    [
        (Rating.AGAIN, Rating.HARD),
        (Rating.HARD, Rating.GOOD),
        (Rating.GOOD, Rating.EASY),
    ],
)
def test_initial_review_monotonicity_across_ratings(rating_a: Rating, rating_b: Rating) -> None:
    out_a = step_fsrs(CardMemoryState(), rating_a)
    out_b = step_fsrs(CardMemoryState(), rating_b)
    assert out_b.memory.stability > out_a.memory.stability
    assert out_b.memory.difficulty < out_a.memory.difficulty
    assert out_b.scheduled_days >= out_a.scheduled_days


def test_subsequent_recall_increases_stability_and_forget_decreases_stability() -> None:
    first = step_fsrs(CardMemoryState(), Rating.GOOD).memory
    recalled = step_fsrs(first, Rating.GOOD, elapsed_days=3.0).memory
    forgotten = step_fsrs(first, Rating.AGAIN, elapsed_days=3.0).memory

    assert recalled.stability > first.stability
    assert forgotten.stability <= first.stability
    assert forgotten.lapses == first.lapses + 1
    assert forgotten.state == "relearning"


def test_preview_all_ratings_returns_four_monotonic_choices() -> None:
    previews = preview_all_ratings(CardMemoryState())
    assert set(previews.keys()) == {"again", "hard", "good", "easy"}
    assert previews["again"].scheduled_days <= previews["hard"].scheduled_days
    assert previews["hard"].scheduled_days <= previews["good"].scheduled_days
    assert previews["good"].scheduled_days <= previews["easy"].scheduled_days


def test_forecast_forgetting_curve_generates_31_points() -> None:
    curve = forecast_forgetting_curve(stability=10.0, horizon_days=30)
    assert len(curve) == 31
    assert curve[0]["retrievability"] == 1.0
    assert curve[10]["retrievability"] == pytest.approx(0.90, abs=1e-4)


@pytest.mark.parametrize(
    "reps,lapses,difficulty,expected",
    [
        (5, 0, 5.0, "healthy"),
        (6, 2, 6.0, "warning"),
        (8, 4, 6.5, "critical_leech"),
        (4, 2, 8.8, "critical_leech"),
    ],
)
def test_detect_leech_severity(reps: int, lapses: int, difficulty: float, expected: str) -> None:
    assert detect_leech_severity(reps, lapses, difficulty) == expected


def test_plan_backlog_decompression_prioritizes_low_retrievability_and_respects_daily_cap() -> None:
    overdue = [
        {"card_id": i, "elapsed_days": float(i * 2), "stability": 5.0, "difficulty": 6.0, "lapses": i % 3}
        for i in range(1, 13)
    ]
    plan = plan_backlog_decompression(overdue, daily_cap=4, horizon_days=3)
    assert len(plan) == 12
    day0 = [p for p in plan if p["day_offset"] == 0]
    day1 = [p for p in plan if p["day_offset"] == 1]
    day2 = [p for p in plan if p["day_offset"] == 2]
    assert len(day0) == 4
    assert len(day1) == 4
    assert len(day2) == 4
    # Day 0 must hold the lowest retrievability (most urgent) cards
    assert max(p["retrievability"] for p in day0) <= min(p["retrievability"] for p in day2)


# 3. Cloze Deletion Parser & Multi-Card Generator Tests
def test_cloze_parser_extracts_ordinals_and_renders_question_and_answer() -> None:
    note = "GAA 트랜지스터는 {{c1::Nanosheet::채널 구조}}를 4면으로 감싸 {{c2::단채널 효과(SCE)}}를 억제한다."
    assert extract_cloze_ordinals(note) == [1, 2]

    q1 = render_cloze_card(note, active_ordinal=1, reveal=False)
    a1 = render_cloze_card(note, active_ordinal=1, reveal=True)
    assert q1 == "GAA 트랜지스터는 [채널 구조]를 4면으로 감싸 단채널 효과(SCE)를 억제한다."
    assert a1 == "GAA 트랜지스터는 【Nanosheet】를 4면으로 감싸 단채널 효과(SCE)를 억제한다."

    q2 = render_cloze_card(note, active_ordinal=2, reveal=False)
    assert q2 == "GAA 트랜지스터는 Nanosheet를 4면으로 감싸 [...]를 억제한다."


# 4. AI Active Recall Evaluator, Socratic Hint, Leech Doctor & Card Factory Tests
@pytest.mark.parametrize(
    "user_ans,expected_ans,expected_rating",
    [
        ("0.55", "차세대 High-NA EUV는 개구수를 【0.55】로 높인다.", Rating.EASY),
        ("Nanosheet 채널", "GAA는 【Nanosheet 채널】을 4면으로 감싼다.", Rating.EASY),
        ("0.33", "차세대 High-NA EUV는 개구수를 【0.55】로 높인다.", Rating.AGAIN),
        ("", "【Nanosheet】", Rating.AGAIN),
    ],
)
def test_ai_evaluate_free_recall_grades_accurately(
    user_ans: str,
    expected_ans: str,
    expected_rating: Rating,
) -> None:
    ev = evaluate_free_recall(user_answer=user_ans, expected_answer=expected_ans)
    assert ev.recommended_rating == expected_rating


def test_ai_socratic_hint_and_leech_decomposition() -> None:
    hint1 = generate_socratic_hint(
        question_text="EUV 파장은 얼마인가?",
        target_answer="【13.5 nm】",
        lapses=3,
        level=1,
    )
    hint2 = generate_socratic_hint(
        question_text="EUV 파장은 얼마인가?",
        target_answer="【13.5 nm】",
        lapses=3,
        level=2,
    )
    assert "첫 글자: '1...'" in hint1.structural_cue
    assert "구조 힌트:" in hint2.structural_cue
    assert "Leech 집중 처방" in hint1.mnemonic_tip

    subcards = decompose_leech_card(
        front_text="GAA 트랜지스터는 Nanosheet 채널을 4면으로 감싸며, 단채널 효과(SCE)를 효과적으로 억제한다.",
        back_text="2nm 공정 핵심 소자",
    )
    assert len(subcards) >= 2
    assert all(c.note_type == "cloze" and "{{c1::" in c.front_text for c in subcards)


def test_ai_card_factory_deterministic_and_llm_json_parser() -> None:
    raw_notes = """
    • CFET (Complementary FET): NMOS와 PMOS를 수직 적층하여 셀 면적을 축소하는 소자
    • 회의 후속 논의를 진행하고 싶습니다 -> I would like to follow up on our meeting.
    • High-NA EUV 노광장비는 0.55 개구수를 사용한다.
    """
    specs = extract_smart_cards_deterministic(raw_notes, domain_mode="auto")
    assert len(specs) == 3
    assert specs[0].note_type == "cloze"
    assert specs[1].note_type == "speaking"
    assert specs[2].note_type == "cloze"

    # Malformed LLM output must Fail-Closed to deterministic extraction
    fallback_specs = parse_ai_generated_cards("NOT_VALID_JSON", fallback_source_text=raw_notes)
    assert len(fallback_specs) == 3


# 5. SQLite WAL Store, Backlog Decompression, and .apkg Roundtrip Tests
def test_sqlite_store_cloze_card_expansion_and_review_lifecycle(tmp_path: Path) -> None:
    store = AnkiStudioStore(tmp_path / "anki_studio.sqlite")
    deck_id = store.ensure_deck("반도체 공정 & 영어회화", desired_retention=0.90)

    now = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
    store.add_note(
        deck_id=deck_id,
        note_type="cloze",
        front_text="EUV 노광장비의 파장은 {{c1::13.5 nm}}이며 {{c2::High-NA::차세대 기술}}는 개구수를 0.55로 높인다.",
        now_iso=now.isoformat(),
    )

    due = store.get_due_cards(deck_id=deck_id, as_of_iso=now.isoformat())
    assert len(due) == 2
    assert due[0]["rendered_question"].startswith("EUV 노광장비의 파장은 [...]")
    assert due[1]["rendered_question"].endswith("[차세대 기술]는 개구수를 0.55로 높인다.")
    assert "button_previews" in due[0]

    res = store.review_card(due[0]["card_id"], Rating.GOOD, reviewed_at=now)
    assert res["scheduled_days"] >= 3
    assert res["memory"].state == "review"

    remaining = store.get_due_cards(deck_id=deck_id, as_of_iso=now.isoformat())
    assert len(remaining) == 1
    assert remaining[0]["ordinal"] == 2


def test_apkg_export_and_import_roundtrip(tmp_path: Path) -> None:
    store_a = AnkiStudioStore(tmp_path / "source.sqlite")
    deck_id = store_a.ensure_deck("Exported Deck")
    store_a.add_note(
        deck_id=deck_id,
        front_text="I'd like to follow up on our meeting.",
        back_text="회의 후속 논의를 하고 싶습니다.",
        tags=["english", "speaking"],
    )
    store_a.add_note(
        deck_id=deck_id,
        front_text="FinFET 대비 {{c1::GAA}}는 게이트 제어력이 우수하다.",
        back_text="4면 게이트 제어",
        note_type="cloze",
        tags=["semiconductor"],
    )

    apkg_file = store_a.export_apkg(tmp_path / "roundtrip.apkg", deck_id=deck_id)
    assert apkg_file.is_file()

    store_b = AnkiStudioStore(tmp_path / "target.sqlite")
    imported = store_b.import_apkg(apkg_file, target_deck_name="Imported Roundtrip")
    assert imported == 2
    due = store_b.get_due_cards()
    assert len(due) == 2


def _call_handler_in_memory(
    handler_cls: type,
    method: str,
    path: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    import io

    hdr_lines = [f"{method} {path} HTTP/1.1", "Host: 127.0.0.1:4390"]
    if body:
        hdr_lines.append(f"Content-Length: {len(body)}")
    for k, v in (headers or {}).items():
        hdr_lines.append(f"{k}: {v}")
    raw_req = ("\r\n".join(hdr_lines) + "\r\n\r\n").encode("utf-8") + body

    rfile = io.BytesIO(raw_req)
    wfile = io.BytesIO()

    class _DummySocket:
        def makefile(self, mode: str, *args: object, **kwargs: object) -> object:
            return rfile if "r" in mode else wfile

        def sendall(self, data: bytes) -> None:
            wfile.write(data)

    handler_cls(_DummySocket(), ("127.0.0.1", 54321), None)
    raw_resp = wfile.getvalue()
    head_bytes, _, payload = raw_resp.partition(b"\r\n\r\n")
    head_lines = head_bytes.decode("iso-8859-1").split("\r\n")
    status_code = int(head_lines[0].split(" ")[1])
    resp_headers: dict[str, str] = {}
    for line in head_lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            resp_headers[k.strip()] = v.strip()
    return status_code, resp_headers, payload


# 6. HTTP Server E2E & Fail-Closed Security Tests
def test_http_server_endpoints_and_fail_closed_validation(tmp_path: Path) -> None:
    from anki_studio.service.studio_server import create_http_handler

    svc = AnkiStudioService(db_path=tmp_path / "e2e.sqlite", seed_defaults=True)
    handler_cls = create_http_handler(svc)

    # 1) GET /api/status
    code, _, raw = _call_handler_in_memory(handler_cls, "GET", "/api/status")
    assert code == 200
    status_data = json.loads(raw.decode("utf-8"))
    assert status_data["ok"] is True
    assert status_data["stats"]["total_cards"] >= 6

    # 2) POST /api/ai/generate-cards
    gen_body = json.dumps(
        {
            "raw_text": "CFET: NMOS와 PMOS를 수직 적층하여 면적을 50% 줄이는 차세대 소자",
            "domain_mode": "semiconductor_ai",
            "auto_save": True,
        }
    ).encode("utf-8")
    code, _, raw = _call_handler_in_memory(
        handler_cls,
        "POST",
        "/api/ai/generate-cards",
        body=gen_body,
        headers={"Content-Type": "application/json"},
    )
    assert code == 200
    gen_data = json.loads(raw.decode("utf-8"))
    assert gen_data["ok"] is True
    assert gen_data["generated_count"] == 1
    assert gen_data["provider"] == "deterministic_nlp"
    assert gen_data["fallback_reason"] == "endpoint_unconfigured"
    assert isinstance(gen_data["latency_ms"], float)

    # 3) POST /api/ai/evaluate & /api/ai/hint
    eval_body = json.dumps(
        {
            "user_answer": "0.55",
            "expected_answer": "【0.55】",
            "question_text": "High-NA EUV 개구수",
        }
    ).encode("utf-8")
    code, _, raw = _call_handler_in_memory(
        handler_cls,
        "POST",
        "/api/ai/evaluate",
        body=eval_body,
        headers={"Content-Type": "application/json"},
    )
    assert code == 200
    assert json.loads(raw.decode("utf-8"))["recommended_rating"] == 4

    # 4) Non-finite float (1e400 / Infinity) must be rejected with HTTP 400
    code, _, raw = _call_handler_in_memory(
        handler_cls,
        "POST",
        "/api/review",
        body=b'{"card_id": 1, "rating": 1e400}',
        headers={"Content-Type": "application/json"},
    )
    assert code == 400
    assert json.loads(raw.decode("utf-8"))["error"] == "invalid_json"


def test_leech_decomposition_suspends_parent_and_preserves_revlog(tmp_path: Path) -> None:
    svc = AnkiStudioService(db_path=tmp_path / "leech_handoff.sqlite", seed_defaults=False)
    deck_id = svc.store.ensure_deck("Leech Handoff Deck")
    svc.store.add_note(
        deck_id=deck_id,
        note_type="basic",
        front_text="FinFET과 GAA의 구조적 차이와 장점은?",
        back_text="FinFET은 3면 게이트 제어 구조이고; GAA는 Nanosheet 4면을 모두 감싸 단채널 효과를 억제한다.",
    )
    due_before = svc.store.get_due_cards(deck_id=deck_id)
    assert len(due_before) == 1
    parent_card_id = due_before[0]["card_id"]

    # Record two Again lapses on the parent card so it becomes a Leech with revlog history
    svc.submit_review(card_id=parent_card_id, rating=1)
    svc.submit_review(card_id=parent_card_id, rating=1)
    stats_before = svc.store.get_dashboard_stats()
    assert stats_before["total_reviews"] == 2

    res = svc.decompose_leech(
        front_text=due_before[0]["front_text"],
        back_text=due_before[0]["back_text"],
        deck_id=deck_id,
        auto_save=True,
        parent_card_id=parent_card_id,
    )
    assert res["ok"] is True
    assert res["parent_suspended"] is True
    assert res["parent_card_id"] == parent_card_id
    assert len(res["saved_note_ids"]) >= 2

    # Parent card is suspended and excluded from active due queue, while revlog is preserved
    due_after = svc.store.get_due_cards(deck_id=deck_id)
    assert all(c["card_id"] != parent_card_id for c in due_after)
    assert all(c["state"] == "new" for c in due_after)
    stats_after = svc.store.get_dashboard_stats()
    assert stats_after["suspended_cards"] == 1
    assert stats_after["total_reviews"] == 2


# 7. ViewModel Pure JS Unit Test via Node
def test_viewmodel_js_pure_functions() -> None:
    vm_path = Path(__file__).resolve().parents[1] / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    script = f"""
    const vm = require({json.dumps(str(vm_path))});
    const b1 = vm.formatRetentionBadge(92.4);
    if (b1.tone !== 'emerald') process.exit(1);
    const l1 = vm.formatLeechBadge('critical_leech', 4);
    if (!l1.visible || l1.tone !== 'rose') process.exit(2);
    const k1 = vm.mapKeyboardShortcut(' ', false, false);
    if (!k1 || k1.action !== 'reveal') process.exit(3);
    const k2 = vm.mapKeyboardShortcut('3', true, false);
    if (!k2 || k2.action !== 'rate' || k2.rating !== 3) process.exit(4);
    const pts = vm.buildForgettingCurveSvgPoints([{{day:0, retrievability:1.0}}, {{day:10, retrievability:0.9}}], 480, 120);
    if (!pts.includes(',')) process.exit(5);
    const cat = vm.formatCategoryBadge('law');
    if (cat.tone !== 'indigo') process.exit(6);
    const pat = vm.formatPatternBadge('statute_numeric');
    if (pat !== '조문·수치') process.exit(7);
    const blk = vm.formatIngestStatusBanner({{status: 'BLOCKED', error_code: 'encrypted_pdf'}});
    if (blk.canSave !== false || blk.tone !== 'rose') process.exit(8);
    const okB = vm.formatIngestStatusBanner({{status: 'OK', deck_name: '민법', category: 'law', cards: [{{}}], stats: {{pages: 2}}}});
    if (okB.canSave !== true || okB.tone !== 'emerald') process.exit(9);
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Node ViewModel test failed: {proc.stderr}"


