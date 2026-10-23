"""ATDD / BDD / DDT Tests for Universal Document & Photo Deck Builder (`domain/document_deck_builder.py`)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import pytest

from anki_studio.domain.ai_learning import GeneratedCardSpec
from anki_studio.domain.document_deck_builder import (
    DocumentBlock,
    ExtractedDocument,
    SourcedCard,
    build_deck_plan,
    classify_block_pattern,
    ground_cards,
    infer_category,
    infer_deck_name,
    normalize_card_front_key,
)


def test_t13_document_deck_builder_ast_zero_io_imports() -> None:
    """T13: Pure domain module `document_deck_builder.py` must have zero external I/O imports."""
    target = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "anki_studio"
        / "domain"
        / "document_deck_builder.py"
    )
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
    assert imported.isdisjoint(forbidden), f"Forbidden I/O imports in domain: {imported & forbidden}"


def test_t1_t2_t3_five_card_patterns_and_source_pages() -> None:
    """T1, T2, T3: Definitions, numbered lists, causal/compare, statute/numeric, and language pairs."""
    doc = ExtractedDocument(
        title_hint="행정법 및 의학 통합 노트",
        source_kind="pdf",
        page_count=3,
        blocks=(
            DocumentBlock(
                kind="paragraph",
                text="처분성: 행정청이 행하는 구체적 사실에 관한 법집행으로서의 공권력 행사를 말한다.",
                page=1,
                confidence=0.95,
            ),
            DocumentBlock(
                kind="list_item",
                text="행정행위의 부관 종류 1) 조건 2) 기한 3) 부담 4) 철회권 유보",
                page=2,
                confidence=0.92,
            ),
            DocumentBlock(
                kind="paragraph",
                text="행정소송법 제20조 제1항에 따라 취소소송은 처분이 있음을 안 날부터 90일 이내에 제기하여야 한다.",
                page=2,
                confidence=0.96,
            ),
            DocumentBlock(
                kind="paragraph",
                text="기속행위는 법규에 의해 일의적으로 결정되기 때문에 부관을 붙일 수 없는 반면 재량행위는 부관을 붙일 수 있다.",
                page=3,
                confidence=0.91,
            ),
            DocumentBlock(
                kind="paragraph",
                text="소멸시효를 원용하다 -> invoke the statute of limitations",
                page=3,
                confidence=0.99,
            ),
        ),
    )
    plan = build_deck_plan(doc, max_cards=20)
    assert plan.status == "OK"
    assert plan.category == "law"
    assert len(plan.cards) == 5
    patterns = {c.pattern for c in plan.cards}
    assert patterns == {
        "definition",
        "numbered_list",
        "statute_numeric",
        "causal_compare",
        "language_pair",
    }
    # Verify T2: numbered list keeps all 4 items in back_text and masks items in front_text
    list_card = next(c for c in plan.cards if c.pattern == "numbered_list")
    assert list_card.source_page == 2
    for item in ("조건", "기한", "부담", "철회권 유보"):
        assert item in list_card.spec.back_text

    # Verify T3: statute & numeric unit (`제20조`, `90일 이내`) are masked as Cloze targets
    stat_card = next(c for c in plan.cards if c.pattern == "statute_numeric")
    assert "{{c1::제20조::조문}}" in stat_card.spec.front_text
    assert "{{c2::90일 이내::수치·단위}}" in stat_card.spec.front_text


def test_t4_grounding_discards_ungrounded_llm_cards() -> None:
    """T4: Any card whose answer tokens do not exist in the source document is discarded."""
    doc = ExtractedDocument(
        title_hint="반도체 공정 기초",
        source_kind="pdf",
        page_count=1,
        blocks=(
            DocumentBlock(
                kind="paragraph",
                text="EUV 리소그래피: 13.5nm 파장의 극자외선을 사용하여 미세 회로 패턴을 노광하는 공정 기술이다.",
                page=1,
                confidence=0.95,
            ),
        ),
    )
    hallucinated = SourcedCard(
        spec=GeneratedCardSpec(
            note_type="basic",
            front_text="양자컴퓨터 초전도 큐비트의 동작 온도는?",
            back_text="절대영도에 가까운 15밀리켈빈(mK) 극저온 환경",
            tags=("ai",),
            rationale="LLM hallucinated card",
        ),
        pattern="definition",
        source_page=1,
        source_excerpt="없음",
    )
    plan = build_deck_plan(doc, extra_llm_cards=(hallucinated,))
    assert plan.status == "OK"
    assert plan.stats.dropped_ungrounded == 1
    assert len(plan.cards) == 1
    assert "EUV" in plan.cards[0].spec.front_text


@pytest.mark.parametrize(
    ("conf", "expected_kept", "expected_low", "expected_unmeasured"),
    [
        (0.59, False, 1, 0),
        (0.60, True, 0, 0),
        (None, True, 0, 1),
    ],
)
def test_t5_confidence_boundary_and_null_handling(
    conf: float | None,
    expected_kept: bool,
    expected_low: int,
    expected_unmeasured: int,
) -> None:
    """T5: Confidence 0.59 is excluded, 0.60 is included (boundary), None is counted as unmeasured."""
    filler = "기초 배경 설명: 이 문장은 최소 글자수 마흔 자 조건을 충족하기 위한 충분한 길이의 참조 텍스트입니다."
    doc = ExtractedDocument(
        title_hint="신뢰도 경계 테스트",
        source_kind="image",
        page_count=1,
        blocks=(
            DocumentBlock(kind="paragraph", text=filler, page=1, confidence=1.0),
            DocumentBlock(
                kind="paragraph",
                text="아세틸콜린: 부교감신경 말단에서 분비되는 대표적인 신경전달물질이다.",
                page=1,
                confidence=conf,
            ),
        ),
    )
    plan = build_deck_plan(doc, min_confidence=0.60)
    assert plan.status == "OK"
    assert plan.stats.low_confidence_lines == expected_low
    assert plan.stats.unmeasured_confidence_lines == expected_unmeasured
    has_target = any("아세틸콜린" in c.spec.front_text for c in plan.cards)
    assert has_target is expected_kept


@pytest.mark.parametrize(
    ("text_len", "expected_status", "expected_err"),
    [
        (39, "BLOCKED", "insufficient_text"),
        (40, "OK", None),
    ],
)
def test_t6_minimum_text_chars_boundary(
    text_len: int,
    expected_status: str,
    expected_err: str | None,
) -> None:
    """T6: 39 chars -> BLOCKED `insufficient_text`; 40 chars -> OK."""
    prefix = "항상성: "
    rem = text_len - len(prefix)
    body = ("생체내부환경유지작용" * 6)[:rem]
    full_line = prefix + body
    assert len(full_line) == text_len

    doc = ExtractedDocument(
        blocks=(DocumentBlock(kind="paragraph", text=full_line, page=1, confidence=0.95),),
        title_hint="경계값",
        source_kind="image",
        page_count=1,
    )
    plan = build_deck_plan(doc, min_text_chars=40)
    assert plan.status == expected_status
    assert plan.error_code == expected_err


def test_t7_infer_deck_name_priority_order() -> None:
    """T7: user_name > title_hint > heading block > top keywords > injected date."""
    doc_with_title = ExtractedDocument(
        title_hint="PDF 메타데이터 제목",
        blocks=(
            DocumentBlock(kind="heading", text="# 1장 헤딩 제목", page=1, confidence=1.0),
            DocumentBlock(kind="paragraph", text="열역학 제1법칙은 에너지 보존 법칙이다.", page=1, confidence=1.0),
        ),
    )
    # 1. User specified name wins
    assert infer_deck_name(doc_with_title, user_name="내가 정한 덱", now_date_str="2026-10-19") == "내가 정한 덱"
    # 2. Title hint wins when user_name is None
    assert infer_deck_name(doc_with_title, user_name=None, now_date_str="2026-10-19") == "PDF 메타데이터 제목"

    # 3. Heading block wins when title_hint is None
    doc_heading = ExtractedDocument(
        title_hint=None,
        blocks=(
            DocumentBlock(kind="heading", text="# 헌법 기본권 총론", page=1, confidence=1.0),
            DocumentBlock(kind="paragraph", text="행복추구권은 포괄적 기본권이다.", page=1, confidence=1.0),
        ),
    )
    assert infer_deck_name(doc_heading, user_name=None, now_date_str="2026-10-19") == "헌법 기본권 총론"

    # 4. Top keywords win when no title_hint and no heading
    doc_keywords = ExtractedDocument(
        title_hint=None,
        blocks=(
            DocumentBlock(
                kind="paragraph",
                text="미토콘드리아 세포호흡 과정에서 ATP 합성이 일어난다. 미토콘드리아 내막에서 ATP 합성효소가 작동한다.",
                page=1,
                confidence=1.0,
            ),
        ),
    )
    inferred_kw = infer_deck_name(doc_keywords, user_name=None, now_date_str="2026-10-19")
    assert "미토콘드리아" in inferred_kw and "ATP" in inferred_kw

    # 5. Date fallback when blocks are empty
    doc_empty = ExtractedDocument(title_hint=None, blocks=())
    assert infer_deck_name(doc_empty, user_name=None, now_date_str="2026-10-19") == "문서 덱 2026-10-19"


def test_t11_duplicate_front_normalization_and_dedup() -> None:
    """T11: Two cards with identical normalized front text (differing only in spaces/case/punctuation) are deduplicated."""
    doc = ExtractedDocument(
        title_hint="중복 제거 테스트",
        blocks=(
            DocumentBlock(
                kind="paragraph",
                text="Deadlock: 두 개 이상의 프로세스가 서로 자원을 점유한 채 무한정 대기하는 상태이다.",
                page=1,
                confidence=0.95,
            ),
            DocumentBlock(
                kind="paragraph",
                text="deadlock :  두 개 이상의 프로세스가 서로 자원을 점유한 채 무한정 대기하는 상태이다!",
                page=2,
                confidence=0.95,
            ),
        ),
    )
    plan = build_deck_plan(doc)
    assert plan.status == "OK"
    assert len(plan.cards) == 1
    assert plan.stats.duplicates == 1


def test_t14_golden_fixtures_parity() -> None:
    """T14: Verify golden fixtures produce exact deterministic category, deck_name, and card counts."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "document_golden" / "golden_cases.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    for case in cases:
        doc = ExtractedDocument(
            title_hint=case["title_hint"],
            source_kind=case["source_kind"],
            page_count=case["page_count"],
            blocks=tuple(
                DocumentBlock(
                    kind=b["kind"],
                    text=b["text"],
                    page=b["page"],
                    confidence=b["confidence"],
                )
                for b in case["blocks"]
            ),
        )
        plan = build_deck_plan(doc)
        assert plan.status == "OK", f"Case {case['case_id']} failed: {plan.error_code}"
        assert plan.category == case["expected_category"]
        assert plan.deck_name == case["expected_deck_name"]
        assert len(plan.cards) == case["expected_card_count"]
        if "expected_low_confidence_lines" in case:
            assert plan.stats.low_confidence_lines == case["expected_low_confidence_lines"]
        if "expected_unmeasured_confidence_lines" in case:
            assert plan.stats.unmeasured_confidence_lines == case["expected_unmeasured_confidence_lines"]
        for c in plan.cards:
            assert c.source_page >= 1
            assert len(c.source_excerpt) >= 5


def test_grounding_rejects_partial_fabricated_tokens_and_wrong_source_page() -> None:
    """Every answer token must exist on the cited source_page; partial matches or wrong pages are rejected."""
    doc = ExtractedDocument(
        title_hint="Grounding Precision Test",
        source_kind="pdf",
        page_count=2,
        blocks=(
            DocumentBlock(
                kind="paragraph",
                text="Alpha beta gamma: Core Greek letters used in statistical significance and power analysis.",
                page=1,
                confidence=0.95,
            ),
            DocumentBlock(
                kind="paragraph",
                text="Delta epsilon: Infinitesimal quantities used in formal limit definitions in calculus.",
                page=2,
                confidence=0.95,
            ),
        ),
    )
    partial_fabricated = SourcedCard(
        spec=GeneratedCardSpec(
            note_type="basic",
            front_text="What are the core symbols?",
            back_text="alpha beta gamma fabricated",
            tags=("ai",),
            rationale="75% match with 1 fabricated token must be rejected",
        ),
        pattern="definition",
        source_page=1,
        source_excerpt="Alpha beta gamma",
    )
    wrong_page_citation = SourcedCard(
        spec=GeneratedCardSpec(
            note_type="basic",
            front_text="Which Greek letters appear on page 1?",
            back_text="alpha beta gamma",
            tags=("ai",),
            rationale="Tokens exist on page 1 but card cites page 2",
        ),
        pattern="definition",
        source_page=2,
        source_excerpt="Alpha beta gamma",
    )
    nonexistent_page_citation = SourcedCard(
        spec=GeneratedCardSpec(
            note_type="basic",
            front_text="Out of range page citation",
            back_text="alpha beta gamma",
            tags=("ai",),
            rationale="Card cites non-existent page 99",
        ),
        pattern="definition",
        source_page=99,
        source_excerpt="Alpha beta gamma",
    )
    plan = build_deck_plan(
        doc,
        extra_llm_cards=(partial_fabricated, wrong_page_citation, nonexistent_page_citation),
    )
    assert plan.status == "OK"
    assert plan.stats.dropped_ungrounded == 3
    assert all("fabricated" not in c.spec.back_text for c in plan.cards)

    # Numeric substring collision check: '30 days' must NOT pass against '130 days'
    num_doc = ExtractedDocument(
        title_hint="Statutory Deadline",
        source_kind="pdf",
        page_count=1,
        blocks=(
            DocumentBlock(
                kind="paragraph",
                text="Filing rule: The statutory deadline is 130 days from the notice date.",
                page=1,
                confidence=0.98,
            ),
        ),
    )
    wrong_num_card = SourcedCard(
        spec=GeneratedCardSpec(
            note_type="basic",
            front_text="What is the statutory deadline?",
            back_text="30 days",
            tags=("ai",),
            rationale="30 is a substring of 130 but a different number",
        ),
        pattern="statute_numeric",
        source_page=1,
        source_excerpt="The statutory deadline is 30 days",
    )
    kept, dropped = ground_cards((wrong_num_card,), num_doc)
    assert len(kept) == 0
    assert dropped == 1


def test_short_factual_statute_line_is_synthesized_not_skipped_as_heading() -> None:
    """Short factual lines like '제12조 근로자는 30일 이내에 신고한다' must produce statute_numeric cards."""
    doc = ExtractedDocument(
        title_hint="노동법 핵심 조문",
        source_kind="pdf",
        page_count=1,
        blocks=(
            DocumentBlock(
                kind="paragraph",
                text="제12조 근로자는 30일 이내에 신고한다",
                page=1,
                confidence=0.98,
            ),
            DocumentBlock(
                kind="paragraph",
                text="제13조 사용자는 해고하려는 날부터 30일 전에 예고를 하여야 한다.",
                page=1,
                confidence=0.98,
            ),
        ),
    )
    plan = build_deck_plan(doc)
    assert plan.status == "OK"
    assert len(plan.cards) == 2
    assert any("제12조" in c.spec.front_text and "30일 이내" in c.spec.front_text for c in plan.cards)


@pytest.mark.parametrize(
    ("line_text", "kind", "expected_is_toc_or_heading"),
    [
        ("목차", "heading", True),
        ("차례", "paragraph", True),
        ("Table of Contents", "heading", True),
        ("[단원 요약]", "paragraph", True),
        ("[학습 목표]", "paragraph", True),
        ("1. 서론 ..... 3", "paragraph", True),
        ("Ⅰ. 연구 배경 ─── 12쪽", "paragraph", True),
        ("제1장 총칙 ····· p.5", "paragraph", True),
        ("2. 이론적 배경     14p", "paragraph", True),
        ("1. 서론 2. 본론 3. 결론", "paragraph", True),
        ("① 배경 ② 목적 ③ 의의", "paragraph", True),
        ("제1장 근로기준법 총칙", "paragraph", True),
        ("제2절 소멸시효와 제척기간", "heading", True),
        ("Chapter 1: Overview", "paragraph", True),
        ("1. 연구의 필요성", "paragraph", True),
        ("특징", "paragraph", True),
        ("제12조 근로자는 30일 이내에 신고한다", "paragraph", False),
        ("소멸시효: 권리자가 권리를 행사할 수 있음에도 일정 기간 행사하지 않는 경우 권리가 소멸하는 제도이다.", "paragraph", False),
        ("광합성이란 엽록체에서 빛에너지를 이용해 포도당을 합성하는 과정이다.", "paragraph", False),
    ],
)
def test_ddt_toc_and_structural_heading_filter_parity(
    line_text: str,
    kind: str,
    expected_is_toc_or_heading: bool,
) -> None:
    """DDT: Verify TOC lines, dotted leader lines, and non-propositional headings are rejected in Python & JS."""
    import subprocess
    from anki_studio.domain.document_deck_builder import is_toc_or_structural_heading

    assert is_toc_or_structural_heading(line_text, kind) is expected_is_toc_or_heading

    vm_path = Path(__file__).resolve().parent.parent / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    js_code = (
        f"const vm = require({json.dumps(str(vm_path))});"
        f"console.log(JSON.stringify(vm.isTocOrStructuralHeading({json.dumps(line_text)}, {json.dumps(kind)})));"
    )
    out = subprocess.check_output(["node", "-e", js_code], text=True).strip()
    assert json.loads(out) is expected_is_toc_or_heading


def test_bdd_auto_deck_excludes_toc_and_unwraps_generic_labels_into_content_questions() -> None:
    """BDD: Given a document with TOC, chapter headings, generic section labels ('특징:', '1. 배경:'), and definitions,
    When auto-deck synthesis runs across Python and JS,
    Then TOC/headings are excluded, generic labels are never asked as questions/answers, and content is the question.
    """
    import subprocess
    from anki_studio.domain.ai_learning import extract_smart_cards_deterministic
    from anki_studio.domain.document_deck_builder import is_generic_section_label

    for lbl in ("특징", "1. 배경", "(2) 의의", "목적", "원인", "결과", "개요", "목차"):
        assert is_generic_section_label(lbl) is True
    for real_term in ("광합성", "소멸시효", "미토콘드리아", "강화도 조약"):
        assert is_generic_section_label(real_term) is False

    doc = ExtractedDocument(
        title_hint=None,
        source_kind="pdf",
        page_count=1,
        blocks=(
            DocumentBlock(kind="heading", text="목차", page=1, confidence=0.99),
            DocumentBlock(
                kind="paragraph",
                text="1. 서론 ..... 3\n2. 본론 ..... 12\n3. 결론 ..... 25",
                page=1,
                confidence=0.99,
            ),
            DocumentBlock(kind="heading", text="제1장 광합성과 세포 호흡", page=1, confidence=0.99),
            DocumentBlock(
                kind="paragraph",
                text="특징: 엽록체에서 빛에너지를 화학에너지로 전환하여 포도당을 합성한다.",
                page=1,
                confidence=0.98,
            ),
            DocumentBlock(
                kind="paragraph",
                text="소멸시효: 권리자가 권리를 행사할 수 있음에도 일정 기간 행사하지 않는 경우 그 권리가 소멸하는 제도이다.",
                page=1,
                confidence=0.98,
            ),
        ),
    )

    # 1. Checklv1 / lv3 / mixed in build_deck_plan
    plan_mixed = build_deck_plan(doc, difficulty_level="mixed")
    assert plan_mixed.status == "OK"
    # Deck name must not be "목차"
    assert plan_mixed.deck_name != "목차"
    assert "광합성" in plan_mixed.deck_name

    forbidden_targets = {"목차", "차례", "서론", "본론", "결론", "특징", "제1장 광합성과 세포 호흡"}
    for card in plan_mixed.cards:
        front = card.spec.front_text
        back_primary = card.spec.back_text.split("💡 해설:")[0].strip()
        assert back_primary not in forbidden_targets, f"Forbidden generic/TOC target in back: {card.spec}"
        assert "....." not in front
        assert "특징'의 핵심" not in front
        assert "{{c1::특징" not in front

    # Basic lv1 card for "소멸시효: ..." must have the content/definition on front_text and "소멸시효" on back_text
    somyeol_lv1 = [
        c for c in plan_mixed.cards if "diff_lv1" in c.spec.tags and "권리자가" in c.spec.front_text
    ]
    assert len(somyeol_lv1) == 1
    assert somyeol_lv1[0].spec.back_text.startswith("소멸시효")
    assert "소멸시효" not in somyeol_lv1[0].spec.front_text

    # Unwrapped generic label ("특징: 엽록체에서...") must attach heading context and ask about content
    unwrapped_cards = [c for c in plan_mixed.cards if "빛에너지" in c.spec.front_text or "포도당" in c.spec.front_text]
    assert len(unwrapped_cards) >= 1
    assert any("제1장 광합성과 세포 호흡" in c.spec.front_text for c in unwrapped_cards)

    # 2. Check extract_smart_cards_deterministic
    raw_notes = (
        "목차\n"
        "1. 서론 ..... 3\n"
        "제1장 광합성과 에너지\n"
        "특징: 엽록체에서 빛에너지를 이용해 포도당을 합성하는 과정이다.\n"
        "미토콘드리아: 세포 호흡을 통해 ATP를 합성하는 세포 소기관이다."
    )
    det_cards = extract_smart_cards_deterministic(raw_notes, difficulty_level="lv1")
    assert len(det_cards) == 2
    assert all("목차" not in c.front_text and "서론" not in c.front_text for c in det_cards)
    assert all(not c.back_text.startswith("특징") for c in det_cards)
    assert any("세포 호흡을 통해 ATP를 합성하는" in c.front_text and c.back_text.startswith("미토콘드리아") for c in det_cards)

    # 3. Check JS ViewModel buildSmartTextDeck parity
    vm_path = Path(__file__).resolve().parent.parent / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    js_code = (
        f"const vm = require({json.dumps(str(vm_path))});"
        f"const eng = vm.createStandaloneEngine();"
        f"const res = eng.buildSmartTextDeck({{text: {json.dumps(raw_notes)}, difficulty_level: 'lv1', auto_save: false}});"
        f"console.log(JSON.stringify(res));"
    )
    js_res = json.loads(subprocess.check_output(["node", "-e", js_code], text=True).strip())
    assert js_res["ok"] is True
    assert js_res["generated_count"] == 2
    for c in js_res["cards"]:
        assert "목차" not in c["front_text"]
        assert "서론" not in c["front_text"]
        assert not c["back_text"].startswith("특징")
    assert any("세포 호흡을 통해 ATP를 합성하는" in c["front_text"] and c["back_text"].startswith("미토콘드리아") for c in js_res["cards"])


def test_bdd_concise_card_front_back_minimum_information_principle() -> None:
    """BDD: Verify front/back redundant chatter and duplicate explanations are eliminated across Python & JS 1,000-card decks."""
    import subprocess
    from anki_studio.domain.full_scale_corpus import build_full_scale_deck_cards

    banned_front_boilerplates = (
        "다음 어휘·표현의 문맥 속 정확한 뜻은?",
        "(출제 포인트 점검)",
        "(빈칸에 들어갈 핵심 표현은?)",
        "위 설명에 해당하는 역사적 사건·인물·제도·유산은?",
    )
    banned_back_boilerplates = (
        "표제어 '",
        "— 훈음:",
    )

    sample_ref_ids = (
        "moe-eng:elementary-800",
        "hanja-grade:8geup",
        "khist:essential",
        "sci-element-formula:core",
        "moe-math:core",
        "moe-kor:orthography",
        "cert-it:core",
    )

    for ref_id in sample_ref_ids:
        cards = build_full_scale_deck_cards(ref_id=ref_id, target_count=1000)
        assert len(cards) >= 1000
        for c in cards:
            front = str(c["front_text"])
            back = str(c["back_text"])
            for phrase in banned_front_boilerplates:
                assert phrase not in front, f"Verbose front boilerplate '{phrase}' found in {ref_id}: {front}"
            for phrase in banned_back_boilerplates:
                assert phrase not in back, f"Redundant back boilerplate '{phrase}' found in {ref_id}: {back}"
            if "💡 해설:" in back:
                ans_part, exp_part = [p.strip() for p in back.split("💡 해설:", 1)]
                assert ans_part != exp_part, f"Duplicate answer == explanation in {ref_id}: {back}"

    vm_path = Path(__file__).resolve().parent.parent / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"
    js_code = (
        f"const vm = require({json.dumps(str(vm_path))});"
        f"const eng = vm.createStandaloneEngine();"
        f"const d = eng.buildCollectionDeck({{collection_id: 'hanja-grade:8geup', limit: 1000}});"
        f"console.log(JSON.stringify(d.cards.slice(0, 60)));"
    )
    sample_js_cards = json.loads(subprocess.check_output(["node", "-e", js_code], text=True).strip())
    assert len(sample_js_cards) == 60
    for c in sample_js_cards:
        for phrase in banned_front_boilerplates:
            assert phrase not in c["front_text"]
        if "💡 해설:" in c["back_text"]:
            ans_part, exp_part = [p.strip() for p in c["back_text"].split("💡 해설:", 1)]
            assert ans_part != exp_part


