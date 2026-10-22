package com.ankistudio.domain.catalog

/**
 * Pure JVM Kotlin BrainDeck In-App BrainPack Store Catalog & Entitlement Engine.
 * Strictly zero `android.*` or `androidx.*` imports.
 */
object BrainPackStoreCatalog {

    data class SampleCardPreview(
        val front: String,
        val back: String,
        val tag: String
    )

    data class BrainPackProduct(
        val packId: String,
        val title: String,
        val subtitle: String,
        val category: String,      // "starter_free" | "k12_textbook" | "hanja_history" | "language_exam" | "pro_cert"
        val ageTier: String,       // "junior" | "teen" | "adult" | "all"
        val priceKrw: Int,
        val isFreeStarter: Boolean,
        val linkKind: String,      // "textbook" | "collection"
        val primaryRefId: String,
        val coveredRefIds: List<String>,
        val estimatedCardCount: Int,
        val badgeLabel: String,
        val features: List<String>,
        val sampleCards: List<SampleCardPreview>
    ) {
        val priceLabel: String
            get() = if (priceKrw == 0) "무료 기본 탑재" else "₩%,d".format(priceKrw)
    }

    data class EntitlementCheckResult(
        val allowed: Boolean,
        val targetRefId: String,
        val requiredPackId: String?,
        val requiredPackTitle: String?,
        val priceKrw: Int,
        val reason: String
    )

    val products: List<BrainPackProduct> = listOf(
        BrainPackProduct(
            packId = "pack.free.starter_k12",
            title = "🎁 [무료 기본] 초등 받아쓰기·기초 영단어 & 한자 8급 입문 브레인팩",
            subtitle = "앱 설치 즉시 기본 탑재되는 무료 스타터 데이터팩 (본인 사진/PDF 업로드 무제한 무료 포함)",
            category = "starter_free",
            ageTier = "all",
            priceKrw = 0,
            isFreeStarter = true,
            linkKind = "collection",
            primaryRefId = "hanja-grade:8geup",
            coveredRefIds = listOf(
                "hanja-grade:8geup",
                "ko-dictation:grade1-2",
                "moe-eng:elementary"
            ),
            estimatedCardCount = 20,
            badgeLabel = "무료 기본 탑재",
            features = listOf(
                "어문회 8급 입문 기초 한자 12자 + 부수·획수 완비",
                "초등 1~2학년 받아쓰기 핵심 문장 & 교육부 초등 영단어 맛보기",
                "카메라 촬영·교재 스캔·PDF 자체 카드 생성 무제한 무료"
            ),
            sampleCards = listOf(
                SampleCardPreview("韓", "나라 한 (부수: 韋 · 17획)", "hanja_8geup"),
                SampleCardPreview("무궁화 꽃이 활짝 피었습니다", "초등 받아쓰기 (받침·쌍자음 연습)", "dictation")
            )
        ),
        BrainPackProduct(
            packId = "pack.mid1.eng.donga_yoon.full",
            title = "📦 [중1 내신] 동아(윤정미) 영어 Lesson 1~8 전 단원 마스터 브레인팩",
            subtitle = "2022 개정 교육과정 · 단원별·쪽수별 시험범위 슬라이싱 + 핵심 영단어·문법 함정선지 완비",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "textbook",
            primaryRefId = "kr.mid1.eng.donga_yoon.2022",
            coveredRefIds = listOf("kr.mid1.eng.donga_yoon.2022"),
            estimatedCardCount = 34,
            badgeLabel = "중1 내신 베스트",
            features = listOf(
                "Lesson 1 ~ Lesson 8 전 단원 필수 어휘·숙어·핵심 문법 완벽 매핑",
                "학교 시험범위(단원 체크 + 시작~끝 쪽수) 맞춤형 즉시 덱 생성",
                "내가 찍은 학교 영어 프린트물·본문 스캔과 자동 통합"
            ),
            sampleCards = listOf(
                SampleCardPreview("introduce (p.12)", "소개하다 (동사)", "Lesson 1"),
                SampleCardPreview(
                    "[Lesson 5 핵심문법] want, hope, plan, decide가 목적어로 취하는 형태는?",
                    "to부정사 (to + 동사원형, 명사적 용법)",
                    "Lesson 5"
                )
            )
        ),
        BrainPackProduct(
            packId = "pack.mid2.eng.donga_yoon.full",
            title = "📦 [중2 내신] 동아(윤정미) 영어 전 단원·쪽수 마스터 브레인팩",
            subtitle = "중학교 2학년 내신 만점 대비 · 단원/쪽수 슬라이싱 & 4지선다 유의어 함정 방어",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "textbook",
            primaryRefId = "kr.mid2.eng.donga_yoon.2022",
            coveredRefIds = listOf("kr.mid2.eng.donga_yoon.2022"),
            estimatedCardCount = 24,
            badgeLabel = "중2 내신 필수",
            features = listOf(
                "Lesson 1(Express Yourself) ~ Lesson 3(Green Earth) 핵심 어휘·문법 수록",
                "비연속 단원 및 쪽수 구간(p.Start~End) 시험범위 필터링",
                "4지선다 객관식 ➔ 단어블록 조립 ➔ 스펠링 인출 3단계 자동 승격"
            ),
            sampleCards = listOf(
                SampleCardPreview("confident (p.16)", "자신감 있는 (형용사)", "Lesson 1"),
                SampleCardPreview("recipe (p.31)", "조리법, 레시피 (명사)", "Lesson 2")
            )
        ),
        BrainPackProduct(
            packId = "pack.mid2.hist.miraeen.full",
            title = "📦 [중2 내신] 미래엔 역사① 연표·사료·문화재 브레인팩",
            subtitle = "중학교 역사 내신 출판사 단원 매핑 · 동시대 사건 함정 보기 자동 구성",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "textbook",
            primaryRefId = "kr.mid2.hist.miraeen.2022",
            coveredRefIds = listOf("kr.mid2.hist.miraeen.2022"),
            estimatedCardCount = 20,
            badgeLabel = "역사 내신 특화",
            features = listOf(
                "미래엔 중학교 역사① 단원·쪽수별 사건·연표·조약·문화재 정리",
                "가짜 합성 연도 배제 — 실제 역사 사건 연도 기반 4지선다 구성",
                "시험 직전 틀린 연표만 모아 푸는 오답 Cram 세션 연동"
            ),
            sampleCards = listOf(
                SampleCardPreview("훈민정음 창제 (1443, 반포 1446)", "조선 세종 대 백성을 가르치는 바른 소리 28자 창제", "Ⅰ단원"),
                SampleCardPreview("강화도 조약 (1876)", "조선 최초의 근대적 조약이자 불평등 조약", "Ⅰ단원")
            )
        ),
        BrainPackProduct(
            packId = "pack.high1.sci.visang.full",
            title = "📦 [고1 내신] 비상 통합과학1 공식·핵심개념 브레인팩",
            subtitle = "고등학교 1학년 통합과학 물리·화학·생명·지구과학 필수 공식 및 원소 완벽 대비",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "textbook",
            primaryRefId = "kr.high1.sci.visang.2022",
            coveredRefIds = listOf("kr.high1.sci.visang.2022", "sci-element-formula:core"),
            estimatedCardCount = 25,
            badgeLabel = "고1 내신 1등급",
            features = listOf(
                "비상교육 고1 통합과학1 단원·쪽수별 핵심 공식 및 주기율표 원소 매핑",
                "수치·단위(V, A, Ω, 원자번호) 정확도 검증 능동 인출 채점",
                "물리·화학·수학 핵심 공식 컬렉션 동시 잠금해제"
            ),
            sampleCards = listOf(
                SampleCardPreview("옴의 법칙: V = I × R", "전압(V)은 전류(I)와 저항(R)의 곱에 비례한다", "통합과학1"),
                SampleCardPreview("원소기호 Fe (원자번호 26)", "철 (Iron) — 전이금속", "주기율표")
            )
        ),
        BrainPackProduct(
            packId = "pack.exam.hanja_master",
            title = "📦 [급수한자] 어문회 7급~3급 필수 한자 & 사자성어 올인원 브레인팩",
            subtitle = "동음이의어·유사한자 함정선지 완벽 방어 + 두음법칙/다음자(樂 락·악·요) 정밀 채점",
            category = "hanja_history",
            ageTier = "all",
            priceKrw = 1500,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "hanja-grade:7geup",
            coveredRefIds = listOf(
                "hanja-grade:7geup",
                "hanja-grade:6geup",
                "hanja-grade:5geup",
                "hanja-grade:4geup",
                "hanja-grade:3geup",
                "ko-idiom:essential"
            ),
            estimatedCardCount = 50,
            badgeLabel = "급수시험 올인원",
            features = listOf(
                "한자 7급·6급·5급·4급·3급 급수별 필수 한자 및 사자성어 전체 잠금해제",
                "독음 질문 시 동음이의어 복수 정답 사고를 원천 차단하는 Anti-Leak 4지선다",
                "훈음·부수·획수·사자성어 속뜻 다면 학습 지원"
            ),
            sampleCards = listOf(
                SampleCardPreview("樂 (3급 대표 다음자)", "즐길 락(낙) / 노래 악 / 좋아할 요 (부수: 木 · 15획)", "hanja_3geup"),
                SampleCardPreview("苦盡甘來 (고진감래)", "쓴 것이 다하면 단 것이 온다 — 고생 끝에 낙이 옴", "ko_idiom")
            )
        ),
        BrainPackProduct(
            packId = "pack.exam.khist_master",
            title = "📦 [한국사] 한국사능력검정 심화(1~3급) 핵심 연표·사료·문화재 브레인팩",
            subtitle = "고려·조선·근현대사 핵심 사건·조약·유네스코 문화재 완벽 총정리",
            category = "hanja_history",
            ageTier = "all",
            priceKrw = 1500,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "khist:essential",
            coveredRefIds = listOf("khist:essential"),
            estimatedCardCount = 30,
            badgeLabel = "한능검 단기합격",
            features = listOf(
                "시대별·왕대별 핵심 사건·조약·문화재 연표 양방향 Cloze",
                "동일 시대·인접 연도 함정 보기 자동 조합으로 실전 변별력 극대화",
                "FSRS-5 시험 D-Day 집중 복습 스케줄링 지원"
            ),
            sampleCards = listOf(
                SampleCardPreview("갑신정변 (1884)", "김옥균·박영효 등 급진개화파가 일으킨 근대화 개혁 운동", "khist"),
                SampleCardPreview("직지심체요절 (1377, 청주 흥덕사)", "현존 세계 최고(最古)의 금속활자본", "khist")
            )
        ),
        BrainPackProduct(
            packId = "pack.exam.lang_toeic_jlpt",
            title = "📦 [어학] 토익(TOEIC) 고득점 빈출 & JLPT N5~N3 필수 어휘 브레인팩",
            subtitle = "비즈니스 영어 핵심 어휘 + 일본어 한자·히라가나 발음/원어민 TTS 스피킹 드릴",
            category = "language_exam",
            ageTier = "adult",
            priceKrw = 1900,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "exam-eng:toeic-core",
            coveredRefIds = listOf("exam-eng:toeic-core", "exam-ja:jlpt-n5-n3"),
            estimatedCardCount = 40,
            badgeLabel = "어학 베스트셀러",
            features = listOf(
                "토익 빈출 어휘(CEFR B2~C1) 및 JLPT N5~N3 핵심 어휘 동시 수록",
                "애플/안드로이드 내장 원어민 TTS 발음 듣기 및 스펠링/발음 인출 채점",
                "품사별·난이도별 유의어 4지선다 퀴즈 자동 생성"
            ),
            sampleCards = listOf(
                SampleCardPreview("reimburse", "(경비를) 변제하다, 환급하다 (동사 · C1)", "TOEIC"),
                SampleCardPreview("約束 (やくそく)", "약속 (야쿠소쿠)", "JLPT")
            )
        ),
        BrainPackProduct(
            packId = "pack.pro.law_it_cert",
            title = "📦 [성인/전문] 헌법 핵심 조문 & 정보처리기사·컴활 마스터 브레인팩",
            subtitle = "공무원·법학 시험 필수 헌법 조문 + IT 자격증(정처기·컴활) 핵심 팩트 완벽 수록",
            category = "pro_cert",
            ageTier = "adult",
            priceKrw = 1900,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "cert-it:core",
            coveredRefIds = listOf("cert-it:core", "law-statute:constitution"),
            estimatedCardCount = 35,
            badgeLabel = "수험·자격증 프로",
            features = listOf(
                "대한민국 헌법 핵심 조문(제1조, 제10조, 제37조 제2항 과잉금지원칙 등) 원문 수록",
                "정보처리기사·컴활 필수 데이터베이스(ACID, B-Tree)·네트워크(OSI 7계층) 완벽 정리",
                "조문 번호·수치·부정어 충돌을 정밀 감지하는 서술형 핵심 키워드 채점"
            ),
            sampleCards = listOf(
                SampleCardPreview("데이터베이스 트랜잭션의 4대 특성 (ACID)", "원자성(Atomicity), 일관성(Consistency), 격리성(Isolation), 영속성(Durability)", "정처기"),
                SampleCardPreview("대한민국 헌법 제37조 제2항 (과잉금지원칙)", "자유와 권리의 본질적인 내용을 침해할 수 없다 (비례원칙)", "헌법")
            )
        )
    )

    val defaultFreePackIds: Set<String> =
        products.filter { it.isFreeStarter }.map { it.packId }.toSet()

    fun getProductById(packId: String): BrainPackProduct? =
        products.firstOrNull { it.packId == packId.trim() }

    fun filterCatalog(
        categoryFilter: String? = null,
        ageTierFilter: String? = null
    ): List<BrainPackProduct> {
        val cat = categoryFilter?.trim()?.lowercase().orEmpty()
        val age = ageTierFilter?.trim()?.lowercase().orEmpty()
        return products.filter { p ->
            val catOk = cat.isEmpty() || cat == "all" || p.category == cat
            val ageOk = age.isEmpty() || age == "all" || p.ageTier == "all" || p.ageTier == age
            catOk && ageOk
        }
    }

    fun checkRefEntitlement(
        targetRefId: String,
        unlockedPackIds: Set<String>
    ): EntitlementCheckResult {
        val effectiveUnlocked = defaultFreePackIds + unlockedPackIds
        val matching = products.filter { targetRefId in it.coveredRefIds }
        if (matching.isEmpty()) {
            return EntitlementCheckResult(
                allowed = true,
                targetRefId = targetRefId,
                requiredPackId = null,
                requiredPackTitle = null,
                priceKrw = 0,
                reason = "unrestricted_or_user_uploaded"
            )
        }
        val unlockedMatch = matching.firstOrNull { it.isFreeStarter || it.packId in effectiveUnlocked }
        if (unlockedMatch != null) {
            return EntitlementCheckResult(
                allowed = true,
                targetRefId = targetRefId,
                requiredPackId = unlockedMatch.packId,
                requiredPackTitle = unlockedMatch.title,
                priceKrw = unlockedMatch.priceKrw,
                reason = "entitled"
            )
        }
        val req = matching.first()
        return EntitlementCheckResult(
            allowed = false,
            targetRefId = targetRefId,
            requiredPackId = req.packId,
            requiredPackTitle = req.title,
            priceKrw = req.priceKrw,
            reason = "pack_purchase_required"
        )
    }

    data class BundleQuoteResult(
        val billablePackIds: List<String>,
        val subtotalKrw: Int,
        val discountKrw: Int,
        val finalPriceKrw: Int,
        val discountApplied: Boolean
    )

    fun calculateBundleQuote(
        packIds: List<String>,
        unlockedPackIds: Set<String> = emptySet()
    ): BundleQuoteResult {
        val effectiveUnlocked = defaultFreePackIds + unlockedPackIds
        val billable = mutableListOf<String>()
        val seen = mutableSetOf<String>()
        var subtotal = 0

        for (rawId in packIds) {
            val pid = rawId.trim()
            if (pid.isEmpty() || !seen.add(pid)) continue
            val pack = getProductById(pid) ?: continue
            if (pack.isFreeStarter || pack.packId in effectiveUnlocked || pack.priceKrw <= 0) continue
            billable.add(pack.packId)
            subtotal += pack.priceKrw
        }

        val discountApplied = billable.size >= 3
        val finalPrice = if (discountApplied) ((subtotal * 85) / 1000) * 10 else subtotal
        val discount = subtotal - finalPrice
        return BundleQuoteResult(
            billablePackIds = billable,
            subtotalKrw = subtotal,
            discountKrw = discount,
            finalPriceKrw = finalPrice,
            discountApplied = discountApplied
        )
    }
}
