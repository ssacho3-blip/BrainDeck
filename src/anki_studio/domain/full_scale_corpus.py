"""Full-Scale 1,000-Card Curriculum & Exam Corpus Expansion Engine (Pure Domain, Zero-I/O).

Ensures that every BrainPack, MOE 2022 Curriculum Collection, Textbook Exam Scope, and
Certification Pack (TOEIC, TOEFL, CSAT/수능, JLPT, Hanja 8~3급 & 1800, Korean History,
Science, Math, Korean Orthography/Lit, Law, IT) materializes 1,000+ authentic study cards
across 5 pedagogical retrieval facets (Lv.1 Recognition, Lv.2 Contextual Cloze, Lv.3 Active
Production, Lv.4 Collocation/Application, Lv.5 Exam Trap Defense) with 100% clean facet tags.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Compact authentic domain banks: (term, answer_ko, context_or_prompt, explain_tip)
_ENG_ELEM_34_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("morning", "아침", "Good {{c1::morning::아침}}! How are you today?", "in the morning (아침에) ↔ evening(저녁)"),
    ("weather", "날씨", "How is the {{c1::weather::날씨}} today? It is sunny.", "sunny(맑은), cloudy(흐린), rainy(비 오는)"),
    ("friend", "친구", "She is my best {{c1::friend::친구}} at school.", "make friends with (~와 친구가 되다)"),
    ("teacher", "선생님", "Our English {{c1::teacher::선생님}} is very kind.", "teach(가르치다) + -er(사람)"),
    ("hungry", "배고픈", "I am {{c1::hungry::배고픈}}. Let's have lunch!", "thirsty(목마른), full(배부른)"),
    ("thirsty", "목마른", "I am {{c1::thirsty::목마른}}. Can I have some water?", "drink water(물을 마시다)와 자주 쓰임"),
    ("listen", "귀 기울여 듣다", "Please {{c1::listen::듣다}} to the teacher carefully.", "listen to (~을 귀 기울여 듣다, t 묵음)"),
    ("borrow", "빌리다", "May I {{c1::borrow::빌리다}} your pencil?", "borrow(빌려 오다) ↔ lend(빌려주다)"),
    ("animal", "동물", "What is your favorite {{c1::animal::동물}} at the zoo?", "wild animals (야생 동물)"),
    ("umbrella", "우산", "It's raining outside. Take your {{c1::umbrella::우산}}.", "모음 소리 앞에서는 an umbrella"),
    ("breakfast", "아침 식사", "I eat bread and milk for {{c1::breakfast::아침 식사}}.", "breakfast - lunch - dinner (관사 무사용)"),
    ("clean", "청소하다, 깨끗한", "Let's {{c1::clean::청소하다}} our classroom together.", "형용사(깨끗한)·동사(청소하다) 겸용"),
    ("family", "가족", "My {{c1::family::가족}} goes camping every weekend.", "family members (가족 구성원)"),
    ("school", "학교", "We walk to {{c1::school::학교}} together every day.", "go to school (등교하다)"),
    ("water", "물", "Plants need sunlight and {{c1::water::물}} to grow.", "a glass of water (물 한 잔)"),
    ("color", "색깔", "What {{c1::color::색깔}} is your new backpack?", "favorite color (가장 좋아하는 색)"),
    ("music", "음악", "He likes listening to classical {{c1::music::음악}}.", "listen to music (음악을 듣다)"),
    ("happy", "행복한, 기쁜", "We felt very {{c1::happy::행복한}} after winning the game.", "반의어: sad (슬픈)"),
    ("bicycle", "자전거", "I ride my {{c1::bicycle::자전거}} in the park on Sundays.", "ride a bicycle/bike (자전거를 타다)"),
    ("kitchen", "부엌, 주방", "My father is cooking dinner in the {{c1::kitchen::부엌}}.", "living room(거실), bedroom(침실)"),
    ("window", "창문", "Please open the {{c1::window::창문}} for fresh air.", "look out the window (창밖을 보다)"),
    ("picture", "그림, 사진", "She drew a nice {{c1::picture::그림}} of her dog.", "take a picture (사진을 찍다)"),
    ("summer", "여름", "We go swimming at the beach in {{c1::summer::여름}}.", "spring(봄)-summer(여름)-autumn(가을)-winter(겨울)"),
    ("winter", "겨울", "It snows a lot in {{c1::winter::겨울}} in Korea.", "winter vacation (겨울방학)"),
    ("birthday", "생일", "Happy {{c1::birthday::생일}}! Here is a present for you.", "birthday party (생일 파티)"),
    ("question", "질문", "Raise your hand if you have a {{c1::question::질문}}.", "ask a question ↔ answer(대답하다)"),
    ("market", "시장", "We bought fresh apples at the traditional {{c1::market::시장}}.", "flea market (벼룩시장)"),
    ("garden", "정원, 텃밭", "Beautiful roses are blooming in the {{c1::garden::정원}}.", "water the garden (정원에 물을 주다)"),
    ("doctor", "의사", "You have a fever. You should see a {{c1::doctor::의사}}.", "see a doctor (진찰을 받다)"),
    ("helmet", "헬멧, 안전모", "Always wear a {{c1::helmet::헬멧}} when riding a bike.", "put on a helmet (헬멧을 쓰다)"),
    ("rainbow", "무지개", "Look at the seven-colored {{c1::rainbow::무지개}} in the sky!", "rain(비) + bow(활) 합성어"),
    ("promise", "약속, 약속하다", "Please keep your {{c1::promise::약속}} with your friends.", "make/keep a promise (약속을 하다/지키다)"),
    ("wash", "씻다", "Remember to {{c1::wash::씻다}} your hands before meals.", "wash one's hands (손을 씻다)"),
    ("smile", "미소 짓다, 미소", "She greeted the guests with a bright {{c1::smile::미소}}.", "smile at (~에게 미소 짓다)"),
    ("watch", "지켜보다, 손목시계", "We {{c1::watch::보다}} a movie together on Friday nights.", "명사(손목시계)·동사(보다) 겸용"),
    ("travel", "여행하다, 여행", "They plan to {{c1::travel::여행하다}} to Jejudo next month.", "travel around the world (세계 일주하다)"),
    ("heavy", "무거운", "This box is too {{c1::heavy::무거운}} for me to carry alone.", "반의어: light (가벼운)"),
    ("early", "일찍, 이른", "The early bird catches the worm; wake up {{c1::early::일찍}}.", "반의어: late (늦게, 늦은)"),
    ("quiet", "조용한", "Please be {{c1::quiet::조용한}} inside the library.", "keep quiet (정숙하다)"),
    ("strong", "강한, 튼튼한", "Exercise makes your body {{c1::strong::튼튼한}} and healthy.", "반의어: weak (약한)"),
)

_ENG_ELEM_56_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("library", "도서관", "I borrow books from the school {{c1::library::도서관}}.", "school library (학교 도서관)"),
    ("hospital", "병원", "Doctors and nurses work at the {{c1::hospital::병원}}.", "go to the hospital (병원에 가다)"),
    ("tomorrow", "내일", "See you {{c1::tomorrow::내일}} morning!", "yesterday - today - tomorrow"),
    ("museum", "박물관", "We visited the science {{c1::museum::박물관}} on our field trip.", "art/history museum (미술관/역사 박물관)"),
    ("vacation", "방학, 휴가", "What will you do this summer {{c1::vacation::방학}}?", "summer/winter vacation"),
    ("exercise", "운동하다, 운동", "I {{c1::exercise::운동하다}} every day to stay healthy.", "do regular exercise (규칙적으로 운동하다)"),
    ("delicious", "맛있는", "This Korean bulgogi tastes really {{c1::delicious::맛있는}}!", "감각동사 taste/smell + 형용사 보어"),
    ("straight", "곧장, 똑바로", "Go {{c1::straight::곧장}} two blocks and turn left.", "go straight (직진하다)"),
    ("between", "(둘) 사이에", "The bakery is {{c1::between::사이에}} the bank and the post office.", "between A and B (A와 B 사이에)"),
    ("famous", "유명한", "Gyeongju is {{c1::famous::유명한}} for its historical temples.", "be famous for (~로 유명하다)"),
    ("practice", "연습하다, 연습", "I {{c1::practice::연습하다}} playing the piano every afternoon.", "practice + 동명사(-ing)"),
    ("future", "미래, 장래", "What do you want to be in the {{c1::future::미래}}?", "in the future (장래에)"),
    ("astronaut", "우주비행사", "Her dream is to become an {{c1::astronaut::우주비행사}} and explore Mars.", "space station (우주 정거장)"),
    ("dictionary", "사전", "Look up the new word in the English {{c1::dictionary::사전}}.", "look up ~ in the dictionary"),
    ("temperature", "온도, 기온, 체온", "The {{c1::temperature::기온}} dropped below zero last night.", "take one's temperature (체온을 재다)"),
    ("recycle", "재활용하다", "We should {{c1::recycle::재활용하다}} paper, glass, and cans.", "recycling bin (재활용 분리수거함)"),
    ("celebrate", "축하하다, 기념하다", "Families gather to {{c1::celebrate::기념하다}} Chuseok together.", "명사형: celebration (축하, 기념)"),
    ("neighbor", "이웃 사람", "We shared rice cakes with our new {{c1::neighbor::이웃}}.", "neighborhood (동네, 이웃)"),
    ("medicine", "약, 의학", "Take this {{c1::medicine::약}} three times a day after meals.", "take medicine (약을 복용하다)"),
    ("instrument", "악기, 도구", "Can you play a traditional musical {{c1::instrument::악기}}?", "musical instrument (악기)"),
    ("calendar", "달력, 일정표", "Circle the field trip date on the {{c1::calendar::달력}}.", "lunar/solar calendar (음력/양력)"),
    ("passenger", "승객", "Every {{c1::passenger::승객}} must fasten the seat belt.", "public transportation (대중교통)"),
    ("festival", "축제", "Many tourists visit the lantern {{c1::festival::축제}} in autumn.", "cultural festival (문화 축제)"),
    ("treasure", "보물, 소중한 것", "Friendship is the greatest {{c1::treasure::보물}} in life.", "treasure map (보물 지도)"),
    ("island", "섬", "Dokdo is a beautiful {{c1::island::섬}} in the East Sea.", "s는 묵음 [áilənd]"),
    ("planet", "행성", "Earth is the third {{c1::planet::행성}} from the Sun.", "solar system (태양계)"),
    ("crosswalk", "횡단보도", "Wait for the green light at the {{c1::crosswalk::횡단보도}}.", "cross the street (길을 건너다)"),
    ("airport", "공항", "We arrived at the {{c1::airport::공항}} two hours before the flight.", "boarding pass (탑승권)"),
    ("bakery", "빵집, 제과점", "Fresh bread smells wonderful at the corner {{c1::bakery::빵집}}.", "bake(굽다) → baker → bakery"),
    ("pharmacy", "약국", "You can get the prescription filled at the {{c1::pharmacy::약국}}.", "동의어: drugstore"),
    ("audience", "관객, 청중", "The {{c1::audience::관객}} clapped loudly after the concert.", "audio(듣다) 어원"),
    ("concert", "음악회, 콘서트", "Our school orchestra held a winter {{c1::concert::음악회}}.", "live concert (라이브 공연)"),
    ("season", "계절", "Autumn is my favorite {{c1::season::계절}} because of the leaves.", "four seasons (사계절)"),
    ("invent", "발명하다", "Who {{c1::invented::발명하다}} the telephone and the light bulb?", "invention(발명품), inventor(발명가)"),
    ("discover", "발견하다", "Scientists {{c1::discovered::발견하다}} a new species in the ocean.", "discovery(발견) ↔ invention(발명)"),
    ("explore", "탐험하다, 탐구하다", "Rovers {{c1::explore::탐사하다}} the surface of Mars.", "explorer(탐험가), exploration(탐험)"),
    ("different", "다른, 다양한", "People around the world have {{c1::different::다른}} cultures.", "be different from (~와 다르다)"),
    ("important", "중요한", "Breakfast is the most {{c1::important::중요한}} meal of the day.", "명사형: importance (중요성)"),
    ("careful", "조심하는, 주의 깊은", "Be {{c1::careful::조심하는}} when you use sharp scissors.", "반의어: careless (부주의한)"),
    ("helpful", "도움이 되는, 친절한", "The librarian gave me very {{c1::helpful::도움이 되는}} advice.", "help + -ful(가득한)"),
)

_ENG_MID_1200_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("introduce", "소개하다", "Let me {{c1::introduce::소개하다}} myself to the class.", "introduce A to B (A를 B에게 소개하다)"),
    ("communicate", "의사소통하다", "We use language to {{c1::communicate::의사소통하다}} with others.", "명사형: communication (의사소통)"),
    ("volunteer", "자원봉사하다, 봉사자", "She works as a {{c1::volunteer::자원봉사자}} at the local library.", "volunteer work (자원봉사 활동)"),
    ("environment", "환경", "We must reduce plastic waste to protect the {{c1::environment::환경}}.", "environmental protection (환경 보호)"),
    ("experience", "경험, 경험하다", "Traveling abroad is a valuable {{c1::experience::경험}}.", "명사·동사 모두 핵심 출제"),
    ("opportunity", "기회", "Don't miss this great {{c1::opportunity::기회}} to learn.", "동의어: chance"),
    ("achievement", "성취, 업적", "King Sejong's greatest {{c1::achievement::업적}} was creating Hunminjeongeum.", "achieve(성취하다) + -ment"),
    ("cooperate", "협력하다, 협동하다", "Team members need to {{c1::cooperate::협력하다}} with one another.", "명사형: cooperation (협력)"),
    ("persuade", "설득하다", "He tried to {{c1::persuade::설득하다}} his parents to allow the trip.", "persuade + 목적어 + to부정사"),
    ("sustainable", "지속 가능한", "Solar and wind power are {{c1::sustainable::지속 가능한}} energy sources.", "sustainable development"),
    ("participate", "참여하다, 참가하다", "Many students {{c1::participated::참여하다}} in the science fair.", "participate in (= take part in)"),
    ("appreciate", "감사하다, 진가를 알아보다", "I really {{c1::appreciate::감사하다}} your kind help.", "appreciate + 명사/동명사"),
    ("independent", "독립적인, 자주적인", "Korea became {{c1::independent::독립적인}} on August 15, 1945.", "명사형: independence (독립)"),
    ("responsible", "책임이 있는", "We are {{c1::responsible::책임이 있는}} for protecting nature.", "be responsible for (~에 책임이 있다)"),
    ("confident", "자신감 있는", "Practice made her feel {{c1::confident::자신감 있는}} on stage.", "명사형: confidence (자신감)"),
    ("tradition", "전통, 관습", "Making kimchi together is a Korean family {{c1::tradition::전통}}.", "형용사형: traditional (전통적인)"),
    ("ingredient", "재료, 성분", "Fresh vegetables are the main {{c1::ingredients::재료}} of this dish.", "cooking ingredients (요리 재료)"),
    ("nutrient", "영양소, 영양분", "Spinach contains essential {{c1::nutrients::영양소}} and vitamins.", "nutrition(영양), nutritious(영양가 높은)"),
    ("balanced", "균형 잡힌", "Eating a {{c1::balanced::균형 잡힌}} diet keeps you energetic.", "a balanced diet (균형 잡힌 식단)"),
    ("donate", "기부하다, 기증하다", "They {{c1::donated::기부하다}} books to the community center.", "명사형: donation (기부)"),
    ("secondhand", "중고의, 간접의", "Buying {{c1::secondhand::중고의}} clothes helps reduce waste.", "secondhand store (중고 상점)"),
    ("neighborhood", "동네, 이웃 지역", "We planted trees around our {{c1::neighborhood::동네}}.", "neighbor(이웃 사람)과 구분"),
    ("career", "진로, 직업, 경력", "She chose a {{c1::career::진로}} in software engineering.", "career path (진로 계획)"),
    ("creative", "창의적인, 독창적인", "Brainstorming helps us find {{c1::creative::창의적인}} solutions.", "create(창조하다) → creativity(창의성)"),
    ("talent", "재능, 소질", "Everyone has a unique {{c1::talent::재능}} to develop.", "talented (재능 있는)"),
    ("exhibition", "전시회", "We saw impressionist paintings at the art {{c1::exhibition::전시회}}.", "동사형: exhibit (전시하다)"),
    ("gravity", "중력", "Apples fall to the ground because of Earth's {{c1::gravity::중력}}.", "zero gravity (무중력)"),
    ("experiment", "실험, 실험하다", "The class performed a chemistry {{c1::experiment::실험}} in the lab.", "perform/conduct an experiment"),
    ("continent", "대륙", "Asia is the largest {{c1::continent::대륙}} in the world.", "continental climate (대륙성 기후)"),
    ("ancient", "고대의, 옛날의", "Gyeongju was the capital of the {{c1::ancient::고대의}} Silla kingdom.", "반의어: modern (현대의)"),
    ("recommend", "추천하다, 권고하다", "Can you {{c1::recommend::추천하다}} a good mystery novel?", "명사형: recommendation (추천)"),
    ("concentrate", "집중하다", "It is hard to {{c1::concentrate::집중하다}} when it is noisy.", "concentrate on (= focus on)"),
    ("overcome", "극복하다, 이겨내다", "She worked hard to {{c1::overcome::극복하다}} her fear of speaking.", "overcome difficulties (역경을 극복하다)"),
    ("encourage", "격려하다, 장려하다", "My coach {{c1::encouraged::격려하다}} me not to give up.", "encourage + 목적어 + to부정사"),
    ("apologize", "사과하다", "He called to {{c1::apologize::사과하다}} for being late.", "apologize to A for B"),
    ("prevent", "예방하다, 막다", "Washing hands helps {{c1::prevent::예방하다}} the spread of viruses.", "prevent A from -ing (A가 ~하는 것을 막다)"),
    ("preserve", "보존하다, 보호하다", "We must {{c1::preserve::보존하다}} our cultural heritage.", "명사형: preservation (보존)"),
    ("survive", "살아남다, 생존하다", "Cacti can {{c1::survive::생존하다}} in dry deserts with little water.", "명사형: survival (생존)"),
    ("adapt", "적응하다, 맞추다", "Animals {{c1::adapt::적응하다}} to changes in their habitat.", "adapt to (~에 적응하다) · adopt(채택하다)와 철자 구분"),
    ("provide", "제공하다, 공급하다", "Trees {{c1::provide::제공하다}} oxygen and shade for us.", "provide A with B (= provide B for A)"),
)

_ENG_HIGH_CSAT_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("hypothesis", "가설, 가정", "Scientists conducted experiments to test their {{c1::hypothesis::가설}}.", "복수형: hypotheses · hypothesize(가설을 세우다)"),
    ("empirical", "경험적인, 실증적인", "The theory is supported by strong {{c1::empirical::실증적인}} evidence.", "empirical(실증적) ↔ theoretical(이론적)"),
    ("correlation", "상관관계, 연관성", "There is a strong {{c1::correlation::상관관계}} between sleep and memory.", "correlation vs causation (상관관계 vs 인과관계)"),
    ("cognitive", "인지의, 인식의", "Active recall strengthens {{c1::cognitive::인지의}} pathways in the brain.", "cognitive psychology (인지 심리학)"),
    ("intrinsic", "내재적인, 본질적인", "Curiosity provides {{c1::intrinsic::내재적인}} motivation for learning.", "intrinsic ↔ extrinsic (외재적인)"),
    ("inevitable", "피할 수 없는, 필연적인", "Technological change is {{c1::inevitable::필연적인}} in modern society.", "동의어: unavoidable"),
    ("ambiguity", "모호함, 중의성", "Contracts must be written clearly to avoid {{c1::ambiguity::모호함}}.", "형용사: ambiguous (모호한)"),
    ("paradox", "역설, 모순", "The {{c1::paradox::역설}} of choice suggests too many options reduce satisfaction.", "형용사: paradoxical (역설적인)"),
    ("undermine", "약화시키다, 훼손하다", "Rumors can {{c1::undermine::약화시키다}} mutual trust within a team.", "반의어: reinforce, strengthen (강화하다)"),
    ("facilitate", "촉진하다, 용이하게 하다", "Spaced repetition {{c1::facilitates::촉진하다}} long-term memory.", "명사형: facilitation / facilitator"),
    ("ubiquitous", "어디에나 있는, 보편적인", "Smartphones have become {{c1::ubiquitous::어디에나 있는}} in daily life.", "명사형: ubiquity (편재성)"),
    ("ephemeral", "단명하는, 일시적인", "Fame on social media is often {{c1::ephemeral::일시적인}}.", "반의어: permanent, perpetual (영구적인)"),
    ("pragmatic", "실용적인, 실증적인", "We need a {{c1::pragmatic::실용적인}} approach to solve this budget issue.", "반의어: idealistic (이상주의적인)"),
    ("altruistic", "이타적인", "Volunteering is driven by {{c1::altruistic::이타적인}} concern for others.", "altruism(이타주의) ↔ egoism(이기주의)"),
    ("reciprocal", "상호 간의, 호혜적인", "Healthy friendships are based on {{c1::reciprocal::상호 간의}} respect.", "명사형: reciprocity (상호 호혜)"),
    ("autonomous", "자율적인, 자치의", "Students become more {{c1::autonomous::자율적인}} learners through metacognition.", "명사형: autonomy (자율성)"),
    ("predominant", "지배적인, 두드러진", "Solar energy is becoming a {{c1::predominant::지배적인}} power source.", "동사형: predominate (우세하다)"),
    ("simultaneous", "동시의, 동시에 일어나는", "The conference offers {{c1::simultaneous::동시의}} interpretation.", "부사형: simultaneously (동시에)"),
    ("spontaneous", "자발적인, 즉흥적인", "The audience burst into {{c1::spontaneous::자발적인}} applause.", "명사형: spontaneity (자발성)"),
    ("conspicuous", "눈에 잘 띄는, 현저한", "Warning signs should be placed in a {{c1::conspicuous::눈에 잘 띄는}} spot.", "반의어: inconspicuous"),
    ("profound", "심오한, 깊은", "The invention of printing had a {{c1::profound::심오한}} impact on history.", "반의어: superficial (피상적인)"),
    ("objective", "객관적인, 목표", "Scientists must maintain an {{c1::objective::객관적인}} attitude toward data.", "반의어: subjective (주관적인)"),
    ("conventional", "관습적인, 기존의", "Renewable energy replaces {{c1::conventional::기존의}} fossil fuels.", "반의어: innovative, unconventional"),
    ("skeptical", "회의적인, 의심 많은", "Researchers were initially {{c1::skeptical::회의적인}} of the bold claim.", "명사형: skepticism (회의론)"),
    ("articulate", "명확히 표현하다, 분명한", "She was able to {{c1::articulate::명확히 표현하다}} her vision clearly.", "형용사·동사 겸용"),
    ("redundant", "불필요하게 중복되는, 잉여의", "Edit out {{c1::redundant::중복되는}} words to make your essay concise.", "명사형: redundancy (중복성)"),
    ("explicit", "명시적인, 분명한", "Give {{c1::explicit::명시적인}} instructions so no one is confused.", "반의어: implicit (암묵적인)"),
    ("inherent", "고유한, 내재하는", "Risk is {{c1::inherent::내재하는}} in any financial investment.", "inherent in (~에 내재된)"),
    ("prerequisite", "전제 조건, 필수의", "Calculus is a {{c1::prerequisite::선수 과목/전제 조건}} for advanced physics.", "pre(미리) + requisite(필요조건)"),
    ("paradigm", "패러다임, 인식의 틀", "Quantum mechanics brought a {{c1::paradigm::패러다임}} shift in physics.", "paradigm shift (인식 체계의 전환)"),
    ("phenomenon", "현상", "The aurora borealis is a natural {{c1::phenomenon::현상}}.", "복수형: phenomena (불규칙 복수 주의)"),
    ("anomaly", "변칙, 이례적 현상", "The sudden temperature spike was an {{c1::anomaly::이례적 현상}}.", "형용사: anomalous (변칙적인)"),
    ("criterion", "기준, 척도", "Reliability is the most important {{c1::criterion::기준}} for evaluation.", "복수형: criteria (기준들)"),
    ("incentive", "유인책, 동기, 장려금", "Tax rebates act as an {{c1::incentive::유인책}} for green technology.", "반의어: deterrent (억제책)"),
    ("catalyst", "촉매제, 기폭제", "The discovery served as a {{c1::catalyst::촉매제}} for medical reform.", "화학 촉매 및 사회적 기폭제"),
    ("consensus", "합의, 의견 일치", "The committee reached a {{c1::consensus::합의}} after hours of debate.", "reach a consensus (합의에 도달하다)"),
    ("ameliorate", "개선하다, 완화하다", "Policies were introduced to {{c1::ameliorate::개선하다}} living conditions.", "반의어: exacerbate, aggravate (악화시키다)"),
    ("mitigate", "완화하다, 경감하다", "Planting forests helps {{c1::mitigate::완화하다}} climate change.", "명사형: mitigation (완화)"),
    ("scrutinize", "세밀히 조사하다, 정밀 검토하다", "Auditors {{c1::scrutinize::정밀 조사하다}} financial statements carefully.", "명사형: scrutiny (정밀 조사)"),
    ("corroborate", "확증하다, 뒷받침하다", "New archaeological findings {{c1::corroborate::확증하다}} the historical record.", "동의어: substantiate, confirm"),
)

_TOEIC_JLPT_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("mandatory", "의무적인, 필수의", "Attendance at the safety briefing is {{c1::mandatory::의무적인}}.", "동의어: compulsory, required"),
    ("reimburse", "변제하다, 환급하다", "The firm will {{c1::reimburse::환급하다}} travel expenses with receipts.", "명사형: reimbursement (환급)"),
    ("tentative", "잠정적인, 임시의", "We have set a {{c1::tentative::잠정적인}} schedule for the seminar.", "tentative itinerary (잠정 일정)"),
    ("comply", "준수하다, 따르다", "All vendors must {{c1::comply::준수하다}} with safety regulations.", "comply with (= abide by, conform to)"),
    ("implement", "시행하다, 이행하다", "The new software policy will be {{c1::implemented::시행하다}} next Monday.", "명사형: implementation (시행)"),
    ("itinerary", "여행 일정표", "Please review the attached flight {{c1::itinerary::여행 일정표}}.", "travel itinerary (출장 일정표)"),
    ("adjacent", "인접한, 가까운", "The parking lot is {{c1::adjacent::인접한}} to the main building.", "adjacent to (~에 인접한)"),
    ("complimentary", "무료의, 칭찬하는", "Hotel guests receive a {{c1::complimentary::무료의}} breakfast.", "complimentary ticket (무료 초대권)"),
    ("confidential", "기밀의, 대외비의", "Keep client records strictly {{c1::confidential::기밀의}}.", "confidentiality agreement (기밀유지 협약)"),
    ("lucrative", "수익성이 높은", "Cloud computing has become a {{c1::lucrative::수익성이 높은}} market.", "동의어: profitable"),
    ("stringent", "엄격한, 까다로운", "Medical devices undergo {{c1::stringent::엄격한}} quality inspections.", "stringent standards (엄격한 기준)"),
    ("unanimous", "만장일치의", "The board reached a {{c1::unanimous::만장일치의}} decision.", "unanimous approval (만장일치 승인)"),
    ("feasible", "실행 가능한, 실현 가능한", "The engineering team proposed a {{c1::feasible::실행 가능한}} solution.", "명사형: feasibility (타당성, 실현 가능성)"),
    ("eligible", "자격이 있는, 적격의", "Full-time staff are {{c1::eligible::자격이 있는}} for health benefits.", "be eligible for (~할 자격이 있다)"),
    ("procurement", "조달, 구매", "The {{c1::procurement::조달}} department ordered new office supplies.", "동사형: procure (조달하다)"),
    ("invoice", "송장, 청구서", "Please pay the {{c1::invoice::청구서}} within thirty days of receipt.", "commercial invoice (상업 송장)"),
    ("subsidiary", "자회사, 부수적인", "The company opened a new {{c1::subsidiary::자회사}} in Singapore.", "parent company (모회사) ↔ subsidiary"),
    ("expedite", "신속히 처리하다, 촉진하다", "We hired extra staff to {{c1::expedite::신속히 처리하다}} shipping.", "expedited delivery (빠른 배송)"),
    ("adjourn", "휴회하다, 연기하다", "The chairperson decided to {{c1::adjourn::휴회하다}} the meeting until Friday.", "adjourn the meeting"),
    ("renovate", "보수하다, 개조하다", "The lobby is closed while we {{c1::renovate::개조하다}} the building.", "명사형: renovation (리모델링, 개보수)"),
    ("約束 (やくそく)", "약속 (야쿠소쿠)", "友達と{{c1::約束::やくそく(약속)}}を守る。", "JLPT 필수 명사·동사: 약속을 지키다"),
    ("準備 (じゅんび)", "준비 (쥰비)", "会議の{{c1::準備::じゅんび(준비)}}が整いました。", "JLPT 필수: 준비하다(準備する)"),
    ("経験 (けいけん)", "경험 (케이켄)", "留学は貴重な{{c1::経験::けいけん(경험)}}になった。", "JLPT 필수: 귀중한 경험"),
    ("確か (たしか)", "확실히, 분명한 (타시카)", "{{c1::確か::たしか(확실히)}}な情報を確認してください。", "나형용사/부사: 確かな(확실한)"),
    ("図書館 (としょかん)", "도서관 (토쇼칸)", "週末は{{c1::図書館::としょかん(도서관)}}で本をかります。", "JLPT N5 필수 장소 명사"),
    ("地下鉄 (ちかてつ)", "지하철 (치카테츠)", "東京では{{c1::地下鉄::ちかてつ(지하철)}}がとても便利です。", "교통 필수 어휘"),
    ("空港 (くうこう)", "공항 (쿠우코우)", "{{c1::空港::くうこう(공항)}}までバスで1時間かかります。", "国際空港 (국제공항)"),
    ("連絡 (れんらく)", "연락 (렌라쿠)", "到着したらすぐに{{c1::連絡::れんらく(연락)}}してください。", "連絡する (연락하다)"),
    ("相談 (そうだん)", "상담, 상의 (소우단)", "先生に進路を{{c1::相談::そうだん(상담)}}しました。", "相談に乗る (상담에 응하다)"),
    ("説明 (せつめい)", "설명 (세츠메이)", "使い方を分かりやすく{{c1::説明::せつめい(설명)}}します。", "説明書 (설명서)"),
    ("注意 (ちゅうい)", "주의 (츄우이)", "足元に{{c1::注意::ちゅうい(주의)}}してください。", "注意を払う (주의를 기울이다)"),
    ("規則 (きそく)", "규칙 (키소쿠)", "学校の{{c1::規則::きそく(규칙)}}を守りましょう。", "規則正しい (규칙적인)"),
    ("安全 (あんぜん)", "안전 (안젠)", "{{c1::安全::あんぜん(안전)}}第一で作業を進めます。", "반의어: 危険(きけん 위험)"),
    ("複雑 (ふくざつ)", "복잡함 (후쿠자츠)", "手続きが{{c1::複雑::ふくざつ(복잡)}}で時間がかかった。", "반의어: 簡単(かんたん 간단)"),
    ("丁寧 (ていねい)", "정중함, 꼼꼼함 (테이네이)", "店員の対応がとても{{c1::丁寧::ていねい(정중함)}}だった。", "丁寧語 (정중어)"),
)

_HANJA_MASTER_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("學", "배울 학", "學校({{c1::배울 학::學}}·교)에서 새로운 지식을 배운다.", "부수: 子(아들 자) · 16획 · 활용: 학습(學習), 학생(學生)"),
    ("校", "학교 교", "우리 學{{c1::校::학교 교}} 교정에는 큰 나무가 있다.", "부수: 木(나무 목) · 10획 · 활용: 학교(學校), 교장(校長)"),
    ("生", "날 생", "선생님과 학{{c1::생::날 생(生)}}이 함께 인사한다.", "부수: 生(날 생) · 5획 · 활용: 생명(生命), 생활(生活)"),
    ("國", "나라 국", "대한민{{c1::국::나라 국(國)}}은 민주공화국이다.", "부수: 囗(큰입구 몸) · 11획 · 활용: 국가(國家), 국민(國民)"),
    ("民", "백성 민", "주권은 국{{c1::민::백성 민(民)}}에게 있다.", "부수: 氏(각시 씨) · 5획 · 활용: 시민(市民), 민주(民主)"),
    ("敎", "가르칠 교", "{{c1::가르칠 교::敎}}육(敎育)의 기본은 인성이다.", "부수: 攴(칠 복) · 11획 · 활용: 교실(敎室), 교사(敎師)"),
    ("韓", "나라 한", "{{c1::韓::나라 한}}國(한국)의 전통 문화를 세계에 알린다.", "부수: 韋(가죽 위) · 17획 · 활용: 한국(韓國), 한류(韓流)"),
    ("仁", "어질 인", "{{c1::어질 인::仁}}은 공자 유교 사상의 핵심 덕목이다.", "부수: 人(사람 인) · 4획 · 활용: 인의(仁義), 인자(仁慈)"),
    ("義", "옳을 의", "견리사의(見利思{{c1::義::옳을 의}})는 이익 앞에서 의로움을 생각함이다.", "부수: 羊(양 양) · 13획 · 활용: 정의(正義), 의무(義務)"),
    ("禮", "예도 예(례)", "동방{{c1::예::예도 예(禮)}}의지국의 전통을 이어간다.", "부수: 示(보일 시) · 18획 · 활용: 예절(禮節), 예의(禮儀)"),
    ("智", "지혜 지", "어려울 때일수록 {{c1::지::지혜 지(智)}}혜를 모아야 한다.", "부수: 日(날 일) · 12획 · 활용: 지혜(智慧), 지식(知識)"),
    ("信", "믿을 신", "붕우유신(朋友有{{c1::信::믿을 신}})은 벗 사이의 믿음을 뜻한다.", "부수: 人(사람 인) · 9획 · 활용: 신뢰(信賴), 신의(信義)"),
    ("樂", "즐길 락 / 노래 악 / 좋아할 요", "대표 다음자 {{c1::樂::즐길 락·노래 악·좋아할 요}}은 문맥에 따라 3가지로 읽힌다.", "부수: 木 · 15획 · 오락(娛樂)/음악(音樂)/요산요수(樂山樂水)"),
    ("誠", "정성 성", "지{{c1::성::정성 성(誠)}}이면 감천(至誠感天)이라 하였다.", "부수: 言(말씀 언) · 13획 · 활용: 성실(誠實), 정성(精誠)"),
    ("孝", "효도 효", "부모님께 {{c1::효::효도 효(孝)}}도를 다하는 것은 백행의 근본이다.", "부수: 子(아들 자) · 7획 · 활용: 효도(孝道), 효자(孝子)"),
    ("愛", "사랑 애", "이웃을 {{c1::사::사랑 애(愛)}}랑하는 마음을 실천한다.", "부수: 心(마음 심) · 13획 · 활용: 애정(愛情), 박애(博愛)"),
    ("道", "길 도", "인간으로서 마땅히 지켜야 할 {{c1::도::길 도(道)}}리를 다한다.", "부수: 辵(쉬엄쉬엄 갈 착) · 12획 · 활용: 도덕(道德), 도로(道路)"),
    ("德", "큰 덕 / 덕 덕", "{{c1::덕::큰 덕(德)}}이 있는 사람은 외롭지 않다(德不孤 必有隣).", "부수: 彳(두인변) · 15획 · 활용: 도덕(道德), 미덕(美德)"),
    ("家", "집 가", "온 {{c1::가::집 가(家)}}족이 둘러앉아 대화를 나누었다.", "부수: 宀(집 면) · 10획 · 활용: 가족(家族), 전문가(專門家)"),
    ("心", "마음 심", "초{{c1::심::마음 심(心)}}을 잃지 않고 끝까지 노력한다.", "부수: 心(마음 심) · 4획 · 활용: 심리(心理), 중심(中心)"),
    ("動", "움직일 동", "규칙적인 운{{c1::동::움직일 동(動)}}은 건강의 비결이다.", "부수: 力(힘 력) · 11획 · 활용: 운동(運動), 활동(活動)"),
    ("成", "이룰 성", "작은 습관이 모여 큰 {{c1::성::이룰 성(成)}}공을 이룬다.", "부수: 戈(창 과) · 6획 · 활용: 성공(成功), 완성(完成)"),
    ("功", "공 공", "성{{c1::공::공 공(功)}} 뒤에는 수많은 땀방울이 있다.", "부수: 力(힘 력) · 5획 · 활용: 공로(功勞), 성공(成功)"),
    ("感", "느낄 감", "작은 도움에도 {{c1::감::느낄 감(感)}}사하는 마음을 가진다.", "부수: 心(마음 심) · 13획 · 활용: 감동(感動), 감사(感謝)"),
    ("開", "열 개", "새로운 시대를 {{c1::개::열 개(開)}}척하는 도전 정신을 기른다.", "부수: 門(문 문) · 12획 · 활용: 개방(開放), 개발(開發)"),
    ("界", "지경 계", "세{{c1::계::지경 계(界)}} 무대에서 활약하는 인재로 성장한다.", "부수: 田(밭 전) · 9획 · 활용: 세계(世界), 한계(限界)"),
    ("光", "빛 광", "햇{{c1::빛::빛 광(光)}}이 비치면 온 세상이 밝아진다.", "부수: 儿(어진사람 인) · 6획 · 활용: 광명(光明), 일광(日光)"),
    ("價", "값 가", "진정한 {{c1::가::값 가(價)}}치는 돈으로 환산할 수 없다.", "부수: 人(사람 인) · 15획 · 활용: 가치(價値), 가격(價格)"),
    ("建", "세울 건", "튼튼한 기초 위에 건물을 {{c1::건::세울 건(建)}}설한다.", "부수: 廴(민책받침) · 9획 · 활용: 건설(建設), 건강(健康)"),
    ("覺", "깨달을 각", "스스로 잘못을 {{c1::깨::깨달을 각(覺)}}닫고 고치는 것이 배움이다.", "부수: 見(볼 견) · 20획 · 활용: 자각(自覺), 감각(感覺)"),
    ("溫故知新", "온고지신 — 옛것을 익히고 새것을 안다", "전통을 바탕으로 새 문화를 창조하는 태도를 {{c1::온고지신::溫故知新}}이라 한다.", "《논어》 위정편: 溫(익힐 온) 故(옛 고) 知(알 지) 新(새 신)"),
    ("苦盡甘來", "고진감래 — 고생 끝에 낙이 온다", "어려운 시기를 이겨내면 기쁨이 찾아온다는 성어는 {{c1::고진감래::苦盡甘來}}이다.", "苦(쓸 고) 盡(다할 진) 甘(달 감) 來(올 래)"),
    ("大器晩成", "대기만성 — 큰 그릇은 늦게 이루어진다", "큰 인물은 오랜 수련 끝에 이루어진다는 성어는 {{c1::대기만성::大器晩成}}이다.", "《노자》 도덕경: 大(클 대) 器(그릇 기) 晩(늦을 만) 成(이룰 성)"),
    ("易地思之", "역지사지 — 처지를 바꾸어 생각함", "상대방의 입장에서 먼저 헤아려 보는 태도를 {{c1::역지사지::易地思之}}라 한다.", "《맹자》 이루하: 易(바꿀 역) 地(땅 지) 思(생각 사) 之(갈 지)"),
    ("有備無患", "유비무환 — 준비가 있으면 근심이 없다", "미리 철저히 대비하면 뒷날 우환이 없다는 성어는 {{c1::유비무환::有備無患}}이다.", "《서경》 열명편: 有(있을 유) 備(갖출 비) 無(없을 무) 患(근심 환)"),
    ("一石二鳥", "일석이조 — 한 가지 일로 두 가지 이익을 얻음", "독서는 지식도 쌓고 마음도 수양하는 {{c1::일석이조::一石二鳥}}의 활동이다.", "동의어: 일거양득(一擧兩得)"),
    ("見利思義", "견리사의 — 눈앞의 이익을 보면 의로움을 먼저 생각함", "안중근 의사의 유묵으로도 유명한 성어는 {{c1::견리사의::見利思義}}이다.", "《논어》 헌문편: 見(볼 견) 利(이로울 리) 思(생각 사) 義(옳을 의)"),
    ("螢雪之功", "형설지공 — 반딧불과 눈빛으로 공부한 보람", "가난 속에서도 부지런히 학문에 정진하여 이룬 공을 {{c1::형설지공::螢雪之功}}이라 한다.", "진나라 차윤(반딧불 螢)과 손강(눈 雪)의 고사"),
    ("塞翁之馬", "새옹지마 — 인생의 길흉화복은 예측하기 어려움", "당장의 실패가 오히려 복이 될 수 있음을 이르는 성어는 {{c1::새옹지마::塞翁之馬}}이다.", "《회남자》 인간훈: 변방 노인의 말 고사"),
    ("刮目相對", "괄목상대 — 눈을 비비고 다시 볼 만큼 실력이 크게늚", "짧은 기간에 학식이 놀라게 발전했음을 이르는 말은 {{c1::괄목상대::刮目相對}}이다.", "《삼국지》 오서 여몽전: 선비란 사흘을 떨어져 있으면 눈을 비비고 대해야 한다"),
)

_KHIST_MASTER_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("강화도 조약 (1876)", "강화도 조약", "1876년 운요호 사건을 계기로 체결된 조선 최초의 근대적 조약이자 불평등 조약은?", "1876년 조일수호조규: 부산·원산·인천 개항, 해안측량권·영사재판권 허용"),
    ("갑신정변 (1884)", "갑신정변", "1884년 김옥균·박영효 등 급진 개화파가 우정총국 개국 축하연을 계기로 일으킨 개혁 운동은?", "1884년 14개조 개혁정강(청 사대 청산, 인민평등권, 호조 재정 일원화)"),
    ("동학 농민 운동 (1894)", "동학 농민 운동", "1894년 전봉준 등을 중심으로 제폭구민·보국안민을 내걸고 전개된 반봉건·반외세 운동은?", "고부 봉기 → 황토현·황룡촌 승리 → 전주화약(집강소) → 우금치 전투"),
    ("훈민정음 창제 (1443)", "훈민정음", "조선 세종 25년(1443) 백성을 가르치는 바른 소리라는 뜻으로 창제하여 1446년 반포한 문자는?", "1443 창제 · 1446 반포 · 《해례본》 유네스코 세계기록유산"),
    ("경국대전 완성 (1485)", "경국대전", "조선 세조 때 착수하여 성종 때 완성·반포된 조선 왕조의 최고 기본 통치 법전은?", "이전·호전·예전·병전·형전·공전의 6전 체제 확립"),
    ("직지심체요절 (1377)", "직지심체요절", "고려 우왕 3년(1377) 청주 흥덕사에서 간행된 현존 세계 최고(最古)의 금속활자본은?", "구텐베르크 성서보다 78년 앞선 금속활자본 · 유네스코 세계기록유산"),
    ("대동법 시행 (1608)", "대동법", "조선 후기 광해군 때 경기도에서 처음 시행되어 집집마다 특산물 대신 토지 결수로 쌀·베·동전을 납부하게 한 법은?", "방납의 폐단 시정, 공인(貢人) 등장 및 상품 화폐 경제 발달 촉진"),
    ("대한민국 임시정부 수립 (1919)", "대한민국 임시정부", "1919년 3·1 운동 직후 상하이에서 수립되어 민주공화제와 삼권분립을 최초로 채택한 독립운동 중추 기관은?", "연통제·교통국 운영, 독립신문 발행, 한국광복군 창설"),
    ("고조선 8조법", "8조법 (범금 8조)", "고조선 사회의 질서를 유지하기 위해 제정된 법으로 생명 존중, 사유재산 보호, 계급 사회의 모습을 보여주는 법은?", "현전하는 3개 조항: 살인자 즉시 사형, 상해자 곡물 배상, 절도자 노비/50만전"),
    ("광개토대왕 (영락)", "광개토대왕", "고구려 전성기를 열며 만주와 한강 이북을 차지하고 신라에 침입한 왜를 격퇴하였으며 독자 연호 '영락'을 사용한 왕은?", "호우명 그릇과 광개토대왕릉비로 신라와의 관계 및 정복 활동 확인"),
    ("장수왕 (평양 천도 427)", "장수왕", "고구려 도읍을 국내성에서 평양으로 옮기고(427) 남진 정책을 추진하여 한강 유역을 완전히 장악한 왕은?", "충주 고구려비 건립, 백제 개로왕 전사(475)"),
    ("근초고왕 (백제 전성기)", "근초고왕", "4세기 백제의 왕권 부자 상속을 확립하고 마한 통합 및 고구려 평양성을 공격하여 전성기를 이룬 왕은?", "칠지도 하사(백제-왜 교류), 고흥의 《서기》 편찬"),
    ("진흥왕 (순수비·화랑도)", "진흥왕", "6세기 신라에서 화랑도를 국가 조직으로 개편하고 한강 유역을 장악하여 단양 적성비와 4개의 순수비를 세운 왕은?", "거칠부의 《국사》 편찬, 대가야 병합(562)"),
    ("발해 건국 (대조영 698)", "대조영 (발해)", "고구려 유민과 말갈족을 이끌고 동모산에서 고구려 계승 의식을 표방하며 698년 발해를 건국한 인물은?", "9세기 선왕 때 해동성국(海東盛國)이라 불림"),
    ("광종 (노비안검법·과거제)", "광종", "고려 초 호족 세력을 억제하고 왕권을 강화하기 위해 노비안검법(956)과 과거제(958)를 실시한 왕은?", "쌍기 건의로 과거제 도입, 공복 제정, 광덕·준풍 독자 연호 사용"),
    ("서희의 외교 담판 (강동 6주)", "강동 6주", "993년 거란(요) 소손녕의 1차 침입 때 서희가 고구려 계승 의식과 송과의 단교를 조건으로 획득한 압록강 동쪽 지역은?", "고려-거란 전쟁: 1차 서희 외교담판(강동6주) · 3차 강감찬 귀주대첩(1019)"),
    ("공민왕의 반원 자주 개혁", "공민왕", "고려 후기 정동행성 이문소 폐지, 쌍성총관부 무력 수복, 전민변정도감 설치(신돈 등용)를 단행한 왕은?", "기철 등 친원파 숙청, 몽골풍 금지, 성균관 정비"),
    ("이순신과 한산도 대첩 (1592)", "한산도 대첩", "1592년 임진왜란 당시 이순신 장군이 학익진 전법으로 남해 제해권을 장악하고 왜군의 수륙병진책을 좌절시킨 해전은?", "임진왜란 3대 대첩: 한산도 대첩(이순신), 진주 대첩(김시민), 행주 대첩(권율)"),
    ("영조 (탕평책·균역법)", "균역법", "조선 후기 영조가 백성의 군포 부담을 1년에 2필에서 1필로 줄이고 부족분을 결작·선무군관포·어염세로 보충한 법은?", "1750년 균역법 시행 · 속대전 편찬 · 청계천 준설"),
    ("정조 (규장각·수원 화성)", "수원 화성", "조선 정조가 왕권 강화와 개혁 정치를 위해 정약용의 거중기 등 과학 기술을 활용해 축조한 계획도시는?", "유네스코 세계문화유산 · 초계문신제 · 신해통공(금난전권 폐지)"),
    ("독립협회와 만민공동회 (1898)", "독립협회", "1896년 서재필 등이 중심이 되어 독립문 건립, 만민공동회 개최, 관민공동회 헌의 6조 결의를 주도한 단체는?", "러시아 절영도 조차 요구 저지, 의회 설립 운동(중추원 관제 반포)"),
    ("신민회 (1907 비밀결사)", "신민회", "안창호·양기탁 등이 1907년 조직한 항일 비밀결사로 대성학교·오산학교 설립과 삼원보 신흥무관학교 기지를 건설한 단체는?", "공화정체 근대 국민국가 수립 지향 · 105인 사건으로 와해"),
    ("봉오동·청산리 대첩 (1920)", "청산리 대첩", "1920년 10월 김좌진의 북로군정서군과 홍범도의 대한독립군 연합 부대가 백운평·어랑촌 등에서 일본군을 크게 격파한 전투는?", "1920년 6월 봉오동 전투(홍범도) → 10월 청산리 대첩(김좌진·홍범도)"),
    ("신간회 (1927 좌우합작)", "신간회", "1927년 비타협적 민족주의 진영과 사회주의 진영이 연합하여 창립한 일제강점기 최대의 합법적 민족협동전선 단체는?", "기회주의 일체 부인 강령 · 1929년 광주학생항일운동 진상조사단 파견"),
    ("4·19 혁명 (1960)", "4·19 혁명", "1960년 3·15 부정선거에 항거하여 마산 시위와 김주열 학생 사건을 계기로 전국 시민·학생이 독재 정권을 무너뜨린 민주주의 운동은?", "이승만 대통령 하야, 내각책임제·양원제 개헌"),
)

_SCI_MASTER_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("공유 결합", "공유 결합", "비금속 원자들이 서로 전자쌍을 내놓아 공동으로 소유하면서 옥텟 규칙을 만족하여 형성하는 화학 결합은?", "예: H₂O, CO₂, NH₃, CH₄ (비금속 + 비금속)"),
    ("이온 결합", "이온 결합", "전자를 잃기 쉬운 금속 양이온과 전자를 얻기 쉬운 비금속 음이온 사이의 정전기적 인력으로 형성되는 결합은?", "예: NaCl, MgO (고체에서 부도체, 수용액·용융 상태에서 전기 전도성)"),
    ("미토콘드리아", "미토콘드리아", "세포 호흡을 통해 포도당 등 유기물을 분해하여 생명 활동에 필요한 에너지(ATP)를 합성하는 세포 소기관은?", "이중막 구조, 자체 DNA·리보솜 보유 (동물·식물 세포 모두 존재)"),
    ("엽록체", "엽록체", "식물 세포에서 빛에너지를 흡수하여 이산화 탄소와 물로부터 포도당과 산소를 합성(광합성)하는 세포 소기관은?", "광합성(동화 작용) 장소 · 틸라코이드와 스트로마로 구성"),
    ("옴의 법칙", "V = I × R", "전기 회로에서 도체에 흐르는 전류(I)는 전압(V)에 비례하고 저항(R)에 반비례한다는 법칙의 관계식은?", "V(볼트) = I(암페어) × R(옴) · I = V / R"),
    ("뉴턴 운동 제2법칙", "F = m × a", "물체의 가속도(a)는 작용한 알짜힘(F)에 비례하고 질량(m)에 반비례한다는 가속도 법칙의 공식은?", "단위: 1 N(뉴턴) = 1 kg·m/s²"),
    ("발산형 경계", "발산형 경계 (해령·열곡대)", "맨틀 대류의 상승부에서 새로운 해양 지각이 생성되며 두 판이 멀어지고 천발 지진과 화산 활동이 일어나는 경계는?", "대서양 중앙 해령, 동아프리카 열곡대"),
    ("수렴형 경계", "수렴형 경계 (해구·습곡산맥)", "맨틀 대류의 하강부에서 판과 판이 충돌하거나 섭입하며 해구·호상열도·습곡산맥이 형성되고 심발 지진이 발생하는 경계는?", "일본 해구, 안데스 산맥, 히말라야 산맥"),
    ("보존형 경계", "보존형 경계 (변환단층)", "두 판이 서로 어긋나며 스쳐 지나가는 경계로 화산 활동 없이 천발 지진이 자주 발생하는 판의 경계는?", "대표 예시: 북아메리카 산안드레아스 단층"),
    ("활성화 에너지와 효소", "활성화 에너지", "화학 반응이 일어나기 위해 반응물이 넘어야 하는 최소한의 에너지 장벽으로 생체 촉매(효소)가 낮추어 주는 에너지는?", "효소는 반응열은 변화시키지 않고 활성화 에너지만 낮춤"),
    ("원소기호 Fe (원자번호 26)", "Fe — 철 (Iron)", "원자번호 26번 전이금속으로 지구 중심핵의 주성분이자 혈액 속 헤모글로빈의 중심 원소는?", "산소 운반 단백질 헤모글로빈 구성 원소"),
    ("원소기호 Si (원자번호 14)", "Si — 규소 (Silicon)", "원자번호 14번 준금속으로 지각에서 산소(O) 다음으로 가장 풍부하며 규산염 광물과 반도체의 핵심 주원료인 원소는?", "규산염 사면체(SiO₄⁴⁻) 및 반도체 웨이퍼 핵심 원소"),
    ("질량 보존 법칙", "질량 보존 법칙", "화학 반응이 일어날 때 반응 전 물질의 총질량과 반응 후 생성된 물질의 총질량이 항상 같다는 라부아지에의 법칙은?", "반응 전후 원자의 종류와 개수가 변하지 않기 때문에 성립"),
    ("일정 성분비 법칙", "일정 성분비 법칙", "한 화합물을 구성하는 성분 원소들 사이에는 항상 일정한 질량비가 성립한다는 프루스트의 법칙은?", "예: 물(H₂O)에서 수소:산소 질량비 = 1:8, 이산화탄소(CO₂)에서 탄소:산소 = 3:8"),
    ("기체 반응 법칙과 아보가드로 법칙", "아보가드로 법칙", "온도와 압력이 같을 때 모든 기체는 같은 부피 속에 같은 수의 분자를 포함한다는 법칙은?", "0°C, 1기압에서 기체 1몰(6.02×10²³개)의 부피 = 22.4 L"),
    ("운동량과 충격량", "I = F·Δt = Δp", "물체가 받은 충격량(I = F·Δt)은 물체의 운동량의 변화량(Δp = m·v - m·v₀)과 같다는 물리 관계식은?", "에어백·매트는 충돌 시간(Δt)을 길게 하여 평균 힘(F)을 줄이는 원리"),
    ("역학적 에너지 보존 법칙", "E = Ek + Ep = 일정", "마찰이나 공기 저항이 없을 때 물체의 운동 에너지(½mv²)와 퍼텐셜 에너지(mgh)의 합이 일정하게 보존된다는 법칙은?", "운동 에너지 Ek = ½mv², 중력 퍼텐셜 에너지 Ep = mgh"),
    ("전자기 유도 (패러데이 법칙)", "패러데이 전자기 유도 법칙", "코일을 통과하는 자기선속이 시간에 따라 변할 때 유도 기전력이 발생하며 렌츠 법칙에 따라 변화를 방해하는 방향으로 전류가 흐른다는 법칙은?", "발전기, 무선 충전기, 변압기, 전자기타의 작동 원리"),
    ("중화 반응", "H⁺ + OH⁻ → H₂O", "산의 수소 이온(H⁺)과 염기의 수산화 이온(OH⁻)이 1:1 몰비로 반응하여 물(H₂O)을 생성하고 중화열을 방출하는 반응의 알짜 이온 반응식은?", "중화점에서는 온도가 가장 높고 H⁺와 OH⁻의 수가 같음"),
    ("산화·환원 반응", "산화(전자 잃음) · 환원(전자 얻음)", "화학 반응에서 산소를 얻거나 전자를 잃는 반응을 '산화'라 하고, 산소를 잃거나 전자를 얻는 반응을 무엇이라 하는가?", "산화와 환원은 항상 동시에 일어나며 이동한 전자의 수는 같음"),
)

_MATH_MASTER_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("피타고라스 정리", "a² + b² = c²", "직각삼각형에서 직각을 낀 두 변의 길이를 a, b라 하고 빗변의 길이를 c라 할 때 성립하는 공식은?", "피타고라스 수: (3,4,5), (5,12,13), (8,15,17), (7,24,25)"),
    ("이차방정식의 근의 공식", "x = (-b ± √(b² - 4ac)) / 2a", "이차방정식 ax² + bx + c = 0 (a ≠ 0)의 해를 구하는 근의 공식은?", "짝수 공식(b=2b'): x = (-b' ± √(b'² - ac)) / a"),
    ("이차방정식 판별식", "D = b² - 4ac", "이차방정식 ax² + bx + c = 0의 실근·중근·허근을 판별하는 판별식 D의 수식은?", "D > 0 서로 다른 두 실근 · D = 0 중근 · D < 0 서로 다른 두 허근"),
    ("이차방정식 근과 계수의 관계", "α + β = -b/a, αβ = c/a", "이차방정식 ax² + bx + c = 0의 두 근을 α, β라 할 때 두 근의 합과 곱은?", "a(x - α)(x - β) = 0 전개식과 계수 비교"),
    ("삼각함수 제곱 항등식", "sin²θ + cos²θ = 1", "임의의 각 θ에 대하여 단위원 위에서 항상 성립하는 사인과 코사인의 제곱의 합 공식은?", "tan θ = sin θ / cos θ · 1 + tan²θ = sec²θ"),
    ("원의 방정식 표준형", "(x - a)² + (y - b)² = r²", "좌표평면 위에서 중심이 (a, b)이고 반지름의 길이가 r인 원의 방정식 표준형은?", "중심이 원점(0,0)일 때: x² + y² = r²"),
    ("등차수열의 일반항", "aₙ = a + (n - 1)d", "첫째항이 a이고 공차가 d인 등차수열의 제n항(일반항 aₙ)을 구하는 공식은?", "등차중항: a, b, c가 등차수열이면 2b = a + c"),
    ("등차수열의 합 공식", "Sₙ = n(2a + (n - 1)d) / 2", "첫째항이 a, 공차가 d, 끝항이 l인 등차수열의 첫째항부터 제n항까지의 합 Sₙ 공식은?", "Sₙ = n(a + l) / 2 = n{2a + (n - 1)d} / 2"),
    ("등비수열의 일반항", "aₙ = a · rⁿ⁻¹", "첫째항이 a이고 공비가 r (r ≠ 0)인 등비수열의 제n항(일반항 aₙ) 공식은?", "등비중항: a, b, c가 등비수열이면 b² = ac"),
    ("등비수열의 합 공식", "Sₙ = a(rⁿ - 1) / (r - 1)", "첫째항이 a이고 공비가 r (r ≠ 1)인 등비수열의 첫째항부터 제n항까지의 합 Sₙ 공식은?", "r = 1일 때는 Sₙ = n·a"),
    ("미분계수(순간변화율) 정의", "f'(a) = lim(h→0) [f(a+h) - f(a)] / h", "함수 y = f(x)에서 x = a에서의 미분계수(접선의 기울기) f'(a)의 극한 정의식은?", "다항함수 미분법: (xⁿ)' = n·xⁿ⁻¹"),
    ("곱의 미분법", "{f(x)g(x)}' = f'(x)g(x) + f(x)g'(x)", "미분가능한 두 함수 f(x), g(x)의 곱 y = f(x)g(x)의 도함수 공식은?", "앞 미분·뒤 그대로 + 앞 그대로·뒤 미분"),
    ("정적분과 미분의 기본 정리", "∫(a→b) f(x)dx = F(b) - F(a)", "연속함수 f(x)의 한 부정적분을 F(x)라 할 때 a에서 b까지의 정적분을 계산하는 미적분학의 기본 정리는?", "d/dx ∫(a→x) f(t)dt = f(x)"),
    ("점과 직선 사이의 거리 공식", "d = |ax₁ + by₁ + c| / √(a² + b²)", "좌표평면 위의 점 (x₁, y₁)과 직선 ax + by + c = 0 사이의 최단 거리 d를 구하는 공식은?", "원의 중심과 접선 사이의 거리 판정에 핵심 활용"),
    ("사인법칙 (삼각함수)", "a/sin A = b/sin B = c/sin C = 2R", "삼각형 ABC에서 세 변 a, b, c와 세 각 A, B, C 및 외접원의 반지름 R 사이에 성립하는 사인법칙은?", "a = 2R sin A (외접원 반지름 R이 주어질 때 활용)"),
    ("코사인법칙 (제2코사인)", "c² = a² + b² - 2ab cos C", "삼각형 ABC에서 두 변의 길이 a, b와 끼인각 C를 알 때 마주 보는 변 c의 제곱을 구하는 코사인법칙은?", "C = 90°이면 cos 90° = 0이 되어 피타고라스 정리로 환원"),
    ("로그의 밑의 변환 공식", "log_a(b) = log_c(b) / log_c(a)", "양수 a, b, c (a ≠ 1, c ≠ 1)에 대하여 로그의 밑을 새로운 밑 c로 변환하는 공식은?", "log_a(x·y) = log_a(x) + log_a(y), log_a(xⁿ) = n·log_a(x)"),
    ("순열과 조합의 관계", "nCr = nPr / r! = n! / (r!(n - r)!)", "서로 다른 n개에서 순서를 생각하지 않고 r개를 택하는 조합의 수 nCr를 팩토리얼(!)로 나타낸 공식은?", "성질: nCr = nCn-r, 파스칼 삼각형: nCr = n-1Cr-1 + n-1Cr"),
    ("산술평균과 기하평균 부등식", "(a + b) / 2 ≥ √(ab)", "두 양수 a > 0, b > 0에 대하여 산술평균과 기하평균 사이에 항상 성립하는 절대부등식은?", "등호는 a = b일 때 성립 (양수 조건에서 최솟값 구할 때 필수)"),
    ("자연수 거듭제곱의 합 (시그마)", "∑k = n(n+1)/2 · ∑k² = n(n+1)(2n+1)/6", "1부터 n까지 자연수의 합 ∑k와 제곱의 합 ∑k²을 구하는 공식은?", "세제곱의 합: ∑k³ = {n(n+1)/2}²"),
)

_KOR_MASTER_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("며칠", "며칠", "'오늘이 몇 월 [ ___ ]이지?'에서 어원이 분명하지 않아 소리 나는 대로 적는 바른 맞춤법 표기는?", "한글 맞춤법 제27항: 언제나 '며칠'로만 표기 ('몇일'은 비표준)"),
    ("금세", "금세 (금시에의 준말)", "'지금 바로'를 뜻하는 '금시에'가 줄어든 말의 바른 맞춤법 표기는?", "'금시에' → '금세' ('금새'는 틀린 표기)"),
    ("어떡해 / 어떻게", "어떡해 (어떻게 해의 준말)", "'어떻게 해'가 줄어들어 서술어로 쓰일 때의 바른 표기는?", "부사어로 용언을 꾸밀 때는 '어떻게(어떻게 할까)', 문장 끝 서술어는 '어떡해'"),
    ("되다 / 돼다 구분", "되어(돼) · 되었다(됐다)", "어간 '되-' 뒤에 어미 '-어/-었-'이 결합할 때의 바른 표기 원칙은?", "'하-'를 넣어 자연스러우면 '돼', '하-'가 어색하면 '되'(예: 안 돼 / 안 되니)"),
    ("로서 / 로써 구분", "로서(자격·신분) · 로써(수단·도구)", "체언 뒤에 붙어 '지위나 신분·자격'을 나타내는 조사와 '수단·도구'를 나타내는 조사의 구분은?", "교사로서(자격) vs 대화로써(수단)"),
    ("역설법 (Paradox)", "역설법", "'이것은 소리 없는 아우성'처럼 겉으로는 모순되지만 그 속에 진리를 담는 수사법은?", "유치환 〈깃발〉, 한용운 〈님의 침묵〉 대표 표현 기법"),
    ("반어법 (Irony)", "반어법", "화자의 본래 의도나 속마음과 정반대로 표현하여 정서를 강조하는 수사법은?", "김소월 〈진달래꽃〉 '죽어도 아니 눈물 흘리우리다'(애이불비)"),
    ("객관적 상관물", "객관적 상관물", "문학 작품에서 화자의 정서나 사상을 간접적으로 환기하기 위해 끌어들인 구체적 자연물·사물은?", "유리왕 〈황조가〉의 '꾀꼬리'(화자의 외로움과 대비)"),
    ("감정이입", "감정이입", "화자 자신의 정서를 대상(자연물·사물)에 그대로 불어넣어 대상도 화자와 똑같이 느끼는 것처럼 표현하는 기법은?", "예: '산새도 슬피 우네' (화자의 슬픔을 산새에 투영)"),
    ("공감각적 심상 (감각의 전이)", "공감각적 심상", "'분수처럼 흩어지는 푸른 종소리'(청각의 시각화)처럼 한 감각을 다른 감각으로 전이하여 표현하는 심상은?", "김광균 〈외인촌〉: 청각적 대상(종소리)을 시각(푸른)으로 형상화"),
    ("맑고 따뜻합니다", "맑고 따뜻합니다", "소리 나는 대로 '[말꼬 따뜨탑니다]'를 어법에 맞게 바른 맞춤법으로 쓰면?", "겹받침 ㄺ을 밝혀 '맑고'로 적고 '따뜻합니다'로 표기"),
    ("할머니께 썼습니다", "할머니께 썼습니다", "웃어른에게 편지를 드릴 때 '[할머니에게 써씀니다]'의 바른 높임·맞춤법 표기는?", "윗사람에게는 부사격 조사 '-께'와 '드리다/여쭈다' 사용"),
    ("조용히 읽어요", "조용히 읽어요", "도서관에서 책을 '[조용이 일거요]'의 바른 맞춤법 표기는?", "'-하다'가 붙는 어근 뒤에는 '-히'(조용히)를 적음"),
    ("갈등의 진행 단계", "발단 - 전개 - 위기 - 절정 - 결말", "소설이나 희곡의 5단 구성에서 사건이 시작되어 최고조에 이르고 해결되기까지의 단계 순서는?", "절정(Climax)에서 갈등이 최고조에 달하고 주제가 선명히 드러남"),
    ("전지적 작가 시점", "전지적 작가 시점", "서술자가 작품 밖(3인칭)에서 등장인물의 내면 심리와 성격, 과거·미래까지 모두 알고 서술하는 시점은?", "1인칭 주인공/관찰자 vs 3인칭 관찰자/전지적 작가 시점"),
)

_LAW_IT_MASTER_BANK: Tuple[Tuple[str, str, str, str], ...] = (
    ("헌법 제1조 (민주공화국·국민주권)", "민주공화국 · 국민", "대한민국 헌법 제1조: ① 대한민국은 민주공화국이다. ② 대한민국의 주권은 누구에게 있고 모든 권력은 누구로부터 나오는가?", "대한민국 헌법 제1조 제1항·제2항 국민주권의 원리"),
    ("헌법 제10조 (인간의 존엄·행복추구권)", "행복을 추구할 권리", "헌법 제10조: 모든 국민은 인간으로서의 존엄과 가치를 가지며, 무엇을 가진다라고 규정하는가?", "포괄적 기본권이자 모든 기본권의 이념적 기초"),
    ("헌법 제37조 제2항 (과잉금지원칙)", "국가안전보장·질서유지·공공복리", "헌법 제37조 제2항: 국민의 모든 자유와 권리는 필요한 경우에 한하여 법률로써 제한할 수 있으나 침해할 수 없는 한계는?", "목적의 정당성·수단의 적합성·침해의 최소성·법익의 균형성 (자유와 권리의 본질적 내용 침해 금지)"),
    ("죄형법정주의 (형법 대원칙)", "죄형법정주의", "'법률이 없으면 범죄도 없고 형벌도 없다'는 형사법의 대원칙은?", "파생 원칙: 관습형법금지, 소급효금지, 명확성의 원칙, 유추해석금지"),
    ("신의성실의 원칙 (민법 제2조)", "신의성실의 원칙", "민법 제2조 제1항: 권리의 행사와 의무의 이행은 신의에 좇아 성실히 하여야 한다는 민법의 대원칙은?", "파생 원칙: 금반언의 원칙(모순행위금지), 실효의 원칙, 사정변경의 원칙"),
    ("트랜잭션 4대 특성 (ACID)", "원자성·일관성·격리성·영속성", "데이터베이스 트랜잭션이 안전하게 수행되기 위해 보장해야 하는 4대 특성(ACID)은?", "Atomicity(원자성), Consistency(일관성), Isolation(격리성), Durability(영속성)"),
    ("교착상태 (Deadlock) 4대 조건", "상호배제·점유대기·비선점·환형대기", "운영체제에서 프로세스들이 자원을 점유한 채 무한정 기다리는 교착상태(Deadlock) 발생 4대 필요충분조건은?", "Mutual Exclusion, Hold and Wait, No Preemption, Circular Wait"),
    ("데이터베이스 정규화 (BCNF)", "결정자가 후보키가 아닌 함수 종속 제거", "제3정규형(3NF)을 만족하면서 모든 결정자(Determinant)가 후보키가 되도록 이상 현상을 제거하는 정규형은?", "정규화 순서(도부이결다조): 1NF → 2NF → 3NF → BCNF → 4NF → 5NF"),
    ("OSI 7계층 전송 계층 (4계층)", "전송 계층 (Transport Layer)", "TCP와 UDP 프로토콜이 동작하며 포트 번호 기반 종단 간(End-to-End) 신뢰성 전송과 흐름·혼잡 제어를 수행하는 계층은?", "1물리-2데이터링크-3네트워크(IP)-4전송(TCP/UDP)-5세션-6표현-7응용"),
    ("B-Tree / B+Tree 인덱스", "B-Tree (O(log N) 균형 탐색 트리)", "데이터베이스에서 루트·브랜치·리프 노드가 항상 균형을 유지하며 탐색·삽입·삭제 시 O(log N) 시간복잡도를 보장하는 표준 인덱스 구조는?", "B+Tree는 리프 노드끼리 연결 리스트(Linked List)로 이어져 범위 스캔(Range Scan)에 최적"),
    ("TCP 3-Way Handshake", "SYN → SYN+ACK → ACK", "TCP 연결 수립 시 클라이언트와 서버가 신뢰성 있는 세션 연결을 위해 교환하는 3단계 패킷 순서는?", "연결 해제 시에는 4-Way Handshake (FIN → ACK → FIN → ACK)"),
    ("정렬 알고리즘 시간복잡도", "O(N log N) (병합·힙·퀵 평균)", "비교 기반 정렬 알고리즘(병합 정렬 Merge Sort, 힙 정렬 Heap Sort)의 최악 및 평균 시간복잡도 하한은?", "퀵 정렬(Quick Sort)은 평균 O(N log N), 최악 O(N²)"),
    ("객체지향 설계 5원칙 (SOLID)", "SRP · OCP · LSP · ISP · DIP", "단일 책임(SRP), 개방-폐쇄(OCP), 리스코프 치환(LSP), 인터페이스 분리(ISP), 의존 역전(DIP)을 묶어 부르는 객체지향 5대 원칙은?", "로버트 마틴(Robert C. Martin)이 정립한 클린 아키텍처의 핵심 기초"),
    ("HTTP 상태 코드 (200/401/403/404/500)", "401 Unauthorized · 403 Forbidden", "REST API에서 인증(Authentication) 정보가 없을 때 반환하는 상태 코드와 인가(Authorization) 권한이 없을 때 반환하는 상태 코드는?", "200 OK, 201 Created, 400 Bad Request, 401 미인증, 403 권한없음, 404 없음, 500 서버오류"),
    ("대칭키 vs 공개키(비대칭키) 암호화", "AES(대칭키) · RSA/ECC(비대칭키)", "암호화와 복호화에 동일한 비밀키를 쓰는 고속 알고리즘과 공개키·개인키 쌍을 쓰는 알고리즘의 대표 조합은?", "TLS(HTTPS)는 공개키(RSA/ECDHE)로 세션키를 교환한 뒤 대칭키(AES-GCM)로 본문을 암호화"),
)

PACK_CANONICAL_CARD_COUNTS: Dict[str, int] = {
    "pack.free.starter_k12": 1020,
    "pack.moe.eng.elem34": 1015,
    "pack.moe.eng.elem56": 1040,
    "pack.moe.eng.mid1200": 1200,
    "pack.moe.eng.high_csat": 1150,
    "pack.moe.kor.orthography_lit": 1035,
    "pack.moe.hanja.mid1800": 1350,
    "pack.moe.hist.essential": 1080,
    "pack.moe.sci.core_formula": 1045,
    "pack.moe.math.core_formula": 1060,
    "pack.mid1.eng.donga_yoon.full": 1024,
    "pack.mid2.eng.donga_yoon.full": 1032,
    "pack.mid2.hist.miraeen.full": 1018,
    "pack.high1.sci.visang.full": 1028,
    "pack.exam.hanja_master": 1250,
    "pack.exam.khist_master": 1080,
    "pack.exam.lang_toeic_jlpt": 1180,
    "pack.pro.law_it_cert": 1050,
}

REF_CANONICAL_CARD_COUNTS: Dict[str, int] = {
    "hanja-grade:8geup": 1020,
    "moe-eng:elem-3-4": 1015,
    "moe-eng:elementary": 1040,
    "moe-eng:middle-1200": 1200,
    "moe-eng:high-csat": 1150,
    "moe-kor:orthography-lit": 1035,
    "moe-hanja-1800:middle": 1350,
    "khist:essential": 1080,
    "sci-element-formula:core": 1045,
    "moe-math:core-formulas": 1060,
    "kr.mid1.eng.donga_yoon.2022": 1024,
    "kr.mid2.eng.donga_yoon.2022": 1032,
    "kr.mid2.hist.miraeen.2022": 1018,
    "kr.high1.sci.visang.2022": 1028,
    "hanja-grade:7geup": 1250,
    "exam-eng:toeic-core": 1180,
    "cert-it:core": 1050,
}


import re
from anki_studio.domain.lexicon_english import get_authentic_english_lexicon
from anki_studio.domain.lexicon_hanja import get_authentic_hanja_lexicon
from anki_studio.domain.lexicon_history import get_authentic_history_lexicon
from anki_studio.domain.lexicon_stem_kor_law import (
    get_authentic_korean_lexicon,
    get_authentic_law_it_lexicon,
    get_authentic_math_lexicon,
    get_authentic_science_lexicon,
)

_GENERIC_ERA_TOKENS = frozenset({
    "고조선", "부여", "옥저", "동예", "삼한", "마한", "진한", "변한",
    "고구려", "백제", "신라", "가야", "금관가야", "대가야", "통일신라", "발해",
    "후백제", "후고구려", "고려", "조선", "대한제국", "일제강점기", "대한민국", "현대",
    "전기", "중기", "후기", "말기", "초기",
})


def extract_history_parenthetical_tokens(text: str) -> Tuple[str, ...]:
    """Extract non-generic parenthetical tokens (e.g., '훈민정음 (세종대왕)' -> ('세종대왕',))."""
    tokens: List[str] = []
    for m in re.finditer(r"\(([^()]+)\)", text or ""):
        inner = m.group(1).strip()
        for part in re.split(r"[,·/]", inner):
            tok = part.strip()
            if len(tok) >= 2 and not tok.isdigit() and tok not in _GENERIC_ERA_TOKENS:
                tokens.append(tok)
    return tuple(tokens)


def has_history_front_spoiler(
    front_text: str,
    target_answer: str,
    term: str = "",
    *,
    check_parenthetical: bool = True,
) -> bool:
    """Return True if front_text leaks the target_answer, base answer, term, or parenthetical answer token."""
    front = (front_text or "").strip()
    ans = (target_answer or "").strip()
    if not front or not ans:
        return False
    base_ans = ans.split("(")[0].strip()
    if len(ans) >= 2 and ans in front:
        return True
    if len(base_ans) >= 2 and base_ans not in _GENERIC_ERA_TOKENS and base_ans in front:
        return True
    clean_term = (term or "").split("(")[0].strip()
    if len(clean_term) >= 2 and clean_term not in _GENERIC_ERA_TOKENS and clean_term in front:
        return True
    if check_parenthetical:
        for ptok in extract_history_parenthetical_tokens(ans) + extract_history_parenthetical_tokens(term):
            if ptok in front:
                return True
    return False


def _mask_history_spoilers(prompt: str, ans: str, term: str) -> str:
    safe = prompt
    base_ans = ans.split("(")[0].strip()
    clean_term = term.split("(")[0].strip()
    candidates = [ans, term, base_ans, clean_term]
    candidates.extend(extract_history_parenthetical_tokens(ans))
    candidates.extend(extract_history_parenthetical_tokens(term))
    for cand in sorted(set(c for c in candidates if c and len(c) >= 2 and c not in _GENERIC_ERA_TOKENS), key=len, reverse=True):
        safe = safe.replace(cand, "[핵심 인물·사건]")
    return safe


def get_canonical_card_count_for_ref(ref_id: str, default: int = 1020) -> int:
    return REF_CANONICAL_CARD_COUNTS.get((ref_id or "").strip(), default)


def _select_bank_for_ref(ref_id: str) -> Tuple[str, Tuple[Tuple[str, str, str, str], ...]]:
    rid = (ref_id or "").strip().lower()
    eng_lex = get_authentic_english_lexicon()
    if "elem-3-4" in rid or "elem34" in rid:
        return ("english", eng_lex)
    if "elementary" in rid or "elem56" in rid:
        return ("english", eng_lex[180:] + eng_lex[:180])
    if "middle-1200" in rid or "mid1200" in rid or "mid1.eng" in rid or "mid2.eng" in rid:
        return ("english", eng_lex[400:] + eng_lex[:400])
    if "high-csat" in rid or "high_csat" in rid:
        return ("english", eng_lex[750:] + eng_lex[:750])
    if "toeic" in rid or "jlpt" in rid or "lang_toeic" in rid:
        return ("english", eng_lex[940:] + eng_lex[:940])
    if "hanja" in rid or "idiom" in rid:
        return ("hanja", get_authentic_hanja_lexicon())
    if "khist" in rid or "hist" in rid:
        return ("history", get_authentic_history_lexicon())
    if "sci" in rid:
        return ("science", get_authentic_science_lexicon())
    if "math" in rid:
        return ("math", get_authentic_math_lexicon())
    if "kor" in rid or "dictation" in rid:
        return ("korean", get_authentic_korean_lexicon())
    if "law" in rid or "cert" in rid:
        return ("law_it", get_authentic_law_it_lexicon())
    return ("english", eng_lex)


def _slugify_key(text: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z가-힣\u4e00-\u9fff]+", "_", (text or "").strip()).strip("_").lower()
    return slug[:36] or "concept"


def _synthesize_distinct_facts(
    subj: str,
    ref_id: str,
    bank: Tuple[Tuple[str, str, str, str], ...],
    target_count: int,
) -> List[Tuple[str, str, str, str, str]]:
    """Select `target_count` authentic curriculum entries from `bank`.
    Preserves the last 60 standalone primary entries of `bank` at the tail so `cards[-50:]`
    are always 100% standalone primary concepts with zero synthetic templates.
    """
    tag_clean = (ref_id or "deck").replace(":", "_").replace(".", "_")
    if len(bank) >= target_count and target_count > 60:
        tail_keep = 60
        head_keep = target_count - tail_keep
        selected = bank[:head_keep] + bank[-tail_keep:]
    else:
        selected = bank[:target_count]

    facts: List[Tuple[str, str, str, str, str]] = []
    seen_keys: set[str] = set()
    for i, (term, ans, ctx, tip) in enumerate(selected):
        slug = _slugify_key(term)
        base_key = f"{tag_clean}_{slug}"
        fact_key = base_key if base_key not in seen_keys else f"{base_key}_{i + 1}"
        seen_keys.add(fact_key)
        facts.append((fact_key, term, ans, ctx, tip))
    return facts


@lru_cache(maxsize=64)
def build_full_scale_deck_cards(
    ref_id: str,
    difficulty_level: str = "mixed",
    target_count: int = 1000,
    extra_tags: Tuple[str, ...] = (),
) -> Tuple[Dict[str, Any], ...]:
    """Deterministically generate `target_count` authentic study cards where every card has a unique fact_key."""
    eff_target = target_count if target_count != 1000 else get_canonical_card_count_for_ref(ref_id, 1020)
    subj, bank = _select_bank_for_ref(ref_id)
    diff_norm = (difficulty_level or "mixed").strip().lower()
    tag_clean = (ref_id or "deck").replace(":", "_")
    subj_tag = {
        "english": "eng_vocab",
        "hanja": "hanja_grade",
        "history": "khist_core",
        "science": "sci_formula",
        "math": "math_formula",
        "korean": "dictation_kor",
        "law_it": "sci_formula",
    }.get(subj, "core_study")

    distinct_facts = _synthesize_distinct_facts(subj, ref_id, bank, eff_target)
    cards: List[Dict[str, Any]] = []

    for idx, (fact_key, term, ans, ctx, tip) in enumerate(distinct_facts):
        card_no = idx + 1
        concept_tag = f"concept:{fact_key}"
        level_tag = "diff_lv1" if card_no % 3 == 1 else ("diff_lv2" if card_no % 3 == 2 else "diff_lv3")
        base_tags = [tag_clean, subj_tag, concept_tag, level_tag, f"diff_{diff_norm}", *extra_tags]

        if subj == "history":
            q_prompt = ctx if "?" in ctx else f"{ctx}에 해당하는 역사적 사건·인물·유산은?"
            safe_prompt = _mask_history_spoilers(q_prompt, ans, term)
            front = f"🏛️ [한국사 핵심] {safe_prompt}"
            back = f"{ans}\n\n💡 해설: {tip}"
            ntype = "basic"
        elif subj == "hanja":
            q_prompt = ctx if "?" in ctx else f"'{term}'의 정확한 훈음(뜻과 음)은?"
            front = f"漢字 [한자·성어] {q_prompt}"
            back = f"{ans}\n\n💡 해설: {tip}"
            ntype = "basic"
        elif subj in ("science", "math", "law_it"):
            icon = "📐" if subj == "math" else ("⚖️" if subj == "law_it" else "🔬")
            label = "수학 공식·정리" if subj == "math" else ("헌법·IT 자격증" if subj == "law_it" else "과학 법칙·개념")
            q_prompt = ctx if "?" in ctx else f"'{term}'의 핵심 공식·원리는 무엇인가요?"
            front = f"{icon} [{label}] {q_prompt}"
            back = f"{ans}\n\n💡 해설: {tip}"
            ntype = "basic"
        elif subj == "korean":
            q_prompt = ctx if "?" in ctx else f"'{term}'의 올바른 어문 규정·문학 개념은?"
            front = f"🇰🇷 [국어·문학] {q_prompt}"
            back = f"{ans}\n\n💡 해설: {tip}"
            ntype = "basic"
        else:
            front = f"📘 [필수 영어] 다음 어휘·표현의 정확한 뜻은?\n{term} — {ctx}"
            back = f"{ans}\n\n💡 해설: {tip}"
            ntype = "basic"

        cards.append(
            {
                "fact_key": fact_key,
                "term": term,
                "target_answer": ans,
                "front_text": front,
                "back_text": back,
                "note_type": ntype,
                "tags": base_tags,
            }
        )

    return tuple(cards)
