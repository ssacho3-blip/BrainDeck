"""Pure-Domain AI Active Recall Evaluator, Socratic Tutor, Leech Doctor & Smart Card Factory.

100% Pure Domain Layer — Zero external I/O (no sqlite3, http, urllib, socket, subprocess, or filesystem).
Provides:
1. Objective Free-Recall Answer Grading (`evaluate_free_recall`) to eliminate Anki's blind self-grading bias.
2. Progressive Socratic Hint & Mnemonic Generation (`generate_socratic_hint`).
3. Leech Card Atomic Decomposition (`decompose_leech_card`) to cure repeated lapses.
4. Zero-Effort Smart Card Extraction (`extract_smart_cards_deterministic`, `parse_ai_generated_cards`).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Dict, List, Sequence, Tuple

from .fsrs_math import Rating, extract_cloze_ordinals


_STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "and", "or",
        "that", "this", "it", "its", "이", "그", "저", "것", "수", "등", "및", "또는",
        "이다", "입니다", "한다", "있는", "하는", "에서", "으로", "로", "을", "를", "은", "는", "이", "가", "의",
    }
)

_NEGATION_TOKENS = frozenset(
    {
        "not", "no", "never", "without", "none", "neither", "cannot", "can't", "don't", "doesn't",
        "아니다", "아닌", "없다", "없는", "불가", "금지", "억제", "방지", "차단", "감소", "하락",
    }
)

_NUMBER_UNIT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:nm|um|mm|hz|khz|mhz|ghz|db|dbfs|%|gb|tb|mb|w|v|m|s|ms|일|개|배|차|년|세기|조|항)?\b", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[A-Za-z0-9가-힣\-\+/\.]+")
_CLOZE_STRIP_PATTERN = re.compile(r"\{\{c\d+::([^}:]+)(?:::[^}]+)?\}\}")
_POS_TAG_SUFFIX_RE = re.compile(
    r"\s*\((?:동사|명사|형용사|부사|숙어|전치사|접속사|대명사|감탄사|교과서\s*핵심\s*구문|v\.|n\.|adj\.|adv\.)\)\s*$",
    re.IGNORECASE,
)
_EXPLANATION_SPLIT_RE = re.compile(r"(?:\n+\s*💡\s*해설\s*:|\s+—\s+\(예문:|\n+\s*\[해설\])")
_HANGUL_CHOSEONG = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)


@dataclass(frozen=True)
class RecallEvaluation:
    """Objective evaluation of a learner's typed/spoken answer against the target answer."""

    score_pct: float
    recommended_rating: Rating
    matched_terms: Tuple[str, ...]
    missing_terms: Tuple[str, ...]
    numeric_match: bool
    negation_conflict: bool
    feedback: str


@dataclass(frozen=True)
class SocraticHint:
    """Non-spoiler Socratic hint and mnemonic cue for a card."""

    level: int
    structural_cue: str
    socratic_question: str
    mnemonic_tip: str


@dataclass(frozen=True)
class GeneratedCardSpec:
    """Specification of an automatically generated flashcard."""

    note_type: str  # 'cloze' | 'basic' | 'speaking'
    front_text: str
    back_text: str
    tags: Tuple[str, ...]
    rationale: str


def _clean_expected_text(text: str) -> str:
    """Unwrap Cloze brackets `{{c1::answer::hint}}` or `【answer】` into plain target text."""
    unwrapped = _CLOZE_STRIP_PATTERN.sub(r"\1", text or "")
    unwrapped = unwrapped.replace("【", "").replace("】", "")
    return unwrapped.strip()


def extract_clean_target_answer(
    front_text: str,
    back_text: str,
    explicit_target: str | None = None,
) -> Tuple[str, str]:
    """Separate the concise core grading/hint target_answer from extra_explanation.

    Returns `(target_answer, extra_explanation)`.
    Ensures Cloze cards and commentary-enriched cards grade/hint ONLY the blank/core answer
    rather than the entire 80-character sentence + `💡 해설: ...`.
    """
    raw_front = str(front_text or "").strip()
    raw_back = str(back_text or "").strip()

    if explicit_target and explicit_target.strip():
        exp_parts = _EXPLANATION_SPLIT_RE.split(explicit_target.strip(), maxsplit=1)
        first_line_t = exp_parts[0].splitlines()[0].strip() if exp_parts[0] else ""
        clean_t = _POS_TAG_SUFFIX_RE.sub("", first_line_t).strip()
        parts = _EXPLANATION_SPLIT_RE.split(raw_back, maxsplit=1)
        extra = parts[1].strip() if len(parts) > 1 else (exp_parts[1].strip() if len(exp_parts) > 1 else "")
        return (clean_t or first_line_t or explicit_target.strip(), extra)

    # 1. Raw Cloze tags `{{c1::answer::hint}}` in front_text
    cloze_matches = [m.strip() for m in _CLOZE_STRIP_PATTERN.findall(raw_front) if m.strip()]
    if cloze_matches:
        unique_cloze: List[str] = []
        for m in cloze_matches:
            if m not in unique_cloze:
                unique_cloze.append(m)
        return (" · ".join(unique_cloze), raw_back)

    # 2. Rendered `【answer】` or `[answer]` in back_text when front_text has `[...]`
    bracket_matches = [m.strip() for m in re.findall(r"【([^】]+)】", raw_back) if m.strip()]
    if not bracket_matches and "[..." in raw_front:
        first_line = raw_back.splitlines()[0] if raw_back else ""
        sq_matches = [
            m.strip()
            for m in re.findall(r"\[([^\[\]\n]{1,40})\]", first_line)
            if m.strip() and not m.strip().startswith("Leech")
        ]
        if sq_matches:
            bracket_matches = sq_matches
    if bracket_matches:
        unique_b: List[str] = []
        for m in bracket_matches:
            if m not in unique_b:
                unique_b.append(m)
        parts = _EXPLANATION_SPLIT_RE.split(raw_back, maxsplit=1)
        extra = parts[1].strip() if len(parts) > 1 else raw_back
        return (" · ".join(unique_b), extra)

    # 3. Split commentary (`💡 해설:`, `— (예문:`) from back_text
    parts = _EXPLANATION_SPLIT_RE.split(raw_back, maxsplit=1)
    core = parts[0].strip()
    extra = parts[1].strip() if len(parts) > 1 else ""

    if core.startswith("정답:"):
        core = re.sub(r"^정답:\s*", "", core)
        core = re.sub(r"\s*\(p\.\d+\)\s*$", "", core).strip()

    core_clean = _POS_TAG_SUFFIX_RE.sub("", core).strip()
    return (core_clean or core, extra)


def _build_choseong_or_letter_mask(target: str, reveal_first_char: bool = False) -> Tuple[str, int, str]:
    """Build a practical Hangul Choseong mask (`ㅎ ㅁ ㅈ ㅇ`) or English letter mask (`i _ _ r _ _ _ _ e`).

    Returns `(mask_str, meaningful_char_count, primary_clean_target)`.
    """
    cleaned = _POS_TAG_SUFFIX_RE.sub("", (target or "").strip()).strip()
    # Strip trailing parenthetical gloss like "소개하다 (introduce)" so char count reflects the primary answer
    primary = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned).strip() or cleaned

    char_count = sum(1 for ch in primary if not ch.isspace())
    if not primary:
        return ("...", 0, "")

    out_tokens: List[str] = []
    first_revealed = False
    alpha_indices: List[int] = []
    for ch in primary:
        if ch.isspace():
            out_tokens.append(" ")
            continue
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            if reveal_first_char and not first_revealed:
                out_tokens.append(ch)
                first_revealed = True
            else:
                cho_idx = (code - 0xAC00) // 588
                out_tokens.append(_HANGUL_CHOSEONG[cho_idx])
        elif ch.isalpha():
            idx_pos = len(out_tokens)
            alpha_indices.append(idx_pos)
            if not first_revealed:
                out_tokens.append(ch)
                first_revealed = True
            else:
                out_tokens.append("_")
        elif ch.isdigit():
            if not first_revealed:
                out_tokens.append(ch)
                first_revealed = True
            else:
                out_tokens.append("□")
        else:
            out_tokens.append(ch)

    if reveal_first_char and len(alpha_indices) >= 4:
        last_idx = alpha_indices[-1]
        # Reveal last letter of English word on Step 2
        alpha_chars = [ch for ch in primary if ch.isalpha()]
        if alpha_chars:
            out_tokens[last_idx] = alpha_chars[-1]
        if len(alpha_indices) >= 6:
            mid_idx = alpha_indices[len(alpha_indices) // 2]
            out_tokens[mid_idx] = alpha_chars[len(alpha_chars) // 2]

    mask_str = " ".join(tok for tok in out_tokens if tok != " ").strip()
    return (mask_str, max(1, char_count), primary)


def _extract_meaningful_tokens(text: str) -> List[str]:
    cleaned = _clean_expected_text(text).lower()
    raw_tokens = _WORD_PATTERN.findall(cleaned)
    tokens: List[str] = []
    for tok in raw_tokens:
        t = tok.strip(".,;:!?()[]{}\"'")
        # Strip common Korean particles at the end of multi-character words
        for suffix in ("에서는", "으로서", "으로써", "입니다", "한다", "하며", "이고", "이나", "에서", "으로", "에게", "보다", "처럼", "까지", "부터", "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과"):
            if len(t) > len(suffix) + 1 and t.endswith(suffix):
                t = t[: -len(suffix)]
                break
        if len(t) >= 2 and t not in _STOPWORDS:
            tokens.append(t)
    return tokens


def _char_bigrams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", _clean_expected_text(text).lower())
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def evaluate_free_recall(
    user_answer: str,
    expected_answer: str,
    question_text: str = "",
) -> RecallEvaluation:
    """Grade a learner's free-recall response objectively and recommend an FSRS-5 Rating."""
    user_clean = (user_answer or "").strip()
    target_clean = _clean_expected_text(expected_answer)

    if not target_clean:
        raise ValueError("expected_answer must not be empty")

    if not user_clean:
        return RecallEvaluation(
            score_pct=0.0,
            recommended_rating=Rating.AGAIN,
            matched_terms=(),
            missing_terms=tuple(_extract_meaningful_tokens(target_clean)[:5]),
            numeric_match=False,
            negation_conflict=False,
            feedback="답변이 입력되지 않았습니다. 핵심 개념을 직접 인출(Active Recall)해 보세요.",
        )

    # Extract concise core answer (e.g. Cloze blank target or main answer before `💡 해설:`)
    extracted_core, _ = extract_clean_target_answer(question_text, expected_answer)
    cloze_focus_matches = re.findall(r"【([^】]+)】", expected_answer or "")
    if cloze_focus_matches:
        grading_reference = " ".join(cloze_focus_matches)
    elif extracted_core:
        grading_reference = _clean_expected_text(extracted_core)
    else:
        grading_reference = target_clean

    # Strip parenthetical POS tags or redundant English/Hanja glosses when checking exact match
    grading_primary = re.sub(r"\s*\([^)]*\)\s*$", "", grading_reference).strip() or grading_reference

    ref_tokens = _extract_meaningful_tokens(grading_primary) or _extract_meaningful_tokens(grading_reference)
    user_tokens = set(_extract_meaningful_tokens(user_clean))
    user_lower = user_clean.lower()

    matched: List[str] = []
    missing: List[str] = []
    for tok in dict.fromkeys(ref_tokens):
        if tok in user_tokens or tok in user_lower:
            matched.append(tok)
        else:
            missing.append(tok)

    token_recall = (len(matched) / len(set(ref_tokens))) if ref_tokens else 1.0

    ref_bigrams = _char_bigrams(grading_primary)
    user_bigrams = _char_bigrams(user_clean)
    if ref_bigrams and user_bigrams:
        overlap = len(ref_bigrams & user_bigrams)
        bigram_recall = overlap / len(ref_bigrams)
    else:
        bigram_recall = 0.0

    # Check critical numbers/units:
    # 1) Required numbers in primary target must be present in user_answer.
    # 2) If user_answer includes numbers and full reference has numbers (even in parentheses), user numbers must not conflict!
    primary_numbers = {re.sub(r"\s+", "", m.group(0).lower()) for m in _NUMBER_UNIT_PATTERN.finditer(grading_primary)}
    full_ref_numbers = {re.sub(r"\s+", "", m.group(0).lower()) for m in _NUMBER_UNIT_PATTERN.finditer(grading_reference)}
    user_numbers = {re.sub(r"\s+", "", m.group(0).lower()) for m in _NUMBER_UNIT_PATTERN.finditer(user_clean)}
    numeric_match = True
    if primary_numbers:
        numeric_match = primary_numbers.issubset(user_numbers) or all(
            any(rn in un or un in rn for un in user_numbers) for rn in primary_numbers
        )
    if user_numbers and full_ref_numbers:
        if not all(any(un in rn or rn in un for rn in full_ref_numbers) for un in user_numbers):
            numeric_match = False

    # Check negation conflict
    ref_has_neg = any(neg in grading_primary.lower() for neg in _NEGATION_TOKENS)
    user_has_neg = any(neg in user_lower for neg in _NEGATION_TOKENS)
    negation_conflict = bool(ref_tokens) and (ref_has_neg != user_has_neg) and len(ref_tokens) >= 2

    raw_score = (0.65 * token_recall + 0.35 * bigram_recall) * 100.0
    if matched and missing and token_recall >= 0.45:
        raw_score = max(46.0, raw_score)

    # Exact normalized match boost (either against full grading_reference, primary core answer, or target_clean)
    norm_user = re.sub(r"[\s\(\)\[\],·]+", "", user_clean.lower())
    norm_Candidates = {
        re.sub(r"[\s\(\)\[\],·]+", "", grading_reference.lower()),
        re.sub(r"[\s\(\)\[\],·]+", "", grading_primary.lower()),
        re.sub(r"[\s\(\)\[\],·]+", "", target_clean.lower()),
    }
    if norm_user in norm_Candidates and numeric_match and not negation_conflict:
        raw_score = 100.0
        missing = []

    if not numeric_match:
        raw_score = min(raw_score, 55.0)
    if negation_conflict:
        raw_score = max(0.0, raw_score - 35.0)

    score_pct = round(max(0.0, min(100.0, raw_score)), 1)

    if score_pct >= 92.0 and numeric_match and not negation_conflict:
        rating = Rating.EASY
        feedback = "✅ 완벽한 인출입니다! 핵심 키워드와 수치가 모두 정확히 일치합니다 (Easy 추천)."
    elif score_pct >= 74.0 and numeric_match and not negation_conflict:
        rating = Rating.GOOD
        feedback = "🟢 핵심 개념을 정확히 기억하고 있습니다 (Good 추천)."
    elif score_pct >= 45.0:
        rating = Rating.HARD
        miss_preview = ", ".join(missing[:3]) if missing else "세부 수치/표현"
        feedback = f"🟡 부분 인출 성공: 핵심 포인트({miss_preview})를 보강하면 완벽합니다 (Hard 추천)."
    else:
        rating = Rating.AGAIN
        miss_preview = ", ".join(missing[:4]) if missing else grading_primary[:30]
        feedback = f"🔴 재학습 필요: 핵심 개념({miss_preview})이 누락되었습니다. 정답을 소리 내어 읽고 10분 뒤 다시 인출해 보세요 (Again 추천)."

    return RecallEvaluation(
        score_pct=score_pct,
        recommended_rating=rating,
        matched_terms=tuple(matched),
        missing_terms=tuple(missing),
        numeric_match=numeric_match,
        negation_conflict=negation_conflict,
        feedback=feedback,
    )


def generate_socratic_hint(
    question_text: str,
    target_answer: str,
    lapses: int = 0,
    level: int = 1,
) -> SocraticHint:
    """Generate a practical, non-spoiler 2-step progressive hint (Hangul Choseong / English letter mask + context cue)."""
    core_answer, extra_explanation = extract_clean_target_answer(question_text, target_answer)
    if not core_answer:
        core_answer = _clean_expected_text(target_answer) or "핵심 개념"

    mask_step1, char_len, primary_target = _build_choseong_or_letter_mask(core_answer, reveal_first_char=False)
    mask_step2, _, _ = _build_choseong_or_letter_mask(core_answer, reveal_first_char=True)
    tokens = _extract_meaningful_tokens(primary_target)
    first_char = primary_target[0] if primary_target else core_answer[0]

    has_hangul = any(0xAC00 <= ord(ch) <= 0xD7A3 for ch in primary_target)
    has_alpha = any("a" <= ch.lower() <= "z" for ch in primary_target)
    numbers = [m.group(0) for m in _NUMBER_UNIT_PATTERN.finditer(primary_target)]

    if level <= 1:
        if has_hangul:
            structural_cue = f"초성 힌트: [{mask_step1}] · 글자 수: {char_len}자 (첫 글자: '{first_char}...')"
        elif has_alpha:
            structural_cue = f"철자 힌트: [{mask_step1}] · 알파벳 {char_len}자 (첫 글자: '{first_char}...')"
        else:
            structural_cue = f"형태 힌트: [{mask_step1}] · 길이: {char_len}자 (첫 글자: '{first_char}...')"
    else:
        structural_cue = f"구조 힌트: 앞글자 공개 [{mask_step2}] · 총 {char_len}자 (핵심 어휘 {len(tokens) or 1}개)"

    # Build a meaningful, non-robotic contextual cue without leaking primary_target
    masked_context = ""
    if extra_explanation:
        safe_ctx = extra_explanation
        if primary_target:
            safe_ctx = re.compile(re.escape(primary_target), re.IGNORECASE).sub("[ ___ ]", safe_ctx)
        for tok in tokens:
            if len(tok) >= 2:
                safe_ctx = re.compile(re.escape(tok), re.IGNORECASE).sub("[ ___ ]", safe_ctx)
        masked_context = safe_ctx[:95].strip()

    if masked_context:
        socratic_q = f"맥락 단서: {masked_context}"
    elif numbers:
        socratic_q = f"숫자·단위 단서: 총 {char_len}자이며 핵심 수치 형태([{mask_step1}])를 포함합니다."
    elif has_alpha:
        socratic_q = f"영단어 단서: '{first_char}'(으)로 시작하는 {char_len}글자 표현입니다. [{mask_step1}]"
    else:
        socratic_q = f"핵심 초성 [{mask_step1}] ({char_len}글자)에 들어갈 알맞은 말을 떠올려 보세요."

    if lapses >= 2:
        mnemonic = f"💡 [Leech 집중 처방] 첫 글자 '{first_char}' + [{mask_step2}] 조합만 먼저 입으로 소리 내어 기억하세요."
    else:
        mnemonic = f"💡 1단계 초성/철자 [{mask_step1}] → 한 번 더 누르면 앞글자([{mask_step2}])가 열립니다."

    return SocraticHint(
        level=max(1, int(level)),
        structural_cue=structural_cue,
        socratic_question=socratic_q,
        mnemonic_tip=mnemonic,
    )


def decompose_leech_card(front_text: str, back_text: str) -> List[GeneratedCardSpec]:
    """Break a complex 'Leech' card into atomic micro-cards, guarding short/1-word cards against self-spoilers."""
    core_answer, extra_exp = extract_clean_target_answer(front_text, back_text)
    clean_front = _clean_expected_text(front_text)
    clauses = [
        c.strip()
        for c in re.split(r"(?:[.;\n]|이며,|이고,|또한|그리고|반면)", _clean_expected_text(f"{front_text} — {back_text}"))
        if len(c.strip()) >= 12
    ]

    # Guard for short / single-word / atomic vocabulary cards:
    # Instead of creating a broken `{{c1::소개하다}}` self-answering card, generate 2 complementary scaffolded micro-cards!
    if len(core_answer) <= 18 and len(clauses) <= 1:
        mask_step1, char_len, primary_target = _build_choseong_or_letter_mask(core_answer, reveal_first_char=False)
        prompt_head = clean_front.splitlines()[-1].strip() if clean_front else front_text.strip()
        card1 = GeneratedCardSpec(
            note_type="basic",
            front_text=f"🧩 [기초 징검다리 #1 · 초성/철자 인출]\n{front_text.strip()}\n💡 힌트: [{mask_step1}] ({char_len}자)",
            back_text=core_answer + (f"\n\n💡 해설: {extra_exp}" if extra_exp else ""),
            tags=("leech-decomposed", "scaffold-step1"),
            rationale=f"단일 개념('{primary_target}')에 초성/철자 스캐폴딩을 부여하여 인출 장벽 완화",
        )
        card2 = GeneratedCardSpec(
            note_type="basic",
            front_text=f"🔄 [기초 징검다리 #2 · 역방향 확인]\n뜻/정답이 '{primary_target}'에 해당하는 핵심 표현·개념은?",
            back_text=prompt_head,
            tags=("leech-decomposed", "reverse-check"),
            rationale=f"단일 개념('{primary_target}')을 역방향으로 교차 확인하여 장기기억 고정",
        )
        return [card1, card2]

    if not clauses:
        clauses = [_clean_expected_text(f"{front_text} — {back_text}")]

    atomic_cards: List[GeneratedCardSpec] = []
    for idx, clause in enumerate(clauses[:4], start=1):
        tokens = _extract_meaningful_tokens(clause)
        if not tokens:
            continue
        target_tok = max(tokens, key=lambda t: (any(ch.isdigit() for ch in t), len(t)))
        pattern = re.compile(re.escape(target_tok), re.IGNORECASE)
        cloze_clause = pattern.sub(f"{{{{c1::{target_tok}::핵심 키워드}}}}", clause, count=1)
        if "{{c1::" not in cloze_clause:
            cloze_clause = f"{clause} → {{{{c1::{target_tok}}}}}"
        atomic_cards.append(
            GeneratedCardSpec(
                note_type="cloze",
                front_text=cloze_clause,
                back_text=f"[Leech 원자 분할 #{idx}] 정답: {target_tok}\n💡 해설: 원문 — {clause}",
                tags=("leech-decomposed", "atomic-micro-card"),
                rationale=f"복합 문장을 단일 인출 타겟('{target_tok}')으로 원자화하여 인지 부하를 낮춤",
            )
        )
    return atomic_cards


def extract_smart_cards_deterministic(
    raw_text: str,
    domain_mode: str = "auto",
    max_cards: int = 12,
    difficulty_level: str = "standard",
) -> List[GeneratedCardSpec]:
    """Deterministic NLP card extractor (0-Quota instant generation & Fail-Closed fallback).

    Supports difficulty stratification:
    - 'lv1' / 'standard': foundational recognition & single-concept Cloze
    - 'lv2': contextual Cloze / application
    - 'lv3': reverse production (meaning -> term/formula) & multi-blank deep synthesis
    - 'mixed': balanced combination of Lv.1, Lv.2, and Lv.3 cards
    """
    text = (raw_text or "").strip()
    if not text:
        return []

    from anki_studio.domain.document_deck_builder import (
        _extract_noun_candidates,
        _mask_term_in_desc,
        is_generic_section_label,
        is_toc_or_structural_heading,
    )

    diff_norm = (difficulty_level or "standard").strip().lower()
    raw_lines = [ln.strip(" \t•-*") for ln in text.splitlines() if len(ln.strip(" \t•-*")) >= 2]
    cards: List[GeneratedCardSpec] = []
    active_heading_topic = ""

    for line_idx, line in enumerate(raw_lines):
        if len(cards) >= max_cards:
            break

        if is_toc_or_structural_heading(line, "paragraph"):
            cleaned_h = line.lstrip("#*•- ").strip(" []<>《》「」『』")
            if (
                2 <= len(cleaned_h) <= 40
                and not is_generic_section_label(cleaned_h)
                and not re.search(r"(?:목\s*차|차\s*례|table\s+of\s+contents|\.{2,}|…+)", cleaned_h, re.IGNORECASE)
            ):
                active_heading_topic = cleaned_h
            continue

        if len(line) < 6:
            continue

        eff_diff = diff_norm
        if diff_norm in ("mixed", "all"):
            eff_diff = ("lv1", "lv2", "lv3")[len(cards) % 3]

        # 1. Already contains Cloze syntax
        if extract_cloze_ordinals(line):
            cards.append(
                GeneratedCardSpec(
                    note_type="cloze",
                    front_text=line,
                    back_text="",
                    tags=(domain_mode, "auto-cloze", eff_diff),
                    rationale="기존 Cloze 구문 자동 인식",
                )
            )
            continue

        # 2. English correction or translation pair: `Wrong -> Right` or `English | 한국어`
        arrow_match = re.split(r"\s*(?:->|→|=>|\|)\s*", line, maxsplit=1)
        if len(arrow_match) == 2 and len(arrow_match[0]) >= 3 and len(arrow_match[1]) >= 3:
            left, right = arrow_match[0].strip(), arrow_match[1].strip()
            if is_generic_section_label(left) and is_generic_section_label(right):
                continue
            is_english = sum(1 for c in right if "a" <= c.lower() <= "z") > len(right) * 0.4
            if is_english or domain_mode == "english":
                if eff_diff == "lv1":
                    cards.append(
                        GeneratedCardSpec(
                            note_type="basic",
                            front_text=f"📘 [Lv.1] {right}",
                            back_text=left,
                            tags=("english", "lv1", "ai-factory"),
                            rationale="Lv.1 영어 표현 의미 인지 카드",
                        )
                    )
                elif eff_diff == "lv3":
                    mask_s1, char_c, _ = _build_choseong_or_letter_mask(right, reveal_first_char=False)
                    cards.append(
                        GeneratedCardSpec(
                            note_type="speaking",
                            front_text=f"🔥 [Lv.3 영작·발화] {left}\n(단서: {mask_s1}, {char_c}자)",
                            back_text=right,
                            tags=("english", "speaking-drill", "lv3", "ai-factory"),
                            rationale="Lv.3 역방향 능동 영작·발화 카드",
                        )
                    )
                else:
                    cards.append(
                        GeneratedCardSpec(
                            note_type="speaking",
                            front_text=f"🗣️ [영어 발화] {left}",
                            back_text=right,
                            tags=("english", "speaking-drill", "ai-factory"),
                            rationale="한영/교정 쌍을 스피킹 액티브 리콜 카드로 변환",
                        )
                    )
            else:
                if eff_diff == "lv3":
                    cards.append(
                        GeneratedCardSpec(
                            note_type="basic",
                            front_text=f"🔥 [Lv.3 원인·조건] {right}",
                            back_text=left,
                            tags=(domain_mode, "causal-reverse", "lv3", "ai-factory"),
                            rationale="Lv.3 결과에서 원인을 역추적하는 심화 카드",
                        )
                    )
                else:
                    cards.append(
                        GeneratedCardSpec(
                            note_type="cloze",
                            front_text=f"{left} ➔ {{{{c1::{right}::핵심 결과/정의}}}}",
                            back_text=f"{right}\n\n💡 해설: {left} → {right}",
                            tags=(domain_mode, "causal-cloze", "ai-factory"),
                            rationale="인과/화살표 구문을 Cloze 빈칸 카드로 변환",
                        )
                    )
            continue

        # 3. `Term : Definition` or `Term — Definition`
        colon_match = re.split(r"\s*(?::|：|—| - )\s*", line, maxsplit=1)
        topic_prefix = ""
        if len(colon_match) == 2 and 2 <= len(colon_match[0]) <= 45 and len(colon_match[1]) >= 6:
            term, definition = colon_match[0].strip(), colon_match[1].strip()
            if is_toc_or_structural_heading(definition, "paragraph"):
                continue
            if is_generic_section_label(term):
                # Do NOT ask the generic label ('특징', '1. 배경', '의의') as the question or answer!
                # Unwrap the content sentence on the right-hand side and attach heading context if available.
                line = definition
                if active_heading_topic and active_heading_topic not in line:
                    topic_prefix = f"[{active_heading_topic}] "
            else:
                safe_def = _mask_term_in_desc(definition, term)
                if eff_diff == "lv1":
                    cards.append(
                        GeneratedCardSpec(
                            note_type="basic",
                            front_text=f"🌱 [Lv.1 개념 확인] {safe_def}",
                            back_text=f"{term}\n\n💡 해설: {definition}",
                            tags=(domain_mode, "term-basic", "lv1", "ai-factory"),
                            rationale=f"Lv.1 내용·정의를 보고 핵심 용어('{term}') 확인",
                        )
                    )
                elif eff_diff == "lv3":
                    cards.append(
                        GeneratedCardSpec(
                            note_type="basic",
                            front_text=f"🔥 [Lv.3 용어 인출] {safe_def}",
                            back_text=f"{term}\n\n💡 해설: {definition}",
                            tags=(domain_mode, "term-reverse", "lv3", "ai-factory"),
                            rationale=f"Lv.3 정의를 보고 용어('{term}')를 역산출하는 심화 카드",
                        )
                    )
                else:
                    cards.append(
                        GeneratedCardSpec(
                            note_type="cloze",
                            front_text=f"{{{{c1::{term}::핵심 용어}}}}: {safe_def}",
                            back_text=f"{term}\n\n💡 해설: {definition}",
                            tags=(domain_mode, "term-cloze", "ai-factory"),
                            rationale=f"핵심 용어('{term}')와 정의를 Cloze로 변환",
                        )
                    )
                continue

        # 4. General prose sentence: convert key technical metric + key concept into Cloze
        noun_cands = _extract_noun_candidates(line)
        tokens = noun_cands if noun_cands else [
            t for t in _extract_meaningful_tokens(line) if not is_generic_section_label(t)
        ]
        if len(tokens) >= 1:
            ranked = sorted(
                dict.fromkeys(tokens),
                key=lambda t: (
                    any(ch.isdigit() for ch in t),
                    any("A" <= ch <= "Z" for ch in t),
                    len(t),
                ),
                reverse=True,
            )
            max_blanks = 1 if eff_diff == "lv1" else (3 if eff_diff == "lv3" else 2)
            cloze_line = line
            used = 0
            used_tokens: List[str] = []
            for tok in ranked[:max_blanks]:
                pat = re.compile(re.escape(tok), re.IGNORECASE)
                if pat.search(cloze_line):
                    used += 1
                    used_tokens.append(tok)
                    cloze_line = pat.sub(f"{{{{c{used}::{tok}}}}}", cloze_line, count=1)
            if used > 0:
                cards.append(
                    GeneratedCardSpec(
                        note_type="cloze",
                        front_text=f"{topic_prefix}{cloze_line}",
                        back_text=f"{' · '.join(used_tokens)}\n\n💡 해설: {topic_prefix}{line}",
                        tags=(domain_mode, "prose-cloze", "ai-factory"),
                        rationale="문장 내 핵심 기술 용어/수치를 빈칸(Cloze) 카드로 자동 변환",
                    )
                )

    return cards


def interleave_study_cards(
    cards: Sequence[Dict[str, object]],
    shuffle_mode: str = "interleaved",
    seed: int | None = None,
) -> List[Dict[str, object]]:
    """Intelligent Interleaved Random Shuffler for Multi-Scope Exam & Daily Study Queues.

    Prevents sequential context dependency (e.g., all Lesson 1 cards in insertion order followed
    by all Lesson 2 cards) by grouping cards into source/topic buckets, sorting/shuffling within
    buckets with FSRS urgency weighting, and interleaving across buckets with an anti-streak
    constraint (no >2 consecutive cards from the same bucket while other buckets remain).
    """
    items = list(cards)
    if len(items) <= 1 or shuffle_mode in ("sequential", "off", "none"):
        return items

    import hashlib

    def _det_hash(card_obj: Dict[str, object], salt: int) -> int:
        cid = str(card_obj.get("card_id") or card_obj.get("note_id") or card_obj.get("front_text") or "")
        raw = f"{cid}:{salt}:{seed if seed is not None else 'auto'}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")

    def _source_bucket(card_obj: Dict[str, object]) -> str:
        raw_tags = card_obj.get("tags")
        if raw_tags is None:
            raw_tags = card_obj.get("tags_json")
        if isinstance(raw_tags, str) and raw_tags.strip().startswith("["):
            try:
                parsed = json.loads(raw_tags)
                if isinstance(parsed, list):
                    raw_tags = parsed
            except Exception:
                pass
        if isinstance(raw_tags, (list, tuple)):
            tag_tokens = [str(t).strip() for t in raw_tags if str(t).strip()]
        else:
            tag_tokens = [t.strip("[]'\" ") for t in str(raw_tags or "").replace(",", " ").split() if t.strip("[]'\" ")]
        for tok in tag_tokens:
            if any(tok.startswith(p) for p in ("kr.", "hanja-", "hanja_", "moe-", "ko-", "khist:", "exam-", "law-", "sci-", "cert-", "U0", "u")):
                return tok
        for tok in tag_tokens:
            if not tok.startswith("diff_") and tok not in ("curriculum", "combined_exam", "basic", "cloze", "speaking", "auto"):
                return tok
        front = str(card_obj.get("front_text") or card_obj.get("front") or "")
        m_br = re.search(r"\[([^\[\]]{2,24})\]", front)
        if m_br:
            return m_br.group(1)
        return str(card_obj.get("deck_name") or card_obj.get("note_type") or "general")

    if shuffle_mode == "random":
        salt_base = seed if seed is not None else len(items) * 37
        return sorted(items, key=lambda c: _det_hash(c, salt_base))

    # Default: "interleaved" — bucket by unit/collection/topic, shuffle within buckets, then greedy largest-bucket-first anti-streak
    buckets: Dict[str, List[Dict[str, object]]] = {}
    for c in items:
        b_key = _source_bucket(c)
        buckets.setdefault(b_key, []).append(c)

    salt_val = seed if seed is not None else (sum(int(c.get("card_id") or idx) for idx, c in enumerate(items, 1)) % 9973)
    for b_key, b_list in buckets.items():
        # Priority: learning/relearning first, then randomized within tier
        b_list.sort(
            key=lambda c: (
                0 if str(c.get("state") or "") in ("learning", "relearning") else 1,
                _det_hash(c, salt_val),
            )
        )

    bucket_rank = {
        k: int.from_bytes(hashlib.sha256(f"{k}:{salt_val}".encode("utf-8")).digest()[:4], "big")
        for k in buckets
    }
    bucket_keys = sorted(buckets.keys(), key=lambda k: bucket_rank[k])

    result: List[Dict[str, object]] = []
    last_bucket = ""
    streak = 0
    remaining = sum(len(v) for v in buckets.values())

    while remaining > 0:
        active_keys = [k for k in bucket_keys if buckets[k]]
        if not active_keys:
            break
        candidates = active_keys
        if len(active_keys) > 1 and last_bucket and streak >= 2:
            non_streak = [k for k in active_keys if k != last_bucket]
            if non_streak:
                candidates = non_streak
        # Greedy largest-bucket-first with switch bonus to prevent end-of-queue streak clustering
        candidates = sorted(
            candidates,
            key=lambda k: (
                len(buckets[k]) + (0.35 if k != last_bucket else 0.0),
                -bucket_rank[k],
            ),
            reverse=True,
        )
        chosen_key = candidates[0]
        picked = buckets[chosen_key].pop(0)
        result.append(picked)
        remaining -= 1
        if chosen_key == last_bucket:
            streak += 1
        else:
            last_bucket = chosen_key
            streak = 1

    return result


def build_ai_card_generation_prompt(raw_text: str, domain_mode: str = "auto", max_cards: int = 8) -> str:
    """Construct a strict JSON-only prompt for LLM-powered flashcard synthesis."""
    return (
        "당신은 인지과학(FSRS-5 & Active Recall) 기반 플래시카드 설계 전문가입니다.\n"
        f"도메인 모드: {domain_mode}\n"
        f"아래 원문에서 장기 기억에 꼭 필요한 핵심 지식만 골라 최대 {max_cards}개의 카드를 JSON 배열로 생성하세요.\n"
        "규칙:\n"
        "1. 하나의 카드가 너무 많은 정보를 묻지 않도록 '최소 정보 원칙(Minimum Information Principle)'을 지키세요.\n"
        "2. `note_type`은 'cloze'(빈칸: `{{c1::정답::힌트}}`), 'basic'(질문/답변), 'speaking'(영어회화 발화) 중 하나입니다.\n"
        "3. 목차(차례, Table of Contents, 페이지 번호 점선), 단순 장·절 제목(제1장, Chapter 1), 일반 항목 라벨(특징, 배경, 개요, 의의, 목적 등)을 묻는 카드는 절대 생성하지 마세요.\n"
        "4. 질문(front_text)에는 구체적인 내용·정의·맥락을 제시하고, 정답(back_text)에는 핵심 용어·개념만 간결하게 제시하세요. 불필요한 상투적 지시문과 중복 해설을 배제하세요.\n"
        "5. 반드시 순수 JSON 배열만 출력하세요:\n"
        '[{"note_type":"cloze","front_text":"...","back_text":"...","tags":["tag1"],"rationale":"..."}]\n\n'
        f"원문:\n{raw_text.strip()}"
    )


def parse_ai_generated_cards(
    raw_llm_output: str,
    fallback_source_text: str = "",
    domain_mode: str = "auto",
    max_cards: int = 12,
) -> List[GeneratedCardSpec]:
    """Parse LLM JSON response into `GeneratedCardSpec` list with Fail-Closed deterministic fallback."""
    from anki_studio.domain.document_deck_builder import (
        is_generic_section_label,
        is_toc_or_structural_heading,
    )

    cleaned = (raw_llm_output or "").strip()
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start_idx = cleaned.find("[")
    end_idx = cleaned.rfind("]")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_slice = cleaned[start_idx : end_idx + 1]
        try:
            parsed = json.loads(json_slice)
            if isinstance(parsed, list):
                specs: List[GeneratedCardSpec] = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    front = str(item.get("front_text") or "").strip()
                    back = str(item.get("back_text") or "").strip()
                    ntype = str(item.get("note_type") or "basic").strip().lower()
                    if ntype not in ("cloze", "basic", "speaking"):
                        ntype = "cloze" if "{{c" in front else "basic"
                    if not front:
                        continue
                    if is_toc_or_structural_heading(front, "paragraph") or is_generic_section_label(front):
                        continue
                    if back and is_generic_section_label(back.splitlines()[0]):
                        continue
                    if ntype == "cloze" and not extract_cloze_ordinals(front):
                        ntype = "basic"
                    raw_tags = item.get("tags")
                    tags = tuple(str(t).strip() for t in raw_tags if str(t).strip()) if isinstance(raw_tags, Sequence) and not isinstance(raw_tags, str) else (domain_mode, "ai-llm")
                    rationale = str(item.get("rationale") or "스마트 구조화 카드").strip()
                    specs.append(
                        GeneratedCardSpec(
                            note_type=ntype,
                            front_text=front,
                            back_text=back,
                            tags=tags,
                            rationale=rationale,
                        )
                    )
                if specs:
                    return specs[:max_cards]
        except (ValueError, TypeError):
            pass

    return extract_smart_cards_deterministic(fallback_source_text, domain_mode=domain_mode, max_cards=max_cards)


def resolve_card_solve_mode(
    solve_mode: str = "adaptive",
    reps: int = 0,
    lapses: int = 0,
    state: str = "new",
) -> str:
    """Resolve the single active interaction mode (`flip` | `choice` | `typing`) for a card (Law 2: 1-Card 1-Mode)."""
    mode = (solve_mode or "adaptive").strip().lower()
    if mode in ("flip", "choice", "typing"):
        return mode
    # Adaptive mode: first encounter (`reps == 0` or `state == "new"`) -> 4-choice recognition;
    # subsequent reviews (`reps >= 1`) -> active typing production (or choice if repeated lapse needs scaffolding)
    if int(reps or 0) <= 0 or str(state or "").lower() == "new":
        return "choice"
    return "typing"


def resolve_allowed_ratings(
    is_revealed: bool,
    choice_correct: bool | None = None,
    typed_verdict: str | None = None,
    hint_step: int = 0,
    dont_know: bool = False,
    age_tier: str = "adult",
) -> Dict[str, object]:
    """Enforce Metacognitive Rating Calibration (Law 3: EvidenceRatingGuard).

    Rules:
    1. If `is_revealed` is False -> `allowed_ratings = ()`, `locked_reason = "pre_reveal"`.
    2. If `dont_know` is True, `choice_correct` is False, or `typed_verdict == "UNKNOWN"` ->
       Only `Again(1)` is allowed (`allowed_ratings = (1,)`), `recommended_rating = 1`.
    3. If `hint_step >= 1` -> Capped at `Hard(2)` (`allowed_ratings = (1, 2)`), `recommended_rating = 2`.
    4. If `typed_verdict == "PARTIAL"` (without hint) -> Capped at `Good(3)` (`allowed_ratings = (1, 2, 3)`), `recommended_rating = 2`.
    5. Otherwise (unassisted recall / flip) -> `allowed_ratings = (1, 2, 3)` for `junior` else `(1, 2, 3, 4)`, `recommended_rating = 3`.
    """
    if not is_revealed:
        return {
            "allowed_ratings": (),
            "recommended_rating": None,
            "max_rating": 0,
            "locked_reason": "pre_reveal",
        }

    verdict_upper = str(typed_verdict or "").strip().upper()
    if dont_know or (choice_correct is False) or verdict_upper == "UNKNOWN":
        return {
            "allowed_ratings": (1,),
            "recommended_rating": 1,
            "max_rating": 1,
            "locked_reason": "wrong_or_unknown",
        }

    if int(hint_step or 0) >= 1:
        return {
            "allowed_ratings": (1, 2),
            "recommended_rating": 2,
            "max_rating": 2,
            "locked_reason": "hint_assisted_cap",
        }

    if verdict_upper == "PARTIAL":
        return {
            "allowed_ratings": (1, 2, 3),
            "recommended_rating": 2,
            "max_rating": 3,
            "locked_reason": "partial_recall_cap",
        }

    tier = str(age_tier or "adult").strip().lower()
    if tier == "junior":
        return {
            "allowed_ratings": (1, 2, 3),
            "recommended_rating": 3,
            "max_rating": 3,
            "locked_reason": "none",
        }

    return {
        "allowed_ratings": (1, 2, 3, 4),
        "recommended_rating": 3,
        "max_rating": 4,
        "locked_reason": "none",
    }


def deduplicate_session_siblings(cards: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """Enforce Sibling Burying (Law 4: 1-Concept 1-Session).

    If multiple difficulty facets (`lv1`, `lv2`, `lv3`) sharing the same `concept:<id>` tag appear in
    a study session queue, keep at most 1 card per concept in the current session, prioritizing
    `learning`/`relearning` cards first, then `lv1` -> `lv2` -> `lv3`.
    """
    items = list(cards)
    if len(items) <= 1:
        return items

    def _extract_tags(card_obj: Dict[str, object]) -> List[str]:
        raw = card_obj.get("tags")
        if raw is None:
            raw = card_obj.get("tags_json")
        if isinstance(raw, str) and raw.strip().startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    raw = parsed
            except Exception:
                pass
        if isinstance(raw, (list, tuple)):
            return [str(t).strip() for t in raw if str(t).strip()]
        return [t.strip("[]'\" ") for t in str(raw or "").replace(",", " ").split() if t.strip("[]'\" ")]

    def _concept_key(card_obj: Dict[str, object]) -> str | None:
        for tok in _extract_tags(card_obj):
            if tok.startswith("concept:") and len(tok) > 8:
                return tok
        return None

    def _priority_rank(card_obj: Dict[str, object]) -> Tuple[int, int]:
        st = str(card_obj.get("state") or "new").lower()
        state_rank = 0 if st in ("learning", "relearning") else (1 if st == "review" else 2)
        tags = _extract_tags(card_obj)
        diff_rank = 0 if ("diff_lv1" in tags or "lv1" in tags) else (1 if ("diff_lv2" in tags or "lv2" in tags) else 2)
        return (state_rank, diff_rank)

    best_by_concept: Dict[str, Dict[str, object]] = {}
    for c in items:
        ckey = _concept_key(c)
        if not ckey:
            continue
        prev = best_by_concept.get(ckey)
        if prev is None or _priority_rank(c) < _priority_rank(prev):
            best_by_concept[ckey] = c

    seen_concepts: set[str] = set()
    deduped: List[Dict[str, object]] = []
    for c in items:
        ckey = _concept_key(c)
        if not ckey:
            deduped.append(c)
            continue
        if ckey in seen_concepts:
            continue
        seen_concepts.add(ckey)
        deduped.append(best_by_concept[ckey])
    return deduped

