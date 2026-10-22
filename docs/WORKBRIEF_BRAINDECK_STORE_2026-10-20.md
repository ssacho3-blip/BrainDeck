# 📋 Implementation Contract: BrainDeck Rebranding + Apple Self-Contained PWA + Cross-Platform BrainPack Store

- **Brief ID**: `WORKBRIEF-BRAINDECK-STORE-2026-10-20`
- **Scale**: Track M (`FULL` Pipeline)
- **Target Platforms**:
  1. **Apple (iOS / iPadOS / macOS)**: Web-App / Standalone Offline-First PWA (`index.html`, `manifest.json`, `viewmodel.js`, `app.js`) + `BrainDeck.app`
  2. **Android (`android-app/`)**: Kotlin `:domain` (`BrainPackStoreCatalog.kt`) + `:app` Compose UI & Room persistence (`AnkiStudioDatabase.kt`, `AnkiStudioViewModel.kt`, `MainActivity.kt`)
  3. **Backend / Core Engine (`src/anki_studio/`)**: Pure domain `domain/pack_store.py` + `adapters/reference_pack_store.py` (`store_entitlements`) + `service/studio_server.py` (`/api/store/packs`, `/api/store/purchase`, `/api/bundle/offline-snapshot`)

---

## 1. Acceptance Criteria (ATDD)

1. **AC-1 (Rebranding to BrainDeck & BrainPack)**:
   - User-facing brand across Web UI, manifest, macOS app, Android Compose UI, and documentation is updated to **BrainDeck (브레인덱)** and **BrainPack Store (브레인팩 스토어)**.
   - Internal Python (`anki_studio`) and Kotlin (`com.ankistudio`) package namespaces remain intact so all existing unit/integration/contract tests pass without regression.
2. **AC-2 (Pure Domain BrainPack Store Engine — Zero I/O & 1:1 Python/Kotlin Parity)**:
   - `src/anki_studio/domain/pack_store.py` and `android-app/domain/.../catalog/BrainPackStoreCatalog.kt` have zero external I/O (`sqlite3`, `android.*`, `androidx.*` forbidden).
   - Supports free starter packs (`is_free_starter=True`, `price_krw=0`) + user self-upload (camera/PDF/text) for free, while offering 8 curated commercial BrainPacks (`price_krw` 990~1,900 KRW micro-pricing) covering middle/high school textbooks (`₩990`), Hanja grades 7~3 & Korean History (`₩1,500`), and TOEIC/JLPT & Law/IT certifications (`₩1,900`).
3. **AC-3 (Atomic Purchase, Entitlement Persistence & Instant Deck Mounting)**:
   - `GET /api/store/packs` returns all store packs with live `unlocked` status, `price_krw`, `sample_cards`, and summary stats.
   - `POST /api/store/purchase` atomically records the entitlement in `store_entitlements` (idempotent on repeat calls) and optionally materializes the purchased BrainPack into an active study deck inside the app immediately.
4. **AC-4 (Apple Web/PWA Self-Contained Offline Capability)**:
   - `index.html` and `manifest.json` configure iOS/iPadOS standalone Web App mode (`apple-mobile-web-app-capable`, `apple-mobile-web-app-title="BrainDeck"`).
   - `GET /api/bundle/offline-snapshot` and client-side `BrainDeckLocalVault` (`localStorage` snapshot + client-side FSRS-5 fallback) ensure that all unlocked BrainPacks and decks remain accessible and playable inside the app even if the network/server disconnects.
5. **AC-5 (Android Native App Parity)**:
   - `:domain` `BrainPackStoreCatalog.kt` and `:app` `AnkiStudioViewModel.kt` + `MainActivity.kt` provide the In-App BrainPack Store UI, category filter chips, and 1-Click purchase/unlock & deck creation.
