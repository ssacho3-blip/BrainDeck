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
                TextbookEntryItem("khist:hunmin_1443", "$MID2_MIRAEEN_HIST:U01", 18, "훈민정음 창제 (1443, 반포 1446)", "조선 세종 대 훈민정음 28자 창제·반포", "historical_event"),
                TextbookEntryItem("khist:ganghwa_1876", "$MID2_MIRAEEN_HIST:U01", 26, "강화도 조약 (1876)", "조선 최초의 근대적 조약이자 불평등 조약", "historical_event")
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
                TextbookEntryItem("sci:ohm_law", "$HIGH1_VISANG_SCI:U01", 20, "옴의 법칙: V = I × R", "전압(V) = 전류(I) × 저항(R)", "formula"),
                TextbookEntryItem("sci:elem_fe", "$HIGH1_VISANG_SCI:U01", 32, "원소기호 Fe (원자번호 26)", "철 (Iron)", "formula")
            )
        )
    )

    private fun card(front: String, back: String, tag: String, pattern: String = "definition", page: Int = 1): SourcedCard =
        SourcedCard(
            spec = GeneratedCardSpec(
                noteType = "basic",
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
            title = "漢字 교육부 중학 기초한자 900 핵심",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("樂", "즐길 락(낙) / 노래 악 / 좋아할 요 (부수: 木 · 15획)", "moe_hanja_mid"),
                card("學", "배울 학 (부수: 子 · 16획)", "moe_hanja_mid"),
                card("校", "학교 교 (부수: 木 · 10획)", "moe_hanja_mid"),
                card("民", "백성 민 (부수: 氏 · 5획)", "moe_hanja_mid"),
                card("國", "나라 국 (부수: 囗 · 11획)", "moe_hanja_mid"),
                card("道", "길 도 (부수: 辵 · 12획)", "moe_hanja_mid")
            )
        ),
        CollectionCatalogItem(
            collectionId = "ko-dictation:grade1-2",
            title = "🌱 초등 1~2학년 받아쓰기 핵심 문장",
            category = "language",
            ageRecommendation = "junior",
            cards = listOf(
                card("무궁화 꽃이 활짝 피었습니다", "받침 '꽃이'와 쌍자음 '활짝' 주의", "dictation_g1"),
                card("오늘 날씨가 참 맑고 따뜻합니다", "겹받침 '맑고(ㄺ)'와 '따뜻합니다' 주의", "dictation_g1"),
                card("할머니께 예쁜 편지를 썼습니다", "높임 조사 '-께'와 '썼습니다' 주의", "dictation_g1"),
                card("도서관에서 조용히 책을 읽어요", "겹받침 '읽어요(ㄺ)' 주의", "dictation_g1")
            )
        ),
        CollectionCatalogItem(
            collectionId = "moe-eng:elementary",
            title = "🔤 교육부 고시 초등 필수 영단어",
            category = "language",
            ageRecommendation = "junior",
            cards = listOf(
                card("library", "도서관", "moe_elem_eng"),
                card("hospital", "병원", "moe_elem_eng"),
                card("weather", "날씨", "moe_elem_eng"),
                card("tomorrow", "내일", "moe_elem_eng")
            )
        ),
        CollectionCatalogItem(
            collectionId = "khist:essential",
            title = "🏛️ 한국사능력검정 핵심 연표·사건·문화재",
            category = "exam",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("훈민정음 창제 (1443, 반포 1446)", "조선 세종 대 백성을 가르치는 바른 소리 28자를 창제·반포한 사건", "khist_core"),
                card("강화도 조약 (조일수호조규, 1876)", "조선이 외국과 맺은 최초의 근대적 조약이자 불평등 조약 (영사재판권·해안측량권 허용)", "khist_core"),
                card("갑신정변 (1884)", "김옥균·박영효 등 급진개화파가 우정총국 개국 축하연을 계기로 일으킨 근대화 개혁 운동", "khist_core"),
                card("직지심체요절 (1377, 청주 흥덕사)", "고려 우왕 3년 청주 흥덕사에서 간행된 현존 세계 최고(最古)의 금속활자본", "khist_core")
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
                card("約束 (やくそく)", "약속 (야쿠소쿠)", "jlpt_core"),
                card("準備 (じゅんび)", "준비 (준비)", "jlpt_core"),
                card("経験 (けいけん)", "경험 (케이켄)", "jlpt_core"),
                card("確か (たしか)", "확실히, 틀림없이 (타시카)", "jlpt_core")
            )
        ),
        CollectionCatalogItem(
            collectionId = "ko-idiom:essential",
            title = "📜 필수 사자성어·고사성어 핵심",
            category = "language",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("苦盡甘來 (고진감래)", "쓴 것이 다하면 단 것이 온다 — 고생 끝에 낙이 온다는 뜻", "idiom_core"),
                card("大器晩成 (대기만성)", "큰 그릇은 늦게 이루어진다 — 크게 될 인물은 오랜 노력 끝에 대기(大器)를 이룸", "idiom_core"),
                card("易地思之 (역지사지)", "처지를 바꾸어 생각함 — 상대편의 입장에서 헤아려 생각한다는 뜻", "idiom_core"),
                card("一石二鳥 (일석이조)", "돌 한 개를 던져 새 두 마리를 잡는다 — 한 가지 일로 두 가지 이익을 얻음", "idiom_core")
            )
        ),
        CollectionCatalogItem(
            collectionId = "law-statute:constitution",
            title = "⚖️ 대한민국 헌법 및 기본법 핵심 조문",
            category = "law",
            ageRecommendation = "adult",
            cards = listOf(
                card("대한민국 헌법 제1조", "① 대한민국은 민주공화국이다. ② 대한민국의 주권은 국민에게 있고, 모든 권력은 국민으로부터 나온다.", "law_const"),
                card("대한민국 헌법 제10조", "모든 국민은 인간으로서의 존엄과 가치를 가지며, 행복을 추구할 권리를 가진다.", "law_const"),
                card("대한민국 헌법 제37조 제2항 (과잉금지원칙)", "국민의 모든 자유와 권리는 국가안전보장·질서유지 또는 공공복리를 위하여 필요한 경우에 한하여 법률로써 제한할 수 있다.", "law_const")
            )
        ),
        CollectionCatalogItem(
            collectionId = "sci-element-formula:core",
            title = "🔬 주기율표 원소 및 과학·수학 필수 공식",
            category = "engineering",
            ageRecommendation = "teen_to_adult",
            cards = listOf(
                card("옴의 법칙 (Ohm's Law)", "V = I × R (전압 = 전류 × 저항)", "sci_formula"),
                card("원소기호 Fe (원자번호 26)", "철 (Iron) — 헤모글로빈의 핵심 성분이자 대표 전이금속", "sci_formula"),
                card("이차방정식 근의 공식 (ax² + bx + c = 0)", "x = (-b ± √(b² - 4ac)) / 2a (단, a ≠ 0)", "sci_formula")
            )
        ),
        CollectionCatalogItem(
            collectionId = "cert-it:core",
            title = "💻 정보처리기사·컴활 핵심 개념 팩트",
            category = "engineering",
            ageRecommendation = "adult",
            cards = listOf(
                card("데이터베이스 트랜잭션 4대 특성 (ACID)", "원자성(Atomicity) · 일관성(Consistency) · 격리성(Isolation) · 영속성(Durability)", "cert_it"),
                card("OSI 7계층 순서 (하위 1계층 -> 상위 7계층)", "물리 - 데이터링크 - 네트워크 - 전송 - 세션 - 표현 - 응용", "cert_it"),
                card("B-Tree 인덱스의 핵심 특징", "루트·브랜치·리프 노드가 균형을 유지하며 탐색 시간복잡도를 O(log N)으로 보장하는 DB 인덱스", "cert_it")
            )
        )
    )

    fun listTextbooks(): List<TextbookCatalogItem> = TEXTBOOKS

    fun listCollections(): List<CollectionCatalogItem> = COLLECTIONS

    fun buildExamScopeCards(
        textbookId: String,
        selectedUnitIds: Set<String>,
        pageStart: Int? = null,
        pageEnd: Int? = null,
        maxImportanceTier: Int = 2
    ): List<SourcedCard> {
        val tb = TEXTBOOKS.firstOrNull { it.textbookId == textbookId } ?: return emptyList()
        val effectiveUnits = if (selectedUnitIds.isEmpty()) {
            tb.units.map { it.unitId }.toSet()
        } else {
            selectedUnitIds
        }
        return tb.entries
            .filter { entry ->
                entry.unitId in effectiveUnits &&
                    entry.importanceTier <= maxImportanceTier &&
                    (pageStart == null || entry.pageNo >= pageStart) &&
                    (pageEnd == null || entry.pageNo <= pageEnd)
            }
            .map { entry ->
                SourcedCard(
                    spec = GeneratedCardSpec(
                        noteType = "basic",
                        frontText = entry.frontText,
                        backText = entry.backText,
                        tags = listOf(textbookId, entry.unitId, "p.${entry.pageNo}"),
                        rationale = "${tb.title} (${entry.unitId} · p.${entry.pageNo})"
                    ),
                    pattern = if (entry.roleInUnit == "key_grammar") "definition" else "language_pair",
                    sourcePage = entry.pageNo,
                    sourceExcerpt = "${entry.frontText} — ${entry.backText}"
                )
            }
    }

    fun buildCollectionCards(collectionId: String): List<SourcedCard> {
        return COLLECTIONS.firstOrNull { it.collectionId == collectionId }?.cards ?: emptyList()
    }
}
