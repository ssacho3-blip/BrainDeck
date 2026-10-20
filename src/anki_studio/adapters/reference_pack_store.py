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
    ("k12_science", None, "과학"),
    ("language", None, "어학/외국어"),
    ("hanja", None, "한자/어휘"),
    ("korean_history", None, "한국사"),
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
                INSERT INTO ref_entries (
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
                INSERT INTO ref_collections (collection_id, entry_key, ordinal, level_label)
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
                conn.execute("COMMIT")
            finally:
                conn.close()

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
                INSERT OR REPLACE INTO installed_packs (
                    pack_id, pack_version, file_sha256, content_sha256, local_path,
                    state, license_spdx, redistribution_allowed, installed_at_epoch_sec
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        now_sec: int = 1792483200,
    ) -> dict[str, Any]:
        entry_key = str(entry_row["entry_key"])
        entry_type = str(entry_row["entry_type"])
        headword = str(entry_row["headword"])
        gloss_ko = str(entry_row["gloss_ko"] or "")
        reading = str(entry_row["reading"] or "")
        ref_hash = str(entry_row["content_hash"])
        facet_raw = str(entry_row["facet_json"])

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
        front = headword
        back = f"{gloss_ko} ({reading})" if reading else gloss_ko

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
                    ref_pack_version = ?,
                    ref_content_hash = ?,
                    modified_at_epoch_ms = ?
                WHERE id = ?
                """,
                (new_front, new_back, pack_version, ref_hash, now_sec * 1000, note_id),
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
                modified_at_epoch_ms, created_at_epoch_sec
            ) VALUES (?, ?, ?, 'pack_materialized', ?, ?, ?, ?, 'basic', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guid,
                content_hash,
                deck_id,
                pack_id,
                entry_key,
                pack_version,
                ref_hash,
                pattern,
                front,
                back,
                facet_raw,
                provenance,
                textbook_id,
                curriculum_unit_id,
                textbook_page_no,
                0 if redistribution_allowed else 1,
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
                for row in ref_rows:
                    if len(materialized) >= daily_new_limit:
                        break
                    max_ord_seen = int(row["ordinal"])
                    item = self._materialize_ref_entry_into_tx(
                        conn,
                        deck_id=deck_id,
                        deck_sync_id=deck_sync_id,
                        pack_id=pack_id,
                        pack_version=pack_version,
                        redistribution_allowed=redistribution_allowed,
                        entry_row=row,
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


def build_starter_k12_and_exam_pack(db_path: str | Path) -> dict[str, Any]:
    """Build a representative `Tier R` starter pack containing Hanja 1800, Korean History, and Middle-School English Textbook Index."""
    builder = ReferencePackBuilder(db_path)
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
        title="Anki Studio 2.0 자체 편찬 뜻풀이 및 단원 어휘 색인",
        publisher="Anki Studio",
        license_class="FACT_SELF_AUTHORED",
        snapshot_sha256="2" * 64,
    )

    # 1. Hanja 1800 starter entries (with CJK compatibility ideograph test case)
    hanja_entries = [
        (
            "hanja:U+6A02",
            "\uF914",  # CJK compatibility ideograph for 樂(락)
            "락/악/요",
            "즐길 락, 노래 악, 좋아할 요",
            {
                "facet_schema_version": 1,
                "codepoint": "U+6A02",
                "eum": ["락", "악", "요"],
                "hun": {"락": "즐길", "악": "노래", "요": "좋아할"},
                "dueum": {"락": "낙"},
                "radical": "木",
                "strokes": 15,
            },
        ),
        (
            "hanja:U+5B78",
            "學",
            "학",
            "배울 학",
            {
                "facet_schema_version": 1,
                "codepoint": "U+5B78",
                "eum": ["학"],
                "hun": {"학": "배울"},
                "dueum": {},
                "radical": "子",
                "strokes": 16,
            },
        ),
        (
            "hanja:U+6821",
            "校",
            "교",
            "학교 교",
            {
                "facet_schema_version": 1,
                "codepoint": "U+6821",
                "eum": ["교"],
                "hun": {"교": "학교"},
                "dueum": {},
                "radical": "木",
                "strokes": 10,
            },
        ),
    ]
    for idx, (ekey, hw, reading, gloss, facet) in enumerate(hanja_entries, start=1):
        builder.add_entry(
            entry_key=ekey,
            entry_type="hanja_char",
            headword=hw,
            norm_key=hw,
            reading=reading,
            gloss_ko=gloss,
            facet_json=facet,
            source_id="anki_self_fact",
            difficulty_rank=idx,
        )
        builder.add_collection_item(
            collection_id="moe-hanja-1800:middle",
            entry_key=ekey,
            ordinal=idx,
            level_label="중학 기초한자",
        )

    # 2. Middle School Grade 2 English Textbook (동아출판 윤정미 외)
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
        title="중학교 영어 2 (윤정미)",
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
            facet_json={"facet_schema_version": 1, "senses": [{"id": "s1", "gloss_ko": gloss, "pos": pos}]},
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

    return builder.finalize_pack()
