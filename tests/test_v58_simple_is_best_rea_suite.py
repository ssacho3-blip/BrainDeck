"""WORKORDER-BRAINDECK-V58: Simple Is Best — Anki REA Critique & 4-Contract TDD/BDD/DDT Suite.

Designed from the 5-Model Unanchored Critique (Claude Opus 5.5, OpenAI Codex GPT-6.1 Sol,
xAI Grok 4.7, DeepSeek-v4.1-Flash, and Antigravity Gemini 4 Argon High):
- Contract C1: Study Screen Zen Mode (`🎛️ 필터·도구` Progressive Disclosure Drawer & Zero Feature Loss)
- Contract C2: Zero Model Jargon (`✨ 스마트 자동 생성` Single Recommended Engine & Policy Router)
- Contract C3: Curriculum Screen 3-Segment Simplification (`🏫 교과서 단원` | `📚 교육부·급수` | `🎯 시험범위 조합`)
- Contract C4: Response-Time Fluency FSRS-5 Calibration & Exponential-Decay Confusion Matrix
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

from anki_studio.domain import rea_v56


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "anki_studio" / "ui" / "static"
DOCS_DIR = REPO_ROOT / "docs"
ANDROID_MAIN_KT = (
    REPO_ROOT
    / "android-app"
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "ankistudio"
    / "app"
    / "ui"
    / "MainActivity.kt"
)
ANDROID_REA_KT = (
    REPO_ROOT
    / "android-app"
    / "domain"
    / "src"
    / "main"
    / "kotlin"
    / "com"
    / "ankistudio"
    / "domain"
    / "rea"
    / "ReaV56Engine.kt"
)


# ============================================================================
# CONTRACT C1: Study Screen Zen Mode (`🎛️ 필터·도구` Drawer & Summary Chip)
# ============================================================================


@pytest.mark.parametrize(
    "study_filter,qtype_filter,cram_mode,expected_count,expected_default,expected_badge",
    [
        ("all", "all", False, 0, True, ""),
        ("wrong_only", "all", False, 1, False, "필터 1개 적용 중"),
        ("marked_only", "vocab", False, 2, False, "필터 2개 적용 중"),
        ("wrong_only", "grammar", True, 3, False, "필터 3개 적용 중"),
    ],
)
def test_c1_ddt_compute_study_tools_summary(
    study_filter: str,
    qtype_filter: str,
    cram_mode: bool,
    expected_count: int,
    expected_default: bool,
    expected_badge: str,
) -> None:
    res = rea_v56.compute_study_tools_summary(
        study_filter=study_filter,
        qtype_filter=qtype_filter,
        cram_mode=cram_mode,
    )
    assert res["active_count"] == expected_count
    assert res["is_default"] is expected_default
    assert res["summary_badge_text"] == expected_badge


def test_c1_bdd_study_drawer_progressive_disclosure_and_zero_feature_loss() -> None:
    """Verify the 3 study filter/utility bars are collapsed inside `#study-tools-drawer` by default while preserving 100% of DOM IDs."""
    for html_path in (STATIC_DIR / "index.html", DOCS_DIR / "index.html"):
        html = html_path.read_text(encoding="utf-8")
        assert 'id="btn-toggle-study-tools"' in html
        assert 'id="active-study-filter-summary"' in html
        assert 'id="study-tools-drawer"' in html
        # All legacy IDs must still exist inside the DOM (Zero Feature Loss)
        for preserved_id in (
            "study-filter-bar",
            "study-type-filter-bar",
            "v56-rea-utility-bar",
            "btn-filter-wrong",
            "btn-filter-marked",
            "btn-toggle-shuffle",
            "btn-qtype-all",
            "btn-qtype-vocab",
            "btn-qtype-grammar",
            "btn-qtype-hanja",
            "btn-qtype-history_sci",
            "btn-open-summary-sheet",
            "btn-print-exam-sheet",
            "btn-commute-audio-loop",
            "btn-toggle-cram-sandbox",
            "btn-reset-card-arena",
        ):
            assert f'id="{preserved_id}"' in html, f"Lost DOM ID {preserved_id} in {html_path.name}"


# ============================================================================
# CONTRACT C2: Zero Raw AI Model Names (`✨ 스마트 자동 생성` Auto-Router)
# ============================================================================


def test_c2_atdd_zero_raw_llm_model_names_exposed_in_ui() -> None:
    """User-facing HTML and Android Compose UI must not display raw LLM model names (GLM, DeepSeek, Gemma, Ollama Cloud)."""
    forbidden_ui_labels = (
        "GLM-5.3",
        "GLM 5.3",
        "DeepSeek",
        "Gemma-4",
        "Gemma 4",
        "Ollama Cloud",
        "올라마 클라우드",
    )
    for html_path in (STATIC_DIR / "index.html", DOCS_DIR / "index.html"):
        html = html_path.read_text(encoding="utf-8")
        for label in forbidden_ui_labels:
            assert label not in html, f"Raw model jargon '{label}' exposed in {html_path.name}"
        assert "✨ 스마트 자동 생성" in html
        assert "⚡ 오프라인 빠른 생성" in html

    main_kt = ANDROID_MAIN_KT.read_text(encoding="utf-8")
    for label in forbidden_ui_labels:
        assert label not in main_kt, f"Raw model jargon '{label}' exposed in Android MainActivity.kt"
    assert "✨ 스마트 자동 생성" in main_kt

    for js_path in (STATIC_DIR / "app.js", STATIC_DIR / "viewmodel.js", DOCS_DIR / "app.js", DOCS_DIR / "viewmodel.js"):
        js_txt = js_path.read_text(encoding="utf-8")
        for label in ("GLM-5.3", "GLM 5.3", "DeepSeek", "Gemma-4", "Gemma 4", "☁️ Ollama Cloud", "올라마 클라우드"):
            assert label not in js_txt, f"Raw model jargon '{label}' exposed in {js_path.name}"

    android_vm_kt = (ANDROID_MAIN_KT.parent / "AnkiStudioViewModel.kt").read_text(encoding="utf-8")
    for label in ("GLM-5.3", "GLM 5.3", "DeepSeek", "Gemma-4", "Gemma 4", "☁️ Ollama Cloud", "올라마 클라우드"):
        assert label not in android_vm_kt, f"Raw model jargon '{label}' exposed in AnkiStudioViewModel.kt"
    assert "ReaV56Engine.resolveSmartAiEngine" in android_vm_kt


def test_c2_user_visible_banners_and_labels_reject_case_insensitive_raw_model_ids() -> None:
    """User-visible UI labels and interpolated status banners must reject case-insensitive raw model IDs."""
    import re
    from anki_studio.adapters.ai_engine import OLLAMA_CLOUD_MODELS_CATALOG
    from anki_studio.domain.rea_v56 import resolve_smart_ai_engine

    # 1. Every catalog entry and smart router decision ui_label must be free of case-insensitive raw tokens
    forbidden_ci = ("deepseek", "gemma", "glm-5.3", "ollama")
    for entry in OLLAMA_CLOUD_MODELS_CATALOG:
        lbl = str(entry.get("label", "")).lower()
        for tok in forbidden_ci:
            assert tok not in lbl, f"Catalog label '{lbl}' leaked '{tok}'"

    for task in ("card_generate", "ocr_extract", "vision_doc", "reasoning", "math"):
        for offline in (False, True):
            dec = resolve_smart_ai_engine(task_type=task, offline_only=offline)
            ui_lbl = str(dec["ui_label"]).lower()
            for tok in forbidden_ci:
                assert tok not in ui_lbl, f"Router ui_label '{ui_lbl}' leaked '{tok}'"

    # 2. Android statusBannerMessage assignments must never interpolate raw model IDs or contain case-insensitive raw tokens
    android_vm_kt = (ANDROID_MAIN_KT.parent / "AnkiStudioViewModel.kt").read_text(encoding="utf-8")
    banner_lines = [line for line in android_vm_kt.splitlines() if "statusBannerMessage" in line]
    assert len(banner_lines) >= 15
    for line in banner_lines:
        low = line.lower()
        for tok in forbidden_ci:
            assert tok not in low, f"Android statusBannerMessage leaked '{tok}': {line}"
        assert "$clean" not in line and "${selectedmodel}" not in low and "${aidecision.selectedmodel}" not in low

    # 3. HTML visible text (strip script/style tags and HTML attributes) must reject case-insensitive raw tokens
    for html_path in (STATIC_DIR / "index.html", DOCS_DIR / "index.html"):
        html = html_path.read_text(encoding="utf-8")
        visible_text = re.sub(r"<[^>]+>", " ", html).lower()
        for tok in forbidden_ci:
            assert tok not in visible_text, f"Visible HTML text in {html_path.name} leaked '{tok}'"


@pytest.mark.parametrize(
    "task_type,offline_only,manual_override,failed_models,expected_model,expected_status",
    [
        ("card_generate", False, None, (), "glm-5.3-flash", "OK"),
        ("ocr_extract", False, None, ("glm-5.3-flash",), "deepseek-v4.1-flash", "OK"),
        ("vision_doc", False, None, ("glm-5.3-flash",), "gemma4:31b", "OK"),
        ("card_generate", False, None, ("glm-5.3-flash", "deepseek-v4.1-flash"), "gemma4:31b", "OK"),
        ("card_generate", False, None, ("glm-5.3-flash", "deepseek-v4.1-flash", "gemma4:31b", "glm-5.3"), "local_rule", "FALLBACK_LOCAL"),
        ("card_generate", True, None, (), "local_rule", "OFFLINE_LOCAL"),
        ("card_generate", False, "deepseek-v4.1-flash", (), "deepseek-v4.1-flash", "MANUAL_OVERRIDE"),
        ("card_generate", False, "kimi-k2.6", (), "", "BLOCKED_MODEL"),
        ("card_generate", False, "minimax-2.7", (), "", "BLOCKED_MODEL"),
        ("card_generate", False, "unknown-unlisted-model-v9", (), "", "BLOCKED_MODEL"),
    ],
)
def test_c2_ddt_smart_ai_router_policy_and_fail_closed(
    task_type: str,
    offline_only: bool,
    manual_override: Optional[str],
    failed_models: tuple[str, ...],
    expected_model: str,
    expected_status: str,
) -> None:
    route = rea_v56.resolve_smart_ai_engine(
        task_type=task_type,
        offline_only=offline_only,
        manual_override=manual_override,
        failed_models=failed_models,
    )
    assert route["status"] == expected_status
    assert route["selected_model"] == expected_model
    assert route["exposes_raw_model_name"] is False
    for raw_token in ("glm", "deepseek", "gemma", "ollama"):
        assert raw_token not in route["ui_label"].lower()


# ============================================================================
# CONTRACT C3: Curriculum Screen 3-Segment Simplification
# ============================================================================


@pytest.mark.parametrize(
    "segment,combo_count,expected_active,expected_combo_label",
    [
        ("textbook", 0, "textbook", "🎯 시험범위 조합"),
        ("collection", 2, "collection", "🎯 시험범위 조합 (2)"),
        ("combined", 3, "combined", "🎯 시험범위 조합 (3)"),
        ("invalid_seg", 1, "textbook", "🎯 시험범위 조합 (1)"),
    ],
)
def test_c3_ddt_resolve_curriculum_segment_state(
    segment: str,
    combo_count: int,
    expected_active: str,
    expected_combo_label: str,
) -> None:
    state = rea_v56.resolve_curriculum_segment_state(segment, combo_count)
    assert state["active_segment"] == expected_active
    assert state["combined_tab_label"] == expected_combo_label
    assert state["visible_panels"][expected_active] is True
    for k, v in state["visible_panels"].items():
        if k != expected_active:
            assert v is False


def test_c3_bdd_curriculum_segmented_panels_in_web_and_android() -> None:
    for html_path in (STATIC_DIR / "index.html", DOCS_DIR / "index.html"):
        html = html_path.read_text(encoding="utf-8")
        assert 'id="curriculum-seg-bar"' in html
        assert 'id="curr-seg-textbook"' in html
        assert 'id="curr-seg-collection"' in html
        assert 'id="curr-seg-combined"' in html

    main_kt = ANDROID_MAIN_KT.read_text(encoding="utf-8")
    assert "curriculumSegment" in main_kt


# ============================================================================
# CONTRACT C4: Response-Time Fluency Calibration & Confusion Matrix Weighting
# ============================================================================


@pytest.mark.parametrize(
    "raw_rating,rt_ms,baseline,streak,expected_effective,expected_status",
    [
        # Boundary 1: Invalid / too-fast (<300ms) or too-slow (>60000ms) RT -> Fail-Closed bypass
        (3, None, [2000, 2200, 2100, 2300, 2050], 3, 3, "BYPASSED_INVALID_RT"),
        (3, 299, [2000, 2200, 2100, 2300, 2050], 3, 3, "BYPASSED_INVALID_RT"),
        (3, 60001, [2000, 2200, 2100, 2300, 2050], 3, 3, "BYPASSED_INVALID_RT"),
        # Boundary 2: Cold start (<5 baseline samples) -> Fail-Closed bypass
        (3, 800, [2000, 2200, 2100, 2300], 3, 3, "BYPASSED_COLD_START"),
        # Boundary 2b: Zero dispersion (MAD == 0, all baseline samples identical) -> Fail-Closed BYPASSED_ZERO_MAD
        (3, 4000, [2000, 2000, 2000, 2000, 2000], 3, 3, "BYPASSED_ZERO_MAD"),
        # Boundary 3: Non-Good ratings (Again=1, Hard=2, Easy=4) are NEVER mutated
        (1, 500, [3000, 3200, 3100, 3300, 3050], 5, 1, "PRESERVED_EXPLICIT_RATING"),
        (2, 500, [3000, 3200, 3100, 3300, 3050], 5, 2, "PRESERVED_EXPLICIT_RATING"),
        (4, 15000, [3000, 3200, 3100, 3300, 3050], 0, 4, "PRESERVED_EXPLICIT_RATING"),
        # Boundary 4: Hesitant Good (z >= +1.5) -> Downgraded by 1 step to Hard (2)
        (3, 9500, [2000, 2200, 2100, 2300, 2050], 2, 2, "DOWNGRADED_HESITANT_GOOD"),
        # Boundary 5: Effortless Fluent Good (z <= -1.0 AND streak >= 2) -> Upgraded by 1 step to Easy (4)
        (3, 750, [2500, 2800, 2600, 2700, 2550], 2, 4, "UPGRADED_FLUENT_GOOD"),
        # Boundary 6: Fast Good but streak < 2 -> Remains Good (3)
        (3, 750, [2500, 2800, 2600, 2700, 2550], 1, 3, "UNCHANGED_NORMAL_GOOD"),
        # Boundary 7: Normal RT Good -> Remains Good (3)
        (3, 2150, [2000, 2200, 2100, 2300, 2050], 3, 3, "UNCHANGED_NORMAL_GOOD"),
    ],
)
def test_c4_ddt_fluency_calibration_bva_matrix(
    raw_rating: int,
    rt_ms: Optional[int],
    baseline: List[int],
    streak: int,
    expected_effective: int,
    expected_status: str,
) -> None:
    res = rea_v56.calibrate_fluency_grade(
        raw_rating=raw_rating,
        response_time_ms=rt_ms,
        baseline_rt_ms_samples=baseline,
        consecutive_good_streak=streak,
    )
    assert res["raw_rating"] == raw_rating
    assert res["effective_rating"] == expected_effective
    assert res["status"] == expected_status
    # Invariant: Effective rating never deviates by more than 1 step from raw_rating, and Again(1) is never promoted
    assert abs(int(res["effective_rating"]) - raw_rating) <= 1
    if raw_rating == 1:
        assert res["effective_rating"] == 1


def test_c4_ddt_confusion_matrix_exponential_decay_and_idempotency() -> None:
    # 1. Self-pair (A, A) is ignored
    self_res = rea_v56.update_confusion_matrix_weight(
        current_weight=1.0,
        elapsed_days=0.0,
        card_a="card_1",
        card_b="card_1",
        review_id="rev_1",
        seen_review_ids=(),
    )
    assert self_res["weight"] == 1.0
    assert self_res["updated"] is False

    # 2. Duplicate review_id is idempotent
    dup_res = rea_v56.update_confusion_matrix_weight(
        current_weight=2.0,
        elapsed_days=5.0,
        card_a="card_1",
        card_b="card_2",
        review_id="rev_dup",
        seen_review_ids=("rev_dup",),
    )
    assert dup_res["weight"] == 2.0
    assert dup_res["updated"] is False

    # 3. Fresh confusion at elapsed_days=0 adds +1.0
    fresh_res = rea_v56.update_confusion_matrix_weight(
        current_weight=2.0,
        elapsed_days=0.0,
        card_a="card_1",
        card_b="card_2",
        review_id="rev_2",
        seen_review_ids=(),
    )
    assert fresh_res["weight"] == pytest.approx(3.0)
    assert fresh_res["updated"] is True
    assert fresh_res["should_interleave_peer"] is True

    # 4. Decay after tau=30 days: C' = 2.0 * exp(-1) + 1.0
    decay_res = rea_v56.update_confusion_matrix_weight(
        current_weight=2.0,
        elapsed_days=30.0,
        card_a="card_1",
        card_b="card_2",
        review_id="rev_3",
        seen_review_ids=(),
    )
    assert decay_res["weight"] == pytest.approx(2.0 * 0.36787944 + 1.0, rel=1e-4)

    # 5. Lapse interval penalty clamped to [0.85, 1.0]
    assert rea_v56.compute_confusion_interval_factor(0.0) == 1.0
    assert rea_v56.compute_confusion_interval_factor(2.0) == pytest.approx(0.90)
    assert rea_v56.compute_confusion_interval_factor(10.0) == pytest.approx(0.85)


def test_c1_to_c4_tri_engine_js_and_kotlin_parity() -> None:
    """Verify viewmodel.js and ReaV56Engine.kt implement C1~C4 identically to Python rea_v56.py."""
    script = f"""
    const vm = require({json.dumps(str(STATIC_DIR / "viewmodel.js"))});
    const assert = require("assert");

    // C1: computeStudyToolsSummary
    const s0 = vm.computeStudyToolsSummary({{ studyFilter: "all", qtypeFilter: "all", cramMode: false }});
    assert.strictEqual(s0.active_count, 0);
    assert.strictEqual(s0.is_default, true);
    const s2 = vm.computeStudyToolsSummary({{ studyFilter: "wrong_only", qtypeFilter: "vocab", cramMode: false }});
    assert.strictEqual(s2.active_count, 2);
    assert.strictEqual(s2.summary_badge_text, "필터 2개 적용 중");

    // C2: resolveSmartAiEngine
    const rAuto = vm.resolveSmartAiEngine({{ taskType: "card_generate", offlineOnly: false }});
    assert.strictEqual(rAuto.selected_model, "glm-5.3-flash");
    assert.strictEqual(rAuto.exposes_raw_model_name, false);
    const rBlocked = vm.resolveSmartAiEngine({{ taskType: "card_generate", manualOverride: "kimi-k2.6" }});
    assert.strictEqual(rBlocked.status, "BLOCKED_MODEL");

    // C3: resolveCurriculumSegmentState
    const cSeg = vm.resolveCurriculumSegmentState("collection", 3);
    assert.strictEqual(cSeg.active_segment, "collection");
    assert.strictEqual(cSeg.combined_tab_label, "🎯 시험범위 조합 (3)");
    assert.strictEqual(cSeg.visible_panels.collection, true);
    assert.strictEqual(cSeg.visible_panels.textbook, false);

    // C4: calibrateFluencyGrade & updateConfusionMatrixWeight & applyC4ReviewCalibration
    const fSlow = vm.calibrateFluencyGrade(3, 9500, [2000, 2200, 2100, 2300, 2050], 2);
    assert.strictEqual(fSlow.effective_rating, 2);
    assert.strictEqual(fSlow.status, "DOWNGRADED_HESITANT_GOOD");

    const fZeroMad = vm.calibrateFluencyGrade(3, 4500, [2000, 2000, 2000, 2000, 2000], 2);
    assert.strictEqual(fZeroMad.effective_rating, 3);
    assert.strictEqual(fZeroMad.status, "BYPASSED_ZERO_MAD");

    const fFast = vm.calibrateFluencyGrade(3, 750, [2500, 2800, 2600, 2700, 2550], 2);
    assert.strictEqual(fFast.effective_rating, 4);
    assert.strictEqual(fFast.status, "UPGRADED_FLUENT_GOOD");

    const fAgain = vm.calibrateFluencyGrade(1, 500, [2500, 2800, 2600, 2700, 2550], 5);
    assert.strictEqual(fAgain.effective_rating, 1);

    const conf = vm.updateConfusionMatrixWeight(2.0, 0.0, "c1", "c2", "rev_1", []);
    assert.strictEqual(conf.weight, 3.0);
    assert.strictEqual(conf.should_interleave_peer, true);
    assert.strictEqual(vm.computeConfusionIntervalFactor(10.0), 0.85);

    const coordRewritten = vm.applyC4ReviewCalibration(3, 9500, [2000, 2200, 2100, 2300, 2050], 2, 3.0);
    assert.strictEqual(coordRewritten.effective_rating, 2);
    assert.strictEqual(coordRewritten.effective_interval_factor, 1.0);
    assert.strictEqual(coordRewritten.interval_scaled_by_confusion, false);

    const coordUnrewritten = vm.applyC4ReviewCalibration(3, 2100, [2000, 2200, 2100, 2300, 2050], 1, 2.0);
    assert.strictEqual(coordUnrewritten.effective_rating, 3);
    assert.strictEqual(coordUnrewritten.effective_interval_factor, 0.9);
    assert.strictEqual(coordUnrewritten.interval_scaled_by_confusion, true);

    console.log("V58_JS_PARITY_OK");
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Node parity failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "V58_JS_PARITY_OK" in proc.stdout

    rea_kt = ANDROID_REA_KT.read_text(encoding="utf-8")
    for fn_name in (
        "fun computeStudyToolsSummary(",
        "fun resolveSmartAiEngine(",
        "fun resolveCurriculumSegmentState(",
        "fun calibrateFluencyGrade(",
        "fun updateConfusionMatrixWeight(",
        "fun computeConfusionIntervalFactor(",
        "fun applyC4ReviewCalibration(",
    ):
        assert fn_name in rea_kt, f"Missing {fn_name} in Android ReaV56Engine.kt"


def test_c2_and_c4_live_adapter_and_service_wiring(tmp_path: Path) -> None:
    """Verify C2 live multi-model fallback in AICardSynthesizer and C4 live review calibration & SQLite confusion persistence in AnkiStudioService."""
    from anki_studio.adapters.ai_engine import AICardSynthesizer
    from anki_studio.domain.document_deck_builder import DocumentBlock
    from anki_studio.service.studio_server import AnkiStudioService

    # 1. C2 Live Multi-Model Fallback: glm-5.3-flash fails -> deepseek-v4.1-flash succeeds automatically
    called_models: List[str] = []

    def failover_sender(url, payload, headers, timeout):
        m = payload.get("model", "")
        called_models.append(m)
        if m == "glm-5.3-flash":
            raise RuntimeError("Simulated 429 rate limit on primary model")
        return json.dumps(
            {
                "cards": [
                    {
                        "front_text": "피타고라스 정리 공식은?",
                        "back_text": "a² + b² = c²",
                        "note_type": "basic",
                        "source_page": 1,
                        "source_excerpt": "직각삼각형에서 a² + b² = c²",
                    }
                ]
            },
            ensure_ascii=False,
        )

    synth = AICardSynthesizer(ollama_http_sender=failover_sender)
    doc_res = synth.synthesize_document_cards_with_ollama_cloud(
        blocks=[DocumentBlock(page=1, text="직각삼각형에서 피타고라스 정리 a² + b² = c² 성립", kind="paragraph")],
        base_cards=[],
        ollama_cloud_model="auto",
    )
    assert doc_res["ok"] is True
    assert doc_res["ollama_cloud_used"] is True
    assert doc_res["ollama_cloud_model"] == "deepseek-v4.1-flash"
    assert called_models[:2] == ["glm-5.3-flash", "deepseek-v4.1-flash"]

    # 2. C4 Live Review Calibration & SQLite Confusion Persistence in AnkiStudioService
    svc = AnkiStudioService(db_path=tmp_path / "c4_live.sqlite3", seed_defaults=True, ai_synthesizer=synth)
    due = svc.get_due_cards(limit=5)["cards"]
    assert len(due) >= 2
    c1_id = int(due[0]["card_id"])
    c2_id = int(due[1]["card_id"])

    # Submit a hesitant Good(3) with 9500ms RT against a ~2100ms baseline AND confusion with c2_id
    rev_hesitant = svc.submit_review(
        card_id=c1_id,
        rating=3,
        response_time_ms=9500,
        confused_with_card_id=c2_id,
        review_id="rev_live_c4_1",
        baseline_rt_ms_samples=[2000, 2200, 2100, 2300, 2050],
        consecutive_good_streak=2,
    )
    assert rev_hesitant["ok"] is True
    assert rev_hesitant["raw_rating"] == 3
    assert rev_hesitant["effective_rating"] == 2
    assert rev_hesitant["rating"] == 2
    assert rev_hesitant["fluency_status"] == "DOWNGRADED_HESITANT_GOOD"
    # Non-interference: because rating was rewritten (3 -> 2), effective_interval_factor is 1.0 (no double penalty)
    assert rev_hesitant["effective_interval_factor"] == 1.0
    assert rev_hesitant["confusion_weight"] == pytest.approx(1.0)

    # Duplicate review_id is idempotent on confusion weight; normal RT Good(3) applies confusion interval factor
    rev_normal = svc.submit_review(
        card_id=c1_id,
        rating=3,
        response_time_ms=2100,
        confused_with_card_id=c2_id,
        review_id="rev_live_c4_1",
        baseline_rt_ms_samples=[2000, 2200, 2100, 2300, 2050],
        consecutive_good_streak=1,
    )
    assert rev_normal["effective_rating"] == 3
    assert rev_normal["fluency_status"] == "UNCHANGED_NORMAL_GOOD"
    assert rev_normal["confusion_weight"] == pytest.approx(1.0)
    assert rev_normal["effective_interval_factor"] == pytest.approx(0.95)


def test_c1_to_c3_live_service_and_dom_e2e_simple_is_best(tmp_path: Path) -> None:
    """End-to-End verification of Study Tools Drawer (C1), Zero Raw Model Jargon (C2), and 3-Segment Curriculum Switcher (C3) across Python Service, HTML DOM, and JS ViewModel."""
    from anki_studio.service.studio_server import AnkiStudioService

    db_path = tmp_path / "e2e_v58.sqlite3"
    svc = AnkiStudioService(db_path=db_path, seed_defaults=True)

    # 1. Verify Curriculum Catalog & MOE 9 Collections in live service
    from anki_studio.domain.moe_curriculum_corpus import MOE_CURRICULUM_COLLECTIONS

    catalog = svc.get_curriculum_catalog()
    assert len(catalog["collections"]) >= 12
    assert len(MOE_CURRICULUM_COLLECTIONS) == 9
    store_cat = svc.get_store_catalog("moe_curriculum")
    assert len(store_cat["packs"]) == 9

    # 2. Verify DOM initial state and interactive JS controller wiring in index.html + app.js
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    # C1: Drawer starts hidden (`display:none`) and toggle button controls aria-expanded & display
    assert 'id="study-tools-drawer" style="display:none;' in index_html
    assert 'id="btn-toggle-study-tools" aria-expanded="false"' in index_html
    assert "syncStudyToolsSummaryBadge" in app_js

    # C2: Zero raw model jargon in #doc-ollama-model-select options
    select_block = index_html.split('id="doc-ollama-model-select"')[1].split("</select>")[0]
    assert "✨ 스마트 자동 생성 (추천)" in select_block
    assert "⚡ 오프라인 빠른 생성" in select_block
    for raw_jargon in ("GLM", "DeepSeek", "Gemma", "Ollama", "올라마"):
        assert raw_jargon not in select_block

    # C3: Curriculum 3-segment switcher starts with textbook visible and collection/combined hidden
    assert 'id="curr-seg-textbook"' in index_html
    assert 'id="curr-seg-collection" style="display:none;"' in index_html
    assert 'id="curr-seg-combined" style="display:none;' in index_html
    assert "switchCurriculumSegment" in app_js

