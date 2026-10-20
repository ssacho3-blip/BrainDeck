"""Architectural & structural contract tests for the native Android project (android-app/) and Web UI safety."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANDROID_ROOT = PROJECT_ROOT / "android-app"


def test_android_domain_module_has_zero_android_imports() -> None:
    """The :domain Kotlin module must remain 100% pure JVM Kotlin with zero android.* or androidx.* imports."""
    domain_src = ANDROID_ROOT / "domain" / "src" / "main" / "kotlin"
    kt_files = sorted(domain_src.rglob("*.kt"))
    assert len(kt_files) >= 3, "Expected Fsrs5Engine.kt, DocumentDeckBuilder.kt, and AdaptiveQuizEngine.kt in :domain"

    for kt_file in kt_files:
        source = kt_file.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                assert not stripped.startswith("import android."), (
                    f"Forbidden android.* import in pure :domain file {kt_file.name}: {stripped}"
                )
                assert not stripped.startswith("import androidx."), (
                    f"Forbidden androidx.* import in pure :domain file {kt_file.name}: {stripped}"
                )


def test_android_document_ingestor_enforces_pdfrenderer_recycle_guards_and_nullable_confidence() -> None:
    """AndroidDocumentIngestor must enforce 20MB & 50-page BLOCKED guards, recycle bitmaps, implement Closeable, and preserve nullable confidence."""
    ingestor_file = (
        ANDROID_ROOT
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "ingest"
        / "AndroidDocumentIngestor.kt"
    )
    assert ingestor_file.exists()
    content = ingestor_file.read_text(encoding="utf-8")

    assert "PdfRenderer" in content
    assert "KoreanTextRecognizerOptions" in content
    assert "bitmap.recycle()" in content
    assert "rawConfidence?.toDouble()" in content
    assert "?: 1.0" not in content
    assert "MAX_DOCUMENT_BYTES" in content
    assert '"too_large"' in content
    assert "resolveUriByteSizeFailClosed" in content
    assert "pageCount > MAX_PDF_PAGES" in content
    assert '"too_many_pages"' in content
    assert "coerceAtMost(MAX_PDF_PAGES)" not in content
    assert "Closeable" in content
    assert "recognizer.close()" in content


def test_android_kotlin_domain_behavioral_parity_and_symbol_consistency() -> None:
    """Verify DocumentDeckBuilder.kt and Fsrs5Engine.kt implement all parity features and match :app imports."""
    builder_kt = (
        ANDROID_ROOT
        / "domain"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "ankistudio"
        / "domain"
        / "deck"
        / "DocumentDeckBuilder.kt"
    ).read_text(encoding="utf-8")
    fsrs_kt = (
        ANDROID_ROOT
        / "domain"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "ankistudio"
        / "domain"
        / "fsrs"
        / "Fsrs5Engine.kt"
    ).read_text(encoding="utf-8")
    vm_kt = (
        ANDROID_ROOT
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "ui"
        / "AnkiStudioViewModel.kt"
    ).read_text(encoding="utf-8")
    main_kt = (
        ANDROID_ROOT
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "ui"
        / "MainActivity.kt"
    ).read_text(encoding="utf-8")

    # Behavioral parity features in DocumentDeckBuilder.kt
    assert "fun stripRepeatedHeadersFooters(" in builder_kt
    assert "fun selectBalancedCards(" in builder_kt
    assert "FALLBACK_NOUN_RE" in builder_kt
    assert "isTokenGroundedOnPage(" in builder_kt
    assert "fun buildDeckPlan(" in builder_kt

    # Cloze support in Fsrs5Engine.kt & MainActivity.kt
    assert "fun extractClozeOrdinals(" in fsrs_kt
    assert "fun renderClozeCard(" in fsrs_kt
    assert "Fsrs5Engine.renderClozeCard(" in main_kt

    # ViewModel lifecycle & preview editing
    assert "ViewModelProvider.Factory" in vm_kt
    assert "override fun onCleared()" in vm_kt
    assert "fun updatePreviewCard(" in vm_kt
    assert "Fsrs5Engine.stepFsrs(" in vm_kt


def test_android_room_database_atomic_transactions_and_fk_integrity() -> None:
    """AnkiStudioDatabase must use @Transaction for batch deck creation, preserve sourceExcerpt/noteId, and expand Cloze ordinals."""
    db_file = (
        ANDROID_ROOT
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "data"
        / "AnkiStudioDatabase.kt"
    )
    assert db_file.exists()
    content = db_file.read_text(encoding="utf-8")

    assert "@Transaction" in content
    assert "suspend fun createDeckWithGeneratedCards(" in content
    assert "suspend fun recordCardReview(" in content
    assert "val noteId: Long" in content
    assert "val sourceExcerpt: String" in content
    assert "Fsrs5Engine.extractClozeOrdinals(" in content
    assert "version = 2" in content
    assert "MIGRATION_1_2" in content
    assert "val quizStage: Int" in content
    assert "val consecutiveSuccesses: Int" in content
    assert "val queue: Int" in content


def test_android_adaptive_quiz_engine_and_t4_fsrs_contracts() -> None:
    """Verify AdaptiveQuizEngine.kt implements T16, T17, T18, T22, T23 and Fsrs5Engine.kt enforces T4."""
    quiz_kt = (
        ANDROID_ROOT
        / "domain"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "ankistudio"
        / "domain"
        / "quiz"
        / "AdaptiveQuizEngine.kt"
    ).read_text(encoding="utf-8")
    fsrs_kt = (
        ANDROID_ROOT
        / "domain"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "ankistudio"
        / "domain"
        / "fsrs"
        / "Fsrs5Engine.kt"
    ).read_text(encoding="utf-8")

    assert "fun gradeInteraction(" in quiz_kt
    assert "fun selectDistractors(" in quiz_kt
    assert "fun preserveCjkCompatBeforeNfc(" in quiz_kt
    assert "fun gradeDictationJamo(" in quiz_kt
    assert 'if (memory.state == "review")' in fsrs_kt


def test_web_ui_preview_has_no_innerhtml_xss_and_ocr_helper_preserves_confidence() -> None:
    """Verify app.js uses textContent/input.value for preview cards (no innerHTML XSS) and ocr_helper.m does not fabricate 0.85 confidence."""
    app_js = (PROJECT_ROOT / "src" / "anki_studio" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    assert "itemDiv.innerHTML" not in app_js
    assert "listEl.innerHTML" not in app_js

    ocr_m = (
        PROJECT_ROOT / "src" / "anki_studio" / "adapters" / "macos_ocr_helper" / "ocr_helper.m"
    ).read_text(encoding="utf-8")
    assert "conf = 0.85" not in ocr_m


def test_android_builtin_curriculum_catalog_and_ui_wiring() -> None:
    """Verify BuiltInCurriculumCatalog.kt provides Dong-A Yoon Mid-1 8 lessons and Hanja grades 8~3 and is wired into ViewModel and MainActivity."""
    catalog_kt = (
        ANDROID_ROOT
        / "domain"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "ankistudio"
        / "domain"
        / "catalog"
        / "BuiltInCurriculumCatalog.kt"
    ).read_text(encoding="utf-8")
    vm_kt = (
        ANDROID_ROOT
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "ui"
        / "AnkiStudioViewModel.kt"
    ).read_text(encoding="utf-8")
    main_kt = (
        ANDROID_ROOT
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "ankistudio"
        / "app"
        / "ui"
        / "MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert '"kr.mid1.eng.donga_yoon.2022"' in catalog_kt
    assert "윤정미" in catalog_kt
    for grade in ["8geup", "7geup", "6geup", "5geup", "4geup", "3geup"]:
        assert f'"hanja-grade:{grade}"' in catalog_kt
    assert "fun generateExamScopeDeck()" in vm_kt
    assert "fun generateCollectionDeck()" in vm_kt
    assert "BuiltInCurriculumCatalog.buildExamScopeDeckPlan" in vm_kt
    assert "BuiltInCurriculumCatalog.buildCollectionDeckPlan" in vm_kt
    assert "onGenerateExamScopeDeck" in main_kt
    assert "onGenerateCollectionDeck" in main_kt

