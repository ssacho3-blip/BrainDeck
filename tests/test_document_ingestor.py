"""ATDD / BDD / DDT Tests for DocumentIngestor, Atomic Batch Save, and HTTP Ingest Endpoint (T8..T12)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import pytest

from anki_studio.adapters.document_ingestor import (
    MAX_DOCUMENT_BYTES,
    AppleVisionOcrAdapter,
    DocumentIngestor,
    LlmVisionAdapter,
    StdlibPdfTextAdapter,
)
from anki_studio.adapters.sqlite_store import AnkiStudioStore
from anki_studio.service.studio_server import AnkiStudioService, create_http_handler


def _build_minimal_valid_pdf(lines: list[str], title: str = "Algorithms Lecture Note", pages: int = 1, encrypted: bool = False) -> bytes:
    """Build a valid uncompressed PDF byte stream with `/Type /Page` objects and `BT ... Tj ... ET` text."""
    page_objs = b"".join(b"<< /Type /Page >>\n" for _ in range(pages))
    enc_tag = b"/Encrypt << >>\n" if encrypted else b""
    tj_ops = "\n".join(f"({ln}) Tj" for ln in lines).encode("utf-8")
    stream_block = b"stream\r\nBT\r\n" + tj_ops + b"\r\nET\r\nendstream\r\n"
    return (
        b"%PDF-1.4\r\n"
        + f"<< /Title ({title}) >>\r\n".encode("utf-8")
        + enc_tag
        + page_objs
        + stream_block
        + b"%%EOF\r\n"
    )


def test_t8_fail_closed_validation_and_zero_db_writes(tmp_path: Path) -> None:
    """T8: Encrypted, corrupt, 0-page, 51-page, >20MB, and unsupported MIME all return BLOCKED with 0 DB writes."""
    svc = AnkiStudioService(db_path=tmp_path / "t8.sqlite", seed_defaults=False)

    # 1. Unsupported MIME
    res_mime = svc.ingest_document(b"hello", mime="application/zip", auto_save=True)
    assert res_mime["status"] == "BLOCKED"
    assert res_mime["error_code"] == "unsupported_mime"

    # 2. Encrypted PDF
    enc_pdf = _build_minimal_valid_pdf(["Secret"], encrypted=True)
    res_enc = svc.ingest_document(enc_pdf, mime="application/pdf", auto_save=True)
    assert res_enc["status"] == "BLOCKED"
    assert res_enc["error_code"] == "encrypted_pdf"

    # 3. Corrupt PDF (not starting with %PDF-)
    res_corrupt = svc.ingest_document(b"not a pdf at all", mime="application/pdf", auto_save=True)
    assert res_corrupt["status"] == "BLOCKED"
    assert res_corrupt["error_code"] == "corrupt_file"

    # 4. 0-page PDF
    zero_page_pdf = _build_minimal_valid_pdf(["Some text"], pages=0)
    res_zero = svc.ingest_document(zero_page_pdf, mime="application/pdf", auto_save=True)
    assert res_zero["status"] == "BLOCKED"
    assert res_zero["error_code"] == "corrupt_file"

    # 5. 51-page PDF (> MAX_PDF_PAGES=50)
    too_many_pdf = _build_minimal_valid_pdf(["Some text"], pages=51)
    res_many = svc.ingest_document(too_many_pdf, mime="application/pdf", auto_save=True)
    assert res_many["status"] == "BLOCKED"
    assert res_many["error_code"] == "too_many_pages"

    # 6. >20MB payload (MAX_DOCUMENT_BYTES + 1)
    huge_payload = b"%PDF-1.4\n" + (b"A" * (MAX_DOCUMENT_BYTES + 1))
    res_huge = svc.ingest_document(huge_payload, mime="application/pdf", auto_save=True)
    assert res_huge["status"] == "BLOCKED"
    assert res_huge["error_code"] == "too_large"

    # Verify strictly 0 decks and 0 cards written to DB across all blocked calls
    assert svc.store.list_decks() == []
    assert svc.store.get_dashboard_stats()["total_cards"] == 0


def test_t9_ocr_helper_timeout_returns_blocked_ocr_timeout(tmp_path: Path) -> None:
    """T9: When the OCR subprocess times out, ingest returns BLOCKED `ocr_timeout` without empty success."""
    def _timeout_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="anki_vision_ocr", timeout=1.0)

    vision = AppleVisionOcrAdapter(runner=_timeout_runner, timeout_sec=1.0)
    ingestor = DocumentIngestor(vision_adapter=vision)
    svc = AnkiStudioService(
        db_path=tmp_path / "t9.sqlite",
        document_ingestor=ingestor,
        seed_defaults=False,
    )

    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res = svc.ingest_document(fake_png, mime="image/png", auto_save=True)
    assert res["status"] == "BLOCKED"
    assert res["error_code"] == "ocr_timeout"
    assert svc.store.list_decks() == []


def test_t10_create_deck_with_notes_rolls_back_atomically_on_third_note_failure(tmp_path: Path) -> None:
    """T10: If note #3 fails validation during `create_deck_with_notes`, neither deck nor notes #1/#2 remain."""
    store = AnkiStudioStore(tmp_path / "t10.sqlite")
    notes = [
        {"front_text": "Note 1: Valid front", "back_text": "Back 1", "note_type": "basic"},
        {"front_text": "Note 2: Valid front", "back_text": "Back 2", "note_type": "basic"},
        {"front_text": "   ", "back_text": "Invalid empty front on 3rd note!", "note_type": "basic"},
    ]
    with pytest.raises(ValueError, match="non-empty front_text"):
        store.create_deck_with_notes(deck_name="Rollback Test Deck", notes=notes)

    # Both decks and cards must be 0 (complete transaction rollback)
    assert store.list_decks() == []
    assert store.get_dashboard_stats()["total_cards"] == 0


def test_t12_privacy_guard_disallows_cloud_vision_by_default(tmp_path: Path) -> None:
    """T12: When `allow_cloud_vision=False` and local OCR is unavailable, LLM vision adapter is called 0 times."""
    llm_calls = 0

    def _spy_http_sender(payload: bytes) -> str:
        nonlocal llm_calls
        llm_calls += 1
        return '{"blocks": []}'

    unavailable_vision = AppleVisionOcrAdapter(helper_path=tmp_path / "nonexistent_ocr_bin")
    spy_llm = LlmVisionAdapter(endpoint_url="http://127.0.0.1:9999/v1/chat", http_sender=_spy_http_sender)
    ingestor = DocumentIngestor(vision_adapter=unavailable_vision, llm_vision_adapter=spy_llm)
    svc = AnkiStudioService(
        db_path=tmp_path / "t12.sqlite",
        document_ingestor=ingestor,
        seed_defaults=False,
    )

    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res = svc.ingest_document(fake_png, mime="image/png", allow_cloud_vision=False)
    assert res["status"] == "BLOCKED"
    assert res["error_code"] == "ocr_unavailable"
    assert llm_calls == 0

    scanned_pdf = _build_minimal_valid_pdf([], title="Scanned PDF Only", pages=1)
    res_pdf = svc.ingest_document(scanned_pdf, mime="application/pdf", allow_cloud_vision=False)
    assert res_pdf["status"] == "BLOCKED"
    assert res_pdf["error_code"] == "ocr_unavailable"
    assert llm_calls == 0


def test_e2e_pdf_ingest_preview_and_batch_save_via_http_handler(tmp_path: Path) -> None:
    """Verify full lifecycle: PDF upload (preview mode `auto_save=0`) -> inspect grounded cards -> `POST /api/decks/batch-save`."""
    svc = AnkiStudioService(db_path=tmp_path / "e2e_doc.sqlite", seed_defaults=False)
    handler_cls = create_http_handler(svc)

    pdf_bytes = _build_minimal_valid_pdf(
        [
            "Operating System Core Concepts",
            "Mutex: Only one thread that owns the lock can release the critical section.",
            "Semaphore is a signaling mechanism whereas Mutex is a locking mechanism with ownership.",
        ],
        title="OS Study Guide",
        pages=1,
    )

    # Call POST /api/ai/ingest-document?auto_save=0 (preview first per AC-5)
    req_line = "POST /api/ai/ingest-document?auto_save=0&max_cards=10 HTTP/1.1\r\n"
    hdrs = f"Host: 127.0.0.1\r\nContent-Type: application/pdf\r\nContent-Length: {len(pdf_bytes)}\r\n\r\n".encode("utf-8")

    class _DummySock:
        def __init__(self, data: bytes) -> None:
            self._r = io.BytesIO(data)
            self.w = io.BytesIO()

        def makefile(self, mode: str, *args, **kwargs):
            return self._r if "r" in mode else self.w

        def sendall(self, b: bytes) -> None:
            self.w.write(b)

    sock = _DummySock(req_line.encode("utf-8") + hdrs + pdf_bytes)
    handler_cls(sock, ("127.0.0.1", 0), None)
    resp_body = sock.w.getvalue().split(b"\r\n\r\n", 1)[1]
    res = json.loads(resp_body.decode("utf-8"))

    assert res["status"] == "OK"
    assert res["deck_id"] is None  # preview mode did not write to DB yet
    assert res["deck_name"] == "OS Study Guide"
    assert len(res["cards"]) >= 2
    assert svc.store.list_decks() == []

    # Now confirm and batch-save via save_deck_batch
    saved = svc.save_deck_batch(
        deck_name=res["deck_name"],
        cards=res["cards"],
        category=res["category"],
    )
    assert saved["ok"] is True
    assert saved["saved_count"] == len(res["cards"])
    decks = svc.store.list_decks()
    assert len(decks) == 1
    assert decks[0]["name"] == "OS Study Guide"
    assert decks[0]["total_cards"] == len(res["cards"])

    # Verify saved notes retain source_page and source_excerpt on dedicated columns without colliding on source_ref
    due_cards = svc.store.get_due_cards(deck_id=saved["deck_id"])
    assert len(due_cards) >= 2
    for dc in due_cards:
        assert dc.get("source_page") == 1
        assert dc.get("source_excerpt")

    # Saving cards with identical (source_page, source_excerpt) into a second deck must succeed without UNIQUE collision
    saved_second = svc.save_deck_batch(
        deck_name="OS Study Guide Copy",
        cards=res["cards"],
        category=res["category"],
    )
    assert saved_second["ok"] is True
    assert saved_second["saved_count"] == len(res["cards"])


def test_pdf_reversed_and_nested_page_tree_preserves_catalog_order(tmp_path: Path) -> None:
    """Nested /Pages nodes appearing in reverse physical order before the root /Pages node still follow Catalog -> /Pages -> /Kids order."""
    pdf_bytes = (
        b"%PDF-1.4\r\n"
        b"1 0 obj\r\n<< /Type /Catalog /Pages 2 0 R >>\r\nendobj\r\n"
        # Child /Pages node 10 (for Page 2) appears physically BEFORE root /Pages node 2 and child node 9 (for Page 1)
        b"10 0 obj\r\n<< /Type /Pages /Parent 2 0 R /Kids [4 0 R] /Count 1 >>\r\nendobj\r\n"
        b"2 0 obj\r\n<< /Type /Pages /Kids [9 0 R 10 0 R] /Count 2 >>\r\nendobj\r\n"
        b"9 0 obj\r\n<< /Type /Pages /Parent 2 0 R /Kids [3 0 R] /Count 1 >>\r\nendobj\r\n"
        b"3 0 obj\r\n<< /Type /Page /Parent 9 0 R /Contents 6 0 R >>\r\nendobj\r\n"
        b"4 0 obj\r\n<< /Type /Page /Parent 10 0 R /Contents 5 0 R >>\r\nendobj\r\n"
        # Object 5 (Page 2's content stream) also appears BEFORE Object 6 (Page 1's content stream)
        b"5 0 obj\r\n<< /Length 96 >>\r\nstream\r\n"
        b"BT\r\n(PageTwoTerm: This definition belongs strictly to page two of the document.) Tj\r\nET\r\n"
        b"endstream\r\nendobj\r\n"
        b"6 0 obj\r\n<< /Length 96 >>\r\nstream\r\n"
        b"BT\r\n(PageOneTerm: This definition belongs strictly to page one of the document.) Tj\r\nET\r\n"
        b"endstream\r\nendobj\r\n"
        b"%%EOF\r\n"
    )
    svc = AnkiStudioService(db_path=tmp_path / "reversed_pdf.sqlite", seed_defaults=False)
    res = svc.ingest_document(pdf_bytes, mime="application/pdf", auto_save=False)
    assert res["status"] == "OK"
    by_term = {
        ("PageOneTerm" if "PageOneTerm" in c["front_text"] else "PageTwoTerm"): c["source_page"]
        for c in res["cards"]
    }
    assert by_term["PageOneTerm"] == 1
    assert by_term["PageTwoTerm"] == 2

    # Adding 50 detached/unreachable /Page objects must NOT inflate page_count or extract detached text
    detached_objs = b"".join(
        f"{100 + i} 0 obj\r\n<< /Type /Page /Contents 99 0 R >>\r\nendobj\r\n".encode("ascii")
        for i in range(50)
    ) + (
        b"99 0 obj\r\n<< /Length 80 >>\r\nstream\r\n"
        b"BT\r\n(DetachedGhostTerm: This unreferenced object must never be extracted.) Tj\r\nET\r\n"
        b"endstream\r\nendobj\r\n"
    )
    pdf_with_detached = pdf_bytes.replace(b"%%EOF", detached_objs + b"%%EOF")
    res_detached = svc.ingest_document(pdf_with_detached, mime="application/pdf", auto_save=False)
    assert res_detached["status"] == "OK"
    assert res_detached["stats"]["pages"] == 2
    assert all("DetachedGhostTerm" not in c["front_text"] for c in res_detached["cards"])

    # Even if the reachable page is blank (no /Contents), detached streams must NEVER be extracted
    blank_reachable_with_detached = (
        b"%PDF-1.4\r\n"
        b"1 0 obj\r\n<< /Type /Catalog /Pages 2 0 R >>\r\nendobj\r\n"
        b"2 0 obj\r\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\r\nendobj\r\n"
        b"3 0 obj\r\n<< /Type /Page /Parent 2 0 R >>\r\nendobj\r\n"
        + detached_objs
        + b"%%EOF\r\n"
    )
    err_code, pg_count, _, blocks_by_pg = StdlibPdfTextAdapter().inspect_and_extract(blank_reachable_with_detached)
    assert err_code is None
    assert pg_count == 1
    assert blocks_by_pg == {}



