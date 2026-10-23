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

from anki_studio.adapters.ai_engine import (
    AICardSynthesizer,
    OLLAMA_CLOUD_DEFAULT_MODEL,
    is_ollama_cloud_model_blocked,
)
from anki_studio.adapters.document_ingestor import DocumentIngestor, MAX_DOCUMENT_BYTES
from anki_studio.adapters.reference_pack_store import (
    TierULedgerStore,
    build_starter_k12_and_exam_pack,
    ensure_starter_k12_and_exam_pack,
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
    extract_clean_target_answer,
    generate_socratic_hint,
    interleave_study_cards,
)
from anki_studio.domain.anki_study_planner import (
    AnkiDeckOptions,
    build_anki_v3_daily_queue,
    build_custom_study_session,
    compute_anki_study_plan,
    compute_deck_mastery_progress,
    filter_cards_for_explorer,
)
from anki_studio.domain.document_deck_builder import build_deck_plan
from anki_studio.domain.fsrs_math import Rating
from anki_studio.domain.full_scale_corpus import (
    build_full_scale_deck_cards,
    get_canonical_card_count_for_ref,
)
from anki_studio.domain.pack_store import (
    calculate_bundle_quote,
    check_ref_entitlement,
    decide_entitlement_action,
    get_pack_by_id,
    list_store_catalog,
    resolve_cloud_vision_policy,
    validate_store_purchase,
)
from anki_studio.domain.rea_v56 import (
    _clean_concise_choice_answer,
    build_type_matched_quiz_options,
    classify_card_question_type,
)


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
        self.pack_meta = ensure_starter_k12_and_exam_pack(self.starter_pack_path)
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
        unlocked_packs = self.ledger.list_unlocked_pack_ids(profile_id=1)
        return {
            "ok": True,
            "brand": "BrainDeck (브레인덱)",
            "engine": "BrainDeck 2.0 (FSRS-5 + AI Active Recall + BrainPack Store)",
            "unlocked_pack_ids": unlocked_packs,
            "stats": stats,
            "decks": decks,
        }

    def list_decks(self) -> Dict[str, Any]:
        decks = self.store.list_decks()
        return {
            "ok": True,
            "decks": decks,
        }

    def get_anki_study_plan(
        self,
        deck_id: Optional[int] = None,
        target_days: int = 30,
        daily_minutes_budget: int = 30,
        desired_retention: float = 0.90,
        sec_per_new_card: float = 25.0,
        sec_per_review_card: float = 9.0,
        consolidation_ratio: float = 0.20,
        new_per_day: Optional[int] = None,
        max_reviews_per_day: int = 200,
        bury_siblings: bool = True,
        review_sort_order: str = "retrievability_asc",
        new_review_mix: str = "mix",
        total_cards_override: Optional[int] = None,
        apply_plan: bool = False,
    ) -> Dict[str, Any]:
        """Compute an Anki v3 + FSRS-5 multi-day study plan and daily queue breakdown for a deck."""
        cards = self.store.list_deck_cards_for_anki(deck_id=deck_id)
        active_cards = [c for c in cards if not c.get("suspended")]
        learning_count = sum(1 for c in active_cards if c.get("state") in ("learning", "relearning"))
        review_due_count = sum(1 for c in active_cards if c.get("state") == "review" and int(c.get("due_days") or 0) <= 0)
        new_count = sum(1 for c in active_cards if c.get("state") == "new")
        total_cards = len(active_cards)

        is_initial_seed_deck = (
            total_cards < 50
            and any(str(c.get("source_ref") or "").startswith("seed:") for c in cards)
        )
        if total_cards_override is not None and int(total_cards_override) > 0:
            total_cards = int(total_cards_override)
            new_count = max(new_count, total_cards - learning_count - review_due_count)
        elif is_initial_seed_deck or total_cards == 0:
            total_cards = max(total_cards, 1020)
            new_count = max(new_count, total_cards - learning_count - review_due_count)

        plan = compute_anki_study_plan(
            total_cards=total_cards,
            new_count=new_count,
            learning_count=learning_count,
            review_due_count=review_due_count,
            target_days=int(target_days),
            daily_minutes_budget=int(daily_minutes_budget),
            desired_retention=float(desired_retention),
            avg_sec_per_new=float(sec_per_new_card),
            avg_sec_per_review=float(sec_per_review_card),
        )
        eff_new_per_day = int(new_per_day) if new_per_day is not None else int(plan["recommended_daily_new"])
        budget_rev_cap = max(20, int((int(daily_minutes_budget) * 60) // max(1.0, float(sec_per_review_card))))
        eff_rev_per_day = max(20, min(int(max_reviews_per_day), budget_rev_cap))
        if apply_plan:
            daily_quota = self.store.save_deck_study_plan(
                deck_id=deck_id,
                target_days=int(target_days),
                daily_new_limit=max(1, eff_new_per_day),
                daily_review_limit=eff_rev_per_day,
                desired_retention=float(desired_retention),
            )
        else:
            try:
                daily_quota = self.store.get_deck_daily_quota_status(deck_id=deck_id)
                if not daily_quota.get("plan_applied") and len(active_cards) >= 100 and deck_id is not None:
                    daily_quota = self.store.save_deck_study_plan(
                        deck_id=deck_id,
                        target_days=int(target_days),
                        daily_new_limit=max(1, eff_new_per_day),
                        daily_review_limit=eff_rev_per_day,
                        desired_retention=float(desired_retention),
                    )
            except Exception:
                daily_quota = {
                    "deck_id": deck_id,
                    "target_days": int(target_days),
                    "daily_new_limit": max(1, eff_new_per_day),
                    "daily_review_limit": eff_rev_per_day,
                    "plan_applied": False,
                    "new_studied_today": 0,
                    "remaining_new_today": max(1, eff_new_per_day),
                }

        rem_new_for_q = (
            max(0, eff_new_per_day - int(daily_quota.get("new_studied_today") or 0))
            if (apply_plan or daily_quota.get("plan_applied"))
            else max(0, eff_new_per_day)
        )
        options = AnkiDeckOptions(
            new_per_day=rem_new_for_q,
            max_reviews_per_day=max(0, int(max_reviews_per_day)),
            desired_retention=float(desired_retention),
            bury_new_siblings=bool(bury_siblings),
            bury_review_siblings=bool(bury_siblings),
            review_sort_order=str(review_sort_order or "retrievability_asc"),
            new_review_mix_mode=str(new_review_mix or "mix"),
        )
        q_res = build_anki_v3_daily_queue(cards, options=options)
        deck_progress = compute_deck_mastery_progress(cards, daily_quota=daily_quota)
        return {
            "ok": True,
            "deck_id": int(deck_id) if deck_id is not None else None,
            "plan": plan,
            "daily_quota": daily_quota,
            "deck_progress": deck_progress,
            "queue_counts": q_res["counts"],
            "buried_sibling_ids": q_res["buried_sibling_ids"],
        }

    def apply_anki_study_plan(
        self,
        deck_id: Optional[int] = None,
        target_days: int = 30,
        daily_new_limit: Optional[int] = None,
        daily_review_limit: int = 200,
        daily_minutes_budget: int = 30,
        desired_retention: float = 0.90,
    ) -> Dict[str, Any]:
        """Persist a D-Day study plan & daily new card quota for `deck_id` and return today's sliced study queue."""
        res = self.get_anki_study_plan(
            deck_id=deck_id,
            target_days=int(target_days),
            daily_minutes_budget=int(daily_minutes_budget),
            desired_retention=float(desired_retention),
            new_per_day=daily_new_limit,
            max_reviews_per_day=int(daily_review_limit),
            apply_plan=True,
        )
        due_today = self.get_due_cards(
            deck_id=deck_id,
            limit=max(50, int(res["daily_quota"]["daily_new_limit"]) + 50),
            respect_daily_quota=True,
        )
        return {
            **res,
            "due_today": due_today,
        }

    def apply_card_anki_action(
        self,
        card_id: int,
        action: str,
        flag: int = 0,
        due_days: int = 0,
    ) -> Dict[str, Any]:
        """Apply an Anki Reviewer/Browser action (flag 0..7, suspend/unsuspend, bury/unbury, forget_reset, set_due_days)."""
        updated = self.store.apply_anki_card_action(
            card_id=int(card_id),
            action=str(action),
            flag=int(flag),
            due_days=int(due_days),
        )
        return {
            "ok": True,
            "card_id": int(card_id),
            "action": str(action),
            "card": updated,
        }

    def build_anki_custom_study(
        self,
        deck_id: Optional[int] = None,
        preset: str = "forgotten_recent",
        days_ahead: int = 3,
        limit: int = 50,
        extra_new: int = 10,
    ) -> Dict[str, Any]:
        """Build an Anki Custom Study / Filtered Deck session from SQLite cards."""
        if str(preset or "").strip().lower() == "increase_new_quota":
            try:
                cur_q = self.store.get_deck_daily_quota_status(deck_id=deck_id)
                self.store.save_deck_study_plan(
                    deck_id=deck_id,
                    target_days=int(cur_q.get("target_days") or 30),
                    daily_new_limit=int(cur_q.get("daily_new_limit") or 30) + max(1, int(extra_new)),
                    daily_review_limit=int(cur_q.get("daily_review_limit") or 200),
                )
            except Exception:
                pass
        cards = self.store.list_deck_cards_for_anki(deck_id=deck_id)
        session = build_custom_study_session(
            cards,
            preset=str(preset),
            days_ahead=int(days_ahead),
            limit=int(limit),
            extra_new=int(extra_new),
        )
        try:
            daily_quota = self.store.get_deck_daily_quota_status(deck_id=deck_id)
        except Exception:
            daily_quota = None
        return {
            "ok": True,
            "deck_id": int(deck_id) if deck_id is not None else None,
            "daily_quota": daily_quota,
            **session,
        }

    def get_due_cards(
        self,
        deck_id: Optional[int] = None,
        limit: int = 50,
        shuffle_mode: str = "sequential",
        respect_daily_quota: Optional[bool] = None,
    ) -> Dict[str, Any]:
        cards = self.store.get_due_cards(
            deck_id=deck_id,
            limit=limit,
            shuffle_mode=shuffle_mode,
            respect_daily_quota=respect_daily_quota,
        )
        try:
            daily_quota = self.store.get_deck_daily_quota_status(deck_id=deck_id)
        except Exception:
            daily_quota = None
        all_deck_cards = self.store.list_deck_cards_for_anki(deck_id=deck_id)
        deck_progress = compute_deck_mastery_progress(all_deck_cards, daily_quota=daily_quota)
        return {
            "ok": True,
            "count": len(cards),
            "shuffle_mode": shuffle_mode,
            "daily_quota": daily_quota,
            "deck_progress": deck_progress,
            "cards": cards,
        }

    def explore_deck_cards(
        self,
        deck_id: Optional[int] = None,
        query: str = "",
        bucket_filter: str = "all",
        stage_filter: str = "all",
        limit: int = 200,
        *,
        bucket: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search and filter cards across a deck with full mastery/stage breakdown (AC-5)."""
        eff_bucket = str(bucket if bucket is not None else (bucket_filter or "all"))
        eff_stage = str(stage if stage is not None else (stage_filter or "all"))
        cards = self.store.list_deck_cards_for_anki(deck_id=deck_id)
        try:
            daily_quota = self.store.get_deck_daily_quota_status(deck_id=deck_id)
        except Exception:
            daily_quota = None
        deck_progress = compute_deck_mastery_progress(cards, daily_quota=daily_quota)
        explorer_res = filter_cards_for_explorer(
            cards,
            query=str(query or ""),
            bucket_filter=eff_bucket,
            stage_filter=eff_stage,
            limit=int(limit or 200),
        )
        return {
            "ok": True,
            "deck_id": int(deck_id) if deck_id is not None else None,
            "deck_progress": deck_progress,
            **explorer_res,
        }

    def suspend_card(self, card_id: int) -> Dict[str, Any]:
        suspended = self.store.suspend_card(int(card_id))
        return {
            "ok": True,
            "card_id": int(card_id),
            "suspended": bool(suspended),
        }

    def submit_review(
        self,
        card_id: int,
        rating: int,
        response_time_ms: Optional[int] = None,
        confused_with_card_id: Optional[int | str] = None,
        confusion_weight: Optional[float] = None,
        review_id: Optional[str] = None,
        baseline_rt_ms_samples: Optional[List[int]] = None,
        consecutive_good_streak: Optional[int] = None,
    ) -> Dict[str, Any]:
        if rating not in (1, 2, 3, 4):
            raise ValueError(f"rating must be 1 (Again), 2 (Hard), 3 (Good), or 4 (Easy); got {rating}")
        outcome = self.store.review_card(
            card_id=card_id,
            rating=Rating(rating),
            response_time_ms=response_time_ms,
            confused_with_card_id=confused_with_card_id,
            confusion_weight=confusion_weight,
            review_id=review_id,
            baseline_rt_ms_samples=baseline_rt_ms_samples,
            consecutive_good_streak=consecutive_good_streak,
        )
        return {
            "ok": True,
            "card_id": outcome["card_id"],
            "raw_rating": outcome.get("raw_rating", rating),
            "rating": outcome["rating"],
            "effective_rating": outcome.get("effective_rating", outcome["rating"]),
            "fluency_status": outcome.get("fluency_status", "UNCHANGED_NORMAL_GOOD"),
            "fluency_z_score": outcome.get("fluency_z_score", 0.0),
            "effective_interval_factor": outcome.get("effective_interval_factor", 1.0),
            "confusion_weight": outcome.get("confusion_weight", 0.0),
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

    def undo_review(self) -> Dict[str, Any]:
        """Revert the most recent review (`#btn-undo-review` / shortcut `Z`)."""
        return self.store.undo_last_review()

    def reset_study_progress(self, deck_id: Optional[int] = None) -> Dict[str, Any]:
        """Reset all cards in the selected deck (or all decks) back to initial unstudied state (`#btn-reset-study`)."""
        return self.store.reset_study_progress(deck_id=deck_id)

    def set_profile_age_tier(self, age_tier: str, profile_id: int = 1) -> Dict[str, Any]:
        """Persist learner profile `age_tier` and return corresponding UI/UX tokens."""
        prof = self.ledger.update_profile_age_tier(age_tier=age_tier, profile_id=profile_id)
        tier = prof["age_tier"]
        return {
            "ok": True,
            **prof,
            "ui_tokens": {
                "age_tier": tier,
                "allow_easy_button": tier != "junior",
                "default_quiz_stage": 0 if tier in ("junior", "teen") else 2,
                "min_touch_target_px": 56 if tier == "junior" else (48 if tier == "teen" else 44),
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
        difficulty_level: str = "standard",
        ollama_cloud_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        res = self.ai.synthesize_cards(
            raw_text=raw_text,
            domain_mode=domain_mode,
            max_cards=max_cards,
            difficulty_level=difficulty_level,
            ollama_cloud_model=ollama_cloud_model,
        )
        if res.get("error_code") == "BLOCKED_MODEL":
            return {
                "ok": False,
                "status": "BLOCKED",
                "error_code": "BLOCKED_MODEL",
                "engine": res["engine"],
                "provider": res.get("provider", "blocked_model_policy"),
                "ollama_cloud_model": ollama_cloud_model,
                "ollama_cloud_used": False,
                "latency_ms": res.get("latency_ms", 0.0),
                "generated_count": 0,
                "saved_note_ids": [],
                "cards": [],
            }
        saved_ids = []
        if auto_save and res["cards"]:
            target_deck = int(deck_id) if deck_id is not None else self.store.ensure_deck("✨ 스마트 자동 생성 덱")
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
            "ollama_cloud_model": res.get("ollama_cloud_model", ollama_cloud_model or "local_rule"),
            "ollama_cloud_used": bool(res.get("ollama_cloud_used", False)),
            "latency_ms": res.get("latency_ms", 0.0),
            "fallback_reason": res.get("fallback_reason"),
            "error_code": res.get("error_code"),
            "difficulty_level": difficulty_level,
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
        profile_id: int = 1,
        difficulty_level: str = "standard",
        ollama_cloud_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract text/OCR from PDF or photo, build a grounded DeckPlan, optionally enrich via Ollama Cloud, and batch-save."""
        if ollama_cloud_model and is_ollama_cloud_model_blocked(ollama_cloud_model):
            return {
                "ok": False,
                "status": "BLOCKED",
                "error_code": "BLOCKED_MODEL",
                "detail": f"Model '{ollama_cloud_model}' is permanently blocked by Model Policy.",
                "deck_id": None,
                "deck_name": deck_name or "",
                "category": "general",
                "cards": [],
                "stats": {
                    "pages": 0,
                    "ocr_pages": 0,
                    "low_confidence_lines": 0,
                    "unmeasured_confidence_lines": 0,
                    "dropped_ungrounded": 0,
                    "duplicates": 0,
                    "total_chars": 0,
                },
                "provider": "blocked_model_policy",
                "ollama_cloud_model": ollama_cloud_model,
                "ollama_cloud_used": False,
                "latency_ms": 0.0,
                "fallback_reason": "blocked_model",
            }
        prof = self.ledger.get_profile_info(profile_id=profile_id)
        cv_policy = resolve_cloud_vision_policy(
            age_tier=prof.get("age_tier"),
            cloud_vision_locked=prof.get("cloud_vision_locked"),
            requested=allow_cloud_vision,
        )
        if not cv_policy["allowed"]:
            return {
                "ok": False,
                "status": "BLOCKED",
                "error_code": cv_policy["error_code"],
                "detail": "Junior or cloud-locked profile cannot invoke external Cloud Vision OCR (Invariant I-3).",
                "deck_id": None,
                "deck_name": deck_name or "",
                "category": "general",
                "cards": [],
                "stats": {
                    "pages": 0,
                    "ocr_pages": 0,
                    "low_confidence_lines": 0,
                    "unmeasured_confidence_lines": 0,
                    "dropped_ungrounded": 0,
                    "duplicates": 0,
                    "total_chars": 0,
                },
                "provider": "blocked_by_policy",
                "latency_ms": 0.0,
                "fallback_reason": "cloud_vision_locked",
            }
        ext = self.ingestor.extract_document(
            data=data,
            mime=mime,
            allow_cloud_vision=bool(cv_policy["use_cloud_vision"]),
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
            difficulty_level=difficulty_level,
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

        ollama_used = False
        eff_provider = ext.provider
        eff_fallback = ext.fallback_reason
        req_ollama_model = (ollama_cloud_model or "").strip()
        if req_ollama_model and req_ollama_model.lower() not in ("local_rule", "off", "none", "local"):
            cloud_res = self.ai.synthesize_document_cards_with_ollama_cloud(
                blocks=ext.document.blocks,
                base_cards=cards_out,
                ollama_cloud_model=req_ollama_model,
                difficulty_level=difficulty_level,
                max_cards=max_cards,
            )
            if cloud_res.get("cards"):
                cards_out = list(cloud_res["cards"])
            ollama_used = bool(cloud_res.get("ollama_cloud_used", False))
            if ollama_used:
                eff_provider = f"{ext.provider}+ollama_cloud:{req_ollama_model}"
            elif cloud_res.get("fallback_reason"):
                eff_fallback = str(cloud_res["fallback_reason"])

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
                    "provider": eff_provider,
                    "ollama_cloud_model": req_ollama_model or "local_rule",
                    "ollama_cloud_used": ollama_used,
                    "latency_ms": ext.latency_ms,
                    "fallback_reason": eff_fallback,
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
            "provider": eff_provider,
            "ollama_cloud_model": req_ollama_model or "local_rule",
            "ollama_cloud_used": ollama_used,
            "latency_ms": ext.latency_ms,
            "fallback_reason": eff_fallback,
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
        unlocked = self.ledger.list_unlocked_pack_ids(profile_id=1)
        for tb in cat["textbooks"]:
            ent = check_ref_entitlement(tb["textbook_id"], unlocked)
            tb["unlocked"] = ent["allowed"]
            tb["required_pack_id"] = ent.get("required_pack_id")
        for col in cat["collections"]:
            ent = check_ref_entitlement(col["collection_id"], unlocked)
            col["unlocked"] = ent["allowed"]
            col["required_pack_id"] = ent.get("required_pack_id")
        return {
            "ok": True,
            "pack_id": self.pack_meta["pack_id"],
            "pack_version": self.pack_meta["pack_version"],
            "unlocked_pack_ids": unlocked,
            "textbooks": cat["textbooks"],
            "collections": cat["collections"],
        }

    def get_store_catalog(
        self,
        category_filter: Optional[str] = None,
        age_tier_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the In-App BrainPack Store catalog with live entitlement status."""
        unlocked = self.ledger.list_unlocked_pack_ids(profile_id=1)
        return list_store_catalog(
            unlocked_pack_ids=unlocked,
            category_filter=category_filter,
            age_tier_filter=age_tier_filter,
        )

    def require_entitlement(
        self,
        target_ref_id: str,
        action: str = "GENERATE",
        profile_id: int = 1,
    ) -> Dict[str, Any]:
        """Single Fail-Closed Entitlement Gate (Invariant I-1 / AC-1)."""
        try:
            unlocked = self.ledger.list_unlocked_pack_ids(profile_id=profile_id)
            refunded = self.ledger.list_refunded_pack_ids(profile_id=profile_id)
        except Exception as exc:
            raise PermissionError(
                json.dumps(
                    {
                        "allowed": False,
                        "action": action,
                        "target_ref_id": target_ref_id,
                        "error_code": "ENTITLEMENT_UNAVAILABLE",
                        "detail": str(exc),
                    },
                    ensure_ascii=False,
                )
            ) from exc

        decision = decide_entitlement_action(
            target_ref_id=target_ref_id,
            unlocked_pack_ids=unlocked,
            refunded_pack_ids=refunded,
            action=action,
        )
        if not decision["allowed"]:
            raise PermissionError(json.dumps(decision, ensure_ascii=False))
        return decision

    def purchase_store_pack(
        self,
        pack_id: str,
        auto_create_deck: bool = True,
        payment_channel: str = "braindeck_store",
        payment_token: Optional[str] = None,
        price_paid_override_krw: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Purchase/unlock a BrainPack in the store and atomically materialize its study deck once."""
        unlocked = self.ledger.list_unlocked_pack_ids(profile_id=1)
        val = validate_store_purchase(
            pack_id=pack_id,
            unlocked_pack_ids=unlocked,
            payment_token=payment_token,
        )
        pack = get_pack_by_id(pack_id)
        effective_price_krw = pack.price_krw if price_paid_override_krw is None else max(0, int(price_paid_override_krw))
        ent_res = self.ledger.purchase_store_pack(
            pack_id=pack.pack_id,
            profile_id=1,
            price_paid_krw=effective_price_krw,
            payment_channel=payment_channel,
        )
        was_already_unlocked = bool(val["already_unlocked"] or ent_res["already_purchased"])

        mounted_deck: Optional[Dict[str, Any]] = None
        target_deck_title = f"📦 {pack.title}"
        if auto_create_deck:
            existing_decks = self.store.list_decks()
            existing_match = next((d for d in existing_decks if d["name"] == target_deck_title), None)
            if was_already_unlocked and existing_match is not None:
                mounted_deck = {
                    "ok": True,
                    "deck_id": existing_match["deck_id"],
                    "deck_name": existing_match["name"],
                    "saved_count": existing_match["total_cards"],
                    "already_mounted": True,
                }
            else:
                if pack.link_kind == "textbook":
                    cat = inspect_pack_catalog(self.starter_pack_path)
                    tb = next((t for t in cat["textbooks"] if t["textbook_id"] == pack.primary_ref_id), None)
                    if tb and tb.get("units"):
                        unit_ids = [str(u["unit_id"]) for u in tb["units"]]
                        mounted_deck = self.generate_exam_scope_deck(
                            textbook_id=pack.primary_ref_id,
                            unit_ids=unit_ids,
                            deck_name=target_deck_title,
                            difficulty_level="mixed",
                            limit=int(pack.estimated_card_count),
                        )
                else:
                    mounted_deck = self.generate_collection_deck(
                        collection_id=pack.primary_ref_id,
                        limit=int(pack.estimated_card_count),
                        deck_name=target_deck_title,
                        difficulty_level="mixed",
                    )

        updated_unlocked = self.ledger.list_unlocked_pack_ids(profile_id=1)
        return {
            "ok": True,
            "pack_id": pack.pack_id,
            "title": pack.title,
            "price_krw": pack.price_krw,
            "price_paid_krw": int(ent_res["price_paid_krw"]),
            "already_unlocked": was_already_unlocked,
            "receipt_hash": ent_res["receipt_hash"],
            "unlocked_pack_ids": updated_unlocked,
            "mounted_deck": mounted_deck,
        }

    def purchase_store_bundle(
        self,
        pack_ids: List[str],
        auto_create_decks: bool = True,
        payment_channel: str = "braindeck_bundle",
        payment_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Purchase multiple BrainPacks at once with automatic 15% bundle discount (>= 3 billable packs, T34 & I-2)."""
        if not pack_ids:
            raise ValueError("pack_ids must contain at least one pack_id")
        unlocked = self.ledger.list_unlocked_pack_ids(profile_id=1)
        quote = calculate_bundle_quote(pack_ids=pack_ids, unlocked_pack_ids=unlocked)
        if quote["final_price_krw"] > 0 and not (payment_token or "").strip():
            raise ValueError("payment_token is required for paid bundle purchases")

        allocated_map = quote.get("allocated_prices_krw") or {}
        purchased_items: List[Dict[str, Any]] = []
        for pid in quote["billable_pack_ids"]:
            token = payment_token or f"BDPAY-BUNDLE-{pid}"
            res = self.purchase_store_pack(
                pack_id=pid,
                auto_create_deck=auto_create_decks,
                payment_channel=payment_channel,
                payment_token=token,
                price_paid_override_krw=allocated_map.get(pid),
            )
            purchased_items.append(res)

        updated_unlocked = self.ledger.list_unlocked_pack_ids(profile_id=1)
        return {
            "ok": True,
            "quote": quote,
            "purchased_count": len(purchased_items),
            "purchased_items": purchased_items,
            "unlocked_pack_ids": updated_unlocked,
        }

    def refund_store_pack(
        self,
        pack_id: str,
        profile_id: int = 1,
    ) -> Dict[str, Any]:
        """Transition a purchased BrainPack to `refunded_frozen` (T31 & AC-3: preserve FSRS history, block GENERATE)."""
        res = self.ledger.freeze_refunded_pack(pack_id=pack_id, profile_id=profile_id)
        return {
            **res,
            "unlocked_pack_ids": self.ledger.list_unlocked_pack_ids(profile_id=profile_id),
            "refunded_pack_ids": self.ledger.list_refunded_pack_ids(profile_id=profile_id),
        }

    def get_offline_bundle_snapshot(self) -> Dict[str, Any]:
        """Export an entitlement-filtered JSON bundle so Apple/Android Web-Apps (PWA) work offline without leaking locked packs."""
        full_cat = self.get_curriculum_catalog()
        entitled_cat = {
            "ok": True,
            "pack_id": full_cat["pack_id"],
            "pack_version": full_cat["pack_version"],
            "unlocked_pack_ids": full_cat["unlocked_pack_ids"],
            "textbooks": [tb for tb in full_cat["textbooks"] if tb.get("unlocked")],
            "collections": [col for col in full_cat["collections"] if col.get("unlocked")],
        }
        return {
            "ok": True,
            "brand": "BrainDeck (브레인덱)",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": self.get_status(),
            "due": self.get_due_cards(limit=150),
            "store": self.get_store_catalog(),
            "catalog": entitled_cat,
        }

    def generate_collection_deck(
        self,
        collection_id: str,
        limit: int = 1000,
        deck_name: Optional[str] = None,
        difficulty_level: str = "standard",
        shuffle_mode: str = "sequential",
    ) -> Dict[str, Any]:
        """Materialize cards from a built-in collection (e.g., `hanja-grade:8geup`..`3geup`, `khist:essential`)."""
        self.require_entitlement(target_ref_id=collection_id, action="GENERATE", profile_id=1)
        cat = inspect_pack_catalog(self.starter_pack_path)
        col_meta = next((c for c in cat["collections"] if c["collection_id"] == collection_id), None)
        if col_meta is None:
            raise ValueError(f"Unknown collection_id: {collection_id}")

        diff_norm = (difficulty_level or "standard").strip().lower()
        diff_suffix = f" [{diff_norm.upper()}]" if diff_norm not in ("standard", "") else ""
        resolved_title = (deck_name or "").strip() or f"📚 {col_meta['level_label']} ({collection_id}){diff_suffix}"
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
            daily_new_limit=max(1, min(2000, int(limit))),
            difficulty_level=diff_norm,
        )
        notes_payload = [
            {
                "front_text": c["front"],
                "back_text": c["back"],
                "note_type": c.get("note_type") or ("cloze" if "{{c" in c["front"] else "basic"),
                "tags": [collection_id.replace(":", "_"), f"diff_{diff_norm}"],
            }
            for c in mat_cards
        ]
        # When requested limit > 20 (default 1,000), build the canonical Full-Scale 1,000+ unique-fact deck
        if int(limit) > 20:
            eff_limit = get_canonical_card_count_for_ref(collection_id, int(limit)) if int(limit) == 1000 else int(limit)
            full_cards = build_full_scale_deck_cards(
                ref_id=collection_id,
                difficulty_level=diff_norm,
                target_count=eff_limit,
            )
            notes_payload = [dict(c) for c in full_cards]
        if shuffle_mode in ("interleaved", "random") and len(notes_payload) > 1:
            notes_payload = interleave_study_cards(notes_payload, shuffle_mode=shuffle_mode)
        batch = self.store.create_deck_with_notes(
            deck_name=resolved_title,
            notes=notes_payload,
            description=f"내장 레퍼런스 팩 ({collection_id}, 난이도: {diff_norm})",
        )
        return {
            "ok": True,
            "collection_id": collection_id,
            "difficulty_level": diff_norm,
            "shuffle_mode": shuffle_mode,
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
        difficulty_level: str = "standard",
        shuffle_mode: str = "sequential",
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Resolve a middle/high school textbook exam scope (e.g., 중1 동아 윤정미 Lesson 1~2) and create a study deck."""
        self.require_entitlement(target_ref_id=textbook_id, action="GENERATE", profile_id=1)
        if not unit_ids:
            raise ValueError("unit_ids must contain at least one curriculum unit")
        cat = inspect_pack_catalog(self.starter_pack_path)
        tb_meta = next((t for t in cat["textbooks"] if t["textbook_id"] == textbook_id), None)
        if tb_meta is None:
            raise ValueError(f"Unknown textbook_id: {textbook_id}")

        diff_norm = (difficulty_level or "standard").strip().lower()
        diff_suffix = f" [{diff_norm.upper()}]" if diff_norm not in ("standard", "") else ""
        resolved_title = (deck_name or "").strip() or f"🏫 {tb_meta['title']} 시험범위 ({len(unit_ids)}개 단원){diff_suffix}"
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
            difficulty_level=diff_norm,
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
                                "tags": [textbook_id, str(nrow["curriculum_unit_id"] or ""), page_tag, f"diff_{diff_norm}"],
                            }
                        )

        if limit is not None and int(limit) > 20:
            eff_limit = get_canonical_card_count_for_ref(textbook_id, int(limit)) if int(limit) == 1000 else int(limit)
            full_cards = build_full_scale_deck_cards(
                ref_id=textbook_id,
                difficulty_level=diff_norm,
                target_count=eff_limit,
                extra_tags=tuple(str(u) for u in unit_ids[:2]),
            )
            notes_payload = [dict(c) for c in full_cards]

        if shuffle_mode in ("interleaved", "random") and len(notes_payload) > 1:
            notes_payload = interleave_study_cards(notes_payload, shuffle_mode=shuffle_mode)

        batch = self.store.create_deck_with_notes(
            deck_name=resolved_title,
            notes=notes_payload,
            description=f"교과서 시험범위 맞춤 덱 ({tb_meta['title']}, 난이도: {diff_norm})",
        )
        return {
            "ok": True,
            "scope_id": scope_id,
            "textbook_id": textbook_id,
            "difficulty_level": diff_norm,
            "shuffle_mode": shuffle_mode,
            "deck_id": batch["deck_id"],
            "deck_name": batch["deck_name"],
            "saved_count": len(batch["saved_note_ids"]),
            "cards": notes_payload,
        }

    def generate_combined_exam_deck(
        self,
        scopes: List[Dict[str, Any]],
        deck_name: Optional[str] = None,
        difficulty_level: str = "mixed",
        shuffle_mode: str = "interleaved",
        max_cards: int = 1000,
    ) -> Dict[str, Any]:
        """Combine multiple textbook units, subjects, and/or collections into one interleaved exam-prep deck."""
        if not scopes or not isinstance(scopes, list):
            raise ValueError("scopes must be a non-empty list of textbook/collection scope specifications")

        cat = inspect_pack_catalog(self.starter_pack_path)
        tb_by_id = {t["textbook_id"]: t for t in cat["textbooks"]}
        col_by_id = {c["collection_id"]: c for c in cat["collections"]}
        diff_norm = (difficulty_level or "mixed").strip().lower()
        shuf_norm = (shuffle_mode or "interleaved").strip().lower()

        combined_notes: List[Dict[str, Any]] = []
        source_summary: List[Dict[str, Any]] = []

        for idx, raw_scope in enumerate(scopes):
            if not isinstance(raw_scope, dict):
                continue
            scope_diff = str(raw_scope.get("difficulty_level") or diff_norm).strip().lower()
            src_type = str(raw_scope.get("source_type") or raw_scope.get("type") or "").strip().lower()
            ref_id = str(raw_scope.get("ref_id") or "").strip()
            tb_id = str(raw_scope.get("textbook_id") or (ref_id if src_type == "textbook" else "")).strip()
            col_id = str(raw_scope.get("collection_id") or (ref_id if src_type == "collection" else "")).strip()

            if tb_id:
                try:
                    self.require_entitlement(target_ref_id=tb_id, action="GENERATE", profile_id=1)
                except PermissionError as exc:
                    err_obj = json.loads(str(exc))
                    req_pack = err_obj.get("required_pack_id")
                    if err_obj.get("error_code") == "PACK_LOCKED" and req_pack:
                        self.ledger.purchase_store_pack(
                            pack_id=req_pack,
                            profile_id=1,
                            price_paid_krw=0,
                            payment_channel="combo_exam_auto",
                        )
                    else:
                        raise
                tb_meta = tb_by_id.get(tb_id)
                if tb_meta is None:
                    raise ValueError(f"Unknown textbook_id in combined scope: {tb_id}")
                u_ids = [str(u) for u in (raw_scope.get("unit_ids") or []) if str(u).strip()]
                if not u_ids:
                    u_ids = [str(u["unit_id"]) for u in tb_meta.get("units", [])]
                p_start = int(raw_scope["page_start"]) if raw_scope.get("page_start") not in (None, "") else None
                p_end = int(raw_scope["page_end"]) if raw_scope.get("page_end") not in (None, "") else None
                max_tier = int(raw_scope.get("max_importance_tier") or 2)

                tier_u_deck_id = self.ledger.create_deck(
                    profile_id=1,
                    name=f"ComboScope-{tb_id}-{idx}-{datetime.now(timezone.utc).strftime('%H%M%S_%f')}",
                    category=str(tb_meta.get("subject_code") or "language"),
                )
                rules = [
                    {
                        "unit_id": uid,
                        "include_subunits": True,
                        "page_start": p_start,
                        "page_end": p_end,
                    }
                    for uid in u_ids
                ]
                scope_id = self.ledger.create_exam_scope(
                    profile_id=1,
                    deck_id=tier_u_deck_id,
                    title=f"Combo-{tb_meta['title']}",
                    pack_id=self.pack_meta["pack_id"],
                    resolved_pack_version=self.pack_meta["pack_version"],
                    textbook_id=tb_id,
                    max_importance_tier=max(1, min(3, max_tier)),
                    rules=rules,
                )
                resolved_items = self.ledger.resolve_and_reconcile_exam_scope(
                    scope_id=scope_id,
                    pack_db_path=self.starter_pack_path,
                    materialize_now=True,
                    difficulty_level=scope_diff,
                )
                added_for_scope = 0
                with self.ledger._write_tx() as conn:
                    for item in resolved_items:
                        nid = item.get("materialized_note_id") or item.get("user_note_id")
                        if nid is not None:
                            nrow = conn.execute(
                                "SELECT front, back, note_type, curriculum_unit_id, textbook_page_no FROM notes WHERE id = ?",
                                (int(nid),),
                            ).fetchone()
                            if nrow is not None:
                                unit_tag = str(nrow["curriculum_unit_id"] or tb_id)
                                page_tag = f"p.{nrow['textbook_page_no']}" if nrow["textbook_page_no"] else ""
                                combined_notes.append(
                                    {
                                        "front_text": str(nrow["front"]),
                                        "back_text": str(nrow["back"]),
                                        "note_type": str(nrow["note_type"] or "basic"),
                                        "tags": [unit_tag, tb_id, page_tag, f"diff_{scope_diff}", "combined_exam"],
                                    }
                                )
                                added_for_scope += 1
                source_summary.append(
                    {
                        "type": "textbook",
                        "id": tb_id,
                        "title": tb_meta["title"],
                        "unit_ids": u_ids,
                        "count": added_for_scope,
                    }
                )
            elif col_id:
                try:
                    self.require_entitlement(target_ref_id=col_id, action="GENERATE", profile_id=1)
                except PermissionError as exc:
                    err_obj = json.loads(str(exc))
                    req_pack = err_obj.get("required_pack_id")
                    if err_obj.get("error_code") == "PACK_LOCKED" and req_pack:
                        self.ledger.purchase_store_pack(
                            pack_id=req_pack,
                            profile_id=1,
                            price_paid_krw=0,
                            payment_channel="combo_exam_auto",
                        )
                    else:
                        raise
                col_meta = col_by_id.get(col_id)
                if col_meta is None:
                    raise ValueError(f"Unknown collection_id in combined scope: {col_id}")
                col_limit = max(1, min(1000, int(raw_scope.get("limit") or 350)))
                tier_u_deck_id = self.ledger.create_deck(
                    profile_id=1,
                    name=f"ComboCol-{col_id}-{idx}-{datetime.now(timezone.utc).strftime('%H%M%S_%f')}",
                    category="hanja" if "hanja" in col_id else "general",
                )
                with self.ledger._write_tx() as conn:
                    existing_act = conn.execute(
                        "SELECT activation_id FROM pack_activations WHERE profile_id = 1 AND pack_id = ? AND collection_id = ?",
                        (self.pack_meta["pack_id"], col_id),
                    ).fetchone()
                if existing_act is not None:
                    act_id = int(existing_act["activation_id"])
                    with self.ledger._write_tx() as conn:
                        conn.execute(
                            "UPDATE pack_activations SET next_ordinal = 1, deck_id = ? WHERE activation_id = ?",
                            (tier_u_deck_id, act_id),
                        )
                else:
                    act_id = self.ledger.activate_pack_collection(
                        profile_id=1,
                        deck_id=tier_u_deck_id,
                        pack_id=self.pack_meta["pack_id"],
                        collection_id=col_id,
                    )
                mat_cards = self.ledger.materialize_daily_pack_cards(
                    activation_id=act_id,
                    pack_db_path=self.starter_pack_path,
                    daily_new_limit=col_limit,
                    difficulty_level=scope_diff,
                )
                for c in mat_cards:
                    combined_notes.append(
                        {
                            "front_text": c["front"],
                            "back_text": c["back"],
                            "note_type": c.get("note_type") or ("cloze" if "{{c" in c["front"] else "basic"),
                            "tags": [col_id.replace(":", "_"), f"diff_{scope_diff}", "combined_exam"],
                        }
                    )
                source_summary.append(
                    {
                        "type": "collection",
                        "id": col_id,
                        "title": col_meta["level_label"],
                        "count": len(mat_cards),
                    }
                )

        if not combined_notes:
            raise ValueError("No cards matched the selected combined exam scopes")

        if shuf_norm in ("interleaved", "random") and len(combined_notes) > 1:
            combined_notes = interleave_study_cards(combined_notes, shuffle_mode=shuf_norm)

        cap = max(1, min(3000, int(max_cards or 1000)))
        if cap >= 500 and len(combined_notes) < cap:
            needed = cap - len(combined_notes)
            primary_ref = str(source_summary[0]["id"]) if source_summary else "moe-eng:middle-1200"
            extra_cards = build_full_scale_deck_cards(
                ref_id=primary_ref,
                difficulty_level=diff_norm,
                target_count=needed,
                extra_tags=("combined_exam",),
            )
            combined_notes.extend(dict(c) for c in extra_cards)
        combined_notes = combined_notes[:cap]

        summary_labels = [s["title"] for s in source_summary[:3]]
        default_title = f"🎯 통합 시험범위 덱 ({' + '.join(summary_labels)}) [{diff_norm.upper()}]"
        resolved_title = (deck_name or "").strip() or default_title

        batch = self.store.create_deck_with_notes(
            deck_name=resolved_title,
            notes=combined_notes,
            description=f"다중 출제범위 스마트 인터리빙 통합 덱 ({len(source_summary)}개 범위 조합, 난이도: {diff_norm})",
        )
        return {
            "ok": True,
            "deck_id": batch["deck_id"],
            "deck_name": batch["deck_name"],
            "saved_count": len(batch["saved_note_ids"]),
            "difficulty_level": diff_norm,
            "shuffle_mode": shuf_norm,
            "source_summary": source_summary,
            "cards": combined_notes,
        }

    def build_interactive_quiz(
        self,
        card_id: int,
        age_tier: str = "teen",
    ) -> Dict[str, Any]:
        """Build a 4-choice multiple-choice or tap-block interactive quiz for a due card using AdaptiveQuizEngine."""
        due = self.store.get_due_cards(limit=1500)
        target = next((c for c in due if int(c["card_id"]) == int(card_id)), None)
        if target is None:
            raise KeyError(f"Card {card_id} not found in due cards")

        front_str = str(target["front_text"] or "").strip()
        raw_back = str(target["back_text"] or "").strip()
        target_ans = _clean_concise_choice_answer(
            front_str,
            raw_back,
            str(target.get("target_answer") or ""),
        )
        target_qtype = classify_card_question_type(target)
        target_facet_key = str(target_qtype["facet_key"])

        candidates: List[CandidateDistractor] = []
        selected_relations: List[str] = []

        # 1) Query Tier R starter pack for explicit distractor relations (similar_shape, same_radical, homophone)
        conn = sqlite3.connect(f"file:{self.starter_pack_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            headword_guess_1 = front_str.split("]")[-1].strip() if "]" in front_str else front_str
            last_line = front_str.splitlines()[-1].strip() if front_str else ""
            headword_guess_2 = last_line.split("(")[0].strip()
            entry_row = conn.execute(
                "SELECT entry_key, entry_type, facet_json FROM ref_entries WHERE headword IN (?, ?) LIMIT 1",
                (headword_guess_1, headword_guess_2),
            ).fetchone()
            is_hanja = (
                (entry_row is not None and str(entry_row["entry_type"]) == "hanja_char")
                or front_str.startswith("[한자")
                or "[한자" in front_str
                or target_facet_key in ("hanja_hun_eum", "hanja_char")
            )
            q_facet = QuestionFacet.HANJA_CHAR if is_hanja else QuestionFacet.WORD_MEANING
            if entry_row is not None and target_facet_key in ("eng_vocab_meaning", "hanja_hun_eum"):
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
                        if "(부수:" in target_ans:
                            opt_txt = f"{f_data['hun']} {'/'.join(f_data['eum'])} (부수: {f_data.get('radical', '')}, 총 {f_data.get('strokes', '')}획)"
                        else:
                            opt_txt = f"{f_data['hun']} {'/'.join(f_data['eum'])}"
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

            # 2) Add other due cards ONLY if they have the exact same question facet_key (zero cross-type leak!)
            for other in due:
                if int(other["card_id"]) == int(card_id):
                    continue
                other_qtype = classify_card_question_type(other)
                if str(other_qtype["facet_key"]) != target_facet_key:
                    continue
                other_ans = _clean_concise_choice_answer(
                    str(other.get("front_text") or ""),
                    str(other.get("back_text") or ""),
                    str(other.get("target_answer") or ""),
                )
                if not other_ans:
                    continue
                candidates.append(
                    CandidateDistractor(
                        key=f"card:{other['card_id']}",
                        option_text=other_ans,
                        answer_set=frozenset({other_ans, str(other.get("back_text") or "").strip()}),
                        relations=frozenset({"same_radical"} if is_hanja else {"same_pos_level"}),
                        source_priority=2,
                    )
                )

            # 3) Supplement from Tier R entries ONLY when target is Korean meaning or Hanja hun/eum
            if target_facet_key in ("eng_vocab_meaning", "hanja_hun_eum"):
                target_etype = str(entry_row["entry_type"]) if entry_row is not None else ("hanja_char" if is_hanja else "vocab")
                fallback_rows = conn.execute(
                    "SELECT entry_key, gloss_ko, facet_json FROM ref_entries WHERE entry_type = ? ORDER BY difficulty_rank ASC LIMIT 12",
                    (target_etype,),
                ).fetchall()
                for frow in fallback_rows:
                    f_data = json.loads(str(frow["facet_json"] or "{}"))
                    if is_hanja and "hun" in f_data and "eum" in f_data:
                        if "(부수:" in target_ans:
                            opt_txt = f"{f_data['hun']} {'/'.join(f_data['eum'])} (부수: {f_data.get('radical', '')}, 총 {f_data.get('strokes', '')}획)"
                        else:
                            opt_txt = f"{f_data['hun']} {'/'.join(f_data['eum'])}"
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

            # 4) Supplement from strict type-matched fallback bank (for grammar, English words, history, science, etc.)
            type_matched = build_type_matched_quiz_options(target, due)
            for idx_fb, opt_fb in enumerate(type_matched["options"]):
                if opt_fb == target_ans:
                    continue
                candidates.append(
                    CandidateDistractor(
                        key=f"type_fb:{target_facet_key}:{idx_fb}",
                        option_text=opt_fb,
                        answer_set=frozenset({opt_fb}),
                        relations=frozenset({"same_radical"} if is_hanja else {"same_pos_level"}),
                        source_priority=4,
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
            "question_facet_label": str(target_qtype["badge_label"]),
            "question_type": target_qtype,
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
            if getattr(self, "command", "GET") != "HEAD":
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

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

            if path == "/api/store/packs":
                cat_filter = qs.get("category", [None])[0]
                age_filter = qs.get("age_tier", [None])[0]
                self._send_json(
                    svc.get_store_catalog(
                        category_filter=cat_filter,
                        age_tier_filter=age_filter,
                    )
                )
                return

            if path == "/api/bundle/offline-snapshot":
                self._send_json(svc.get_offline_bundle_snapshot())
                return

            if path == "/api/due":
                deck_raw = qs.get("deck_id", [None])[0]
                deck_id = int(deck_raw) if deck_raw and deck_raw.isdigit() else None
                shuffle_mode = str(qs.get("shuffle", ["sequential"])[0] or "sequential")
                limit_raw = qs.get("limit", ["50"])[0]
                limit_val = int(limit_raw) if limit_raw and str(limit_raw).isdigit() else 50
                respect_raw = qs.get("respect_plan", [None])[0]
                respect_quota = (
                    True
                    if respect_raw in ("1", "true", "True")
                    else (False if respect_raw in ("0", "false", "False") else None)
                )
                self._send_json(
                    svc.get_due_cards(
                        deck_id=deck_id,
                        limit=limit_val,
                        shuffle_mode=shuffle_mode,
                        respect_daily_quota=respect_quota,
                    )
                )
                return

            if path == "/api/study-plan":
                deck_raw = qs.get("deck_id", [None])[0]
                deck_id = int(deck_raw) if deck_raw and deck_raw.isdigit() else None
                target_days = int(qs.get("target_days", ["30"])[0] or 30)
                daily_minutes = int(qs.get("daily_minutes_budget", ["30"])[0] or 30)
                retention = float(qs.get("desired_retention", ["0.90"])[0] or 0.90)
                apply_raw = qs.get("apply", ["0"])[0] in ("1", "true", "True")
                self._send_json(
                    svc.get_anki_study_plan(
                        deck_id=deck_id,
                        target_days=target_days,
                        daily_minutes_budget=daily_minutes,
                        desired_retention=retention,
                        apply_plan=apply_raw,
                    )
                )
                return

            if path == "/api/ollama-cloud/models":
                self._send_json(svc.ai.list_ollama_cloud_models())
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

            if path.startswith("/download/") and path.endswith(".apk"):
                root_dir = Path(__file__).resolve().parents[3]
                candidates = [
                    root_dir / "dist" / "BrainDeck-v5.9.apk",
                    root_dir / "dist" / "BrainDeck-v5.8.apk",
                    root_dir / "dist" / "BrainDeck-v5.7.apk",
                    root_dir / "dist" / "BrainDeck-v5.6.apk",
                    root_dir / "dist" / "BrainDeck-v5.5.apk",
                    root_dir / "dist" / "BrainDeck-v5.4.apk",
                    root_dir / "dist" / "BrainDeck-v5.4-Android.apk",
                    root_dir / "dist" / "BrainDeck-v5.3-Android.apk",
                    root_dir / "dist" / "BrainDeck-v5.2-Android.apk",
                    root_dir / "android-app" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk",
                    root_dir / "android-app" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
                ]
                apk_path = next((p for p in candidates if p.is_file()), candidates[0])
                if not apk_path.is_file():
                    self._send_json({"ok": False, "error": "apk_not_found"}, status=404)
                    return
                apk_size = apk_path.stat().st_size
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header("Content-Disposition", f'attachment; filename="{apk_path.name}"')
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Content-Length", str(apk_size))
                self.end_headers()
                if getattr(self, "command", "GET") != "HEAD":
                    try:
                        with apk_path.open("rb") as fp:
                            while True:
                                chunk = fp.read(262144)
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
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
            if getattr(self, "command", "GET") != "HEAD":
                try:
                    self.wfile.write(raw_bytes)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path in ("/api/ai/ingest-document", "/api/ingest/document"):
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
                difficulty_level = str(qs.get("difficulty_level", ["standard"])[0] or "standard")
                ollama_cloud_model = qs.get("ollama_cloud_model", [None])[0]

                res = svc.ingest_document(
                    data=raw_bytes,
                    mime=mime,
                    deck_name=deck_name,
                    max_cards=max_cards,
                    auto_save=auto_save,
                    allow_cloud_vision=allow_cloud,
                    difficulty_level=difficulty_level,
                    ollama_cloud_model=ollama_cloud_model,
                )
                if res.get("error_code") in ("CLOUD_VISION_LOCKED", "BLOCKED_MODEL"):
                    http_code = 403
                elif res.get("status") == "OK":
                    http_code = 200
                else:
                    http_code = 422
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
                    raw_rt = body.get("response_time_ms")
                    rt_val = (
                        int(raw_rt)
                        if (raw_rt is not None and not isinstance(raw_rt, bool) and isinstance(raw_rt, (int, float)))
                        else None
                    )
                    res = svc.submit_review(
                        card_id=int(body["card_id"]),
                        rating=int(body["rating"]),
                        response_time_ms=rt_val,
                        confused_with_card_id=body.get("confused_with_card_id"),
                        confusion_weight=body.get("confusion_weight"),
                        review_id=body.get("review_id"),
                        baseline_rt_ms_samples=body.get("baseline_rt_ms_samples"),
                        consecutive_good_streak=body.get("consecutive_good_streak"),
                    )
                    self._send_json(res)
                    return

                if path == "/api/review/undo":
                    res = svc.undo_review()
                    status_code = 200 if res.get("ok") else 409
                    self._send_json(res, status=status_code)
                    return

                if path in ("/api/reset", "/api/study/reset", "/api/review/reset"):
                    raw_deck = body.get("deck_id")
                    if raw_deck in (None, "", "all"):
                        deck_id = None
                    elif isinstance(raw_deck, bool):
                        raise ValueError("Invalid deck_id: boolean not allowed")
                    else:
                        s_deck = str(raw_deck).strip()
                        if not s_deck.isdigit() or int(s_deck) <= 0:
                            raise ValueError(f"Invalid deck_id: {raw_deck!r}")
                        deck_id = int(s_deck)
                    res = svc.reset_study_progress(deck_id=deck_id)
                    self._send_json(res)
                    return

                if path == "/api/cards/suspend":
                    res = svc.suspend_card(card_id=int(body["card_id"]))
                    self._send_json(res)
                    return

                if path == "/api/cards/action":
                    res = svc.apply_card_anki_action(
                        card_id=int(body["card_id"]),
                        action=str(body.get("action") or ""),
                        flag=int(body.get("flag") or 0),
                        due_days=int(body.get("due_days") or 0),
                    )
                    self._send_json(res)
                    return

                if path in ("/api/study-plan", "/api/study-plan/apply"):
                    raw_deck = body.get("deck_id")
                    deck_id = int(raw_deck) if raw_deck not in (None, "", "all") and str(raw_deck).isdigit() else None
                    should_apply = path == "/api/study-plan/apply" or bool(body.get("apply") or body.get("apply_plan"))
                    if should_apply:
                        res = svc.apply_anki_study_plan(
                            deck_id=deck_id,
                            target_days=int(body.get("target_days") or 30),
                            daily_new_limit=int(body["new_per_day"]) if body.get("new_per_day") not in (None, "") else (int(body["daily_new_limit"]) if body.get("daily_new_limit") not in (None, "") else None),
                            daily_review_limit=int(body.get("max_reviews_per_day") or body.get("daily_review_limit") or 200),
                            daily_minutes_budget=int(body.get("daily_minutes_budget") or 30),
                            desired_retention=float(body.get("desired_retention") or 0.90),
                        )
                    else:
                        res = svc.get_anki_study_plan(
                            deck_id=deck_id,
                            target_days=int(body.get("target_days") or 30),
                            daily_minutes_budget=int(body.get("daily_minutes_budget") or 30),
                            desired_retention=float(body.get("desired_retention") or 0.90),
                            new_per_day=int(body["new_per_day"]) if body.get("new_per_day") not in (None, "") else None,
                            max_reviews_per_day=int(body.get("max_reviews_per_day") or 200),
                            bury_siblings=bool(body.get("bury_siblings", True)),
                            review_sort_order=str(body.get("review_sort_order") or "retrievability_asc"),
                            new_review_mix=str(body.get("new_review_mix") or "mix"),
                            total_cards_override=int(body["total_cards"]) if body.get("total_cards") not in (None, "") else None,
                        )
                    self._send_json(res)
                    return

                if path == "/api/custom-study":
                    raw_deck = body.get("deck_id")
                    deck_id = int(raw_deck) if raw_deck not in (None, "", "all") and str(raw_deck).isdigit() else None
                    res = svc.build_anki_custom_study(
                        deck_id=deck_id,
                        preset=str(body.get("preset") or "forgotten_recent"),
                        days_ahead=int(body.get("days_ahead") or 3),
                        limit=int(body.get("limit") or 50),
                        extra_new=int(body.get("extra_new") or 10),
                    )
                    self._send_json(res)
                    return

                if path == "/api/deck/explorer":
                    raw_deck = body.get("deck_id")
                    deck_id = int(raw_deck) if raw_deck not in (None, "", "all") and str(raw_deck).isdigit() else None
                    res = svc.explore_deck_cards(
                        deck_id=deck_id,
                        query=str(body.get("query") or ""),
                        bucket_filter=str(body.get("bucket_filter") or body.get("bucket") or "all"),
                        stage_filter=str(body.get("stage_filter") or body.get("stage") or "all"),
                        limit=int(body.get("limit") or 200),
                    )
                    self._send_json(res)
                    return

                if path == "/api/profile/age-tier":
                    res = svc.set_profile_age_tier(
                        age_tier=str(body.get("age_tier") or ""),
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

                if path in ("/api/ai/generate-cards", "/api/cards/generate"):
                    deck_id = int(body["deck_id"]) if body.get("deck_id") is not None else None
                    res = svc.generate_ai_cards(
                        raw_text=str(body.get("raw_text") or ""),
                        domain_mode=str(body.get("domain_mode") or "auto"),
                        deck_id=deck_id,
                        auto_save=bool(body.get("auto_save", True)),
                        max_cards=int(body.get("max_cards") or 10),
                        difficulty_level=str(body.get("difficulty_level") or "standard"),
                        ollama_cloud_model=body.get("ollama_cloud_model"),
                    )
                    http_code = 403 if res.get("error_code") == "BLOCKED_MODEL" else 200
                    self._send_json(res, status=http_code)
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
                        limit=int(body.get("limit") or 1000),
                        deck_name=str(body.get("deck_name") or "") or None,
                        difficulty_level=str(body.get("difficulty_level") or "standard"),
                        shuffle_mode=str(body.get("shuffle_mode") or "sequential"),
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
                        difficulty_level=str(body.get("difficulty_level") or "standard"),
                        shuffle_mode=str(body.get("shuffle_mode") or "sequential"),
                        limit=int(body.get("limit") or 1000),
                    )
                    self._send_json(res)
                    return

                if path == "/api/catalog/generate-combined-exam-deck":
                    res = svc.generate_combined_exam_deck(
                        scopes=list(body.get("scopes") or []),
                        deck_name=str(body.get("deck_name") or "") or None,
                        difficulty_level=str(body.get("difficulty_level") or "mixed"),
                        shuffle_mode=str(body.get("shuffle_mode") or "interleaved"),
                        max_cards=int(body.get("max_cards") or 1000),
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

                if path == "/api/store/purchase":
                    res = svc.purchase_store_pack(
                        pack_id=str(body.get("pack_id") or ""),
                        auto_create_deck=bool(body.get("auto_create_deck", True)),
                        payment_channel=str(body.get("payment_channel") or "braindeck_store"),
                        payment_token=str(body["payment_token"]) if body.get("payment_token") is not None else None,
                    )
                    self._send_json(res)
                    return

                if path == "/api/store/purchase-bundle":
                    raw_ids = body.get("pack_ids") or []
                    if not isinstance(raw_ids, list):
                        raise ValueError("pack_ids must be a list")
                    res = svc.purchase_store_bundle(
                        pack_ids=[str(x) for x in raw_ids],
                        auto_create_decks=bool(body.get("auto_create_decks", True)),
                        payment_channel=str(body.get("payment_channel") or "braindeck_bundle"),
                        payment_token=str(body["payment_token"]) if body.get("payment_token") is not None else None,
                    )
                    self._send_json(res)
                    return

                if path == "/api/store/refund":
                    res = svc.refund_store_pack(
                        pack_id=str(body.get("pack_id") or ""),
                    )
                    self._send_json(res)
                    return

                self._send_json({"ok": False, "error": "not_found"}, status=404)
            except PermissionError as exc:
                raw_msg = str(exc)
                try:
                    decision_obj = json.loads(raw_msg)
                    err_code = str(decision_obj.get("error_code") or "FORBIDDEN")
                except Exception:
                    decision_obj = {"detail": raw_msg}
                    err_code = "FORBIDDEN"
                self._send_json(
                    {
                        "ok": False,
                        "error": err_code,
                        "error_code": err_code,
                        "decision": decision_obj,
                    },
                    status=403,
                )
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
    import os
    bind_host = os.environ.get("BRAINDECK_HOST", "0.0.0.0")
    bind_port = int(os.environ.get("BRAINDECK_PORT", "4390"))
    srv = create_http_server(host=bind_host, port=bind_port)
    print(f"BrainDeck 2.0 (Apple PWA & Web Server) running on http://{bind_host}:{bind_port}")
    srv.serve_forever()

