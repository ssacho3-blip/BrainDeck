package com.ankistudio.domain.catalog

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class BrainPackStoreCatalogTest {

    @Test
    fun `starter pack is unlocked by default while paid packs require purchase`() {
        val freeCheck = BrainPackStoreCatalog.checkRefEntitlement(
            targetRefId = "hanja-grade:8geup",
            unlockedPackIds = emptySet()
        )
        assertTrue(freeCheck.allowed)
        assertEquals("entitled", freeCheck.reason)

        val paidCheck = BrainPackStoreCatalog.checkRefEntitlement(
            targetRefId = "kr.mid1.eng.donga_yoon.2022",
            unlockedPackIds = emptySet()
        )
        assertFalse(paidCheck.allowed)
        assertEquals("pack.mid1.eng.donga_yoon.full", paidCheck.requiredPackId)
        assertEquals(990, paidCheck.priceKrw)

        val afterUnlock = BrainPackStoreCatalog.checkRefEntitlement(
            targetRefId = "kr.mid1.eng.donga_yoon.2022",
            unlockedPackIds = setOf("pack.mid1.eng.donga_yoon.full")
        )
        assertTrue(afterUnlock.allowed)
    }

    @Test
    fun `filterCatalog returns category-matched BrainPacks`() {
        val allPacks = BrainPackStoreCatalog.filterCatalog("all")
        assertEquals(9, allPacks.size)

        val textbooks = BrainPackStoreCatalog.filterCatalog("k12_textbook")
        assertEquals(4, textbooks.size)

        val product = BrainPackStoreCatalog.getProductById("pack.exam.hanja_master")
        assertNotNull(product)
        assertEquals(1500, product?.priceKrw)
    }
}
