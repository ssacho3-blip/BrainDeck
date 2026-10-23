package com.ankistudio.domain.planner

import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt

data class AnkiDeckOptions(
    val newPerDay: Int = 30,
    val maxReviewsPerDay: Int = 200,
    val buryNewSiblings: Boolean = true,
    val buryReviewSiblings: Boolean = true,
    val reviewSortOrder: String = "retrievability_asc",
    val newReviewMixMode: String = "mix",
    val leechThreshold: Int = 8,
    val leechAction: String = "suspend",
    val desiredRetention: Double = 0.90,
)

data class AnkiStudyDayForecast(
    val day: Int,
    val phase: String,
    val newCards: Int,
    val learningCards: Int,
    val reviewCards: Int,
    val totalWorkload: Int,
    val estimatedMinutes: Double,
)

data class AnkiStudyPlan(
    val status: String,
    val totalCards: Int,
    val newCount: Int,
    val learningCount: Int,
    val reviewDueCount: Int,
    val targetDays: Int,
    val newIntakeDays: Int,
    val consolidationDays: Int,
    val dailyMinutesBudget: Int,
    val desiredRetention: Double,
    val recommendedDailyNew: Int,
    val recommendedMaxReviews: Int,
    val avgDailyMinutes: Double,
    val peakDailyMinutes: Double,
    val peakDailyReviews: Int,
    val minComfortableDays: Int,
    val recommendations: List<String>,
    val dailyForecast: List<AnkiStudyDayForecast>,
)

data class AnkiCardSnapshot(
    val cardId: String,
    val noteId: String = "",
    val state: String = "new",
    val stability: Double = 0.0,
    val difficulty: Double = 0.0,
    val reps: Int = 0,
    val lapses: Int = 0,
    val dueDays: Int = 0,
    val flag: Int = 0,
    val buriedToday: Boolean = false,
    val suspended: Boolean = false,
    val lastRating: Int? = null,
    val tags: List<String> = emptyList(),
)

data class AnkiV3DailyQueueResult(
    val queue: List<AnkiCardSnapshot>,
    val learningQueue: List<AnkiCardSnapshot>,
    val reviewQueue: List<AnkiCardSnapshot>,
    val newQueue: List<AnkiCardSnapshot>,
    val buriedSiblingIds: List<String>,
)

data class LeechEvaluation(
    val isLeech: Boolean,
    val justTriggered: Boolean,
    val shouldSuspend: Boolean,
    val lapses: Int,
    val leechThreshold: Int,
    val tags: List<String>,
    val coachingMessage: String,
)

data class CustomStudySession(
    val preset: String,
    val title: String,
    val eventKind: String,
    val reschedule: Boolean,
    val cards: List<AnkiCardSnapshot>,
)

object AnkiStudyPlannerEngine {

    val FLAG_LABELS: Map<Int, String> = mapOf(
        0 to "플래그 없음",
        1 to "🔴 집중 요주의 (Red)",
        2 to "🟠 시험 전 재확인 (Orange)",
        3 to "🟢 암기 완료 후보 (Green)",
        4 to "🔵 예문·문맥 보충 (Blue)",
        5 to "🩷 오답 노트 (Pink)",
        6 to "🩵 발음·듣기 체크 (Turquoise)",
        7 to "💜 심화·함정 변별 (Purple)",
    )

    fun computeStudyPlan(
        totalCards: Int,
        newCount: Int,
        learningCount: Int = 0,
        reviewDueCount: Int = 0,
        targetDays: Int = 30,
        dailyMinutesBudget: Int = 30,
        desiredRetention: Double = 0.90,
        avgSecPerNew: Double = 18.0,
        avgSecPerReview: Double = 8.0,
        avgSecPerLearning: Double = 12.0,
    ): AnkiStudyPlan {
        require(targetDays in 1..3650) { "target_days must be in 1..3650" }
        require(totalCards >= 0 && newCount >= 0 && learningCount >= 0 && reviewDueCount >= 0) {
            "card counts must be non-negative"
        }
        require(desiredRetention in 0.70..0.99) { "desired_retention must be in [0.70, 0.99]" }
        require(dailyMinutesBudget > 0) { "daily_minutes_budget must be > 0" }

        val consolidationDays = when {
            targetDays >= 7 -> min(7, max(2, (targetDays * 0.20).roundToInt()))
            targetDays >= 4 -> 1
            else -> 0
        }
        val newIntakeDays = max(1, targetDays - consolidationDays)
        val recommendedDailyNew = if (newCount > 0) max(1, ceil(newCount.toDouble() / newIntakeDays).toInt()) else 0

        val dailyNewSchedule = IntArray(targetDays)
        var remainingNew = newCount
        for (i in 0 until targetDays) {
            if (i < newIntakeDays && remainingNew > 0) {
                val take = min(recommendedDailyNew, remainingNew)
                dailyNewSchedule[i] = take
                remainingNew -= take
            } else {
                dailyNewSchedule[i] = 0
            }
        }
        if (remainingNew > 0) {
            dailyNewSchedule[newIntakeDays - 1] += remainingNew
        }

        val retentionLoadFactor = 1.0 + max(0.0, (desiredRetention - 0.85) * 4.5)
        val cascadeOffsets = listOf(
            1 to 1.0 * retentionLoadFactor,
            3 to 0.72 * retentionLoadFactor,
            7 to 0.55 * retentionLoadFactor,
            14 to 0.42 * retentionLoadFactor,
            28 to 0.32 * retentionLoadFactor,
        )
        val backlogSpreadDays = if (reviewDueCount > 120) min(5, targetDays) else 1
        val baseMatureCards = max(0, totalCards - newCount - learningCount)

        val forecast = mutableListOf<AnkiStudyDayForecast>()
        for (dIdx in 0 until targetDays) {
            val dayNo = dIdx + 1
            val nNew = dailyNewSchedule[dIdx]
            val nLearn = if (dIdx == 0) learningCount else (dailyNewSchedule[max(0, dIdx - 1)] * 0.25).roundToInt()
            val backlogPart = if (dIdx < backlogSpreadDays) {
                ceil(reviewDueCount.toDouble() / backlogSpreadDays).toInt()
            } else {
                (baseMatureCards * 0.06 * retentionLoadFactor).roundToInt()
            }
            var cascadeReviews = 0.0
            for ((offset, weight) in cascadeOffsets) {
                val srcIdx = dIdx - offset
                if (srcIdx in 0 until targetDays) {
                    cascadeReviews += dailyNewSchedule[srcIdx] * weight
                }
            }
            val nRev = (backlogPart + cascadeReviews).roundToInt()
            val estSeconds = nNew * avgSecPerNew + nLearn * avgSecPerLearning + nRev * avgSecPerReview
            val estMinutes = ((estSeconds / 60.0) * 10.0).roundToInt() / 10.0
            val phase = when {
                dIdx >= newIntakeDays -> "consolidation_review"
                dIdx < newIntakeDays / 2 -> "initial_coverage"
                else -> "deep_coverage"
            }
            forecast.add(
                AnkiStudyDayForecast(
                    day = dayNo,
                    phase = phase,
                    newCards = nNew,
                    learningCards = nLearn,
                    reviewCards = nRev,
                    totalWorkload = nNew + nLearn + nRev,
                    estimatedMinutes = estMinutes,
                )
            )
        }

        val peakDailyMinutes = forecast.maxOfOrNull { it.estimatedMinutes } ?: 0.0
        val avgDailyMinutes = ((forecast.sumOf { it.estimatedMinutes } / forecast.size) * 10.0).roundToInt() / 10.0
        val peakDailyReviews = forecast.maxOfOrNull { it.reviewCards } ?: 0

        val status = when {
            avgDailyMinutes <= dailyMinutesBudget * 1.05 &&
                peakDailyMinutes <= dailyMinutesBudget * 1.25 &&
                recommendedDailyNew <= 60 -> "FEASIBLE"
            avgDailyMinutes <= dailyMinutesBudget * 1.65 &&
                peakDailyMinutes <= dailyMinutesBudget * 2.0 &&
                recommendedDailyNew <= 100 -> "TIGHT_SCHEDULE"
            else -> "OVERLOAD_WARNING"
        }

        val minComfortableDays = max(
            targetDays,
            ceil((newCount * avgSecPerNew * 2.4) / max(60.0, dailyMinutesBudget * 60.0)).toInt() + consolidationDays,
        )

        val recommendations = mutableListOf<String>()
        when (status) {
            "FEASIBLE" -> recommendations.add(
                "하루 새 카드 ${recommendedDailyNew}장 + 복습 중심(평균 ${avgDailyMinutes}분/일)으로 D-$targetDays 내 안정적 완주가 가능합니다."
            )
            "TIGHT_SCHEDULE" -> recommendations.add(
                "피크 구간 일일 학습량이 약 ${peakDailyMinutes}분(목표 ${dailyMinutesBudget}분)에 달합니다. 주말 보충 학습(Custom Study)을 병행하세요."
            )
            else -> recommendations.add(
                "하루 새 카드 ${recommendedDailyNew}장(피크 ${peakDailyMinutes}분/일)은 번아웃 위험이 큽니다. 목표 기간을 최소 ${minComfortableDays}일로 늘리세요."
            )
        }
        if (consolidationDays > 0) {
            recommendations.add(
                "시험 직전 마지막 ${consolidationDays}일은 새 카드 진도를 멈추고(0장/일) 총정리 복습 구간으로 배정되었습니다."
            )
        }

        return AnkiStudyPlan(
            status = status,
            totalCards = totalCards,
            newCount = newCount,
            learningCount = learningCount,
            reviewDueCount = reviewDueCount,
            targetDays = targetDays,
            newIntakeDays = newIntakeDays,
            consolidationDays = consolidationDays,
            dailyMinutesBudget = dailyMinutesBudget,
            desiredRetention = desiredRetention,
            recommendedDailyNew = recommendedDailyNew,
            recommendedMaxReviews = max(150, peakDailyReviews + 30),
            avgDailyMinutes = avgDailyMinutes,
            peakDailyMinutes = peakDailyMinutes,
            peakDailyReviews = peakDailyReviews,
            minComfortableDays = minComfortableDays,
            recommendations = recommendations,
            dailyForecast = forecast,
        )
    }

    private fun extractConceptGroup(card: AnkiCardSnapshot): String {
        if (card.noteId.isNotBlank()) return "note:${card.noteId.trim()}"
        for (t in card.tags) {
            val clean = t.trim()
            if (clean.startsWith("concept:") || clean.startsWith("note:") || clean.startsWith("entry:")) {
                return clean
            }
        }
        return ""
    }

    private fun estimateRetrievability(card: AnkiCardSnapshot): Double {
        val s = card.stability
        if (s <= 0.0) return 0.0
        val elapsed = if (card.dueDays < 0) s + abs(card.dueDays.toDouble()) else max(0.0, s - card.dueDays.toDouble())
        return (1.0 + (19.0 / 81.0) * (elapsed / max(0.1, s))).pow(-0.5)
    }

    fun buildV3DailyQueue(
        cards: List<AnkiCardSnapshot>,
        options: AnkiDeckOptions = AnkiDeckOptions(),
    ): AnkiV3DailyQueueResult {
        val learningRaw = mutableListOf<AnkiCardSnapshot>()
        val reviewRaw = mutableListOf<AnkiCardSnapshot>()
        val newRaw = mutableListOf<AnkiCardSnapshot>()

        for (c in cards) {
            if (c.suspended || c.state == "suspended" || "suspended" in c.tags) continue
            if (c.buriedToday || "buried_today" in c.tags) continue
            when (c.state.lowercase()) {
                "learning", "relearning" -> learningRaw.add(c)
                "review" -> if (c.dueDays <= 0) reviewRaw.add(c)
                "new" -> newRaw.add(c)
            }
        }

        val sortedReviews = when (options.reviewSortOrder) {
            "retrievability_asc" -> reviewRaw.sortedWith(
                compareBy<AnkiCardSnapshot> { estimateRetrievability(it) }.thenBy { it.dueDays }
            )
            "retrievability_desc" -> reviewRaw.sortedWith(
                compareByDescending<AnkiCardSnapshot> { estimateRetrievability(it) }.thenBy { it.dueDays }
            )
            "due_date_asc" -> reviewRaw.sortedBy { it.dueDays }
            "difficulty_desc" -> reviewRaw.sortedByDescending { it.difficulty }
            else -> reviewRaw
        }

        val seenConcepts = mutableSetOf<String>()
        val buriedSiblingIds = mutableListOf<String>()
        for (lc in learningRaw) {
            val cg = extractConceptGroup(lc)
            if (cg.isNotEmpty()) seenConcepts.add(cg)
        }

        val selectedReviews = mutableListOf<AnkiCardSnapshot>()
        for (rc in sortedReviews) {
            val cg = extractConceptGroup(rc)
            if (options.buryReviewSiblings && cg.isNotEmpty() && cg in seenConcepts) {
                buriedSiblingIds.add(rc.cardId)
                continue
            }
            if (selectedReviews.size >= max(0, options.maxReviewsPerDay)) continue
            selectedReviews.add(rc)
            if (cg.isNotEmpty()) seenConcepts.add(cg)
        }

        val selectedNew = mutableListOf<AnkiCardSnapshot>()
        for (nc in newRaw) {
            val cg = extractConceptGroup(nc)
            if (options.buryNewSiblings && cg.isNotEmpty() && cg in seenConcepts) {
                buriedSiblingIds.add(nc.cardId)
                continue
            }
            if (selectedNew.size >= max(0, options.newPerDay)) continue
            selectedNew.add(nc)
            if (cg.isNotEmpty()) seenConcepts.add(cg)
        }

        val combinedTail = mutableListOf<AnkiCardSnapshot>()
        when (options.newReviewMixMode) {
            "reviews_first" -> {
                combinedTail.addAll(selectedReviews)
                combinedTail.addAll(selectedNew)
            }
            "new_first" -> {
                combinedTail.addAll(selectedNew)
                combinedTail.addAll(selectedReviews)
            }
            else -> {
                if (selectedNew.isEmpty()) {
                    combinedTail.addAll(selectedReviews)
                } else if (selectedReviews.isEmpty()) {
                    combinedTail.addAll(selectedNew)
                } else {
                    val stride = max(1, selectedReviews.size / selectedNew.size)
                    var rIdx = 0
                    var nIdx = 0
                    while (rIdx < selectedReviews.size || nIdx < selectedNew.size) {
                        for (s in 0 until stride) {
                            if (rIdx < selectedReviews.size) combinedTail.add(selectedReviews[rIdx++])
                        }
                        if (nIdx < selectedNew.size) combinedTail.add(selectedNew[nIdx++])
                    }
                }
            }
        }

        val queue = learningRaw + combinedTail
        return AnkiV3DailyQueueResult(
            queue = queue,
            learningQueue = learningRaw,
            reviewQueue = selectedReviews,
            newQueue = selectedNew,
            buriedSiblingIds = buriedSiblingIds,
        )
    }

    fun evaluateLeechStatus(
        lapses: Int,
        leechThreshold: Int = 8,
        leechAction: String = "suspend",
        existingTags: List<String> = emptyList(),
    ): LeechEvaluation {
        val threshold = max(2, leechThreshold)
        val halfStep = max(1, threshold / 2)
        val curLapses = max(0, lapses)
        val tags = existingTags.map { it.trim() }.filter { it.isNotEmpty() }.toMutableList()
        val isLeech = curLapses >= threshold || "leech" in tags
        val justTriggered = curLapses >= threshold && ((curLapses - threshold) % halfStep == 0)
        val shouldSuspend = justTriggered && leechAction.lowercase() == "suspend"
        if (isLeech && "leech" !in tags) tags.add("leech")
        if (shouldSuspend && "suspended" !in tags) tags.add("suspended")
        val coaching = if (isLeech) {
            "거머리 카드(Leech) 감지 (${curLapses}회 오답): 단서를 더 작게 쪼개거나 초성·어원 연상 힌트를 보강하세요."
        } else {
            ""
        }
        return LeechEvaluation(
            isLeech = isLeech,
            justTriggered = justTriggered,
            shouldSuspend = shouldSuspend,
            lapses = curLapses,
            leechThreshold = threshold,
            tags = tags,
            coachingMessage = coaching,
        )
    }

    fun applyCardAction(
        card: AnkiCardSnapshot,
        action: String,
        flag: Int = 0,
        dueDays: Int = 0,
    ): AnkiCardSnapshot {
        val tags = card.tags.toMutableList()
        return when (action.lowercase()) {
            "set_flag" -> {
                require(flag in FLAG_LABELS.keys) { "flag must be in 0..7" }
                tags.removeAll { it.startsWith("flag:") }
                if (flag > 0) tags.add("flag:$flag")
                card.copy(flag = flag, tags = tags)
            }
            "suspend" -> {
                if ("suspended" !in tags) tags.add("suspended")
                card.copy(suspended = true, tags = tags)
            }
            "unsuspend" -> {
                tags.removeAll { it == "suspended" }
                card.copy(suspended = false, tags = tags)
            }
            "bury" -> {
                if ("buried_today" !in tags) tags.add("buried_today")
                card.copy(buriedToday = true, tags = tags)
            }
            "unbury" -> {
                tags.removeAll { it == "buried_today" }
                card.copy(buriedToday = false, tags = tags)
            }
            "set_due_days" -> {
                val nextState = if (card.state == "new") "review" else card.state
                val nextS = if (card.state == "new") max(1.0, dueDays.toDouble()) else card.stability
                card.copy(dueDays = dueDays, state = nextState, stability = nextS, tags = tags)
            }
            "forget_reset" -> {
                tags.removeAll { it == "leech" || it == "buried_today" }
                card.copy(
                    state = "new",
                    stability = 0.0,
                    difficulty = 0.0,
                    reps = 0,
                    lapses = 0,
                    dueDays = 0,
                    buriedToday = false,
                    tags = tags,
                )
            }
            else -> throw IllegalArgumentException("Unsupported Anki card action: $action")
        }
    }

    fun buildCustomStudySession(
        cards: List<AnkiCardSnapshot>,
        preset: String = "forgotten_recent",
        daysAhead: Int = 3,
        limit: Int = 50,
        extraNew: Int = 10,
    ): CustomStudySession {
        val active = cards.filter { !it.suspended && it.state != "suspended" && !it.buriedToday }
        return when (preset.lowercase()) {
            "forgotten_recent" -> {
                val sel = active.filter {
                    it.lastRating == 1 || it.state == "relearning" || it.lapses >= 2
                }.sortedByDescending { it.lapses }.take(limit)
                CustomStudySession(preset, "🔥 최근 오답·망각 카드 집중 복습", "REVIEW", true, sel)
            }
            "review_ahead" -> {
                val sel = active.filter {
                    it.state == "review" && it.dueDays <= max(0, daysAhead)
                }.sortedBy { it.dueDays }.take(limit)
                CustomStudySession(preset, "⏩ 시험 대비 ${daysAhead}일 선행 복습", "REVIEW_AHEAD", true, sel)
            }
            "preview_new" -> {
                val sel = active.filter { it.state == "new" }.take(limit)
                CustomStudySession(preset, "👀 새 카드 무오염 미리보기", "CRAM", false, sel)
            }
            "cram_flagged_or_leech" -> {
                val sel = active.filter {
                    it.flag > 0 || "leech" in it.tags || it.tags.any { t -> t.startsWith("flag:") } || it.lapses >= 4
                }.sortedWith(compareByDescending<AnkiCardSnapshot> { it.flag }.thenByDescending { it.lapses }).take(limit)
                CustomStudySession(preset, "🚩 플래그·거머리 취약 카드 특훈", "CRAM", false, sel)
            }
            "increase_new_quota" -> {
                val sel = active.filter { it.state == "new" }.take(max(1, extraNew))
                CustomStudySession(preset, "➕ 오늘의 새 카드 할당량 추가", "REVIEW", true, sel)
            }
            else -> throw IllegalArgumentException("Unsupported custom study preset: $preset")
        }
    }
}
