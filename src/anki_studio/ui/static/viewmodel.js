/**
 * Pure Presentation ViewModel for Anki Studio 2.0 (MVVM Architecture).
 * Zero DOM dependencies — 100% deterministic functions testable in Node/Browser.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.AnkiStudioViewModel = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function formatRetentionBadge(retentionPct) {
    const val = Number(retentionPct) || 0;
    if (val >= 90) {
      return { label: `${val.toFixed(1)}% (Optimal FSRS-5)`, tone: "emerald" };
    }
    if (val >= 80) {
      return { label: `${val.toFixed(1)}% (Moderate)`, tone: "amber" };
    }
    return { label: `${val.toFixed(1)}% (At Risk)`, tone: "rose" };
  }

  function formatLeechBadge(leechStatus, lapses) {
    const count = Number(lapses) || 0;
    if (leechStatus === "critical_leech") {
      return {
        visible: true,
        label: `🚨 집중 처방 대상 (Leech ${count}회 오답) — AI 원자 분할 추천`,
        tone: "rose",
      };
    }
    if (leechStatus === "warning") {
      return {
        visible: true,
        label: `⚠️ 반복 오답 주의 (${count}회) — AI 소크라테스 힌트 활용 권장`,
        tone: "amber",
      };
    }
    return { visible: false, label: "", tone: "slate" };
  }

  function mapKeyboardShortcut(key, isAnswerRevealed, isTypingInInput) {
    if (isTypingInInput) {
      return null;
    }
    const normalized = String(key || "").toLowerCase();
    if (normalized === " " || normalized === "enter") {
      return isAnswerRevealed ? { action: "rate", rating: 3 } : { action: "reveal" };
    }
    if (isAnswerRevealed && ["1", "2", "3", "4"].includes(normalized)) {
      return { action: "rate", rating: Number(normalized) };
    }
    if (normalized === "h") {
      return { action: "hint" };
    }
    if (normalized === "t") {
      return { action: "tts" };
    }
    return null;
  }

  function buildForgettingCurveSvgPoints(curvePoints, width, height) {
    const pts = Array.isArray(curvePoints) ? curvePoints : [];
    if (pts.length === 0) return "";
    const w = Number(width) || 480;
    const h = Number(height) || 120;
    const maxDay = Math.max(1, ...pts.map((p) => Number(p.day) || 0));

    return pts
      .map((p) => {
        const x = ((Number(p.day) || 0) / maxDay) * w;
        const r = Math.max(0.5, Math.min(1.0, Number(p.retrievability) || 0.9));
        // Map [0.5 .. 1.0] to [h - 10 .. 10]
        const y = h - 10 - ((r - 0.5) / 0.5) * (h - 20);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }

  const CATEGORY_META = {
    law: { label: "⚖️ 법학·행정·조문", tone: "indigo" },
    medical: { label: "🩺 의학·간호·생명", tone: "emerald" },
    engineering: { label: "🔬 공학·IT·아키텍처", tone: "cyan" },
    language: { label: "🗣️ 어학·외국어 회화", tone: "amber" },
    exam: { label: "📝 자격증·수험 기출", tone: "violet" },
    general: { label: "📚 전공·교양 일반", tone: "slate" },
  };

  const PATTERN_META = {
    definition: "개념 정의",
    numbered_list: "번호 열거",
    causal_compare: "인과·비교",
    statute_numeric: "조문·수치",
    language_pair: "어학 표현",
  };

  function formatCategoryBadge(category) {
    return CATEGORY_META[String(category || "general")] || CATEGORY_META.general;
  }

  function formatPatternBadge(pattern) {
    return PATTERN_META[String(pattern || "definition")] || "개념 정의";
  }

  function formatIngestStatusBanner(res) {
    if (!res || res.status !== "OK") {
      const code = (res && res.error_code) || "unknown_error";
      return {
        status: "BLOCKED",
        tone: "rose",
        title: `⛔ 자동 덱 생성 차단 (${code})`,
        summary: "문서/사진에서 신뢰할 수 있는 텍스트나 카드를 추출하지 못해 빈 덱 생성을 차단했습니다.",
        canSave: false,
      };
    }
    const cards = Array.isArray(res.cards) ? res.cards : [];
    const st = res.stats || {};
    const cat = formatCategoryBadge(res.category);
    const savedMsg = res.deck_id ? ` · 덱 즉시 저장 완료(#${res.deck_id})` : " · 미리보기 검수 대기";
    return {
      status: "OK",
      tone: "emerald",
      title: `✅ [${cat.label}] '${res.deck_name}' — ${cards.length}장 추출${savedMsg}`,
      summary: `총 ${st.pages || 1}쪽 (OCR ${st.ocr_pages || 0}쪽) · 저신뢰 제외 ${st.low_confidence_lines || 0}줄 · 근거미달 폐기 ${st.dropped_ungrounded || 0}장 · 중복제거 ${st.duplicates || 0}장 · 엔진: ${res.provider || "local"} (${res.latency_ms || 0}ms)`,
      canSave: !res.deck_id && cards.length > 0,
    };
  }

  return {
    formatRetentionBadge,
    formatLeechBadge,
    mapKeyboardShortcut,
    buildForgettingCurveSvgPoints,
    formatCategoryBadge,
    formatPatternBadge,
    formatIngestStatusBanner,
  };
});

