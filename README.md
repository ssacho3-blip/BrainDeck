# 🧠 Anki Studio 2.0 — FSRS-5 & AI Active Recall Edition

> **🥈 제 2 SW 개발항목 (2nd In-House & Commercial SW Track)**
> - **독립 워크스페이스**: `/Users/choyoungseo/Documents/개발/Anki-Studio`
> - **노션 마스터 설계서**: [🥈 [제 2 SW 개발항목 · ANKI-1019-02] Anki Studio 마스터 설계서](https://app.notion.com/p/3fee1e1a10378166b23ce99ec8d0fdd2)
> - **라이선스**: **100% Clean-Room Proprietary Ready** (AGPLv3 코드 0건 · 순수 학술 수식 및 Python 표준 라이브러리 기반)

---

## 1. 기존 Anki의 6대 치명적 단점 완벽 극복 & AI 기능 도입 매트릭스

| # | 기존 Anki (SM-2 / Qt)의 고질적 단점 | Anki Studio 2.0의 엔지니어링 & AI 해법 | 구현 모듈 |
| :-: | :--- | :--- | :--- |
| **1** | **Ease Hell (난이도 지옥)**<br>1987년식 SM-2 알고리즘에서 `Again/Hard`를 몇 번 누르면 Ease가 130%로 추락해 영원히 복습 간격이 안 늘어남 | **FSRS-5 (DSR 3변수 기억 모델 + 평균 회귀)**<br>난이도($D$) 평균 회귀($D_0(4)$ 지수 보간)로 Ease Hell 원천 차단 + 목표 기억률(`90%`) 기준 복습량 **30% 절감** | `domain/fsrs_math.py`<br>(`step_fsrs`, `next_difficulty`) |
| **2** | **휴가/출장 후 '복습 폭탄' (Review Bomb)**<br>며칠만 쉬어도 수백 장이 쌓여 학습 의욕 상실 및 포기 유발 | **🏖️ Smart Backlog Decompressor (복습 폭탄 평탄화)**<br>현재 인출확률 $R(t, S)$과 난이도 위험도를 계산해 오늘 가장 시급한 `daily_cap`장만 남기고 나머지는 `horizon_days`로 안전 분산 | `domain/fsrs_math.py`<br>(`plan_backlog_decompression`)<br>`POST /api/backlog/decompress` |
| **3** | **주관적 자기 채점의 착각 (Illusion of Competence)**<br>뒷면 정답을 눈으로만 보고 "아, 알던 거네"라며 `Good`을 누르는 수동적 인식 오류 | **🎯 AI 능동 인출 채점기 (Objective Free-Recall Evaluator)**<br>사용자가 타이핑/발화한 답변의 핵심 의미 토큰·수치/단위(`3nm`, `GAA`)·부정어 충돌을 분석해 **0~100% 채점 및 `Again/Hard/Good/Easy` 객관 추천** | `domain/ai_learning.py`<br>(`evaluate_free_recall`)<br>`POST /api/ai/evaluate` |
| **4** | **거머리 카드 (Leech) 무방비 방치**<br>계속 틀리는 복합 카드를 방치하거나 단순 정지(Suspend)시켜 기억 구멍 발생 | **🧭 AI 소크라테스 힌트 튜터 & 🧬 AI Leech 원자 분할기**<br>정답 스포일러 없이 단계별 단서/연상법(Mnemonic)을 제시하고, `lapses >= 2` 거머리 카드는 **원자적 단일 개념 마이크로 카드들로 자동 쪼개기** | `domain/ai_learning.py`<br>(`generate_socratic_hint`, `decompose_leech_card`) |
| **5** | **수동 카드 제작 노가다 (Card Creation Pain)**<br>노트 정리 후 빈칸(`{{c1::...}}`)과 앞/뒷면을 일일이 수작업으로 만들어야 함 | **✨ AI Zero-Effort 카드 팩토리 (LLM + 무결성 NLP 하이브리드)**<br>영어회화 노트, 반도체/AI 텍스트, `용어: 정의`, `한국어 -> 영어` 문장을 붙여넣으면 **Cloze·Q&A·Speaking 카드 자동 생성** | `adapters/ai_engine.py`<br>(`AICardSynthesizer`)<br>`POST /api/ai/generate-cards` |
| **6** | **노후화된 UI & 모바일 유료 장벽 ($24.99)**<br>2000년대풍 Qt UI, 복잡한 설정, iOS 앱 유료 결제 필요 | **💎 다크 글래스모피즘 스튜디오 UI + `Anki Studio.app` + `.apkg` 양방향 호환**<br>원어민 TTS(`T`), 단축키(`Space`, `1~4`, `H`), 실시간 망각곡선 SVG, 기존 `.apkg` 무손실 Import/Export 기본 내장 | `ui/static/*`<br>`macos_app/main.m`<br>`Anki Studio.app` |

---

## 2. 디렉터리 구조 (Clean / Hexagonal Architecture + MVVM)

```text
Anki-Studio/
├── Anki Studio.app/                    # macOS Universal 네이티브 앱 번들 (arm64 + x86_64)
├── README.md                           # 프로젝트 개요 및 실행 가이드
├── pyproject.toml                      # 패키지 및 pytest 설정
├── docs/
│   └── Anki_Studio_Master_Spec.md      # FSRS-5 수식 · AI Active Recall · 아키텍처 상세 설계서
├── src/
│   └── anki_studio/
│       ├── __init__.py
│       ├── domain/                     # [Pure Domain Layer] 외부 I/O 0건 (AST 강제 검증)
│       │   ├── __init__.py
│       │   ├── fsrs_math.py            # FSRS-5 (DSR) 스케줄러 · Cloze 파서 · 복습 폭탄 평탄화 수식
│       │   └── ai_learning.py          # AI 능동 인출 채점 · 소크라테스 힌트 · Leech 원자 분할 · 스마트 추출
│       ├── adapters/                   # [Infrastructure / Hexagonal Adapter Layer]
│       │   ├── __init__.py
│       │   ├── sqlite_store.py         # SQLite WAL 단일 원장 (BEGIN IMMEDIATE) & .apkg 양방향 코덱
│       │   └── ai_engine.py            # LLM 엔드포인트 연동 + Fail-Closed 결정론적 NLP 카드 합성기
│       ├── service/                    # [Application / HTTP Engine Layer]
│       │   ├── __init__.py
│       │   └── studio_server.py        # REST API & Web UI 서버 (127.0.0.1:4390)
│       └── ui/                         # [Presentation MVVM Layer]
│           └── static/
│               ├── viewmodel.js        # 순수 함수 기반 Presentation ViewModel (DOM 의존성 0)
│               ├── app.js              # 이벤트 바인딩 · Web Speech TTS · AI 튜터 컨트롤러
│               └── index.html          # 다크 글래스모피즘 반응형 스튜디오 UI
├── macos_app/                          # Cocoa WKWebView 네이티브 macOS 앱 소스 (main.m, Info.plist)
└── tests/
    └── test_fsrs_domain.py             # 29개 ATDD / BDD / DDT 단위·통합 및 Clean Architecture 경계 테스트
```

---

## 3. 실행 및 테스트 가이드

### ① 네이티브 macOS 앱 실행
```bash
open "/Users/choyoungseo/Documents/개발/Anki-Studio/Anki Studio.app"
```

### ② 웹 서버 단독 실행 (브라우저 / 모바일 연동)
```bash
PYTHONPATH=src python3 -m anki_studio.service.studio_server
# 브라우저에서 http://127.0.0.1:4390 접속
```

### ③ 전체 테스트 스위트 실행 (29/29 통과)
```bash
pytest tests/ -v
```
