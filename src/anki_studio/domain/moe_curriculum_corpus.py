"""Official Ministry of Education (교육부 2022 개정 교육과정) Grade-Level English & Multi-Subject Core Corpus.

Pure Domain Module (Zero-I/O):
- Collects and structures official MOE-guided grade-level vocabulary, grammar, Korean orthography/literature,
  Hanja 1800, Korean/World History, Science (Physics/Chemistry/Biology/Earth Science), and Mathematics formulas.
- Every item carries explicit `id`, `term`, `answer`, `role`, `prompt`, `sentence` (Cloze), and `explain`
  so it can be expanded into Lv.1 (Basic Recognition), Lv.2 (Contextual Cloze), and Lv.3 (Active Recall) cards
  with 100% deterministic question-type classification (zero cross-type distractor contamination).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


MOE_CURRICULUM_COLLECTIONS: List[Dict[str, Any]] = [
    # =========================================================================
    # 1. 교육부 고시 초등 3~4학년군 기초 필수 영단어 (2022 개정 영어과 기본 어휘표)
    # =========================================================================
    {
        "collection_id": "moe-eng:elem-3-4",
        "grade_band": "초등 3~4학년",
        "subject": "english",
        "level_label": "교육부 고시 초등 3~4학년 기초 필수 영단어 (기본 어휘표)",
        "unlocked": True,
        "items": [
            {"id": "e34_01", "term": "morning", "answer": "아침", "role": "core_vocab", "sentence": "Good {{c1::morning::아침}}! How are you today?", "explain": "in the morning (아침에) · 반대: evening(저녁), night(밤)"},
            {"id": "e34_02", "term": "weather", "answer": "날씨", "role": "core_vocab", "sentence": "How is the {{c1::weather::날씨}} today? It is sunny.", "explain": "sunny(맑은), cloudy(흐린), rainy(비 오는), snowy(눈 오는)"},
            {"id": "e34_03", "term": "friend", "answer": "친구", "role": "core_vocab", "sentence": "She is my best {{c1::friend::친구}} at school.", "explain": "make friends with (~와 친구가 되다)"},
            {"id": "e34_04", "term": "teacher", "answer": "선생님", "role": "core_vocab", "sentence": "Our English {{c1::teacher::선생님}} is very kind.", "explain": "teach(가르치다) + -er(사람) = teacher(선생님)"},
            {"id": "e34_05", "term": "hungry", "answer": "배고픈", "role": "core_vocab", "sentence": "I am {{c1::hungry::배고픈}}. Let's have lunch!", "explain": "thirsty(목마른), full(배부른), tired(피곤한)"},
            {"id": "e34_06", "term": "thirsty", "answer": "목마른", "role": "core_vocab", "sentence": "I am {{c1::thirsty::목마른}}. Can I have some water?", "explain": "drink water(물을 마시다)와 자주 함께 쓰이는 초등 필수 형용사"},
            {"id": "e34_07", "term": "listen", "answer": "귀 기울여 듣다", "role": "core_vocab", "sentence": "Please {{c1::listen::듣다}} to the teacher carefully.", "explain": "listen to (~을 귀 기울여 듣다, 't'는 묵음)"},
            {"id": "e34_08", "term": "borrow", "answer": "빌리다", "role": "core_vocab", "sentence": "May I {{c1::borrow::빌리다}} your pencil?", "explain": "borrow(빌려 오다) ↔ lend(빌려주다)"},
            {"id": "e34_09", "term": "animal", "answer": "동물", "role": "core_vocab", "sentence": "What is your favorite {{c1::animal::동물}} at the zoo?", "explain": "wild animals (야생 동물)"},
            {"id": "e34_10", "term": "umbrella", "answer": "우산", "role": "core_vocab", "sentence": "It's raining outside. Take your {{c1::umbrella::우산}}.", "explain": "모음 소리로 시작하므로 부정관사 an umbrella로 사용"},
            {"id": "e34_11", "term": "breakfast", "answer": "아침 식사", "role": "core_vocab", "sentence": "I eat bread and milk for {{c1::breakfast::아침 식사}}.", "explain": "breakfast(아침) - lunch(점심) - dinner(저녁), 식사 이름 앞에는 관사 무사용"},
            {"id": "e34_12", "term": "clean", "answer": "청소하다, 깨끗한", "role": "core_vocab", "sentence": "Let's {{c1::clean::청소하다}} our classroom together.", "explain": "형용사(깨끗한)와 동사(청소하다)로 모두 쓰임"},
        ],
    },
    # =========================================================================
    # 2. 교육부 고시 초등 5~6학년군 필수 영단어 800 핵심
    # =========================================================================
    {
        "collection_id": "moe-eng:elementary",
        "grade_band": "초등 5~6학년",
        "subject": "english",
        "level_label": "교육부 고시 초등 5~6학년 필수 영단어 800 핵심",
        "unlocked": True,
        "items": [
            {"id": "me_1", "term": "library", "answer": "도서관", "role": "core_vocab", "sentence": "I borrow books from the school {{c1::library::도서관}}.", "explain": "school library (학교 도서관)"},
            {"id": "me_2", "term": "hospital", "answer": "병원", "role": "core_vocab", "sentence": "Doctors and nurses work at the {{c1::hospital::병원}}.", "explain": "go to the hospital (병원에 가다)"},
            {"id": "me_3", "term": "tomorrow", "answer": "내일", "role": "core_vocab", "sentence": "See you {{c1::tomorrow::내일}} morning!", "explain": "yesterday(어제) - today(오늘) - tomorrow(내일)"},
            {"id": "me_4", "term": "museum", "answer": "박물관", "role": "core_vocab", "sentence": "We visited the science {{c1::museum::박물관}} on our field trip.", "explain": "art museum (미술관), history museum (역사 박물관)"},
            {"id": "me_5", "term": "vacation", "answer": "방학, 휴가", "role": "core_vocab", "sentence": "What will you do this summer {{c1::vacation::방학}}?", "explain": "summer vacation (여름방학), winter vacation (겨울방학)"},
            {"id": "me_6", "term": "exercise", "answer": "운동하다, 운동", "role": "core_vocab", "sentence": "I {{c1::exercise::운동하다}} every day to stay healthy.", "explain": "do exercise (운동하다), regular exercise (규칙적인 운동)"},
            {"id": "me_7", "term": "delicious", "answer": "맛있는", "role": "core_vocab", "sentence": "This Korean bulgogi tastes really {{c1::delicious::맛있는}}!", "explain": "감각동사 taste/look/smell 뒤에 형용사 보어로 자주 출제"},
            {"id": "me_8", "term": "straight", "answer": "곧장, 똑바로", "role": "core_vocab", "sentence": "Go {{c1::straight::곧장}} two blocks and turn left.", "explain": "길 찾기 필수 표현: go straight (직진하다)"},
            {"id": "me_9", "term": "between", "answer": "(둘) 사이에", "role": "core_vocab", "sentence": "The bakery is {{c1::between::사이에}} the bank and the post office.", "explain": "between A and B (A와 B 사이에)"},
            {"id": "me_10", "term": "famous", "answer": "유명한", "role": "core_vocab", "sentence": "Gyeongju is {{c1::famous::유명한}} for its historical temples.", "explain": "be famous for (~로 유명하다)"},
            {"id": "me_11", "term": "practice", "answer": "연습하다, 연습", "role": "core_vocab", "sentence": "I {{c1::practice::연습하다}} playing the piano every afternoon.", "explain": "Practice makes perfect (연습이 완벽을 만든다)"},
            {"id": "me_12", "term": "future", "answer": "미래, 장래", "role": "core_vocab", "sentence": "What do you want to be in the {{c1::future::미래}}?", "explain": "in the future (장래에, 미래에)"},
        ],
    },
    # =========================================================================
    # 3. 교육부 고시 중학교 1~3학년 학년별 필수 영단어 & 핵심 문법 (중등 1,200 핵심)
    # =========================================================================
    {
        "collection_id": "moe-eng:middle-1200",
        "grade_band": "중학교 1~3학년",
        "subject": "english",
        "level_label": "교육부 고시 중학교 학년별 필수 영단어 1,200 & 내신 핵심 문법",
        "unlocked": True,
        "items": [
            {"id": "mm_01", "term": "introduce", "answer": "소개하다", "role": "core_vocab", "sentence": "Let me {{c1::introduce::소개하다}} myself to the class.", "explain": "introduce A to B (A를 B에게 소개하다)"},
            {"id": "mm_02", "term": "communicate", "answer": "의사소통하다", "role": "core_vocab", "sentence": "We use language to {{c1::communicate::의사소통하다}} with others.", "explain": "명사형: communication (의사소통)"},
            {"id": "mm_03", "term": "volunteer", "answer": "자원봉사하다, 봉사자", "role": "core_vocab", "sentence": "She works as a {{c1::volunteer::자원봉사자}} at the local library.", "explain": "volunteer work (자원봉사 활동)"},
            {"id": "mm_04", "term": "environment", "answer": "환경", "role": "core_vocab", "sentence": "We must reduce plastic waste to protect the {{c1::environment::환경}}.", "explain": "environmental protection (환경 보호)"},
            {"id": "mm_05", "term": "experience", "answer": "경험, 경험하다", "role": "core_vocab", "sentence": "Traveling abroad is a valuable {{c1::experience::경험}}.", "explain": "명사(경험)와 동사(경험하다) 모두 핵심 출제"},
            {"id": "mm_06", "term": "opportunity", "answer": "기회", "role": "core_vocab", "sentence": "Don't miss this great {{c1::opportunity::기회}} to learn.", "explain": "take the opportunity (기회를 잡다), 동의어: chance"},
            {"id": "mm_07", "term": "achievement", "answer": "성취, 업적", "role": "core_vocab", "sentence": "King Sejong's greatest {{c1::achievement::업적}} was creating Hunminjeongeum.", "explain": "동사 achieve(성취하다) + -ment(명사화 접미사)"},
            {"id": "mm_08", "term": "cooperate", "answer": "협력하다, 협동하다", "role": "core_vocab", "sentence": "Team members need to {{c1::cooperate::협력하다}} with one another.", "explain": "명사형: cooperation (협력, 협동)"},
            {"id": "mm_09", "term": "persuade", "answer": "설득하다", "role": "core_vocab", "sentence": "He tried to {{c1::persuade::설득하다}} his parents to allow the trip.", "explain": "persuade + 목적어 + to부정사 (~가 …하도록 설득하다)"},
            {"id": "mm_10", "term": "sustainable", "answer": "지속 가능한", "role": "core_vocab", "sentence": "Solar and wind power are {{c1::sustainable::지속 가능한}} energy sources.", "explain": "sustainable development (지속 가능한 발전)"},
            {"id": "mm_11", "term": "감각동사 + 형용사 보어", "answer": "형용사 (부사 -ly 불가)", "role": "key_grammar", "prompt": "감각동사(look/sound/smell/taste/feel) 뒤에 보어로 반드시 와야 하는 품사는?", "sentence": "The cookies smell {{c1::good::형용사 보어(well 불가)}} and taste {{c2::sweet::형용사(sweetly 불가)}}.", "explain": "감각동사 뒤에는 부사(-ly)가 올 수 없고 형용사만 보어로 옴 (감각동사 + like + 명사)"},
            {"id": "mm_12", "term": "현재완료 (have/has + p.p.)", "answer": "have / has + 과거분사(p.p.)", "role": "key_grammar", "prompt": "과거에 시작된 동작이나 상태가 현재까지 영향을 미칠 때(경험·계속·완료·결과) 사용하는 시제 형태는?", "sentence": "I {{c1::have lived::현재완료(계속)}} in Seoul for five years.", "explain": "for + 기간 숫자 / since + 과거 시점과 함께 쓰이면 현재완료 '계속' 용법 (yesterday, ~ ago 등 명백한 과거 부사와는 함께 쓸 수 없음)"},
        ],
    },
    # =========================================================================
    # 4. 교육부 고시 고등학교 공통영어·수능 필수 학술 어휘 (고등 1,000 핵심)
    # =========================================================================
    {
        "collection_id": "moe-eng:high-csat",
        "grade_band": "고등학교·수능",
        "subject": "english",
        "level_label": "교육부 고시 고등학교·수능 필수 학술 어휘 (평가원 최빈출)",
        "unlocked": True,
        "items": [
            {"id": "mh_eng_01", "term": "hypothesis", "answer": "가설, 가정", "role": "core_vocab", "sentence": "Scientists conducted experiments to test their {{c1::hypothesis::가설}}.", "explain": "복수형: hypotheses · 동사: hypothesize(가설을 세우다)"},
            {"id": "mh_eng_02", "term": "empirical", "answer": "경험적인, 실증적인", "role": "core_vocab", "sentence": "The theory is supported by strong {{c1::empirical::실증적인}} evidence.", "explain": "empirical evidence (실증적·실험적 증거) ↔ theoretical(이론적인)"},
            {"id": "mh_eng_03", "term": "correlation", "answer": "상관관계, 연관성", "role": "core_vocab", "sentence": "There is a strong {{c1::correlation::상관관계}} between sleep quality and memory retention.", "explain": "correlation does not imply causation (상관관계가 인과관계를 의미하지는 않는다)"},
            {"id": "mh_eng_04", "term": "cognitive", "answer": "인지의, 인식의", "role": "core_vocab", "sentence": "Active recall strengthens {{c1::cognitive::인지의}} pathways in the brain.", "explain": "cognitive psychology (인지 심리학), cognitive load (인지 부하)"},
            {"id": "mh_eng_05", "term": "intrinsic", "answer": "내재적인, 본질적인", "role": "core_vocab", "sentence": "Curiosity provides {{c1::intrinsic::내재적인}} motivation for learning.", "explain": "intrinsic(내재적인) ↔ extrinsic(외재적인)"},
            {"id": "mh_eng_06", "term": "inevitable", "answer": "피할 수 없는, 필연적인", "role": "core_vocab", "sentence": "Technological change is {{c1::inevitable::피할 수 없는}} in modern society.", "explain": "동의어: unavoidable"},
            {"id": "mh_eng_07", "term": "ambiguity", "answer": "모호함, 중의성", "role": "core_vocab", "sentence": "Legal contracts must be written clearly to avoid {{c1::ambiguity::모호함}}.", "explain": "형용사: ambiguous (애매모호한, 두 가지로 해석될 수 있는)"},
            {"id": "mh_eng_08", "term": "paradox", "answer": "역설, 모순", "role": "core_vocab", "sentence": "The {{c1::paradox::역설}} of choice suggests that too many options can reduce satisfaction.", "explain": "형용사: paradoxical (역설적인)"},
            {"id": "mh_eng_09", "term": "undermine", "answer": "(기반·신뢰를) 약화시키다, 훼손하다", "role": "core_vocab", "sentence": "Rumors can {{c1::undermine::약화시키다}} mutual trust within a team.", "explain": "반의어: reinforce, strengthen (강화하다)"},
            {"id": "mh_eng_10", "term": "facilitate", "answer": "촉진하다, 용이하게 하다", "role": "core_vocab", "sentence": "Spaced repetition {{c1::facilitates::촉진하다}} long-term memory consolidation.", "explain": "명사형: facilitator (촉진자, 진행자)"},
        ],
    },
    # =========================================================================
    # 5. 국어과: 초·중·고 필수 맞춤법·어문 규정·문학 개념어
    # =========================================================================
    {
        "collection_id": "moe-kor:orthography-lit",
        "grade_band": "초·중·고 공통",
        "subject": "korean",
        "level_label": "교육부 국어과 필수 한글 맞춤법·표준어 규정 & 문학 핵심 개념어",
        "unlocked": True,
        "items": [
            {"id": "mk_01", "term": "며칠", "answer": "며칠", "role": "core_concept", "prompt": "'오늘이 몇 월 [ ___ ]이지?'에서 어원이 분명하지 아니하여 소리 나는 대로 적는 바른 맞춤법 표기는? ('몇일'은 틀린 표기)", "sentence": "오늘이 몇 월 {{c1::며칠::맞춤법 주의('몇일' 아님)}}인지 달력을 확인해 보자.", "explain": "한글 맞춤법 제27항 붙임2: '며칠'은 '몇+일'로 분석되지 않으므로 언제나 '며칠'로만 적습니다."},
            {"id": "mk_02", "term": "금세", "answer": "금세 (금시에의 준말)", "role": "core_concept", "prompt": "'지금 바로'를 뜻하는 '금시에'가 줄어든 말의 바른 맞춤법 표기는? ('금새'는 틀린 표기)", "sentence": "소나기가 내리더니 {{c1::금세::'금새'가 아님}} 하늘이 맑게 개었다.", "explain": "'금시에'가 줄어든 말이므로 '금세'(ㅡ+ㅔ)가 맞고 '금새'는 틀린 표기입니다."},
            {"id": "mk_03", "term": "되다 / 돼다 구분", "answer": "되어(돼) · 되었다(됐다)", "role": "core_concept", "prompt": "어간 '되-' 뒤에 어미 '-어/-었-'이 결합하여 줄어들 때의 바른 표기 원칙은?", "sentence": "벌써 봄이 {{c1::돼::되어}} 날씨가 따뜻해{{c2::졌다::지었다}}.", "explain": "'하-'를 넣어 말이 되면 '돼(되어)', '하-'를 넣어 어색하고 '하니/하고'가 자연스러우면 '되'를 씁니다(예: 안 돼 / 안 되니)."},
            {"id": "mk_04", "term": "로서 / 로써 구분", "answer": "로서(자격·신분) · 로써(수단·도구)", "role": "core_concept", "prompt": "조사 '로서'와 '로써'의 의미 차이를 구분하시오.", "sentence": "학생{{c1::으로서::자격·신분}} 본분을 지키고, 대화{{c2::로써::수단·방법}} 갈등을 해결한다.", "explain": "로서 = 지위·신분·자격 (교사로서) / 로써 = 물건의 재료·수단·도구 (눈물로써 호소하다)"},
            {"id": "mk_05", "term": "역설법 (Paradox)", "answer": "역설법", "role": "core_concept", "prompt": "'이것은 소리 없는 아우성', '님은 갔지마는 나는 님을 보내지 아니하였습니다'처럼 겉으로는 모순되지만 그 속에 진리를 담는 표현 기법은?", "sentence": "유치환의 〈깃발〉에서 '소리 없는 아우성'은 모순된 표현 속에 진실을 담은 {{c1::역설법::수사법}}이다.", "explain": "역설법(문장 자체에 논리적 모순 존재) ↔ 반어법(문장 자체는 모순이 없으나 속마음과 반대로 표현, 예: '잘~한다!')"},
            {"id": "mk_06", "term": "객관적 상관물", "answer": "객관적 상관물", "role": "core_concept", "prompt": "문학 작품에서 화자의 정서나 사상을 간접적으로 환기·구체화하기 위해 끌어들인 구체적 자연물·사물을 무엇이라 하는가?", "sentence": "황조가의 '꾀꼬리'처럼 화자의 외로움을 부각하는 대상을 {{c1::객관적 상관물::문학 개념어}}이라 한다.", "explain": "화자와 대비되어 외로움을 심화하는 자연물과, 화자의 감정을 그대로 투영한 '감정이입' 대상 모두 객관적 상관물에 포함됩니다."},
        ],
    },
    # =========================================================================
    # 6. 한문과: 교육부 고시 한문 교육용 기초 한자 1,800자 핵심 & 필수 사자성어
    # =========================================================================
    {
        "collection_id": "moe-hanja-1800:middle",
        "grade_band": "중·고등 한문",
        "subject": "hanja",
        "level_label": "교육부 고시 한문 교육용 기초 한자 1,800자 핵심 (중등 900 · 고등 900)",
        "unlocked": True,
        "items": [
            {"id": "mh_1", "term": "仁", "answer": "어질 인", "role": "core_concept", "sentence": "{{c1::어질 인::仁}}은 공자 유교 사상의 핵심 덕목이다.", "explain": "부수: 亻(사람인변) · 활용: 인의(仁義), 인자(仁慈), 살신성인(殺身成仁)"},
            {"id": "mh_2", "term": "義", "answer": "옳을 의", "role": "core_concept", "sentence": "견리사의(見利思{{c1::義::옳을 의}})는 이익을 보면 의로움을 먼저 생각한다는 뜻이다.", "explain": "부수: 羊(양양) · 활용: 정의(正義), 의무(義務), 대의명분(大義名分)"},
            {"id": "mh_3", "term": "禮", "answer": "예도 예", "role": "core_concept", "sentence": "동방{{c1::예::예도 예(禮)}}의지국의 전통을 이어간다.", "explain": "부수: 示(보일시) · 활용: 예절(禮節), 예의(禮儀), 무례(無禮)"},
            {"id": "mh_4", "term": "智", "answer": "지혜 지", "role": "core_concept", "sentence": "어려울 때일수록 {{c1::지::지혜 지(智)}}혜를 모아야 한다.", "explain": "부수: 日(날일) · 활용: 지혜(智慧), 지식(知識)"},
            {"id": "mh_5", "term": "信", "answer": "믿을 신", "role": "core_concept", "sentence": "붕우유신(朋友有{{c1::信::믿을 신}})은 벗 사이에 믿음이 있어야 함을 뜻한다.", "explain": "부수: 亻(사람인변) · 활용: 신뢰(信賴), 신의(信義), 확신(確信)"},
            {"id": "mh_6", "term": "溫故知新", "answer": "온고지신 — 옛것을 익히고 그것을 미루어 새것을 안다", "role": "core_concept", "prompt": "《논어》 위정편에서 유래한 성어로, '옛것을 익히고 그것을 미루어 새것을 안다'(溫故而知新 可以爲師矣)를 뜻하는 사자성어는?", "sentence": "전통문화를 바탕으로 현대 예술을 창조하는 자세를 {{c1::온고지신::溫故知新}}이라 한다.", "explain": "따뜻할/익힐 온(溫) · 옛 고(故) · 알 지(知) · 새 신(新)"},
        ],
    },
    # =========================================================================
    # 7. 사회·역사과: 교육부 초·중·고 한국사 필수 통사 연표·사건·문화재
    # =========================================================================
    {
        "collection_id": "khist:essential",
        "grade_band": "초·중·고 한국사",
        "subject": "history",
        "level_label": "교육부 한국사 교육과정 필수 연표·조약·개혁·문화유산 총정리",
        "unlocked": True,
        "items": [
            {"id": "kh_1", "term": "강화도 조약", "answer": "강화도 조약", "role": "core_concept", "prompt": "1876년 운요호 사건을 계기로 조선이 일본과 체결한 최초의 근대적 조약이자 불평등 조약은?", "sentence": "1876년 체결된 {{c1::강화도 조약::조일수호조규}}은 부산·원산·인천 개항과 영사재판권(치외법권)을 규정하였다.", "explain": "1876년 조일수호조규: 최초의 근대적 조약이나 치외법권·해안측량권을 허용한 불평등 조약"},
            {"id": "kh_2", "term": "갑신정변", "answer": "갑신정변", "role": "core_concept", "prompt": "1884년 김옥균·박영효 등 급진 개화파가 우정총국 개국 축하연을 계기로 일으킨 근대적 개혁 운동은?", "sentence": "1884년 급진 개화파가 일으킨 {{c1::갑신정변::3일 천하}}에서는 청 사대 관계 청산과 인민평등권을 주장하였다.", "explain": "1884년 김옥균 등 급진 개화파 주도, 14개조 개혁정강 발표, 청군 개입으로 3일 만에 실패"},
            {"id": "kh_3", "term": "동학 농민 운동", "answer": "동학 농민 운동", "role": "core_concept", "prompt": "1894년 전봉준 등을 중심으로 고부 농민 봉기에서 시작되어 '제폭구민·보국안민'을 내걸고 전개된 반봉건·반외세 운동은?", "sentence": "1894년 {{c1::동학 농민 운동::전봉준·황토현·우금치}}은 전주 화약 이후 집강소를 설치하여 폐정 개혁안을 실천하였다.", "explain": "1894년 고부 봉기 → 황토현·황룡촌 승리 → 전주 화약·집강소 → 우금치 전투 패배 (갑오개혁과 청일전쟁에 영향)"},
            {"id": "kh_4", "term": "훈민정음", "answer": "훈민정음", "role": "core_concept", "prompt": "조선 세종 25년(1443) 백성을 가르치는 바른 소리라는 뜻으로 창제하여 1446년에 반포한 우리 고유 문자는?", "sentence": "조선 세종이 1443년 창제한 {{c1::훈민정음::해례본 유네스코 유산}}은 과학적 제자 원리를 갖춘 문자이다.", "explain": "1443년 창제, 1446년 반포 · 《훈민정음 해례본》은 유네스코 세계기록유산"},
            {"id": "kh_5", "term": "경국대전", "answer": "경국대전", "role": "core_concept", "prompt": "조선 세조 때 편찬을 시작하여 성종 때 완성·반포함으로써 조선 왕조의 유교적 법치 통치 체제를 확립한 최고 기본 법전은?", "sentence": "조선 성종 때 완성된 {{c1::경국대전::이·호·예·병·형·공 6전}}은 조선 사회의 기본 통치 규범이 되었다.", "explain": "세조 착수 → 성종 완성(1485 반포) · 이전·호전·예전·병전·형전·공전의 6전 체제"},
            {"id": "kh_6", "term": "직지심체요절", "answer": "직지심체요절", "role": "core_concept", "prompt": "고려 우왕 3년(1377) 청주 흥덕사에서 간행된 현존 세계 최고(最古)의 금속활자본은?", "sentence": "1377년 청주 흥덕사에서 인쇄된 {{c1::직지심체요절::세계 최고 금속활자본}}은 유네스코 세계기록유산이다.", "explain": "독일 구텐베르크 성서보다 78년 앞선 세계에서 가장 오래된 금속활자 인쇄본"},
            {"id": "kh_7", "term": "대동법", "answer": "대동법", "role": "core_concept", "prompt": "조선 후기 광해군 때 경기도에서 처음 시행되어 방납의 폐단을 시정하고 집집마다 특산물 대신 토지 결수에 따라 쌀·베·동전으로 납부하게 한 수취 체제 개혁 법령은?", "sentence": "조선 후기 {{c1::대동법::토지 결수 기준 쌀·포·전 납부}}의 시행으로 공인(貢人)이 등장하고 상품 화폐 경제가 발달하였다.", "explain": "가호(집) 기준 특산물 공납 → 토지(결) 기준 쌀(1결당 12두)·면포·동전 납부 (농민 부담 경감, 공인 등장)"},
            {"id": "kh_8", "term": "3·1 운동과 대한민국 임시정부", "answer": "대한민국 임시정부", "role": "core_concept", "prompt": "1919년 3·1 운동을 계기로 상하이에서 수립되어 민주공화제와 삼권분립을 최초로 채택한 독립운동 중추 기관은?", "sentence": "1919년 3·1 운동 직후 상하이에서 수립된 {{c1::대한민국 임시정부::민주공화제·삼권분립}}는 연통제와 교통국을 운영하였다.", "explain": "1919년 4월 상하이 수립 · 초대 대통령 이승만, 국무총리 이동휘 · 대한민국 헌법 전문이 계승을 명시"},
        ],
    },
    # =========================================================================
    # 8. 과학과: 교육부 중·고등 과학 4대 영역(물리·화학·생명·지구과학) 필수 개념·원소·법칙
    # =========================================================================
    {
        "collection_id": "sci-element-formula:core",
        "grade_band": "중·고등 과학",
        "subject": "science",
        "level_label": "교육부 과학과 필수 주기율표 원소·물리법칙·생명과학·지구과학 핵심",
        "unlocked": True,
        "items": [
            {"id": "sc_1", "term": "공유 결합", "answer": "공유 결합", "role": "core_concept", "prompt": "비금속 원자들이 서로 전자쌍을 내놓아 공동으로 소유하면서 옥텟 규칙을 만족하여 형성하는 화학 결합은?", "sentence": "물(H₂O)과 이산화 탄소(CO₂)는 비금속 원자들이 전자쌍을 공유하는 {{c1::공유 결합::비금속+비금속}} 물질이다.", "explain": "공유 결합(비금속+비금속, 예: H₂O, CO₂, NH₃) ↔ 이온 결합(금속 양이온+비금속 음이온, 예: NaCl)"},
            {"id": "sc_2", "term": "이온 결합", "answer": "이온 결합", "role": "core_concept", "prompt": "전자를 잃기 쉬운 금속 양이온과 전자를 얻기 쉬운 비금속 음이온 사이의 정전기적 인력으로 형성되는 화학 결합은?", "sentence": "염화 나트륨(NaCl)은 나트륨 양이온(Na⁺)과 염화 이온(Cl⁻) 사이의 {{c1::이온 결합::금속+비금속 정전기적 인력}}으로 이루어진다.", "explain": "이온 결합 물질은 고체 상태에서는 전기가 통하지 않지만 수용액이나 액체(용융) 상태에서는 이온이 이동해 전기 전도성이 있음"},
            {"id": "sc_3", "term": "미토콘드리아", "answer": "미토콘드리아", "role": "core_concept", "prompt": "세포 호흡을 통해 포도당 등 유기물을 분해하여 생명 활동에 필요한 에너지(ATP)를 생산하는 세포 소기관은?", "sentence": "{{c1::미토콘드리아::세포 호흡·ATP 합성}}는 산소를 이용해 영양소를 분해하고 생명 활동에 필요한 ATP를 합성한다.", "explain": "미토콘드리아(세포 호흡·이화 작용·동물/식물 모두 존재) ↔ 엽록체(광합성·동화 작용·식물 세포에만 존재)"},
            {"id": "sc_4", "term": "옴의 법칙", "answer": "V = I × R", "role": "core_concept", "prompt": "전기 회로에서 도체에 흐르는 전류(I)의 세기는 전압(V)에 비례하고 저항(R)에 반비례한다는 '옴의 법칙' 관계식은?", "sentence": "옴의 법칙에 따르면 전압·전류·저항의 관계식은 {{c1::V = I × R::전압 = 전류 × 저항}}이다.", "explain": "I = V / R, V = I × R, R = V / I (단위: 전압 V[볼트], 전류 A[암페어], 저항 Ω[옴])"},
            {"id": "sc_5", "term": "뉴턴 운동 제2법칙 (가속도 법칙)", "answer": "F = m × a", "role": "core_concept", "prompt": "물체의 가속도(a)는 작용한 알짜힘(F)에 비례하고 질량(m)에 반비례한다는 뉴턴 운동 제2법칙의 공식은?", "sentence": "뉴턴의 가속도 법칙은 알짜힘 F와 질량 m, 가속도 a의 관계를 {{c1::F = m × a::가속도 법칙}}로 나타낸다.", "explain": "제1법칙: 관성 법칙(알짜힘=0일 때 등속직선/정지) · 제2법칙: 가속도 법칙(F=ma) · 제3법칙: 작용·반작용 법칙"},
            {"id": "sc_6", "term": "판구조론 (수렴형·발산형·보존형 경계)", "answer": "발산형 경계 (해령·열곡대)", "role": "core_concept", "prompt": "맨틀 대류의 상승부에서 새로운 해양 지각이 생성되며 두 판이 서로 멀어지고 천발 지진과 화산 활동이 일어나는 판의 경계는?", "sentence": "대서양 중앙 해령과 동아프리카 열곡대는 맨틀 대류 상승부인 {{c1::발산형 경계::판이 멀어지는 경계}}에 해당한다.", "explain": "발산형(해령·열곡대: 천발지진+화산) / 수렴형(해구·습곡산맥: 천발~심발지진) / 보존형(변환단층: 천발지진만, 화산 없음)"},
        ],
    },
    # =========================================================================
    # 9. 수학과: 교육부 중·고등 수학 필수 공식 (대수·기하·삼각비·해석)
    # =========================================================================
    {
        "collection_id": "moe-math:core-formulas",
        "grade_band": "중·고등 수학",
        "subject": "math",
        "level_label": "교육부 수학과 학년별 필수 공식 (방정식·피타고라스·삼각비·수열·미적분)",
        "unlocked": True,
        "items": [
            {"id": "math_01", "term": "피타고라스 정리", "answer": "a² + b² = c²", "role": "core_concept", "prompt": "직각삼각형에서 직각을 낀 두 변의 길이를 a, b라 하고 빗변의 길이를 c라 할 때 성립하는 피타고라스 정리 관계식은?", "sentence": "직각삼각형에서 두 직각변의 제곱의 합은 빗변의 제곱과 같다는 공식은 {{c1::a² + b² = c²::피타고라스 정리}}이다.", "explain": "대표적인 피타고라스 수: (3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25)"},
            {"id": "math_02", "term": "이차방정식의 근의 공식", "answer": "x = (-b ± √(b² - 4ac)) / 2a", "role": "core_concept", "prompt": "이차방정식 ax² + bx + c = 0 (a ≠ 0)의 해를 구하는 근의 공식은?", "sentence": "이차방정식 ax² + bx + c = 0의 해는 {{c1::x = (-b ± √(b² - 4ac)) / 2a::근의 공식}}이며 판별식은 D = b² - 4ac이다.", "explain": "판별식 D = b² - 4ac > 0(서로 다른 두 실근), D = 0(중근), D < 0(서로 다른 두 허근)"},
            {"id": "math_03", "term": "이차방정식 근과 계수의 관계", "answer": "α + β = -b/a, αβ = c/a", "role": "core_concept", "prompt": "이차방정식 ax² + bx + c = 0 (a ≠ 0)의 두 근을 α, β라 할 때 두 근의 합(α + β)과 곱(αβ)은?", "sentence": "이차방정식 ax² + bx + c = 0의 두 근의 합과 곱은 {{c1::α + β = -b/a, αβ = c/a::근과 계수의 관계}}이다.", "explain": "a(x - α)(x - β) = ax² - a(α + β)x + aαβ = ax² + bx + c 항등식 비교로 유도"},
            {"id": "math_04", "term": "삼각함수 제곱 관계", "answer": "sin²θ + cos²θ = 1", "role": "core_concept", "prompt": "임의의 각 θ에 대하여 단위원(반지름 1) 위에서 항상 성립하는 사인(sin θ)과 코사인(cos θ)의 제곱의 합 공식은?", "sentence": "삼각함수 사이의 기본 항등식에 의해 모든 각 θ에서 {{c1::sin²θ + cos²θ = 1::삼각함수 제곱 공식}}이 성립한다.", "explain": "tan θ = sin θ / cos θ 이며, 양변을 cos²θ로 나누면 1 + tan²θ = sec²θ"},
            {"id": "math_05", "term": "원의 방정식 표준형", "answer": "(x - a)² + (y - b)² = r²", "role": "core_concept", "prompt": "좌표평면 위에서 중심의 좌표가 (a, b)이고 반지름의 길이가 r인 원의 방정식 표준형은?", "sentence": "중심이 (a, b)이고 반지름이 r인 원의 방정식은 {{c1::(x - a)² + (y - b)² = r²::원의 방정식}}이다.", "explain": "중심이 원점 (0, 0)인 원의 방정식: x² + y² = r²"},
        ],
    },
]


def list_moe_curriculum_collections() -> List[Dict[str, Any]]:
    """Return metadata for all official MOE grade-level collections."""
    return [
        {
            "collection_id": col["collection_id"],
            "grade_band": col["grade_band"],
            "subject": col["subject"],
            "level_label": col["level_label"],
            "item_count": len(col["items"]),
            "unlocked": bool(col.get("unlocked", True)),
        }
        for col in MOE_CURRICULUM_COLLECTIONS
    ]


def get_moe_collection_by_id(collection_id: str) -> Dict[str, Any] | None:
    """Lookup a specific MOE collection by its `collection_id`."""
    cid = str(collection_id or "").strip()
    for col in MOE_CURRICULUM_COLLECTIONS:
        if col["collection_id"] == cid:
            return col
    return None


def build_tier_r_moe_collections() -> Dict[str, Tuple[str, List[Tuple[str, str, str, str, Dict[str, Any]]]]]:
    """Convert MOE collections into Tier R `balanced_collections` format `(level_label, [(entry_key, entry_type, headword, gloss_ko, facet_dict)])`."""
    result: Dict[str, Tuple[str, List[Tuple[str, str, str, str, Dict[str, Any]]]]] = {}
    for col in MOE_CURRICULUM_COLLECTIONS:
        col_id = str(col["collection_id"])
        if col_id in ("moe-eng:elementary", "khist:essential", "sci-element-formula:core", "moe-hanja-1800:middle"):
            # Handled by existing starter entries + extensions
            continue
        level_label = str(col["level_label"])
        subj = str(col["subject"])
        entries: List[Tuple[str, str, str, str, Dict[str, Any]]] = []
        for it in col["items"]:
            item_id = str(it["id"])
            term = str(it["term"])
            ans = str(it["answer"])
            role = str(it.get("role") or "core_vocab")
            prompt = str(it.get("prompt") or "")
            sent = str(it.get("sentence") or "")
            exp = str(it.get("explain") or "")
            if subj == "english":
                etype = "word" if role == "core_vocab" else "fact_item"
                clean_front = f"📐 [{col['grade_band']} 핵심문법] {prompt}" if role == "key_grammar" else f"📘 [{col['grade_band']} 필수 영단어] 다음 단어의 뜻은?\n{term}"
                lv1_front = clean_front
                lv1_back = f"{ans}\n\n💡 해설: {exp}" if exp else ans
                lv2_front = f"📘 [Lv.2 문맥 빈칸] {sent}" if sent else clean_front
                lv2_back = f"{term} — {ans}" + (f"\n\n💡 해설: {exp}" if exp else "")
                lv3_front = (
                    f"🔥 [Lv.3 영문법 서술] '{term}'의 핵심 형태·규칙을 쓰시오.\n({prompt})"
                    if role == "key_grammar"
                    else f"🔥 [Lv.3 영단어 철자 인출] 뜻이 '{ans}'에 해당하는 영어 단어를 쓰시오."
                )
                lv3_back = f"{ans}\n\n💡 해설: {exp}" if role == "key_grammar" else f"{term} ({ans})"
            elif subj == "hanja":
                etype = "idiom" if len(term) >= 4 else "hanja_char"
                clean_front = f"📜 [{col['grade_band']} 사자성어] {prompt}\n{term}" if prompt else f"漢字 [{col['grade_band']}] 한자 '{term}'의 훈음(뜻과 소리)은?"
                lv1_front = clean_front
                lv1_back = f"{ans}\n\n💡 해설: {exp}" if exp else ans
                lv2_front = f"📘 [Lv.2 한문 빈칸] {sent}" if sent else clean_front
                lv2_back = f"{term}: {ans}\n\n💡 해설: {exp}"
                lv3_front = f"🔥 [Lv.3 한자·성어 인출] '{ans}'에 해당하는 한자(또는 성어)는?"
                lv3_back = f"{term} ({ans})"
            elif subj == "math":
                etype = "formula"
                clean_front = f"📐 [{col['grade_band']} 수학 공식] {prompt}"
                lv1_front = clean_front
                lv1_back = f"{ans}\n\n💡 해설: {exp}" if exp else ans
                lv2_front = f"📘 [Lv.2 수학 공식 빈칸] {sent}" if sent else clean_front
                lv2_back = f"{ans}\n\n💡 해설: {exp}"
                lv3_front = f"🔥 [Lv.3 수학 공식 유도·인출] '{term}'의 정확한 수식을 쓰시오.\n({prompt})"
                lv3_back = f"{ans}\n\n💡 해설: {exp}"
            else:
                etype = "fact_item"
                clean_front = f"🇰🇷 [{col['grade_band']} 국어 핵심] {prompt}"
                lv1_front = clean_front
                lv1_back = f"{ans}\n\n💡 해설: {exp}" if exp else ans
                lv2_front = f"📘 [Lv.2 국어 빈칸] {sent}" if sent else clean_front
                lv2_back = f"{ans}\n\n💡 해설: {exp}"
                lv3_front = f"🔥 [Lv.3 국어 심화 인출] {prompt}"
                lv3_back = f"{ans}\n\n💡 해설: {exp}"

            facet = {
                "senses": [{"id": "s1", "gloss_ko": ans}],
                "clean_front": clean_front,
                "lv1_front": lv1_front,
                "lv1_back": lv1_back,
                "lv2_front": lv2_front,
                "lv2_back": lv2_back,
                "lv3_front": lv3_front,
                "lv3_back": lv3_back,
                "target_answer": ans,
                "extra_explanation": exp,
            }
            entries.append((f"moe:{item_id}", etype, clean_front, f"{ans}\n\n💡 해설: {exp}" if exp else ans, facet))
        result[col_id] = (level_label, entries)
    return result

