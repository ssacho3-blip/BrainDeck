package com.ankistudio.domain.deck

import com.ankistudio.domain.deck.DocumentDeckBuilder.DocumentBlock
import com.ankistudio.domain.deck.DocumentDeckBuilder.ExtractedDocument
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class DocumentDeckBuilderTest {

    @Test
    fun `detects medical category and generates definition and causal cards`() {
        val doc = ExtractedDocument(
            blocks = listOf(
                DocumentBlock(
                    kind = "paragraph",
                    text = "심부전(Heart Failure)이란 심장의 구조적 또는 기능적 이상으로 인해 조직에 필요한 혈액을 공급하지 못하는 임상 증후군이다.",
                    page = 1,
                    confidence = 0.96
                ),
                DocumentBlock(
                    kind = "paragraph",
                    text = "좌심실 박출률 감소 때문에 심박출량 저하 및 폐울혈 호흡곤란이 발생한다.",
                    page = 1,
                    confidence = 0.94
                )
            ),
            titleHint = "내과학_심부전_요약",
            sourceKind = "pdf",
            pageCount = 1
        )

        val plan = DocumentDeckBuilder.buildDeckPlan(doc = doc)

        assertEquals("OK", plan.status)
        assertEquals("medical", plan.category)
        assertTrue(plan.cards.size >= 2)
        val patterns = plan.cards.map { it.pattern }.toSet()
        assertTrue("definition" in patterns)
        assertTrue("causal_compare" in patterns)
    }

    @Test
    fun `filters low confidence OCR blocks and preserves null confidence as unmeasured`() {
        val doc = ExtractedDocument(
            blocks = listOf(
                DocumentBlock(
                    kind = "paragraph",
                    text = "노이즈가 심한 저신뢰도 스캔 문장이라 덱에서 제외되어야 하는 테스트 라인입니다.",
                    page = 2,
                    confidence = 0.42
                ),
                DocumentBlock(
                    kind = "paragraph",
                    text = "FSRS-5(Free Spaced Repetition Scheduler)는 기억 안정성(Stability)과 난이도(Difficulty)를 추적하는 최신 간격 반복 알고리즘이다.",
                    page = 2,
                    confidence = null
                )
            ),
            titleHint = "algorithm_notes",
            sourceKind = "pdf",
            pageCount = 2
        )

        val plan = DocumentDeckBuilder.buildDeckPlan(doc = doc)

        assertEquals("OK", plan.status)
        assertEquals(1, plan.stats.lowConfidenceLines)
        assertEquals(1, plan.stats.unmeasuredConfidenceLines)
        assertTrue(plan.cards.isNotEmpty())
        assertEquals(2, plan.cards.first().sourcePage)
    }

    @Test
    fun `blocks when extracted text is shorter than 40 characters`() {
        val doc = ExtractedDocument(
            blocks = listOf(
                DocumentBlock(
                    kind = "paragraph",
                    text = "짧은 메모",
                    page = 1,
                    confidence = 0.99
                )
            ),
            titleHint = "short",
            sourceKind = "image",
            pageCount = 1
        )

        val plan = DocumentDeckBuilder.buildDeckPlan(doc = doc)

        assertEquals("BLOCKED", plan.status)
        assertEquals("insufficient_text", plan.errorCode)
        assertTrue(plan.cards.isEmpty())
    }

    @Test
    fun `v54 TDD difficulty stratified document deck plan and semantic hinge token selection`() {
        val doc = ExtractedDocument(
            blocks = listOf(
                DocumentBlock(
                    kind = "paragraph",
                    text = "광합성: 식물이 빛에너지를 이용해 이산화탄소와 물로 포도당과 산소를 합성하는 과정이다.",
                    page = 1,
                    confidence = 0.98
                ),
                DocumentBlock(
                    kind = "paragraph",
                    text = "세포호흡: 세포 내 미토콘드리아에서 영양소를 분해하여 ATP 생활 에너지를 얻는 작용이다.",
                    page = 1,
                    confidence = 0.97
                )
            ),
            titleHint = "생물학 핵심 정리",
            sourceKind = "pdf",
            pageCount = 1
        )
        for (diff in listOf("lv1", "lv2", "lv3", "mixed")) {
            val plan = DocumentDeckBuilder.buildDeckPlan(doc = doc, difficultyLevel = diff)
            assertEquals("OK", plan.status, "Failed for difficultyLevel=$diff")
            assertTrue(plan.cards.size >= 2, "Expected >=2 cards for difficultyLevel=$diff")
        }

        // v5.5 Frame 4: lv1, lv2, lv3 must generate distinct cognitive facets + concept:<id> tags
        val planLv1 = DocumentDeckBuilder.buildDeckPlan(doc = doc, difficultyLevel = "lv1")
        val planLv2 = DocumentDeckBuilder.buildDeckPlan(doc = doc, difficultyLevel = "lv2")
        val planLv3 = DocumentDeckBuilder.buildDeckPlan(doc = doc, difficultyLevel = "lv3")
        val planMixed = DocumentDeckBuilder.buildDeckPlan(doc = doc, difficultyLevel = "mixed")

        assertTrue(planLv1.cards.all { it.spec.noteType == "basic" && it.spec.tags.any { t -> t.startsWith("concept:") } })
        assertTrue(planLv2.cards.all { it.spec.noteType == "cloze" && it.spec.frontText.contains("{{c1::") && it.spec.tags.any { t -> t.startsWith("concept:") } })
        assertTrue(planLv3.cards.all { "diff_lv3" in it.spec.tags && it.spec.tags.any { t -> t.startsWith("concept:") } })
        assertTrue(planLv1.cards.first().spec.frontText != planLv3.cards.first().spec.frontText, "lv1 and lv3 fronts must be distinct")
        assertTrue(planMixed.cards.size >= planLv1.cards.size + planLv2.cards.size)
    }
}
