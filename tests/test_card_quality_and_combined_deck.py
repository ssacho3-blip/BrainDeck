from __future__ import annotations

import json
import sqlite3
import pytest

from anki_studio.adapters.reference_pack_store import (
    build_starter_k12_and_exam_pack,
)
from anki_studio.domain.ai_learning import (
    decompose_leech_card,
    evaluate_free_recall,
    extract_clean_target_answer,
    extract_smart_cards_deterministic,
    generate_socratic_hint,
    interleave_study_cards,
)
from anki_studio.domain.document_deck_builder import (
    DocumentBlock,
    ExtractedDocument,
    _select_semantic_hinge_token,
    build_deck_plan,
)
from anki_studio.service.studio_server import AnkiStudioService


def test_zero_front_spoilers_in_builtin_collections_and_textbooks(tmp_path) -> None:
    """Verify that no builtin textbook or collection card leaks the answer in the front prompt."""
    pack_path = tmp_path / "starter_pack.sqlite"
    build_starter_k12_and_exam_pack(pack_path)
    conn = sqlite3.connect(str(pack_path))
    conn.row_factory = sqlite3.Row
    try:
        khist_rows = conn.execute(
            """
            SELECT e.entry_key, e.headword, e.gloss_ko, e.facet_json
            FROM ref_entries e
            JOIN ref_collections c ON e.entry_key = c.entry_key
            WHERE c.collection_id = 'khist:essential'
            """
        ).fetchall()
        assert len(khist_rows) >= 4
        for row in khist_rows:
            facet = json.loads(row["facet_json"])
            clean_front = facet.get("clean_front") or row["headword"]
            target_ans = facet.get("target_answer", "")
            assert target_ans
            assert target_ans not in clean_front, f"Spoiler '{target_ans}' found in front '{clean_front}'"

        # Verify middle school history Mesopotamia & Athens do not spoil the answer in front
        meso_row = conn.execute(
            "SELECT headword, gloss_ko, facet_json FROM ref_entries WHERE entry_key = 'khist:mid2:mesopotamia'"
        ).fetchone()
        assert meso_row is not None
        meso_facet = json.loads(meso_row["facet_json"])
        assert "메소포타미아" not in meso_facet.get("clean_front", "")
        assert "함무라비" not in meso_facet.get("clean_front", "")

        # Verify elementary dictation does not leak the target spelling in the front blank
        dict_row = conn.execute(
            "SELECT headword, gloss_ko, facet_json FROM ref_entries WHERE entry_key = 'dict:g1_01'"
        ).fetchone()
        assert dict_row is not None
        dict_facet = json.loads(dict_row["facet_json"])
        assert "꽃이" not in dict_row["headword"]
    finally:
        conn.close()


@pytest.mark.parametrize("difficulty_level", ["lv1", "lv2", "lv3", "mixed"])
def test_difficulty_stratified_card_generation_across_engines(difficulty_level: str) -> None:
    text = (
        "광합성: 식물이 빛에너지를 이용해 이산화탄소와 물로 포도당과 산소를 합성하는 과정이다.\n"
        "세포호흡: 세포 내 미토콘드리아에서 영양소를 분해하여 생활 에너지를 얻는 작용이다."
    )
    smart_cards = extract_smart_cards_deterministic(text, max_cards=10, difficulty_level=difficulty_level)
    assert len(smart_cards) >= 2
    if difficulty_level == "lv1":
        assert all(c.note_type == "basic" for c in smart_cards)
    elif difficulty_level == "lv2":
        assert all(c.note_type == "cloze" and "{{c1::" in c.front_text for c in smart_cards)
    elif difficulty_level == "lv3":
        assert any("Lv.3" in c.front_text for c in smart_cards)

    doc = ExtractedDocument(
        blocks=(DocumentBlock(kind="paragraph", text=text, page=1, confidence=0.98),),
        title_hint="생물 요약 노트",
        source_kind="text",
        page_count=1,
    )
    doc_plan = build_deck_plan(
        doc=doc,
        difficulty_level=difficulty_level,
    )
    assert doc_plan.status == "OK"
    assert len(doc_plan.cards) >= 2


def test_semantic_hinge_token_selection_avoids_longest_word_boilerplate() -> None:
    rhs = "미토콘드리아에서 포도당을 분해하여 ATP를 합성하는 세포 호흡 과정이다"
    candidates = ["미토콘드리아에서", "포도당을", "합성하는", "과정이다"]
    chosen = _select_semantic_hinge_token(candidates, rhs, "science")
    assert chosen in ("미토콘드리아에서", "포도당을", "합성하는")
    assert chosen != "과정이다"


def test_clean_target_answer_and_two_step_choseong_hints() -> None:
    target, extra = extract_clean_target_answer(
        front_text="[Lv.2 문맥 빈칸] Let me {{c1::introduce}} myself to the class.",
        back_text="introduce\n💡 해설: 동사 '소개하다' — Let me introduce myself",
    )
    assert target == "introduce"
    assert "소개하다" in extra

    # Typing just the blank word 'introduce' on a Cloze card must score 100% EXACT
    eval_res = evaluate_free_recall(
        user_answer="introduce",
        expected_answer="introduce\n💡 해설: 동사 '소개하다' — Let me introduce myself",
        question_text="[Lv.2 문맥 빈칸] Let me {{c1::introduce}} myself to the class.",
    )
    assert eval_res.score_pct == 100.0
    assert int(eval_res.recommended_rating) in (3, 4)

    # Korean Choseong hint step 1 & step 2
    hint1 = generate_socratic_hint(
        question_text="조선 세종 25년 백성을 가르치는 바른 소리라는 뜻으로 창제한 문자는?",
        target_answer="훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포",
        level=1,
    )
    assert "ㅎ ㅁ ㅈ ㅇ" in hint1.structural_cue
    assert "훈민정음" not in hint1.structural_cue

    hint2 = generate_socratic_hint(
        question_text="조선 세종 25년 백성을 가르치는 바른 소리라는 뜻으로 창제한 문자는?",
        target_answer="훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포",
        level=2,
    )
    assert "훈" in hint2.structural_cue
    assert "훈민정음" not in hint2.structural_cue

    # Short 1-word card guard in decompose_leech_card
    sub_cards = decompose_leech_card("교과서 핵심 어휘: 『introduce』의 뜻은?", "소개하다")
    assert len(sub_cards) == 2
    assert "ㅅ ㄱ ㅎ ㄷ" in sub_cards[0].front_text


def test_combined_exam_scope_deck_and_interleaved_shuffle(tmp_path) -> None:
    db_path = tmp_path / "combined_test.db"
    svc = AnkiStudioService(str(db_path))

    res = svc.generate_combined_exam_deck(
        scopes=[
            {
                "source_type": "textbook",
                "ref_id": "kr.mid1.eng.donga_yoon.2022",
                "unit_ids": ["kr.mid1.eng.donga_yoon.2022:U01", "kr.mid1.eng.donga_yoon.2022:U02"],
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
        deck_name="🎯 1학기 중간고사 통합 랜덤 덱",
        difficulty_level="mixed",
        shuffle_mode="interleaved",
    )
    assert res["ok"] is True
    assert len(res["source_summary"]) == 3
    assert res["saved_count"] >= 10

    due_res = svc.get_due_cards(deck_id=res["deck_id"], shuffle_mode="interleaved")
    due = due_res["cards"]
    assert len(due) >= 10
    assert all("target_answer" in c and "extra_explanation" in c for c in due)

    # Verify suspend_card removes card from active due queue
    first_card_id = due[0]["card_id"]
    susp = svc.suspend_card(first_card_id)
    assert susp["ok"] is True
    assert susp["suspended"] is True
    due_after = svc.get_due_cards(deck_id=res["deck_id"], shuffle_mode="interleaved")["cards"]
    assert all(c["card_id"] != first_card_id for c in due_after)


def test_web_viewmodel_js_progressive_hint_and_interleaved_shuffle() -> None:
    import subprocess
    from pathlib import Path

    vm_path = Path(__file__).resolve().parents[1] / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    script = f"""
    import vm from {json.dumps(vm_path.as_uri())};
    const {{
      extractTargetAndExplanation,
      generateProgressiveHint,
      interleaveAndShuffleStudyQueue,
    }} = vm;

    const parsed = extractTargetAndExplanation(
      "Let me {{{{c1::introduce}}}} myself.",
      "introduce\\n💡 해설: 소개하다 (동사)"
    );
    if (parsed.targetAnswer !== "introduce") throw new Error("Bad target: " + parsed.targetAnswer);
    if (!parsed.extraExplanation.includes("소개하다")) throw new Error("Bad extra: " + parsed.extraExplanation);

    const h1 = generateProgressiveHint("훈민정음", "1443년 세종 창제", 1);
    if (!h1.cueText.includes("ㅎ ㅁ ㅈ ㅇ") || h1.cueText.includes("훈민정음")) {{
      throw new Error("Bad step 1 hint: " + JSON.stringify(h1));
    }}

    const cards = [
      {{ card_id: 1, tags: ["u1"], state: "new", lapses: 0 }},
      {{ card_id: 2, tags: ["u1"], state: "new", lapses: 0 }},
      {{ card_id: 3, tags: ["u1"], state: "new", lapses: 0 }},
      {{ card_id: 4, tags: ["u2"], state: "new", lapses: 0 }},
      {{ card_id: 5, tags: ["u2"], state: "new", lapses: 0 }},
      {{ card_id: 6, tags: ["u3"], state: "relearning", lapses: 2 }},
    ];
    const mixed = interleaveAndShuffleStudyQueue(cards, "interleaved", 42);
    if (mixed.length !== 6) throw new Error("Length mismatch");
    """
    proc = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Node viewmodel test failed: {proc.stderr}"


def test_interleave_anti_streak_and_combined_deck_fail_closed(tmp_path) -> None:
    """Verify anti-streak (<=2 while other buckets remain), unequal buckets, and fail-closed validation."""
    raw_cards = [
        {"card_id": 1, "tags": ["u1"], "state": "relearning", "lapses": 3},
        {"card_id": 2, "tags": ["u1"], "state": "relearning", "lapses": 2},
        {"card_id": 3, "tags": ["u1"], "state": "relearning", "lapses": 1},
        {"card_id": 4, "tags": ["u1"], "state": "new", "lapses": 0},
        {"card_id": 5, "tags": ["u2"], "state": "new", "lapses": 0},
        {"card_id": 6, "tags": ["u2"], "state": "new", "lapses": 0},
        {"card_id": 7, "tags": ["u3"], "state": "new", "lapses": 0},
        {"card_id": 8, "tags": ["u3"], "state": "new", "lapses": 0},
    ]
    mixed = interleave_study_cards(raw_cards, shuffle_mode="interleaved", seed=2026)
    assert len(mixed) == 8
    # Check that within the first 6 cards (while multiple buckets remain), streak of u1 never exceeds 2
    streak = 0
    last_tag = None
    for c in mixed[:6]:
        tag = c["tags"][0]
        if tag == last_tag:
            streak += 1
        else:
            last_tag = tag
            streak = 1
        assert streak <= 2, f"Anti-streak violated in first 6 cards: {[x['tags'][0] for x in mixed]}"

    db_path = tmp_path / "fail_closed_combined.db"
    svc = AnkiStudioService(str(db_path))
    with pytest.raises(ValueError):
        svc.generate_combined_exam_deck(scopes=[])
    with pytest.raises(ValueError):
        svc.generate_combined_exam_deck(scopes=[{"source_type": "textbook", "ref_id": "nonexistent.tb"}])
    with pytest.raises(ValueError):
        svc.generate_combined_exam_deck(scopes=[{"source_type": "collection", "ref_id": "nonexistent:col"}])


