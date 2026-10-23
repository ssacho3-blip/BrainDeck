package com.ankistudio.domain.catalog

import com.ankistudio.domain.deck.DocumentDeckBuilder.GeneratedCardSpec
import com.ankistudio.domain.deck.DocumentDeckBuilder.SourcedCard

/**
 * Pure JVM Kotlin Built-in Reference & School Textbook Exam-Scope Catalog (T21, T27, T28).
 * Strictly zero `android.*` or `androidx.*` imports.
 */
object BuiltInCurriculumCatalog {

    data class CurriculumUnitMeta(
        val unitId: String,
        val unitOrdinal: Int,
        val unitCodeLabel: String,
        val unitTitle: String,
        val pageStart: Int,
        val pageEnd: Int,
        val achievementCode: String
    )

    data class TextbookEntryItem(
        val entryKey: String,
        val unitId: String,
        val pageNo: Int,
        val frontText: String,
        val backText: String,
        val roleInUnit: String,
        val importanceTier: Int = 1
    )

    data class TextbookCatalogItem(
        val textbookId: String,
        val title: String,
        val publisherName: String,
        val authorLabel: String,
        val schoolLevel: String,
        val grade: Int,
        val subjectCode: String,
        val curriculumRevision: String,
        val units: List<CurriculumUnitMeta>,
        val entries: List<TextbookEntryItem>
    )

    data class CollectionCatalogItem(
        val collectionId: String,
        val title: String,
        val category: String,
        val ageRecommendation: String,
        val cards: List<SourcedCard>
    )

    private const val MID1_DONGA_YOON = "kr.mid1.eng.donga_yoon.2022"
    private const val MID2_DONGA_YOON = "kr.mid2.eng.donga_yoon.2022"
    private const val MID2_MIRAEEN_HIST = "kr.mid2.hist.miraeen.2022"
    private const val HIGH1_VISANG_SCI = "kr.high1.sci.visang.2022"

    private val TEXTBOOKS: List<TextbookCatalogItem> = listOf(
        TextbookCatalogItem(
            textbookId = MID1_DONGA_YOON,
            title = "중학교 영어 1 (동아출판 윤정미)",
            publisherName = "동아출판",
            authorLabel = "윤정미 외",
            schoolLevel = "middle",
            grade = 1,
            subjectCode = "language",
            curriculumRevision = "2022",
            units = listOf(
                CurriculumUnitMeta("$MID1_DONGA_YOON:U01", 1, "Lesson 1", "My Happy School Life", 10, 27, "[9영01-01]"),
                CurriculumUnitMeta("$MID1_DONGA_YOON:U02", 2, "Lesson 2", "Delicious World", 28, 45, "[9영02-02]"),
                CurriculumUnitMeta("$MID1_DONGA_YOON:U03", 3, "Lesson 3", "Spend Smart, Save Smart", 46, 63, "[9영02-05]"),
                CurriculumUnitMeta("$MID1_DONGA_YOON:U04", 4, "Lesson 4", "Walk Around the Neighborhood", 64, 81, "[9영02-07]"),
                CurriculumUnitMeta("$MID1_DONGA_YOON:U05", 5, "Lesson 5", "Follow Your Dreams", 82, 99, "[9영03-01]"),
                CurriculumUnitMeta("$MID1_DONGA_YOON:U06", 6, "Lesson 6", "Enjoy Art, Connect Hearts", 100, 117, "[9영03-04]"),
                CurriculumUnitMeta("$MID1_DONGA_YOON:U07", 7, "Lesson 7", "Science Full of Wonder", 118, 135, "[9영04-01]"),
                CurriculumUnitMeta("$MID1_DONGA_YOON:U08", 8, "Lesson 8", "Viva South America!", 136, 153, "[9영04-03]")
            ),
            entries = listOf(
                // Lesson 1 (p.10~27)
                TextbookEntryItem("word:introduce", "$MID1_DONGA_YOON:U01", 12, "introduce", "소개하다 (동사)", "core_vocab"),
                TextbookEntryItem("word:classmate", "$MID1_DONGA_YOON:U01", 13, "classmate", "반 친구, 급우 (명사)", "core_vocab"),
                TextbookEntryItem("word:favorite", "$MID1_DONGA_YOON:U01", 15, "favorite", "가장 좋아하는 (형용사)", "core_vocab"),
                TextbookEntryItem("word:subject", "$MID1_DONGA_YOON:U01", 16, "subject", "과목, 주제 (명사)", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u1_be", "$MID1_DONGA_YOON:U01", 20, "[Lesson 1 핵심문법] 주어가 3인칭 단수일 때 일반동사 현재형 부정문 형태는?", "doesn't (does not) + 동사원형", "key_grammar"),
                // Lesson 2 (p.28~45)
                TextbookEntryItem("word:delicious", "$MID1_DONGA_YOON:U02", 30, "delicious", "매우 맛있는 (형용사)", "core_vocab"),
                TextbookEntryItem("word:healthy", "$MID1_DONGA_YOON:U02", 32, "healthy", "건강에 좋은, 건강한 (형용사)", "core_vocab"),
                TextbookEntryItem("word:dessert", "$MID1_DONGA_YOON:U02", 35, "dessert", "후식, 디저트 (명사)", "core_vocab"),
                TextbookEntryItem("word:vegetable", "$MID1_DONGA_YOON:U02", 38, "vegetable", "채소, 야채 (명사)", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u2_prog", "$MID1_DONGA_YOON:U02", 40, "[Lesson 2 핵심문법] 현재진행형과 조동사 can/will 뒤의 동사 형태는?", "현재진행형: am/are/is + V-ing · 조동사 can/will + 동사원형", "key_grammar"),
                // Lesson 3 (p.46~63)
                TextbookEntryItem("word:volunteer", "$MID1_DONGA_YOON:U03", 48, "volunteer", "자원봉사자; 자원봉사하다", "core_vocab"),
                TextbookEntryItem("word:donate", "$MID1_DONGA_YOON:U03", 50, "donate", "기부하다, 기증하다 (동사)", "core_vocab"),
                TextbookEntryItem("word:secondhand", "$MID1_DONGA_YOON:U03", 52, "secondhand", "중고의, 간접의 (형용사)", "core_vocab"),
                TextbookEntryItem("word:treasure", "$MID1_DONGA_YOON:U03", 55, "treasure", "보물, 소중한 것 (명사)", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u3_past", "$MID1_DONGA_YOON:U03", 58, "[Lesson 3 핵심문법] 일반동사 과거시제의 의문문과 부정문 조동사는?", "Did + 주어 + 동사원형? / didn't + 동사원형", "key_grammar"),
                // Lesson 4 (p.64~81)
                TextbookEntryItem("word:neighborhood", "$MID1_DONGA_YOON:U04", 66, "neighborhood", "동네, 이웃 (명사)", "core_vocab"),
                TextbookEntryItem("word:bakery", "$MID1_DONGA_YOON:U04", 68, "bakery", "빵집, 제과점 (명사)", "core_vocab"),
                TextbookEntryItem("word:straight", "$MID1_DONGA_YOON:U04", 70, "straight", "곧장, 똑바로 (부사)", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u4_there", "$MID1_DONGA_YOON:U04", 76, "[Lesson 4 핵심문법] '~이 있다' 구문에서 단수명사·복수명사 수일치 규칙은?", "There is + 단수명사 / There are + 복수명사", "key_grammar"),
                // Lesson 5 (p.82~99)
                TextbookEntryItem("word:career", "$MID1_DONGA_YOON:U05", 84, "career", "직업, 진로, 경력 (명사)", "core_vocab"),
                TextbookEntryItem("word:creative", "$MID1_DONGA_YOON:U05", 86, "creative", "창의적인, 독창적인 (형용사)", "core_vocab"),
                TextbookEntryItem("word:talent", "$MID1_DONGA_YOON:U05", 89, "talent", "재능, 소질 (명사)", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u5_toinf", "$MID1_DONGA_YOON:U05", 94, "[Lesson 5 핵심문법] want, hope, plan, decide가 목적어로 취하는 형태는?", "to부정사 (to + 동사원형, 명사적 용법)", "key_grammar"),
                // Lesson 6 (p.100~117)
                TextbookEntryItem("word:exhibition", "$MID1_DONGA_YOON:U06", 102, "exhibition", "전시회 (명사)", "core_vocab"),
                TextbookEntryItem("word:painting", "$MID1_DONGA_YOON:U06", 105, "painting", "그림, 회화 (명사)", "core_vocab"),
                TextbookEntryItem("word:character", "$MID1_DONGA_YOON:U06", 108, "character", "등장인물, 성격, 글자 (명사)", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u6_gerund", "$MID1_DONGA_YOON:U06", 112, "[Lesson 6 핵심문법] enjoy, finish, mind가 목적어로 취하는 형태는?", "동명사 (V-ing)", "key_grammar"),
                // Lesson 7 (p.118~135)
                TextbookEntryItem("word:gravity", "$MID1_DONGA_YOON:U07", 120, "gravity", "중력 (명사)", "core_vocab"),
                TextbookEntryItem("word:float", "$MID1_DONGA_YOON:U07", 122, "float", "(물·공기 중에) 뜨다 (동사)", "core_vocab"),
                TextbookEntryItem("word:experiment", "$MID1_DONGA_YOON:U07", 125, "experiment", "실험; 실험하다", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u7_comp", "$MID1_DONGA_YOON:U07", 130, "[Lesson 7 핵심문법] 형용사·부사의 비교급과 최상급 구문 형태는?", "비교급(-er/more) + than / the + 최상급(-est/most) + in(of)", "key_grammar"),
                // Lesson 8 (p.136~153)
                TextbookEntryItem("word:continent", "$MID1_DONGA_YOON:U08", 138, "continent", "대륙 (명사)", "core_vocab"),
                TextbookEntryItem("word:waterfall", "$MID1_DONGA_YOON:U08", 140, "waterfall", "폭포 (명사)", "core_vocab"),
                TextbookEntryItem("word:ancient", "$MID1_DONGA_YOON:U08", 144, "ancient", "고대의, 옛날의 (형용사)", "core_vocab"),
                TextbookEntryItem("grammar:mid1_u8_sense", "$MID1_DONGA_YOON:U08", 148, "[Lesson 8 핵심문법] 감각동사(look, sound, smell, taste, feel) 뒤에 오는 품사는?", "형용사 (부사 -ly 사용 불가)", "key_grammar")
            )
        ),
        TextbookCatalogItem(
            textbookId = MID2_DONGA_YOON,
            title = "중학교 영어 2 (동아출판 윤정미)",
            publisherName = "동아출판",
            authorLabel = "윤정미 외",
            schoolLevel = "middle",
            grade = 2,
            subjectCode = "language",
            curriculumRevision = "2022",
            units = listOf(
                CurriculumUnitMeta("$MID2_DONGA_YOON:U01", 1, "Lesson 1", "Express Yourself", 10, 19, "[9영02-01]"),
                CurriculumUnitMeta("$MID2_DONGA_YOON:U02", 2, "Lesson 2", "Food and Culture", 20, 39, "[9영02-04]"),
                CurriculumUnitMeta("$MID2_DONGA_YOON:U03", 3, "Lesson 3", "Green Earth", 40, 59, "[9영03-02]")
            ),
            entries = listOf(
                TextbookEntryItem("word:express", "$MID2_DONGA_YOON:U01", 12, "express", "표현하다 (동사)", "core_vocab"),
                TextbookEntryItem("word:confident", "$MID2_DONGA_YOON:U01", 16, "confident", "자신감 있는 (형용사)", "core_vocab"),
                TextbookEntryItem("word:tradition", "$MID2_DONGA_YOON:U02", 22, "tradition", "전통 (명사)", "core_vocab"),
                TextbookEntryItem("word:recipe", "$MID2_DONGA_YOON:U02", 31, "recipe", "조리법, 레시피 (명사)", "core_vocab"),
                TextbookEntryItem("word:environment", "$MID2_DONGA_YOON:U03", 45, "environment", "환경 (명사)", "core_vocab")
            )
        ),
        TextbookCatalogItem(
            textbookId = MID2_MIRAEEN_HIST,
            title = "중학교 역사 ① (미래엔)",
            publisherName = "미래엔",
            authorLabel = "김태웅 외",
            schoolLevel = "middle",
            grade = 2,
            subjectCode = "social",
            curriculumRevision = "2022",
            units = listOf(
                CurriculumUnitMeta("$MID2_MIRAEEN_HIST:U01", 1, "Ⅰ단원", "문명의 발생과 고대 세계의 형성", 10, 35, "[9역01-01]")
            ),
            entries = listOf(
                TextbookEntryItem("khist:hunmin_1443", "$MID2_MIRAEEN_HIST:U01", 18, "🏛️ [중2 역사①] 조선 세종이 1443년에 창제하고 1446년에 반포한 우리 고유의 28자 문자는?", "훈민정음 (창제 1443 · 반포 1446)\n💡 해설: 백성을 가르치는 바른 소리라는 뜻으로 집현전 학자들과 함께 창제했습니다.", "historical_event"),
                TextbookEntryItem("khist:ganghwa_1876", "$MID2_MIRAEEN_HIST:U01", 26, "🏛️ [중2 역사①] 1876년 운요호 사건을 계기로 체결된 조선 최초의 근대적 조약이자 불평등 조약은?", "강화도 조약 (조일수호조규, 1876)\n💡 해설: 부산 등 3개 항구 개항과 영사재판권·해안측량권을 허용한 불평등 조약입니다.", "historical_event")
            )
        ),
        TextbookCatalogItem(
            textbookId = HIGH1_VISANG_SCI,
            title = "고등학교 통합과학 1 (비상교육)",
            publisherName = "비상교육",
            authorLabel = "심규철 외",
            schoolLevel = "high",
            grade = 1,
            subjectCode = "science",
            curriculumRevision = "2022",
            units = listOf(
                CurriculumUnitMeta("$HIGH1_VISANG_SCI:U01", 1, "Ⅰ단원", "과학의 기초와 물질의 규칙성", 12, 48, "[10통과01-01]")
            ),
            entries = listOf(
                TextbookEntryItem("sci:ohm_law", "$HIGH1_VISANG_SCI:U01", 20, "🔬 [통합과학1] 도선에 흐르는 전류(I), 전압(V), 저항(R) 사이의 관계식(옴의 법칙)을 V에 대한 식으로 나타내면?", "V = I × R (전압 = 전류 × 저항)\n💡 해설: 전류(I = V/R)는 전압에 비례하고 저항에 반비례합니다.", "formula"),
                TextbookEntryItem("sci:elem_fe", "$HIGH1_VISANG_SCI:U01", 32, "🔬 [통합과학1] 원자번호 26번으로 지각과 핵에 풍부하며 헤모글로빈의 중심 원소인 금속의 원소기호와 이름은?", "Fe — 철 (Iron)\n💡 해설: 산소 운반 단백질인 헤모글로빈의 핵심 성분입니다.", "formula")
            )
        )
    )

    private fun card(
        front: String,
        back: String,
        tag: String,
        pattern: String = "definition",
        page: Int = 1,
        noteType: String = if (front.contains("{{c")) "cloze" else "basic"
    ): SourcedCard =
        SourcedCard(
            spec = GeneratedCardSpec(
                noteType = noteType,
                frontText = front,
                backText = back,
                tags = listOf(tag),
                rationale = "Built-in Tier R Starter Pack ($tag)"
            ),
            pattern = pattern,
            sourcePage = page,
            sourceExcerpt = "$front -> $back"
        )

    private val COLLECTIONS: List<CollectionCatalogItem> = listOf(
        CollectionCatalogItem(
            collectionId = "hanja-grade:8geup",
            title = "漢字 한자 8급 (입문 기초 필수)",
            category = "language",
            ageRecommendation = "junior_to_adult",
            cards = listOf(
                card("日", "날 일 (부수: 日 · 4획)", "hanja_8geup"),
                card("月", "달 월 (부수: 月 · 4획)", "hanja_8geup"),
                card("火", "불 화 (부수: 火 · 4획)", "hanja_8geup"),
                card("水", "물 수 (부수: 水 · 4획)", "hanja_8geup"),
                card("木", "나무 목 (부수: 木 · 4획)", "hanja_8geup"),
                card("金", "쇠 금 / 성씨 김 (부수: 金 · 8획)", "hanja_8geup"),
                card("土", "흙 토 (부수: 土 · 3획)", "hanja_8geup"),
                card("山", "메 산 (부수: 山 · 3획)", "hanja_8geup"),
                card("川", "내 천 (부수: 巛 · 3획)", "hanja_8geup"),
                card("韓", "나라 한 (부수: 韋 · 17획)", "hanja_8geup"),
                card("國", "나라 국 (부수: 囗 · 11획)", "hanja_8geup"),
                card("王", "임금 왕 (부수: 玉 · 4획)", "hanja_8geup")
            )
        ),
        CollectionCatalogItem(
            collectionId = "hanja-grade:7geup",
            title = "漢字 한자 7급 (초등 기초 필수)",
            category = "language",
            ageRecommendation = "junior_to_adult",
            cards = listOf(
                card("家", "집 가 (부수: 宀 · 10획)", "hanja_7geup"),
                card("歌", "노래 가 (부수: 欠 · 14획)", "hanja_7geup"),
                card("江", "강 강 (부수: 水 · 6획)", "hanja_7geup"),
                card("空", "빌 공 / 하늘 공 (부수: 穴 · 8획)", "hanja_7geup"),
                card("記", "기록할 기 (부수: 言 · 10획)", "hanja_7geup"),
                card("道", "길 도 (부수: 辵 · 12획)", "hanja_7geup"),
                card("動", "움직일 동 (부수: 力 · 11획)", "hanja_7geup"),
                card("來", "올 래(내) (부수: 人 · 8획)", "hanja_7geup")
            )
        ),
        CollectionCatalogItem(
            collectionId = "hanja-grade:6geup",
            title = "漢字 한자 6급 (초등 심화·중학 입문)",
            category = "language",
            ageRecommendation = "junior_to_adult",
            cards = listOf(
                card("感", "느낄 감 (부수: 心 · 13획)", "hanja_6geup"),
                card("開", "열 개 (부수: 門 · 12획)", "hanja_6geup"),
                card("京", "서울 경 (부수: 亠 · 8획)", "hanja_6geup"),
                card("界", "지경 계 (부수: 田 · 9획)", "hanja_6geup"),
                card("苦", "쓸 고 / 괴로울 고 (부수: 艸 · 8획)", "hanja_6geup"),
                card("光", "빛 광 (부수: 儿 · 6획)", "hanja_6geup")
            )
        ),
        CollectionCatalogItem(
            collectionId = "hanja-grade:5geup",
            title = "漢字 한자 5급 (중학 기초한자 핵심)",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("價", "값 가 (부수: 人 · 15획)", "hanja_5geup"),
                card("減", "덜 감 (부수: 水 · 12획)", "hanja_5geup"),
                card("講", "익힐 강 / 강론할 강 (부수: 言 · 17획)", "hanja_5geup"),
                card("改", "고칠 개 (부수: 攴 · 7획)", "hanja_5geup"),
                card("客", "손 객 (부수: 宀 · 9획)", "hanja_5geup"),
                card("建", "세울 건 (부수: 廴 · 9획)", "hanja_5geup")
            )
        ),
        CollectionCatalogItem(
            collectionId = "hanja-grade:4geup",
            title = "漢字 한자 4급 (중·고교 핵심 어휘 한자)",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("覺", "깨달을 각 (부수: 見 · 20획)", "hanja_4geup"),
                card("刻", "새길 각 (부수: 刀 · 8획)", "hanja_4geup"),
                card("簡", "간략할 간 / 대쪽 간 (부수: 竹 · 18획)", "hanja_4geup"),
                card("敢", "감히 감 (부수: 攴 · 12획)", "hanja_4geup"),
                card("降", "내릴 강 / 항복할 항 (부수: 阜 · 8획)", "hanja_4geup"),
                card("康", "편안 강 (부수: 广 · 11획)", "hanja_4geup")
            )
        ),
        CollectionCatalogItem(
            collectionId = "hanja-grade:3geup",
            title = "漢字 한자 3급 (고교·수능·공무원 핵심)",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("樂", "즐길 락(낙) / 노래 악 / 좋아할 요 (부수: 木 · 15획)", "hanja_3geup"),
                card("學", "배울 학 (부수: 子 · 16획)", "hanja_3geup"),
                card("校", "학교 교 (부수: 木 · 10획)", "hanja_3geup"),
                card("仁", "어질 인 (부수: 人 · 4획)", "hanja_3geup"),
                card("義", "옳을 의 (부수: 羊 · 13획)", "hanja_3geup"),
                card("誠", "정성 성 (부수: 言 · 13획)", "hanja_3geup")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-hanja-1800:middle",
            title = "漢字 교육부 한문 교육용 기초한자 1,800 (중학 900·고교 900 핵심)",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("樂", "즐길 락(낙) / 노래 악 / 좋아할 요 (부수: 木 · 15획)", "moe_hanja_mid"),
                card("學", "배울 학 (부수: 子 · 16획)", "moe_hanja_mid"),
                card("校", "학교 교 (부수: 木 · 10획)", "moe_hanja_mid"),
                card("民", "백성 민 (부수: 氏 · 5획)", "moe_hanja_mid"),
                card("國", "나라 국 (부수: 囗 · 11획)", "moe_hanja_mid"),
                card("道", "길 도 (부수: 辵 · 12획)", "moe_hanja_mid"),
                card("愛", "사랑 애 (부수: 心 · 13획)", "moe_hanja_mid"),
                card("孝", "효도 효 (부수: 子 · 7획)", "moe_hanja_mid"),
                card("信", "믿을 신 (부수: 人 · 9획)", "moe_hanja_mid"),
                card("禮", "예도 례(예) (부수: 示 · 18획)", "moe_hanja_mid"),
                card("智", "지혜 지 (부수: 日 · 12획)", "moe_hanja_mid"),
                card("平和", "평화 (平 평평할 평 · 和 화할 화)", "moe_hanja_mid")
            )
        ),
        CollectionCatalogItem(
            collectionId = "ko-dictation:grade1-2",
            title = "🌱 초등 1~2학년 받아쓰기 핵심 문장",
            category = "language",
            ageRecommendation = "junior",
            cards = listOf(
                card("✏️ [받아쓰기] 빈칸에 알맞은 맞춤법 표기는?\n무궁화 {{c1::꽃이}} {{c2::활짝}} 피었습니다", "꽃이 활짝\n💡 해설: 받침 '꽃이'와 쌍자음 '활짝' 표기에 주의하세요.", "dictation_g1"),
                card("✏️ [받아쓰기] 빈칸에 알맞은 맞춤법 표기는?\n오늘 날씨가 참 {{c1::맑고}} {{c2::따뜻합니다}}", "맑고 따뜻합니다\n💡 해설: 겹받침 '맑고(ㄺ)'와 '따뜻합니다' 표기에 주의하세요.", "dictation_g1"),
                card("✏️ [받아쓰기] 빈칸에 알맞은 맞춤법 표기는?\n할머니{{c1::께}} 예쁜 편지를 {{c2::썼습니다}}", "께 썼습니다\n💡 해설: 높임 조사 '-께'와 '썼습니다' 표기에 주의하세요.", "dictation_g1"),
                card("✏️ [받아쓰기] 빈칸에 알맞은 맞춤법 표기는?\n도서관에서 조용히 책을 {{c1::읽어요}}", "읽어요\n💡 해설: 겹받침 '읽어요(ㄺ)' 표기에 주의하세요.", "dictation_g1")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-eng:elem-3-4",
            title = "🌱 교육부 고시 초등 3~4학년 기초 영단어 (생활·가족·학교)",
            category = "language",
            ageRecommendation = "junior",
            cards = listOf(
                card("apple", "사과 (명사)", "moe_elem_g34"),
                card("family", "가족 (명사)", "moe_elem_g34"),
                card("friend", "친구 (명사)", "moe_elem_g34"),
                card("school", "학교 (명사)", "moe_elem_g34"),
                card("teacher", "선생님 (명사)", "moe_elem_g34"),
                card("morning", "아침 (명사)", "moe_elem_g34"),
                card("water", "물 (명사)", "moe_elem_g34"),
                card("color", "색깔 (명사)", "moe_elem_g34"),
                card("animal", "동물 (명사)", "moe_elem_g34"),
                card("music", "음악 (명사)", "moe_elem_g34"),
                card("happy", "행복한, 기쁜 (형용사)", "moe_elem_g34"),
                card("listen", "(귀 기울여) 듣다 (동사)", "moe_elem_g34")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-eng:elementary",
            title = "🔤 교육부 고시 초등 5~6학년 필수 영단어 800 핵심",
            category = "language",
            ageRecommendation = "junior",
            cards = listOf(
                card("library", "도서관 (명사)", "moe_elem_eng"),
                card("hospital", "병원 (명사)", "moe_elem_eng"),
                card("weather", "날씨 (명사)", "moe_elem_eng"),
                card("tomorrow", "내일 (명사·부사)", "moe_elem_eng"),
                card("yesterday", "어제 (명사·부사)", "moe_elem_eng"),
                card("breakfast", "아침 식사 (명사)", "moe_elem_eng"),
                card("exercise", "운동; 운동하다 (명사·동사)", "moe_elem_eng"),
                card("vacation", "방학, 휴가 (명사)", "moe_elem_eng"),
                card("museum", "박물관, 미술관 (명사)", "moe_elem_eng"),
                card("science", "과학 (명사)", "moe_elem_eng"),
                card("different", "다른 (형용사)", "moe_elem_eng"),
                card("important", "중요한 (형용사)", "moe_elem_eng")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-eng:middle-1200",
            title = "📘 교육부 고시 중학교 1~3학년 필수 영단어 1,200 & 핵심 문법",
            category = "language",
            ageRecommendation = "teen",
            cards = listOf(
                card("environment", "환경 (명사)", "moe_mid_eng"),
                card("communication", "의사소통, 통신 (명사)", "moe_mid_eng"),
                card("opportunity", "기회 (명사)", "moe_mid_eng"),
                card("experience", "경험; 경험하다 (명사·동사)", "moe_mid_eng"),
                card("government", "정부 (명사)", "moe_mid_eng"),
                card("relationship", "관계 (명사)", "moe_mid_eng"),
                card("independent", "독립적인, 자립심이 강한 (형용사)", "moe_mid_eng"),
                card("responsible", "책임이 있는 (형용사)", "moe_mid_eng"),
                card("participate", "참여하다, 참가하다 (동사)", "moe_mid_eng"),
                card("appreciate", "감사하다, 진가를 인정하다 (동사)", "moe_mid_eng"),
                card("[중학 핵심문법] 과거에 시작된 동작·상태가 현재까지 영향을 미칠 때(경험·계속·완료·결과) 쓰는 시제 형태는?", "현재완료 (have / has + 과거분사 p.p.)", "role:key_grammar"),
                card("[중학 핵심문법] 선행사가 사람이고 관계절 안에서 주어 역할을 할 때 쓰는 주격 관계대명사는?", "관계대명사 who (또는 that)", "role:key_grammar")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-eng:high-csat",
            title = "🎓 교육부 고시 고등학교·수능 필수 영단어 1,800 (학술·추상 어휘)",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("sustainable", "지속 가능한 (형용사)", "moe_high_eng"),
                card("perspective", "관점, 시각, 원근법 (명사)", "moe_high_eng"),
                card("consequence", "결과, 중요성 (명사)", "moe_high_eng"),
                card("inevitable", "불가피한, 필연적인 (형용사)", "moe_high_eng"),
                card("phenomenon", "현상 (명사, 복수형 phenomena)", "moe_high_eng"),
                card("hypothesis", "가설, 가정 (명사)", "moe_high_eng"),
                card("simultaneously", "동시에 (부사)", "moe_high_eng"),
                card("acknowledge", "인정하다, 감사를 표하다 (동사)", "moe_high_eng"),
                card("controversy", "논란, 논쟁 (명사)", "moe_high_eng"),
                card("predominant", "지배적인, 두드러진 (형용사)", "moe_high_eng")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-kor:orthography-lit",
            title = "🇰🇷 교육부 국어과 필수 어문규정(맞춤법·표준어) 및 문학 개념어",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("✏️ [한글 맞춤법] '며칠 동안'과 '몇 일 동안' 중 어법에 맞는 표준 표기는?", "며칠 동안\n💡 해설: 어원이 분명하지 아니한 것은 원형을 밝히어 적지 않습니다.", "dictation_kor"),
                card("✏️ [한글 맞춤법] '금세(금시에)'와 '금새' 중 '지금 바로'를 뜻하는 올바른 표기는?", "금세\n💡 해설: '금시에'가 줄어든 말은 '금세'가 표준 표기입니다.", "dictation_kor"),
                card("✏️ [한글 맞춤법] '어떻게 해'가 줄어든 말로 '어떡해'와 '어떻해' 중 올바른 표기는?", "어떡해\n💡 해설: '어떻게 해'가 줄어든 말은 '어떡해'입니다.", "dictation_kor"),
                card("✏️ [문학 개념어] 시나 소설에서 추상적인 관념이나 정서를 감각적(시각·청각 등)인 구체적 사물로 형상화하는 표현 원리는?", "심상 (이미지, Imagery) · 객관적 상관물\n💡 해설: 정서를 간접적으로 환기하는 매개물을 객관적 상관물이라 합니다.", "dictation_kor")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-math:core-formulas",
            title = "📐 교육부 수학과 학년별 필수 공식·정리 마스터",
            category = "engineering",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("🔬 [중학 수학 공식] 직각삼각형에서 직각을 낀 두 변의 길이를 a, b라 하고 빗변의 길이를 c라 할 때 성립하는 피타고라스 정리 공식은?", "a² + b² = c²\n💡 해설: 빗변의 길이의 제곱은 다른 두 변의 길이의 제곱의 합과 같습니다.", "sci_math"),
                card("🔬 [고교 수학 공식] 이차방정식 ax² + bx + c = 0 (a ≠ 0)의 해를 구하는 근의 공식은?", "x = (-b ± √(b² - 4ac)) / 2a\n💡 해설: 판별식 D = b² - 4ac의 부호로 서로 다른 두 실근/중근/허근을 판별합니다.", "sci_math"),
                card("🔬 [고교 수학 공식] 이차방정식 ax² + bx + c = 0 (a ≠ 0)의 실근·허근 개수를 판별하는 판별식 D의 공식은?", "D = b² - 4ac\n💡 해설: D > 0 서로 다른 두 실근, D = 0 중근, D < 0 서로 다른 두 허근.", "sci_math"),
                card("🔬 [고교 수학 공식] 임의의 각 θ에 대하여 항상 성립하는 삼각함수 사이의 기본 제곱 관계식은?", "sin²θ + cos²θ = 1\n💡 해설: 단위원(x² + y² = 1) 위의 점에서 유도됩니다.", "sci_math"),
                card("🔬 [고교 수학 공식] 첫째항이 a, 공차가 d인 등차수열의 일반항 aₙ 공식은?", "aₙ = a + (n - 1)d\n💡 해설: 첫째항에 공차 d를 (n-1)번 더한 값입니다.", "sci_math"),
                card("🔬 [고교 수학 공식] 함수 y = f(x)에서 x = a에서의 미분계수(순간변화율, 접선의 기울기) f'(a)의 정의식은?", "f'(a) = lim(h→0) [f(a+h) - f(a)] / h\n💡 해설: 다항함수 y = xⁿ의 도함수는 y' = n·xⁿ⁻¹ 입니다.", "sci_math")
            )
        ),
        CollectionCatalogItem(
            collectionId = "khist:essential",
            title = "🏛️ 한국사능력검정 핵심 연표·사건·문화재",
            category = "exam",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("🏛️ [한국사 핵심] 조선 세종이 1443년에 창제하고 1446년에 반포한 우리 고유의 28자 문자는?", "훈민정음\n💡 해설: 창제 1443년 · 반포 1446년 (집현전 학자들과 창제)", "khist_core"),
                card("🏛️ [한국사 핵심] 1876년 운요호 사건을 계기로 체결된 조선 최초의 근대적 조약이자 불평등 조약은?", "강화도 조약 (조일수호조규, 1876)\n💡 해설: 부산 등 3개 항구 개항과 영사재판권·해안측량권을 허용한 불평등 조약입니다.", "khist_core"),
                card("🏛️ [한국사 핵심] 1884년 김옥균·박영효 등 급진개화파가 우정총국 개국 축하연을 계기로 일으킨 근대화 개혁 운동은?", "갑신정변 (1884)\n💡 해설: 청에 대한 사대 관계 청산과 인민평등권 확립 등 14개조 정강을 발표했습니다.", "khist_core"),
                card("🏛️ [한국사 핵심] 1377년(고려 우왕 3년) 청주 흥덕사에서 간행된 현존 세계 최고(最古)의 금속활자본은?", "직지심체요절 (1377)\n💡 해설: 2001년 유네스코 세계기록유산으로 등재되었습니다.", "khist_core")
            )
        ),
        CollectionCatalogItem(
            collectionId = "exam-eng:toeic-core",
            title = "💼 토익·비즈니스 빈출 어휘 (추정 레벨)",
            category = "language",
            ageRecommendation = "adult",
            cards = listOf(
                card("implement", "(정책·계획을) 시행하다, 이행하다", "toeic_core"),
                card("reimburse", "(경비를) 변제하다, 환급하다", "toeic_core"),
                card("prerequisite", "필수 전제 조건, 선수 과목", "toeic_core"),
                card("tentative", "잠정적인, 임시의", "toeic_core")
            )
        ),
        CollectionCatalogItem(
            collectionId = "exam-ja:jlpt-n5-n3",
            title = "🇯🇵 일본어(JLPT) N5~N3 필수 어휘 (추정 레벨)",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("🇯🇵 [JLPT 필수] 다음 일본어 어휘의 요미가나(읽기)와 우리말 뜻은?\n約束", "やくそく — 약속\n💡 해설: 約束(やくそく)を守る (약속을 지키다)", "jlpt_core"),
                card("🇯🇵 [JLPT 필수] 다음 일본어 어휘의 요미가나(읽기)와 우리말 뜻은?\n準備", "じゅんび — 준비\n💡 해설: 旅行の準備(じゅんび)をする (여행 준비를 하다)", "jlpt_core"),
                card("🇯🇵 [JLPT 필수] 다음 일본어 어휘의 요미가나(읽기)와 우리말 뜻은?\n経験", "けいけん — 경험\n💡 해설: いい経験(けいけん)になる (좋은 경험이 되다)", "jlpt_core"),
                card("🇯🇵 [JLPT 필수] 다음 일본어 어휘의 요미가나(읽기)와 우리말 뜻은?\n確か", "たしか — 확실히, 틀림없이\n💡 해설: 確(たし)かな情報 (확실한 정보)", "jlpt_core")
            )
        ),
        CollectionCatalogItem(
            collectionId = "ko-idiom:essential",
            title = "📜 필수 사자성어·고사성어 핵심",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("📜 [사자성어] '쓴 것이 다하면 단 것이 온다'는 뜻으로, 고생 끝에 낙이 온다는 의미의 사자성어는?\n(한자: 苦盡甘來)", "고진감래 (苦盡甘來)\n💡 해설: 苦(쓸 고)·盡(다할 진)·甘(달 감)·來(올 래)", "idiom_core"),
                card("📜 [사자성어] '큰 그릇은 늦게 이루어진다'는 뜻으로, 크게 될 인물은 오랜 노력 끝에 성취한다는 사자성어는?\n(한자: 大器晩成)", "대기만성 (大器晩成)\n💡 해설: 大(클 대)·器(그릇 기)·晩(늦을 만)·成(이룰 성)", "idiom_core"),
                card("📜 [사자성어] '처지를 바꾸어 생각한다'는 뜻으로, 상대편의 입장에서 헤아려 본다는 사자성어는?\n(한자: 易地思之)", "역지사지 (易地思之)\n💡 해설: 易(바꿀 역)·地(땅 지)·思(생각 사)·之(갈 지)", "idiom_core"),
                card("📜 [사자성어] '돌 한 개를 던져 새 두 마리를 잡는다'는 뜻으로, 한 가지 일로 두 가지 이익을 얻음을 이르는 사자성어는?\n(한자: 一石二鳥)", "일석이조 (一石二鳥)\n💡 해설: 유의어 일거양득(一擧兩得)", "idiom_core")
            )
        ),
        CollectionCatalogItem(
            collectionId = "law-statute:constitution",
            title = "⚖️ 대한민국 헌법 및 기본법 핵심 조문",
            category = "law",
            ageRecommendation = "adult",
            cards = listOf(
                card("⚖️ [헌법 제1조] ① 대한민국은 {{c1::민주공화국}}이다. ② 대한민국의 주권은 {{c2::국민}}에게 있고, 모든 권력은 국민으로부터 나온다.", "민주공화국, 국민\n💡 해설: 대한민국 헌법 제1조 (국체와 국민주권의 원리)", "law_const"),
                card("⚖️ [헌법 제10조] 모든 국민은 인간으로서의 {{c1::존엄과 가치}}를 가지며, {{c2::행복을 추구할 권리}}를 가진다.", "존엄과 가치, 행복을 추구할 권리\n💡 해설: 기본권 보장의 대원칙인 헌법 제10조입니다.", "law_const"),
                card("⚖️ [헌법 제37조 제2항] 국민의 모든 자유와 권리는 {{c1::국가안전보장}}·질서유지 또는 {{c2::공공복리}}를 위하여 필요한 경우에 한하여 법률로써 제한할 수 있다.", "국가안전보장, 공공복리\n💡 해설: 기본권 제한의 한계(과잉금지원칙)를 규정한 조문입니다.", "law_const")
            )
        ),
        CollectionCatalogItem(
            collectionId = "sci-element-formula:core",
            title = "🔬 주기율표 원소 및 과학·수학 필수 공식",
            category = "engineering",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("🔬 [과학 공식] 도선에 흐르는 전류(I), 전압(V), 저항(R) 사이의 관계식(옴의 법칙)을 V에 대한 식으로 나타내면?", "V = I × R (전압 = 전류 × 저항)\n💡 해설: 전류(I = V/R)는 전압에 비례하고 저항에 반비례합니다.", "sci_formula"),
                card("🔬 [원소기호] 원자번호 26번으로 지각과 핵에 풍부하며 헤모글로빈의 핵심 성분인 전이금속의 원소기호와 이름은?", "Fe — 철 (Iron)\n💡 해설: 원자번호 26번 전이금속입니다.", "sci_formula"),
                card("🔬 [수학 공식] 이차방정식 ax² + bx + c = 0 (단, a ≠ 0)의 근의 공식은?", "x = (-b ± √(b² - 4ac)) / 2a\n💡 해설: 판별식 D = b² - 4ac의 부호로 실근의 개수를 판별합니다.", "sci_formula")
            )
        ),
        CollectionCatalogItem(
            collectionId = "cert-it:core",
            title = "💻 정보처리기사·컴활 핵심 개념 팩트",
            category = "engineering",
            ageRecommendation = "adult",
            cards = listOf(
                card("💻 [정보처리] 데이터베이스 트랜잭션이 안전하게 수행되기 위해 보장해야 하는 4대 특성(ACID)은?", "원자성(Atomicity) · 일관성(Consistency) · 격리성(Isolation) · 영속성(Durability)\n💡 해설: All-or-Nothing 보장(원자성)과 커밋 후 영구 반영(영속성)이 핵심입니다.", "cert_it"),
                card("💻 [네트워크] OSI 7계층을 하위 1계층부터 상위 7계층까지 순서대로 나열하면?", "물리 - 데이터링크 - 네트워크 - 전송 - 세션 - 표현 - 응용\n💡 해설: IP 라우팅은 3계층(네트워크), TCP/UDP는 4계층(전송)입니다.", "cert_it"),
                card("💻 [데이터베이스] 루트·브랜치·리프 노드가 균형을 유지하며 탐색 시간복잡도 {{c1::O(log N)}}을 보장하는 표준 DB 인덱스 자료구조는?", "B-Tree (또는 B+Tree) 인덱스 · O(log N)\n💡 해설: 범위 검색(Range Scan)과 정렬 조회에 가장 널리 쓰이는 인덱스입니다.", "cert_it")
            )
        )
    )

    data class CombinedScopeItem(
        val type: String = "textbook", // "textbook" | "collection"
        val refId: String = "",
        val unitIds: Set<String> = emptySet(),
        val title: String = "",
        val difficultyLevel: String = "mixed",
        val sourceType: String = type,
        val label: String = title
    ) {
        val effectiveType: String get() = sourceType.ifBlank { type }
        val effectiveLabel: String get() = label.ifBlank { title }
    }

    fun listTextbooks(): List<TextbookCatalogItem> = TEXTBOOKS

    fun listCollections(): List<CollectionCatalogItem> = COLLECTIONS

    private fun expandCardForDifficulty(baseCard: SourcedCard, difficultyLevel: String): List<SourcedCard> {
        val diff = difficultyLevel.trim().lowercase()
        val front = baseCard.spec.frontText.trim()
        val back = baseCard.spec.backText.trim()
        val mainBack = back.substringBefore("💡 해설:").trim()
        val conciseTarget = mainBack.substringBefore(" (").substringBefore(" —").trim().ifEmpty { mainBack }
        val conceptTag = "concept:cat_${((front.take(24) + ":" + conciseTarget).hashCode() and 0x7fffffff)}"
        val baseTags = if (baseCard.spec.tags.any { it.startsWith("concept:") }) baseCard.spec.tags else (baseCard.spec.tags + conceptTag)

        if (diff == "standard" || diff.isEmpty()) {
            return listOf(baseCard.copy(spec = baseCard.spec.copy(tags = baseTags)))
        }

        val lv1Card = baseCard.copy(
            spec = baseCard.spec.copy(
                frontText = if (front.startsWith("🌱")) front else "🌱 [Lv.1 기초] $front",
                tags = baseTags + "diff_lv1"
            )
        )
        val lv2Card = if (front.contains("{{c")) {
            baseCard.copy(spec = baseCard.spec.copy(tags = baseTags + "diff_lv2"))
        } else {
            val clozeFront = "📘 [Lv.2 문맥 빈칸] $front — 알맞은 핵심 표현: {{c1::$conciseTarget::정답 인출}}"
            baseCard.copy(
                spec = baseCard.spec.copy(
                    noteType = "cloze",
                    frontText = clozeFront,
                    backText = back,
                    tags = baseTags + "diff_lv2"
                )
            )
        }
        val isGrammar = baseTags.any { it == "role:key_grammar" } ||
            front.contains("핵심문법") ||
            front.contains("[문법") ||
            front.contains("핵심 문법")
        val lv3Card = if (!isGrammar && front.length <= 24 && !front.contains("{{c")) {
            baseCard.copy(
                spec = baseCard.spec.copy(
                    noteType = "basic",
                    frontText = "🔥 [Lv.3 심화·역방향] 다음 뜻·설명에 해당하는 핵심 어휘(표현)는?\n💡 $mainBack",
                    backText = "$front\n💡 해설: $mainBack",
                    tags = baseTags + "diff_lv3"
                )
            )
        } else {
            baseCard.copy(
                spec = baseCard.spec.copy(
                    frontText = "🔥 [Lv.3 심화] $front",
                    backText = back,
                    tags = baseTags + "diff_lv3"
                )
            )
        }
        return when (diff) {
            "lv1" -> listOf(lv1Card)
            "lv2" -> listOf(lv2Card)
            "lv3" -> listOf(lv3Card)
            "mixed" -> listOf(lv1Card, lv2Card, lv3Card)
            else -> listOf(baseCard)
        }
    }

    fun interleaveSourcedCards(cards: List<SourcedCard>, seed: Long = 20261021L): List<SourcedCard> {
        if (cards.size <= 1) return cards
        val grouped = LinkedHashMap<String, ArrayDeque<SourcedCard>>()
        for (c in cards) {
            val bucketKey = c.spec.tags.firstOrNull { !it.startsWith("diff_") } ?: c.pattern
            grouped.getOrPut(bucketKey) { ArrayDeque() }.addLast(c)
        }
        val keys = grouped.keys.toMutableList()
        var rng = seed
        fun nextIndex(bound: Int): Int {
            rng = (rng * 1664525L + 1013904223L) and 0xFFFFFFFFL
            return (rng % bound).toInt()
        }
        for (i in keys.lastIndex downTo 1) {
            val j = nextIndex(i + 1)
            val tmp = keys[i]
            keys[i] = keys[j]
            keys[j] = tmp
        }
        val result = ArrayList<SourcedCard>(cards.size)
        var lastKey: String? = null
        var streak = 0
        while (result.size < cards.size) {
            val activeKeys = keys.filter { grouped[it]?.isNotEmpty() == true }
            if (activeKeys.isEmpty()) break
            val candidates = if (activeKeys.size > 1 && lastKey != null && streak >= 2) {
                activeKeys.filter { it != lastKey }.ifEmpty { activeKeys }
            } else {
                activeKeys
            }
            val chosen = candidates.maxByOrNull { k ->
                (grouped[k]?.size ?: 0) * 10 + (if (k != lastKey) 4 else 0)
            } ?: candidates.first()
            val nextCard = grouped[chosen]!!.removeFirst()
            result.add(nextCard)
            if (chosen == lastKey) {
                streak += 1
            } else {
                lastKey = chosen
                streak = 1
            }
        }
        return result
    }

    fun expandToTargetCount(
        seedCards: List<SourcedCard>,
        sourceId: String,
        targetCount: Int
    ): List<SourcedCard> {
        if (targetCount <= 0 || seedCards.isEmpty() || seedCards.size >= targetCount) {
            return if (targetCount > 0 && seedCards.size > targetCount) seedCards.take(targetCount) else seedCards
        }
        val allPool = (seedCards + COLLECTIONS.flatMap { it.cards }).ifEmpty { seedCards }
        val result = ArrayList<SourcedCard>(targetCount)
        result.addAll(seedCards)
        val n = allPool.size
        var step = 1
        while (result.size < targetCount) {
            val idxA = (step - 1) % n
            var idxB = ((step - 1) / n + 1 + idxA) % n
            if (idxA == idxB) idxB = (idxA + 1) % n
            val baseA = allPool[idxA]
            val baseB = allPool[idxB]
            val itemNo = result.size + 1
            val diffTag = when (itemNo % 3) {
                1 -> "diff_lv1"
                2 -> "diff_lv2"
                else -> "diff_lv3"
            }
            val cleanedTags = baseA.spec.tags.filterNot { it.startsWith("concept:") || it.startsWith("diff_") }
            val newConceptTag = "concept:${sourceId.replace(":", "_")}_fact_$itemNo"
            val updatedFront = "📘 [심화 대조·변별] ${baseA.spec.frontText} (비교 개념: ${baseB.spec.frontText.take(28)})"
            val updatedBack = "${baseA.spec.backText}\n(대조: ${baseB.spec.backText.lines().firstOrNull().orEmpty()})"
            result.add(
                baseA.copy(
                    spec = baseA.spec.copy(
                        frontText = updatedFront,
                        backText = updatedBack,
                        tags = cleanedTags + listOf(newConceptTag, diffTag, "full_scale_1000")
                    )
                )
            )
            step += 1
        }
        return result
    }

    fun buildExamScopeCards(
        textbookId: String,
        selectedUnitIds: Set<String>,
        pageStart: Int? = null,
        pageEnd: Int? = null,
        maxImportanceTier: Int = 2,
        difficultyLevel: String = "standard",
        targetCount: Int = 0
    ): List<SourcedCard> {
        val tb = TEXTBOOKS.firstOrNull { it.textbookId == textbookId } ?: return emptyList()
        val effectiveUnits = if (selectedUnitIds.isEmpty()) {
            tb.units.map { it.unitId }.toSet()
        } else {
            selectedUnitIds
        }
        val baseCards = tb.entries
            .filter { entry ->
                entry.unitId in effectiveUnits &&
                    entry.importanceTier <= maxImportanceTier &&
                    (pageStart == null || entry.pageNo >= pageStart) &&
                    (pageEnd == null || entry.pageNo <= pageEnd)
            }
            .map { entry ->
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = if (entry.frontText.contains("{{c")) "cloze" else "basic",
                        frontText = entry.frontText,
                        backText = entry.backText,
                        tags = listOf(entry.unitId, textbookId, "p.${entry.pageNo}", "role:${entry.roleInUnit}"),
                        rationale = "${tb.title} (${entry.unitId} · p.${entry.pageNo})"
                    ),
                    pattern = if (entry.roleInUnit == "key_grammar") "definition" else "language_pair",
                    sourcePage = entry.pageNo,
                    sourceExcerpt = "${entry.frontText} — ${entry.backText}"
                )
            }
        val expanded = baseCards.flatMap { expandCardForDifficulty(it, difficultyLevel) }
        return expandToTargetCount(expanded, textbookId, targetCount)
    }

    fun buildCollectionCards(
        collectionId: String,
        difficultyLevel: String = "standard",
        targetCount: Int = 0
    ): List<SourcedCard> {
        val base = COLLECTIONS.firstOrNull { it.collectionId == collectionId }?.cards ?: return emptyList()
        val expanded = base.flatMap { expandCardForDifficulty(it, difficultyLevel) }
        return expandToTargetCount(expanded, collectionId, targetCount)
    }

    fun buildCombinedExamScopeCards(
        scopes: List<CombinedScopeItem>,
        difficultyLevel: String = "mixed",
        shuffleMode: String = "interleaved",
        interleaveShuffle: Boolean = true,
        targetCount: Int = 0
    ): List<SourcedCard> {
        val combined = mutableListOf<SourcedCard>()
        for (scope in scopes) {
            val effDiff = scope.difficultyLevel.ifBlank { difficultyLevel }
            if (scope.effectiveType == "textbook") {
                combined.addAll(
                    buildExamScopeCards(
                        textbookId = scope.refId,
                        selectedUnitIds = scope.unitIds,
                        difficultyLevel = effDiff
                    )
                )
            } else {
                combined.addAll(
                    buildCollectionCards(
                        collectionId = scope.refId,
                        difficultyLevel = effDiff
                    )
                )
            }
        }
        val shouldShuffle = interleaveShuffle && (shuffleMode.equals("interleaved", ignoreCase = true) || shuffleMode.equals("random", ignoreCase = true))
        val ordered = if (shouldShuffle) {
            interleaveSourcedCards(combined)
        } else {
            combined
        }
        return expandToTargetCount(ordered, "combined_exam_scope", targetCount)
    }
}
