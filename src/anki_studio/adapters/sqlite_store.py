"""SQLite WAL Single-Writer Ledger & Anki .apkg Lossless Adapter.

Enforces BEGIN IMMEDIATE transactions, WAL concurrency, and lossless
import/export of standard Anki .apkg (collection.anki2) archives.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, Iterator, List, Optional
import zipfile

from anki_studio.domain.fsrs_math import (
    CardMemoryState,
    Rating,
    extract_cloze_ordinals,
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
        """Insert a note and automatically generate its associated cards (Basic or Cloze)."""
        now = now_iso or _utc_now_iso()
        ordinals = extract_cloze_ordinals(front_text) if note_type == "cloze" else [1]
        if not ordinals:
            ordinals = [1]

        with self._write_tx() as conn:
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

    def get_due_cards(self, deck_id: Optional[int] = None, as_of_iso: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        now = as_of_iso or _utc_now_iso()
        conn = self._connect()
        try:
            query = """
                SELECT c.*, n.note_type, n.front_text, n.back_text, n.tags_json, d.name AS deck_name, d.desired_retention
                FROM cards c
                JOIN notes n ON n.note_id = c.note_id
                JOIN decks d ON d.deck_id = c.deck_id
                WHERE c.due_at <= ?
            """
            params: List[Any] = [now]
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
                else:
                    item["rendered_question"] = item["front_text"]
                    item["rendered_answer"] = item["back_text"]
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
