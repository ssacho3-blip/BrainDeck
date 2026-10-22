"""BDD & DDT tests for BrainDeck (브레인덱) Rebranding, Apple Offline PWA Bundle, and In-App BrainPack Store."""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path

import pytest

from anki_studio.domain.pack_store import (
    BRAINPACK_CATALOG,
    calculate_bundle_quote,
    check_ref_entitlement,
    decide_entitlement_action,
    default_free_pack_ids,
    get_pack_by_id,
    list_store_catalog,
    resolve_cloud_vision_policy,
    validate_store_purchase,
)
from anki_studio.service.studio_server import AnkiStudioService, create_http_handler


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pack_store_domain_has_zero_external_io_imports() -> None:
    """Pure domain `pack_store.py` must not import sqlite3, urllib, subprocess, http, or adapters."""
    domain_file = PROJECT_ROOT / "src" / "anki_studio" / "domain" / "pack_store.py"
    tree = ast.parse(domain_file.read_text(encoding="utf-8"))
    forbidden = {"sqlite3", "urllib", "requests", "subprocess", "http", "socket", "anki_studio.adapters"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden
            assert not node.module.startswith("anki_studio.adapters")


@pytest.mark.parametrize(
    "category_filter,expected_min",
    [
        ("all", 9),
        ("starter_free", 1),
        ("k12_textbook", 4),
        ("hanja_history", 2),
        ("language_exam", 1),
        ("pro_cert", 1),
    ],
)
def test_brainpack_catalog_filtering_ddt(category_filter: str, expected_min: int) -> None:
    """Given the BrainPack Store catalog, filtering by category returns the expected products."""
    res = list_store_catalog(unlocked_pack_ids=(), category_filter=category_filter)
    assert res["ok"] is True
    assert res["brand"] == "BrainDeck (브레인덱)"
    assert res["self_upload_free"] is True
    assert len(res["packs"]) >= expected_min


def test_entitlement_gate_free_vs_paid_brainpacks() -> None:
    """Starter packs are unlocked by default; paid packs require purchase until unlocked."""
    # Free starter ref is allowed out of the box
    free_check = check_ref_entitlement("hanja-grade:8geup", unlocked_pack_ids=())
    assert free_check["allowed"] is True
    assert free_check["reason"] == "entitled"

    # Paid textbook pack is locked before purchase (micro-pricing: 990 KRW for textbook packs, max 1900 KRW)
    paid_check = check_ref_entitlement("kr.mid1.eng.donga_yoon.2022", unlocked_pack_ids=())
    assert paid_check["allowed"] is False
    assert paid_check["required_pack_id"] == "pack.mid1.eng.donga_yoon.full"
    assert paid_check["price_krw"] == 990
    assert max(p.price_krw for p in BRAINPACK_CATALOG) <= 1900

    # Once unlocked, entitlement check passes
    unlocked_check = check_ref_entitlement(
        "kr.mid1.eng.donga_yoon.2022",
        unlocked_pack_ids=("pack.mid1.eng.donga_yoon.full",),
    )
    assert unlocked_check["allowed"] is True
    assert unlocked_check["reason"] == "entitled"


def _dispatch_http(handler_cls, method: str, path: str, body_obj: dict | None = None) -> dict:
    raw_body = json.dumps(body_obj).encode("utf-8") if body_obj is not None else b""
    req_line = f"{method} {path} HTTP/1.1\r\n"
    hdrs = (
        f"Host: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {len(raw_body)}\r\n\r\n"
    ).encode("utf-8")

    class _DummySock:
        def __init__(self, data: bytes) -> None:
            self._r = io.BytesIO(data)
            self.w = io.BytesIO()

        def makefile(self, mode: str, *args, **kwargs):
            return self._r if "r" in mode else self.w

        def sendall(self, b: bytes) -> None:
            self.w.write(b)

    sock = _DummySock(req_line.encode("utf-8") + hdrs + raw_body)
    handler_cls(sock, ("127.0.0.1", 0), None)
    resp_body = sock.w.getvalue().split(b"\r\n\r\n", 1)[1]
    return json.loads(resp_body.decode("utf-8"))


def test_http_store_purchase_and_apple_pwa_offline_bundle_bdd(tmp_path: Path) -> None:
    """Given the BrainDeck HTTP handler, purchasing a BrainPack unlocks it, mounts a deck, and updates the offline bundle."""
    db_path = tmp_path / "braindeck_test.sqlite"
    svc = AnkiStudioService(db_path=db_path)
    handler_cls = create_http_handler(svc)

    # 1. GET /api/store/packs & initial offline snapshot (only free starter pack entitled)
    store_data = _dispatch_http(handler_cls, "GET", "/api/store/packs")
    assert store_data["ok"] is True
    assert store_data["unlocked_packs"] == 1
    assert store_data["total_packs"] == len(BRAINPACK_CATALOG)

    initial_bundle = _dispatch_http(handler_cls, "GET", "/api/bundle/offline-snapshot")
    assert initial_bundle["ok"] is True
    assert initial_bundle["catalog"]["textbooks"] == []  # Paid textbooks excluded when unentitled

    # 2. Unverified POST /api/store/purchase without payment_token is rejected (Fail-Closed)
    unverified_res = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/purchase",
        {
            "pack_id": "pack.mid1.eng.donga_yoon.full",
            "auto_create_deck": True,
        },
    )
    assert unverified_res["ok"] is False
    assert unverified_res["error"] == "bad_request"
    assert svc.ledger.list_unlocked_pack_ids(profile_id=1) == ["pack.free.starter_k12"]

    # 3. Verified POST /api/store/purchase for Mid-1 Dong-A Yoon English BrainPack
    purchase_res = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/purchase",
        {
            "pack_id": "pack.mid1.eng.donga_yoon.full",
            "auto_create_deck": True,
            "payment_token": "BDPAY-pack.mid1.eng.donga_yoon.full",
        },
    )
    assert purchase_res["ok"] is True
    assert purchase_res["already_unlocked"] is False
    assert "pack.mid1.eng.donga_yoon.full" in purchase_res["unlocked_pack_ids"]
    assert purchase_res["mounted_deck"] is not None
    assert purchase_res["mounted_deck"]["saved_count"] >= 30
    deck_count_after_first = len(svc.store.list_decks())

    # 4. Idempotent re-purchase returns already_unlocked = True and does NOT mount a duplicate deck
    repurchase_res = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/purchase",
        {
            "pack_id": "pack.mid1.eng.donga_yoon.full",
            "auto_create_deck": True,
            "payment_token": "BDPAY-pack.mid1.eng.donga_yoon.full",
        },
    )
    assert repurchase_res["ok"] is True
    assert repurchase_res["already_unlocked"] is True
    assert repurchase_res["mounted_deck"] is not None
    assert repurchase_res["mounted_deck"]["already_mounted"] is True
    assert len(svc.store.list_decks()) == deck_count_after_first

    # 5. GET /api/bundle/offline-snapshot for Apple PWA self-contained storage includes only entitled textbook
    bundle = _dispatch_http(handler_cls, "GET", "/api/bundle/offline-snapshot")
    assert bundle["ok"] is True
    assert bundle["brand"] == "BrainDeck (브레인덱)"
    assert bundle["store"]["unlocked_packs"] == 2
    assert [tb["textbook_id"] for tb in bundle["catalog"]["textbooks"]] == ["kr.mid1.eng.donga_yoon.2022"]
    assert bundle["due"]["count"] >= 30


def test_apple_pwa_and_android_braindeck_parity_contracts() -> None:
    """Verify Apple Web/PWA files and Android Kotlin files share 1:1 BrainPack IDs and BrainDeck branding."""
    index_html = (PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "index.html").read_text(encoding="utf-8")
    manifest_json = json.loads(
        (PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "manifest.json").read_text(encoding="utf-8")
    )
    kotlin_store = (
        PROJECT_ROOT
        / "android-app"
        / "domain"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "ankistudio"
        / "domain"
        / "catalog"
        / "BrainPackStoreCatalog.kt"
    ).read_text(encoding="utf-8")

    assert 'apple-mobile-web-app-capable" content="yes"' in index_html
    assert 'apple-mobile-web-app-title" content="BrainDeck"' in index_html
    assert "BrainDeck (브레인덱)" in index_html
    assert "브레인팩 스토어" in index_html
    assert manifest_json["short_name"] == "BrainDeck"

    for pack in BRAINPACK_CATALOG:
        assert f'"{pack.pack_id}"' in kotlin_store, f"Missing {pack.pack_id} in Kotlin BrainPackStoreCatalog.kt"


def test_bundle_quote_and_ui_ux_tokens_bdd() -> None:
    """Verify Trap T34 bundle discount (15% off >= 3 paid packs) and UI/UX v4.0 Design Tokens."""
    # 1. Single paid pack has no bundle discount (990 KRW)
    single_q = calculate_bundle_quote(["pack.mid1.eng.donga_yoon.full"])
    assert single_q["billable_count"] == 1
    assert single_q["subtotal_krw"] == 990
    assert single_q["discount_applied"] is False
    assert single_q["final_price_krw"] == 990

    # 2. 3 textbook packs (990 * 3 = 2970 KRW) get 15% bundle discount -> 2520 KRW
    bundle_q = calculate_bundle_quote(
        [
            "pack.free.starter_k12",  # Free starter ignored in billing
            "pack.mid1.eng.donga_yoon.full",
            "pack.mid2.eng.donga_yoon.full",
            "pack.mid2.hist.miraeen.full",
        ]
    )
    assert bundle_q["billable_count"] == 3
    assert bundle_q["subtotal_krw"] == 2970
    assert bundle_q["discount_applied"] is True
    assert bundle_q["final_price_krw"] == 2520
    assert bundle_q["discount_krw"] == 450

    # 3. Verify UI/UX Blueprint v4.0 file exists and contains T29~T34 + 3-tier tokens
    ui_blueprint = (PROJECT_ROOT / "docs" / "UI_UX_DESIGN_BLUEPRINT.md").read_text(encoding="utf-8")
    arch_blueprint = (PROJECT_ROOT / "docs" / "ARCHITECTURE_AND_FEATURE_BLUEPRINT.md").read_text(encoding="utf-8")
    assert "resolveUiUxTokens" in ui_blueprint
    assert "T34" in arch_blueprint
    assert "T29" in arch_blueprint
    assert "₩990" in arch_blueprint

    # 4. Verify viewmodel.js exports resolveUiUxTokens and calculateStoreBundleQuote
    vm_js = (PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "viewmodel.js").read_text(encoding="utf-8")
    assert "resolveUiUxTokens" in vm_js
    assert "calculateStoreBundleQuote" in vm_js
    assert "minTouchTargetPx: 56" in vm_js
    assert "allowEasyButton: false" in vm_js


def test_store_purchase_bundle_http_endpoint_bdd(tmp_path: Path) -> None:
    """Verify POST /api/store/purchase-bundle unlocks 3 paid packs with 15% discount and mounts their decks."""
    svc = AnkiStudioService(db_path=tmp_path / "braindeck_bundle_test.sqlite", seed_defaults=True)
    handler_cls = create_http_handler(service=svc)

    res = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/purchase-bundle",
        {
            "pack_ids": [
                "pack.mid1.eng.donga_yoon.full",
                "pack.mid2.eng.donga_yoon.full",
                "pack.mid2.hist.miraeen.full",
            ],
            "auto_create_decks": True,
            "payment_token": "BDPAY-BUNDLE-3PACKS",
        },
    )
    assert res["ok"] is True
    assert res["purchased_count"] == 3
    assert res["quote"]["subtotal_krw"] == 2970
    assert res["quote"]["final_price_krw"] == 2520
    assert res["quote"]["discount_krw"] == 450
    assert "pack.mid1.eng.donga_yoon.full" in res["unlocked_pack_ids"]
    assert "pack.mid2.eng.donga_yoon.full" in res["unlocked_pack_ids"]
    assert "pack.mid2.hist.miraeen.full" in res["unlocked_pack_ids"]

    # 2. Verify restarting AnkiStudioService on the same db_path succeeds idempotently without UNIQUE constraint errors
    # and without rebuilding starter_pack.sqlite (Invariant I-4 / AC-2)
    mtime_before = svc.starter_pack_path.stat().st_mtime_ns
    svc_restarted = AnkiStudioService(db_path=tmp_path / "braindeck_bundle_test.sqlite", seed_defaults=True)
    assert svc_restarted.pack_meta["rebuilt"] is False
    assert svc_restarted.starter_pack_path.stat().st_mtime_ns == mtime_before
    assert "pack.mid2.hist.miraeen.full" in svc_restarted.get_status()["unlocked_pack_ids"]


def test_opus_v5_structural_invariants_ac1_to_ac5_bdd(tmp_path: Path) -> None:
    """Verify Claude Opus 5.5 v5.0 Structural Hardening Invariants (I-1 ~ I-5, AC-1 ~ AC-5)."""
    svc = AnkiStudioService(db_path=tmp_path / "braindeck_v5.sqlite", seed_defaults=True)
    handler_cls = create_http_handler(service=svc)

    # AC-1: Calling generate-exam-scope-deck or generate-collection-deck on a LOCKED pack returns 403 PACK_LOCKED
    locked_exam = _dispatch_http(
        handler_cls,
        "POST",
        "/api/catalog/generate-exam-scope-deck",
        {
            "textbook_id": "kr.mid1.eng.donga_yoon.2022",
            "unit_ids": ["kr.mid1.eng.donga_yoon.2022:U01"],
        },
    )
    assert locked_exam["ok"] is False
    assert locked_exam["error_code"] == "PACK_LOCKED"

    locked_col = _dispatch_http(
        handler_cls,
        "POST",
        "/api/catalog/generate-collection-deck",
        {
            "collection_id": "hanja-grade:3geup",
            "limit": 10,
        },
    )
    assert locked_col["ok"] is False
    assert locked_col["error_code"] == "PACK_LOCKED"

    # AC-1: Free starter collection (hanja-grade:8geup) is ALLOWED without purchase
    free_col = _dispatch_http(
        handler_cls,
        "POST",
        "/api/catalog/generate-collection-deck",
        {
            "collection_id": "hanja-grade:8geup",
            "limit": 5,
        },
    )
    assert free_col["ok"] is True
    assert free_col["saved_count"] >= 5

    # AC-3: Largest Remainder bundle allocation sum == final_price_krw for mixed prices (990 + 1500 + 1900 = 4390 -> 3730)
    mixed_quote = calculate_bundle_quote(
        [
            "pack.mid1.eng.donga_yoon.full",  # 990
            "pack.exam.hanja_master",  # 1500
            "pack.exam.lang_toeic_jlpt",  # 1900
        ]
    )
    assert mixed_quote["subtotal_krw"] == 4390
    assert mixed_quote["final_price_krw"] == 3730
    assert sum(mixed_quote["allocated_prices_krw"].values()) == mixed_quote["final_price_krw"]

    # Purchase bundle and verify ledger records allocated price_paid_krw (840 KRW each for 3x 990 packs = 2520 KRW)
    bundle_res = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/purchase-bundle",
        {
            "pack_ids": [
                "pack.mid1.eng.donga_yoon.full",
                "pack.mid2.eng.donga_yoon.full",
                "pack.mid2.hist.miraeen.full",
            ],
            "auto_create_decks": True,
            "payment_token": "BDPAY-BUNDLE-V5",
        },
    )
    assert bundle_res["ok"] is True
    paid_sum = sum(item["price_paid_krw"] for item in bundle_res["purchased_items"])
    assert paid_sum == 2520

    # AC-3 & AC-1: Refunding a pack transitions to refunded_frozen (idempotent, preserves FSRS cards, blocks new GENERATE)
    due_before_refund = svc.get_due_cards()["count"]
    refund_res = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/refund",
        {"pack_id": "pack.mid1.eng.donga_yoon.full"},
    )
    assert refund_res["ok"] is True
    assert refund_res["status"] == "refunded_frozen"
    assert refund_res["refund_amount_krw"] == 840
    assert refund_res["fsrs_history_preserved"] is True
    assert svc.get_due_cards()["count"] == due_before_refund

    # 2nd refund call is idempotent
    refund_again = _dispatch_http(
        handler_cls,
        "POST",
        "/api/store/refund",
        {"pack_id": "pack.mid1.eng.donga_yoon.full"},
    )
    assert refund_again["already_frozen"] is True
    assert refund_again["refund_amount_krw"] == 840

    # After refund, GENERATE returns 403 PACK_REFUNDED_FROZEN while REVIEW remains allowed
    frozen_exam = _dispatch_http(
        handler_cls,
        "POST",
        "/api/catalog/generate-exam-scope-deck",
        {
            "textbook_id": "kr.mid1.eng.donga_yoon.2022",
            "unit_ids": ["kr.mid1.eng.donga_yoon.2022:U01"],
        },
    )
    assert frozen_exam["ok"] is False
    assert frozen_exam["error_code"] == "PACK_REFUNDED_FROZEN"
    assert (
        decide_entitlement_action(
            "kr.mid1.eng.donga_yoon.2022",
            unlocked_pack_ids=[],
            refunded_pack_ids=["pack.mid1.eng.donga_yoon.full"],
            action="REVIEW",
        )["allowed"]
        is True
    )

    # AC-4: Server-enforced Cloud Vision policy blocks Junior or cloud_vision_locked=True when requested=True
    cv_denied = resolve_cloud_vision_policy(age_tier="junior", cloud_vision_locked=False, requested=True)
    assert cv_denied["allowed"] is False
    assert cv_denied["error_code"] == "CLOUD_VISION_LOCKED"

    ingest_blocked = svc.ingest_document(
        data=b"dummy",
        mime="image/png",
        allow_cloud_vision=True,
        profile_id=1,  # Default profile has cloud_vision_locked=1
    )
    assert ingest_blocked["ok"] is False
    assert ingest_blocked["error_code"] == "CLOUD_VISION_LOCKED"



