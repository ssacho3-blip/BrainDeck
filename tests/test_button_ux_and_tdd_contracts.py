"""TDD & UX Button-by-Button Functional Contract Suite for BrainDeck v5.1.

Follows strict Red -> Green -> Refactor TDD across:
1. Deterministic FSRS Review Undo (`POST /api/review/undo`, shortcut `Z` / `#btn-undo-review`)
2. Server-persisted Age-Tier Profile Switcher (`POST /api/profile/age-tier` for Junior/Teen/Adult)
3. Unlocked BrainPack Deck Jump/Remount UX (`POST /api/store/purchase` on already-unlocked pack returns active deck)
4. Pure ViewModel (`viewmodel.js`) UX state machines verified via Node.js subprocess:
   - Keyboard shortcuts (`Space`, `1~4` with Junior `Easy(4)` guard, `Q` quiz, `H` hint, `T` TTS, `Z` undo)
   - Age-tier rating button labels (`formatRatingButtonsForAgeTier`)
   - Actionable error banners for `PACK_LOCKED`, `PACK_REFUNDED_FROZEN`, `CLOUD_VISION_LOCKED`, `NOTHING_TO_UNDO` (`formatApiErrorBanner`)
   - Interactive Tap-Block quiz assembly state machine (`evaluateTapBlockAttempt`)
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
from typing import Any, Dict

import pytest

from anki_studio.service.studio_server import AnkiStudioService, create_http_handler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIEWMODEL_JS_PATH = PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js"


def _dispatch_http(
    handler_cls: type,
    method: str,
    path: str,
    body: Dict[str, Any] | None = None,
) -> tuple[int, Dict[str, Any]]:
    raw_body = json.dumps(body).encode("utf-8") if body is not None else b""
    req_line = f"{method} {path} HTTP/1.1\r\n"
    hdrs = (
        f"Host: 127.0.0.1:4390\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(raw_body)}\r\n"
        f"\r\n"
    ).encode("utf-8")

    class _DummySock:
        def __init__(self, req_bytes: bytes) -> None:
            self.r = io.BytesIO(req_bytes)
            self.w = io.BytesIO()

        def makefile(self, mode: str, *args: Any, **kwargs: Any) -> Any:
            return self.r if "r" in mode else self.w

        def sendall(self, b: bytes) -> None:
            self.w.write(b)

    sock = _DummySock(req_line.encode("utf-8") + hdrs + raw_body)
    handler_cls(sock, ("127.0.0.1", 0), None)
    raw_resp = sock.w.getvalue()
    head_bytes, body_bytes = raw_resp.split(b"\r\n\r\n", 1)
    status_line = head_bytes.splitlines()[0].decode("utf-8")
    status_code = int(status_line.split(" ")[1])
    return status_code, json.loads(body_bytes.decode("utf-8"))


def test_tdd_review_and_deterministic_undo_lifecycle(tmp_path: Path) -> None:
    """[TDD-1] Clicking a rating button and then clicking Undo (`#btn-undo-review` / `Z`) restores exact FSRS card state."""
    svc = AnkiStudioService(db_path=tmp_path / "undo_tdd.sqlite", seed_defaults=True)
    handler_cls = create_http_handler(service=svc)

    # 1. Undo before any review fails cleanly with 409 NOTHING_TO_UNDO
    code_empty, empty_undo = _dispatch_http(handler_cls, "POST", "/api/review/undo", {})
    assert code_empty == 409
    assert empty_undo["ok"] is False
    assert empty_undo["error_code"] == "NOTHING_TO_UNDO"

    # 2. Fetch first due card and record its pre-review state
    due_before = svc.get_due_cards()["cards"]
    assert len(due_before) >= 1
    target_card = due_before[0]
    cid = int(target_card["card_id"])
    orig_reps = int(target_card["reps"])
    orig_stability = float(target_card["stability"])
    orig_state = str(target_card["state"])

    # 3. Submit a Good (3) review
    code_rev, rev_res = _dispatch_http(
        handler_cls,
        "POST",
        "/api/review",
        {"card_id": cid, "rating": 3},
    )
    assert code_rev == 200
    assert rev_res["ok"] is True
    assert rev_res["memory"]["reps"] == orig_reps + 1
    assert svc.get_status()["stats"]["reviews_today"] == 1

    # 4. Undo the review (`POST /api/review/undo`) -> restores card to due queue with exact original FSRS parameters
    code_undo, undo_res = _dispatch_http(handler_cls, "POST", "/api/review/undo", {})
    assert code_undo == 200
    assert undo_res["ok"] is True
    assert undo_res["undone_card_id"] == cid
    assert svc.get_status()["stats"]["reviews_today"] == 0

    due_after = svc.get_due_cards()["cards"]
    restored = next(c for c in due_after if int(c["card_id"]) == cid)
    assert int(restored["reps"]) == orig_reps
    assert float(restored["stability"]) == pytest.approx(orig_stability)
    assert str(restored["state"]) == orig_state


def test_tdd_profile_age_tier_switch_persists_and_enforces_junior_lock(tmp_path: Path) -> None:
    """[TDD-2] Clicking `.age-tier-btn` (`🌱 초등` / `🚀 중고등` / `🎓 성인`) persists to Tier U and updates UI tokens."""
    svc = AnkiStudioService(db_path=tmp_path / "age_tier_tdd.sqlite", seed_defaults=True)
    handler_cls = create_http_handler(service=svc)

    for tier, expected_lock, expected_easy in [
        ("junior", True, False),
        ("teen", False, True),
        ("adult", False, True),
    ]:
        code, res = _dispatch_http(
            handler_cls,
            "POST",
            "/api/profile/age-tier",
            {"age_tier": tier},
        )
        assert code == 200
        assert res["ok"] is True
        assert res["age_tier"] == tier
        assert res["cloud_vision_locked"] is expected_lock
        assert res["ui_tokens"]["allow_easy_button"] is expected_easy


def test_tdd_clicking_unlocked_pack_returns_mounted_deck_for_instant_study(tmp_path: Path) -> None:
    """[TDD-3] Clicking an already-unlocked BrainPack in the Store returns its active `mounted_deck` so the UI jumps to it."""
    svc = AnkiStudioService(db_path=tmp_path / "store_jump_tdd.sqlite", seed_defaults=True)
    handler_cls = create_http_handler(service=svc)

    # 1. First purchase creates the deck
    code1, res1 = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/purchase",
        {
            "pack_id": "pack.mid1.eng.donga_yoon.full",
            "auto_create_deck": True,
            "payment_token": "BDPAY-pack.mid1.eng.donga_yoon.full",
        },
    )
    assert code1 == 200
    assert res1["already_unlocked"] is False
    first_deck_id = res1["mounted_deck"]["deck_id"]
    deck_count = len(svc.store.list_decks())

    # 2. Clicking the already-unlocked pack button in the store does NOT duplicate the deck,
    #    but DOES return `mounted_deck` pointing to `first_deck_id` so the UI selects it immediately!
    code2, res2 = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/purchase",
        {
            "pack_id": "pack.mid1.eng.donga_yoon.full",
            "auto_create_deck": True,
            "payment_token": "BDPAY-pack.mid1.eng.donga_yoon.full",
        },
    )
    assert code2 == 200
    assert res2["already_unlocked"] is True
    assert res2["mounted_deck"] is not None
    assert res2["mounted_deck"]["deck_id"] == first_deck_id
    assert len(svc.store.list_decks()) == deck_count


def test_tdd_viewmodel_js_button_and_ux_state_machines_via_node() -> None:
    """[TDD-4] Verify `viewmodel.js` pure UX functions (shortcuts, age-tier rating buttons, error banners, tap-block quiz)."""
    script = f"""
    const vm = require({json.dumps(str(VIEWMODEL_JS_PATH))});
    const assert = require("assert");

    // 1. Keyboard shortcuts including Q (quiz), Z (undo), and Junior Easy(4) block
    assert.deepStrictEqual(vm.mapKeyboardShortcut("q", false, false), {{ action: "quiz" }});
    assert.deepStrictEqual(vm.mapKeyboardShortcut("z", false, false), {{ action: "undo" }});
    assert.strictEqual(vm.mapKeyboardShortcut("4", true, false, "junior"), null);
    assert.deepStrictEqual(vm.mapKeyboardShortcut("4", true, false, "teen"), {{ action: "rate", rating: 4 }});

    // 2. Age-tier adaptive rating buttons
    const juniorBtns = vm.formatRatingButtonsForAgeTier("junior", {{ again: {{ label: "10m" }}, hard: {{ label: "1d" }}, good: {{ label: "3d" }}, easy: {{ label: "14d" }} }});
    assert.strictEqual(juniorBtns.length, 3);
    assert.strictEqual(juniorBtns[0].visible, true);
    assert.ok(juniorBtns[2].title.includes("맞혔어요"));

    const adultBtns = vm.formatRatingButtonsForAgeTier("adult", {{}});
    assert.strictEqual(adultBtns.length, 4);

    // 3. Actionable error banner formatting for Fail-Closed 403/409 responses
    const lockedBanner = vm.formatApiErrorBanner({{ ok: false, error_code: "PACK_LOCKED", decision: {{ required_pack_id: "pack.mid1.eng.donga_yoon.full" }} }});
    assert.strictEqual(lockedBanner.tone, "amber");
    assert.strictEqual(lockedBanner.actionPackId, "pack.mid1.eng.donga_yoon.full");
    assert.ok(lockedBanner.message.includes("스토어"));

    const frozenBanner = vm.formatApiErrorBanner({{ ok: false, error_code: "PACK_REFUNDED_FROZEN" }});
    assert.strictEqual(frozenBanner.tone, "rose");
    assert.ok(frozenBanner.message.includes("환불"));

    // 4. Tap-block assembly state machine
    const step1 = vm.evaluateTapBlockAttempt(["나는"], ["나는", "학교에", "갑니다"]);
    assert.strictEqual(step1.status, "IN_PROGRESS");
    const stepWrong = vm.evaluateTapBlockAttempt(["학교에", "나는"], ["나는", "학교에", "갑니다"]);
    assert.strictEqual(stepWrong.status, "WRONG_ORDER");
    const stepDone = vm.evaluateTapBlockAttempt(["나는", "학교에", "갑니다"], ["나는", "학교에", "갑니다"]);
    assert.strictEqual(stepDone.status, "CORRECT");
    assert.strictEqual(stepDone.recommendedRating, 3);

    // 5. Onboarding mode selector & 5-Tab multi-page navigation state machine
    assert.ok(Array.isArray(vm.NAVIGATION_TABS));
    assert.strictEqual(vm.NAVIGATION_TABS.length, 5);
    assert.deepStrictEqual(
      vm.NAVIGATION_TABS.map((t) => t.id),
      ["study", "curriculum", "create", "store", "stats"]
    );
    assert.ok(Array.isArray(vm.ONBOARDING_MODES));
    assert.strictEqual(vm.ONBOARDING_MODES.length, 3);

    const unconfiguredState = vm.resolveActivePageState("study", false);
    assert.strictEqual(unconfiguredState.showOnboarding, true);

    const storePageState = vm.resolveActivePageState("store", true);
    assert.strictEqual(storePageState.showOnboarding, false);
    assert.strictEqual(storePageState.activeTab, "store");
    assert.strictEqual(storePageState.visiblePages.store, true);
    assert.strictEqual(storePageState.visiblePages.study, false);
    assert.strictEqual(storePageState.visiblePages.curriculum, false);

    // 6. 3-Tier Typing Answer Understanding Grader (EXACT / PARTIAL / UNKNOWN)
    assert.strictEqual(typeof vm.evaluateTypedAnswerUnderstanding, "function");
    const exactRes = vm.evaluateTypedAnswerUnderstanding("소개하다", "소개하다");
    assert.strictEqual(exactRes.verdict, "EXACT");
    assert.ok(exactRes.recommendedRating >= 3);

    const partialRes = vm.evaluateTypedAnswerUnderstanding("산소 운반", "산소 운반 및 이산화탄소 배출");
    assert.strictEqual(partialRes.verdict, "PARTIAL");
    assert.strictEqual(partialRes.recommendedRating, 2);
    assert.ok(partialRes.missingTerms.length >= 1);

    const unknownRes = vm.evaluateTypedAnswerUnderstanding("", "산소 운반 및 이산화탄소 배출");
    assert.strictEqual(unknownRes.verdict, "UNKNOWN");
    assert.strictEqual(unknownRes.recommendedRating, 1);

    // 7. Wrong-Only / Unknown-Only Cram Filter & Anki 3-Color Queue Counter
    assert.strictEqual(typeof vm.filterStudyQueue, "function");
    assert.strictEqual(typeof vm.computeAnkiQueueCounts, "function");
    const sampleCards = [
      {{ card_id: 1, state: "new", lapses: 0 }},
      {{ card_id: 2, state: "relearning", lapses: 2 }},
      {{ card_id: 3, state: "review", lapses: 0 }},
    ];
    const counts = vm.computeAnkiQueueCounts(sampleCards);
    assert.strictEqual(counts.newCount, 1);
    assert.strictEqual(counts.learnCount, 1);
    assert.strictEqual(counts.reviewCount, 1);

    const wrongOnly = vm.filterStudyQueue(sampleCards, "wrong_only", [3], []);
    assert.deepStrictEqual(wrongOnly.map((c) => c.card_id), [2, 3]);

    const markedOnly = vm.filterStudyQueue(sampleCards, "marked_only", [], [1]);
    assert.deepStrictEqual(markedOnly.map((c) => c.card_id), [1]);

    console.log("ALL_VIEWMODEL_UX_ASSERTIONS_PASSED");
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check= False)
    assert proc.returncode == 0, f"Node ViewModel TDD failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "ALL_VIEWMODEL_UX_ASSERTIONS_PASSED" in proc.stdout


def test_tdd_html_and_app_js_button_wiring_integrity() -> None:
    """[TDD-5] Verify `index.html` and `app.js` pass JS syntax checks and wire all interactive button contracts."""
    index_html_path = PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "index.html"
    app_js_path = PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "app.js"

    html_text = index_html_path.read_text(encoding="utf-8")
    app_js_text = app_js_path.read_text(encoding="utf-8")

    # 1. Required DOM IDs in index.html (including Onboarding + 5 separate Tab Pages)
    for required_id in [
        "btn-undo-review",
        "ux-toast-banner",
        "btn-toggle-all-units",
        "rate-title-1",
        "rate-title-2",
        "rate-title-3",
        "rate-title-4",
        "onboarding-modal",
        "btn-open-mode-setup",
        "main-tab-nav",
        "page-study",
        "page-curriculum",
        "page-create",
        "page-store",
        "page-stats",
    ]:
        assert f'id="{required_id}"' in html_text, f"Missing DOM id={required_id} in index.html"

    # 2. Required UX handlers in app.js
    for required_token in [
        "/api/review/undo",
        "/api/profile/age-tier",
        "/api/store/refund",
        "evaluateTapBlockAttempt",
        "formatRatingButtonsForAgeTier",
        "formatApiErrorBanner",
        "btn-toggle-all-units",
        "store-bundle-cb",
        "switchTabPage",
        "completeOnboardingMode",
    ]:
        assert required_token in app_js_text, f"Missing handler token {required_token} in app.js"

    # 3. Node.js syntax check on app.js & Toss Light UI / Persistence contracts
    assert "--bg: #f2f4f6" in html_text
    assert "--panel: #ffffff" in html_text
    assert "--accent: #1b64da" in html_text
    assert "ONBOARDING_STORAGE_KEY" in app_js_text
    syntax_proc = subprocess.run(["node", "--check", str(app_js_path)], capture_output=True, text=True, check=False)
    assert syntax_proc.returncode == 0, f"app.js syntax error: {syntax_proc.stderr}"

