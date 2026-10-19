"""Pure-Domain Universal Document & Photo -> Auto-Deck Builder.

Strictly zero external I/O imports (no sqlite3, urllib, http, subprocess, os, pathlib, io).
Supports any learner (university, medical, law/civil service, certifications, languages, general study)
by extracting grounded flashcards across 5 universal educational patterns:
  1. `definition`: Term/Concept definitions (`용어: 설명`, `~란 ~이다`, `refers to`)
  2. `numbered_list`: Enumerated lists & exam criteria (`1) ... 2) ...`, `① ... ② ...`)
  3. `causal_compare`: Cause-effect & comparison (`~반면`, `~때문에`, `vs`, `→`, `whereas`)
  4. `statute_numeric`: Legal articles & numeric/unit facts (`제12조`, `30일 이내`, `120mmHg`, `3nm`)
  5. `language_pair`: Bilingual expressions & vocabulary (`A -> B`, example sentences)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Dict, List, Optional, Sequence, Tuple
import unicodedata

from .ai_learning import GeneratedCardSpec


VALID_BLOCK_KINDS = ("heading", "paragraph", "list_item", "table_row")
VALID_CATEGORIES = ("language", "law", "medical", "engineering", "exam", "general")
VALID_PATTERNS = (
    "definition",
    "numbered_list",
    "causal_compare",
    "statute_numeric",
    "language_pair",
)


@dataclass(frozen=True)
class DocumentBlock:
    """Single structural text block extracted from a document page or image."""

    kind: str
    text: str
    page: int = 1
    confidence: Optional[float] = None


@dataclass(frozen=True)
class ExtractedDocument:
    """Normalized representation of an uploaded PDF or photo."""

    blocks: Tuple[DocumentBlock, ...]
    title_hint: Optional[str] = None
    source_kind: str = "pdf"  # "pdf" | "image"
    page_count: int = 1


@dataclass(frozen=True)
class SourcedCard:
    """Flashcard grounded to an exact page and excerpt in the source document."""

    spec: GeneratedCardSpec
    pattern: str
    source_page: int
    source_excerpt: str


@dataclass(frozen=True)
class BuildStats:
    """Telemetry and quality gates for automatic deck construction."""

    pages: int
    ocr_pages: int
    low_confidence_lines: int
    unmeasured_confidence_lines: int
    dropped_ungrounded: int
    duplicates: int
    total_chars: int


@dataclass(frozen=True)
class DeckPlan:
    """Deterministic result of building a deck from an ExtractedDocument."""

    status: str  # "OK" | "BLOCKED"
    error_code: Optional[str]
    deck_name: str
    category: str
    cards: Tuple[SourcedCard, ...]
    stats: BuildStats


_CATEGORY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "law": (
        "제1조",
        "제2조",
        "제3조",
        "제1항",
        "판례",
        "대법원",
        "민법",
        "형법",
        "헌법",
        "행정법",
        "소멸시효",
        "불법행위",
        "선관주의",
        "법률",
        "조문",
        "청구권",
    ),
    "medical": (
        "환자",
        "증상",
        "진단",
        "치료",
        "투여",
        "해부",
        "생리",
        "약리",
        "항생제",
        "혈압",
        "mmhg",
        "심근",
        "신경",
        "세포",
        "호르몬",
        "증후군",
        "병리",
    ),
    "engineering": (
        "트랜지스터",
        "반도체",
        "알고리즘",
        "프로토콜",
        "아키텍처",
        "데이터베이스",
        "트랜잭션",
        "네트워크",
        "커널",
        "컴파일러",
        "메모리",
        "전압",
        "공정",
        "회로",
        "finfet",
        "gaa",
        "euv",
        "latency",
    ),
    "language": (
        "숙어",
        "문법",
        "발음",
        "예문",
        "뜻",
        "어휘",
        "회화",
        "idiom",
        "phrasal",
        "vocabulary",
        "grammar",
        "Follow up",
        "rain check",
    ),
    "exam": (
        "기출",
        "출제",
        "시험",
        "자격증",
        "암기",
        "요약",
        "핵심",
        "오답",
        "단원",
        "특징",
        "장단점",
    ),
}

_STOPWORDS = {
    "그리고",
    "그러나",
    "하지만",
    "따라서",
    "경우",
    "통해",
    "대한",
    "위한",
    "있는",
    "하는",
    "되는",
    "이다",
    "있다",
    "한다",
    "에서",
    "으로",
    "에게",
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "are",
    "was",
    "were",
    "have",
    "has",
}

_CLOZE_EXTRACT_RE = re.compile(r"\{\{c\d+::(.*?)(?:::.*?)?\}\}", re.DOTALL)
_STATUTE_RE = re.compile(r"(제\s*\d+\s*조(?:\s*의\s*\d+)?|제\s*\d+\s*항)")
_NUMERIC_UNIT_RE = re.compile(
    r"(?<![0-9A-Za-z])(\d+(?:\.\d+)?\s*(?:nm|um|mm|cm|km|mg|kg|ml|mmHg|Hz|kHz|MHz|GHz|V|mV|W|kW|%|배|일\s*이내|년\s*이하|년\s*이상|년간|개월|세\s*이상|시간))",
    re.IGNORECASE,
)
_NUMBERED_ITEM_RE = re.compile(
    r"(?:^|\s)(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(\d+\)|\d+\)|\d+\.)\s*(.+?)(?=(?:\s+(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(\d+\)|\d+\)|\d+\.)\s)|$)"
)
_ARROW_PAIR_RE = re.compile(r"^(.{3,100}?)\s*(?:->|=>|↔|⇄)\s*(.{3,160})$")
_COLON_DEF_RE = re.compile(r"^([^\n:：\-–—]{2,55}?)\s*(?::|：|\s-\s|\s–\s|\s—\s)\s*(.{8,300})$")
_KOREAN_DEF_RE = re.compile(
    r"^([가-힣A-Za-z0-9\s\(\)·\-/]{2,45}?)(?:이란|란|은|는)\s+(.{10,260}?(?:이다|말한다|의미한다|뜻한다|가리킨다|정의된다)\.?)$"
)
_ENGLISH_DEF_RE = re.compile(
    r"^([A-Za-z0-9\s\(\)\-/]{2,50}?)\s+(?:is defined as|refers to|means)\s+(.{10,260})$",
    re.IGNORECASE,
)
_CAUSAL_COMPARE_RE = re.compile(
    r"(.{6,160}?)\s*(때문에|반면에?|와\s*달리|과\s*달리|에\s*비해|→|whereas|because|leads\s+to|results\s+in|compared\s+to)\s*(.{6,200})",
    re.IGNORECASE,
)


def _clean_line(text: str) -> str:
    norm = unicodedata.normalize("NFKC", text or "")
    # Join hyphenated line-breaks (e.g. "semi-\nconductor" -> "semiconductor")
    norm = re.sub(r"([A-Za-z])-\s*\n\s*([A-Za-z])", r"\1\2", norm)
    norm = re.sub(r"[ \t]+", " ", norm)
    return norm.strip()


def infer_category(doc: ExtractedDocument) -> str:
    """Deterministically classify document into one of 6 universal study categories."""
    combined = " ".join([doc.title_hint or ""] + [b.text for b in doc.blocks]).lower()
    scores: Dict[str, int] = {cat: 0 for cat in VALID_CATEGORIES}

    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in combined:
                scores[cat] += 2

    # Structural signals
    if _STATUTE_RE.search(combined):
        scores["law"] += 4
    if any(_ARROW_PAIR_RE.match(b.text.strip()) for b in doc.blocks):
        scores["language"] += 3

    best_cat = "general"
    best_score = 0
    for cat in ("law", "medical", "engineering", "language", "exam"):
        if scores[cat] > best_score:
            best_score = scores[cat]
            best_cat = cat
    return best_cat if best_score >= 2 else "general"


def infer_deck_name(
    doc: ExtractedDocument,
    user_name: Optional[str] = None,
    now_date_str: str = "2026-10-19",
) -> str:
    """Priority: user_name > title_hint > first heading block > top 2-3 keywords > date fallback."""
    if user_name and user_name.strip():
        return user_name.strip()[:80]

    if doc.title_hint and len(doc.title_hint.strip()) >= 2:
        return doc.title_hint.strip()[:80]

    for b in doc.blocks:
        if b.kind == "heading":
            cleaned = _clean_line(b.text).lstrip("#*•- ").strip()
            if len(cleaned) >= 2:
                return cleaned[:80]

    # Extract top salient keywords
    token_counts: Counter[str] = Counter()
    for b in doc.blocks:
        if b.confidence is not None and b.confidence < 0.60:
            continue
        words = re.findall(r"[가-힣]{2,12}|[A-Za-z][A-Za-z0-9\-]{2,15}", b.text)
        for w in words:
            w_clean = re.sub(r"(이란|란|에서는|에서|으로|에게|이다|한다|의|은|는|이|가|을|를)$", "", w)
            if len(w_clean) >= 2 and w_clean.lower() not in _STOPWORDS:
                token_counts[w_clean] += 1

    top_keywords = [kw for kw, _ in token_counts.most_common(3)]
    if len(top_keywords) >= 2:
        return " · ".join(top_keywords[:3])[:80]

    return f"문서 덱 {now_date_str}"


def classify_block_pattern(text: str) -> str:
    """Classify a single text block into one of the 5 universal study card patterns."""
    cleaned = _clean_line(text)
    if not cleaned:
        return "definition"

    if _ARROW_PAIR_RE.match(cleaned):
        return "language_pair"

    numbered_matches = _NUMBERED_ITEM_RE.findall(cleaned)
    if len(numbered_matches) >= 2:
        return "numbered_list"

    if _STATUTE_RE.search(cleaned) or _NUMERIC_UNIT_RE.search(cleaned):
        # If it is explicitly a Term: Definition, keep definition unless statute/numeric is dominant
        if _STATUTE_RE.search(cleaned) or not _COLON_DEF_RE.match(cleaned):
            return "statute_numeric"

    if _COLON_DEF_RE.match(cleaned) or _KOREAN_DEF_RE.match(cleaned) or _ENGLISH_DEF_RE.match(cleaned):
        return "definition"

    if _CAUSAL_COMPARE_RE.search(cleaned):
        return "causal_compare"

    if _NUMERIC_UNIT_RE.search(cleaned):
        return "statute_numeric"

    return "definition"


def normalize_card_front_key(front_text: str) -> str:
    """Normalize front text (NFKC + strip cloze wrapper + lowercase + strip punctuation/spaces) for deduplication."""
    norm = unicodedata.normalize("NFKC", front_text or "")
    norm = _CLOZE_EXTRACT_RE.sub(r"\1", norm)
    norm = norm.lower()
    norm = re.sub(r"[\s\W_]+", "", norm, flags=re.UNICODE)
    return norm


def _extract_answer_Verification_tokens(spec: GeneratedCardSpec) -> List[str]:
    """Extract target answer tokens that MUST exist in the source document for grounding."""
    cloze_targets = _CLOZE_EXTRACT_RE.findall(spec.front_text)
    raw_target = " ".join(cloze_targets) if cloze_targets else spec.back_text
    norm_target = unicodedata.normalize("NFKC", raw_target).lower()
    tokens = re.findall(r"[가-힣]{2,}|[a-z0-9]+(?:\.[0-9]+)?", norm_target)
    return [t for t in tokens if t not in _STOPWORDS]


def _is_token_grounded_on_page(
    token: str,
    page_tokens: set[str],
    page_numbers: set[str],
) -> bool:
    """Verify a token against page tokens with strict boundary checks for numbers and ASCII words."""
    for num in re.findall(r"\d+(?:\.\d+)?", token):
        if num not in page_numbers:
            return False
    if re.match(r"^[a-z0-9]", token):
        return token in page_tokens
    # Korean multi-character token: allow inflected particle suffix on the page token (e.g. '심박출량' in '심박출량이')
    return any(pt == token or pt.startswith(token) or token in pt for pt in page_tokens)


def ground_cards(
    cards: Sequence[SourcedCard],
    doc: ExtractedDocument,
) -> Tuple[Tuple[SourcedCard, ...], int]:
    """Verify every card's answer tokens, numbers, and excerpt exist on its cited `source_page` in `doc`."""
    page_texts: Dict[int, List[str]] = {}
    for b in doc.blocks:
        page_texts.setdefault(b.page, []).append(_clean_line(b.text))
    page_corpus: Dict[int, str] = {
        p: unicodedata.normalize("NFKC", " ".join(txts)).lower()
        for p, txts in page_texts.items()
    }
    page_token_sets: Dict[int, set[str]] = {
        p: set(re.findall(r"[가-힣]{2,}|[a-z0-9]+(?:\.[0-9]+)?", text))
        for p, text in page_corpus.items()
    }
    page_number_sets: Dict[int, set[str]] = {
        p: set(re.findall(r"\d+(?:\.\d+)?", text))
        for p, text in page_corpus.items()
    }

    kept: List[SourcedCard] = []
    dropped = 0

    for card in cards:
        page_text = page_corpus.get(card.source_page)
        if not page_text:
            dropped += 1
            continue
        p_tokens = page_token_sets[card.source_page]
        p_numbers = page_number_sets[card.source_page]

        tokens = _extract_answer_Verification_tokens(card.spec)
        if not tokens:
            dropped += 1
            continue

        if not all(_is_token_grounded_on_page(t, p_tokens, p_numbers) for t in tokens):
            dropped += 1
            continue

        if card.source_excerpt:
            norm_excerpt = unicodedata.normalize("NFKC", _clean_line(card.source_excerpt)).lower()
            excerpt_tokens = [
                t
                for t in re.findall(r"[가-힣]{2,}|[a-z0-9]+(?:\.[0-9]+)?", norm_excerpt)
                if t not in _STOPWORDS
            ]
            excerpt_numbers = re.findall(r"\d+(?:\.\d+)?", norm_excerpt)
            if any(num not in p_numbers for num in excerpt_numbers):
                dropped += 1
                continue
            if excerpt_tokens and not all(
                _is_token_grounded_on_page(t, p_tokens, p_numbers) for t in excerpt_tokens
            ):
                dropped += 1
                continue

        kept.append(card)

    return tuple(kept), dropped


def _strip_repeated_headers_footers(blocks: Sequence[DocumentBlock]) -> List[DocumentBlock]:
    """Remove identical header/footer lines that repeat across >= 3 distinct pages."""
    line_pages: Dict[str, set[int]] = {}
    for b in blocks:
        for line in b.text.splitlines():
            norm = _clean_line(line)
            if norm:
                line_pages.setdefault(norm, set()).add(b.page)

    repeated = {line for line, pages in line_pages.items() if len(pages) >= 3}
    if not repeated:
        return list(blocks)

    cleaned_blocks: List[DocumentBlock] = []
    for b in blocks:
        kept_lines = [
            ln for ln in b.text.splitlines() if _clean_line(ln) not in repeated
        ]
        joined = "\n".join(kept_lines).strip()
        if joined:
            cleaned_blocks.append(
                DocumentBlock(
                    kind=b.kind,
                    text=joined,
                    page=b.page,
                    confidence=b.confidence,
                )
            )
    return cleaned_blocks


def _synthesize_cards_from_block(block: DocumentBlock, category: str) -> List[SourcedCard]:
    """Deterministically generate grounded SourcedCards from a single DocumentBlock."""
    text = _clean_line(block.text)
    if len(text) < 8:
        return []

    excerpt = text[:140]
    pattern = classify_block_pattern(text)
    base_tags = ("auto-deck", category, pattern, f"p{block.page}")
    results: List[SourcedCard] = []

    # 1. Language Pair (`A -> B`)
    if pattern == "language_pair":
        m = _ARROW_PAIR_RE.match(text)
        if m:
            src_phrase, dst_phrase = m.group(1).strip(), m.group(2).strip()
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="speaking",
                        front_text=f"🗣️ [어학·표현 인출] {src_phrase}",
                        back_text=dst_phrase,
                        tags=base_tags,
                        rationale=f"p.{block.page} 어학 표현 쌍 자동 추출",
                    ),
                    pattern="language_pair",
                    source_page=block.page,
                    source_excerpt=excerpt,
                )
            )
            return results

    # 2. Numbered List (`1) ... 2) ...` or `① ... ② ...`)
    if pattern == "numbered_list":
        items = [it.strip(" ,.;:") for it in _NUMBERED_ITEM_RE.findall(text) if len(it.strip()) >= 2]
        if len(items) >= 2:
            # Build a multi-cloze card covering up to 3 key items so none of the items are lost
            cloze_parts: List[str] = []
            for idx, item in enumerate(items):
                if idx < 3:
                    cloze_parts.append(f"({idx + 1}) {{{{c{idx + 1}::{item}}}}}")
                else:
                    cloze_parts.append(f"({idx + 1}) {item}")
            header_prefix = text.split("1")[0].split("①")[0].split("(1)")[0].strip(" :：-")
            title_prefix = f"[{header_prefix}] " if len(header_prefix) >= 2 else "[핵심 항목 열거] "
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="cloze",
                        front_text=f"{title_prefix}" + " / ".join(cloze_parts),
                        back_text=f"전체 항목 ({len(items)}개): " + " · ".join(items),
                        tags=base_tags,
                        rationale=f"p.{block.page} 번호 목록 {len(items)}개 항목 열거 Cloze",
                    ),
                    pattern="numbered_list",
                    source_page=block.page,
                    source_excerpt=excerpt,
                )
            )
            return results

    # 3. Statute / Numeric + Unit (`제12조`, `3nm`, `120mmHg`, `30일 이내`)
    if pattern == "statute_numeric":
        stat_m = _STATUTE_RE.search(text)
        num_m = _NUMERIC_UNIT_RE.search(text)
        cloze_text = text
        ordinal = 1
        if stat_m:
            target = stat_m.group(1)
            cloze_text = cloze_text.replace(target, f"{{{{c{ordinal}::{target}::조문}}}}", 1)
            ordinal += 1
        if num_m:
            num_target = num_m.group(1)
            if num_target in cloze_text:
                cloze_text = cloze_text.replace(num_target, f"{{{{c{ordinal}::{num_target}::수치·단위}}}}", 1)
                ordinal += 1
        if ordinal > 1:
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="cloze",
                        front_text=cloze_text,
                        back_text=f"출처 원문 (p.{block.page}): {excerpt}",
                        tags=base_tags,
                        rationale=f"p.{block.page} 조문·핵심 수치/단위 빈칸 Cloze",
                    ),
                    pattern="statute_numeric",
                    source_page=block.page,
                    source_excerpt=excerpt,
                )
            )
            return results

    # 4. Definition (`용어: 설명`, `~란 ~이다`, `is defined as`)
    col_m = _COLON_DEF_RE.match(text)
    if col_m:
        term, desc = col_m.group(1).strip(), col_m.group(2).strip()
        results.append(
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="cloze",
                    front_text=f"{{{{c1::{term}::핵심 개념}}}}: {desc}",
                    back_text=f"{term} — {desc}",
                    tags=base_tags,
                    rationale=f"p.{block.page} 용어 정의 Cloze",
                ),
                pattern="definition",
                source_page=block.page,
                source_excerpt=excerpt,
            )
        )
        return results

    kor_m = _KOREAN_DEF_RE.match(text)
    if kor_m:
        term, desc = kor_m.group(1).strip(), kor_m.group(2).strip()
        results.append(
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="cloze",
                    front_text=f"{{{{c1::{term}::핵심 개념}}}}은(는) {desc}",
                    back_text=f"{term}: {desc}",
                    tags=base_tags,
                    rationale=f"p.{block.page} 국문 개념 정의 Cloze",
                ),
                pattern="definition",
                source_page=block.page,
                source_excerpt=excerpt,
            )
        )
        return results

    eng_m = _ENGLISH_DEF_RE.match(text)
    if eng_m:
        term, desc = eng_m.group(1).strip(), eng_m.group(2).strip()
        results.append(
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="cloze",
                    front_text=f"{{{{c1::{term}::Concept}}}} is defined as {desc}",
                    back_text=f"{term}: {desc}",
                    tags=base_tags,
                    rationale=f"p.{block.page} 영문 개념 정의 Cloze",
                ),
                pattern="definition",
                source_page=block.page,
                source_excerpt=excerpt,
            )
        )
        return results

    # 5. Causal / Comparison (`~때문에`, `~반면`, `→`, `whereas`, `leads to`)
    cc_m = _CAUSAL_COMPARE_RE.search(text)
    if cc_m:
        lhs, connector, rhs = cc_m.group(1).strip(), cc_m.group(2).strip(), cc_m.group(3).strip()
        results.append(
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="basic",
                    front_text=f"❓ [인과·비교 핵심] {lhs} ({connector}) 뒤에 이어지는 핵심 결과·대조 내용은?",
                    back_text=rhs,
                    tags=base_tags,
                    rationale=f"p.{block.page} 인과·비교({connector}) Q&A",
                ),
                pattern="causal_compare",
                source_page=block.page,
                source_excerpt=excerpt,
            )
        )
        return results

    # Fallback for general informative sentence: mask the longest domain noun/keyword
    if block.kind == "heading":
        return []
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,18}|[가-힣]{2,10}", text)
    filtered = [c for c in candidates if c.lower() not in _STOPWORDS]
    if filtered and len(text) >= 18:
        target = max(filtered, key=len)
        cloze_sentence = text.replace(target, f"{{{{c1::{target}::핵심 키워드}}}}", 1)
        results.append(
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="cloze",
                    front_text=cloze_sentence,
                    back_text=f"정답: {target} (p.{block.page})",
                    tags=base_tags,
                    rationale=f"p.{block.page} 핵심 키워드 Cloze",
                ),
                pattern="definition",
                source_page=block.page,
                source_excerpt=excerpt,
            )
        )
    return results


def _select_balanced_cards(cards: Sequence[SourcedCard], max_cards: int) -> List[SourcedCard]:
    """Round-robin selection across pattern types to preserve diversity up to `max_cards`."""
    if len(cards) <= max_cards:
        return list(cards)

    by_pattern: Dict[str, List[SourcedCard]] = {p: [] for p in VALID_PATTERNS}
    for c in cards:
        by_pattern.setdefault(c.pattern, []).append(c)

    selected: List[SourcedCard] = []
    idx = 0
    while len(selected) < max_cards:
        added_in_round = False
        for p in VALID_PATTERNS:
            bucket = by_pattern.get(p, [])
            if idx < len(bucket):
                selected.append(bucket[idx])
                added_in_round = True
                if len(selected) >= max_cards:
                    break
        if not added_in_round:
            break
        idx += 1
    return selected


def build_deck_plan(
    doc: ExtractedDocument,
    user_deck_name: Optional[str] = None,
    max_cards: int = 30,
    min_confidence: float = 0.60,
    min_text_chars: int = 40,
    now_date_str: str = "2026-10-19",
    extra_llm_cards: Sequence[SourcedCard] = (),
    ocr_pages: int = 0,
) -> DeckPlan:
    """Build a verified, grounded DeckPlan from an ExtractedDocument (Fail-Closed on insufficient quality)."""
    max_cards = max(1, min(60, int(max_cards)))
    low_confidence_lines = 0
    unmeasured_confidence_lines = 0
    confident_blocks: List[DocumentBlock] = []

    for b in doc.blocks:
        if b.confidence is None:
            unmeasured_confidence_lines += 1
            confident_blocks.append(b)
        elif b.confidence < min_confidence:
            low_confidence_lines += 1
        else:
            confident_blocks.append(b)

    cleaned_blocks = _strip_repeated_headers_footers(confident_blocks)
    filtered_doc = ExtractedDocument(
        blocks=tuple(cleaned_blocks),
        title_hint=doc.title_hint,
        source_kind=doc.source_kind,
        page_count=doc.page_count,
    )

    category = infer_category(filtered_doc)
    deck_name = infer_deck_name(filtered_doc, user_name=user_deck_name, now_date_str=now_date_str)
    total_chars = sum(len(_clean_line(b.text)) for b in cleaned_blocks)

    if total_chars < min_text_chars:
        return DeckPlan(
            status="BLOCKED",
            error_code="insufficient_text",
            deck_name=deck_name,
            category=category,
            cards=(),
            stats=BuildStats(
                pages=doc.page_count,
                ocr_pages=ocr_pages,
                low_confidence_lines=low_confidence_lines,
                unmeasured_confidence_lines=unmeasured_confidence_lines,
                dropped_ungrounded=0,
                duplicates=0,
                total_chars=total_chars,
            ),
        )

    raw_candidates: List[SourcedCard] = []
    for block in cleaned_blocks:
        # Split multi-line paragraphs into logical lines if they contain separate definitions/pairs
        lines = [ln.strip() for ln in block.text.splitlines() if ln.strip()]
        if len(lines) > 1 and any(
            _COLON_DEF_RE.match(ln) or _ARROW_PAIR_RE.match(ln) for ln in lines
        ):
            for ln in lines:
                sub_block = DocumentBlock(
                    kind=block.kind,
                    text=ln,
                    page=block.page,
                    confidence=block.confidence,
                )
                raw_candidates.extend(_synthesize_cards_from_block(sub_block, category))
        else:
            raw_candidates.extend(_synthesize_cards_from_block(block, category))

    if extra_llm_cards:
        raw_candidates.extend(extra_llm_cards)

    grounded_cards, dropped_ungrounded = ground_cards(raw_candidates, filtered_doc)

    # Deduplicate by normalized front text
    seen_keys: set[str] = set()
    deduped_cards: List[SourcedCard] = []
    duplicates = 0
    for c in grounded_cards:
        key = normalize_card_front_key(c.spec.front_text)
        if not key or key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(key)
        deduped_cards.append(c)

    final_cards = _select_balanced_cards(deduped_cards, max_cards=max_cards)

    if not final_cards:
        return DeckPlan(
            status="BLOCKED",
            error_code="no_cards",
            deck_name=deck_name,
            category=category,
            cards=(),
            stats=BuildStats(
                pages=doc.page_count,
                ocr_pages=ocr_pages,
                low_confidence_lines=low_confidence_lines,
                unmeasured_confidence_lines=unmeasured_confidence_lines,
                dropped_ungrounded=dropped_ungrounded,
                duplicates=duplicates,
                total_chars=total_chars,
            ),
        )

    return DeckPlan(
        status="OK",
        error_code=None,
        deck_name=deck_name,
        category=category,
        cards=tuple(final_cards),
        stats=BuildStats(
            pages=doc.page_count,
            ocr_pages=ocr_pages,
            low_confidence_lines=low_confidence_lines,
            unmeasured_confidence_lines=unmeasured_confidence_lines,
            dropped_ungrounded=dropped_ungrounded,
            duplicates=duplicates,
            total_chars=total_chars,
        ),
    )
