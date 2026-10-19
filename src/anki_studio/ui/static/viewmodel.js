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

  return {
    formatRetentionBadge,
    formatLeechBadge,
    mapKeyboardShortcut,
    buildForgettingCurveSvgPoints,
  };
});
