# 🧠 Anki Studio 1.0 — 마스터 아키텍처 & 상세 기술 규격서 (`ANKI-1019-02`)

- **문서 번호**: `ANKI-1019-02` (제 2 SW 개발항목 정본)
- **프로젝트 경로**: `/Users/choyoungseo/Documents/개발/Anki-Studio`
- **작성일**: 2026-10-19 KST
- **아키텍처 표준**: Clean / Hexagonal Architecture + MVVM + ATDD/BDD/TDD/DDT
- **라이선스 등급**: **100% Clean-Room Commercial Ready** (AGPLv3 의존성 0건)

---

## 1. 기획 배경 및 문제 정의 (Problem Statement)

### 1.1 기존 Anki 생태계의 4대 병목
1. **구형 SM-2 알고리즘의 구조적 한계 ('Ease Hell')**:
   - 1987년 SuperMemo 2(SM-2)에 기반한 기본 스케줄러는 한두 번 `Again`이나 `Hard`를 누르면 난이도 계수(Ease Factor)가 영구 추락하여 이미 아는 카드도 수시로 다시 튀어나오는 **복습 폭탄(Ease Hell)**을 유발합니다.
2. **수동 카드 제작의 높은 진입장벽**:
   - 학습 자체보다 카드를 입력하고 빈칸(`{{c1::...}}`)을 뚫는 데 시간이 더 많이 걸려 바쁜 직장인·연구자가 중도 포기하게 됩니다.
3. **플랫폼 파편화 및 과금 장벽**:
   - 데스크톱 앱은 무거운 구형 Qt 프레임워크로 구동되며, iOS 앱(`AnkiMobile`)은 $24.99 유료 결제 없이는 모바일 복습이 불가능합니다.
4. **상용화 불가능 라이선스 (AGPLv3)**:
   - 오픈소스 Anki 코어는 `AGPLv3` 라이선스로 묶여 있어, 이를 수정하거나 웹 서비스로 제공할 경우 전체 소스코드를 강제로 공개해야 하므로 독자 상용 SW 런칭이 불가능합니다.

### 1.2 Anki Studio의 해결 전략
- **FSRS-5 (DSR 모델) Clean-Room 자체 구현**: 최신 공개 학술 수식(Three-Component Model of Memory)만 사용하여 `fsrs_math.py`를 100% 독자 코드로 작성합니다.
- **기존 `.apkg` 포맷 무손실 호환**: 표준 `zipfile` + `sqlite3`로 `.apkg` 아카이브를 직접 파싱하여 기존 Anki 사용자 데이터를 100% 그대로 흡수합니다.
- **AI & Notion 자동 카드 생성 파이프라인**: 사용자의 노션 `영어회화` DB, `반도체/AI 핸드북`, PDF 논문에서 핵심 문장과 수식을 자동 추출해 Cloze/Q&A 카드를 생성합니다.

---

## 2. FSRS-5 (DSR 기억망각곡선) 수학 엔진 상세 명세 (`domain/fsrs_math.py`)

인간의 장기 기억 상태를 **3개의 상태 변수 $(D, S, R)$**로 모델링합니다:
- **$D \in [1.0, 10.0]$ (Difficulty, 난이도)**: 카드 자체의 내재적 복잡도 (`1.0` = 매우 쉬움, `10.0` = 매우 어려움).
- **$S > 0$ (Stability, 안정성 [단위: 일])**: 인출 확률 $R$이 $100\% \to 90\%$로 떨어지는 데 걸리는 일수(Days). 예: $S = 30$이면 30일 뒤 기억할 확률이 정확히 $90\%$.
- **$R \in (0.0, 1.0]$ (Retrievability, 인출 가능성)**: 마지막 복습 후 $t$일이 지났을 때 기억을 떠올릴 확률.

### 2.1 망각 곡선 (Power-Law Forgetting Curve)
지수 함수보다 실제 인간 뇌의 망각 데이터를 훨씬 정확하게 설명하는 멱함수(Power-law) 망각 곡선을 사용합니다:
$$R(t, S) = \left(1 + F \cdot \frac{t}{S}\right)^C \quad \text{where } F = \frac{19}{81},\; C = -0.5$$
- 검증 불변식: $t = 0 \implies R(0, S) = 1.0$, $t = S \implies R(S, S) = \left(1 + \frac{19}{81}\right)^{-0.5} = \left(\frac{100}{81}\right)^{-0.5} = 0.90$.

### 2.2 목표 기억 유지율($R_{\text{req}}$) 기반 최적 복습 간격($I$)
사용자가 원하는 목표 기억 유지율 $R_{\text{req}} \in [0.70, 0.97]$ (기본값 `0.90`)에 대해 다음 복습 간격 $I$는:
$$I(S, R_{\text{req}}) = \max\left(1,\; \text{round}\left(\frac{S}{F} \left(R_{\text{req}}^{1/C} - 1\right)\right)\right)$$

### 2.3 최초 학습(First Review) 초기 상태 $(D_0, S_0)$
신규 카드를 처음 학습할 때 선택한 버튼 등급 $G \in \{1:\text{Again}, 2:\text{Hard}, 3:\text{Good}, 4:\text{Easy}\}$에 대해:
$$S_0(G) = w_{G - 1}, \quad D_0(G) = \text{clip}\Big(w_4 - e^{w_5 (G - 1)} + 1,\; 1.0,\; 10.0\Big)$$

### 2.4 복습 후 상태 전이 $(D', S')$
1. **난이도 갱신 (선형 감쇠 및 평균 회귀 Mean Reversion)**:
   $$\Delta D(G) = -w_6 \cdot (G - 3)$$
   $$D_{\text{ damped}} = D + \Delta D(G) \cdot \frac{10 - D}{9}$$
   $$D' = \text{clip}\Big(w_7 \cdot D_0(4) + (1 - w_7) \cdot D_{\text{damped}},\; 1.0,\; 10.0\Big)$$
2. **회상 성공 시 ($G \in \{2:\text{Hard}, 3:\text{Good}, 4:\text{Easy}\}$) 기억 안정성 증폭 ($S'_r$)**:
   - 기억이 아슬아슬할 때($R$이 낮을 때) 성공적으로 떠올릴수록 안정성 증가폭($e^{w_{10}(1-R)} - 1$)이 커지는 **바람직한 어려움(Desirable Difficulty)** 효과를 반영합니다:
   $$S'_r(D, S, R, G) = S \cdot \left(1 + e^{w_8} \cdot (11 - D) \cdot S^{-w_9} \cdot \left(e^{w_{10}(1 - R)} - 1\right) \cdot h(G) \cdot b(G)\right)$$
   (단, $h(2) = w_{15}$, $b(4) = w_{16}$, 그 외에는 $1.0$)
3. **망각(실패) 시 ($G = 1:\text{Again}$) 기억 안정성 감쇠 ($S'_f$)**:
   $$S'_f(D, S, R) = \min\left(S,\; w_{11} \cdot D^{-w_{12}} \cdot \left((S + 1)^{w_{13}} - 1\right) \cdot e^{w_{14}(1 - R)}\right)$$

---

## 3. 데이터 스키마 & `.apkg` 무손실 호환 설계 (`adapters/sqlite_store.py`)

### 3.1 SQLite WAL 단일 원장 (`anki_studio.sqlite`)
모든 상태 변경(카드 생성, 복습 결과 반영, 덱 임포트)은 `BEGIN IMMEDIATE` 트랜잭션으로 원자적(Atomic)으로 처리됩니다.
- `decks`: `deck_id (PK)`, `name`, `description`, `desired_retention (default 0.90)`, `created_at`
- `notes`: `note_id (PK)`, `deck_id (FK)`, `note_type ('basic' | 'cloze' | 'speaking' | 'image_occlusion')`, `front_text`, `back_text`, `extra_json`, `tags_json`, `source_ref (Notion/PDF 멱등성 키)`
- `cards`: `card_id (PK)`, `note_id (FK)`, `deck_id (FK)`, `ordinal`, `state ('new' | 'learning' | 'review' | 'relearning')`, `difficulty`, `stability`, `due_at`, `last_review_at`, `reps`, `lapses`
- `revlog`: `rev_id (PK)`, `card_id (FK)`, `rating (1~4)`, `state_before`, `difficulty_before`, `stability_before`, `difficulty_after`, `stability_after`, `retrievability`, `scheduled_days`, `elapsed_days`, `review_duration_ms`, `reviewed_at`

### 3.2 Cloze (빈칸 채우기) 문법 파서 (`domain/fsrs_math.py`)
- 입력 노트: `"GAA 트랜지스터는 {{c1::Nanosheet::구조 명칭}} 채널을 4면으로 감싸 {{c2::단채널 효과(SCE)}}를 억제한다."`
- `ordinal = 1` 카드 앞면: `"GAA 트랜지스터는 [구조 명칭] 채널을 4면으로 감싸 단채널 효과(SCE)를 억제한다."`
- `ordinal = 1` 카드 뒷면: `"GAA 트랜지스터는 【Nanosheet】 채널을 4면으로 감싸 단채널 효과(SCE)를 억제한다."`
- 하나의 노트에서 `c1, c2, ..., cN` 번호별로 독립된 FSRS-5 카드를 자동 파생합니다.

---

## 4. 단계별 구현 마일스톤

1. **Step 1 (완료 — Foundation & Pure Domain TDD)**:
   - `Anki-Studio` 독립 폴더 및 Git 저장소 구성
   - `fsrs_math.py`: FSRS-5 DSR 스케줄러, 4개 버튼(`Again/Hard/Good/Easy`) 프리뷰 계산기, Cloze 멀티 빈칸 파서 구현
   - `sqlite_store.py`: SQLite WAL 원장 및 `.apkg` 임포터/익스포터 어댑터 구현
   - `tests/test_fsrs_domain.py`: 수학적 불변식, 경계값, Cloze 파싱, SQLite 원장 트랜잭션, AST Zero-I/O 테스트 완비
2. **Step 2 (Next — UI 스튜디오 & macOS 앱 번들)**:
   - 다크 글래스모피즘 `Zen Review Mode` 웹 UI (`viewmodel.js` + `app.js` + `index.html`)
   - 키보드 단축키(`Space`, `1~4`), 원어민 Web Speech / TTS 발음 재생, 기억 망각곡선 실시간 그래프 및 GitHub 잔디 히트맵
   - `Anki Studio.app` 네이티브 macOS 앱 빌드
3. **Step 3 (Next — Notion & PDF 원클릭 AI 카드 생성기)**:
   - 노션 `영어회화` DB 및 `반도체/AI 핸드북` 연동 자동 카드 생성기 탑재
