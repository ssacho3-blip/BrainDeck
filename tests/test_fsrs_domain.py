"""ATDD / BDD / DDT Test Suite for Anki Studio FSRS-5 Domain & SQLite/.apkg Store."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import zipfile

import pytest

from anki_studio.adapters.sqlite_store import AnkiStudioStore
from anki_studio.domain.fsrs_math import (
    CardMemoryState,
    Rating,
    compute_next_interval,
    compute_retrievability,
    extract_cloze_ordinals,
    forecast_forgetting_curve,
    preview_all_ratings,
    render_cloze_card,
    step_fsrs,
)


# 1. Architecture Boundary Test (Zero External I/O in Pure Domain)
def test_domain_layer_has_zero_io_imports() -> None:
    domain_file = Path(__file__).resolve().parents[1] / "src" / "anki_studio" / "domain" / "fsrs_math.py"
    tree = ast.parse(domain_file.read_text(encoding="utf-8"))
    forbidden = {"sqlite3", "urllib", "http", "socket", "subprocess", "requests", "zipfile", "pathlib", "os"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden), f"Forbidden I/O modules in pure domain: {imported & forbidden}"


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
    # Higher rating must produce higher initial stability and lower initial difficulty
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


# 4. SQLite WAL Store & .apkg Import Integration Tests (BDD Given-When-Then)
def test_sqlite_store_cloze_card_expansion_and_review_lifecycle(tmp_path: Path) -> None:
    # Given a new SQLite WAL store and a deck
    store = AnkiStudioStore(tmp_path / "anki_studio.sqlite")
    deck_id = store.ensure_deck("반도체 공정 & 영어회화", desired_retention=0.90)

    # When adding a 2-ordinal Cloze note at `now`
    now = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
    store.add_note(
        deck_id=deck_id,
        note_type="cloze",
        front_text="EUV 노광장비의 파장은 {{c1::13.5 nm}}이며 {{c2::High-NA::차세대 기술}}는 개구수를 0.55로 높인다.",
        now_iso=now.isoformat(),
    )

    # Then 2 independent due cards are created
    due = store.get_due_cards(deck_id=deck_id, as_of_iso=now.isoformat())
    assert len(due) == 2
    assert due[0]["rendered_question"].startswith("EUV 노광장비의 파장은 [...]")
    assert due[1]["rendered_question"].endswith("[차세대 기술]는 개구수를 0.55로 높인다.")

    # When reviewing card 1 with GOOD
    res = store.review_card(due[0]["card_id"], Rating.GOOD, reviewed_at=now)
    assert res["scheduled_days"] >= 3
    assert res["memory"].state == "review"

    # Then only 1 card remains immediately due at `now`
    remaining = store.get_due_cards(deck_id=deck_id, as_of_iso=now.isoformat())
    assert len(remaining) == 1
    assert remaining[0]["ordinal"] == 2


def test_import_apkg_archive_losslessly(tmp_path: Path) -> None:
    # Given a synthetic standard Anki .apkg archive containing collection.anki2
    anki2_path = tmp_path / "collection.anki2"
    conn = sqlite3.connect(str(anki2_path))
    conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT, tags TEXT)")
    conn.execute(
        "INSERT INTO notes (id, flds, tags) VALUES (101, ?, 'english speaking')",
        ("I'd like to follow up on our meeting.\x1f회의 후속 논의를 하고 싶습니다.",),
    )
    conn.execute(
        "INSERT INTO notes (id, flds, tags) VALUES (102, ?, 'semiconductor')",
        ("FinFET 대비 {{c1::GAA}}는 게이트 제어력이 우수하다.\x1f",),
    )
    conn.commit()
    conn.close()

    apkg_path = tmp_path / "Sample_Deck.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(anki2_path, arcname="collection.anki2")

    # When importing into AnkiStudioStore
    store = AnkiStudioStore(tmp_path / "studio.sqlite")
    count = store.import_apkg(apkg_path, target_deck_name="Imported Deck")
    assert count == 2

    due = store.get_due_cards()
    assert len(due) == 2
    assert any("follow up on" in c["rendered_question"] for c in due)
    assert any("[...]" in c["rendered_question"] for c in due)
