# 🧠 Anki Studio 1.0 — FSRS-5 & AI Active Recall Edition

> **🥈 제 2 SW 개발항목 (2nd In-House & Commercial SW Track)**
> - **독립 워크스페이스**: `/Users/choyoungseo/Documents/개발/Anki-Studio`
> - **노션 마스터 설계서**: [🥈 [제 2 SW 개발항목 · ANKI-1019-02] Anki Studio 마스터 설계서](https://app.notion.com/p/3fee1e1a10378166b23ce99ec8d0fdd2)
> - **라이선스**: **100% Clean-Room Proprietary Ready** (AGPLv3 코드 0건 · 순수 학술 수식 및 Python 표준 라이브러리 기반)

---

## 1. 프로젝트 개요 (Why Anki Studio?)

기존 Anki(Desktop Qt / AnkiMobile)의 **4대 고질적 한계(1987년식 SM-2 알고리즘의 복습 폭탄, 수동 카드 타이핑의 고통, 노후화된 Qt UI 및 iOS 유료 장벽, AGPLv3 라이선스)**를 해결하기 위해 Clean-Room 방식으로 설계된 **차세대 간격반복(Spaced Repetition) & AI 액티브 리콜 스튜디오**입니다.

### ✨ 5대 핵심 기능
1. **FSRS-5 (DSR Memory Model) 순수 수학 스케줄러 (`src/anki_studio/domain/fsrs_math.py`)**:
   - 기억의 **난이도($D$, Difficulty)**, **안정성($S$, Stability)**, **인출확률($R$, Retrievability)** 3변수 미분방정식을 통해 목표 기억 유지율(기본 `90%`)을 달성하면서 기존 SM-2 대비 **복습 횟수를 약 25~35% 절감**합니다.
2. **기존 Anki `.apkg` 덱 100% 무손실 호환 (`src/anki_studio/adapters/apkg_codec.py`)**:
   - 기존에 사용하던 Anki `.apkg` 파일(단어장, 의학/공학 덱, 오디오/이미지 미디어 포함)을 드래그-앤-드롭으로 즉시 Import / Export 합니다.
3. **AI Zero-Effort 카드 팩토리 (영어회화 & 반도체/딥테크 특화)**:
   - 노션 `영어회화` DB (`내 실수 패턴`, `핵심 배운 표현`, `스크립트 암기`) 및 `반도체/AI 핸드북`, PDF/Markdown 문서를 읽어 **Cloze(`{{c1::정답::힌트}}`)·Q&A·오답 교정 카드**를 자동 생성합니다.
4. **멀티모달 학습 도구 (Native TTS + KaTeX + Image Occlusion)**:
   - 영어 문장 원어민 발음 자동 재생 & 쉐도잉 드릴, 반도체 물성/딥러닝 수식(`KaTeX`) 렌더링, 공정 단면도/아키텍처 다이어그램 **Image Occlusion(이미지 빈칸 가리기)** 기본 탑재.
5. **macOS 네이티브 앱 (`Anki Studio.app`) + 모바일 웹(PWA) 무과금 연동**:
   - 맥에서는 Cocoa `WKWebView` 기반 네이티브 데스크톱 앱으로, 아이폰/아이패드에서는 유료 앱($24.99) 구매 없이 브라우저/PWA로 동일한 학습 원장(`anki_studio.sqlite`)을 실시간 학습합니다.

---

## 2. 디렉터리 구조 (Clean Architecture + MVVM)

```text
Anki-Studio/
├── README.md                           # 프로젝트 개요 및 실행 가이드
├── pyproject.toml                      # 패키지 및 pytest 설정
├── docs/
│   └── Anki_Studio_Master_Spec.md      # FSRS-5 수식 · .apkg 규격 · 아키텍처 상세 설계서
├── src/
│   └── anki_studio/
│       ├── __init__.py
│       ├── domain/                     # [Pure Domain Layer] 외부 I/O 0건 (AST 강제)
│       │   ├── __init__.py
│       │   └── fsrs_math.py            # FSRS-5 (DSR) 스케줄러 · Cloze 파서 · 기억곡선 예측
│       ├── adapters/                   # [Infrastructure / Adapter Layer]
│       │   ├── __init__.py
│       │   └── sqlite_store.py         # SQLite WAL 단일 원장 (BEGIN IMMEDIATE) & .apkg 코덱
│       ├── service/                    # [Application / HTTP Engine Layer]
│       │   └── __init__.py
│       └── ui/                         # [Presentation MVVM Layer]
│           └── static/                 # viewmodel.js (순수 상태), app.js, index.html
├── macos_app/                          # Cocoa WKWebView 네이티브 macOS 앱 래퍼 (Anki Studio.app)
└── tests/
    └── test_fsrs_domain.py             # ATDD / BDD / DDT 단위 및 아키텍처 경계 테스트
```

---

## 3. 빠른 테스트 실행

```bash
pytest tests/ -v
```
