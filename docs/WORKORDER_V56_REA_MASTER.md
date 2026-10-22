# 📋 WORKORDER-BRAINDECK-V56 — 4대 프론티어 모델 REA 심층 발굴 & 마스터 작업 지시서

> **문서 ID**: `WORKORDER-BRAINDECK-V56`
> **작성 일시**: 2026-10-22 13:45 KST
> **참여 모델 (4-Model Multi-Agent REA & Architecture Council)**:
> - **Gemini 4 Argon High (Main Dev)**: BrainDeck 생태계(Desktop/Mobile/Add-ons) 및 글로벌·국내 경쟁 앱 8종 1차 REA & 벤치마킹 12대 기능 발굴
> - **Claude Opus 5.5 (Tech Lead & Architect)**: SuperMemo(SM-18)·RemNote·BrainDeck 심층 도메인 REA 6대 축 발굴 + **마스터 작업 지시서(`WORKORDER-BRAINDECK-V56`) 및 구현 계약 설계**
> - **Codex GPT-6.1 Sol (Senior Systems Reviewer)**: SQLite/IndexedDB 원장 정합성, FSRS-5 당일/비파괴 수식 분리, USN 충돌 해결, CAS 미디어 불변식 6대 발굴
> - **Grok 4.7 (Unanchored Product & Release Auditor)**: 한국 K-12/성인 행동 기반 시험일 역산(`Exam Countdown Autopilot`), QR 스냅샷 공유/학부모 리포트, 서술형 루브릭 채점, 완주 기반 Streak Shield 및 3대 Fail-Closed 감사 게이트 수립

---

## 🔬 Part 1. 4대 프론티어 모델(Gemini · Opus 5.5 · GPT-6.1 Sol · Grok 4.7) REA 추가 발굴 종합 매트릭스

### 1. Claude Opus 5.5 심층 도메인 REA 발굴 (Resource 간 계보 · Event 정본성 · Agent 목표 모델)

| 코드 | 발굴 항목 | REA 역공학 근거 (BrainDeck / SuperMemo SM-18 / RemNote) | BrainDeck v5.6 도입 명세 |
| :--- | :--- | :--- | :--- |
| **`REA-D1`** | **Incremental Reading (점진적 독해·발췌 계보)** | SuperMemo SM-18의 핵심: 원문 전체를 한 번에 카드로 만들면 카드 폭증(Deck Bloating) 발생. `원문(SourceDoc) ➔ 발췌(Extract) ➔ 노트(Note) ➔ 카드(Card)`로 점진 정제 | 사진/PDF 무제한 OCR 시 즉시 수백 장 카드로 쪼개지 않고 `SourceDoc ➔ Extract(anchor, priority) ➔ Note ➔ Card` 계보(`lineage_id`)를 보존. 카드에서 원문 페이지/문단으로 즉시 역추적 및 상단 브레드크럼 자동 바인딩 |
| **`REA-D2`** | **전제조건 DAG (`Prerequisite DAG`) & 실패 원인 역추적** | RemNote 지식 계층 & SM '이해 선행' 원칙: 기초 개념 A를 모르는데 응용 카드 B를 외우면 거머리(Leech) 카드가 됨 | ① **정방향 해금 게이트**: 부모(전제) 카드의 회상 확률 $R \ge 0.85$ 도달 전까지 후속 응용 신규 카드 출제 보류 (Tarjan SCC 순환 차단)<br>② **역방향 실패 진단**: 응용 카드 반복 오답 시 원자 분할 전에 **전제 카드 결손 여부부터 역추적하여 진단 복습 큐에 선행 삽입** |
| **`REA-D3`** | **의미 간섭쌍(`ConfusableEdge`) 감지 & 변별 대조 드릴** | SM 지식 구성 20원칙 중 '의미 간섭(Semantic Interference) 제거': 비슷한 개념(예: `임진왜란/정유재란`, `affect/effect`, `미토콘드리아/엽록체`)은 서로의 기억을 지움 | 주관식/객관식 오답 로그에서 **'A를 물었는데 B로 답한 이벤트'**를 감지하여 방향성 간선 `ConfusableEdge(A ➔ B)` 구축. 임계치 도달 시 **`[A vs B 핵심 차이 구별]` 대조 카드(Contrastive Card)**를 자동 파생하고 세션 내 **2장 이내 인접 배치** |
| **`REA-D4`** | **목표 리텐션(`target_R`) 동적 설정 (CMRR & 마감일 역산)** | BrainDeck CMRR(최적 리텐션) & SM 망각 지수(FI): 모든 카드를 똑같이 90%로 외우는 것은 비효율적 | `target_R(card) = clamp(f(priority, days_left, backlog), 0.70, 0.97)` 동적 산출. 상시 학습은 0.85~0.90 유지, 시험 D-n 구간에서는 시험 당일 적중률을 극대화하도록 역산 후 시험 종료 시 자동 복귀 |
| **`REA-D5`** | **복습 이벤트 원장 정본화 (`ReviewEvent` Fold Architecture)** | BrainDeck `revlog`는 append-only 정본 원장이며, FSRS 가중치 재최적화 시 원장을 처음부터 다시 접어(`fold`) 카드 상태를 재계산함 | `CardState = fold_review_events(events, params)` 순수 함수 정본화. 단계마다 `q(x) = round(x / 1e-6) * 1e-6` 고정 정밀도 양자화로 Python ↔ JS(PWA) ↔ Kotlin(Android) 3개 플랫폼의 부동소수점 오차(`1 ULP`)를 0으로 통제 |
| **`REA-D6`** | **음성 인출 4단계 승격 (발음 평가 GOP & 섀도잉)** | 말해보카·ELSA Speak 역공학: `4지선다 ➔ 블록조립 ➔ 받아쓰기` 다음의 최종 완전 인출은 **소리 내어 말하기(Speaking)** | 온디바이스 ASR 기반 발음/구술 채점을 Stage 3(4단계)로 추가. 단, 마이크 미권한·소음·만 14세 미만(`junior` 보호자 미동의) 시 `SpeechScore = NotRun(reason)` 합 타입으로 처리하고 가짜 0점/만점 부여 차단(Fail-Closed) |

---

### 2. Codex GPT-6.1 Sol 시스템 엔지니어링 & 데이터 무결성 REA 발굴

| 코드 | 발굴 항목 | 시스템 역공학 근거 (`col / notes / cards / revlog / graves`) | 핵심 불변식 (Invariants) |
| :--- | :--- | :--- | :--- |
| **`SYS-1`** | **노트 수정 시 파생 카드 무손실 재조정 & 지연 GC** | BrainDeck는 노트 템플릿/필드 수정 시 빈 카드를 즉시 하드 삭제하지 않아 수년간 쌓인 `revlog` 증발을 방지함 | `diff_facets(expected, existing)`를 통해 `UNIQUE(note_id, facet_key)` 유지. 사라진 Facet은 `ACTIVE ➔ RETIRED ➔ TOMBSTONED`로 지연 전이하며 `review_events` 연쇄 삭제 절대 금지. 동일 `facet_key` 재등장 시 이력 자동 부활 |
| **`SYS-2`** | **USN 증분 전송과 필드 단위 충돌 해결 분리** | BrainDeck Rust 코어(`chunks.rs`) 역공학: USN은 전송 커서일 뿐 CRDT가 아님 | `entity_revision / base_revision / idem_key` 도입. 서로 다른 필드 수정은 자동 병합하되, 동일 필드 동시 수정이나 동일 상태 분기 복습은 양쪽 모두 보존(`CONCURRENT_REVIEW`)하고 임의 평균/덮어쓰기 금지 |
| **`SYS-3`** | **비파괴 연습(`CRAM`) vs 선행 복습(`REVIEW_AHEAD`) 수식 분리** | FSRS-5 공식 수식: 당일 복습도 $S' = S e^{w_{17}(G-3+w_{18})}$로 $S$를 변경하므로, 벼락치기 반복을 일반 복습으로 넣으면 $S$가 왜곡됨 | `CRAM` 모드는 `(D, S, due, last_ts_ms, reps, lapses)` 바이트 단위 완전 불변($S'=S$) 보장 및 FSRS 옵티마이저/리텐션 통계에서 하드 제외. `REVIEW_AHEAD`는 실제 경과시간 $t < I$를 사용해 정식 수식으로 반영 |
| **`SYS-4`** | **Image Occlusion 마스크와 원본 미디어 분리 CAS (`sha256`)** | 카드마다 이미지를 복제하면 모바일/PWA 저장소(IndexedDB/OPFS)가 즉시 포화됨 | 원본 이미지는 `media_cas(sha256)`에 단 1회 저장하고, 가리기 카드는 `base_sha256 + 정규화 bbox 좌표 + mask_id`만 참조. `STAGED ➔ VERIFIED ➔ READY`(`os.replace`) 원자적 저장 및 미동기화 원본 축출 금지 |
| **`SYS-5`** | **방향성 오답 혼동 그래프 (`A ➔ B ≠ B ➔ A`)** | A를 물었을 때 B로 답할 확률과 B를 물었을 때 A로 답할 확률은 비대칭적임 | `confusion_edges(src, dst)`에서 `src <> dst` 방향성 유지. 단순 오타(자모 편집거리 1 이내)나 허용 동의어는 혼동 간선에서 분리 |
| **`SYS-6`** | **보상 이벤트(`VOID`) 기반 비파괴 Undo & 재투영** | 과거 `revlog` 행을 `DELETE`하면 멀티디바이스 동기화 시 좀비 복습 이력이 부활함 | 실행 취소(Undo)는 `DELETE`가 아니라 `kind='VOID', voids=target_event_id` 보상 이벤트를 append하고 `fold_review_events`로 현재 상태를 재투영 |

---

### 3. Grok 4.7 프로덕트 전략 · 한국 K-12/성인 행동 REA & 릴리즈 감사 게이트

| 코드 | 발굴 항목 | 한국 학생·성인 행동 역공학 (Behavioral REA) | BrainDeck v5.6 도입 명세 & Fail-Closed 규칙 |
| :--- | :--- | :--- | :--- |
| **`GRK-1`** | **Exam Countdown Autopilot (D-Day 역산 스케줄러)** | 한국 중고등 내신·성인 자격증 시장에서는 '평생 기억'보다 **'시험 당일 아침 9시 최고 적중률'**이 결제와 직결됨 | • **D-14**: 시험범위 잠금, 미학습 신규 카드 우선 소화<br>• **D-7**: 신규 카드 중단, 취약 카드·혼동 대조쌍 집중 인터리빙<br>• **D-1**: 신규 0장, 당일 할당량만 소화 (수면 전 과부하 차단)<br>• **시험 당일 아침**: 5~15분 초단기 웜업 (직전 오답·핵심 공식만)<br>• **Fail-Closed**: 과거 시험일·범위 0장·용량 초과 시 가짜 할당("오늘 20장") 생성 금지 ➔ `PLAN_BLOCKED(reason)` 반환 |
| **`GRK-2`** | **QR·단축코드 시험범위 스냅샷 공유 & 역할별 완주 리포트** | 클래스카드·Quizlet이 학교/학원을 장악한 핵심 동력은 '선생님/반장이 만든 시험범위 세트를 링크 하나로 반 전체가 공유'하는 루프 | • QR/코드에는 개인 학습 이력(PII) 없이 `deck_rev + scope_hash + exam_ms`만 포함<br>• **역할 분리**: 학생(학습), 교사(범위 잠금·학급 집계), **학부모(완주 리포트 카드: 범위명·시험일·할당 대비 완료율·연속 학습일만 표시, 가짜 예상 등급/상위 N% 전면 금지)** |
| **`GRK-3`** | **핵심 키워드 루브릭(`RubricSpec`) 서술형·수행평가·구술 카드** | 한국 내신 지필평가의 30~50%는 서술형·논술형이며, 성인 시험은 실기/면접이 당락을 가름 | • 기존 단답형(`recall`) 외에 서술/구술형(`constructed`) 카드 타입 도입<br>• `RubricSpec(required, bonus, forbidden, pass_ratio)`: 필수 키워드 적중·누락 및 **금기어(대표 오개념) 감점** 채점<br>• 학습 중 정답 키워드 전체 노출 금지 (개수 ➔ 첫 글자 ➔ 누락 항목 단계형 힌트)<br>• STT/채점기 장애 시 0점 처리 금지 ➔ `SCORE_UNAVAILABLE` 반환 (이벤트 미생성) |
| **`GRK-4`** | **할당 완주 기반 Streak Shield(스트릭 실드) & 주간 완주 리그** | 듀오링고·말해보카의 스트릭은 앱만 열거나 1문제만 풀어도 유지되는 '출석 꼼수'가 발생함 | • 스트릭 인정 기준 = **"그날 Autopilot 할당량을 100% 완주한 날"** (단순 `CRAM` 연습은 제외)<br>• `Streak Shield`는 퀘스트 완주 보상으로만 적립되며 결손 1일을 1회 방어 (기기 시계 조작 방지를 위해 사용자 고정 IANA 타임존 기준 검증) |
| **`GRK-5`** | **v5.6 Fail-Closed 3대 릴리즈 감사 게이트** | 수석 감사관(Grok 4.7) 릴리즈 차단 기준 | ① **스케줄 무결성** (`PLAN_BLOCKED` 사유 코드 강제)<br>② **공유·리포트 무결성** (만료/범위해시 변경 시 구 코드 즉시 무효, 학부모 카드 내 가짜 예상 점수 0건)<br>③ **스트릭·채점 무결성** (`SCORE_UNAVAILABLE` 시 부분 JSON 합격 처리 금지) |

---

## 🛠️ Part 2. Claude Opus 5.5 설계 — 『WORKORDER-BRAINDECK-V56』 마스터 작업 지시서 및 구현 계약

> **Track L 아키텍처 파이프라인**: 지시서 설계(`Claude Opus 5.5`) ➔ 구현(`Antigravity Gemini / Codex`) ➔ 독립 코드 리뷰(`Codex GPT-6.1 Sol`) ➔ 최종 릴리즈 감사(`Grok 4.7`)
> **5대 엔지니어링 불변식**:
> 1. **Domain Zero-I/O** (`.importlinter` 및 AST 정적 분석으로 외부 I/O import 0건 강제)
> 2. **Fail-Closed** (`PLAN_BLOCKED`, `SCORE_UNAVAILABLE` 명시적 타입 반환)
> 3. **Zero Fabricated Status** (가짜 예상 점수, 가짜 완주율, 가짜 할당량 생성 금지)
> 4. **Atomic Staging** (`STAGED ➔ VERIFIED ➔ os.replace` 원자적 미디어/PDF 교체)
> 5. **`BEGIN IMMEDIATE` Single Source of Truth** (`review_events` append-only 원장 단일 트랜잭션)

### 1. Phase 1 ~ 4 단계별 구현 로드맵

1. **Phase 1 — Core Ledger & Schedule (`fsrs_math.py`, `adaptive_quiz.py`, `sqlite_store.py`)**
   - **불변 복습 원장 (`ReviewEvent`)**: 모든 카드 상태(`CardState`)는 순수 함수 `fold_review_events(events, params)`의 결과로만 결정.
     - 정렬 키: `(ts_ms, event_id)` / 단계별 `q(x) = round(x / 1e-6) * 1e-6` 고정 정밀도 양자화(Python ↔ JS ↔ Kotlin `1e-6` 패리티 보장).
     - `review_events` 테이블은 `UPDATE / DELETE` 트리거로 원천 차단하며, 실행 취소(Undo)는 `kind="VOID", voids=event_id` 보상 이벤트로 기록.
   - **`CRAM` vs `REVIEW_AHEAD` 분리**:
     - `CRAM`: 원장에 활동 이력은 남기되 `fold_review_events`에서 `S'=S, D'=D, due_ms=due_ms`로 완전 비파괴 보존.
     - `REVIEW_AHEAD`: 실제 경과 시간 $t < I$를 사용해 정식 FSRS-5 수식으로 안정성 갱신.
   - **`Exam Countdown Autopilot` (`plan_exam`)**:
     - `D-14`(범위 커버리지) ➔ `D-7`(약점·혼동쌍 집중) ➔ `D-1`(고위험 카드 재노출, 수면 전 과부하 차단) ➔ `D-Day 아침`(신규 0장, 최대 20장 초단기 웜업).
     - `target_R = clamp(f(days_left, backlog), 0.70, 0.97)`.
     - 용량 초과·과거 시험일·빈 범위·전제조건 DAG 사이클 발견 시 축소 플랜을 몰래 만들지 않고 즉시 `PlanBlocked(reason)` 반환.
   - **`Load Balancer & Easy Days` (`balance_due`)**:
     - 퍼즈 구간 `[0.95*I, 1.05*I]` 내에서 `load[d] / weight[d]`가 최소인 날짜를 결정론적으로 선택(동률 시 가장 이른 날짜).

2. **Phase 2 — Resource Graph & Media (`document_deck_builder.py`, `document_ingestor.py`, `reference_pack_store.py`)**
   - **`1 Note ➔ N Facet Cards` (`diff_facets`)**:
     - 노트 1개에서 `forward`, `reverse`, `listening_tts`, `context_cloze` 파생.
     - 노트 수정 시 `expected_facets`와 비교해 사라진 Facet은 `ACTIVE ➔ RETIRED`(숨김) ➔ 유예기간 후 `TOMBSTONED` 전이(`review_events` 삭제 금지). 동일 `facet_key` 재등장 시 `ACTIVE` 복구 및 기존 이력 승계.
   - **OCR Bounding Box 기반 자동 `Image Occlusion` & `media_cas`**:
     - 원본 이미지와 SVG 마스크를 `sha256` CAS(`media_cas`)에 저장하고 해시 불일치 시 거부.
   - **Incremental Reading 계보 & Context Breadcrumb & 4색 Flag**:
     - `SourceDoc ➔ Extract ➔ Note ➔ Card` FK 체인 구축, ViewModel에서 상단 브레드크럼 생성, `flag ∈ {0, 1, 2, 3, 4}` 별도 컬럼 분리.

3. **Phase 3 — Active Recall 2.0 (`ai_learning.py`, `adaptive_quiz.py`)**
   - **방향성 혼동 그래프 (`ConfusableEdge A ➔ B`) & 대조 카드 인접 인터리빙 (`interleave_contrastive`)**:
     - A를 물었을 때 B로 답한 경우만 `src=A, dst=B` 가중치 상승. 파생된 대조 카드(`Contrastive Card`)는 A, B와 세션 내 간격 2장 이하(`max_gap=2`)로 인접 배치.
   - **전제조건 DAG (`find_cycles` & R≥0.85 해금 게이트)**:
     - Tarjan SCC 알고리즘으로 사이클 감지 시 `PLAN_BLOCKED` 반환. 모든 부모 카드의 $R \ge 0.85$일 때만 자식 신규 카드 해금(닫힘 히스테리시스 $0.75$).
   - **키워드 루브릭 서술형·구술 채점 (`score_rubric`)**:
     - `RubricSpec(required, bonus, forbidden, pass_ratio)` 기반 채점. 입력 누락이나 STT/채점기 장애 시 `ScoreUnavailable` 반환 및 `ReviewEvent` 생성 차단(`call_count == 0`).
   - **7-Card 마이크로 스프린트 체크포인트 & 60초 4×3 매칭 보드**:
     - 7장 단위 미니 라운드 완주 피드백 제공. 매칭 게임 결과는 `CRAM` 이벤트로만 기록해 정규 FSRS 스케줄 오염 방지.

4. **Phase 4 — View & Viral Utility (`viewmodel.js`, `app.js`, `android-app/`)**
   - **시험 직전 『전자 셀로판지 요약 시트(Summary Sheet View)』 & 『인쇄용 2단 쪽지시험지(문제지+정답지 동일 시드) 생성기』**
   - **핸즈프리 『통학/주행 오디오 루프(Commute Audio Loop)』** (`질문 TTS ➔ 사고시간 3초 ➔ 정답/해설 TTS ➔ 자동 다음 카드`)
   - **QR/단축코드 시험범위 스냅샷 공유 & 학부모/교사 완주 리포트 카드 + 할당 완주 기반 `Streak Shield`**

---

### 2. 핵심 데이터클래스 및 순수 함수 시그니처 계약 (Python ↔ JS ViewModel ↔ Kotlin Domain)

```python
from dataclasses import dataclass
from datetime import date
from typing import Literal, Mapping, Sequence

@dataclass(frozen=True)
class ReviewEvent:
    event_id: str
    card_id: str
    kind: Literal["REVIEW", "REVIEW_AHEAD", "CRAM", "VOID"]
    rating: int | None
    ts_ms: int
    device_id: str
    idem_key: str
    voids: str | None = None

@dataclass(frozen=True)
class CardState:
    s: float
    d: float
    due_ms: int
    last_ts_ms: int | None
    reps: int
    lapses: int

@dataclass(frozen=True)
class ExamPlan:
    plan_id: str
    scope: tuple[str, ...]
    exam_ms: int
    target_r: float
    status: Literal["ACTIVE", "BLOCKED", "DONE"]
    reason: str | None = None

@dataclass(frozen=True)
class FacetSpec:
    note_id: str
    facet_key: str
    template: str

@dataclass(frozen=True)
class ConfusableEdge:
    src: str
    dst: str
    weight: float
    count: int
    last_ts_ms: int

@dataclass(frozen=True)
class RubricSpec:
    required: tuple[str, ...]
    bonus: tuple[str, ...]
    forbidden: tuple[str, ...]
    pass_ratio: float

def fold_review_events(events: Sequence[ReviewEvent], params: "FSRSWeights") -> CardState: ...
def plan_exam(cards: Sequence[dict], now_ms: int, exam_ms: int, daily_cap: int, prereq: Mapping[str, Sequence[str]]) -> ExamPlan: ...
def balance_due(ivl_days: float, load: Mapping[date, int], weights: Mapping[date, float], today: date) -> date: ...
def diff_facets(expected: set[str], existing: Mapping[str, str], now_ms: int, grace_ms: int) -> list[dict]: ...
def find_cycles(edges: Mapping[str, Sequence[str]]) -> list[frozenset[str]]: ...
def score_rubric(answer: str | None, spec: RubricSpec) -> dict: ...
def interleave_contrastive(queue: list[str], edges: Sequence[ConfusableEdge], max_gap: int = 2) -> list[str]: ...
```

---

### 3. SQLite (`sqlite_store.py`) & IndexedDB (`BrainDeckLocalVault`) 확장 스키마 (DDL)

```sql
CREATE TABLE IF NOT EXISTS review_events (
    event_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('REVIEW', 'REVIEW_AHEAD', 'CRAM', 'VOID')),
    rating INTEGER CHECK(rating BETWEEN 1 AND 4),
    ts_ms INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    idem_key TEXT NOT NULL UNIQUE,
    voids TEXT REFERENCES review_events(event_id)
);
CREATE INDEX IF NOT EXISTS ix_re_card_ts ON review_events(card_id, ts_ms, event_id);

CREATE TABLE IF NOT EXISTS note_facets (
    note_id TEXT NOT NULL,
    facet_key TEXT NOT NULL,
    card_id TEXT UNIQUE NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('ACTIVE', 'RETIRED', 'TOMBSTONED')),
    retired_at_ms INTEGER,
    tombstoned_at_ms INTEGER,
    PRIMARY KEY(note_id, facet_key)
);

CREATE TABLE IF NOT EXISTS confusion_edges (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    weight REAL NOT NULL CHECK(weight >= 0),
    count INTEGER NOT NULL,
    last_ts_ms INTEGER NOT NULL,
    PRIMARY KEY(src, dst),
    CHECK(src <> dst)
);

CREATE TABLE IF NOT EXISTS exam_plans (
    plan_id TEXT PRIMARY KEY,
    scope_json TEXT NOT NULL,
    exam_ms INTEGER NOT NULL,
    target_r REAL NOT NULL CHECK(target_r BETWEEN 0.70 AND 0.97),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'BLOCKED', 'DONE')),
    reason TEXT,
    CHECK(status <> 'BLOCKED' OR reason IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS media_cas (
    sha256 TEXT PRIMARY KEY CHECK(length(sha256) = 64),
    mime TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    refcount INTEGER NOT NULL DEFAULT 0,
    created_ms INTEGER NOT NULL
);
```

---

### 4. 신규 재작업 방지 함정 가드레일 (`T35 ~ T42`) 및 ATDD 테스트 스위트 (`tests/test_v56_*.py`)

| 게이트 ID | 방어 대상 함정 (Trap) | 결정론적 해법 및 불변식 | 검증 테스트 스위트 |
| :--- | :--- | :--- | :--- |
| **`T35`** | **3-플랫폼 부동소수점 패리티 붕괴** | 단계별 `q(x) = round(x / 1e-6) * 1e-6` 고정 양자화 및 3개 플랫폼 공통 Golden Vector 검증 | `tests/test_v56_ledger.py` |
| **`T36`** | **CRAM 연습의 정규 스케줄 오염 & 원장 훼손** | `CRAM` 이벤트는 `fold` 시 $S'=S, D'=D$ 바이트 불변 유지, `review_events` UPDATE/DELETE 트리거 차단, 중복 `idem_key` First-Writer-Wins | `tests/test_v56_schedule.py` |
| **`T37`** | **Exam Autopilot 불가능 플랜의 조용한 축소** | 과거 시험일·빈 범위·일일 한도 초과·DAG 사이클 시 가짜 할당 대신 즉시 `status='BLOCKED'` + `reason` 반환 | `tests/test_v56_exam_autopilot.py` |
| **`T38`** | **노트 수정 시 파생 카드 삭제 및 복습 이력 증발** | `ACTIVE ➔ RETIRED ➔ TOMBSTONED` 지연 전이, `review_events` 행 수 불변, 동일 `facet_key` 재등장 시 이력 부활 | `tests/test_v56_facets.py` |
| **`T39`** | **이미지 가리기 미디어 중복 복제 및 깨진 파일 적재** | `sha256` CAS 중복 제거 + 해시 재검증 + `os.replace` 원자적 스테이징 (실패 시 잔여물 0바이트) | `tests/test_v56_media.py` |
| **`T40`** | **혼동 간선 대칭 오염 & 전제조건 DAG 순환 교착** | `A ➔ B ≠ B ➔ A` 방향성 분리, Tarjan SCC 순환 차단, 부모 $R \ge 0.85$ 해금 게이트 (닫힘 $0.75$ 히스테리시스) | `tests/test_v56_recall.py` |
| **`T41`** | **서술/구술 채점기·STT 장애 시 0점/만점 둔갑** | 입력 누락·타임아웃·장애 시 `SCORE_UNAVAILABLE` 반환 및 `ReviewEvent` 기록 0건(`call_count == 0`) 보장 | `tests/test_v56_recall.py` |
| **`T42`** | **Domain I/O 누수 및 리포트/스트릭 허위 상태 생성** | AST Domain Purity 검사, QR 스냅샷 내 PII 0건, 데이터 부재 시 `'집계 없음'` 명시, `CRAM`만으로 Streak Shield 적립 차단 | `tests/test_v56_views.py` |
