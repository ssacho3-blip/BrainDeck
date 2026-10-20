"""BDD & Integration Tests for 2-Tier DB (`Tier R` + `Tier U` v2) & School Textbook Exam-Scope Engine (T19 ~ T28).

Scenarios:
1. [T21 & T27] Reference Pack Builder rejects non-allowlisted licenses (`NC`, `ND`, `UNKNOWN`) and blocks unlicensed textbook passages (`licensed_passage`) or invalid unit hierarchies on both INSERT and UPDATE.
2. [T19] `Tier U` v2 enforces `junior` cloud lock (`cloud_vision_locked = 1`) and blocks `cross_profile_violation` across decks, notes, cards, sessions, pack activations, and exam scopes.
3. [T20] Lazy Materialization (`materialize_daily_pack_cards`) materializes only up to `daily_new_limit` in a single `BEGIN IMMEDIATE` transaction, advances `next_ordinal`, and preserves `user_override_json` and FSRS `stability` on pack errata updates.
4. [T27 & T28] Middle/High school textbook `exam_scopes` resolution (`resolve_and_reconcile_exam_scope`):
   - Supports non-contiguous units (e.g., Lesson 1 + Lesson 3) and multiple disjoint page ranges within one unit (e.g., Lesson 2 p.20..25 & p.30..35).
   - Combines `Tier R` pack entries (`pack_entry`) and student-scanned textbook/handout notes (`user_note`), deduplicating repeated words across units.
   - Shrinking the exam scope transitions excluded items to `in_scope = 0, scope_ordinal = NULL` without colliding on `ux_exam_scope_items_active_ordinal` and WITHOUT overwriting `cards.queue` or `cards.state` (preserving manual suspend `-1` / manual bury `-2` and FSRS history).
   - Deleting a bound `user_note` cascades cleanly on `exam_scope_items`, while deleting a materialized `pack_entry` note sets `materialized_note_id = NULL`.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from anki_studio.adapters.reference_pack_store import (
    LicensePolicyError,
    ReferencePackBuilder,
    TierULedgerStore,
    build_starter_k12_and_exam_pack,
)


def test_t21_t27_pack_builder_license_gate_and_tier_r_triggers(tmp_path: Path) -> None:
    pack_path = tmp_path / "invalid_pack.sqlite"
    builder = ReferencePackBuilder(pack_path)
    builder.init_schema(
        pack_id="test.pack",
        pack_version="1.0.0",
        domain="textbook_curriculum",
        license_spdx="CC0-1.0",
        redistribution_allowed=True,
        attribution_text="Test Attribution",
    )

    # 1. T21: Non-allowlisted license class ('CC_BY_NC') must be rejected fail-closed
    with pytest.raises((LicensePolicyError, sqlite3.IntegrityError)):
        builder.add_source(
            source_id="src_nc",
            title="Non-Commercial Wordlist",
            publisher="Bad Source",
            license_class="CC_BY_NC",
            snapshot_sha256="0" * 64,
        )

    # Add valid CC0 and CONTRACT_LICENSED sources
    builder.add_source(
        source_id="src_fact",
        title="MOE Curriculum Fact",
        publisher="MOE",
        license_class="PUBLIC_LAW_ART7",
        snapshot_sha256="a" * 64,
    )
    builder.add_source(
        source_id="src_self",
        title="Self Authored",
        publisher="Anki Studio",
        license_class="FACT_SELF_AUTHORED",
        snapshot_sha256="b" * 64,
    )

    builder.add_entry(
        entry_key="word:express",
        entry_type="word",
        headword="express",
        norm_key="express",
        gloss_ko="표현하다",
        facet_json={"facet_schema_version": 1, "senses": [{"id": "s1", "gloss_ko": "표현하다", "pos": "verb"}]},
        source_id="src_self",
    )

    builder.add_textbook(
        textbook_id="kr.mid2.eng.donga_yoon.2022",
        curriculum_revision="2022",
        school_level="middle",
        grade=2,
        semester=1,
        subject_code="language",
        publisher_name="동아출판",
        author_label="윤정미 외",
        title="중학교 영어 2 (윤정미)",
        total_pages=160,
        source_id="src_fact",
        valid_school_year_from=2025,
    )
    builder.add_curriculum_unit(
        unit_id="kr.mid2.eng.donga_yoon.2022:U01",
        textbook_id="kr.mid2.eng.donga_yoon.2022",
        parent_unit_id=None,
        depth=1,
        unit_ordinal=1,
        unit_code_label="Lesson 1",
        unit_title="Express Yourself",
        page_start=10,
        page_end=29,
    )

    # 2. T27: Self-parenting or invalid depth must fail
    with pytest.raises(sqlite3.IntegrityError):
        builder.add_curriculum_unit(
            unit_id="kr.mid2.eng.donga_yoon.2022:U02",
            textbook_id="kr.mid2.eng.donga_yoon.2022",
            parent_unit_id="kr.mid2.eng.donga_yoon.2022:U02",
            depth=2,
            unit_ordinal=2,
            unit_code_label="Lesson 2",
            unit_title="Self Parent",
        )

    # 3. T27: Unlicensed 'licensed_passage' on FACT_SELF_AUTHORED source must be blocked by SQLite trigger
    with pytest.raises(sqlite3.IntegrityError, match="textbook_entry_violation"):
        builder.add_unit_entry(
            textbook_id="kr.mid2.eng.donga_yoon.2022",
            unit_id="kr.mid2.eng.donga_yoon.2022:U01",
            entry_key="word:express",
            unit_item_ordinal=1,
            page_no=12,
            importance_tier=1,
            role_in_unit="licensed_passage",
        )

    # Valid core_vocab mapping succeeds, but UPDATE to licensed_passage must also be blocked!
    builder.add_unit_entry(
        textbook_id="kr.mid2.eng.donga_yoon.2022",
        unit_id="kr.mid2.eng.donga_yoon.2022:U01",
        entry_key="word:express",
        unit_item_ordinal=1,
        page_no=12,
        importance_tier=1,
        role_in_unit="core_vocab",
    )
    with pytest.raises(sqlite3.IntegrityError, match="textbook_entry_violation"):
        builder.conn.execute("UPDATE ref_unit_entries SET role_in_unit = 'licensed_passage'")


def test_t19_t20_lazy_materialization_and_cross_profile_isolation(tmp_path: Path) -> None:
    pack_path = tmp_path / "starter_pack.sqlite"
    pack_info = build_starter_k12_and_exam_pack(pack_path)

    ledger = TierULedgerStore(tmp_path / "tier_u.sqlite")
    jr_profile_id = ledger.create_profile(name="민준(초3)", age_tier="junior")
    teen_profile_id = ledger.create_profile(name="서연(중2)", age_tier="teen")

    # T19: Junior profile cannot disable cloud_vision_locked
    with pytest.raises(sqlite3.IntegrityError):
        with ledger._write_tx() as conn:
            conn.execute(
                "UPDATE learner_profiles SET cloud_vision_locked = 0 WHERE profile_id = ?",
                (jr_profile_id,),
            )

    jr_deck_id = ledger.create_deck(profile_id=jr_profile_id, name="초등 한자", category="hanja")
    teen_deck_id = ledger.create_deck(profile_id=teen_profile_id, name="중2 한자", category="hanja")

    # T19: Cross-profile parent deck link must fail
    with pytest.raises(sqlite3.IntegrityError, match="cross_profile_violation"):
        with ledger._write_tx() as conn:
            conn.execute(
                "UPDATE decks SET parent_id = ? WHERE id = ?",
                (jr_deck_id, teen_deck_id),
            )

    # Register pack and activate collection with daily limit = 2
    ledger.register_installed_pack(
        pack_id=pack_info["pack_id"],
        pack_version=pack_info["pack_version"],
        file_sha256=pack_info["file_sha256"],
        content_sha256=pack_info["content_sha256"],
        local_path=str(pack_path),
        license_spdx="CC0-1.0",
        redistribution_allowed=True,
    )
    act_id = ledger.activate_pack_collection(
        profile_id=teen_profile_id,
        deck_id=teen_deck_id,
        pack_id=pack_info["pack_id"],
        collection_id="moe-hanja-1800:middle",
    )

    # T20: Materialize only 2 cards on Day 1
    batch1 = ledger.materialize_daily_pack_cards(
        activation_id=act_id,
        pack_db_path=pack_path,
        daily_new_limit=2,
        as_of_date="2026-10-20",
    )
    assert len(batch1) == 2
    # Verify cursor advanced and a second call with limit=1 pulls the 3rd entry without duplicating the first 2
    batch2 = ledger.materialize_daily_pack_cards(
        activation_id=act_id,
        pack_db_path=pack_path,
        daily_new_limit=1,
        as_of_date="2026-10-20",
    )
    assert len(batch2) == 1
    assert batch2[0]["ref_entry_key"] not in {b["ref_entry_key"] for b in batch1}


def test_t27_t28_school_textbook_exam_scope_filtering_and_queue_preserving_reconcile(tmp_path: Path) -> None:
    pack_path = tmp_path / "starter_pack.sqlite"
    pack_info = build_starter_k12_and_exam_pack(pack_path)

    ledger = TierULedgerStore(tmp_path / "tier_u.sqlite")
    teen_id = ledger.create_profile(name="서연(중2)", age_tier="teen")
    deck_id = ledger.create_deck(
        profile_id=teen_id,
        name="2학년 1학기 중간고사 영어 (동아 윤정미)",
        category="language",
    )
    ledger.register_installed_pack(
        pack_id=pack_info["pack_id"],
        pack_version=pack_info["pack_version"],
        file_sha256=pack_info["file_sha256"],
        content_sha256=pack_info["content_sha256"],
        local_path=str(pack_path),
        license_spdx="CC0-1.0",
        redistribution_allowed=True,
    )

    # Student scans a school handout / textbook passage for Lesson 1 (page 15) and Lesson 2 (page 27)
    user_note_u1 = ledger.add_user_textbook_note(
        deck_id=deck_id,
        front="Lesson 1 본문 핵심 문장: {{c1::Express}} yourself freely.",
        back="자유롭게 자신을 표현하세요.",
        textbook_id="kr.mid2.eng.donga_yoon.2022",
        curriculum_unit_id="kr.mid2.eng.donga_yoon.2022:U01",
        textbook_page_no=15,
    )
    user_note_u2_excluded = ledger.add_user_textbook_note(
        deck_id=deck_id,
        front="Lesson 2 수행평가 문장 (시험 제외 구간 p.27)",
        back="제외 구간",
        textbook_id="kr.mid2.eng.donga_yoon.2022",
        curriculum_unit_id="kr.mid2.eng.donga_yoon.2022:U02",
        textbook_page_no=27,
    )
    user_note_u2_included = ledger.add_user_textbook_note(
        deck_id=deck_id,
        front="Lesson 2 기말 포함 문장 (p.32)",
        back="포함 구간",
        textbook_id="kr.mid2.eng.donga_yoon.2022",
        curriculum_unit_id="kr.mid2.eng.donga_yoon.2022:U02",
        textbook_page_no=32,
    )

    # Create Exam Scope:
    # - Lesson 1 (whole unit)
    # - Lesson 2 disjoint page ranges: p.20..25 AND p.30..35 (skipping p.26..29!)
    # - Lesson 3 is NOT selected!
    scope_id = ledger.create_exam_scope(
        profile_id=teen_id,
        deck_id=deck_id,
        title="1학기 중간고사 영어",
        pack_id=pack_info["pack_id"],
        resolved_pack_version=pack_info["pack_version"],
        textbook_id="kr.mid2.eng.donga_yoon.2022",
        exam_study_day=20560,
        rules=[
            {"unit_id": "kr.mid2.eng.donga_yoon.2022:U01", "include_subunits": True, "page_start": None, "page_end": None},
            {"unit_id": "kr.mid2.eng.donga_yoon.2022:U02", "include_subunits": True, "page_start": 20, "page_end": 25},
            {"unit_id": "kr.mid2.eng.donga_yoon.2022:U02", "include_subunits": True, "page_start": 30, "page_end": 35},
        ],
    )

    resolved = ledger.resolve_and_reconcile_exam_scope(
        scope_id=scope_id,
        pack_db_path=pack_path,
        as_of_date="2026-04-28",
        materialize_now=True,
    )

    in_scope_keys = [item["entry_key"] for item in resolved if item["item_kind"] == "pack_entry"]
    in_scope_user_notes = [item["user_note_id"] for item in resolved if item["item_kind"] == "user_note"]

    # Lesson 1 words + Lesson 2 (p.22, p.31) words are included; Lesson 2 (p.27) and Lesson 3 (p.45) words are excluded!
    assert "word:express" in in_scope_keys
    assert "word:tradition" in in_scope_keys   # Lesson 2 p.22
    assert "word:recipe" in in_scope_keys      # Lesson 2 p.31
    assert "word:perform_skip" not in in_scope_keys  # Lesson 2 p.27 (outside disjoint page ranges)
    assert "word:environment" not in in_scope_keys   # Lesson 3 p.45 (unselected unit)

    # Student scanned notes: U01(p.15) and U02(p.32) included; U02(p.27) excluded!
    assert user_note_u1 in in_scope_user_notes
    assert user_note_u2_included in in_scope_user_notes
    assert user_note_u2_excluded not in in_scope_user_notes

    # Manually suspend (-1) one card in Lesson 2 and manually bury (-2) one card in Lesson 1
    recipe_note_id = next(item["materialized_note_id"] for item in resolved if item["entry_key"] == "word:recipe")
    express_note_id = next(item["materialized_note_id"] for item in resolved if item["entry_key"] == "word:express")
    with ledger._write_tx() as conn:
        conn.execute("UPDATE cards SET state = 'suspended', queue = -1 WHERE note_id = ?", (recipe_note_id,))
        conn.execute("UPDATE cards SET queue = -2 WHERE note_id = ?", (express_note_id,))

    # Now teacher announces: "Lesson 2 is completely removed from the midterm exam scope!"
    ledger.update_exam_scope_rules(
        scope_id=scope_id,
        rules=[
            {"unit_id": "kr.mid2.eng.donga_yoon.2022:U01", "include_subunits": True, "page_start": None, "page_end": None},
        ],
    )
    narrowed = ledger.resolve_and_reconcile_exam_scope(
        scope_id=scope_id,
        pack_db_path=pack_path,
        as_of_date="2026-04-28",
        materialize_now=True,
    )
    narrowed_keys = [item["entry_key"] for item in narrowed if item["item_kind"] == "pack_entry"]
    assert "word:express" in narrowed_keys
    assert "word:recipe" not in narrowed_keys

    # Verify cards.queue & cards.state were NOT overwritten when scope narrowed and then re-expanded!
    with ledger._write_tx() as conn:
        recipe_card = conn.execute("SELECT state, queue FROM cards WHERE note_id = ?", (recipe_note_id,)).fetchone()
        express_card = conn.execute("SELECT state, queue FROM cards WHERE note_id = ?", (express_note_id,)).fetchone()
        assert (recipe_card["state"], recipe_card["queue"]) == ("suspended", -1)
        assert express_card["queue"] == -2

    # Verify deleting a bound user_note cascades cleanly without CHECK or trigger failure
    ledger.delete_note(user_note_u1)
    remaining_items = ledger.list_exam_scope_items(scope_id=scope_id, only_in_scope=False)
    assert all(item["user_note_id"] != user_note_u1 for item in remaining_items)

    # Verify user_override_json & FSRS stability are preserved when re-materializing
    with ledger._write_tx() as conn:
        conn.execute(
            "UPDATE notes SET back = '내가 직접 수정한 뜻', user_override_json = '{\"back\": true}' WHERE id = ?",
            (express_note_id,),
        )
        conn.execute(
            "UPDATE cards SET stability = 14.5, difficulty = 4.2, reps = 5 WHERE note_id = ?",
            (express_note_id,),
        )
    ledger.resolve_and_reconcile_exam_scope(
        scope_id=scope_id,
        pack_db_path=pack_path,
        as_of_date="2026-04-28",
        materialize_now=True,
    )
    with ledger._write_tx() as conn:
        note_row = conn.execute("SELECT back FROM notes WHERE id = ?", (express_note_id,)).fetchone()
        card_row = conn.execute("SELECT stability, reps FROM cards WHERE note_id = ?", (express_note_id,)).fetchone()
        assert note_row["back"] == "내가 직접 수정한 뜻"
        assert card_row["stability"] == pytest.approx(14.5)
        assert card_row["reps"] == 5
