package com.ankistudio.domain.planner

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AnkiStudyPlannerEngineTest {

    @Test
    fun `computeStudyPlan calculates D-Day pacing and consolidation buffer for 1200 cards`() {
        val plan = AnkiStudyPlannerEngine.computeStudyPlan(
            totalCards = 1200,
            newCount = 1000,
            learningCount = 20,
            reviewDueCount = 80,
            targetDays = 30,
            dailyMinutesBudget = 45,
            desiredRetention = 0.90,
        )
        assertEquals("FEASIBLE", plan.status)
        assertEquals(30, plan.dailyForecast.size)
        assertEquals(1000, plan.dailyForecast.sumOf { it.newCards })
        assertTrue(plan.consolidationDays >= 2)
        for (tailDay in plan.dailyForecast.takeLast(plan.consolidationDays)) {
            assertEquals(0, tailDay.newCards)
            assertEquals("consolidation_review", tailDay.phase)
        }
    }

    @Test
    fun `buildV3DailyQueue enforces sibling burying and sort order`() {
        val cards = listOf(
            AnkiCardSnapshot(cardId = "rev_1", state = "review", stability = 2.0, difficulty = 6.0, dueDays = -3, tags = listOf("concept:c1")),
            AnkiCardSnapshot(cardId = "rev_2", state = "review", stability = 10.0, difficulty = 4.0, dueDays = 0, tags = listOf("concept:c2")),
            AnkiCardSnapshot(cardId = "new_sibling", state = "new", tags = listOf("concept:c1")),
            AnkiCardSnapshot(cardId = "new_ok", state = "new", tags = listOf("concept:c3")),
        )
        val res = AnkiStudyPlannerEngine.buildV3DailyQueue(
            cards = cards,
            options = AnkiDeckOptions(newPerDay = 5, maxReviewsPerDay = 10, buryNewSiblings = true),
        )
        assertTrue("new_sibling" in res.buriedSiblingIds)
        assertEquals(listOf("new_ok"), res.newQueue.map { it.cardId })
        assertEquals(listOf("rev_1", "rev_2"), res.reviewQueue.map { it.cardId })
    }

    @Test
    fun `applyCardAction and buildCustomStudySession work end-to-end`() {
        val raw = AnkiCardSnapshot(cardId = "c_101", state = "review", stability = 8.0, difficulty = 6.0, lapses = 8)
        val flagged = AnkiStudyPlannerEngine.applyCardAction(raw, action = "set_flag", flag = 1)
        assertEquals(1, flagged.flag)
        assertTrue("flag:1" in flagged.tags)

        val leech = AnkiStudyPlannerEngine.evaluateLeechStatus(lapses = 8, leechThreshold = 8, leechAction = "suspend")
        assertTrue(leech.isLeech)
        assertTrue(leech.justTriggered)
        assertTrue(leech.shouldSuspend)

        val cramSession = AnkiStudyPlannerEngine.buildCustomStudySession(
            cards = listOf(flagged),
            preset = "cram_flagged_or_leech",
            limit = 10,
        )
        assertEquals(1, cramSession.cards.size)
        assertFalse(cramSession.reschedule)
        assertEquals("CRAM", cramSession.eventKind)
    }
}
