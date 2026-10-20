"""DDT & Unit Tests for Pure-Domain AdaptiveQuizEngine & FSRS v2 Contracts (T4, T16, T17, T18, T22, T23).

Verifies:
- T4: FSRS-5 `lapses` increments ONLY when `state == 'review'` and `rating == AGAIN`.
- T16: `grade_interaction` first-attempt enforcement, recognition rating caps, and `quiz_stage` scaffolding.
- T17 & T23: `select_distractors` Forbidden-Wins matrix, Answer-Set Non-Overlap (including dueum), and Cold-Start fallback.
- T18 & T22: CJK Compatibility Ideograph preservation before Unicode NFC + Hangul Jamo edit-distance dictation grading.
"""

from __future__ import annotations

import unicodedata
import pytest

from anki_studio.domain.fsrs_math import CardMemoryState, Rating, step_fsrs
from anki_studio.domain.adaptive_quiz import (
    AgeTier,
    CandidateDistractor,
    ProfilePolicy,
    QuestionFacet,
    build_tap_blocks,
    get_profile_policy,
    grade_dictation_jamo,
    grade_interaction,
    preserve_cjk_compat_before_nfc,
    select_distractors,
)


@pytest.mark.parametrize(
    "initial_state,initial_reps,initial_stability,rating,expected_lapses",
    [
        ("new", 0, 0.0, Rating.AGAIN, 0),
        ("learning", 1, 0.4, Rating.AGAIN, 0),
        ("relearning", 3, 1.2, Rating.AGAIN, 1),  # stays at initial_lapses=1, does not increment on relearning AGAIN
        ("review", 3, 5.5, Rating.AGAIN, 2),      # increments from 1 -> 2 ONLY from 'review' state
        ("review", 3, 5.5, Rating.GOOD, 1),
    ],
)
def test_t4_lapses_increments_only_from_review_state(
    initial_state: str,
    initial_reps: int,
    initial_stability: float,
    rating: Rating,
    expected_lapses: int,
) -> None:
    mem = CardMemoryState(
        difficulty=5.0,
        stability=initial_stability,
        reps=initial_reps,
        lapses=0 if initial_state in ("new", "learning") else 1,
        state=initial_state,
    )
    outcome = step_fsrs(mem, rating, elapsed_days=3.0)
    assert outcome.memory.lapses == expected_lapses


@pytest.mark.parametrize(
    "age_tier,expected_daily_new,expected_front_limit,expected_cloud_locked",
    [
        (AgeTier.JUNIOR, 10, 40, True),
        (AgeTier.TEEN, 20, 100, False),
        (AgeTier.ADULT, 25, 220, False),
    ],
)
def test_profile_policy_by_age_tier(
    age_tier: AgeTier,
    expected_daily_new: int,
    expected_front_limit: int,
    expected_cloud_locked: bool,
) -> None:
    policy: ProfilePolicy = get_profile_policy(age_tier)
    assert policy.default_daily_new == expected_daily_new
    assert policy.max_front_chars == expected_front_limit
    assert policy.cloud_vision_locked is expected_cloud_locked


@pytest.mark.parametrize(
    "age_tier,mode,option_count,is_correct,attempt_count,hint_used,response_ms,block_corrections,recall_score,expected_rating,expected_evidence",
    [
        # Second attempt is never graded for FSRS (returns None)
        (AgeTier.JUNIOR, "multiple_choice", 4, True, 2, False, 1500, 0, 100.0, None, None),
        # 2-button mode & 3-option MC capped at HARD (2)
        (AgeTier.JUNIOR, "button_2", None, True, 1, False, 1000, 0, 100.0, Rating.HARD, "recognition"),
        (AgeTier.JUNIOR, "multiple_choice", 3, True, 1, False, 1000, 0, 100.0, Rating.HARD, "recognition"),
        # 4-choice MC fast & no hint -> GOOD (3), never EASY (4)
        (AgeTier.JUNIOR, "multiple_choice", 4, True, 1, False, 2000, 0, 100.0, Rating.GOOD, "recognition"),
        # 4-choice MC with hint -> HARD (2)
        (AgeTier.JUNIOR, "multiple_choice", 4, True, 1, True, 2000, 0, 100.0, Rating.HARD, "recognition"),
        # 4-choice MC wrong -> AGAIN (1)
        (AgeTier.TEEN, "multiple_choice", 4, False, 1, False, 2000, 0, 0.0, Rating.AGAIN, "recognition"),
        # Tap-block clean & fast -> GOOD (3), never EASY (4)
        (AgeTier.JUNIOR, "tap_block", None, True, 1, False, 3000, 0, 100.0, Rating.GOOD, "cued_recall"),
        (AgeTier.JUNIOR, "tap_block", None, True, 1, False, 3000, 2, 100.0, Rating.HARD, "cued_recall"),
        # Free recall / dictation: JUNIOR cannot get EASY (4), capped at GOOD (3)
        (AgeTier.JUNIOR, "dictation", None, True, 1, False, 2500, 0, 98.0, Rating.GOOD, "recall"),
        # TEEN & ADULT get EASY (4) on fast high-score recall without hint
        (AgeTier.TEEN, "free_recall", None, True, 1, False, 3000, 0, 96.0, Rating.EASY, "recall"),
        (AgeTier.ADULT, "cloze", None, True, 1, False, 3500, 0, 82.0, Rating.GOOD, "recall"),
        (AgeTier.ADULT, "free_recall", None, True, 1, False, 3500, 0, 52.0, Rating.HARD, "recall"),
        (AgeTier.ADULT, "free_recall", None, False, 1, False, 3500, 0, 30.0, Rating.AGAIN, "recall"),
    ],
)
def test_t16_grade_interaction_caps_and_evidence_classes(
    age_tier: AgeTier,
    mode: str,
    option_count: int | None,
    is_correct: bool,
    attempt_count: int,
    hint_used: bool,
    response_ms: int,
    block_corrections: int,
    recall_score: float,
    expected_rating: Rating | None,
    expected_evidence: str | None,
) -> None:
    res = grade_interaction(
        age_tier=age_tier,
        interaction_mode=mode,
        is_correct=is_correct,
        attempt_count=attempt_count,
        hint_used=hint_used,
        response_ms=response_ms,
        option_count=option_count,
        block_corrections=block_corrections,
        recall_score_pct=recall_score,
        current_quiz_stage=0,
        current_consecutive_successes=0,
        next_stability=1.5,
    )
    if expected_rating is None:
        assert res is None
    else:
        assert res is not None
        assert res.rating == expected_rating
        assert res.evidence_class == expected_evidence


def test_t16_progressive_quiz_stage_promotion_and_step_down() -> None:
    # Junior at stage 0: 1st success with stability 3.5 -> consecutive_successes=1, stage stays 0
    r1 = grade_interaction(
        age_tier=AgeTier.JUNIOR,
        interaction_mode="multiple_choice",
        is_correct=True,
        attempt_count=1,
        hint_used=False,
        response_ms=2000,
        option_count=4,
        current_quiz_stage=0,
        current_consecutive_successes=0,
        next_stability=3.5,
    )
    assert r1 is not None
    assert r1.next_quiz_stage == 0
    assert r1.next_consecutive_successes == 1

    # 2nd consecutive success with stability >= 3.0 -> promotes to stage 1 (tap_block), resets consecutive_successes=0
    r2 = grade_interaction(
        age_tier=AgeTier.JUNIOR,
        interaction_mode="multiple_choice",
        is_correct=True,
        attempt_count=1,
        hint_used=False,
        response_ms=2000,
        option_count=4,
        current_quiz_stage=r1.next_quiz_stage,
        current_consecutive_successes=r1.next_consecutive_successes,
        next_stability=4.2,
    )
    assert r2 is not None
    assert r2.next_quiz_stage == 1
    assert r2.next_consecutive_successes == 0

    # Failure (AGAIN) at stage 1 -> steps down to stage 0 and resets consecutive_successes=0
    r3 = grade_interaction(
        age_tier=AgeTier.JUNIOR,
        interaction_mode="tap_block",
        is_correct=False,
        attempt_count=1,
        hint_used=False,
        response_ms=4000,
        current_quiz_stage=1,
        current_consecutive_successes=1,
        next_stability=1.0,
    )
    assert r3 is not None
    assert r3.rating == Rating.AGAIN
    assert r3.next_quiz_stage == 0
    assert r3.next_consecutive_successes == 0


def test_t17_t23_distractor_selector_forbidden_wins_and_answer_set_non_overlap() -> None:
    # Target Hanja: 樂 (eum: 락, 악, 요; dueum: 낙) -> asking for EUM (reading)
    target_answers = {"락", "악", "요", "낙"}
    candidates = [
        # Candidate 1: has allowed 'similar_shape' AND forbidden 'homophone' -> Forbidden Wins, MUST be rejected!
        CandidateDistractor(
            key="hanja:1",
            option_text="악",
            answer_set=frozenset({"악"}),
            relations=frozenset({"similar_shape", "homophone"}),
            source_priority=2,
        ),
        # Candidate 2: answer_set overlaps via dueum '낙' (落 떨어질 락/낙) -> Answer-Set Non-Overlap, MUST be rejected!
        CandidateDistractor(
            key="hanja:2",
            option_text="낙",
            answer_set=frozenset({"락", "낙"}),
            relations=frozenset({"same_radical"}),
            source_priority=2,
        ),
        # Candidate 3: valid distractor '미' (未 아닐 미, similar_shape)
        CandidateDistractor(
            key="hanja:3",
            option_text="미",
            answer_set=frozenset({"미"}),
            relations=frozenset({"similar_shape"}),
            source_priority=2,
        ),
        # Candidate 4: valid distractor '말' (末 끝 말, similar_shape)
        CandidateDistractor(
            key="hanja:4",
            option_text="말",
            answer_set=frozenset({"말"}),
            relations=frozenset({"similar_shape"}),
            source_priority=2,
        ),
        # Candidate 5: duplicate normalized option text '말' -> deduplicated!
        CandidateDistractor(
            key="hanja:5",
            option_text=" 말 ",
            answer_set=frozenset({"말"}),
            relations=frozenset({"same_radical"}),
            source_priority=3,
        ),
        # Candidate 6: valid distractor '본' (本 근본 본)
        CandidateDistractor(
            key="hanja:6",
            option_text="본",
            answer_set=frozenset({"본"}),
            relations=frozenset({"same_radical"}),
            source_priority=2,
        ),
    ]

    selection = select_distractors(
        question_facet=QuestionFacet.HANJA_EUM,
        target_option_text="락",
        target_answer_set=target_answers,
        candidates=candidates,
    )
    assert selection.fallback_mode is None
    assert len(selection.distractors) == 3
    assert [d.option_text for d in selection.distractors] == ["미", "말", "본"]


def test_t17_cold_start_fallback_when_fewer_than_3_valid_distractors() -> None:
    selection = select_distractors(
        question_facet=QuestionFacet.WORD_SPELLING,
        target_option_text="apple",
        target_answer_set={"apple"},
        candidates=[
            CandidateDistractor(
                key="w1",
                option_text="apply",
                answer_set=frozenset({"apply"}),
                relations=frozenset({"confusable_spelling"}),
                source_priority=2,
            )
        ],
    )
    assert selection.distractors == ()
    assert selection.fallback_mode == "tap_block"


def test_t22_preserve_cjk_compat_before_nfc_and_jamo_dictation() -> None:
    # U+F914 is CJK Compatibility Ideograph '樂' (pronounced 락/낙), which NFC turns into U+6A02 '樂'
    raw_compat = "\uf914\uc6d0"  # 樂園 (낙원)
    res = preserve_cjk_compat_before_nfc(raw_compat)
    assert res.compat_codepoints == ("U+F914",)
    assert res.nfc_text == unicodedata.normalize("NFC", raw_compat)

    # NFD vs NFC Hangul dictation grading
    nfd_input = unicodedata.normalize("NFD", "훈민정음")
    nfc_target = unicodedata.normalize("NFC", "훈민정음")
    exact_grade = grade_dictation_jamo(nfd_input, nfc_target, spacing_strict=True)
    assert exact_grade.score_pct == 100.0
    assert exact_grade.jamo_distance == 0
    assert exact_grade.is_exact is True

    # 1 Jamo typo ("훈민정은" vs "훈민정음": 종성 ㄴ vs ㅁ -> 1 jamo edit out of 12 jamos)
    near_grade = grade_dictation_jamo("훈민정은", "훈민정음", spacing_strict=False)
    assert near_grade.jamo_distance == 1
    assert 90.0 <= near_grade.score_pct < 100.0

    # Tap block assembly deterministic generation
    blocks = build_tap_blocks("훈민정음", distractor_chars=("한", "글"))
    assert set("훈민정음").issubset(set(blocks))
    assert len(blocks) == 6
