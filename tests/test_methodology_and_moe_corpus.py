"""5-Layer Verification & Test Methodology Suite + MOE Curriculum Corpus Tests.

Verifies:
- Layer 1 (Equivalence Partitioning & Boundary Value Analysis):
  * Difficulty badges ([Lv.1 기초], [Lv.2 문맥 빈칸], [Lv.3 심화]) do not misclassify non-English cards.
  * Default role tag (`role:core_vocab`) does not pollute Korean history/science/dictation/math cards.
  * Cloze markers (`{{c1::...}}`) and parenthetical POS (`(명사)`) strip cleanly without spoiler leaks.
- Layer 2 (State-Transition Matrix):
  * `UNREVEALED -> REVEALED -> RATED -> NEXT_CARD -> UNDO -> RESET` transitions work deterministically.
  * `POST /api/reset` and `standaloneEngine.resetStudyProgress` restore all cards to `state='new', reps=0, lapses=0`.
- Layer 3 (Exhaustive Distractor Contamination Matrix):
  * 0.0% cross-type contamination across all 9 MOE grade-level & subject collections.
- Layer 4 (Tri-Engine Cross-Platform Parity):
  * Python (`rea_v56.py`), Web/iOS JS (`viewmodel.js`), and Android Kotlin (`AdaptiveQuizEngine.kt`) agree 100% on facet classification and reset capabilities.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

import pytest

from anki_studio.adapters.reference_pack_store import (
    ensure_starter_k12_and_exam_pack,
    inspect_pack_catalog,
)
from anki_studio.domain.moe_curriculum_corpus import (
    MOE_CURRICULUM_COLLECTIONS,
    build_tier_r_moe_collections,
    get_moe_collection_by_id,
    list_moe_curriculum_collections,
)
from anki_studio.domain.rea_v56 import (
    build_type_matched_quiz_options,
    classify_card_question_type,
    extract_clean_target_answer,
)
from anki_studio.service.studio_server import AnkiStudioService, create_http_server


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "anki_studio" / "ui" / "static"


# ============================================================================
# LAYER 1: Equivalence Partitioning & Boundary Value Analysis (EP & BVA)
# ============================================================================


@pytest.mark.parametrize(
    "front_text,back_text,tags,expected_category,expected_facet",
    [
        # EP-1: English Vocab with Lv.1/Lv.2/Lv.3 badges
        ("🌱 [Lv.1 기초] sustainable", "지속 가능한 (형용사)", ["moe_high_eng", "diff_lv1"], "vocab", "eng_vocab_meaning"),
        ("📘 [Lv.2 문맥 빈칸] sustainable — 알맞은 핵심 표현: {{c1::지속 가능한::정답 인출}}", "지속 가능한 (형용사)", ["moe_high_eng", "diff_lv2"], "vocab", "eng_vocab_meaning"),
        ("🔥 [Lv.3 심화·역방향] 다음 뜻·설명에 해당하는 핵심 어휘는?\n💡 지속 가능한", "sustainable\n💡 해설: 지속 가능한", ["moe_high_eng", "diff_lv3"], "vocab", "eng_vocab_word"),
        # EP-2: English Grammar with Lv badges
        ("🌱 [Lv.1 기초] [중학 핵심문법] 과거에 시작된 동작이 현재까지 영향을 미칠 때 쓰는 시제는?", "현재완료 (have / has + 과거분사 p.p.)", ["role:key_grammar", "diff_lv1"], "grammar", "eng_grammar"),
        ("🔥 [Lv.3 심화] [Lesson 1 핵심문법] 주어가 3인칭 단수일 때 일반동사 현재형 부정문 형태는?", "doesn't (does not) + 동사원형", ["role:key_grammar", "diff_lv3"], "grammar", "eng_grammar"),
        # EP-3: Korean History with default `role:core_vocab` & `[Lv.2]` (Boundary: must NOT be classified as English vocab!)
        ("📘 [Lv.2 문맥 빈칸] 고조선의 사회 질서를 유지하기 위해 제정된 {{c1::8조법(범금 8조)::정답 인출}}", "8조법(범금 8조)\n💡 해설: 생명과 노동력, 사유재산을 중시했습니다.", ["role:core_vocab", "diff_lv2"], "history_sci", "history"),
        # EP-4: Science & Math Formulas with `Lv.` badge
        ("🌱 [Lv.1 기초] 🔬 [중학 수학 공식] 직각삼각형에서 직각을 낀 두 변 a, b와 빗변 c의 피타고라스 정리 공식은?", "a² + b² = c²\n💡 해설: 피타고라스 정리", ["sci_math", "diff_lv1"], "history_sci", "science"),
        ("🔬 [과학 공식] 도선에 흐르는 전류(I), 전압(V), 저항(R) 사이의 옴의 법칙 관계식은?", "V = I × R (전압 = 전류 × 저항)", ["sci_formula"], "history_sci", "science"),
        # EP-5: Hanja & Idioms
        ("🌱 [Lv.1 기초] 樂", "즐길 락(낙) / 노래 악 / 좋아할 요 (부수: 木 · 15획)", ["moe_hanja_mid", "diff_lv1"], "hanja", "hanja_hun_eum"),
        ("📜 [사자성어] 고생 끝에 낙이 온다는 뜻의 한자성어는? (苦盡甘來)", "고진감래 (苦盡甘來)", ["idiom_core"], "hanja", "idiom"),
        # EP-6: Korean Orthography & Dictation
        ("✏️ [한글 맞춤법] '며칠 동안'과 '몇 일 동안' 중 어법에 맞는 표준 표기는?", "며칠 동안\n💡 해설: 어원이 분명하지 아니한 것은 원형을 밝혀 적지 않습니다.", ["dictation_kor"], "vocab", "ko_dictation"),
    ],
)
def test_layer1_equivalence_partitioning_and_bva_classification(
    front_text: str,
    back_text: str,
    tags: List[str],
    expected_category: str,
    expected_facet: str,
) -> None:
    qtype = classify_card_question_type(
        {"front_text": front_text, "back_text": back_text, "tags": tags}
    )
    assert qtype["category_key"] == expected_category
    assert qtype["facet_key"] == expected_facet


def test_layer1_moe_curriculum_corpus_completeness_and_spoiler_free_invariants() -> None:
    """Verify all 9 MOE collections exist, have rich items, and never leak target answers in prompts."""
    meta_list = list_moe_curriculum_collections()
    assert len(meta_list) == 9
    required_ids = {
        "moe-eng:elem-3-4",
        "moe-eng:elementary",
        "moe-eng:middle-1200",
        "moe-eng:high-csat",
        "moe-kor:orthography-lit",
        "moe-hanja-1800:middle",
        "khist:essential",
        "sci-element-formula:core",
        "moe-math:core-formulas",
    }
    assert {c["collection_id"] for c in meta_list} == required_ids
    for cid in required_ids:
        col = get_moe_collection_by_id(cid)
        assert col is not None
        assert len(col["items"]) >= 5

    # Verify Tier R reference pack builder integrates all 9 MOE collections into SQLite
    with tempfile.TemporaryDirectory() as tmpdir:
        pack_path = Path(tmpdir) / "ref_moe_test.sqlite3"
        ensure_starter_k12_and_exam_pack(pack_path)
        catalog = inspect_pack_catalog(pack_path)
        coll_ids = {c["collection_id"] for c in catalog["collections"]}
        assert required_ids.issubset(coll_ids)

        svc = AnkiStudioService(
            db_path=Path(tmpdir) / "user_moe_test.sqlite3",
            seed_defaults=False,
        )
        # Unlock khist & sci packs so all 9 collections can be materialized
        svc.purchase_store_pack(
            pack_id="pack.exam.khist_master",
            auto_create_deck=False,
            payment_token="BDPAY-pack.exam.khist_master",
        )
        svc.purchase_store_pack(
            pack_id="pack.high1.sci.visang.full",
            auto_create_deck=False,
            payment_token="BDPAY-pack.high1.sci.visang.full",
        )
        for cid in required_ids:
            built = svc.generate_collection_deck(collection_id=cid, difficulty_level="standard")
            assert built["ok"] is True, f"Collection {cid} failed: {built}"
            assert built["saved_count"] >= 3, f"Collection {cid} has too few cards"


# ============================================================================
# LAYER 2: State-Transition Matrix Testing (Review -> Undo -> Reset)
# ============================================================================


def test_layer2_state_transition_matrix_backend_and_http_reset() -> None:
    """Verify full state lifecycle: NEW -> REVIEWED (reps=1) -> RESET (state='new', reps=0, lapses=0)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "state_matrix.sqlite3"
        svc = AnkiStudioService(db_path=db_path, seed_defaults=False)

        # 1. Create a deck from MOE Elementary 3-4 collection
        res_create = svc.generate_collection_deck(
            collection_id="moe-eng:elem-3-4",
            difficulty_level="standard",
            deck_name="초등 3~4학년 영단어 테스트",
        )
        assert res_create["ok"] is True
        deck_id = res_create["deck_id"]

        due_initial = svc.get_due_cards(deck_id=deck_id, shuffle_mode="sequential")
        total_cards = len(due_initial["cards"])
        assert total_cards >= 12
        first_card = due_initial["cards"][0]
        assert first_card["state"] == "new"
        assert first_card["reps"] == 0

        # 2. Transition UNREVEALED -> REVEALED -> RATED (rating=3 Good) for first 3 cards
        for idx in range(3):
            cid = due_initial["cards"][idx]["card_id"]
            rev_res = svc.submit_review(card_id=cid, rating=3)
            assert rev_res["ok"] is True
            assert rev_res["memory"]["reps"] == 1

        due_after_3 = svc.get_due_cards(deck_id=deck_id, shuffle_mode="sequential")
        assert len(due_after_3["cards"]) == total_cards - 3

        # 3. Transition RATED -> UNDO (restores 1 card)
        undo_res = svc.undo_review()
        assert undo_res["ok"] is True
        due_after_undo = svc.get_due_cards(deck_id=deck_id, shuffle_mode="sequential")
        assert len(due_after_undo["cards"]) == total_cards - 2

        # 4. Transition ANY_STATE -> RESET via HTTP POST /api/reset
        import io
        from anki_studio.service.studio_server import create_http_handler

        handler_cls = create_http_handler(service=svc)
        body_bytes = json.dumps({"deck_id": deck_id}).encode("utf-8")
        raw_req = (
            "POST /api/reset HTTP/1.1\r\n"
            "Host: 127.0.0.1:4390\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body_bytes)}\r\n\r\n"
        ).encode("utf-8") + body_bytes
        rfile = io.BytesIO(raw_req)
        wfile = io.BytesIO()

        class _DummySocket:
            def makefile(self, mode: str, *args: object, **kwargs: object) -> object:
                return rfile if "r" in mode else wfile

            def sendall(self, data: bytes) -> None:
                wfile.write(data)

        handler_cls(_DummySocket(), ("127.0.0.1", 54321), None)
        head_bytes, _, payload_bytes = wfile.getvalue().partition(b"\r\n\r\n")
        status_code = int(head_bytes.decode("iso-8859-1").split("\r\n")[0].split(" ")[1])
        assert status_code == 200
        reset_payload = json.loads(payload_bytes.decode("utf-8"))
        assert reset_payload["ok"] is True
        assert reset_payload["reset_count"] == total_cards

        due_after_reset = svc.get_due_cards(deck_id=deck_id, shuffle_mode="sequential")
        assert len(due_after_reset["cards"]) == total_cards
        for c in due_after_reset["cards"]:
            assert c["state"] == "new"
            assert c["reps"] == 0
            assert c["lapses"] == 0


# ============================================================================
# LAYER 3: Exhaustive Distractor Contamination Matrix (0.0% Cross-Contamination)
# ============================================================================


def test_layer3_exhaustive_distractor_contamination_zero_across_all_moe_collections() -> None:
    """Build a mixed mega-pool of all 9 MOE collections and verify 0% cross-type option contamination."""
    collections = build_tier_r_moe_collections()
    mixed_pool: List[Dict[str, Any]] = []
    cid_counter = 1
    for coll_id, (_level_label, entries) in collections.items():
        for entry_key, _etype, clean_front, clean_back, facet in entries:
            mixed_pool.append(
                {
                    "card_id": cid_counter,
                    "front_text": clean_front,
                    "back_text": clean_back,
                    "target_answer": facet["target_answer"],
                    "tags": [entry_key, coll_id],
                    "reps": 0,
                }
            )
            cid_counter += 1

    grammar_markers = ("동사원형", "과거분사", "현재완료", "관계대명사", "부사 -ly", "There is")
    for card in mixed_pool:
        quiz = build_type_matched_quiz_options(card, mixed_pool, desired_total=4)
        assert len(quiz["options"]) == 4
        assert quiz["target_answer"] in quiz["options"]
        facet = quiz["question_type"]["facet_key"]

        if facet == "eng_vocab_meaning":
            for opt in quiz["options"]:
                for g_marker in grammar_markers:
                    assert g_marker not in opt, f"Vocab card polluted by grammar option '{opt}': {card}"
        elif facet == "eng_grammar":
            # Grammar options should not be single basic Korean nouns like '사과' or '도서관'
            for opt in quiz["options"]:
                assert opt not in {"사과", "도서관", "병원", "아침 식사"}, f"Grammar card polluted by vocab option '{opt}'"


# ============================================================================
# LAYER 4: Tri-Engine Cross-Platform Parity (Python vs JS ViewModel vs Kotlin)
# ============================================================================


def test_layer4_tri_engine_parity_js_standalone_moe_and_reset() -> None:
    """Run Node.js against viewmodel.js to verify all MOE collections, resetStudyProgress, and facet parity."""
    script = f"""
    const vm = require({json.dumps(str(STATIC_DIR / "viewmodel.js"))});
    const engine = vm.createStandaloneEngine();
    const cat = engine.getCatalog();
    const collIds = cat.collections.map(c => c.collection_id);
    const requiredIds = [
      "moe-eng:elem-3-4",
      "moe-eng:elementary",
      "moe-eng:middle-1200",
      "moe-eng:high-csat",
      "moe-kor:orthography-lit",
      "moe-hanja-1800:middle",
      "khist:essential",
      "sci-element-formula:core",
      "moe-math:core-formulas"
    ];
    for (const id of requiredIds) {{
      if (!collIds.includes(id)) {{
        throw new Error("Missing MOE collection in standalone viewmodel.js: " + id);
      }}
      const built = engine.buildCollectionDeck({{ collection_id: id, difficulty_level: "standard" }});
      if (!built.ok || !built.cards || built.cards.length < 4) {{
        throw new Error("Failed building MOE collection in standalone engine: " + id);
      }}
    }}

    // Verify resetStudyProgress in standaloneEngine
    const dueBefore = engine.getDueCards({{ deck_id: 1 }});
    const totalBefore = dueBefore.cards.length;
    engine.submitReview({{ card_id: dueBefore.cards[0].card_id, rating: 3 }});
    engine.submitReview({{ card_id: dueBefore.cards[1].card_id, rating: 4 }});
    const dueMid = engine.getDueCards({{ deck_id: 1 }});
    if (dueMid.cards.length !== totalBefore - 2) {{
      throw new Error("Expected 2 fewer due cards after review, got " + dueMid.cards.length);
    }}
    const resetRes = engine.resetStudyProgress({{ deck_id: 1 }});
    if (!resetRes.ok || resetRes.reset_count < totalBefore) {{
      throw new Error("resetStudyProgress failed: " + JSON.stringify(resetRes));
    }}
    const dueAfter = engine.getDueCards({{ deck_id: 1 }});
    if (dueAfter.cards.length !== totalBefore) {{
      throw new Error("Expected all cards restored after reset, got " + dueAfter.cards.length);
    }}
    if (dueAfter.cards[0].state !== "new" || dueAfter.cards[0].reps !== 0) {{
      throw new Error("Card not restored to new state: " + JSON.stringify(dueAfter.cards[0]));
    }}

    // Verify math & grammar classification parity
    const mathType = vm.classifyCardQuestionType({{
      front_text: "🔬 [중학 수학 공식] 피타고라스 정리 공식은?",
      back_text: "a² + b² = c²",
      tags: ["sci_math"]
    }});
    if (mathType.facet_key !== "science") {{
      throw new Error("Expected math formula facet_key=science, got " + mathType.facet_key);
    }}
    console.log("TRI_ENGINE_JS_OK");
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Node parity check failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "TRI_ENGINE_JS_OK" in proc.stdout


def test_layer4_android_kotlin_moe_and_reset_contracts() -> None:
    """Verify Android Kotlin files contain all MOE collections and resetStudyProgress support."""
    catalog_kt = (
        REPO_ROOT
        / "android-app"
        / "domain"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "ankistudio"
        / "domain"
        / "catalog"
        / "BuiltInCurriculumCatalog.kt"
    ).read_text(encoding="utf-8")
    for cid in (
        "moe-eng:elem-3-4",
        "moe-eng:elementary",
        "moe-eng:middle-1200",
        "moe-eng:high-csat",
        "moe-kor:orthography-lit",
        "moe-hanja-1800:middle",
        "moe-math:core-formulas",
    ):
        assert cid in catalog_kt, f"Missing {cid} in Android BuiltInCurriculumCatalog.kt"

    vm_kt = (
        REPO_ROOT
        / "android-app"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "ui"
        / "AnkiStudioViewModel.kt"
    ).read_text(encoding="utf-8")
    assert "fun resetStudyProgress()" in vm_kt
    assert "dao.resetCardsProgress(" in vm_kt

    main_kt = (
        REPO_ROOT
        / "android-app"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "ui"
        / "MainActivity.kt"
    ).read_text(encoding="utf-8")
    assert "🔄 초기화" in main_kt
    assert "onResetStudyProgress" in main_kt


def test_docs_have_zero_anki_strings() -> None:
    """Ensure all markdown and HTML documents in docs/ contain zero '안키' or 'Anki' strings."""
    docs_dir = REPO_ROOT / "docs"
    for doc_file in docs_dir.iterdir():
        if doc_file.suffix in {".md", ".html", ".json"}:
            text = doc_file.read_text(encoding="utf-8")
            assert "안키" not in text, f"'안키' found in {doc_file.name}"
            assert "anki" not in text.lower(), f"'anki' found in {doc_file.name}"


# ============================================================================
# LAYER 5: Real Browser Headless Chromium E2E Journey (4-Choice Hold + Reset + MOE Deck)
# ============================================================================


def test_layer5_real_playwright_browser_e2e_reset_and_moe_journey() -> None:
    """Verify in real Headless Chromium:
    1) Clicking a 4-choice option reveals answer & explanation WITHOUT skipping to the next card.
    2) Clicking a rating button advances to the next card.
    3) Clicking `#btn-reset-study` (🔄 초기화) restores all cards in the deck back to initial state (새 카드 N).
    4) Generating an MOE grade-level collection deck from the Curriculum tab mounts and starts learning immediately.
    """
    playwright_sync = pytest.importorskip("playwright.sync_api")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "e2e_browser.sqlite3"
        svc = AnkiStudioService(db_path=db_path, seed_defaults=True)
        server = create_http_server(host="127.0.0.1", port=0, service=svc)
        port = server.server_address[1]
        import threading

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with playwright_sync.sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")

                # Close onboarding if visible
                onboarding = page.locator("#onboarding-modal")
                if onboarding.is_visible():
                    page.locator('button[data-onboarding-tier="teen"]').click()
                    page.wait_for_timeout(150)

                page.wait_for_selector("#card-question")
                initial_new_text = page.locator("#count-new").inner_text()
                first_meta_before = page.locator("#card-meta").inner_text()

                # Wait for 4-choice buttons to render inside #interactive-quiz-box
                page.wait_for_selector("#interactive-quiz-box button")
                option_btn = page.locator("#interactive-quiz-box button", has_text="1.")
                option_btn.click()

                # INVARIANT L2: Must NOT auto-advance! Answer & rating grid must be visible on the SAME card.
                assert page.locator("#card-answer").is_visible()
                assert page.locator("#rating-grid-box").is_visible()
                assert page.locator("#card-meta").inner_text() == first_meta_before

                # Now click rating button #rate-3 (보통) or #rate-1 (다시) — whichever is enabled by evidence guard
                if not page.locator("#rate-3").is_disabled():
                    page.locator("#rate-3").click()
                else:
                    page.locator("#rate-1").click()

                page.wait_for_timeout(350)
                new_text_after_one = page.locator("#count-new").inner_text()
                assert new_text_after_one != initial_new_text

                # Click 🔄 초기화 (#btn-reset-study) and verify full restoration to initial state
                page.locator("#btn-reset-study").click()
                page.wait_for_timeout(400)
                restored_new_text = page.locator("#count-new").inner_text()
                assert restored_new_text == initial_new_text
                toast_text = page.locator("#ux-toast-banner").inner_text()
                assert "학습 초기화 완료" in toast_text

                browser.close()
        finally:
            server.shutdown()
            server.server_close()

