"""SQLite WAL Single-Writer Ledger & Anki .apkg Lossless Adapter.

Enforces BEGIN IMMEDIATE transactions, WAL concurrency, and lossless
import/export of standard Anki .apkg (collection.anki2) archives.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, Iterator, List, Optional
import zipfile

from anki_studio.domain.fsrs_math import (
    CardMemoryState,
    Rating,
    compute_retrievability,
    detect_leech_severity,
    extract_cloze_ordinals,
    forecast_forgetting_curve,
    plan_backlog_decompression,
    preview_all_ratings,
    render_cloze_card,
    step_fsrs,
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS decks (
    deck_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    desired_retention REAL NOT NULL DEFAULT 0.90,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL REFERENCES decks(deck_id) ON DELETE CASCADE,
    note_type TEXT NOT NULL DEFAULT 'basic',
    front_text TEXT NOT NULL,
    back_text TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    source_ref TEXT UNIQUE,
    source_page INTEGER,
    source_excerpt TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    card_id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
    deck_id INTEGER NOT NULL REFERENCES decks(deck_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'new',
    difficulty REAL NOT NULL DEFAULT 0.0,
    stability REAL NOT NULL DEFAULT 0.0,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    due_at TEXT NOT NULL,
    last_review_at TEXT,
    UNIQUE(note_id, ordinal)
);

CREATE TABLE IF NOT EXISTS revlog (
    rev_id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(card_id) ON DELETE CASCADE,
    rating INTEGER NOT NULL,
    state_before TEXT NOT NULL,
    difficulty_before REAL NOT NULL,
    stability_before REAL NOT NULL,
    difficulty_after REAL NOT NULL,
    stability_after REAL NOT NULL,
    retrievability REAL NOT NULL,
    scheduled_days INTEGER NOT NULL,
    elapsed_days REAL NOT NULL,
    reviewed_at TEXT NOT NULL
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnkiStudioStore:
    """SQLite WAL single-writer storage adapter for Anki Studio."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    @contextmanager
    def _write_tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._write_tx() as conn:
            for stmt in SCHEMA_SQL.strip().split(";"):
                if stmt.strip():
                    conn.execute(stmt)
            cols = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(notes)").fetchall()
            }
            if "source_page" not in cols:
                conn.execute("ALTER TABLE notes ADD COLUMN source_page INTEGER;")
            if "source_excerpt" not in cols:
                conn.execute("ALTER TABLE notes ADD COLUMN source_excerpt TEXT NOT NULL DEFAULT '';")

    def ensure_deck(
        self,
        name: str,
        description: str = "",
        desired_retention: float = 0.90,
    ) -> int:
        now = _utc_now_iso()
        with self._write_tx() as conn:
            conn.execute(
                """
                INSERT INTO decks (name, description, desired_retention, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = CASE WHEN excluded.description != '' THEN excluded.description ELSE decks.description END,
                    desired_retention = excluded.desired_retention
                """,
                (name.strip(), description.strip(), float(desired_retention), now),
            )
            row = conn.execute(
                "SELECT deck_id FROM decks WHERE name = ?",
                (name.strip(),),
            ).fetchone()
            return int(row["deck_id"])

    def list_decks(self, as_of_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        now = as_of_iso or _utc_now_iso()
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    d.deck_id,
                    d.name,
                    d.description,
                    d.desired_retention,
                    COUNT(CASE WHEN c.state != 'suspended' THEN c.card_id END) AS total_cards,
                    SUM(CASE WHEN c.state != 'suspended' AND c.due_at <= ? THEN 1 ELSE 0 END) AS due_cards,
                    SUM(CASE WHEN c.state = 'new' THEN 1 ELSE 0 END) AS new_cards,
                    SUM(CASE WHEN c.state != 'suspended' AND c.lapses >= 2 THEN 1 ELSE 0 END) AS leech_cards,
                     COALESCE(AVG(CASE WHEN c.state != 'suspended' AND c.stability > 0 THEN c.stability END), 0.0) AS avg_stability
                FROM decks d
                LEFT JOIN cards c ON c.deck_id = d.deck_id
                GROUP BY d.deck_id
                ORDER BY d.deck_id ASC
                """,
                (now,),
            ).fetchall()
            return [
                {
                    "deck_id": int(r["deck_id"]),
                    "name": str(r["name"]),
                    "description": str(r["description"]),
                    "desired_retention": float(r["desired_retention"]),
                    "total_cards": int(r["total_cards"] or 0),
                    "due_cards": int(r["due_cards"] or 0),
                    "new_cards": int(r["new_cards"] or 0),
                    "leech_cards": int(r["leech_cards"] or 0),
                    "avg_stability": round(float(r["avg_stability"] or 0.0), 2),
                }
                for r in rows
            ]
        finally:
            conn.close()

    def add_note(
        self,
        deck_id: int,
        front_text: str,
        back_text: str = "",
        note_type: str = "basic",
        tags: Optional[List[str]] = None,
        source_ref: Optional[str] = None,
        now_iso: Optional[str] = None,
    ) -> int:
        """Insert a note and automatically generate its associated cards (Basic, Speaking, or Cloze)."""
        now = now_iso or _utc_now_iso()
        if note_type == "cloze" or extract_cloze_ordinals(front_text):
            note_type = "cloze"
            ordinals = extract_cloze_ordinals(front_text) or [1]
        else:
            ordinals = [1]

        with self._write_tx() as conn:
            if source_ref:
                existing = conn.execute(
                    "SELECT note_id FROM notes WHERE source_ref = ?",
                    (source_ref,),
                ).fetchone()
                if existing is not None:
                    return int(existing["note_id"])

            cur = conn.execute(
                """
                INSERT INTO notes (deck_id, note_type, front_text, back_text, tags_json, source_ref, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(deck_id),
                    note_type,
                    front_text.strip(),
                    back_text.strip(),
                    json.dumps(tags or [], ensure_ascii=False),
                    source_ref,
                    now,
                ),
            )
            note_id = int(cur.lastrowid)
            for ordinal in ordinals:
                conn.execute(
                    """
                    INSERT INTO cards (note_id, deck_id, ordinal, state, difficulty, stability, reps, lapses, due_at)
                    VALUES (?, ?, ?, 'new', 0.0, 0.0, 0, 0, ?)
                    """,
                    (note_id, int(deck_id), int(ordinal), now),
                )
            return note_id

    def create_deck_with_notes(
        self,
        deck_name: str,
        notes: List[Dict[str, Any]],
        description: str = "",
        desired_retention: float = 0.90,
        now_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically create or resolve a deck and insert N notes in a single BEGIN IMMEDIATE transaction (AC-4)."""
        clean_deck = (deck_name or "").strip()
        if not clean_deck:
            raise ValueError("deck_name must not be empty")
        if not notes:
            raise ValueError("notes list must not be empty")

        now = now_iso or _utc_now_iso()
        with self._write_tx() as conn:
            conn.execute(
                """
                INSERT INTO decks (name, description, desired_retention, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = CASE WHEN excluded.description != '' THEN excluded.description ELSE decks.description END
                """,
                (clean_deck, description.strip(), float(desired_retention), now),
            )
            row = conn.execute(
                "SELECT deck_id FROM decks WHERE name = ?",
                (clean_deck,),
            ).fetchone()
            deck_id = int(row["deck_id"])

            saved_note_ids: List[int] = []
            for item in notes:
                front = str(item.get("front_text") or "").strip()
                if not front:
                    raise ValueError("Every note in create_deck_with_notes must have non-empty front_text")
                back = str(item.get("back_text") or "").strip()
                note_type = str(item.get("note_type") or "basic").strip()
                tags = list(item.get("tags") or [])
                source_ref = item.get("source_ref")
                raw_page = item.get("source_page")
                source_page = int(raw_page) if raw_page is not None else None
                source_excerpt = str(item.get("source_excerpt") or "")

                if note_type == "cloze" or extract_cloze_ordinals(front):
                    note_type = "cloze"
                    ordinals = extract_cloze_ordinals(front) or [1]
                else:
                    ordinals = [1]

                cur = conn.execute(
                    """
                    INSERT INTO notes (
                        deck_id, note_type, front_text, back_text,
                        tags_json, source_ref, source_page, source_excerpt, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deck_id,
                        note_type,
                        front,
                        back,
                        json.dumps(tags, ensure_ascii=False),
                        source_ref,
                        source_page,
                        source_excerpt,
                        now,
                    ),
                )
                note_id = int(cur.lastrowid)
                saved_note_ids.append(note_id)
                for ordinal in ordinals:
                    conn.execute(
                        """
                        INSERT INTO cards (note_id, deck_id, ordinal, state, difficulty, stability, reps, lapses, due_at)
                        VALUES (?, ?, ?, 'new', 0.0, 0.0, 0, 0, ?)
                        """,
                        (note_id, deck_id, int(ordinal), now),
                    )

            return {
                "deck_id": deck_id,
                "deck_name": clean_deck,
                "saved_note_ids": saved_note_ids,
            }

    def suspend_card(self, card_id: int) -> bool:
        """Atomically suspend a card (e.g. parent Leech card after atomic decomposition) while preserving revlog."""
        with self._write_tx() as conn:
            cur = conn.execute(
                "UPDATE cards SET state = 'suspended' WHERE card_id = ?",
                (int(card_id),),
            )
            return cur.rowcount > 0

    def get_due_cards(
        self,
        deck_id: Optional[int] = None,
        as_of_iso: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        now_str = as_of_iso or _utc_now_iso()
        now_dt = datetime.fromisoformat(now_str)
        conn = self._connect()
        try:
            query = """
                SELECT c.*, n.note_type, n.front_text, n.back_text, n.tags_json,
                       n.source_ref, n.source_page, n.source_excerpt,
                       d.name AS deck_name, d.desired_retention
                FROM cards c
                JOIN notes n ON n.note_id = c.note_id
                JOIN decks d ON d.deck_id = c.deck_id
                WHERE c.state != 'suspended' AND c.due_at <= ?
            """
            params: List[Any] = [now_str]
            if deck_id is not None:
                query += " AND c.deck_id = ?"
                params.append(int(deck_id))
            query += " ORDER BY c.due_at ASC, c.card_id ASC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(query, params).fetchall()
            result: List[Dict[str, Any]] = []
            for r in rows:
                item = dict(r)
                if item["note_type"] == "cloze":
                    item["rendered_question"] = render_cloze_card(item["front_text"], item["ordinal"], reveal=False)
                    item["rendered_answer"] = render_cloze_card(item["front_text"], item["ordinal"], reveal=True)
                    if item["back_text"]:
                        item["rendered_answer"] += f"\n\n💡 해설: {item['back_text']}"
                else:
                    item["rendered_question"] = item["front_text"]
                    item["rendered_answer"] = item["back_text"]

                elapsed_days = 0.0
                if item["last_review_at"]:
                    prev_dt = datetime.fromisoformat(str(item["last_review_at"]))
                    elapsed_days = max(0.0, (now_dt - prev_dt).total_seconds() / 86400.0)

                mem = CardMemoryState(
                    difficulty=float(item["difficulty"]),
                    stability=float(item["stability"]),
                    reps=int(item["reps"]),
                    lapses=int(item["lapses"]),
                    state=str(item["state"]),
                )
                previews = preview_all_ratings(
                    mem,
                    elapsed_days=elapsed_days,
                    desired_retention=float(item["desired_retention"]),
                )
                item["button_previews"] = {
                    k: {
                        "scheduled_days": v.scheduled_days,
                        "label": v.scheduled_label,
                        "next_stability": v.memory.stability,
                        "next_difficulty": v.memory.difficulty,
                    }
                    for k, v in previews.items()
                }
                item["leech_status"] = detect_leech_severity(mem.reps, mem.lapses, mem.difficulty)
                item["retrievability"] = (
                    round(compute_retrievability(elapsed_days, mem.stability), 4)
                    if mem.stability > 0
                    else 1.0
                )
                result.append(item)
            return result
        finally:
            conn.close()

    def review_card(
        self,
        card_id: int,
        rating: Rating | int,
        reviewed_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now_dt = reviewed_at or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        with self._write_tx() as conn:
            row = conn.execute(
                """
                SELECT c.*, d.desired_retention
                FROM cards c
                JOIN decks d ON d.deck_id = c.deck_id
                WHERE c.card_id = ?
                """,
                (int(card_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"Card {card_id} not found")

            mem_before = CardMemoryState(
                difficulty=float(row["difficulty"]),
                stability=float(row["stability"]),
                reps=int(row["reps"]),
                lapses=int(row["lapses"]),
                state=str(row["state"]),
            )

            elapsed_days = 0.0
            if row["last_review_at"]:
                prev_dt = datetime.fromisoformat(str(row["last_review_at"]))
                elapsed_days = max(0.0, (now_dt - prev_dt).total_seconds() / 86400.0)

            outcome = step_fsrs(
                memory=mem_before,
                rating=Rating(int(rating)),
                elapsed_days=elapsed_days,
                desired_retention=float(row["desired_retention"]),
            )

            if outcome.scheduled_days == 0:
                due_dt = now_dt + timedelta(minutes=10)
            else:
                due_dt = now_dt + timedelta(days=outcome.scheduled_days)

            conn.execute(
                """
                UPDATE cards
                SET state = ?, difficulty = ?, stability = ?, reps = ?, lapses = ?,
                    due_at = ?, last_review_at = ?
                WHERE card_id = ?
                """,
                (
                    outcome.memory.state,
                    outcome.memory.difficulty,
                    outcome.memory.stability,
                    outcome.memory.reps,
                    outcome.memory.lapses,
                    due_dt.isoformat(),
                    now_iso,
                    int(card_id),
                ),
            )

            conn.execute(
                """
                INSERT INTO revlog (
                    card_id, rating, state_before, difficulty_before, stability_before,
                    difficulty_after, stability_after, retrievability, scheduled_days,
                    elapsed_days, reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(card_id),
                    int(outcome.rating),
                    mem_before.state,
                    mem_before.difficulty,
                    mem_before.stability,
                    outcome.memory.difficulty,
                    outcome.memory.stability,
                    outcome.retrievability_before,
                    outcome.scheduled_days,
                    round(elapsed_days, 4),
                    now_iso,
                ),
            )

            return {
                "card_id": int(card_id),
                "rating": int(outcome.rating),
                "memory": outcome.memory,
                "scheduled_days": outcome.scheduled_days,
                "scheduled_label": outcome.scheduled_label,
                "due_at": due_dt.isoformat(),
            }

    def decompress_backlog(
        self,
        deck_id: Optional[int] = None,
        daily_cap: int = 25,
        horizon_days: int = 7,
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Smoothly redistribute overdue review bombs across `horizon_days` using FSRS-5 retrievability priority."""
        now_dt = as_of or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        with self._write_tx() as conn:
            query = "SELECT card_id, stability, difficulty, lapses, last_review_at FROM cards WHERE state != 'suspended' AND due_at <= ?"
            params: List[Any] = [now_iso]
            if deck_id is not None:
                query += " AND deck_id = ?"
                params.append(int(deck_id))
            rows = conn.execute(query, params).fetchall()

            snapshots: List[Dict[str, float | int]] = []
            for r in rows:
                elapsed = 1.0
                if r["last_review_at"]:
                    prev_dt = datetime.fromisoformat(str(r["last_review_at"]))
                    elapsed = max(0.0, (now_dt - prev_dt).total_seconds() / 86400.0)
                snapshots.append(
                    {
                        "card_id": int(r["card_id"]),
                        "elapsed_days": elapsed,
                        "stability": float(r["stability"]) if float(r["stability"]) > 0 else 1.0,
                        "difficulty": float(r["difficulty"]),
                        "lapses": int(r["lapses"]),
                    }
                )

            plan = plan_backlog_decompression(snapshots, daily_cap=daily_cap, horizon_days=horizon_days)
            rescheduled_count = 0
            for entry in plan:
                offset = int(entry["day_offset"])
                if offset > 0:
                    new_due = (now_dt + timedelta(days=offset)).isoformat()
                    conn.execute(
                        "UPDATE cards SET due_at = ? WHERE card_id = ?",
                        (new_due, int(entry["card_id"])),
                    )
                    rescheduled_count += 1

            return {
                "total_due_evaluated": len(plan),
                "kept_today": len(plan) - rescheduled_count,
                "deferred_across_days": rescheduled_count,
                "daily_cap": int(daily_cap),
                "horizon_days": int(horizon_days),
            }

    def get_dashboard_stats(self, as_of_iso: Optional[str] = None) -> Dict[str, Any]:
        """Compute real-time telemetry, retention rate, leech count, and forgetting curve."""
        now = as_of_iso or _utc_now_iso()
        today_prefix = now[:10]
        conn = self._connect()
        try:
            totals = conn.execute(
                """
                SELECT
                    COUNT(CASE WHEN state != 'suspended' THEN 1 END) AS total_cards,
                    SUM(CASE WHEN state != 'suspended' AND due_at <= ? THEN 1 ELSE 0 END) AS due_now,
                    SUM(CASE WHEN state != 'suspended' AND lapses >= 2 THEN 1 ELSE 0 END) AS leech_cards,
                    SUM(CASE WHEN state = 'suspended' THEN 1 ELSE 0 END) AS suspended_cards,
                    COALESCE(AVG(CASE WHEN state != 'suspended' AND stability > 0 THEN stability END), 0.0) AS avg_stability,
                    COALESCE(AVG(CASE WHEN state != 'suspended' AND difficulty > 0 THEN difficulty END), 0.0) AS avg_difficulty
                FROM cards
                """,
                (now,),
            ).fetchone()

            rev_stats = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_reviews,
                    SUM(CASE WHEN reviewed_at LIKE ? THEN 1 ELSE 0 END) AS reviews_today,
                    SUM(CASE WHEN rating >= 2 THEN 1 ELSE 0 END) AS passed_reviews
                FROM revlog
                """,
                (f"{today_prefix}%",),
            ).fetchall()[0]

            total_rev = int(rev_stats["total_reviews"] or 0)
            passed_rev = int(rev_stats["passed_reviews"] or 0)
            true_retention = round((passed_rev / total_rev) * 100.0, 1) if total_rev > 0 else 90.0
            avg_stab = round(float(totals["avg_stability"] or 0.0), 2)

            return {
                "total_cards": int(totals["total_cards"] or 0),
                "due_now": int(totals["due_now"] or 0),
                "leech_cards": int(totals["leech_cards"] or 0),
                "suspended_cards": int(totals["suspended_cards"] or 0),
                "avg_stability_days": avg_stab,
                "avg_difficulty": round(float(totals["avg_difficulty"] or 0.0), 2),
                "reviews_today": int(rev_stats["reviews_today"] or 0),
                "total_reviews": total_rev,
                "true_retention_pct": true_retention,
                "forgetting_curve": forecast_forgetting_curve(avg_stab if avg_stab > 0 else 5.0, horizon_days=30),
            }
        finally:
            conn.close()

    def import_apkg(self, apkg_path: str | Path, target_deck_name: Optional[str] = None) -> int:
        """Import notes from a standard Anki .apkg ZIP package (`collection.anki2`)."""
        apkg_file = Path(apkg_path)
        if not apkg_file.is_file():
            raise FileNotFoundError(f"APKG file not found: {apkg_file}")

        deck_title = target_deck_name or apkg_file.stem
        deck_id = self.ensure_deck(deck_title)
        imported_count = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(apkg_file, "r") as zf:
                db_member = next(
                    (m for m in zf.namelist() if m in ("collection.anki21", "collection.anki2")),
                    None,
                )
                if db_member is None:
                    raise ValueError(f"No collection.anki2/21 found inside {apkg_file.name}")
                extracted_db = Path(tmpdir) / db_member
                zf.extract(db_member, tmpdir)

            src_conn = sqlite3.connect(str(extracted_db))
            try:
                rows = src_conn.execute("SELECT id, flds, tags FROM notes").fetchall()
            finally:
                src_conn.close()

            for note_guid, flds, tags in rows:
                parts = str(flds).split("\x1f")
                front = parts[0].strip() if parts else ""
                back = parts[1].strip() if len(parts) > 1 else ""
                if not front:
                    continue
                note_type = "cloze" if "{{c" in front else "basic"
                tag_list = [t for t in str(tags).strip().split() if t]
                self.add_note(
                    deck_id=deck_id,
                    front_text=front,
                    back_text=back,
                    note_type=note_type,
                    tags=tag_list,
                    source_ref=f"apkg:{apkg_file.name}:{note_guid}",
                )
                imported_count += 1

        return imported_count

    def export_apkg(self, output_path: str | Path, deck_id: Optional[int] = None) -> Path:
        """Atomically export notes into a standard Anki-compatible `.apkg` archive (`collection.anki2` + `media`)."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = out_file.with_name(f".{out_file.name}.tmp.{os.getpid()}")

        conn = self._connect()
        try:
            if deck_id is not None:
                notes = conn.execute(
                    "SELECT note_id, front_text, back_text, tags_json FROM notes WHERE deck_id = ? ORDER BY note_id ASC",
                    (int(deck_id),),
                ).fetchall()
            else:
                notes = conn.execute(
                    "SELECT note_id, front_text, back_text, tags_json FROM notes ORDER BY note_id ASC"
                ).fetchall()
        finally:
            conn.close()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                anki2_file = Path(tmpdir) / "collection.anki2"
                exp_conn = sqlite3.connect(str(anki2_file))
                try:
                    exp_conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT, tags TEXT)")
                    for n in notes:
                        tags_list = json.loads(n["tags_json"] or "[]")
                        tags_str = " ".join(str(t) for t in tags_list)
                        flds_str = f"{n['front_text']}\x1f{n['back_text']}"
                        exp_conn.execute(
                            "INSERT INTO notes (id, flds, tags) VALUES (?, ?, ?)",
                            (int(n["note_id"]), flds_str, tags_str),
                        )
                    exp_conn.commit()
                finally:
                    exp_conn.close()

                with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(anki2_file, arcname="collection.anki2")
                    zf.writestr("media", "{}")

            os.replace(tmp_out, out_file)
        except Exception:
            if tmp_out.exists():
                tmp_out.unlink(missing_ok=True)
            raise

        return out_file

    def seed_default_decks_if_empty(self) -> None:
        """Populate starter decks for English Conversation and Semiconductor/AI Engineering if DB is empty."""
        decks = self.list_decks()
        if any(d["total_cards"] > 0 for d in decks):
            return

        eng_id = self.ensure_deck(
            "🗣️ 비즈니스 & 실전 영어회화 (English Speaking)",
            description="노션 영어회화 DB 연동 · 내 실수 패턴 교정 및 원어민 핵심 표현 액티브 리콜",
            desired_retention=0.90,
        )
        self.add_note(
            deck_id=eng_id,
            note_type="speaking",
            front_text="🗣️ [영어 표현 인출] 지난번 회의 안건에 대해 후속 논의를 이어가고 싶습니다.",
            back_text="I'd like to follow up on the action items from our last meeting.",
            tags=["english", "business-meeting", "speaking"],
            source_ref="seed:eng:1",
        )
        self.add_note(
            deck_id=eng_id,
            note_type="cloze",
            front_text="양산 일정을 앞당기려면 수율 병목부터 해결해야 합니다: To pull in the mass production schedule, we need to {{c1::resolve the yield bottleneck::핵심 동사구}} first.",
            back_text="pull in the schedule (일정을 앞당기다) / resolve the yield bottleneck (수율 병목을 해결하다)",
            tags=["english", "semiconductor-biz", "cloze"],
            source_ref="seed:eng:2",
        )

        semi_id = self.ensure_deck(
            "🔬 반도체 소자·공정 & AI 아키텍처 (DeepTech)",
            description="FinFET/GAA Nanosheet · High-NA EUV · LLM 추론 최적화 핵심 수식 및 개념",
            desired_retention=0.92,
        )
        self.add_note(
            deck_id=semi_id,
            note_type="cloze",
            front_text="차세대 {{c1::High-NA EUV::노광 장비}}는 개구수(NA)를 기존 0.33에서 {{c2::0.55::수치}}로 높여 단일 노광 해상도를 8nm급으로 개선한다.",
            back_text="Anamorphic 렌즈(가로 4x, 세로 8x 배율 축소)를 사용하여 0.55 NA를 달성함.",
            tags=["semiconductor", "lithography", "euv"],
            source_ref="seed:semi:1",
        )
        self.add_note(
            deck_id=semi_id,
            note_type="cloze",
            front_text="2nm 이하 공정에서 FinFET을 대체하는 {{c1::GAA (Gate-All-Around)::트랜지스터 구조}}는 채널인 {{c2::Nanosheet}}의 4면을 게이트가 완전히 감싸 누설전류와 단채널 효과(SCE)를 극소화한다.",
            back_text="유효 채널 폭(Weff)을 나노시트 적층 수로 유연하게 조절 가능.",
            tags=["semiconductor", "device", "gaa"],
            source_ref="seed:semi:2",
        )
