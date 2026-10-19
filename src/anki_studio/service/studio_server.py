"""HTTP Application Server for Anki Studio 2.0 (FSRS-5 & AI Active Recall Engine)."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from anki_studio.adapters.ai_engine import AICardSynthesizer
from anki_studio.adapters.sqlite_store import AnkiStudioStore
from anki_studio.domain.ai_learning import (
    decompose_leech_card,
    evaluate_free_recall,
    generate_socratic_hint,
)
from anki_studio.domain.fsrs_math import Rating


MAX_JSON_BODY_BYTES = 512 * 1024  # 512 KB hard cap
STATIC_DIR = Path(__file__).resolve().parents[1] / "ui" / "static"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "build" / "anki_studio.sqlite"


def _finite_float(val_str: str) -> float:
    val = float(val_str)
    if not math.isfinite(val):
        raise ValueError(f"Non-finite float value rejected: {val_str}")
    return val


class AnkiStudioService:
    """Application facade coordinating FSRS-5 domain, SQLite WAL store, and AI card synthesizer."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        ai_synthesizer: Optional[AICardSynthesizer] = None,
        seed_defaults: bool = True,
    ) -> None:
        self.store = AnkiStudioStore(db_path)
        self.ai = ai_synthesizer or AICardSynthesizer()
        if seed_defaults:
            self.store.seed_default_decks_if_empty()

    def get_status(self) -> Dict[str, Any]:
        stats = self.store.get_dashboard_stats()
        decks = self.store.list_decks()
        return {
            "ok": True,
            "engine": "Anki Studio 2.0 (FSRS-5 + AI Active Recall)",
            "stats": stats,
            "decks": decks,
        }

    def get_due_cards(self, deck_id: Optional[int] = None, limit: int = 50) -> Dict[str, Any]:
        cards = self.store.get_due_cards(deck_id=deck_id, limit=limit)
        return {"ok": True, "count": len(cards), "cards": cards}

    def submit_review(self, card_id: int, rating: int) -> Dict[str, Any]:
        if rating not in (1, 2, 3, 4):
            raise ValueError(f"rating must be 1 (Again), 2 (Hard), 3 (Good), or 4 (Easy); got {rating}")
        outcome = self.store.review_card(card_id=card_id, rating=Rating(rating))
        return {
            "ok": True,
            "card_id": outcome["card_id"],
            "rating": outcome["rating"],
            "scheduled_days": outcome["scheduled_days"],
            "scheduled_label": outcome["scheduled_label"],
            "due_at": outcome["due_at"],
            "memory": {
                "difficulty": outcome["memory"].difficulty,
                "stability": outcome["memory"].stability,
                "reps": outcome["memory"].reps,
                "lapses": outcome["memory"].lapses,
                "state": outcome["memory"].state,
            },
        }

    def evaluate_recall(
        self,
        user_answer: str,
        expected_answer: str,
        question_text: str = "",
    ) -> Dict[str, Any]:
        ev = evaluate_free_recall(
            user_answer=user_answer,
            expected_answer=expected_answer,
            question_text=question_text,
        )
        return {
            "ok": True,
            "score_pct": ev.score_pct,
            "recommended_rating": int(ev.recommended_rating),
            "recommended_label": ev.recommended_rating.name,
            "matched_terms": list(ev.matched_terms),
            "missing_terms": list(ev.missing_terms),
            "numeric_match": ev.numeric_match,
            "negation_conflict": ev.negation_conflict,
            "feedback": ev.feedback,
        }

    def get_socratic_hint(
        self,
        question_text: str,
        target_answer: str,
        lapses: int = 0,
        level: int = 1,
    ) -> Dict[str, Any]:
        hint = generate_socratic_hint(
            question_text=question_text,
            target_answer=target_answer,
            lapses=lapses,
            level=level,
        )
        return {
            "ok": True,
            "level": hint.level,
            "structural_cue": hint.structural_cue,
            "socratic_question": hint.socratic_question,
            "mnemonic_tip": hint.mnemonic_tip,
        }

    def decompose_leech(
        self,
        front_text: str,
        back_text: str,
        deck_id: Optional[int] = None,
        auto_save: bool = False,
        parent_card_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        specs = decompose_leech_card(front_text=front_text, back_text=back_text)
        saved_ids = []
        parent_suspended = False
        if auto_save and deck_id is not None:
            for s in specs:
                nid = self.store.add_note(
                    deck_id=int(deck_id),
                    front_text=s.front_text,
                    back_text=s.back_text,
                    note_type=s.note_type,
                    tags=list(s.tags),
                )
                saved_ids.append(nid)
            if parent_card_id is not None and saved_ids:
                parent_suspended = self.store.suspend_card(int(parent_card_id))
        return {
            "ok": True,
            "cards": [
                {
                    "note_type": s.note_type,
                    "front_text": s.front_text,
                    "back_text": s.back_text,
                    "tags": list(s.tags),
                    "rationale": s.rationale,
                }
                for s in specs
            ],
            "saved_note_ids": saved_ids,
            "parent_card_id": int(parent_card_id) if parent_card_id is not None else None,
            "parent_suspended": parent_suspended,
        }

    def generate_ai_cards(
        self,
        raw_text: str,
        domain_mode: str = "auto",
        deck_id: Optional[int] = None,
        auto_save: bool = True,
        max_cards: int = 10,
    ) -> Dict[str, Any]:
        res = self.ai.synthesize_cards(raw_text=raw_text, domain_mode=domain_mode, max_cards=max_cards)
        saved_ids = []
        if auto_save and res["cards"]:
            target_deck = int(deck_id) if deck_id is not None else self.store.ensure_deck("✨ AI 자동 생성 덱 (AI Card Factory)")
            for c in res["cards"]:
                nid = self.store.add_note(
                    deck_id=target_deck,
                    front_text=c["front_text"],
                    back_text=c["back_text"],
                    note_type=c["note_type"],
                    tags=c["tags"],
                )
                saved_ids.append(nid)
        return {
            "ok": True,
            "engine": res["engine"],
            "provider": res.get("provider", "deterministic_nlp"),
            "latency_ms": res.get("latency_ms", 0.0),
            "fallback_reason": res.get("fallback_reason"),
            "error_code": res.get("error_code"),
            "generated_count": len(res["cards"]),
            "saved_note_ids": saved_ids,
            "cards": res["cards"],
        }

    def decompress_backlog(
        self,
        deck_id: Optional[int] = None,
        daily_cap: int = 25,
        horizon_days: int = 7,
    ) -> Dict[str, Any]:
        summary = self.store.decompress_backlog(
            deck_id=deck_id,
            daily_cap=daily_cap,
            horizon_days=horizon_days,
        )
        return {"ok": True, **summary}


def create_http_handler(service: Optional[AnkiStudioService] = None) -> type[BaseHTTPRequestHandler]:
    """Create the BaseHTTPRequestHandler class bound to AnkiStudioService."""
    svc = service or AnkiStudioService()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_JSON_BODY_BYTES:
                raise OverflowError("payload_too_large")
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw, parse_float=_finite_float, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"Invalid constant: {c}")))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/api/status":
                self._send_json(svc.get_status())
                return

            if path == "/api/due":
                deck_raw = qs.get("deck_id", [None])[0]
                deck_id = int(deck_raw) if deck_raw and deck_raw.isdigit() else None
                self._send_json(svc.get_due_cards(deck_id=deck_id))
                return

            if path == "/api/export.apkg":
                deck_raw = qs.get("deck_id", [None])[0]
                deck_id = int(deck_raw) if deck_raw and deck_raw.isdigit() else None
                with tempfile.TemporaryDirectory() as tmpdir:
                    out_apkg = Path(tmpdir) / "Anki_Studio_Export.apkg"
                    svc.store.export_apkg(out_apkg, deck_id=deck_id)
                    data = out_apkg.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="Anki_Studio_Export.apkg"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            # Static UI files
            rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
            target = (STATIC_DIR / rel).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
                self._send_json({"ok": False, "error": "not_found"}, status=404)
                return

            mime = "text/html; charset=utf-8"
            if target.suffix == ".js":
                mime = "application/javascript; charset=utf-8"
            elif target.suffix == ".css":
                mime = "text/css; charset=utf-8"

            raw_bytes = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw_bytes)))
            self.end_headers()
            self.wfile.write(raw_bytes)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                body = self._read_json_body()
            except OverflowError:
                self._send_json({"ok": False, "error": "payload_too_large"}, status=413)
                return
            except ValueError as exc:
                self._send_json({"ok": False, "error": "invalid_json", "detail": str(exc)}, status=400)
                return

            try:
                if path == "/api/review":
                    res = svc.submit_review(
                        card_id=int(body["card_id"]),
                        rating=int(body["rating"]),
                    )
                    self._send_json(res)
                    return

                if path == "/api/ai/evaluate":
                    res = svc.evaluate_recall(
                        user_answer=str(body.get("user_answer") or ""),
                        expected_answer=str(body.get("expected_answer") or ""),
                        question_text=str(body.get("question_text") or ""),
                    )
                    self._send_json(res)
                    return

                if path == "/api/ai/hint":
                    res = svc.get_socratic_hint(
                        question_text=str(body.get("question_text") or ""),
                        target_answer=str(body.get("target_answer") or ""),
                        lapses=int(body.get("lapses") or 0),
                        level=int(body.get("level") or 1),
                    )
                    self._send_json(res)
                    return

                if path == "/api/ai/decompose-leech":
                    deck_id = int(body["deck_id"]) if body.get("deck_id") is not None else None
                    parent_card_id = int(body["parent_card_id"]) if body.get("parent_card_id") is not None else None
                    res = svc.decompose_leech(
                        front_text=str(body.get("front_text") or ""),
                        back_text=str(body.get("back_text") or ""),
                        deck_id=deck_id,
                        auto_save=bool(body.get("auto_save", False)),
                        parent_card_id=parent_card_id,
                    )
                    self._send_json(res)
                    return

                if path == "/api/ai/generate-cards":
                    deck_id = int(body["deck_id"]) if body.get("deck_id") is not None else None
                    res = svc.generate_ai_cards(
                        raw_text=str(body.get("raw_text") or ""),
                        domain_mode=str(body.get("domain_mode") or "auto"),
                        deck_id=deck_id,
                        auto_save=bool(body.get("auto_save", True)),
                        max_cards=int(body.get("max_cards") or 10),
                    )
                    self._send_json(res)
                    return

                if path == "/api/backlog/decompress":
                    deck_id = int(body["deck_id"]) if body.get("deck_id") is not None else None
                    res = svc.decompress_backlog(
                        deck_id=deck_id,
                        daily_cap=int(body.get("daily_cap") or 25),
                        horizon_days=int(body.get("horizon_days") or 7),
                    )
                    self._send_json(res)
                    return

                self._send_json({"ok": False, "error": "not_found"}, status=404)
            except KeyError as exc:
                self._send_json({"ok": False, "error": "not_found", "detail": str(exc)}, status=404)
            except (ValueError, TypeError) as exc:
                self._send_json({"ok": False, "error": "bad_request", "detail": str(exc)}, status=400)

    return Handler


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 4390,
    service: Optional[AnkiStudioService] = None,
) -> ThreadingHTTPServer:
    handler_cls = create_http_handler(service=service)
    return ThreadingHTTPServer((host, port), handler_cls)


if __name__ == "__main__":
    srv = create_http_server(host="127.0.0.1", port=4390)
    print("Anki Studio 2.0 running on http://127.0.0.1:4390")
    srv.serve_forever()

