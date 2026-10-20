"""HTTP Application Server for Anki Studio 2.0 (FSRS-5 & AI Active Recall Engine)."""

from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from anki_studio.adapters.ai_engine import AICardSynthesizer
from anki_studio.adapters.document_ingestor import DocumentIngestor, MAX_DOCUMENT_BYTES
from anki_studio.adapters.reference_pack_store import (
    TierULedgerStore,
    build_starter_k12_and_exam_pack,
    inspect_pack_catalog,
)
from anki_studio.adapters.sqlite_store import AnkiStudioStore
from anki_studio.domain.adaptive_quiz import (
    CandidateDistractor,
    QuestionFacet,
    build_tap_blocks,
    select_distractors,
)
from anki_studio.domain.ai_learning import (
    decompose_leech_card,
    evaluate_free_recall,
    generate_socratic_hint,
)
from anki_studio.domain.document_deck_builder import build_deck_plan
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
    """Application facade coordinating FSRS-5 domain, SQLite WAL store, AI synthesizer, and Document Ingestor."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        ai_synthesizer: Optional[AICardSynthesizer] = None,
        document_ingestor: Optional[DocumentIngestor] = None,
        seed_defaults: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.store = AnkiStudioStore(self.db_path)
        self.ai = ai_synthesizer or AICardSynthesizer()
        self.ingestor = document_ingestor or DocumentIngestor()
        self.starter_pack_path = self.db_path.parent / "starter_pack.sqlite"
        self.tier_u_path = self.db_path.parent / "tier_u_ledger.sqlite"
        self.pack_meta = build_starter_k12_and_exam_pack(self.starter_pack_path)
        self.ledger = TierULedgerStore(self.tier_u_path)
        self.ledger.register_installed_pack(
            pack_id=self.pack_meta["pack_id"],
            pack_version=self.pack_meta["pack_version"],
            file_sha256=self.pack_meta["file_sha256"],
            content_sha256=self.pack_meta["content_sha256"],
            local_path=str(self.starter_pack_path),
            license_spdx=self.pack_meta["license_spdx"],
            redistribution_allowed=bool(self.pack_meta["redistribution_allowed"]),
        )
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

    def ingest_document(
        self,
        data: bytes,
        mime: str,
        deck_name: Optional[str] = None,
        max_cards: int = 30,
        auto_save: bool = False,
        allow_cloud_vision: bool = False,
        now_date_str: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract text/OCR from PDF or photo, build a grounded DeckPlan, and optionally batch-save (AC-1..AC-10)."""
        ext = self.ingestor.extract_document(
            data=data,
            mime=mime,
            allow_cloud_vision=allow_cloud_vision,
        )
        if ext.status != "OK" or ext.document is None:
            return {
                "ok": False,
                "status": "BLOCKED",
                "error_code": ext.error_code or "corrupt_file",
                "detail": ext.detail,
                "deck_id": None,
                "deck_name": deck_name or "",
                "category": "general",
                "cards": [],
                "stats": {
                    "pages": 0,
                    "ocr_pages": ext.ocr_pages,
                    "low_confidence_lines": 0,
                    "unmeasured_confidence_lines": 0,
                    "dropped_ungrounded": 0,
                    "duplicates": 0,
                    "total_chars": 0,
                },
                "provider": ext.provider,
                "latency_ms": ext.latency_ms,
                "fallback_reason": ext.fallback_reason,
            }

        date_str = now_date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plan = build_deck_plan(
            doc=ext.document,
            user_deck_name=deck_name,
            max_cards=max_cards,
            now_date_str=date_str,
            ocr_pages=ext.ocr_pages,
        )
        stats_dict = {
            "pages": plan.stats.pages,
            "ocr_pages": plan.stats.ocr_pages,
            "low_confidence_lines": plan.stats.low_confidence_lines,
            "unmeasured_confidence_lines": plan.stats.unmeasured_confidence_lines,
            "dropped_ungrounded": plan.stats.dropped_ungrounded,
            "duplicates": plan.stats.duplicates,
            "total_chars": plan.stats.total_chars,
        }

        if plan.status != "OK":
            return {
                "ok": False,
                "status": "BLOCKED",
                "error_code": plan.error_code or "no_cards",
                "deck_id": None,
                "deck_name": plan.deck_name,
                "category": plan.category,
                "cards": [],
                "stats": stats_dict,
                "provider": ext.provider,
                "latency_ms": ext.latency_ms,
                "fallback_reason": ext.fallback_reason,
            }

        cards_out = [
            {
                "front_text": sc.spec.front_text,
                "back_text": sc.spec.back_text,
                "note_type": sc.spec.note_type,
                "tags": list(sc.spec.tags),
                "rationale": sc.spec.rationale,
                "pattern": sc.pattern,
                "source_page": sc.source_page,
                "source_excerpt": sc.source_excerpt,
            }
            for sc in plan.cards
        ]

        saved_deck_id: Optional[int] = None
        saved_note_ids: List[int] = []
        if auto_save:
            try:
                batch_res = self.store.create_deck_with_notes(
                    deck_name=plan.deck_name,
                    notes=cards_out,
                    description=f"📄 사진·PDF 자동 생성 덱 ({plan.category})",
                )
                saved_deck_id = int(batch_res["deck_id"])
                saved_note_ids = list(batch_res["saved_note_ids"])
            except Exception as exc:
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "error_code": "db_write_failed",
                    "detail": str(exc),
                    "deck_id": None,
                    "deck_name": plan.deck_name,
                    "category": plan.category,
                    "cards": [],
                    "stats": stats_dict,
                    "provider": ext.provider,
                    "latency_ms": ext.latency_ms,
                    "fallback_reason": ext.fallback_reason,
                }

        return {
            "ok": True,
            "status": "OK",
            "error_code": None,
            "deck_id": saved_deck_id,
            "deck_name": plan.deck_name,
            "category": plan.category,
            "saved_note_ids": saved_note_ids,
            "cards": cards_out,
            "stats": stats_dict,
            "provider": ext.provider,
            "latency_ms": ext.latency_ms,
            "fallback_reason": ext.fallback_reason,
        }

    def save_deck_batch(
        self,
        deck_name: str,
        cards: List[Dict[str, Any]],
        category: str = "general",
    ) -> Dict[str, Any]:
        """Atomically save previewed document/photo cards into a single deck (AC-4)."""
        res = self.store.create_deck_with_notes(
            deck_name=deck_name,
            notes=cards,
            description=f"📄 사진·PDF 자동 생성 덱 ({category})",
        )
        return {
            "ok": True,
            "deck_id": res["deck_id"],
            "deck_name": res["deck_name"],
            "saved_count": len(res["saved_note_ids"]),
            "saved_note_ids": res["saved_note_ids"],
        }

    def get_curriculum_catalog(self) -> Dict[str, Any]:
        """Return built-in K-12 textbooks (e.g. Mid-1 Dong-A Yoon) and Hanja/Exam collections."""
        cat = inspect_pack_catalog(self.starter_pack_path)
        return {
            "ok": True,
            "pack_id": self.pack_meta["pack_id"],
            "pack_version": self.pack_meta["pack_version"],
            "textbooks": cat["textbooks"],
            "collections": cat["collections"],
        }

    def generate_collection_deck(
        self,
        collection_id: str,
        limit: int = 25,
        deck_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Materialize cards from a built-in collection (e.g., `hanja-grade:8geup`..`3geup`, `khist:essential`)."""
        cat = inspect_pack_catalog(self.starter_pack_path)
        col_meta = next((c for c in cat["collections"] if c["collection_id"] == collection_id), None)
        if col_meta is None:
            raise ValueError(f"Unknown collection_id: {collection_id}")

        resolved_title = (deck_name or "").strip() or f"📚 {col_meta['level_label']} ({collection_id})"
        tier_u_deck_id = self.ledger.create_deck(
            profile_id=1,
            name=f"{resolved_title} [{datetime.now(timezone.utc).strftime('%H%M%S_%f')}]",
            category="hanja" if "hanja" in collection_id else "general",
        )
        # Re-use or create activation for profile 1
        with self.ledger._write_tx() as conn:
            existing_act = conn.execute(
                "SELECT activation_id FROM pack_activations WHERE profile_id = 1 AND pack_id = ? AND collection_id = ?",
                (self.pack_meta["pack_id"], collection_id),
            ).fetchone()
        if existing_act is not None:
            act_id = int(existing_act["activation_id"])
            with self.ledger._write_tx() as conn:
                conn.execute("UPDATE pack_activations SET next_ordinal = 1, deck_id = ? WHERE activation_id = ?", (tier_u_deck_id, act_id))
        else:
            act_id = self.ledger.activate_pack_collection(
                profile_id=1,
                deck_id=tier_u_deck_id,
                pack_id=self.pack_meta["pack_id"],
                collection_id=collection_id,
            )

        mat_cards = self.ledger.materialize_daily_pack_cards(
            activation_id=act_id,
            pack_db_path=self.starter_pack_path,
            daily_new_limit=max(1, min(200, int(limit))),
        )
        notes_payload = [
            {
                "front_text": c["front"],
                "back_text": c["back"],
                "note_type": "basic",
                "tags": [collection_id.replace(":", "_")],
            }
            for c in mat_cards
        ]
        batch = self.store.create_deck_with_notes(
            deck_name=resolved_title,
            notes=notes_payload,
            description=f"내장 레퍼런스 팩 ({collection_id})",
        )
        return {
            "ok": True,
            "collection_id": collection_id,
            "deck_id": batch["deck_id"],
            "deck_name": batch["deck_name"],
            "saved_count": len(batch["saved_note_ids"]),
            "cards": notes_payload,
        }

    def generate_exam_scope_deck(
        self,
        textbook_id: str,
        unit_ids: List[str],
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        max_importance_tier: int = 2,
        deck_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve a middle/high school textbook exam scope (e.g., 중1 동아 윤정미 Lesson 1~2) and create a study deck."""
        if not unit_ids:
            raise ValueError("unit_ids must contain at least one curriculum unit")
        cat = inspect_pack_catalog(self.starter_pack_path)
        tb_meta = next((t for t in cat["textbooks"] if t["textbook_id"] == textbook_id), None)
        if tb_meta is None:
            raise ValueError(f"Unknown textbook_id: {textbook_id}")

        resolved_title = (deck_name or "").strip() or f"🏫 {tb_meta['title']} 시험범위 ({len(unit_ids)}개 단원)"
        tier_u_deck_id = self.ledger.create_deck(
            profile_id=1,
            name=f"{resolved_title} [{datetime.now(timezone.utc).strftime('%H%M%S_%f')}]",
            category=str(tb_meta.get("subject_code") or "language"),
        )
        rules = [
            {
                "unit_id": str(uid),
                "include_subunits": True,
                "page_start": int(page_start) if page_start is not None else None,
                "page_end": int(page_end) if page_end is not None else None,
            }
            for uid in unit_ids
        ]
        scope_id = self.ledger.create_exam_scope(
            profile_id=1,
            deck_id=tier_u_deck_id,
            title=resolved_title,
            pack_id=self.pack_meta["pack_id"],
            resolved_pack_version=self.pack_meta["pack_version"],
            textbook_id=textbook_id,
            max_importance_tier=max(1, min(3, int(max_importance_tier))),
            rules=rules,
        )
        resolved_items = self.ledger.resolve_and_reconcile_exam_scope(
            scope_id=scope_id,
            pack_db_path=self.starter_pack_path,
            materialize_now=True,
        )
        notes_payload: List[Dict[str, Any]] = []
        with self.ledger._write_tx() as conn:
            for item in resolved_items:
                nid = item.get("materialized_note_id") or item.get("user_note_id")
                if nid is not None:
                    nrow = conn.execute(
                        "SELECT front, back, note_type, curriculum_unit_id, textbook_page_no FROM notes WHERE id = ?",
                        (int(nid),),
                    ).fetchone()
                    if nrow is not None:
                        page_tag = f"p.{nrow['textbook_page_no']}" if nrow["textbook_page_no"] else ""
                        notes_payload.append(
                            {
                                "front_text": str(nrow["front"]),
                                "back_text": str(nrow["back"]),
                                "note_type": str(nrow["note_type"] or "basic"),
                                "tags": [textbook_id, str(nrow["curriculum_unit_id"] or ""), page_tag],
                            }
                        )

        batch = self.store.create_deck_with_notes(
            deck_name=resolved_title,
            notes=notes_payload,
            description=f"교과서 시험범위 맞춤 덱 ({tb_meta['title']})",
        )
        return {
            "ok": True,
            "scope_id": scope_id,
            "textbook_id": textbook_id,
            "deck_id": batch["deck_id"],
            "deck_name": batch["deck_name"],
            "saved_count": len(batch["saved_note_ids"]),
            "cards": notes_payload,
        }

    def build_interactive_quiz(
        self,
        card_id: int,
        age_tier: str = "teen",
    ) -> Dict[str, Any]:
        """Build a 4-choice multiple-choice or tap-block interactive quiz for a due card using AdaptiveQuizEngine."""
        due = self.store.get_due_cards(limit=200)
        target = next((c for c in due if int(c["card_id"]) == int(card_id)), None)
        if target is None:
            raise KeyError(f"Card {card_id} not found in due cards")

        front_str = str(target["front_text"] or "").strip()
        target_ans = str(target["back_text"] or "").strip()

        candidates: List[CandidateDistractor] = []
        selected_relations: List[str] = []

        # 1) Query Tier R starter pack for explicit distractor relations (similar_shape, same_radical, homophone)
        conn = sqlite3.connect(f"file:{self.starter_pack_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            headword_guess = front_str.split("]")[-1].strip() if "]" in front_str else front_str
            entry_row = conn.execute(
                "SELECT entry_key, entry_type, facet_json FROM ref_entries WHERE headword = ? LIMIT 1",
                (headword_guess,),
            ).fetchone()
            is_hanja = (
                (entry_row is not None and str(entry_row["entry_type"]) == "hanja_char")
                or front_str.startswith("[한자")
            )
            q_facet = QuestionFacet.HANJA_CHAR if is_hanja else QuestionFacet.WORD_MEANING
            if entry_row is not None:
                rel_rows = conn.execute(
                    """
                    SELECT r.to_key AS distractor_key, r.rel_type AS relation, r.weight, e.headword, e.gloss_ko, e.facet_json
                    FROM ref_relations r
                    JOIN ref_entries e ON e.entry_key = r.to_key
                    WHERE r.from_key = ?
                    ORDER BY r.weight DESC, r.to_key ASC
                    """,
                    (str(entry_row["entry_key"]),),
                ).fetchall()
                for rrow in rel_rows:
                    f_data = json.loads(str(rrow["facet_json"] or "{}"))
                    if is_hanja and "hun" in f_data and "eum" in f_data:
                        opt_txt = f"{f_data['hun']} {'/'.join(f_data['eum'])} (부수: {f_data.get('radical', '')}, 총 {f_data.get('strokes', '')}획)"
                    else:
                        opt_txt = str(rrow["gloss_ko"])
                    rel_name = str(rrow["relation"])
                    selected_relations.append(rel_name)
                    candidates.append(
                        CandidateDistractor(
                            key=str(rrow["distractor_key"]),
                            option_text=opt_txt,
                            answer_set=frozenset({opt_txt, str(rrow["gloss_ko"])}),
                            relations=frozenset({rel_name}),
                            source_priority=1,
                        )
                    )

            # 2) Add other due cards in the workspace
            for other in due:
                if int(other["card_id"]) == int(card_id):
                    continue
                other_ans = str(other["back_text"] or "").strip()
                if not other_ans:
                    continue
                candidates.append(
                    CandidateDistractor(
                        key=f"card:{other['card_id']}",
                        option_text=other_ans,
                        answer_set=frozenset({other_ans}),
                        relations=frozenset({"same_radical"} if is_hanja else {"same_pos_level"}),
                        source_priority=2,
                    )
                )

            # 3) Supplement from Tier R entries of the same entry_type so even 1-card decks get 3 distractors
            target_etype = str(entry_row["entry_type"]) if entry_row is not None else ("hanja_char" if is_hanja else "vocab")
            fallback_rows = conn.execute(
                "SELECT entry_key, gloss_ko, facet_json FROM ref_entries WHERE entry_type = ? ORDER BY difficulty_rank ASC LIMIT 12",
                (target_etype,),
            ).fetchall()
            for frow in fallback_rows:
                f_data = json.loads(str(frow["facet_json"] or "{}"))
                if is_hanja and "hun" in f_data and "eum" in f_data:
                    opt_txt = f"{f_data['hun']} {'/'.join(f_data['eum'])} (부수: {f_data.get('radical', '')}, 총 {f_data.get('strokes', '')}획)"
                else:
                    opt_txt = str(frow["gloss_ko"])
                candidates.append(
                    CandidateDistractor(
                        key=f"pack:{frow['entry_key']}",
                        option_text=opt_txt,
                        answer_set=frozenset({opt_txt, str(frow["gloss_ko"])}),
                        relations=frozenset({"same_radical"} if is_hanja else {"same_pos_level"}),
                        source_priority=3,
                    )
                )
        finally:
            conn.close()

        sel = select_distractors(
            question_facet=q_facet,
            target_option_text=target_ans,
            target_answer_set=frozenset({target_ans}),
            candidates=candidates,
            required_count=3,
        )
        tap_blocks = build_tap_blocks(target_ans)
        mode = sel.fallback_mode or "multiple_choice"
        options = [target_ans] + [d.option_text for d in sel.distractors] if mode == "multiple_choice" else [target_ans]
        return {
            "ok": True,
            "card_id": int(card_id),
            "question": str(target["rendered_question"]),
            "target_answer": target_ans,
            "question_facet": q_facet.value,
            "mode": mode,
            "options": options,
            "distractor_relations_used": sorted(set(selected_relations)),
            "tap_blocks": list(tap_blocks),
            "age_tier": age_tier,
        }


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

            if path == "/api/catalog":
                self._send_json(svc.get_curriculum_catalog())
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
            elif target.suffix == ".json":
                mime = "application/manifest+json; charset=utf-8"

            raw_bytes = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw_bytes)))
            self.end_headers()
            self.wfile.write(raw_bytes)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/api/ai/ingest-document":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_DOCUMENT_BYTES:
                    self._send_json(
                        {
                            "ok": False,
                            "status": "BLOCKED",
                            "error_code": "too_large",
                            "deck_id": None,
                            "cards": [],
                        },
                        status=413,
                    )
                    return
                raw_bytes = self.rfile.read(length) if length > 0 else b""
                mime = self.headers.get("Content-Type") or "application/octet-stream"
                deck_name = qs.get("deck_name", [None])[0]
                max_cards = int(qs.get("max_cards", ["30"])[0] or 30)
                auto_save = qs.get("auto_save", ["0"])[0] in ("1", "true", "True")
                allow_cloud = qs.get("allow_cloud_vision", ["0"])[0] in ("1", "true", "True")

                res = svc.ingest_document(
                    data=raw_bytes,
                    mime=mime,
                    deck_name=deck_name,
                    max_cards=max_cards,
                    auto_save=auto_save,
                    allow_cloud_vision=allow_cloud,
                )
                http_code = 200 if res.get("status") == "OK" else 422
                self._send_json(res, status=http_code)
                return

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

                if path == "/api/decks/batch-save":
                    res = svc.save_deck_batch(
                        deck_name=str(body.get("deck_name") or ""),
                        cards=list(body.get("cards") or []),
                        category=str(body.get("category") or "general"),
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

                if path == "/api/catalog/generate-collection-deck":
                    res = svc.generate_collection_deck(
                        collection_id=str(body.get("collection_id") or ""),
                        limit=int(body.get("limit") or 25),
                        deck_name=str(body.get("deck_name") or "") or None,
                    )
                    self._send_json(res)
                    return

                if path == "/api/catalog/generate-exam-scope-deck":
                    p_start = int(body["page_start"]) if body.get("page_start") not in (None, "") else None
                    p_end = int(body["page_end"]) if body.get("page_end") not in (None, "") else None
                    res = svc.generate_exam_scope_deck(
                        textbook_id=str(body.get("textbook_id") or ""),
                        unit_ids=[str(u) for u in (body.get("unit_ids") or [])],
                        page_start=p_start,
                        page_end=p_end,
                        max_importance_tier=int(body.get("max_importance_tier") or 2),
                        deck_name=str(body.get("deck_name") or "") or None,
                    )
                    self._send_json(res)
                    return

                if path == "/api/quiz/interactive-options":
                    res = svc.build_interactive_quiz(
                        card_id=int(body["card_id"]),
                        age_tier=str(body.get("age_tier") or "teen"),
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

