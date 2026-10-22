"""2-Tier Reference Pack (`Tier R`) & User Ledger v2 (`Tier U`) SQLite Adapter (T19 ~ T28).

Implements:
- `Tier R: ReferencePackBuilder` (`packs/<pack_id>@<ver>.sqlite`):
  - Read-only reference pack schema (`pack_meta`, `ref_sources`, `ref_entries`, `ref_aliases`,
    `ref_collections`, `ref_relations`, `ref_changelog`, `ref_textbooks`, `ref_curriculum_units`,
    `ref_unit_entries`).
  - Fail-Closed License Policy Gate (`T21, T27`): Rejects `NC`, `ND`, `UNKNOWN` licenses and
    blocks `licensed_passage` entries on non-contract/non-public-law sources via both Python
    validation and SQLite triggers (INSERT + UPDATE).
  - Textbook curriculum hierarchy triggers (`trg_ref_units_hierarchy_insert/update`,
    `trg_ref_unit_entries_integrity_insert/update`, `trg_ref_entries_licensed_passage_update`,
    `trg_ref_sources_licensed_passage_update`).
- `Tier U: TierULedgerStore` (v2 Multi-Profile + Lazy Materialization + School Exam-Scope Engine):
  - Multi-profile isolation (`learner_profiles`, `subject_taxonomy`) with Junior cloud-lock
    invariant (`CHECK (age_tier != 'junior' OR cloud_vision_locked = 1)`) and cross-profile
    SQLite triggers (`T19`).
  - Append-only `next_ordinal` Lazy Materialization (`materialize_daily_pack_cards`, `T20`) inside
    `BEGIN IMMEDIATE` transactions, preserving `user_override_json` and FSRS `stability` on pack
    errata updates.
  - Middle/High school textbook `exam_scopes`, `exam_scope_rules`, and `exam_scope_items` (`T27, T28`):
    - Supports non-contiguous units (e.g., Lesson 1 + Lesson 3) and multiple disjoint page ranges
      within the same unit (e.g., Lesson 2 p.20..25 and p.30..35).
    - Combines `Tier R` pack entries (`item_kind='pack_entry'`) and student-scanned notes
      (`item_kind='user_note'`) into one deterministic exam scope without colliding on `scope_ordinal`
      and without overwriting `cards.queue` or `cards.state` when narrowing/expanding the scope.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterator, Mapping, Sequence
import uuid

from anki_studio.domain.adaptive_quiz import preserve_cjk_compat_before_nfc
from anki_studio.domain.fsrs_math import extract_cloze_ordinals
from anki_studio.domain.moe_curriculum_corpus import build_tier_r_moe_collections


ALLOWED_SOURCE_LICENSES: frozenset[str] = frozenset(
    {
        "PUBLIC_LAW_ART7",
        "KOGL_1",
        "CC0",
        "CC_BY",
        "CC_BY_SA",
        "FACT_SELF_AUTHORED",
        "SYNTH_REVIEWED",
        "CONTRACT_LICENSED",
    }
)

LICENSED_PASSAGE_SOURCES: frozenset[str] = frozenset(
    {
        "CONTRACT_LICENSED",
        "PUBLIC_LAW_ART7",
        "KOGL_1",
    }
)


class LicensePolicyError(ValueError):
    """Raised when a pack or source violates the T21/T27 license allowlist."""


TIER_R_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pack_meta (
    pack_id TEXT PRIMARY KEY,
    pack_version TEXT NOT NULL,
    pack_schema_version INTEGER NOT NULL DEFAULT 1,
    domain TEXT NOT NULL
        CHECK (domain IN ('vocab', 'hanja', 'idiom', 'history', 'law', 'orthography', 'formula', 'element', 'exam_fact', 'dictation', 'generator', 'textbook_curriculum')),
    license_spdx TEXT NOT NULL,
    redistribution_allowed INTEGER NOT NULL CHECK (redistribution_allowed IN (0, 1)),
    modification_allowed INTEGER NOT NULL CHECK (modification_allowed = 1),
    attribution_text TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    min_app_schema INTEGER NOT NULL DEFAULT 2,
    built_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    url TEXT,
    license_class TEXT NOT NULL
        CHECK (license_class IN ('PUBLIC_LAW_ART7', 'KOGL_1', 'CC0', 'CC_BY', 'CC_BY_SA', 'FACT_SELF_AUTHORED', 'SYNTH_REVIEWED', 'CONTRACT_LICENSED')),
    snapshot_sha256 TEXT NOT NULL,
    retrieved_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_entries (
    entry_key TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL
        CHECK (entry_type IN ('word', 'hanja_char', 'idiom', 'event', 'person', 'treaty', 'heritage', 'statute', 'formula', 'element', 'fact_item')),
    headword TEXT NOT NULL,
    norm_key TEXT NOT NULL,
    reading TEXT,
    gloss_ko TEXT,
    pos TEXT,
    facet_json TEXT NOT NULL,
    facet_schema_version INTEGER NOT NULL DEFAULT 1,
    difficulty_rank INTEGER,
    source_id TEXT NOT NULL REFERENCES ref_sources(source_id),
    quality TEXT NOT NULL CHECK (quality IN ('verified', 'reviewed')),
    disputed INTEGER NOT NULL DEFAULT 0 CHECK (disputed IN (0, 1)),
    valid_from TEXT,
    valid_until TEXT,
    content_hash TEXT NOT NULL,
    retired INTEGER NOT NULL DEFAULT 0 CHECK (retired IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_ref_entries_norm ON ref_entries(norm_key);
CREATE INDEX IF NOT EXISTS ix_ref_entries_type_rank ON ref_entries(entry_type, difficulty_rank);

CREATE TABLE IF NOT EXISTS ref_aliases (
    alias_norm TEXT NOT NULL,
    entry_key TEXT NOT NULL REFERENCES ref_entries(entry_key),
    alias_kind TEXT NOT NULL
        CHECK (alias_kind IN ('variant_char', 'inflection', 'abbrev', 'old_name', 'honorific_name', 'romanization', 'ocr_confusion')),
    PRIMARY KEY (alias_norm, entry_key)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ref_collections (
    collection_id TEXT NOT NULL,
    entry_key TEXT NOT NULL REFERENCES ref_entries(entry_key),
    ordinal INTEGER NOT NULL,
    level_label TEXT NOT NULL,
    PRIMARY KEY (collection_id, entry_key),
    UNIQUE (collection_id, ordinal)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ref_relations (
    from_key TEXT NOT NULL REFERENCES ref_entries(entry_key),
    rel_type TEXT NOT NULL
        CHECK (rel_type IN ('similar_shape', 'homophone', 'same_radical', 'synonym', 'antonym', 'confusable_spelling', 'same_pos_level', 'same_era', 'same_reign', 'adjacent_time', 'same_category', 'ambiguous_abbrev', 'variant_of')),
    to_key TEXT NOT NULL REFERENCES ref_entries(entry_key),
    weight REAL NOT NULL CHECK (weight BETWEEN 0.0 AND 1.0),
    PRIMARY KEY (from_key, rel_type, to_key)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ref_changelog (
    entry_key TEXT NOT NULL REFERENCES ref_entries(entry_key),
    since_version TEXT NOT NULL,
    change_kind TEXT NOT NULL
        CHECK (change_kind IN ('added', 'cosmetic', 'errata', 'answer_changed', 'retired')),
    PRIMARY KEY (entry_key, since_version)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ref_textbooks (
    textbook_id TEXT PRIMARY KEY,
    curriculum_revision TEXT NOT NULL
        CHECK (curriculum_revision IN ('2015', '2022')),
    school_level TEXT NOT NULL
        CHECK (school_level IN ('elementary', 'middle', 'high')),
    grade INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 6),
    semester INTEGER CHECK (semester IN (1, 2)),
    subject_code TEXT NOT NULL,
    publisher_name TEXT NOT NULL,
    author_label TEXT,
    title TEXT NOT NULL,
    total_pages INTEGER CHECK (total_pages IS NULL OR total_pages > 0),
    source_id TEXT NOT NULL REFERENCES ref_sources(source_id),
    valid_school_year_from INTEGER NOT NULL,
    valid_school_year_until INTEGER,
    retired INTEGER NOT NULL DEFAULT 0 CHECK (retired IN (0, 1))
);

CREATE TABLE IF NOT EXISTS ref_curriculum_units (
    unit_id TEXT PRIMARY KEY,
    textbook_id TEXT NOT NULL REFERENCES ref_textbooks(textbook_id) ON DELETE CASCADE,
    parent_unit_id TEXT REFERENCES ref_curriculum_units(unit_id) ON DELETE CASCADE,
    depth INTEGER NOT NULL CHECK (depth BETWEEN 1 AND 3),
    unit_ordinal INTEGER NOT NULL CHECK (unit_ordinal >= 1),
    unit_code_label TEXT NOT NULL,
    unit_title TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    achievement_code TEXT,
    UNIQUE (textbook_id, unit_ordinal),
    CHECK (
        (depth = 1 AND parent_unit_id IS NULL)
        OR (depth IN (2, 3) AND parent_unit_id IS NOT NULL AND parent_unit_id != unit_id)
    ),
    CHECK (
        (page_start IS NULL AND page_end IS NULL)
        OR (page_start IS NOT NULL AND page_end IS NOT NULL AND page_start >= 1 AND page_end >= page_start)
    )
);

CREATE INDEX IF NOT EXISTS ix_ref_units_textbook_pages ON ref_curriculum_units(textbook_id, page_start, page_end);

CREATE TABLE IF NOT EXISTS ref_unit_entries (
    textbook_id TEXT NOT NULL REFERENCES ref_textbooks(textbook_id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL REFERENCES ref_curriculum_units(unit_id) ON DELETE CASCADE,
    entry_key TEXT NOT NULL REFERENCES ref_entries(entry_key),
    unit_item_ordinal INTEGER NOT NULL CHECK (unit_item_ordinal >= 1),
    page_no INTEGER CHECK (page_no IS NULL OR page_no >= 1),
    importance_tier INTEGER NOT NULL DEFAULT 1 CHECK (importance_tier IN (1, 2, 3)),
    role_in_unit TEXT NOT NULL DEFAULT 'core_vocab'
        CHECK (role_in_unit IN ('core_vocab', 'key_grammar', 'core_concept', 'timeline_event', 'formula_law', 'hanja_term', 'licensed_passage')),
    PRIMARY KEY (unit_id, entry_key),
    UNIQUE (unit_id, unit_item_ordinal)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS ix_ref_unit_entries_page ON ref_unit_entries(textbook_id, page_no);

CREATE TRIGGER IF NOT EXISTS trg_ref_units_hierarchy_insert
BEFORE INSERT ON ref_curriculum_units
WHEN NEW.parent_unit_id IS NOT NULL
  AND (
      (SELECT textbook_id FROM ref_curriculum_units WHERE unit_id = NEW.parent_unit_id) != NEW.textbook_id
      OR (SELECT depth FROM ref_curriculum_units WHERE unit_id = NEW.parent_unit_id) != NEW.depth - 1
  )
BEGIN
    SELECT RAISE(ABORT, 'textbook_unit_hierarchy_violation: parent textbook_id or depth mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_ref_units_hierarchy_update
BEFORE UPDATE OF textbook_id, parent_unit_id, depth ON ref_curriculum_units
WHEN (
    NEW.parent_unit_id IS NOT NULL
    AND (
        (SELECT textbook_id FROM ref_curriculum_units WHERE unit_id = NEW.parent_unit_id) != NEW.textbook_id
        OR (SELECT depth FROM ref_curriculum_units WHERE unit_id = NEW.parent_unit_id) != NEW.depth - 1
    )
)
OR EXISTS (
    SELECT 1 FROM ref_curriculum_units child
    WHERE child.parent_unit_id = NEW.unit_id
      AND (child.textbook_id != NEW.textbook_id OR child.depth != NEW.depth + 1)
)
OR (
    NEW.textbook_id != OLD.textbook_id
    AND EXISTS (SELECT 1 FROM ref_unit_entries rue WHERE rue.unit_id = NEW.unit_id)
)
BEGIN
    SELECT RAISE(ABORT, 'textbook_unit_hierarchy_violation: unit update breaks parent/child/entry hierarchy');
END;

CREATE TRIGGER IF NOT EXISTS trg_ref_unit_entries_integrity_insert
BEFORE INSERT ON ref_unit_entries
WHEN (SELECT textbook_id FROM ref_curriculum_units WHERE unit_id = NEW.unit_id) != NEW.textbook_id
  OR (
      NEW.role_in_unit = 'licensed_passage'
      AND (SELECT s.license_class FROM ref_entries e JOIN ref_sources s ON e.source_id = s.source_id WHERE e.entry_key = NEW.entry_key)
          NOT IN ('CONTRACT_LICENSED', 'PUBLIC_LAW_ART7', 'KOGL_1')
  )
BEGIN
    SELECT RAISE(ABORT, 'textbook_entry_violation: textbook mismatch or unlicensed textbook passage');
END;

CREATE TRIGGER IF NOT EXISTS trg_ref_unit_entries_integrity_update
BEFORE UPDATE OF textbook_id, unit_id, entry_key, role_in_unit ON ref_unit_entries
WHEN (SELECT textbook_id FROM ref_curriculum_units WHERE unit_id = NEW.unit_id) != NEW.textbook_id
  OR (
      NEW.role_in_unit = 'licensed_passage'
      AND (SELECT s.license_class FROM ref_entries e JOIN ref_sources s ON e.source_id = s.source_id WHERE e.entry_key = NEW.entry_key)
          NOT IN ('CONTRACT_LICENSED', 'PUBLIC_LAW_ART7', 'KOGL_1')
  )
BEGIN
    SELECT RAISE(ABORT, 'textbook_entry_violation: textbook mismatch or unlicensed textbook passage');
END;

CREATE TRIGGER IF NOT EXISTS trg_ref_entries_licensed_passage_update
BEFORE UPDATE OF source_id ON ref_entries
WHEN EXISTS (
    SELECT 1 FROM ref_unit_entries rue
    WHERE rue.entry_key = NEW.entry_key AND rue.role_in_unit = 'licensed_passage'
)
AND (SELECT license_class FROM ref_sources WHERE source_id = NEW.source_id)
    NOT IN ('CONTRACT_LICENSED', 'PUBLIC_LAW_ART7', 'KOGL_1')
BEGIN
    SELECT RAISE(ABORT, 'textbook_entry_violation: cannot rebind licensed_passage entry to unlicensed source');
END;

CREATE TRIGGER IF NOT EXISTS trg_ref_sources_licensed_passage_update
BEFORE UPDATE OF license_class ON ref_sources
WHEN NEW.license_class NOT IN ('CONTRACT_LICENSED', 'PUBLIC_LAW_ART7', 'KOGL_1')
  AND EXISTS (
      SELECT 1 FROM ref_entries e JOIN ref_unit_entries rue ON e.entry_key = rue.entry_key
      WHERE e.source_id = NEW.source_id AND rue.role_in_unit = 'licensed_passage'
  )
BEGIN
    SELECT RAISE(ABORT, 'textbook_entry_violation: cannot downgrade source license referenced by licensed_passage');
END;
"""


TIER_U_V2_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subject_taxonomy (
    subject_code TEXT PRIMARY KEY,
    parent_code TEXT REFERENCES subject_taxonomy(subject_code) ON DELETE SET NULL,
    display_name_ko TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learner_profiles (
    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    age_tier TEXT NOT NULL DEFAULT 'adult'
        CHECK (age_tier IN ('junior', 'teen', 'adult')),
    avatar_emoji TEXT NOT NULL DEFAULT '🧠',
    preferred_quiz_mode TEXT NOT NULL DEFAULT 'auto'
        CHECK (preferred_quiz_mode IN ('auto', 'multiple_choice', 'tap_block', 'dictation', 'free_recall')),
    cloud_vision_locked INTEGER NOT NULL DEFAULT 1
        CHECK (age_tier != 'junior' OR cloud_vision_locked = 1),
    daily_new_override INTEGER,
    daily_review_override INTEGER,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_study_day INTEGER,
    created_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256_hash TEXT NOT NULL UNIQUE,
    doc_lineage_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    local_cas_path TEXT,
    pii_redacted INTEGER NOT NULL DEFAULT 0,
    extractor_version INTEGER NOT NULL DEFAULT 1,
    imported_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_pins (
    pin_id TEXT PRIMARY KEY,
    sha256_hash TEXT NOT NULL,
    expires_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS media_files (
    sha256_hash TEXT PRIMARY KEY,
    media_kind TEXT NOT NULL DEFAULT 'asset'
        CHECK (media_kind IN ('asset', 'page_snapshot', 'occlusion_base', 'tts_audio')),
    mime_type TEXT NOT NULL,
    local_path TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    last_accessed_epoch_sec INTEGER NOT NULL,
    created_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    profile_id INTEGER NOT NULL DEFAULT 1 REFERENCES learner_profiles(profile_id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES decks(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general' REFERENCES subject_taxonomy(subject_code),
    desired_retention REAL,
    daily_new_limit INTEGER,
    daily_review_limit INTEGER,
    rollover_hour INTEGER NOT NULL DEFAULT 4,
    learning_steps_sec_json TEXT NOT NULL DEFAULT '[60, 600]',
    relearning_steps_sec_json TEXT NOT NULL DEFAULT '[600]',
    fsrs_weights_json TEXT,
    exam_target_study_day INTEGER,
    modified_at_epoch_ms INTEGER NOT NULL,
    created_at_epoch_sec INTEGER NOT NULL,
    UNIQUE(profile_id, name)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    doc_id INTEGER REFERENCES source_documents(doc_id) ON DELETE SET NULL,
    origin_kind TEXT NOT NULL DEFAULT 'doc_extracted'
        CHECK (origin_kind IN ('doc_extracted', 'pack_materialized', 'manual')),
    ref_pack_id TEXT,
    ref_entry_key TEXT,
    ref_pack_version TEXT,
    ref_content_hash TEXT,
    note_type TEXT NOT NULL
        CHECK (note_type IN ('basic', 'basic_reversed', 'cloze', 'speaking', 'dictation', 'image_occlusion')),
    pattern TEXT NOT NULL DEFAULT 'definition'
        CHECK (pattern IN ('definition', 'vocab_table', 'dictation_sentence', 'chronology_timeline', 'wrong_answer_note', 'numbered_list', 'causal_compare', 'statute_numeric', 'image_occlusion', 'hanja_char', 'idiom_cloze', 'formula_law')),
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '{"schema_version":1}',
    field_provenance_json TEXT NOT NULL DEFAULT '{}',
    user_override_json TEXT,
    textbook_id TEXT,
    curriculum_unit_id TEXT,
    textbook_page_no INTEGER CHECK (textbook_page_no IS NULL OR textbook_page_no >= 1),
    export_restricted INTEGER NOT NULL DEFAULT 0 CHECK (export_restricted IN (0, 1)),
    extra_context TEXT NOT NULL DEFAULT '',
    tags_csv TEXT NOT NULL DEFAULT '',
    marked INTEGER NOT NULL DEFAULT 0,
    source_filename TEXT NOT NULL DEFAULT '',
    source_page INTEGER NOT NULL DEFAULT 1,
    page_label TEXT,
    source_excerpt TEXT NOT NULL DEFAULT '',
    page_snapshot_sha256 TEXT REFERENCES media_files(sha256_hash) ON DELETE SET NULL,
    media_sha256 TEXT REFERENCES media_files(sha256_hash) ON DELETE SET NULL,
    modified_at_epoch_ms INTEGER NOT NULL,
    created_at_epoch_sec INTEGER NOT NULL,
    CHECK (
        (origin_kind = 'pack_materialized' AND ref_pack_id IS NOT NULL AND ref_entry_key IS NOT NULL AND ref_pack_version IS NOT NULL AND ref_content_hash IS NOT NULL)
        OR (origin_kind IN ('doc_extracted', 'manual') AND ref_pack_id IS NULL AND ref_entry_key IS NULL AND ref_pack_version IS NULL AND ref_content_hash IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_notes_ref_entry ON notes(deck_id, ref_pack_id, ref_entry_key) WHERE origin_kind = 'pack_materialized';

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'new'
        CHECK (state IN ('new', 'learning', 'review', 'relearning', 'suspended')),
    queue INTEGER NOT NULL DEFAULT 0
        CHECK (queue IN (0, 1, 2, 3, -1, -2, -3)),
    quiz_stage INTEGER NOT NULL DEFAULT 0
        CHECK (quiz_stage IN (0, 1, 2)),
    consecutive_successes INTEGER NOT NULL DEFAULT 0,
    learning_step_index INTEGER NOT NULL DEFAULT 0,
    stability REAL NOT NULL DEFAULT 0.0,
    difficulty REAL NOT NULL DEFAULT 0.0,
    due_epoch_sec INTEGER NOT NULL,
    due_study_day INTEGER NOT NULL DEFAULT 0,
    last_review_epoch_sec INTEGER,
    buried_until_study_day INTEGER,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    scheduled_days REAL NOT NULL DEFAULT 0.0,
    flags INTEGER NOT NULL DEFAULT 0,
    modified_at_epoch_ms INTEGER NOT NULL,
    UNIQUE(note_id, ord)
);

CREATE TABLE IF NOT EXISTS revlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    undo_group_id TEXT NOT NULL,
    profile_id INTEGER NOT NULL DEFAULT 1,
    card_id INTEGER NOT NULL,
    deck_id INTEGER NOT NULL,
    review_type TEXT NOT NULL DEFAULT 'normal'
        CHECK (review_type IN ('normal', 'cram', 'reschedule')),
    interaction_mode TEXT NOT NULL DEFAULT 'button_4'
        CHECK (interaction_mode IN ('button_2', 'button_4', 'multiple_choice', 'tap_block', 'dictation', 'free_recall', 'speaking', 'cloze', 'image_occlusion')),
    evidence_class TEXT NOT NULL DEFAULT 'recall'
        CHECK (evidence_class IN ('recognition', 'cued_recall', 'recall')),
    attempt_count INTEGER NOT NULL DEFAULT 1,
    hint_used INTEGER NOT NULL DEFAULT 0,
    option_count INTEGER,
    policy_version INTEGER NOT NULL DEFAULT 1,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),
    prev_state TEXT NOT NULL,
    next_state TEXT NOT NULL,
    prev_queue INTEGER NOT NULL,
    next_queue INTEGER NOT NULL,
    prev_quiz_stage INTEGER NOT NULL DEFAULT 0,
    next_quiz_stage INTEGER NOT NULL DEFAULT 0,
    prev_stability REAL NOT NULL,
    next_stability REAL NOT NULL,
    prev_difficulty REAL NOT NULL,
    next_difficulty REAL NOT NULL,
    prev_due_epoch_sec INTEGER NOT NULL,
    prev_due_study_day INTEGER NOT NULL,
    prev_last_review_epoch_sec INTEGER,
    prev_reps INTEGER NOT NULL,
    prev_lapses INTEGER NOT NULL,
    prev_scheduled_days REAL NOT NULL,
    scheduled_days REAL NOT NULL,
    elapsed_days REAL NOT NULL,
    retrievability REAL NOT NULL DEFAULT 1.0,
    review_duration_ms INTEGER NOT NULL DEFAULT 0,
    user_typed_answer TEXT,
    ai_eval_score_pct REAL,
    reviewed_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS undo_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    undo_group_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    card_id INTEGER NOT NULL,
    before_card_json TEXT NOT NULL,
    after_modified_at_epoch_ms INTEGER NOT NULL,
    created_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS study_sessions (
    session_id TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL DEFAULT 1 REFERENCES learner_profiles(profile_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    filter_query TEXT NOT NULL,
    reschedule_enabled INTEGER NOT NULL DEFAULT 0,
    created_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS study_session_items (
    session_id TEXT NOT NULL REFERENCES study_sessions(session_id) ON DELETE CASCADE,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, card_id)
);

CREATE TABLE IF NOT EXISTS graves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    sync_id TEXT NOT NULL,
    deleted_at_epoch_ms INTEGER NOT NULL,
    UNIQUE(entity_type, sync_id)
);

CREATE TABLE IF NOT EXISTS store_entitlements (
    pack_id TEXT NOT NULL,
    profile_id INTEGER NOT NULL DEFAULT 1 REFERENCES learner_profiles(profile_id) ON DELETE CASCADE,
    price_paid_krw INTEGER NOT NULL DEFAULT 0 CHECK (price_paid_krw >= 0),
    payment_channel TEXT NOT NULL DEFAULT 'braindeck_store',
    receipt_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'refunded_frozen')),
    purchased_at_epoch_sec INTEGER NOT NULL,
    PRIMARY KEY (profile_id, pack_id)
);

CREATE TABLE IF NOT EXISTS installed_packs (
    pack_id TEXT NOT NULL,
    pack_version TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    local_path TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'verified'
        CHECK (state IN ('verified', 'active', 'superseded', 'quarantined')),
    license_spdx TEXT NOT NULL,
    redistribution_allowed INTEGER NOT NULL CHECK (redistribution_allowed IN (0, 1)),
    installed_at_epoch_sec INTEGER NOT NULL,
    PRIMARY KEY (pack_id, pack_version)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_pack ON installed_packs(pack_id) WHERE state = 'active';

CREATE TABLE IF NOT EXISTS pack_activations (
    activation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    profile_id INTEGER NOT NULL REFERENCES learner_profiles(profile_id) ON DELETE CASCADE,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    pack_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    facets_csv TEXT NOT NULL DEFAULT 'default',
    next_ordinal INTEGER NOT NULL DEFAULT 1 CHECK (next_ordinal >= 1),
    version_policy TEXT NOT NULL DEFAULT 'follow_latest'
        CHECK (version_policy IN ('follow_latest', 'pinned')),
    resolved_pack_version TEXT NOT NULL,
    pinned_version TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    created_at_epoch_sec INTEGER NOT NULL,
    UNIQUE (profile_id, pack_id, collection_id),
    FOREIGN KEY (pack_id, resolved_pack_version) REFERENCES installed_packs(pack_id, pack_version) ON DELETE RESTRICT,
    CHECK (
        (version_policy = 'follow_latest' AND pinned_version IS NULL)
        OR (version_policy = 'pinned' AND pinned_version IS NOT NULL AND pinned_version = resolved_pack_version)
    )
);

CREATE TABLE IF NOT EXISTS enrichment_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    surface TEXT NOT NULL,
    candidates_json TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'pending'
        CHECK (decision IN ('pending', 'accepted', 'rejected', 'auto_applied')),
    conflict_kind TEXT
        CHECK (conflict_kind IN ('ambiguous_sense', 'multi_candidate', 'source_pack_conflict', 'ocr_fuzzy', 'disputed')),
    matcher_version INTEGER NOT NULL DEFAULT 1,
    created_at_epoch_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS exam_scopes (
    scope_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    profile_id INTEGER NOT NULL REFERENCES learner_profiles(profile_id) ON DELETE CASCADE,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    pack_id TEXT NOT NULL,
    resolved_pack_version TEXT NOT NULL,
    version_policy TEXT NOT NULL DEFAULT 'pinned'
        CHECK (version_policy IN ('follow_latest', 'pinned')),
    pinned_version TEXT,
    textbook_id TEXT NOT NULL,
    exam_study_day INTEGER,
    materialize_mode TEXT NOT NULL DEFAULT 'lazy_daily'
        CHECK (materialize_mode IN ('lazy_daily', 'eager_exam_pack')),
    max_importance_tier INTEGER NOT NULL DEFAULT 2 CHECK (max_importance_tier IN (1, 2, 3)),
    facets_csv TEXT NOT NULL DEFAULT 'default',
    include_user_scanned_notes INTEGER NOT NULL DEFAULT 1 CHECK (include_user_scanned_notes IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'archived')),
    created_at_epoch_sec INTEGER NOT NULL,
    updated_at_epoch_sec INTEGER NOT NULL,
    FOREIGN KEY (pack_id, resolved_pack_version) REFERENCES installed_packs(pack_id, pack_version) ON DELETE RESTRICT,
    CHECK (
        (version_policy = 'follow_latest' AND pinned_version IS NULL)
        OR (version_policy = 'pinned' AND pinned_version IS NOT NULL AND pinned_version = resolved_pack_version)
    )
);

CREATE TABLE IF NOT EXISTS exam_scope_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_id INTEGER NOT NULL REFERENCES exam_scopes(scope_id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL,
    include_subunits INTEGER NOT NULL DEFAULT 1 CHECK (include_subunits IN (0, 1)),
    page_start INTEGER,
    page_end INTEGER,
    CHECK (
        (page_start IS NULL AND page_end IS NULL)
        OR (page_start IS NOT NULL AND page_end IS NOT NULL AND page_start >= 1 AND page_end >= page_start)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_exam_scope_rules_whole_unit ON exam_scope_rules(scope_id, unit_id) WHERE page_start IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_exam_scope_rules_page_range ON exam_scope_rules(scope_id, unit_id, page_start, page_end) WHERE page_start IS NOT NULL;

CREATE TABLE IF NOT EXISTS exam_scope_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_id INTEGER NOT NULL REFERENCES exam_scopes(scope_id) ON DELETE CASCADE,
    item_kind TEXT NOT NULL CHECK (item_kind IN ('pack_entry', 'user_note')),
    entry_key TEXT,
    user_note_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL,
    page_no INTEGER CHECK (page_no IS NULL OR page_no >= 1),
    scope_ordinal INTEGER,
    in_scope INTEGER NOT NULL DEFAULT 1 CHECK (in_scope IN (0, 1)),
    materialized_note_id INTEGER REFERENCES notes(id) ON DELETE SET NULL,
    CHECK (
        (item_kind = 'pack_entry' AND entry_key IS NOT NULL AND user_note_id IS NULL)
        OR (item_kind = 'user_note' AND user_note_id IS NOT NULL AND entry_key IS NULL AND materialized_note_id IS NULL)
    ),
    CHECK (
        (in_scope = 1 AND scope_ordinal IS NOT NULL AND scope_ordinal >= 1)
        OR (in_scope = 0 AND scope_ordinal IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_exam_scope_items_pack_entry ON exam_scope_items(scope_id, entry_key) WHERE item_kind = 'pack_entry';
CREATE UNIQUE INDEX IF NOT EXISTS ux_exam_scope_items_user_note ON exam_scope_items(scope_id, user_note_id) WHERE item_kind = 'user_note';
CREATE UNIQUE INDEX IF NOT EXISTS ux_exam_scope_items_active_ordinal ON exam_scope_items(scope_id, scope_ordinal) WHERE in_scope = 1;

-- Cross-profile isolation & pack pin triggers (T19, T20, T28)
CREATE TRIGGER IF NOT EXISTS trg_decks_profile_immutable
BEFORE UPDATE OF profile_id ON decks
WHEN NEW.profile_id != OLD.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: deck profile_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_decks_same_profile_insert
BEFORE INSERT ON decks
WHEN NEW.parent_id IS NOT NULL AND (SELECT profile_id FROM decks WHERE id = NEW.parent_id) != NEW.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: parent deck profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_decks_same_profile_update
BEFORE UPDATE OF parent_id ON decks
WHEN NEW.parent_id IS NOT NULL AND (SELECT profile_id FROM decks WHERE id = NEW.parent_id) != NEW.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: parent deck profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_notes_same_profile_update
BEFORE UPDATE OF deck_id, origin_kind, ref_pack_id, ref_entry_key, textbook_id, curriculum_unit_id ON notes
WHEN (SELECT profile_id FROM decks WHERE id = NEW.deck_id) != (SELECT profile_id FROM decks WHERE id = OLD.deck_id)
  OR EXISTS (
      SELECT 1 FROM cards c JOIN decks d ON c.deck_id = d.id
      WHERE c.note_id = NEW.id AND d.profile_id != (SELECT profile_id FROM decks WHERE id = NEW.deck_id)
  )
  OR EXISTS (
      SELECT 1 FROM exam_scope_items esi JOIN exam_scopes es ON esi.scope_id = es.scope_id
      WHERE (esi.materialized_note_id = NEW.id OR esi.user_note_id = NEW.id)
        AND (
            es.deck_id != NEW.deck_id
            OR (
                esi.item_kind = 'user_note' AND esi.user_note_id = NEW.id
                AND (
                    NEW.origin_kind NOT IN ('doc_extracted', 'manual')
                    OR NEW.textbook_id IS NULL OR NEW.textbook_id != es.textbook_id
                    OR NEW.curriculum_unit_id IS NULL OR NEW.curriculum_unit_id != esi.unit_id
                )
            )
            OR (
                esi.item_kind = 'pack_entry' AND esi.materialized_note_id = NEW.id
                AND (
                    NEW.origin_kind != 'pack_materialized'
                    OR NEW.ref_pack_id IS NULL OR NEW.ref_pack_id != es.pack_id
                    OR NEW.ref_entry_key IS NULL OR NEW.ref_entry_key != esi.entry_key
                )
            )
        )
  )
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_or_scope_violation: note deck, origin_kind, pack/entry, or textbook/unit binding mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_cards_same_profile_insert
BEFORE INSERT ON cards
WHEN (SELECT profile_id FROM decks WHERE id = NEW.deck_id) != (SELECT d.profile_id FROM notes n JOIN decks d ON n.deck_id = d.id WHERE n.id = NEW.note_id)
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: card deck and note deck profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_cards_same_profile_update
BEFORE UPDATE OF deck_id, note_id ON cards
WHEN (SELECT profile_id FROM decks WHERE id = NEW.deck_id) != (SELECT d.profile_id FROM notes n JOIN decks d ON n.deck_id = d.id WHERE n.id = NEW.note_id)
  OR EXISTS (
      SELECT 1 FROM study_session_items ssi JOIN study_sessions ss ON ssi.session_id = ss.session_id
      WHERE ssi.card_id = NEW.id AND ss.profile_id != (SELECT profile_id FROM decks WHERE id = NEW.deck_id)
  )
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: card deck, note deck, or session profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_study_sessions_profile_immutable
BEFORE UPDATE OF profile_id ON study_sessions
WHEN NEW.profile_id != OLD.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: study_session profile_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_session_items_same_profile_insert
BEFORE INSERT ON study_session_items
WHEN (SELECT profile_id FROM study_sessions WHERE session_id = NEW.session_id) != (SELECT d.profile_id FROM cards c JOIN decks d ON c.deck_id = d.id WHERE c.id = NEW.card_id)
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: session and card profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_session_items_same_profile_update
BEFORE UPDATE OF session_id, card_id ON study_session_items
WHEN (SELECT profile_id FROM study_sessions WHERE session_id = NEW.session_id) != (SELECT d.profile_id FROM cards c JOIN decks d ON c.deck_id = d.id WHERE c.id = NEW.card_id)
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: session and card profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_pack_activations_profile_immutable
BEFORE UPDATE OF profile_id ON pack_activations
WHEN NEW.profile_id != OLD.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: pack_activation profile_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_pack_activations_same_profile_insert
BEFORE INSERT ON pack_activations
WHEN (SELECT profile_id FROM decks WHERE id = NEW.deck_id) != NEW.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: pack_activation deck profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_pack_activations_same_profile_update
BEFORE UPDATE OF deck_id ON pack_activations
WHEN (SELECT profile_id FROM decks WHERE id = NEW.deck_id) != NEW.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: pack_activation deck profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_pack_activations_require_healthy_pack_insert
BEFORE INSERT ON pack_activations
WHEN (SELECT state FROM installed_packs WHERE pack_id = NEW.pack_id AND pack_version = NEW.resolved_pack_version) NOT IN ('active', 'verified', 'superseded')
BEGIN
    SELECT RAISE(ABORT, 'invalid_pack_state: resolved_pack_version is quarantined or missing');
END;

CREATE TRIGGER IF NOT EXISTS trg_pack_activations_require_healthy_pack_update
BEFORE UPDATE OF pack_id, resolved_pack_version, status ON pack_activations
WHEN NEW.status != 'archived'
  AND (SELECT state FROM installed_packs WHERE pack_id = NEW.pack_id AND pack_version = NEW.resolved_pack_version) NOT IN ('active', 'verified', 'superseded')
BEGIN
    SELECT RAISE(ABORT, 'invalid_pack_state: resolved_pack_version is quarantined or missing');
END;

CREATE TRIGGER IF NOT EXISTS trg_exam_scopes_profile_immutable
BEFORE UPDATE OF profile_id ON exam_scopes
WHEN NEW.profile_id != OLD.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: exam_scope profile_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_exam_scopes_same_profile_insert
BEFORE INSERT ON exam_scopes
WHEN (SELECT profile_id FROM decks WHERE id = NEW.deck_id) != NEW.profile_id
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_violation: exam_scope deck profile_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_exam_scopes_same_profile_update
BEFORE UPDATE OF deck_id, pack_id, textbook_id ON exam_scopes
WHEN (SELECT profile_id FROM decks WHERE id = NEW.deck_id) != NEW.profile_id
  OR (
      NEW.deck_id != OLD.deck_id
      AND EXISTS (SELECT 1 FROM exam_scope_items WHERE scope_id = NEW.scope_id AND (materialized_note_id IS NOT NULL OR user_note_id IS NOT NULL))
  )
  OR (
      (NEW.textbook_id != OLD.textbook_id OR NEW.pack_id != OLD.pack_id)
      AND EXISTS (SELECT 1 FROM exam_scope_items WHERE scope_id = NEW.scope_id)
  )
BEGIN
    SELECT RAISE(ABORT, 'cross_profile_or_scope_violation: exam_scope deck/pack/textbook change invalidates bound scope items');
END;

CREATE TRIGGER IF NOT EXISTS trg_exam_scope_items_same_profile_insert
BEFORE INSERT ON exam_scope_items
WHEN (
    NEW.item_kind = 'pack_entry'
    AND NEW.materialized_note_id IS NOT NULL
    AND (
        (SELECT deck_id FROM exam_scopes WHERE scope_id = NEW.scope_id) != (SELECT deck_id FROM notes WHERE id = NEW.materialized_note_id)
        OR (SELECT origin_kind FROM notes WHERE id = NEW.materialized_note_id) != 'pack_materialized'
        OR (SELECT ref_pack_id FROM notes WHERE id = NEW.materialized_note_id) IS NULL
        OR (SELECT ref_pack_id FROM notes WHERE id = NEW.materialized_note_id) != (SELECT pack_id FROM exam_scopes WHERE scope_id = NEW.scope_id)
        OR (SELECT ref_entry_key FROM notes WHERE id = NEW.materialized_note_id) IS NULL
        OR (SELECT ref_entry_key FROM notes WHERE id = NEW.materialized_note_id) != NEW.entry_key
    )
)
OR (
    NEW.item_kind = 'user_note'
    AND (
        (SELECT deck_id FROM exam_scopes WHERE scope_id = NEW.scope_id) != (SELECT deck_id FROM notes WHERE id = NEW.user_note_id)
        OR (SELECT origin_kind FROM notes WHERE id = NEW.user_note_id) NOT IN ('doc_extracted', 'manual')
        OR (SELECT textbook_id FROM notes WHERE id = NEW.user_note_id) IS NULL
        OR (SELECT textbook_id FROM notes WHERE id = NEW.user_note_id) != (SELECT textbook_id FROM exam_scopes WHERE scope_id = NEW.scope_id)
        OR (SELECT curriculum_unit_id FROM notes WHERE id = NEW.user_note_id) IS NULL
        OR (SELECT curriculum_unit_id FROM notes WHERE id = NEW.user_note_id) != NEW.unit_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'scope_item_binding_violation: note deck, origin_kind, pack/entry, textbook_id, or unit_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_exam_scope_items_same_profile_update
BEFORE UPDATE OF scope_id, item_kind, entry_key, user_note_id, unit_id, materialized_note_id ON exam_scope_items
WHEN (
    NEW.item_kind = 'pack_entry'
    AND NEW.materialized_note_id IS NOT NULL
    AND (
        (SELECT deck_id FROM exam_scopes WHERE scope_id = NEW.scope_id) != (SELECT deck_id FROM notes WHERE id = NEW.materialized_note_id)
        OR (SELECT origin_kind FROM notes WHERE id = NEW.materialized_note_id) != 'pack_materialized'
        OR (SELECT ref_pack_id FROM notes WHERE id = NEW.materialized_note_id) IS NULL
        OR (SELECT ref_pack_id FROM notes WHERE id = NEW.materialized_note_id) != (SELECT pack_id FROM exam_scopes WHERE scope_id = NEW.scope_id)
        OR (SELECT ref_entry_key FROM notes WHERE id = NEW.materialized_note_id) IS NULL
        OR (SELECT ref_entry_key FROM notes WHERE id = NEW.materialized_note_id) != NEW.entry_key
    )
)
OR (
    NEW.item_kind = 'user_note'
    AND (
        (SELECT deck_id FROM exam_scopes WHERE scope_id = NEW.scope_id) != (SELECT deck_id FROM notes WHERE id = NEW.user_note_id)
        OR (SELECT origin_kind FROM notes WHERE id = NEW.user_note_id) NOT IN ('doc_extracted', 'manual')
        OR (SELECT textbook_id FROM notes WHERE id = NEW.user_note_id) IS NULL
        OR (SELECT textbook_id FROM notes WHERE id = NEW.user_note_id) != (SELECT textbook_id FROM exam_scopes WHERE scope_id = NEW.scope_id)
        OR (SELECT curriculum_unit_id FROM notes WHERE id = NEW.user_note_id) IS NULL
        OR (SELECT curriculum_unit_id FROM notes WHERE id = NEW.user_note_id) != NEW.unit_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'scope_item_binding_violation: note deck, origin_kind, pack/entry, textbook_id, or unit_id mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_exam_scopes_require_healthy_pack_insert
BEFORE INSERT ON exam_scopes
WHEN (SELECT state FROM installed_packs WHERE pack_id = NEW.pack_id AND pack_version = NEW.resolved_pack_version) NOT IN ('active', 'verified', 'superseded')
BEGIN
    SELECT RAISE(ABORT, 'invalid_pack_state: exam_scope resolved_pack_version is quarantined or missing');
END;

CREATE TRIGGER IF NOT EXISTS trg_exam_scopes_require_healthy_pack_update
BEFORE UPDATE OF pack_id, resolved_pack_version, status ON exam_scopes
WHEN NEW.status != 'archived'
  AND (SELECT state FROM installed_packs WHERE pack_id = NEW.pack_id AND pack_version = NEW.resolved_pack_version) NOT IN ('active', 'verified', 'superseded')
BEGIN
    SELECT RAISE(ABORT, 'invalid_pack_state: exam_scope resolved_pack_version is quarantined or missing');
END;

CREATE TRIGGER IF NOT EXISTS trg_installed_packs_protect_referenced_update
BEFORE UPDATE OF state ON installed_packs
WHEN NEW.state = 'quarantined' AND (
    EXISTS (
        SELECT 1 FROM pack_activations
        WHERE pack_id = NEW.pack_id AND resolved_pack_version = NEW.pack_version AND status != 'archived'
    )
    OR EXISTS (
        SELECT 1 FROM exam_scopes
        WHERE pack_id = NEW.pack_id AND resolved_pack_version = NEW.pack_version AND status != 'archived'
    )
)
BEGIN
    SELECT RAISE(ABORT, 'pack_in_use: archive or re-resolve pack_activations/exam_scopes before quarantining');
END;
"""


DEFAULT_SUBJECT_TAXONOMY: tuple[tuple[str, str | None, str], ...] = (
    ("general", None, "일반"),
    ("k12_korean", None, "국어"),
    ("k12_math", None, "수학"),
    ("k12_social", None, "사회"),
    ("social", "k12_social", "사회/역사"),
    ("k12_science", None, "과학"),
    ("science", "k12_science", "통합과학"),
    ("language", None, "어학/외국어"),
    ("english", "language", "영어"),
    ("hanja", None, "한자/어휘"),
    ("korean_history", None, "한국사"),
    ("history", "k12_social", "역사"),
    ("law", None, "법학/공무원"),
    ("medical", None, "의학/간호"),
    ("engineering", None, "공학/반도체"),
    ("exam", None, "자격증/수험"),
    ("cert_it", "exam", "IT 자격증"),
    ("civil_service", "exam", "공무원 시험"),
)


class ReferencePackBuilder:
    """Builds and validates a read-only `Tier R` SQLite Reference Pack (T21, T22, T27)."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def init_schema(
        self,
        *,
        pack_id: str,
        pack_version: str,
        domain: str,
        license_spdx: str,
        redistribution_allowed: bool,
        attribution_text: str,
        built_at_epoch_sec: int = 1792483200,
    ) -> None:
        if any(bad in license_spdx.upper() for bad in ("-NC", "-ND", "UNKNOWN", "PROPRIETARY")):
            raise LicensePolicyError(f"Non-allowlisted SPDX license for Tier R pack: {license_spdx}")
        self.conn.executescript(TIER_R_SCHEMA_SQL)
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO pack_meta (
                    pack_id, pack_version, pack_schema_version, domain,
                    license_spdx, redistribution_allowed, modification_allowed,
                    attribution_text, content_sha256, min_app_schema, built_at_epoch_sec
                ) VALUES (?, ?, 1, ?, ?, ?, 1, ?, ?, 2, ?)
                """,
                (
                    pack_id,
                    pack_version,
                    domain,
                    license_spdx,
                    1 if redistribution_allowed else 0,
                    attribution_text,
                    "0" * 64,
                    built_at_epoch_sec,
                ),
            )

    def add_source(
        self,
        *,
        source_id: str,
        title: str,
        publisher: str,
        license_class: str,
        snapshot_sha256: str,
        url: str | None = None,
        retrieved_at_epoch_sec: int = 1792483200,
    ) -> None:
        if license_class not in ALLOWED_SOURCE_LICENSES:
            raise LicensePolicyError(f"Disallowed source license_class: {license_class}")
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO ref_sources (
                    source_id, title, publisher, url, license_class, snapshot_sha256, retrieved_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source_id, title, publisher, url, license_class, snapshot_sha256, retrieved_at_epoch_sec),
            )

    def add_entry(
        self,
        *,
        entry_key: str,
        entry_type: str,
        headword: str,
        norm_key: str,
        gloss_ko: str,
        facet_json: Mapping[str, Any],
        source_id: str,
        reading: str | None = None,
        pos: str | None = None,
        difficulty_rank: int = 1,
        quality: str = "verified",
        disputed: bool = False,
        valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> str:
        compat_res = preserve_cjk_compat_before_nfc(headword)
        norm_headword = compat_res.nfc_text
        compat_cps = compat_res.compat_codepoints
        facet_payload = dict(facet_json)
        facet_payload.setdefault("facet_schema_version", 1)
        if compat_cps and "compat_codepoints" not in facet_payload:
            facet_payload["compat_codepoints"] = list(compat_cps)
        canonical_facet = json.dumps(facet_payload, ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(
            f"{entry_key}\0{norm_headword}\0{gloss_ko}\0{canonical_facet}".encode("utf-8")
        ).hexdigest()
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO ref_entries (
                    entry_key, entry_type, headword, norm_key, reading, gloss_ko, pos,
                    facet_json, facet_schema_version, difficulty_rank, source_id,
                    quality, disputed, valid_from, valid_until, content_hash, retired
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    entry_key,
                    entry_type,
                    headword,
                    norm_key.strip().lower(),
                    reading,
                    gloss_ko,
                    pos,
                    canonical_facet,
                    difficulty_rank,
                    source_id,
                    quality,
                    1 if disputed else 0,
                    valid_from,
                    valid_until,
                    content_hash,
                ),
            )
        return content_hash

    def add_collection_item(
        self,
        *,
        collection_id: str,
        entry_key: str,
        ordinal: int,
        level_label: str,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO ref_collections (collection_id, entry_key, ordinal, level_label)
                VALUES (?, ?, ?, ?)
                """,
                (collection_id, entry_key, ordinal, level_label),
            )

    def add_relation(
        self,
        *,
        from_key: str,
        rel_type: str,
        to_key: str,
        weight: float = 0.85,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO ref_relations (from_key, rel_type, to_key, weight)
                VALUES (?, ?, ?, ?)
                """,
                (from_key, rel_type, to_key, weight),
            )

    def add_textbook(
        self,
        *,
        textbook_id: str,
        curriculum_revision: str,
        school_level: str,
        grade: int,
        semester: int | None,
        subject_code: str,
        publisher_name: str,
        author_label: str | None,
        title: str,
        total_pages: int | None,
        source_id: str,
        valid_school_year_from: int,
        valid_school_year_until: int | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO ref_textbooks (
                    textbook_id, curriculum_revision, school_level, grade, semester,
                    subject_code, publisher_name, author_label, title, total_pages,
                    source_id, valid_school_year_from, valid_school_year_until, retired
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    textbook_id,
                    curriculum_revision,
                    school_level,
                    grade,
                    semester,
                    subject_code,
                    publisher_name,
                    author_label,
                    title,
                    total_pages,
                    source_id,
                    valid_school_year_from,
                    valid_school_year_until,
                ),
            )

    def add_curriculum_unit(
        self,
        *,
        unit_id: str,
        textbook_id: str,
        parent_unit_id: str | None,
        depth: int,
        unit_ordinal: int,
        unit_code_label: str,
        unit_title: str,
        page_start: int | None = None,
        page_end: int | None = None,
        achievement_code: str | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO ref_curriculum_units (
                    unit_id, textbook_id, parent_unit_id, depth, unit_ordinal,
                    unit_code_label, unit_title, page_start, page_end, achievement_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unit_id,
                    textbook_id,
                    parent_unit_id,
                    depth,
                    unit_ordinal,
                    unit_code_label,
                    unit_title,
                    page_start,
                    page_end,
                    achievement_code,
                ),
            )

    def add_unit_entry(
        self,
        *,
        textbook_id: str,
        unit_id: str,
        entry_key: str,
        unit_item_ordinal: int,
        page_no: int | None,
        importance_tier: int = 1,
        role_in_unit: str = "core_vocab",
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO ref_unit_entries (
                    textbook_id, unit_id, entry_key, unit_item_ordinal,
                    page_no, importance_tier, role_in_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    textbook_id,
                    unit_id,
                    entry_key,
                    unit_item_ordinal,
                    page_no,
                    importance_tier,
                    role_in_unit,
                ),
            )

    def finalize_pack(self) -> dict[str, Any]:
        """Compute deterministic content_sha256, run integrity checks, and return pack metadata."""
        rows = self.conn.execute(
            "SELECT entry_key, content_hash FROM ref_entries ORDER BY entry_key ASC"
        ).fetchall()
        digest = hashlib.sha256()
        for r in rows:
            digest.update(f"{r['entry_key']}:{r['content_hash']}\n".encode("utf-8"))
        content_sha256 = digest.hexdigest()
        with self.conn:
            self.conn.execute("UPDATE pack_meta SET content_sha256 = ?", (content_sha256,))
        fk_errors = self.conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise sqlite3.IntegrityError(f"foreign_key_check failed: {fk_errors}")
        meta = dict(self.conn.execute("SELECT * FROM pack_meta LIMIT 1").fetchone())
        self.conn.close()
        file_sha256 = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        meta["file_sha256"] = file_sha256
        return meta


class TierULedgerStore:
    """User Ledger v2 SQLite store (`Tier U`) with Multi-Profile, Lazy Pack Materialization & Exam Scopes."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _write_tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(TIER_U_V2_SCHEMA_SQL)
                ent_cols = {
                    str(r["name"])
                    for r in conn.execute("PRAGMA table_info(store_entitlements)").fetchall()
                }
                if "status" not in ent_cols:
                    conn.execute(
                        "ALTER TABLE store_entitlements ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                    )
                conn.execute("BEGIN IMMEDIATE")
                for code, parent_code, label in DEFAULT_SUBJECT_TAXONOMY:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO subject_taxonomy (subject_code, parent_code, display_name_ko)
                        VALUES (?, ?, ?)
                        """,
                        (code, parent_code, label),
                    )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO learner_profiles (
                        profile_id, sync_id, name, age_tier, avatar_emoji,
                        preferred_quiz_mode, cloud_vision_locked, created_at_epoch_sec
                    ) VALUES (1, 'profile-default-1', '기본 학습자', 'adult', '🧠', 'auto', 1, 1792483200)
                    """
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO store_entitlements (
                        pack_id, profile_id, price_paid_krw, payment_channel,
                        receipt_hash, purchased_at_epoch_sec
                    ) VALUES ('pack.free.starter_k12', 1, 0, 'starter_default', 'free-starter-seed', 1792483200)
                    """
                )
                conn.execute("COMMIT")
            finally:
                conn.close()

    def list_unlocked_pack_ids(self, profile_id: int = 1) -> list[str]:
        """Return all active unlocked BrainPack IDs for a learner profile (excludes refunded_frozen, T31)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT pack_id FROM store_entitlements WHERE profile_id = ? AND status = 'active' ORDER BY purchased_at_epoch_sec ASC",
                (profile_id,),
            ).fetchall()
            unlocked = ["pack.free.starter_k12"]
            for r in rows:
                pid = str(r["pack_id"])
                if pid not in unlocked:
                    unlocked.append(pid)
            return unlocked
        finally:
            conn.close()

    def list_refunded_pack_ids(self, profile_id: int = 1) -> list[str]:
        """Return all `refunded_frozen` BrainPack IDs for a learner profile (Invariant I-1 / AC-1)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT pack_id FROM store_entitlements WHERE profile_id = ? AND status = 'refunded_frozen' ORDER BY purchased_at_epoch_sec ASC",
                (profile_id,),
            ).fetchall()
            return [str(r["pack_id"]) for r in rows]
        finally:
            conn.close()

    def get_profile_info(self, profile_id: int = 1) -> dict[str, Any]:
        """Return learner profile metadata including age_tier and cloud_vision_locked (T19)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM learner_profiles WHERE profile_id = ?",
                (int(profile_id),),
            ).fetchone()
            if row is None:
                return {
                    "profile_id": int(profile_id),
                    "age_tier": "adult",
                    "cloud_vision_locked": True,
                }
            return {
                "profile_id": int(row["profile_id"]),
                "name": str(row["name"]),
                "age_tier": str(row["age_tier"]),
                "cloud_vision_locked": bool(row["cloud_vision_locked"]),
            }
        finally:
            conn.close()

    def update_profile_age_tier(
        self,
        *,
        age_tier: str,
        profile_id: int = 1,
    ) -> dict[str, Any]:
        """Update learner profile `age_tier` ('junior' | 'teen' | 'adult') and enforce Junior cloud lock (T19)."""
        tier_norm = str(age_tier or "").strip().lower()
        if tier_norm not in ("junior", "teen", "adult"):
            raise ValueError(f"age_tier must be 'junior', 'teen', or 'adult'; got {age_tier!r}")
        locked_val = 1 if tier_norm == "junior" else 0
        with self._write_tx() as conn:
            conn.execute(
                """
                UPDATE learner_profiles
                SET age_tier = ?, cloud_vision_locked = ?
                WHERE profile_id = ?
                """,
                (tier_norm, locked_val, int(profile_id)),
            )
        return self.get_profile_info(profile_id=profile_id)

    def purchase_store_pack(
        self,
        *,
        pack_id: str,
        profile_id: int = 1,
        price_paid_krw: int = 0,
        payment_channel: str = "braindeck_store",
    ) -> dict[str, Any]:
        """Atomically record a BrainPack Store entitlement in `Tier U` SQLite (or reactivate a refunded_frozen pack)."""
        now_sec = int(datetime.now(timezone.utc).timestamp())
        receipt_hash = hashlib.sha256(
            f"{profile_id}:{pack_id}:{payment_channel}:{now_sec}".encode("utf-8")
        ).hexdigest()
        with self._write_tx() as conn:
            existing = conn.execute(
                "SELECT * FROM store_entitlements WHERE profile_id = ? AND pack_id = ?",
                (profile_id, pack_id),
            ).fetchone()
            if existing is not None and str(existing["status"]) == "active":
                return {
                    "ok": True,
                    "pack_id": pack_id,
                    "profile_id": profile_id,
                    "already_purchased": True,
                    "status": "active",
                    "price_paid_krw": int(existing["price_paid_krw"]),
                    "receipt_hash": str(existing["receipt_hash"]),
                    "purchased_at_epoch_sec": int(existing["purchased_at_epoch_sec"]),
                }
            if existing is not None and str(existing["status"]) == "refunded_frozen":
                conn.execute(
                    """
                    UPDATE store_entitlements
                    SET status = 'active', price_paid_krw = ?, payment_channel = ?, receipt_hash = ?, purchased_at_epoch_sec = ?
                    WHERE profile_id = ? AND pack_id = ?
                    """,
                    (max(0, int(price_paid_krw)), payment_channel, receipt_hash, now_sec, profile_id, pack_id),
                )
                return {
                    "ok": True,
                    "pack_id": pack_id,
                    "profile_id": profile_id,
                    "already_purchased": False,
                    "reactivated_from_refund": True,
                    "status": "active",
                    "price_paid_krw": max(0, int(price_paid_krw)),
                    "receipt_hash": receipt_hash,
                    "purchased_at_epoch_sec": now_sec,
                }
            conn.execute(
                """
                INSERT INTO store_entitlements (
                    pack_id, profile_id, price_paid_krw, payment_channel,
                    receipt_hash, status, purchased_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                (pack_id, profile_id, max(0, int(price_paid_krw)), payment_channel, receipt_hash, now_sec),
            )
            return {
                "ok": True,
                "pack_id": pack_id,
                "profile_id": profile_id,
                "already_purchased": False,
                "status": "active",
                "price_paid_krw": max(0, int(price_paid_krw)),
                "receipt_hash": receipt_hash,
                "purchased_at_epoch_sec": now_sec,
            }

    def freeze_refunded_pack(
        self,
        *,
        pack_id: str,
        profile_id: int = 1,
    ) -> dict[str, Any]:
        """Transition an entitlement to `refunded_frozen` (T31: preserve FSRS history, block new materialization)."""
        if pack_id == "pack.free.starter_k12":
            raise ValueError("Cannot refund the free starter pack")
        with self._write_tx() as conn:
            existing = conn.execute(
                "SELECT * FROM store_entitlements WHERE profile_id = ? AND pack_id = ?",
                (profile_id, pack_id),
            ).fetchone()
            if existing is None:
                raise KeyError(f"Entitlement not found for pack_id={pack_id}")
            already_frozen = str(existing["status"]) == "refunded_frozen"
            if not already_frozen:
                conn.execute(
                    "UPDATE store_entitlements SET status = 'refunded_frozen' WHERE profile_id = ? AND pack_id = ?",
                    (profile_id, pack_id),
                )
            return {
                "ok": True,
                "pack_id": pack_id,
                "profile_id": profile_id,
                "status": "refunded_frozen",
                "already_frozen": already_frozen,
                "refund_amount_krw": int(existing["price_paid_krw"]),
                "fsrs_history_preserved": True,
            }

    def create_profile(
        self,
        *,
        name: str,
        age_tier: str,
        avatar_emoji: str = "🌱",
        preferred_quiz_mode: str = "auto",
        cloud_vision_locked: bool | None = None,
    ) -> int:
        locked_val = 1 if (age_tier == "junior" or cloud_vision_locked is not False) else 0
        now_sec = int(datetime.now(timezone.utc).timestamp())
        with self._write_tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO learner_profiles (
                    sync_id, name, age_tier, avatar_emoji, preferred_quiz_mode,
                    cloud_vision_locked, created_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"profile-{uuid.uuid4().hex[:12]}",
                    name,
                    age_tier,
                    avatar_emoji,
                    preferred_quiz_mode,
                    locked_val,
                    now_sec,
                ),
            )
            return int(cur.lastrowid)

    def create_deck(
        self,
        *,
        profile_id: int,
        name: str,
        category: str = "general",
        parent_id: int | None = None,
        desired_retention: float | None = None,
    ) -> int:
        now_sec = int(datetime.now(timezone.utc).timestamp())
        with self._write_tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO decks (
                    sync_id, profile_id, parent_id, name, category,
                    desired_retention, modified_at_epoch_ms, created_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"deck-{uuid.uuid4().hex[:12]}",
                    profile_id,
                    parent_id,
                    name,
                    category,
                    desired_retention,
                    now_sec * 1000,
                    now_sec,
                ),
            )
            return int(cur.lastrowid)

    def register_installed_pack(
        self,
        *,
        pack_id: str,
        pack_version: str,
        file_sha256: str,
        content_sha256: str,
        local_path: str,
        license_spdx: str,
        redistribution_allowed: bool,
        promote_active: bool = True,
    ) -> None:
        now_sec = int(datetime.now(timezone.utc).timestamp())
        with self._write_tx() as conn:
            if promote_active:
                conn.execute(
                    "UPDATE installed_packs SET state = 'superseded' WHERE pack_id = ? AND state = 'active'",
                    (pack_id,),
                )
            conn.execute(
                """
                INSERT INTO installed_packs (
                    pack_id, pack_version, file_sha256, content_sha256, local_path,
                    state, license_spdx, redistribution_allowed, installed_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pack_id, pack_version) DO UPDATE SET
                    file_sha256 = excluded.file_sha256,
                    content_sha256 = excluded.content_sha256,
                    local_path = excluded.local_path,
                    state = excluded.state,
                    license_spdx = excluded.license_spdx,
                    redistribution_allowed = excluded.redistribution_allowed,
                    installed_at_epoch_sec = excluded.installed_at_epoch_sec
                """,
                (
                    pack_id,
                    pack_version,
                    file_sha256,
                    content_sha256,
                    local_path,
                    "active" if promote_active else "verified",
                    license_spdx,
                    1 if redistribution_allowed else 0,
                    now_sec,
                ),
            )

    def activate_pack_collection(
        self,
        *,
        profile_id: int,
        deck_id: int,
        pack_id: str,
        collection_id: str,
        facets_csv: str = "default",
        version_policy: str = "follow_latest",
        pinned_version: str | None = None,
    ) -> int:
        now_sec = int(datetime.now(timezone.utc).timestamp())
        with self._write_tx() as conn:
            if version_policy == "pinned" and pinned_version:
                resolved_ver = pinned_version
            else:
                row = conn.execute(
                    "SELECT pack_version FROM installed_packs WHERE pack_id = ? AND state = 'active'",
                    (pack_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"No active installed pack found for {pack_id}")
                resolved_ver = str(row["pack_version"])
            cur = conn.execute(
                """
                INSERT INTO pack_activations (
                    sync_id, profile_id, deck_id, pack_id, collection_id, facets_csv,
                    next_ordinal, version_policy, resolved_pack_version, pinned_version,
                    status, created_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'active', ?)
                """,
                (
                    f"act-{uuid.uuid4().hex[:12]}",
                    profile_id,
                    deck_id,
                    pack_id,
                    collection_id,
                    facets_csv,
                    version_policy,
                    resolved_ver,
                    pinned_version,
                    now_sec,
                ),
            )
            return int(cur.lastrowid)

    def _materialize_ref_entry_into_tx(
        self,
        conn: sqlite3.Connection,
        *,
        deck_id: int,
        deck_sync_id: str,
        pack_id: str,
        pack_version: str,
        redistribution_allowed: bool,
        entry_row: sqlite3.Row,
        textbook_id: str | None = None,
        curriculum_unit_id: str | None = None,
        textbook_page_no: int | None = None,
        difficulty_level: str = "standard",
        now_sec: int = 1792483200,
    ) -> dict[str, Any]:
        entry_key = str(entry_row["entry_key"])
        entry_type = str(entry_row["entry_type"])
        headword = str(entry_row["headword"])
        gloss_ko = str(entry_row["gloss_ko"] or "")
        reading = str(entry_row["reading"] or "")
        ref_hash = str(entry_row["content_hash"])
        facet_raw = str(entry_row["facet_json"])
        try:
            facet_obj = json.loads(facet_raw) if facet_raw else {}
        except Exception:
            facet_obj = {}

        pattern_map = {
            "hanja_char": "hanja_char",
            "idiom": "idiom_cloze",
            "event": "chronology_timeline",
            "person": "chronology_timeline",
            "treaty": "chronology_timeline",
            "heritage": "chronology_timeline",
            "statute": "statute_numeric",
            "formula": "formula_law",
            "element": "formula_law",
        }
        pattern = pattern_map.get(entry_type, "vocab_table")
        default_front = str(facet_obj.get("clean_front") or headword)
        default_back = f"{gloss_ko} ({reading})" if reading else gloss_ko
        extra_context = str(facet_obj.get("extra_explanation") or "")

        diff_norm = (difficulty_level or "standard").strip().lower()
        if diff_norm == "lv1" and facet_obj.get("lv1_front") and facet_obj.get("lv1_back"):
            front = str(facet_obj["lv1_front"])
            back = str(facet_obj["lv1_back"])
        elif diff_norm == "lv2" and facet_obj.get("lv2_front") and facet_obj.get("lv2_back"):
            front = str(facet_obj["lv2_front"])
            back = str(facet_obj["lv2_back"])
        elif diff_norm == "lv3" and facet_obj.get("lv3_front") and facet_obj.get("lv3_back"):
            front = str(facet_obj["lv3_front"])
            back = str(facet_obj["lv3_back"])
        else:
            front = default_front
            back = default_back

        resolved_note_type = "cloze" if "{{c" in front else "basic"
        tags_list = [entry_type, diff_norm]
        if textbook_id:
            tags_list.append(textbook_id)
        if curriculum_unit_id:
            tags_list.append(curriculum_unit_id)
        tags_csv = ",".join(dict.fromkeys(t for t in tags_list if t))

        guid = hashlib.sha256(f"{deck_sync_id}||{pack_id}||{entry_key}".encode("utf-8")).hexdigest()[:16]
        content_hash = hashlib.sha256(f"{front}\0{back}\0{facet_raw}".encode("utf-8")).hexdigest()
        provenance = json.dumps(
            {
                "front": {
                    "kind": "ref_pack",
                    "pack_id": pack_id,
                    "pack_version": pack_version,
                    "entry_key": entry_key,
                    "content_hash": ref_hash,
                    "source_id": str(entry_row["source_id"]),
                },
                "back": {
                    "kind": "ref_pack",
                    "pack_id": pack_id,
                    "pack_version": pack_version,
                    "entry_key": entry_key,
                    "content_hash": ref_hash,
                    "source_id": str(entry_row["source_id"]),
                },
            },
            ensure_ascii=False,
        )

        existing = conn.execute(
            """
            SELECT id, user_override_json FROM notes
            WHERE deck_id = ? AND origin_kind = 'pack_materialized'
              AND ref_pack_id = ? AND ref_entry_key = ?
            """,
            (deck_id, pack_id, entry_key),
        ).fetchone()

        if existing is not None:
            note_id = int(existing["id"])
            overrides = json.loads(existing["user_override_json"] or "{}")
            new_front = front if "front" not in overrides else None
            new_back = back if "back" not in overrides else None
            conn.execute(
                """
                UPDATE notes
                SET front = COALESCE(?, front),
                    back = COALESCE(?, back),
                    note_type = ?,
                    extra_context = ?,
                    tags_csv = ?,
                    ref_pack_version = ?,
                    ref_content_hash = ?,
                    modified_at_epoch_ms = ?
                WHERE id = ?
                """,
                (new_front, new_back, resolved_note_type, extra_context, tags_csv, pack_version, ref_hash, now_sec * 1000, note_id),
            )
            return {
                "note_id": note_id,
                "ref_entry_key": entry_key,
                "front": front,
                "back": back,
                "created_new": False,
            }

        cur = conn.execute(
            """
            INSERT INTO notes (
                guid, content_hash, deck_id, origin_kind,
                ref_pack_id, ref_entry_key, ref_pack_version, ref_content_hash,
                note_type, pattern, front, back, fields_json, field_provenance_json,
                textbook_id, curriculum_unit_id, textbook_page_no, export_restricted,
                extra_context, tags_csv,
                modified_at_epoch_ms, created_at_epoch_sec
            ) VALUES (?, ?, ?, 'pack_materialized', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guid,
                content_hash,
                deck_id,
                pack_id,
                entry_key,
                pack_version,
                ref_hash,
                resolved_note_type,
                pattern,
                front,
                back,
                facet_raw,
                provenance,
                textbook_id,
                curriculum_unit_id,
                textbook_page_no,
                0 if redistribution_allowed else 1,
                extra_context,
                tags_csv,
                now_sec * 1000,
                now_sec,
            ),
        )
        note_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO cards (
                sync_id, note_id, deck_id, ord, state, queue, quiz_stage,
                consecutive_successes, due_epoch_sec, due_study_day, modified_at_epoch_ms
            ) VALUES (?, ?, ?, 1, 'new', 0, 0, 0, ?, 0, ?)
            """,
            (
                f"card-{uuid.uuid4().hex[:12]}",
                note_id,
                deck_id,
                now_sec,
                now_sec * 1000,
            ),
        )
        return {
            "note_id": note_id,
            "ref_entry_key": entry_key,
            "front": front,
            "back": back,
            "created_new": True,
        }

    def materialize_daily_pack_cards(
        self,
        *,
        activation_id: int,
        pack_db_path: str | Path,
        daily_new_limit: int,
        as_of_date: str | None = None,
        difficulty_level: str = "standard",
    ) -> list[dict[str, Any]]:
        """Materialize up to `daily_new_limit` cards from `Tier R` in one `BEGIN IMMEDIATE` transaction (T20)."""
        if daily_new_limit <= 0:
            return []
        pack_conn = sqlite3.connect(f"file:{Path(pack_db_path)}?mode=ro", uri=True)
        pack_conn.row_factory = sqlite3.Row
        now_sec = int(datetime.now(timezone.utc).timestamp())
        materialized: list[dict[str, Any]] = []
        try:
            with self._write_tx() as conn:
                act = conn.execute(
                    """
                    SELECT pa.*, d.sync_id AS deck_sync_id, ip.redistribution_allowed
                    FROM pack_activations pa
                    JOIN decks d ON pa.deck_id = d.id
                    JOIN installed_packs ip ON pa.pack_id = ip.pack_id AND pa.resolved_pack_version = ip.pack_version
                    WHERE pa.activation_id = ? AND pa.status = 'active'
                    """,
                    (activation_id,),
                ).fetchone()
                if act is None:
                    return []
                next_ord = int(act["next_ordinal"])
                collection_id = str(act["collection_id"])
                deck_id = int(act["deck_id"])
                deck_sync_id = str(act["deck_sync_id"])
                pack_id = str(act["pack_id"])
                pack_version = str(act["resolved_pack_version"])
                redistribution_allowed = bool(act["redistribution_allowed"])

                ref_rows = pack_conn.execute(
                    """
                    SELECT rc.ordinal, re.*
                    FROM ref_collections rc
                    JOIN ref_entries re ON rc.entry_key = re.entry_key
                    WHERE rc.collection_id = ?
                      AND rc.ordinal >= ?
                      AND re.retired = 0
                      AND ( ? IS NULL OR (
                            (re.valid_from IS NULL OR re.valid_from <= ?)
                            AND (re.valid_until IS NULL OR re.valid_until >= ?)
                      ))
                    ORDER BY rc.ordinal ASC
                    """,
                    (collection_id, next_ord, as_of_date, as_of_date, as_of_date),
                ).fetchall()

                max_ord_seen = next_ord - 1
                for idx_row, row in enumerate(ref_rows):
                    if len(materialized) >= daily_new_limit:
                        break
                    max_ord_seen = int(row["ordinal"])
                    eff_diff = difficulty_level
                    if difficulty_level in ("mixed", "all"):
                        eff_diff = ("lv1", "lv2", "lv3")[idx_row % 3]
                    item = self._materialize_ref_entry_into_tx(
                        conn,
                        deck_id=deck_id,
                        deck_sync_id=deck_sync_id,
                        pack_id=pack_id,
                        pack_version=pack_version,
                        redistribution_allowed=redistribution_allowed,
                        entry_row=row,
                        difficulty_level=eff_diff,
                        now_sec=now_sec,
                    )
                    if item["created_new"]:
                        materialized.append(item)

                if max_ord_seen >= next_ord:
                    conn.execute(
                        "UPDATE pack_activations SET next_ordinal = ? WHERE activation_id = ?",
                        (max_ord_seen + 1, activation_id),
                    )
        finally:
            pack_conn.close()
        return materialized

    def add_user_textbook_note(
        self,
        *,
        deck_id: int,
        front: str,
        back: str,
        textbook_id: str,
        curriculum_unit_id: str,
        textbook_page_no: int | None = None,
        note_type: str | None = None,
        origin_kind: str = "doc_extracted",
    ) -> int:
        """Add a student-scanned textbook/handout note with `export_restricted = 1` (T27 Layer B)."""
        now_sec = int(datetime.now(timezone.utc).timestamp())
        resolved_type = note_type or ("cloze" if "{{c" in front else "basic")
        guid = hashlib.sha256(
            f"{deck_id}||{textbook_id}||{curriculum_unit_id}||{front}".encode("utf-8")
        ).hexdigest()[:16]
        content_hash = hashlib.sha256(f"{front}\0{back}".encode("utf-8")).hexdigest()
        with self._write_tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO notes (
                    guid, content_hash, deck_id, origin_kind, note_type, pattern,
                    front, back, textbook_id, curriculum_unit_id, textbook_page_no,
                    export_restricted, modified_at_epoch_ms, created_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, 'definition', ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    guid,
                    content_hash,
                    deck_id,
                    origin_kind,
                    resolved_type,
                    front,
                    back,
                    textbook_id,
                    curriculum_unit_id,
                    textbook_page_no,
                    now_sec * 1000,
                    now_sec,
                ),
            )
            note_id = int(cur.lastrowid)
            ordinals = extract_cloze_ordinals(front) if resolved_type == "cloze" else [1]
            for ord_idx in ordinals:
                conn.execute(
                    """
                    INSERT INTO cards (
                        sync_id, note_id, deck_id, ord, state, queue, quiz_stage,
                        consecutive_successes, due_epoch_sec, due_study_day, modified_at_epoch_ms
                    ) VALUES (?, ?, ?, ?, 'new', 0, 0, 0, ?, 0, ?)
                    """,
                    (
                        f"card-{uuid.uuid4().hex[:12]}",
                        note_id,
                        deck_id,
                        ord_idx,
                        now_sec,
                        now_sec * 1000,
                    ),
                )
            return note_id

    def delete_note(self, note_id: int) -> None:
        with self._write_tx() as conn:
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    def create_exam_scope(
        self,
        *,
        profile_id: int,
        deck_id: int,
        title: str,
        pack_id: str,
        resolved_pack_version: str,
        textbook_id: str,
        exam_study_day: int | None = None,
        max_importance_tier: int = 2,
        include_user_scanned_notes: bool = True,
        rules: Sequence[Mapping[str, Any]] = (),
    ) -> int:
        now_sec = int(datetime.now(timezone.utc).timestamp())
        with self._write_tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO exam_scopes (
                    sync_id, profile_id, deck_id, title, pack_id, resolved_pack_version,
                    version_policy, pinned_version, textbook_id, exam_study_day,
                    materialize_mode, max_importance_tier, facets_csv,
                    include_user_scanned_notes, status, created_at_epoch_sec, updated_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, ?, 'pinned', ?, ?, ?, 'lazy_daily', ?, 'default', ?, 'active', ?, ?)
                """,
                (
                    f"scope-{uuid.uuid4().hex[:12]}",
                    profile_id,
                    deck_id,
                    title,
                    pack_id,
                    resolved_pack_version,
                    resolved_pack_version,
                    textbook_id,
                    exam_study_day,
                    max_importance_tier,
                    1 if include_user_scanned_notes else 0,
                    now_sec,
                    now_sec,
                ),
            )
            scope_id = int(cur.lastrowid)
            self._insert_scope_rules_tx(conn, scope_id, rules)
            return scope_id

    def _insert_scope_rules_tx(
        self,
        conn: sqlite3.Connection,
        scope_id: int,
        rules: Sequence[Mapping[str, Any]],
    ) -> None:
        for rule in rules:
            conn.execute(
                """
                INSERT INTO exam_scope_rules (
                    scope_id, unit_id, include_subunits, page_start, page_end
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    scope_id,
                    str(rule["unit_id"]),
                    1 if rule.get("include_subunits", True) else 0,
                    rule.get("page_start"),
                    rule.get("page_end"),
                ),
            )

    def update_exam_scope_rules(
        self,
        *,
        scope_id: int,
        rules: Sequence[Mapping[str, Any]],
    ) -> None:
        now_sec = int(datetime.now(timezone.utc).timestamp())
        with self._write_tx() as conn:
            conn.execute("DELETE FROM exam_scope_rules WHERE scope_id = ?", (scope_id,))
            self._insert_scope_rules_tx(conn, scope_id, rules)
            conn.execute(
                "UPDATE exam_scopes SET updated_at_epoch_sec = ? WHERE scope_id = ?",
                (now_sec, scope_id),
            )

    def resolve_and_reconcile_exam_scope(
        self,
        *,
        scope_id: int,
        pack_db_path: str | Path,
        as_of_date: str | None = None,
        materialize_now: bool = True,
        difficulty_level: str = "standard",
    ) -> list[dict[str, Any]]:
        """Resolve `Tier R` pack entries + `Tier U` scanned textbook notes and reconcile `exam_scope_items` (T28).

        Invariants:
        1. Recursive subunit expansion (`WITH RECURSIVE selected_units`) supports disjoint units
           and multiple disjoint page ranges within one unit.
        2. Before renumbering `scope_ordinal = 1..N`, resets `in_scope = 0, scope_ordinal = NULL`
           to prevent transient unique collisions on `ux_exam_scope_items_active_ordinal`.
        3. Never overwrites `cards.queue` or `cards.state` when narrowing/expanding the scope.
        """
        pack_conn = sqlite3.connect(f"file:{Path(pack_db_path)}?mode=ro", uri=True)
        pack_conn.row_factory = sqlite3.Row
        now_sec = int(datetime.now(timezone.utc).timestamp())
        try:
            with self._write_tx() as conn:
                scope = conn.execute(
                    """
                    SELECT es.*, d.sync_id AS deck_sync_id, ip.redistribution_allowed
                    FROM exam_scopes es
                    JOIN decks d ON es.deck_id = d.id
                    JOIN installed_packs ip ON es.pack_id = ip.pack_id AND es.resolved_pack_version = ip.pack_version
                    WHERE es.scope_id = ?
                    """,
                    (scope_id,),
                ).fetchone()
                if scope is None:
                    raise ValueError(f"Unknown exam_scope {scope_id}")

                textbook_id = str(scope["textbook_id"])
                max_tier = int(scope["max_importance_tier"])
                deck_id = int(scope["deck_id"])
                deck_sync_id = str(scope["deck_sync_id"])
                pack_id = str(scope["pack_id"])
                pack_version = str(scope["resolved_pack_version"])
                redistribution_allowed = bool(scope["redistribution_allowed"])
                include_user_notes = bool(scope["include_user_scanned_notes"])

                rules = conn.execute(
                    "SELECT * FROM exam_scope_rules WHERE scope_id = ? ORDER BY rule_id ASC",
                    (scope_id,),
                ).fetchall()

                # Load all units for this textbook from Tier R
                units = pack_conn.execute(
                    """
                    SELECT unit_id, parent_unit_id, unit_ordinal
                    FROM ref_curriculum_units
                    WHERE textbook_id = ?
                    ORDER BY unit_ordinal ASC
                    """,
                    (textbook_id,),
                ).fetchall()
                unit_ordinal_map = {str(u["unit_id"]): int(u["unit_ordinal"]) for u in units}
                children_by_parent: dict[str, list[str]] = {}
                for u in units:
                    pid = u["parent_unit_id"]
                    if pid is not None:
                        children_by_parent.setdefault(str(pid), []).append(str(u["unit_id"]))

                def expand_unit_ids(root_unit_id: str, include_sub: bool) -> list[str]:
                    if not include_sub:
                        return [root_unit_id] if root_unit_id in unit_ordinal_map else []
                    result: list[str] = []
                    stack = [root_unit_id]
                    while stack:
                        curr = stack.pop(0)
                        if curr in unit_ordinal_map and curr not in result:
                            result.append(curr)
                            stack.extend(children_by_parent.get(curr, []))
                    return result

                # Expand rules into (unit_id, page_start, page_end) predicates
                expanded_rules: list[tuple[str, int | None, int | None]] = []
                for r in rules:
                    for uid in expand_unit_ids(str(r["unit_id"]), bool(r["include_subunits"])):
                        expanded_rules.append((uid, r["page_start"], r["page_end"]))

                def matches_page_rules(unit_id: str, page_no: int | None) -> bool:
                    unit_rules = [er for er in expanded_rules if er[0] == unit_id]
                    if not unit_rules:
                        return False
                    for _, p_start, p_end in unit_rules:
                        if p_start is None and p_end is None:
                            return True
                        if page_no is not None and p_start is not None and p_end is not None:
                            if int(p_start) <= int(page_no) <= int(p_end):
                                return True
                    return False

                # 1. Query Tier R unit entries for textbook_id
                raw_unit_entries = pack_conn.execute(
                    """
                    SELECT rue.*, re.*, rcu.unit_ordinal
                    FROM ref_unit_entries rue
                    JOIN ref_curriculum_units rcu ON rue.unit_id = rcu.unit_id
                    JOIN ref_entries re ON rue.entry_key = re.entry_key
                    WHERE rue.textbook_id = ?
                      AND rue.importance_tier <= ?
                      AND re.retired = 0
                      AND ( ? IS NULL OR (
                            (re.valid_from IS NULL OR re.valid_from <= ?)
                            AND (re.valid_until IS NULL OR re.valid_until >= ?)
                      ))
                    ORDER BY rcu.unit_ordinal ASC, rue.unit_item_ordinal ASC
                    """,
                    (textbook_id, max_tier, as_of_date, as_of_date, as_of_date),
                ).fetchall()

                # Deduplicate repeated entry_key across units by earliest (unit_ordinal, unit_item_ordinal)
                selected_pack_entries: dict[str, sqlite3.Row] = {}
                for row in raw_unit_entries:
                    uid = str(row["unit_id"])
                    p_no = row["page_no"]
                    if matches_page_rules(uid, int(p_no) if p_no is not None else None):
                        ekey = str(row["entry_key"])
                        if ekey not in selected_pack_entries:
                            selected_pack_entries[ekey] = row

                # 2. Query Tier U student-scanned/manual textbook notes if enabled
                selected_user_notes: list[sqlite3.Row] = []
                if include_user_notes:
                    user_rows = conn.execute(
                        """
                        SELECT id, curriculum_unit_id, textbook_page_no
                        FROM notes
                        WHERE deck_id = ?
                          AND origin_kind IN ('doc_extracted', 'manual')
                          AND textbook_id = ?
                          AND curriculum_unit_id IS NOT NULL
                        ORDER BY COALESCE(textbook_page_no, 999999) ASC, id ASC
                        """,
                        (deck_id, textbook_id),
                    ).fetchall()
                    for urow in user_rows:
                        uid = str(urow["curriculum_unit_id"])
                        p_no = urow["textbook_page_no"]
                        if matches_page_rules(uid, int(p_no) if p_no is not None else None):
                            selected_user_notes.append(urow)

                # Step A of Reconciliation: Reset all existing scope items to in_scope=0, scope_ordinal=NULL
                conn.execute(
                    "UPDATE exam_scope_items SET in_scope = 0, scope_ordinal = NULL WHERE scope_id = ?",
                    (scope_id,),
                )

                # Step B: Upsert active pack_entry and user_note items with contiguous scope_ordinal = 1..N
                ordinal_counter = 0
                for ekey, row in selected_pack_entries.items():
                    ordinal_counter += 1
                    uid = str(row["unit_id"])
                    p_no = int(row["page_no"]) if row["page_no"] is not None else None
                    mat_note_id: int | None = None
                    if materialize_now:
                        eff_diff = difficulty_level
                        if difficulty_level in ("mixed", "all"):
                            eff_diff = ("lv1", "lv2", "lv3")[(ordinal_counter - 1) % 3]
                        mat_info = self._materialize_ref_entry_into_tx(
                            conn,
                            deck_id=deck_id,
                            deck_sync_id=deck_sync_id,
                            pack_id=pack_id,
                            pack_version=pack_version,
                            redistribution_allowed=redistribution_allowed,
                            entry_row=row,
                            textbook_id=textbook_id,
                            curriculum_unit_id=uid,
                            textbook_page_no=p_no,
                            difficulty_level=eff_diff,
                            now_sec=now_sec,
                        )
                        mat_note_id = int(mat_info["note_id"])

                    existing_item = conn.execute(
                        """
                        SELECT item_id, materialized_note_id FROM exam_scope_items
                        WHERE scope_id = ? AND item_kind = 'pack_entry' AND entry_key = ?
                        """,
                        (scope_id, ekey),
                    ).fetchone()
                    if existing_item is not None:
                        conn.execute(
                            """
                            UPDATE exam_scope_items
                            SET unit_id = ?, page_no = ?, scope_ordinal = ?, in_scope = 1,
                                materialized_note_id = COALESCE(?, materialized_note_id)
                            WHERE item_id = ?
                            """,
                            (uid, p_no, ordinal_counter, mat_note_id, int(existing_item["item_id"])),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO exam_scope_items (
                                scope_id, item_kind, entry_key, user_note_id, unit_id,
                                page_no, scope_ordinal, in_scope, materialized_note_id
                            ) VALUES (?, 'pack_entry', ?, NULL, ?, ?, ?, 1, ?)
                            """,
                            (scope_id, ekey, uid, p_no, ordinal_counter, mat_note_id),
                        )

                for urow in selected_user_notes:
                    ordinal_counter += 1
                    unote_id = int(urow["id"])
                    uid = str(urow["curriculum_unit_id"])
                    p_no = int(urow["textbook_page_no"]) if urow["textbook_page_no"] is not None else None
                    existing_uitem = conn.execute(
                        """
                        SELECT item_id FROM exam_scope_items
                        WHERE scope_id = ? AND item_kind = 'user_note' AND user_note_id = ?
                        """,
                        (scope_id, unote_id),
                    ).fetchone()
                    if existing_uitem is not None:
                        conn.execute(
                            """
                            UPDATE exam_scope_items
                            SET unit_id = ?, page_no = ?, scope_ordinal = ?, in_scope = 1,
                                materialized_note_id = NULL
                            WHERE item_id = ?
                            """,
                            (uid, p_no, ordinal_counter, int(existing_uitem["item_id"])),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO exam_scope_items (
                                scope_id, item_kind, entry_key, user_note_id, unit_id,
                                page_no, scope_ordinal, in_scope, materialized_note_id
                            ) VALUES (?, 'user_note', NULL, ?, ?, ?, ?, 1, NULL)
                            """,
                            (scope_id, unote_id, uid, p_no, ordinal_counter),
                        )

                active_rows = conn.execute(
                    """
                    SELECT * FROM exam_scope_items
                    WHERE scope_id = ? AND in_scope = 1
                    ORDER BY scope_ordinal ASC
                    """,
                    (scope_id,),
                ).fetchall()
                return [dict(r) for r in active_rows]
        finally:
            pack_conn.close()

    def list_exam_scope_items(self, *, scope_id: int, only_in_scope: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                if only_in_scope:
                    rows = conn.execute(
                        "SELECT * FROM exam_scope_items WHERE scope_id = ? AND in_scope = 1 ORDER BY scope_ordinal ASC",
                        (scope_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM exam_scope_items WHERE scope_id = ? ORDER BY item_id ASC",
                        (scope_id,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_in_scope_review_cards(self, *, scope_id: int) -> list[dict[str, Any]]:
        """Return active, non-suspended/non-buried cards belonging to `in_scope = 1` items of `scope_id` (T28)."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT
                        c.id AS card_id,
                        c.note_id,
                        c.queue,
                        c.state,
                        c.stability,
                        c.difficulty,
                        c.reps,
                        c.lapses,
                        n.front,
                        n.back,
                        n.curriculum_unit_id,
                        n.textbook_page_no,
                        esi.scope_ordinal,
                        esi.in_scope
                    FROM exam_scope_items esi
                    JOIN notes n ON n.id = COALESCE(esi.materialized_note_id, esi.user_note_id)
                    JOIN cards c ON c.note_id = n.id
                    WHERE esi.scope_id = ?
                      AND esi.in_scope = 1
                      AND c.queue >= 0
                    ORDER BY esi.scope_ordinal ASC, c.ord ASC
                    """,
                    (scope_id,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()


def build_starter_k12_and_exam_pack(db_path: str | Path) -> dict[str, Any]:
    """Build the comprehensive `Tier R` starter pack:
    - Priority #1: 중학교 1학년 영어 (동아출판 윤정미 외, `kr.mid1.eng.donga_yoon.2022`) Lesson 1~8 전 단원 어휘·핵심문법·쪽수 매핑
      + 중학교 2학년 영어 (동아출판 윤정미 외, `kr.mid2.eng.donga_yoon.2022`)
      + 중학교 1학년 역사/사회 (미래엔, `kr.mid1.hist.miraen.2022`) & 과학 (비상교육, `kr.mid1.sci.visang.2022`)
    - Priority #2: 한자 급수별 카드 컬렉션 (`hanja-grade:8geup` ~ `hanja-grade:3geup` + `moe-hanja-1800:middle`)
    - Priority #3: 전 연령·전 분야 골고루 스타터 컬렉션 (초등 받아쓰기, 초등 영단어, 한국사, 토익, JLPT, 사자성어, 헌법·법학, 과학 원소·공식, IT 자격증)
    """
    target_path = Path(db_path)
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{target_path}{suffix}")
        if p.exists():
            p.unlink()
    builder = ReferencePackBuilder(target_path)
    builder.init_schema(
        pack_id="ko.k12.starter-bundle",
        pack_version="1.0.0",
        domain="textbook_curriculum",
        license_spdx="CC0-1.0",
        redistribution_allowed=True,
        attribution_text="MOE 2022 Curriculum Achievement Standards & Anki Studio Self-Authored Fact Database",
    )
    builder.add_source(
        source_id="moe_2022_public",
        title="2022 개정 교육과정 성취기준 및 기초한자·기본어휘 고시",
        publisher="대한민국 교육부",
        license_class="PUBLIC_LAW_ART7",
        snapshot_sha256="1" * 64,
    )
    builder.add_source(
        source_id="anki_self_fact",
        title="Anki Studio 2.0 자체 편찬 뜻풀이 및 단원 어휘·문법 색인",
        publisher="Anki Studio",
        license_class="FACT_SELF_AUTHORED",
        snapshot_sha256="2" * 64,
    )

    # =========================================================================
    # 1. 한자 급수별 카드 컬렉션 (8급 ~ 3급 + 중학 교육용 기초한자 1800)
    # =========================================================================
    hanja_by_grade: dict[str, tuple[str, list[tuple[str, str, str, str, dict[str, Any]]]]] = {
        "hanja-grade:8geup": (
            "한자 8급 (입문 기초 50자 핵심)",
            [
                ("hanja:U+65E5", "日", "일", "날 일", {"codepoint": "U+65E5", "eum": ["일"], "hun": {"일": "날"}, "dueum": {}, "radical": "日", "strokes": 4}),
                ("hanja:U+6708", "月", "월", "달 월", {"codepoint": "U+6708", "eum": ["월"], "hun": {"월": "달"}, "dueum": {}, "radical": "月", "strokes": 4}),
                ("hanja:U+706B", "火", "화", "불 화", {"codepoint": "U+706B", "eum": ["화"], "hun": {"화": "불"}, "dueum": {}, "radical": "火", "strokes": 4}),
                ("hanja:U+6C34", "水", "수", "물 수", {"codepoint": "U+6C34", "eum": ["수"], "hun": {"수": "물"}, "dueum": {}, "radical": "水", "strokes": 4}),
                ("hanja:U+6728", "木", "목", "나무 목", {"codepoint": "U+6728", "eum": ["목"], "hun": {"목": "나무"}, "dueum": {}, "radical": "木", "strokes": 4}),
                ("hanja:U+91D1", "金", "금/김", "쇠 금, 성씨 김", {"codepoint": "U+91D1", "eum": ["금", "김"], "hun": {"금": "쇠", "김": "성씨"}, "dueum": {}, "radical": "金", "strokes": 8}),
                ("hanja:U+571F", "土", "토", "흙 토", {"codepoint": "U+571F", "eum": ["토"], "hun": {"토": "흙"}, "dueum": {}, "radical": "土", "strokes": 3}),
                ("hanja:U+5C71", "山", "산", "메 산", {"codepoint": "U+5C71", "eum": ["산"], "hun": {"산": "메"}, "dueum": {}, "radical": "山", "strokes": 3}),
                ("hanja:U+5DDD", "川", "천", "내 천", {"codepoint": "U+5DDD", "eum": ["천"], "hun": {"천": "내"}, "dueum": {}, "radical": "巛", "strokes": 3}),
                ("hanja:U+97D3", "韓", "한", "나라 한", {"codepoint": "U+97D3", "eum": ["한"], "hun": {"한": "나라"}, "dueum": {}, "radical": "韋", "strokes": 17}),
                ("hanja:U+570B", "國", "국", "나라 국", {"codepoint": "U+570B", "eum": ["국"], "hun": {"국": "나라"}, "dueum": {}, "radical": "囗", "strokes": 11}),
                ("hanja:U+738B", "王", "왕", "임금 왕", {"codepoint": "U+738B", "eum": ["왕"], "hun": {"왕": "임금"}, "dueum": {}, "radical": "玉", "strokes": 4}),
            ],
        ),
        "hanja-grade:7geup": (
            "한자 7급 (초등 기초 필수)",
            [
                ("hanja:U+5BB6", "家", "가", "집 가", {"codepoint": "U+5BB6", "eum": ["가"], "hun": {"가": "집"}, "dueum": {}, "radical": "宀", "strokes": 10}),
                ("hanja:U+6B4C", "歌", "가", "노래 가", {"codepoint": "U+6B4C", "eum": ["가"], "hun": {"가": "노래"}, "dueum": {}, "radical": "欠", "strokes": 14}),
                ("hanja:U+6C5F", "江", "강", "강 강", {"codepoint": "U+6C5F", "eum": ["강"], "hun": {"강": "강"}, "dueum": {}, "radical": "水", "strokes": 6}),
                ("hanja:U+7A7A", "空", "공", "빌 공, 하늘 공", {"codepoint": "U+7A7A", "eum": ["공"], "hun": {"공": "빌"}, "dueum": {}, "radical": "穴", "strokes": 8}),
                ("hanja:U+8A18", "記", "기", "기록할 기", {"codepoint": "U+8A18", "eum": ["기"], "hun": {"기": "기록할"}, "dueum": {}, "radical": "言", "strokes": 10}),
                ("hanja:U+9053", "道", "도", "길 도", {"codepoint": "U+9053", "eum": ["도"], "hun": {"도": "길"}, "dueum": {}, "radical": "辵", "strokes": 12}),
                ("hanja:U+52D5", "動", "동", "움직일 동", {"codepoint": "U+52D5", "eum": ["동"], "hun": {"동": "움직일"}, "dueum": {}, "radical": "力", "strokes": 11}),
                ("hanja:U+4F86", "來", "래", "올 래(내)", {"codepoint": "U+4F86", "eum": ["래"], "hun": {"래": "올"}, "dueum": {"래": "내"}, "radical": "人", "strokes": 8}),
            ],
        ),
        "hanja-grade:6geup": (
            "한자 6급 (초등 심화·중학 입문)",
            [
                ("hanja:U+611F", "感", "감", "느낄 감", {"codepoint": "U+611F", "eum": ["감"], "hun": {"감": "느낄"}, "dueum": {}, "radical": "心", "strokes": 13}),
                ("hanja:U+958B", "開", "개", "열 개", {"codepoint": "U+958B", "eum": ["개"], "hun": {"개": "열"}, "dueum": {}, "radical": "門", "strokes": 12}),
                ("hanja:U+4EAC", "京", "경", "서울 경", {"codepoint": "U+4EAC", "eum": ["경"], "hun": {"경": "서울"}, "dueum": {}, "radical": "亠", "strokes": 8}),
                ("hanja:U+754C", "界", "계", "지경 계", {"codepoint": "U+754C", "eum": ["계"], "hun": {"계": "지경"}, "dueum": {}, "radical": "田", "strokes": 9}),
                ("hanja:U+82E6", "苦", "고", "쓸 고, 괴로울 고", {"codepoint": "U+82E6", "eum": ["고"], "hun": {"고": "쓸"}, "dueum": {}, "radical": "艸", "strokes": 8}),
                ("hanja:U+5149", "光", "광", "빛 광", {"codepoint": "U+5149", "eum": ["광"], "hun": {"광": "빛"}, "dueum": {}, "radical": "儿", "strokes": 6}),
            ],
        ),
        "hanja-grade:5geup": (
            "한자 5급 (중학 기초한자 핵심)",
            [
                ("hanja:U+50F9", "價", "가", "값 가", {"codepoint": "U+50F9", "eum": ["가"], "hun": {"가": "값"}, "dueum": {}, "radical": "人", "strokes": 15}),
                ("hanja:U+6E1B", "減", "감", "덜 감", {"codepoint": "U+6E1B", "eum": ["감"], "hun": {"감": "덜"}, "dueum": {}, "radical": "水", "strokes": 12}),
                ("hanja:U+8B1B", "講", "강", "익힐 강, 강론할 강", {"codepoint": "U+8B1B", "eum": ["강"], "hun": {"강": "익힐"}, "dueum": {}, "radical": "言", "strokes": 17}),
                ("hanja:U+6539", "改", "개", "고칠 개", {"codepoint": "U+6539", "eum": ["개"], "hun": {"개": "고칠"}, "dueum": {}, "radical": "攴", "strokes": 7}),
                ("hanja:U+5BA2", "客", "객", "손 객", {"codepoint": "U+5BA2", "eum": ["객"], "hun": {"객": "손"}, "dueum": {}, "radical": "宀", "strokes": 9}),
                ("hanja:U+5EFA", "建", "건", "세울 건", {"codepoint": "U+5EFA", "eum": ["건"], "hun": {"건": "세울"}, "dueum": {}, "radical": "廴", "strokes": 9}),
            ],
        ),
        "hanja-grade:4geup": (
            "한자 4급 (중·고교 핵심 어휘 한자)",
            [
                ("hanja:U+89BA", "覺", "각", "깨달을 각", {"codepoint": "U+89BA", "eum": ["각"], "hun": {"각": "깨달을"}, "dueum": {}, "radical": "見", "strokes": 20}),
                ("hanja:U+523B", "刻", "각", "새길 각", {"codepoint": "U+523B", "eum": ["각"], "hun": {"각": "새길"}, "dueum": {}, "radical": "刀", "strokes": 8}),
                ("hanja:U+7C21", "簡", "간", "대쪽 간, 간략할 간", {"codepoint": "U+7C21", "eum": ["간"], "hun": {"간": "간략할"}, "dueum": {}, "radical": "竹", "strokes": 18}),
                ("hanja:U+6562", "敢", "감", "감히 감", {"codepoint": "U+6562", "eum": ["감"], "hun": {"감": "감히"}, "dueum": {}, "radical": "攴", "strokes": 12}),
                ("hanja:U+964D", "降", "강/항", "내릴 강, 항복할 항", {"codepoint": "U+964D", "eum": ["강", "항"], "hun": {"강": "내릴", "항": "항복할"}, "dueum": {}, "radical": "阜", "strokes": 8}),
                ("hanja:U+5EB7", "康", "강", "편안 강", {"codepoint": "U+5EB7", "eum": ["강"], "hun": {"강": "편안"}, "dueum": {}, "radical": "广", "strokes": 11}),
            ],
        ),
        "hanja-grade:3geup": (
            "한자 3급 (고교·수능·공무원 핵심 한자)",
            [
                ("hanja:U+6A02", "\uF914", "락/악/요", "즐길 락, 노래 악, 좋아할 요", {"codepoint": "U+6A02", "eum": ["락", "악", "요"], "hun": {"락": "즐길", "악": "노래", "요": "좋아할"}, "dueum": {"락": "낙"}, "radical": "木", "strokes": 15}),
                ("hanja:U+5B78", "學", "학", "배울 학", {"codepoint": "U+5B78", "eum": ["학"], "hun": {"학": "배울"}, "dueum": {}, "radical": "子", "strokes": 16}),
                ("hanja:U+6821", "校", "교", "학교 교", {"codepoint": "U+6821", "eum": ["교"], "hun": {"교": "학교"}, "dueum": {}, "radical": "木", "strokes": 10}),
                ("hanja:U+4EC1", "仁", "인", "어질 인", {"codepoint": "U+4EC1", "eum": ["인"], "hun": {"인": "어질"}, "dueum": {}, "radical": "人", "strokes": 4}),
                ("hanja:U+7FA9", "義", "의", "옳을 의", {"codepoint": "U+7FA9", "eum": ["의"], "hun": {"의": "옳을"}, "dueum": {}, "radical": "羊", "strokes": 13}),
                ("hanja:U+8AA0", "誠", "성", "정성 성", {"codepoint": "U+8AA0", "eum": ["성"], "hun": {"성": "정성"}, "dueum": {}, "radical": "言", "strokes": 13}),
            ],
        ),
    }

    moe_middle_ord = 0
    for col_id, (level_label, entries) in hanja_by_grade.items():
        for idx, (ekey, hw, reading, gloss, facet) in enumerate(entries, start=1):
            enriched_facet = dict(facet)
            enriched_facet.setdefault("clean_front", f"📜 [{level_label}] 다음 한자의 훈(뜻)과 음(소리)은?\n{hw}")
            enriched_facet.setdefault("lv1_front", f"🌱 [Lv.1 기초 한자] 다음 한자의 훈과 음은 무엇인가요?\n{hw} (부수: {facet.get('radical', '')}, {facet.get('strokes', '')}획)")
            enriched_facet.setdefault("lv1_back", f"{gloss} ({reading})")
            enriched_facet.setdefault("lv2_front", f"📘 [Lv.2 실전 한자] 뜻이 '{{{{c1::{gloss}::훈과 음}}}}'인 한자는 {hw}이다.")
            enriched_facet.setdefault("lv2_back", f"{gloss} ({hw}, 음: {reading})")
            enriched_facet.setdefault("lv3_front", f"🔥 [Lv.3 심화 역방향] 훈과 음이 '{gloss}'인 한자를 고르거나 쓰시오. (부수: {facet.get('radical', '')}, 총 {facet.get('strokes', '')}획)")
            enriched_facet.setdefault("lv3_back", f"{hw} — {gloss} ({reading})")
            enriched_facet.setdefault("target_answer", gloss)
            enriched_facet.setdefault("extra_explanation", f"한자: {hw} · 음: {reading} · 부수: {facet.get('radical', '')} ({facet.get('strokes', '')}획)")
            builder.add_entry(
                entry_key=ekey,
                entry_type="hanja_char",
                headword=hw,
                norm_key=hw,
                reading=reading,
                gloss_ko=gloss,
                facet_json=enriched_facet,
                source_id="anki_self_fact",
                difficulty_rank=idx,
            )
            builder.add_collection_item(
                collection_id=col_id,
                entry_key=ekey,
                ordinal=idx,
                level_label=level_label,
            )
            moe_middle_ord += 1
            builder.add_collection_item(
                collection_id="moe-hanja-1800:middle",
                entry_key=ekey,
                ordinal=moe_middle_ord,
                level_label="교육부 중학 기초한자 1800",
            )

    # Add Hanja distractor relations (similar_shape, same_radical, homophone)
    hanja_relations = [
        ("hanja:U+65E5", "similar_shape", "hanja:U+6708", 0.90),
        ("hanja:U+706B", "same_radical", "hanja:U+6C34", 0.85),
        ("hanja:U+6728", "same_radical", "hanja:U+6821", 0.92),
        ("hanja:U+6821", "similar_shape", "hanja:U+5B78", 0.89),
        ("hanja:U+6821", "homophone", "hanja:U+6539", 0.86),
        ("hanja:U+5BB6", "homophone", "hanja:U+6B4C", 0.95),
        ("hanja:U+5BB6", "homophone", "hanja:U+50F9", 0.94),
        ("hanja:U+89BA", "homophone", "hanja:U+523B", 0.95),
        ("hanja:U+6A02", "same_radical", "hanja:U+6821", 0.88),
        ("hanja:U+6A02", "similar_shape", "hanja:U+5B78", 0.84),
    ]
    for f_key, r_type, t_key, w in hanja_relations:
        builder.add_relation(from_key=f_key, rel_type=r_type, to_key=t_key, weight=w)
        builder.add_relation(from_key=t_key, rel_type=r_type, to_key=f_key, weight=w)

    # =========================================================================
    # 2. Priority #1: 중학교 1학년 영어 (동아출판 윤정미 외 — kr.mid1.eng.donga_yoon.2022)
    #    Lesson 1 ~ Lesson 8 전 단원 어휘·핵심문법·쪽수 매핑 (Spoiler-Free & Lv1/Lv2/Lv3)
    # =========================================================================
    tb_mid1 = "kr.mid1.eng.donga_yoon.2022"
    builder.add_textbook(
        textbook_id=tb_mid1,
        curriculum_revision="2022",
        school_level="middle",
        grade=1,
        semester=1,
        subject_code="language",
        publisher_name="동아출판",
        author_label="윤정미 외",
        title="중학교 영어 1 (동아출판 윤정미)",
        total_pages=168,
        source_id="moe_2022_public",
        valid_school_year_from=2025,
    )

    mid1_lessons = [
        (1, "Lesson 1", "My Happy School Life", 10, 27, "[9영01-01]"),
        (2, "Lesson 2", "Delicious World", 28, 45, "[9영02-02]"),
        (3, "Lesson 3", "Spend Smart, Save Smart", 46, 63, "[9영02-05]"),
        (4, "Lesson 4", "Walk Around the Neighborhood", 64, 81, "[9영02-07]"),
        (5, "Lesson 5", "Follow Your Dreams", 82, 99, "[9영03-01]"),
        (6, "Lesson 6", "Enjoy Art, Connect Hearts", 100, 117, "[9영03-04]"),
        (7, "Lesson 7", "Science Full of Wonder", 118, 135, "[9영04-01]"),
        (8, "Lesson 8", "Viva South America!", 136, 153, "[9영04-03]"),
    ]
    for ord_no, code_lbl, u_title, p_start, p_end, ach_code in mid1_lessons:
        builder.add_curriculum_unit(
            unit_id=f"{tb_mid1}:U0{ord_no}",
            textbook_id=tb_mid1,
            parent_unit_id=None,
            depth=1,
            unit_ordinal=ord_no,
            unit_code_label=code_lbl,
            unit_title=u_title,
            page_start=p_start,
            page_end=p_end,
            achievement_code=ach_code,
        )

    mid1_examples = {
        "word:introduce": "Let me {{c1::introduce::소개하다}} myself to the class.",
        "word:classmate": "Jimin is my new {{c1::classmate::반 친구}} this year.",
        "word:favorite": "What is your {{c1::favorite::가장 좋아하는}} school subject?",
        "word:subject": "English is my favorite {{c1::subject::과목}} at school.",
        "word:delicious": "This bulgogi pizza smells and tastes {{c1::delicious::매우 맛있는}}!",
        "word:healthy": "Eating fresh fruit keeps your body {{c1::healthy::건강한}}.",
        "word:dessert": "We had sweet ice cream for {{c1::dessert::후식}} after dinner.",
        "word:vegetable": "Carrots and broccoli are fresh {{c1::vegetable::채소}} ingredients.",
        "word:volunteer": "She works as a {{c1::volunteer::자원봉사자}} at the local animal shelter.",
        "word:donate": "Many students {{c1::donate::기부하다}} their books to the charity market.",
        "word:secondhand": "I bought a clean {{c1::secondhand::중고의}} backpack at the flea market.",
        "word:treasure": "One person's trash can be another person's {{c1::treasure::보물}}.",
        "word:neighborhood": "There is a quiet park in my {{c1::neighborhood::동네}}.",
        "word:bakery": "Fresh bread smells wonderful at the corner {{c1::bakery::빵집}}.",
        "word:straight": "Go {{c1::straight::곧장}} two blocks and turn left at the bank.",
        "word:career": "She is exploring her future {{c1::career::진로·직업}} on Career Day.",
        "word:creative": "Webtoon artists need {{c1::creative::창의적인}} ideas and storytelling skills.",
        "word:talent": "He has a great {{c1::talent::재능}} for playing the guitar.",
        "word:exhibition": "We visited a modern art {{c1::exhibition::전시회}} at the museum.",
        "word:painting": "This famous {{c1::painting::회화·그림}} shows a starry night sky.",
        "word:character": "Who is the main {{c1::character::등장인물}} in this animated movie?",
        "word:gravity": "Things fall to the ground because of Earth's {{c1::gravity::중력}}.",
        "word:float": "Astronauts {{c1::float::뜨다}} in space where there is microgravity.",
        "word:experiment": "We did an exciting science {{c1::experiment::실험}} in the lab.",
        "word:continent": "South America is a {{c1::continent::대륙}} with rich nature and history.",
        "word:waterfall": "Iguazu Falls is a giant {{c1::waterfall::폭포}} in South America.",
        "word:ancient": "Machu Picchu is an {{c1::ancient::고대의}} Inca city high in the Andes.",
    }

    mid1_entries = [
        # Lesson 1 (p.10~27)
        ("word:introduce", "word", "introduce", "소개하다", "verb", f"{tb_mid1}:U01", 1, 12, 1, "core_vocab"),
        ("word:classmate", "word", "classmate", "반 친구, 급우", "noun", f"{tb_mid1}:U01", 2, 13, 1, "core_vocab"),
        ("word:favorite", "word", "favorite", "가장 좋아하는", "adj", f"{tb_mid1}:U01", 3, 15, 1, "core_vocab"),
        ("word:subject", "word", "subject", "과목, 주제", "noun", f"{tb_mid1}:U01", 4, 16, 1, "core_vocab"),
        ("grammar:mid1_u1_be_verb", "fact_item", "Lesson 1 핵심문법: 주어가 3인칭 단수(he/she/it)일 때 일반동사 현재형의 어미 변화와 부정문 형태는?", "동사원형에 -(e)s를 붙이며, 부정문은 doesn't + 동사원형을 쓴다.", "grammar", f"{tb_mid1}:U01", 5, 20, 1, "key_grammar"),
        # Lesson 2 (p.28~45)
        ("word:delicious", "word", "delicious", "매우 맛있는", "adj", f"{tb_mid1}:U02", 1, 30, 1, "core_vocab"),
        ("word:healthy", "word", "healthy", "건강에 좋은, 건강한", "adj", f"{tb_mid1}:U02", 2, 32, 1, "core_vocab"),
        ("word:dessert", "word", "dessert", "후식, 디저트", "noun", f"{tb_mid1}:U02", 3, 35, 1, "core_vocab"),
        ("word:vegetable", "word", "vegetable", "채소, 야채", "noun", f"{tb_mid1}:U02", 4, 38, 2, "core_vocab"),
        ("grammar:mid1_u2_present_prog", "fact_item", "Lesson 2 핵심문법: 지금 진행 중인 동작을 나타내는 현재진행형의 형태와 조동사 can/will 뒤의 동사 형태는?", "현재진행형: am/are/is + V-ing · 조동사 can/will + 동사원형", "grammar", f"{tb_mid1}:U02", 5, 40, 1, "key_grammar"),
        # Lesson 3 (p.46~63)
        ("word:volunteer", "word", "volunteer", "자원봉사자; 자원봉사하다", "noun", f"{tb_mid1}:U03", 1, 48, 1, "core_vocab"),
        ("word:donate", "word", "donate", "기부하다, 기증하다", "verb", f"{tb_mid1}:U03", 2, 50, 1, "core_vocab"),
        ("word:secondhand", "word", "secondhand", "중고의, 간접의", "adj", f"{tb_mid1}:U03", 3, 52, 1, "core_vocab"),
        ("word:treasure", "word", "treasure", "보물, 소중한 것", "noun", f"{tb_mid1}:U03", 4, 55, 1, "core_vocab"),
        ("grammar:mid1_u3_past_tense", "fact_item", "Lesson 3 핵심문법: 일반동사 과거시제의 규칙 어미 형태와 과거 의문문·부정문에 쓰는 조동사는?", "규칙 변화: 동사원형 + -(e)d · 의문문/부정문: Did / didn't + 동사원형", "grammar", f"{tb_mid1}:U03", 5, 58, 1, "key_grammar"),
        # Lesson 4 (p.64~81)
        ("word:neighborhood", "word", "neighborhood", "동네, 이웃", "noun", f"{tb_mid1}:U04", 1, 66, 1, "core_vocab"),
        ("word:bakery", "word", "bakery", "빵집, 제과점", "noun", f"{tb_mid1}:U04", 2, 68, 1, "core_vocab"),
        ("word:straight", "word", "straight", "곧장, 똑바로", "adv", f"{tb_mid1}:U04", 3, 70, 1, "core_vocab"),
        ("grammar:mid1_u4_there_is", "fact_item", "Lesson 4 핵심문법: '~이 있다'를 뜻하는 유도부사 구문의 단수·복수 형태와 길 안내 명령문의 시작 형태는?", "There is + 단수명사 / There are + 복수명사 · 명령문은 주어 없이 동사원형으로 시작", "grammar", f"{tb_mid1}:U04", 4, 76, 1, "key_grammar"),
        # Lesson 5 (p.82~99)
        ("word:career", "word", "career", "직업, 진로, 경력", "noun", f"{tb_mid1}:U05", 1, 84, 1, "core_vocab"),
        ("word:creative", "word", "creative", "창의적인, 독창적인", "adj", f"{tb_mid1}:U05", 2, 86, 1, "core_vocab"),
        ("word:talent", "word", "talent", "재능, 소질", "noun", f"{tb_mid1}:U05", 3, 89, 1, "core_vocab"),
        ("grammar:mid1_u5_to_inf", "fact_item", "Lesson 5 핵심문법: want/hope/plan 뒤에 목적어로 오는 형태와 수여동사(give/show) 4형식 어순은?", "목적어: to부정사(to + 동사원형) · 수여동사: 간접목적어(~에게) + 직접목적어(~을/를)", "grammar", f"{tb_mid1}:U05", 4, 94, 1, "key_grammar"),
        # Lesson 6 (p.100~117)
        ("word:exhibition", "word", "exhibition", "전시회", "noun", f"{tb_mid1}:U06", 1, 102, 1, "core_vocab"),
        ("word:painting", "word", "painting", "그림, 회화", "noun", f"{tb_mid1}:U06", 2, 105, 1, "core_vocab"),
        ("word:character", "word", "character", "등장인물, 성격, 글자", "noun", f"{tb_mid1}:U06", 3, 108, 1, "core_vocab"),
        ("grammar:mid1_u6_gerund", "fact_item", "Lesson 6 핵심문법: enjoy, finish, mind, give up 동사가 목적어로 취하는 준동사 형태는?", "동명사 (동사원형 + -ing) — to부정사는 목적어로 쓸 수 없음", "grammar", f"{tb_mid1}:U06", 4, 112, 1, "key_grammar"),
        # Lesson 7 (p.118~135)
        ("word:gravity", "word", "gravity", "중력", "noun", f"{tb_mid1}:U07", 1, 120, 1, "core_vocab"),
        ("word:float", "word", "float", "(물·공기 중에) 뜨다", "verb", f"{tb_mid1}:U07", 2, 122, 1, "core_vocab"),
        ("word:experiment", "word", "experiment", "실험; 실험하다", "noun", f"{tb_mid1}:U07", 3, 125, 1, "core_vocab"),
        ("grammar:mid1_u7_comparative", "fact_item", "Lesson 7 핵심문법: 형용사·부사의 비교급 구문과 셋 이상을 비교하는 최상급 구문의 핵심 형태는?", "비교급: -er / more ~ + than · 최상급: the + -est / most ~ (+ in/of)", "grammar", f"{tb_mid1}:U07", 4, 130, 1, "key_grammar"),
        # Lesson 8 (p.136~153)
        ("word:continent", "word", "continent", "대륙", "noun", f"{tb_mid1}:U08", 1, 138, 1, "core_vocab"),
        ("word:waterfall", "word", "waterfall", "폭포", "noun", f"{tb_mid1}:U08", 2, 140, 1, "core_vocab"),
        ("word:ancient", "word", "ancient", "고대의, 옛날의", "adj", f"{tb_mid1}:U08", 3, 144, 1, "core_vocab"),
        ("grammar:mid1_u8_sensory_verb", "fact_item", "Lesson 8 핵심문법: 감각동사(look/sound/smell/taste/feel) 뒤에 보어로 와야 하는 품사는?", "형용사 (주의: 부사 -ly는 보어로 올 수 없음. 예: It looks great)", "grammar", f"{tb_mid1}:U08", 4, 148, 1, "key_grammar"),
    ]
    for ekey, etype, hw, gloss, pos, uid, item_ord, page_no, tier, role in mid1_entries:
        u_num = uid.split(":U0")[-1]
        if etype == "word":
            ex_cloze = mid1_examples.get(ekey, f"Please remember the word {{{{c1::{hw}::{gloss}}}}}.")
            ex_plain = ex_cloze.replace(f"{{{{c1::{hw}::{gloss}}}}}", f"[{hw}]")
            facet_data = {
                "facet_schema_version": 2,
                "senses": [{"id": "s1", "gloss_ko": gloss, "pos": pos}],
                "clean_front": f"📘 [Lesson {u_num} · 어휘] 다음 영단어의 뜻은?\n{hw}",
                "lv1_front": f"🌱 [Lv.1 기초 어휘 · Lesson {u_num}] 다음 영단어의 우리말 뜻은?\n{hw} ({pos})",
                "lv1_back": f"{gloss}\n\n💡 해설: 예문 — {ex_plain}",
                "lv2_front": f"📘 [Lv.2 실전 문맥 빈칸 · Lesson {u_num}] 문맥에 알맞은 영단어를 채우세요:\n{ex_cloze}",
                "lv2_back": f"{hw} — {gloss}\n\n💡 해설: 완성 문장 — {ex_plain}",
                "lv3_front": f"🔥 [Lv.3 심화 영작 인출 · Lesson {u_num}] '{gloss}'에 해당하는 영어 단어({pos})를 철자에 맞게 쓰시오.",
                "lv3_back": f"{hw}\n\n💡 해설: {hw} ({pos}): {gloss} · {ex_plain}",
                "target_answer": gloss,
                "extra_explanation": f"예문: {ex_plain}",
            }
        else:
            facet_data = {
                "facet_schema_version": 2,
                "senses": [{"id": "s1", "gloss_ko": gloss, "pos": pos}],
                "clean_front": f"📐 [{hw}]",
                "lv1_front": f"🌱 [Lv.1 기초 문법 확인]\n{hw}",
                "lv1_back": gloss,
                "lv2_front": f"📘 [Lv.2 실전 문법 적용]\n{hw}\n핵심 규칙: {{{{c1::{gloss.split('·')[0].strip()}::문법 핵심 형태}}}}",
                "lv2_back": gloss,
                "lv3_front": f"🔥 [Lv.3 심화 서술·어법 변별]\n{hw}\n(핵심 형태와 오답 주의점을 함께 서술하시오)",
                "lv3_back": gloss,
                "target_answer": gloss,
                "extra_explanation": f"교과서 p.{page_no} 핵심 문법 포인트",
            }
        builder.add_entry(
            entry_key=ekey,
            entry_type=etype,
            headword=hw,
            norm_key=hw,
            gloss_ko=gloss,
            pos=pos,
            facet_json=facet_data,
            source_id="anki_self_fact",
        )
        builder.add_unit_entry(
            textbook_id=tb_mid1,
            unit_id=uid,
            entry_key=ekey,
            unit_item_ordinal=item_ord,
            page_no=page_no,
            importance_tier=tier,
            role_in_unit=role,
        )

    # =========================================================================
    # 3. 중학교 2학년 영어 (동아출판 윤정미 외 — kr.mid2.eng.donga_yoon.2022)
    # =========================================================================
    tb_id = "kr.mid2.eng.donga_yoon.2022"
    builder.add_textbook(
        textbook_id=tb_id,
        curriculum_revision="2022",
        school_level="middle",
        grade=2,
        semester=1,
        subject_code="language",
        publisher_name="동아출판",
        author_label="윤정미 외",
        title="중학교 영어 2 (동아출판 윤정미)",
        total_pages=160,
        source_id="moe_2022_public",
        valid_school_year_from=2025,
    )
    builder.add_curriculum_unit(
        unit_id=f"{tb_id}:U01",
        textbook_id=tb_id,
        parent_unit_id=None,
        depth=1,
        unit_ordinal=1,
        unit_code_label="Lesson 1",
        unit_title="Express Yourself",
        page_start=10,
        page_end=19,
        achievement_code="[9영02-01]",
    )
    builder.add_curriculum_unit(
        unit_id=f"{tb_id}:U02",
        textbook_id=tb_id,
        parent_unit_id=None,
        depth=1,
        unit_ordinal=2,
        unit_code_label="Lesson 2",
        unit_title="Food and Culture",
        page_start=20,
        page_end=39,
        achievement_code="[9영02-04]",
    )
    builder.add_curriculum_unit(
        unit_id=f"{tb_id}:U03",
        textbook_id=tb_id,
        parent_unit_id=None,
        depth=1,
        unit_ordinal=3,
        unit_code_label="Lesson 3",
        unit_title="Green Earth",
        page_start=40,
        page_end=59,
        achievement_code="[9영03-02]",
    )

    tb_words = [
        ("word:express", "express", "표현하다", "verb", f"{tb_id}:U01", 1, 12, 1),
        ("word:confident", "confident", "자신감 있는", "adj", f"{tb_id}:U01", 2, 16, 1),
        ("word:tradition", "tradition", "전통", "noun", f"{tb_id}:U02", 1, 22, 1),
        ("word:perform_skip", "perform", "수행하다", "verb", f"{tb_id}:U02", 2, 27, 2),
        ("word:recipe", "recipe", "조리법", "noun", f"{tb_id}:U02", 3, 31, 1),
        ("word:environment", "environment", "환경", "noun", f"{tb_id}:U03", 1, 45, 1),
    ]
    for ekey, hw, gloss, pos, uid, item_ord, page_no, tier in tb_words:
        builder.add_entry(
            entry_key=ekey,
            entry_type="word",
            headword=hw,
            norm_key=hw,
            gloss_ko=gloss,
            pos=pos,
            facet_json={
                "facet_schema_version": 2,
                "senses": [{"id": "s1", "gloss_ko": gloss, "pos": pos}],
                "clean_front": f"📘 [중2 영어 · 어휘] 다음 영단어의 뜻은?\n{hw}",
                "lv1_front": f"🌱 [Lv.1 기초 어휘] '{hw}' ({pos})의 우리말 뜻은?",
                "lv1_back": gloss,
                "lv2_front": f"📘 [Lv.2 실전 빈칸] 핵심 어휘 {{{{c1::{hw}::{gloss}}}}} ({pos})",
                "lv2_back": f"{hw} — {gloss}",
                "lv3_front": f"🔥 [Lv.3 심화 영작] '{gloss}'에 해당하는 영단어({pos})를 쓰시오.",
                "lv3_back": hw,
                "target_answer": gloss,
            },
            source_id="anki_self_fact",
        )
        builder.add_unit_entry(
            textbook_id=tb_id,
            unit_id=uid,
            entry_key=ekey,
            unit_item_ordinal=item_ord,
            page_no=page_no,
            importance_tier=tier,
            role_in_unit="core_vocab",
        )

    # 중학교 2학년 역사 (미래엔) & 고등학교 1학년 통합과학 (비상교육)
    builder.add_textbook(
        textbook_id="kr.mid2.hist.miraeen.2022",
        curriculum_revision="2022",
        school_level="middle",
        grade=2,
        semester=1,
        subject_code="social",
        publisher_name="미래엔",
        author_label="김태웅 외",
        title="중학교 역사 ① (미래엔)",
        total_pages=220,
        source_id="moe_2022_public",
        valid_school_year_from=2025,
    )
    builder.add_curriculum_unit(
        unit_id="kr.mid2.hist.miraeen.2022:U01",
        textbook_id="kr.mid2.hist.miraeen.2022",
        parent_unit_id=None,
        depth=1,
        unit_ordinal=1,
        unit_code_label="Ⅰ단원",
        unit_title="문명의 발생과 고대 세계의 형성",
        page_start=10,
        page_end=35,
        achievement_code="[9역01-01]",
    )
    builder.add_textbook(
        textbook_id="kr.high1.sci.visang.2022",
        curriculum_revision="2022",
        school_level="high",
        grade=1,
        semester=1,
        subject_code="science",
        publisher_name="비상교육",
        author_label="심규철 외",
        title="고등학교 통합과학 1 (비상교육)",
        total_pages=240,
        source_id="moe_2022_public",
        valid_school_year_from=2025,
    )
    builder.add_curriculum_unit(
        unit_id="kr.high1.sci.visang.2022:U01",
        textbook_id="kr.high1.sci.visang.2022",
        parent_unit_id=None,
        depth=1,
        unit_ordinal=1,
        unit_code_label="Ⅰ단원",
        unit_title="과학의 기초와 물질의 규칙성",
        page_start=12,
        page_end=48,
        achievement_code="[10통과01-01]",
    )
    extra_tb_entries = [
        (
            "khist:mid2:mesopotamia",
            "event",
            "🏛️ [중2 역사 · 고대 문명] 티그리스·유프라테스강 유역의 개방적 지형에서 발달하여 60진법·태음력·쐐기문자와 동해복수법의 법전을 남긴 문명과 그 법전 이름은?",
            "메소포타미아 문명 · 함무라비 법전",
            "kr.mid2.hist.miraeen.2022",
            "kr.mid2.hist.miraeen.2022:U01",
            1,
            14,
            "티그리스·유프라테스강 유역의 개방적 지형 때문에 이민족 침입이 잦아 현세적 종교관이 발달했으며, 쐐기문자와 함무라비 법전(눈에는 눈, 이에는 이)을 남겼다.",
        ),
        (
            "khist:mid2:polis_athens",
            "event",
            "🏛️ [중2 역사 · 그리스 폴리스] 도편추방제로 참주 출현을 막고 민회 중심의 직접 민주 정치를 확립한 폴리스와 핵심 개혁가(2명)는?",
            "아테네 · 클레이스테네스(도편추방제), 페리클레스(직접 민주 정치 전성기)",
            "kr.mid2.hist.miraeen.2022",
            "kr.mid2.hist.miraeen.2022:U01",
            2,
            24,
            "클레이스테네스는 도편추방제를 마련했고, 페리클레스는 민회 권한 강화와 공직자 수당제 도입으로 아테네 직접 민주 정치를 완성했다.",
        ),
        (
            "sci:high1:alkali_metals",
            "element",
            "🧪 [고1 통합과학 · 주기율표] 주기율표 1족(수소 제외)에 속하며 원자가 전자가 1개여서 물과 격렬히 반응해 수소 기체와 염기성 수용액을 만드는 금속 원소군의 이름과 대표 원소 3가지는?",
            "알칼리 금속 (리튬 Li, 나트륨 Na, 칼륨 K)",
            "kr.high1.sci.visang.2022",
            "kr.high1.sci.visang.2022:U01",
            1,
            28,
            "알칼리 금속은 원자번호가 커질수록(Li → Na → K) 반응성이 커지며, 공기 중 산소나 물과의 접촉을 막기 위해 석유나 액체 파라핀 속에 보관한다.",
        ),
        (
            "sci:high1:covalent_ionic",
            "formula",
            "🧪 [고1 통합과학 · 화학 결합] 금속 양이온과 비금속 음이온의 정전기적 인력에 의한 결합과, 비금속 원자들이 전자쌍을 공유하여 형성하는 결합을 각각 무엇이라 하는가?",
            "이온 결합 (금속+비금속) · 공유 결합 (비금속+비금속)",
            "kr.high1.sci.visang.2022",
            "kr.high1.sci.visang.2022:U01",
            2,
            36,
            "이온 결합 물질(예: NaCl)은 수용액 상태에서 전기 전도성이 있고, 공유 결합 물질(예: H₂O, CO₂)은 비금속 원자들이 전자쌍을 공유해 안정한 전자 배치를 이룬다.",
        ),
    ]
    for ekey, etype, hw, gloss, tbid, uid, ord_no, pno, extra_exp in extra_tb_entries:
        builder.add_entry(
            entry_key=ekey,
            entry_type=etype,
            headword=hw,
            norm_key=hw,
            gloss_ko=f"{gloss}\n\n💡 해설: {extra_exp}",
            facet_json={
                "facet_schema_version": 2,
                "senses": [{"id": "s1", "gloss_ko": gloss}],
                "clean_front": hw,
                "lv1_front": f"🌱 [Lv.1 기초 개념]\n{hw}",
                "lv1_back": f"{gloss}\n\n💡 해설: {extra_exp}",
                "lv2_front": f"📘 [Lv.2 실전 빈칸] {{{{c1::{gloss.split('·')[0].strip()}::핵심 정답}}}}: {extra_exp}",
                "lv2_back": f"{gloss}\n\n💡 해설: {extra_exp}",
                "lv3_front": f"🔥 [Lv.3 심화 서술]\n{hw}\n(핵심 특징과 이유를 함께 설명하시오)",
                "lv3_back": f"{gloss}\n\n💡 해설: {extra_exp}",
                "target_answer": gloss,
                "extra_explanation": extra_exp,
            },
            source_id="anki_self_fact",
        )
        builder.add_unit_entry(
            textbook_id=tbid,
            unit_id=uid,
            entry_key=ekey,
            unit_item_ordinal=ord_no,
            page_no=pno,
            importance_tier=1,
            role_in_unit="core_concept",
        )

    # =========================================================================
    # 4. 전 연령·전 분야 골고루 스타터 컬렉션 (초등·한국사·어학·사자성어·법학·과학·IT)
    # =========================================================================
    balanced_collections: dict[str, tuple[str, list[tuple[str, str, str, str, dict[str, Any]]]]] = {
        "ko-dictation:grade1-2": (
            "초등 1~2학년 급수별 받아쓰기 핵심 문장",
            [
                (
                    "dict:g1_01",
                    "fact_item",
                    "✏️ [초등 받아쓰기 1급] 빈칸에 들어갈 말을 바른 맞춤법으로 쓰세요:\n무궁화 [ ___ ] 활짝 피었습니다 (소리: 꼬치 / 힌트: ㅊ 받침 + 조사 + 쌍자음)",
                    "꽃이 활짝\n\n💡 해설: 정답 문장 — 무궁화 꽃이 활짝 피었습니다 ('꽃이'는 [꼬치]로 소리 나지만 '꽃이'로 적습니다).",
                    {
                        "expression": "무궁화 꽃이 활짝 피었습니다",
                        "senses": [{"id": "s1", "gloss_ko": "꽃이 활짝"}],
                        "lv1_front": "🌱 [Lv.1 받아쓰기 기초] [꼬치]라고 소리 나는 낱말의 바른 표기는?\n무궁화 [ ___ ] 활짝 피었습니다",
                        "lv1_back": "꽃이\n\n💡 해설: 무궁화 꽃이 활짝 피었습니다",
                        "lv2_front": "📘 [Lv.2 받아쓰기 빈칸] 무궁화 {{c1::꽃이::[꼬치]}} {{c2::활짝::강조 부사}} 피었습니다.",
                        "lv2_back": "꽃이 활짝 — 무궁화 꽃이 활짝 피었습니다",
                        "lv3_front": "🔥 [Lv.3 전체 문장 받아쓰기] 소리 나는 대로를 바른 맞춤법 문장으로 고쳐 쓰세요:\n\"무궁화 꼬치 활짝 피어씀니다\"",
                        "lv3_back": "무궁화 꽃이 활짝 피었습니다",
                        "target_answer": "꽃이 활짝",
                        "extra_explanation": "전체 문장: 무궁화 꽃이 활짝 피었습니다",
                    },
                ),
                (
                    "dict:g1_02",
                    "fact_item",
                    "✏️ [초등 받아쓰기 2급] 겹받침과 된소리에 주의하여 빈칸을 바르게 쓰세요:\n오늘 날씨가 참 [ ___ ] (소리: 말꼬 따뜨탑니다)",
                    "맑고 따뜻합니다\n\n💡 해설: 정답 문장 — 오늘 날씨가 참 맑고 따뜻합니다 (겹받침 ㄺ '맑고', 받침 ㅅ '따뜻합니다').",
                    {
                        "expression": "오늘 날씨가 참 맑고 따뜻합니다",
                        "senses": [{"id": "s1", "gloss_ko": "맑고 따뜻합니다"}],
                        "lv1_front": "🌱 [Lv.1 받아쓰기 기초] [말꼬]라고 소리 나는 낱말의 바른 겹받침 표기는?\n오늘 날씨가 참 [ ___ ] 따뜻합니다",
                        "lv1_back": "맑고\n\n💡 해설: 겹받침 ㄺ을 써서 '맑고'로 적습니다.",
                        "lv2_front": "📘 [Lv.2 받아쓰기 빈칸] 오늘 날씨가 참 {{c1::맑고::[말꼬]}} {{c2::따뜻합니다::[따뜨탑니다]}}.",
                        "lv2_back": "맑고 따뜻합니다",
                        "lv3_front": "🔥 [Lv.3 전체 문장 받아쓰기] 소리 나는 대로를 바른 맞춤법 문장으로 고쳐 쓰세요:\n\"오늘 날씨가 참 말꼬 따뜨탑니다\"",
                        "lv3_back": "오늘 날씨가 참 맑고 따뜻합니다",
                        "target_answer": "맑고 따뜻합니다",
                        "extra_explanation": "전체 문장: 오늘 날씨가 참 맑고 따뜻합니다",
                    },
                ),
                (
                    "dict:g1_03",
                    "fact_item",
                    "✏️ [초등 받아쓰기 3급] 높임 조사와 과거형 맞춤법에 맞게 빈칸을 쓰세요:\n[ ___ ] 예쁜 편지를 [ ___ ] (소리: 할머니께 / 써씀니다)",
                    "할머니께 썼습니다\n\n💡 해설: 정답 문장 — 할머니께 예쁜 편지를 썼습니다 (윗사람에게는 높임 조사 '-께'를 씁니다).",
                    {
                        "expression": "할머니께 예쁜 편지를 썼습니다",
                        "senses": [{"id": "s1", "gloss_ko": "할머니께 썼습니다"}],
                        "lv1_front": "🌱 [Lv.1 받아쓰기 기초] 웃어른에게 드릴 때 쓰는 높임말 조사는?\n할머니[ ___ ] 예쁜 편지를 썼습니다",
                        "lv1_back": "할머니께",
                        "lv2_front": "📘 [Lv.2 받아쓰기 빈칸] {{c1::할머니께::높임 조사}} 예쁜 편지를 {{c2::썼습니다::[써씀니다]}}.",
                        "lv2_back": "할머니께 썼습니다",
                        "lv3_front": "🔥 [Lv.3 전체 문장 받아쓰기] 틀린 맞춤법을 바르게 고쳐 전체 문장을 쓰세요:\n\"할머니에게 예쁜 편지를 써씀니다\"",
                        "lv3_back": "할머니께 예쁜 편지를 썼습니다",
                        "target_answer": "할머니께 썼습니다",
                        "extra_explanation": "전체 문장: 할머니께 예쁜 편지를 썼습니다",
                    },
                ),
                (
                    "dict:g1_04",
                    "fact_item",
                    "✏️ [초등 받아쓰기 4급] 겹받침 연음 표기에 주의하여 빈칸을 쓰세요:\n도서관에서 [ ___ ] 책을 [ ___ ] (소리: 조용히 / 일거요)",
                    "조용히 읽어요\n\n💡 해설: 정답 문장 — 도서관에서 조용히 책을 읽어요 ('읽어요'는 [일거요]로 발음되지만 겹받침 ㄺ을 밝혀 적습니다).",
                    {
                        "expression": "도서관에서 조용히 책을 읽어요",
                        "senses": [{"id": "s1", "gloss_ko": "조용히 읽어요"}],
                        "lv1_front": "🌱 [Lv.1 받아쓰기 기초] [일거요]라고 소리 나는 낱말의 바른 표기는?\n도서관에서 조용히 책을 [ ___ ]",
                        "lv1_back": "읽어요",
                        "lv2_front": "📘 [Lv.2 받아쓰기 빈칸] 도서관에서 {{c1::조용히::부사}} 책을 {{c2::읽어요::[일거요]}}.",
                        "lv2_back": "조용히 읽어요",
                        "lv3_front": "🔥 [Lv.3 전체 문장 받아쓰기] 소리 나는 대로를 바른 맞춤법 문장으로 고쳐 쓰세요:\n\"도서관에서 조용이 채글 일거요\"",
                        "lv3_back": "도서관에서 조용히 책을 읽어요",
                        "target_answer": "조용히 읽어요",
                        "extra_explanation": "전체 문장: 도서관에서 조용히 책을 읽어요",
                    },
                ),
            ],
        ),
        "moe-eng:elementary": (
            "교육부 고시 초등 필수 영단어 800 핵심",
            [
                ("word:elem_library", "word", "library", "도서관", {"senses": [{"id": "s1", "gloss_ko": "도서관", "pos": "noun"}], "cefr": "A1", "clean_front": "📘 [초등 필수 영단어] 다음 단어의 뜻은?\nlibrary", "lv1_front": "🌱 [Lv.1 초등 영단어] 'library'의 우리말 뜻은?", "lv1_back": "도서관", "lv2_front": "📘 [Lv.2 문맥 빈칸] I borrow books from the school {{c1::library::도서관}}.", "lv2_back": "library (도서관)", "lv3_front": "🔥 [Lv.3 철자 쓰기] '도서관'을 영어로 쓰시오.", "lv3_back": "library", "target_answer": "도서관"}),
                ("word:elem_hospital", "word", "hospital", "병원", {"senses": [{"id": "s1", "gloss_ko": "병원", "pos": "noun"}], "cefr": "A1", "clean_front": "📘 [초등 필수 영단어] 다음 단어의 뜻은?\nhospital", "lv1_front": "🌱 [Lv.1 초등 영단어] 'hospital'의 우리말 뜻은?", "lv1_back": "병원", "lv2_front": "📘 [Lv.2 문맥 빈칸] Doctors and nurses work at the {{c1::hospital::병원}}.", "lv2_back": "hospital (병원)", "lv3_front": "🔥 [Lv.3 철자 쓰기] '병원'을 영어로 쓰시오.", "lv3_back": "hospital", "target_answer": "병원"}),
                ("word:elem_weather", "word", "weather", "날씨", {"senses": [{"id": "s1", "gloss_ko": "날씨", "pos": "noun"}], "cefr": "A1", "clean_front": "📘 [초등 필수 영단어] 다음 단어의 뜻은?\nweather", "lv1_front": "🌱 [Lv.1 초등 영단어] 'weather'의 우리말 뜻은?", "lv1_back": "날씨", "lv2_front": "📘 [Lv.2 문맥 빈칸] How is the {{c1::weather::날씨}} today?", "lv2_back": "weather (날씨)", "lv3_front": "🔥 [Lv.3 철자 쓰기] '날씨'를 영어로 쓰시오.", "lv3_back": "weather", "target_answer": "날씨"}),
                ("word:elem_tomorrow", "word", "tomorrow", "내일", {"senses": [{"id": "s1", "gloss_ko": "내일", "pos": "noun"}], "cefr": "A1", "clean_front": "📘 [초등 필수 영단어] 다음 단어의 뜻은?\ntomorrow", "lv1_front": "🌱 [Lv.1 초등 영단어] 'tomorrow'의 우리말 뜻은?", "lv1_back": "내일", "lv2_front": "📘 [Lv.2 문맥 빈칸] See you {{c1::tomorrow::내일}} morning!", "lv2_back": "tomorrow (내일)", "lv3_front": "🔥 [Lv.3 철자 쓰기] '내일'을 영어로 쓰시오.", "lv3_back": "tomorrow", "target_answer": "내일"}),
            ],
        ),
        "khist:essential": (
            "한국사능력검정 핵심 연표·사건·문화재",
            [
                (
                    "khist:event:hunmin_1443",
                    "event",
                    "🏛️ [한국사 핵심] 조선 세종 대 집현전 학자들과 함께 백성을 가르치는 바른 소리 28자를 창제(1443)·반포(1446)한 우리 고유의 문자는?",
                    "훈민정음 (1443년 창제 · 1446년 반포)\n\n💡 해설: 세종 대 창제된 민족 문자로, 창제 원리를 밝힌 《훈민정음 해례본》은 유네스코 세계기록유산으로 등재되어 있습니다.",
                    {
                        "era": "joseon_early",
                        "reign": "sejong",
                        "year": 1443,
                        "senses": [{"id": "s1", "gloss_ko": "훈민정음 (조선 세종, 1443년 창제·1446년 반포)"}],
                        "lv1_front": "🌱 [Lv.1 한국사 기초] 조선 세종이 백성을 위해 창제한 28자 고유의 문자 이름은?",
                        "lv1_back": "훈민정음 (1443년 창제, 1446년 반포)",
                        "lv2_front": "📘 [Lv.2 한국사 연표 빈칸] 조선 {{c1::세종::왕}} 대인 {{c2::1443년::연도}}에 {{c3::훈민정음::문자}}을 창제하고 1446년에 반포하였다.",
                        "lv2_back": "세종 · 1443년 · 훈민정음",
                        "lv3_front": "🔥 [Lv.3 한국사 심화] '훈민정음'을 창제한 왕, 창제·반포 연도, 그리고 창제 원리가 담긴 세계기록유산 책의 이름을 쓰시오.",
                        "lv3_back": "세종 · 1443년 창제(1446년 반포) · 훈민정음 해례본",
                        "target_answer": "훈민정음",
                        "extra_explanation": "조선 세종 25년(1443) 창제, 세종 28년(1446) 반포",
                    },
                ),
                (
                    "khist:event:gapsin_1884",
                    "event",
                    "🏛️ [한국사 핵심] 1884년 김옥균·박영효 등 급진개화파가 우정총국 개국 축하연을 계기로 일으킨 근대적 국정 개혁 사건은?",
                    "갑신정변 (1884년)\n\n💡 해설: 청에 대한 사대 관계 청산, 인민평등권 확립, 호조 중심 재정 일원화 등 14개조 개혁정강을 발표했으나 청군의 개입으로 3일 천하로 끝났습니다.",
                    {
                        "era": "joseon_late",
                        "reign": "gojong",
                        "year": 1884,
                        "senses": [{"id": "s1", "gloss_ko": "갑신정변 (1884년 급진개화파 정변)"}],
                        "lv1_front": "🌱 [Lv.1 한국사 기초] 김옥균 등 급진개화파가 우정총국 개국 축하연에서 일으킨 사건 이름은?",
                        "lv1_back": "갑신정변 (1884년)",
                        "lv2_front": "📘 [Lv.2 한국사 빈칸] {{c1::1884년::연도}} 급진개화파가 우정총국 개국 축하연을 계기로 일으킨 정변을 {{c2::갑신정변::사건명}}이라 한다.",
                        "lv2_back": "1884년 · 갑신정변",
                        "lv3_front": "🔥 [Lv.3 한국사 심화] '갑신정변'이 일어난 연도, 주도 세력, 그리고 발표된 개혁안의 핵심 내용 2가지를 서술하시오.",
                        "lv3_back": "1884년 · 급진개화파(김옥균·박영효) · 청 사대 관계 청산, 인민평등권 제정, 호조 재정 일원화(14개조 개혁정강)",
                        "target_answer": "갑신정변",
                        "extra_explanation": "1884년 급진개화파 정변 (14개조 개혁정강 발표, 3일 천하)",
                    },
                ),
                (
                    "khist:treaty:ganghwa_1876",
                    "treaty",
                    "🏛️ [한국사 핵심] 1876년 운요호 사건을 계기로 조선이 외국(일본)과 맺은 최초의 근대적 조약이자 불평등 조약은?",
                    "강화도 조약 (조일수호조규, 1876년)\n\n💡 해설: 부산 외 2개 항구(원산·인천) 개항, 해안측량권 및 영사재판권(치외법권)을 인정한 불평등 조약입니다.",
                    {
                        "era": "joseon_late",
                        "reign": "gojong",
                        "year": 1876,
                        "senses": [{"id": "s1", "gloss_ko": "강화도 조약 (1876년 최초의 근대적·불평등 조약)"}],
                        "lv1_front": "🌱 [Lv.1 한국사 기초] 1876년 조선이 일본과 맺은 최초의 근대적·불평등 조약 이름은?",
                        "lv1_back": "강화도 조약 (조일수호조규)",
                        "lv2_front": "📘 [Lv.2 한국사 빈칸] {{c1::강화도 조약::조약명}}(1876)은 부산·원산·인천 3포 개항과 {{c2::영사재판권::불평등 독소조항}}(치외법권)을 포함하였다.",
                        "lv2_back": "강화도 조약 · 영사재판권(치외법권)",
                        "lv3_front": "🔥 [Lv.3 한국사 심화] '강화도 조약(1876)'이 불평등 조약으로 평가받는 근거 조항 2가지를 쓰시오.",
                        "lv3_back": "영사재판권(치외법권) 인정 · 일본의 조선 해안측량권 허용",
                        "target_answer": "강화도 조약",
                        "extra_explanation": "1876년 조일수호조규 (최초의 근대적 조약이자 치외법권·해안측량권 불평등 조약)",
                    },
                ),
                (
                    "khist:heritage:jikji_1377",
                    "heritage",
                    "🏛️ [한국사 핵심] 고려 우왕 3년(1377) 청주 흥덕사에서 간행된 현존 세계 최고(最古)의 금속활자본 이름은?",
                    "직지심체요절 (백운화상초록불조직지심체요절)\n\n💡 해설: 구텐베르크 성서보다 78년 앞선 1377년 청주 흥덕사에서 금속활자로 인쇄되었으며 유네스코 세계기록유산입니다.",
                    {
                        "era": "goryeo",
                        "reign": "u_wang",
                        "year": 1377,
                        "senses": [{"id": "s1", "gloss_ko": "직지심체요절 (현존 세계 최고 금속활자본)"}],
                        "lv1_front": "🌱 [Lv.1 한국사 기초] 고려 시대 청주 흥덕사에서 간행된 현존 세계 최고(最古) 금속활자본은?",
                        "lv1_back": "직지심체요절 (1377년)",
                        "lv2_front": "📘 [Lv.2 한국사 빈칸] 고려 우왕 때({{c1::1377년::연도}}) 청주 흥덕사에서 간행된 {{c2::직지심체요절::문화유산}}은 현존 세계 최고의 금속활자본이다.",
                        "lv2_back": "1377년 · 직지심체요절",
                        "lv3_front": "🔥 [Lv.3 한국사 심화] '직지심체요절'이 간행된 시대, 연도, 사찰 이름, 그리고 역사적 의의를 쓰시오.",
                        "lv3_back": "고려 시대(우왕, 1377년) · 청주 흥덕사 · 현존 세계 최고(最古)의 금속활자본(유네스코 세계기록유산)",
                        "target_answer": "직지심체요절",
                        "extra_explanation": "1377년 청주 흥덕사 간행, 현존 세계 최고 금속활자본",
                    },
                ),
            ],
        ),
        "exam-eng:toeic-core": (
            "토익·비즈니스 빈출 핵심 어휘 (추정 레벨)",
            [
                ("word:toeic_implement", "word", "implement", "(정책·계획을) 시행하다, 이행하다", {"senses": [{"id": "s1", "gloss_ko": "시행하다, 실행하다", "pos": "verb"}], "cefr": "B2", "clean_front": "💼 [토익 핵심 어휘] 다음 단어의 뜻은?\nimplement (v.)", "lv1_front": "🌱 [Lv.1 토익 기초] 'implement'의 핵심 뜻은?", "lv1_back": "(정책·계획을) 시행하다, 이행하다", "lv2_front": "📘 [Lv.2 토익 빈칸] The company will {{c1::implement::시행하다}} the new safety policy next month.", "lv2_back": "implement — 시행하다, 이행하다", "lv3_front": "🔥 [Lv.3 비즈니스 영작] '(정책·계획을) 시행하다, 이행하다'에 해당하는 동사를 쓰시오.", "lv3_back": "implement", "target_answer": "시행하다"}),
                ("word:toeic_reimburse", "word", "reimburse", "(경비를) 변제하다, 환급하다", {"senses": [{"id": "s1", "gloss_ko": "변제하다, 상환하다", "pos": "verb"}], "cefr": "C1", "clean_front": "💼 [토익 핵심 어휘] 다음 단어의 뜻은?\nreimburse (v.)", "lv1_front": "🌱 [Lv.1 토익 기초] 'reimburse'의 핵심 뜻은?", "lv1_back": "(경비를) 변제하다, 환급하다", "lv2_front": "📘 [Lv.2 토익 빈칸] Accounting will {{c1::reimburse::변제·환급하다}} your travel expenses within 5 days.", "lv2_back": "reimburse — 변제하다, 환급하다", "lv3_front": "🔥 [Lv.3 비즈니스 영작] '(출장비·경비를) 변제하다, 환급하다'에 해당하는 동사를 쓰시오.", "lv3_back": "reimburse", "target_answer": "변제하다"}),
                ("word:toeic_prerequisite", "word", "prerequisite", "필수 전제 조건, 선수 과목", {"senses": [{"id": "s1", "gloss_ko": "전제 조건, 필수 조건", "pos": "noun"}], "cefr": "C1", "clean_front": "💼 [토익 핵심 어휘] 다음 단어의 뜻은?\nprerequisite (n.)", "lv1_front": "🌱 [Lv.1 토익 기초] 'prerequisite'의 핵심 뜻은?", "lv1_back": "필수 전제 조건, 선수 과목", "lv2_front": "📘 [Lv.2 토익 빈칸] A valid license is a {{c1::prerequisite::필수 전제 조건}} for this position.", "lv2_back": "prerequisite — 필수 전제 조건", "lv3_front": "🔥 [Lv.3 비즈니스 영작] '필수 전제 조건, 선수 과목'을 뜻하는 명사를 쓰시오.", "lv3_back": "prerequisite", "target_answer": "필수 전제 조건"}),
                ("word:toeic_tentative", "word", "tentative", "잠정적인, 임시의", {"senses": [{"id": "s1", "gloss_ko": "잠정적인, 확정이 아닌", "pos": "adj"}], "cefr": "B2", "clean_front": "💼 [토익 핵심 어휘] 다음 단어의 뜻은?\ntentative (adj.)", "lv1_front": "🌱 [Lv.1 토익 기초] 'tentative'의 핵심 뜻은?", "lv1_back": "잠정적인, 임시의", "lv2_front": "📘 [Lv.2 토익 빈칸] We have set a {{c1::tentative::잠정적인}} schedule for the conference.", "lv2_back": "tentative — 잠정적인, 임시의", "lv3_front": "🔥 [Lv.3 비즈니스 영작] '(일정·계획이) 잠정적인, 임시의'를 뜻하는 형용사를 쓰시오.", "lv3_back": "tentative", "target_answer": "잠정적인"}),
            ],
        ),
        "exam-ja:jlpt-n5-n3": (
            "일본어 능력시험(JLPT) N5~N3 필수 어휘 (추정 레벨)",
            [
                ("word:ja_yakusoku", "word", "🇯🇵 [JLPT 필수 어휘] 다음 일본어 단어의 히라가나 읽기와 뜻은?\n約束", "약속 (やくそく / 야쿠소쿠)", {"senses": [{"id": "s1", "gloss_ko": "약속", "pos": "noun"}], "lv1_front": "🌱 [Lv.1 JLPT 기초] '約束'의 우리말 뜻과 읽기는?", "lv1_back": "약속 (やくそく)", "lv2_front": "📘 [Lv.2 JLPT 빈칸] 友達と {{c1::約束::やくそく (약속)}} を守る。", "lv2_back": "約束 (やくそく) — 약속", "lv3_front": "🔥 [Lv.3 JLPT 히라가나 인출] '約束(약속)'의 정확한 히라가나 표기를 쓰시오.", "lv3_back": "やくそく (약속)", "target_answer": "약속 (やくそく)"}),
                ("word:ja_junbi", "word", "🇯🇵 [JLPT 필수 어휘] 다음 일본어 단어의 히라가나 읽기와 뜻은?\n準備", "준비 (じゅんび / 준비)", {"senses": [{"id": "s1", "gloss_ko": "준비", "pos": "noun"}], "lv1_front": "🌱 [Lv.1 JLPT 기초] '準備'의 우리말 뜻과 읽기는?", "lv1_back": "준비 (じゅんび)", "lv2_front": "📘 [Lv.2 JLPT 빈칸] 旅行の {{c1::準備::じゅんび (준비)}} をする。", "lv2_back": "準備 (じゅんび) — 준비", "lv3_front": "🔥 [Lv.3 JLPT 히라가나 인출] '準備(준비)'의 정확한 히라가나 표기를 쓰시오.", "lv3_back": "じゅんび (준비)", "target_answer": "준비 (じゅんび)"}),
                ("word:ja_keiken", "word", "🇯🇵 [JLPT 필수 어휘] 다음 일본어 단어의 히라가나 읽기와 뜻은?\n経験", "경험 (けいけん / 케이켄)", {"senses": [{"id": "s1", "gloss_ko": "경험", "pos": "noun"}], "lv1_front": "🌱 [Lv.1 JLPT 기초] '経験'의 우리말 뜻과 읽기는?", "lv1_back": "경험 (けいけん)", "lv2_front": "📘 [Lv.2 JLPT 빈칸] 良い {{c1::経験::けいけん (경험)}} になりました。", "lv2_back": "経験 (けいけん) — 경험", "lv3_front": "🔥 [Lv.3 JLPT 히라가나 인출] '経験(경험)'의 정확한 히라가나 표기를 쓰시오.", "lv3_back": "けいけん (경험)", "target_answer": "경험 (けいけん)"}),
                ("word:ja_tashika", "word", "🇯🇵 [JLPT 필수 어휘] 다음 일본어 단어의 히라가나 읽기와 뜻은?\n確か", "확실히, 틀림없이 (たしか / 타시카)", {"senses": [{"id": "s1", "gloss_ko": "확실히, 분명히", "pos": "adv"}], "lv1_front": "🌱 [Lv.1 JLPT 기초] '確か'의 우리말 뜻과 읽기는?", "lv1_back": "확실히, 틀림없이 (たしか)", "lv2_front": "📘 [Lv.2 JLPT 빈칸] {{c1::確か::たしか (분명히)}} 彼の名前は田中さんです。", "lv2_back": "確か (たしか) — 확실히, 분명히", "lv3_front": "🔥 [Lv.3 JLPT 히라가나 인출] '確か(확실히)'의 정확한 히라가나 표기를 쓰시오.", "lv3_back": "たしか (확실히)", "target_answer": "확실히 (たしか)"}),
            ],
        ),
        "ko-idiom:essential": (
            "필수 사자성어·고사성어 핵심",
            [
                ("idiom:gojingamrae", "idiom", "📜 [사자성어] 다음 한자성어의 독음(읽기)과 속뜻은?\n苦盡甘來", "고진감래 — 고생 끝에 즐거움(낙)이 온다\n\n💡 해설: 괴로울 고(苦)·다할 진(盡)·달 감(甘)·올 래(來). 쓴 것이 다하면 단 것이 온다는 뜻입니다.", {"hanja": "苦盡甘來", "reading": "고진감래", "senses": [{"id": "s1", "gloss_ko": "고진감래 — 고생 끝에 즐거움이 옴"}], "char_meanings": ["괴로울 고", "다할 진", "달 감", "올 래"], "lv1_front": "🌱 [Lv.1 사자성어 기초] '苦盡甘來'의 독음(4글자)과 뜻은?", "lv1_back": "고진감래 — 고생 끝에 낙이 온다", "lv2_front": "📘 [Lv.2 사자성어 빈칸] 쓴 것이 다하면 단 것이 온다는 뜻으로, 고생 끝에 낙이 옴을 이르는 성어는 {{c1::고진감래::독음 4글자}}(苦盡甘來)이다.", "lv2_back": "고진감래 (苦盡甘來)", "lv3_front": "🔥 [Lv.3 사자성어 역방향] '쓴 것이 다하면 단 것이 온다(고생 끝에 낙이 온다)'를 뜻하는 사자성어를 쓰시오.", "lv3_back": "고진감래 (苦盡甘來)", "target_answer": "고진감래", "extra_explanation": "苦(괴로울 고) 盡(다할 진) 甘(달 감) 來(올 래)"}),
                ("idiom:daegimanseong", "idiom", "📜 [사자성어] 다음 한자성어의 독음(읽기)과 속뜻은?\n大器晩成", "대기만성 — 크게 될 인물은 오랜 노력 끝에 늦게 이루어진다\n\n💡 해설: 클 대(大)·그릇 기(器)·늦을 만(晩)·이룰 성(成). 큰 그릇은 만드는 데 시간이 오래 걸린다는 뜻입니다.", {"hanja": "大器晩成", "reading": "대기만성", "senses": [{"id": "s1", "gloss_ko": "대기만성 — 큰 인물은 늦게 이루어짐"}], "char_meanings": ["클 대", "그릇 기", "늦을 만", "이룰 성"], "lv1_front": "🌱 [Lv.1 사자성어 기초] '大器晩成'의 독음(4글자)과 뜻은?", "lv1_back": "대기만성 — 큰 인물은 늦게 이루어진다", "lv2_front": "📘 [Lv.2 사자성어 빈칸] 큰 그릇은 늦게 이루어진다는 뜻으로, 크게 될 인물은 오랜 수양 끝에 대성함을 이르는 말은 {{c1::대기만성::독음 4글자}}(大器晩成)이다.", "lv2_back": "대기만성 (大器晩成)", "lv3_front": "🔥 [Lv.3 사자성어 역방향] '큰 그릇은 늦게 이루어진다(크게 될 인물은 늦게 대성한다)'를 뜻하는 사자성어를 쓰시오.", "lv3_back": "대기만성 (大器晩成)", "target_answer": "대기만성", "extra_explanation": "大(클 대) 器(그릇 기) 晩(늦을 만) 成(이룰 성)"}),
                ("idiom:yeokjisaji", "idiom", "📜 [사자성어] 다음 한자성어의 독음(읽기)과 속뜻은?\n易地思之", "역지사지 — 상대편의 처지나 입장에서 바꾸어 생각한다\n\n💡 해설: 바꿀 역(易)·땅 지(地)·생각 사(思)·갈 지(之). 처지를 바꾸어 생각함을 뜻합니다.", {"hanja": "易地思之", "reading": "역지사지", "senses": [{"id": "s1", "gloss_ko": "역지사지 — 입장을 바꾸어 생각함"}], "char_meanings": ["바꿀 역", "땅 지", "생각 사", "갈 지"], "lv1_front": "🌱 [Lv.1 사자성어 기초] '易地思之'의 독음(4글자)과 뜻은?", "lv1_back": "역지사지 — 다른 사람의 입장에서 생각함", "lv2_front": "📘 [Lv.2 사자성어 빈칸] 처지를 바꾸어 생각한다는 뜻으로, 상대방의 입장에서 헤아려 봄을 이르는 성어는 {{c1::역지사지::독음 4글자}}(易地思之)이다.", "lv2_back": "역지사지 (易地思之)", "lv3_front": "🔥 [Lv.3 사자성어 역방향] '처지를 바꾸어 상대방의 입장에서 생각한다'를 뜻하는 사자성어를 쓰시오.", "lv3_back": "역지사지 (易地思之)", "target_answer": "역지사지", "extra_explanation": "易(바꿀 역) 地(땅 지) 思(생각 사) 之(갈 지)"}),
                ("idiom:일석이조", "idiom", "📜 [사자성어] 다음 한자성어의 독음(읽기)과 속뜻은?\n一石二鳥", "일석이조 — 한 가지 일로 두 가지 이익을 동시에 얻는다\n\n💡 해설: 한 일(一)·돌 석(石)·두 이(二)·새 조(鳥). 돌 하나로 새 두 마리를 잡는다는 뜻입니다.", {"hanja": "一石二鳥", "reading": "일석이조", "senses": [{"id": "s1", "gloss_ko": "일석이조 — 한 가지 일로 두 가지 이득을 얻음"}], "char_meanings": ["한 일", "돌 석", "두 이", "새 조"], "lv1_front": "🌱 [Lv.1 사자성어 기초] '一石二鳥'의 독음(4글자)과 뜻은?", "lv1_back": "일석이조 — 한 가지 일로 두 가지 이익을 얻음", "lv2_front": "📘 [Lv.2 사자성어 빈칸] 돌 한 개로 새 두 마리를 잡는다는 뜻의 사자성어는 {{c1::일석이조::독음 4글자}}(一石二鳥)이다.", "lv2_back": "일석이조 (一石二鳥)", "lv3_front": "🔥 [Lv.3 사자성어 역방향] '돌 하나로 새 두 마리를 잡는다(한 가지 일로 두 가지 이익을 얻음)'를 뜻하는 사자성어를 쓰시오.", "lv3_back": "일석이조 (一石二鳥)", "target_answer": "일석이조", "extra_explanation": "一(한 일) 石(돌 석) 二(두 이) 鳥(새 조)"}),
            ],
        ),
        "law-statute:constitution": (
            "대한민국 헌법 및 기본법 핵심 조문",
            [
                ("statute:const_art1", "statute", "⚖️ [헌법 제1조] 대한민국의 국체(국가 형태)와 주권의 소재를 규정한 헌법 제1조 제1항·제2항의 핵심 내용은?", "민주공화국 · 국민주권 (주권은 국민에게 있고 모든 권력은 국민으로부터 나온다)", {"law_id": "헌법", "article": "제1조", "effective_from": "1988-02-25", "senses": [{"id": "s1", "gloss_ko": "민주공화국 및 국민주권 원리"}], "lv1_front": "🌱 [Lv.1 헌법 기초] 대한민국 헌법 제1조가 선언하는 국가 형태와 주권의 주체는?", "lv1_back": "민주공화국 · 주권은 국민에게 있다(국민주권)", "lv2_front": "📘 [Lv.2 헌법 조문 빈칸] 헌법 제1조 ① 대한민국은 {{c1::민주공화국::국체}}이다. ② 대한민국의 {{c2::주권::핵심 권력}}은 국민에게 있고, 모든 권력은 국민으로부터 나온다.", "lv2_back": "민주공화국 · 주권", "lv3_front": "🔥 [Lv.3 헌법 심화] '대한민국은 민주공화국이며 주권은 국민에게 있다'고 규정한 헌법 조문 번호와 기본 원리를 쓰시오.", "lv3_back": "헌법 제1조 (민주공화국 원리 및 국민주권주의)", "target_answer": "민주공화국 · 국민주권"}),
                ("statute:const_art10", "statute", "⚖️ [헌법 기본권] 모든 국민이 가지는 '인간으로서의 존엄과 가치' 및 '행복추구권'과 국가의 기본권 보장 의무를 규정한 헌법 조문은?", "헌법 제10조 (인간의 존엄과 가치 · 행복추구권)\n\n💡 해설: 모든 국민은 인간으로서의 존엄과 가치를 가지며, 행복을 추구할 권리를 가진다.", {"law_id": "헌법", "article": "제10조", "effective_from": "1988-02-25", "senses": [{"id": "s1", "gloss_ko": "인간의 존엄과 가치, 행복추구권"}], "lv1_front": "🌱 [Lv.1 헌법 기초] 인간의 존엄과 가치 및 행복추구권을 규정한 대한민국 헌법 조문은?", "lv1_back": "헌법 제10조", "lv2_front": "📘 [Lv.2 헌법 조문 빈칸] 헌법 {{c1::제10조::조문}}: 모든 국민은 인간으로서의 존엄과 가치를 가지며, {{c2::행복을 추구할 권리::포괄적 기본권}}를 가진다.", "lv2_back": "제10조 · 행복을 추구할 권리(행복추구권)", "lv3_front": "🔥 [Lv.3 헌법 심화] 헌법 제10조가 보장하는 2대 핵심 권리와 국가의 의무를 서술하시오.", "lv3_back": "인간으로서의 존엄과 가치, 행복추구권 · 국가는 개인이 가지는 불가침의 기본적 인권을 확인하고 이를 보장할 의무를 진다.", "target_answer": "헌법 제10조 (인간의 존엄과 가치·행복추구권)"}),
                ("statute:const_art37_2", "statute", "⚖️ [헌법 기본권 제한] 국민의 기본권을 법률로써 제한할 수 있는 3대 목적 사유와 그 한계(과잉금지원칙)를 규정한 조문은?", "헌법 제37조 제2항 — 국가안전보장 · 질서유지 · 공공복리 (자유와 권리의 본질적 내용 침해 금지)", {"law_id": "헌법", "article": "제37조 제2항", "effective_from": "1988-02-25", "senses": [{"id": "s1", "gloss_ko": "기본권 제한의 한계 및 비례원칙(과잉금지원칙)"}], "lv1_front": "🌱 [Lv.1 헌법 기초] 기본권 제한의 한계(과잉금지원칙)를 규정한 헌법 조문은?", "lv1_back": "헌법 제37조 제2항", "lv2_front": "📘 [Lv.2 헌법 조문 빈칸] 헌법 제37조 제2항: 기본권은 {{c1::국가안전보장·질서유지·공공복리::3대 목적}}를 위하여 필요한 경우에 한하여 {{c2::법률::형식}}로써 제한할 수 있다.", "lv2_back": "국가안전보장·질서유지·공공복리 · 법률", "lv3_front": "🔥 [Lv.3 헌법 심화] 헌법 제37조 제2항에 따른 기본권 제한의 3대 목적 사유와 절대적 한계를 쓰시오.", "lv3_back": "목적: 국가안전보장, 질서유지, 공공복리 · 한계: 자유와 권리의 본질적인 내용을 침해할 수 없음(과잉금지원칙)", "target_answer": "헌법 제37조 제2항 (국가안전보장·질서유지·공공복리)"}),
            ],
        ),
        "sci-element-formula:core": (
            "주기율표 필수 원소 및 물리·화학·수학 공식",
            [
                ("sci:ohm_law", "formula", "🔬 [물리 공식] 전기 회로에서 전압(V), 전류(I), 저항(R) 사이의 관계를 나타내는 '옴의 법칙' 관계식은?", "V = I × R (전압 = 전류 × 저항, I = V / R)\n\n💡 해설: 도체에 흐르는 전류(I)의 세기는 전압(V)에 비례하고 저항(R)에 반비례합니다.", {"expression": "V = I × R", "senses": [{"id": "s1", "gloss_ko": "V = I × R (전압 = 전류 × 저항)"}], "lv1_front": "🌱 [Lv.1 과학 기초] 전압(V), 전류(I), 저항(R)의 관계를 나타낸 '옴의 법칙' 공식은?", "lv1_back": "V = I × R (전압 = 전류 × 저항)", "lv2_front": "📘 [Lv.2 과학 빈칸] 옴의 법칙에서 전류 I는 전압 V에 비례하고 저항 R에 반비례하므로 관계식은 {{c1::V = I × R::옴의 법칙}}이다.", "lv2_back": "V = I × R (또는 I = V / R)", "lv3_front": "🔥 [Lv.3 과학 응용 계산] 저항이 10Ω인 회로에 2A의 전류가 흐를 때 걸리는 전압(V)과 적용된 법칙 이름을 쓰시오.", "lv3_back": "20V · 옴의 법칙 (V = I × R = 2A × 10Ω = 20V)", "target_answer": "V = I × R"}),
                ("sci:elem_fe", "element", "🔬 [화학 원소] 원자번호 26번이며 혈액 속 헤모글로빈의 핵심 성분이자 산업의 중심이 되는 전이금속의 이름과 원소기호는?", "철 (Fe, Iron)\n\n💡 해설: 원자번호 26번 원소기호 Fe(라틴어 Ferrum 유래)로, 산소를 운반하는 헤모글로빈과 강철 합금의 주성분입니다.", {"expression": "Fe (26)", "senses": [{"id": "s1", "gloss_ko": "철 (Fe, 원자번호 26)"}], "lv1_front": "🌱 [Lv.1 화학 기초] 원소기호 'Fe'(원자번호 26)는 어떤 원소인가요?", "lv1_back": "철 (Iron)", "lv2_front": "📘 [Lv.2 화학 빈칸] 헤모글로빈의 중심 금속이자 원자번호 26번인 {{c1::철 (Fe)::원소명·기호}}은 대표적인 전이금속이다.", "lv2_back": "철 (Fe)", "lv3_front": "🔥 [Lv.3 화학 심화] 원자번호 26번 '철(Iron)'의 원소기호와 생체 내(혈액) 주요 역할을 쓰시오.", "lv3_back": "Fe · 적혈구 헤모글로빈의 구성 성분으로 산소 운반", "target_answer": "철 (Fe)"}),
                ("sci:quadratic_formula", "formula", "📐 [수학 공식] 이차방정식 ax² + bx + c = 0 (단, a ≠ 0)의 해를 구하는 '근의 공식'과 판별식 D는?", "x = (-b ± √(b² - 4ac)) / 2a · 판별식 D = b² - 4ac\n\n💡 해설: D > 0이면 서로 다른 두 실근, D = 0이면 중근, D < 0이면 서로 다른 두 허근을 가집니다.", {"expression": "x = (-b ± √(b² - 4ac)) / 2a", "senses": [{"id": "s1", "gloss_ko": "x = (-b ± √(b² - 4ac)) / 2a"}], "lv1_front": "🌱 [Lv.1 수학 기초] 이차방정식 ax² + bx + c = 0의 실근 개수를 판별하는 판별식 D는?", "lv1_back": "D = b² - 4ac", "lv2_front": "📘 [Lv.2 수학 빈칸] 이차방정식 ax² + bx + c = 0의 근의 공식은 x = {{c1::(-b ± √(b² - 4ac)) / 2a::근의 공식}}이다.", "lv2_back": "x = (-b ± √(b² - 4ac)) / 2a", "lv3_front": "🔥 [Lv.3 수학 심화] 이차방정식 ax² + bx + c = 0의 근의 공식을 쓰고, 판별식 D의 부호에 따른 근의 종류를 설명하시오.", "lv3_back": "x = (-b ± √(b² - 4ac)) / 2a · D>0: 서로 다른 두 실근, D=0: 중근, D<0: 서로 다른 두 허근", "target_answer": "x = (-b ± √(b² - 4ac)) / 2a"}),
            ],
        ),
        "cert-it:core": (
            "정보처리기사·컴퓨터활용능력 핵심 개념 팩트",
            [
                ("cert:acid_tx", "fact_item", "💻 [정보처리기사 · DB] 데이터베이스 트랜잭션이 안전하게 수행되기 위해 보장해야 하는 4대 특성(ACID)은?", "원자성(Atomicity) · 일관성(Consistency) · 격리성(Isolation) · 영속성(Durability)", {"expression": "ACID", "senses": [{"id": "s1", "gloss_ko": "원자성 · 일관성 · 격리성 · 영속성"}], "lv1_front": "🌱 [Lv.1 IT 기초] DB 트랜잭션의 4대 특성 약자(ACID)가 뜻하는 우리말 4가지는?", "lv1_back": "원자성(Atomicity), 일관성(Consistency), 격리성(Isolation), 영속성(Durability)", "lv2_front": "📘 [Lv.2 IT 빈칸] 트랜잭션 연산이 모두 반영되거나 전혀 반영되지 않아야 하는 All-or-Nothing 특성은 {{c1::원자성 (Atomicity)::ACID 중 A}}이다.", "lv2_back": "원자성 (Atomicity)", "lv3_front": "🔥 [Lv.3 IT 심화] DB 트랜잭션의 4대 특성(ACID)을 영문과 우리말로 모두 나열하시오.", "lv3_back": "Atomicity(원자성) · Consistency(일관성) · Isolation(격리성) · Durability(영속성)", "target_answer": "원자성 · 일관성 · 격리성 · 영속성"}),
                ("cert:osi_7layer", "fact_item", "💻 [정보처리기사 · 네트워크] OSI 7계층을 하위 1계층부터 상위 7계층까지 순서대로 나열하면?", "물리 - 데이터링크 - 네트워크 - 전송 - 세션 - 표현 - 응용 (물·데·네·전·세·표·응)", {"expression": "물·데·네·전·세·표·응", "senses": [{"id": "s1", "gloss_ko": "물리-데이터링크-네트워크-전송-세션-표현-응용"}], "lv1_front": "🌱 [Lv.1 IT 기초] OSI 7계층의 1계층~7계층 앞글자 순서는?", "lv1_back": "물·데·네·전·세·표·응 (물리-데이터링크-네트워크-전송-세션-표현-응용)", "lv2_front": "📘 [Lv.2 IT 빈칸] OSI 7계층 중 IP 라우팅을 담당하는 3계층은 {{c1::네트워크 계층::3계층}}이고, TCP/UDP 종단 간 전달을 담당하는 4계층은 {{c2::전송 계층::4계층}}이다.", "lv2_back": "네트워크 계층(3계층) · 전송 계층(4계층)", "lv3_front": "🔥 [Lv.3 IT 심화] OSI 7계층을 1계층부터 7계층까지 순서대로 모두 쓰시오.", "lv3_back": "1.물리(Physical) - 2.데이터링크(Data Link) - 3.네트워크(Network) - 4.전송(Transport) - 5.세션(Session) - 6.표현(Presentation) - 7.응용(Application)", "target_answer": "물리 - 데이터링크 - 네트워크 - 전송 - 세션 - 표현 - 응용"}),
                ("cert:db_index_btree", "fact_item", "💻 [정보처리기사 · DB] 루트·브랜치·리프 노드가 균형을 유지하며 탐색 성능을 O(log N)으로 높이는 대표적인 DB 인덱스 자료구조는?", "B-Tree 인덱스 (Balanced Tree Index, O(log N) 탐색)", {"expression": "B-Tree Index", "senses": [{"id": "s1", "gloss_ko": "B-Tree 인덱스 (O(log N) 균형 탐색 트리)"}], "lv1_front": "🌱 [Lv.1 IT 기초] 루트·브랜치·리프 노드가 균형을 유지하며 O(log N) 탐색을 제공하는 DB 기본 인덱스 구조는?", "lv1_back": "B-Tree 인덱스 (또는 B+Tree 인덱스)", "lv2_front": "📘 [Lv.2 IT 빈칸] {{c1::B-Tree::자료구조}} 인덱스는 균형 트리를 유지하여 평균 및 최악 탐색 시간복잡도 {{c2::O(log N)::시간복잡도}}을 보장한다.", "lv2_back": "B-Tree · O(log N)", "lv3_front": "🔥 [Lv.3 IT 심화] 데이터베이스에서 B-Tree 인덱스를 사용하는 이유와 탐색 시간복잡도를 쓰시오.", "lv3_back": "루트·브랜치·리프 노드의 균형을 유지해 전체 테이블 스캔(O(N)) 없이 O(log N) 시간복잡도로 고속 조회·범위 검색을 수행하기 위해", "target_answer": "B-Tree 인덱스 (O(log N))"}),
            ],
        ),
        **build_tier_r_moe_collections(),
    }

    for col_id, (level_label, entries) in balanced_collections.items():
        for idx, (ekey, etype, hw, gloss, facet) in enumerate(entries, start=1):
            builder.add_entry(
                entry_key=ekey,
                entry_type=etype,
                headword=hw,
                norm_key=hw,
                gloss_ko=gloss,
                facet_json=facet,
                source_id="anki_self_fact",
                difficulty_rank=idx,
            )
            builder.add_collection_item(
                collection_id=col_id,
                entry_key=ekey,
                ordinal=idx,
                level_label=level_label,
            )

    return builder.finalize_pack()


def ensure_starter_k12_and_exam_pack(db_path: str | Path) -> dict[str, Any]:
    """Verify existing `Tier R` starter pack in read-only mode or build atomically via `.tmp.<pid>` + `os.replace` (Invariant I-4 / AC-2)."""
    import os

    target_path = Path(db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    def _verify_ro_pack(candidate_path: Path) -> dict[str, Any] | None:
        if not candidate_path.is_file():
            return None
        try:
            conn = sqlite3.connect(f"file:{candidate_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                qc = conn.execute("PRAGMA quick_check").fetchone()
                if qc is None or str(qc[0]).lower() != "ok":
                    return None
                fk_errs = conn.execute("PRAGMA foreign_key_check").fetchall()
                if fk_errs:
                    return None
                meta_row = conn.execute("SELECT * FROM pack_meta LIMIT 1").fetchone()
                if meta_row is None or str(meta_row["pack_version"]) != "1.0.0":
                    return None
                rows = conn.execute(
                    "SELECT entry_key, content_hash FROM ref_entries ORDER BY entry_key ASC"
                ).fetchall()
                digest = hashlib.sha256()
                for r in rows:
                    digest.update(f"{r['entry_key']}:{r['content_hash']}\n".encode("utf-8"))
                if digest.hexdigest() != str(meta_row["content_sha256"]):
                    return None
                # Ensure required textbooks have unit entries and v5.4 spoiler-free multi-level facets
                hist_cnt = conn.execute(
                    "SELECT COUNT(*) FROM ref_unit_entries WHERE textbook_id = 'kr.mid2.hist.miraeen.2022'"
                ).fetchone()[0]
                if int(hist_cnt) < 1:
                    return None
                g_row = conn.execute(
                    "SELECT facet_json FROM ref_entries WHERE entry_key = 'grammar:mid1_u1_be_verb'"
                ).fetchone()
                if g_row is None or '"lv1_front"' not in str(g_row["facet_json"]):
                    return None
                moe_cnt = conn.execute(
                    "SELECT COUNT(*) FROM ref_collections WHERE collection_id = 'moe-eng:elem-3-4'"
                ).fetchone()[0]
                if int(moe_cnt) < 1:
                    return None
                math_entry_cnt = conn.execute(
                    "SELECT COUNT(*) FROM ref_collections WHERE collection_id = 'moe-math:core-formulas'"
                ).fetchone()[0]
                if int(math_entry_cnt) < 7:
                    return None
                meta = dict(meta_row)
                meta["file_sha256"] = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
                meta["rebuilt"] = False
                return meta
            finally:
                conn.close()
        except Exception:
            return None

    verified = _verify_ro_pack(target_path)
    if verified is not None:
        return verified

    tmp_path = Path(f"{target_path}.tmp.{os.getpid()}")
    try:
        build_starter_k12_and_exam_pack(tmp_path)
        checked = _verify_ro_pack(tmp_path)
        if checked is None:
            raise RuntimeError("Newly built starter pack failed RO verification")
        os.replace(tmp_path, target_path)
        for suffix in ("-wal", "-shm"):
            wal_p = Path(f"{tmp_path}{suffix}")
            if wal_p.exists():
                wal_p.unlink()
        checked["file_sha256"] = hashlib.sha256(target_path.read_bytes()).hexdigest()
        checked["rebuilt"] = True
        return checked
    except Exception:
        for suffix in ("", "-wal", "-shm"):
            p = Path(f"{tmp_path}{suffix}")
            if p.exists():
                p.unlink()
        raise



def inspect_pack_catalog(pack_db_path: str | Path) -> dict[str, Any]:
    """Read textbooks (with units) and collections (with item counts) from a `Tier R` SQLite pack."""
    conn = sqlite3.connect(f"file:{Path(pack_db_path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tb_rows = conn.execute(
            """
            SELECT * FROM ref_textbooks
            WHERE retired = 0
            ORDER BY school_level ASC, grade ASC, textbook_id ASC
            """
        ).fetchall()
        textbooks: list[dict[str, Any]] = []
        for tb in tb_rows:
            tdict = dict(tb)
            units = conn.execute(
                """
                SELECT u.*, COUNT(rue.entry_key) AS entry_count
                FROM ref_curriculum_units u
                LEFT JOIN ref_unit_entries rue ON u.unit_id = rue.unit_id
                WHERE u.textbook_id = ?
                GROUP BY u.unit_id
                ORDER BY u.unit_ordinal ASC
                """,
                (str(tb["textbook_id"]),),
            ).fetchall()
            tdict["units"] = [dict(u) for u in units]
            textbooks.append(tdict)

        col_rows = conn.execute(
            """
            SELECT collection_id, level_label, COUNT(*) AS item_count
            FROM ref_collections
            GROUP BY collection_id, level_label
            ORDER BY collection_id ASC
            """
        ).fetchall()
        collections = [dict(c) for c in col_rows]
        return {"textbooks": textbooks, "collections": collections}
    finally:
        conn.close()

