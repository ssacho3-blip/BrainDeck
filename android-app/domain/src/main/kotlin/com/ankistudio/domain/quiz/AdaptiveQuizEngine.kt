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
}
