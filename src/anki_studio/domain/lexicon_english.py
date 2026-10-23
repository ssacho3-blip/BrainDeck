"""Authentic 1,280+ English Vocabulary & Idiom Lexicon for MOE 2022 Curriculum & Exams (Pure Domain, Zero-I/O).

Covers Elementary (3~6), Middle School (1,200 core), High School / CSAT (수능 학술 어휘), and TOEIC/Test Essential Vocabulary.
Every entry is a distinct, real English headword or phrasal expression with its accurate Korean dictionary meaning.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Tuple

# Compact format: "word:한국어 뜻|word:한국어 뜻|..."
_RAW_ELEM_WORDS = """
morning:아침|afternoon:오후|evening:저녁|night:밤|today:오늘|tomorrow:내일|yesterday:어제|weekend:주말
spring:봄|summer:여름|autumn:가을|winter:겨울|season:계절|weather:날씨|sunny:화창한, 맑은|cloudy:구름 낀, 흐린
rainy:비가 오는|snowy:눈이 오는|windy:바람이 부는|warm:따뜻한|cool:시원한, 멋진|cold:추운, 차가운|hot:더운, 뜨거운|humid:습한
rainbow:무지개|umbrella:우산|thunder:천둥|lightning:번개|storm:폭풍우|fog:안개|shower:소나기, 샤워|breeze:산들바람
family:가족|parent:부모님|father:아버지|mother:어머니|brother:형, 오빠, 남동생|sister:언니, 누나, 여동생|uncle:삼촌, 외삼촌|aunt:이모, 고모
cousin:사촌|grandparent:조부모님|grandfather:할아버지|grandmother:할머니|baby:아기|child:어린이, 자녀|adult:어른, 성인|neighbor:이웃 사람
friend:친구|classmate:반 친구|teacher:선생님|student:학생|doctor:의사|nurse:간호사|dentist:치과의사|pilot:비행기 조종사
police officer:경찰관|firefighter:소방관|scientist:과학자|astronaut:우주비행사|artist:예술가, 화가|musician:음악가|actor:배우|singer:가수
writer:작가|chef:요리사|baker:제빵사|farmer:농부|driver:운전기사|engineer:기술자, 엔지니어|reporter:기자|librarian:사서
school:학교|classroom:교실|playground:운동장|library:도서관|gym:체육관|cafeteria:구내식당, 급식실|office:사무실, 교무실|restroom:화장실
hospital:병원|pharmacy:약국|bakery:빵집, 제과점|market:시장|supermarket:슈퍼마켓|department store:백화점|bank:은행|post office:우체국
police station:경찰서|fire station:소방서|museum:박물관|art gallery:미술관|theater:극장, 영화관|cinema:영화관|stadium:경기장|park:공원
zoo:동물원|aquarium:수족관|amusement park:놀이공원|airport:공항|station:역, 정거장|harbor:항구|bridge:다리|crosswalk:횡단보도
sidewalk:보도, 인도|street:거리, 도로|corner:모퉁이|block:구역, 블록|building:건물, 빌딩|apartment:아파트|house:집, 주택|yard:마당, 뜰
garden:정원, 텃밭|kitchen:부엌, 주방|living room:거실|bedroom:침실|bathroom:욕실|basement:지하실|attic:다락방|roof:지붕
window:창문|door:문|wall:벽|floor:바닥, 층|ceiling:천장|stairs:계단|elevator:엘리베이터|mirror:거울
table:식탁, 탁자|desk:책상|chair:의자|sofa:소파|bed:침대|blanket:담요, 이불|pillow:베개|closet:옷장
clock:벽시계|watch:손목시계, 지켜보다|calendar:달력|lamp:스탠드, 등|computer:컴퓨터|keyboard:키보드, 건반|screen:화면, 스크린|telephone:전화기
camera:카메라|television:텔레비전|refrigerator:냉장고|microwave:전자레인지|stove:가스레인지, 난로|sink:싱크대, 가라앉다|washing machine:세탁기|vacuum:진공청소기
book:책|notebook:공책|diary:일기, 수첩|dictionary:사전|textbook:교과서|newspaper:신문|magazine:잡지|letter:편지, 글자
pencil:연필|eraser:지우개|ruler:자, 통치자|scissors:가위|glue:풀, 접착제|tape:테이프|crayon:크레용|paintbrush:붓
backpack:배낭, 책가방|pocket:주머니|wallet:지갑|glasses:안경|hat:모자|cap:야구모자|helmet:헬멧, 안전모|gloves:장갑
scarf:목도리, 스카프|coat:코트, 외투|jacket:재킷, 상의|shirt:셔츠|sweater:스웨터|pants:바지|skirt:치마|dress:원피스, 드레스
shoes:신발|boots:장화, 부츠|sneakers:운동화|socks:양말|uniform:교복, 제복|belt:허리띠, 벨트|ring:반지, 울리다|necklace:목걸이
breakfast:아침 식사|lunch:점심 식사|dinner:저녁 식사|snack:간식|dessert:후식, 디저트|water:물|milk:우유|juice:주스
tea:차(茶)|bread:빵|rice:쌀, 밥|noodle:국수, 면|soup:수프, 국|salad:샐러드|sandwich:샌드위치|pizza:피자
cheese:치즈|butter:버터|egg:달걀|meat:고기|beef:소고기|pork:돼지고기|chicken:닭고기, 닭|fish:물고기, 생선
vegetable:채소, 야채|carrot:당근|onion:양파|potato:감자|tomato:토마토|cucumber:오이|cabbage:양배추|garlic:마늘
pepper:고추, 후추|mushroom:버섯|corn:옥수수|bean:콩|fruit:과일|apple:사과|banana:바나나|orange:오렌지, 주황색
grape:포도|strawberry:딸기|watermelon:수박|peach:복숭아|pear:배(과일)|lemon:레몬|melon:멜론|cherry:체리
sugar:설탕|salt:소금|oil:기름, 석유|sauce:소스|honey:꿀|chocolate:초콜릿|cookie:쿠키, 과자|candy:사탕
cake:케이크|pie:파이|ice cream:아이스크림|fork:포크|spoon:숟가락|chopsticks:젓가락|knife:칼, 나이프|plate:접시
bowl:그릇, 사발|cup:컵|glass:유리잔, 유리|bottle:병|kettle:주전자|pan:프라이팬|pot:냄비|tray:쟁반
animal:동물|dog:개, 강아지|cat:고양이|bird:새|rabbit:토끼|mouse:쥐|horse:말|cow:소
pig:돼지|sheep:양|goat:염소|duck:오리|hen:암탉|rooster:수탉|lion:사자|tiger:호랑이
bear:곰, 견디다|elephant:코끼리|monkey:원숭이|giraffe:기린|zebra:얼룩말|fox:여우|wolf:늑대|deer:사슴
kangaroo:캥거루|panda:판다|koala:코알라|hippo:하마|rhino:코뿔소|camel:낙타|snake:뱀|frog:개구리
turtle:거북이|crocodile:악어|whale:고래|dolphin:돌고래|shark:상어|octopus:문어|crab:게|shrimp:새우
insect:곤충|bee:벌|butterfly:나비|ant:개미|spider:거미|beetle:딱정벌레|dragonfly:잠자리|mosquito:모기
nature:자연|tree:나무|flower:꽃|grass:풀, 잔디|leaf:나뭇잎|branch:나뭇가지|root:뿌리|seed:씨앗
forest:숲|mountain:산|hill:언덕|valley:계곡, 골짜기|river:강|lake:호수|pond:연못|waterfall:폭포
ocean:대양, 바다|sea:바다|beach:해변, 바닷가|island:섬|desert:사막|cave:동굴|rock:바위|stone:돌
sand:모래|soil:흙, 토양|sky:하늘|sun:태양, 해|moon:달|star:별|cloud:구름|planet:행성
earth:지구, 땅|space:우주, 공간|air:공기|fire:불, 화재|ice:얼음|steam:수증기, 증기|shadow:그림자|light:빛, 가벼운
body:몸, 신체|head:머리|hair:머리카락|face:얼굴|eye:눈|ear:귀|nose:코|mouth:입
tooth:치아, 이|tongue:혀|lip:입술|neck:목|shoulder:어깨|arm:팔|elbow:팔꿈치|hand:손
finger:손가락|thumb:엄지손가락|chest:가슴|stomach:위, 배|back:등, 뒤|waist:허리|leg:다리|knee:무릎
foot:발|toe:발가락|bone:뼈|skin:피부|heart:심장, 마음|brain:뇌, 두뇌|blood:피, 혈액|voice:목소리
color:색깔|white:흰색|black:검은색|red:빨간색|blue:파란색|yellow:노란색|green:초록색|purple:보라색
pink:분홍색|brown:갈색|gray:회색|silver:은색, 은|number:숫자, 번호|first:첫 번째의|second:두 번째의, 초|third:세 번째의
half:절반, 반|pair:한 쌍, 한 켤레|piece:조각|group:그룹, 모둠|team:팀|line:선, 줄|circle:원, 동그라미|square:정사각형, 광장
triangle:삼각형|shape:모양, 형태|size:크기, 치수|weight:무게, 체중|height:키, 높이|length:길이|speed:속도|distance:거리
time:시간|hour:시간(60분)|minute:분(시간)|moment:순간|week:주(7일)|month:달, 월|year:해, 년|century:세기(100년)
past:과거, 지나간|present:현재, 선물|future:미래, 장래|birthday:생일|holiday:휴일, 공휴일|vacation:방학, 휴가|festival:축제|party:파티, 일행
picnic:소풍, 피크닉|trip:여행, 소풍|travel:여행하다, 여행|tour:관광, 견학|camp:캠프, 야영하다|tent:텐트|map:지도|passport:여권
ticket:표, 티켓|luggage:수하물, 짐|passenger:승객|bicycle:자전거|bus:버스|subway:지하철|train:기차|airplane:비행기
helicopter:헬리콥터|ship:배, 선박|boat:보트, 작은 배|truck:트럭|taxi:택시|ambulance:구급차|rocket:로켓|spaceship:우주선
subject:과목, 주제|Korean:한국어, 한국인|English:영어|math:수학|science:과학|history:역사|music:음악|art:미술, 예술
physical education:체육|homework:숙제|exam:시험|test:시험, 검사|grade:학년, 성적|score:점수|question:질문, 문제|answer:대답, 정답
mistake:실수|problem:문제|example:예시, 본보기|story:이야기|fairy tale:동화|poem:시(詩)|song:노래|concert:음악회, 콘서트
instrument:악기, 도구|piano:피아노|violin:바이올린|guitar:기타|drum:드럼, 북|flute:플루트, 피리|bell:종, 방울|picture:그림, 사진
painting:회화, 그림|drawing:스케치, 그림|statue:조각상, 동상|movie:영화|cartoon:만화|puzzle:퍼즐, 수수께끼|game:게임, 경기|toy:장난감
doll:인형|ball:공|kite:연(날리기)|balloon:풍선|skateboard:스케이트보드|soccer:축구|baseball:야구|basketball:농구
volleyball:배구|tennis:테니스|badminton:배드민턴|swimming:수영|skating:스케이팅|skiing:스키|hiking:등산, 하이킹|fishing:낚시
"""

_RAW_MID_WORDS = """
happy:행복한, 기쁜|sad:슬픈|angry:화난|excited:신난, 들뜬|surprised:놀란|scared:무서워하는|afraid:두려워하는|nervous:긴장한, 불안한
worried:걱정하는|proud:자랑스러워하는|lonely:외로운|bored:지루해하는|tired:피곤한|sleepy:졸린|hungry:배고픈|thirsty:목마른
full:배부른, 가득 찬|sick:아픈|healthy:건강한|strong:강한, 튼튼한|weak:약한|tall:키가 큰, 높은|short:짧은, 키가 작은|long:긴
big:큰|small:작은|large:큰, 넓은|tiny:아주 작은|heavy:무거운|light:가벼운, 빛|fast:빠른, 빨리|slow:느린
early:일찍, 이른|late:늦은, 늦게|young:어린, 젊은|old:오래된, 나이 든|new:새로운|good:좋은, 훌륭한|bad:나쁜|great:위대한, 훌륭한
nice:좋은, 친절한|kind:친절한, 종류|friendly:다정한, 친근한|polite:예의 바른|honest:정직한|brave:용감한|smart:똑똑한, 영리한|clever:영리한, 기발한
wise:지혜로운, 현명한|foolish:어리석은|lazy:게으른|diligent:부지런한, 근면한|careful:조심하는|careless:부주의한|helpful:도움이 되는|useful:유용한
famous:유명한|popular:인기 있는|important:중요한|special:특별한|common:흔한, 공통의|strange:이상한, 낯선|different:다른, 다양한|same:같은, 동일한
similar:비슷한, 유사한|easy:쉬운|difficult:어려운|hard:단단한, 어려운, 열심히|soft:부드러운|smooth:매끄러운|rough:거친|sharp:날카로운
bright:밝은, 눈부신|dark:어두운|clean:깨끗한, 청소하다|dirty:더러운|fresh:신선한|sweet:달콤한|sour:신(맛이 나는)|bitter:쓴(맛이 나는)
salty:짠|spicy:매운|delicious:맛있는|terrible:끔찍한, 형편없는|wonderful:훌륭한, 멋진|beautiful:아름다운|pretty:예쁜|handsome:잘생긴
cute:귀여운|ugly:못생긴, 추한|rich:부유한, 풍부한|poor:가난한, 가엾은|expensive:비싼|cheap:값싼|free:자유로운, 무료의|busy:바쁜
quiet:조용한|noisy:시끄러운|loud:소리가 큰|silent:침묵하는, 조용한|safe:안전한|dangerous:위험한|lucky:운이 좋은|ready:준비가 된
sure:확신하는|true:참된, 사실인|false:거짓의, 틀린|right:오른쪽, 올바른, 권리|wrong:틀린, 잘못된|left:왼쪽|straight:곧장, 똑바른|round:둥근
deep:깊은|shallow:얕은|wide:넓은|narrow:좁은|thick:두꺼운|thin:얇은, 여윈|high:높은|low:낮은
near:가까운|far:먼|inside:안쪽에|outside:바깥쪽에|between:(둘) 사이에|among:(셋 이상) 사이에|across:가로질러, 건너편에|along:~을 따라
around:주위에, 약|through:~을 통과하여|toward:~을 향하여|against:~에 반대하여, 기대어|without:~ 없이|during:~ 동안|until:~할 때까지|since:~ 이래로, ~ 때문에
go:가다|come:오다|walk:걷다|run:달리다, 운영하다|jump:점프하다, 뛰다|swim:수영하다|fly:날다, 파리|climb:오르다, 등반하다
ride:타다|drive:운전하다|stop:멈추다, 정류장|wait:기다리다|stay:머무르다|leave:떠나다, 남기다|arrive:도착하다|return:돌아오다, 반납하다
enter:들어가다|visit:방문하다|move:움직이다, 이사하다|follow:따라가다, 따르다|lead:이끌다, 안내하다|carry:나르다, 휴대하다|bring:가져오다|take:가져가다, 시간이 걸리다
send:보내다|receive:받다|give:주다|get:얻다, 도착하다|buy:사다, 구매하다|sell:팔다, 판매하다|pay:지불하다|spend:(시간·돈을) 쓰다
save:저축하다, 구하다, 아끼다|borrow:빌리다|lend:빌려주다|keep:유지하다, 보관하다|lose:잃어버리다, 지다|find:찾다, 발견하다|search:수색하다, 검색하다|choose:선택하다
pick:고르다, 따다|make:만들다|build:짓다, 건설하다|create:창조하다, 만들다|invent:발명하다|discover:발견하다|explore:탐험하다, 탐구하다|fix:고치다, 수리하다
repair:수리하다, 보수하다|break:깨뜨리다, 고장 내다|cut:자르다, 베다|draw:그리다, 당기다|paint:칠하다, 그림을 그리다|write:쓰다, 작성하다|read:읽다|speak:말하다
talk:이야기하다|say:말하다|tell:말해주다, 구별하다|ask:질문하다, 요청하다|answer:대답하다|call:부르다, 전화하다|shout:외치다, 소리치다|whisper:속삭이다
sing:노래하다|dance:춤추다|play:놀다, 연주하다, 경기하다|listen:귀 기울여 듣다|hear:듣다, 들리다|see:보다, 알다|look:보다, ~처럼 보이다|watch:지켜보다, 관람하다
smell:냄새가 나다, 냄새를 맡다|taste:맛이 나다, 맛보다|feel:느끼다|touch:만지다, 감동시키다|think:생각하다|know:알다|understand:이해하다|remember:기억하다
forget:잊어버리다|learn:배우다|study:공부하다, 연구하다|teach:가르치다|practice:연습하다|try:시도하다, 노력하다|plan:계획하다, 계획|decide:결정하다
hope:희망하다, 바라다|wish:소망하다, 바라다|want:원하다|need:필요로 하다|like:좋아하다|love:사랑하다|hate:미워하다, 싫어하다|enjoy:즐기다
smile:미소 짓다|laugh:웃다|cry:울다, 외치다|worry:걱정하다|help:돕다, 도움|care:돌보다, 상관하다|share:공유하다, 나누다|invite:초대하다
welcome:환영하다|celebrate:축하하다, 기념하다|thank:감사하다|apologize:사과하다|forgive:용서하다|promise:약속하다, 약속|agree:동의하다|disagree:동의하지 않다
eat:먹다|drink:마시다|cook:요리하다|bake:굽다(빵·과자)|boil:끓이다, 삶다|fry:튀기다, 볶다|mix:섞다, 혼합하다|pour:붓다, 따르다
wash:씻다, 세탁하다|clean:청소하다, 깨끗한|brush:솔질하다, 붓|wear:입다, 착용하다|put on:입다, 쓰다|take off:벗다, 이륙하다|open:열다, 열려 있는|close:닫다, 가까운
lock:잠그다, 자물쇠|turn on:켜다|turn off:끄다|wake up:잠에서 깨다|get up:일어나다|sleep:자다, 수면|dream:꿈꾸다, 꿈|rest:쉬다, 휴식
exercise:운동하다, 운동|grow:자라다, 재배하다|plant:심다, 식물|water:물을 주다, 물|feed:먹이를 주다|catch:잡다, 타다|throw:던지다|hit:치다, 때리다
kick:차다|push:밀다|pull:당기다|lift:들어 올리다|drop:떨어뜨리다, 물방울|fall:떨어지다, 넘어지다, 가을|win:이기다, 우승하다|pass:통과하다, 건네주다
fail:실패하다, 낙제하다|join:가입하다, 함께하다|meet:만나다|introduce:소개하다|communicate:의사소통하다|volunteer:자원봉사하다, 봉사자|environment:환경|experience:경험, 경험하다
opportunity:기회|achievement:성취, 업적|cooperate:협력하다, 협동하다|persuade:설득하다|sustainable:지속 가능한|participate:참여하다, 참가하다|appreciate:감사하다, 진가를 알아보다|independent:독립적인, 자주적인
responsible:책임이 있는|confident:자신감 있는|tradition:전통, 관습|ingredient:재료, 성분|recommend:추천하다, 권고하다|improve:개선하다, 향상하다|protect:보호하다|prevent:예방하다, 막다
reduce:줄이다, 감소시키다|recycle:재활용하다|reuse:재사용하다|pollute:오염시키다|pollution:오염, 공해|garbage:쓰레기|waste:낭비하다, 폐기물|energy:에너지, 활력
electricity:전기, 전력|temperature:온도, 기온, 체온|climate:기후|global:세계적인, 지구의|earthquake:지진|flood:홍수, 범람하다|drought:가뭄|typhoon:태풍
damage:피해, 손상시키다|destroy:파괴하다|survive:살아남다, 생존하다|rescue:구조하다, 구출|shelter:대피소, 피난처|emergency:비상사태, 응급|accident:사고, 우연|traffic:교통, 통행량
rule:규칙, 통치하다|law:법, 법률|peace:평화|war:전쟁|history:역사|culture:문화|custom:관습, 풍습|society:사회, 모임
citizen:시민, 국민|government:정부|nation:국가, 민족|country:나라, 시골|hometown:고향|community:지역 사회, 공동체|volunteer work:자원봉사 활동|charity:자선 단체, 자비
donation:기부, 기증|donate:기부하다|support:지지하다, 후원하다|encourage:격려하다, 권장하다|respect:존경하다, 존중|trust:신뢰하다, 믿음|honesty:정직|courage:용기
wisdom:지혜|patience:인내심, 참을성|effort:노력, 수고|success:성공|failure:실패|goal:목표, 골|purpose:목적, 의도|challenge:도전, 난제
habit:습관, 버릇|routine:일과, 규칙적인 순서|schedule:일정, 시간표|appointment:약속, 예약|interview:면접, 인터뷰|career:직업, 경력|job:일자리, 직업|salary:급여, 월급
company:회사, 동석|factory:공장|business:사업, 업무|customer:고객, 손님|client:의뢰인, 고객|product:제품, 상품|item:물품, 항목|price:가격, 값
cost:비용, 값|value:가치, 소중히 여기다|quality:품질, 자질|amount:양, 총액|percent:퍼센트(%)|average:평균, 평균의|total:전체의, 합계|increase:증가하다, 늘다
decrease:감소하다, 줄다|produce:생산하다, 제작하다|provide:제공하다, 공급하다|supply:공급하다, 보급품|demand:수요, 요구하다|deliver:배달하다, 전달하다|order:주문하다, 명령, 순서|exchange:교환하다, 환전
advertise:광고하다|advertisement:광고|commercial:상업적인, 광고 방송|profit:이익, 수익|benefit:혜택, 이득|account:계좌, 설명하다|receipt:영수증|discount:할인
tax:세금|fortune:행운, 재산|treasure:보물|knowledge:지식|information:정보|fact:사실|truth:진실, 진리|opinion:의견, 견해
idea:생각, 아이디어|thought:생각, 사고|mind:마음, 꺼리다|memory:기억, 추억|imagination:상상력|imagine:상상하다|creative:창의적인|creativity:창의성
talent:재능|ability:능력|skill:기술, 숙련|method:방법, 방식|way:길, 방법|solution:해결책, 용액|solve:해결하다, 풀다|result:결과
cause:원인, 야기하다|reason:이유, 이성|effect:효과, 영향|influence:영향, 영향을 미치다|impact:충격, 영향|change:변화하다, 잔돈|develop:발전시키다, 개발하다|development:발달, 개발
progress:진보, 전진|growth:성장, 발전|advance:전진, 발전하다|technology:과학 기술|machine:기계|tool:도구, 연장|device:장치, 기기|invention:발명, 발명품
experiment:실험, 실험하다|research:연구, 조사하다|data:자료, 데이터|evidence:증거|proof:증명, 증거|prove:증명하다, 입증하다|discover:발견하다|discovery:발견
universe:우주|galaxy:은하계|solar system:태양계|orbit:궤도, 궤도를 돌다|gravity:중력|satellite:인공위성, 위성|telescope:망원경|microscope:현미경
cell:세포, 작은 방|gene:유전자|species:종(생물 분류)|mammal:포유류|reptile:파충류|habitat:서식지|ecosystem:생태계|extinct:멸종된
fossil:화석|mineral:광물, 미네랄|chemical:화학 물질, 화학의|oxygen:산소|hydrogen:수소|carbon:탄소|nitrogen:질소|metal:금속
iron:철, 다리미|gold:금|copper:구리|plastic:플라스틱|rubber:고무|cotton:면화, 솜|silk:비단, 실크|leather:가죽
wood:목재, 나무|paper:종이, 논문|cloth:천, 옷감|material:재료, 물질, 자료|surface:표면, 수면|bottom:바닥, 맨 아래|edge:가장자리, 날|center:중심, 중앙
middle:가운데, 중간의|direction:방향, 지시|north:북쪽|south:남쪽|east:동쪽|west:서쪽|region:지역, 지방|area:면적, 지역
location:위치, 장소|site:장소, 유적지, 웹사이트|position:위치, 자세, 직위|border:국경, 경계|continent:대륙|population:인구, 개체군|language:언어|dialect:방언, 사투리
foreign:외국의, 이질적인|foreigner:외국인|abroad:해외로, 외국에|native:모국어의, 토착의|local:지역의, 현지의|international:국제적인|national:국가의, 국립의|public:공공의, 대중
private:사적인, 개인의|personal:개인의, 사적인|individual:개인, 개별의|social:사회의, 사교적인|political:정치적인|economic:경제의, 경제학의|cultural:문화적인|historical:역사의, 역사적인
traditional:전통적인|modern:현대의, 근대의|ancient:고대의|medical:의학의, 의료의|medicine:약, 의학|patient:환자, 참을성 있는|symptom:증상|disease:질병, 질환
illness:병, 질환|virus:바이러스|bacteria:박테리아, 세균|fever:열, 발열|cough:기침, 기침하다|headache:두통|toothache:치통|stomachache:복통
injury:부상, 상처|wound:상처, 부상|pain:통증, 아픔|hurt:다치게 하다, 아프다|heal:치유되다, 낫다|cure:치료하다, 치료법|recover:회복하다, 되찾다|treatment:치료, 대우
surgery:수술|operation:수술, 작동, 작전|vaccine:백신|vitamin:비타민|nutrition:영양, 영양분|diet:식단, 다이어트|stress:스트레스, 강조하다|relax:긴장을 풀다, 쉬다
breathe:숨을 쉬다, 호흡하다|breath:숨, 호흡|sweat:땀, 땀을 흘리다|tear:눈물, 찢다|sight:시력, 시야, 광경|vision:시력, 비전, 통찰력|hearing:청력|sense:감각, 의미
emotion:감정, 정서|feeling:느낌, 감정|mood:기분, 분위기|attitude:태도, 자세|behavior:행동, 품행|character:성격, 등장인물, 글자|personality:성격, 개성|identity:정체성, 신원
relationship:관계|friendship:우정|marriage:결혼|wedding:결혼식|generation:세대|youth:청춘, 젊은이|childhood:어린 시절|citizen:시민
audience:관객, 청중|spectator:관중, 구경꾼|crowd:군중, 무리|guest:손님, 하객|host:주인, 진행자|stranger:낯선 사람|hero:영웅|leader:지도자, 리더
member:회원, 구성원|partner:파트너, 동반자|rival:경쟁자, 라이벌|enemy:적, 원수|expert:전문가|master:달인, 주인, 숙달하다|beginner:초보자|volunteer:자원봉사자
author:저자, 작가|poet:시인|director:감독, 이사|producer:제작자, 생산자|audience:청중|novel:소설, 새로운|fiction:소설, 허구|nonfiction:비소설, 실화
literature:문학|poetry:시(문학 장르)|drama:연극, 드라마|comedy:희극, 코미디|tragedy:비극|character:등장인물|plot:줄거리, 구성|scene:장면, 현장
stage:무대, 단계|background:배경|theme:주제, 테마|title:제목, 직함|chapter:장(책의 구분)|paragraph:단락, 문단|sentence:문장|phrase:구(句), 표현
word:단어, 말|vocabulary:어휘|grammar:문법|pronunciation:발음|meaning:의미, 뜻|definition:정의|translation:번역|translate:번역하다
express:표현하다, 급행의|expression:표현, 표정|describe:묘사하다, 설명하다|description:묘사, 설명|explain:설명하다|explanation:설명, 해설|discuss:토론하다, 논의하다|discussion:토론, 논의
debate:토론, 논쟁하다|argue:주장하다, 논쟁하다|argument:주장, 논쟁|suggest:제안하다, 시사하다|suggestion:제안, 암시|advise:조언하다, 충고하다|advice:조언, 충고|warn:경고하다
warning:경고, 주의보|notice:알아차리다, 공지문|announce:발표하다, 알리다|announcement:발표, 공고|report:보고하다, 보도, 보고서|inform:알리다, 통지하다|mention:언급하다|complain:불평하다, 항의하다
complaint:불평, 항의|praise:칭찬하다, 칭찬|criticize:비판하다, 비난하다|blame:탓하다, 비난|admire:존경하다, 감탄하다|envy:부러워하다, 질투|regret:후회하다, 유감|ignore:무시하다
refuse:거절하다, 거부하다|reject:거부하다, 기각하다|accept:받아들이다, 수락하다|admit:인정하다, 입장을 허가하다|allow:허락하다, 허용하다|permit:허가하다, 허가증|forbid:금지하다|ban:금지하다, 금지령
limit:제한하다, 한계|control:통제하다, 조절|manage:관리하다, 해내다|handle:다루다, 손잡이|deal:다루다, 거래|require:요구하다, 필요로 하다|request:요청하다, 요청|expect:기대하다, 예상하다
predict:예측하다, 예언하다|compare:비교하다|comparison:비교|contrast:대조하다, 대비|connect:연결하다|connection:연결, 관련성|separate:분리하다, 별개의|divide:나누다, 분할하다
combine:결합하다, 겸비하다|include:포함하다|contain:포함하다, 함유하다|consist:구성되다|belong:속하다|depend:의존하다, 달려 있다|rely:의지하다, 신뢰하다|affect:영향을 미치다
"""

_RAW_HIGH_CSAT_WORDS = """
abandon:버리다, 포기하다|abolish:폐지하다|abound:풍부하다, 많이 있다|abrupt:갑작스러운, 퉁명스러운|absence:부재, 결석|absolute:절대적인, 완전한|absorb:흡수하다, 열중하게 하다|abstract:추상적인, 요약
absurd:터무니없는, 부조리한|abundant:풍부한, 많은|abuse:남용하다, 학대하다|academic:학문적인, 대학의|accelerate:가속화하다, 촉진하다|accessible:접근하기 쉬운, 이용 가능한|accommodate:수용하다, 편의를 도모하다|accompany:동반하다, 수반하다
accomplish:성취하다, 완수하다|accord:일치하다, 합의|Account for:설명하다, (비율을) 차지하다|accumulate:축적하다, 모으다|accurate:정확한, 정밀한|accuse:고발하다, 비난하다|achieve:달성하다, 성취하다|acknowledge:인정하다, 감사를 표하다
acquire:습득하다, 획득하다|acquisition:습득, 인수|activate:활성화하다, 작동시키다|acute:급성의, 예리한, 심각한|adapt:적응하다, 개작하다|adaptation:적응, 각색|addict:중독자, 중독시키다|adequate:적절한, 충분한
adhere:고수하다, 달라붙다|adjacent:인접한, 가까운|adjust:조절하다, 적응하다|administer:관리하다, 집행하다, 투여하다|administration:행정, 관리, 정권|adolescent:청소년, 청소년기의|adopt:채택하다, 입양하다|adore:흠모하다, 아주 좋아하다
advent:출현, 도래|adverse:불리한, 역행하는|advocate:옹호하다, 지지자|aesthetic:미학적인, 심미적인|affection:애정, 보살핌|affiliate:제휴하다, 지부|affluent:부유한, 풍부한|afford:~할 여유가 되다, 제공하다
agenda:의제, 안건|aggravate:악화시키다, 화나게 하다|aggregate:총계, 집합체, 모으다|aggressive:공격적인, 적극적인|agile:민첩한, 기민한|agriculture:농업, 농학|ailment:질병, 가벼운 병|aisle:통로, 복도
alarm:경보, 놀라게 하다|alien:외계의, 외국인, 이질적인|align:정렬시키다, 제휴하다|allege:(증거 없이) 주장하다|alleviate:완화하다, 경감하다|alliance:동맹, 연합|allocate:할당하다, 배분하다|allude:암시하다, 넌지시 언급하다
ally:동맹국, 협력자|alter:바꾸다, 변경하다|alternate:번갈아 하다, 교대의|alternative:대안, 대체 가능한|altitude:고도, 해발|altruism:이타주의|amateur:아마추어, 비전문가|ambassador:대사, 사절
ambiguous:모호한, 애매한|ambition:야망, 포부|amend:개정하다, 수정하다|amiable:상냥한, 호감을 주는|ample:충분한, 풍부한|amplify:증폭시키다, 확대하다|analogy:유추, 비유|analyze:분석하다
ancestor:조상, 선조|anchor:닻, 앵커, 고정시키다|anecdote:일화, 비화|anguish:고뇌, 극심한 고통|animate:생기를 불어넣다, 살아 있는|anniversary:기념일|annoy:짜증 나게 하다, 괴롭히다|annual:연례의, 1년의
anonymous:익명의, 작자 미상의|antagonist:적대자, 라이벌|anticipate:예상하다, 고대하다|antique:골동품, 고풍스러운|anxiety:불안, 염려, 열망|apathy:무관심, 냉담|appall:오싹하게 하다, 경악하게 하다|apparatus:기구, 장치, 조직
apparent:분명한, 외관상의|appeal:호소하다, 매력, 항소|appease:달래다, 진정시키다|append:덧붙이다, 첨부하다|appetite:식욕, 욕구|applaud:박수갈채를 보내다, 칭찬하다|appliance:가전제품, 기구|applicable:적용 가능한, 해당되는
appoint:임명하다, 지명하다|appraise:평가하다, 감정하다|apprehend:체포하다, 이해하다, 염려하다|apprentice:견습생, 도제|approach:접근하다, 접근법|appropriate:적절한, 전용하다|approve:승인하다, 찬성하다|approximate:대략적인, 근접하다
aptitude:적성, 소질|arbitrary:임의적인, 독단적인|archaeology:고고학|architect:건축가, 설계자|archive:기록 보관소, 보관하다|ardent:열렬한, 열정적인|arduous:고된, 험난한|arena:경기장, 활동 무대
arise:발생하다, 일어나다|aristocrat:귀족|arithmetic:산수, 연산|aroma:향기, 방향|arouse:불러일으키다, 깨우다|arrange:배열하다, 준비하다|array:배열, 집합, 정렬시키다|arrest:체포하다, 저지하다
arrogant:오만한, 거만한|articulate:분명히 표현하다, 발음이 분명한|artifact:인공 유물, 공예품|artificial:인공적인, 인위적인|ascend:오르다, 승진하다|ascertain:확인하다, 규명하다|ascribe:(원인을) ~로 돌리다|aspect:측면, 양상
aspire:열망하다, 동경하다|assault:폭행, 공격하다|assemble:조립하다, 모이다|assert:단언하다, 주장하다|assess:평가하다, 사정하다|asset:자산, 강점|assign:할당하다, 배정하다|assimilate:동화되다, 흡수하다
assist:돕다, 원조하다|associate:연상하다, 동료, 제휴하다|assume:추정하다, (책임을) 맡다|assure:보장하다, 확신시키다|astonish:깜짝 놀라게 하다|astronomy:천문학|astute:기민한, 통찰력 있는|asylum:망명, 보호 시설
atmosphere:대기, 분위기|atom:원자|atrocity:잔학 행위, 흉악함|attach:부착하다, 첨부하다|attain:달성하다, 이루다|attempt:시도하다, 시도|attend:참석하다, 주의를 기울이다|attorney:변호사, 대리인
attract:끌어당기다, 매혹하다|attribute:~의 탓으로 돌리다, 속성|auction:경매|audacious:대담한, 무모한|audible:들리는, 가청의|audit:회계 감사, 감사하다|augment:증가시키다, 늘리다|authentic:진정한, 진품의
authority:권위, 당국|authorize:권한을 부여하다, 인가하다|autonomy:자율성, 자치권|auxiliary:보조의, 예비의|avail:소용, 도움이 되다|avalanche:눈사태, 쇄도|avenge:복수하다, 보복하다|averse:꺼리는, 반대하는
avert:방지하다, (시선을) 돌리다|aviation:항공, 비행|avid:열심인, 탐욕스러운|await:기다리다, 대기하다|awkward:어색한, 서투른|bankrupt:파산한, 파산시키다|barren:척박한, 불모의|barrier:장벽, 장애물
behalf:이익, 대표하여|benevolent:자비로운, 선의의|acknowledge:인정하다|betray:배신하다, 드러내다|beverage:음료|bewilder:당황하게 하다, 어리둥절하게 하다|bias:편견, 편향|biodiversity:생물 다양성
biography:전기, 일대기|bizarre:기괴한, 별난|bleak:황량한, 암울한|blend:혼합하다, 조화되다|blossom:꽃을 피우다, 번영하다|blur:흐리게 하다, 흐릿함|boast:자랑하다, 뽐내다|bold:대담한, 굵은
bolster:강화하다, 북돋우다|bond:유대, 채권, 결합하다|boom:호황, 급증하다|boost:신장시키다, 북돋우다|boycott:불매 운동을 하다, 거부하다|Breakthrough:획기적 발전, 돌파구|breed:번식하다, 품종, 기르다|accelerate:가속하다
brief:간단한, 요약하다|brilliant:찬란한, 명석한|brisk:활발한, 상쾌한|brittle:부서지기 쉬운, 연약한|broaden:넓히다, 확장하다|budget:예산, 예산을 세우다|bulk:대량, 부피, 대부분|burden:부담, 짐, 지우다
bureaucracy:관료제, 관료주의|Bury:묻다, 매장하다|cabinet:내각, 수납장|calamity:재앙, 참사|calculate:계산하다, 산출하다|campaign:캠페인, 유세, 작전|candidate:후보자, 지원자|capacity:용량, 수용력, 능력
captivate:매혹하다, 사로잡다|captive:포로, 사로잡힌|carbon footprint:탄소 발자국|cardinal:가장 중요한, 기본적인|catastrophe:대참사, 파국|category:범주, 카테고리|cater:음식을 공급하다, 부응하다|caution:주의, 경고하다
cease:중단하다, 그치다|celebrity:유명 인사, 명성|censor:검열하다, 검열관|census:인구 조사|ceremony:의식, 기념식|certificate:증명서, 자격증|chamber:회의실, 방, 공간|chaos:혼돈, 대혼란
characteristic:특징, 고유한|cherish:소중히 여기다, 간직하다|chronic:만성적인, 고질적인|chronology:연대기, 시간순 배열|circulate:순환하다, 유포하다|circumstance:상황, 환경, 사정|cite:인용하다, 언급하다|civilization:문명
clarify:명확하게 하다, 해명하다|clash:충돌하다, 맞붙다|classify:분류하다, 구분하다|clause:조항, (문법) 절|cling:집착하다, 달라붙다|clinical:임상의, 냉철한|cluster:무리, 군집, 모이다|coalition:연합, 연립 정부
code:규범, 암호, 코드|coherent:일관성 있는, 논리적인|coincide:동시에 일어나다, 일치하다|coincidence:우연의 일치|collaborate:공동 작업하다, 협력하다|collapse:붕괴하다, 무너지다|colleague:동료|collective:집단적인, 공동의
collide:충돌하다, 부딪치다|collision:충돌, 대립|colony:식민지, 군락|combat:전투, 싸우다|commemorate:기념하다, 추모하다|commence:시작하다, 개시하다|commend:칭찬하다, 추천하다|commentary:해설, 논평
commerce:상업, 무역|commission:위원회, 수수료, 의뢰하다|commit:(죄를) 저지르다, 헌신하다|commitment:헌신, 약속, 책무|commodity:상품, 원자재|commonplace:흔한 일, 평범한|communal:공동의, 공용의|commute:통근하다, 통학하다
compact:소형의, 조밀한, 협약|companion:동반자, 벗|comparable:비교할 만한, 비슷한|compatible:호환되는, 양립할 수 있는|compel:강요하다, 어쩔 수 없이 ~하게 하다|compensate:보상하다, 상쇄하다|compensation:보상, 배상금|compete:경쟁하다, 겨루다
competent:유능한, 적격의|compile:편찬하다, 수집하다|complacent:안주하는, 자기만족의|complement:보완하다, 보충물|complex:복잡한, 복합 단지|complexity:복잡성|compliance:준수, 복종|complicate:복잡하게 만들다
compliment:칭찬, 칭찬하다|comply:준수하다, 따르다|component:구성 요소, 부품|compose:구성하다, 작곡하다, 진정시키다|comprehensive:포괄적인, 종합적인|comprise:구성되다, 포함하다|compromise:타협하다, 훼손하다|compulsory:의무적인, 강제의
conceal:숨기다, 은폐하다|concede:인정하다, 양보하다|conceive:상상하다, 고안하다, 임신하다|concentrate:집중하다, 농축하다|concept:개념, 관념|concern:우려, 관심사, 관련되다|conclude:결론을 내리다, 종결하다|concrete:구체적인, 콘크리트
concurrent:동시에 발생하는|condemn:규탄하다, 선고하다|condense:응축하다, 요약하다|confer:수여하다, 협의하다|confess:고백하다, 자백하다|confine:제한하다, 가두다|confirm:확인하다, 승인하다|conflict:갈등, 분쟁, 충돌하다
conform:순응하다, 따르다|confront:직면하다, 맞서다|confuse:혼란스럽게 하다|congratulate:축하하다|congress:의회, 국회, 학회|conjunction:결합, 접속사|conquer:정복하다, 극복하다|conscience:양심
conscious:의식하는, 자각하는|consecutive:연속적인, 연이은|consensus:합의, 일치된 의견|consent:동의하다, 승낙|consequence:결과, 중요성|consequent:결과로서 일어나는|conservation:보존, 보호|conservative:보수적인, 보수주의자
conserve:보존하다, 아끼다|considerable:상당한, 많은|considerate:사려 깊은, 배려하는|consistent:일관된, 부합하는|console:위로하다, 제어반|consolidate:공고히 하다, 통합하다|conspicuous:눈에 잘 띄는, 현저한|conspiracy:음모, 공모
constant:일정한, 끊임없는, 상수|constitute:구성하다, 제정하다|constitution:헌법, 체질, 구성|constrain:제약하다, 강요하다|construct:건설하다, 구성하다|consult:상담하다, 참고하다|consume:소비하다, 섭취하다|consumer:소비자
contact:접촉, 연락하다|contagious:전염성의, 옮기 쉬운|contaminate:오염시키다|contemplate:심사숙고하다, 응시하다|contemporary:동시대의, 현대의|contempt:경멸, 모독|contend:주장하다, 다투다|content:만족하는, 내용물, 목차
context:문맥, 맥락, 배경|contract:계약, 수축하다|contradict:모순되다, 반박하다|contrary:반대의, 정반대|contribute:기여하다, 기부하다, 원인이 되다|controversy:논란, 논쟁|convenient:편리한, 가까운|convention:관습, 집회, 협약
conventional:전통적인, 관습적인|converge:수렴하다, 한데 모이다|converse:대화하다, 정반대의|convert:전환하다, 개조하다|convey:전달하다, 운반하다|convict:유죄를 선고하다, 기결수|convince:확신시키다, 설득하다|coordinate:조정하다, 좌표
cope:대처하다, 맞서다|copyright:저작권|core:핵심, 중심부|corporate:기업의, 법인의|corporation:주식회사, 법인|correlate:상관관계가 있다|correspond:일치하다, 서신을 주고받다|corrupt:부패한, 타락시키다
council:의회, 평의회|counsel:조언하다, 변호인, 상담|counterpart:상대방, 대응물|countless:무수한, 셀 수 없이 많은|courtesy:예의, 공손함|coverage:보도 범위, 보상 범위|craft:공예, 기술, 정교하게 만들다|cram:벼락치기 공부를 하다, 쑤셔 넣다
crash:추락하다, 충돌, 폭락|credential:자격증, 신임장|credible:신뢰할 수 있는, 믿을 만한|credit:신용, 학점, 공로|criteria:기준, 척도(복수형)|criterion:기준, 표준(단수형)|crucial:결정적인, 매우 중요한|crude:가공하지 않은, 대강의
cultivate:경작하다, 기르다, 함양하다|cumulative:누적되는, 축적된|curb:억제하다, 연석|curiosity:호기심|curious:호기심이 많은, 기이한|currency:통화, 화폐, 통용|curriculum:교육과정, 커리큘럼|custody:양육권, 구류, 보관
customary:관례적인, 습관적인|cynical:냉소적인, 비꼬는|debris:잔해, 파편|decade:10년|decay:부패하다, 쇠퇴하다|deceive:속이다, 기만하다|decent:제대로 된, 품위 있는|CEPTION:속임수, 기만
declare:선언하다, 신고하다|decline:감소하다, 거절하다, 쇠퇴|decode:해독하다|decompose:분해되다, 부패하다|dedicate:바치다, 헌신하다|deduce:추론하다, 연역하다|deduct:공제하다, 차감하다|deem:여기다, 간주하다
defect:결함, 단점, 망명하다|defend:방어하다, 변호하다|deficiency:결핍, 부족|deficit:적자, 부족액|define:정의하다, 규정하다|definite:확실한, 명확한|defy:거역하다, 물리치다|degenerate:퇴화하다, 타락하다
degrade:비하하다, 분해되다|delay:지연시키다, 연기|delegate:위임하다, 대표자|deliberate:의도적인, 숙고하다|delicate:섬세한, 연약한, 미묘한|delusion:망상, 착각|democracy:민주주의|demographic:인구 통계학의
demonstrate:증명하다, 시연하다, 시위하다|denote:나타내다, 의미하다|dense:조밀한, 짙은|deny:부인하다, 거부하다|depart:출발하다, 떠나다|depict:묘사하다, 그리다|deplete:고갈시키다, 소모하다|deploy:배치하다, 전개하다
deposit:예금하다, 보증금, 퇴적물|depress:우울하게 하다, 침체시키다|deprive:박탈하다, 빼앗다|deputy:대리인, 부(副)책임자|derive:유래하다, 이끌어내다|descend:내려오다, 물려주다|descendant:후손, 자손|designate:지정하다, 지명하다
desirable:바람직한, 호감 가는|despair:절망, 절망하다|desperate:절박한, 필사적인|despise:경멸하다, 얕보다|destination:목적지, 도착지|destiny:운명, 숙명|detach:분리하다, 떼어내다|detect:감지하다, 발견하다
deter:단념시키다, 억제하다|deteriorate:악화되다, 저하되다|determine:결정하다, 알아내다|detrimental:해로운, 불리한|devastate:황폐화시키다, 엄청난 충격을 주다|deviate:일탈하다, 벗어나다|devise:고안하다, 창안하다|devote:바치다, 헌신하다
diagnose:진단하다|diagnosis:진단|dictate:받아쓰게 하다, 명령하다, 좌우하다|differentiate:구별하다, 차별화하다|diffuse:확산시키다, 퍼지다|digest:소화하다, 완전히 이해하다|dignity:존엄성, 위엄|dilemma:진퇴양난, 딜레마
dilute:희석하다, 약화시키다|dimension:차원, 측면, 크기|diminish:줄어들다, 감소시키다|diplomacy:외교, 협상 수완|diplomat:외교관|disability:장애, 무능력|disaster:재난, 참사|discard:버리다, 폐기하다
discern:식별하다, 분별하다|discharge:방출하다, 퇴원시키다, 이행하다|discipline:규율, 훈육, 학문 분야|disclose:폭로하다, 공개하다|discourse:담론, 강연|discrete:별개의, 불연속적인|discretion:재량권, 신중함|discriminate:차별하다, 식별하다
disguise:변장하다, 숨기다|disgust:혐오감, 역겹게 하다|dismay:경악, 실망시키다|dismiss:해고하다, 묵살하다, 해산시키다|disorder:무질서, 장애, 질환|dispatch:파견하다, 발송하다|dispel:떨쳐버리다, 불식시키다|dispense:분배하다, 조제하다
disperse:흩어지다, 분산시키다|displace:대체하다, 쫓아내다|display:전시하다, 드러내다|dispose:배치하다, 처분하다|disposition:성향, 기질, 배치|dispute:분쟁, 논쟁하다|disregard:무시하다, 묵살|disrupt:방해하다, 붕괴시키다
dissipate:소멸하다, 흩어지다|dissolve:용해하다, 해산하다|distinct:뚜렷한, 별개의|distinction:구별, 차이, 탁월함|distinguish:구별하다, 식별하다|distort:왜곡하다, 비틀다|distract:주의를 산만하게 하다|distribute:분배하다, 유통하다
district:지구, 구역, 행정구|disturb:방해하다, 불안하게 하다|diverse:다양한, 다채로운|diversify:다각화하다, 다양화하다|divert:(주의·방향을) 돌리다, 우회시키다|divine:신성한, 신의|doctrine:교리, 원칙, 독트린|domestic:국내의, 가정의, 길들여진
dominant:지배적인, 우세한|dominate:지배하다, 우위를 차지하다|dormant:휴면기의, 잠재된|dose:복용량, 1회분|drastic:과감한, 급격한|drawback:결점, 단점|dread:두려워하다, 공포|drowsy:나른한, 졸리는
dual:이중의, 둘의|dubious:의심스러운, 모호한|due:만기가 된, 마땅한, ~ 때문에|dull:무딘, 지루한, 흐릿한|duplicate:복제하다, 사본|durable:내구성이 있는, 오래가는|duration:지속 기간|dwell:거주하다, 곰곰이 생각하다
dynamic:역동적인, 활발한|dynasty:왕조, 가문|eager:열망하는, 간절히 바라는|earnest:진지한, 성실한|eccentric:괴짜인, 별난|eclipse:일식, 월식, 무색하게 하다|ecology:생태학, 생태 환경|economical:경제적인, 절약하는
edible:먹을 수 있는, 식용의|edit:편집하다, 교정하다|elaborate:정교한, 상세히 설명하다|elastic:탄력 있는, 유연한|elated:마냥 들뜬, 의기양양한|elevate:들어 올리다, 격상시키다|eligible:자격이 있는, 적격의|eliminate:제거하다, 탈락시키다
elite:엘리트, 핵심 계층|eloquent:유창한, 설득력 있는|elude:피하다, 이해되지 않다|emancipate:해방시키다|embark:(사업 등을) 시작하다, 승선하다|embarrass:당황스럽게 하다, 난처하게 하다|embassy:대사관|embed:끼워 넣다, 깊이 새기다
embody:구현하다, 상징하다, 포함하다|embrace:포용하다, 받아들이다, 껴안다|emerge:나타나다, 부상하다|emigrate:(타국으로) 이주하다|eminent:저명한, 탁월한|emission:배출, 방출물|emit:방출하다, 내뿜다|empathy:공감, 감정이입
emphasize:강조하다|empirical:경험적인, 실증적인|empower:권한을 부여하다, 자율권을 주다|emulate:모방하다, 본받다|enable:가능하게 하다|enact:(법을) 제정하다, 상연하다|enclose:둘러싸다, 동봉하다|encounter:우연히 만나다, 마주치다
endeavor:노력하다, 시도|endorse:지지하다, 승인하다, 배서하다|endow:기부하다, (재능을) 부여하다|endure:견디다, 인내하다|enforce:집행하다, 강제하다|engage:참여하다, 고용하다, 사로잡다|enhance:향상시키다, 높이다|enlightenment:계몽, 깨달음
enormous:막대한, 거대한|enquire:문의하다, 조사하다|enrich:풍요롭게 하다, 부유하게 하다|enroll:등록하다, 입학하다|ensue:뒤이어 일어나다|ensure:보장하다, 확실하게 하다|entail:수반하다, 필요로 하다|enterprise:기업, 진취적 사업
entertain:즐겁게 하다, 대접하다|enthusiasm:열정, 열의|entitle:자격을 주다, 제목을 붙이다|entity:실체, 독립체|entrepreneur:기업가, 창업가|envision:마음속에 그리다, 구상하다|epidemic:유행병, 전염병|episode:사건, 에피소드
equilibrium:평형, 균형 상태|equip:장비를 갖추다, 채비하다|equivalent:동등한, 상응하는 것|era:시대, 연대|eradicate:근절하다, 박멸하다|erase:지우다, 삭제하다|erect:세우다, 직립한|erode:침식하다, 약화시키다
erroneous:잘못된, 틀린|erupt:분출하다, 폭발하다|escalate:확대되다, 고조되다|essence:본질, 정수|establish:설립하다, 확립하다|estate:토지, 재산, 사유지|esteem:존경, 존중하다|estimate:추정하다, 견적서
eternal:영원한, 불멸의|ethic:윤리, 도덕률|ethnic:민족의, 인종의|evacuate:대피시키다, 피난하다|evade:회피하다, 모면하다|evaluate:평가하다, 감정하다|evaporate:증발하다, 사라지다|eventual:궁극적인, 최종적인
evoke:불러일으키다, 일깨우다|evolution:진화, 발전|evolve:진화하다, 발전하다|exaggerate:과장하다|exceed:초과하다, 능가하다|excel:탁월하다, 뛰어나다|exception:예외|excerpt:발췌, 인용문
excess:초과, 과잉|excessive:과도한, 지나친|exclude:배제하다, 제외하다|exclusive:독점적인, 배타적인|execute:실행하다, 처형하다|executive:경영진, 행정부의|exempt:면제된, 면제하다|exert:(힘·영향력을) 행사하다, 발휘하다
exhaust:기진맥진하게 하다, 배기가스, 고갈시키다|exhibit:전시하다, 보이다, 전시품|exile:망명, 추방하다|exotic:이국적인, 외래의|expand:확장하다, 팽창하다|expedition:탐험대, 원정|expel:추방하다, 퇴학시키다|expenditure:지출, 경비
expertise:전문 지식, 전문 기술|expire:만료되다, 숨을 거두다|explicit:명시적인, 명백한|exploit:착취하다, 개발하다, 위업|exponential:기하급수적인|export:수출하다, 수출품|expose:노출시키다, 폭로하다|extend:연장하다, 확장하다
extensive:광범위한, 대규모의|extent:정도, 범위|exterior:외부의, 외관|external:외부의, 대외적인|extinguish:(불을) 끄다, 소멸시키다|extract:추출하다, 발췌하다|extraordinary:비범한, 놀라운|extravagant:사치스러운, 낭비하는
extreme:극도의, 극단|fabric:직물, 천, 구조|fabricate:조작하다, 제작하다|facilitate:촉진하다, 용이하게 하다|facility:시설, 설비, 재능|faction:파벌, 당파|faculty:교수진, 학부, 능력|fade:서서히 사라지다, 바래다
famine:기근, 굶주림|fanatic:광신도, 열광적인|fascinate:매혹하다, 마음을 사로잡다|fatal:치명적인, 운명적인|fatigue:피로, 권태|feasible:실행 가능한, 실현 가능한|feat:위업, 공적|federal:연방의, 연방 정부의
feeble:연약한, 희미한|fertile:비옥한, 다산의|fierce:사나운, 치열한|filter:여과기, 거르다|finance:재정, 금융, 자금을 대다|finite:유한한, 한정된|fiscal:재정의, 회계의|flaw:결함, 흠
flee:달아나다, 피하다|fleet:함대, 선단, 빠른|flexible:유연한, 융통성 있는|fluctuate:변동하다, 오르내리다|fluent:유창한|foster:촉진하다, 육성하다, 위탁의|foundation:기초, 재단, 설립|fraction:분수, 일부, 파편
fracture:골절, 균열|fragile:깨지기 쉬운, 취약한|fragment:파편, 조각|framework:틀, 체제, 뼈대|frank:솔직한, 숨김없는|fraud:사기, 기만|freight:화물, 화물 운송|frequent:빈번한, 자주 가다
friction:마찰, 불화|frustrate:좌절시키다, 실망시키다|fulfill:이행하다, 충족시키다, 실현하다|function:기능, 함수, 작동하다|fund:기금, 자금을 대다|fundamental:근본적인, 핵심적인|furious:맹렬한, 격노한|furnish:비치하다, 제공하다
fusion:융합, 핵융합|futile:헛된, 무익한|garment:의복, 옷|gather:모으다, 수집하다|gaze:응시하다, 바라보다|gender:성, 성별|generate:생성하다, 발생시키다|generous:관대한, 후한
genetic:유전의, 유전학의|genuine:진짜의, 진심 어린|gesture:몸짓, 제스처|gigantic:거대한, 엄청난|glacier:빙하|glance:언뜻 보다, 일견|glare:노려보다, 눈부신 빛|glimpse:얼핏 봄, 흘끗 보다
globe:지구, 구체|gloom:우울, 어둠|glory:영광, 찬란함|govern:통치하다, 지배하다|grace:우아함, 은총|gradual:점진적인, 서서히 일어나는|grain:곡물, 낟알, 결|grant:수여하다, 보조금, 인정하다
grasp:움켜잡다, 완전히 이해하다|grateful:감사하는, 고마워하는|gratitude:감사, 사의|grave:무덤, 중대한, 심각한|greed:탐욕, 욕심|grief:큰 슬픔, 비탄|grim:암울한, 단호한|grind:갈다, 빻다
grip:꽉 잡다, 장악력|gross:총계의, 중대한, 역겨운|guarantee:보장하다, 보증서|guardian:보호자, 후견인|guideline:지침, 가이드라인|guilty:유죄의, 죄책감을 느끼는|halt:멈추다, 중단|hamper:방해하다, 저해하다
handicap:불리한 조건, 장애|harass:괴롭히다, 희롱하다|hardship:고난, 역경|harmony:조화, 화음|harness:(동력원으로) 이용하다, 마구|harsh:가혹한, 거친|harvest:수확하다, 수확물|haste:서두름, 급함
hazard:위험 요소, 위태롭게 하다|headline:머리기사, 표제|headquarters:본부, 본사|heir:상속인, 후계자|hemisphere:반구(지구·뇌)|heritage:유산, 전통|hesitate:주저하다, 망설이다|hierarchy:계층제, 위계질서
hinder:방해하다, 저해하다|holistic:전체론적인, 통합적인|hollow:속이 빈, 공허한|homogenous:동질적인, 균질한|horizon:수평선, 지평선, 시야|404_hostile:적대적인|hostile:적대적인, 불리한|household:가정, 가구
humanity:인류, 인간성, 인문학|humble:겸손한, 초라한|humiliate:굴욕감을 주다, 창피를 주다|hygiene:위생, 청결|hypothesis:가설, 전제|identical:동일한, 똑같은|identify:식별하다, 확인하다, 동일시하다|ideology:이념, 이데올로기
ignorant:무지한, 모르는|illuminate:비추다, 계몽하다, 밝히다|illusion:환상, 착각|illustrate:설명하다, 삽화를 넣다|imitate:모방하다, 흉내 내다|immense:거대한, 막대한|immerse:몰두시키다, 담그다|immigrant:이민자
imminent:임박한, 촉박한|immune:면역성이 있는, 면제된|impair:손상시키다, 해치다|impartial:공정한, 치우치지 않는|imperative:필수적인, 명령의|implement:시행하다, 도구|implicate:연루시키다, 함축하다|implicit:암묵적인, 내포된
imply:암시하다, 함축하다|import:수입하다, 중요성|impose:부과하다, 강요하다|impress:감명을 주다, 각인시키다|impulse:충동, 추진력|incentive:유인책, 장려금|incident:사건, 일어난 일|incline:기울다, 성향이 있다, 경사
incorporate:통합하다, 법인으로 만들다|incredible:믿을 수 없는, 놀라운|incur:초래하다, (손실을) 입다|indifferent:무관심한, 냉담한|indigenous:토착의, 고유한|indignant:분개한, 화가 난|indispensable:필수 불가결한, 없어서는 안 될|induce:유발하다, 설득하다
indulge:탐닉하다, 마음껏 즐기다|industrial:산업의, 공업의|inevitable:불가피한, 필연적인|infant:유아, 젖먹이|infect:감염시키다, 오염시키다|infer:추론하다, 암시하다|inferior:열등한, 하위자의|infinite:무한한, 끝없는
inflate:부풀리다, 통화를 팽창시키다|inflict:(고통·피해를) 가하다|infrastructure:사회 기반 시설, 인프라|ingenious:독창적인, 기발한|inherent:내재하는, 고유의|inherit:물려받다, 상속받다|inhibit:억제하다, 저해하다|initial:초기의, 머리글자
initiate:시작하다, 개시하다|initiative:주도권, 새로운 계획|inject:주입하다, 주사하다|innate:타고난, 선천적인|innocent:무죄인, 순진한|innovate:혁신하다|input:투입, 입력|inquire:질문하다, 조사하다
insight:통찰력, 식견|insist:주장하다, 고집하다|inspect:검사하다, 점검하다|inspire:영감을 주다, 고무하다|install:설치하다, 임명하다|instance:사례, 경우|instant:즉각적인, 순간|instinct:본능, 직감
institute:연구소, 도입하다, 제정하다|institution:기관, 제도, 관습|instruct:지시하다, 가르치다|insult:모욕하다, 모욕|insurance:보험|intact:손상되지 않은, 온전한|intake:섭취량, 받아들임|integral:필수적인, 적분의
integrate:통합하다, 결합하다|integrity:진실성, 청렴, 완전한 상태|intellect:지성, 사고력|intelligent:지적인, 총명한|intend:의도하다, 작정하다|intense:강렬한, 치열한|intensify:강화하다, 심화시키다|intent:의도, 몰두하는
interact:상호작용하다, 소통하다|interfere:간섭하다, 방해하다|interim:중간의, 임시의|interior:내부의, 실내 장식|intermediate:중급의, 중간의|internal:내부의, 국내의|interpret:해석하다, 통역하다|intervene:개입하다, 중재하다
intimate:친밀한, 소상히 아는|intimidate:위협하다, 겁주다|intricate:복잡한, 얽힌|intrigue:흥미를 끌다, 음모|intrinsic:본질적인, 고유의|invade:침략하다, 침해하다|invalid:무효의, 근거 없는|invaluable:매우 귀중한, 값을 매길 수 없는
invariable:변함없는, 일정한|inventory:재고 목록, 물품|invert:뒤집다, 역전시키다|invest:투자하다|investigate:조사하다, 수사하다|invisible:보이지 않는|invoke:발동하다, 호소하다, 불러일으키다|involve:포함하다, 수반하다, 참여시키다
irony:역설, 아이러니|irrational:비이성적인, 불합리한|irrelevant:무관한, 상관없는|irrigate:관개하다, 물을 대다|irritate:짜증 나게 하다, 자극하다|isolate:고립시키다, 격리하다|issue:쟁점, 발행하다, 문제|jeopardize:위태롭게 하다
justify:정당화하다, 옳음을 증명하다|juvenile:청소년의, 유치한|keen:예리한, 열망하는|kin:친척, 혈족|kinetic:운동의, 활동적인|labor:노동, 산고, 열심히 일하다|laboratory:실험실, 연구소|lack:부족, 결핍되다
lament:한탄하다, 애도하다|landscape:풍경, 조경|launch:출시하다, 발사하다, 시작하다|lavish:아낌없는, 호화로운|lawsuit:소송|layer:층, 겹|layout:배치, 설계|leak:새다, 누출, 유출하다
leap:도약하다, 급증|lease:임대하다, 임대차 계약|lecture:강의, 강연하다|legacy:유산, 전통|legal:법적인, 합법적인|legend:전설, 범례|legislate:법률을 제정하다|legitimate:정당한, 합법적인
leisure:여가, 자유 시간|lenient:관대한, 너그러운|lethal:치명적인|liable:책임이 있는, ~하기 쉬운|liberal:자유주의의, 관대한, 교양의|liberate:해방시키다, 자유롭게 하다|liberty:자유, 해방|license:면허, 허가하다
"""


@lru_cache(maxsize=1)
def get_authentic_english_lexicon() -> Tuple[Tuple[str, str, str, str], ...]:
    """Return 1,280+ distinct (word, meaning_ko, context_cloze, tip) English entries."""
    items: List[Tuple[str, str, str, str]] = []
    seen = set()

    for tier_idx, raw_block in enumerate((_RAW_ELEM_WORDS, _RAW_MID_WORDS, _RAW_HIGH_CSAT_WORDS)):
        level_label = (
            "초등 필수 핵심 어휘"
            if tier_idx == 0
            else "중학 내신 필수 핵심 어휘"
            if tier_idx == 1
            else "고교·수능·공인시험 필수 학술 어휘"
        )
        for line in raw_block.strip().splitlines():
            for token in line.split("|"):
                token = token.strip()
                if not token or ":" not in token:
                    continue
                word, meaning = token.split(":", 1)
                w = word.strip()
                m = meaning.strip()
                if not w or not m or w.startswith("404_") or w.lower() in seen:
                    continue
                seen.add(w.lower())
                if w.endswith(("tion", "sion", "ment", "ness", "ity", "ance", "ence", "ism", "ship", "ology")):
                    ctx = f"Understanding the concept of {{{{c1::{w}::{m}}}}} is essential in this passage."
                    pos_tip = f"{level_label} · 명사형 파생·핵심 개념어 ({w}: {m})"
                elif w.endswith(("ous", "ive", "al", "ful", "less", "able", "ible", "ic", "ant", "ent", "ary")):
                    ctx = f"The researchers observed a very {{{{c1::{w}::{m}}}}} pattern in the study."
                    pos_tip = f"{level_label} · 형용사 핵심 수식어 ({w}: {m})"
                elif " " in w:
                    ctx = f"Key expression: {{{{c1::{w}::{m}}}}} in daily and academic communication."
                    pos_tip = f"{level_label} · 필수 숙어·핵심 표현 ({w}: {m})"
                else:
                    ctx = f"Core vocabulary in context: {{{{c1::{w}::{m}}}}} — key meaning: '{m}'."
                    pos_tip = f"{level_label} · 대표 표제어 ({w}: {m})"
                items.append((w, m, ctx, pos_tip))
    return tuple(items)
