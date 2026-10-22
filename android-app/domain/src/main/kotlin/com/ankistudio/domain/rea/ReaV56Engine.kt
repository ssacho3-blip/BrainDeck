package com.ankistudio.domain.rea

import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToLong

object ReaV56Engine {
    const val DAY_MS: Long = 86_400_000L

    val DEFAULT_FSRS5_PARAMS: DoubleArray = doubleArrayOf(
        0.40255, 1.18385, 3.17300, 15.69105, 7.19490,
        0.53450, 1.46040, 0.00460, 1.54575, 0.11920,
        1.01925, 1.93950, 0.11000, 0.29605, 2.26980,
        0.23150, 2.98980, 0.51655, 0.66210
    )

    data class ReviewEvent(
        val eventId: String,
        val cardId: String,
        val kind: String,
        val rating: Int?,
        val tsMs: Long,
        val deviceId: String,
        val idemKey: String,
        val voids: String? = null
    )

    data class CardStateV56(
        val s: Double,
        val d: Double,
        val dueMs: Long,
        val lastTsMs: Long?,
        val reps: Int,
        val lapses: Int
    )

    data class SummarySheetRow(
        val index: Int,
        val prompt: String,
        val cleanAnswer: String,
        val masked: Boolean = true
    )

    fun quantize1e6(x: Double): Double {
        return (x * 1_000_000.0).roundToLong().toDouble() / 1_000_000.0
    }

    private fun clamp(v: Double, lo: Double, hi: Double): Double = max(lo, min(hi, v))

    fun foldReviewEvents(
        events: List<ReviewEvent>,
        params: DoubleArray = DEFAULT_FSRS5_PARAMS
    ): CardStateV56 {
        require(params.size >= 19) { "FSRS-5 params must contain 19 weights" }
        val ordered = events.sortedWith(compareBy<ReviewEvent> { it.tsMs }.thenBy { it.eventId })
        val seenIdem = mutableSetOf<String>()
        val voidedIds = mutableSetOf<String>()
        val deduped = mutableListOf<ReviewEvent>()

        for (ev in ordered) {
            require(ev.eventId.isNotBlank() && ev.idemKey.isNotBlank()) { "eventId and idemKey must not be blank" }
            if (!seenIdem.add(ev.idemKey)) continue
            if (ev.kind == "VOID") {
                ev.voids?.let { voidedIds.add(it) }
                continue
            }
            deduped.add(ev)
        }

        var s = 0.0
        var d = 0.0
        var dueMs = 0L
        var lastTsMs: Long? = null
        var reps = 0
        var lapses = 0

        for (ev in deduped) {
            if (ev.eventId in voidedIds) continue
            if (ev.kind == "CRAM") continue

            val g = (ev.rating ?: 3).coerceIn(1, 4)
            val nowMs = ev.tsMs

            if (reps == 0 || lastTsMs == null || s <= 0.0) {
                s = quantize1e6(max(0.1, params[g - 1]))
                val d0 = params[4] - exp(params[5] * (g - 1)) + 1.0
                d = quantize1e6(clamp(d0, 1.0, 10.0))
                reps = 1
                lastTsMs = nowMs
                val ivlDays = max(1L, s.roundToLong())
                dueMs = nowMs + ivlDays * DAY_MS
                continue
            }

            val elapsedDays = max(0.0, (nowMs - lastTsMs).toDouble() / DAY_MS.toDouble())
            val rNow = quantize1e6((1.0 + (19.0 / 81.0) * (elapsedDays / max(0.1, s))).pow(-0.5))

            val d0Good = params[4] - exp(params[5] * 2.0) + 1.0
            val deltaD = -params[6] * (g - 3.0)
            val dPrime = d + deltaD * ((10.0 - d) / 9.0)
            val dNext = quantize1e6(clamp(params[7] * d0Good + (1.0 - params[7]) * dPrime, 1.0, 10.0))

            val sNext = if (elapsedDays < 1.0 && ev.kind == "REVIEW_AHEAD") {
                if (g == 1) lapses += 1
                quantize1e6(clamp(s * exp(params[17] * (g - 3.0 + params[18])), 0.1, 36500.0))
            } else if (g == 1) {
                lapses += 1
                val sFail = params[11] *
                    dNext.pow(-params[12]) *
                    ((s + 1.0).pow(params[13]) - 1.0) *
                    exp(params[14] * (1.0 - rNow))
                quantize1e6(clamp(min(s, sFail), 0.1, 36500.0))
            } else {
                val hardPenalty = if (g == 2) params[15] else 1.0
                val easyBonus = if (g == 4) params[16] else 1.0
                val inc = exp(params[8]) *
                    (11.0 - dNext) *
                    s.pow(-params[9]) *
                    (exp(params[10] * (1.0 - rNow)) - 1.0) *
                    hardPenalty *
                    easyBonus
                quantize1e6(clamp(s * (1.0 + inc), 0.1, 36500.0))
            }

            s = sNext
            d = dNext
            reps += 1
            lastTsMs = nowMs
            val ivlDays = if (g == 1) 1L else max(1L, s.roundToLong())
            dueMs = nowMs + ivlDays * DAY_MS
        }

        return CardStateV56(s = s, d = d, dueMs = dueMs, lastTsMs = lastTsMs, reps = reps, lapses = lapses)
    }

    fun buildSummarySheetRows(pairs: List<Pair<String, String>>, masked: Boolean = true): List<SummarySheetRow> {
        return pairs.mapIndexed { idx, (front, back) ->
            val clean = back.lines().firstOrNull()?.replace(Regex("""\s*\([^)]*\)\s*$"""), "")?.trim().orEmpty()
            SummarySheetRow(
                index = idx + 1,
                prompt = front,
                cleanAnswer = clean.ifEmpty { back.trim() },
                masked = masked
            )
        }
    }
}
