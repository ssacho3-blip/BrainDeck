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

_GENERIC_SECTION_LABELS: frozenset[str] = frozenset(
    {
        "특징",
        "배경",
        "개요",
        "목적",
        "의의",
        "종류",
        "장점",
        "단점",
        "장단점",
        "원인",
        "결과",
        "원인과 결과",
        "정의",
        "개념",
        "요약",
        "결론",
        "서론",
        "본론",
        "구분",
        "내용",
        "핵심",
        "핵심 내용",
        "정리",
        "핵심 정리",
        "예시",
        "사례",
        "비교",
        "차이",
        "차이점",
        "공통점",
        "효과",
        "기대 효과",
        "영향",
        "한계",
        "문제점",
        "해결책",
        "대책",
        "방안",
        "절차",
        "과정",
        "순서",
        "방법",
        "원리",
        "구조",
        "기능",
        "역할",
        "조건",
        "요건",
        "성립 요건",
        "주의",
        "참고",
        "비고",
        "보충",
        "심화",
        "출처",
        "기타",
        "도입",
        "전개",
        "정착",
        "배경과 원인",
        "주요 내용",
        "추진 배경",
        "발생 원인",
    }
)

_TOC_OUTLINE_SECTIONS: frozenset[str] = frozenset(
    {
        "목차",
        "차례",
        "서론",
        "본론",
        "결론",
        "개요",
        "배경",
        "연구 배경",
        "목적",
        "연구 목적",
        "의의",
        "필요성",
        "연구 방법",
        "결과",
        "고찰",
        "결론 및 제언",
        "요약",
        "참고문헌",
        "참고 문헌",
        "부록",
        "머리말",
        "서문",
        "맺음말",
        "문제 제기",
        "이론적 배경",
        "선행 연구",
        "기대 효과",
        "현황",
        "과제",
        "전망",
        "찾아보기",
        "판권",
        "저작권",
        "introduction",
        "background",
        "overview",
        "methodology",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "summary",
        "references",
        "bibliography",
        "appendix",
        "table of contents",
        "contents",
        "index",
        "preface",
    }
)

_TOC_EXACT_TITLE_RE = re.compile(
    r"^[\[<【《(]*\s*(?:목\s*차|차\s*례|table\s+of\s+contents|contents|index|찾아보기|참고\s*문헌|references|bibliography|부\s*록|appendix|머리말|서문|일러두기|판권|저작권|단원\s*요약|학습\s*목표|핵심\s*정리|생각해보기|연습\s*문제|확인\s*문제|출제\s*포인트)\s*[\]>】》)]*$",
    re.IGNORECASE,
)
_TOC_PREFIX_RE = re.compile(
    r"^(?:목\s*차|차\s*례|table\s+of\s+contents|contents)\s*(?::|：|-|—|\d|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])",
    re.IGNORECASE,
)
_TOC_LEADER_PAGE_RE = re.compile(
    r"(?:\.{2,}|…+|·{2,}|•{2,}|-{2,}|─{2,}|_{2,}|\s{3,})\s*(?:p\.?\s*)?\d{1,4}\s*(?:쪽|페이지|p)?$",
    re.IGNORECASE,
)
_TOC_NUMBERED_PAGE_END_RE = re.compile(
    r"^(?:제\s*\d+\s*[장절편부관과단원]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+\.?|\d+(?:\.\d+)*\.?|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩])\s+[^\n]{1,55}?\s+(?:p\.?\s*\d{1,4}|\d{1,4}\s*(?:쪽|페이지|p))$",
    re.IGNORECASE,
)
_STRUCTURAL_CHAPTER_HEADER_RE = re.compile(
    r"^(?:제\s*\d+\s*(?:장|절|편|부|관|과|단원)|chapter\s+\d+|part\s+[0-9ivx]+|unit\s+\d+|lesson\s+\d+|section\s+\d+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.)(?:\s|$|:)",
    re.IGNORECASE,
)
_LIST_PREFIX_STRIP_RE = re.compile(
    r"^(?:[\[<【《(]?\s*(?:제\s*\d+\s*[장절편부관과단원]|[①②③④⑤⑥⑦⑧⑨⑩]|(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+|\d+(?:\.\d+)*|[가-하]|[A-Za-z])\s*[\]>】》).:：\-])\s*)+"
)
_FACTUAL_PREDICATE_RE = re.compile(
    r"(?:이다|입니다|한다|된다|있다|없다|말한다|뜻한다|의미한다|가리킨다|정의된다|구성된다|분류된다|나뉜다|발생한다|일어난다|작용한다|억제한다|촉진한다|유발한다|소멸한다|규정한다|보장한다|제한한다|위반한다|합성하는|전환하는|교환하는|수행하는|is\s+defined\s+as|refers\s+to|means|leads\s+to|results\s+in|causes|consists\s+of|->|→)",
    re.IGNORECASE,
)


def _has_factual_predicate(text: str) -> bool:
    return bool(_FACTUAL_PREDICATE_RE.search(text or ""))


def _normalize_label_core(raw_label: str) -> str:
    cleaned = _clean_line(raw_label).strip(" :：-–—[]<>【】《》()\"'")
    stripped = _LIST_PREFIX_STRIP_RE.sub("", cleaned).strip(" :：-–—[]<>【】《》()\"'")
    return stripped or cleaned


def is_generic_section_label(raw_label: str) -> bool:
    """Return True if `raw_label` is a generic structural label (e.g., '특징', '1. 배경', '(2) 의의') rather than a domain concept."""
    raw_clean = _clean_line(raw_label)
    if not raw_clean or len(raw_clean) > 28:
        return False
    core = _normalize_label_core(raw_clean).lower()
    if not core:
        return True
    if core in _GENERIC_SECTION_LABELS or core in _TOC_OUTLINE_SECTIONS:
        return True
    if re.match(
        r"^(?:제?\s*\d+\s*[장절편부관과단원]|파트\s*\d+|단계\s*\d+|유형\s*\d+|특징\s*\d+|원인\s*\d+|목적\s*\d+|내용\s*\d+|배경\s*\d+|의의\s*\d+)$",
        core,
    ):
        return True
    return False


def is_toc_or_structural_heading(text: str, kind: str = "paragraph") -> bool:
    """Return True if `text` is a Table of Contents line, chapter/section title, or non-propositional heading."""
    cleaned = _clean_line(text)
    if len(cleaned) < 2:
        return True
    stripped = cleaned.lstrip("#*•- ").strip()
    if not stripped:
        return True

    # 1. Explicit TOC / Front-matter / Meta-header title or prefix
    if _TOC_EXACT_TITLE_RE.match(stripped) or _TOC_PREFIX_RE.match(stripped):
        return True

    # 2. Dotted/dashed leader line or outline line ending with a page number
    if _TOC_LEADER_PAGE_RE.search(stripped) or _TOC_NUMBERED_PAGE_END_RE.match(stripped):
        return True

    # 3. Standalone generic section label without content (e.g. "1. 배경", "Ⅱ. 본론", "[특징]")
    if ":" not in stripped and "：" not in stripped and "->" not in stripped and "→" not in stripped:
        if is_generic_section_label(stripped):
            return True

    # 4. Chapter / Section / Unit structural header without a factual proposition
    if _STRUCTURAL_CHAPTER_HEADER_RE.match(stripped):
        if not _has_factual_predicate(stripped):
            return True
        # Even if colon is present, e.g. "제1장: 총칙" or "Chapter 1: Overview"
        if ":" in stripped or "：" in stripped:
            rhs = re.split(r"[:：]", stripped, maxsplit=1)[-1].strip()
            if len(rhs) < 12 and not _has_factual_predicate(rhs):
                return True

    # 5. Numbered outline where items are generic TOC section titles (e.g. "1. 서론 2. 본론 3. 결론")
    numbered_items = [it.strip(" ,.;:") for it in _NUMBERED_ITEM_RE.findall(stripped) if len(it.strip()) >= 2]
    if len(numbered_items) >= 2:
        toc_item_hits = sum(
            1
            for it in numbered_items
            if _normalize_label_core(it).lower() in _TOC_OUTLINE_SECTIONS
            or _normalize_label_core(it).lower() in _GENERIC_SECTION_LABELS
            or bool(_TOC_LEADER_PAGE_RE.search(it))
        )
        if toc_item_hits >= 2 and toc_item_hits * 2 >= len(numbered_items):
            return True

    # 6. Explicit heading blocks that do not contain a complete factual proposition
    if kind == "heading":
        if not _has_factual_predicate(stripped):
            return True
        if not (
            _STATUTE_RE.search(stripped)
            or _NUMERIC_UNIT_RE.search(stripped)
            or _CAUSAL_COMPARE_RE.search(stripped)
        ):
            return True

    # 7. Short numbered section header without predicate/colon/arrow (e.g. "1. 연구의 필요성")
    if (
        len(numbered_items) < 2
        and len(stripped) <= 28
        and not _has_factual_predicate(stripped)
        and ":" not in stripped
        and "：" not in stripped
        and "->" not in stripped
        and "→" not in stripped
    ):
        if re.match(
            r"^(?:\d+(?:\.\d+)*\.?|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.?|[가-하]\.)\s+\S+",
            stripped,
        ):
            return True

    return False


def _mask_term_in_desc(desc: str, term: str) -> str:
    """Mask any direct occurrence of `term` (or its base headword) in `desc` to prevent front-side spoilers."""
    safe = (desc or "").strip()
    clean_term = (term or "").strip()
    if not safe or not clean_term:
        return safe
    base_term = clean_term.split("(")[0].strip()
    candidates = [clean_term]
    if len(base_term) >= 2 and base_term != clean_term:
        candidates.append(base_term)
    for m in re.finditer(r"\(([^()]{2,30})\)", clean_term):
        inner = m.group(1).strip()
        if len(inner) >= 2:
            candidates.append(inner)
    for cand in sorted(set(candidates), key=len, reverse=True):
        if len(cand) >= 2 and cand in safe:
            safe = safe.replace(cand, "[ ___ ]")
    return safe


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
            if (
                len(cleaned) >= 2
                and not _TOC_EXACT_TITLE_RE.match(cleaned)
                and not _TOC_PREFIX_RE.match(cleaned)
            ):
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
    raw_target = " ".join(cloze_targets) if cloze_targets else spec.back_text.split("💡 해설:")[0]
    norm_target = unicodedata.normalize("NFKC", raw_target).lower()
    tokens = re.findall(r"[가-힣]{2,}|[a-z0-9]+(?:\.[0-9]+)?", norm_target)
    return [t for t in tokens if t not in _STOPWORDS and t not in ("해설", "정답")]


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


def _extract_noun_candidates(text: str) -> List[str]:
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,18}|[가-힣]{2,12}", text or "")
    cleaned: List[str] = []
    for tok in raw_tokens:
        tl = tok.lower()
        if tl in _STOPWORDS:
            continue
        if re.match(r"^[가-힣]+$", tok):
            stem = re.sub(
                r"(?:이란|란|에서는|에서|으로|에게|부터|까지|처럼|보다|라고|하고|이며|이고|이나| 또는|의|은|는|이|가|을|를|에|로|과|와|도|만)$",
                "",
                tok,
            )
            if len(stem) >= 2 and stem in text and stem.lower() not in _STOPWORDS:
                tok = stem
        if tok.lower() in _STOPWORDS or is_generic_section_label(tok):
            continue
        if tok not in cleaned:
            cleaned.append(tok)
    return cleaned


def _select_semantic_hinge_token(
    candidates: Sequence[str],
    text: str,
    category: str,
) -> str:
    """Select the most semantically pivotal domain token rather than naively picking the longest word."""
    cat_keywords = {kw.lower() for kw in _CATEGORY_KEYWORDS.get(category, ())}
    all_domain_kw = {kw.lower() for kws in _CATEGORY_KEYWORDS.values() for kw in kws}

    def _score(tok: str) -> Tuple[int, int, int, int]:
        tl = tok.lower()
        in_cat = 1 if any(kw in tl or tl in kw for kw in cat_keywords) else 0
        in_any_dom = 1 if any(kw in tl or tl in kw for kw in all_domain_kw) else 0
        is_tech_or_num = 1 if (any(ch.isdigit() for ch in tok) or any("A" <= ch <= "Z" for ch in tok)) else 0
        # Penalize generic verbal/modifier endings in Korean
        generic_penalty = (
            -4
            if tok.endswith(
                (
                    "하는",
                    "되는",
                    "있는",
                    "없는",
                    "통한",
                    "대한",
                    "의한",
                    "되었다",
                    "하였다",
                    "이다",
                    "한다",
                    "된다",
                    "있다",
                    "없다",
                    "빠르고",
                    "적다",
                    "많다",
                )
            )
            else 0
        )
        return (in_cat * 3 + in_any_dom * 2 + is_tech_or_num * 2 + generic_penalty, is_tech_or_num, in_any_dom, len(tok))

    return max(candidates, key=_score)


def _synthesize_content_keyword_cards(
    content_text: str,
    page: int,
    excerpt: str,
    category: str,
    base_tags: Tuple[str, ...],
    difficulty_level: str,
    context_prefix: str = "",
) -> List[SourcedCard]:
    """Synthesize a content-first card from a proposition sentence by masking its pivotal domain keyword."""
    filtered = _extract_noun_candidates(content_text)
    if not filtered or len(content_text) < 10:
        return []
    target = _select_semantic_hinge_token(filtered, content_text, category)
    diff = (difficulty_level or "standard").strip().lower()
    prefix = f"{context_prefix} " if context_prefix else ""
    masked = content_text.replace(target, "[ ___ ]", 1)
    cloze_sentence = content_text.replace(target, f"{{{{c1::{target}::핵심 키워드}}}}", 1)
    concise_back = f"{target}\n\n💡 해설: {prefix}{content_text}".strip()

    if diff == "lv1":
        return [
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="basic",
                    front_text=f"🌱 [Lv.1 기초 개념] {prefix}{masked} — 빈칸에 들어갈 핵심 용어는?",
                    back_text=concise_back,
                    tags=base_tags + ("lv1",),
                    rationale=f"p.{page} Lv.1 내용 기반 핵심어 인출",
                ),
                pattern="definition",
                source_page=page,
                source_excerpt=excerpt,
            )
        ]
    if diff == "lv3":
        return [
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="basic",
                    front_text=f"🔥 [Lv.3 심화 인출] 다음 내용의 빈칸에 들어갈 핵심 개념어를 쓰시오.\n\"{prefix}{masked}\"",
                    back_text=concise_back,
                    tags=base_tags + ("lv3",),
                    rationale=f"p.{page} Lv.3 내용 기반 핵심어 서술 인출",
                ),
                pattern="definition",
                source_page=page,
                source_excerpt=excerpt,
            )
        ]
    cards = [
        SourcedCard(
            spec=GeneratedCardSpec(
                note_type="cloze",
                front_text=f"{prefix}{cloze_sentence}",
                back_text=concise_back,
                tags=base_tags,
                rationale=f"p.{page} 핵심 키워드 Cloze",
            ),
            pattern="definition",
            source_page=page,
            source_excerpt=excerpt,
        )
    ]
    if diff in ("mixed", "all"):
        cards.append(
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="basic",
                    front_text=f"🔥 [Lv.3 심화 인출] 다음 내용의 빈칸에 들어갈 핵심 개념어를 쓰시오.\n\"{prefix}{masked}\"",
                    back_text=concise_back,
                    tags=base_tags + ("lv3",),
                    rationale=f"p.{page} Lv.3 내용 기반 핵심어 인출",
                ),
                pattern="definition",
                source_page=page,
                source_excerpt=excerpt,
            )
        )
    return cards


def _synthesize_cards_from_block(
    block: DocumentBlock,
    category: str,
    difficulty_level: str = "standard",
    heading_context: Optional[str] = None,
) -> List[SourcedCard]:
    """Deterministically generate grounded SourcedCards from a single DocumentBlock.

    Supports difficulty stratification (`standard`, `lv1`, `lv2`, `lv3`, `mixed`).
    Enforces:
    1) Top-level TOC / structural heading rejection (`is_toc_or_structural_heading`).
    2) Generic section label unwrapping (`특징:`, `1. 배경:`, `의의:` -> content becomes question).
    3) Content-as-question inversion for Basic cards (`safe_desc` on front, concise `term` on back).
    """
    text = _clean_line(block.text)
    if len(text) < 8:
        return []
    if is_toc_or_structural_heading(text, block.kind):
        return []

    diff = (difficulty_level or "standard").strip().lower()
    excerpt = text[:140]
    pattern = classify_block_pattern(text)
    base_tags = ("auto-deck", category, pattern, f"p{block.page}")
    results: List[SourcedCard] = []

    # 1. Language Pair (`A -> B`)
    if pattern == "language_pair":
        m = _ARROW_PAIR_RE.match(text)
        if m:
            src_phrase, dst_phrase = m.group(1).strip(), m.group(2).strip()
            if diff == "lv1":
                results.append(
                    SourcedCard(
                        spec=GeneratedCardSpec(
                            note_type="basic",
                            front_text=f"🌱 [Lv.1 표현 의미] {dst_phrase}",
                            back_text=src_phrase,
                            tags=base_tags + ("lv1",),
                            rationale=f"p.{block.page} Lv.1 어학 표현 의미 인지",
                        ),
                        pattern="language_pair",
                        source_page=block.page,
                        source_excerpt=excerpt,
                    )
                )
            elif diff == "lv3":
                first_ch = dst_phrase[0] if dst_phrase else ""
                results.append(
                    SourcedCard(
                        spec=GeneratedCardSpec(
                            note_type="speaking",
                            front_text=f"🔥 [Lv.3 역방향 발화·작문] '{src_phrase}' (첫 글자 '{first_ch}', 총 {len(dst_phrase)}자)",
                            back_text=dst_phrase,
                            tags=base_tags + ("lv3",),
                            rationale=f"p.{block.page} Lv.3 어학 역방향 완전 인출",
                        ),
                        pattern="language_pair",
                        source_page=block.page,
                        source_excerpt=excerpt,
                    )
                )
            else:
                results.append(
                    SourcedCard(
                        spec=GeneratedCardSpec(
                            note_type="speaking",
                            front_text=f"🗣️ [어학·표현] {src_phrase}",
                            back_text=dst_phrase,
                            tags=base_tags,
                            rationale=f"p.{block.page} 어학 표현 쌍 자동 추출",
                        ),
                        pattern="language_pair",
                        source_page=block.page,
                        source_excerpt=excerpt,
                    )
                )
                if diff in ("mixed", "all"):
                    results.append(
                        SourcedCard(
                            spec=GeneratedCardSpec(
                                note_type="basic",
                                front_text=f"🌱 [Lv.1 역방향 확인] {dst_phrase}",
                                back_text=src_phrase,
                                tags=base_tags + ("lv1",),
                                rationale=f"p.{block.page} 어학 표현 양방향 교차 카드",
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
            max_blanks = 1 if diff == "lv1" else (min(len(items), 4) if diff == "lv3" else 3)
            cloze_parts: List[str] = []
            for idx, item in enumerate(items):
                if idx < max_blanks:
                    cloze_parts.append(f"({idx + 1}) {{{{c{idx + 1}::{item}}}}}")
                else:
                    cloze_parts.append(f"({idx + 1}) {item}")
            header_prefix = text.split("1")[0].split("①")[0].split("(1)")[0].strip(" :：-")
            if is_generic_section_label(header_prefix) and heading_context:
                title_prefix = f"[{heading_context} · {_normalize_label_core(header_prefix)}] "
            elif len(header_prefix) >= 2:
                title_prefix = f"[{header_prefix}] "
            elif heading_context:
                title_prefix = f"[{heading_context}] "
            else:
                title_prefix = "[핵심 항목] "
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="cloze",
                        front_text=f"{title_prefix}" + " / ".join(cloze_parts),
                        back_text=" · ".join(items),
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
        extracted_targets: List[str] = []
        if stat_m:
            target = stat_m.group(1)
            cloze_text = cloze_text.replace(target, f"{{{{c{ordinal}::{target}::조문}}}}", 1)
            extracted_targets.append(target)
            ordinal += 1
        if num_m:
            num_target = num_m.group(1)
            if num_target in cloze_text:
                cloze_text = cloze_text.replace(num_target, f"{{{{c{ordinal}::{num_target}::수치·단위}}}}", 1)
                extracted_targets.append(num_target)
                ordinal += 1
        if ordinal > 1:
            ans_head = " · ".join(extracted_targets)
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="cloze",
                        front_text=cloze_text,
                        back_text=f"{ans_head}\n\n💡 해설: {excerpt}",
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
        if is_generic_section_label(term):
            label_core = _normalize_label_core(term)
            ctx_badge = f"[{heading_context} · {label_core}]" if heading_context else f"[{label_core}]"
            return _synthesize_content_keyword_cards(
                content_text=desc,
                page=block.page,
                excerpt=excerpt,
                category=category,
                base_tags=base_tags,
                difficulty_level=diff,
                context_prefix=ctx_badge,
            )
        safe_desc = _mask_term_in_desc(desc, term)
        concise_back = f"{term}\n\n💡 해설: {desc}"
        c_lv1 = SourcedCard(
            spec=GeneratedCardSpec(
                note_type="basic",
                front_text=f"🌱 [Lv.1 개념 확인] {safe_desc}",
                back_text=concise_back,
                tags=base_tags + ("lv1", "diff_lv1"),
                rationale=f"p.{block.page} Lv.1 내용 → 핵심 용어 인출",
            ),
            pattern="definition",
            source_page=block.page,
            source_excerpt=excerpt,
        )
        c_lv2 = SourcedCard(
            spec=GeneratedCardSpec(
                note_type="cloze",
                front_text=f"{{{{c1::{term}::핵심 개념}}}}: {safe_desc}",
                back_text=concise_back,
                tags=base_tags + ("lv2", "diff_lv2") if diff in ("lv2", "mixed", "all") else base_tags,
                rationale=f"p.{block.page} 용어 정의 Cloze",
            ),
            pattern="definition",
            source_page=block.page,
            source_excerpt=excerpt,
        )
        c_lv3 = SourcedCard(
            spec=GeneratedCardSpec(
                note_type="basic",
                front_text=f"🔥 [Lv.3 용어 인출] {safe_desc}",
                back_text=concise_back,
                tags=base_tags + ("lv3", "diff_lv3"),
                rationale=f"p.{block.page} Lv.3 정의 → 용어 역방향 인출",
            ),
            pattern="definition",
            source_page=block.page,
            source_excerpt=excerpt,
        )
        if diff == "lv1":
            results.append(c_lv1)
        elif diff == "lv3":
            results.append(c_lv3)
        elif diff in ("mixed", "all"):
            results.extend([c_lv1, c_lv2, c_lv3])
        else:
            results.append(c_lv2)
        return results

    kor_m = _KOREAN_DEF_RE.match(text)
    if kor_m:
        term, desc = kor_m.group(1).strip(), kor_m.group(2).strip()
        if is_generic_section_label(term):
            label_core = _normalize_label_core(term)
            ctx_badge = f"[{heading_context} · {label_core}]" if heading_context else f"[{label_core}]"
            return _synthesize_content_keyword_cards(
                content_text=desc,
                page=block.page,
                excerpt=excerpt,
                category=category,
                base_tags=base_tags,
                difficulty_level=diff,
                context_prefix=ctx_badge,
            )
        safe_desc = _mask_term_in_desc(desc, term)
        concise_back = f"{term}\n\n💡 해설: {desc}"
        if diff == "lv1":
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="basic",
                        front_text=f"🌱 [Lv.1 개념 확인] {safe_desc}",
                        back_text=concise_back,
                        tags=base_tags + ("lv1", "diff_lv1"),
                        rationale=f"p.{block.page} Lv.1 국문 내용 → 개념 인출",
                    ),
                    pattern="definition",
                    source_page=block.page,
                    source_excerpt=excerpt,
                )
            )
        elif diff == "lv3":
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="basic",
                        front_text=f"🔥 [Lv.3 용어 인출] {safe_desc}",
                        back_text=concise_back,
                        tags=base_tags + ("lv3", "diff_lv3"),
                        rationale=f"p.{block.page} Lv.3 국문 개념 역방향 인출",
                    ),
                    pattern="definition",
                    source_page=block.page,
                    source_excerpt=excerpt,
                )
            )
        else:
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="cloze",
                        front_text=f"{{{{c1::{term}::핵심 개념}}}}은(는) {safe_desc}",
                        back_text=concise_back,
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
        if is_generic_section_label(term):
            return _synthesize_content_keyword_cards(
                content_text=desc,
                page=block.page,
                excerpt=excerpt,
                category=category,
                base_tags=base_tags,
                difficulty_level=diff,
                context_prefix=f"[{_normalize_label_core(term)}]",
            )
        safe_desc = _mask_term_in_desc(desc, term)
        results.append(
            SourcedCard(
                spec=GeneratedCardSpec(
                    note_type="cloze",
                    front_text=f"{{{{c1::{term}::Concept}}}} is defined as {safe_desc}",
                    back_text=f"{term}\n\n💡 해설: {desc}",
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
        if diff == "lv3":
            results.append(
                SourcedCard(
                    spec=GeneratedCardSpec(
                        note_type="basic",
                        front_text=f"🔥 [Lv.3 심화 역인과 추론] '{rhs}' 결과가 나타나거나 대조되는 선행 조건·원인({connector} 앞 내용)은?",
                        back_text=lhs,
                        tags=base_tags + ("lv3",),
                        rationale=f"p.{block.page} Lv.3 역방향 인과·비교 추론",
                    ),
                    pattern="causal_compare",
                    source_page=block.page,
                    source_excerpt=excerpt,
                )
            )
        else:
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

    # Fallback for general informative sentence: mask the semantically pivotal domain noun/keyword
    if len(text) >= 18:
        ctx_prefix = f"[{heading_context}]" if heading_context else ""
        return _synthesize_content_keyword_cards(
            content_text=text,
            page=block.page,
            excerpt=excerpt,
            category=category,
            base_tags=base_tags,
            difficulty_level=diff,
            context_prefix=ctx_prefix,
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
    difficulty_level: str = "standard",
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
    active_heading_topic: str = ""

    def _update_heading_topic(candidate_line: str) -> None:
        nonlocal active_heading_topic
        cleaned_h = _clean_line(candidate_line).lstrip("#*•- ").strip()
        if not cleaned_h:
            return
        if (
            _TOC_EXACT_TITLE_RE.match(cleaned_h)
            or _TOC_PREFIX_RE.match(cleaned_h)
            or _TOC_LEADER_PAGE_RE.search(cleaned_h)
            or _TOC_NUMBERED_PAGE_END_RE.match(cleaned_h)
        ):
            return
        topic = re.sub(r"^(?:#{1,6}\s*)", "", cleaned_h).strip(" []<>《》「」『』")
        if 2 <= len(topic) <= 45 and not is_generic_section_label(topic):
            active_heading_topic = topic

    for block in cleaned_blocks:
        if block.kind == "heading" or is_toc_or_structural_heading(block.text, block.kind):
            _update_heading_topic(block.text)
        # Split multi-line paragraphs into logical lines if they contain separate definitions/pairs or headings/TOC lines
        lines = [ln.strip() for ln in block.text.splitlines() if ln.strip()]
        if len(lines) > 1 and any(
            _COLON_DEF_RE.match(ln)
            or _ARROW_PAIR_RE.match(ln)
            or is_toc_or_structural_heading(ln, "paragraph")
            for ln in lines
        ):
            for ln in lines:
                if is_toc_or_structural_heading(ln, "paragraph"):
                    _update_heading_topic(ln)
                    continue
                sub_block = DocumentBlock(
                    kind="paragraph" if block.kind == "heading" else block.kind,
                    text=ln,
                    page=block.page,
                    confidence=block.confidence,
                )
                raw_candidates.extend(
                    _synthesize_cards_from_block(
                        sub_block,
                        category,
                        difficulty_level=difficulty_level,
                        heading_context=active_heading_topic,
                    )
                )
        else:
            raw_candidates.extend(
                _synthesize_cards_from_block(
                    block,
                    category,
                    difficulty_level=difficulty_level,
                    heading_context=active_heading_topic,
                )
            )

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
