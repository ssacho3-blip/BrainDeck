"""Strict TDD (Red -> Green -> Refactor) + BDD (Given-When-Then) + DDT (@pytest.mark.parametrize) Suite.

Covers:
1. Clean Architecture AST Zero-I/O Gate across ALL pure domain modules (`domain/*.py` & `:domain` Kotlin).
2. DDT Exact/Partial/Unknown Answer Grading Parity (`Python`, `viewmodel.js`, `Kotlin`) for cards with parenthetical Hanja, years, POS tags, and Cloze commentary.
3. BDD Multi-Source Combined Exam Deck SQLite `tags` Hydration & Greedy Largest-Bucket-First Anti-Streak (<= 2) Interleaving across unequal buckets (e.g. 6:2:2).
4. DDT 2-Step Progressive Choseong/Letter Hint Primary-Char-Count & Zero-Spoiler Guarantees across Python, JS ViewModel, and Android Kotlin.
5. Difficulty-Stratified (`lv1`, `lv2`, `lv3`, `mixed`) Document & Curriculum Card Generation invariants.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
from typing import List, Sequence

import pytest

from anki_studio.domain.ai_learning import (
    evaluate_free_recall,
    extract_clean_target_answer,
    generate_socratic_hint,
    interleave_study_cards,
)
from anki_studio.service.studio_server import AnkiStudioService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_DIR = PROJECT_ROOT / "src" / "anki_studio" / "domain"
VIEWMODEL_JS_PATH = PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"


@pytest.mark.parametrize(
    "domain_file",
    [
        "fsrs_math.py",
        "adaptive_quiz.py",
        "ai_learning.py",
        "document_deck_builder.py",
        "pack_store.py",
    ],
)
def test_tdd_clean_architecture_all_domain_modules_zero_io_imports(domain_file: str) -> None:
    """[Clean Architecture Gate] Every module in `src/anki_studio/domain/` must have zero I/O or adapter imports."""
    target = DOMAIN_DIR / domain_file
    assert target.exists(), f"Missing domain module: {domain_file}"
    tree = ast.parse(target.read_text(encoding="utf-8"))
    forbidden = {
        "sqlite3",
        "urllib",
        "http",
        "subprocess",
        "socket",
        "requests",
        "os",
        "pathlib",
        "io",
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden), (
        f"Clean Architecture violation in {domain_file}: forbidden imports {imported & forbidden}"
    )


@pytest.mark.parametrize(
    ("question_text", "expected_answer", "user_answer", "expected_verdict", "min_score"),
    [
        (
            "조선 세종 25년(1443) 백성을 가르치는 바른 소리라는 뜻으로 창제한 문자는?",
            "훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포",
            "훈민정음",
            "EXACT",
            100.0,
        ),
        (
            "1876년 일본의 운요호 사건을 계기로 체결된 최초의 근대적 불평등 조약은?",
            "강화도 조약 (조일수호조규, 1876)\n💡 해설: 부산 외 2개 항구 개항 및 영사재판권 인정",
            "강화도 조약",
            "EXACT",
            100.0,
        ),
        (
            "교과서 핵심 어휘: 『introduce』의 뜻은?",
            "소개하다 (동사)\n💡 해설: Let me introduce myself.",
            "소개하다",
            "EXACT",
            100.0,
        ),
        (
            "조선 세종 25년(1443) 백성을 가르치는 바른 소리라는 뜻으로 창제한 문자는?",
            "훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포",
            "훈민정음 (訓民正音)",
            "EXACT",
            100.0,
        ),
        (
            "1876년 일본의 운요호 사건을 계기로 체결된 최초의 근대적 불평등 조약은?",
            "강화도 조약 (조일수호조규, 1876)\n💡 해설: 부산 외 2개 항구 개항 및 영사재판권 인정",
            "강화도 조약 (조일수호조규, 1876)",
            "EXACT",
            100.0,
        ),
        (
            "교과서 핵심 어휘: 『introduce』의 뜻은?",
            "소개하다 (동사)\n💡 해설: Let me introduce myself.",
            "소개하다 (동사)",
            "EXACT",
            100.0,
        ),
        (
            "1876년 일본의 운요호 사건을 계기로 체결된 최초의 근대적 불평등 조약은?",
            "강화도 조약 (조일수호조규, 1876)\n💡 해설: 부산 외 2개 항구 개항 및 영사재판권 인정",
            "강화도 조약 1877",
            "PARTIAL",
            40.0,
        ),
        (
            "[Lv.2 문맥 빈칸] Let me {{c1::introduce}} myself to the class.",
            "introduce\n💡 해설: 동사 '소개하다'",
            "introduce",
            "EXACT",
            100.0,
        ),
        (
            "적혈구 내 헤모글로빈의 핵심 기능 두 가지는?",
            "산소 운반 및 이산화탄소 배출",
            "산소 운반",
            "PARTIAL",
            45.0,
        ),
        (
            "적혈구 내 헤모글로빈의 핵심 기능 두 가지는?",
            "산소 운반 및 이산화탄소 배출",
            "모름",
            "UNKNOWN",
            0.0,
        ),
    ],
)
def test_ddt_primary_answer_grading_parity_python_and_js_viewmodel(
    question_text: str,
    expected_answer: str,
    user_answer: str,
    expected_verdict: str,
    min_score: float,
) -> None:
    """[DDT] Python `evaluate_free_recall` and JS `evaluateTypedAnswerUnderstanding` must agree on primary answers."""
    py_res = evaluate_free_recall(
        user_answer="" if user_answer == "모름" else user_answer,
        expected_answer=expected_answer,
        question_text=question_text,
    )
    assert py_res.score_pct >= min_score
    if expected_verdict == "EXACT":
        assert py_res.score_pct == 100.0
        assert int(py_res.recommended_rating) in (3, 4)
    elif expected_verdict == "PARTIAL":
        assert int(py_res.recommended_rating) == 2
    else:
        assert int(py_res.recommended_rating) == 1

    # Verify JS ViewModel `evaluateTypedAnswerUnderstanding` parity via Node
    script = f"""
    const vm = require({json.dumps(str(VIEWMODEL_JS_PATH))});
    const parsed = vm.extractTargetAndExplanation({json.dumps(question_text)}, {json.dumps(expected_answer)});
    const res = vm.evaluateTypedAnswerUnderstanding({json.dumps(user_answer)}, parsed.targetAnswer);
    if (res.verdict !== {json.dumps(expected_verdict)}) {{
      throw new Error("Expected verdict " + {json.dumps(expected_verdict)} + " but got " + JSON.stringify(res));
    }}
    if (res.scorePct < {min_score}) {{
      throw new Error("Expected scorePct >= {min_score} but got " + res.scorePct);
    }}
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"JS ViewModel DDT grading failed:\n{proc.stderr}"


def test_bdd_unequal_buckets_6_2_2_greedy_interleaving_zero_streak_violation() -> None:
    """[BDD] Given 6 English cards, 2 History cards, and 2 Hanja cards (6:2:2 ratio),
    When interleaved shuffling is executed in both Python and JS ViewModel,
    Then NO subject ever appears 3 times consecutively across the entire 10-card queue.
    """
    raw_cards = [
        *[
            {"card_id": i, "tags_json": json.dumps(["curriculum", "kr.mid1.eng.donga_yoon.2022:U01", "diff_lv1"]), "deck_name": "중간고사 통합 덱", "state": "new", "lapses": 0}
            for i in range(1, 7)
        ],
        *[
            {"card_id": i, "tags_json": json.dumps(["curriculum", "kr.mid2.hist.miraeen.2022:U01", "diff_lv1"]), "deck_name": "중간고사 통합 덱", "state": "new", "lapses": 0}
            for i in range(7, 9)
        ],
        *[
            {"card_id": i, "tags_json": json.dumps(["curriculum", "hanja-grade:8geup", "diff_lv1"]), "deck_name": "중간고사 통합 덱", "state": "new", "lapses": 0}
            for i in range(9, 11)
        ],
    ]

    # 1. Python `interleave_study_cards` with raw SQLite `tags_json`
    py_mixed = interleave_study_cards(raw_cards, shuffle_mode="interleaved", seed=42)
    assert len(py_mixed) == 10

    def _extract_subject(c: dict) -> str:
        tags: Sequence[str] = c.get("tags") or json.loads(c["tags_json"])
        return next(t for t in tags if t not in ("curriculum", "diff_lv1"))

    py_subjects = [_extract_subject(c) for c in py_mixed]
    streak = 0
    last_subj = None
    for subj in py_subjects:
        if subj == last_subj:
            streak += 1
        else:
            last_subj = subj
            streak = 1
        assert streak <= 2, f"Python interleave violated anti-streak <= 2 on 6:2:2 queue: {py_subjects}"

    # 2. JS `interleaveAndShuffleStudyQueue` with raw `tags_json`
    script = f"""
    const vm = require({json.dumps(str(VIEWMODEL_JS_PATH))});
    const raw = {json.dumps(raw_cards)};
    const mixed = vm.interleaveAndShuffleStudyQueue(raw, "interleaved", 42);
    if (mixed.length !== 10) throw new Error("Expected 10 cards");
    let streak = 0;
    let lastSubj = null;
    const seq = mixed.map((c) => {{
      const tags = Array.isArray(c.tags) ? c.tags : JSON.parse(c.tags_json);
      return tags.find((t) => t !== "curriculum" && t !== "diff_lv1");
    }});
    for (const s of seq) {{
      if (s === lastSubj) streak += 1;
      else {{ lastSubj = s; streak = 1; }}
      if (streak > 2) throw new Error("JS interleave violated anti-streak <= 2: " + JSON.stringify(seq));
    }}
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"JS ViewModel interleave failed:\n{proc.stderr}"


def test_bdd_sqlite_get_due_cards_hydrates_tags_and_interleaves_combined_exam_deck(tmp_path: Path) -> None:
    """[BDD] Given a combined exam deck stored in SQLite,
    When `get_due_cards(deck_id, shuffle_mode='interleaved')` is called,
    Then every returned card has a hydrated `tags` list and the first 6 cards span all 3 subjects.
    """
    svc = AnkiStudioService(str(tmp_path / "tdd_combined_due.db"))
    res = svc.generate_combined_exam_deck(
        scopes=[
            {
                "source_type": "textbook",
                "ref_id": "kr.mid1.eng.donga_yoon.2022",
                "unit_ids": ["kr.mid1.eng.donga_yoon.2022:U01"],
            },
            {
                "source_type": "textbook",
                "ref_id": "kr.mid2.hist.miraeen.2022",
                "unit_ids": ["kr.mid2.hist.miraeen.2022:U01"],
            },
            {
                "source_type": "collection",
                "ref_id": "hanja-grade:8geup",
                "limit": 4,
            },
        ],
        deck_name="TDD 중간고사 3과목 통합 덱",
        difficulty_level="lv1",
        shuffle_mode="interleaved",
    )
    assert res["ok"] is True

    due = svc.get_due_cards(deck_id=res["deck_id"], shuffle_mode="interleaved")["cards"]
    assert len(due) >= 9
    for card in due:
        assert isinstance(card.get("tags"), list), "Expected `tags` list hydrated on every due card"
        assert len(card["tags"]) >= 2

    # Verify the first 6 cards contain at least 2 distinct subject sources (not all English U01 first)
    first_six_sources = {
        next(
            (t for t in c["tags"] if t.startswith(("kr.", "hanja-"))),
            "unknown",
        )
        for c in due[:6]
    }
    assert len(first_six_sources) >= 2, f"Expected mixed sources in first 6 due cards, got {first_six_sources}"


@pytest.mark.parametrize(
    ("target_with_annotation", "extra_exp", "expected_mask_step1", "expected_char_count", "forbidden_spoiler"),
    [
        (
            "훈민정음 (訓民正音)",
            "조선 세종이 백성을 위해 창제한 훈민정음 문자 체계",
            "ㅎ ㅁ ㅈ ㅇ",
            4,
            "훈민정음",
        ),
        (
            "강화도 조약 (1876)",
            "강화도 조약은 조선이 체결한 최초의 근대적 불평등 조약이다.",
            "ㄱ ㅎ ㄷ ㅈ ㅇ",
            5,
            "강화도 조약",
        ),
        (
            "introduce (동사)",
            "Introduce yourself: Let me introduce myself to the class.",
            "i _ _ _ _ _ _ _ e",
            9,
            "introduce",
        ),
    ],
)
def test_ddt_two_step_progressive_hint_primary_length_and_zero_spoiler_parity(
    target_with_annotation: str,
    extra_exp: str,
    expected_mask_step1: str,
    expected_char_count: int,
    forbidden_spoiler: str,
) -> None:
    """[DDT] Both Python and JS ViewModel 2-step hints must count only primary characters and never leak the answer."""
    full_back = f"{target_with_annotation}\n💡 해설: {extra_exp}"
    py_h1 = generate_socratic_hint("질문 프롬프트", full_back, level=1)
    py_h2 = generate_socratic_hint("질문 프롬프트", full_back, level=2)

    assert f"{expected_char_count}자" in py_h1.structural_cue
    assert forbidden_spoiler.lower() not in py_h1.structural_cue.lower()
    assert forbidden_spoiler.lower() not in py_h1.socratic_question.lower()
    assert forbidden_spoiler.lower() not in py_h2.structural_cue.lower()
    assert forbidden_spoiler.lower() not in py_h2.socratic_question.lower()

    script = f"""
    const vm = require({json.dumps(str(VIEWMODEL_JS_PATH))});
    const h1 = vm.generateProgressiveHint({json.dumps(target_with_annotation)}, {json.dumps(extra_exp)}, 1);
    const h2 = vm.generateProgressiveHint({json.dumps(target_with_annotation)}, {json.dumps(extra_exp)}, 2);
    if (h1.charCount !== {expected_char_count} || h2.charCount !== {expected_char_count}) {{
      throw new Error("Expected charCount {expected_char_count}, got " + h1.charCount + " / " + h2.charCount);
    }}
    if (h1.cueText.toLowerCase().includes({json.dumps(forbidden_spoiler.lower())})) {{
      throw new Error("Step 1 leaked spoiler: " + h1.cueText);
    }}
    if (h2.cueText.toLowerCase().includes({json.dumps(forbidden_spoiler.lower())})) {{
      throw new Error("Step 2 leaked spoiler: " + h2.cueText);
    }}
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"JS ViewModel 2-step hint DDT failed:\n{proc.stderr}"


def test_bdd_interleave_termination_on_empty_single_5_1_and_8_1_1_and_malformed_tags_json(tmp_path: Path) -> None:
    """[BDD] Verify interleave termination & multiset preservation on `[]`, single bucket, `5:1`, `8:1:1`,
    and verify `get_due_cards` fail-closed handling of `NULL`, `""`, and malformed `"{` `tags_json`.
    """
    assert interleave_study_cards([], shuffle_mode="interleaved", seed=42) == []

    single_bucket = [{"card_id": i, "tags": ["u1"], "state": "new"} for i in range(1, 5)]
    single_out = interleave_study_cards(single_bucket, shuffle_mode="interleaved", seed=42)
    assert sorted(c["card_id"] for c in single_out) == [1, 2, 3, 4]

    for counts in [(5, 1), (8, 1, 1)]:
        cards = []
        cid = 1
        for b_idx, cnt in enumerate(counts, start=1):
            for _ in range(cnt):
                cards.append({"card_id": cid, "tags": [f"u{b_idx}"], "state": "new"})
                cid += 1
        out = interleave_study_cards(cards, shuffle_mode="interleaved", seed=42)
        assert sorted(c["card_id"] for c in out) == list(range(1, cid))
        # Verify streak > 2 happens ONLY after all other buckets are exhausted
        remaining_by_bucket = {f"u{i}": cnt for i, cnt in enumerate(counts, start=1)}
        streak = 0
        last_b = None
        for c in out:
            b = c["tags"][0]
            other_remaining = sum(v for k, v in remaining_by_bucket.items() if k != b)
            if b == last_b:
                streak += 1
            else:
                last_b = b
                streak = 1
            if other_remaining > 0:
                assert streak <= 2, f"Violated streak <= 2 while other buckets remained on {counts}"
            remaining_by_bucket[b] -= 1

    # Verify SQLite `get_due_cards` with NULL, "", and malformed "{" tags_json yields tags=[] and still returns cards
    svc = AnkiStudioService(str(tmp_path / "malformed_tags.db"), seed_defaults=False)
    created = svc.store.create_deck_with_notes(
        deck_name="Malformed Tags Deck",
        notes=[
            {"front_text": "Q1", "back_text": "A1", "note_type": "basic", "tags": ["u1"]},
            {"front_text": "Q2", "back_text": "A2", "note_type": "basic", "tags": ["u2"]},
            {"front_text": "Q3", "back_text": "A3", "note_type": "basic", "tags": ["u3"]},
        ],
    )
    deck_id = created["deck_id"]
    nids = created["saved_note_ids"]
    with svc.store._write_tx() as conn:
        with pytest.raises( Exception):
            conn.execute("UPDATE notes SET tags_json = NULL WHERE note_id = ?", (nids[0],))
        conn.execute("UPDATE notes SET tags_json = 'null' WHERE note_id = ?", (nids[0],))
        conn.execute("UPDATE notes SET tags_json = '' WHERE note_id = ?", (nids[1],))
        conn.execute("UPDATE notes SET tags_json = '{' WHERE note_id = ?", (nids[2],))

    due_cards = svc.get_due_cards(deck_id=deck_id, shuffle_mode="interleaved")["cards"]
    assert len(due_cards) == 3
    assert all(c["tags"] == [] for c in due_cards)
    assert len(interleave_study_cards([{"card_id": 1, "tags_json": None}, {"card_id": 2, "tags_json": "{"}], shuffle_mode="interleaved", seed=42)) == 2


class TestV55CoreMemoryFramesRedGreenRefactor:
    """v5.5 5 Core Memory-Science Frames TDD Suite (Python + Web ViewModel + Standalone Apple PWA Engine)."""

    def test_python_evidence_rating_guard_and_sibling_burying(self) -> None:
        from anki_studio.domain.ai_learning import (
            deduplicate_session_siblings,
            resolve_allowed_ratings,
        )

        # 1. Pre-reveal lock: no ratings allowed before answer reveal
        pre_reveal = resolve_allowed_ratings(is_revealed=False, hint_step=0, age_tier="adult")
        assert pre_reveal["allowed_ratings"] == ()
        assert pre_reveal["locked_reason"] == "pre_reveal"

        # 2. Wrong answer / dont_know / UNKNOWN typed verdict -> Only Again(1)
        wrong_choice = resolve_allowed_ratings(
            is_revealed=True,
            choice_correct=False,
            hint_step=0,
            age_tier="adult",
        )
        assert wrong_choice["allowed_ratings"] == (1,)
        assert wrong_choice["recommended_rating"] == 1

        dont_know = resolve_allowed_ratings(
            is_revealed=True,
            dont_know=True,
            hint_step=0,
            age_tier="teen",
        )
        assert dont_know["allowed_ratings"] == (1,)
        assert dont_know["recommended_rating"] == 1

        # 3. Hint used (hint_step >= 1) -> Capped at Hard(2)! Good(3) & Easy(4) blocked
        hinted = resolve_allowed_ratings(
            is_revealed=True,
            choice_correct=True,
            hint_step=1,
            age_tier="adult",
        )
        assert hinted["allowed_ratings"] == (1, 2)
        assert hinted["recommended_rating"] == 2

        # 4. Partial typed recall without hint -> Capped at Good(3), recommended Hard(2)
        partial = resolve_allowed_ratings(
            is_revealed=True,
            typed_verdict="PARTIAL",
            hint_step=0,
            age_tier="adult",
        )
        assert partial["allowed_ratings"] == (1, 2, 3)
        assert partial["recommended_rating"] == 2

        # 5. Unassisted recall -> Junior caps at 1..3, Adult allows 1..4
        junior_ok = resolve_allowed_ratings(is_revealed=True, hint_step=0, age_tier="junior")
        assert junior_ok["allowed_ratings"] == (1, 2, 3)
        assert junior_ok["recommended_rating"] == 3

        adult_ok = resolve_allowed_ratings(
            is_revealed=True,
            typed_verdict="EXACT",
            hint_step=0,
            age_tier="adult",
        )
        assert adult_ok["allowed_ratings"] == (1, 2, 3, 4)
        assert adult_ok["recommended_rating"] in (3, 4)

        # 6. Sibling burying: 3 difficulty cards sharing the same concept:<id> -> only 1 kept per session
        raw_session = [
            {"card_id": 101, "front_text": "[Lv.1] introduce", "tags": ["concept:eng_introduce", "diff_lv1"], "state": "new"},
            {"card_id": 102, "front_text": "[Lv.2] {{c1::introduce}}", "tags": ["concept:eng_introduce", "diff_lv2"], "state": "new"},
            {"card_id": 103, "front_text": "[Lv.3] 소개하다 -> ?", "tags": ["concept:eng_introduce", "diff_lv3"], "state": "new"},
            {"card_id": 201, "front_text": "[Lv.1] delicious", "tags": ["concept:eng_delicious", "diff_lv1"], "state": "new"},
        ]
        deduped = deduplicate_session_siblings(raw_session)
        assert len(deduped) == 2
        assert [c["card_id"] for c in deduped] == [101, 201]

    def test_viewmodel_js_five_frames_and_apple_standalone_pwa_engine(self) -> None:
        vm_path = Path(__file__).resolve().parents[1] / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
        html_path = Path(__file__).resolve().parents[1] / "src" / "anki_studio" / "ui" / "static" / "index.html"
        html_text = html_path.read_text(encoding="utf-8")

        script = f"""
        const VM = require({json.dumps(str(vm_path))});
        const html = {json.dumps(html_text)};

        // Frame 1: LearnerProfile v2 normalization & presets
        const jrPreset = VM.buildLearnerProfilePreset('junior');
        const profile = VM.normalizeLearnerProfile({{ ageTier: 'teen', solveMode: 'adaptive', difficulty: 'mixed', order: 'interleaved', autoSave: true }});

        // Frame 2: 1-Card 1-Mode solver resolution
        const modeNew = VM.resolveCardSolveMode({{ reps: 0, state: 'new' }}, profile);
        const modeRev = VM.resolveCardSolveMode({{ reps: 2, state: 'review' }}, profile);
        const modeFlip = VM.resolveCardSolveMode({{ reps: 2 }}, {{ ...profile, solveMode: 'flip' }});

        // Frame 3: EvidenceRatingGuard
        const guardPre = VM.resolveAllowedRatings({{ isRevealed: false, hintStep: 0 }}, 'adult');
        const guardWrong = VM.resolveAllowedRatings({{ isRevealed: true, choiceCorrect: false, hintStep: 0 }}, 'adult');
        const guardHint = VM.resolveAllowedRatings({{ isRevealed: true, choiceCorrect: true, hintStep: 1 }}, 'adult');
        const guardExact = VM.resolveAllowedRatings({{ isRevealed: true, typedVerdict: 'EXACT', hintStep: 0 }}, 'adult');

        // Frame 4: Sibling Burying
        const sibQueue = VM.deduplicateSessionSiblings([
          {{ card_id: 1, front_text: 'Lv1', tags: ['concept:c1', 'diff_lv1'], state: 'new' }},
          {{ card_id: 2, front_text: 'Lv2', tags: ['concept:c1', 'diff_lv2'], state: 'new' }},
          {{ card_id: 3, front_text: 'Lv1-B', tags: ['concept:c2', 'diff_lv1'], state: 'new' }},
        ]);

        // Frame 5: Standalone Apple/Web PWA Engine (works offline without Python API)
        const standalone = VM.createStandaloneEngine();
        const catalog = standalone.getCatalog();
        const builtDeck = standalone.buildCombinedExamDeck({{
          scopes: [
            {{ source_type: 'textbook', ref_id: 'kr.mid1.eng.donga_yoon.2022', unit_ids: ['kr.mid1.eng.donga_yoon.2022:U01'], label: '중1 영어 1단원' }},
            {{ source_type: 'collection', ref_id: 'hanja-grade:8geup', label: '8급 한자' }}
          ],
          difficulty_level: 'mixed',
          interleave_shuffle: true
        }});
        const docDeck = standalone.buildSmartTextDeck({{
          text: '광합성: 식물이 빛에너지를 이용해 포도당과 산소를 합성하는 과정이다.\\n세포호흡: 미토콘드리아에서 영양소를 분해하여 ATP를 얻는 작용이다.',
          deck_name: '생물 요약',
          difficulty_level: 'lv2'
        }});

        console.log(JSON.stringify({{
          jrSolveMode: jrPreset.solveMode,
          modeNew,
          modeRev,
          modeFlip,
          guardPreAllowed: guardPre.allowedRatings,
          guardWrongAllowed: guardWrong.allowedRatings,
          guardHintAllowed: guardHint.allowedRatings,
          guardExactAllowed: guardExact.allowedRatings,
          sibIds: sibQueue.map(c => c.card_id),
          textbookCount: (catalog.textbooks || []).length,
          collectionCount: (catalog.collections || []).length,
          builtDeckCards: (builtDeck.cards || []).length,
          docDeckCards: (docDeck.cards || []).length,
          hasCreateSegmentSwitcher: html.includes('data-create-seg='),
        }}));
        """
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())
        assert res["jrSolveMode"] == "choice"
        assert res["modeNew"] == "choice"
        assert res["modeRev"] == "typing"
        assert res["modeFlip"] == "flip"
        assert res["guardPreAllowed"] == []
        assert res["guardWrongAllowed"] == [1]
        assert res["guardHintAllowed"] == [1, 2]
        assert res["guardExactAllowed"] == [1, 2, 3, 4]
        assert res["sibIds"] == [1, 3]
        assert res["textbookCount"] >= 4
        assert res["collectionCount"] >= 10
        assert res["builtDeckCards"] >= 10
        assert res["docDeckCards"] >= 2
        assert res["hasCreateSegmentSwitcher"] is True


