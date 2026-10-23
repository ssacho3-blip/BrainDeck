package com.ankistudio.domain.deck

import java.text.Normalizer
import kotlin.math.max
import kotlin.math.min

/**
 * Pure Kotlin Universal Document & Photo -> Auto-Deck Builder.
 * 1:1 behavioral port of `src/anki_studio/domain/document_deck_builder.py`.
 * Strictly zero `android.*` imports — verifiable on standard JVM.
 */
object DocumentDeckBuilder {

    val VALID_CATEGORIES = listOf("language", "law", "medical", "engineering", "exam", "general")
    val VALID_PATTERNS = listOf(
        "definition",
        "numbered_list",
        "causal_compare",
        "statute_numeric",
        "language_pair"
    )

    data class DocumentBlock(
        val kind: String,
        val text: String,
        val page: Int = 1,
        val confidence: Double? = null
    )

    data class ExtractedDocument(
        val blocks: List<DocumentBlock>,
        val titleHint: String? = null,
        val sourceKind: String = "pdf",
        val pageCount: Int = 1
    )

    data class GeneratedCardSpec(
        val noteType: String,
        val frontText: String,
        val backText: String,
        val tags: List<String>,
        val rationale: String
    )

    data class SourcedCard(
        val spec: GeneratedCardSpec,
        val pattern: String,
        val sourcePage: Int,
        val sourceExcerpt: String
    )

    data class BuildStats(
        val pages: Int,
        val ocrPages: Int,
        val lowConfidenceLines: Int,
        val unmeasuredConfidenceLines: Int,
        val droppedUngrounded: Int,
        val duplicates: Int,
        val totalChars: Int
    )

    data class DeckPlan(
        val status: String, // "OK" | "BLOCKED"
        val errorCode: String?,
        val deckName: String,
        val category: String,
        val cards: List<SourcedCard>,
        val stats: BuildStats
    )

    private val CATEGORY_KEYWORDS: Map<String, List<String>> = mapOf(
        "law" to listOf(
            "제1조", "제2조", "제3조", "제1항", "판례", "대법원", "민법", "형법", "헌법",
            "행정법", "소멸시효", "불법행위", "선관주의", "법률", "조문", "청구권"
        ),
        "medical" to listOf(
            "환자", "증상", "진단", "치료", "투여", "해부", "생리", "약리", "항생제",
            "혈압", "mmhg", "심근", "신경", "세포", "호르몬", "증후군", "병리"
        ),
        "engineering" to listOf(
            "트랜지스터", "반도체", "알고리즘", "프로토콜", "아키텍처", "데이터베이스", "트랜잭션",
            "네트워크", "커널", "컴파일러", "메모리", "전압", "공정", "회로", "finfet", "gaa", "euv", "latency"
        ),
        "language" to listOf(
            "숙어", "문법", "발음", "예문", "뜻", "어휘", "회화",
            "idiom", "phrasal", "vocabulary", "grammar", "follow up", "rain check"
        ),
        "exam" to listOf(
            "기출", "출제", "시험", "자격증", "암기", "요약", "핵심", "오답", "단원", "특징", "장단점"
        )
    )

    private val STOPWORDS = setOf(
        "그리고", "그러나", "하지만", "따라서", "경우", "통해", "대한", "위한", "있는", "하는", "되는",
        "이다", "있다", "한다", "에서", "으로", "에게",
        "the", "and", "for", "that", "with", "from", "this", "are", "was", "were", "have", "has"
    )

    private val CLOZE_EXTRACT_RE = Regex("""\{\{c\d+::(.*?)(?:::.*?)?\}\}""", RegexOption.DOT_MATCHES_ALL)
    private val STATUTE_RE = Regex("""(제\s*\d+\s*조(?:\s*의\s*\d+)?|제\s*\d+\s*항)""")
    private val NUMERIC_UNIT_RE = Regex(
        """(?<![0-9A-Za-z])(\d+(?:\.\d+)?\s*(?:nm|um|mm|cm|km|mg|kg|ml|mmHg|Hz|kHz|MHz|GHz|V|mV|W|kW|%|배|일\s*이내|년\s*이하|년\s*이상|년간|개월|세\s*이상|시간))""",
        RegexOption.IGNORE_CASE
    )
    private val NUMBERED_ITEM_RE = Regex(
        """(?:^|\s)(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(\d+\)|\d+\)|\d+\.)\s*(.+?)(?=(?:\s+(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(\d+\)|\d+\)|\d+\.)\s)|$)"""
    )
    private val ARROW_PAIR_RE = Regex("""^(.{3,100}?)\s*(?:->|=>|↔|⇄)\s*(.{3,160})$""")
    private val COLON_DEF_RE = Regex("""^([^\n:：\-–—]{2,55}?)\s*(?::|：|\s-\s|\s–\s|\s—\s)\s*(.{8,300})$""")
    private val KOREAN_DEF_RE = Regex(
        """^([가-힣A-Za-z0-9\s()·\-/]{2,45}?)(?:이란|란|은|는)\s+(.{10,260}?(?:이다|말한다|의미한다|뜻한다|가리킨다|정의된다)\.?)$"""
    )
    private val ENGLISH_DEF_RE = Regex(
        """^([A-Za-z0-9\s()\-/]{2,50}?)\s+(?:is defined as|refers to|means)\s+(.{10,260})$""",
        RegexOption.IGNORE_CASE
    )
    private val CAUSAL_COMPARE_RE = Regex(
        """(.{6,160}?)\s*(때문에|반면에?|와\s*달리|과\s*달리|에\s*비해|→|whereas|because|leads\s+to|results\s+in|compared\s+to)\s*(.{6,200})""",
        RegexOption.IGNORE_CASE
    )
    private val TOKEN_RE = Regex("""[가-힣]{2,}|[a-z0-9]+(?:\.[0-9]+)?""")
    private val FALLBACK_NOUN_RE = Regex("""[A-Za-z][A-Za-z0-9\-]{3,18}|[가-힣]{2,10}""")

    private val GENERIC_SECTION_LABELS = setOf(
        "특징", "배경", "개요", "목적", "의의", "종류", "장점", "단점", "장단점",
        "원인", "결과", "원인과 결과", "정의", "개념", "요약", "결론", "서론", "본론",
        "구분", "내용", "핵심", "핵심 내용", "정리", "핵심 정리", "예시", "사례",
        "비교", "차이", "차이점", "공통점", "효과", "기대 효과", "영향", "한계",
        "문제점", "해결책", "대책", "방안", "절차", "과정", "순서", "방법", "원리",
        "구조", "기능", "역할", "조건", "요건", "성립 요건", "주의", "참고", "비고",
        "보충", "심화", "출처", "기타", "도입", "전개", "정착", "배경과 원인",
        "주요 내용", "추진 배경", "발생 원인"
    )

    private val TOC_OUTLINE_SECTIONS = setOf(
        "목차", "차례", "서론", "본론", "결론", "개요", "배경", "연구 배경",
        "목적", "연구 목적", "의의", "필요성", "연구 방법", "결과", "고찰",
        "결론 및 제언", "요약", "참고문헌", "참고 문헌", "부록", "머리말", "서문",
        "맺음말", "문제 제기", "이론적 배경", "선행 연구", "기대 효과", "현황",
        "과제", "전망", "찾아보기", "판권", "저작권",
        "introduction", "background", "overview", "methodology", "methods",
        "results", "discussion", "conclusion", "summary", "references",
        "bibliography", "appendix", "table of contents", "contents", "index", "preface"
    )

    private val TOC_EXACT_TITLE_RE = Regex(
        """^[\[<【《(]*\s*(?:목\s*차|차\s*례|table\s+of\s+contents|contents|index|찾아보기|참고\s*문헌|references|bibliography|부\s*록|appendix|머리말|서문|일러두기|판권|저작권|단원\s*요약|학습\s*목표|핵심\s*정리|생각해보기|연습\s*문제|확인\s*문제|출제\s*포인트)\s*[\]>】》)]*$""",
        RegexOption.IGNORE_CASE
    )
    private val TOC_PREFIX_RE = Regex(
        """^(?:목\s*차|차\s*례|table\s+of\s+contents|contents)\s*(?::|：|-|—|\d|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])""",
        RegexOption.IGNORE_CASE
    )
    private val TOC_LEADER_PAGE_RE = Regex(
        """(?:\.{2,}|…+|·{2,}|•{2,}|-{2,}|─{2,}|_{2,}|\s{3,})\s*(?:p\.?\s*)?\d{1,4}\s*(?:쪽|페이지|p)?$""",
        RegexOption.IGNORE_CASE
    )
    private val TOC_NUMBERED_PAGE_END_RE = Regex(
        """^(?:제\s*\d+\s*[장절편부관과단원]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+\.?|\d+(?:\.\d+)*\.?|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩])\s+[^\n]{1,55}?\s+(?:p\.?\s*\d{1,4}|\d{1,4}\s*(?:쪽|페이지|p))$""",
        RegexOption.IGNORE_CASE
    )
    private val STRUCTURAL_CHAPTER_HEADER_RE = Regex(
        """^(?:제\s*\d+\s*(?:장|절|편|부|관|과|단원)|chapter\s+\d+|part\s+[0-9ivx]+|unit\s+\d+|lesson\s+\d+|section\s+\d+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.)(?:\s|$|:)""",
        RegexOption.IGNORE_CASE
    )
    private val LIST_PREFIX_STRIP_RE = Regex(
        """^(?:[\[<【《(]?\s*(?:제\s*\d+\s*[장절편부관과단원]|[①②③④⑤⑥⑦⑧⑨⑩]|(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+|\d+(?:\.\d+)*|[가-하]|[A-Za-z])\s*[\]>】》).:：\-])\s*)+"""
    )
    private val FACTUAL_PREDICATE_RE = Regex(
        """(?:이다|입니다|한다|된다|있다|없다|말한다|뜻한다|의미한다|가리킨다|정의된다|구성된다|분류된다|나뉜다|발생한다|일어난다|작용한다|억제한다|촉진한다|유발한다|소멸한다|규정한다|보장한다|제한한다|위반한다|합성하는|전환하는|교환하는|수행하는|is\s+defined\s+as|refers\s+to|means|leads\s+to|results\s+in|causes|consists\s+of|->|→)""",
        RegexOption.IGNORE_CASE
    )

    private fun hasFactualPredicate(text: String): Boolean = FACTUAL_PREDICATE_RE.containsMatchIn(text)

    private fun normalizeLabelCore(rawLabel: String): String {
        val trimChars = charArrayOf(' ', ':', '：', '-', '–', '—', '[', ']', '<', '>', '【', '】', '《', '》', '(', ')', '"', '\'')
        val cleaned = cleanLine(rawLabel).trim(*trimChars)
        val stripped = LIST_PREFIX_STRIP_RE.replace(cleaned, "").trim(*trimChars)
        return stripped.ifEmpty { cleaned }
    }

    fun isGenericSectionLabel(rawLabel: String): Boolean {
        val rawClean = cleanLine(rawLabel)
        if (rawClean.isEmpty() || rawClean.length > 28) return false
        val core = normalizeLabelCore(rawClean).lowercase()
        if (core.isEmpty()) return true
        if (core in GENERIC_SECTION_LABELS || core in TOC_OUTLINE_SECTIONS) return true
        if (Regex("""^(?:제?\s*\d+\s*[장절편부관과단원]|파트\s*\d+|단계\s*\d+|유형\s*\d+|특징\s*\d+|원인\s*\d+|목적\s*\d+|내용\s*\d+|배경\s*\d+|의의\s*\d+)$""").matches(core)) {
            return true
        }
        return false
    }

    fun isTocOrStructuralHeading(text: String, kind: String = "paragraph"): Boolean {
        val cleaned = cleanLine(text)
        if (cleaned.length < 2) return true
        val stripped = cleaned.trimStart('#', '*', '•', '-', ' ').trim()
        if (stripped.isEmpty()) return true

        if (TOC_EXACT_TITLE_RE.matches(stripped) || TOC_PREFIX_RE.containsMatchIn(stripped)) return true
        if (TOC_LEADER_PAGE_RE.containsMatchIn(stripped) || TOC_NUMBERED_PAGE_END_RE.matches(stripped)) return true

        if (":" !in stripped && "：" !in stripped && "->" !in stripped && "→" !in stripped) {
            if (isGenericSectionLabel(stripped)) return true
        }

        if (STRUCTURAL_CHAPTER_HEADER_RE.containsMatchIn(stripped)) {
            if (!hasFactualPredicate(stripped)) return true
            if (":" in stripped || "：" in stripped) {
                val rhs = stripped.split(Regex("[:：]"), limit = 2).last().trim()
                if (rhs.length < 12 && !hasFactualPredicate(rhs)) return true
            }
        }

        val numberedItems = NUMBERED_ITEM_RE.findAll(stripped)
            .map { it.groupValues[1].trim(' ', ',', '.', ';', ':') }
            .filter { it.length >= 2 }
            .toList()
        if (numberedItems.size >= 2) {
            val tocHits = numberedItems.count { it ->
                val core = normalizeLabelCore(it).lowercase()
                core in TOC_OUTLINE_SECTIONS || core in GENERIC_SECTION_LABELS || TOC_LEADER_PAGE_RE.containsMatchIn(it)
            }
            if (tocHits >= 2 && tocHits * 2 >= numberedItems.size) return true
        }

        if (kind == "heading" && !hasFactualPredicate(stripped)) return true

        if (!hasFactualPredicate(stripped) && ":" !in stripped && "：" !in stripped && "->" !in stripped && "→" !in stripped) {
            if (stripped.length <= 28 && Regex("""^(?:\d+(?:\.\d+)*\.?|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.?|[가-하]\.)\s+\S+""").containsMatchIn(stripped)) {
                return true
            }
        }
        return false
    }

    private fun maskTermInDesc(desc: String, term: String): String {
        val d = desc.trim()
        val t = term.trim()
        if (d.isEmpty() || t.isEmpty()) return d
        val candidates = mutableListOf(t)
        val baseTerm = t.replace(Regex("""\s*\([^)]*\)\s*"""), "").trim()
        if (baseTerm.length >= 2 && baseTerm !in candidates) {
            candidates.add(baseTerm)
        }
        var masked = d
        for (cand in candidates) {
            if (cand.length >= 2) {
                masked = masked.replace(Regex(Regex.escape(cand), RegexOption.IGNORE_CASE), "[ ___ ]")
            }
        }
        return masked
    }

    private val VERB_ENDINGS_RE = Regex(
        """(이다|입니다|한다|된다|있다|없다|말한다|뜻한다|의미한다|가리킨다|정의된다|하는|되는|있는|없는|하여|하고|하며|이고|이나|에서|으로|에게|까지|부터)$"""
    )
    private val PARTICLE_STRIP_RE = Regex(
        """(에서는|으로서|으로써|으로부터|에게는|이란|란|에서|으로|에게|보다|처럼|까지|부터|은|는|이|가|을|를|의|에|로|와|과|도|만)$"""
    )

    private fun extractNounCandidates(text: String): List<String> {
        val rawTokens = FALLBACK_NOUN_RE.findAll(text).map { it.value }.toList()
        val cleanedList = mutableListOf<String>()
        for (tok in rawTokens) {
            if (VERB_ENDINGS_RE.containsMatchIn(tok)) continue
            val stem = PARTICLE_STRIP_RE.replace(tok, "").trim()
            if (stem.length < 2) continue
            if (stem.lowercase() in STOPWORDS) continue
            if (isGenericSectionLabel(stem)) continue
            if (VERB_ENDINGS_RE.containsMatchIn(stem)) continue
            if (stem !in cleanedList) {
                cleanedList.add(stem)
            }
        }
        return cleanedList
    }

    private fun cleanLine(text: String): String {
        var norm = Normalizer.normalize(text, Normalizer.Form.NFKC)
        norm = norm.replace(Regex("""([A-Za-z])-\s*\n\s*([A-Za-z])"""), "$1$2")
        norm = norm.replace(Regex("""[ \t]+"""), " ")
        return norm.trim()
    }

    fun inferCategory(doc: ExtractedDocument): String {
        val combined = (listOfNotNull(doc.titleHint) + doc.blocks.map { it.text }).joinToString(" ").lowercase()
        val scores = mutableMapOf("law" to 0, "medical" to 0, "engineering" to 0, "language" to 0, "exam" to 0)

        for ((cat, keywords) in CATEGORY_KEYWORDS) {
            for (kw in keywords) {
                if (combined.contains(kw.lowercase())) {
                    scores[cat] = (scores[cat] ?: 0) + 2
                }
            }
        }
        if (STATUTE_RE.containsMatchIn(combined)) {
            scores["law"] = (scores["law"] ?: 0) + 4
        }
        if (doc.blocks.any { ARROW_PAIR_RE.matches(it.text.trim()) }) {
            scores["language"] = (scores["language"] ?: 0) + 3
        }

        var bestCat = "general"
        var bestScore = 0
        for (cat in listOf("law", "medical", "engineering", "language", "exam")) {
            val s = scores[cat] ?: 0
            if (s > bestScore) {
                bestScore = s
                bestCat = cat
            }
        }
        return if (bestScore >= 2) bestCat else "general"
    }

    fun inferDeckName(
        doc: ExtractedDocument,
        userName: String? = null,
        nowDateStr: String = "2026-10-19"
    ): String {
        if (!userName.isNullOrBlank()) {
            return userName.trim().take(80)
        }
        if (!doc.titleHint.isNullOrBlank() && doc.titleHint.trim().length >= 2) {
            return doc.titleHint.trim().take(80)
        }
        for (b in doc.blocks) {
            if (b.kind == "heading") {
                val cleaned = cleanLine(b.text).trimStart('#', '*', '•', '-', ' ').trim()
                if (cleaned.length >= 2 &&
                    !TOC_EXACT_TITLE_RE.matches(cleaned) &&
                    !TOC_PREFIX_RE.containsMatchIn(cleaned) &&
                    !isGenericSectionLabel(cleaned)
                ) {
                    return cleaned.take(80)
                }
            }
        }

        val counts = linkedMapOf<String, Int>()
        val wordRe = Regex("""[가-힣]{2,12}|[A-Za-z][A-Za-z0-9\-]{2,15}""")
        val suffixRe = Regex("""(이란|란|에서는|에서|으로|에게|이다|한다|의|은|는|이|가|을|를)$""")
        for (b in doc.blocks) {
            if (b.confidence != null && b.confidence < 0.60) continue
            for (m in wordRe.findAll(b.text)) {
                val wClean = m.value.replace(suffixRe, "")
                if (wClean.length >= 2 && wClean.lowercase() !in STOPWORDS && !isGenericSectionLabel(wClean)) {
                    counts[wClean] = (counts[wClean] ?: 0) + 1
                }
            }
        }
        val topKeywords = counts.entries.sortedByDescending { it.value }.take(3).map { it.key }
        if (topKeywords.size >= 2) {
            return topKeywords.joinToString(" · ").take(80)
        }
        return "문서 덱 $nowDateStr"
    }

    fun classifyBlockPattern(text: String): String {
        val cleaned = cleanLine(text)
        if (cleaned.isEmpty()) return "definition"
        if (ARROW_PAIR_RE.matches(cleaned)) return "language_pair"
        if (NUMBERED_ITEM_RE.findAll(cleaned).count() >= 2) return "numbered_list"
        if (STATUTE_RE.containsMatchIn(cleaned) || NUMERIC_UNIT_RE.containsMatchIn(cleaned)) {
            if (STATUTE_RE.containsMatchIn(cleaned) || !COLON_DEF_RE.matches(cleaned)) {
                return "statute_numeric"
            }
        }
        if (COLON_DEF_RE.matches(cleaned) || KOREAN_DEF_RE.matches(cleaned) || ENGLISH_DEF_RE.matches(cleaned)) {
            return "definition"
        }
        if (CAUSAL_COMPARE_RE.containsMatchIn(cleaned)) return "causal_compare"
        if (NUMERIC_UNIT_RE.containsMatchIn(cleaned)) return "statute_numeric"
        return "definition"
    }

    fun normalizeCardFrontKey(frontText: String): String {
        var norm = Normalizer.normalize(frontText, Normalizer.Form.NFKC)
        norm = CLOZE_EXTRACT_RE.replace(norm, "$1").lowercase()
        return norm.replace(Regex("""[^\p{L}\p{N}]+"""), "")
    }

    private fun extractAnswerVerificationTokens(spec: GeneratedCardSpec): List<String> {
        val clozeTargets = CLOZE_EXTRACT_RE.findAll(spec.frontText).map { it.groupValues[1] }.toList()
        val rawTarget = if (clozeTargets.isNotEmpty()) {
            clozeTargets.joinToString(" ")
        } else {
            spec.backText.substringBefore("💡 해설:").trim()
        }
        val normTarget = Normalizer.normalize(rawTarget, Normalizer.Form.NFKC).lowercase()
        return TOKEN_RE.findAll(normTarget).map { it.value }.filter { it !in STOPWORDS }.toList()
    }

    private val NUMBER_TOKEN_RE = Regex("""\d+(?:\.\d+)?""")
    private val ASCII_START_RE = Regex("""^[a-z0-9]""")

    private fun isTokenGroundedOnPage(
        token: String,
        pageTokens: Set<String>,
        pageNumbers: Set<String>
    ): Boolean {
        for (numMatch in NUMBER_TOKEN_RE.findAll(token)) {
            if (numMatch.value !in pageNumbers) return false
        }
        if (ASCII_START_RE.containsMatchIn(token)) {
            return token in pageTokens
        }
        return pageTokens.any { pt -> pt == token || pt.startsWith(token) || pt.contains(token) }
    }

    fun groundCards(cards: List<SourcedCard>, doc: ExtractedDocument): Pair<List<SourcedCard>, Int> {
        val pageTexts = linkedMapOf<Int, MutableList<String>>()
        for (b in doc.blocks) {
            pageTexts.getOrPut(b.page) { mutableListOf() }.add(cleanLine(b.text))
        }
        val pageCorpus: Map<Int, String> = pageTexts.mapValues { (_, txts) ->
            Normalizer.normalize(txts.joinToString(" "), Normalizer.Form.NFKC).lowercase()
        }
        val pageTokenSets: Map<Int, Set<String>> = pageCorpus.mapValues { (_, text) ->
            TOKEN_RE.findAll(text).map { it.value }.toSet()
        }
        val pageNumberSets: Map<Int, Set<String>> = pageCorpus.mapValues { (_, text) ->
            NUMBER_TOKEN_RE.findAll(text).map { it.value }.toSet()
        }

        val kept = mutableListOf<SourcedCard>()
        var dropped = 0

        for (card in cards) {
            val pageText = pageCorpus[card.sourcePage]
            if (pageText.isNullOrEmpty()) {
                dropped += 1
                continue
            }
            val pTokens = pageTokenSets[card.sourcePage] ?: emptySet()
            val pNumbers = pageNumberSets[card.sourcePage] ?: emptySet()

            val tokens = extractAnswerVerificationTokens(card.spec)
            if (tokens.isEmpty() || !tokens.all { isTokenGroundedOnPage(it, pTokens, pNumbers) }) {
                dropped += 1
                continue
            }
            if (card.sourceExcerpt.isNotBlank()) {
                val normExcerpt = Normalizer.normalize(cleanLine(card.sourceExcerpt), Normalizer.Form.NFKC).lowercase()
                val excerptNumbers = NUMBER_TOKEN_RE.findAll(normExcerpt).map { it.value }.toList()
                if (excerptNumbers.any { it !in pNumbers }) {
                    dropped += 1
                    continue
                }
                val excerptTokens = TOKEN_RE.findAll(normExcerpt).map { it.value }.filter { it !in STOPWORDS }.toList()
                if (excerptTokens.isNotEmpty() && !excerptTokens.all { isTokenGroundedOnPage(it, pTokens, pNumbers) }) {
                    dropped += 1
                    continue
                }
            }
            kept.add(card)
        }
        return kept to dropped
    }

    fun stripRepeatedHeadersFooters(blocks: List<DocumentBlock>): List<DocumentBlock> {
        val linePages = linkedMapOf<String, MutableSet<Int>>()
        for (b in blocks) {
            for (line in b.text.lines()) {
                val norm = cleanLine(line)
                if (norm.isNotEmpty()) {
                    linePages.getOrPut(norm) { mutableSetOf() }.add(b.page)
                }
            }
        }
        val repeated = linePages.filterValues { it.size >= 3 }.keys
        if (repeated.isEmpty()) return blocks

        val cleanedBlocks = mutableListOf<DocumentBlock>()
        for (b in blocks) {
            val keptLines = b.text.lines().filter { cleanLine(it) !in repeated }
            val joined = keptLines.joinToString("\n").trim()
            if (joined.isNotEmpty()) {
                cleanedBlocks.add(b.copy(text = joined))
            }
        }
        return cleanedBlocks
    }

    private val GENERIC_BOILERPLATE_SUFFIXES = listOf("시스템", "프로그램", "애플리케이션", "프로세스", "알고리즘", "메커니즘", "인터페이스", "네트워크", "데이터베이스")

    fun selectSemanticHingeToken(candidates: List<String>, text: String, category: String): String {
        if (candidates.isEmpty()) return ""
        val catKeywords = CATEGORY_KEYWORDS[category] ?: emptySet()
        fun scoreCandidate(tok: String): Double {
            var score = min(tok.length, 6).toDouble() * 1.2
            if (tok.any { it.isUpperCase() } && tok.any { it.isLetter() }) score += 3.0
            if (tok.any { it.isDigit() }) score += 2.5
            if (tok.lowercase() in catKeywords || catKeywords.any { it in tok.lowercase() }) score += 3.5
            val pos = text.indexOf(tok)
            if (pos in 0..(text.length / 2)) score += 1.5
            if (GENERIC_BOILERPLATE_SUFFIXES.any { tok.endsWith(it) } && tok.length >= 4) score -= 2.5
            return score
        }
        return candidates.maxByOrNull { scoreCandidate(it) } ?: candidates.first()
    }

    private fun synthesizeContentKeywordCards(
        contentText: String,
        block: DocumentBlock,
        category: String,
        difficultyLevel: String,
        baseTags: List<String>,
        excerpt: String,
        headingContext: String = ""
    ): List<SourcedCard> {
        val candidates = extractNounCandidates(contentText)
        if (candidates.isEmpty() || contentText.length < 10) return emptyList()
        val target = selectSemanticHingeToken(candidates, contentText, category)
        if (target.isEmpty() || target !in contentText) return emptyList()

        val topicPrefix = if (headingContext.isNotBlank() && headingContext !in contentText) "[$headingContext] " else ""
        val clozeSentence = topicPrefix + contentText.replaceFirst(target, "{{c1::$target::핵심 키워드}}")
        val maskedDesc = topicPrefix + contentText.replace(target, "[ ___ ]")
        val diff = difficultyLevel.trim().lowercase()

        val lv1 = SourcedCard(
            spec = GeneratedCardSpec(
                noteType = "basic",
                frontText = "🌱 [Lv.1 개념 확인] $maskedDesc",
                backText = "$target\n\n💡 해설: $excerpt",
                tags = baseTags + "diff_lv1",
                rationale = "p.${block.page} 내용 기반 핵심 키워드 확인"
            ),
            pattern = "definition",
            sourcePage = block.page,
            sourceExcerpt = excerpt
        )
        val lv2 = SourcedCard(
            spec = GeneratedCardSpec(
                noteType = "cloze",
                frontText = clozeSentence,
                backText = "$target\n\n💡 해설: $excerpt",
                tags = baseTags + "diff_lv2",
                rationale = "p.${block.page} 문맥 빈칸 Cloze"
            ),
            pattern = "definition",
            sourcePage = block.page,
            sourceExcerpt = excerpt
        )
        val lv3 = SourcedCard(
            spec = GeneratedCardSpec(
                noteType = "basic",
                frontText = "🔥 [Lv.3 용어 인출] $maskedDesc",
                backText = "$target\n\n💡 해설: $excerpt",
                tags = baseTags + "diff_lv3",
                rationale = "p.${block.page} 내용 기반 핵심 용어 산출"
            ),
            pattern = "definition",
            sourcePage = block.page,
            sourceExcerpt = excerpt
        )
        return when (diff) {
            "lv1" -> listOf(lv1)
            "lv2" -> listOf(lv2)
            "lv3" -> listOf(lv3)
            "mixed", "all" -> listOf(lv1, lv2, lv3)
            else -> listOf(lv2.copy(spec = lv2.spec.copy(tags = baseTags)))
        }
    }

    private fun synthesizeCardsFromBlock(
        block: DocumentBlock,
        category: String,
        difficultyLevel: String = "standard",
        headingContext: String = ""
    ): List<SourcedCard> {
        val text = cleanLine(block.text)
        if (text.length < 8) return emptyList()
        if (isTocOrStructuralHeading(text, block.kind)) return emptyList()

        val excerpt = text.take(140)
        val pattern = classifyBlockPattern(text)
        val diff = difficultyLevel.trim().lowercase()
        val conceptTag = "concept:doc_${(text.take(36).hashCode() and 0x7fffffff)}"
        val baseTags = listOf("auto-deck", category, pattern, "p${block.page}", conceptTag)

        fun expandTermDefCards(term: String, desc: String, stdFront: String, stdBack: String, pat: String = "definition"): List<SourcedCard> {
            val safeDesc = maskTermInDesc(desc, term)
            val conciseBack = "$term\n\n💡 해설: $desc"
            val lv1 = SourcedCard(
                spec = GeneratedCardSpec(
                    noteType = "basic",
                    frontText = "🌱 [Lv.1 개념 확인] $safeDesc",
                    backText = conciseBack,
                    tags = baseTags + "diff_lv1",
                    rationale = "p.${block.page} Lv.1 내용·정의 기반 핵심 개념 확인"
                ),
                pattern = pat,
                sourcePage = block.page,
                sourceExcerpt = excerpt
            )
            val lv2 = SourcedCard(
                spec = GeneratedCardSpec(
                    noteType = "cloze",
                    frontText = stdFront,
                    backText = stdBack,
                    tags = baseTags + "diff_lv2",
                    rationale = "p.${block.page} Lv.2 문맥 빈칸 Cloze"
                ),
                pattern = pat,
                sourcePage = block.page,
                sourceExcerpt = excerpt
            )
            val lv3 = SourcedCard(
                spec = GeneratedCardSpec(
                    noteType = "basic",
                    frontText = "🔥 [Lv.3 용어 인출] $safeDesc",
                    backText = conciseBack,
                    tags = baseTags + "diff_lv3",
                    rationale = "p.${block.page} Lv.3 역방향 능동 산출"
                ),
                pattern = pat,
                sourcePage = block.page,
                sourceExcerpt = excerpt
            )
            return when (diff) {
                "lv1" -> listOf(lv1)
                "lv2" -> listOf(lv2)
                "lv3" -> listOf(lv3)
                "mixed", "all" -> listOf(lv1, lv2, lv3)
                else -> listOf(lv2.copy(spec = lv2.spec.copy(tags = baseTags)))
            }
        }

        if (pattern == "language_pair") {
            val m = ARROW_PAIR_RE.matchEntire(text)
            if (m != null) {
                val srcPhrase = m.groupValues[1].trim()
                val dstPhrase = m.groupValues[2].trim()
                return listOf(
                    SourcedCard(
                        spec = GeneratedCardSpec(
                            noteType = "speaking",
                            frontText = "🗣️ [어학·표현] $srcPhrase",
                            backText = dstPhrase,
                            tags = baseTags,
                            rationale = "p.${block.page} 어학 표현 쌍 자동 추출"
                        ),
                        pattern = "language_pair",
                        sourcePage = block.page,
                        sourceExcerpt = excerpt
                    )
                )
            }
        }

        if (pattern == "numbered_list") {
            val items = NUMBERED_ITEM_RE.findAll(text)
                .map { it.groupValues[1].trim(' ', ',', '.', ';', ':') }
                .filter { it.length >= 2 }
                .toList()
            if (items.size >= 2) {
                val tocHits = items.count { isGenericSectionLabel(it) || TOC_LEADER_PAGE_RE.containsMatchIn(it) }
                if (tocHits >= 2 && tocHits * 2 >= items.size) return emptyList()
                val clozeParts = items.mapIndexed { idx, item ->
                    if (idx < 3) "(${idx + 1}) {{c${idx + 1}::$item}}" else "(${idx + 1}) $item"
                }
                val rawHeader = text.split("1")[0].split("①")[0].split("(1)")[0].trim(' ', ':', '：', '-')
                val headerPrefix = if (isGenericSectionLabel(rawHeader)) headingContext else rawHeader
                val titlePrefix = if (headerPrefix.length >= 2) "[$headerPrefix] " else "[핵심 항목] "
                return listOf(
                    SourcedCard(
                        spec = GeneratedCardSpec(
                            noteType = "cloze",
                            frontText = titlePrefix + clozeParts.joinToString(" / "),
                            backText = items.joinToString(" · ") + "\n\n💡 해설: $excerpt",
                            tags = baseTags,
                            rationale = "p.${block.page} 번호 목록 ${items.size}개 항목 열거 Cloze"
                        ),
                        pattern = "numbered_list",
                        sourcePage = block.page,
                        sourceExcerpt = excerpt
                    )
                )
            }
        }

        if (pattern == "statute_numeric") {
            val statM = STATUTE_RE.find(text)
            val numM = NUMERIC_UNIT_RE.find(text)
            var clozeText = text
            var ordinal = 1
            val targets = mutableListOf<String>()
            if (statM != null) {
                val target = statM.groupValues[1]
                clozeText = clozeText.replaceFirst(target, "{{c$ordinal::$target::조문}}")
                targets.add(target)
                ordinal += 1
            }
            if (numM != null) {
                val numTarget = numM.groupValues[1]
                if (clozeText.contains(numTarget)) {
                    clozeText = clozeText.replaceFirst(numTarget, "{{c$ordinal::$numTarget::수치·단위}}")
                    targets.add(numTarget)
                    ordinal += 1
                }
            }
            if (ordinal > 1) {
                return listOf(
                    SourcedCard(
                        spec = GeneratedCardSpec(
                            noteType = "cloze",
                            frontText = clozeText,
                            backText = targets.joinToString(" · ") + "\n\n💡 해설: $excerpt",
                            tags = baseTags,
                            rationale = "p.${block.page} 조문·핵심 수치/단위 빈칸 Cloze"
                        ),
                        pattern = "statute_numeric",
                        sourcePage = block.page,
                        sourceExcerpt = excerpt
                    )
                )
            }
        }

        COLON_DEF_RE.matchEntire(text)?.let { m ->
            val term = m.groupValues[1].trim()
            val desc = m.groupValues[2].trim()
            if (isTocOrStructuralHeading(desc, "paragraph")) return emptyList()
            if (isGenericSectionLabel(term)) {
                return synthesizeContentKeywordCards(desc, block, category, difficultyLevel, baseTags, excerpt, headingContext)
            }
            val safeDesc = maskTermInDesc(desc, term)
            return expandTermDefCards(term, desc, "{{c1::$term::핵심 개념}}: $safeDesc", "$term\n\n💡 해설: $desc")
        }

        KOREAN_DEF_RE.matchEntire(text)?.let { m ->
            val term = m.groupValues[1].trim()
            val desc = m.groupValues[2].trim()
            if (isGenericSectionLabel(term)) {
                return synthesizeContentKeywordCards(desc, block, category, difficultyLevel, baseTags, excerpt, headingContext)
            }
            val safeDesc = maskTermInDesc(desc, term)
            return expandTermDefCards(term, desc, "{{c1::$term::핵심 개념}}은(는) $safeDesc", "$term\n\n💡 해설: $desc")
        }

        ENGLISH_DEF_RE.matchEntire(text)?.let { m ->
            val term = m.groupValues[1].trim()
            val desc = m.groupValues[2].trim()
            if (isGenericSectionLabel(term)) {
                return synthesizeContentKeywordCards(desc, block, category, difficultyLevel, baseTags, excerpt, headingContext)
            }
            val safeDesc = maskTermInDesc(desc, term)
            return expandTermDefCards(term, desc, "{{c1::$term::Concept}} is defined as $safeDesc", "$term\n\n💡 해설: $desc")
        }

        CAUSAL_COMPARE_RE.find(text)?.let { m ->
            val lhs = m.groupValues[1].trim()
            val conn = m.groupValues[2].trim()
            val rhs = m.groupValues[3].trim()
            return listOf(
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = "basic",
                        frontText = "❓ [인과·비교] $lhs ($conn) ➔ ?",
                        backText = "$rhs\n\n💡 해설: $excerpt",
                        tags = baseTags,
                        rationale = "p.${block.page} 인과·비교($conn) Q&A"
                    ),
                    pattern = "causal_compare",
                    sourcePage = block.page,
                    sourceExcerpt = excerpt
                )
            )
        }

        // Fallback for general informative sentence: mask the highest semantic-hinge domain noun/keyword
        if (block.kind == "heading") return emptyList()
        if (text.length >= 16) {
            return synthesizeContentKeywordCards(text, block, category, difficultyLevel, baseTags, excerpt, headingContext)
        }

        return emptyList()
    }

    fun selectBalancedCards(cards: List<SourcedCard>, maxCards: Int): List<SourcedCard> {
        if (cards.size <= maxCards) return cards
        val byPattern = linkedMapOf<String, MutableList<SourcedCard>>()
        for (p in VALID_PATTERNS) {
            byPattern[p] = mutableListOf()
        }
        for (c in cards) {
            byPattern.getOrPut(c.pattern) { mutableListOf() }.add(c)
        }

        val selected = mutableListOf<SourcedCard>()
        var idx = 0
        while (selected.size < maxCards) {
            var addedInRound = false
            for (p in VALID_PATTERNS) {
                val bucket = byPattern[p] ?: emptyList()
                if (idx < bucket.size) {
                    selected.add(bucket[idx])
                    addedInRound = true
                    if (selected.size >= maxCards) break
                }
            }
            if (!addedInRound) break
            idx += 1
        }
        return selected
    }

    fun buildDeckPlan(
        doc: ExtractedDocument,
        userDeckName: String? = null,
        categoryOverride: String? = null,
        maxCards: Int = 30,
        minConfidence: Double = 0.60,
        minTextChars: Int = 40,
        nowDateStr: String = "2026-10-19",
        ocrPages: Int = 0,
        difficultyLevel: String = "standard"
    ): DeckPlan {
        val cap = max(1, min(60, maxCards))
        var lowConfidenceLines = 0
        var unmeasuredConfidenceLines = 0
        val confidentBlocks = mutableListOf<DocumentBlock>()

        for (b in doc.blocks) {
            if (b.confidence == null) {
                unmeasuredConfidenceLines += 1
                confidentBlocks.add(b)
            } else if (b.confidence < minConfidence) {
                lowConfidenceLines += 1
            } else {
                confidentBlocks.add(b)
            }
        }

        val cleanedBlocks = stripRepeatedHeadersFooters(confidentBlocks)
        val filteredDoc = doc.copy(blocks = cleanedBlocks)
        val category = categoryOverride?.takeIf { it in VALID_CATEGORIES } ?: inferCategory(filteredDoc)
        val deckName = inferDeckName(filteredDoc, userName = userDeckName, nowDateStr = nowDateStr)
        val totalChars = cleanedBlocks.sumOf { cleanLine(it.text).length }

        if (totalChars < minTextChars) {
            return DeckPlan(
                status = "BLOCKED",
                errorCode = "insufficient_text",
                deckName = deckName,
                category = category,
                cards = emptyList(),
                stats = BuildStats(doc.pageCount, ocrPages, lowConfidenceLines, unmeasuredConfidenceLines, 0, 0, totalChars)
            )
        }

        val rawCandidates = mutableListOf<SourcedCard>()
        var activeHeadingTopic = ""

        fun updateHeadingTopic(candidateLine: String) {
            val cleanedH = cleanLine(candidateLine).trimStart('#', '*', '•', '-', ' ').trim()
            if (cleanedH.isEmpty()) return
            if (TOC_EXACT_TITLE_RE.matches(cleanedH) ||
                TOC_PREFIX_RE.containsMatchIn(cleanedH) ||
                TOC_LEADER_PAGE_RE.containsMatchIn(cleanedH) ||
                TOC_NUMBERED_PAGE_END_RE.matches(cleanedH)
            ) {
                return
            }
            val topic = cleanedH.trim(' ', '[', ']', '<', '>', '《', '》', '「', '」', '『', '』')
            if (topic.length in 2..45 && !isGenericSectionLabel(topic)) {
                activeHeadingTopic = topic
            }
        }

        for (block in cleanedBlocks) {
            if (block.kind == "heading" || isTocOrStructuralHeading(block.text, block.kind)) {
                updateHeadingTopic(block.text)
            }
            val lines = block.text.lines().map { it.trim() }.filter { it.isNotEmpty() }
            if (lines.size > 1 && lines.any { COLON_DEF_RE.matches(it) || ARROW_PAIR_RE.matches(it) || isTocOrStructuralHeading(it, "paragraph") }) {
                for (ln in lines) {
                    if (isTocOrStructuralHeading(ln, "paragraph")) {
                        updateHeadingTopic(ln)
                        continue
                    }
                    val subBlock = block.copy(kind = if (block.kind == "heading") "paragraph" else block.kind, text = ln)
                    rawCandidates.addAll(synthesizeCardsFromBlock(subBlock, category, difficultyLevel, activeHeadingTopic))
                }
            } else {
                rawCandidates.addAll(synthesizeCardsFromBlock(block, category, difficultyLevel, activeHeadingTopic))
            }
        }

        val (grounded, droppedUngrounded) = groundCards(rawCandidates, filteredDoc)

        val seenKeys = mutableSetOf<String>()
        val deduped = mutableListOf<SourcedCard>()
        var duplicates = 0
        for (c in grounded) {
            val key = normalizeCardFrontKey(c.spec.frontText)
            if (key.isEmpty() || !seenKeys.add(key)) {
                duplicates += 1
                continue
            }
            deduped.add(c)
        }

        val finalCards = selectBalancedCards(deduped, maxCards = cap)
        if (finalCards.isEmpty()) {
            return DeckPlan(
                status = "BLOCKED",
                errorCode = "no_cards",
                deckName = deckName,
                category = category,
                cards = emptyList(),
                stats = BuildStats(doc.pageCount, ocrPages, lowConfidenceLines, unmeasuredConfidenceLines, droppedUngrounded, duplicates, totalChars)
            )
        }

        return DeckPlan(
            status = "OK",
            errorCode = null,
            deckName = deckName,
            category = category,
            cards = finalCards,
            stats = BuildStats(doc.pageCount, ocrPages, lowConfidenceLines, unmeasuredConfidenceLines, droppedUngrounded, duplicates, totalChars)
        )
    }
}
