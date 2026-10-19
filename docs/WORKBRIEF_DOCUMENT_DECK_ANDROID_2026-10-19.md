# Work Brief — 사진·PDF 자동 덱 생성 + Android 앱 (Implementation Contract)

- 작성: 2026-10-19 · Claude Opus 5.5 (Tech Lead)
- 대상 저장소: `~/Documents/개발/Anki-Studio`
- 규칙 원천: `~/.grok/rules/07-sw-development-methodology.md` (5대 불변식)

---

## 1. Goal & Track — **Track L** (신규 플랫폼 + DB 쓰기 + 외부 LLM 전송)

범용 학습자가 교재 사진이나 강의 PDF를 넣으면 **출처가 붙은 카드만으로 구성된 덱**이 한 번에 생성된다.
"완료"의 정의: 실제 샘플 문서 5종(한국어 교재 사진, 영어 강의 PDF, 법조문 PDF, 어학 패턴 사진, 스캔 PDF)이
서버와 Android 양쪽에서 덱으로 저장되고, 모든 카드에 원문 페이지 출처가 남는다.

### 단계 분할 (각 단계 별도 리뷰 게이트)

| 단계 | 범위 | 비고 |
|---|---|---|
| **P1** | `domain/document_deck_builder.py` + `adapters/document_ingestor.py` + `POST /api/ai/ingest-document` | 서버 정본. 이후 단계의 골든 픽스처 생산자 |
| **P2** | 웹/PWA 드래그앤드롭 + 모바일 카메라 업로드 UI (`ui/static/*`) | MVVM: `viewmodel.js`에 순수 함수 추가 |
| **P3** | `android-app/` 네이티브 (오프라인 OCR + FSRS-5 + 덱 빌더 Kotlin 포팅) | P1 골든 픽스처로 Python과 동일 결과 강제 |

---

## 2. Acceptance Criteria (ATDD)

### 기능
- [ ] **AC-1 추출**: 이미지(JPEG/PNG/HEIC) 및 PDF → `ExtractedDocument`(블록 목록: 종류·텍스트·페이지·신뢰도).
      텍스트 레이어가 있는 PDF는 파싱하고, 없는 페이지(스캔본)만 OCR로 보낸다 (페이지 단위 판정).
- [ ] **AC-2 덱 이름**: 사용자 지정 > 문서 제목(PDF `/Title` 메타 또는 첫 heading 블록) > 상위 키워드 2~3개 조합 > `"문서 덱 YYYY-MM-DD"`.
      카테고리는 `language | law | medical | engineering | exam | general` 중 하나로 결정적 판정한다.
- [ ] **AC-3 카드 패턴 5종**: 정의(`용어: 설명`, `~란 ~이다`) → Q&A/Cloze, 번호 목록 → 항목별 Cloze 또는 열거 Q&A,
      인과·비교(`때문에`, `반면`, `vs`, `→`) → Q&A, 조문·수치(`제N조`, 숫자+단위) → 수치 Cloze, 어학 패턴(`A -> B`, 예문) → speaking/basic.
- [ ] **AC-4 일괄 저장**: 덱 생성과 노트 N건 삽입이 **단일 `BEGIN IMMEDIATE` 트랜잭션**에서 처리된다. 중간에 실패하면 덱도 남지 않는다.
- [ ] **AC-5 미리보기 우선**: 기본 `auto_save=false`. 사용자는 카드를 확인하고 일부를 빼거나 고친 뒤 저장한다. 바로 저장은 `auto_save=true`를 명시했을 때만 한다.

### Fail-Closed / 허위 상태 금지
- [ ] **AC-6** OCR 엔진 불가, 암호화 PDF, 페이지 0, 손상 파일, 크기 초과(20MB), 페이지 초과(기본 50) → `status:"BLOCKED"` + `error_code`. **빈 덱을 "성공"으로 반환하지 않는다.**
- [ ] **AC-7** 추출 텍스트가 최소량(기본 40자) 미만 → `BLOCKED/insufficient_text`. 카드가 0장이면 덱을 만들지 않는다.
- [ ] **AC-8 근거 검증 (Grounding)**: 모든 카드의 정답 핵심 토큰은 원문 블록에 실제로 있어야 한다. LLM이 만든 카드도 같은 검증을 거치며, 없는 내용은 **폐기**하고 `dropped_ungrounded` 건수를 보고한다.
- [ ] **AC-9 저신뢰 OCR**: 신뢰도가 기본 0.6 미만인 줄은 카드 소스에서 제외하고 `low_confidence_lines` 건수를 보고한다. 추정으로 보정하지 않는다.
- [ ] **AC-10 개인정보**: LLM 비전 폴백(이미지를 외부로 전송)은 요청에 `allow_cloud_vision=true`가 있고 서버 환경에 엔드포인트가 설정돼 있을 때만 쓴다. 기본은 OFF이고, 응답에 `provider`를 표기한다.

---

## 3. Architecture & Dependency Boundaries

### 3.1 서버 (Python, `dependencies = []` 유지 — 표준 라이브러리 전용)

```text
src/anki_studio/
├── domain/document_deck_builder.py   # [신규·순수] I/O 0, ai_learning·fsrs_math만 import
├── adapters/document_ingestor.py     # [신규] Port 구현: PDF 파서 · Apple Vision · LLM 비전
├── adapters/macos_ocr_helper/        # [신규] Swift CLI (Vision + PDFKit) → stdout JSON
├── service/studio_server.py          # [수정] 라우트 1개 + 서비스 메서드 1개
└── ui/static/{viewmodel.js,app.js,index.html}  # [수정, P2]
tests/
├── test_document_deck_builder_ddt.py # [신규]
├── test_document_ingestor.py         # [신규]
└── fixtures/document_golden/*.json   # [신규] Python↔Kotlin 공용 골든 벡터
```

**Domain 계약 (`document_deck_builder.py`)**
- `DocumentBlock(kind: heading|paragraph|list_item|table_row, text, page:int, confidence:float)` — frozen dataclass
- `ExtractedDocument(blocks: tuple[DocumentBlock,...], title_hint: str|None, source_kind: image|pdf, page_count:int)`
- `DeckPlan(deck_name, category, cards: tuple[SourcedCard,...], stats: BuildStats)`
- `SourcedCard(spec: GeneratedCardSpec, pattern: str, source_page: int, source_excerpt: str)` — 기존 `GeneratedCardSpec` 재사용
- 순수 함수: `infer_category(doc)`, `infer_deck_name(doc, user_name)`, `classify_block_pattern(block)`,
  `build_deck_plan(doc, user_deck_name, max_cards, min_confidence) -> DeckPlan`, `ground_cards(cards, doc) -> (kept, dropped)`
- 중복 제거: 앞면을 정규화(NFKC + 공백·구두점 제거 + 소문자)한 해시가 같으면 먼저 나온 카드를 남긴다.
- **금지 import**: `sqlite3, urllib, http, subprocess, os, pathlib, io` (기존 AST 경계 테스트 대상에 추가)

**Port (`document_ingestor.py` 상단 Protocol)**
```text
DocumentExtractorPort.extract(data: bytes, mime: str) -> ExtractionResult
ExtractionResult = ok(ExtractedDocument) | blocked(error_code, detail)
```
어댑터 체인 (페이지 단위, 순서 고정):
1. `StdlibPdfTextAdapter` — `/FlateDecode`(zlib) 스트림 + `Tj/TJ` 연산자 텍스트 추출. CID·ToUnicode 매핑을 못 풀면 그 페이지는 "텍스트 없음"으로 넘긴다. **추측 디코딩 금지.**
2. `AppleVisionOcrAdapter` — macOS에서만 `macos_ocr_helper`를 subprocess로 호출(`ko-KR, en-US`, 타임아웃 30s/문서). PDFKit으로 페이지를 렌더링해 Vision에 넘긴다. 비 macOS나 바이너리가 없으면 `unavailable`.
3. `LlmVisionAdapter` — AC-10 조건을 만족할 때만. 출력 JSON이 잘렸거나 스키마가 맞지 않으면 그 페이지를 BLOCKED 처리한다(부분 파싱 금지).
- 모든 호출은 `(provider, latency_ms, fallback_reason, error_code)` 구조화 로그를 남긴다.

**HTTP 계약 — `POST /api/ai/ingest-document`**
- 요청: **raw binary body** (`Content-Type: application/pdf | image/jpeg | image/png | image/heic`).
  쿼리: `deck_name?`, `max_cards=1..60 (기본 30)`, `auto_save=0|1`, `allow_cloud_vision=0|1`.
  multipart/`cgi` 모듈은 쓰지 않는다(3.13에서 제거됨). 상한은 `MAX_DOCUMENT_BYTES = 20MB`로 따로 두고, 기존 `MAX_JSON_BODY_BYTES`는 건드리지 않는다.
- 응답: `{status: "OK"|"BLOCKED", error_code, deck_id|null, deck_name, category, cards:[{front,back,note_type,pattern,source_page,source_excerpt}], stats:{pages, ocr_pages, low_confidence_lines, dropped_ungrounded, duplicates}, provider, latency_ms}`
- 미리보기 확정은 기존 노트 추가 경로로 하되, 덱 생성과 노트 N건을 단일 트랜잭션으로 넣는 `store.create_deck_with_notes(...)`를 신설한다(기존 `ensure_deck`+`add_note` 루프 금지 → AC-4).

### 3.2 Android (`android-app/`) — 네이티브 (하이브리드 WebView 아님)

```text
android-app/
├── settings.gradle.kts / build.gradle.kts (minSdk 26, targetSdk 최신, Kotlin 2.x, Compose BOM)
└── app/src/main/java/.../ankistudio/
    ├── domain/            # 순수 Kotlin (android.* import 0 — Gradle 모듈 분리 `:domain`, JVM 전용)
    │   ├── fsrs/Fsrs5.kt              # DEFAULT_FSRS5_WEIGHTS 19개 그대로 포팅
    │   └── deck/DocumentDeckBuilder.kt # Python 도메인 1:1 포팅
    ├── data/              # Room(SQLite) — 덱+노트 일괄 삽입은 @Transaction 단일 트랜잭션
    ├── ingest/            # Adapter: MlKitOcrAdapter(Korean recognizer), PdfRendererAdapter, ServerIngestAdapter(선택)
    └── ui/                # Compose + Material 3 · 화면별 ViewModel(StateFlow) · Composable은 상태 바인딩만
```
- **PDF 처리 사실관계**: `android.graphics.pdf.PdfRenderer`는 비트맵 렌더링만 하고 텍스트 레이어를 주지 않는다. 그래서 Android는 **모든 PDF 페이지를 렌더링한 뒤 OCR**한다(기본 200dpi 상당, 페이지당 메모리 상한 적용 후 즉시 `recycle`).
- OCR: ML Kit `text-recognition-korean`(라틴 문자 동시 인식)을 번들 모델로 넣어 **오프라인**으로 동작하게 한다. 블록 단위 신뢰도가 없을 수 있으므로, 줄/요소 신뢰도가 없으면 `confidence=null`로 두고 AC-9 판정에서 "미측정"으로 집계한다(1.0으로 둔갑시키지 않는다).
- 입력: CameraX 촬영, Photo Picker(`PickVisualMedia`), SAF(`OpenDocument` application/pdf). 저장소 권한은 요청하지 않는다.
- 서버 연동은 선택 사항이다: 서버 URL이 설정되고 사용자가 켰을 때만 `ServerIngestAdapter`를 쓴다. 기본은 완전 오프라인.
- `.apkg` 내보내기는 범위 밖(P4)이다.

---

## 4. Core Logic & State Transitions

수집 작업 상태 머신 (서버 응답·Android ViewModel 공통):
```text
IDLE → VALIDATING → EXTRACTING(page i/n) → BUILDING → PREVIEW → SAVING → SAVED
          └──────────────┴──────────────┴──────────→ BLOCKED(error_code)   (모든 단계에서 진입 가능, 종단)
```
- `EXTRACTING`: 페이지 단위로 PDF 텍스트를 먼저 시도하고, 없으면 OCR로 넘긴다. 한 페이지가 실패해도 나머지는 계속하지만, 성공 페이지가 0이면 BLOCKED.
- `BUILDING`: 블록 정규화(하이픈 줄바꿈 결합, 머리말/꼬리말 반복 줄 제거 — 3페이지 이상 동일 줄) → 패턴 분류 → 카드 생성 → grounding → 중복 제거 → `max_cards` 절단(패턴 다양성 우선 라운드로빈).
- LLM 카드 합성(선택)은 기존 `AICardSynthesizer` 체인을 재사용하고, 그 출력도 반드시 `ground_cards`를 통과해야 한다.

error_code 목록: `unsupported_mime, too_large, too_many_pages, encrypted_pdf, corrupt_file, ocr_unavailable, ocr_timeout, insufficient_text, no_cards, cloud_vision_disallowed, llm_truncated, db_write_failed`

---

## 5. Test Design (BDD + DDT + TDD)

명령: `cd ~/Documents/개발/Anki-Studio && python3.12 -m pytest -q` · Android: `./gradlew :domain:test :app:testDebugUnitTest`

| # | Given | When | Then |
|---|---|---|---|
| T1 | `용어: 정의` 블록 3개 | build | 정의 카드 3장, 각 카드에 `source_page`가 있다 |
| T2 | 번호 목록 1)~5) | build | 열거 카드 생성, 항목 누락 0 |
| T3 | `제12조 ① …` + 수치 `3nm` | build | 수치 Cloze 정답 = 원문 숫자+단위 |
| T4 | 원문에 없는 답을 담은 LLM 출력 | ground | 폐기, `dropped_ungrounded=1` |
| T5 | 신뢰도 0.59 / 0.60 / null 줄 | build | 0.59 제외, 0.60 포함(경계), null은 "미측정"으로 집계 |
| T6 | 텍스트 39자 / 40자 | build | 39 → BLOCKED `insufficient_text`, 40 → 진행 |
| T7 | 사용자 덱명 / 제목 메타 / 키워드만 / 아무것도 없음 | infer_deck_name | 우선순위대로, 마지막은 주입된 날짜(`now` 파라미터) |
| T8 | 암호화·손상·0페이지·51페이지·20MB+1B | ingest | 각 error_code, **DB 쓰기 호출 0회** |
| T9 | OCR 헬퍼 타임아웃 (fake subprocess) | ingest | BLOCKED `ocr_timeout`, 빈 성공 반환 없음 |
| T10 | `create_deck_with_notes` 중 3번째 노트에서 예외 | save | 덱·노트 모두 0건 (롤백) |
| T11 | 중복 앞면 2장 (공백·대소문자만 다름) | build | 1장, `duplicates=1` |
| T12 | `allow_cloud_vision=0` + OCR 불가 | ingest | LLM 어댑터 호출 0회, BLOCKED |
| T13 | 도메인 모듈 AST | import 검사 | 금지 import 0 (기존 경계 테스트 확장) |
| T14 | `fixtures/document_golden/*.json` | Python·Kotlin 양쪽 build | 카드 목록이 바이트 단위로 같다 (FSRS 골든 벡터도 동일 방식) |

- 시간·OCR·subprocess·HTTP는 전부 주입한다(fake). 실제 Vision/ML Kit 호출은 수동 스모크 체크리스트로 분리한다.
- 뮤테이션 확인: grounding 가드나 신뢰도 비교(`<` ↔ `<=`)를 뒤집으면 T4/T5가 Red가 되어야 한다.

---

## 6. Out of Scope / Do NOT

- 서버에 서드파티 패키지 추가 금지(pypdf, PyMuPDF, Pillow, Tesseract 등). `dependencies = []` 유지.
- AGPL 코드(Anki 원본, AnkiDroid) 복사·참조 구현 금지 — 클린룸 원칙 유지.
- Android WebView 하이브리드로 기존 웹 UI를 감싸는 방식 금지(네이티브 Compose로 결정됨).
- 이미지 원본의 장기 보관 금지. 처리 후 메모리/임시파일을 폐기하고, 카드에는 발췌 텍스트만 남긴다.
- 클라우드 계정·동기화·결제·`.apkg` Android 내보내기는 이번 범위 밖이다.
- OCR 오탈자 자동 "교정"(LLM으로 원문 재작성) 금지 — grounding 기준이 무너진다.
