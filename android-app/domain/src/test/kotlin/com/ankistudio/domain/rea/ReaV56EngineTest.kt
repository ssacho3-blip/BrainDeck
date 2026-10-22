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
}
