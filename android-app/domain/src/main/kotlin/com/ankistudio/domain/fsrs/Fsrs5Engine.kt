package com.ankistudio.domain.fsrs

import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt

/**
 * Pure Kotlin FSRS-5 (DSR Memory Model) Engine + Cloze Renderer.
 * Strictly zero `android.*` imports — runs on any JVM / Android / KMP target.
 */
object Fsrs5Engine {

    val DEFAULT_FSRS5_WEIGHTS: DoubleArray = doubleArrayOf(
        0.40255, 1.18385, 3.17300, 15.69105,
        7.19490, 0.53450, 1.46040, 0.00460,
        1.54575, 0.11920, 1.01925, 1.93950,
        0.11000, 0.29605, 2.26980, 0.23150,
        2.98980, 0.51655, 0.66210
    )

    private const val DECAY = -0.5
    private const val FACTOR = 19.0 / 81.0
    private val CLOZE_TAG_RE = Regex("""\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}""", RegexOption.DOT_MATCHES_ALL)

    enum class Rating(val code: Int) {
        AGAIN(1),
        HARD(2),
        GOOD(3),
        EASY(4);

        companion object {
            fun fromCode(code: Int): Rating = entries.firstOrNull { it.code == code }
                ?: throw IllegalArgumentException("Invalid FSRS rating code: $code")
        }
    }

    data class CardMemoryState(
        val difficulty: Double = 0.0,
        val stability: Double = 0.0,
        val reps: Int = 0,
        val lapses: Int = 0,
        val state: String = "new"
    )

    data class ReviewOutcome(
        val rating: Rating,
        val memory: CardMemoryState,
        val scheduledDays: Int,
        val scheduledLabel: String,
        val retrievabilityBefore: Double
    )

    fun extractClozeOrdinals(frontText: String): List<Int> {
        return CLOZE_TAG_RE.findAll(frontText)
            .mapNotNull { it.groupValues[1].toIntOrNull() }
            .filter { it > 0 }
            .distinct()
            .sorted()
            .toList()
    }

    fun renderClozeCard(frontText: String, ordinal: Int = 1, reveal: Boolean = false): String {
        return CLOZE_TAG_RE.replace(frontText) { match ->
            val ord = match.groupValues[1].toIntOrNull() ?: 1
            val answer = match.groupValues[2]
            val hint = match.groupValues.getOrNull(3)?.takeIf { it.isNotEmpty() }
            if (ord == ordinal) {
                if (reveal) {
                    "[$answer]"
                } else if (hint != null) {
                    "[...:$hint]"
                } else {
                    "[...]"
                }
            } else {
                answer
            }
        }
    }

    private fun clampDifficulty(d: Double): Double = max(1.0, min(10.0, d))
    private fun clampStability(s: Double): Double = max(0.1, min(36500.0, s))

    fun initialStability(rating: Rating, w: DoubleArray = DEFAULT_FSRS5_WEIGHTS): Double =
        clampStability(w[rating.code - 1])

    fun initialDifficulty(rating: Rating, w: DoubleArray = DEFAULT_FSRS5_WEIGHTS): Double {
        val g = rating.code.toDouble()
        val d0 = w[4] - exp(w[5] * (g - 1.0)) + 1.0
        return clampDifficulty(d0)
    }

    fun nextDifficulty(d: Double, rating: Rating, w: DoubleArray = DEFAULT_FSRS5_WEIGHTS): Double {
        val g = rating.code.toDouble()
        val deltaD = -w[6] * (g - 3.0)
        val dPrime = d + deltaD * ((10.0 - d) / 9.0)
        val d0Easy = initialDifficulty(Rating.EASY, w)
        val dNext = w[7] * d0Easy + (1.0 - w[7]) * dPrime
        return clampDifficulty(dNext)
    }

    fun computeRetrievability(elapsedDays: Double, stability: Double): Double {
        if (stability <= 0.0) return 0.0
        val t = max(0.0, elapsedDays)
        val r = (1.0 + FACTOR * (t / stability)).pow(DECAY)
        return max(0.0, min(1.0, r))
    }

    fun computeNextInterval(
        stability: Double,
        desiredRetention: Double = 0.90,
        maxInterval: Int = 36500
    ): Int {
        val r = max(0.70, min(0.99, desiredRetention))
        val s = clampStability(stability)
        val rawDays = (s / FACTOR) * (r.pow(1.0 / DECAY) - 1.0)
        return max(1, min(maxInterval, rawDays.roundToInt()))
    }

    fun stepFsrs(
        memory: CardMemoryState,
        rating: Rating,
        elapsedDays: Double = 0.0,
        desiredRetention: Double = 0.90,
        w: DoubleArray = DEFAULT_FSRS5_WEIGHTS
    ): ReviewOutcome {
        val isNew = memory.reps == 0 || memory.state == "new" || memory.stability <= 0.0
        val rBefore: Double
        val dAfter: Double
        val sAfter: Double
        var lapses = memory.lapses
        val nextState: String

        if (isNew) {
            rBefore = 1.0
            dAfter = initialDifficulty(rating, w)
            sAfter = initialStability(rating, w)
            if (rating == Rating.AGAIN) {
                nextState = "learning"
            } else {
                nextState = "review"
            }
        } else {
            rBefore = computeRetrievability(elapsedDays, memory.stability)
            dAfter = nextDifficulty(memory.difficulty, rating, w)
            if (rating == Rating.AGAIN) {
                if (memory.state == "review") {
                    lapses += 1
                }
                nextState = "relearning"
                val sForget = w[11] *
                    dAfter.pow(-w[12]) *
                    ((memory.stability + 1.0).pow(w[13]) - 1.0) *
                    exp(w[14] * (1.0 - rBefore))
                sAfter = clampStability(min(memory.stability, sForget))
            } else {
                nextState = "review"
                val hardPenalty = if (rating == Rating.HARD) w[15] else 1.0
                val easyBonus = if (rating == Rating.EASY) w[16] else 1.0
                val inc = exp(w[8]) *
                    (11.0 - dAfter) *
                    memory.stability.pow(-w[9]) *
                    (exp(w[10] * (1.0 - rBefore)) - 1.0) *
                    hardPenalty *
                    easyBonus
                sAfter = clampStability(memory.stability * (1.0 + inc))
            }
        }

        val scheduledDays: Int
        val label: String
        if (rating == Rating.AGAIN) {
            scheduledDays = 0
            label = "10m"
        } else {
            var days = computeNextInterval(sAfter, desiredRetention)
            if (rating == Rating.HARD) days = max(1, days)
            else if (rating == Rating.GOOD) days = max(2, days)
            else if (rating == Rating.EASY) days = max(4, days)
            scheduledDays = days
            label = "${days}d"
        }

        return ReviewOutcome(
            rating = rating,
            memory = CardMemoryState(
                difficulty = (dAfter * 10000.0).roundToInt() / 10000.0,
                stability = (sAfter * 10000.0).roundToInt() / 10000.0,
                reps = memory.reps + 1,
                lapses = lapses,
                state = nextState
            ),
            scheduledDays = scheduledDays,
            scheduledLabel = label,
            retrievabilityBefore = (rBefore * 10000.0).roundToInt() / 10000.0
        )
    }
}
