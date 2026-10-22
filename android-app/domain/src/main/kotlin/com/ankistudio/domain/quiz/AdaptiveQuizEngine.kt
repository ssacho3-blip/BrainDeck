package com.ankistudio.domain.quiz

import com.ankistudio.domain.fsrs.Fsrs5Engine.Rating
import java.text.Normalizer
import kotlin.math.max
import kotlin.math.min

/**
 * Pure JVM Kotlin K-12 & Adult Adaptive Quiz Engine (T16, T17, T18, T22, T23).
 * Strictly zero `android.*` or `androidx.*` imports.
 */
object AdaptiveQuizEngine {

    enum class AgeTier(val code: String) {
        JUNIOR("junior"),
        TEEN("teen"),
        ADULT("adult");

        companion object {
            fun fromCode(code: String): AgeTier =
                entries.firstOrNull { it.code.equals(code.trim(), ignoreCase = true) } ?: ADULT
        }
    }

    data class ProfilePolicy(
        val ageTier: AgeTier,
        val defaultDailyNew: Int,
        val defaultDailyReview: Int,
        val maxFrontChars: Int,
        val maxBackChars: Int,
        val stabilityPromoteThreshold: Double,
        val normalLatencyMs: Long,
        val cloudVisionLocked: Boolean
    )

    private val POLICIES: Map<AgeTier, ProfilePolicy> = mapOf(
        AgeTier.JUNIOR to ProfilePolicy(
            ageTier = AgeTier.JUNIOR,
            defaultDailyNew = 10,
            defaultDailyReview = 50,
            maxFrontChars = 40,
            maxBackChars = 60,
            stabilityPromoteThreshold = 3.0,
            normalLatencyMs = 8000L,
            cloudVisionLocked = true
        ),
        AgeTier.TEEN to ProfilePolicy(
            ageTier = AgeTier.TEEN,
            defaultDailyNew = 20,
            defaultDailyReview = 150,
            maxFrontChars = 100,
            maxBackChars = 150,
            stabilityPromoteThreshold = 5.0,
            normalLatencyMs = 6000L,
            cloudVisionLocked = false
        ),
        AgeTier.ADULT to ProfilePolicy(
            ageTier = AgeTier.ADULT,
            defaultDailyNew = 25,
            defaultDailyReview = 150,
            maxFrontChars = 220,
            maxBackChars = 400,
            stabilityPromoteThreshold = 5.0,
            normalLatencyMs = 5000L,
            cloudVisionLocked = false
        )
    )

    fun getProfilePolicy(ageTier: AgeTier): ProfilePolicy = POLICIES.getValue(ageTier)

    data class InteractionGradeResult(
        val rating: Rating,
        val evidenceClass: String, // "recognition" | "cued_recall" | "recall"
        val nextQuizStage: Int,    // 0: RECOGNITION_MC, 1: TAP_BLOCK, 2: RECALL_INPUT
        val nextConsecutiveSuccesses: Int
    )

    fun gradeInteraction(
        ageTier: AgeTier,
        interactionMode: String,
        isCorrect: Boolean,
        attemptCount: Int = 1,
        hintUsed: Boolean = false,
        responseMs: Long = 3000L,
        optionCount: Int? = null,
        blockCorrections: Int = 0,
        recallScorePct: Double = 100.0,
        currentQuizStage: Int = 0,
        currentConsecutiveSuccesses: Int = 0,
        currentStability: Double = 0.0
    ): InteractionGradeResult {
        val policy = getProfilePolicy(ageTier)
        val stage = currentQuizStage.coerceIn(0, 2)
        val mode = interactionMode.trim().lowercase()

        val evidenceClass = when (mode) {
            "multiple_choice", "button_2" -> "recognition"
            "tap_block" -> "cued_recall"
            else -> "recall"
        }

        val rating: Rating = if (!isCorrect || attemptCount != 1) {
            Rating.AGAIN
        } else if (evidenceClass == "recognition") {
            if ((optionCount != null && optionCount <= 3) || mode == "button_2") {
                Rating.HARD
            } else if (hintUsed || responseMs > policy.normalLatencyMs) {
                Rating.HARD
            } else {
                // 4-choice recognition never grants EASY (T16)
                Rating.GOOD
            }
        } else if (evidenceClass == "cued_recall") {
            if (hintUsed || blockCorrections >= 1 || responseMs > policy.normalLatencyMs * 1.5) {
                Rating.HARD
            } else {
                // Tap-block cued recall caps at GOOD
                Rating.GOOD
            }
        } else {
            if (hintUsed) {
                if (recallScorePct >= 60.0) Rating.HARD else Rating.AGAIN
            } else if (recallScorePct >= 95.0 && responseMs <= policy.normalLatencyMs) {
                Rating.EASY
            } else if (recallScorePct >= 85.0) {
                Rating.GOOD
            } else if (recallScorePct >= 65.0) {
                Rating.HARD
            } else {
                Rating.AGAIN
            }
        }

        val nextStage: Int
        val nextConsec: Int
        if (rating == Rating.AGAIN) {
            nextStage = max(0, stage - 1)
            nextConsec = 0
        } else if (rating == Rating.GOOD || rating == Rating.EASY) {
            val incremented = currentConsecutiveSuccesses + 1
            if (stage < 2 && incremented >= 2 && currentStability >= policy.stabilityPromoteThreshold) {
                nextStage = stage + 1
                nextConsec = 0
            } else {
                nextStage = stage
                nextConsec = incremented
            }
        } else {
            nextStage = stage
            nextConsec = 0
        }

        return InteractionGradeResult(
            rating = rating,
            evidenceClass = evidenceClass,
            nextQuizStage = nextStage,
            nextConsecutiveSuccesses = nextConsec
        )
    }

    enum class QuestionFacet(
        val allowedRelations: Set<String>,
        val forbiddenRelations: Set<String>
    ) {
        VOCAB_MEANING(
            allowedRelations = setOf("antonym", "confusable_spelling", "same_pos_level", "same_category"),
            forbiddenRelations = setOf("synonym", "variant_of")
        ),
        HANJA_EUM(
            allowedRelations = setOf("similar_shape", "same_radical"),
            forbiddenRelations = setOf("homophone", "variant_of")
        ),
        HANJA_HUN(
            allowedRelations = setOf("homophone", "similar_shape", "same_radical"),
            forbiddenRelations = setOf("synonym", "variant_of")
        ),
        HANJA_CHAR(
            allowedRelations = setOf("homophone", "similar_shape", "same_radical"),
            forbiddenRelations = setOf("variant_of")
        ),
        HISTORY_ERA_KING(
            allowedRelations = setOf("adjacent_time", "same_category"),
            forbiddenRelations = setOf("same_era", "same_reign", "variant_of")
        ),
        HISTORY_EVENT(
            allowedRelations = setOf("same_era", "same_reign", "adjacent_time"),
            forbiddenRelations = setOf("synonym", "variant_of")
        ),
        STATUTE_NUMERIC(
            allowedRelations = setOf("same_category", "adjacent_time"),
            forbiddenRelations = setOf("synonym", "variant_of")
        )
    }

    data class CandidateDistractor(
        val entryKey: String,
        val displayText: String,
        val answerSet: Set<String>,
        val relationsToTarget: Set<String> = emptySet(),
        val sameCategory: Boolean = true,
        val disputed: Boolean = false,
        val weight: Double = 0.5
    )

    data class DistractorSelectionResult(
        val mode: String, // "multiple_choice" | "tap_block" | "button_2"
        val options: List<String>,
        val distractors: List<CandidateDistractor>
    )

    private fun normalizeAnswerToken(token: String): String =
        Normalizer.normalize(token.trim().lowercase(), Normalizer.Form.NFC)
            .replace(Regex("\\s+"), " ")

    fun selectDistractors(
        targetKey: String,
        targetDisplay: String,
        targetAnswerSet: Set<String>,
        questionFacet: QuestionFacet,
        candidates: List<CandidateDistractor>,
        desiredDistractorCount: Int = 3
    ): DistractorSelectionResult {
        val normTargetAnswers = (targetAnswerSet + targetDisplay)
            .map { normalizeAnswerToken(it) }
            .filter { it.isNotEmpty() }
            .toSet()

        val validCandidates = mutableListOf<Pair<Int, CandidateDistractor>>()
        val seenDisplays = mutableSetOf(normalizeAnswerToken(targetDisplay))

        for (cand in candidates) {
            if (cand.disputed || cand.entryKey == targetKey) continue
            val candDisplayNorm = normalizeAnswerToken(cand.displayText)
            if (candDisplayNorm.isEmpty() || candDisplayNorm in seenDisplays) continue

            // 1. Forbidden Wins (T23)
            if (cand.relationsToTarget.intersect(questionFacet.forbiddenRelations).isNotEmpty()) {
                continue
            }

            // 2. Answer-Set Non-Overlap (T23)
            val candAnswersNorm = (cand.answerSet + cand.displayText)
                .map { normalizeAnswerToken(it) }
                .filter { it.isNotEmpty() }
                .toSet()
            if (candAnswersNorm.intersect(normTargetAnswers).isNotEmpty()) {
                continue
            }

            // 3. Priority tiering
            val tier = when {
                cand.relationsToTarget.intersect(questionFacet.allowedRelations).isNotEmpty() -> 1
                cand.sameCategory -> 2
                else -> continue
            }
            seenDisplays.add(candDisplayNorm)
            validCandidates.add(tier to cand)
        }

        val sorted = validCandidates
            .sortedWith(compareBy<Pair<Int, CandidateDistractor>> { it.first }
                .thenByDescending { it.second.weight }
                .thenBy { it.second.entryKey })
            .take(desiredDistractorCount)
            .map { it.second }

        return if (sorted.size < desiredDistractorCount) {
            val fallbackMode = if (targetDisplay.trim().length >= 2) "tap_block" else "button_2"
            DistractorSelectionResult(
                mode = fallbackMode,
                options = listOf(targetDisplay),
                distractors = sorted
            )
        } else {
            DistractorSelectionResult(
                mode = "multiple_choice",
                options = listOf(targetDisplay) + sorted.map { it.displayText },
                distractors = sorted
            )
        }
    }

    data class CompatNormalizedText(
        val nfcText: String,
        val compatCodepoints: List<String>
    )

    fun preserveCjkCompatBeforeNfc(rawText: String): CompatNormalizedText {
        val compat = mutableListOf<String>()
        var i = 0
        while (i < rawText.length) {
            val code = rawText.codePointAt(i)
            if (code in 0xF900..0xFAFF || code in 0x2F800..0x2FA1F) {
                val tag = "U+${code.toString(16).uppercase().padStart(4, '0')}"
                if (tag !in compat) compat.add(tag)
            }
            i += Character.charCount(code)
        }
        return CompatNormalizedText(
            nfcText = Normalizer.normalize(rawText, Normalizer.Form.NFC),
            compatCodepoints = compat
        )
    }

    private val CHOSEONG = arrayOf(
        'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ',
        'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    )
    private val JUNGSEONG = arrayOf(
        'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ',
        'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ'
    )
    private val JONGSEONG = arrayOf(
        null, 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ',
        'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ',
        'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    )

    fun decomposeHangulToJamo(text: String, keepSpaces: Boolean = true): String {
        val nfc = Normalizer.normalize(text.trim(), Normalizer.Form.NFC)
        val normalized = if (keepSpaces) {
            nfc.replace(Regex("\\s+"), " ")
        } else {
            nfc.replace(Regex("\\s+"), "")
        }
        val sb = StringBuilder()
        for (ch in normalized) {
            val code = ch.code
            if (code in 0xAC00..0xD7A3) {
                val offset = code - 0xAC00
                val cho = offset / 588
                val jung = (offset % 588) / 28
                val jong = offset % 28
                sb.append(CHOSEONG[cho])
                sb.append(JUNGSEONG[jung])
                JONGSEONG[jong]?.let { sb.append(it) }
            } else {
                sb.append(ch.lowercaseChar())
            }
        }
        return sb.toString()
    }

    private fun levenshtein(a: String, b: String): Int {
        if (a == b) return 0
        if (a.isEmpty()) return b.length
        if (b.isEmpty()) return a.length
        var prev = IntArray(b.length + 1) { it }
        for (i in 1..a.length) {
            val curr = IntArray(b.length + 1)
            curr[0] = i
            for (j in 1..b.length) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                curr[j] = min(min(prev[j] + 1, curr[j - 1] + 1), prev[j - 1] + cost)
            }
            prev = curr
        }
        return prev[b.length]
    }

    data class DictationGradeResult(
        val jamoSimilarityPct: Double,
        val jamoDistance: Int,
        val spacingExact: Boolean,
        val recommendedRating: Rating
    )

    fun gradeDictationJamo(
        userAnswer: String,
        expectedAnswer: String,
        ageTier: AgeTier = AgeTier.JUNIOR,
        hintUsed: Boolean = false
    ): DictationGradeResult {
        val expSpaced = decomposeHangulToJamo(expectedAnswer, keepSpaces = true)
        val usrSpaced = decomposeHangulToJamo(userAnswer, keepSpaces = true)
        if (expSpaced.isEmpty()) {
            return DictationGradeResult(0.0, 0, false, Rating.AGAIN)
        }
        if (usrSpaced.isEmpty()) {
            return DictationGradeResult(0.0, expSpaced.length, false, Rating.AGAIN)
        }
        val expNoSpace = decomposeHangulToJamo(expectedAnswer, keepSpaces = false)
        val usrNoSpace = decomposeHangulToJamo(userAnswer, keepSpaces = false)
        val spacingExact = (expSpaced == usrSpaced)
        val dist = levenshtein(usrNoSpace, expNoSpace)
        val maxLen = max(1, max(expNoSpace.length, usrNoSpace.length))
        val similarity = max(0.0, (1.0 - dist.toDouble() / maxLen.toDouble()) * 100.0)

        val rating = if (dist == 0 && spacingExact) {
            if (hintUsed) Rating.HARD else Rating.EASY
        } else if (dist == 0 && !spacingExact) {
            if (ageTier == AgeTier.JUNIOR && !hintUsed) Rating.GOOD else Rating.HARD
        } else if (dist <= 1 && similarity >= 85.0) {
            Rating.HARD
        } else {
            Rating.AGAIN
        }

        return DictationGradeResult(
            jamoSimilarityPct = similarity,
            jamoDistance = dist,
            spacingExact = spacingExact,
            recommendedRating = rating
        )
    }

    enum class TypedUnderstandingVerdict {
        EXACT,
        PARTIAL,
        UNKNOWN
    }

    data class TypedAnswerEvaluation(
        val verdict: TypedUnderstandingVerdict,
        val badgeLabel: String,
        val scorePct: Int,
        val recommendedRating: Rating,
        val matchedTerms: List<String>,
        val missingTerms: List<String>,
        val feedback: String
    )

    data class AnkiQueueCounts(
        val newCount: Int,
        val learnCount: Int,
        val reviewCount: Int
    )

    private val KO_EN_STOPWORDS = setOf(
        "the", "a", "an", "is", "are", "to", "of", "in", "on", "for", "and", "or",
        "이", "그", "저", "것", "수", "등", "및", "또는", "이다", "입니다", "하는", "있는"
    )

    private val KO_SUFFIXES = listOf(
        "에서는", "으로서", "입니다", "한다", "에서", "으로", "에게", "까지", "부터",
        "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과"
    )

    fun cleanExpectedAnswerText(rawText: String): String {
        var text = rawText
        val commentaryIdx = text.indexOf("💡 해설:")
        if (commentaryIdx >= 0) {
            text = text.substring(0, commentaryIdx)
        }
        val bracketMatches = Regex("【([^】]+)】").findAll(text).map { it.groupValues[1] }.toList()
        if (bracketMatches.isNotEmpty()) {
            return bracketMatches.joinToString(" ").trim()
        }
        text = text.replace(Regex("""\{\{c\d+::([^}:]+)(?:::[^}]+)?\}\}"""), "$1")
        text = text.replace(Regex("""[【】\[\]]"""), " ")
        return text.trim()
    }

    fun extractMeaningfulAnswerTokens(rawText: String): List<String> {
        val cleaned = cleanExpectedAnswerText(rawText).lowercase()
        val matches = Regex("[a-z0-9가-힣]+").findAll(cleaned).map { it.value }.toList()
        val result = mutableListOf<String>()
        for (word in matches) {
            var w = word
            for (sfx in KO_SUFFIXES) {
                if (w.length > sfx.length + 1 && w.endsWith(sfx)) {
                    w = w.substring(0, w.length - sfx.length)
                    break
                }
            }
            if (w.isNotEmpty() && w !in KO_EN_STOPWORDS && w !in result) {
                result.add(w)
            }
        }
        return result
    }

    private fun buildCharBigrams(rawText: String): Set<String> {
        val compact = cleanExpectedAnswerText(rawText).lowercase().replace(Regex("\\s+"), "")
        if (compact.isEmpty()) return emptySet()
        if (compact.length == 1) return setOf(compact)
        val set = mutableSetOf<String>()
        for (i in 0 until compact.length - 1) {
            set.add(compact.substring(i, i + 2))
        }
        return set
    }

    fun evaluateTypedAnswerUnderstanding(
        userAnswer: String,
        expectedAnswer: String
    ): TypedAnswerEvaluation {
        val userRaw = userAnswer.trim()
        val targetClean = cleanExpectedAnswerText(expectedAnswer)
        val primaryTarget = targetClean.replace(Regex("\\s*\\([^)]*\\)\\s*$"), "").trim().ifEmpty { targetClean }
        val refTokens = extractMeaningfulAnswerTokens(primaryTarget).ifEmpty { extractMeaningfulAnswerTokens(targetClean) }

        if (userRaw.isEmpty() || userRaw == "?" || userRaw == "모름" || userRaw == "모르겠어요") {
            val preview = refTokens.take(4).joinToString(", ").ifEmpty { primaryTarget.take(24) }
            return TypedAnswerEvaluation(
                verdict = TypedUnderstandingVerdict.UNKNOWN,
                badgeLabel = "❓ 모름 · 오답 (다시 학습 추천)",
                scorePct = 0,
                recommendedRating = Rating.AGAIN,
                matchedTerms = emptyList(),
                missingTerms = refTokens.take(5),
                feedback = "핵심 정답 키워드($preview)를 확인하고 '다시(10분)'로 복습하세요."
            )
        }

        val normUser = userRaw.lowercase().replace(Regex("[\\s()\\[\\],·]+"), "")
        val normTarget = targetClean.lowercase().replace(Regex("[\\s()\\[\\],·]+"), "")
        val normPrimary = primaryTarget.lowercase().replace(Regex("[\\s()\\[\\],·]+"), "")

        val userNums = Regex("\\d+").findAll(userRaw).map { it.value }.toSet()
        val targetNums = Regex("\\d+").findAll(targetClean).map { it.value }.toSet()
        val primaryNums = Regex("\\d+").findAll(primaryTarget).map { it.value }.toSet()
        val numericConflict = (primaryNums.isNotEmpty() && !userNums.containsAll(primaryNums)) ||
            (userNums.isNotEmpty() && targetNums.isNotEmpty() && !targetNums.containsAll(userNums))

        if (!numericConflict && normUser.isNotEmpty() && normTarget.isNotEmpty() &&
            (normUser == normTarget ||
                normUser == normPrimary ||
                (normUser.length >= 2 && normPrimary.contains(normUser) && normUser.length.toDouble() / normPrimary.length.toDouble() >= 0.85) ||
                (normUser.length >= 2 && normTarget.contains(normUser) && normUser.length.toDouble() / normTarget.length.toDouble() >= 0.85))
        ) {
            return TypedAnswerEvaluation(
                verdict = TypedUnderstandingVerdict.EXACT,
                badgeLabel = "🎯 정답 · 완벽 이해",
                scorePct = 100,
                recommendedRating = Rating.EASY,
                matchedTerms = refTokens,
                missingTerms = emptyList(),
                feedback = "✅ 정답을 정확하게 이해하고 인출했습니다! '알맞음' 또는 '쉬움'을 눌러주세요."
            )
        }

        val userTokens = extractMeaningfulAnswerTokens(userRaw).toSet()
        val userLower = userRaw.lowercase()
        val matched = mutableListOf<String>()
        val missing = mutableListOf<String>()
        for (tok in refTokens) {
            if (tok in userTokens || userLower.contains(tok)) {
                matched.add(tok)
            } else {
                missing.add(tok)
            }
        }
        if (numericConflict) {
            missing.addAll(targetNums - userNums)
        }

        val tokenRecall = if (refTokens.isNotEmpty()) matched.size.toDouble() / refTokens.size.toDouble() else 0.0
        val refBigrams = buildCharBigrams(primaryTarget)
        val userBigrams = buildCharBigrams(userRaw)
        val bigramOverlap = if (refBigrams.isNotEmpty() && userBigrams.isNotEmpty()) {
            refBigrams.intersect(userBigrams).size.toDouble() / refBigrams.size.toDouble()
        } else {
            0.0
        }

        val jamoGrade = gradeDictationJamo(userRaw, primaryTarget)
        val combinedRaw = max(
            (tokenRecall * 0.65 + bigramOverlap * 0.35) * 100.0,
            if (jamoGrade.jamoDistance <= 2) jamoGrade.jamoSimilarityPct else 0.0
        )
        var scorePct = combinedRaw.toInt().coerceIn(0, 100)
        if (numericConflict) {
            scorePct = min(scorePct, 55)
        }

        if (!numericConflict && scorePct >= 82 && missing.isEmpty()) {
            return TypedAnswerEvaluation(
                verdict = TypedUnderstandingVerdict.EXACT,
                badgeLabel = "🎯 정답 · 완벽 이해",
                scorePct = scorePct,
                recommendedRating = if (scorePct >= 94) Rating.EASY else Rating.GOOD,
                matchedTerms = matched,
                missingTerms = missing,
                feedback = "✅ 핵심 개념(${matched.take(3).joinToString(", ")})을 정확히 이해하고 있습니다!"
            )
        }

        if (scorePct >= 35 || (matched.isNotEmpty() && missing.isNotEmpty())) {
            val matchedPreview = matched.take(3).joinToString(", ").ifEmpty { "유사 발음/철자" }
            val missingPreview = missing.take(3).joinToString(", ").ifEmpty { "세부 철자" }
            val floorScore = if (tokenRecall >= 0.45) 46 else 40
            return TypedAnswerEvaluation(
                verdict = TypedUnderstandingVerdict.PARTIAL,
                badgeLabel = "💡 약간 이해 · 부분 일치",
                scorePct = max(floorScore, scorePct),
                recommendedRating = Rating.HARD,
                matchedTerms = matched,
                missingTerms = missing,
                feedback = "💡 일부분($matchedPreview)은 이해했지만 핵심 키워드($missingPreview) 보강이 필요합니다. '어려움'을 추천합니다."
            )
        }

        val missPreview = (if (missing.isNotEmpty()) missing else listOf(targetClean.take(24))).take(3).joinToString(", ")
        return TypedAnswerEvaluation(
            verdict = TypedUnderstandingVerdict.UNKNOWN,
            badgeLabel = "❓ 모름 · 오답 (재학습 필요)",
            scorePct = scorePct,
            recommendedRating = Rating.AGAIN,
            matchedTerms = matched,
            missingTerms = if (missing.isNotEmpty()) missing else listOf(targetClean.take(24)),
            feedback = "❓ 정답과 차이가 큽니다. 핵심어($missPreview)를 확인하고 '다시'로 복습하세요."
        )
    }

    fun extractCleanTargetAnswer(frontText: String, backText: String): Pair<String, String> {
        val clozeMatch = Regex("\\{\\{c\\d+::([^:}]+)(?:::[^}]*)?\\}\\}").find(frontText)
        val rawBack = backText.trim()
        val lines = rawBack.lines().map { it.trim() }.filter { it.isNotEmpty() }
        val primaryLine = lines.firstOrNull().orEmpty()
        val restLines = lines.drop(1).joinToString("\n").replace(Regex("^💡\\s*해설\\s*:\\s*"), "").trim()

        if (clozeMatch != null) {
            val clozeAns = clozeMatch.groupValues[1].trim()
            val extra = when {
                restLines.isNotEmpty() && primaryLine != clozeAns -> "$primaryLine\n$restLines"
                restLines.isNotEmpty() -> restLines
                primaryLine != clozeAns -> primaryLine
                else -> ""
            }
            return clozeAns to extra
        }

        if (primaryLine.contains(" — ")) {
            val parts = primaryLine.split(" — ", limit = 2)
            val target = parts[0].trim()
            val extra = listOf(parts[1].trim(), restLines).filter { it.isNotEmpty() }.joinToString("\n")
            return target to extra
        }

        return primaryLine to restLines
    }

    fun generateProgressiveHint(frontText: String, backText: String, step: Int = 1): String {
        val (target, extra) = extractCleanTargetAnswer(frontText, backText)
        val clean = target.replace(Regex("\\s*\\([^)]*\\)\\s*$"), "").trim().ifEmpty { target.trim() }
        if (clean.isEmpty()) return "💡 핵심 개념을 떠올려 보세요."

        val maskedChars = mutableListOf<String>()
        var nonSpaceLen = 0
        for (ch in clean) {
            if (ch.isWhitespace()) {
                maskedChars.add(" ")
                continue
            }
            nonSpaceLen += 1
            val code = ch.code
            when {
                code in 0xAC00..0xD7A3 -> {
                    val choIdx = (code - 0xAC00) / 588
                    maskedChars.add(CHOSEONG[choIdx].toString())
                }
                ch.isLetter() -> {
                    maskedChars.add(if (nonSpaceLen == 1) ch.toString() else "_")
                }
                else -> maskedChars.add("○")
            }
        }
        val maskStr = maskedChars.joinToString(" ").replace(Regex("\\s+"), " ").trim()
        if (step <= 1) {
            return "💡 1단계 힌트 (초성·철자 ${nonSpaceLen}자): $maskStr"
        }
        val firstReveal = clean.first()
        val safeExtra = if (extra.isNotEmpty()) {
            extra.replace(Regex(Regex.escape(clean), RegexOption.IGNORE_CASE), "___").take(60)
        } else {
            "첫 글자 '$firstReveal'로 시작하는 핵심 개념"
        }
        return "💡 2단계 힌트 (첫 글자 공개): '$firstReveal...' · 힌트: $safeExtra"
    }

    fun <T> interleaveStudyQueue(
        items: List<T>,
        bucketSelector: (T) -> String,
        seed: Int = 42
    ): List<T> {
        if (items.size <= 2) return items
        val buckets = linkedMapOf<String, MutableList<T>>()
        for (item in items) {
            val key = bucketSelector(item).ifBlank { "default" }
            buckets.getOrPut(key) { mutableListOf() }.add(item)
        }
        for ((k, group) in buckets) {
            buckets[k] = group.sortedBy { ((it.hashCode() * 31) xor seed) and 0x7fffffff }.toMutableList()
        }
        val keys = buckets.keys.toList()
        if (keys.size <= 1) {
            return buckets.values.flatten()
        }
        val interleaved = mutableListOf<T>()
        var lastKey: String? = null
        var streak = 0
        val total = items.size
        while (interleaved.size < total) {
            val activeKeys = keys.filter { !buckets[it].isNullOrEmpty() }
            if (activeKeys.isEmpty()) break
            val eligible = if (activeKeys.size > 1 && lastKey != null && streak >= 2) {
                activeKeys.filter { it != lastKey }.ifEmpty { activeKeys }
            } else {
                activeKeys
            }
            val chosenKey = eligible.maxWithOrNull(
                compareBy<String> { buckets[it]!!.size * 10 + if (it != lastKey) 4 else 0 }
                    .thenBy { ((it.hashCode() * 17) xor seed) and 0x7fffffff }
            ) ?: eligible.first()
            val nextItem = buckets[chosenKey]!!.removeAt(0)
            interleaved.add(nextItem)
            if (chosenKey == lastKey) {
                streak += 1
            } else {
                lastKey = chosenKey
                streak = 1
            }
        }
        return interleaved
    }

    fun computeAnkiQueueCounts(statesAndLapses: List<Pair<String, Int>>): AnkiQueueCounts {
        var newCount = 0
        var learnCount = 0
        var reviewCount = 0
        for ((stateRaw, lapses) in statesAndLapses) {
            val st = stateRaw.trim().lowercase()
            if (st == "new") {
                newCount += 1
            } else if (st == "learning" || st == "relearning" || lapses > 0) {
                learnCount += 1
            } else {
                reviewCount += 1
            }
        }
        return AnkiQueueCounts(newCount = newCount, learnCount = learnCount, reviewCount = reviewCount)
    }

    data class RatingGuardResult(
        val allowedRatings: List<Rating>,
        val recommendedRating: Rating?,
        val lockedReason: String,
        val bannerText: String
    )

    fun resolveCardSolveMode(
        solveMode: String = "adaptive",
        reps: Int = 0,
        lapses: Int = 0,
        state: String = ""
    ): String {
        val norm = solveMode.trim().lowercase()
        if (norm in setOf("flip", "choice", "typing")) return norm
        return if (reps <= 0 || state.trim().lowercase() == "new") "choice" else "typing"
    }

    fun resolveAllowedRatings(
        isRevealed: Boolean,
        choiceCorrect: Boolean? = null,
        typedVerdict: TypedUnderstandingVerdict? = null,
        hintStep: Int = 0,
        dontKnow: Boolean = false,
        ageTier: AgeTier = AgeTier.ADULT
    ): RatingGuardResult {
        if (!isRevealed) {
            return RatingGuardResult(
                allowedRatings = emptyList(),
                recommendedRating = null,
                lockedReason = "pre_reveal",
                bannerText = "정답을 확인하기 전에는 난이도 평가를 누를 수 없습니다."
            )
        }
        if (dontKnow || choiceCorrect == false || typedVerdict == TypedUnderstandingVerdict.UNKNOWN) {
            return RatingGuardResult(
                allowedRatings = listOf(Rating.AGAIN),
                recommendedRating = Rating.AGAIN,
                lockedReason = "wrong_or_unknown",
                bannerText = "🔴 오답·모름 상태에서는 기억 왜곡 방지를 위해 '다시(1)'만 선택할 수 있습니다."
            )
        }
        if (hintStep >= 1) {
            return RatingGuardResult(
                allowedRatings = listOf(Rating.AGAIN, Rating.HARD),
                recommendedRating = Rating.HARD,
                lockedReason = "hint_assisted_cap",
                bannerText = "🟡 힌트를 사용했으므로 최대 평가가 '어려움(2)'으로 제한됩니다."
            )
        }
        if (typedVerdict == TypedUnderstandingVerdict.PARTIAL) {
            return RatingGuardResult(
                allowedRatings = listOf(Rating.AGAIN, Rating.HARD, Rating.GOOD),
                recommendedRating = Rating.HARD,
                lockedReason = "partial_recall_cap",
                bannerText = "🟡 부분 인출 상태이므로 '쉬움(4)'이 잠기며 '어려움(2)'을 권장합니다."
            )
        }
        if (ageTier == AgeTier.JUNIOR) {
            return RatingGuardResult(
                allowedRatings = listOf(Rating.AGAIN, Rating.HARD, Rating.GOOD),
                recommendedRating = Rating.GOOD,
                lockedReason = "none",
                bannerText = "🟢 스스로 인출 성공! '알겠음(3)'을 추천합니다."
            )
        }
        return RatingGuardResult(
            allowedRatings = listOf(Rating.AGAIN, Rating.HARD, Rating.GOOD, Rating.EASY),
            recommendedRating = Rating.GOOD,
            lockedReason = "none",
            bannerText = "🟢 무보조 인출 성공! 기억 난이도에 맞춰 평가하세요 ('보통 3' 추천)."
        )
    }

    fun <T> deduplicateSessionSiblings(
        items: List<T>,
        tagsSelector: (T) -> Collection<String>,
        stateSelector: (T) -> String = { "new" }
    ): List<T> {
        if (items.size <= 1) return items

        fun conceptKey(item: T): String? =
            tagsSelector(item).firstOrNull { it.startsWith("concept:") && it.length > 8 }

        fun priorityScore(item: T): Int {
            val st = stateSelector(item).trim().lowercase()
            val stateRank = when (st) {
                "learning", "relearning" -> 0
                "review" -> 1
                else -> 2
            }
            val tags = tagsSelector(item)
            val diffRank = when {
                "diff_lv1" in tags || "lv1" in tags -> 0
                "diff_lv2" in tags || "lv2" in tags -> 1
                else -> 2
            }
            return stateRank * 10 + diffRank
        }

        val bestByConcept = LinkedHashMap<String, T>()
        for (item in items) {
            val ckey = conceptKey(item) ?: continue
            val prev = bestByConcept[ckey]
            if (prev == null || priorityScore(item) < priorityScore(prev)) {
                bestByConcept[ckey] = item
            }
        }

        val seen = HashSet<String>()
        val result = ArrayList<T>(items.size)
        for (item in items) {
            val ckey = conceptKey(item)
            if (ckey == null) {
                result.add(item)
                continue
            }
            if (seen.add(ckey)) {
                result.add(bestByConcept.getValue(ckey))
            }
        }
        return result
    }

    // =========================================================================
    // Gate T43: Type-Homogeneous 4-Choice Distractor Isolation & Question-Type Filter
    // =========================================================================
    data class CardQuestionType(
        val categoryKey: String, // "vocab" | "grammar" | "hanja" | "history_sci"
        val facetKey: String,    // "eng_vocab_meaning" | "eng_vocab_word" | "eng_grammar" | "hanja_hun_eum" | "hanja_char" | "idiom" | "history" | "science" | "ko_dictation"
        val badgeLabel: String,
        val shortLabel: String
    )

    private val TYPE_FALLBACK_DISTRACTOR_BANK: Map<String, List<String>> = mapOf(
        "eng_vocab_meaning" to listOf(
            "소개하다",
            "가장 좋아하는",
            "악기",
            "함께",
            "맛있는",
            "전통적인",
            "자원봉사하다",
            "의무적인",
            "준수하다",
            "경험하다"
        ),
        "eng_vocab_word" to listOf(
            "introduce",
            "favorite",
            "instrument",
            "together",
            "delicious",
            "traditional",
            "volunteer",
            "mandatory",
            "comply",
            "communicate"
        ),
        "eng_grammar" to listOf(
            "doesn't (does not) + 동사원형",
            "am / are / is + 동사원형-ing (현재진행형)",
            "감각동사(look/sound/smell/taste/feel) + 형용사 보어",
            "have / has + 과거분사(p.p.) (현재완료)",
            "조동사(will/can/must) + 동사원형",
            "전치사(at/in/of) + 동명사(-ing)",
            "주격 관계대명사 who / which / that + 불완전 절"
        ),
        "hanja_hun_eum" to listOf(
            "배울 학",
            "학교 교",
            "날 생",
            "나라 국",
            "백성 민",
            "가르칠 교",
            "집 가",
            "마음 심",
            "이룰 성",
            "믿을 신"
        ),
        "hanja_char" to listOf("學", "校", "生", "國", "民", "敎", "家", "心", "成", "信"),
        "idiom" to listOf(
            "대기만성 (大器晩成)",
            "역지사지 (易地思之)",
            "유비무환 (有備無患)",
            "일석이조 (一石二鳥)",
            "우공이산 (愚公移山)"
        ),
        "history" to listOf(
            "강화도 조약",
            "함무라비 법전",
            "훈민정음",
            "경국대전",
            "갑신정변",
            "동학 농민 운동",
            "독립협회",
            "3·1 운동"
        ),
        "science" to listOf(
            "공유 결합",
            "이온 결합",
            "활성화 에너지",
            "미토콘드리아",
            "옴의 법칙 (V = IR)",
            "원자성·일관성·격리성·지속성"
        ),
        "ko_dictation" to listOf(
            "맑고 따뜻합니다",
            "할머니께 썼습니다",
            "조용히 읽어요",
            "깨끗이 씻어요",
            "같이 걸어요"
        ),
        "general_concept" to listOf(
            "핵심 원리 및 개념 정의",
            "상호 배제와 동기화 조건",
            "원인과 결과의 상관관계",
            "필수 성립 요건 및 예외 조항",
            "구조적 특징과 작동 원리"
        )
    )

    fun classifyCardQuestionType(
        frontText: String,
        backText: String,
        tags: Collection<String> = emptyList()
    ): CardQuestionType {
        val front = frontText.trim()
        val back = backText.trim()
        val target = extractCleanTargetAnswer(front, back).first.trim().ifEmpty { back }
        val tagStr = tags.joinToString(" ").lowercase()

        val hasCjk = (front + " " + target).any { it.code in 0x4E00..0x9FFF }
        val isAsciiTarget = target.isNotEmpty() &&
            target.all { it.code < 128 && (it.isLetter() || it in " ~'.,?!-") } &&
            target.any { it.isLetter() }

        if (
            "role:key_grammar" in tagStr ||
            "grammar" in tagStr ||
            "핵심문법" in front ||
            "[문법" in front ||
            "핵심 문법" in front ||
            "문법 빈칸" in front ||
            "어법" in front ||
            "동사원형" in target ||
            "과거분사" in target ||
            "현재분사" in target ||
            "형용사 보어" in target ||
            "관계대명사" in target ||
            "현재진행형" in target
        ) {
            return CardQuestionType(
                categoryKey = "grammar",
                facetKey = "eng_grammar",
                badgeLabel = "📐 영문법·어법",
                shortLabel = "문법"
            )
        }

        if ("idiom" in tagStr || "사자성어" in front || "고사성어" in front) {
            return CardQuestionType(
                categoryKey = "hanja",
                facetKey = "idiom",
                badgeLabel = "📜 사자성어",
                shortLabel = "한자·성어"
            )
        }

        if ("hanja" in tagStr || "[한자" in front || hasCjk) {
            if (target.length <= 2 && target.any { it.code in 0x4E00..0x9FFF }) {
                return CardQuestionType(
                    categoryKey = "hanja",
                    facetKey = "hanja_char",
                    badgeLabel = "漢字 한자 자형",
                    shortLabel = "한자·성어"
                )
            }
            return CardQuestionType(
                categoryKey = "hanja",
                facetKey = "hanja_hun_eum",
                badgeLabel = "漢字 한자 훈음",
                shortLabel = "한자·성어"
            )
        }

        if ("dictation" in tagStr || "받아쓰기" in front || "맞춤법" in front) {
            return CardQuestionType(
                categoryKey = "vocab",
                facetKey = "ko_dictation",
                badgeLabel = "✏️ 맞춤법·받아쓰기",
                shortLabel = "단어·어휘"
            )
        }

        val combinedLower = "$front $back $tagStr".lowercase()
        val historyKeywords = listOf(
            "한국사", "세계사", "역사", "조약", "정변", "운동", "봉기", "독립협회",
            "법전", "훈민정음", "경국대전", "카스트제", "왕조", "세조", "세종", "성종",
            "전봉준", "김옥균", "서재필", "개화파", "조선", "일제", "바빌로니아"
        )
        if (
            "hist" in tagStr ||
            "khist" in tagStr ||
            "kh_" in tagStr ||
            historyKeywords.any { it in combinedLower }
        ) {
            return CardQuestionType(
                categoryKey = "history_sci",
                facetKey = "history",
                badgeLabel = "🏛️ 역사 개념",
                shortLabel = "역사·과학·전공"
            )
        }

        val scienceKeywords = listOf(
            "결합", "에너지", "트랜잭션", "헌법", "법칙", "미토콘드리아",
            "교착상태", "계층", "정규화", "세포", "염색체", "전자쌍"
        )
        if (
            "sci" in tagStr ||
            "law" in tagStr ||
            "cert" in tagStr ||
            scienceKeywords.any { it in combinedLower }
        ) {
            return CardQuestionType(
                categoryKey = "history_sci",
                facetKey = "science",
                badgeLabel = "🔬 과학·전공 개념",
                shortLabel = "역사·과학·전공"
            )
        }

        if (isAsciiTarget) {
            return CardQuestionType(
                categoryKey = "vocab",
                facetKey = "eng_vocab_word",
                badgeLabel = "🔤 영단어 스펠링·빈칸",
                shortLabel = "단어·어휘"
            )
        }

        val frontWithoutCloze = front.replace(
            Regex("""\{\{c\d+::|::[^}]*\}\}|\}\}|\[Lv\.\d+[^\]]*\]|\bLv\.\d+\b""", RegexOption.IGNORE_CASE),
            " "
        )
        val tagStrWithoutDefaultRole = tagStr.replace("role:core_vocab", " ")
        val hasEnglishInFront = frontWithoutCloze.any { it.code < 128 && it.isLetter() }
        val hasVocabSignal = hasEnglishInFront ||
            listOf("eng", "vocab", "word", "toeic", "teps", "toefl", "opic", "lang", "mid1", "elem").any { it in tagStrWithoutDefaultRole } ||
            listOf("영단어", "어휘", "단어", "숙어").any { it in front }
        if (!hasVocabSignal) {
            return CardQuestionType(
                categoryKey = "history_sci",
                facetKey = "general_concept",
                badgeLabel = "💡 핵심 개념·정의",
                shortLabel = "역사·과학·전공"
            )
        }

        return CardQuestionType(
            categoryKey = "vocab",
            facetKey = "eng_vocab_meaning",
            badgeLabel = "📘 단어 뜻·어휘",
            shortLabel = "단어·어휘"
        )
    }

    private fun seededFisherYates(items: List<String>, seedVal: Long): List<String> {
        val arr = items.toMutableList()
        var state = ((kotlin.math.abs(seedVal).let { if (it == 0L) 1L else it }) * 1664525L + 1013904223L) and 0xFFFFFFFFL
        for (i in arr.size - 1 downTo 1) {
            state = (state * 1664525L + 1013904223L) and 0xFFFFFFFFL
            val j = (state % (i + 1)).toInt()
            val tmp = arr[i]
            arr[i] = arr[j]
            arr[j] = tmp
        }
        return arr
    }

    fun buildTypeMatchedQuizOptions(
        cardId: Long,
        frontText: String,
        backText: String,
        tags: Collection<String> = emptyList(),
        candidatePool: List<Triple<Long, String, String>>,
        requiredOptions: Int = 4,
        reps: Int = 0
    ): List<String> {
        val qtype = classifyCardQuestionType(frontText, backText, tags)
        val facetKey = qtype.facetKey
        val targetAnswer = extractCleanTargetAnswer(frontText, backText).first.trim().ifEmpty { backText.trim() }

        val distractors = mutableListOf<String>()
        val seenNorm = mutableSetOf(targetAnswer.lowercase())
        val poolCandidates = mutableListOf<String>()

        for ((otherId, otherFront, otherBack) in candidatePool) {
            if (otherId == cardId && cardId != 0L) continue
            val otherType = classifyCardQuestionType(otherFront, otherBack)
            if (otherType.facetKey != facetKey) continue
            val cand = extractCleanTargetAnswer(otherFront, otherBack).first.trim().ifEmpty { otherBack.trim() }
            if (cand.isEmpty()) continue
            val norm = cand.lowercase()
            if (norm in seenNorm) continue
            seenNorm.add(norm)
            poolCandidates.add(cand)
        }

        val shuffledPool = seededFisherYates(poolCandidates, cardId * 31L + reps * 997L + 17L)
        distractors.addAll(shuffledPool.take(max(0, requiredOptions - 1)))

        val fallbackPool = seededFisherYates(
            TYPE_FALLBACK_DISTRACTOR_BANK[facetKey]
                ?: TYPE_FALLBACK_DISTRACTOR_BANK.getValue("eng_vocab_meaning"),
            cardId * 73L + reps * 389L + 53L
        )
        for (cand in fallbackPool) {
            if (distractors.size >= requiredOptions - 1) break
            val norm = cand.lowercase()
            if (norm in seenNorm) continue
            seenNorm.add(norm)
            distractors.add(cand)
        }

        val rawOptions = listOf(targetAnswer) + distractors.take(max(0, requiredOptions - 1))
        return seededFisherYates(rawOptions, cardId * 131L + reps * 521L + 2026L)
    }
}
