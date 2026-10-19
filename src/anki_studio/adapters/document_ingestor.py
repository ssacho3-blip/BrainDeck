"""Hexagonal Document & Photo Ingestion Adapters (Stdlib PDF + Apple Vision OCR + Optional Cloud Vision).

Implements the DocumentExtractorPort contract with strict Fail-Closed guards:
- Max payload size: 20 MB (`too_large`)
- Max PDF pages: 50 (`too_many_pages`)
- Encrypted PDF detection (`encrypted_pdf`)
- Corrupt file / 0-page detection (`corrupt_file`)
- Zero persistent storage of uploaded user images/PDFs (in-memory or ephemeral temp file deleted in `finally`)
- Privacy guard (AC-10): Cloud LLM Vision is strictly disabled unless `allow_cloud_vision=True`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import urllib.error
import urllib.request
import zlib

from anki_studio.domain.document_deck_builder import (
    DeckPlan,
    DocumentBlock,
    ExtractedDocument,
    SourcedCard,
    build_deck_plan,
)

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_PDF_PAGES = 50

SUPPORTED_MIMES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/webp": ".webp",
}

_PDF_PAGE_RE = re.compile(rb"/Type\s*/Page\b")
_PDF_PAGES_NODE_RE = re.compile(rb"/Type\s*/Pages\b")
_PDF_ENCRYPT_RE = re.compile(rb"/Encrypt\b")
_PDF_TITLE_RE = re.compile(rb"/Title\s*\(([^()\\]{2,120})\)")
_PDF_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", re.DOTALL)
_PDF_REF_RE = re.compile(rb"(\d+)\s+\d+\s+R\b")
_PDF_KIDS_ARRAY_RE = re.compile(rb"/Kids\s*\[(.*?)\]", re.DOTALL)
_PDF_CONTENTS_ARRAY_RE = re.compile(rb"/Contents\s*\[(.*?)\]", re.DOTALL)
_PDF_CONTENTS_SINGLE_RE = re.compile(rb"/Contents\s+(\d+)\s+\d+\s+R\b")
_PDF_STREAM_RE = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
_PDF_TJ_PAREN_RE = re.compile(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj")
_PDF_TJ_ARRAY_RE = re.compile(r"\[(.*?)\]\s*TJ", re.DOTALL)
_PDF_ARRAY_STR_RE = re.compile(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)")
_PDF_HEX_UTF16_RE = re.compile(r"<([0-9A-Fa-f]{4,})>")


@dataclass(frozen=True)
class ExtractionResult:
    """Result of extracting structured text blocks from a PDF or image."""

    status: str  # "OK" | "BLOCKED"
    document: Optional[ExtractedDocument]
    ocr_pages: int
    provider: str
    latency_ms: float
    fallback_reason: Optional[str] = None
    error_code: Optional[str] = None
    detail: Optional[str] = None


def _classify_line_kind_py(line: str) -> str:
    trimmed = line.strip()
    if (
        re.match(r"^(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(\d+\)|\d+\)|\d+\.|•|-\s)", trimmed)
        is not None
    ):
        return "list_item"
    if (
        trimmed.startswith("#")
        or re.match(r"^제\s*\d+\s*[장절편]\b", trimmed) is not None
        or re.match(r"^(?:Chapter|Section|Part)\s+\d+\b", trimmed, re.IGNORECASE) is not None
    ):
        return "heading"
    if (
        len(trimmed) <= 28
        and ":" not in trimmed
        and "：" not in trimmed
        and "." not in trimmed
        and "->" not in trimmed
        and not re.search(r"\d", trimmed)
        and not re.search(r"(?:다|요|음|함|됨)$", trimmed)
    ):
        return "heading"
    return "paragraph"


def _unescape_pdf_literal(raw: str) -> str:
    out = (
        raw.replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
    )
    return out


def _extract_text_from_pdf_stream(content_bytes: bytes) -> List[str]:
    """Extract readable text lines from a decompressed PDF content stream without guessing CID maps."""
    text = content_bytes.decode("latin1", errors="ignore")
    lines: List[str] = []

    for m in _PDF_TJ_PAREN_RE.finditer(text):
        val = _unescape_pdf_literal(m.group(1)).strip()
        if val:
            lines.append(val)

    for m in _PDF_TJ_ARRAY_RE.finditer(text):
        arr = m.group(1)
        parts = [_unescape_pdf_literal(sm.group(1)) for sm in _PDF_ARRAY_STR_RE.finditer(arr)]
        joined = "".join(parts).strip()
        if joined:
            lines.append(joined)

    for m in _PDF_HEX_UTF16_RE.finditer(text):
        hex_str = m.group(1)
        if hex_str.upper().startswith("FEFF") and len(hex_str) % 4 == 0:
            try:
                raw_bytes = bytes.fromhex(hex_str[4:])
                decoded = raw_bytes.decode("utf-16-be", errors="strict").strip()
                if decoded:
                    lines.append(decoded)
            except ValueError:
                pass

    return lines


def _extract_lines_from_raw_stream(raw_stream: bytes) -> List[str]:
    decompressed = raw_stream
    if not (b"BT" in raw_stream and b"ET" in raw_stream):
        try:
            decompressed = zlib.decompress(raw_stream.strip(b"\r\n"))
        except zlib.error:
            return []
    if b"BT" not in decompressed or b"ET" not in decompressed:
        return []
    return _extract_text_from_pdf_stream(decompressed)


class StdlibPdfTextAdapter:
    """Zero-dependency Python stdlib PDF text extractor with page-tree & /Contents reference resolution."""

    def inspect_and_extract(self, data: bytes) -> Tuple[Optional[str], int, Optional[str], Dict[int, List[DocumentBlock]]]:
        """Return (error_code, page_count, title_hint, blocks_by_page)."""
        if not data or not data.lstrip().startswith(b"%PDF-"):
            return "corrupt_file", 0, None, {}

        if _PDF_ENCRYPT_RE.search(data):
            return "encrypted_pdf", 0, None, {}

        title_hint: Optional[str] = None
        title_m = _PDF_TITLE_RE.search(data)
        if title_m:
            try:
                title_hint = title_m.group(1).decode("utf-8", errors="ignore").strip()
            except Exception:
                title_hint = None

        # Parse indirect objects to resolve page-tree order and /Contents references accurately
        obj_map: Dict[int, bytes] = {}
        page_objs_in_file_order: List[int] = []
        pages_nodes: List[int] = []
        catalog_pages_root: Optional[int] = None

        for m in _PDF_OBJ_RE.finditer(data):
            obj_num = int(m.group(1))
            body = m.group(3)
            obj_map[obj_num] = body
            if re.search(rb"/Type\s*/Catalog\b", body):
                cat_pages_m = re.search(rb"/Pages\s+(\d+)\s+\d+\s+R\b", body)
                if cat_pages_m:
                    catalog_pages_root = int(cat_pages_m.group(1))
            if _PDF_PAGE_RE.search(body):
                page_objs_in_file_order.append(obj_num)
            elif _PDF_PAGES_NODE_RE.search(body):
                pages_nodes.append(obj_num)

        ordered_page_objs: List[int] = []
        visited_nodes: set[int] = set()

        def _walk_pages_node(node_id: int) -> None:
            if node_id in visited_nodes:
                return
            visited_nodes.add(node_id)
            body = obj_map.get(node_id, b"")
            if _PDF_PAGE_RE.search(body):
                if node_id not in ordered_page_objs:
                    ordered_page_objs.append(node_id)
                return
            kids_m = _PDF_KIDS_ARRAY_RE.search(body)
            if kids_m:
                for ref_m in _PDF_REF_RE.finditer(kids_m.group(1)):
                    _walk_pages_node(int(ref_m.group(1)))

        has_page_tree = catalog_pages_root is not None or bool(pages_nodes)
        if catalog_pages_root is not None:
            _walk_pages_node(catalog_pages_root)
        elif pages_nodes:
            root_pages_nodes = [
                pnode
                for pnode in pages_nodes
                if not re.search(rb"/Parent\s+\d+\s+\d+\s+R\b", obj_map.get(pnode, b""))
            ]
            for rnode in root_pages_nodes or pages_nodes[:1]:
                _walk_pages_node(rnode)
        else:
            ordered_page_objs = list(page_objs_in_file_order)

        if has_page_tree or obj_map:
            page_count = len(ordered_page_objs)
        else:
            page_count = len(_PDF_PAGE_RE.findall(data))

        if page_count == 0:
            return "corrupt_file", 0, None, {}

        if page_count > MAX_PDF_PAGES:
            return "too_many_pages", page_count, None, {}

        blocks_by_page: Dict[int, List[DocumentBlock]] = {}
        resolved_any_page_contents = False

        for idx, page_obj_num in enumerate(ordered_page_objs[:page_count], start=1):
            page_body = obj_map.get(page_obj_num, b"")
            content_obj_nums: List[int] = []
            arr_m = _PDF_CONTENTS_ARRAY_RE.search(page_body)
            if arr_m:
                content_obj_nums = [int(rm.group(1)) for rm in _PDF_REF_RE.finditer(arr_m.group(1))]
            else:
                single_m = _PDF_CONTENTS_SINGLE_RE.search(page_body)
                if single_m:
                    content_obj_nums = [int(single_m.group(1))]

            page_lines: List[str] = []
            if content_obj_nums:
                resolved_any_page_contents = True
                for c_num in content_obj_nums:
                    c_body = obj_map.get(c_num, b"")
                    for raw_stream in _PDF_STREAM_RE.findall(c_body):
                        page_lines.extend(_extract_lines_from_raw_stream(raw_stream))
            else:
                # Check if stream is embedded directly inside the page object
                for raw_stream in _PDF_STREAM_RE.findall(page_body):
                    resolved_any_page_contents = True
                    page_lines.extend(_extract_lines_from_raw_stream(raw_stream))

            if page_lines:
                page_blocks = blocks_by_page.setdefault(idx, [])
                for ln in page_lines:
                    for sub_ln in ln.splitlines():
                        cleaned = sub_ln.strip()
                        if cleaned:
                            page_blocks.append(
                                DocumentBlock(
                                    kind=_classify_line_kind_py(cleaned),
                                    text=cleaned,
                                    page=idx,
                                    confidence=1.0,
                                )
                            )

        # Fallback only if synthetic PDF had raw streams without a page tree or indirect objects
        if not resolved_any_page_contents and not has_page_tree and not obj_map:
            streams = _PDF_STREAM_RE.findall(data)
            page_idx = 1
            for raw_stream in streams:
                lines = _extract_lines_from_raw_stream(raw_stream)
                if lines:
                    target_page = min(page_count, page_idx)
                    page_blocks = blocks_by_page.setdefault(target_page, [])
                    for ln in lines:
                        for sub_ln in ln.splitlines():
                            cleaned = sub_ln.strip()
                            if cleaned:
                                page_blocks.append(
                                    DocumentBlock(
                                        kind=_classify_line_kind_py(cleaned),
                                        text=cleaned,
                                        page=target_page,
                                        confidence=1.0,
                                    )
                                )
                    page_idx += 1

        return None, page_count, title_hint, blocks_by_page


class AppleVisionOcrAdapter:
    """macOS Native Vision.framework + PDFKit helper adapter (`anki_vision_ocr`)."""

    def __init__(
        self,
        helper_path: Optional[Path] = None,
        timeout_sec: float = 30.0,
        runner: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
    ) -> None:
        default_bin = Path(__file__).resolve().parent / "macos_ocr_helper" / "anki_vision_ocr"
        self.helper_path = helper_path if helper_path is not None else default_bin
        self.timeout_sec = float(timeout_sec)
        self._runner = runner or subprocess.run

    def is_available(self) -> bool:
        return self.helper_path.is_file() and os.access(self.helper_path, os.X_OK)

    def extract(self, data: bytes, mime: str) -> ExtractionResult:
        t0 = time.perf_counter()
        if not self.is_available() and self._runner is subprocess.run:
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="apple_vision",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                fallback_reason="helper_binary_missing",
                error_code="ocr_unavailable",
                detail="Apple Vision OCR binary not available",
            )

        suffix = SUPPORTED_MIMES.get(mime, ".bin")
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(prefix="anki_ingest_", suffix=suffix, delete=False) as tf:
                tf.write(data)
                tmp_path = Path(tf.name)

            proc = self._runner(
                [str(self.helper_path), str(tmp_path), mime],
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
            elapsed = round((time.perf_counter() - t0) * 1000.0, 2)
            raw_out = (proc.stdout or "").strip()
            if not raw_out:
                return ExtractionResult(
                    status="BLOCKED",
                    document=None,
                    ocr_pages=0,
                    provider="apple_vision",
                    latency_ms=elapsed,
                    error_code="corrupt_file",
                    detail=proc.stderr or "Empty OCR helper output",
                )
            payload = json.loads(raw_out)
            if not payload.get("ok"):
                return ExtractionResult(
                    status="BLOCKED",
                    document=None,
                    ocr_pages=0,
                    provider="apple_vision",
                    latency_ms=elapsed,
                    error_code=str(payload.get("error_code") or "corrupt_file"),
                    detail="Rejected by Apple Vision / PDFKit helper",
                )

            blocks = tuple(
                DocumentBlock(
                    kind=str(b.get("kind") or "paragraph"),
                    text=str(b.get("text") or ""),
                    page=int(b.get("page") or 1),
                    confidence=float(b["confidence"]) if b.get("confidence") is not None else None,
                )
                for b in payload.get("blocks", [])
            )
            doc = ExtractedDocument(
                blocks=blocks,
                title_hint=payload.get("title_hint") or None,
                source_kind=str(payload.get("source_kind") or ("pdf" if mime == "application/pdf" else "image")),
                page_count=int(payload.get("page_count") or 1),
            )
            return ExtractionResult(
                status="OK",
                document=doc,
                ocr_pages=int(payload.get("ocr_pages") or 0),
                provider="apple_vision",
                latency_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="apple_vision",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="ocr_timeout",
                detail="Apple Vision OCR timed out",
            )
        except (ValueError, KeyError, OSError) as exc:
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="apple_vision",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="corrupt_file",
                detail=str(exc),
            )
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)


class LlmVisionAdapter:
    """Optional Cloud/Local Multimodal Vision Adapter (strictly opt-in via `allow_cloud_vision=True`)."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_sec: float = 12.0,
        http_sender: Optional[Callable[[bytes], str]] = None,
    ) -> None:
        self.endpoint_url = (endpoint_url or os.environ.get("ANKI_STUDIO_VISION_URL") or "").strip()
        self.model_name = (model_name or os.environ.get("ANKI_STUDIO_VISION_MODEL") or "glm-5.3-flash").strip()
        self.timeout_sec = float(timeout_sec)
        self._http_sender = http_sender

    def is_configured(self) -> bool:
        return bool(self.endpoint_url or self._http_sender is not None)

    def extract(self, data: bytes, mime: str) -> ExtractionResult:
        t0 = time.perf_counter()
        if not self.is_configured():
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="llm_vision",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="ocr_unavailable",
                detail="Vision LLM endpoint is not configured",
            )

        b64 = base64.b64encode(data).decode("ascii")
        req_payload = json.dumps(
            {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Extract all text blocks from this study image/document as strict JSON: "
                                    '{"title_hint": "...", "blocks": [{"kind": "heading|paragraph|list_item", "text": "...", "page": 1}]}'
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ],
                    }
                ],
                "temperature": 0.0,
            }
        ).encode("utf-8")

        try:
            if self._http_sender is not None:
                raw_resp = self._http_sender(req_payload)
            else:
                req = urllib.request.Request(
                    self.endpoint_url,
                    data=req_payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    raw_resp = (
                        body.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )

            parsed = json.loads(raw_resp)
            if not isinstance(parsed, dict) or not isinstance(parsed.get("blocks"), list):
                return ExtractionResult(
                    status="BLOCKED",
                    document=None,
                    ocr_pages=0,
                    provider=f"llm_vision:{self.model_name}",
                    latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    error_code="llm_truncated",
                    detail="Invalid or truncated JSON schema from Vision LLM",
                )

            blocks: List[DocumentBlock] = []
            for item in parsed["blocks"]:
                if not isinstance(item, dict) or not str(item.get("text") or "").strip():
                    continue
                blocks.append(
                    DocumentBlock(
                        kind=str(item.get("kind") or "paragraph"),
                        text=str(item["text"]).strip(),
                        page=int(item.get("page") or 1),
                        confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
                    )
                )

            return ExtractionResult(
                status="OK",
                document=ExtractedDocument(
                    blocks=tuple(blocks),
                    title_hint=parsed.get("title_hint") or None,
                    source_kind="pdf" if mime == "application/pdf" else "image",
                    page_count=1,
                ),
                ocr_pages=1,
                provider=f"llm_vision:{self.model_name}",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider=f"llm_vision:{self.model_name}",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="llm_truncated",
                detail=str(exc),
            )


def _validate_image_magic(data: bytes, mime: str) -> bool:
    if len(data) < 8:
        return False
    if mime in ("image/png",):
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime in ("image/jpeg", "image/jpg"):
        return data.startswith(b"\xff\xd8\xff")
    if mime == "image/webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if mime == "image/heic":
        return b"ftyp" in data[:16]
    return False


class DocumentIngestor:
    """Coordinates validation, page-level PDF/OCR extraction, and grounded DeckPlan synthesis."""

    def __init__(
        self,
        pdf_adapter: Optional[StdlibPdfTextAdapter] = None,
        vision_adapter: Optional[AppleVisionOcrAdapter] = None,
        llm_vision_adapter: Optional[LlmVisionAdapter] = None,
    ) -> None:
        self.pdf_adapter = pdf_adapter or StdlibPdfTextAdapter()
        self.vision_adapter = vision_adapter or AppleVisionOcrAdapter()
        self.llm_vision_adapter = llm_vision_adapter or LlmVisionAdapter()

    def extract_document(
        self,
        data: bytes,
        mime: str,
        allow_cloud_vision: bool = False,
    ) -> ExtractionResult:
        t0 = time.perf_counter()
        norm_mime = (mime or "").split(";")[0].strip().lower()

        if norm_mime not in SUPPORTED_MIMES:
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="validator",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="unsupported_mime",
                detail=f"Unsupported Content-Type: {norm_mime}",
            )

        if not data:
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="validator",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="corrupt_file",
                detail="Empty document payload",
            )

        if len(data) > MAX_DOCUMENT_BYTES:
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="validator",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="too_large",
                detail=f"Payload exceeds {MAX_DOCUMENT_BYTES} bytes",
            )

        if norm_mime == "application/pdf":
            err, page_count, title_hint, blocks_by_page = self.pdf_adapter.inspect_and_extract(data)
            if err is not None:
                return ExtractionResult(
                    status="BLOCKED",
                    document=None,
                    ocr_pages=0,
                    provider="stdlib_pdf",
                    latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    error_code=err,
                    detail=f"PDF validation failed: {err}",
                )

            # Check if all pages have sufficient text (>= 20 chars) from stdlib parser
            missing_pages = [
                p
                for p in range(1, page_count + 1)
                if sum(len(b.text) for b in blocks_by_page.get(p, [])) < 20
            ]
            if not missing_pages:
                all_blocks: List[DocumentBlock] = []
                for p in range(1, page_count + 1):
                    all_blocks.extend(blocks_by_page.get(p, []))
                return ExtractionResult(
                    status="OK",
                    document=ExtractedDocument(
                        blocks=tuple(all_blocks),
                        title_hint=title_hint,
                        source_kind="pdf",
                        page_count=page_count,
                    ),
                    ocr_pages=0,
                    provider="stdlib_pdf",
                    latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                )

            # Need OCR for scanned pages
            vision_res = self.vision_adapter.extract(data, norm_mime)
            if vision_res.status == "OK" and vision_res.document is not None:
                # Merge stdlib text pages with OCR pages
                merged_blocks: List[DocumentBlock] = []
                ocr_by_page: Dict[int, List[DocumentBlock]] = {}
                for b in vision_res.document.blocks:
                    ocr_by_page.setdefault(b.page, []).append(b)
                ocr_used = 0
                for p in range(1, page_count + 1):
                    std_b = blocks_by_page.get(p, [])
                    if sum(len(b.text) for b in std_b) >= 20:
                        merged_blocks.extend(std_b)
                    else:
                        ocr_used += 1
                        merged_blocks.extend(ocr_by_page.get(p, []))
                return ExtractionResult(
                    status="OK",
                    document=ExtractedDocument(
                        blocks=tuple(merged_blocks),
                        title_hint=title_hint or vision_res.document.title_hint,
                        source_kind="pdf",
                        page_count=page_count,
                    ),
                    ocr_pages=ocr_used,
                    provider="stdlib_pdf+apple_vision",
                    latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    fallback_reason="scanned_pdf_pages",
                )

            if vision_res.error_code == "ocr_timeout":
                return vision_res

            # If at least some pages had stdlib text, return them if >= 40 chars total
            partial_blocks = [b for p in range(1, page_count + 1) for b in blocks_by_page.get(p, [])]
            if sum(len(b.text) for b in partial_blocks) >= 40:
                return ExtractionResult(
                    status="OK",
                    document=ExtractedDocument(
                        blocks=tuple(partial_blocks),
                        title_hint=title_hint,
                        source_kind="pdf",
                        page_count=page_count,
                    ),
                    ocr_pages=0,
                    provider="stdlib_pdf",
                    latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    fallback_reason="partial_text_layer",
                )

            if allow_cloud_vision:
                return self.llm_vision_adapter.extract(data, norm_mime)

            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="apple_vision",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                fallback_reason="cloud_vision_disabled",
                error_code=vision_res.error_code or "ocr_unavailable",
                detail="Scanned PDF requires OCR, and local OCR is unavailable",
            )

        # Image path (PNG / JPEG / HEIC / WEBP)
        if not _validate_image_magic(data, norm_mime):
            return ExtractionResult(
                status="BLOCKED",
                document=None,
                ocr_pages=0,
                provider="validator",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                error_code="corrupt_file",
                detail="Invalid image header magic bytes",
            )

        vision_res = self.vision_adapter.extract(data, norm_mime)
        if vision_res.status == "OK" or vision_res.error_code in ("ocr_timeout", "corrupt_file"):
            return vision_res

        if allow_cloud_vision:
            return self.llm_vision_adapter.extract(data, norm_mime)

        return ExtractionResult(
            status="BLOCKED",
            document=None,
            ocr_pages=0,
            provider="apple_vision",
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            fallback_reason="cloud_vision_disabled",
            error_code="ocr_unavailable",
            detail="Image OCR unavailable and allow_cloud_vision is False",
        )
