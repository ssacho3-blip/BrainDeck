package com.ankistudio.domain.quiz

import com.ankistudio.domain.catalog.BuiltInCurriculumCatalog
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

    @Test
    fun `T27 and T28 BuiltInCurriculumCatalog provides Mid-1 Dong-A Yoon 8 lessons and Hanja grades 8 to 3`() {
        val textbooks = BuiltInCurriculumCatalog.listTextbooks()
        assertEquals(
            setOf(
                "kr.mid1.eng.donga_yoon.2022",
                "kr.mid2.eng.donga_yoon.2022",
                "kr.mid2.hist.miraeen.2022",
                "kr.high1.sci.visang.2022"
            ),
            textbooks.map { it.textbookId }.toSet()
        )
        val mid1 = textbooks.first { it.textbookId == "kr.mid1.eng.donga_yoon.2022" }
        assertEquals(8, mid1.units.size)
        assertEquals(35, mid1.entries.size)
        assertEquals(10, mid1.units.first().pageStart)
        assertEquals(153, mid1.units.last().pageEnd)

        val examCards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = "kr.mid1.eng.donga_yoon.2022",
            selectedUnitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01", "kr.mid1.eng.donga_yoon.2022:U02"),
            pageStart = 10,
            pageEnd = 35
        )
        assertTrue(examCards.isNotEmpty())
        assertTrue(examCards.any { it.spec.frontText.contains("introduce") })
        assertTrue(examCards.any { it.spec.frontText.contains("delicious") })
        assertTrue(examCards.none { it.spec.frontText.contains("volunteer") }) // Lesson 3 excluded

        val expectedCollections = setOf(
            "hanja-grade:8geup",
            "hanja-grade:7geup",
            "hanja-grade:6geup",
            "hanja-grade:5geup",
            "hanja-grade:4geup",
            "hanja-grade:3geup",
            "moe-hanja-1800:middle",
            "ko-dictation:grade1-2",
            "moe-eng:elementary",
            "khist:essential",
            "exam-eng:toeic-core",
            "exam-ja:jlpt-n5-n3",
            "ko-idiom:essential",
            "law-statute:constitution",
            "sci-element-formula:core",
            "cert-it:core"
        )
        val collections = BuiltInCurriculumCatalog.listCollections().map { it.collectionId }.toSet()
        assertEquals(expectedCollections, collections)
        for (colId in expectedCollections) {
            val cards = BuiltInCurriculumCatalog.buildCollectionCards(colId)
            assertTrue(cards.size >= 3, "Expected >= 3 cards for $colId")
        }
    }

    @Test
    fun `v53 3-tier typed answer understanding grader and Anki queue counters`() {
        val exact = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding("소개하다", "소개하다")
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.EXACT, exact.verdict)
        assertTrue(exact.recommendedRating.code >= 3)

        val partial = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding("산소 운반", "산소 운반 및 이산화탄소 배출")
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.PARTIAL, partial.verdict)
        assertEquals(Rating.HARD, partial.recommendedRating)
        assertTrue(partial.missingTerms.isNotEmpty())

        val unknown = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding("", "산소 운반 및 이산화탄소 배출")
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.UNKNOWN, unknown.verdict)
        assertEquals(Rating.AGAIN, unknown.recommendedRating)

        val counts = AdaptiveQuizEngine.computeAnkiQueueCounts(
            listOf("new" to 0, "relearning" to 2, "review" to 0)
        )
        assertEquals(1, counts.newCount)
        assertEquals(1, counts.learnCount)
        assertEquals(1, counts.reviewCount)
    }

    @Test
    fun `v54 zero front spoiler and difficulty stratified card generation`() {
        val khistCards = BuiltInCurriculumCatalog.buildCollectionCards("khist:essential", difficultyLevel = "standard")
        assertTrue(khistCards.none { it.spec.frontText.contains("훈민정음") })
        assertTrue(khistCards.none { it.spec.frontText.contains("강화도 조약") })
        assertTrue(khistCards.none { it.spec.frontText.contains("갑신정변") })

        val lv1Cards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = "kr.mid1.eng.donga_yoon.2022",
            selectedUnitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01"),
            difficultyLevel = "lv1"
        )
        val lv2Cards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = "kr.mid1.eng.donga_yoon.2022",
            selectedUnitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01"),
            difficultyLevel = "lv2"
        )
        val lv3Cards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = "kr.mid1.eng.donga_yoon.2022",
            selectedUnitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01"),
            difficultyLevel = "lv3"
        )
        val mixedCards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = "kr.mid1.eng.donga_yoon.2022",
            selectedUnitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01"),
            difficultyLevel = "mixed"
        )
        assertTrue(lv1Cards.all { it.spec.noteType == "basic" })
        assertTrue(lv2Cards.all { it.spec.noteType == "cloze" && it.spec.frontText.contains("{{c1::") })
        assertTrue(lv3Cards.all { "diff_lv3" in it.spec.tags })
        assertEquals(lv1Cards.size + lv2Cards.size + lv3Cards.size, mixedCards.size)
    }

    @Test
    fun `v54 2-step progressive choseong hint and clean target extraction`() {
        val (target, extra) = AdaptiveQuizEngine.extractCleanTargetAnswer(
            frontText = "[Lv.2 문맥 빈칸] Let me {{c1::introduce}} myself to the class.",
            backText = "introduce\n💡 해설: 동사 '소개하다' — Let me introduce myself (나를 소개할게)"
        )
        assertEquals("introduce", target)
        assertTrue(extra.contains("소개하다"))

        val koHint1 = AdaptiveQuizEngine.generateProgressiveHint(
            frontText = "조선 세종 25년(1443) 백성을 가르치는 바른 소리라는 뜻으로 창제한 문자는?",
            backText = "훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포",
            step = 1
        )
        assertTrue(koHint1.contains("ㅎ ㅁ ㅈ ㅇ"))
        assertTrue(!koHint1.contains("훈민정음"))

        val koHint2 = AdaptiveQuizEngine.generateProgressiveHint(
            frontText = "조선 세종 25년(1443) 백성을 가르치는 바른 소리라는 뜻으로 창제한 문자는?",
            backText = "훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포",
            step = 2
        )
        assertTrue(koHint2.contains("'훈...'"))
        assertTrue(!koHint2.contains("훈민정음"))
    }

    @Test
    fun `v54 multi-combination exam scope deck and interleaved random shuffle`() {
        val combined = BuiltInCurriculumCatalog.buildCombinedExamScopeCards(
            scopes = listOf(
                BuiltInCurriculumCatalog.CombinedScopeItem(
                    sourceType = "textbook",
                    refId = "kr.mid1.eng.donga_yoon.2022",
                    unitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01", "kr.mid1.eng.donga_yoon.2022:U02"),
                    label = "중1 영어 Lesson 1~2"
                ),
                BuiltInCurriculumCatalog.CombinedScopeItem(
                    sourceType = "textbook",
                    refId = "kr.mid2.hist.miraeen.2022",
                    unitIds = setOf("kr.mid2.hist.miraeen.2022:U01"),
                    label = "중2 역사 Ⅰ-1"
                ),
                BuiltInCurriculumCatalog.CombinedScopeItem(
                    sourceType = "collection",
                    refId = "hanja-grade:8geup",
                    label = "어문회 8급 한자"
                )
            ),
            difficultyLevel = "mixed",
            interleaveShuffle = true
        )
        assertTrue(combined.size >= 15)
        // Verify cards from multiple subjects are mixed in the first 6 cards
        val firstSixTags = combined.take(6).flatMap { it.spec.tags }.toSet()
        assertTrue(firstSixTags.size >= 3)
    }

    @Test
    fun `v54 TDD parenthetical Hanja and POS tag primary answer grading and 6-2-2 anti-streak interleaving`() {
        // 1. Typing primary answer without parenthetical Hanja/year/POS tag must grade as EXACT (100%)
        val hunmin = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = "훈민정음",
            expectedAnswer = "훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포"
        )
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.EXACT, hunmin.verdict)
        assertEquals(100, hunmin.scorePct)

        val ganghwa = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = "강화도 조약",
            expectedAnswer = "강화도 조약 (조일수호조규, 1876)\n💡 해설: 최초의 근대적 불평등 조약"
        )
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.EXACT, ganghwa.verdict)
        assertEquals(100, ganghwa.scorePct)

        val intro = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = "소개하다",
            expectedAnswer = "소개하다 (동사)\n💡 해설: Let me introduce myself."
        )
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.EXACT, intro.verdict)
        assertEquals(100, intro.scorePct)

        // Full annotated form also grades as EXACT (100%)
        val hunminFull = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = "훈민정음 (訓民正音)",
            expectedAnswer = "훈민정음 (訓民正音)\n💡 해설: 1443년 창제, 1446년 반포"
        )
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.EXACT, hunminFull.verdict)
        assertEquals(100, hunminFull.scorePct)

        val ganghwaFull = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = "강화도 조약 (조일수호조규, 1876)",
            expectedAnswer = "강화도 조약 (조일수호조규, 1876)\n💡 해설: 최초의 근대적 불평등 조약"
        )
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.EXACT, ganghwaFull.verdict)
        assertEquals(100, ganghwaFull.scorePct)

        val introFull = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = "소개하다 (동사)",
            expectedAnswer = "소개하다 (동사)\n💡 해설: Let me introduce myself."
        )
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.EXACT, introFull.verdict)
        assertEquals(100, introFull.scorePct)

        // Conflicting wrong year '1877' must NOT grade as EXACT
        val ganghwaWrongYear = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = "강화도 조약 1877",
            expectedAnswer = "강화도 조약 (조일수호조규, 1876)\n💡 해설: 최초의 근대적 불평등 조약"
        )
        assertEquals(AdaptiveQuizEngine.TypedUnderstandingVerdict.PARTIAL, ganghwaWrongYear.verdict)
        assertTrue(ganghwaWrongYear.scorePct <= 55)

        // 2. Step 1 & Step 2 hints must exclude parenthetical Hanja from charCount and mask primary target in Step 2
        val h1 = AdaptiveQuizEngine.generateProgressiveHint(
            frontText = "조선 세종이 창제한 문자는?",
            backText = "훈민정음 (訓民正音)\n💡 해설: 조선 세종이 훈민정음을 창제함",
            step = 1
        )
        assertTrue(h1.contains("4자"), "Expected 4자 in step 1 hint, got: $h1")
        assertTrue(!h1.contains("훈민정음"))

        val h2 = AdaptiveQuizEngine.generateProgressiveHint(
            frontText = "조선 세종이 창제한 문자는?",
            backText = "훈민정음 (訓民正音)\n💡 해설: 조선 세종이 훈민정음을 창제함",
            step = 2
        )
        assertTrue(!h2.contains("훈민정음"), "Step 2 hint leaked spoiler: $h2")

        val enH1 = AdaptiveQuizEngine.generateProgressiveHint(
            frontText = "[Lv.2 문맥 빈칸] Let me {{c1::introduce}} myself.",
            backText = "introduce (동사)\n💡 해설: Introduce yourself to the class.",
            step = 1
        )
        val enH2 = AdaptiveQuizEngine.generateProgressiveHint(
            frontText = "[Lv.2 문맥 빈칸] Let me {{c1::introduce}} myself.",
            backText = "introduce (동사)\n💡 해설: Introduce yourself to the class.",
            step = 2
        )
        assertTrue(enH1.contains("9자"), "Expected 9자 for introduce, got: $enH1")
        assertTrue(!enH2.lowercase().contains("introduce"), "Step 2 leaked Introduce: $enH2")

        // 3. 6:2:2 unequal buckets must have zero streaks > 2 across all 10 items
        val rawItems = (1..6).map { "eng" to it } + (7..8).map { "hist" to it } + (9..10).map { "hanja" to it }
        val mixed = AdaptiveQuizEngine.interleaveStudyQueue(
            items = rawItems,
            bucketSelector = { it.first },
            seed = 42
        )
        assertEquals(10, mixed.size)
        var streak = 0
        var lastBucket: String? = null
        for ((bucket, _) in mixed) {
            if (bucket == lastBucket) {
                streak += 1
            } else {
                lastBucket = bucket
                streak = 1
            }
            assertTrue(streak <= 2, "Kotlin interleaveStudyQueue violated anti-streak <= 2 on 6:2:2: ${mixed.map { it.first }}")
        }

        // 4. Termination & multiset preservation on empty, single-bucket, 5:1, and 8:1:1
        assertTrue(AdaptiveQuizEngine.interleaveStudyQueue(emptyList<Pair<String, Int>>(), { it.first }, 42).isEmpty())
        val singleBucket = (1..4).map { "u1" to it }
        assertEquals((1..4).toSet(), AdaptiveQuizEngine.interleaveStudyQueue(singleBucket, { it.first }, 42).map { it.second }.toSet())
        val ratio811 = (1..8).map { "u1" to it } + listOf("u2" to 9, "u3" to 10)
        val out811 = AdaptiveQuizEngine.interleaveStudyQueue(ratio811, { it.first }, 42)
        assertEquals((1..10).toSet(), out811.map { it.second }.toSet())
    }

    @Test
    fun `v55 TDD five memory science frames - 1-Card 1-Mode, EvidenceRatingGuard, SiblingBurying, and NoLv2Spoiler`() {
        // Frame 2: 1-Card 1-Mode resolution
        assertEquals("choice", AdaptiveQuizEngine.resolveCardSolveMode("adaptive", reps = 0))
        assertEquals("typing", AdaptiveQuizEngine.resolveCardSolveMode("adaptive", reps = 2))
        assertEquals("flip", AdaptiveQuizEngine.resolveCardSolveMode("flip", reps = 3))

        // Frame 3: EvidenceRatingGuard
        val preReveal = AdaptiveQuizEngine.resolveAllowedRatings(
            isRevealed = false,
            hintStep = 0,
            ageTier = AgeTier.ADULT
        )
        assertTrue(preReveal.allowedRatings.isEmpty())

        val wrongGuard = AdaptiveQuizEngine.resolveAllowedRatings(
            isRevealed = true,
            choiceCorrect = false,
            hintStep = 0,
            ageTier = AgeTier.ADULT
        )
        assertEquals(listOf(Rating.AGAIN), wrongGuard.allowedRatings)
        assertEquals(Rating.AGAIN, wrongGuard.recommendedRating)

        val hintGuard = AdaptiveQuizEngine.resolveAllowedRatings(
            isRevealed = true,
            choiceCorrect = true,
            hintStep = 1,
            ageTier = AgeTier.ADULT
        )
        assertEquals(listOf(Rating.AGAIN, Rating.HARD), hintGuard.allowedRatings)
        assertEquals(Rating.HARD, hintGuard.recommendedRating)

        val partialGuard = AdaptiveQuizEngine.resolveAllowedRatings(
            isRevealed = true,
            typedVerdict = AdaptiveQuizEngine.TypedUnderstandingVerdict.PARTIAL,
            hintStep = 0,
            ageTier = AgeTier.ADULT
        )
        assertEquals(listOf(Rating.AGAIN, Rating.HARD, Rating.GOOD), partialGuard.allowedRatings)
        assertEquals(Rating.HARD, partialGuard.recommendedRating)

        // Frame 4: No Lv.2 "➔ 핵심 정답:" suffix and Sibling Burying per concept:<id>
        val lv2Cards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = "kr.mid1.eng.donga_yoon.2022",
            selectedUnitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01"),
            difficultyLevel = "lv2"
        )
        assertTrue(lv2Cards.none { it.spec.frontText.contains("➔ 핵심 정답:") })
        assertTrue(lv2Cards.all { it.spec.tags.any { t -> t.startsWith("concept:") } })

        val mixedCards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = "kr.mid1.eng.donga_yoon.2022",
            selectedUnitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01"),
            difficultyLevel = "mixed"
        )
        val sessionDeduped = AdaptiveQuizEngine.deduplicateSessionSiblings(
            items = mixedCards,
            tagsSelector = { it.spec.tags },
            stateSelector = { "new" }
        )
        assertEquals(lv2Cards.size, sessionDeduped.size, "Sibling burying must keep exactly 1 card per concept in a single session")
    }
}
