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
                if (cleaned.length >= 2) return cleaned.take(80)
            }
        }

        val counts = linkedMapOf<String, Int>()
        val wordRe = Regex("""[가-힣]{2,12}|[A-Za-z][A-Za-z0-9\-]{2,15}""")
        val suffixRe = Regex("""(이란|란|에서는|에서|으로|에게|이다|한다|의|은|는|이|가|을|를)$""")
        for (b in doc.blocks) {
            if (b.confidence != null && b.confidence < 0.60) continue
            for (m in wordRe.findAll(b.text)) {
                val wClean = m.value.replace(suffixRe, "")
                if (wClean.length >= 2 && wClean.lowercase() !in STOPWORDS) {
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
        val rawTarget = if (clozeTargets.isNotEmpty()) clozeTargets.joinToString(" ") else spec.backText
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

    private fun synthesizeCardsFromBlock(block: DocumentBlock, category: String): List<SourcedCard> {
        val text = cleanLine(block.text)
        if (text.length < 8) return emptyList()

        val excerpt = text.take(140)
        val pattern = classifyBlockPattern(text)
        val baseTags = listOf("auto-deck", category, pattern, "p${block.page}")

        if (pattern == "language_pair") {
            val m = ARROW_PAIR_RE.matchEntire(text)
            if (m != null) {
                val srcPhrase = m.groupValues[1].trim()
                val dstPhrase = m.groupValues[2].trim()
                return listOf(
                    SourcedCard(
                        spec = GeneratedCardSpec(
                            noteType = "speaking",
                            frontText = "🗣️ [어학·표현 인출] $srcPhrase",
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
                val clozeParts = items.mapIndexed { idx, item ->
                    if (idx < 3) "(${idx + 1}) {{c${idx + 1}::$item}}" else "(${idx + 1}) $item"
                }
                val headerPrefix = text.split("1")[0].split("①")[0].split("(1)")[0].trim(' ', ':', '：', '-')
                val titlePrefix = if (headerPrefix.length >= 2) "[$headerPrefix] " else "[핵심 항목 열거] "
                return listOf(
                    SourcedCard(
                        spec = GeneratedCardSpec(
                            noteType = "cloze",
                            frontText = titlePrefix + clozeParts.joinToString(" / "),
                            backText = "전체 항목 (${items.size}개): " + items.joinToString(" · "),
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
            if (statM != null) {
                val target = statM.groupValues[1]
                clozeText = clozeText.replaceFirst(target, "{{c$ordinal::$target::조문}}")
                ordinal += 1
            }
            if (numM != null) {
                val numTarget = numM.groupValues[1]
                if (clozeText.contains(numTarget)) {
                    clozeText = clozeText.replaceFirst(numTarget, "{{c$ordinal::$numTarget::수치·단위}}")
                    ordinal += 1
                }
            }
            if (ordinal > 1) {
                return listOf(
                    SourcedCard(
                        spec = GeneratedCardSpec(
                            noteType = "cloze",
                            frontText = clozeText,
                            backText = "출처 원문 (p.${block.page}): $excerpt",
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
            return listOf(
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = "cloze",
                        frontText = "{{c1::$term::핵심 개념}}: $desc",
                        backText = "$term — $desc",
                        tags = baseTags,
                        rationale = "p.${block.page} 용어 정의 Cloze"
                    ),
                    pattern = "definition",
                    sourcePage = block.page,
                    sourceExcerpt = excerpt
                )
            )
        }

        KOREAN_DEF_RE.matchEntire(text)?.let { m ->
            val term = m.groupValues[1].trim()
            val desc = m.groupValues[2].trim()
            return listOf(
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = "cloze",
                        frontText = "{{c1::$term::핵심 개념}}은(는) $desc",
                        backText = "$term: $desc",
                        tags = baseTags,
                        rationale = "p.${block.page} 국문 개념 정의 Cloze"
                    ),
                    pattern = "definition",
                    sourcePage = block.page,
                    sourceExcerpt = excerpt
                )
            )
        }

        ENGLISH_DEF_RE.matchEntire(text)?.let { m ->
            val term = m.groupValues[1].trim()
            val desc = m.groupValues[2].trim()
            return listOf(
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = "cloze",
                        frontText = "{{c1::$term::Concept}} is defined as $desc",
                        backText = "$term: $desc",
                        tags = baseTags,
                        rationale = "p.${block.page} 영문 개념 정의 Cloze"
                    ),
                    pattern = "definition",
                    sourcePage = block.page,
                    sourceExcerpt = excerpt
                )
            )
        }

        CAUSAL_COMPARE_RE.find(text)?.let { m ->
            val lhs = m.groupValues[1].trim()
            val conn = m.groupValues[2].trim()
            val rhs = m.groupValues[3].trim()
            return listOf(
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = "basic",
                        frontText = "❓ [인과·비교 핵심] $lhs ($conn) 뒤에 이어지는 핵심 결과·대조 내용은?",
                        backText = rhs,
                        tags = baseTags,
                        rationale = "p.${block.page} 인과·비교($conn) Q&A"
                    ),
                    pattern = "causal_compare",
                    sourcePage = block.page,
                    sourceExcerpt = excerpt
                )
            )
        }

        // Fallback for general informative sentence: mask the longest domain noun/keyword
        if (block.kind == "heading") return emptyList()
        val candidates = FALLBACK_NOUN_RE.findAll(text).map { it.value }.filter { it.lowercase() !in STOPWORDS }.toList()
        if (candidates.isNotEmpty() && text.length >= 18) {
            val target = candidates.maxByOrNull { it.length }!!
            val clozeSentence = text.replaceFirst(target, "{{c1::$target::핵심 키워드}}")
            return listOf(
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = "cloze",
                        frontText = clozeSentence,
                        backText = "정답: $target (p.${block.page})",
                        tags = baseTags,
                        rationale = "p.${block.page} 핵심 키워드 Cloze"
                    ),
                    pattern = "definition",
                    sourcePage = block.page,
                    sourceExcerpt = excerpt
                )
            )
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
        ocrPages: Int = 0
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
        for (block in cleanedBlocks) {
            val lines = block.text.lines().map { it.trim() }.filter { it.isNotEmpty() }
            if (lines.size > 1 && lines.any { COLON_DEF_RE.matches(it) || ARROW_PAIR_RE.matches(it) }) {
                for (ln in lines) {
                    val subBlock = block.copy(text = ln)
                    rawCandidates.addAll(synthesizeCardsFromBlock(subBlock, category))
                }
            } else {
                rawCandidates.addAll(synthesizeCardsFromBlock(block, category))
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
