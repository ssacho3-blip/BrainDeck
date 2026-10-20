"""Pure-Domain All-Ages Adaptive Quiz Engine (T16, T17, T18, T22, T23).

100% Pure Domain Layer — Zero external I/O (no sqlite3, http, urllib, socket, subprocess, pathlib, or os).
Provides:
1. Age-Adaptive `ProfilePolicy` (`junior` / `teen` / `adult`).
2. Recognition vs. Recall `grade_interaction` with rating caps and progressive `quiz_stage` scaffolding (`T16`).
3. Facet-aware `select_distractors` with Forbidden-Wins, Answer-Set Non-Overlap, and Cold-Start fallback (`T17, T23`).
4. Pre-NFC CJK Compatibility Ideograph codepoint preservation (`T22`) and Hangul Jamo dictation grading (`T18`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple
import unicodedata

from .fsrs_math import Rating


class AgeTier(str, Enum):
    """3-Tier age profile classification."""

    JUNIOR = "junior"
    TEEN = "teen"
    ADULT = "adult"


@dataclass(frozen=True)
class ProfilePolicy:
    """Deterministic age-tier learning and guard policy (Blueprint §2.1)."""

    age_tier: AgeTier
    default_daily_new: int
    default_daily_review: int
    max_front_chars: int
    max_back_chars: int
    stability_promote_threshold: float
    normal_latency_ms: int
    cloud_vision_locked: bool


_POLICIES: Dict[AgeTier, ProfilePolicy] = {
    AgeTier.JUNIOR: ProfilePolicy(
        age_tier=AgeTier.JUNIOR,
        default_daily_new=10,
        default_daily_review=50,
        max_front_chars=40,
        max_back_chars=60,
        stability_promote_threshold=3.0,
        normal_latency_ms=8000,
        cloud_vision_locked=True,
    ),
    AgeTier.TEEN: ProfilePolicy(
        age_tier=AgeTier.TEEN,
        default_daily_new=20,
        default_daily_review=150,
        max_front_chars=100,
        max_back_chars=150,
        stability_promote_threshold=5.0,
        normal_latency_ms=6000,
        cloud_vision_locked=False,
    ),
    AgeTier.ADULT: ProfilePolicy(
        age_tier=AgeTier.ADULT,
        default_daily_new=25,
        default_daily_review=150,
        max_front_chars=220,
        max_back_chars=400,
        stability_promote_threshold=5.0,
        normal_latency_ms=5000,
        cloud_vision_locked=False,
    ),
}


def get_profile_policy(age_tier: AgeTier | str) -> ProfilePolicy:
    """Resolve `ProfilePolicy` for the given `age_tier`."""
    tier = AgeTier(str(age_tier).lower()) if not isinstance(age_tier, AgeTier) else age_tier
    return _POLICIES[tier]


@dataclass(frozen=True)
class InteractionGradeResult:
    """Result of grading a quiz interaction and advancing `quiz_stage` scaffolding."""

    rating: Rating
    evidence_class: str  # 'recognition' | 'cued_recall' | 'recall'
    next_quiz_stage: int
    next_consecutive_successes: int


def grade_interaction(
    age_tier: AgeTier | str,
    interaction_mode: str,
    is_correct: bool,
    attempt_count: int = 1,
    hint_used: bool = False,
    response_ms: int = 2000,
    option_count: Optional[int] = None,
    block_corrections: int = 0,
    recall_score_pct: float = 100.0,
    current_quiz_stage: int = 0,
    current_consecutive_successes: int = 0,
    next_stability: float = 0.0,
) -> Optional[InteractionGradeResult]:
    """Grade a single quiz interaction according to Blueprint §2.2 & T16.

    Returns `None` when `attempt_count > 1` so retry attempts never pollute FSRS stability.
    """
    if attempt_count < 1:
        raise ValueError(f"attempt_count must be >= 1, got {attempt_count}")
    if attempt_count > 1:
        return None

    policy = get_profile_policy(age_tier)
    mode = interaction_mode.strip().lower()
    stage = max(0, min(2, int(current_quiz_stage)))
    consec = max(0, int(current_consecutive_successes))

    if mode in ("button_2", "multiple_choice"):
        evidence_class = "recognition"
        if not is_correct:
            rating = Rating.AGAIN
        elif mode == "button_2" or (option_count is not None and option_count <= 3):
            rating = Rating.HARD
        else:
            # 4+ choice multiple_choice: capped at GOOD(3), never EASY(4)
            if not hint_used and response_ms <= policy.normal_latency_ms:
                rating = Rating.GOOD
            else:
                rating = Rating.HARD
    elif mode == "tap_block":
        evidence_class = "cued_recall"
        if not is_correct:
            rating = Rating.AGAIN
        elif block_corrections == 0 and not hint_used and response_ms <= policy.normal_latency_ms:
            rating = Rating.GOOD
        else:
            rating = Rating.HARD
    elif mode in ("dictation", "free_recall", "speaking", "cloze", "image_occlusion", "button_4"):
        evidence_class = "recall"
        if not is_correct or recall_score_pct < 45.0:
            rating = Rating.AGAIN
        elif recall_score_pct < 74.0 or hint_used:
            rating = Rating.HARD
        elif (
            recall_score_pct >= 92.0
            and not hint_used
            and response_ms <= policy.normal_latency_ms
            and policy.age_tier in (AgeTier.TEEN, AgeTier.ADULT)
        ):
            rating = Rating.EASY
        else:
            rating = Rating.GOOD
    else:
        raise ValueError(f"Unsupported interaction_mode: {interaction_mode}")

    # Progressive Scaffolding (T16): promote 0 -> 1 -> 2 or step down on AGAIN
    if rating == Rating.AGAIN:
        next_stage = max(0, stage - 1)
        next_consec = 0
    else:
        next_consec = consec + 1
        if stage < 2 and next_consec >= 2 and next_stability >= policy.stability_promote_threshold:
            next_stage = stage + 1
            next_consec = 0
        else:
            next_stage = stage

    return InteractionGradeResult(
        rating=rating,
        evidence_class=evidence_class,
        next_quiz_stage=next_stage,
        next_consecutive_successes=next_consec,
    )


class QuestionFacet(str, Enum):
    """Question facet determining allowed vs. forbidden distractor relations (Blueprint §6.3)."""

    HANJA_EUM = "hanja_eum"
    HANJA_CHAR = "hanja_char"
    WORD_SPELLING = "word_spelling"
    WORD_MEANING = "word_meaning"
    HISTORY_YEAR = "history_year"
    HISTORY_REIGN_ACHIEVEMENT = "history_reign_achievement"
    GENERAL = "general"


_FORBIDDEN_RELATIONS: Dict[QuestionFacet, FrozenSet[str]] = {
    QuestionFacet.HANJA_EUM: frozenset({"homophone", "synonym", "variant_of"}),
    QuestionFacet.HANJA_CHAR: frozenset({"synonym", "variant_of"}),
    QuestionFacet.WORD_SPELLING: frozenset({"synonym"}),
    QuestionFacet.WORD_MEANING: frozenset({"synonym"}),
    QuestionFacet.HISTORY_YEAR: frozenset({"same_year"}),
    QuestionFacet.HISTORY_REIGN_ACHIEVEMENT: frozenset({"same_reign"}),
    QuestionFacet.GENERAL: frozenset({"synonym", "variant_of"}),
}


@dataclass(frozen=True)
class CandidateDistractor:
    """Candidate wrong option evaluated by `select_distractors`."""

    key: str
    option_text: str
    answer_set: FrozenSet[str]
    relations: FrozenSet[str] = frozenset()
    source_priority: int = 3  # 1: wrong_answer_note, 2: ref_relations, 3: same_deck, 4: same_category, 5: seed


@dataclass(frozen=True)
class DistractorSelection:
    """Selected distractors or deterministic Cold-Start fallback mode."""

    distractors: Tuple[CandidateDistractor, ...]
    fallback_mode: Optional[str]  # None when len(distractors) == required_count, else 'tap_block' | 'button_2'


def _norm_token(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", (text or "").strip())).lower()


def select_distractors(
    question_facet: QuestionFacet | str,
    target_option_text: str,
    target_answer_set: Iterable[str],
    candidates: Sequence[CandidateDistractor],
    required_count: int = 3,
    allow_tap_block_fallback: bool = True,
) -> DistractorSelection:
    """Select `required_count` non-overlapping, leak-free distractors (T17, T23).

    Enforces:
    1. Forbidden Wins: Any candidate with a relation in `_FORBIDDEN_RELATIONS[question_facet]` is rejected.
    2. Answer-Set Non-Overlap: `target_norm_answers ∩ candidate_norm_answers == ∅`.
    3. Normalized option text uniqueness (no duplicate option text or substring leak of target).
    4. Cold-Start Fallback: If `< required_count` valid distractors remain, returns `fallback_mode`.
    """
    facet = QuestionFacet(str(question_facet)) if not isinstance(question_facet, QuestionFacet) else question_facet
    forbidden_rels = _FORBIDDEN_RELATIONS.get(facet, frozenset({"synonym", "variant_of"}))

    target_norm_opt = _norm_token(target_option_text)
    target_norm_set: Set[str] = {_norm_token(a) for a in target_answer_set if _norm_token(a)}
    if target_norm_opt:
        target_norm_set.add(target_norm_opt)

    seen_option_texts: Set[str] = {target_norm_opt} if target_norm_opt else set()
    seen_answer_values: Set[str] = set(target_norm_set)

    ordered = sorted(candidates, key=lambda c: (c.source_priority, c.key))
    chosen: List[CandidateDistractor] = []

    for cand in ordered:
        if len(chosen) >= required_count:
            break
        opt_norm = _norm_token(cand.option_text)
        if not opt_norm or opt_norm in seen_option_texts:
            continue

        # 1. Forbidden Wins check
        if not cand.relations.isdisjoint(forbidden_rels):
            continue

        # 2. Answer-Set Non-Overlap check
        cand_norm_answers = {_norm_token(a) for a in cand.answer_set if _norm_token(a)}
        cand_norm_answers.add(opt_norm)
        if not cand_norm_answers.isdisjoint(seen_answer_values):
            continue

        seen_option_texts.add(opt_norm)
        seen_answer_values.update(cand_norm_answers)
        chosen.append(cand)

    if len(chosen) < required_count:
        return DistractorSelection(
            distractors=(),
            fallback_mode="tap_block" if allow_tap_block_fallback else "button_2",
        )

    return DistractorSelection(
        distractors=tuple(chosen),
        fallback_mode=None,
    )


@dataclass(frozen=True)
class CompatNormalizedText:
    """Pre-NFC CJK Compatibility Ideograph capture result (T22)."""

    nfc_text: str
    compat_codepoints: Tuple[str, ...]


def is_cjk_compatibility_ideograph(codepoint: int) -> bool:
    """Return True if `codepoint` is in CJK Compatibility Ideographs (U+F900..U+FAFF or U+2F800..U+2FA1F)."""
    return (0xF900 <= codepoint <= 0xFAFF) or (0x2F800 <= codepoint <= 0x2FA1F)


def preserve_cjk_compat_before_nfc(raw_text: str) -> CompatNormalizedText:
    """Capture CJK Compatibility Ideograph codepoints BEFORE applying Unicode NFC (T22)."""
    compat: List[str] = []
    for ch in raw_text or "":
        cp = ord(ch)
        if is_cjk_compatibility_ideograph(cp):
            tag = f"U+{cp:04X}"
            if tag not in compat:
                compat.append(tag)
    return CompatNormalizedText(
        nfc_text=unicodedata.normalize("NFC", raw_text or ""),
        compat_codepoints=tuple(compat),
    )


# Hangul Syllable (U+AC00..U+D7A3) Jamo Decomposition for Dictation Grading (T18)
_CHOSEONG = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)
_JUNGSEONG = (
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
)
_JONGSEONG = (
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)


def decompose_hangul_to_jamo(text: str, keep_spaces: bool = True) -> str:
    """Normalize text to NFC first, then decompose Hangul syllables into Choseong/Jungseong/Jongseong Jamo."""
    nfc = unicodedata.normalize("NFC", (text or "").strip())
    if not keep_spaces:
        nfc = re.sub(r"\s+", "", nfc)
    else:
        nfc = re.sub(r"\s+", " ", nfc)

    out: List[str] = []
    for ch in nfc:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            offset = code - 0xAC00
            cho = offset // 588
            jung = (offset % 588) // 28
            jong = offset % 28
            out.append(_CHOSEONG[cho])
            out.append(_JUNGSEONG[jung])
            if jong > 0:
                out.append(_JONGSEONG[jong])
        else:
            out.append(ch.lower())
    return "".join(out)


def _levenshtein(seq_a: str, seq_b: str) -> int:
    if seq_a == seq_b:
        return 0
    if not seq_a:
        return len(seq_b)
    if not seq_b:
        return len(seq_a)
    prev = list(range(len(seq_b) + 1))
    for i, ca in enumerate(seq_a, start=1):
        curr = [i] + [0] * len(seq_b)
        for j, cb in enumerate(seq_b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


@dataclass(frozen=True)
class DictationGradeResult:
    """Result of grading a dictation or spelling input using Jamo edit distance."""

    score_pct: float
    jamo_distance: int
    is_exact: bool


def grade_dictation_jamo(
    user_input: str,
    target_text: str,
    spacing_strict: bool = False,
) -> DictationGradeResult:
    """Grade dictation input using NFC + Hangul Jamo Levenshtein distance (T18)."""
    user_jamo = decompose_hangul_to_jamo(user_input, keep_spaces=spacing_strict)
    target_jamo = decompose_hangul_to_jamo(target_text, keep_spaces=spacing_strict)
    if not target_jamo:
        raise ValueError("target_text must not be empty")
    if not user_jamo:
        return DictationGradeResult(score_pct=0.0, jamo_distance=len(target_jamo), is_exact=False)

    dist = _levenshtein(user_jamo, target_jamo)
    denom = max(len(user_jamo), len(target_jamo), 1)
    score = round(max(0.0, (1.0 - (dist / denom)) * 100.0), 1)
    return DictationGradeResult(
        score_pct=score,
        jamo_distance=dist,
        is_exact=(dist == 0),
    )


def build_tap_blocks(target_text: str, distractor_chars: Sequence[str] = ()) -> Tuple[str, ...]:
    """Build deterministic shuffled character/word blocks for Mode B (`tap_block`)."""
    nfc = unicodedata.normalize("NFC", (target_text or "").strip())
    words = nfc.split()
    if len(words) >= 3:
        base_units = list(words)
    else:
        base_units = [ch for ch in nfc if not ch.isspace()]

    for d in distractor_chars:
        clean_d = unicodedata.normalize("NFC", d.strip())
        if clean_d and clean_d not in base_units:
            base_units.append(clean_d)

    # Deterministic rotation based on character code sum so order is reproducible and not already solved
    if len(base_units) > 1:
        shift = (sum(ord(c) for u in base_units for c in u) % (len(base_units) - 1)) + 1
        rotated = base_units[shift:] + base_units[:shift]
        return tuple(rotated)
    return tuple(base_units)
