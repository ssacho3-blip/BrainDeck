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
                "moe-eng:elem-3-4",
                "moe-eng:elementary",
                "moe-eng:middle-1200",
                "moe-eng:high-csat",
                "moe-kor:orthography-lit",
                "moe-hanja-1800:middle",
                "moe-math:core-formulas"
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
            packId = "pack.moe.eng.elem34",
            title = "📘 [교육부 1 · 초등 3~4] 초등 3~4학년 기초 필수 영단어 브레인팩",
            subtitle = "2022 개정 교육과정 초등 3~4학년군 기본 어휘표 · 생활·학교·자연·동작 필수 영단어",
            category = "k12_textbook",
            ageTier = "junior",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "moe-eng:elem-3-4",
            coveredRefIds = listOf("moe-eng:elem-3-4"),
            estimatedCardCount = 36,
            badgeLabel = "교육부 초등 3~4",
            features = listOf(
                "교육부 2022 개정 초등 3~4학년 기초 필수 영단어(morning, weather, borrow 등) 완비",
                "Lv.1 기초 뜻 인지 · Lv.2 문맥 빈칸 · Lv.3 스펠링 인출 3단계 구성",
                "초등 눈높이 4지선다 퀴즈 및 예문 해설 기본 탑재"
            ),
            sampleCards = listOf(
                SampleCardPreview("weather", "날씨 — How is the weather today?", "초등 3~4"),
                SampleCardPreview("borrow", "빌리다 — May I borrow your pencil?", "초등 3~4")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.eng.elem56",
            title = "📘 [교육부 2 · 초등 5~6] 초등 5~6학년 필수 영단어 800 핵심 브레인팩",
            subtitle = "2022 개정 교육과정 초등 5~6학년군 필수 영단어 800 핵심 어휘 & 의사소통 표현",
            category = "k12_textbook",
            ageTier = "junior",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "moe-eng:elementary",
            coveredRefIds = listOf("moe-eng:elementary"),
            estimatedCardCount = 36,
            badgeLabel = "교육부 초등 5~6",
            features = listOf(
                "초등 고학년 필수 영단어 800 핵심(library, museum, vacation, between 등) 수록",
                "중학교 입학 전 반드시 마스터해야 할 핵심 동사·전치사·형용사 정리",
                "품사 노이즈 없는 깔끔한 4지선다 보기 & 상세 예문 해설"
            ),
            sampleCards = listOf(
                SampleCardPreview("museum", "박물관, 미술관 — We visited the science museum.", "초등 5~6"),
                SampleCardPreview("between", "(둘) 사이에 — between A and B", "초등 5~6")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.eng.mid1200",
            title = "📘 [교육부 3 · 중학교] 중학교 1~3학년 필수 영단어 1,200 & 내신 8대 핵심 영문법 브레인팩",
            subtitle = "2022 개정 중학 필수 영단어 1,200 핵심 + 현재완료·관계대명사·감각동사 등 내신 8대 영문법",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "moe-eng:middle-1200",
            coveredRefIds = listOf("moe-eng:middle-1200"),
            estimatedCardCount = 36,
            badgeLabel = "교육부 중학 영단어·문법",
            features = listOf(
                "중학교 1~3학년 필수 영단어 1,200 핵심 어휘(environment, persuade, opportunity 등) 총정리",
                "중학 내신 시험 최빈출 8대 핵심 영문법(감각동사+형용사, 현재완료, 관계대명사 등) 동시 수록",
                "단어 뜻 문제와 영문법 문제를 자동 분리하는 무오염 4지선다"
            ),
            sampleCards = listOf(
                SampleCardPreview("persuade", "설득하다 — persuade + 목적어 + to부정사", "중학 1,200"),
                SampleCardPreview("[중학 핵심문법] 감각동사(look/smell/taste) 뒤 보어 품사는?", "형용사 (부사 -ly 불가)", "중학 영문법")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.eng.high_csat",
            title = "🎓 [교육부 4 · 고교·수능] 고등학교·수능 필수 학술 어휘 브레인팩",
            subtitle = "2022 개정 고등학교 공통영어 및 평가원 모의고사·수능 최빈출 추상·학술 어휘",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "moe-eng:high-csat",
            coveredRefIds = listOf("moe-eng:high-csat"),
            estimatedCardCount = 30,
            badgeLabel = "교육부 고교·수능",
            features = listOf(
                "수능 빈칸추론·순서배열 지문 핵심 학술 어휘(hypothesis, empirical, correlation, cognitive 등)",
                "파생어·반의어(intrinsic ↔ extrinsic, undermine ↔ reinforce) 비교 해설 탑재",
                "고등 내신 서술형 대비 Lv.3 역방향 스펠링 인출 지원"
            ),
            sampleCards = listOf(
                SampleCardPreview("empirical", "경험적인, 실증적인 (↔ theoretical 이론적인)", "수능 학술"),
                SampleCardPreview("correlation", "상관관계, 연관성", "수능 학술")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.kor.orthography_lit",
            title = "🇰🇷 [교육부 5 · 국어] 초·중·고 국어 한글 맞춤법·표준어 규정 & 필수 문학 개념어 브레인팩",
            subtitle = "자주 틀리는 한글 맞춤법(며칠/금세/되·돼/로서·로써) & 내신·수능 필수 문학 개념어",
            category = "k12_textbook",
            ageTier = "all",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "moe-kor:orthography-lit",
            coveredRefIds = listOf("moe-kor:orthography-lit"),
            estimatedCardCount = 24,
            badgeLabel = "교육부 국어·문학",
            features = listOf(
                "국립국어원 한글 맞춤법·표준어 규정 최빈출 혼동 어휘(며칠, 금세, 돼/되, 로서/로써) 명쾌 정리",
                "중·고교 국어 내신 및 수능 필수 문학 개념어(역설법, 반어법, 객관적 상관물, 감정이입) 수록",
                "조항 근거 및 대표 문학 작품(유치환 〈깃발〉, 〈황조가〉 등) 예시 해설"
            ),
            sampleCards = listOf(
                SampleCardPreview("'오늘이 몇 월 [ ___ ]이지?' 바른 맞춤법 표기는?", "며칠 ('몇일'은 틀린 표기 · 한글 맞춤법 제27항)", "한글 맞춤법"),
                SampleCardPreview("'이것은 소리 없는 아우성'처럼 모순 속에 진리를 담는 기법은?", "역설법 (Paradox)", "문학 개념어")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.hanja.mid1800",
            title = "漢字 [교육부 6 · 한문] 중·고교 한문 교육부 기초한자 1,800 핵심 브레인팩",
            subtitle = "교육부 고시 한문 교육용 기초한자 1,800자 핵심(중등 900·고등 900) & 교과서 필수 성어",
            category = "hanja_history",
            ageTier = "all",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "moe-hanja-1800:middle",
            coveredRefIds = listOf("moe-hanja-1800:middle"),
            estimatedCardCount = 30,
            badgeLabel = "교육부 한자 1,800",
            features = listOf(
                "교육부 고시 중학교 900자·고등학교 900자 핵심 한자 훈음·부수·획수 수록",
                "교과서 필수 사자성어(온고지신 溫故知新, 견리사의 見利思義 등) 출전과 속뜻 정리",
                "한자 훈음 전용 4지선다 보기 구성으로 타 과목 보기 혼입 0%"
            ),
            sampleCards = listOf(
                SampleCardPreview("仁 · 義 · 禮 · 智 · 信", "어질 인 · 옳을 의 · 예도 예 · 지혜 지 · 믿을 신", "기초한자 1800"),
                SampleCardPreview("溫故知新 (온고지신)", "옛것을 익히고 그것을 미루어 새것을 안다", "한문 성어")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.hist.essential",
            title = "🏛️ [교육부 7 · 한국사] 한국사 시대별 필수 연표·사건 브레인팩",
            subtitle = "2022 개정 초·중·고 한국사 시대별 필수 연표·조약·개혁·유네스코 세계유산 총정리",
            category = "hanja_history",
            ageTier = "all",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "khist:essential",
            coveredRefIds = listOf("khist:essential"),
            estimatedCardCount = 30,
            badgeLabel = "교육부 한국사 연표",
            features = listOf(
                "고조선 8조법부터 훈민정음·경국대전·대동법·강화도 조약·갑신정변·동학농민운동·임시정부까지 핵심 총망라",
                "사건 연도·핵심 키워드·역사적 의의를 함께 익히는 입체 해설",
                "한국사 전용 오답 풀(Pool) 적용으로 실전형 4지선다 제공"
            ),
            sampleCards = listOf(
                SampleCardPreview("1876년 체결된 조선 최초의 근대적 조약이자 불평등 조약은?", "강화도 조약 (조일수호조규)", "한국사 연표"),
                SampleCardPreview("광해군 때 시행되어 집집마다 특산물 대신 토지 결수로 쌀·베·동전을 납부한 법은?", "대동법 (공인 등장)", "한국사 제도")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.sci.core_formula",
            title = "🔬 [교육부 8 · 과학] 과학 물리·화학·생명·지구과학 핵심 법칙·공식 브레인팩",
            subtitle = "중·고등학교 과학 4대 영역(물리·화학·생명·지구과학) 필수 법칙·화학결합·공식 마스터",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "sci-element-formula:core",
            coveredRefIds = listOf("sci-element-formula:core"),
            estimatedCardCount = 24,
            badgeLabel = "교육부 과학 법칙·공식",
            features = listOf(
                "물리(옴의 법칙 V=IR, 뉴턴 가속도 법칙 F=ma) · 화학(공유결합·이온결합) 필수 개념 수록",
                "생명과학(미토콘드리아 ATP 세포호흡) · 지구과학(판구조론 발산형·수렴형 경계) 핵심 정리",
                "단위·공식 기호까지 정확하게 점검하는 과학 전용 퀴즈"
            ),
            sampleCards = listOf(
                SampleCardPreview("뉴턴 운동 제2법칙(가속도 법칙) 공식은?", "F = m × a (알짜힘 = 질량 × 가속도)", "물리 법칙"),
                SampleCardPreview("세포 호흡을 통해 ATP 에너지를 합성하는 세포 소기관은?", "미토콘드리아", "생명과학")
            )
        ),
        BrainPackProduct(
            packId = "pack.moe.math.core_formula",
            title = "📐 [교육부 9 · 수학] 수학 중·고교 필수 공식 (피타고라스·근의 공식·삼각함수·등차수열·미분계수) 브레인팩",
            subtitle = "중·고등학교 수학과 대수·기하·삼각함수·수열·미적분 핵심 공식 완벽 암기",
            category = "k12_textbook",
            ageTier = "teen",
            priceKrw = 990,
            isFreeStarter = false,
            linkKind = "collection",
            primaryRefId = "moe-math:core-formulas",
            coveredRefIds = listOf("moe-math:core-formulas"),
            estimatedCardCount = 28,
            badgeLabel = "교육부 수학 필수공식",
            features = listOf(
                "피타고라스 정리(a²+b²=c²), 이차방정식 근의 공식·판별식(D=b²-4ac), 근과 계수의 관계 수록",
                "삼각함수 제곱 공식(sin²θ+cos²θ=1), 원의 방정식, 등차수열 일반항(a+(n-1)d), 미분계수 정의 완비",
                "공식 유도 원리와 대표 예제 팁이 포함된 해설 제공"
            ),
            sampleCards = listOf(
                SampleCardPreview("이차방정식 ax² + bx + c = 0 의 근의 공식은?", "x = (-b ± √(b² - 4ac)) / 2a", "수학 공식"),
                SampleCardPreview("첫째항 a, 공차 d인 등차수열의 일반항 aₙ과 미분계수 f'(a)는?", "aₙ = a + (n - 1)d · f'(a) = lim(h→0)[f(a+h)-f(a)]/h", "수열·미분")
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
            val catOk = when {
                cat.isEmpty() || cat == "all" -> true
                cat == "moe_curriculum" -> p.packId.startsWith("pack.moe.")
                else -> p.category == cat
            }
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
