package com.ankistudio.domain.planner

import com.ankistudio.domain.catalog.BuiltInCurriculumCatalog
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

    @Test
    fun `BuiltInCurriculumCatalog generates 1000+ subject-pure cards without cross-subject contrast or front spoilers`() {
        val mathCards = BuiltInCurriculumCatalog.buildCollectionCards(
            collectionId = "moe-math:core-formulas",
            difficultyLevel = "mixed",
            targetCount = 1000,
        )
        assertEquals(1000, mathCards.size)
        assertTrue(mathCards.none { it.spec.frontText.contains("[심화 대조·변별]") || it.spec.frontText.contains("함무라비") })

        val engCards = BuiltInCurriculumCatalog.buildCollectionCards(
            collectionId = "moe-eng:middle-1200",
            difficultyLevel = "mixed",
            targetCount = 1000,
        )
        assertEquals(1000, engCards.size)
        assertTrue(
            engCards.none {
                (it.spec.noteType == "basic" && it.spec.frontText.contains("{{c")) ||
                    it.spec.frontText.contains("[심화 대조·변별]")
            }
        )
    }

    @Test
    fun `computePercentTenths and computeDeckMasteryProgress match Python and JS 100 percent`() {
        assertEquals(0, AnkiStudyPlannerEngine.computePercentTenths(0, 0))
        assertEquals(0, AnkiStudyPlannerEngine.computePercentTenths(0, 1000))
        assertEquals(1, AnkiStudyPlannerEngine.computePercentTenths(1, 1000))
        assertEquals(1, AnkiStudyPlannerEngine.computePercentTenths(1, 5000))
        assertEquals(171, AnkiStudyPlannerEngine.computePercentTenths(180, 1050))
        assertEquals(400, AnkiStudyPlannerEngine.computePercentTenths(12, 30))
        assertEquals(999, AnkiStudyPlannerEngine.computePercentTenths(999, 1000))
        assertEquals(1000, AnkiStudyPlannerEngine.computePercentTenths(1000, 1000))

        val cards = mutableListOf<AnkiCardSnapshot>()
        for (i in 0 until 700) {
            val stTag = if (i < 350) "lv1" else "lv2"
            cards.add(AnkiCardSnapshot(cardId = "u_$i", state = "new", stability = 0.0, reps = 0, tags = listOf(stTag), frontText = "Unseen $i"))
        }
        for (i in 0 until 100) {
            cards.add(AnkiCardSnapshot(cardId = "l_$i", state = "learning", stability = 0.5, reps = 1, tags = listOf("lv1"), frontText = "Learn $i"))
        }
        for (i in 0 until 100) {
            cards.add(AnkiCardSnapshot(cardId = "y_$i", state = "review", stability = 7.0, reps = 3, tags = listOf("lv3"), frontText = "Young $i"))
        }
        for (i in 0 until 100) {
            cards.add(AnkiCardSnapshot(cardId = "m_$i", state = "review", stability = 30.0, reps = 6, tags = listOf("lv4"), frontText = "Mature $i"))
        }
        for (i in 0 until 10) {
            cards.add(AnkiCardSnapshot(cardId = "s_$i", state = "suspended", stability = 10.0, reps = 2, suspended = true, tags = listOf("suspended")))
        }

        val prog = AnkiStudyPlannerEngine.computeDeckMasteryProgress(
            cards = cards,
            dailyTarget = 30,
            todayCompleted = 12,
            remainingQueueCount = 18,
            avgSecondsPerCard = 12.0,
        )
        assertEquals(1010, prog.totalCards)
        assertEquals(1000, prog.activeCards)
        assertEquals(10, prog.suspendedCards)
        assertEquals(300, prog.touchedCards)
        assertEquals(30.0, prog.coveragePct)
        assertEquals(19.0, prog.masteryPct)
        assertEquals(10.0, prog.maturePct)
        assertEquals(12, prog.today.completedCount)
        assertEquals(30, prog.today.targetCount)
        assertEquals(18, prog.today.remainingCount)
        assertEquals(40.0, prog.today.percent)
        assertEquals(13, prog.today.currentCardOrdinal)
        assertEquals(25, prog.milestone.currentPct)
        assertEquals(50, prog.milestone.nextPct)
        assertEquals(200, prog.milestone.cardsToNext)
        assertEquals(100.0, prog.byStage["lv4"]?.coveragePct)
        assertEquals(100.0, prog.byStage["lv4"]?.masteryPct)

        val exp = AnkiStudyPlannerEngine.filterCardsForExplorer(
            cards = cards,
            query = "Mature 42",
            bucketFilter = "mature",
            stageFilter = "lv4",
        )
        assertEquals(1, exp.matchedCount)
        assertEquals("m_42", exp.cards.first().cardId)

        // Parity probes: reps=0 on review state is unseen; difficulty 3.7 is lv1; lapses=3 is lv4
        assertEquals(
            "unseen",
            AnkiStudyPlannerEngine.classifyCardMaturityBucket(
                AnkiCardSnapshot(cardId = "p1", state = "review", reps = 0, stability = 30.0)
            )
        )
        assertEquals(
            "lv1",
            AnkiStudyPlannerEngine.classifyCardStage(
                AnkiCardSnapshot(cardId = "p2", difficulty = 3.7)
            )
        )
        assertEquals(
            "lv4",
            AnkiStudyPlannerEngine.classifyCardStage(
                AnkiCardSnapshot(cardId = "p3", difficulty = 4.5, lapses = 3)
            )
        )

        // Daily target parity when 30 new + 20 reviews studied today -> targetCount == 50
        val progWithReviews = AnkiStudyPlannerEngine.computeDeckMasteryProgress(
            cards = cards,
            dailyTarget = 30,
            todayCompleted = 20,
            newStudiedToday = 0,
            reviewsStudiedToday = 20,
        )
        assertEquals(50, progWithReviews.today.targetCount)
        assertEquals(30, progWithReviews.today.remainingCount)
    }
}
