package com.ankistudio.domain.quiz

import com.ankistudio.domain.fsrs.Fsrs5Engine
import com.ankistudio.domain.fsrs.Fsrs5Engine.CardMemoryState
import com.ankistudio.domain.fsrs.Fsrs5Engine.Rating
import com.ankistudio.domain.quiz.AdaptiveQuizEngine.AgeTier
import com.ankistudio.domain.quiz.AdaptiveQuizEngine.CandidateDistractor
import com.ankistudio.domain.quiz.AdaptiveQuizEngine.QuestionFacet
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AdaptiveQuizEngineTest {

    @Test
    fun `T4 lapses increments only when state is review and rating is AGAIN`() {
        val newAgain = Fsrs5Engine.stepFsrs(
            CardMemoryState(state = "new", reps = 0, lapses = 0),
            Rating.AGAIN
        )
        assertEquals(0, newAgain.memory.lapses)
        assertEquals("learning", newAgain.memory.state)

        val relearningAgain = Fsrs5Engine.stepFsrs(
            CardMemoryState(state = "relearning", reps = 3, stability = 1.5, difficulty = 6.0, lapses = 1),
            Rating.AGAIN,
            elapsedDays = 1.0
        )
        assertEquals(1, relearningAgain.memory.lapses)

        val reviewAgain = Fsrs5Engine.stepFsrs(
            CardMemoryState(state = "review", reps = 4, stability = 8.0, difficulty = 5.0, lapses = 1),
            Rating.AGAIN,
            elapsedDays = 5.0
        )
        assertEquals(2, reviewAgain.memory.lapses)
    }

    @Test
    fun `T16 recognition caps at GOOD for 4-choice and HARD for 2-choice and promotes quizStage`() {
        val mc4 = AdaptiveQuizEngine.gradeInteraction(
            ageTier = AgeTier.JUNIOR,
            interactionMode = "multiple_choice",
            isCorrect = true,
            attemptCount = 1,
            optionCount = 4,
            responseMs = 1500L,
            currentQuizStage = 0,
            currentConsecutiveSuccesses = 1,
            currentStability = 3.5
        )
        assertEquals(Rating.GOOD, mc4.rating)
        assertEquals("recognition", mc4.evidenceClass)
        assertEquals(1, mc4.nextQuizStage)
        assertEquals(0, mc4.nextConsecutiveSuccesses)

        val mc2 = AdaptiveQuizEngine.gradeInteraction(
            ageTier = AgeTier.JUNIOR,
            interactionMode = "multiple_choice",
            isCorrect = true,
            attemptCount = 1,
            optionCount = 2,
            responseMs = 1200L
        )
        assertEquals(Rating.HARD, mc2.rating)

        val secondAttempt = AdaptiveQuizEngine.gradeInteraction(
            ageTier = AgeTier.TEEN,
            interactionMode = "multiple_choice",
            isCorrect = true,
            attemptCount = 2,
            optionCount = 4,
            currentQuizStage = 2
        )
        assertEquals(Rating.AGAIN, secondAttempt.rating)
        assertEquals(1, secondAttempt.nextQuizStage)
    }

    @Test
    fun `T17 and T23 selectDistractors enforces Forbidden Wins and Answer Set Non Overlap`() {
        val candidates = listOf(
            CandidateDistractor(
                entryKey = "hanja:homophone_forbidden",
                displayText = "락",
                answerSet = setOf("락"),
                relationsToTarget = setOf("similar_shape", "homophone"),
                weight = 0.99
            ),
            CandidateDistractor(
                entryKey = "hanja:dueum_overlap",
                displayText = "낙",
                answerSet = setOf("낙"),
                relationsToTarget = setOf("similar_shape"),
                weight = 0.95
            ),
            CandidateDistractor(
                entryKey = "hanja:valid_1",
                displayText = "학",
                answerSet = setOf("학"),
                relationsToTarget = setOf("similar_shape"),
                weight = 0.90
            ),
            CandidateDistractor(
                entryKey = "hanja:valid_2",
                displayText = "교",
                answerSet = setOf("교"),
                relationsToTarget = setOf("same_radical"),
                weight = 0.85
            ),
            CandidateDistractor(
                entryKey = "hanja:valid_3",
                displayText = "생",
                answerSet = setOf("생"),
                relationsToTarget = setOf("similar_shape"),
                weight = 0.80
            )
        )
        val res = AdaptiveQuizEngine.selectDistractors(
            targetKey = "hanja:U+6A02",
            targetDisplay = "락",
            targetAnswerSet = setOf("락", "악", "요", "낙"),
            questionFacet = QuestionFacet.HANJA_EUM,
            candidates = candidates,
            desiredDistractorCount = 3
        )
        assertEquals("multiple_choice", res.mode)
        assertEquals(listOf("락", "학", "교", "생"), res.options)
    }

    @Test
    fun `T18 and T22 CJK compat preservation and Hangul Jamo dictation grading`() {
        val compat = AdaptiveQuizEngine.preserveCjkCompatBeforeNfc("\uF914")
        assertEquals(listOf("U+F914"), compat.compatCodepoints)
        assertEquals("樂", compat.nfcText)

        val exact = AdaptiveQuizEngine.gradeDictationJamo("맞춤법", "맞춤법", AgeTier.JUNIOR)
        assertEquals(Rating.EASY, exact.recommendedRating)
        assertEquals(0, exact.jamoDistance)

        val nearMiss = AdaptiveQuizEngine.gradeDictationJamo("마춤법", "맞춤법", AgeTier.JUNIOR)
        assertEquals(Rating.HARD, nearMiss.recommendedRating)
        assertEquals(1, nearMiss.jamoDistance)
    }
}
