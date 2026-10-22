package com.ankistudio.domain.rea

import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.ln
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

    // =========================================================================
    // PHASE 5 (v5.8): SIMPLE IS BEST — ANKI REA PROGRESSIVE DISCLOSURE & FLUENCY
    // =========================================================================

    data class StudyToolsSummary(
        val activeCount: Int,
        val isDefault: Boolean,
        val summaryBadgeText: String
    )

    data class SmartAiEngineDecision(
        val ok: Boolean,
        val status: String,
        val selectedModel: String,
        val fallbackChain: List<String>,
        val uiLabel: String,
        val exposesRawModelName: Boolean = false
    )

    data class CurriculumSegmentState(
        val activeSegment: String,
        val combinedScopeCount: Int,
        val combinedTabLabel: String,
        val visiblePanels: Map<String, Boolean>
    )

    data class FluencyCalibrationResult(
        val rawRating: Int,
        val effectiveRating: Int,
        val zScore: Double,
        val status: String
    )

    data class ConfusionMatrixUpdateResult(
        val weight: Double,
        val updated: Boolean,
        val shouldInterleavePeer: Boolean,
        val shouldSuggestContrastNote: Boolean
    )

    data class C4ReviewCalibrationResult(
        val rawRating: Int,
        val effectiveRating: Int,
        val zScore: Double,
        val status: String,
        val rawConfusionFactor: Double,
        val effectiveIntervalFactor: Double,
        val intervalScaledByConfusion: Boolean
    )

    val SMART_AI_FALLBACK_CHAIN: List<String> = listOf(
        "glm-5.3-flash",
        "deepseek-v4.1-flash",
        "gemma4:31b",
        "glm-5.3",
        "local_rule"
    )

    val ALLOWED_SMART_AI_MODELS: Set<String> = setOf(
        "glm-5.3-flash",
        "deepseek-v4.1-flash",
        "gemma4:31b",
        "glm-5.3",
        "local_rule"
    )

    private val BLOCKED_MODEL_PREFIXES = listOf(
        "kimi-k2",
        "kimi-2",
        "kimi-k3",
        "minimax-2.7",
        "minimax-m3",
        "minimax"
    )

    fun computeStudyToolsSummary(
        studyFilter: String = "all",
        qtypeFilter: String = "all",
        cramMode: Boolean = false,
        shuffleMode: String = "sequential"
    ): StudyToolsSummary {
        var count = 0
        if (!studyFilter.trim().equals("all", ignoreCase = true)) count += 1
        if (!qtypeFilter.trim().equals("all", ignoreCase = true)) count += 1
        if (cramMode) count += 1
        val sh = shuffleMode.trim().lowercase()
        if (sh.isNotEmpty() && sh != "sequential" && sh != "default") count += 1
        val isDef = count == 0
        return StudyToolsSummary(
            activeCount = count,
            isDefault = isDef,
            summaryBadgeText = if (isDef) "" else "필터 ${count}개 적용 중"
        )
    }

    fun resolveSmartAiEngine(
        taskType: String = "card_generate",
        offlineOnly: Boolean = false,
        manualOverride: String? = null,
        failedModels: Set<String> = emptySet()
    ): SmartAiEngineDecision {
        val taskNorm = taskType.trim().lowercase()
        val chain = when (taskNorm) {
            "vision_doc" -> listOf("glm-5.3-flash", "gemma4:31b", "deepseek-v4.1-flash", "glm-5.3", "local_rule")
            "reasoning", "math", "stem" -> listOf("deepseek-v4.1-flash", "glm-5.3-flash", "gemma4:31b", "glm-5.3", "local_rule")
            else -> SMART_AI_FALLBACK_CHAIN
        }

        val overrideNorm = manualOverride?.trim().orEmpty()
        if (overrideNorm.isNotEmpty()) {
            val lower = overrideNorm.lowercase()
            if (lower != "auto" && lower != "smart") {
                if (lower == "offline") {
                    return SmartAiEngineDecision(
                        ok = true,
                        status = "OFFLINE_LOCAL",
                        selectedModel = "local_rule",
                        fallbackChain = listOf("local_rule"),
                        uiLabel = "⚡ 오프라인 빠른 생성",
                        exposesRawModelName = false
                    )
                }
                if (BLOCKED_MODEL_PREFIXES.any { lower.startsWith(it) || lower.contains(it) } || lower !in ALLOWED_SMART_AI_MODELS) {
                    return SmartAiEngineDecision(
                        ok = false,
                        status = "BLOCKED_MODEL",
                        selectedModel = "",
                        fallbackChain = chain,
                        uiLabel = "✨ 스마트 자동 생성",
                        exposesRawModelName = false
                    )
                }
                return SmartAiEngineDecision(
                    ok = true,
                    status = "MANUAL_OVERRIDE",
                    selectedModel = lower,
                    fallbackChain = chain,
                    uiLabel = if (lower == "local_rule") "⚡ 오프라인 빠른 생성" else "✨ 스마트 자동 생성",
                    exposesRawModelName = false
                )
            }
        }

        if (offlineOnly) {
            return SmartAiEngineDecision(
                ok = true,
                status = "OFFLINE_LOCAL",
                selectedModel = "local_rule",
                fallbackChain = listOf("local_rule"),
                uiLabel = "⚡ 오프라인 빠른 생성",
                exposesRawModelName = false
            )
        }

        val failedLower = failedModels.map { it.trim().lowercase() }.toSet()
        for (cand in chain) {
            if (cand.lowercase() !in failedLower) {
                return SmartAiEngineDecision(
                    ok = true,
                    status = if (cand == "local_rule") "FALLBACK_LOCAL" else "OK",
                    selectedModel = cand,
                    fallbackChain = chain,
                    uiLabel = if (cand == "local_rule") "⚡ 오프라인 빠른 생성" else "✨ 스마트 자동 생성",
                    exposesRawModelName = false
                )
            }
        }
        return SmartAiEngineDecision(
            ok = true,
            status = "FALLBACK_LOCAL",
            selectedModel = "local_rule",
            fallbackChain = chain,
            uiLabel = "⚡ 오프라인 빠른 생성",
            exposesRawModelName = false
        )
    }

    fun resolveCurriculumSegmentState(
        segment: String = "textbook",
        combinedScopeCount: Int = 0
    ): CurriculumSegmentState {
        val raw = segment.trim().lowercase()
        val seg = if (raw in setOf("textbook", "collection", "combined")) raw else "textbook"
        val cnt = max(0, combinedScopeCount)
        return CurriculumSegmentState(
            activeSegment = seg,
            combinedScopeCount = cnt,
            combinedTabLabel = if (cnt > 0) "🎯 시험범위 조합 ($cnt)" else "🎯 시험범위 조합",
            visiblePanels = mapOf(
                "textbook" to (seg == "textbook"),
                "collection" to (seg == "collection"),
                "combined" to (seg == "combined")
            )
        )
    }

    fun calibrateFluencyGrade(
        rawRating: Int,
        responseTimeMs: Long?,
        baselineRtMsSamples: List<Long>,
        consecutiveGoodStreak: Int = 0
    ): FluencyCalibrationResult {
        require(rawRating in 1..4) { "rawRating must be 1..4" }
        if (rawRating != 3) {
            return FluencyCalibrationResult(
                rawRating = rawRating,
                effectiveRating = rawRating,
                zScore = 0.0,
                status = "PRESERVED_EXPLICIT_RATING"
            )
        }
        if (responseTimeMs == null || responseTimeMs < 300L || responseTimeMs > 60_000L) {
            return FluencyCalibrationResult(
                rawRating = rawRating,
                effectiveRating = rawRating,
                zScore = 0.0,
                status = "BYPASSED_INVALID_RT"
            )
        }
        val valid = baselineRtMsSamples.filter { it in 300L..60_000L }
        if (valid.size < 5) {
            return FluencyCalibrationResult(
                rawRating = rawRating,
                effectiveRating = rawRating,
                zScore = 0.0,
                status = "BYPASSED_COLD_START"
            )
        }
        val lnSorted = valid.map { ln(it.toDouble()) }.sorted()
        val n = lnSorted.size
        val mid = n / 2
        val medianLn = if (n % 2 == 1) lnSorted[mid] else 0.5 * (lnSorted[mid - 1] + lnSorted[mid])
        val absDevs = lnSorted.map { abs(it - medianLn) }.sorted()
        val madLn = if (n % 2 == 1) absDevs[mid] else 0.5 * (absDevs[mid - 1] + absDevs[mid])
        if (madLn < 1e-9) {
            return FluencyCalibrationResult(
                rawRating = rawRating,
                effectiveRating = rawRating,
                zScore = 0.0,
                status = "BYPASSED_ZERO_MAD"
            )
        }
        val denom = max(0.15, 1.4826 * madLn)
        val z = quantize1e6((ln(responseTimeMs.toDouble()) - medianLn) / denom)

        return when {
            z >= 1.5 -> FluencyCalibrationResult(
                rawRating = rawRating,
                effectiveRating = 2,
                zScore = z,
                status = "DOWNGRADED_HESITANT_GOOD"
            )
            z <= -1.0 && consecutiveGoodStreak >= 2 -> FluencyCalibrationResult(
                rawRating = rawRating,
                effectiveRating = 4,
                zScore = z,
                status = "UPGRADED_FLUENT_GOOD"
            )
            else -> FluencyCalibrationResult(
                rawRating = rawRating,
                effectiveRating = 3,
                zScore = z,
                status = "UNCHANGED_NORMAL_GOOD"
            )
        }
    }

    fun updateConfusionMatrixWeight(
        currentWeight: Double,
        elapsedDays: Double,
        cardA: String,
        cardB: String,
        reviewId: String = "",
        seenReviewIds: Set<String> = emptySet(),
        tauDays: Double = 30.0
    ): ConfusionMatrixUpdateResult {
        val aId = cardA.trim()
        val bId = cardB.trim()
        val curW = if (!currentWeight.isFinite() || currentWeight < 0.0) 0.0 else min(100.0, currentWeight)
        if (aId.isEmpty() || bId.isEmpty() || aId == bId) {
            return ConfusionMatrixUpdateResult(
                weight = quantize1e6(curW),
                updated = false,
                shouldInterleavePeer = curW >= 2.0,
                shouldSuggestContrastNote = curW >= 4.0
            )
        }
        val revKey = reviewId.trim()
        if (revKey.isNotEmpty() && revKey in seenReviewIds) {
            return ConfusionMatrixUpdateResult(
                weight = quantize1e6(curW),
                updated = false,
                shouldInterleavePeer = curW >= 2.0,
                shouldSuggestContrastNote = curW >= 4.0
            )
        }
        val dt = if (!elapsedDays.isFinite() || elapsedDays < 0.0) 0.0 else elapsedDays
        val tau = if (!tauDays.isFinite() || tauDays < 1.0) 30.0 else tauDays
        val nextW = quantize1e6(min(100.0, curW * exp(-dt / tau) + 1.0))
        return ConfusionMatrixUpdateResult(
            weight = nextW,
            updated = true,
            shouldInterleavePeer = nextW >= 2.0,
            shouldSuggestContrastNote = nextW >= 4.0
        )
    }

    fun computeConfusionIntervalFactor(confusionWeight: Double): Double {
        if (!confusionWeight.isFinite() || confusionWeight <= 0.0) return 1.0
        val w = min(100.0, confusionWeight)
        val penalty = min(0.15, 0.05 * w)
        return quantize1e6(max(0.85, 1.0 - penalty))
    }

    fun applyC4ReviewCalibration(
        rawRating: Int,
        responseTimeMs: Long? = null,
        baselineRtMsSamples: List<Long> = emptyList(),
        consecutiveGoodStreak: Int = 0,
        confusionWeight: Double = 0.0
    ): C4ReviewCalibrationResult {
        val fluency = calibrateFluencyGrade(
            rawRating = rawRating,
            responseTimeMs = responseTimeMs,
            baselineRtMsSamples = baselineRtMsSamples,
            consecutiveGoodStreak = consecutiveGoodStreak
        )
        val rawFactor = computeConfusionIntervalFactor(confusionWeight)
        val rewritten = fluency.effectiveRating != fluency.rawRating
        val effectiveFactor = if (rewritten) 1.0 else rawFactor
        return C4ReviewCalibrationResult(
            rawRating = fluency.rawRating,
            effectiveRating = fluency.effectiveRating,
            zScore = fluency.zScore,
            status = fluency.status,
            rawConfusionFactor = rawFactor,
            effectiveIntervalFactor = effectiveFactor,
            intervalScaledByConfusion = !rewritten && effectiveFactor < 1.0
        )
    }
}
