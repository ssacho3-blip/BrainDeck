package com.ankistudio.domain.rea

import com.ankistudio.domain.quiz.AdaptiveQuizEngine
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ReaV56EngineTest {
    @Test
    fun `foldReviewEvents enforces permutation invariance idempotency void and cram non-destructive`() {
        val e1 = ReaV56Engine.ReviewEvent("e1", "c100", "REVIEW", 3, 1700000000000L, "d1", "k1")
        val e1Dup = ReaV56Engine.ReviewEvent("e1-dup", "c100", "REVIEW", 1, 1700000005000L, "d1", "k1")
        val e2Cram = ReaV56Engine.ReviewEvent("e2", "c100", "CRAM", 1, 1700043200000L, "d1", "k2")
        val e3 = ReaV56Engine.ReviewEvent("e3", "c100", "REVIEW", 4, 1700259200000L, "d1", "k3")
        val e4Mistake = ReaV56Engine.ReviewEvent("e4-bad", "c100", "REVIEW", 1, 1700500000000L, "d1", "k4-bad")
        val e5Void = ReaV56Engine.ReviewEvent("e5-void", "c100", "VOID", null, 1700500001000L, "d1", "k5-void", voids = "e4-bad")

        val cleanState = ReaV56Engine.foldReviewEvents(listOf(e1, e3))
        val noisyState = ReaV56Engine.foldReviewEvents(listOf(e5Void, e3, e2Cram, e1Dup, e4Mistake, e1))

        assertEquals(cleanState, noisyState)
        assertEquals(2, cleanState.reps)
        assertEquals(0, cleanState.lapses)
        assertTrue(abs(cleanState.s - 31.148621) < 50.0)
    }

    @Test
    fun `buildSummarySheetRows strips parenthetical explanations for red cellophane mask`() {
        val rows = ReaV56Engine.buildSummarySheetRows(
            listOf("accommodate 뜻은?" to "수용하다 (명사: accommodation)")
        )
        assertEquals(1, rows.size)
        assertEquals("수용하다", rows[0].cleanAnswer)
        assertTrue(rows[0].masked)
    }

    @Test
    fun `buildTypeMatchedQuizOptions never leaks grammar into vocab 4 choice options`() {
        val mixedPool = listOf(
            Triple(101L, "introduce", "소개하다"),
            Triple(102L, "[Lesson 1 핵심문법] 주어가 3인칭 단수일 때 일반동사 현재형 부정문 형태는?", "doesn't (does not) + 동사원형"),
            Triple(103L, "favorite", "가장 좋아하는"),
            Triple(104L, "[한자 8급] 學", "배울 학 (부수: 子)")
        )

        val vocabOptions = AdaptiveQuizEngine.buildTypeMatchedQuizOptions(
            cardId = 101L,
            frontText = "introduce",
            backText = "소개하다",
            candidatePool = mixedPool,
            requiredOptions = 4
        )
        assertEquals(4, vocabOptions.size)
        assertTrue("소개하다" in vocabOptions)
        vocabOptions.forEach { opt ->
            assertFalse("doesn't" in opt || "동사원형" in opt, "Grammar leaked into vocab options: $opt")
            assertFalse("배울 학" in opt, "Hanja leaked into vocab options: $opt")
        }

        val grammarOptions = AdaptiveQuizEngine.buildTypeMatchedQuizOptions(
            cardId = 102L,
            frontText = "[Lesson 1 핵심문법] 주어가 3인칭 단수일 때 일반동사 현재형 부정문 형태는?",
            backText = "doesn't (does not) + 동사원형",
            candidatePool = mixedPool,
            requiredOptions = 4
        )
        assertEquals(4, grammarOptions.size)
        assertTrue("doesn't (does not) + 동사원형" in grammarOptions)
        grammarOptions.forEach { opt ->
            assertFalse(opt == "소개하다" || opt == "가장 좋아하는")
        }

        val customQType = AdaptiveQuizEngine.classifyCardQuestionType(
            frontText = "우리 프로젝트의 최우선 아키텍처 원칙은 무엇인가요?",
            backText = "무결성 우선 설계",
            tags = listOf("custom")
        )
        assertEquals("general_concept", customQType.facetKey)
        assertEquals("history_sci", customQType.categoryKey)
    }

    @Test
    fun `v58 C1 to C4 simple is best drawer summary smart router curriculum segments and fluency calibration`() {
        // C1: Study tools summary
        val s0 = ReaV56Engine.computeStudyToolsSummary("all", "all", false)
        assertEquals(0, s0.activeCount)
        assertTrue(s0.isDefault)
        assertEquals("", s0.summaryBadgeText)

        val s2 = ReaV56Engine.computeStudyToolsSummary("wrong_only", "vocab", false)
        assertEquals(2, s2.activeCount)
        assertFalse(s2.isDefault)
        assertEquals("필터 2개 적용 중", s2.summaryBadgeText)

        // C2: Smart AI Engine router & fail-closed block
        val rAuto = ReaV56Engine.resolveSmartAiEngine(taskType = "card_generate", offlineOnly = false)
        assertEquals("OK", rAuto.status)
        assertEquals("glm-5.3-flash", rAuto.selectedModel)
        assertFalse(rAuto.exposesRawModelName)

        val rBlocked = ReaV56Engine.resolveSmartAiEngine(taskType = "card_generate", manualOverride = "kimi-k2.6")
        assertEquals("BLOCKED_MODEL", rBlocked.status)
        assertEquals("", rBlocked.selectedModel)

        val rUnknown = ReaV56Engine.resolveSmartAiEngine(taskType = "card_generate", manualOverride = "unknown-model-x")
        assertEquals("BLOCKED_MODEL", rUnknown.status)

        val sShuffle = ReaV56Engine.computeStudyToolsSummary("all", "all", false, "interleaved")
        assertEquals(1, sShuffle.activeCount)
        assertEquals("필터 1개 적용 중", sShuffle.summaryBadgeText)

        // C3: Curriculum 3-segment state
        val cSeg = ReaV56Engine.resolveCurriculumSegmentState("collection", 2)
        assertEquals("collection", cSeg.activeSegment)
        assertEquals("🎯 시험범위 조합 (2)", cSeg.combinedTabLabel)
        assertEquals(true, cSeg.visiblePanels["collection"])
        assertEquals(false, cSeg.visiblePanels["textbook"])

        // C4: Response-Time Fluency Calibration & Confusion Matrix
        val baseline = listOf(2000L, 2200L, 2100L, 2300L, 2050L)
        val hesitantGood = ReaV56Engine.calibrateFluencyGrade(3, 9500L, baseline, 2)
        assertEquals(2, hesitantGood.effectiveRating)
        assertEquals("DOWNGRADED_HESITANT_GOOD", hesitantGood.status)

        val zeroMad = ReaV56Engine.calibrateFluencyGrade(3, 4000L, listOf(2000L, 2000L, 2000L, 2000L, 2000L), 2)
        assertEquals(3, zeroMad.effectiveRating)
        assertEquals("BYPASSED_ZERO_MAD", zeroMad.status)

        val tooFast = ReaV56Engine.calibrateFluencyGrade(3, 250L, baseline, 2)
        assertEquals(3, tooFast.effectiveRating)
        assertEquals("BYPASSED_INVALID_RT", tooFast.status)

        val tooSlow = ReaV56Engine.calibrateFluencyGrade(3, 65000L, baseline, 2)
        assertEquals(3, tooSlow.effectiveRating)
        assertEquals("BYPASSED_INVALID_RT", tooSlow.status)

        val coldStart = ReaV56Engine.calibrateFluencyGrade(3, 9500L, listOf(2000L, 2100L, 2200L), 2)
        assertEquals(3, coldStart.effectiveRating)
        assertEquals("BYPASSED_COLD_START", coldStart.status)

        val rReasoning = ReaV56Engine.resolveSmartAiEngine(taskType = "reasoning", offlineOnly = false)
        assertEquals("deepseek-v4.1-flash", rReasoning.selectedModel)
        assertEquals("✨ 스마트 자동 생성", rReasoning.uiLabel)
        assertFalse(rReasoning.exposesRawModelName)

        val fluentGood = ReaV56Engine.calibrateFluencyGrade(3, 750L, listOf(2500L, 2800L, 2600L, 2700L, 2550L), 2)
        assertEquals(4, fluentGood.effectiveRating)
        assertEquals("UPGRADED_FLUENT_GOOD", fluentGood.status)

        val explicitAgain = ReaV56Engine.calibrateFluencyGrade(1, 500L, baseline, 5)
        assertEquals(1, explicitAgain.effectiveRating)
        assertEquals("PRESERVED_EXPLICIT_RATING", explicitAgain.status)

        val conf = ReaV56Engine.updateConfusionMatrixWeight(2.0, 0.0, "c1", "c2", "rev1", emptySet())
        assertEquals(3.0, conf.weight)
        assertTrue(conf.shouldInterleavePeer)
        assertEquals(1.0, ReaV56Engine.computeConfusionIntervalFactor(0.0))
        assertEquals(0.85, ReaV56Engine.computeConfusionIntervalFactor(10.0))

        // C4 Non-interference: fluency rating downgrade (3 -> 2) wins and locks intervalFactor = 1.0
        val coordRewritten = ReaV56Engine.applyC4ReviewCalibration(3, 9500L, baseline, 2, 3.0)
        assertEquals(2, coordRewritten.effectiveRating)
        assertEquals(1.0, coordRewritten.effectiveIntervalFactor)
        assertFalse(coordRewritten.intervalScaledByConfusion)

        val coordUnrewritten = ReaV56Engine.applyC4ReviewCalibration(3, 2100L, baseline, 1, 2.0)
        assertEquals(3, coordUnrewritten.effectiveRating)
        assertEquals(0.9, coordUnrewritten.effectiveIntervalFactor)
        assertTrue(coordUnrewritten.intervalScaledByConfusion)
    }
}
