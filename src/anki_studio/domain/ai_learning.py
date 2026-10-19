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

_NUMBER_UNIT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:nm|um|mm|hz|khz|mhz|ghz|db|dbfs|%|gb|tb|mb|w|v|m|s|ms|일|개|배|차)?\b", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[A-Za-z0-9가-힣\-\+/\.]+")
_CLOZE_STRIP_PATTERN = re.compile(r"\{\{c\d+::([^}:]+)(?:::[^}]+)?\}\}")


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

    # If the expected answer had explicit Cloze focus `【...】`, prioritize grading that focus span
    cloze_focus_matches = re.findall(r"【([^】]+)】", expected_answer or "")
    grading_reference = " ".join(cloze_focus_matches) if cloze_focus_matches else target_clean

    ref_tokens = _extract_meaningful_tokens(grading_reference)
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

    ref_bigrams = _char_bigrams(grading_reference)
    user_bigrams = _char_bigrams(user_clean)
    if ref_bigrams and user_bigrams:
        overlap = len(ref_bigrams & user_bigrams)
        bigram_recall = overlap / len(ref_bigrams)
    else:
        bigram_recall = 0.0

    # Check critical numbers/units (e.g., 13.5 nm, 90%, 0.55)
    ref_numbers = {re.sub(r"\s+", "", m.group(0).lower()) for m in _NUMBER_UNIT_PATTERN.finditer(grading_reference)}
    user_numbers = {re.sub(r"\s+", "", m.group(0).lower()) for m in _NUMBER_UNIT_PATTERN.finditer(user_clean)}
    numeric_match = True
    if ref_numbers:
        numeric_match = ref_numbers.issubset(user_numbers) or all(
            any(rn in un or un in rn for un in user_numbers) for rn in ref_numbers
        )

    # Check negation conflict
    ref_has_neg = any(neg in grading_reference.lower() for neg in _NEGATION_TOKENS)
    user_has_neg = any(neg in user_lower for neg in _NEGATION_TOKENS)
    negation_conflict = bool(ref_tokens) and (ref_has_neg != user_has_neg) and len(ref_tokens) >= 2

    raw_score = (0.65 * token_recall + 0.35 * bigram_recall) * 100.0
    if not numeric_match:
        raw_score = min(raw_score, 55.0)
    if negation_conflict:
        raw_score = max(0.0, raw_score - 35.0)

    # Exact normalized match boost
    if re.sub(r"\s+", "", user_clean.lower()) == re.sub(r"\s+", "", grading_reference.lower()):
        raw_score = 100.0
        missing = []

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
        miss_preview = ", ".join(missing[:4]) if missing else grading_reference[:30]
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
    """Generate a non-spoiler Socratic hint and mnemonic cue for active recall."""
    focus_matches = re.findall(r"【([^】]+)】", target_answer or "")
    core_answer = focus_matches[0].strip() if focus_matches else _clean_expected_text(target_answer)
    if not core_answer:
        core_answer = "핵심 개념"

    tokens = _extract_meaningful_tokens(core_answer)
    first_char = core_answer[0]
    char_len = len(core_answer)

    if level <= 1:
        structural_cue = f"첫 글자: '{first_char}...' · 길이: {char_len}자"
    else:
        masked = " ".join(
            (w[0] + "·" * max(1, len(w) - 1)) if len(w) > 1 else w
            for w in core_answer.split()
        )
        structural_cue = f"구조 힌트: {masked} (핵심 어휘 {len(tokens) or 1}개)"

    numbers = [m.group(0) for m in _NUMBER_UNIT_PATTERN.finditer(core_answer)]
    if numbers:
        socratic_q = f"이 개념에서 가장 결정적인 물리적/정량적 수치(단위 포함)는 얼마인가요?"
    elif any("a" <= ch.lower() <= "z" for ch in core_answer):
        socratic_q = f"'{first_char}'(으)로 시작하는 핵심 전문 용어/표현의 정확한 역할은 무엇인가요?"
    else:
        socratic_q = f"문제의 맥락({question_text[:28]}...)에서 원인과 결과를 연결하는 핵심 메커니즘은 무엇인가요?"

    acronym = "".join(t[0].upper() for t in tokens[:4]) if tokens else first_char.upper()
    if lapses >= 2:
        mnemonic = f"💡 [Leech 집중 처방] 앞글자 연상 코드 [{acronym}] — 통째로 외우지 말고 '{tokens[0] if tokens else core_answer[:8]}' 키워드 하나만 먼저 떠올리세요."
    else:
        mnemonic = f"💡 연상 앵커 [{acronym}]: 질문의 핵심 조건과 '{first_char}...' 키워드를 1:1로 묶어 기억하세요."

    return SocraticHint(
        level=max(1, int(level)),
        structural_cue=structural_cue,
        socratic_question=socratic_q,
        mnemonic_tip=mnemonic,
    )


def decompose_leech_card(front_text: str, back_text: str) -> List[GeneratedCardSpec]:
    """Break a complex 'Leech' card (repeatedly forgotten) into atomic micro-Cloze cards."""
    combined = _clean_expected_text(front_text if "{{c" in (front_text or "") else f"{front_text} — {back_text}")
    clauses = [
        c.strip()
        for c in re.split(r"(?:[.;\n]|이며,|이고,|또한|그리고|반면)", combined)
        if len(c.strip()) >= 10
    ]
    if not clauses:
        clauses = [combined]

    atomic_cards: List[GeneratedCardSpec] = []
    for idx, clause in enumerate(clauses[:4], start=1):
        tokens = _extract_meaningful_tokens(clause)
        if not tokens:
            continue
        # Pick the most specific token (longest or containing digits/uppercase)
        target_tok = max(tokens, key=lambda t: (any(ch.isdigit() for ch in t), len(t)))
        pattern = re.compile(re.escape(target_tok), re.IGNORECASE)
        cloze_clause = pattern.sub(f"{{{{c1::{target_tok}::핵심 키워드}}}}", clause, count=1)
        if "{{c1::" not in cloze_clause:
            cloze_clause = f"{clause} → {{{{c1::{target_tok}}}}}"
        atomic_cards.append(
            GeneratedCardSpec(
                note_type="cloze",
                front_text=cloze_clause,
                back_text=f"[Leech 원자 분할 #{idx}] 원문: {clause}",
                tags=("leech-decomposed", "atomic-micro-card"),
                rationale=f"복합 문장을 단일 인출 타겟('{target_tok}')으로 원자화하여 인지 부하를 낮춤",
            )
        )
    return atomic_cards


def extract_smart_cards_deterministic(
    raw_text: str,
    domain_mode: str = "auto",
    max_cards: int = 12,
) -> List[GeneratedCardSpec]:
    """Deterministic NLP card extractor (0-Quota instant generation & Fail-Closed fallback).

    Converts raw notes (English tutoring notes, semiconductor/AI handbook paragraphs,
    bullet lists, or `Term: Definition` lines) into Cloze, Basic Q&A, and Speaking cards.
    """
    text = (raw_text or "").strip()
    if not text:
        return []

    lines = [ln.strip(" \t•-*") for ln in text.splitlines() if len(ln.strip(" \t•-*")) >= 6]
    cards: List[GeneratedCardSpec] = []

    for line in lines:
        if len(cards) >= max_cards:
            break

        # 1. Already contains Cloze syntax
        if extract_cloze_ordinals(line):
            cards.append(
                GeneratedCardSpec(
                    note_type="cloze",
                    front_text=line,
                    back_text="",
                    tags=(domain_mode, "auto-cloze"),
                    rationale="기존 Cloze 구문 자동 인식",
                )
            )
            continue

        # 2. English correction or translation pair: `Wrong -> Right` or `English | 한국어`
        arrow_match = re.split(r"\s*(?:->|→|=>|\|)\s*", line, maxsplit=1)
        if len(arrow_match) == 2 and len(arrow_match[0]) >= 3 and len(arrow_match[1]) >= 3:
            left, right = arrow_match[0].strip(), arrow_match[1].strip()
            is_english = sum(1 for c in right if "a" <= c.lower() <= "z") > len(right) * 0.4
            if is_english or domain_mode == "english":
                cards.append(
                    GeneratedCardSpec(
                        note_type="speaking",
                        front_text=f"🗣️ [영어 표현 인출] {left}",
                        back_text=right,
                        tags=("english", "speaking-drill", "ai-factory"),
                        rationale="한영/교정 쌍을 스피킹 액티브 리콜 카드로 변환",
                    )
                )
            else:
                cards.append(
                    GeneratedCardSpec(
                        note_type="cloze",
                        front_text=f"{left} ➔ {{{{c1::{right}::핵심 결과/정의}}}}",
                        back_text=f"{left} → {right}",
                        tags=(domain_mode, "causal-cloze", "ai-factory"),
                        rationale="인과/화살표 구문을 Cloze 빈칸 카드로 변환",
                    )
                )
            continue

        # 3. `Term : Definition` or `Term — Definition`
        colon_match = re.split(r"\s*(?::|—| - )\s*", line, maxsplit=1)
        if len(colon_match) == 2 and 2 <= len(colon_match[0]) <= 45 and len(colon_match[1]) >= 6:
            term, definition = colon_match[0].strip(), colon_match[1].strip()
            cards.append(
                GeneratedCardSpec(
                    note_type="cloze",
                    front_text=f"{{{{c1::{term}::핵심 용어}}}}: {definition}",
                    back_text=f"용어: {term}\n정의: {definition}",
                    tags=(domain_mode, "term-cloze", "ai-factory"),
                    rationale=f"핵심 용어('{term}')와 정의를 양방향 인출용 Cloze로 변환",
                )
            )
            continue

        # 4. General prose sentence: convert key technical metric + key concept into dual Cloze
        tokens = _extract_meaningful_tokens(line)
        if len(tokens) >= 2:
            # Prefer tokens with numbers/units or English technical acronyms
            ranked = sorted(
                dict.fromkeys(tokens),
                key=lambda t: (
                    any(ch.isdigit() for ch in t),
                    any("A" <= ch <= "Z" for ch in t),
                    len(t),
                ),
                reverse=True,
            )
            cloze_line = line
            used = 0
            for tok in ranked[:2]:
                pat = re.compile(re.escape(tok), re.IGNORECASE)
                if pat.search(cloze_line):
                    used += 1
                    cloze_line = pat.sub(f"{{{{c{used}::{tok}}}}}", cloze_line, count=1)
            if used > 0:
                cards.append(
                    GeneratedCardSpec(
                        note_type="cloze",
                        front_text=cloze_line,
                        back_text=line,
                        tags=(domain_mode, "prose-cloze", "ai-factory"),
                        rationale="문장 내 핵심 기술 용어/수치를 다중 빈칸(Cloze) 카드로 자동 변환",
                    )
                )

    return cards


def build_ai_card_generation_prompt(raw_text: str, domain_mode: str = "auto", max_cards: int = 8) -> str:
    """Construct a strict JSON-only prompt for LLM-powered flashcard synthesis."""
    return (
        "당신은 인지과학(FSRS-5 & Active Recall) 기반 플래시카드 설계 전문가입니다.\n"
        f"도메인 모드: {domain_mode}\n"
        f"아래 원문에서 장기 기억에 꼭 필요한 핵심 지식만 골라 최대 {max_cards}개의 카드를 JSON 배열로 생성하세요.\n"
        "규칙:\n"
        "1. 하나의 카드가 너무 많은 정보를 묻지 않도록 '최소 정보 원칙(Minimum Information Principle)'을 지키세요.\n"
        "2. `note_type`은 'cloze'(빈칸: `{{c1::정답::힌트}}`), 'basic'(질문/답변), 'speaking'(영어회화 발화) 중 하나입니다.\n"
        "3. 반드시 순수 JSON 배열만 출력하세요:\n"
        '[{"note_type":"cloze","front_text":"...","back_text":"...","tags":["tag1"],"rationale":"..."}]\n\n'
        f"원문:\n{raw_text.strip()}"
    )


def parse_ai_generated_cards(
    raw_llm_output: str,
    fallback_source_text: str = "",
    domain_mode: str = "auto",
) -> List[GeneratedCardSpec]:
    """Parse LLM JSON response into `GeneratedCardSpec` list with Fail-Closed deterministic fallback."""
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
                    if ntype == "cloze" and not extract_cloze_ordinals(front):
                        ntype = "basic"
                    raw_tags = item.get("tags")
                    tags = tuple(str(t).strip() for t in raw_tags if str(t).strip()) if isinstance(raw_tags, Sequence) and not isinstance(raw_tags, str) else (domain_mode, "ai-llm")
                    rationale = str(item.get("rationale") or "AI 구조화 카드").strip()
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
                    return specs
        except (ValueError, TypeError):
            pass

    return extract_smart_cards_deterministic(fallback_source_text, domain_mode=domain_mode)
