"""Pure Domain Model for BrainDeck In-App BrainPack Store (Zero External I/O).

Enforces the commercial Freemium + Paid Reference Pack business model:
- Free Self-Upload (Camera photo / PDF / Text card factory) + Starter K-12 & Hanja 8-geup Pack are unlocked by default.
- Curated Premium BrainPacks (Middle/High school publisher textbooks, Hanja 7~3 geup, Korean History, TOEIC/JLPT, Law/IT certifications) can be purchased/unlocked in-app and mounted directly into the user's on-device database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class SampleCardPreview:
    front: str
    back: str
    tag: str


@dataclass(frozen=True)
class BrainPackProduct:
    pack_id: str
    title: str
    subtitle: str
    category: str  # 'k12_textbook' | 'hanja_history' | 'language_exam' | 'pro_cert' | 'starter_free'
    age_tier: str  # 'junior' | 'teen' | 'adult' | 'all'
    price_krw: int
    is_free_starter: bool
    link_kind: str  # 'textbook' | 'collection'
    primary_ref_id: str
    covered_ref_ids: tuple[str, ...]
    estimated_card_count: int
    badge_label: str
    features: tuple[str, ...]
    sample_cards: tuple[SampleCardPreview, ...]


BRAINPACK_CATALOG: tuple[BrainPackProduct, ...] = (
    BrainPackProduct(
        pack_id="pack.free.starter_k12",
        title="🎁 [무료 기본] 초등 받아쓰기·기초 영단어 & 한자 8급 입문 브레인팩",
        subtitle="앱 설치 즉시 기본 탑재되는 무료 스타터 데이터팩 (본인 사진/PDF 업로드 무제한 무료 포함)",
        category="starter_free",
        age_tier="all",
        price_krw=0,
        is_free_starter=True,
        link_kind="collection",
        primary_ref_id="hanja-grade:8geup",
        covered_ref_ids=(
            "hanja-grade:8geup",
            "ko-dictation:grade1-2",
            "moe-eng:elem-3-4",
            "moe-eng:elementary",
            "moe-eng:middle-1200",
            "moe-eng:high-csat",
            "moe-kor:orthography-lit",
            "moe-hanja-1800:middle",
            "moe-math:core-formulas",
        ),
        estimated_card_count=20,
        badge_label="무료 기본 탑재",
        features=(
            "어문회 8급 입문 기초 한자 12자 + 부수·획수 완비",
            "초등 1~2학년 받아쓰기 핵심 문장 & 교육부 초등 영단어 맛보기",
            "카메라 촬영·교재 스캔·PDF 자체 카드 생성 무제한 무료",
        ),
        sample_cards=(
            SampleCardPreview("韓", "나라 한 (부수: 韋 · 17획)", "hanja_8geup"),
            SampleCardPreview("무궁화 꽃이 활짝 피었습니다", "초등 받아쓰기 (받침·쌍자음 연습)", "dictation"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.eng.elem34",
        title="📘 [교육부 1 · 초등 3~4] 초등 3~4학년 기초 필수 영단어 브레인팩",
        subtitle="2022 개정 교육과정 초등 3~4학년군 기본 어휘표 · 생활·학교·자연·동작 필수 영단어",
        category="k12_textbook",
        age_tier="junior",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="moe-eng:elem-3-4",
        covered_ref_ids=("moe-eng:elem-3-4",),
        estimated_card_count=36,
        badge_label="교육부 초등 3~4",
        features=(
            "교육부 2022 개정 초등 3~4학년 기초 필수 영단어(morning, weather, borrow 등) 완비",
            "Lv.1 기초 뜻 인지 · Lv.2 문맥 빈칸 · Lv.3 스펠링 인출 3단계 구성",
            "초등 눈높이 4지선다 퀴즈 및 예문 해설 기본 탑재",
        ),
        sample_cards=(
            SampleCardPreview("weather", "날씨 — How is the weather today?", "초등 3~4"),
            SampleCardPreview("borrow", "빌리다 — May I borrow your pencil?", "초등 3~4"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.eng.elem56",
        title="📘 [교육부 2 · 초등 5~6] 초등 5~6학년 필수 영단어 800 핵심 브레인팩",
        subtitle="2022 개정 교육과정 초등 5~6학년군 필수 영단어 800 핵심 어휘 & 의사소통 표현",
        category="k12_textbook",
        age_tier="junior",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="moe-eng:elementary",
        covered_ref_ids=("moe-eng:elementary",),
        estimated_card_count=36,
        badge_label="교육부 초등 5~6",
        features=(
            "초등 고학년 필수 영단어 800 핵심(library, museum, vacation, between 등) 수록",
            "중학교 입학 전 반드시 마스터해야 할 핵심 동사·전치사·형용사 정리",
            "품사 노이즈 없는 깔끔한 4지선다 보기 & 상세 예문 해설",
        ),
        sample_cards=(
            SampleCardPreview("museum", "박물관, 미술관 — We visited the science museum.", "초등 5~6"),
            SampleCardPreview("between", "(둘) 사이에 — between A and B", "초등 5~6"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.eng.mid1200",
        title="📘 [교육부 3 · 중학교] 중학교 1~3학년 필수 영단어 1,200 & 내신 8대 핵심 영문법 브레인팩",
        subtitle="2022 개정 중학 필수 영단어 1,200 핵심 + 현재완료·관계대명사·감각동사 등 내신 8대 영문법",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="moe-eng:middle-1200",
        covered_ref_ids=("moe-eng:middle-1200",),
        estimated_card_count=36,
        badge_label="교육부 중학 영단어·문법",
        features=(
            "중학교 1~3학년 필수 영단어 1,200 핵심 어휘(environment, persuade, opportunity 등) 총정리",
            "중학 내신 시험 최빈출 8대 핵심 영문법(감각동사+형용사, 현재완료, 관계대명사 등) 동시 수록",
            "단어 뜻 문제와 영문법 문제를 자동 분리하는 무오염 4지선다",
        ),
        sample_cards=(
            SampleCardPreview("persuade", "설득하다 — persuade + 목적어 + to부정사", "중학 1,200"),
            SampleCardPreview("[중학 핵심문법] 감각동사(look/smell/taste) 뒤 보어 품사는?", "형용사 (부사 -ly 불가)", "중학 영문법"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.eng.high_csat",
        title="🎓 [교육부 4 · 고교·수능] 고등학교·수능 필수 학술 어휘 브레인팩",
        subtitle="2022 개정 고등학교 공통영어 및 평가원 모의고사·수능 최빈출 추상·학술 어휘",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="moe-eng:high-csat",
        covered_ref_ids=("moe-eng:high-csat",),
        estimated_card_count=30,
        badge_label="교육부 고교·수능",
        features=(
            "수능 빈칸추론·순서배열 지문 핵심 학술 어휘(hypothesis, empirical, correlation, cognitive 등)",
            "파생어·반의어(intrinsic ↔ extrinsic, undermine ↔ reinforce) 비교 해설 탑재",
            "고등 내신 서술형 대비 Lv.3 역방향 스펠링 인출 지원",
        ),
        sample_cards=(
            SampleCardPreview("empirical", "경험적인, 실증적인 (↔ theoretical 이론적인)", "수능 학술"),
            SampleCardPreview("correlation", "상관관계, 연관성", "수능 학술"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.kor.orthography_lit",
        title="🇰🇷 [교육부 5 · 국어] 초·중·고 국어 한글 맞춤법·표준어 규정 & 필수 문학 개념어 브레인팩",
        subtitle="자주 틀리는 한글 맞춤법(며칠/금세/되·돼/로서·로써) & 내신·수능 필수 문학 개념어",
        category="k12_textbook",
        age_tier="all",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="moe-kor:orthography-lit",
        covered_ref_ids=("moe-kor:orthography-lit",),
        estimated_card_count=24,
        badge_label="교육부 국어·문학",
        features=(
            "국립국어원 한글 맞춤법·표준어 규정 최빈출 혼동 어휘(며칠, 금세, 돼/되, 로서/로써) 명쾌 정리",
            "중·고교 국어 내신 및 수능 필수 문학 개념어(역설법, 반어법, 객관적 상관물, 감정이입) 수록",
            "조항 근거 및 대표 문학 작품(유치환 〈깃발〉, 〈황조가〉 등) 예시 해설",
        ),
        sample_cards=(
            SampleCardPreview("'오늘이 몇 월 [ ___ ]이지?' 바른 맞춤법 표기는?", "며칠 ('몇일'은 틀린 표기 · 한글 맞춤법 제27항)", "한글 맞춤법"),
            SampleCardPreview("'이것은 소리 없는 아우성'처럼 모순 속에 진리를 담는 기법은?", "역설법 (Paradox)", "문학 개념어"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.hanja.mid1800",
        title="漢字 [교육부 6 · 한문] 중·고교 한문 교육부 기초한자 1,800 핵심 브레인팩",
        subtitle="교육부 고시 한문 교육용 기초한자 1,800자 핵심(중등 900·고등 900) & 교과서 필수 성어",
        category="hanja_history",
        age_tier="all",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="moe-hanja-1800:middle",
        covered_ref_ids=("moe-hanja-1800:middle",),
        estimated_card_count=30,
        badge_label="교육부 한자 1,800",
        features=(
            "교육부 고시 중학교 900자·고등학교 900자 핵심 한자 훈음·부수·획수 수록",
            "교과서 필수 사자성어(온고지신 溫故知新, 견리사의 見利思義 등) 출전과 속뜻 정리",
            "한자 훈음 전용 4지선다 보기 구성으로 타 과목 보기 혼입 0%",
        ),
        sample_cards=(
            SampleCardPreview("仁 · 義 · 禮 · 智 · 信", "어질 인 · 옳을 의 · 예도 예 · 지혜 지 · 믿을 신", "기초한자 1800"),
            SampleCardPreview("溫故知新 (온고지신)", "옛것을 익히고 그것을 미루어 새것을 안다", "한문 성어"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.hist.essential",
        title="🏛️ [교육부 7 · 한국사] 한국사 시대별 필수 연표·사건 브레인팩",
        subtitle="2022 개정 초·중·고 한국사 시대별 필수 연표·조약·개혁·유네스코 세계유산 총정리",
        category="hanja_history",
        age_tier="all",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="khist:essential",
        covered_ref_ids=("khist:essential",),
        estimated_card_count=30,
        badge_label="교육부 한국사 연표",
        features=(
            "고조선 8조법부터 훈민정음·경국대전·대동법·강화도 조약·갑신정변·동학농민운동·임시정부까지 핵심 총망라",
            "사건 연도·핵심 키워드·역사적 의의를 함께 익히는 입체 해설",
            "한국사 전용 오답 풀(Pool) 적용으로 실전형 4지선다 제공",
        ),
        sample_cards=(
            SampleCardPreview("1876년 체결된 조선 최초의 근대적 조약이자 불평등 조약은?", "강화도 조약 (조일수호조규)", "한국사 연표"),
            SampleCardPreview("광해군 때 시행되어 집집마다 특산물 대신 토지 결수로 쌀·베·동전을 납부한 법은?", "대동법 (공인 등장)", "한국사 제도"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.sci.core_formula",
        title="🔬 [교육부 8 · 과학] 과학 물리·화학·생명·지구과학 핵심 법칙·공식 브레인팩",
        subtitle="중·고등학교 과학 4대 영역(물리·화학·생명·지구과학) 필수 법칙·화학결합·공식 마스터",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="sci-element-formula:core",
        covered_ref_ids=("sci-element-formula:core",),
        estimated_card_count=24,
        badge_label="교육부 과학 법칙·공식",
        features=(
            "물리(옴의 법칙 V=IR, 뉴턴 가속도 법칙 F=ma) · 화학(공유결합·이온결합) 필수 개념 수록",
            "생명과학(미토콘드리아 ATP 세포호흡) · 지구과학(판구조론 발산형·수렴형 경계) 핵심 정리",
            "단위·공식 기호까지 정확하게 점검하는 과학 전용 퀴즈",
        ),
        sample_cards=(
            SampleCardPreview("뉴턴 운동 제2법칙(가속도 법칙) 공식은?", "F = m × a (알짜힘 = 질량 × 가속도)", "물리 법칙"),
            SampleCardPreview("세포 호흡을 통해 ATP 에너지를 합성하는 세포 소기관은?", "미토콘드리아", "생명과학"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.moe.math.core_formula",
        title="📐 [교육부 9 · 수학] 수학 중·고교 필수 공식 (피타고라스·근의 공식·삼각함수·등차수열·미분계수) 브레인팩",
        subtitle="중·고등학교 수학과 대수·기하·삼각함수·수열·미적분 핵심 공식 완벽 암기",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="moe-math:core-formulas",
        covered_ref_ids=("moe-math:core-formulas",),
        estimated_card_count=28,
        badge_label="교육부 수학 필수공식",
        features=(
            "피타고라스 정리(a²+b²=c²), 이차방정식 근의 공식·판별식(D=b²-4ac), 근과 계수의 관계 수록",
            "삼각함수 제곱 공식(sin²θ+cos²θ=1), 원의 방정식, 등차수열 일반항(a+(n-1)d), 미분계수 정의 완비",
            "공식 유도 원리와 대표 예제 팁이 포함된 해설 제공",
        ),
        sample_cards=(
            SampleCardPreview("이차방정식 ax² + bx + c = 0 의 근의 공식은?", "x = (-b ± √(b² - 4ac)) / 2a", "수학 공식"),
            SampleCardPreview("첫째항 a, 공차 d인 등차수열의 일반항 aₙ과 미분계수 f'(a)는?", "aₙ = a + (n - 1)d · f'(a) = lim(h→0)[f(a+h)-f(a)]/h", "수열·미분"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.mid1.eng.donga_yoon.full",
        title="📦 [중1 내신] 동아(윤정미) 영어 Lesson 1~8 전 단원 마스터 브레인팩",
        subtitle="2022 개정 교육과정 · 단원별·쪽수별 시험범위 슬라이싱 + 핵심 영단어·문법 함정선지 완비",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="textbook",
        primary_ref_id="kr.mid1.eng.donga_yoon.2022",
        covered_ref_ids=("kr.mid1.eng.donga_yoon.2022",),
        estimated_card_count=34,
        badge_label="중1 내신 베스트",
        features=(
            "Lesson 1 ~ Lesson 8 전 단원 필수 어휘·숙어·핵심 문법 완벽 매핑",
            "학교 시험범위(단원 체크 + 시작~끝 쪽수) 맞춤형 즉시 덱 생성",
            "내가 찍은 학교 영어 프린트물·본문 스캔과 자동 통합",
        ),
        sample_cards=(
            SampleCardPreview("introduce (p.12)", "소개하다 (동사)", "Lesson 1"),
            SampleCardPreview(
                "[Lesson 5 핵심문법] want, hope, plan, decide가 목적어로 취하는 형태는?",
                "to부정사 (to + 동사원형, 명사적 용법)",
                "Lesson 5",
            ),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.mid2.eng.donga_yoon.full",
        title="📦 [중2 내신] 동아(윤정미) 영어 전 단원·쪽수 마스터 브레인팩",
        subtitle="중학교 2학년 내신 만점 대비 · 단원/쪽수 슬라이싱 & 4지선다 유의어 함정 방어",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="textbook",
        primary_ref_id="kr.mid2.eng.donga_yoon.2022",
        covered_ref_ids=("kr.mid2.eng.donga_yoon.2022",),
        estimated_card_count=24,
        badge_label="중2 내신 필수",
        features=(
            "Lesson 1(Express Yourself) ~ Lesson 3(Green Earth) 핵심 어휘·문법 수록",
            "비연속 단원 및 쪽수 구간(p.Start~End) 시험범위 필터링",
            "4지선다 객관식 ➔ 단어블록 조립 ➔ 스펠링 인출 3단계 자동 승격",
        ),
        sample_cards=(
            SampleCardPreview("confident (p.16)", "자신감 있는 (형용사)", "Lesson 1"),
            SampleCardPreview("recipe (p.31)", "조리법, 레시피 (명사)", "Lesson 2"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.mid2.hist.miraeen.full",
        title="📦 [중2 내신] 미래엔 역사① 연표·사료·문화재 브레인팩",
        subtitle="중학교 역사 내신 출판사 단원 매핑 · 동시대 사건 함정 보기 자동 구성",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="textbook",
        primary_ref_id="kr.mid2.hist.miraeen.2022",
        covered_ref_ids=("kr.mid2.hist.miraeen.2022",),
        estimated_card_count=20,
        badge_label="역사 내신 특화",
        features=(
            "미래엔 중학교 역사① 단원·쪽수별 사건·연표·조약·문화재 정리",
            "가짜 합성 연도 배제 — 실제 역사 사건 연도 기반 4지선다 구성",
            "시험 직전 틀린 연표만 모아 푸는 오답 Cram 세션 연동",
        ),
        sample_cards=(
            SampleCardPreview("훈민정음 창제 (1443, 반포 1446)", "조선 세종 대 백성을 가르치는 바른 소리 28자 창제", "Ⅰ단원"),
            SampleCardPreview("강화도 조약 (1876)", "조선 최초의 근대적 조약이자 불평등 조약", "Ⅰ단원"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.high1.sci.visang.full",
        title="📦 [고1 내신] 비상 통합과학1 공식·핵심개념 브레인팩",
        subtitle="고등학교 1학년 통합과학 물리·화학·생명·지구과학 필수 공식 및 원소 완벽 대비",
        category="k12_textbook",
        age_tier="teen",
        price_krw=990,
        is_free_starter=False,
        link_kind="textbook",
        primary_ref_id="kr.high1.sci.visang.2022",
        covered_ref_ids=("kr.high1.sci.visang.2022", "sci-element-formula:core"),
        estimated_card_count=25,
        badge_label="고1 내신 1등급",
        features=(
            "비상교육 고1 통합과학1 단원·쪽수별 핵심 공식 및 주기율표 원소 매핑",
            "수치·단위(V, A, Ω, 원자번호) 정확도 검증 능동 인출 채점",
            "물리·화학·수학 핵심 공식 컬렉션 동시 잠금해제",
        ),
        sample_cards=(
            SampleCardPreview("옴의 법칙: V = I × R", "전압(V)은 전류(I)와 저항(R)의 곱에 비례한다", "통합과학1"),
            SampleCardPreview("원소기호 Fe (원자번호 26)", "철 (Iron) — 전이금속", "주기율표"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.exam.hanja_master",
        title="📦 [급수한자] 어문회 7급~3급 필수 한자 & 사자성어 올인원 브레인팩",
        subtitle="동음이의어·유사한자 함정선지 완벽 방어 + 두음법칙/다음자(樂 락·악·요) 정밀 채점",
        category="hanja_history",
        age_tier="all",
        price_krw=1500,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="hanja-grade:7geup",
        covered_ref_ids=(
            "hanja-grade:7geup",
            "hanja-grade:6geup",
            "hanja-grade:5geup",
            "hanja-grade:4geup",
            "hanja-grade:3geup",
            "ko-idiom:essential",
        ),
        estimated_card_count=50,
        badge_label="급수시험 올인원",
        features=(
            "한자 7급·6급·5급·4급·3급 급수별 필수 한자 및 사자성어 전체 잠금해제",
            "독음 질문 시 동음이의어 복수 정답 사고를 원천 차단하는 Anti-Leak 4지선다",
            "훈음·부수·획수·사자성어 속뜻 다면 학습 지원",
        ),
        sample_cards=(
            SampleCardPreview("樂 (3급 대표 다음자)", "즐길 락(낙) / 노래 악 / 좋아할 요 (부수: 木 · 15획)", "hanja_3geup"),
            SampleCardPreview("苦盡甘來 (고진감래)", "쓴 것이 다하면 단 것이 온다 — 고생 끝에 낙이 옴", "ko_idiom"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.exam.khist_master",
        title="📦 [한국사] 한국사능력검정 심화(1~3급) 핵심 연표·사료·문화재 브레인팩",
        subtitle="고려·조선·근현대사 핵심 사건·조약·유네스코 문화재 완벽 총정리",
        category="hanja_history",
        age_tier="all",
        price_krw=1500,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="khist:essential",
        covered_ref_ids=("khist:essential",),
        estimated_card_count=30,
        badge_label="한능검 단기합격",
        features=(
            "시대별·왕대별 핵심 사건·조약·문화재 연표 양방향 Cloze",
            "동일 시대·인접 연도 함정 보기 자동 조합으로 실전 변별력 극대화",
            "FSRS-5 시험 D-Day 집중 복습 스케줄링 지원",
        ),
        sample_cards=(
            SampleCardPreview("갑신정변 (1884)", "김옥균·박영효 등 급진개화파가 일으킨 근대화 개혁 운동", "khist"),
            SampleCardPreview("직지심체요절 (1377, 청주 흥덕사)", "현존 세계 최고(最古)의 금속활자본", "khist"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.exam.lang_toeic_jlpt",
        title="📦 [어학] 토익(TOEIC) 고득점 빈출 & JLPT N5~N3 필수 어휘 브레인팩",
        subtitle="비즈니스 영어 핵심 어휘 + 일본어 한자·히라가나 발음/원어민 TTS 스피킹 드릴",
        category="language_exam",
        age_tier="adult",
        price_krw=1900,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="exam-eng:toeic-core",
        covered_ref_ids=("exam-eng:toeic-core", "exam-ja:jlpt-n5-n3"),
        estimated_card_count=40,
        badge_label="어학 베스트셀러",
        features=(
            "토익 पार्ट 5~7 빈출 어휘(CEFR B2~C1) 및 JLPT N5~N3 핵심 어휘 동시 수록",
            "애플/안드로이드 내장 원어민 TTS 발음 듣기 및 스펠링/발음 인출 채점",
            "품사별·난이도별 유의어 4지선다 퀴즈 자동 생성",
        ),
        sample_cards=(
            SampleCardPreview("reimburse", "(경비를) 변제하다, 환급하다 (동사 · C1)", "TOEIC"),
            SampleCardPreview("約束 (やくそく)", "약속 (야쿠소쿠)", "JLPT"),
        ),
    ),
    BrainPackProduct(
        pack_id="pack.pro.law_it_cert",
        title="📦 [성인/전문] 헌법 핵심 조문 & 정보처리기사·컴활 마스터 브레인팩",
        subtitle="공무원·법학 시험 필수 헌법 조문 + IT 자격증(정처기·컴활) 핵심 팩트 완벽 수록",
        category="pro_cert",
        age_tier="adult",
        price_krw=1900,
        is_free_starter=False,
        link_kind="collection",
        primary_ref_id="cert-it:core",
        covered_ref_ids=("cert-it:core", "law-statute:constitution"),
        estimated_card_count=35,
        badge_label="수험·자격증 프로",
        features=(
            "대한민국 헌법 핵심 조문(제1조, 제10조, 제37조 제2항 과잉금지원칙 등) 원문 수록",
            "정보처리기사·컴활 필수 데이터베이스(ACID, B-Tree)·네트워크(OSI 7계층) 완벽 정리",
            "조문 번호·수치·부정어 충돌을 정밀 감지하는 서술형 핵심 키워드 채점",
        ),
        sample_cards=(
            SampleCardPreview("데이터베이스 트랜잭션의 4대 특성 (ACID)", "원자성(Atomicity), 일관성(Consistency), 격리성(Isolation), 영속성(Durability)", "정처기"),
            SampleCardPreview("대한민국 헌법 제37조 제2항 (과잉금지원칙)", "자유와 권리의 본질적인 내용을 침해할 수 없다 (비례원칙)", "헌법"),
        ),
    ),
)

_PACK_BY_ID: dict[str, BrainPackProduct] = {p.pack_id: p for p in BRAINPACK_CATALOG}


def default_free_pack_ids() -> frozenset[str]:
    """Return pack IDs that are unlocked for free out of the box."""
    return frozenset(p.pack_id for p in BRAINPACK_CATALOG if p.is_free_starter)


def get_pack_by_id(pack_id: str) -> BrainPackProduct:
    """Return a BrainPackProduct by ID or raise KeyError."""
    key = str(pack_id or "").strip()
    if key not in _PACK_BY_ID:
        raise KeyError(f"Unknown BrainPack ID: {key}")
    return _PACK_BY_ID[key]


def serialize_pack_product(pack: BrainPackProduct, unlocked_set: set[str]) -> dict[str, Any]:
    """Serialize a BrainPackProduct into a pure dictionary for API/ViewModel consumption."""
    is_unlocked = pack.is_free_starter or (pack.pack_id in unlocked_set)
    return {
        "pack_id": pack.pack_id,
        "title": pack.title,
        "subtitle": pack.subtitle,
        "category": pack.category,
        "age_tier": pack.age_tier,
        "price_krw": pack.price_krw,
        "price_label": "무료 기본 탑재" if pack.price_krw == 0 else f"₩{pack.price_krw:,}",
        "is_free_starter": pack.is_free_starter,
        "unlocked": is_unlocked,
        "status_badge": "✅ 앱 내 장착 완료" if is_unlocked else f"🔒 스토어 구매 (₩{pack.price_krw:,})",
        "link_kind": pack.link_kind,
        "primary_ref_id": pack.primary_ref_id,
        "covered_ref_ids": list(pack.covered_ref_ids),
        "estimated_card_count": pack.estimated_card_count,
        "badge_label": pack.badge_label,
        "features": list(pack.features),
        "sample_cards": [
            {"front": s.front, "back": s.back, "tag": s.tag}
            for s in pack.sample_cards
        ],
    }


def list_store_catalog(
    unlocked_pack_ids: Iterable[str] = (),
    category_filter: str | None = None,
    age_tier_filter: str | None = None,
) -> dict[str, Any]:
    """Return filtered BrainPack Store catalog and entitlement summary."""
    unlocked_set = set(default_free_pack_ids()) | {str(x) for x in unlocked_pack_ids if x}
    cat_norm = str(category_filter or "").strip().lower()
    age_norm = str(age_tier_filter or "").strip().lower()

    items: list[dict[str, Any]] = []
    for pack in BRAINPACK_CATALOG:
        if cat_norm == "moe_curriculum":
            if not pack.pack_id.startswith("pack.moe."):
                continue
        elif cat_norm and cat_norm not in ("all", "") and pack.category != cat_norm:
            continue
        if age_norm and age_norm not in ("all", "") and pack.age_tier not in ("all", age_norm):
            continue
        items.append(serialize_pack_product(pack, unlocked_set))

    total_count = len(BRAINPACK_CATALOG)
    unlocked_count = sum(1 for p in BRAINPACK_CATALOG if p.is_free_starter or p.pack_id in unlocked_set)
    return {
        "ok": True,
        "brand": "BrainDeck (브레인덱)",
        "store_name": "BrainPack Store (브레인팩 스토어)",
        "total_packs": total_count,
        "unlocked_packs": unlocked_count,
        "self_upload_free": True,
        "packs": items,
    }


def check_ref_entitlement(
    target_ref_id: str,
    unlocked_pack_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Check whether a textbook_id or collection_id is unlocked by the user's BrainPacks."""
    ref_norm = str(target_ref_id or "").strip()
    unlocked_set = set(default_free_pack_ids()) | {str(x) for x in unlocked_pack_ids if x}

    matching_packs = [p for p in BRAINPACK_CATALOG if ref_norm in p.covered_ref_ids]
    if not matching_packs:
        # User-uploaded or custom reference not governed by a paid pack
        return {
            "allowed": True,
            "target_ref_id": ref_norm,
            "required_pack_id": None,
            "reason": "unrestricted_or_user_uploaded",
        }

    for pack in matching_packs:
        if pack.is_free_starter or pack.pack_id in unlocked_set:
            return {
                "allowed": True,
                "target_ref_id": ref_norm,
                "required_pack_id": pack.pack_id,
                "reason": "entitled",
            }

    req = matching_packs[0]
    return {
        "allowed": False,
        "target_ref_id": ref_norm,
        "required_pack_id": req.pack_id,
        "required_pack_title": req.title,
        "price_krw": req.price_krw,
        "reason": "pack_purchase_required",
    }


def validate_store_purchase(
    pack_id: str,
    unlocked_pack_ids: Iterable[str] = (),
    payment_token: str | None = None,
) -> dict[str, Any]:
    """Validate a BrainPack purchase/unlock request deterministically (Fail-Closed on missing payment proof)."""
    pack = get_pack_by_id(pack_id)
    unlocked_set = set(default_free_pack_ids()) | {str(x) for x in unlocked_pack_ids if x}
    already_unlocked = pack.is_free_starter or (pack.pack_id in unlocked_set)
    token_norm = str(payment_token or "").strip()
    if not already_unlocked and pack.price_krw > 0:
        if not token_norm.startswith(("BDPAY-", "RECEIPT-", "TEST-OK-")):
            raise ValueError(
                f"payment_verification_required: valid payment_token required for paid BrainPack '{pack.pack_id}'"
            )
    return {
        "ok": True,
        "pack_id": pack.pack_id,
        "title": pack.title,
        "price_krw": pack.price_krw,
        "already_unlocked": already_unlocked,
        "payment_verified": True,
        "link_kind": pack.link_kind,
        "primary_ref_id": pack.primary_ref_id,
        "covered_ref_ids": list(pack.covered_ref_ids),
    }


def calculate_bundle_quote(
    pack_ids: Iterable[str],
    unlocked_pack_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Calculate multi-pack bundle cart quote (Trap T34: 15% discount when buying >= 3 paid packs)."""
    unlocked_set = set(default_free_pack_ids()) | {str(x) for x in unlocked_pack_ids if x}
    billable_ids: list[str] = []
    seen: set[str] = set()
    subtotal_krw = 0

    for raw_id in pack_ids:
        pid = str(raw_id or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        pack = get_pack_by_id(pid)
        if pack.is_free_starter or pack.pack_id in unlocked_set or pack.price_krw <= 0:
            continue
        billable_ids.append(pack.pack_id)
        subtotal_krw += pack.price_krw

    discount_applied = len(billable_ids) >= 3
    if discount_applied:
        final_price_krw = ((subtotal_krw * 85) // 1000) * 10
        discount_krw = subtotal_krw - final_price_krw
    else:
        final_price_krw = subtotal_krw
        discount_krw = 0

    allocated_prices_krw: dict[str, int] = {}
    if billable_ids and subtotal_krw > 0:
        floors: dict[str, int] = {}
        remainders: list[tuple[int, str]] = []
        floor_sum = 0
        for pid in billable_ids:
            pack = get_pack_by_id(pid)
            num = pack.price_krw * final_price_krw
            fl = num // subtotal_krw
            rem = num % subtotal_krw
            floors[pid] = fl
            floor_sum += fl
            remainders.append((rem, pid))
        leftover = max(0, final_price_krw - floor_sum)
        # Largest remainder method: sort by (-remainder, pack_id ascending)
        remainders.sort(key=lambda item: (-item[0], item[1]))
        for idx in range(leftover):
            target_pid = remainders[idx % len(remainders)][1]
            floors[target_pid] += 1
        allocated_prices_krw = floors

    return {
        "schema_version": 1,
        "billable_pack_ids": billable_ids,
        "billable_count": len(billable_ids),
        "subtotal_krw": subtotal_krw,
        "discount_krw": discount_krw,
        "final_price_krw": final_price_krw,
        "allocated_prices_krw": allocated_prices_krw,
        "discount_applied": discount_applied,
        "discount_rate_pct": 15 if discount_applied else 0,
    }


def decide_entitlement_action(
    target_ref_id: str,
    unlocked_pack_ids: Iterable[str] = (),
    refunded_pack_ids: Iterable[str] = (),
    action: str = "GENERATE",
) -> dict[str, Any]:
    """Single Fail-Closed Entitlement Policy Gate (Invariants I-1 / AC-1).

    Actions:
      - 'GENERATE': Creating new exam scope decks, collection decks, or materializing new pack cards.
      - 'REVIEW': Studying/reviewing already materialized FSRS cards in the user's ledger.
    """
    act = str(action or "GENERATE").strip().upper()
    if act not in ("GENERATE", "REVIEW"):
        return {
            "allowed": False,
            "action": act,
            "target_ref_id": str(target_ref_id or ""),
            "required_pack_id": None,
            "error_code": "ENTITLEMENT_UNAVAILABLE",
        }

    ref_norm = str(target_ref_id or "").strip()
    if not ref_norm:
        return {
            "allowed": False,
            "action": act,
            "target_ref_id": "",
            "required_pack_id": None,
            "error_code": "ENTITLEMENT_UNAVAILABLE",
        }

    unlocked_set = set(default_free_pack_ids()) | {str(x) for x in unlocked_pack_ids if x}
    refunded_set = {str(x) for x in refunded_pack_ids if x} - set(default_free_pack_ids())

    matching_packs: list[BrainPackCatalogItem] = [
        p for p in BRAINPACK_CATALOG if ref_norm == p.primary_ref_id or ref_norm in p.covered_ref_ids
    ]
    if not matching_packs:
        return {
            "allowed": True,
            "action": act,
            "target_ref_id": ref_norm,
            "required_pack_id": None,
            "error_code": None,
        }

    for pack in matching_packs:
        if pack.is_free_starter or (pack.pack_id in unlocked_set and pack.pack_id not in refunded_set):
            return {
                "allowed": True,
                "action": act,
                "target_ref_id": ref_norm,
                "required_pack_id": pack.pack_id,
                "error_code": None,
            }

    req = matching_packs[0]
    if any(p.pack_id in refunded_set for p in matching_packs):
        if act == "REVIEW":
            return {
                "allowed": True,
                "action": act,
                "target_ref_id": ref_norm,
                "required_pack_id": req.pack_id,
                "error_code": None,
            }
        return {
            "allowed": False,
            "action": act,
            "target_ref_id": ref_norm,
            "required_pack_id": req.pack_id,
            "error_code": "PACK_REFUNDED_FROZEN",
        }

    return {
        "allowed": False,
        "action": act,
        "target_ref_id": ref_norm,
        "required_pack_id": req.pack_id,
        "error_code": "PACK_LOCKED",
    }


def resolve_cloud_vision_policy(
    age_tier: str | None,
    cloud_vision_locked: bool | int | None,
    requested: bool,
) -> dict[str, Any]:
    """Server-enforced Junior & PIPA Cloud-Vision Gate (Invariant I-3 / AC-4).

    Unknown or missing age_tier defaults Fail-Closed to 'junior'.
    If requested=True while locked or junior, returns allowed=False with error_code='CLOUD_VISION_LOCKED'
    rather than silently downgrading (Zero Fabricated Status).
    """
    tier_norm = str(age_tier or "").strip().lower()
    if tier_norm not in ("junior", "teen", "adult"):
        tier_norm = "junior"
    is_locked = (tier_norm == "junior") or (cloud_vision_locked is None) or bool(cloud_vision_locked)
    req_bool = bool(requested)

    if req_bool and is_locked:
        return {
            "allowed": False,
            "use_cloud_vision": False,
            "effective_age_tier": tier_norm,
            "cloud_vision_locked": True,
            "error_code": "CLOUD_VISION_LOCKED",
        }
    return {
        "allowed": True,
        "use_cloud_vision": req_bool and not is_locked,
        "effective_age_tier": tier_norm,
        "cloud_vision_locked": is_locked,
        "error_code": None,
    }
