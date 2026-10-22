/**
 * Pure Presentation ViewModel for BrainDeck 2.0 (MVVM Architecture).
 * Zero DOM dependencies — 100% deterministic functions testable in Node/Browser.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    const api = factory();
    root.AnkiStudioViewModel = api;
    root.BrainDeckViewModel = api;
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
        label: `🚨 집중 복습 대상 (${count}회 오답) — 쉬운 카드로 쪼개기 추천`,
        tone: "rose",
      };
    }
    if (leechStatus === "warning") {
      return {
        visible: true,
        label: `⚠️ 반복 오답 주의 (${count}회) — 단계별 힌트 활용 권장`,
        tone: "amber",
      };
    }
    return { visible: false, label: "", tone: "slate" };
  }

  function mapKeyboardShortcut(key, isAnswerRevealed, isTypingInInput, ageTier) {
    if (isTypingInInput) {
      return null;
    }
    const normalized = String(key || "").toLowerCase();
    const tierNorm = String(ageTier || "teen").toLowerCase();
    if (normalized === " " || normalized === "enter") {
      return isAnswerRevealed ? { action: "rate", rating: 3 } : { action: "reveal" };
    }
    if (isAnswerRevealed && ["1", "2", "3", "4"].includes(normalized)) {
      if (normalized === "4" && tierNorm === "junior") {
        return null;
      }
      return { action: "rate", rating: Number(normalized) };
    }
    if (normalized === "q") {
      return { action: "quiz" };
    }
    if (normalized === "h") {
      return { action: "hint" };
    }
    if (normalized === "t") {
      return { action: "tts" };
    }
    if (normalized === "z") {
      return { action: "undo" };
    }
    return null;
  }

  function formatRatingButtonsForAgeTier(ageTier, previews) {
    const tierNorm = String(ageTier || "teen").toLowerCase();
    const p = previews || {};
    const l1 = (p.again && p.again.label) || "10m";
    const l2 = (p.hard && p.hard.label) || "1d";
    const l3 = (p.good && p.good.label) || "3d";
    const l4 = (p.easy && p.easy.label) || "16d";

    if (tierNorm === "junior") {
      return [
        { rating: 1, title: "1 · 다시 볼래요 🌱", subLabel: l1, visible: true },
        { rating: 2, title: "2 · 조금 헷갈려요 🤔", subLabel: l2, visible: true },
        { rating: 3, title: "3 · 맞혔어요! 🎉", subLabel: l3, visible: true },
      ];
    }
    return [
      { rating: 1, title: "1 · Again (망각)", subLabel: l1, visible: true },
      { rating: 2, title: "2 · Hard (어려움)", subLabel: l2, visible: true },
      { rating: 3, title: "3 · Good (적정)", subLabel: l3, visible: true },
      { rating: 4, title: "4 · Easy (완벽)", subLabel: l4, visible: true },
    ];
  }

  function formatApiErrorBanner(res) {
    const r = res || {};
    const code = String(r.error_code || r.error || "UNKNOWN_ERROR");
    const reqPackId = (r.decision && r.decision.required_pack_id) || null;
    if (code === "PACK_LOCKED") {
      return {
        tone: "amber",
        errorCode: code,
        actionPackId: reqPackId,
        message: `🔒 아직 잠금 해제되지 않은 유료 브레인팩(${reqPackId || "스토어 팩"})입니다. 상단 '🛒 브레인팩 스토어'에서 먼저 장착(₩990~₩1,900)해 주세요!`,
      };
    }
    if (code === "PACK_REFUNDED_FROZEN") {
      return {
        tone: "rose",
        errorCode: code,
        actionPackId: reqPackId,
        message: "❄️ 환불 동결(refunded_frozen)된 브레인팩입니다. 기존 FSRS 복습 기록은 보존되지만 신규 시험범위·컬렉션 덱 생성은 제한됩니다.",
      };
    }
    if (code === "CLOUD_VISION_LOCKED") {
      return {
        tone: "rose",
        errorCode: code,
        actionPackId: null,
        message: "🛡️ 아동 개인정보 보호(Junior 하드락) 정책에 의해 외부 클라우드 비전 전송이 차단되었습니다. 온디바이스 OCR만 사용합니다.",
      };
    }
    if (code === "NOTHING_TO_UNDO") {
      return {
        tone: "slate",
        errorCode: code,
        actionPackId: null,
        message: "↩️ 되돌릴 최근 복습 기록이 없습니다.",
      };
    }
    return {
      tone: "rose",
      errorCode: code,
      actionPackId: null,
      message: `⚠️ 요청을 처리할 수 없습니다 (${code}).`,
    };
  }

  function evaluateTapBlockAttempt(selectedBlocks, targetBlocks) {
    const sel = Array.isArray(selectedBlocks) ? selectedBlocks.map(String) : [];
    const tgt = Array.isArray(targetBlocks) ? targetBlocks.map(String) : [];
    if (tgt.length === 0) {
      return { status: "IN_PROGRESS", progressPct: 0, recommendedRating: null };
    }
    for (let i = 0; i < sel.length; i += 1) {
      if (sel[i] !== tgt[i]) {
        return {
          status: "WRONG_ORDER",
          mismatchIndex: i,
          progressPct: Math.round((i / tgt.length) * 100),
          recommendedRating: 1,
        };
      }
    }
    if (sel.length < tgt.length) {
      return {
        status: "IN_PROGRESS",
        progressPct: Math.round((sel.length / tgt.length) * 100),
        recommendedRating: null,
      };
    }
    return {
      status: "CORRECT",
      progressPct: 100,
      recommendedRating: 3,
    };
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

  const OLLAMA_CLOUD_MODELS = [
    { id: "glm-5.3-flash", label: "☁️ Ollama Cloud · GLM-5.3 Flash (초고속 핵심 카드)", recommended: true },
    { id: "deepseek-v4.1-flash", label: "☁️ Ollama Cloud · DeepSeek-v4.1 Flash (정밀 빈칸·문맥)", recommended: false },
    { id: "gemma4:31b", label: "☁️ Ollama Cloud · Gemma-4 31B (시각·표·문서 정밀 분석)", recommended: false },
    { id: "glm-5.3", label: "☁️ Ollama Cloud · GLM-5.3 (심화·전공 서술 카드)", recommended: false },
    { id: "local_rule", label: "⚡ 기기 내장 초고속 엔진 (오프라인 · 0초)", recommended: false },
  ];

  function isOllamaCloudModelBlocked(modelName) {
    const norm = String(modelName || "").trim().toLowerCase();
    if (!norm) return false;
    return norm.startsWith("kimi") || norm.includes("/kimi") || norm.startsWith("minimax") || norm.includes("/minimax");
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
    const cloudBadge =
      res.ollama_cloud_model && res.ollama_cloud_model !== "local_rule"
        ? ` · ☁️ Ollama Cloud (${res.ollama_cloud_model})`
        : "";
    return {
      status: "OK",
      tone: "emerald",
      title: `✅ [${cat.label}] '${res.deck_name}' — ${cards.length}장 추출${savedMsg}${cloudBadge}`,
      summary: `총 ${st.pages || 1}쪽 (OCR ${st.ocr_pages || 0}쪽) · 저신뢰 제외 ${st.low_confidence_lines || 0}줄 · 근거미달 폐기 ${st.dropped_ungrounded || 0}장 · 중복제거 ${st.duplicates || 0}장 · 엔진: ${res.provider || "local"} (${res.latency_ms || 0}ms)`,
      canSave: !res.deck_id && cards.length > 0,
    };
  }

  const STORE_CATEGORY_LABELS = {
    all: "전체 브레인팩",
    starter_free: "🎁 무료 기본",
    k12_textbook: "🏫 중·고등 내신 교과서",
    hanja_history: "漢字 한자·한국사",
    language_exam: "🗣️ 토익·JLPT 어학",
    pro_cert: "⚖️ 공무원·IT 자격증",
  };

  function filterStorePacks(packs, categoryFilter) {
    const list = Array.isArray(packs) ? packs : [];
    const cat = String(categoryFilter || "all").trim();
    if (!cat || cat === "all") return list;
    return list.filter((p) => p && p.category === cat);
  }

  function formatStorePackCard(pack) {
    const p = pack || {};
    const isUnlocked = Boolean(p.unlocked || p.is_free_starter);
    return {
      packId: String(p.pack_id || ""),
      title: String(p.title || ""),
      subtitle: String(p.subtitle || ""),
      badgeLabel: String(p.badge_label || "BrainPack"),
      priceLabel: isUnlocked ? "✅ 앱 내 장착됨" : `🛒 구매 및 즉시 장착 (${p.price_label || "유료"})`,
      unlocked: isUnlocked,
      tone: isUnlocked ? "emerald" : "indigo",
      estimatedCountLabel: `수록 문항 약 ${Number(p.estimated_card_count) || 20}장`,
      features: Array.isArray(p.features) ? p.features : [],
      sampleCards: Array.isArray(p.sample_cards) ? p.sample_cards : [],
    };
  }

  const NAVIGATION_TABS = [
    { id: "study", icon: "🏠", label: "학습" },
    { id: "curriculum", icon: "🏫", label: "시험·급수" },
    { id: "create", icon: "➕", label: "만들기" },
    { id: "store", icon: "🛒", label: "스토어" },
    { id: "stats", icon: "📊", label: "내 정보" },
  ];

  const ONBOARDING_MODES = [
    {
      id: "junior",
      icon: "🌱",
      title: "주니어 (초등)",
      desc: "큰 글씨 · 쉬운 3버튼 · 4지선다 퀴즈",
    },
    {
      id: "teen",
      icon: "🚀",
      title: "중고등 (내신·수능)",
      desc: "교과서 시험범위 단원 · 스피드 암기",
    },
    {
      id: "adult",
      icon: "🎓",
      title: "성인 (자격증·어학·전공)",
      desc: "핵심 요약 · 정밀 복습 · 자유 입력",
    },
  ];

  function resolveActivePageState(activeTab, onboardingCompleted) {
    const validIds = NAVIGATION_TABS.map((t) => t.id);
    const tab = validIds.includes(String(activeTab || "")) ? String(activeTab) : "study";
    const visiblePages = {};
    validIds.forEach((id) => {
      visiblePages[id] = id === tab;
    });
    return {
      showOnboarding: !Boolean(onboardingCompleted),
      activeTab: tab,
      visiblePages,
    };
  }

  const KO_STOPWORDS = new Set([
    "the", "a", "an", "is", "are", "to", "of", "in", "on", "for", "and", "or",
    "이", "그", "저", "것", "수", "등", "및", "또는", "이다", "입니다", "하는", "있는"
  ]);

  function cleanExpectedAnswerText(rawText) {
    let text = String(rawText || "");
    const commentaryIdx = text.indexOf("💡 해설:");
    if (commentaryIdx >= 0) {
      text = text.slice(0, commentaryIdx);
    }
    const clozeFocus = [];
    const bracketRe = /【([^】]+)】/g;
    let m;
    while ((m = bracketRe.exec(text)) !== null) {
      clozeFocus.push(m[1]);
    }
    if (clozeFocus.length > 0) {
      return clozeFocus.join(" ").trim();
    }
    text = text.replace(/\{\{c\d+::([^}:]+)(?:::[^}]+)?\}\}/g, "$1");
    text = text.replace(/[【】\[\]]/g, " ");
    return text.trim();
  }

  function extractMeaningfulAnswerTokens(rawText) {
    const cleaned = cleanExpectedAnswerText(rawText).toLowerCase();
    const matches = cleaned.match(/[a-z0-9가-힣]+/g) || [];
    const suffixes = ["에서는", "으로서", "입니다", "한다", "에서", "으로", "에게", "까지", "부터", "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과"];
    const result = [];
    matches.forEach((word) => {
      let w = word;
      for (let i = 0; i < suffixes.length; i += 1) {
        const sfx = suffixes[i];
        if (w.length > sfx.length + 1 && w.endsWith(sfx)) {
          w = w.slice(0, -sfx.length);
          break;
        }
      }
      if (w.length >= 1 && !KO_STOPWORDS.has(w)) {
        result.push(w);
      }
    });
    return Array.from(new Set(result));
  }

  function buildCharBigrams(rawText) {
    const compact = cleanExpectedAnswerText(rawText).toLowerCase().replace(/\s+/g, "");
    if (!compact) return new Set();
    if (compact.length === 1) return new Set([compact]);
    const set = new Set();
    for (let i = 0; i < compact.length - 1; i += 1) {
      set.add(compact.slice(i, i + 2));
    }
    return set;
  }

  function evaluateTypedAnswerUnderstanding(userAnswer, expectedAnswer) {
    const userRaw = String(userAnswer || "").trim();
    const targetClean = cleanExpectedAnswerText(expectedAnswer);
    const primaryTarget = targetClean.replace(/\s*\([^)]*\)\s*$/g, "").trim() || targetClean;
    const refTokens = extractMeaningfulAnswerTokens(primaryTarget);

    if (!userRaw || userRaw === "?" || userRaw === "모름" || userRaw === "모르겠어요") {
      return {
        verdict: "UNKNOWN",
        badgeLabel: "❓ 모름 · 오답 (다시 학습 추천)",
        tone: "rose",
        scorePct: 0,
        recommendedRating: 1,
        matchedTerms: [],
        missingTerms: refTokens.slice(0, 5),
        feedback: `핵심 정답 키워드(${refTokens.slice(0, 4).join(", ") || primaryTarget.slice(0, 24)})를 확인하고 '다시(10분)'로 복습하세요.`,
      };
    }

    const normUser = userRaw.toLowerCase().replace(/[\s()[\],·]+/g, "");
    const normTarget = targetClean.toLowerCase().replace(/[\s()[\],·]+/g, "");
    const normPrimary = primaryTarget.toLowerCase().replace(/[\s()[\],·]+/g, "");

    const userNums = userRaw.match(/\d+/g) || [];
    const targetNums = targetClean.match(/\d+/g) || [];
    const primaryNums = primaryTarget.match(/\d+/g) || [];
    let numericConflict = false;
    if (primaryNums.length > 0 && !primaryNums.every((n) => userNums.includes(n))) {
      numericConflict = true;
    }
    if (userNums.length > 0 && targetNums.length > 0 && !userNums.every((n) => targetNums.includes(n))) {
      numericConflict = true;
    }

    if (
      !numericConflict &&
      normUser &&
      (normUser === normTarget ||
        normUser === normPrimary ||
        (normUser.length >= 2 && normPrimary.includes(normUser) && normUser.length / normPrimary.length >= 0.85) ||
        (normUser.length >= 2 && normTarget.includes(normUser) && normUser.length / normTarget.length >= 0.85))
    ) {
      return {
        verdict: "EXACT",
        badgeLabel: "🎯 정답 · 완벽 이해",
        tone: "emerald",
        scorePct: 100,
        recommendedRating: 4,
        matchedTerms: refTokens,
        missingTerms: [],
        feedback: "✅ 정답을 정확하게 이해하고 인출했습니다! '알맞음(Good)' 또는 '쉬움(Easy)'을 눌러주세요.",
      };
    }

    const userTokens = new Set(extractMeaningfulAnswerTokens(userRaw));
    const userLower = userRaw.toLowerCase();
    const matched = [];
    const missing = [];
    refTokens.forEach((tok) => {
      if (userTokens.has(tok) || userLower.includes(tok)) {
        matched.push(tok);
      } else {
        missing.push(tok);
      }
    });
    if (numericConflict) {
      missing.push(...targetNums.filter((n) => !userNums.includes(n)));
    }

    const tokenRecall = refTokens.length > 0 ? matched.length / refTokens.length : 0;
    const refBigrams = buildCharBigrams(primaryTarget);
    const userBigrams = buildCharBigrams(userRaw);
    let bigramOverlap = 0;
    if (refBigrams.size > 0 && userBigrams.size > 0) {
      let hit = 0;
      refBigrams.forEach((bg) => {
        if (userBigrams.has(bg)) hit += 1;
      });
      bigramOverlap = hit / refBigrams.size;
    }

    let scorePct = Math.round(Math.min(100, Math.max(0, (tokenRecall * 0.65 + bigramOverlap * 0.35) * 100)));
    if (numericConflict) {
      scorePct = Math.min(scorePct, 55);
    }

    if (!numericConflict && scorePct >= 82 && missing.length === 0) {
      return {
        verdict: "EXACT",
        badgeLabel: "🎯 정답 · 완벽 이해",
        tone: "emerald",
        scorePct,
        recommendedRating: scorePct >= 94 ? 4 : 3,
        matchedTerms: matched,
        missingTerms: missing,
        feedback: `✅ 핵심 개념(${matched.slice(0, 3).join(", ")})을 정확히 이해하고 있습니다!`,
      };
    }

    if (scorePct >= 35 || (matched.length >= 1 && missing.length >= 1)) {
      const floorScore = tokenRecall >= 0.45 ? 46 : 40;
      return {
        verdict: "PARTIAL",
        badgeLabel: "💡 약간 이해 · 부분 일치",
        tone: "amber",
        scorePct: Math.max(floorScore, scorePct),
        recommendedRating: 2,
        matchedTerms: matched,
        missingTerms: missing,
        feedback: `💡 일부분(${matched.slice(0, 3).join(", ") || "유사 표현"})은 이해했지만 핵심 키워드(${missing.slice(0, 3).join(", ") || "세부 표현"})가 빠졌습니다. '어려움(Hard)'을 추천합니다.`,
      };
    }

    return {
      verdict: "UNKNOWN",
      badgeLabel: "❓ 모름 · 오답 (재학습 필요)",
      tone: "rose",
      scorePct,
      recommendedRating: 1,
      matchedTerms: matched,
      missingTerms: missing.length > 0 ? missing : [targetClean.slice(0, 24)],
      feedback: `❓ 정답과 차이가 큽니다. 누락된 핵심어(${(missing.length > 0 ? missing : [targetClean]).slice(0, 3).join(", ")})를 확인하고 '다시(Again)'로 복습하세요.`,
    };
  }

  function computeAnkiQueueCounts(cards) {
    const list = Array.isArray(cards) ? cards : [];
    let newCount = 0;
    let learnCount = 0;
    let reviewCount = 0;
    list.forEach((c) => {
      if (!c) return;
      const st = String(c.state || "new").toLowerCase();
      const lapses = Number(c.lapses) || 0;
      if (st === "new") {
        newCount += 1;
      } else if (st === "learning" || st === "relearning" || lapses > 0) {
        learnCount += 1;
      } else {
        reviewCount += 1;
      }
    });
    return { newCount, learnCount, reviewCount };
  }

  function filterStudyQueue(cards, filterMode, sessionWrongCardIds, markedCardIds) {
    const list = Array.isArray(cards) ? cards : [];
    const mode = String(filterMode || "all").toLowerCase();
    const wrongSet = new Set(Array.isArray(sessionWrongCardIds) ? sessionWrongCardIds.map(Number) : []);
    const markedSet = new Set(Array.isArray(markedCardIds) ? markedCardIds.map(Number) : []);

    if (mode === "wrong_only") {
      return list.filter((c) => {
        if (!c) return false;
        const cid = Number(c.card_id ?? c.cardId);
        const st = String(c.state || "").toLowerCase();
        const lapses = Number(c.lapses) || 0;
        return lapses > 0 || st === "learning" || st === "relearning" || wrongSet.has(cid);
      });
    }
    if (mode === "marked_only") {
      return list.filter((c) => {
        if (!c) return false;
        const cid = Number(c.card_id ?? c.cardId);
        return Boolean(c.marked) || markedSet.has(cid);
      });
    }
    return list;
  }

  const AGE_TIER_UI_PROFILES = {
    junior: {
      ageTier: "junior",
      themeLabel: "🌱 주니어",
      questionFontPx: 22,
      minTouchTargetPx: 56,
      cardBorderRadiusPx: 20,
      maxFrontChars: 40,
      maxBackChars: 60,
      defaultQuizStage: 0,
      allowEasyButton: false,
      privacyHardLock: true,
      bannerText: "🌱 주니어 모드 (큰 글씨 · 4지선다)",
    },
    teen: {
      ageTier: "teen",
      themeLabel: "🚀 중고등",
      questionFontPx: 19,
      minTouchTargetPx: 48,
      cardBorderRadiusPx: 14,
      maxFrontChars: 100,
      maxBackChars: 150,
      defaultQuizStage: 0,
      allowEasyButton: true,
      privacyHardLock: false,
      bannerText: "🚀 중고등 모드 (내신·수능 표준)",
    },
    adult: {
      ageTier: "adult",
      themeLabel: "🎓 성인",
      questionFontPx: 17,
      minTouchTargetPx: 44,
      cardBorderRadiusPx: 12,
      maxFrontChars: 220,
      maxBackChars: 400,
      defaultQuizStage: 2,
      allowEasyButton: true,
      privacyHardLock: false,
      bannerText: "🎓 성인 모드 (자격증·전공 고밀도)",
    },
  };

  function resolveUiUxTokens(ageTier, viewportWidth, isStandalone) {
    const tierKey = String(ageTier || "teen").trim().toLowerCase();
    const base = AGE_TIER_UI_PROFILES[tierKey] || AGE_TIER_UI_PROFILES.teen;
    const vw = Number(viewportWidth) || 1200;
    let navigationMode = "desktop_studio_3pane";
    if (vw < 768) {
      navigationMode = "bottom_tabs_5";
    } else if (vw < 1100) {
      navigationMode = "navigation_rail_split";
    }
    return {
      ...base,
      viewportWidth: vw,
      navigationMode,
      showPwaInstallBanner: !Boolean(isStandalone),
    };
  }

  function calculateStoreBundleQuote(packs, selectedPackIds) {
    const list = Array.isArray(packs) ? packs : [];
    const selectedSet = new Set(Array.isArray(selectedPackIds) ? selectedPackIds.map(String) : []);
    let subtotalKrw = 0;
    const billablePackIds = [];
    list.forEach((p) => {
      if (!p || !selectedSet.has(String(p.pack_id))) return;
      const isUnlocked = Boolean(p.unlocked || p.is_free_starter);
      const price = Number(p.price_krw) || 0;
      if (!isUnlocked && price > 0) {
        billablePackIds.push(String(p.pack_id));
        subtotalKrw += price;
      }
    });
    const discountApplied = billablePackIds.length >= 3;
    const finalPriceKrw = discountApplied ? Math.floor((subtotalKrw * 85) / 1000) * 10 : subtotalKrw;
    return {
      billablePackIds,
      billableCount: billablePackIds.length,
      subtotalKrw,
      discountKrw: subtotalKrw - finalPriceKrw,
      finalPriceKrw,
      finalKrw: finalPriceKrw,
      discountApplied,
    };
  }

  const HANGUL_CHOSEONG = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"
  ];

  function extractTargetAndExplanation(frontText, backText, explicitTarget, explicitExtra) {
    const front = String(frontText || "").trim();
    const back = String(backText || "").trim();
    let mainBack = back;
    let extraExp = String(explicitExtra || "").trim();
    if (back.includes("💡 해설:")) {
      const parts = back.split("💡 해설:");
      mainBack = String(parts[0] || "").trim();
      if (!extraExp) {
        extraExp = String(parts.slice(1).join("💡 해설:") || "").trim();
      }
    }
    if (explicitTarget && String(explicitTarget).trim()) {
      return {
        targetAnswer: String(explicitTarget).trim(),
        extraExplanation: extraExp || (mainBack !== String(explicitTarget).trim() ? mainBack : ""),
      };
    }
    const clozeMatches = [];
    const clozeRe = /\{\{c\d+::([^}:]+)(?:::[^}]+)?\}\}/gi;
    let m;
    while ((m = clozeRe.exec(front)) !== null) {
      if (m[1] && m[1].trim()) clozeMatches.push(m[1].trim());
    }
    if (clozeMatches.length > 0) {
      return {
        targetAnswer: clozeMatches.join(", "),
        extraExplanation: extraExp || mainBack,
      };
    }
    const bracketMatches = [];
    const bracketRe = /【([^】]+)】/g;
    while ((m = bracketRe.exec(mainBack)) !== null) {
      if (m[1] && m[1].trim()) bracketMatches.push(m[1].trim());
    }
    if (bracketMatches.length > 0) {
      return {
        targetAnswer: bracketMatches.join(", "),
        extraExplanation: extraExp || mainBack,
      };
    }
    const firstLine = (mainBack.split("\n")[0] || mainBack).trim();
    return {
      targetAnswer: firstLine,
      extraExplanation: extraExp,
    };
  }

  function generateProgressiveHint(targetAnswer, extraExplanation, step) {
    const cleanTarget = cleanExpectedAnswerText(targetAnswer) || "핵심 정답";
    const withoutParen = cleanTarget.replace(/\s*\([^)]*\)\s*$/g, "").trim() || cleanTarget;
    const primary = withoutParen.split(/\s*(?:\/|·|,|\()\s*/)[0].trim() || withoutParen;
    const stepNum = Math.max(1, Number(step) || 1);
    const chars = Array.from(primary);
    let nonSpaceCount = 0;
    const maskedTokens = chars.map((ch, idx) => {
      if (/\s/.test(ch)) return " ";
      nonSpaceCount += 1;
      if (stepNum >= 2 && idx === 0) return ch;
      const code = ch.charCodeAt(0);
      if (code >= 0xac00 && code <= 0xd7a3) {
        const choIdx = Math.floor((code - 0xac00) / 588);
        return HANGUL_CHOSEONG[choIdx] || "ㅇ";
      }
      if (/[a-zA-Z]/.test(ch)) {
        return idx === 0 ? ch : "_";
      }
      if (/[0-9]/.test(ch)) {
        return idx === 0 ? ch : "□";
      }
      return ch;
    });
    const maskStr = maskedTokens.join(" ").replace(/\s+/g, " ").trim();
    let contextCue = "";
    if (extraExplanation && String(extraExplanation).trim()) {
      let safe = String(extraExplanation).trim();
      if (primary.length >= 2) {
        const escaped = primary.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        safe = safe.replace(new RegExp(escaped, "gi"), "[ ___ ]");
      }
      contextCue = safe.slice(0, 85);
    }
    if (stepNum === 1) {
      return {
        step: 1,
        mask: maskStr,
        charCount: nonSpaceCount,
        cueText: `💡 1단계 힌트: [${maskStr}] (${nonSpaceCount}글자) — 한 번 더 누르면 첫 글자와 문맥 단서가 공개됩니다.`,
      };
    }
    return {
      step: 2,
      mask: maskStr,
      charCount: nonSpaceCount,
      cueText: `💡 2단계 힌트 (앞글자 공개): [${maskStr}] (${nonSpaceCount}글자)${contextCue ? ` · 단서: ${contextCue}` : ""}`,
    };
  }

  function interleaveAndShuffleStudyQueue(cards, shuffleMode, seed) {
    const list = Array.isArray(cards) ? cards.slice() : [];
    const mode = String(shuffleMode || "interleaved").toLowerCase();
    if (list.length <= 1 || mode === "sequential" || mode === "off") {
      return list;
    }
    // Simple deterministic LCG PRNG for reproducible tests while varying per session when seed omitted
    let rngState = Number.isFinite(Number(seed)) ? Math.abs(Number(seed)) + 1 : 20261021;
    function nextRand() {
      rngState = (rngState * 1664525 + 1013904223) % 4294967296;
      return rngState / 4294967296;
    }
    function shuffleArr(arr) {
      const a = arr.slice();
      for (let i = a.length - 1; i > 0; i -= 1) {
        const j = Math.floor(nextRand() * (i + 1));
        const tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
      }
      return a;
    }
    if (mode === "random") {
      return shuffleArr(list);
    }
    function resolveBucketKey(c) {
      let tags = [];
      if (Array.isArray(c.tags)) {
        tags = c.tags.map(String);
      } else if (typeof c.tags_json === "string" && c.tags_json.trim().startsWith("[")) {
        try {
          const parsed = JSON.parse(c.tags_json);
          if (Array.isArray(parsed)) tags = parsed.map(String);
        } catch (_e) {
          tags = [];
        }
      }
      const prefixes = ["kr.", "hanja-", "hanja_", "moe-", "ko-", "khist:", "exam-", "law-", "sci-", "cert-", "U0", "u"];
      for (let i = 0; i < tags.length; i += 1) {
        const t = tags[i].trim();
        if (prefixes.some((p) => t.startsWith(p))) return t;
      }
      const generic = new Set(["curriculum", "combined_exam", "basic", "cloze", "speaking", "auto"]);
      for (let i = 0; i < tags.length; i += 1) {
        const t = tags[i].trim();
        if (t && !t.startsWith("diff_") && !generic.has(t)) return t;
      }
      return String(c.deck_name || c.pattern || c.note_type || "default");
    }
    // Group by source bucket (unit / collection / topic / deck)
    const buckets = new Map();
    list.forEach((c) => {
      if (!c) return;
      const bKey = resolveBucketKey(c);
      if (!buckets.has(bKey)) buckets.set(bKey, []);
      buckets.get(bKey).push(c);
    });
    const bucketKeys = shuffleArr(Array.from(buckets.keys()));
    bucketKeys.forEach((k) => {
      const group = shuffleArr(buckets.get(k));
      group.sort((a, b) => {
        const stA = String(a.state || "").toLowerCase();
        const stB = String(b.state || "").toLowerCase();
        const prioA = stA === "learning" || stA === "relearning" ? 0 : 1;
        const prioB = stB === "learning" || stB === "relearning" ? 0 : 1;
        return prioA - prioB;
      });
      buckets.set(k, group);
    });

    const result = [];
    let lastBucket = null;
    let streak = 0;
    const total = list.length;

    while (result.length < total) {
      const activeKeys = bucketKeys.filter((k) => buckets.get(k).length > 0);
      if (activeKeys.length === 0) break;
      let candidates = activeKeys;
      if (activeKeys.length > 1 && lastBucket && streak >= 2) {
        const nonStreak = activeKeys.filter((k) => k !== lastBucket);
        if (nonStreak.length > 0) candidates = nonStreak;
      }
      candidates.sort((a, b) => {
        const diffSwitchA = a !== lastBucket ? 0.35 : 0;
        const diffSwitchB = b !== lastBucket ? 0.35 : 0;
        return (buckets.get(b).length + diffSwitchB) - (buckets.get(a).length + diffSwitchA);
      });
      const chosenKey = candidates[0];
      const nextCard = buckets.get(chosenKey).shift();
      result.push(nextCard);
      if (chosenKey === lastBucket) {
        streak += 1;
      } else {
        lastBucket = chosenKey;
        streak = 1;
      }
    }
    return result;
  }

  const DIFFICULTY_LEVEL_MODES = [
    { id: "standard", label: "표준 (기본)" },
    { id: "lv1", label: "Lv.1 기초·핵심" },
    { id: "lv2", label: "Lv.2 실전 문맥 빈칸" },
    { id: "lv3", label: "Lv.3 심화·역방향" },
    { id: "mixed", label: "통합 (Lv.1~3 밸런스)" },
  ];

  // ============================================================================
  // v5.5 Core Memory-Science Frame 1: LearnerProfile v2 & Centralized Policy
  // ============================================================================
  function buildLearnerProfilePreset(ageTier) {
    const tier = ["junior", "teen", "adult"].includes(String(ageTier || "").toLowerCase())
      ? String(ageTier).toLowerCase()
      : "teen";
    if (tier === "junior") {
      return {
        ageTier: "junior",
        solveMode: "choice",
        difficulty: "lv1",
        order: "interleaved",
        autoSave: true,
      };
    }
    if (tier === "adult") {
      return {
        ageTier: "adult",
        solveMode: "adaptive",
        difficulty: "mixed",
        order: "interleaved",
        autoSave: true,
      };
    }
    return {
      ageTier: "teen",
      solveMode: "adaptive",
      difficulty: "mixed",
      order: "interleaved",
      autoSave: true,
    };
  }

  function normalizeLearnerProfile(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const preset = buildLearnerProfilePreset(src.ageTier || src.age_tier || "teen");
    const solveModeRaw = String(src.solveMode || src.solve_mode || preset.solveMode).toLowerCase();
    const solveMode = ["adaptive", "flip", "choice", "typing"].includes(solveModeRaw)
      ? solveModeRaw
      : preset.solveMode;
    const diffRaw = String(src.difficulty || src.difficultyLevel || preset.difficulty).toLowerCase();
    const difficulty = ["standard", "lv1", "lv2", "lv3", "mixed"].includes(diffRaw)
      ? diffRaw
      : preset.difficulty;
    const orderRaw = String(src.order || src.shuffleMode || preset.order).toLowerCase();
    const order = ["interleaved", "random", "sequential"].includes(orderRaw)
      ? orderRaw
      : preset.order;
    const autoSave = src.autoSave !== undefined ? Boolean(src.autoSave) : true;

    const tierLabel = preset.ageTier === "junior" ? "초등·기초" : (preset.ageTier === "teen" ? "중고등·시험" : "성인·자격증");
    const modeLabel = solveMode === "adaptive" ? "자동진화(선다→서술)" : (solveMode === "choice" ? "4지선다" : (solveMode === "typing" ? "직접타이핑" : "카드뒤집기"));
    const diffLabel = difficulty === "lv1" ? "Lv.1 기초" : (difficulty === "lv2" ? "Lv.2 빈칸" : (difficulty === "lv3" ? "Lv.3 심화" : (difficulty === "mixed" ? "통합(Lv.1~3)" : "표준")));
    const orderLabel = order === "interleaved" ? "스마트교차섞기" : (order === "random" ? "완전랜덤" : "순차");

    return {
      ageTier: preset.ageTier,
      solveMode,
      difficulty,
      order,
      autoSave,
      summaryLabel: `🎯 ${tierLabel} · ${modeLabel} · ${diffLabel} · ${orderLabel}`,
    };
  }

  // ============================================================================
  // v5.5 Core Memory-Science Frame 2: 1-Card 1-Mode Solver Resolution
  // ============================================================================
  function resolveCardSolveMode(card, profile) {
    const prof = normalizeLearnerProfile(profile);
    if (prof.solveMode === "flip" || prof.solveMode === "choice" || prof.solveMode === "typing") {
      return prof.solveMode;
    }
    const reps = Number((card && card.reps) || 0);
    const st = String((card && card.state) || "new").toLowerCase();
    if (reps <= 0 || st === "new") {
      return "choice";
    }
    return "typing";
  }

  // ============================================================================
  // v5.5 Core Memory-Science Frame 3: EvidenceRatingGuard (Metacognitive Calibration)
  // ============================================================================
  function resolveAllowedRatings(evidence, ageTier) {
    const ev = evidence && typeof evidence === "object" ? evidence : {};
    const tier = ["junior", "teen", "adult"].includes(String(ageTier || ev.ageTier || "").toLowerCase())
      ? String(ageTier || ev.ageTier).toLowerCase()
      : "adult";

    if (!ev.isRevealed) {
      return {
        allowedRatings: [],
        recommendedRating: null,
        maxRating: 0,
        lockedReason: "pre_reveal",
        bannerText: "정답을 확인하기 전에는 난이도 평가를 누를 수 없습니다.",
      };
    }

    const verdictUpper = String(ev.typedVerdict || "").toUpperCase();
    if (ev.dontKnow === true || ev.choiceCorrect === false || verdictUpper === "UNKNOWN") {
      return {
        allowedRatings: [1],
        recommendedRating: 1,
        maxRating: 1,
        lockedReason: "wrong_or_unknown",
        bannerText: "🔴 오답·모름 상태에서는 기억 왜곡 방지를 위해 '다시(1)'만 선택할 수 있습니다.",
      };
    }

    if (Number(ev.hintStep || 0) >= 1) {
      return {
        allowedRatings: [1, 2],
        recommendedRating: 2,
        maxRating: 2,
        lockedReason: "hint_assisted_cap",
        bannerText: "🟡 힌트 단서를 사용했으므로 최대 평가가 '어려움(2)'으로 제한됩니다 (인출 강도 보정).",
      };
    }

    if (verdictUpper === "PARTIAL") {
      return {
        allowedRatings: [1, 2, 3],
        recommendedRating: 2,
        maxRating: 3,
        lockedReason: "partial_recall_cap",
        bannerText: "🟡 부분 인출 상태이므로 '쉬움(4)'이 잠기며 '어려움(2)'을 권장합니다.",
      };
    }

    if (tier === "junior") {
      return {
        allowedRatings: [1, 2, 3],
        recommendedRating: 3,
        maxRating: 3,
        lockedReason: "none",
        bannerText: "🟢 스스로 인출에 성공했습니다! '알겠음(3)'을 추천합니다.",
      };
    }

    return {
      allowedRatings: [1, 2, 3, 4],
      recommendedRating: 3,
      maxRating: 4,
      lockedReason: "none",
      bannerText: "🟢 무보조 인출 성공! 기억 난이도에 맞춰 평가하세요 ('보통 3' 추천).",
    };
  }

  // ============================================================================
  // v5.5 Core Memory-Science Frame 4: Sibling Burying (1-Concept 1-Session)
  // ============================================================================
  function extractCardTagList(card) {
    if (!card) return [];
    if (Array.isArray(card.tags)) return card.tags.map((t) => String(t).trim()).filter(Boolean);
    if (typeof card.tags_json === "string" && card.tags_json.trim().startsWith("[")) {
      try {
        const parsed = JSON.parse(card.tags_json);
        if (Array.isArray(parsed)) return parsed.map((t) => String(t).trim()).filter(Boolean);
      } catch (_e) {
        return [];
      }
    }
    if (typeof card.tags === "string") {
      return card.tags.split(/[\s,]+/).map((t) => t.trim()).filter(Boolean);
    }
    return [];
  }

  function deduplicateSessionSiblings(cards) {
    const list = Array.isArray(cards) ? cards.slice() : [];
    if (list.length <= 1) return list;

    function getConceptKey(c) {
      const tags = extractCardTagList(c);
      for (let i = 0; i < tags.length; i += 1) {
        if (tags[i].startsWith("concept:") && tags[i].length > 8) return tags[i];
      }
      return null;
    }

    function priorityRank(c) {
      const st = String((c && c.state) || "new").toLowerCase();
      const stateScore = (st === "learning" || st === "relearning") ? 0 : (st === "review" ? 1 : 2);
      const tags = extractCardTagList(c);
      const diffScore = (tags.includes("diff_lv1") || tags.includes("lv1"))
        ? 0
        : ((tags.includes("diff_lv2") || tags.includes("lv2")) ? 1 : 2);
      return stateScore * 10 + diffScore;
    }

    const bestByConcept = new Map();
    list.forEach((c) => {
      const ckey = getConceptKey(c);
      if (!ckey) return;
      if (!bestByConcept.has(ckey) || priorityRank(c) < priorityRank(bestByConcept.get(ckey))) {
        bestByConcept.set(ckey, c);
      }
    });

    const seen = new Set();
    const out = [];
    list.forEach((c) => {
      const ckey = getConceptKey(c);
      if (!ckey) {
        out.push(c);
        return;
      }
      if (seen.has(ckey)) return;
      seen.add(ckey);
      out.push(bestByConcept.get(ckey));
    });
    return out;
  }

  // ============================================================================
  // v5.5 Core Memory-Science Frame 5: Standalone Apple iOS/iPadOS/Web PWA Engine
  // ============================================================================
  const STANDALONE_TEXTBOOKS = [
    {
      textbook_id: "kr.mid1.eng.donga_yoon.2022",
      title: "중1 영어 (동아 윤정미)",
      subject_code: "eng",
      unlocked: true,
      units: [
        { unit_id: "kr.mid1.eng.donga_yoon.2022:U01", unit_code: "Lesson 1", unit_title: "My Happy School Life", page_start: 10, page_end: 27, entry_count: 6 },
        { unit_id: "kr.mid1.eng.donga_yoon.2022:U02", unit_code: "Lesson 2", unit_title: "Discover Your Culture", page_start: 28, page_end: 45, entry_count: 5 },
        { unit_id: "kr.mid1.eng.donga_yoon.2022:U03", unit_code: "Lesson 3", unit_title: "Spend Smart, Save Smart", page_start: 46, page_end: 63, entry_count: 4 },
        { unit_id: "kr.mid1.eng.donga_yoon.2022:U04", unit_code: "Lesson 4", unit_title: "Walk Around the World", page_start: 64, page_end: 81, entry_count: 4 },
      ],
      entries: [
        { id: "m1_u1_1", unit_id: "kr.mid1.eng.donga_yoon.2022:U01", term: "introduce", answer: "소개하다", pos: "동사", sentence: "Let me {{c1::introduce::소개하다}} myself to the class.", explain: "Let me introduce myself (나를 소개할게)" },
        { id: "m1_u1_2", unit_id: "kr.mid1.eng.donga_yoon.2022:U01", term: "favorite", answer: "가장 좋아하는", pos: "형용사", sentence: "My {{c1::favorite::가장 좋아하는}} subject is PE.", explain: "favorite subject (가장 좋아하는 과목)" },
        { id: "m1_u1_3", unit_id: "kr.mid1.eng.donga_yoon.2022:U01", term: "instrument", answer: "악기", pos: "명사", sentence: "Do you play any musical {{c1::instrument::악기}}?", explain: "musical instrument (악기)" },
        { id: "m1_u1_4", unit_id: "kr.mid1.eng.donga_yoon.2022:U01", term: "together", answer: "함께", pos: "부사", sentence: "We eat lunch {{c1::together::함께}} every day.", explain: "do ~ together (함께 ~하다)" },
        { id: "m1_u1_5", unit_id: "kr.mid1.eng.donga_yoon.2022:U01", term: "be good at ~", answer: "~을 잘하다", pos: "숙어", role: "core_vocab", sentence: "She {{c1::is good at::~을 잘하다}} playing basketball.", explain: "전치사 at 뒤에는 명사/동명사(-ing)가 옵니다." },
        { id: "m1_u1_g1", unit_id: "kr.mid1.eng.donga_yoon.2022:U01", term: "[Lesson 1 핵심문법] 3인칭 단수 일반동사 부정문", answer: "doesn't (does not) + 동사원형", prompt: "[Lesson 1 핵심문법] 주어가 3인칭 단수(he/she/it)일 때 일반동사 현재형 부정문의 올바른 형태는?", role: "key_grammar", sentence: "He {{c1::doesn't play::3인칭 단수 부정문}} computer games on weekdays.", explain: "주어가 3인칭 단수일 때 doesn't 뒤에는 반드시 동사원형을 씁니다." },
        { id: "m1_u2_1", unit_id: "kr.mid1.eng.donga_yoon.2022:U02", term: "delicious", answer: "맛있는", pos: "형용사", role: "core_vocab", sentence: "This traditional soup smells really {{c1::delicious::맛있는}}.", explain: "감각동사 smell + 형용사 보어" },
        { id: "m1_u2_2", unit_id: "kr.mid1.eng.donga_yoon.2022:U02", term: "popular", answer: "인기 있는", pos: "형용사", role: "core_vocab", sentence: "K-pop is very {{c1::popular::인기 있는}} around the world.", explain: "be popular with (~에게 인기가 있다)" },
        { id: "m1_u2_3", unit_id: "kr.mid1.eng.donga_yoon.2022:U02", term: "traditional", answer: "전통적인", pos: "형용사", role: "core_vocab", sentence: "Hanbok is Korean {{c1::traditional::전통적인}} clothing.", explain: "tradition(전통) + -al(형용사 접미사)" },
        { id: "m1_u2_g1", unit_id: "kr.mid1.eng.donga_yoon.2022:U02", term: "[Lesson 2 핵심문법] 현재진행형 어순", answer: "am / are / is + 동사원형-ing", prompt: "[Lesson 2 핵심문법] '지금 ~하고 있는 중이다'를 나타내는 현재진행형의 올바른 문법 형태는?", role: "key_grammar", sentence: "They {{c1::are making::현재진행형}} songpyeon together now.", explain: "be동사(am/are/is) + 동사원형-ing" },
        { id: "m1_u3_1", unit_id: "kr.mid1.eng.donga_yoon.2022:U03", term: "volunteer", answer: "자원봉사하다", pos: "동사", role: "core_vocab", sentence: "We {{c1::volunteer::자원봉사하다}} at the animal shelter.", explain: "자원봉사자(명사) / 자원봉사하다(동사)" },
        { id: "m1_u4_1", unit_id: "kr.mid1.eng.donga_yoon.2022:U04", term: "ancient", answer: "고대의", pos: "형용사", role: "core_vocab", sentence: "They visited an {{c1::ancient::고대의}} palace in Rome.", explain: "반의어: modern (현대의)" },
      ],
    },
    {
      textbook_id: "kr.mid2.eng.donga_yoon.2022",
      title: "중2 영어 (동아 윤정미)",
      subject_code: "eng",
      unlocked: true,
      units: [
        { unit_id: "kr.mid2.eng.donga_yoon.2022:U01", unit_code: "Lesson 1", unit_title: "Express Yourself", page_start: 10, page_end: 29, entry_count: 5 },
        { unit_id: "kr.mid2.eng.donga_yoon.2022:U02", unit_code: "Lesson 2", unit_title: "Eat Right, Be Happy", page_start: 30, page_end: 49, entry_count: 4 },
      ],
      entries: [
        { id: "m2_u1_1", unit_id: "kr.mid2.eng.donga_yoon.2022:U01", term: "communicate", answer: "의사소통하다", pos: "동사", role: "core_vocab", sentence: "We {{c1::communicate::의사소통하다}} with friends through emojis.", explain: "communicate with (~와 소통하다)" },
        { id: "m2_u1_2", unit_id: "kr.mid2.eng.donga_yoon.2022:U01", term: "experience", answer: "경험하다", pos: "동사", role: "core_vocab", sentence: "Traveling helps you {{c1::experience::경험하다}} new cultures.", explain: "경험(명사) / 경험하다(동사)" },
        { id: "m2_u1_g1", unit_id: "kr.mid2.eng.donga_yoon.2022:U01", term: "[Lesson 1 핵심문법] 감각동사 + 형용사", answer: "감각동사(look/sound/smell/taste/feel) + 형용사 보어", prompt: "[Lesson 1 핵심문법] 감각동사(look, sound, smell, taste, feel) 뒤에 보어로 반드시 와야 하는 품사는?", role: "key_grammar", sentence: "That idea sounds {{c1::great::감각동사+형용사}}! (부사 greatly 불가)", explain: "감각동사 뒤에는 부사(-ly)가 아니라 형용사 보어가 옵니다." },
        { id: "m2_u2_1", unit_id: "kr.mid2.eng.donga_yoon.2022:U02", term: "balanced", answer: "균형 잡힌", pos: "형용사", role: "core_vocab", sentence: "Eating a {{c1::balanced::균형 잡힌}} diet is important for health.", explain: "a balanced diet (균형 잡힌 식단)" },
        { id: "m2_u2_2", unit_id: "kr.mid2.eng.donga_yoon.2022:U02", term: "nutrient", answer: "영양소", pos: "명사", role: "core_vocab", sentence: "Vegetables contain essential {{c1::nutrients::영양소}}.", explain: "nutrition(영양) / nutrient(영양소)" },
      ],
    },
    {
      textbook_id: "kr.mid2.hist.miraeen.2022",
      title: "중학 역사 1·2 (미래엔 핵심 한국사·세계사)",
      subject_code: "hist",
      unlocked: true,
      units: [
        { unit_id: "kr.mid2.hist.miraeen.2022:U01", unit_code: "Ⅰ-1", unit_title: "문명의 발생과 고대 세계", page_start: 12, page_end: 45, entry_count: 4 },
        { unit_id: "kr.mid2.hist.miraeen.2022:U02", unit_code: "Ⅱ-1", unit_title: "조선의 건국과 문화 발전", page_start: 46, page_end: 88, entry_count: 4 },
      ],
      entries: [
        { id: "hist_u1_1", unit_id: "kr.mid2.hist.miraeen.2022:U01", term: "함무라비 법전", answer: "함무라비 법전", prompt: "고대 바빌로니아 왕국이 제정한 '눈에는 눈, 이에는 이' 보복주의 원칙의 성문법은?", sentence: "고대 바빌로니아의 {{c1::함무라비 법전::성문법}}은 신분에 따라 처벌을 달리한 보복주의 법전이다.", explain: "메소포타미아 바빌로니아 왕국 함무라비 왕 통치기 편찬" },
        { id: "hist_u1_2", unit_id: "kr.mid2.hist.miraeen.2022:U01", term: "카스트제", answer: "카스트제", prompt: "고대 인도 아리아인이 정복 과정에서 브라만·크샤트리아·바이샤·수드라로 구분한 엄격한 신분 제도는?", sentence: "고대 인도 사회는 브라만 중심의 4성 계급인 {{c1::카스트제::인도 신분제}}를 바탕으로 유지되었다.", explain: "브라만(사제)·크샤트리아(귀족/무사)·바이샤(평민)·수드라(예속민)" },
        { id: "hist_u2_1", unit_id: "kr.mid2.hist.miraeen.2022:U02", term: "훈민정음", answer: "훈민정음", prompt: "조선 세종 25년(1443) 백성을 가르치는 바른 소리라는 뜻으로 창제한 우리 고유 문자는?", sentence: "조선 세종은 집현전 학자들과 함께 백성을 위한 문자 {{c1::훈민정음::1443 창제}}을 창제하였다.", explain: "1443년 창제, 1446년 반포 (해례본 국보 지정)" },
        { id: "hist_u2_2", unit_id: "kr.mid2.hist.miraeen.2022:U02", term: "경국대전", answer: "경국대전", prompt: "조선 세조 때 편찬을 시작하여 성종 때 완성·반포된 조선 왕조의 최고 기본 법전은?", sentence: "성종 때 완성된 {{c1::경국대전::조선 기본 법전}}은 이·호·예·병·형·공 6전 체제로 통치 규범을 확립했다.", explain: "조선 성종 16년(1485) 반포된 통치 기본 법전" },
      ],
    },
    {
      textbook_id: "kr.high1.sci.visang.2022",
      title: "고1 통합과학 (비상교육 2022 개정)",
      subject_code: "sci",
      unlocked: true,
      units: [
        { unit_id: "kr.high1.sci.visang.2022:U01", unit_code: "Ⅰ-1", unit_title: "물질의 규칙성과 결합", page_start: 10, page_end: 52, entry_count: 4 },
        { unit_id: "kr.high1.sci.visang.2022:U02", unit_code: "Ⅱ-2", unit_title: "생명 시스템과 화학 반응", page_start: 53, page_end: 96, entry_count: 4 },
      ],
      entries: [
        { id: "sci_u1_1", unit_id: "kr.high1.sci.visang.2022:U01", term: "공유 결합", answer: "공유 결합", prompt: "비금속 원자들이 전자쌍을 서로 내놓아 함께 공유하면서 형성하는 화학 결합은?", sentence: "물(H₂O)과 이산화탄소(CO₂)는 비금속 원소들이 전자쌍을 나누어 갖는 {{c1::공유 결합::비금속 간 결합}} 물질이다.", explain: "비금속 + 비금속 원소 간 전자쌍 공유 (옥텟 규칙 충족)" },
        { id: "sci_u1_2", unit_id: "kr.high1.sci.visang.2022:U01", term: "이온 결합", answer: "이온 결합", prompt: "금속 양이온과 비금속 음이온 사이의 정전기적 인력으로 형성되는 화학 결합은?", sentence: "염화 나트륨(NaCl)은 나트륨 양이온(Na⁺)과 염화 이온(Cl⁻) 사이의 {{c1::이온 결합::정전기적 인력}}으로 이루어진다.", explain: "고체 상태에서 전기 전도성이 없으나 수용액/용융 상태에서 전기가 통함" },
        { id: "sci_u2_1", unit_id: "kr.high1.sci.visang.2022:U02", term: "활성화 에너지", answer: "활성화 에너지", prompt: "화학 반응이 일어나기 위해 반응물이 넘어야 하는 최소한의 에너지 장벽은?", sentence: "생체 촉매인 효소는 화학 반응의 {{c1::활성화 에너지::최소 에너지 장벽}}를 낮추어 반응 속도를 빠르게 한다.", explain: "효소는 반응열(ΔH)은 바꾸지 않고 활성화 에너지만 낮춤" },
        { id: "sci_u2_2", unit_id: "kr.high1.sci.visang.2022:U02", term: "미토콘드리아", answer: "미토콘드리아", prompt: "세포호흡을 통해 포도당 등 유기물을 분해하여 생명 활동에 필요한 ATP를 합성하는 세포 소기관은?", sentence: "{{c1::미토콘드리아::ATP 합성 소기관}}는 세포 내 발전소로서 산소를 이용해 ATP 에너지를 생성한다.", explain: "이중막 구조, 자체 DNA와 리보솜 보유" },
      ],
    },
  ];

  const STANDALONE_COLLECTIONS = [
    {
      collection_id: "hanja-grade:8geup",
      level_label: "어문회 한자능력검정 8급 (기초 50자 핵심)",
      item_count: 6,
      unlocked: true,
      items: [
        { id: "hj8_1", term: "學", answer: "배울 학", sentence: "學校({{c1::배울 학::學}}·교)에서 새로운 지식을 배운다.", explain: "부수: 子(아들 자) · 활용: 학습(學習), 학생(學生)" },
        { id: "hj8_2", term: "校", answer: "학교 교", sentence: "우리 學{{c1::校::학교 교}} 교정에는 큰 나무가 있다.", explain: "부수: 木(나무 목) · 활용: 학교(學校), 교장(校長)" },
        { id: "hj8_3", term: "生", answer: "날 생", sentence: "선생님과 학{{c1::생::날 생(生)}}이 함께 인사한다.", explain: "부수: 生(날 생) · 활용: 생명(生命), 생활(生活)" },
        { id: "hj8_4", term: "國", answer: "나라 국", sentence: "대한민{{c1::국::나라 국(國)}}은 민주공화국이다.", explain: "부수: 囗(큰입구 몸) · 활용: 국가(國家), 국민(國民)" },
        { id: "hj8_5", term: "民", answer: "백성 민", sentence: "주권은 국{{c1::민::백성 민(民)}}에게 있다.", explain: "부수: 氏(각시 씨) · 활용: 시민(市民), 민주(民主)" },
        { id: "hj8_6", term: "敎", answer: "가르칠 교", sentence: "{{c1::가르칠 교::敎}}육(敎育)의 기본은 인성이다.", explain: "부수: 攴(칠 복) · 활용: 교실(敎室), 교사(敎師)" },
      ],
    },
    {
      collection_id: "hanja-grade:7geup",
      level_label: "어문회 한자능력검정 7급",
      item_count: 4,
      unlocked: true,
      items: [
        { id: "hj7_1", term: "家", answer: "집 가", sentence: "온 {{c1::가::집 가(家)}}족이 저녁 식사를 함께했다.", explain: "활용: 가족(家族), 국가(國家)" },
        { id: "hj7_2", term: "族", answer: "겨레 족", sentence: "한민{{c1::족::겨레 족(族)}}의 역사와 문화를 배운다.", explain: "활용: 민족(民族), 가족(家族)" },
        { id: "hj7_3", term: "心", answer: "마음 심", sentence: "진{{c1::심::마음 심(心)}}은 언제나 통한다.", explain: "활용: 심리(心理), 중심(中心)" },
        { id: "hj7_4", term: "動", answer: "움직일 동", sentence: "규칙적인 운{{c1::동::움직일 동(動)}}으로 건강을 지킨다.", explain: "활용: 운동(運動), 활동(活動)" },
      ],
    },
    {
      collection_id: "hanja-grade:6geup",
      level_label: "어문회 한자능력검정 6급",
      item_count: 4,
      unlocked: true,
      items: [
        { id: "hj6_1", term: "成", answer: "이룰 성", sentence: "꾸준한 노력이 {{c1::성::이룰 성(成)}}공을 만든다.", explain: "활용: 성공(成功), 완성(完成)" },
        { id: "hj6_2", term: "功", answer: "공 공", sentence: "성{{c1::공::공 공(功)}}의 비결은 성실함이다.", explain: "활용: 공로(功勞), 성공(成功)" },
        { id: "hj6_3", term: "信", answer: "믿을 신", sentence: "친구 사이에 {{c1::신::믿을 신(信)}}뢰가 가장 중요하다.", explain: "활용: 신뢰(信賴), 자신(自信)" },
        { id: "hj6_4", term: "義", answer: "옳을 의", sentence: "사회 정{{c1::의::옳을 의(義)}}를 실천한다.", explain: "활용: 정의(正義), 의무(義務)" },
      ],
    },
    {
      collection_id: "khist:essential",
      level_label: "한국사능력검정 핵심 필수 개념",
      item_count: 5,
      unlocked: true,
      items: [
        { id: "kh_1", term: "강화도 조약", answer: "강화도 조약", prompt: "1876년 운요호 사건을 계기로 일본과 체결한 조선 최초의 근대적 불평등 조약은?", sentence: "1876년 체결된 {{c1::강화도 조약::조일수호조규}}은 부산 외 2개 항구 개항과 영사재판권을 포함했다.", explain: "정식 명칭: 조·일 수호 조규 (자주국 규정, 해안측량권, 치외법권)" },
        { id: "kh_2", term: "갑신정변", answer: "갑신정변", prompt: "1884년 김옥균·박영효 등 급진개화파가 우정총국 개국 축하연을 이용해 일으킨 근대화 개혁 운동은?", sentence: "급진개화파는 1884년 {{c1::갑신정변::우정총국 정변}}을 일으켜 14개조 개혁 정강을 발표했다.", explain: "청에 대한 사대 관계 청산, 인민 평등권 확립, 호조 재정 일원화 주장" },
        { id: "kh_3", term: "동학 농민 운동", answer: "동학 농민 운동", prompt: "1894년 전봉준 등을 중심으로 제폭구민·보국안민을 내걸고 반봉건·반외세를 외친 농민 봉기는?", sentence: "1894년 {{c1::동학 농민 운동::전봉준·집강소}}은 황토현·황룡촌 전투 승리 후 전주 화약을 맺고 집강소를 설치했다.", explain: "고부 농민 봉기 → 백산 봉기 → 황토현 승리 → 전주화약(집강소) → 우금치 전투" },
        { id: "kh_4", term: "독립협회", answer: "독립협회", prompt: "1896년 서재필 등이 중심이 되어 독립문 건립과 만민공동회 개최를 주도한 근대 민권 단체는?", sentence: "{{c1::독립협회::만민공동회·헌의6조}}는 러시아의 절영도 조차 요구를 저지하고 관민공동회에서 헌의 6조를 결의했다.", explain: "기관지 독립신문 발행, 자주국권·자유민권·자강개혁 운동 전개" },
        { id: "kh_5", term: "3·1 운동", answer: "3·1 운동", prompt: "1919년 일제의 무단 통치에 맞서 민족자결주의와 고종 인산일을 계기로 전국에서 일어난 최대 규모의 독립 만세 운동은?", sentence: "1919년 {{c1::3·1 운동::대한민국 임시정부 수립 계기}}의 결과 일제는 통치 방식을 이른바 문화 통치로 바꾸고 상하이에 대한민국 임시정부가 수립되었다.", explain: "비폭력 평화 시위에서 전국적·전 계층적 항일 운동으로 확산" },
      ],
    },
    {
      collection_id: "exam-eng:toeic-core",
      level_label: "TOEIC 실전 빈출 핵심 어휘",
      item_count: 4,
      unlocked: true,
      items: [
        { id: "toeic_1", term: "mandatory", answer: "의무적인", sentence: "Attendance at the safety orientation is {{c1::mandatory::의무적인}} for all new employees.", explain: "동의어: compulsory, required, obligatory" },
        { id: "toeic_2", term: "reimburse", answer: "변제하다 (환급하다)", sentence: "The company will {{c1::reimburse::변제하다}} travel expenses upon receipt submission.", explain: "reimburse A for B (A에게 B 비용을 환급하다)" },
        { id: "toeic_3", term: "tentative", answer: "잠정적인", sentence: "We have set a {{c1::tentative::잠정적인}} schedule for the product launch.", explain: "tentative schedule/agreement (잠정 일정/합의)" },
        { id: "toeic_4", term: "comply", answer: "준수하다", sentence: "All contractors must {{c1::comply::준수하다}} with environmental regulations.", explain: "comply with (~을 준수하다) = abide by, conform to" },
      ],
    },
    {
      collection_id: "ko-idiom:essential",
      level_label: "필수 사자성어·고사성어 핵심",
      item_count: 4,
      unlocked: true,
      items: [
        { id: "idiom_1", term: "대기만성 (大器晩成)", answer: "큰 그릇은 늦게 이루어진다", prompt: "큰 인물이 되기 위해서는 많은 노력과 시간이 필요하여 늦게 이루어진다는 뜻의 사자성어는?", sentence: "지금 당장 성과가 없더라도 {{c1::대기만성::大器晩成}}의 자세로 꾸준히 실력을 쌓아라.", explain: "大(큰 대) 器(그릇 기) 晩(늦을 만) 成(이룰 성)" },
        { id: "idiom_2", term: "역지사지 (易地思之)", answer: "처지를 바꾸어 생각함", prompt: "상대방과 처지나 입장을 바꾸어 놓고 생각한다는 뜻의 사자성어는?", sentence: "갈등을 해결하려면 먼저 상대방의 입장에서 생각하는 {{c1::역지사지::易地思之}}의 태도가 필요하다.", explain: "易(바꿀 역) 地(땅 지) 思(생각 사) 之(갈 지)" },
        { id: "idiom_3", term: "유비무환 (有備無患)", answer: "준비가 있으면 근심이 없다", prompt: "미리 철저히 준비해 두면 뒷날 걱정할 우환이 없다는 뜻의 사자성어는?", sentence: "재난에 대비해 평소 훈련을 반복하는 것은 {{c1::유비무환::有備無患}}의 지혜이다.", explain: "有(있을 유) 備(갖출 비) 無(없을 무) 患(근심 환)" },
        { id: "idiom_4", term: "일석이조 (一石二鳥)", answer: "돌 하나로 새 두 마리를 잡음", prompt: "한 가지 일을 해서 두 가지 이익을 동시에 얻는다는 뜻의 사자성어는?", sentence: "자전거 출퇴근은 건강도 챙기고 교통비도 아끼는 {{c1::일석이조::一石二鳥}}의 방법이다.", explain: "동의어: 일거양득(一擧兩得)" },
      ],
    },
    {
      collection_id: "law-statute:constitution",
      level_label: "대한민국 헌법 및 필수 법학 조문",
      item_count: 4,
      unlocked: true,
      items: [
        { id: "law_1", term: "헌법 제1조 제2항 (국민주권)", answer: "국민", prompt: "대한민국 헌법 제1조 제2항: '대한민국의 주권은 [ ___ ]에게 있고, 모든 권력은 [ ___ ]으로부터 나온다.' 빈칸에 공통으로 들어갈 말은?", sentence: "대한민국의 주권은 {{c1::국민::주권의 주체}}에게 있고, 모든 권력은 {{c1::국민}}으로부터 나온다.", explain: "헌법 제1조 제1항(민주공화국) · 제2항(국민주권주의)" },
        { id: "law_2", term: "헌법 제10조 (인간의 존엄과 가치)", answer: "행복을 추구할 권리", prompt: "헌법 제10조: '모든 국민은 인간으로서의 존엄과 가치를 가지며, [ ___ ]를 가진다.' 빈칸에 들어갈 기본권은?", sentence: "모든 국민은 인간으로서의 존엄과 가치를 가지며, {{c1::행복을 추구할 권리::헌법 제10조}}를 가진다.", explain: "국가는 개인이 가지는 불가침의 기본적 인권을 확인하고 보장할 의무를 진다." },
        { id: "law_3", term: "죄형법정주의", answer: "죄형법정주의", prompt: "'법률이 없으면 범죄도 없고 형벌도 없다'는 형사법의 대원칙은?", sentence: "{{c1::죄형법정주의::형법 대원칙}}에 따라 관습형법금지, 소급효금지, 유추해석금지, 명확성의 원칙이 도출된다.", explain: "헌법 제12조 제1항 및 제13조 제1항 근거" },
        { id: "law_4", term: "신의성실의 원칙", answer: "신의성실의 원칙", prompt: "민법 제2조 제1항: 권리의 행사와 의무의 이행은 신의에 좇아 성실히 하여야 한다는 원칙은?", sentence: "민법 제2조 제1항의 {{c1::신의성실의 원칙::민법 대원칙}}에서 금반언의 원칙과 사정변경의 원칙이 파생된다.", explain: "민법 전반을 지배하는 최고 지도 원리" },
      ],
    },
    {
      collection_id: "cert-it:core",
      level_label: "정보처리기사·CS 핵심 컴퓨터공학",
      item_count: 4,
      unlocked: true,
      items: [
        { id: "it_1", term: "트랜잭션 ACID", answer: "원자성·일관성·격리성·지속성", prompt: "데이터베이스 트랜잭션이 안전하게 수행되기 위해 보장해야 하는 4대 특성(ACID)은?", sentence: "트랜잭션의 ACID 속성은 {{c1::원자성(Atomicity)::All or Nothing}}, 일관성(Consistency), 격리성(Isolation), 지속성(Durability)이다.", explain: "Atomicity, Consistency, Isolation, Durability" },
        { id: "it_2", term: "데드락 (교착상태) 4조건", answer: "상호배제·점유대기·비선점·환형대기", prompt: "운영체제에서 교착상태(Deadlock)가 발생하기 위한 4가지 필요충분조건은?", sentence: "교착상태 발생 조건 4가지는 상호배제, 점유와 대기, 비선점, {{c1::환형 대기::Circular Wait}}이다.", explain: "4가지 조건 중 하나만 제거해도 교착상태를 예방할 수 있음" },
        { id: "it_3", term: "정규화 (BCNF)", answer: "결정자가 후보키가 아닌 함수 종속 제거", prompt: "제3정규형(3NF)을 만족하면서 모든 결정자가 후보키가 되도록 이행적·비후보키 함수 종속을 제거하는 정규화 단계는?", sentence: "{{c1::BCNF::보이스-코드 정규형}}는 강한 제3정규형으로 모든 결정자가 후보키(Candidate Key)이어야 한다.", explain: "도부이결다조 (1NF -> 2NF -> 3NF -> BCNF -> 4NF -> 5NF)" },
        { id: "it_4", term: "OSI 7계층 전송 계층", answer: "전송 계층 (Transport Layer)", prompt: "TCP와 UDP 프로토콜이 동작하며 종단 간(End-to-End) 신뢰성 있는 데이터 전송과 포트 번호 기반 다중화를 담당하는 OSI 계층은?", sentence: "OSI 4계층인 {{c1::전송 계층::TCP/UDP 계층}}은 세그먼트(Segment) 단위로 종단 간 오류 복구와 흐름 제어를 수행한다.", explain: "물리(1)-데이터링크(2)-네트워크(3)-전송(4)-세션(5)-표현(6)-응용(7)" },
      ],
    },
    {
      collection_id: "moe-hanja-1800:middle",
      level_label: "교육부 고시 한문 교육용 기초 한자 1,800자 핵심 (중·고등)",
      item_count: 6,
      unlocked: true,
      items: [
        { id: "mh_1", term: "仁", answer: "어질 인", sentence: "{{c1::어질 인::仁}}은 공자 사상의 핵심 덕목이다.", explain: "부수: 亻(사람인변) · 활용: 인의(仁義), 인자(仁慈)" },
        { id: "mh_2", term: "義", answer: "옳을 의", sentence: "견리사의(見利思{{c1::義::옳을 의}})는 이익을 보면 의로움을 먼저 생각한다는 뜻이다.", explain: "부수: 羊(양양) · 활용: 정의(正義), 의무(義務)" },
        { id: "mh_3", term: "禮", answer: "예도 예", sentence: "동방{{c1::예::예도 예(禮)}}의지국의 전통을 이어간다.", explain: "부수: 示(보일시) · 활용: 예절(禮節), 예의(禮儀)" },
        { id: "mh_4", term: "智", answer: "지혜 지", sentence: "어려울 때일수록 {{c1::지::지혜 지(智)}}혜를 모아야 한다.", explain: "부수: 日(날일) · 활용: 지혜(智慧), 지식(知識)" },
        { id: "mh_5", term: "信", answer: "믿을 신", sentence: "붕우유신(朋友有{{c1::信::믿을 신}})은 벗 사이에 믿음이 있어야 함을 뜻한다.", explain: "부수: 亻(사람인변) · 활용: 신뢰(信賴), 신의(信義)" },
        { id: "mh_6", term: "溫故知新", answer: "온고지신 — 옛것을 익히고 새것을 안다", prompt: "《논어》에서 유래한 성어로 '옛것을 익히고 그것을 미루어 새것을 안다'는 뜻의 사자성어는?", sentence: "전통을 바탕으로 현대를 창조하는 자세를 {{c1::온고지신::溫故知新}}이라 한다.", explain: "익힐 온(溫) · 옛 고(故) · 알 지(知) · 새 신(新)" },
      ],
    },
    {
      collection_id: "ko-dictation:grade1-2",
      level_label: "초등 1~2학년 급수별 받아쓰기 핵심",
      item_count: 3,
      unlocked: true,
      items: [
        { id: "kd_1", term: "맑고 따뜻합니다", answer: "맑고 따뜻합니다", prompt: "소리 나는 대로 '[말꼬 따뜨탑니다]'를 바른 맞춤법으로 쓰면?", sentence: "오늘 날씨가 참 {{c1::맑고::[말꼬]}} {{c2::따뜻합니다::[따뜨탑니다]}}.", explain: "겹받침 ㄺ을 밝혀 '맑고'로 적습니다." },
        { id: "kd_2", term: "할머니께 썼습니다", answer: "할머니께 썼습니다", prompt: "웃어른에게 편지를 드릴 때 '[할머니에게 써씀니다]'의 바른 높임·맞춤법 표기는?", sentence: "{{c1::할머니께::높임 조사}} 예쁜 편지를 {{c2::썼습니다::[써씀니다]}}.", explain: "윗사람에게는 부사격 조사 '-께'를 씁니다." },
        { id: "kd_3", term: "조용히 읽어요", answer: "조용히 읽어요", prompt: "도서관에서 책을 '[조용이 일거요]'의 바른 맞춤법 표기는?", sentence: "도서관에서 {{c1::조용히::부사}} 책을 {{c2::읽어요::[일거요]}}.", explain: "'-하다'가 붙는 어근 뒤에는 '-히'(조용히)를 적습니다." },
      ],
    },
    {
      collection_id: "moe-eng:elem-3-4",
      level_label: "교육부 고시 초등 3~4학년 기초 필수 영단어 (기본 어휘표)",
      item_count: 12,
      unlocked: true,
      items: [
        { id: "e34_01", term: "morning", answer: "아침", role: "core_vocab", sentence: "Good {{c1::morning::아침}}! How are you today?", explain: "in the morning (아침에) · 반대: evening(저녁), night(밤)" },
        { id: "e34_02", term: "weather", answer: "날씨", role: "core_vocab", sentence: "How is the {{c1::weather::날씨}} today? It is sunny.", explain: "sunny(맑은), cloudy(흐린), rainy(비 오는), snowy(눈 오는)" },
        { id: "e34_03", term: "friend", answer: "친구", role: "core_vocab", sentence: "She is my best {{c1::friend::친구}} at school.", explain: "make friends with (~와 친구가 되다)" },
        { id: "e34_04", term: "teacher", answer: "선생님", role: "core_vocab", sentence: "Our English {{c1::teacher::선생님}} is very kind.", explain: "teach(가르치다) + -er(사람) = teacher(선생님)" },
        { id: "e34_05", term: "hungry", answer: "배고픈", role: "core_vocab", sentence: "I am {{c1::hungry::배고픈}}. Let's have lunch!", explain: "thirsty(목마른), full(배부른), tired(피곤한)" },
        { id: "e34_06", term: "thirsty", answer: "목마른", role: "core_vocab", sentence: "I am {{c1::thirsty::목마른}}. Can I have some water?", explain: "drink water(물을 마시다)와 자주 함께 쓰이는 초등 필수 형용사" },
        { id: "e34_07", term: "listen", answer: "귀 기울여 듣다", role: "core_vocab", sentence: "Please {{c1::listen::듣다}} to the teacher carefully.", explain: "listen to (~을 귀 기울여 듣다, 't'는 묵음)" },
        { id: "e34_08", term: "borrow", answer: "빌리다", role: "core_vocab", sentence: "May I {{c1::borrow::빌리다}} your pencil?", explain: "borrow(빌려 오다) ↔ lend(빌려주다)" },
        { id: "e34_09", term: "animal", answer: "동물", role: "core_vocab", sentence: "What is your favorite {{c1::animal::동물}} at the zoo?", explain: "wild animals (야생 동물)" },
        { id: "e34_10", term: "umbrella", answer: "우산", role: "core_vocab", sentence: "It's raining outside. Take your {{c1::umbrella::우산}}.", explain: "모음 소리로 시작하므로 부정관사 an umbrella로 사용" },
        { id: "e34_11", term: "breakfast", answer: "아침 식사", role: "core_vocab", sentence: "I eat bread and milk for {{c1::breakfast::아침 식사}}.", explain: "breakfast(아침) - lunch(점심) - dinner(저녁)" },
        { id: "e34_12", term: "clean", answer: "청소하다", role: "core_vocab", sentence: "Let's {{c1::clean::청소하다}} our classroom together.", explain: "형용사(깨끗한)와 동사(청소하다)로 모두 쓰임" },
      ],
    },
    {
      collection_id: "moe-eng:elementary",
      level_label: "교육부 고시 초등 5~6학년 필수 영단어 800 핵심",
      item_count: 12,
      unlocked: true,
      items: [
        { id: "me_1", term: "library", answer: "도서관", role: "core_vocab", sentence: "I borrow books from the school {{c1::library::도서관}}.", explain: "school library (학교 도서관)" },
        { id: "me_2", term: "hospital", answer: "병원", role: "core_vocab", sentence: "Doctors and nurses work at the {{c1::hospital::병원}}.", explain: "go to the hospital (병원에 가다)" },
        { id: "me_3", term: "tomorrow", answer: "내일", role: "core_vocab", sentence: "See you {{c1::tomorrow::내일}} morning!", explain: "yesterday(어제) - today(오늘) - tomorrow(내일)" },
        { id: "me_4", term: "museum", answer: "박물관", role: "core_vocab", sentence: "We visited the science {{c1::museum::박물관}} on our field trip.", explain: "art museum (미술관), history museum (역사 박물관)" },
        { id: "me_5", term: "vacation", answer: "방학", role: "core_vocab", sentence: "What will you do this summer {{c1::vacation::방학}}?", explain: "summer vacation (여름방학), winter vacation (겨울방학)" },
        { id: "me_6", term: "exercise", answer: "운동하다", role: "core_vocab", sentence: "I {{c1::exercise::운동하다}} every day to stay healthy.", explain: "do exercise (운동하다), regular exercise (규칙적인 운동)" },
        { id: "me_7", term: "delicious", answer: "맛있는", role: "core_vocab", sentence: "This Korean bulgogi tastes really {{c1::delicious::맛있는}}!", explain: "감각동사 taste/look/smell 뒤에 형용사 보어로 자주 출제" },
        { id: "me_8", term: "straight", answer: "곧장", role: "core_vocab", sentence: "Go {{c1::straight::곧장}} two blocks and turn left.", explain: "길 찾기 필수 표현: go straight (직진하다)" },
        { id: "me_9", term: "between", answer: "사이에", role: "core_vocab", sentence: "The bakery is {{c1::between::사이에}} the bank and the post office.", explain: "between A and B (A와 B 사이에)" },
        { id: "me_10", term: "famous", answer: "유명한", role: "core_vocab", sentence: "Gyeongju is {{c1::famous::유명한}} for its historical temples.", explain: "be famous for (~로 유명하다)" },
        { id: "me_11", term: "practice", answer: "연습하다", role: "core_vocab", sentence: "I {{c1::practice::연습하다}} playing the piano every afternoon.", explain: "Practice makes perfect (연습이 완벽을 만든다)" },
        { id: "me_12", term: "future", answer: "미래", role: "core_vocab", sentence: "What do you want to be in the {{c1::future::미래}}?", explain: "in the future (장래에, 미래에)" },
      ],
    },
    {
      collection_id: "moe-eng:middle-1200",
      level_label: "교육부 고시 중학교 학년별 필수 영단어 1,200 & 내신 핵심 문법",
      item_count: 12,
      unlocked: true,
      items: [
        { id: "mm_01", term: "introduce", answer: "소개하다", role: "core_vocab", sentence: "Let me {{c1::introduce::소개하다}} myself to the class.", explain: "introduce A to B (A를 B에게 소개하다)" },
        { id: "mm_02", term: "communicate", answer: "의사소통하다", role: "core_vocab", sentence: "We use language to {{c1::communicate::의사소통하다}} with others.", explain: "명사형: communication (의사소통)" },
        { id: "mm_03", term: "volunteer", answer: "자원봉사하다", role: "core_vocab", sentence: "She works as a {{c1::volunteer::자원봉사자}} at the local library.", explain: "volunteer work (자원봉사 활동)" },
        { id: "mm_04", term: "environment", answer: "환경", role: "core_vocab", sentence: "We must reduce plastic waste to protect the {{c1::environment::환경}}.", explain: "environmental protection (환경 보호)" },
        { id: "mm_05", term: "experience", answer: "경험하다", role: "core_vocab", sentence: "Traveling abroad is a valuable {{c1::experience::경험}}.", explain: "명사(경험)와 동사(경험하다) 모두 핵심 출제" },
        { id: "mm_06", term: "opportunity", answer: "기회", role: "core_vocab", sentence: "Don't miss this great {{c1::opportunity::기회}} to learn.", explain: "take the opportunity (기회를 잡다), 동의어: chance" },
        { id: "mm_07", term: "achievement", answer: "성취", role: "core_vocab", sentence: "King Sejong's greatest {{c1::achievement::업적}} was creating Hunminjeongeum.", explain: "동사 achieve(성취하다) + -ment(명사화 접미사)" },
        { id: "mm_08", term: "cooperate", answer: "협력하다", role: "core_vocab", sentence: "Team members need to {{c1::cooperate::협력하다}} with one another.", explain: "명사형: cooperation (협력, 협동)" },
        { id: "mm_09", term: "persuade", answer: "설득하다", role: "core_vocab", sentence: "He tried to {{c1::persuade::설득하다}} his parents to allow the trip.", explain: "persuade + 목적어 + to부정사 (~가 …하도록 설득하다)" },
        { id: "mm_10", term: "sustainable", answer: "지속 가능한", role: "core_vocab", sentence: "Solar and wind power are {{c1::sustainable::지속 가능한}} energy sources.", explain: "sustainable development (지속 가능한 발전)" },
        { id: "mm_11", term: "[중학 핵심문법] 감각동사 + 형용사 보어", answer: "감각동사(look/sound/smell/taste/feel) + 형용사 보어", role: "key_grammar", prompt: "[중학 핵심문법] 감각동사(look, sound, smell, taste, feel) 뒤에 보어로 반드시 와야 하는 품사는?", sentence: "The cookies smell {{c1::good::형용사 보어(well 불가)}}.", explain: "감각동사 뒤에는 부사(-ly)가 올 수 없고 형용사만 보어로 옴" },
        { id: "mm_12", term: "[중학 핵심문법] 현재완료 (have/has + p.p.)", answer: "have / has + 과거분사(p.p.) (현재완료)", role: "key_grammar", prompt: "[중학 핵심문법] 과거에 시작된 동작이나 상태가 현재까지 이어질 때(경험·계속·완료·결과) 사용하는 시제 형태는?", sentence: "I {{c1::have lived::현재완료(계속)}} in Seoul for five years.", explain: "for + 기간 / since + 과거 시점과 함께 쓰이면 현재완료 계속 용법" },
      ],
    },
    {
      collection_id: "moe-eng:high-csat",
      level_label: "교육부 고시 고등학교·수능 필수 학술 어휘 (평가원 최빈출)",
      item_count: 10,
      unlocked: true,
      items: [
        { id: "mh_eng_01", term: "hypothesis", answer: "가설", role: "core_vocab", sentence: "Scientists conducted experiments to test their {{c1::hypothesis::가설}}.", explain: "복수형: hypotheses · 동사: hypothesize(가설을 세우다)" },
        { id: "mh_eng_02", term: "empirical", answer: "실증적인", role: "core_vocab", sentence: "The theory is supported by strong {{c1::empirical::실증적인}} evidence.", explain: "empirical evidence (실증적·실험적 증거) ↔ theoretical(이론적인)" },
        { id: "mh_eng_03", term: "correlation", answer: "상관관계", role: "core_vocab", sentence: "There is a strong {{c1::correlation::상관관계}} between sleep quality and memory retention.", explain: "correlation does not imply causation (상관관계가 인과관계를 의미하지는 않는다)" },
        { id: "mh_eng_04", term: "cognitive", answer: "인지의", role: "core_vocab", sentence: "Active recall strengthens {{c1::cognitive::인지의}} pathways in the brain.", explain: "cognitive psychology (인지 심리학), cognitive load (인지 부하)" },
        { id: "mh_eng_05", term: "intrinsic", answer: "내재적인", role: "core_vocab", sentence: "Curiosity provides {{c1::intrinsic::내재적인}} motivation for learning.", explain: "intrinsic(내재적인) ↔ extrinsic(외재적인)" },
        { id: "mh_eng_06", term: "inevitable", answer: "피할 수 없는", role: "core_vocab", sentence: "Technological change is {{c1::inevitable::피할 수 없는}} in modern society.", explain: "동의어: unavoidable" },
        { id: "mh_eng_07", term: "ambiguity", answer: "모호함", role: "core_vocab", sentence: "Legal contracts must be written clearly to avoid {{c1::ambiguity::모호함}}.", explain: "형용사: ambiguous (애매모호한)" },
        { id: "mh_eng_08", term: "paradox", answer: "역설", role: "core_vocab", sentence: "The {{c1::paradox::역설}} of choice suggests that too many options can reduce satisfaction.", explain: "형용사: paradoxical (역설적인)" },
        { id: "mh_eng_09", term: "undermine", answer: "약화시키다", role: "core_vocab", sentence: "Rumors can {{c1::undermine::약화시키다}} mutual trust within a team.", explain: "반의어: reinforce, strengthen (강화하다)" },
        { id: "mh_eng_10", term: "facilitate", answer: "촉진하다", role: "core_vocab", sentence: "Spaced repetition {{c1::facilitates::촉진하다}} long-term memory consolidation.", explain: "명사형: facilitator (촉진자, 진행자)" },
      ],
    },
    {
      collection_id: "moe-kor:orthography-lit",
      level_label: "교육부 국어과 필수 한글 맞춤법·표준어 & 문학 핵심 개념어",
      item_count: 6,
      unlocked: true,
      items: [
        { id: "mk_01", term: "며칠", answer: "며칠", role: "core_concept", prompt: "'오늘이 몇 월 [ ___ ]이지?'에서 어원이 분명하지 아니하여 소리 나는 대로 적는 바른 맞춤법 표기는? ('몇일'은 틀린 표기)", sentence: "오늘이 몇 월 {{c1::며칠::맞춤법 주의('몇일' 아님)}}인지 달력을 확인해 보자.", explain: "한글 맞춤법 제27항 붙임2: 언제나 '며칠'로만 적습니다." },
        { id: "mk_02", term: "금세", answer: "금세", role: "core_concept", prompt: "'지금 바로'를 뜻하는 '금시에'가 줄어든 말의 바른 맞춤법 표기는? ('금새'는 틀린 표기)", sentence: "소나기가 내리더니 {{c1::금세::'금새'가 아님}} 하늘이 맑게 개었다.", explain: "'금시에'가 줄어든 말이므로 '금세'(ㅡ+ㅔ)가 맞습니다." },
        { id: "mk_03", term: "되다 / 돼다 구분", answer: "되어(돼) · 되었다(됐다)", role: "core_concept", prompt: "어간 '되-' 뒤에 어미 '-어/-었-'이 결합하여 줄어들 때의 바른 맞춤법 표기 원칙은?", sentence: "벌써 봄이 {{c1::돼::되어}} 날씨가 따뜻해졌다.", explain: "'하-'를 넣어 말이 되면 '돼(되어)', '하니/하고'가 자연스러우면 '되'를 씁니다." },
        { id: "mk_04", term: "로서 / 로써 구분", answer: "로서(자격·신분) · 로써(수단·도구)", role: "core_concept", prompt: "조사 '로서'와 '로써'의 맞춤법 의미 차이를 구분하시오.", sentence: "학생{{c1::으로서::자격·신분}} 본분을 지키고, 대화{{c2::로써::수단·방법}} 갈등을 해결한다.", explain: "로서 = 지위·신분·자격 / 로써 = 수단·도구" },
        { id: "mk_05", term: "역설법", answer: "역설법", role: "core_concept", prompt: "'이것은 소리 없는 아우성'처럼 겉으로는 모순되지만 그 속에 진리를 담는 문학 표현 기법은?", sentence: "유치환의 〈깃발〉에서 '소리 없는 아우성'은 모순 속에 진실을 담은 {{c1::역설법::수사법}}이다.", explain: "역설법(문장 자체에 논리적 모순 존재) ↔ 반어법(속마음과 반대로 표현)" },
        { id: "mk_06", term: "객관적 상관물", answer: "객관적 상관물", role: "core_concept", prompt: "문학 작품에서 화자의 정서나 사상을 간접적으로 환기·구체화하기 위해 끌어들인 구체적 자연물·사물을 무엇이라 하는가?", sentence: "황조가의 '꾀꼬리'처럼 화자의 정서를 환기하는 대상을 {{c1::객관적 상관물::문학 개념어}}이라 한다.", explain: "화자와 대비되거나 감정이 이입된 자연물 모두 객관적 상관물에 포함됩니다." },
      ],
    },
    {
      collection_id: "sci-element-formula:core",
      level_label: "교육부 과학과 필수 주기율표 원소·물리법칙·생명·지구과학 핵심",
      item_count: 6,
      unlocked: true,
      items: [
        { id: "sc_1", term: "공유 결합", answer: "공유 결합", role: "core_concept", prompt: "비금속 원자들이 전자쌍을 내놓아 공동으로 소유하면서 형성하는 화학 결합은?", sentence: "물(H₂O)과 이산화 탄소(CO₂)는 비금속 원자들이 전자쌍을 공유하는 {{c1::공유 결합::비금속+비금속}} 물질이다.", explain: "공유 결합(비금속+비금속) ↔ 이온 결합(금속+비금속)" },
        { id: "sc_2", term: "이온 결합", answer: "이온 결합", role: "core_concept", prompt: "금속 양이온과 비금속 음이온 사이의 정전기적 인력으로 형성되는 화학 결합은?", sentence: "염화 나트륨(NaCl)은 나트륨 양이온과 염화 이온 사이의 {{c1::이온 결합::정전기적 인력}}으로 이루어진다.", explain: "수용액이나 용융 상태에서 전기 전도성이 있음" },
        { id: "sc_3", term: "미토콘드리아", answer: "미토콘드리아", role: "core_concept", prompt: "세포 호흡을 통해 포도당 등 유기물을 분해하여 생명 활동에 필요한 에너지(ATP)를 생산하는 세포 소기관은?", sentence: "{{c1::미토콘드리아::세포 호흡·ATP 합성}}는 산소를 이용해 ATP를 합성한다.", explain: "세포 호흡의 중심 소기관 (이중막 구조)" },
        { id: "sc_4", term: "옴의 법칙", answer: "V = I × R", role: "core_concept", prompt: "전기 회로에서 전압(V), 전류(I), 저항(R) 사이의 관계를 나타내는 '옴의 법칙' 관계식은?", sentence: "옴의 법칙에 따르면 전압·전류·저항의 관계식은 {{c1::V = I × R::전압 = 전류 × 저항}}이다.", explain: "전류(I)는 전압(V)에 비례하고 저항(R)에 반비례함" },
        { id: "sc_5", term: "뉴턴 운동 제2법칙", answer: "F = m × a", role: "core_concept", prompt: "물체의 가속도(a)는 알짜힘(F)에 비례하고 질량(m)에 반비례한다는 가속도 법칙 공식은?", sentence: "뉴턴의 가속도 법칙은 {{c1::F = m × a::가속도 법칙}}로 나타낸다.", explain: "제1법칙: 관성 법칙 · 제2법칙: 가속도 법칙 · 제3법칙: 작용·반작용 법칙" },
        { id: "sc_6", term: "발산형 경계", answer: "발산형 경계 (해령·열곡대)", role: "core_concept", prompt: "맨틀 대류의 상승부에서 새로운 해양 지각이 생성되며 두 판이 서로 멀어지는 판의 경계는?", sentence: "대서양 중앙 해령과 동아프리카 열곡대는 {{c1::발산형 경계::맨틀 대류 상승부}}에 해당한다.", explain: "천발 지진과 화산 활동 활발" },
      ],
    },
    {
      collection_id: "moe-math:core-formulas",
      level_label: "교육부 수학과 학년별 필수 공식 (방정식·피타고라스·삼각비·함수)",
      item_count: 5,
      unlocked: true,
      items: [
        { id: "math_01", term: "피타고라스 정리", "answer": "a² + b² = c²", role: "core_concept", prompt: "직각삼각형에서 직각을 낀 두 변의 길이를 a, b라 하고 빗변의 길이를 c라 할 때 성립하는 피타고라스 정리 관계식은?", sentence: "직각삼각형의 피타고라스 정리 공식은 {{c1::a² + b² = c²::피타고라스 정리}}이다.", explain: "대표 피타고라스 수: (3, 4, 5), (5, 12, 13), (8, 15, 17)" },
        { id: "math_02", term: "이차방정식의 근의 공식", "answer": "x = (-b ± √(b² - 4ac)) / 2a", role: "core_concept", prompt: "이차방정식 ax² + bx + c = 0 (a ≠ 0)의 해를 구하는 근의 공식은?", sentence: "이차방정식의 해는 {{c1::x = (-b ± √(b² - 4ac)) / 2a::근의 공식}}이다.", explain: "판별식 D = b² - 4ac > 0(서로 다른 두 실근), D = 0(중근), D < 0(허근)" },
        { id: "math_03", term: "근과 계수의 관계", "answer": "α + β = -b/a, αβ = c/a", role: "core_concept", prompt: "이차방정식 ax² + bx + c = 0의 두 근을 α, β라 할 때 두 근의 합(α + β)과 곱(αβ)은?", sentence: "이차방정식 두 근의 합과 곱은 {{c1::α + β = -b/a, αβ = c/a::근과 계수의 관계}}이다.", explain: "이차방정식 인수분해 항등식 비교로 유도" },
        { id: "math_04", term: "삼각함수 제곱 관계", "answer": "sin²θ + cos²θ = 1", role: "core_concept", prompt: "단위원 위에서 임의의 각 θ에 대하여 항상 성립하는 사인(sin θ)과 코사인(cos θ)의 제곱의 합 공식은?", sentence: "삼각함수 기본 항등식에 의해 {{c1::sin²θ + cos²θ = 1::삼각함수 제곱 공식}}이 성립한다.", explain: "tan θ = sin θ / cos θ" },
        { id: "math_05", term: "원의 방정식 표준형", "answer": "(x - a)² + (y - b)² = r²", role: "core_concept", prompt: "좌표평면 위에서 중심이 (a, b)이고 반지름이 r인 원의 방정식 표준형은?", sentence: "중심이 (a, b)이고 반지름이 r인 원의 방정식은 {{c1::(x - a)² + (y - b)² = r²::원의 방정식}}이다.", explain: "중심이 원점 (0, 0)이면 x² + y² = r²" },
      ],
    },
  ];

  function expandStandaloneItemByDifficulty(item, sourceTag, difficultyLevel) {
    const diff = String(difficultyLevel || "standard").toLowerCase();
    const itemId = String((item && item.id) || "");
    const srcLower = String(sourceTag || "").toLowerCase();
    const isNonVocabConcept =
      /^(kh_|hist_|sci_|sc_|law_|it_|mh_\d|kd_|id_|mk_|math_)/.test(itemId) ||
      /khist|hist|sci|math|moe-kor|law|cert|hanja|idiom|dictation/.test(srcLower);
    const defaultRole = isNonVocabConcept ? "core_concept" : "core_vocab";
    const conceptTag = `concept:${itemId}`;
    const roleTag = `role:${item.role || defaultRole}`;
    const baseTags = [sourceTag, conceptTag, roleTag];
    const explainSuffix = item.explain ? `\n\n💡 해설: ${item.explain}` : "";
    const isGrammar = item.role === "key_grammar";

    const lv1Front = item.prompt
      ? `${isGrammar ? "📐 [핵심 문법]" : "🌱 [Lv.1 핵심 개념]"} ${item.prompt}`
      : `🌱 [Lv.1 기초 인지] '${item.term}'의 뜻·의미는 무엇인가요?`;
    const lv1Back = `${item.answer}${explainSuffix}`;

    const lv2Front = item.sentence
      ? `${isGrammar ? "📐 [문법 문맥 빈칸]" : "📘 [Lv.2 문맥 빈칸]"} ${item.sentence}`
      : `📘 [Lv.2 핵심 빈칸] ${item.prompt || item.term} ➔ {{c1::${item.answer}}}`;
    const lv2Back = isGrammar ? `${item.answer}${explainSuffix}` : `${item.term} — ${item.answer}${explainSuffix}`;

    const isFactPrompt = Boolean(item.prompt && (item.term === item.answer || isGrammar));
    const lv3Front = isFactPrompt
      ? `${isGrammar ? "📐 [심화 문법 인출]" : "🔥 [Lv.3 심화 서술 인출]"} ${item.prompt}`
      : `🔥 [Lv.3 역방향 능동 산출] 뜻·정의가 '${item.answer}'에 해당하는 정확한 용어/표현을 쓰시오.`;
    const lv3Back = isFactPrompt ? `${item.answer}${explainSuffix}` : `${item.term}${explainSuffix}`;

    const cLv1 = {
      front_text: lv1Front,
      back_text: lv1Back,
      note_type: "basic",
      tags: baseTags.concat(["diff_lv1"]),
    };
    const cLv2 = {
      front_text: lv2Front,
      back_text: lv2Back,
      note_type: "cloze",
      tags: baseTags.concat(["diff_lv2"]),
    };
    const cLv3 = {
      front_text: lv3Front,
      back_text: lv3Back,
      note_type: "basic",
      tags: baseTags.concat(["diff_lv3"]),
    };

    if (diff === "lv1" || diff === "standard") return [cLv1];
    if (diff === "lv2") return [cLv2];
    if (diff === "lv3") return [cLv3];
    if (diff === "mixed" || diff === "all") return [cLv1, cLv2, cLv3];
    return [cLv1];
  }

  function createStandaloneEngine(customStorage) {
    const STORAGE_KEY = "braindeck_standalone_v56_db";
    const storageObj = customStorage || (typeof localStorage !== "undefined" ? localStorage : null);
    let memoryDbRaw = null;

    function loadDb() {
      if (storageObj) {
        try {
          const raw = storageObj.getItem(STORAGE_KEY);
          if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && Array.isArray(parsed.decks) && Array.isArray(parsed.cards)) {
              return parsed;
            }
          }
        } catch (_e) {
          // ignore
        }
      } else if (memoryDbRaw) {
        try {
          const parsed = JSON.parse(memoryDbRaw);
          if (parsed && Array.isArray(parsed.decks) && Array.isArray(parsed.cards)) {
            return parsed;
          }
        } catch (_e) {
          // ignore
        }
      }
      // Seed initial starter deck so Apple/Web users can study immediately on first launch!
      const seedCards = [];
      let nextCardId = 1;
      const engStarterItems = STANDALONE_TEXTBOOKS[0].entries.slice(0, 4).map((it) => ({
        item: it,
        srcTag: "textbook:mid1-eng-neungyul-kim",
      }));
      const histStarterItems = STANDALONE_COLLECTIONS[3].items.slice(0, 3).map((it) => ({
        item: it,
        srcTag: "khist:essential",
      }));
      engStarterItems.concat(histStarterItems).forEach(({ item: it, srcTag }) => {
        const expanded = expandStandaloneItemByDifficulty(it, srcTag, "lv1");
        expanded.forEach((spec) => {
          seedCards.push({
            card_id: nextCardId++,
            deck_id: 1,
            deck_name: "🚀 브레인덱 스타터 덱 (영어·한국사 핵심)",
            front_text: spec.front_text,
            back_text: spec.back_text,
            note_type: spec.note_type,
            tags: spec.tags,
            state: "new",
            reps: 0,
            lapses: 0,
            stability: 1.2,
            difficulty: 5.0,
            due_at: new Date().toISOString(),
          });
        });
      });

      const initialDb = {
        nextDeckId: 2,
        nextCardId,
        decks: [
          {
            deck_id: 1,
            name: "🚀 브레인덱 스타터 덱 (영어·한국사 핵심)",
            description: "아이폰·아이패드·웹 즉시 학습용 기본 탑재 덱",
          },
        ],
        cards: seedCards,
        reviewHistory: [],
      };
      saveDb(initialDb);
      return initialDb;
    }

    function saveDb(db) {
      const serialized = JSON.stringify(db);
      memoryDbRaw = serialized;
      if (storageObj) {
        try {
          storageObj.setItem(STORAGE_KEY, serialized);
        } catch (_e) {
          // ignore quota error
        }
      }
    }

    function getCatalog() {
      return {
        ok: true,
        standalone: true,
        textbooks: STANDALONE_TEXTBOOKS,
        collections: STANDALONE_COLLECTIONS,
      };
    }

    function enrichCardWithRenderedFields(card) {
      const c = Object.assign({}, card || {});
      const rawFront = String(c.front_text || c.rendered_question || "").trim();
      const rawBack = String(c.back_text || c.rendered_answer || "").trim();
      const ext = extractTargetAndExplanation(rawFront, rawBack, c.target_answer, c.extra_explanation);
      const renderedQ = rawFront.replace(/\{\{c\d+::([^:}]+)(?:::([^}]+))?\}\}/g, function (_, ans, hint) {
        return hint ? `[힌트: ${hint}]` : "[ ... ]";
      });
      c.rendered_question = renderedQ || rawFront;
      c.rendered_answer = ext.targetAnswer || rawBack;
      c.target_answer = ext.targetAnswer || rawBack;
      c.extra_explanation = ext.extraExplanation || "";
      return c;
    }

    function isCardDueNow(card, nowMs) {
      if (!card) return false;
      if (card.state === "new" || card.state === "learning" || card.state === "relearning") {
        if (!card.due_at) return true;
        const parsed = Date.parse(card.due_at);
        if (!Number.isFinite(parsed)) return true;
        return parsed <= nowMs + 60000;
      }
      if (!card.due_at) return true;
      const dueTime = Date.parse(card.due_at);
      if (!Number.isFinite(dueTime)) return true;
      return dueTime <= nowMs;
    }

    function computeDeckSummaries(db) {
      const nowMs = Date.now();
      return db.decks.map((d) => {
        const dCards = db.cards.filter((c) => Number(c.deck_id) === Number(d.deck_id));
        const dueCards = dCards.filter((c) => isCardDueNow(c, nowMs));
        const newCount = dueCards.filter((c) => c.state === "new").length;
        const learnCount = dueCards.filter((c) => c.state === "learning" || c.state === "relearning").length;
        const reviewCount = dueCards.filter((c) => c.state === "review").length;
        return {
          deck_id: d.deck_id,
          name: d.name,
          description: d.description || "",
          total_cards: dCards.length,
          due_cards: dueCards.length,
          new_count: newCount,
          learn_count: learnCount,
          review_count: reviewCount,
        };
      });
    }

    function getDashboard() {
      const db = loadDb();
      const nowMs = Date.now();
      const decks = computeDeckSummaries(db);
      const totalCards = db.cards.length;
      const dueNowCount = db.cards.filter((c) => isCardDueNow(c, nowMs)).length;
      const avgStability = totalCards > 0
        ? db.cards.reduce((acc, c) => acc + Number(c.stability || 1.2), 0) / totalCards
        : 0;
      return {
        ok: true,
        standalone: true,
        brand: "BrainDeck (브레인덱 Web/iOS)",
        decks,
        stats: {
          total_cards: totalCards,
          due_now: dueNowCount,
          reviews_today: (db.reviewHistory || []).length,
          retention_rate_30d: 92.5,
          avg_stability_days: Number(avgStability.toFixed(1)),
          leech_cards: db.cards.filter((c) => Number(c.lapses || 0) >= 3).length,
        },
      };
    }

    function getDueCards(opts) {
      const options = opts || {};
      const db = loadDb();
      const nowMs = Date.now();
      let pool = db.cards.slice();
      if (options.deck_id !== undefined && options.deck_id !== null && options.deck_id !== "") {
        pool = pool.filter((c) => Number(c.deck_id) === Number(options.deck_id));
      }
      if (!options.include_all_cards) {
        pool = pool.filter((c) => isCardDueNow(c, nowMs));
      }
      const shuffleMode = String(options.shuffle_mode || "interleaved").toLowerCase();
      if (shuffleMode !== "sequential" && pool.length > 1) {
        pool = interleaveAndShuffleStudyQueue(pool, shuffleMode);
      }
      if (options.bury_siblings !== false) {
        pool = deduplicateSessionSiblings(pool);
      }
      pool = pool.map(enrichCardWithRenderedFields);
      return {
        ok: true,
        standalone: true,
        count: pool.length,
        shuffle_mode: shuffleMode,
        cards: pool,
      };
    }

    function insertDeckWithSpecs(deckName, description, specs, shuffleMode) {
      const db = loadDb();
      const deckId = db.nextDeckId++;
      let ordered = specs.slice();
      if (shuffleMode && shuffleMode !== "sequential" && ordered.length > 1) {
        ordered = interleaveAndShuffleStudyQueue(ordered, shuffleMode);
      }
      const createdCards = ordered.map((s) => ({
        card_id: db.nextCardId++,
        deck_id: deckId,
        deck_name: deckName,
        front_text: s.front_text,
        back_text: s.back_text,
        note_type: s.note_type || (s.front_text.includes("{{c") ? "cloze" : "basic"),
        tags: Array.isArray(s.tags) ? s.tags : [],
        state: "new",
        reps: 0,
        lapses: 0,
        stability: 1.2,
        difficulty: 5.0,
        due_at: new Date().toISOString(),
      }));
      db.decks.unshift({
        deck_id: deckId,
        name: deckName,
        description: description || "",
      });
      db.cards = createdCards.concat(db.cards);
      saveDb(db);
      return {
        ok: true,
        standalone: true,
        deck_id: deckId,
        deck_name: deckName,
        saved_count: createdCards.length,
        cards: createdCards,
      };
    }

    function buildExamScopeDeck(payload) {
      const p = payload || {};
      const tb = STANDALONE_TEXTBOOKS.find((t) => t.textbook_id === p.textbook_id) || STANDALONE_TEXTBOOKS[0];
      const unitSet = new Set(Array.isArray(p.unit_ids) && p.unit_ids.length > 0 ? p.unit_ids : tb.units.map((u) => u.unit_id));
      const matched = tb.entries.filter((e) => unitSet.has(e.unit_id));
      const diff = p.difficulty_level || "standard";
      const specs = [];
      matched.forEach((e) => {
        expandStandaloneItemByDifficulty(e, e.unit_id, diff).forEach((s) => specs.push(s));
      });
      const deckName = (p.deck_name || "").trim() || `🏫 ${tb.title} (${unitSet.size}개 단원)`;
      return insertDeckWithSpecs(deckName, "시험범위 맞춤 덱", specs, p.shuffle_mode || "interleaved");
    }

    function buildCollectionDeck(payload) {
      const p = payload || {};
      const col = STANDALONE_COLLECTIONS.find((c) => c.collection_id === p.collection_id) || STANDALONE_COLLECTIONS[0];
      const diff = p.difficulty_level || "standard";
      const specs = [];
      col.items.forEach((item) => {
        expandStandaloneItemByDifficulty(item, col.collection_id, diff).forEach((s) => specs.push(s));
      });
      const deckName = (p.deck_name || "").trim() || `📚 ${col.level_label}`;
      return insertDeckWithSpecs(deckName, "급수·자격증 맞춤 덱", specs, p.shuffle_mode || "interleaved");
    }

    function buildCombinedExamDeck(payload) {
      const p = payload || {};
      const scopes = Array.isArray(p.scopes) ? p.scopes : [];
      const diff = p.difficulty_level || "mixed";
      const specs = [];
      const labels = [];

      scopes.forEach((sc) => {
        const stype = String(sc.source_type || "collection").toLowerCase();
        const refId = String(sc.ref_id || "");
        if (sc.label) labels.push(sc.label);
        if (stype === "textbook") {
          const tb = STANDALONE_TEXTBOOKS.find((t) => t.textbook_id === refId);
          if (tb) {
            const unitSet = new Set(Array.isArray(sc.unit_ids) && sc.unit_ids.length > 0 ? sc.unit_ids : tb.units.map((u) => u.unit_id));
            tb.entries.filter((e) => unitSet.has(e.unit_id)).forEach((e) => {
              expandStandaloneItemByDifficulty(e, e.unit_id, sc.difficulty_level || diff).forEach((s) => specs.push(s));
            });
          }
        } else {
          const col = STANDALONE_COLLECTIONS.find((c) => c.collection_id === refId);
          if (col) {
            col.items.forEach((item) => {
              expandStandaloneItemByDifficulty(item, col.collection_id, sc.difficulty_level || diff).forEach((s) => specs.push(s));
            });
          }
        }
      });

      const deckName = (p.deck_name || "").trim() || `🎯 통합 시험범위 (${labels.slice(0, 2).join(" + ") || `${scopes.length}개 범위`})`;
      const shuffleMode = p.interleave_shuffle === false ? "sequential" : "interleaved";
      return insertDeckWithSpecs(deckName, "다중 시험범위 교차 덱", specs, shuffleMode);
    }

    function buildSmartTextDeck(payload) {
      const p = payload || {};
      const rawText = String(p.text || p.raw_text || "").trim();
      const diff = String(p.difficulty_level || "standard").toLowerCase();
      const lines = rawText.split(/\r?\n/).map((l) => l.replace(/^[\s•\-*]+/, "").trim()).filter((l) => l.length >= 4);
      const specs = [];

      lines.forEach((line, idx) => {
        const conceptTag = `concept:doc_${idx + 1}`;
        const colonParts = line.split(/\s*(?::|—|->|→|\|)\s*/);
        if (colonParts.length >= 2 && colonParts[0].length >= 1 && colonParts[1].length >= 2) {
          const term = colonParts[0].trim();
          const defText = colonParts.slice(1).join(" — ").trim();
          const item = {
            id: `doc_${idx + 1}`,
            term,
            answer: defText,
            sentence: `{{c1::${term}::핵심 개념}}: ${defText}`,
            explain: `${term} — ${defText}`,
          };
          expandStandaloneItemByDifficulty(item, "custom_doc", diff).forEach((s) => specs.push(s));
        } else {
          const words = line.split(/\s+/).filter((w) => w.length >= 2);
          const pivot = words[0] || line.slice(0, 6);
          const clozeLine = line.replace(pivot, `{{c1::${pivot}}}`);
          specs.push({
            front_text: diff === "lv1" ? `🌱 [핵심 문장 빈칸] ${clozeLine}` : clozeLine,
            back_text: `${pivot}\n\n💡 해설: ${line}`,
            note_type: "cloze",
            tags: ["custom_doc", conceptTag, `diff_${diff}`],
          });
        }
      });

      const deckName = (p.deck_name || "").trim() || `✨ 스마트 노트 덱 (${specs.length}장)`;
      if (p.auto_save === false) {
        return { ok: true, standalone: true, deck_name: deckName, generated_count: specs.length, cards: specs };
      }
      return insertDeckWithSpecs(deckName, "노트·문서 기반 자동 생성 덱", specs, "interleaved");
    }

    function submitReview(payload) {
      const p = payload || {};
      const db = loadDb();
      const card = db.cards.find((c) => Number(c.card_id) === Number(p.card_id));
      const rating = Math.max(1, Math.min(4, Number(p.rating || 3)));
      if (!card) {
        return { ok: false, error: "Card not found" };
      }
      const nowMs = Date.now();
      const prevEvents = Array.isArray(card.review_events) ? card.review_events.slice() : [];
      db.reviewHistory.push({
        card_id: card.card_id,
        prev_state: card.state,
        prev_reps: card.reps,
        prev_lapses: card.lapses,
        prev_stability: card.stability,
        prev_difficulty: card.difficulty,
        prev_due_at: card.due_at,
        prev_review_events: prevEvents,
        rating,
        at: new Date(nowMs).toISOString(),
      });

      const nextEvents = prevEvents.concat([
        {
          event_id: `ev_${card.card_id}_${nowMs}_${prevEvents.length + 1}`,
          card_id: card.card_id,
          rating,
          ts_ms: nowMs,
          kind: String(p.kind || "REVIEW"),
          idem_key: `idem_${card.card_id}_${nowMs}_${prevEvents.length + 1}`,
        },
      ]);
      const folded = foldReviewEvents(nextEvents);
      card.review_events = nextEvents;
      card.reps = folded.reps;
      card.lapses = folded.lapses;
      card.stability = folded.s;
      card.difficulty = folded.d;

      if (rating === 1) {
        card.state = "relearning";
        card.due_at = new Date(nowMs).toISOString();
      } else if (rating === 2) {
        card.state = "learning";
        const ivlDays = Math.max(1, Math.round(card.stability));
        card.due_at = new Date(nowMs + ivlDays * DAY_MS_V56).toISOString();
      } else {
        card.state = "review";
        const ivlDays = Math.max(1, Math.round(card.stability));
        card.due_at = new Date(nowMs + ivlDays * DAY_MS_V56).toISOString();
      }
      saveDb(db);
      const schedDays = rating === 1 ? 0 : Math.max(1, Math.round(card.stability));
      const labelMap = {
        1: "10분 후 재학습",
        2: `${schedDays}일 후 복습`,
        3: `${schedDays}일 후 복습`,
        4: `${schedDays}일 후 복습`,
      };
      return {
        ok: true,
        standalone: true,
        card_id: card.card_id,
        rating,
        scheduled_days: schedDays,
        scheduled_label: labelMap[rating],
        due_at: card.due_at,
        memory: {
          state: card.state,
          reps: card.reps,
          lapses: card.lapses,
          stability: Number(card.stability.toFixed(2)),
          difficulty: Number(card.difficulty.toFixed(2)),
        },
      };
    }

    function undoLastReview() {
      const db = loadDb();
      if (!Array.isArray(db.reviewHistory) || db.reviewHistory.length === 0) {
        return { ok: false, standalone: true, error: "되돌릴 최근 복습 기록이 없습니다." };
      }
      const last = db.reviewHistory.pop();
      const card = db.cards.find((c) => Number(c.card_id) === Number(last.card_id));
      if (!card) {
        saveDb(db);
        return { ok: false, standalone: true, error: "카드를 찾을 수 없습니다." };
      }
      card.state = last.prev_state || "new";
      card.reps = Number(last.prev_reps || 0);
      card.lapses = Number(last.prev_lapses || 0);
      card.stability = Number(last.prev_stability || 1.2);
      card.difficulty = Number(last.prev_difficulty || 5.0);
      card.due_at = last.prev_due_at || new Date().toISOString();
      card.review_events = Array.isArray(last.prev_review_events) ? last.prev_review_events.slice() : [];
      saveDb(db);
      return {
        ok: true,
        standalone: true,
        card_id: card.card_id,
        restored_state: card.state,
        restored_stability: Number(card.stability.toFixed(2)),
      };
    }

    function resetStudyProgress(payload) {
      const p = payload || {};
      const db = loadDb();
      const rawDeckId = p.deck_id;
      const hasDeckFilter =
        rawDeckId !== undefined &&
        rawDeckId !== null &&
        rawDeckId !== "" &&
        rawDeckId !== "all" &&
        Number.isFinite(Number(rawDeckId));
      const targetDeckId = hasDeckFilter ? Number(rawDeckId) : null;
      const nowIso = new Date().toISOString();
      const resetCardIds = new Set();
      let resetCount = 0;

      db.cards.forEach((c) => {
        if (!c) return;
        if (targetDeckId !== null && Number(c.deck_id) !== targetDeckId) return;
        c.state = "new";
        c.reps = 0;
        c.lapses = 0;
        c.stability = 1.2;
        c.difficulty = 5.0;
        c.due_at = nowIso;
        c.review_events = [];
        resetCardIds.add(Number(c.card_id));
        resetCount += 1;
      });

      const prevHistLen = Array.isArray(db.reviewHistory) ? db.reviewHistory.length : 0;
      if (targetDeckId === null) {
        db.reviewHistory = [];
      } else if (Array.isArray(db.reviewHistory)) {
        db.reviewHistory = db.reviewHistory.filter((h) => !resetCardIds.has(Number(h && h.card_id)));
      }
      const clearedReviews = prevHistLen - (db.reviewHistory ? db.reviewHistory.length : 0);
      saveDb(db);
      return {
        ok: true,
        standalone: true,
        deck_id: targetDeckId,
        reset_cards: resetCount,
        cleared_reviews: clearedReviews,
        due_at: nowIso,
      };
    }

    function batchSaveDeck(payload) {
      const p = payload || {};
      const cards = Array.isArray(p.cards) ? p.cards : [];
      const deckName = String(p.deck_name || "사진·PDF 추출 단어장").trim();
      const specs = cards
        .map((c) => ({
          front_text: String(c.front_text || c.front || "").trim(),
          back_text: String(c.back_text || c.back || "").trim(),
          note_type: c.note_type || (String(c.front_text || "").includes("{{c") ? "cloze" : "basic"),
          tags: Array.isArray(c.tags) ? c.tags : [String(p.category || "custom_doc")],
        }))
        .filter((s) => s.front_text && s.back_text);
      return insertDeckWithSpecs(deckName, "사진·PDF 문서 추출 단어장", specs, "interleaved");
    }

    return {
      getCatalog,
      getDashboard,
      getDueCards,
      buildExamScopeDeck,
      buildCollectionDeck,
      buildCombinedExamDeck,
      buildSmartTextDeck,
      batchSaveDeck,
      submitReview,
      undoLastReview,
      resetStudyProgress,
    };
  }

  // =========================================================================
  // BrainDeck v5.6 Master Upgrade — Event Fold, Summary Sheet, Exam Print, Audio Loop
  // =========================================================================
  const DEFAULT_FSRS5_PARAMS = [
    0.40255, 1.18385, 3.17300, 15.69105, 7.19490,
    0.53450, 1.46040, 0.00460, 1.54575, 0.11920,
    1.01925, 1.93950, 0.11000, 0.29605, 2.26980,
    0.23150, 2.98980, 0.51655, 0.66210,
  ];
  const DAY_MS_V56 = 86400000;

  function quantize1e6(x) {
    return Math.round(Number(x) * 1000000) / 1000000;
  }

  function clampV56(val, lo, hi) {
    return Math.max(lo, Math.min(hi, val));
  }

  function foldReviewEvents(events, params) {
    const w = Array.isArray(params) && params.length >= 19 ? params.map(Number) : DEFAULT_FSRS5_PARAMS;
    const rawList = Array.isArray(events) ? events.slice() : [];
    const ordered = rawList.sort((a, b) => {
      const dt = Number(a.ts_ms) - Number(b.ts_ms);
      if (dt !== 0) return dt;
      return String(a.event_id).localeCompare(String(b.event_id));
    });

    const seenIdem = new Set();
    const voidedIds = new Set();
    const deduped = [];

    for (let i = 0; i < ordered.length; i += 1) {
      const ev = ordered[i] || {};
      const eid = String(ev.event_id || "").trim();
      const ikey = String(ev.idem_key || "").trim();
      if (!eid || !ikey) throw new Error("event_id and idem_key must be non-empty");
      if (seenIdem.has(ikey)) continue;
      seenIdem.add(ikey);
      if (ev.kind === "VOID") {
        if (ev.voids) voidedIds.add(String(ev.voids));
        continue;
      }
      deduped.push(ev);
    }

    let s = 0.0;
    let d = 0.0;
    let due_ms = 0;
    let last_ts_ms = null;
    let reps = 0;
    let lapses = 0;

    for (let i = 0; i < deduped.length; i += 1) {
      const ev = deduped[i];
      if (voidedIds.has(String(ev.event_id))) continue;
      if (ev.kind === "CRAM") continue;

      const g = Number(ev.rating || 3);
      const now_ms = Number(ev.ts_ms);

      if (reps === 0 || last_ts_ms === null || s <= 0.0) {
        s = quantize1e6(Math.max(0.1, w[g - 1]));
        const d0 = w[4] - Math.exp(w[5] * (g - 1)) + 1.0;
        d = quantize1e6(clampV56(d0, 1.0, 10.0));
        reps = 1;
        last_ts_ms = now_ms;
        const ivlDays = Math.max(1, Math.round(s));
        due_ms = now_ms + ivlDays * DAY_MS_V56;
        continue;
      }

      const elapsedDays = Math.max(0.0, (now_ms - last_ts_ms) / DAY_MS_V56);
      const rNow = quantize1e6(Math.pow(1.0 + (19.0 / 81.0) * (elapsedDays / Math.max(0.1, s)), -0.5));

      const d0Good = w[4] - Math.exp(w[5] * 2.0) + 1.0;
      const deltaD = -w[6] * (g - 3.0);
      const dPrime = d + deltaD * ((10.0 - d) / 9.0);
      const dNext = quantize1e6(clampV56(w[7] * d0Good + (1.0 - w[7]) * dPrime, 1.0, 10.0));

      let sNext = s;
      if (elapsedDays < 1.0 && ev.kind === "REVIEW_AHEAD") {
        sNext = quantize1e6(clampV56(s * Math.exp(w[17] * (g - 3.0 + w[18])), 0.1, 36500.0));
        if (g === 1) lapses += 1;
      } else if (g === 1) {
        lapses += 1;
        const sFail =
          w[11] *
          Math.pow(dNext, -w[12]) *
          (Math.pow(s + 1.0, w[13]) - 1.0) *
          Math.exp(w[14] * (1.0 - rNow));
        sNext = quantize1e6(clampV56(Math.min(s, sFail), 0.1, 36500.0));
      } else {
        const hardPenalty = g === 2 ? w[15] : 1.0;
        const easyBonus = g === 4 ? w[16] : 1.0;
        const inc =
          Math.exp(w[8]) *
          (11.0 - dNext) *
          Math.pow(s, -w[9]) *
          (Math.exp(w[10] * (1.0 - rNow)) - 1.0) *
          hardPenalty *
          easyBonus;
        sNext = quantize1e6(clampV56(s * (1.0 + inc), 0.1, 36500.0));
      }

      s = sNext;
      d = dNext;
      reps += 1;
      last_ts_ms = now_ms;
      const ivlDays = g === 1 ? 1 : Math.max(1, Math.round(s));
      due_ms = now_ms + ivlDays * DAY_MS_V56;
    }

    return { s, d, due_ms, last_ts_ms, reps, lapses };
  }

  function buildSummarySheetView(cards, maskMode = "red_filter") {
    const list = Array.isArray(cards) ? cards : [];
    const rows = list.map((c, idx) => {
      const ext = extractTargetAndExplanation(c.front_text || c.rendered_question, c.back_text || c.rendered_answer, c.target_answer, c.extra_explanation);
      return {
        index: idx + 1,
        card_id: c.card_id,
        question: String(c.rendered_question || c.front_text || "").replace(/\{\{c\d+::([^:}]+)(?:::[^}]+)?\}\}/g, "[ $1 ]"),
        clean_answer: ext.targetAnswer || String(c.rendered_answer || c.back_text || ""),
        extra: ext.extraExplanation || "",
        lapses: Number(c.lapses || 0),
      };
    });
    return {
      mask_mode: maskMode || "red_filter",
      total_rows: rows.length,
      rows,
    };
  }

  function buildPrintableExamSheet(cards, title = "BrainDeck 2단 실전 쪽지시험지", seed = 20261022) {
    const list = Array.isArray(cards) ? cards.slice() : [];
    let s = Number(seed) || 20261022;
    function nextRand() {
      s = (s * 1664525 + 1013904223) % 4294967296;
      return s / 4294967296;
    }
    for (let i = list.length - 1; i > 0; i -= 1) {
      const j = Math.floor(nextRand() * (i + 1));
      const tmp = list[i];
      list[i] = list[j];
      list[j] = tmp;
    }
    const items = list.map((c, idx) => {
      const ext = extractTargetAndExplanation(c.front_text || c.rendered_question, c.back_text || c.rendered_answer, c.target_answer, c.extra_explanation);
      const qText = String(c.rendered_question || c.front_text || "").replace(/\{\{c\d+::[^:}]+(?:::([^}]+))?\}\}/g, " [ ______ ] ");
      return {
        number: idx + 1,
        card_id: c.card_id,
        question: qText,
        answer: ext.targetAnswer || String(c.rendered_answer || c.back_text || ""),
        explanation: ext.extraExplanation || "",
      };
    });

    const qRowsHtml = items
      .map(
        (it) =>
          `<div style="break-inside:avoid;margin-bottom:12px;padding-bottom:8px;border-bottom:1px dashed #cbd5e1;">
            <div style="font-weight:700;font-size:13px;color:#0f172a;">${it.number}. ${it.question}</div>
            <div style="margin-top:6px;font-size:12px;color:#64748b;">정답: ________________________</div>
          </div>`
      )
      .join("");

    const ansRowsHtml = items
      .map(
        (it) =>
          `<div style="font-size:12px;margin-bottom:4px;"><strong>${it.number}번:</strong> <span style="color:#be123c;font-weight:700;">${it.answer}</span> ${
            it.explanation ? `<span style="color:#64748b;">(${it.explanation})</span>` : ""
          }</div>`
      )
      .join("");

    const printable_html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>${title}</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Pretendard", sans-serif; padding: 24px; color: #0f172a; }
        .header { display:flex; justify-content:space-between; align-items:center; border-bottom: 2px solid #0f172a; padding-bottom: 10px; margin-bottom: 18px; }
        .two-col { column-count: 2; column-gap: 28px; }
        .ans-page { page-break-before: always; margin-top: 32px; padding-top: 16px; border-top: 2px solid #0f172a; }
        @media print { .no-print { display: none; } }
      </style></head><body>
      <div class="no-print" style="margin-bottom:16px;display:flex;gap:10px;">
        <button onclick="window.print()" style="padding:10px 18px;background:#1b64da;color:#fff;border:none;border-radius:10px;font-weight:800;cursor:pointer;">🖨️ 인쇄 / PDF 저장</button>
      </div>
      <div class="header">
        <div><h1 style="margin:0;font-size:20px;">📝 ${title}</h1><div style="font-size:12px;color:#475569;margin-top:4px;">BrainDeck v5.6 2단 실전 쪽지시험지 (총 ${items.length}문항)</div></div>
        <div style="font-size:13px;">이름: ____________ &nbsp; 점수: _____ / ${items.length}</div>
      </div>
      <div class="two-col">${qRowsHtml}</div>
      <div class="ans-page">
        <h2 style="font-size:16px;margin:0 0 12px 0;">🔑 빠른 채점 정답 및 해설지</h2>
        <div class="two-col">${ansRowsHtml}</div>
      </div>
      </body></html>`;

    return {
      title,
      column_count: 2,
      items,
      question_sheet: items,
      answer_key: items,
      printable_html,
    };
  }

  function buildCommuteAudioScript(cards, thinkSeconds = 3) {
    const list = Array.isArray(cards) ? cards : [];
    const waitSec = Math.max(1, Math.min(10, Number(thinkSeconds) || 3));
    const tracks = list.map((c, idx) => {
      const ext = extractTargetAndExplanation(c.front_text || c.rendered_question, c.back_text || c.rendered_answer, c.target_answer, c.extra_explanation);
      return {
        index: idx + 1,
        card_id: c.card_id,
        prompt_tts: String(c.rendered_question || c.front_text || "").replace(/\[[^\]]+\]/g, "빈칸"),
        pause_seconds: waitSec,
        answer_tts: ext.targetAnswer || String(c.rendered_answer || c.back_text || ""),
      };
    });
    return {
      think_seconds: waitSec,
      total_tracks: tracks.length,
      tracks,
    };
  }

  function chunkMicroSprints(cards, sprintSize = 7) {
    const list = Array.isArray(cards) ? cards : [];
    const sz = Math.max(3, Math.min(15, Number(sprintSize) || 7));
    const totalSprints = Math.max(1, Math.ceil(list.length / sz));
    const sprints = [];
    for (let i = 0; i < list.length; i += sz) {
      const idx = Math.floor(i / sz) + 1;
      const chunk = list.slice(i, i + sz);
      sprints.push({
        sprint_index: idx,
        total_sprints: totalSprints,
        cards: chunk,
        checkpoint_label: `🏁 스프린트 ${idx} / ${totalSprints} (${chunk.length}장)`,
      });
    }
    return sprints;
  }

  // =========================================================================
  // Gate T43: Type-Homogeneous 4-Choice Distractor Isolation & Question-Type Filter
  // =========================================================================
  const TYPE_FALLBACK_DISTRACTOR_BANK = {
    eng_vocab_meaning: [
      "소개하다",
      "가장 좋아하는",
      "악기",
      "함께",
      "맛있는",
      "전통적인",
      "자원봉사하다",
      "의무적인",
      "준수하다",
      "경험하다",
    ],
    eng_vocab_word: [
      "introduce",
      "favorite",
      "instrument",
      "together",
      "delicious",
      "traditional",
      "volunteer",
      "mandatory",
      "comply",
      "communicate",
    ],
    eng_grammar: [
      "doesn't (does not) + 동사원형",
      "am / are / is + 동사원형-ing (현재진행형)",
      "감각동사(look/sound/smell/taste/feel) + 형용사 보어",
      "have / has + 과거분사(p.p.) (현재완료)",
      "조동사(will/can/must) + 동사원형",
      "전치사(at/in/of) + 동명사(-ing)",
      "주격 관계대명사 who / which / that + 불완전 절",
    ],
    hanja_hun_eum: [
      "배울 학",
      "학교 교",
      "날 생",
      "나라 국",
      "백성 민",
      "가르칠 교",
      "집 가",
      "마음 심",
      "이룰 성",
      "믿을 신",
    ],
    hanja_char: ["學", "校", "生", "國", "民", "敎", "家", "心", "成", "信"],
    idiom: ["대기만성 (大器晩成)", "역지사지 (易地思之)", "유비무환 (有備無患)", "일석이조 (一石二鳥)", "우공이산 (愚公移山)"],
    history: ["강화도 조약", "함무라비 법전", "훈민정음", "경국대전", "갑신정변", "동학 농민 운동", "독립협회", "3·1 운동"],
    science: ["공유 결합", "이온 결합", "활성화 에너지", "미토콘드리아", "옴의 법칙 (V = IR)", "원자성·일관성·격리성·지속성"],
    ko_dictation: ["맑고 따뜻합니다", "할머니께 썼습니다", "조용히 읽어요", "깨끗이 씻어요", "같이 걸어요"],
    general_concept: [
      "핵심 원리 및 개념 정의",
      "상호 배제와 동기화 조건",
      "원인과 결과의 상관관계",
      "필수 성립 요건 및 예외 조항",
      "구조적 특징과 작동 원리",
    ],
  };

  function classifyCardQuestionType(card) {
    const c = card || {};
    const front = String(c.front_text || c.rendered_question || "").trim();
    const back = String(c.back_text || c.rendered_answer || "").trim();
    const ext = extractTargetAndExplanation(front, back, c.target_answer, c.extra_explanation);
    const target = String(ext.targetAnswer || back).trim();
    const rawTags = c.tags || [];
    const tagStr = (Array.isArray(rawTags) ? rawTags.join(" ") : String(rawTags)).toLowerCase();

    const hasCjk = /[\u4e00-\u9fff]/.test(front + " " + target);
    const isAsciiAlpha = Boolean(target) && /^[A-Za-z\s~'.,?!-]+$/.test(target) && /[A-Za-z]/.test(target);
    const isAsciiTarget =
      isAsciiAlpha &&
      target.split(/\s+/).filter(Boolean).length <= 3 &&
      !target.endsWith(".");

    if (
      tagStr.includes("role:key_grammar") ||
      tagStr.includes("grammar") ||
      front.includes("핵심문법") ||
      front.includes("[문법") ||
      front.includes("핵심 문법") ||
      front.includes("문법 빈칸") ||
      front.includes("어법") ||
      target.includes("동사원형") ||
      target.includes("과거분사") ||
      target.includes("현재분사") ||
      target.includes("형용사 보어") ||
      target.includes("관계대명사") ||
      target.includes("현재진행형")
    ) {
      return {
        category_key: "grammar",
        facet_key: "eng_grammar",
        badge_label: "📐 영문법·어법",
        short_label: "문법",
      };
    }

    if (tagStr.includes("idiom") || front.includes("사자성어") || front.includes("고사성어")) {
      return {
        category_key: "hanja",
        facet_key: "idiom",
        badge_label: "📜 사자성어",
        short_label: "한자·성어",
      };
    }

    if (tagStr.includes("hanja") || front.includes("[한자") || hasCjk) {
      if (target.length <= 2 && /[\u4e00-\u9fff]/.test(target)) {
        return {
          category_key: "hanja",
          facet_key: "hanja_char",
          badge_label: "漢字 한자 자형",
          short_label: "한자·성어",
        };
      }
      return {
        category_key: "hanja",
        facet_key: "hanja_hun_eum",
        badge_label: "漢字 한자 훈음",
        short_label: "한자·성어",
      };
    }

    if (tagStr.includes("dictation") || front.includes("받아쓰기") || front.includes("맞춤법")) {
      return {
        category_key: "vocab",
        facet_key: "ko_dictation",
        badge_label: "✏️ 맞춤법·받아쓰기",
        short_label: "단어·어휘",
      };
    }

    const combinedLower = `${front} ${back} ${tagStr}`.toLowerCase();
    const historyKeywords = [
      "한국사",
      "세계사",
      "역사",
      "조약",
      "정변",
      "운동",
      "봉기",
      "독립협회",
      "법전",
      "훈민정음",
      "경국대전",
      "카스트제",
      "왕조",
      "세조",
      "세종",
      "성종",
      "전봉준",
      "김옥균",
      "서재필",
      "개화파",
      "조선",
      "일제",
      "바빌로니아",
    ];
    if (
      tagStr.includes("hist") ||
      tagStr.includes("khist") ||
      tagStr.includes("kh_") ||
      historyKeywords.some((kw) => combinedLower.includes(kw))
    ) {
      return {
        category_key: "history_sci",
        facet_key: "history",
        badge_label: "🏛️ 역사 개념",
        short_label: "역사·과학·전공",
      };
    }

    const scienceKeywords = [
      "결합",
      "에너지",
      "트랜잭션",
      "헌법",
      "법칙",
      "미토콘드리아",
      "교착상태",
      "계층",
      "정규화",
      "세포",
      "염색체",
      "전자쌍",
      "피타고라스",
      "방정식",
      "삼각함수",
      "판별식",
      "수학 공식",
      "해령",
      "열곡대",
    ];
    if (
      tagStr.includes("sci") ||
      tagStr.includes("math") ||
      tagStr.includes("law") ||
      tagStr.includes("cert") ||
      scienceKeywords.some((kw) => combinedLower.includes(kw))
    ) {
      return {
        category_key: "history_sci",
        facet_key: "science",
        badge_label: "🔬 과학·전공 개념",
        short_label: "역사·과학·전공",
      };
    }

    if (isAsciiTarget) {
      return {
        category_key: "vocab",
        facet_key: "eng_vocab_word",
        badge_label: "🔤 영단어 스펠링·빈칸",
        short_label: "단어·어휘",
      };
    }

    if (isAsciiAlpha) {
      return {
        category_key: "history_sci",
        facet_key: "general_concept",
        badge_label: "💡 핵심 개념·정의",
        short_label: "역사·과학·전공",
      };
    }

    const frontWithoutCloze = front.replace(/\{\{c\d+::|::[^}]*\}\}|\}\}|\[Lv\.\d+[^\]]*\]|\bLv\.\d+\b/gi, " ");
    const tagStrWithoutDefaultRole = tagStr.replace(/role:core_vocab/g, " ");
    const hasEnglishInFront = /[A-Za-z]/.test(frontWithoutCloze);
    const hasVocabSignal =
      hasEnglishInFront ||
      /eng|vocab|word|toeic|teps|toefl|opic|lang|mid1|elem/.test(tagStrWithoutDefaultRole) ||
      front.includes("영단어") ||
      front.includes("어휘") ||
      front.includes("단어") ||
      front.includes("숙어");
    if (!hasVocabSignal) {
      return {
        category_key: "history_sci",
        facet_key: "general_concept",
        badge_label: "💡 핵심 개념·정의",
        short_label: "역사·과학·전공",
      };
    }

    return {
      category_key: "vocab",
      facet_key: "eng_vocab_meaning",
      badge_label: "📘 단어 뜻·어휘",
      short_label: "단어·어휘",
    };
  }

  function filterStudyQueueByQuestionType(cards, categoryKey = "all") {
    const list = Array.isArray(cards) ? cards : [];
    const key = String(categoryKey || "all").trim().toLowerCase();
    if (!key || key === "all") return list.slice();
    return list.filter((c) => {
      const qtype = classifyCardQuestionType(c);
      return qtype.category_key === key || qtype.facet_key === key;
    });
  }

  function computeQuestionTypeCounts(cards) {
    const list = Array.isArray(cards) ? cards : [];
    const counts = {
      all: list.length,
      vocab: 0,
      grammar: 0,
      hanja: 0,
      history_sci: 0,
    };
    list.forEach((c) => {
      const cat = classifyCardQuestionType(c).category_key;
      if (Object.prototype.hasOwnProperty.call(counts, cat)) {
        counts[cat] += 1;
      }
    });
    return counts;
  }

  function _seededFisherYatesJs(items, seedVal) {
    const arr = Array.isArray(items) ? items.slice() : [];
    let state = (Math.abs(Number(seedVal) || 1) * 1664525 + 1013904223) % 4294967296;
    for (let i = arr.length - 1; i > 0; i -= 1) {
      state = (state * 1664525 + 1013904223) % 4294967296;
      const j = state % (i + 1);
      const tmp = arr[i];
      arr[i] = arr[j];
      arr[j] = tmp;
    }
    return arr;
  }

  function buildTypeMatchedQuizOptions(card, deckCards, requiredOptions = 4) {
    const c = card || {};
    const qtype = classifyCardQuestionType(c);
    const facetKey = qtype.facet_key;
    const front = String(c.front_text || c.rendered_question || "").trim();
    const back = String(c.back_text || c.rendered_answer || "").trim();
    const ext = extractTargetAndExplanation(front, back, c.target_answer, c.extra_explanation);
    const targetAnswer = String(ext.targetAnswer || back || "정답").trim();

    const cid = Number(c.card_id || 1);
    const reps = Math.max(0, Number(c.reps || 0));
    const distractors = [];
    const seenNorm = new Set([targetAnswer.toLowerCase()]);

    const pool = Array.isArray(deckCards) ? deckCards : [];
    const poolCandidates = [];
    for (let i = 0; i < pool.length; i += 1) {
      const other = pool[i] || {};
      if (Number(other.card_id || -1) === cid && cid !== 0) continue;
      const otherQtype = classifyCardQuestionType(other);
      if (otherQtype.facet_key !== facetKey) continue;
      const oFront = String(other.front_text || other.rendered_question || "").trim();
      const oBack = String(other.back_text || other.rendered_answer || "").trim();
      const oExt = extractTargetAndExplanation(oFront, oBack, other.target_answer, other.extra_explanation);
      const cand = String(oExt.targetAnswer || oBack).trim();
      if (!cand) continue;
      const norm = cand.toLowerCase();
      if (seenNorm.has(norm)) continue;
      seenNorm.add(norm);
      poolCandidates.push(cand);
    }

    const shuffledPool = _seededFisherYatesJs(poolCandidates, cid * 31 + reps * 997 + 17);
    for (let i = 0; i < shuffledPool.length; i += 1) {
      if (distractors.length >= requiredOptions - 1) break;
      distractors.push(shuffledPool[i]);
    }

    const fallbackPool = _seededFisherYatesJs(
      TYPE_FALLBACK_DISTRACTOR_BANK[facetKey] || TYPE_FALLBACK_DISTRACTOR_BANK.eng_vocab_meaning,
      cid * 73 + reps * 389 + 53
    );
    for (let i = 0; i < fallbackPool.length; i += 1) {
      if (distractors.length >= requiredOptions - 1) break;
      const cand = fallbackPool[i];
      const norm = cand.toLowerCase();
      if (seenNorm.has(norm)) continue;
      seenNorm.add(norm);
      distractors.push(cand);
    }

    const rawOptions = [targetAnswer].concat(distractors.slice(0, Math.max(0, requiredOptions - 1)));
    const shuffledOptions = _seededFisherYatesJs(rawOptions, cid * 131 + reps * 521 + 2026);

    return {
      ok: true,
      question_type: qtype,
      question_facet: qtype.badge_label,
      target_answer: targetAnswer,
      options: shuffledOptions,
      tap_blocks: targetAnswer.split(/\s+/).filter(Boolean),
    };
  }

  return {
    formatRetentionBadge,
    formatLeechBadge,
    mapKeyboardShortcut,
    buildForgettingCurveSvgPoints,
    formatCategoryBadge,
    formatPatternBadge,
    OLLAMA_CLOUD_MODELS,
    isOllamaCloudModelBlocked,
    formatIngestStatusBanner,
    STORE_CATEGORY_LABELS,
    filterStorePacks,
    formatStorePackCard,
    resolveUiUxTokens,
    calculateStoreBundleQuote,
    formatRatingButtonsForAgeTier,
    formatApiErrorBanner,
    evaluateTapBlockAttempt,
    NAVIGATION_TABS,
    ONBOARDING_MODES,
    DIFFICULTY_LEVEL_MODES,
    resolveActivePageState,
    evaluateTypedAnswerUnderstanding,
    computeAnkiQueueCounts,
    filterStudyQueue,
    extractTargetAndExplanation,
    generateProgressiveHint,
    interleaveAndShuffleStudyQueue,
    buildLearnerProfilePreset,
    normalizeLearnerProfile,
    resolveCardSolveMode,
    resolveAllowedRatings,
    deduplicateSessionSiblings,
    createStandaloneEngine,
    quantize1e6,
    foldReviewEvents,
    buildSummarySheetView,
    buildPrintableExamSheet,
    buildCommuteAudioScript,
    chunkMicroSprints,
    classifyCardQuestionType,
    filterStudyQueueByQuestionType,
    computeQuestionTypeCounts,
    buildTypeMatchedQuizOptions,
  };
});


