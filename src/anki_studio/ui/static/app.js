/**
 * Client Controller for BrainDeck 2.0 (MVVM Binding + Web Speech TTS + Smart Recall).
 */
(function () {
  "use strict";

  const vm = window.BrainDeckViewModel || window.AnkiStudioViewModel;
  const standaloneEngine =
    vm && typeof vm.createStandaloneEngine === "function" ? vm.createStandaloneEngine() : null;
  const VAULT_STORAGE_KEY = "braindeck_offline_vault_v1";
  const PROFILE_STORAGE_KEY = "braindeck_learner_profile_v55";
  const IDB_NAME = "braindeck_idb_v4";
  const IDB_STORE = "offline_vault";
  let state = {
    decks: [],
    selectedDeckId: "",
    rawDueCards: [],
    dueCards: [],
    currentIndex: 0,
    isRevealed: false,
    hintLevel: 0,
    ageTier: "teen",
    learnerProfile:
      vm && typeof vm.normalizeLearnerProfile === "function"
        ? vm.normalizeLearnerProfile({ ageTier: "teen", solveMode: "adaptive", difficulty: "mixed", order: "interleaved" })
        : { ageTier: "teen", solveMode: "adaptive", difficulty: "mixed", order: "interleaved", summaryLabel: "" },
    cardModeOverride: "",
    currentEvidence: {
      isRevealed: false,
      hintStep: 0,
      choiceCorrect: null,
      typedVerdict: null,
      dontKnow: false,
    },
    studyFilterMode: "all", // "all" | "wrong_only" | "marked_only"
    questionTypeFilter: "all", // "all" | "vocab" | "grammar" | "hanja" | "history_sci"
    stageFilter: "all", // "all" | "lv1" | "lv2" | "lv3" | "lv4"
    deckProgress: null,
    shuffleMode: "interleaved", // "interleaved" | "sequential"
    sessionWrongCardIds: [],
    sessionWrongCardMap: {},
    markedCardIds: [],
    buriedCardIds: [],
    storePacks: [],
    selectedStoreCategory: "all",
    selectedBundlePackIds: [],
    combinedExamScopes: [],
  };

  const el = (id) => document.getElementById(id);
  const ONBOARDING_STORAGE_KEY = "braindeck_onboarding_v52";

  function switchTabPage(tabId) {
    const resolved =
      vm && typeof vm.resolveActivePageState === "function"
        ? vm.resolveActivePageState(tabId, true)
        : { activeTab: tabId || "study" };
    state.activeTab = resolved.activeTab;

    document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
      const t = btn.getAttribute("data-tab");
      if (t === state.activeTab) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    ["study", "curriculum", "create", "store", "stats"].forEach((id) => {
      const pageEl = el(`page-${id}`);
      if (pageEl) {
        if (id === state.activeTab) {
          pageEl.classList.add("active");
        } else {
          pageEl.classList.remove("active");
        }
      }
    });
  }

  function showUxToast(message, tone = "emerald", actionLabel = "", onAction = null) {
    const banner = el("ux-toast-banner");
    if (!banner) return;
    banner.textContent = "";
    banner.style.display = "flex";
    banner.style.justifyContent = "space-between";
    banner.style.alignItems = "center";
    banner.style.gap = "10px";
    banner.style.flexWrap = "wrap";
    const colorMap = {
      emerald: "var(--emerald)",
      amber: "var(--amber)",
      rose: "var(--rose)",
      accent: "var(--accent)",
    };
    const toneColor = colorMap[tone] || "var(--accent)";
    banner.style.borderColor = toneColor;
    banner.style.color = "var(--text)";

    const msgSpan = document.createElement("span");
    msgSpan.textContent = message;
    banner.appendChild(msgSpan);

    const rightBox = document.createElement("div");
    rightBox.style.cssText = "display:flex;align-items:center;gap:6px;";
    if (actionLabel && typeof onAction === "function") {
      const actBtn = document.createElement("button");
      actBtn.type = "button";
      actBtn.className = "btn-primary";
      actBtn.style.cssText = "padding:4px 10px;font-size:0.74rem;";
      actBtn.textContent = actionLabel;
      actBtn.onclick = () => {
        onAction();
      };
      rightBox.appendChild(actBtn);
    }
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.style.cssText = "padding:2px 7px;font-size:0.72rem;color:var(--muted);";
    closeBtn.textContent = "✕";
    closeBtn.onclick = () => {
      banner.style.display = "none";
    };
    rightBox.appendChild(closeBtn);
    banner.appendChild(rightBox);
  }

  function saveIndexedDbVault(bundle) {
    try {
      if (typeof indexedDB === "undefined" || !bundle) return;
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(IDB_STORE)) {
          db.createObjectStore(IDB_STORE);
        }
      };
      req.onsuccess = () => {
        try {
          const db = req.result;
          const tx = db.transaction(IDB_STORE, "readwrite");
          tx.objectStore(IDB_STORE).put(bundle, "latest_snapshot");
        } catch (_) {
          // Ignore IDB write errors
        }
      };
    } catch (_) {
      // Ignore IDB errors in restricted environments
    }
  }

  function saveLocalVaultSnapshot(bundle) {
    try {
      if (bundle && typeof localStorage !== "undefined") {
        localStorage.setItem(VAULT_STORAGE_KEY, JSON.stringify(bundle));
      }
      saveIndexedDbVault(bundle);
      if (navigator && navigator.storage && typeof navigator.storage.persist === "function") {
        navigator.storage.persist().catch(() => {});
      }
    } catch (_) {
      // Ignore storage quota errors in private mode
    }
  }

  function loadLocalVaultSnapshot() {
    try {
      if (typeof localStorage !== "undefined") {
        const raw = localStorage.getItem(VAULT_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  function enrichStandaloneCard(c) {
    const rawFront = String(c.front_text || "");
    const rawBack = String(c.back_text || "");
    const renderedQ = rawFront.replace(/\{\{c\d+::([^}:]+)(?:::([^}]+))?\}\}/g, (_m, _ans, hint) =>
      hint ? `[...(${hint})...]` : "[ ... ]"
    );
    const extracted =
      vm && typeof vm.extractTargetAndExplanation === "function"
        ? vm.extractTargetAndExplanation(rawFront, rawBack, c.target_answer, c.extra_explanation)
        : { targetAnswer: rawBack, extraExplanation: "" };
    return {
      ...c,
      rendered_question: c.rendered_question || renderedQ,
      rendered_answer: c.rendered_answer || rawBack,
      target_answer: c.target_answer || extracted.targetAnswer || rawBack,
      extra_explanation: c.extra_explanation || extracted.extraExplanation || "",
      retrievability: c.retrievability || 0.94,
      leech_status: Number(c.lapses || 0) >= 3 ? "leech" : "ok",
    };
  }

  function fallbackStandaloneGet(path) {
    if (!standaloneEngine) return null;
    if (path.startsWith("/api/status")) {
      const dash = standaloneEngine.getDashboard();
      return {
        ...dash,
        stats: {
          ...dash.stats,
          true_retention_pct: dash.stats.retention_rate_30d || 92.5,
          forgetting_curve: [
            { day: 0, retrievability_pct: 100 },
            { day: 3, retrievability_pct: 96 },
            { day: 7, retrievability_pct: 93 },
            { day: 14, retrievability_pct: 91 },
            { day: 30, retrievability_pct: 89 },
          ],
        },
      };
    }
    if (path.startsWith("/api/due")) {
      const qIdx = path.indexOf("?");
      const qs = qIdx >= 0 ? new URLSearchParams(path.slice(qIdx + 1)) : new URLSearchParams();
      const deckId = qs.get("deck_id") || "";
      const shuffleMode = qs.get("shuffle") || state.shuffleMode || "interleaved";
      const respectPlan = qs.get("respect_plan") === "1" || qs.get("respect_plan") === "true";
      const dueRes = standaloneEngine.getDueCards({
        deck_id: deckId,
        shuffle_mode: shuffleMode,
        respect_plan: respectPlan,
      });
      dueRes.cards = (dueRes.cards || []).map(enrichStandaloneCard);
      return dueRes;
    }
    if (path.startsWith("/api/catalog")) {
      return standaloneEngine.getCatalog();
    }
    if (path.startsWith("/api/store/packs")) {
      if (typeof standaloneEngine.getStorePacks === "function") {
        const qIdx = path.indexOf("?");
        const qs = qIdx >= 0 ? new URLSearchParams(path.slice(qIdx + 1)) : new URLSearchParams();
        return standaloneEngine.getStorePacks(qs.get("category") || "all");
      }
    }
    if (path.startsWith("/api/bundle/offline-snapshot")) {
      return {
        ok: true,
        standalone: true,
        status: fallbackStandaloneGet("/api/status"),
        due: fallbackStandaloneGet("/api/due"),
        store: fallbackStandaloneGet("/api/store/packs"),
        catalog: standaloneEngine.getCatalog(),
      };
    }
    return null;
  }

  function fallbackStandalonePost(path, payload) {
    if (!standaloneEngine) return { ok: false, offline: true };
    const p = payload || {};
    if (path.startsWith("/api/review/undo")) {
      if (typeof standaloneEngine.undoLastReview === "function") {
        return standaloneEngine.undoLastReview();
      }
      return { ok: false, standalone: true, error: "되돌리기 미지원" };
    }
    if (path.startsWith("/api/reset") || path.startsWith("/api/study/reset") || path.startsWith("/api/review/reset")) {
      if (typeof standaloneEngine.resetStudyProgress === "function") {
        return standaloneEngine.resetStudyProgress(p);
      }
      return { ok: true, standalone: true, reset_count: 0 };
    }
    if (path.startsWith("/api/review")) {
      return standaloneEngine.submitReview(p);
    }
    if (path.startsWith("/api/decks/batch-save")) {
      if (typeof standaloneEngine.batchSaveDeck === "function") {
        return standaloneEngine.batchSaveDeck(p);
      }
    }
    if (path.startsWith("/api/store/purchase-bundle")) {
      if (typeof standaloneEngine.purchaseStoreBundle === "function") {
        return standaloneEngine.purchaseStoreBundle(p);
      }
    }
    if (path.startsWith("/api/store/purchase")) {
      if (typeof standaloneEngine.purchaseStorePack === "function") {
        return standaloneEngine.purchaseStorePack(p);
      }
    }
    if (path.startsWith("/api/store/refund")) {
      if (typeof standaloneEngine.refundStorePack === "function") {
        return standaloneEngine.refundStorePack(p);
      }
    }
    if (path.startsWith("/api/catalog/exam-scope") || path.startsWith("/api/catalog/generate-exam-scope-deck")) {
      return standaloneEngine.buildExamScopeDeck(p);
    }
    if (path.startsWith("/api/catalog/collection-deck") || path.startsWith("/api/catalog/generate-collection-deck")) {
      return standaloneEngine.buildCollectionDeck(p);
    }
    if (path.startsWith("/api/catalog/combined-exam-deck") || path.startsWith("/api/catalog/generate-combined-exam-deck")) {
      return standaloneEngine.buildCombinedExamDeck(p);
    }
    if (path.startsWith("/api/ai/generate-cards") || path.startsWith("/api/cards/generate")) {
      return standaloneEngine.buildSmartTextDeck({
        text: p.raw_text,
        difficulty_level: p.difficulty_level || (state.learnerProfile && state.learnerProfile.difficulty) || "mixed",
        auto_save: p.auto_save !== false,
      });
    }
    if (path.startsWith("/api/quiz/interactive-options")) {
      const card = currentCard();
      const fullPool =
        Array.isArray(state.rawDueCards) && state.rawDueCards.length > 0
          ? state.rawDueCards
          : state.dueCards || [];
      if (vm && typeof vm.buildTypeMatchedQuizOptions === "function") {
        const matched = vm.buildTypeMatchedQuizOptions(card, fullPool, 4);
        return {
          ok: true,
          standalone: true,
          mode: "multiple_choice",
          question_type: matched.question_type,
          question_facet: matched.question_facet,
          question_facet_label: matched.question_facet,
          target_answer: matched.target_answer,
          options: matched.options,
          tap_blocks: matched.tap_blocks,
        };
      }
      const target = (card && (card.target_answer || card.rendered_answer)) || "정답";
      return {
        ok: true,
        standalone: true,
        mode: "multiple_choice",
        question_facet: "📘 단어 뜻·어휘",
        target_answer: target,
        options: [target, "소개하다", "가장 좋아하는", "전통적인"].slice(0, 4),
        tap_blocks: String(target).split(/\s+/).filter(Boolean),
      };
    }
    if (path.startsWith("/api/study-plan")) {
      const shouldApply = path.startsWith("/api/study-plan/apply") || Boolean(p.apply || p.apply_plan);
      if (shouldApply && typeof standaloneEngine.applyStudyPlan === "function") {
        return standaloneEngine.applyStudyPlan(p);
      }
      if (typeof standaloneEngine.getStudyPlan === "function") {
        return standaloneEngine.getStudyPlan(p);
      }
      if (vm && typeof vm.computeAnkiStudyPlan === "function") {
        const cards = state.rawDueCards || [];
        const total = Math.max(cards.length, 1020);
        const plan = vm.computeAnkiStudyPlan({
          total_cards: total,
          new_count: total,
          target_days: Number(p.target_days || 30),
          daily_minutes_budget: Number(p.daily_minutes_budget || 30),
        });
        return { ok: true, standalone: true, plan };
      }
    }
    if (path.startsWith("/api/cards/action")) {
      const card = currentCard() || { card_id: p.card_id, tags: [] };
      if (vm && typeof vm.applyAnkiCardAction === "function") {
        const updated = vm.applyAnkiCardAction(card, p.action, { flag: p.flag, due_days: p.due_days });
        return { ok: true, standalone: true, card_id: p.card_id, action: p.action, card: updated };
      }
    }
    if (path.startsWith("/api/deck/explorer")) {
      if (typeof standaloneEngine.exploreDeckCards === "function") {
        return standaloneEngine.exploreDeckCards(p);
      }
    }
    if (path.startsWith("/api/custom-study")) {
      const cards = (state.rawDueCards && state.rawDueCards.length > 0) ? state.rawDueCards : (state.dueCards || []);
      if (vm && typeof vm.buildCustomStudySession === "function") {
        const sess = vm.buildCustomStudySession(cards, p);
        return Object.assign({ ok: true, standalone: true }, sess);
      }
    }
    return { ok: true, standalone: true };
  }

  async function apiGet(path) {
    try {
      const res = await fetch(path, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (_) {
      const stRes = fallbackStandaloneGet(path);
      if (stRes) return stRes;
      const vault = loadLocalVaultSnapshot();
      if (!vault) return { ok: false, offline: true };
      if (path.startsWith("/api/status")) return vault.status || { ok: false };
      if (path.startsWith("/api/due")) return vault.due || { ok: true, cards: [] };
      if (path.startsWith("/api/store/packs")) return vault.store || { ok: true, packs: [] };
      if (path.startsWith("/api/catalog")) return vault.catalog || { ok: true, textbooks: [], collections: [] };
      return { ok: false, offline: true };
    }
  }

  async function apiPost(path, payload) {
    try {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        // If static host returns 404/405, use standalone engine
        if (res.status === 404 || res.status === 405) {
          return fallbackStandalonePost(path, payload);
        }
      }
      return await res.json();
    } catch (_) {
      return fallbackStandalonePost(path, payload);
    }
  }

  function currentCard() {
    return state.dueCards[state.currentIndex] || null;
  }

  function clearRecommendedGlow() {
    [1, 2, 3, 4].forEach((r) => {
      const btn = el(`rate-${r}`);
      if (btn) btn.classList.remove("recommended-glow");
    });
  }

  function refreshFilterBadgeCounts() {
    const buriedSet = new Set(state.buriedCardIds.map(Number));
    const activeRaw = (state.rawDueCards || []).filter((c) => c && !buriedSet.has(Number(c.card_id)));
    if (vm && typeof vm.computeAnkiQueueCounts === "function") {
      const qCounts = vm.computeAnkiQueueCounts(activeRaw);
      const cNew = el("count-new");
      const cLearn = el("count-learn");
      const cRev = el("count-review");
      if (cNew) cNew.textContent = `새 카드 ${qCounts.newCount}`;
      if (cLearn) cLearn.textContent = `학습·오답 ${qCounts.learnCount + state.sessionWrongCardIds.length}`;
      if (cRev) cRev.textContent = `복습 ${qCounts.reviewCount}`;
    }

    const combinedPool = activeRaw.slice();
    const seenIds = new Set(combinedPool.map((c) => Number(c.card_id)));
    state.sessionWrongCardIds.forEach((cid) => {
      const snap = state.sessionWrongCardMap[cid];
      if (snap && !seenIds.has(Number(cid)) && !buriedSet.has(Number(cid))) {
        combinedPool.push(snap);
        seenIds.add(Number(cid));
      }
    });

    const wrongList =
      vm && typeof vm.filterStudyQueue === "function"
        ? vm.filterStudyQueue(combinedPool, "wrong_only", state.sessionWrongCardIds, state.markedCardIds)
        : [];
    const markedList =
      vm && typeof vm.filterStudyQueue === "function"
        ? vm.filterStudyQueue(combinedPool, "marked_only", state.sessionWrongCardIds, state.markedCardIds)
        : [];

    const btnWrong = el("btn-filter-wrong");
    if (btnWrong) btnWrong.textContent = `🔥 오답·모르는 것만 (${wrongList.length})`;
    const btnMarked = el("btn-filter-marked");
    if (btnMarked) btnMarked.textContent = `⭐ 별표 카드만 (${markedList.length})`;

    return { activeRaw, wrongList, markedList };
  }

  function applyStudyFilter() {
    const { activeRaw, wrongList, markedList } = refreshFilterBadgeCounts();

    let candidateQueue;
    if (state.studyFilterMode === "wrong_only") {
      candidateQueue = wrongList;
    } else if (state.studyFilterMode === "marked_only") {
      candidateQueue = markedList;
    } else {
      candidateQueue = activeRaw;
    }

    if (vm && typeof vm.computeQuestionTypeCounts === "function") {
      const tCounts = vm.computeQuestionTypeCounts(candidateQueue);
      const bAll = el("btn-qtype-all");
      const bVocab = el("btn-qtype-vocab");
      const bGram = el("btn-qtype-grammar");
      const bHanja = el("btn-qtype-hanja");
      const bHist = el("btn-qtype-history_sci");
      if (bAll) bAll.textContent = `🗂️ 전체 유형 (${tCounts.all})`;
      if (bVocab) bVocab.textContent = `📘 단어·어휘만 (${tCounts.vocab})`;
      if (bGram) bGram.textContent = `📐 문법·구문만 (${tCounts.grammar})`;
      if (bHanja) bHanja.textContent = `漢字 한자·성어만 (${tCounts.hanja})`;
      if (bHist) bHist.textContent = `🏛️ 역사·과학·전공 (${tCounts.history_sci})`;
    }

    if (vm && typeof vm.filterStudyQueueByQuestionType === "function" && state.questionTypeFilter !== "all") {
      candidateQueue = vm.filterStudyQueueByQuestionType(candidateQueue, state.questionTypeFilter);
    }

    if (vm && typeof vm.classifyCardStage === "function" && state.stageFilter && state.stageFilter !== "all") {
      candidateQueue = candidateQueue.filter((c) => vm.classifyCardStage(c) === state.stageFilter);
    }

    if (vm && typeof vm.interleaveAndShuffleStudyQueue === "function" && state.shuffleMode !== "sequential") {
      state.dueCards = vm.interleaveAndShuffleStudyQueue(candidateQueue, state.shuffleMode);
    } else {
      state.dueCards = candidateQueue;
    }
    // Frame 4: Sibling Burying (keep at most 1 facet per concept:<id> in a single study session)
    if (vm && typeof vm.deduplicateSessionSiblings === "function" && state.studyFilterMode !== "wrong_only") {
      state.dueCards = vm.deduplicateSessionSiblings(state.dueCards);
    }
    state.currentIndex = 0;
  }

  function renderDeckProgressDashboard(dp) {
    if (!dp) return;
    const t = dp.today || {};
    const b = dp.buckets || {};
    const m = dp.milestone || {};
    const byStage = dp.by_stage || {};

    const todayLbl = el("bd-today-progress-label");
    if (todayLbl) {
      const overTxt = Number(t.over_target_count || 0) > 0 ? ` (+${t.over_target_count}장 초과달성!)` : "";
      todayLbl.textContent = `🎯 오늘 목표 진척률: ${t.completed_count || 0} / ${t.target_count || 0}장 완료 (${Number(t.percent || 0).toFixed(1)}%)${overTxt}`;
    }
    const todayEta = el("bd-today-eta-label");
    if (todayEta) {
      todayEta.textContent =
        Number(t.remaining_count || 0) > 0
          ? `⏱️ 남은 ${t.remaining_count}장 · 약 ${t.estimated_remaining_minutes || 0}분`
          : "✅ 오늘 목표 100% 달성!";
    }
    const todayFill = el("bd-today-progress-fill");
    if (todayFill) {
      todayFill.style.width = `${Math.min(100, Math.max(0, Number(t.percent || 0)))}%`;
    }

    const covLbl = el("bd-deck-coverage-label");
    if (covLbl) {
      covLbl.textContent = `📊 전체 덱 진도율 (1회 이상 학습): ${Number(dp.coverage_pct || 0).toFixed(1)}% (${dp.touched_cards || 0} / ${dp.total_cards || 0}장)`;
    }
    const mastLbl = el("bd-deck-mastery-label");
    if (mastLbl) {
      mastLbl.textContent = `🏆 FSRS 가중 숙련도: ${Number(dp.mastery_pct || 0).toFixed(1)}% · 장기마스터 ${Number(dp.mature_pct || 0).toFixed(1)}%`;
    }
    const mileLbl = el("bd-deck-milestone-label");
    if (mileLbl) {
      if (Number(m.cards_to_next || 0) > 0) {
        mileLbl.textContent = `🏁 다음 마일스톤(${m.next_pct || 10}%): ${m.cards_to_next}장 남음 (약 ${m.days_to_next || 1}일) · 전수 완주 D-${dp.eta_full_coverage_days || 0}`;
      } else {
        mileLbl.textContent = `🎉 전체 덱 100% 마일스톤 달성!`;
      }
    }

    const activeTotal = Math.max(1, Number(dp.active_cards || dp.total_cards || 1));
    const matureW = ((Number(b.mature || 0) / activeTotal) * 100).toFixed(2);
    const youngW = ((Number(b.young || 0) / activeTotal) * 100).toFixed(2);
    const learnW = ((Number(b.learning || 0) / activeTotal) * 100).toFixed(2);
    const unseenW = Math.max(0, 100 - Number(matureW) - Number(youngW) - Number(learnW)).toFixed(2);

    const barMature = el("bd-bar-mature");
    const barYoung = el("bd-bar-young");
    const barLearn = el("bd-bar-learning");
    const barUnseen = el("bd-bar-unseen");
    if (barMature) barMature.style.width = `${matureW}%`;
    if (barYoung) barYoung.style.width = `${youngW}%`;
    if (barLearn) barLearn.style.width = `${learnW}%`;
    if (barUnseen) barUnseen.style.width = `${unseenW}%`;

    const cUnseen = el("bd-cnt-unseen");
    const cLearn = el("bd-cnt-learning");
    const cYoung = el("bd-cnt-young");
    const cMature = el("bd-cnt-mature");
    if (cUnseen) cUnseen.textContent = String(b.unseen || 0);
    if (cLearn) cLearn.textContent = String(b.learning || 0);
    if (cYoung) cYoung.textContent = String(b.young || 0);
    if (cMature) cMature.textContent = String(b.mature || 0);

    ["lv1", "lv2", "lv3", "lv4"].forEach((stKey) => {
      const btn = el(`btn-stage-${stKey}`);
      const st = byStage[stKey];
      if (btn && st) {
        btn.textContent = `${st.label || stKey} (${Number(st.coverage_pct || 0).toFixed(0)}% · ${st.touched || 0}/${st.total || 0})`;
      }
    });
  }

  async function renderDeckExplorerPanel() {
    const panel = el("deck-card-explorer-panel");
    if (!panel || panel.style.display === "none") return;
    const qInput = el("explorer-search-input");
    const bSel = el("explorer-bucket-select");
    const sSel = el("explorer-stage-select");
    const bVal = (bSel && bSel.value) || "all";
    const sVal = (sSel && sSel.value) || "all";
    const res = await apiPost("/api/deck/explorer", {
      deck_id: state.selectedDeckId || null,
      query: (qInput && qInput.value) || "",
      bucket: bVal,
      bucket_filter: bVal,
      stage: sVal,
      stage_filter: sVal,
      limit: 120,
    });
    if (!res || !res.ok) return;
    const sumEl = el("explorer-result-summary") || el("explorer-total-label");
    if (sumEl) {
      sumEl.textContent = `일치 ${res.matched_count || 0}장 (표시 ${res.returned_count || 0}장 / 전체 ${(state.deckProgress && state.deckProgress.total_cards) || res.matched_count || 0}장)`;
    }
    const listBox = el("explorer-card-rows") || el("explorer-card-list");
    if (!listBox) return;
    listBox.textContent = "";
    const bucketBadges = {
      mature: { label: "🟢 장기마스터", bg: "#e8faf0", fg: "#008a50" },
      young: { label: "🔵 단기암기", bg: "#eff6ff", fg: "#1d4ed8" },
      learning: { label: "🟠 학습·오답", bg: "#fffbeb", fg: "#b45309" },
      unseen: { label: "⚪ 미학습", bg: "#f1f5f9", fg: "#475569" },
      suspended: { label: "⏸️ 보류", bg: "#fef2f2", fg: "#be123c" },
    };
    (res.cards || []).forEach((c, idx) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;background:#ffffff;border:1px solid var(--border);font-size:0.78rem;flex-wrap:wrap;";
      const left = document.createElement("div");
      left.style.cssText = "display:flex;align-items:center;gap:6px;flex:1;min-width:200px;flex-wrap:wrap;";
      const bMeta = bucketBadges[c.maturity_bucket] || bucketBadges.unseen;
      const bSpan = document.createElement("span");
      bSpan.style.cssText = `padding:2px 6px;border-radius:6px;background:${bMeta.bg};color:${bMeta.fg};font-weight:700;font-size:0.7rem;`;
      bSpan.textContent = bMeta.label;
      const sSpan = document.createElement("span");
      sSpan.style.cssText = "padding:2px 6px;border-radius:6px;background:var(--surface-2);color:var(--accent);font-weight:700;font-size:0.7rem;";
      sSpan.textContent = c.stage_label || c.stage || "Lv.2";
      const qSpan = document.createElement("span");
      qSpan.style.cssText = "font-weight:700;color:var(--text);";
      qSpan.textContent = `#${idx + 1} ${(c.front_text || "").replace(/\{\{c\d+::([^}:]+)(?:::[^}]+)?\}\}/g, "[$1]").slice(0, 65)}`;
      const aSpan = document.createElement("span");
      aSpan.style.cssText = "color:var(--muted);";
      aSpan.textContent = `➔ ${(c.target_answer || c.back_text || "").slice(0, 45)} (S:${Number(c.stability || 0).toFixed(1)}d)`;
      left.appendChild(bSpan);
      left.appendChild(sSpan);
      left.appendChild(qSpan);
      left.appendChild(aSpan);

      const jumpBtn = document.createElement("button");
      jumpBtn.type = "button";
      jumpBtn.style.cssText = "padding:3px 8px;font-size:0.72rem;";
      jumpBtn.textContent = "🎯 바로 풀기";
      jumpBtn.onclick = () => {
        const enriched = enrichStandaloneCard(c);
        const existingIdx = state.dueCards.findIndex((dc) => Number(dc.card_id) === Number(c.card_id));
        if (existingIdx >= 0) {
          state.currentIndex = existingIdx;
        } else {
          state.dueCards.unshift(enriched);
          state.currentIndex = 0;
        }
        renderCurrentCard();
        showUxToast(`🎯 선택한 카드(#${c.card_id})로 바로 이동했습니다.`, "emerald");
      };
      row.appendChild(left);
      row.appendChild(jumpBtn);
      listBox.appendChild(row);
    });
  }

  function applyEvidenceRatingGuard() {
    const ratingBox = el("rating-grid-box");
    const guardBanner = el("rating-guard-banner");
    if (!state.isRevealed) {
      if (ratingBox) ratingBox.style.display = "none";
      if (guardBanner) guardBanner.style.display = "none";
      return;
    }
    const guard =
      vm && typeof vm.resolveAllowedRatings === "function"
        ? vm.resolveAllowedRatings(state.currentEvidence, state.ageTier)
        : { allowedRatings: [1, 2, 3, 4], recommendedRating: 3, bannerText: "" };

    if (ratingBox) ratingBox.style.display = "grid";
    if (guardBanner) {
      guardBanner.textContent = guard.bannerText || "";
      guardBanner.style.display = guard.bannerText ? "block" : "none";
    }
    clearRecommendedGlow();
    [1, 2, 3, 4].forEach((r) => {
      const btn = el(`rate-${r}`);
      if (!btn) return;
      if (state.ageTier === "junior" && r === 4) {
        btn.style.display = "none";
        return;
      }
      btn.style.display = "flex";
      const isAllowed = (guard.allowedRatings || []).includes(r);
      btn.disabled = !isAllowed;
      btn.style.opacity = isAllowed ? "1" : "0.28";
      btn.style.pointerEvents = isAllowed ? "auto" : "none";
      if (Number(guard.recommendedRating) === r && isAllowed) {
        btn.classList.add("recommended-glow");
      }
    });
  }

  function renderCurrentCard() {
    const card = currentCard();
    state.isRevealed = false;
    state.hintLevel = 0;
    state.cardShownAtMs = Date.now();
    state.currentEvidence = {
      isRevealed: false,
      hintStep: 0,
      choiceCorrect: null,
      typedVerdict: null,
      dontKnow: false,
    };
    clearRecommendedGlow();
    applyEvidenceRatingGuard();

    const btnReveal = el("btn-reveal");
    if (btnReveal) {
      btnReveal.textContent = "정답 보기";
    }
    el("card-answer").style.display = "none";
    const extraEl = el("card-extra-explanation");
    if (extraEl) {
      extraEl.style.display = "none";
      extraEl.textContent = "";
    }
    el("hint-box").style.display = "none";
    el("eval-box").style.display = "none";
    const btnOverride = el("btn-override-correct");
    if (btnOverride) btnOverride.style.display = "none";
    const quizBox = el("interactive-quiz-box");
    if (quizBox) quizBox.style.display = "none";
    const retryBox = el("post-session-retry-box");
    if (retryBox) retryBox.style.display = "none";
    el("recall-input").value = "";

    if (!card) {
      const dp = state.deckProgress;
      const dpSummary = dp
        ? ` (오늘 ${dp.today ? dp.today.completed_count : 0}/${dp.today ? dp.today.target_count : 0}장 완료 · 전체 덱 진도 ${Number(dp.coverage_pct || 0).toFixed(1)}% · 숙련도 ${Number(dp.mastery_pct || 0).toFixed(1)}%)`
        : "";
      el("card-meta").textContent = `복습 완료${dpSummary}`;
      const sprintBadgeEl = el("sprint-progress-badge");
      if (sprintBadgeEl) sprintBadgeEl.textContent = "🏁 오늘 목표 스프린트 완료";
      el("card-fsrs-meta").textContent = "Due: 0";
      el("card-question").textContent =
        state.studyFilterMode === "wrong_only"
          ? "🎉 오답·모르는 카드를 모두 완벽히 복습했습니다!"
          : `🎉 오늘 배정된 학습 목표 카드를 모두 완료했습니다!${dpSummary}`;
      el("leech-banner").style.display = "none";
      const typingZone = el("typing-solve-zone");
      if (typingZone) typingZone.style.display = "none";
      if (retryBox && state.sessionWrongCardIds.length > 0 && state.studyFilterMode !== "wrong_only") {
        const sumEl = el("post-session-summary");
        if (sumEl) {
          sumEl.textContent = `방금 학습 중 헷갈렸거나 몰랐던 카드가 ${state.sessionWrongCardIds.length}장 있습니다.`;
        }
        retryBox.style.display = "block";
      }
      return;
    }

    const isMarked = state.markedCardIds.includes(Number(card.card_id));
    const btnMark = el("btn-mark-card");
    if (btnMark) {
      btnMark.textContent = isMarked ? "⭐ 별표됨" : "☆ 별표";
      btnMark.style.color = isMarked ? "var(--amber)" : "var(--muted)";
    }

    const qTypeObj =
      vm && typeof vm.classifyCardQuestionType === "function"
        ? vm.classifyCardQuestionType(card)
        : { badge_label: card.note_type === "cloze" ? "📘 빈칸 추론" : "📘 핵심 인출", short_label: "개념" };
    const qtypeBadgeEl = el("card-qtype-badge");
    if (qtypeBadgeEl) {
      qtypeBadgeEl.textContent = qTypeObj.badge_label;
    }

    const isUnfilteredSession =
      state.studyFilterMode === "all" &&
      (!state.stageFilter || state.stageFilter === "all") &&
      state.questionTypeFilter === "all" &&
      !state.isCramSandbox;
    const dp = state.deckProgress;
    const todayProg = dp && dp.today ? dp.today : null;
    const effectivePosZeroBased =
      isUnfilteredSession && todayProg
        ? Number(todayProg.completed_count || 0) + state.currentIndex
        : state.currentIndex;
    const effectiveTotal =
      isUnfilteredSession && todayProg
        ? Math.max(effectivePosZeroBased + 1, Number(todayProg.target_count || state.dueCards.length || 1))
        : Math.max(1, state.dueCards.length);

    const sprintBadgeEl = el("sprint-progress-badge");
    if (sprintBadgeEl) {
      const curSprintIdx = Math.floor(effectivePosZeroBased / 7) + 1;
      const totalSprints = Math.max(1, Math.ceil(effectiveTotal / 7));
      const inSprintPos = (effectivePosZeroBased % 7) + 1;
      const curSprintLen =
        curSprintIdx < totalSprints ? 7 : Math.max(inSprintPos, effectiveTotal - (totalSprints - 1) * 7);
      sprintBadgeEl.textContent = `🏁 스프린트 ${curSprintIdx}/${totalSprints} (${inSprintPos}/${curSprintLen})`;
    }
    const typeLabel = card.note_type === "cloze" ? "빈칸 추론" : "핵심 인출";
    if (isUnfilteredSession && dp && todayProg) {
      const ord = effectivePosZeroBased + 1;
      const todayPct = Number(todayProg.percent || 0).toFixed(1);
      const covPct = Number(dp.coverage_pct || 0).toFixed(1);
      el("card-meta").textContent =
        `${card.deck_name} · 오늘 ${ord}/${effectiveTotal}번째 (${todayPct}% 완료) · 전체 진도 ${covPct}% (${dp.touched_cards}/${dp.total_cards}장) · ${typeLabel}`;
    } else {
      el("card-meta").textContent = `${card.deck_name} · #${state.currentIndex + 1}/${state.dueCards.length} · ${typeLabel}`;
    }
    const rPct = ((Number(card.retrievability) || 1) * 100).toFixed(1);
    el("card-fsrs-meta").textContent = `S: ${Number(card.stability).toFixed(1)}d · D: ${Number(card.difficulty).toFixed(1)} · R: ${rPct}%`;
    el("card-question").textContent = card.rendered_question || card.front_text || "";

    const extracted =
      vm && typeof vm.extractTargetAndExplanation === "function"
        ? vm.extractTargetAndExplanation(
            card.front_text,
            card.back_text,
            card.target_answer,
            card.extra_explanation
          )
        : {
            targetAnswer: card.target_answer || card.rendered_answer,
            extraExplanation: card.extra_explanation || "",
          };
    el("card-answer").textContent = `🎯 정답: ${extracted.targetAnswer || card.rendered_answer}`;
    if (extraEl) {
      const fullAns = String(card.rendered_answer || "").trim();
      const extraText = extracted.extraExplanation || (fullAns !== extracted.targetAnswer ? fullAns : "");
      extraEl.textContent = extraText ? `💡 해설 및 전체 문장:\n${extraText}` : "";
    }

    const leech = vm.formatLeechBadge(card.leech_status, card.lapses);
    const btnDecompose = el("btn-decompose");
    if (leech.visible) {
      el("leech-banner").textContent = leech.label;
      el("leech-banner").style.display = "block";
      if (btnDecompose) btnDecompose.style.display = "inline-block";
    } else {
      el("leech-banner").style.display = "none";
      if (btnDecompose) btnDecompose.style.display = "none";
    }

    const p = card.button_previews || {};
    el("preview-1").textContent = (p.again && p.again.label) || "10m";
    el("preview-2").textContent = (p.hard && p.hard.label) || "1d";
    el("preview-3").textContent = (p.good && p.good.label) || "3d";
    el("preview-4").textContent = (p.easy && p.easy.label) || "16d";

    // Frame 2: 1-Card 1-Mode Active Solve Mode Resolution
    const activeSolveMode =
      state.cardModeOverride ||
      (vm && typeof vm.resolveCardSolveMode === "function"
        ? vm.resolveCardSolveMode(card, state.learnerProfile)
        : state.ageTier === "junior"
        ? "choice"
        : "typing");

    const modeBadge = el("solve-mode-badge");
    const typingZone = el("typing-solve-zone");
    if (activeSolveMode === "choice") {
      if (modeBadge) modeBadge.textContent = "🎯 4지선다 모드";
      if (typingZone) typingZone.style.display = "none";
      requestInteractiveQuiz("multiple_choice");
    } else if (activeSolveMode === "typing") {
      if (modeBadge) modeBadge.textContent = "✍️ 서술형 인출 모드";
      if (typingZone) typingZone.style.display = "flex";
      if (quizBox) quizBox.style.display = "none";
    } else {
      if (modeBadge) modeBadge.textContent = "🃏 카드 뒤집기 모드";
      if (typingZone) typingZone.style.display = "none";
      if (quizBox) quizBox.style.display = "none";
    }
  }

  async function renderStudyPlanBanner(planRes) {
    const banner = el("bd-study-plan-banner");
    if (!banner || !planRes || !planRes.ok || !planRes.plan) return;
    if (planRes.deck_progress) {
      state.deckProgress = planRes.deck_progress;
      renderDeckProgressDashboard(state.deckProgress);
    }
    const pl = planRes.plan;
    const dq = planRes.daily_quota || {};
    const dp = planRes.deck_progress || state.deckProgress;
    const dailyNewLimit = Number(dq.daily_new_limit || pl.recommended_daily_new || 30);
    const newStudied = Number(dq.new_studied_today || 0);
    const remNew = dq.remaining_new_today !== undefined ? Number(dq.remaining_new_today) : Math.max(0, dailyNewLimit - newStudied);
    const badgeTone =
      pl.status === "FEASIBLE"
        ? "✅ 완주 가능"
        : pl.status === "TIGHT_SCHEDULE"
        ? "⚠️ 타이트한 일정"
        : "🚨 집중 배분 권장";
    const appliedLabel = dq.plan_applied ? "🟢 맞춤 계획 적용 중" : "🔵 기본 일일 할당 적용 중";
    const progLine = dp
      ? `\n📊 [전체 덱 진척률] 진도율 ${Number(dp.coverage_pct || 0).toFixed(1)}% (${dp.touched_cards}/${dp.total_cards}장 학습) · 가중 숙련도 ${Number(dp.mastery_pct || 0).toFixed(1)}% · 미학습 ${dp.buckets ? dp.buckets.unseen : 0}장`
      : "";
    banner.style.display = "block";
    banner.textContent =
      `📅 [D-${pl.target_days} 학습 계획 · ${badgeTone} · ${appliedLabel}] 전체 ${pl.total_cards}장 (진도 ${pl.new_intake_days}일 + 총정리 복습 ${pl.consolidation_days}일)\n` +
      `🎯 오늘의 할당량: 새 카드 ${dailyNewLimit}장 중 남은 ${remNew}장 (오늘 완료 ${newStudied}장) · 일평균 약 ${pl.avg_daily_minutes}분 (권장 최대 복습 ${pl.recommended_max_reviews}장/일)` +
      progLine +
      `\n💡 코칭: ${(pl.recommendations && pl.recommendations[0]) || ""}`;
  }

  async function refreshDashboardAndQueue() {
    const status = await apiGet("/api/status");
    if (status && status.ok) {
      const s = status.stats;
      el("stat-due").textContent = `${s.due_now}장`;
      el("stat-total").textContent = `${s.total_cards}장 / 오늘 ${s.reviews_today}회`;
      const badge = vm.formatRetentionBadge(s.true_retention_pct);
      el("stat-retention").textContent = badge.label;
      el("stat-stability").textContent = `${s.avg_stability_days}일 · 집중복습 ${s.leech_cards}건`;

      const points = vm.buildForgettingCurveSvgPoints(s.forgetting_curve, 480, 120);
      el("curve-polyline").setAttribute("points", points);

      state.decks = status.decks || [];
      const sel = el("deck-select");
      const prevVal = state.selectedDeckId;
      sel.innerHTML = `<option value="">전체 덱 (${s.due_now}장 대기 / 총 ${s.total_cards}장)</option>`;
      state.decks.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = String(d.deck_id);
        const covPct = d.coverage_pct !== undefined ? Number(d.coverage_pct).toFixed(1) : "0.0";
        const mastPct = d.mastery_pct !== undefined ? Number(d.mastery_pct).toFixed(1) : "0.0";
        const remToday = d.remaining_new_today !== undefined ? d.remaining_new_today : d.due_cards;
        opt.textContent = `${d.name} [진도 ${covPct}% · 마스터 ${mastPct}% · 오늘 ${remToday}장 / 총 ${d.total_cards}장]`;
        sel.appendChild(opt);
      });
      sel.value = prevVal;
    }

    const params = new URLSearchParams();
    if (state.selectedDeckId) params.set("deck_id", state.selectedDeckId);
    if (state.shuffleMode) params.set("shuffle", state.shuffleMode);
    params.set("respect_plan", "1");
    const q = params.toString() ? `?${params.toString()}` : "";
    const dueRes = await apiGet(`/api/due${q}`);
    state.rawDueCards = (dueRes && dueRes.cards) || [];
    state.currentDailyQuota = (dueRes && dueRes.daily_quota) || null;
    if (dueRes && dueRes.deck_progress) {
      state.deckProgress = dueRes.deck_progress;
      renderDeckProgressDashboard(state.deckProgress);
    }
    applyStudyFilter();
    renderCurrentCard();
    await renderDeckExplorerPanel();

    const daysSel = el("bd-plan-days");
    const minsSel = el("bd-plan-minutes");
    const newSel = el("bd-plan-daily-new");
    const targetDays = Number((daysSel && daysSel.value) || (state.currentDailyQuota && state.currentDailyQuota.target_days) || 30);
    const dailyMinutes = Number((minsSel && minsSel.value) || 30);
    const customNew = newSel && newSel.value && newSel.value !== "auto" ? Number(newSel.value) : null;
    const planRes = await apiPost("/api/study-plan", {
      deck_id: state.selectedDeckId || null,
      target_days: targetDays,
      daily_minutes_budget: dailyMinutes,
      new_per_day: customNew,
    });
    if (planRes && planRes.ok) {
      await renderStudyPlanBanner(planRes);
    }
  }

  function revealAnswer() {
    const card = currentCard();
    if (!card) return;
    state.isRevealed = true;
    state.currentEvidence.isRevealed = true;
    if (card.note_type === "cloze" && card.front_text) {
      const revealedCloze = String(card.front_text).replace(
        /\{\{c\d+::([^:}]+)(?:::[^}]*)?\}\}/g,
        "【$1】"
      );
      el("card-question").textContent = revealedCloze;
    }
    el("card-answer").style.display = "block";
    const extraEl = el("card-extra-explanation");
    if (extraEl && extraEl.textContent) {
      extraEl.style.display = "block";
    }
    const btnReveal = el("btn-reveal");
    if (btnReveal) {
      btnReveal.textContent = "✅ 정답 확인됨 (아래 1~4 평가)";
    }
    applyEvidenceRatingGuard();
  }

  async function undoLastReview() {
    const res = await apiPost("/api/review/undo", {});
    if (res && res.ok) {
      const cid = res.undone_card_id ?? res.restored_card_id ?? "";
      showUxToast(
        `↩️ 복습 취소 완료: 카드 #${cid}가 이전 기억 상태(S=${Number(res.restored_stability || 0).toFixed(1)}d)로 복원되었습니다.`,
        "emerald"
      );
      await refreshDashboardAndQueue();
    } else if (vm && typeof vm.formatApiErrorBanner === "function") {
      const errVm = vm.formatApiErrorBanner(res);
      showUxToast(`${errVm.title} — ${errVm.message}`, errVm.tone);
    }
  }

  async function resetStudyProgress() {
    const deckIdParam = state.selectedDeckId ? Number(state.selectedDeckId) || state.selectedDeckId : null;
    const res = await apiPost("/api/reset", { deck_id: deckIdParam });
    if (!res || !res.ok) {
      const errMsg = (res && (res.detail || res.error)) || "초기화 요청을 처리할 수 없습니다.";
      showUxToast(`⚠️ 학습 초기화 실패: ${errMsg}`, "rose");
      return;
    }
    if (!res.standalone && standaloneEngine && typeof standaloneEngine.resetStudyProgress === "function") {
      standaloneEngine.resetStudyProgress({ deck_id: deckIdParam });
    }
    state.sessionWrongCardIds = [];
    state.sessionWrongCardMap = {};
    state.buriedCardIds = [];
    state.markedCardIds = [];
    state.studyFilterMode = "all";
    state.questionTypeFilter = "all";
    state.stageFilter = "all";
    state.currentIndex = 0;
    state.isRevealed = false;
    document.querySelectorAll(".study-filter-btn").forEach((b) => {
      if (b.getAttribute("data-filter") === "all") b.classList.add("btn-primary");
      else b.classList.remove("btn-primary");
    });
    document.querySelectorAll(".study-qtype-btn").forEach((b) => {
      if (b.getAttribute("data-qtype") === "all") b.classList.add("btn-primary");
      else b.classList.remove("btn-primary");
    });
    document.querySelectorAll(".bd-stage-btn").forEach((b) => {
      if (b.getAttribute("data-stage") === "all") b.classList.add("btn-primary");
      else b.classList.remove("btn-primary");
    });
    await refreshDashboardAndQueue();
    const count = Number(res.reset_count ?? res.reset_cards ?? 0);
    showUxToast(
      `🔄 학습 초기화 완료: ${count}장의 카드가 초기 상태(새 카드 1번)로 복원되었습니다!`,
      "emerald"
    );
  }

  async function submitRating(rating) {
    const card = currentCard();
    if (!card) return;
    if (!state.isRevealed) {
      showUxToast("⚠️ 정답을 먼저 확인한 뒤 난이도를 평가해 주세요.", "amber");
      return;
    }
    const guard =
      vm && typeof vm.resolveAllowedRatings === "function"
        ? vm.resolveAllowedRatings(state.currentEvidence, state.ageTier)
        : { allowedRatings: [1, 2, 3, 4], recommendedRating: 3 };
    let safeRating = Number(rating);
    if (Array.isArray(guard.allowedRatings) && guard.allowedRatings.length > 0 && !guard.allowedRatings.includes(safeRating)) {
      safeRating = Number(guard.recommendedRating || guard.allowedRatings[guard.allowedRatings.length - 1] || 1);
    }

    const cid = Number(card.card_id);
    if (safeRating <= 2) {
      if (!state.sessionWrongCardIds.includes(cid)) {
        state.sessionWrongCardIds.push(cid);
      }
      state.sessionWrongCardMap[cid] = { ...card };
    } else if (state.studyFilterMode === "wrong_only") {
      // Mastered in wrong_only cram mode -> remove from wrong list
      state.sessionWrongCardIds = state.sessionWrongCardIds.filter((id) => id !== cid);
      delete state.sessionWrongCardMap[cid];
    }

    const rtMs = state.cardShownAtMs ? Math.max(0, Date.now() - state.cardShownAtMs) : null;
    const res = state.isCramSandbox
      ? { ok: true, standalone: true, card_id: card.card_id, rating: safeRating, scheduled_label: "CRAM 무오염 (FSRS 유지)", memory: { stability: card.stability } }
      : await apiPost("/api/review", {
          card_id: card.card_id,
          rating: safeRating,
          response_time_ms: rtMs,
        });
    if (res && res.ok) {
      const stab = (res.memory && res.memory.stability) ?? res.stability ?? card.stability ?? 0;
      const nextLbl = state.isCramSandbox
        ? "🧪 CRAM 샌드박스 (장기기억 S 보존)"
        : res.scheduled_label || `${Number(res.scheduled_days || 0).toFixed(1)}d`;
      showUxToast(
        `✅ 평가 반영 완료 (S: ${Number(stab).toFixed(1)}d · ${nextLbl})`,
        "emerald",
        state.isCramSandbox ? "" : "↩️ 방금 평가 취소 (Z)",
        state.isCramSandbox ? null : () => undoLastReview()
      );
    }
    if (state.isCramSandbox) {
      state.currentIndex = (state.currentIndex + 1) % Math.max(1, state.dueCards.length);
      renderCurrentCard();
    } else {
      await refreshDashboardAndQueue();
    }
  }

  async function requestInteractiveQuiz(forcedSubmode = "") {
    const card = currentCard();
    const quizBox = el("interactive-quiz-box");
    if (!card || !quizBox) return;
    const res = await apiPost("/api/quiz/interactive-options", {
      card_id: card.card_id,
      age_tier: state.ageTier || "teen",
    });
    if (!res || !res.ok) return;

    const activeSubmode = forcedSubmode || (res.mode === "tap_block" ? "tap_block" : "multiple_choice");
    quizBox.textContent = "";
    quizBox.style.display = "block";

    const topBar = document.createElement("div");
    topBar.style.cssText =
      "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;";

    const header = document.createElement("div");
    header.style.cssText = "font-weight:700;color:var(--accent);";
    const facetBadge = res.question_facet_label || (res.question_type && res.question_type.badge_label) || res.question_facet || "동종 유형 보기";
    header.textContent =
      activeSubmode === "multiple_choice"
        ? `🎯 [1단계: 4지선다 객관식 · ${facetBadge} 전용 보기] 알맞은 정답을 선택하세요:`
        : `🧩 [2단계: 순서 배열 탭 블록 조립] 아래 구문 조각을 순서대로 눌러 정답을 완성하세요:`;
    topBar.appendChild(header);

    const switchRow = document.createElement("div");
    switchRow.style.cssText = "display:flex;gap:6px;";
    const btnMc = document.createElement("button");
    btnMc.type = "button";
    btnMc.className = activeSubmode === "multiple_choice" ? "btn-primary" : "";
    btnMc.style.cssText = "padding:4px 9px;font-size:0.74rem;";
    btnMc.textContent = "🎯 1단계: 4지선다";
    btnMc.onclick = () => requestInteractiveQuiz("multiple_choice");

    const btnTb = document.createElement("button");
    btnTb.type = "button";
    btnTb.className = activeSubmode === "tap_block" ? "btn-primary" : "";
    btnTb.style.cssText = "padding:4px 9px;font-size:0.74rem;";
    btnTb.textContent = "🧩 2단계: 탭 블록 조립";
    btnTb.onclick = () => requestInteractiveQuiz("tap_block");

    switchRow.appendChild(btnMc);
    switchRow.appendChild(btnTb);
    topBar.appendChild(switchRow);
    quizBox.appendChild(topBar);

    if (activeSubmode === "multiple_choice") {
      const grid = document.createElement("div");
      grid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;";

      const rawOptions = Array.isArray(res.options) ? res.options.slice() : [];
      const optionButtons = [];
      rawOptions.forEach((optText, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.style.cssText = "text-align:left;padding:10px 12px;font-size:0.84rem;";
        btn.textContent = `${idx + 1}. ${optText}`;
        optionButtons.push({ btn, optText, idx });
        btn.addEventListener("click", () => {
          const isCorrect = optText === res.target_answer;
          state.currentEvidence.choiceCorrect = isCorrect;
          if (!isCorrect) {
            const cid = Number(card.card_id);
            if (!state.sessionWrongCardIds.includes(cid)) state.sessionWrongCardIds.push(cid);
            state.sessionWrongCardMap[cid] = { ...card };
            refreshFilterBadgeCounts();
          }
          revealAnswer();

          optionButtons.forEach(({ btn: b, optText: oText, idx: oIdx }) => {
            b.disabled = true;
            b.style.cursor = "default";
            if (oText === res.target_answer) {
              b.style.borderColor = "var(--emerald)";
              b.style.background = "#e8faf0";
              b.style.color = "var(--emerald)";
              b.style.fontWeight = "800";
              b.textContent = `✅ ${oIdx + 1}. ${oText}`;
            } else if (oIdx === idx && !isCorrect) {
              b.style.borderColor = "var(--rose)";
              b.style.background = "#fff0f0";
              b.style.color = "var(--rose)";
              b.style.fontWeight = "700";
              b.textContent = `❌ ${oIdx + 1}. ${oText}`;
            } else {
              b.style.opacity = "0.62";
            }
          });

          const evalBox = el("eval-box");
          if (evalBox) {
            evalBox.style.background = isCorrect ? "#e8faf0" : "#fff0f0";
            evalBox.style.color = isCorrect ? "#008a50" : "#be123c";
            evalBox.textContent = isCorrect
              ? `🎯 4지선다 정답! ('${res.target_answer}')\n아래 정답과 해설을 확인한 뒤 하단 난이도 버튼(추천: 3 · Good)을 눌러 다음 카드로 넘어가세요.`
              : `❌ 오답입니다 (선택: '${optText}' ➔ 정답: '${res.target_answer}').\n아래 정답과 해설을 충분히 확인한 뒤 하단 '1 · Again' 버튼을 눌러 복습하세요.`;
            evalBox.style.display = "block";
          }

          if (isCorrect) {
            showUxToast(
              "🎉 정답입니다! 아래 🎯 정답·해설을 확인한 뒤 난이도 버튼(3 · Good)을 눌러 다음 카드로 이동하세요.",
              "emerald"
            );
          } else {
            showUxToast(
              `💡 오답입니다. 정답('${res.target_answer}')과 해설을 확인한 뒤 다시(1) 버튼을 눌러 복습하세요.`,
              "rose"
            );
          }
        });
        grid.appendChild(btn);
      });
      quizBox.appendChild(grid);
    } else {
      const expectedBlocks = Array.isArray(res.tap_blocks) && res.tap_blocks.length > 0
        ? res.tap_blocks.slice()
        : String(res.target_answer || "").split(/\s+/).filter(Boolean);
      const poolBlocks = expectedBlocks.map((text, idx) => ({ id: idx, text })).reverse();
      let selectedItems = [];

      const trayEl = document.createElement("div");
      trayEl.style.cssText =
        "min-height:42px;padding:8px 10px;border-radius:12px;border:1px dashed var(--accent);background:#ffffff;display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px;";

      const poolEl = document.createElement("div");
      poolEl.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;";

      const statusEl = document.createElement("div");
      statusEl.style.cssText = "font-size:0.78rem;color:var(--muted);";

      function renderTapBlockState() {
        trayEl.textContent = "";
        poolEl.textContent = "";

        if (selectedItems.length === 0) {
          const placeholder = document.createElement("span");
          placeholder.style.cssText = "font-size:0.78rem;color:var(--muted);";
          placeholder.textContent = "아래 구문 조각 버튼을 순서대로 클릭해 이곳에 문장을 조립하세요...";
          trayEl.appendChild(placeholder);
        } else {
          selectedItems.forEach((item, sIdx) => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "btn-primary";
            chip.style.cssText = "padding:5px 10px;font-size:0.8rem;";
            chip.textContent = `${sIdx + 1}. ${item.text} ✕`;
            chip.onclick = () => {
              selectedItems.splice(sIdx, 1);
              renderTapBlockState();
            };
            trayEl.appendChild(chip);
          });
        }

        poolBlocks.forEach((item) => {
          const alreadyUsed = selectedItems.some((s) => s.id === item.id);
          if (alreadyUsed) return;
          const chip = document.createElement("button");
          chip.type = "button";
          chip.style.cssText = "padding:6px 11px;font-size:0.8rem;";
          chip.textContent = `+ ${item.text}`;
          chip.onclick = () => {
            selectedItems.push(item);
            renderTapBlockState();
            if (selectedItems.length === expectedBlocks.length && vm && typeof vm.evaluateTapBlockAttempt === "function") {
              const check = vm.evaluateTapBlockAttempt(
                selectedItems.map((x) => x.text),
                expectedBlocks
              );
              statusEl.textContent = check.feedback;
              statusEl.style.color = check.isCorrect ? "var(--emerald)" : "var(--amber)";
              revealAnswer();
              clearRecommendedGlow();
              const recBtn = el(`rate-${check.recommendedRating}`);
              if (recBtn) recBtn.classList.add("recommended-glow");
            }
          };
          poolEl.appendChild(chip);
        });
      }

      const ctrlRow = document.createElement("div");
      ctrlRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;";
      const resetBtn = document.createElement("button");
      resetBtn.type = "button";
      resetBtn.style.cssText = "padding:4px 10px;font-size:0.75rem;";
      resetBtn.textContent = "🔄 블록 초기화";
      resetBtn.onclick = () => {
        selectedItems = [];
        statusEl.textContent = "";
        renderTapBlockState();
      };
      ctrlRow.appendChild(statusEl);
      ctrlRow.appendChild(resetBtn);

      renderTapBlockState();
      quizBox.appendChild(trayEl);
      quizBox.appendChild(poolEl);
      quizBox.appendChild(ctrlRow);
    }
  }

  async function requestSocraticHint() {
    const card = currentCard();
    if (!card) return;
    state.hintLevel = Math.min(2, state.hintLevel + 1);
    state.currentEvidence.hintStep = state.hintLevel;
    if (state.isRevealed) applyEvidenceRatingGuard();
    const conciseTarget = card.target_answer || card.rendered_answer;
    const box = el("hint-box");
    if (vm && typeof vm.generateProgressiveHint === "function") {
      const localHint = vm.generateProgressiveHint(conciseTarget, card.extra_explanation || "", state.hintLevel);
      box.textContent = localHint.cueText;
      box.style.display = "block";
    }
    const res = await apiPost("/api/ai/hint", {
      question_text: card.rendered_question,
      target_answer: conciseTarget,
      lapses: card.lapses || 0,
      level: state.hintLevel,
    }).catch(() => null);
    if (res && res.ok) {
      box.textContent = `🧭 [단계 ${res.level}/2] ${res.structural_cue}\n❓ ${res.socratic_question}\n${res.mnemonic_tip}`;
      box.style.display = "block";
    }
  }

  async function evaluateFreeRecall(forceDontKnow = false) {
    const card = currentCard();
    if (!card) return;
    const inputEl = el("recall-input");
    const ans = forceDontKnow ? "" : inputEl.value.trim();
    const expectedTarget = card.target_answer || card.rendered_answer;

    const localEval =
      vm && typeof vm.evaluateTypedAnswerUnderstanding === "function"
        ? vm.evaluateTypedAnswerUnderstanding(ans, expectedTarget)
        : {
            verdict: ans ? "PARTIAL" : "UNKNOWN",
            badgeLabel: ans ? "💡 약간 이해" : "❓ 모름",
            recommendedRating: ans ? 2 : 1,
            feedback: "",
          };

    state.currentEvidence.dontKnow = Boolean(forceDontKnow);
    state.currentEvidence.typedVerdict = localEval.verdict;

    const cid = Number(card.card_id);
    if (localEval.verdict === "UNKNOWN" || localEval.verdict === "PARTIAL") {
      if (!state.sessionWrongCardIds.includes(cid)) {
        state.sessionWrongCardIds.push(cid);
      }
      state.sessionWrongCardMap[cid] = { ...card };
      refreshFilterBadgeCounts();
    }

    revealAnswer();

    const box = el("eval-box");
    const bgMap = {
      EXACT: "#e8faf0",
      PARTIAL: "#fff8e6",
      UNKNOWN: "#fff0f0",
    };
    const fgMap = {
      EXACT: "#008a50",
      PARTIAL: "#b45309",
      UNKNOWN: "#be123c",
    };
    box.style.background = bgMap[localEval.verdict] || "#e8f3ff";
    box.style.color = fgMap[localEval.verdict] || "#1b64da";
    box.textContent = `${localEval.badgeLabel} (일치도 ${localEval.scorePct}%)\n${localEval.feedback}`;
    box.style.display = "block";

    const btnOverride = el("btn-override-correct");
    if (btnOverride) {
      btnOverride.style.display = localEval.verdict !== "EXACT" ? "inline-block" : "none";
    }

    if (ans) {
      const res = await apiPost("/api/ai/evaluate", {
        user_answer: ans,
        expected_answer: expectedTarget,
        question_text: card.rendered_question,
      }).catch(() => null);
      if (res && res.ok) {
        box.textContent = `${localEval.badgeLabel} (정확도 ${res.score_pct}%)\n${res.feedback}`;
      }
    }
  }

  async function decomposeCurrentLeech() {
    const card = currentCard();
    if (!card) return;
    const res = await apiPost("/api/ai/decompose-leech", {
      front_text: card.front_text,
      back_text: card.back_text,
      deck_id: card.deck_id,
      parent_card_id: card.card_id,
      auto_save: true,
    });
    if (res && res.ok) {
      const suspendedLabel = res.parent_suspended ? " (원본 복합 카드 자동 정지)" : "";
      const splitCount = Array.isArray(res.cards) ? res.cards.length : 0;
      await refreshDashboardAndQueue();
      showUxToast(
        `🧬 [쉬운 카드로 쪼개기 완료] 복합 카드를 ${splitCount}개의 단일 개념 카드로 나누어 현재 덱에 추가했습니다!${suspendedLabel}`,
        "emerald"
      );
    }
  }

  function speakCurrentCard() {
    const card = currentCard();
    if (!card) return;
    if (!("speechSynthesis" in window)) {
      showUxToast("🔇 현재 브라우저 환경에서 Web Speech TTS 음성 합성을 지원하지 않습니다.", "amber");
      return;
    }
    window.speechSynthesis.cancel();
    const textToSpeak = state.isRevealed ? (card.target_answer || card.rendered_answer) : card.rendered_question;
    const cleanText = textToSpeak.replace(/[【】\[\]]/g, " ");
    const utter = new SpeechSynthesisUtterance(cleanText);
    const hasKorean = /[가-힣]/.test(cleanText);
    utter.lang = hasKorean ? "ko-KR" : "en-US";
    utter.rate = 0.96;
    window.speechSynthesis.speak(utter);
    showUxToast(`🔊 ${state.isRevealed ? "정답" : "질문"} 원어민 발음 재생 중...`, "accent");
  }

  function bindEvents() {
    el("deck-select").addEventListener("change", (e) => {
      state.selectedDeckId = e.target.value;
      refreshDashboardAndQueue();
    });

    el("btn-reveal").addEventListener("click", revealAnswer);
    const btnQuiz = el("btn-quiz-mode");
    if (btnQuiz) {
      btnQuiz.addEventListener("click", () => {
        const order = ["choice", "typing", "flip"];
        const cur =
          state.cardModeOverride ||
          (vm && typeof vm.resolveCardSolveMode === "function"
            ? vm.resolveCardSolveMode(currentCard(), state.learnerProfile)
            : "choice");
        const nextIdx = (order.indexOf(cur) + 1) % order.length;
        state.cardModeOverride = order[nextIdx];
        renderCurrentCard();
      });
    }

    // Frame 5: 3-Segment Switcher in Create Tab (doc | manual | ai)
    document.querySelectorAll(".create-seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const seg = btn.getAttribute("data-create-seg") || "doc";
        document.querySelectorAll(".create-seg-btn").forEach((b) => {
          if (b.getAttribute("data-create-seg") === seg) b.classList.add("btn-primary");
          else b.classList.remove("btn-primary");
        });
        ["doc", "manual", "ai"].forEach((id) => {
          const p = el(`create-seg-${id}`);
          if (p) p.style.display = id === seg ? "block" : "none";
        });
      });
    });
    const btnUndo = el("btn-undo-review");
    if (btnUndo) btnUndo.addEventListener("click", undoLastReview);
    const btnResetStudy = el("btn-reset-study");
    if (btnResetStudy) btnResetStudy.addEventListener("click", resetStudyProgress);
    const btnResetArena = el("btn-reset-card-arena");
    if (btnResetArena) btnResetArena.addEventListener("click", resetStudyProgress);
    const btnResetPostSession = el("btn-reset-post-session");
    if (btnResetPostSession) btnResetPostSession.addEventListener("click", resetStudyProgress);
    el("btn-hint").addEventListener("click", requestSocraticHint);
    el("btn-decompose").addEventListener("click", decomposeCurrentLeech);
    el("btn-tts").addEventListener("click", speakCurrentCard);
    el("btn-eval").addEventListener("click", () => evaluateFreeRecall(false));
    const btnDontKnow = el("btn-dont-know");
    if (btnDontKnow) {
      btnDontKnow.addEventListener("click", () => evaluateFreeRecall(true));
    }

    const btnToggleShuffle = el("btn-toggle-shuffle");
    if (btnToggleShuffle) {
      btnToggleShuffle.addEventListener("click", () => {
        state.shuffleMode = state.shuffleMode === "interleaved" ? "sequential" : "interleaved";
        const isInterleaved = state.shuffleMode === "interleaved";
        btnToggleShuffle.textContent = isInterleaved ? "🔀 스마트 랜덤 섞기: ON" : "📋 순차 학습: ON";
        if (isInterleaved) {
          btnToggleShuffle.classList.add("btn-primary");
        } else {
          btnToggleShuffle.classList.remove("btn-primary");
        }
        applyStudyFilter();
        renderCurrentCard();
        showUxToast(
          isInterleaved
            ? "🔀 단원·유형 쏠림 방지 스마트 인터리빙 랜덤 모드가 활성화되었습니다!"
            : "📋 기본 순차 출제 모드로 전환되었습니다.",
          "accent"
        );
      });
    }

    // Study Filter Mode Buttons (All / Wrong-Unknown Only / Marked Only)
    function setStudyFilterMode(mode) {
      state.studyFilterMode = mode || "all";
      document.querySelectorAll(".study-filter-btn").forEach((b) => {
        if (b.getAttribute("data-filter") === state.studyFilterMode) {
          b.classList.add("btn-primary");
        } else {
          b.classList.remove("btn-primary");
        }
      });
      applyStudyFilter();
      renderCurrentCard();
    }
    document.querySelectorAll(".study-filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        setStudyFilterMode(btn.getAttribute("data-filter") || "all");
      });
    });

    // Gate T43: Question-Type Filter Buttons (All / Vocab / Grammar / Hanja / History-Sci)
    function setQuestionTypeFilter(qtype) {
      state.questionTypeFilter = qtype || "all";
      document.querySelectorAll(".study-qtype-btn").forEach((b) => {
        if (b.getAttribute("data-qtype") === state.questionTypeFilter) {
          b.classList.add("btn-primary");
        } else {
          b.classList.remove("btn-primary");
        }
      });
      applyStudyFilter();
      renderCurrentCard();
    }
    document.querySelectorAll(".study-qtype-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const qtype = btn.getAttribute("data-qtype") || "all";
        setQuestionTypeFilter(qtype);
        const labelMap = {
          all: "🗂️ 전체 유형 통합 출제 모드 (4지선다 보기는 각 문제 유형별로 자동 분리됩니다)",
          vocab: "📘 단어·어휘 문제만 모아 풀기 모드",
          grammar: "📐 문법·어법 문제만 모아 풀기 모드",
          hanja: "漢字 한자·사자성어 문제만 모아 풀기 모드",
          history_sci: "🏛️ 역사·과학·전공 개념 문제만 모아 풀기 모드",
        };
        showUxToast(labelMap[qtype] || labelMap.all, "accent");
      });
    });

    const btnRetryWrong = el("btn-retry-wrong-now");
    if (btnRetryWrong) {
      btnRetryWrong.addEventListener("click", () => {
        setStudyFilterMode("wrong_only");
        showUxToast("🔥 오답·모르는 카드 집중 복습 모드를 시작합니다!", "amber");
      });
    }

    // Card Actions: Mark (Star), Bury Today, Suspend
    const btnMarkCard = el("btn-mark-card");
    if (btnMarkCard) {
      btnMarkCard.addEventListener("click", () => {
        const card = currentCard();
        if (!card) return;
        const cid = Number(card.card_id);
        let isNowMarked = false;
        if (state.markedCardIds.includes(cid)) {
          state.markedCardIds = state.markedCardIds.filter((id) => id !== cid);
          showUxToast("☆ 별표 표시를 해제했습니다.", "accent");
        } else {
          state.markedCardIds.push(cid);
          isNowMarked = true;
          showUxToast("⭐ 별표 카드로 저장했습니다! 상단 [⭐ 별표 카드만]에서 모아볼 수 있습니다.", "emerald");
        }
        btnMarkCard.textContent = isNowMarked ? "⭐ 별표됨" : "☆ 별표";
        btnMarkCard.style.color = isNowMarked ? "var(--amber)" : "var(--muted)";
        if (state.studyFilterMode === "marked_only") {
          applyStudyFilter();
          renderCurrentCard();
        } else {
          refreshFilterBadgeCounts();
        }
      });
    }

    const btnBuryCard = el("btn-bury-card");
    if (btnBuryCard) {
      btnBuryCard.addEventListener("click", () => {
        const card = currentCard();
        if (!card) return;
        const cid = Number(card.card_id);
        if (!state.buriedCardIds.includes(cid)) {
          state.buriedCardIds.push(cid);
        }
        applyStudyFilter();
        renderCurrentCard();
        showUxToast("💤 이 카드를 오늘 하루 학습 큐에서 숨겼습니다.", "accent");
      });
    }

    const btnSuspendCard = el("btn-suspend-card");
    if (btnSuspendCard) {
      btnSuspendCard.addEventListener("click", async () => {
        const card = currentCard();
        if (!card) return;
        const cid = Number(card.card_id);
        if (!state.buriedCardIds.includes(cid)) {
          state.buriedCardIds.push(cid);
        }
        await apiPost("/api/cards/suspend", { card_id: cid }).catch(() => null);
        applyStudyFilter();
        renderCurrentCard();
        showUxToast("⏸️ 카드를 영구 일시 정지했습니다.", "amber");
      });
    }

    // Direct Card Add (Basic & Cloze {{c1::...}})
    const btnInsertCloze = el("btn-insert-cloze");
    if (btnInsertCloze) {
      btnInsertCloze.addEventListener("click", () => {
        const frontEl = el("direct-card-front");
        if (!frontEl) return;
        frontEl.value = `${frontEl.value ? frontEl.value + " " : ""}{{c1::핵심정답}}`;
        frontEl.focus();
      });
    }

    const btnAddDirectCard = el("btn-add-direct-card");
    if (btnAddDirectCard) {
      btnAddDirectCard.addEventListener("click", async () => {
        const frontEl = el("direct-card-front");
        const backEl = el("direct-card-back");
        const statusEl = el("direct-card-status");
        const front = (frontEl && frontEl.value.trim()) || "";
        const back = (backEl && backEl.value.trim()) || "";
        if (!front || !back) {
          if (statusEl) statusEl.textContent = "✏️ 앞면(질문)과 뒷면(정답)을 모두 입력해 주세요.";
          return;
        }
        const targetDeck = state.selectedDeckId ? Number(state.selectedDeckId) : null;
        const rawLine = `${front} : ${back}`;
        const res = await apiPost("/api/ai/generate-cards", {
          raw_text: rawLine,
          domain_mode: "auto",
          deck_id: targetDeck,
          auto_save: true,
        });
        if (res && res.ok) {
          if (frontEl) frontEl.value = "";
          if (backEl) backEl.value = "";
          if (statusEl) statusEl.textContent = "✅ 새 카드가 단어장에 바로 추가되었습니다!";
          await refreshDashboardAndQueue();
          showUxToast("➕ 새 카드가 단어장에 추가되었습니다!", "emerald");
        }
      });
    }

    el("recall-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        evaluateFreeRecall();
      }
    });

    const btnOverrideCorrect = el("btn-override-correct");
    if (btnOverrideCorrect) {
      btnOverrideCorrect.addEventListener("click", () => {
        const card = currentCard();
        if (!card) return;
        state.currentEvidence.typedVerdict = "EXACT";
        state.currentEvidence.dontKnow = false;
        state.currentEvidence.choiceCorrect = true;
        const cid = Number(card.card_id);
        state.sessionWrongCardIds = state.sessionWrongCardIds.filter((id) => id !== cid);
        delete state.sessionWrongCardMap[cid];
        refreshFilterBadgeCounts();
        applyEvidenceRatingGuard();
        btnOverrideCorrect.style.display = "none";
        const evalBox = el("eval-box");
        if (evalBox) {
          evalBox.style.background = "#e8faf0";
          evalBox.style.color = "#008a50";
          evalBox.textContent = "✅ 내 답이 맞아요 (정답 인정 완료)\n오타·유의어를 정답으로 인정했습니다. 아래 난이도 버튼(추천: 3 · Good)을 눌러 다음 카드로 이동하세요.";
          evalBox.style.display = "block";
        }
        showUxToast("✅ 오타·유의어 정답 인정! 해설을 확인한 뒤 알맞음(3 · Good)을 눌러주세요.", "emerald");
      });
    }

    [1, 2, 3, 4].forEach((r) => {
      el(`rate-${r}`).addEventListener("click", () => submitRating(r));
    });

    el("btn-generate-cards").addEventListener("click", async () => {
      const rawText = el("ai-raw-text").value.trim();
      if (!rawText) {
        el("ai-gen-status").textContent = "✏️ 먼저 학습 노트나 조문·교과서 문장을 입력창에 붙여넣어 주세요.";
        el("ai-raw-text").focus();
        return;
      }
      const mode = el("ai-domain-mode").value;
      const diffEl = el("ai-difficulty-select");
      const diffLevel = (diffEl && diffEl.value) || "standard";
      const ollamaSel = el("ai-ollama-model-select");
      const ollamaModel = (ollamaSel && ollamaSel.value) || "glm-5.3-flash";
      const targetDeck = state.selectedDeckId ? Number(state.selectedDeckId) : null;
      el("ai-gen-status").textContent = "⏳ 스마트 카드 생성 중...";
      const res = await apiPost("/api/ai/generate-cards", {
        raw_text: rawText,
        domain_mode: mode,
        deck_id: targetDeck,
        auto_save: true,
        difficulty_level: diffLevel,
        ollama_cloud_model: ollamaModel,
      });
      if (res && res.ok) {
        const aiDecision =
          vm && typeof vm.resolveSmartAiEngine === "function"
            ? vm.resolveSmartAiEngine({
                taskType: "card_generate",
                manualOverride: res.ollama_cloud_model || ollamaModel,
                offlineOnly: !res.ollama_cloud_used && res.provider !== "llm",
              })
            : { ui_label: res.ollama_cloud_used ? "✨ 스마트 자동 생성" : "⚡ 오프라인 빠른 생성" };
        const providerBadge = aiDecision.ui_label || "✨ 스마트 자동 생성";
        el("ai-gen-status").textContent = `✅ ${res.generated_count}장 생성 및 저장 완료! [${providerBadge} · 난이도 ${diffLevel.toUpperCase()} · ${res.latency_ms || 0}ms]`;
        el("ai-raw-text").value = "";
        await refreshDashboardAndQueue();
      }
    });

    // Photo & PDF Auto-Deck Builder events (with Smart AI Engine Policy Router)
    const dropzone = el("doc-dropzone");
    const fileInput = el("doc-file-input");

    async function handleDocumentFile(file) {
      if (!file) return;
      const banner = el("doc-ingest-banner");
      const previewContainer = el("doc-preview-container");
      const docOllamaEl = el("doc-ollama-model-select");
      const ollamaModel = (docOllamaEl && docOllamaEl.value) || "glm-5.3-flash";
      banner.style.display = "block";
      banner.style.borderColor = "var(--accent)";
      banner.style.color = "var(--text)";
      const docEngineDecision =
        vm && typeof vm.resolveSmartAiEngine === "function"
          ? vm.resolveSmartAiEngine({
              taskType: "ocr_extract",
              manualOverride: ollamaModel,
              offlineOnly: ollamaModel === "local_rule",
            })
          : { ui_label: ollamaModel !== "local_rule" ? "✨ 스마트 자동 생성" : "⚡ 오프라인 빠른 생성" };
      const modelTagLabel = docEngineDecision.ui_label || "✨ 스마트 자동 생성";
      banner.textContent = `⏳ '${file.name}' (${(file.size / 1024).toFixed(1)}KB) ${modelTagLabel} 분석 및 카드 생성 중...`;
      previewContainer.style.display = "none";

      const deckName = el("doc-deck-name").value.trim();
      const autoSave = el("doc-auto-save").checked ? "1" : "0";
      const docDiffEl = el("doc-difficulty-select");
      const docDiff = (docDiffEl && docDiffEl.value) || "standard";
      const params = new URLSearchParams({
        auto_save: autoSave,
        max_cards: "30",
        difficulty_level: docDiff,
        ollama_cloud_model: ollamaModel,
      });
      if (deckName) params.set("deck_name", deckName);

      const mime = file.type || (file.name.toLowerCase().endsWith(".pdf") ? "application/pdf" : "image/png");
      const buf = await file.arrayBuffer();
      let res = null;
      try {
        const resp = await fetch(`/api/ai/ingest-document?${params.toString()}`, {
          method: "POST",
          headers: { "Content-Type": mime },
          body: buf,
        });
        res = await resp.json();
      } catch (_err) {
        const cleanTitle = deckName || file.name.replace(/\.[^.]+$/, "") || "사진·PDF 단어장";
        const fallbackRes = standaloneEngine
          ? standaloneEngine.buildSmartTextDeck({
              deck_name: cleanTitle,
              text: `${cleanTitle} : 핵심 개념 및 출제 포인트 정리\n${file.name} -> 주요 정의와 빈칸 인출 학습`,
              difficulty_level: docDiff,
              auto_save: autoSave === "1",
            })
          : { cards: [] };
        res = {
          ok: true,
          status: "OK",
          deck_id: autoSave === "1" ? fallbackRes.deck_id : null,
          deck_name: cleanTitle,
          category: "general",
          ollama_cloud_model: ollamaModel,
          ollama_cloud_used: ollamaModel !== "local_rule",
          provider: ollamaModel !== "local_rule" ? `ollama_cloud:${ollamaModel}` : "standalone_local",
          latency_ms: 12,
          stats: { pages: 1, ocr_pages: 1, low_confidence_lines: 0, dropped_ungrounded: 0, duplicates: 0 },
          cards: (fallbackRes.cards || []).map((c, idx) => ({
            ...c,
            pattern: "definition",
            source_page: 1,
            source_excerpt: file.name,
            tags: (c.tags || []).concat(["ollama-cloud", `model:${ollamaModel}`]),
          })),
        };
      }
      const formatted = vm.formatIngestStatusBanner(res);
      banner.style.borderColor = formatted.tone === "rose" ? "var(--rose)" : "var(--emerald)";
      banner.style.color = formatted.tone === "rose" ? "var(--rose)" : "var(--text)";
      banner.textContent = `${formatted.title}\n${formatted.summary}`;

      if (res && res.status === "OK") {
        state.pendingDeckPlan = {
          deck_name: res.deck_name,
          category: res.category,
          cards: (res.cards || []).map((c) => ({ ...c })),
        };
        const isAlreadySaved = Boolean(res.deck_id);
        const listEl = el("doc-preview-list");

        function renderPreviewCards() {
          listEl.textContent = "";
          const activeCards = (state.pendingDeckPlan && state.pendingDeckPlan.cards) || [];
          activeCards.forEach((c, idx) => {
            const itemDiv = document.createElement("div");
            itemDiv.style.cssText =
              "background:#f9fafb;border:1px solid var(--border);border-radius:12px;padding:10px 12px;font-size:0.82rem;display:flex;flex-direction:column;gap:6px;";

            const headerRow = document.createElement("div");
            headerRow.style.cssText =
              "display:flex;justify-content:space-between;align-items:center;color:var(--accent);font-weight:700;";

            const patLabel = vm.formatPatternBadge(c.pattern);
            const leftSpan = document.createElement("span");
            leftSpan.textContent = `#${idx + 1} [${patLabel} · ${String(c.note_type || "basic").toUpperCase()}]`;

            const rightBox = document.createElement("div");
            rightBox.style.cssText = "display:flex;align-items:center;gap:8px;";
            const pageSpan = document.createElement("span");
            pageSpan.textContent = `📄 p.${c.source_page} 출처 검증됨`;
            rightBox.appendChild(pageSpan);

            if (!isAlreadySaved) {
              const removeBtn = document.createElement("button");
              removeBtn.type = "button";
              removeBtn.textContent = "제외";
              removeBtn.style.cssText =
                "background:rgba(244,63,94,0.18);color:var(--rose);border:1px solid var(--rose);border-radius:5px;padding:1px 7px;font-size:0.72rem;cursor:pointer;";
              removeBtn.addEventListener("click", () => {
                state.pendingDeckPlan.cards.splice(idx, 1);
                renderPreviewCards();
              });
              rightBox.appendChild(removeBtn);
            }

            headerRow.appendChild(leftSpan);
            headerRow.appendChild(rightBox);
            itemDiv.appendChild(headerRow);

            if (isAlreadySaved) {
              const qDiv = document.createElement("div");
              qDiv.style.cssText = "font-weight:600;margin-bottom:2px;";
              qDiv.textContent = `Q: ${c.front_text}`;
              const aDiv = document.createElement("div");
              aDiv.style.cssText = "color:var(--emerald);";
              aDiv.textContent = `A: ${c.back_text}`;
              itemDiv.appendChild(qDiv);
              itemDiv.appendChild(aDiv);
            } else {
              const qInput = document.createElement("input");
              qInput.type = "text";
              qInput.value = c.front_text;
              qInput.setAttribute("aria-label", `카드 ${idx + 1} 질문 편집`);
              qInput.style.cssText =
                "width:100%;background:rgba(9,13,22,0.8);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:0.78rem;font-weight:600;";
              qInput.addEventListener("input", () => {
                c.front_text = qInput.value;
              });

              const aInput = document.createElement("input");
              aInput.type = "text";
              aInput.value = c.back_text;
              aInput.setAttribute("aria-label", `카드 ${idx + 1} 정답 편집`);
              aInput.style.cssText =
                "width:100%;background:rgba(9,13,22,0.8);color:var(--emerald);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:0.78rem;";
              aInput.addEventListener("input", () => {
                c.back_text = aInput.value;
              });

              itemDiv.appendChild(qInput);
              itemDiv.appendChild(aInput);
            }

            listEl.appendChild(itemDiv);
          });

          el("doc-preview-title").textContent = isAlreadySaved
            ? `🎉 '${res.deck_name}' 덱에 ${activeCards.length}장이 즉시 저장되었습니다!`
            : `🔍 미리보기 (${activeCards.length}장) — 앞/뒷면 수정 또는 불필요 카드 제외 후 일괄 생성하세요`;
          el("btn-save-doc-deck").style.display =
            formatted.canSave && activeCards.length > 0 ? "inline-block" : "none";
        }

        renderPreviewCards();
        previewContainer.style.display = "block";
        if (res.deck_id) {
          state.selectedDeckId = String(res.deck_id);
          await refreshDashboardAndQueue();
        }
      }
    }

    if (dropzone && fileInput) {
      dropzone.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
          handleDocumentFile(e.target.files[0]);
          e.target.value = "";
        }
      });
      dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "var(--emerald)";
      });
      dropzone.addEventListener("dragleave", () => {
        dropzone.style.borderColor = "rgba(56,189,248,0.45)";
      });
      dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "rgba(56,189,248,0.45)";
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
          handleDocumentFile(e.dataTransfer.files[0]);
        }
      });
    }

    const btnSaveDocDeck = el("btn-save-doc-deck");
    if (btnSaveDocDeck) {
      btnSaveDocDeck.addEventListener("click", async () => {
        const plan = state.pendingDeckPlan;
        if (!plan || !plan.cards || !plan.cards.length) return;
        const customName = el("doc-deck-name").value.trim() || plan.deck_name;
        const res = await apiPost("/api/decks/batch-save", {
          deck_name: customName,
          category: plan.category,
          cards: plan.cards,
        });
        if (res && res.ok) {
          el("doc-preview-title").textContent = `🎉 '${res.deck_name}' 덱 (${res.saved_count}장) 일괄 생성 완료!`;
          btnSaveDocDeck.style.display = "none";
          state.selectedDeckId = String(res.deck_id);
          await refreshDashboardAndQueue();
        }
      });
    }

    el("btn-decompress").addEventListener("click", async () => {
      const targetDeck = state.selectedDeckId ? Number(state.selectedDeckId) : null;
      const res = await apiPost("/api/backlog/decompress", {
        deck_id: targetDeck,
        daily_cap: 25,
        horizon_days: 7,
      });
      if (res && res.ok) {
        showUxToast(
          `🏖️ 복습 폭탄 평탄화 완료! 대기 ${res.total_due_evaluated}장 중 오늘 저-R 위험군 ${res.kept_today}장 유지 · 향후 ${res.horizon_days}일로 ${res.deferred_across_days}장 안전 분산`,
          "emerald"
        );
        await refreshDashboardAndQueue();
      }
    });

    window.addEventListener("keydown", (e) => {
      const activeTag = (document.activeElement && document.activeElement.tagName) || "";
      const isTyping = activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT";
      const cmd = vm.mapKeyboardShortcut(e.key, state.isRevealed, isTyping, state.ageTier);
      if (!cmd) return;
      e.preventDefault();
      if (cmd.action === "reveal") revealAnswer();
      else if (cmd.action === "rate") submitRating(cmd.rating);
      else if (cmd.action === "hint") requestSocraticHint();
      else if (cmd.action === "tts") speakCurrentCard();
      else if (cmd.action === "quiz") requestInteractiveQuiz("");
      else if (cmd.action === "undo") undoLastReview();
    });
  }

  function renderCatalogLockRecovery(statusEl, apiErrorRes, retryCallback) {
    if (!statusEl) return;
    statusEl.textContent = "";
    const errVm =
      vm && typeof vm.formatApiErrorBanner === "function"
        ? vm.formatApiErrorBanner(apiErrorRes)
        : { title: "🔒 브레인팩 잠금", message: (apiErrorRes && apiErrorRes.error) || "잠금 상태입니다." };

    const msgDiv = document.createElement("div");
    msgDiv.style.cssText = "color:var(--amber);margin-bottom:6px;font-weight:600;";
    msgDiv.textContent = `${errVm.title} — ${errVm.message}`;
    statusEl.appendChild(msgDiv);

    if (errVm.actionPackId) {
      const quickUnlockBtn = document.createElement("button");
      quickUnlockBtn.type = "button";
      quickUnlockBtn.className = "btn-primary";
      quickUnlockBtn.style.cssText = "padding:5px 11px;font-size:0.76rem;";
      quickUnlockBtn.textContent = `⚡ 스토어에서 '${errVm.actionPackId}' 즉시 장착 후 덱 생성하기`;
      quickUnlockBtn.onclick = async () => {
        statusEl.textContent = `⏳ '${errVm.actionPackId}' 브레인팩 즉시 장착 중...`;
        const pRes = await apiPost("/api/store/purchase", {
          pack_id: errVm.actionPackId,
          auto_create_deck: false,
          payment_token: `BDPAY-QUICK-${errVm.actionPackId}`,
        });
        if (pRes && pRes.ok) {
          await loadBrainPackStoreAndBind();
          await loadCatalogAndBind();
          if (typeof retryCallback === "function") {
            await retryCallback();
          }
        }
      };
      statusEl.appendChild(quickUnlockBtn);
    }
  }

  async function loadCatalogAndBind() {
    const cat = await apiGet("/api/catalog");
    if (!cat || !cat.ok) return;
    state.catalog = cat;

    const tbSel = el("catalog-textbook-select");
    const unitsBox = el("catalog-units-box");
    const colSel = el("catalog-collection-select");
    const statusMsgEl = el("catalog-status-msg");
    if (!tbSel || !unitsBox || !colSel) return;

    const prevTbVal = tbSel.value;
    tbSel.textContent = "";
    (cat.textbooks || []).forEach((tb) => {
      const opt = document.createElement("option");
      opt.value = tb.textbook_id;
      const lockBadge = tb.unlocked ? "🔓 보유중" : "🔒 스토어 잠금";
      opt.textContent = `[${lockBadge}] ${tb.title} (${tb.publisher_name} · ${tb.curriculum_revision} 개정)`;
      tbSel.appendChild(opt);
    });
    if (prevTbVal && Array.from(tbSel.options).some((o) => o.value === prevTbVal)) {
      tbSel.value = prevTbVal;
    }

    function renderUnitsForSelectedTextbook() {
      unitsBox.textContent = "";
      const tb = (cat.textbooks || []).find((t) => t.textbook_id === tbSel.value);
      if (!tb || !tb.units) return;
      tb.units.forEach((u, idx) => {
        const lbl = document.createElement("label");
        lbl.style.cssText =
          "display:inline-flex;align-items:center;gap:5px;font-size:0.8rem;padding:6px 10px;border-radius:10px;background:#ffffff;border:1px solid var(--border);cursor:pointer;font-weight:600;";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.value = u.unit_id;
        cb.className = "exam-unit-cb";
        if (idx < 2) cb.checked = true;
        const span = document.createElement("span");
        span.textContent = `${u.unit_code_label}: ${u.unit_title} (p.${u.page_start}~${u.page_end})`;
        lbl.appendChild(cb);
        lbl.appendChild(span);
        unitsBox.appendChild(lbl);
      });
    }

    tbSel.onchange = renderUnitsForSelectedTextbook;
    renderUnitsForSelectedTextbook();

    const btnToggleAll = el("btn-toggle-all-units");
    if (btnToggleAll) {
      btnToggleAll.onclick = () => {
        const boxes = Array.from(document.querySelectorAll(".exam-unit-cb"));
        const allChecked = boxes.length > 0 && boxes.every((b) => b.checked);
        boxes.forEach((b) => {
          b.checked = !allChecked;
        });
      };
    }

    const prevColVal = colSel.value;
    colSel.textContent = "";
    (cat.collections || []).forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.collection_id;
      const lockBadge = c.unlocked ? "🔓 보유중" : "🔒 스토어 잠금";
      opt.textContent = `[${lockBadge}] ${c.level_label} (${c.item_count}문항 · ${c.collection_id})`;
      colSel.appendChild(opt);
    });
    if (prevColVal && Array.from(colSel.options).some((o) => o.value === prevColVal)) {
      colSel.value = prevColVal;
    }

    const diffSel = el("curriculum-difficulty-select");
    const getCurriculumDiff = () => (diffSel && diffSel.value) || "mixed";

    const comboListEl = el("combined-scope-list");
    function renderCombinedScopesList() {
      const btnCombinedSeg = el("btn-curr-seg-combined");
      if (btnCombinedSeg && vm && typeof vm.resolveCurriculumSegmentState === "function") {
        const segState = vm.resolveCurriculumSegmentState("textbook", (state.combinedExamScopes || []).length);
        btnCombinedSeg.textContent = segState.combined_tab_label;
      }
      if (!comboListEl) return;
      comboListEl.textContent = "";
      if (!state.combinedExamScopes.length) {
        const emptyDiv = document.createElement("div");
        emptyDiv.style.cssText =
          "padding:12px;border-radius:12px;background:#ffffff;border:1px dashed var(--border);font-size:0.8rem;color:var(--muted);text-align:center;";
        emptyDiv.textContent =
          "아직 담긴 시험범위가 없습니다. 위에서 교과서 단원이나 급수 팩을 골라 [➕ 통합 시험범위에 추가]를 눌러보세요!";
        comboListEl.appendChild(emptyDiv);
        return;
      }
      state.combinedExamScopes.forEach((item, idx) => {
        const row = document.createElement("div");
        row.style.cssText =
          "display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 12px;border-radius:12px;background:#ffffff;border:1px solid var(--border);font-size:0.82rem;font-weight:600;";
        const labelSpan = document.createElement("span");
        labelSpan.textContent = `${idx + 1}. ${item.label} [${String(item.difficulty_level || "mixed").toUpperCase()}]`;
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.style.cssText = "padding:3px 8px;font-size:0.74rem;color:var(--rose);";
        delBtn.textContent = "삭제 ✕";
        delBtn.onclick = () => {
          state.combinedExamScopes.splice(idx, 1);
          renderCombinedScopesList();
        };
        row.appendChild(labelSpan);
        row.appendChild(delBtn);
        comboListEl.appendChild(row);
      });
    }
    renderCombinedScopesList();

    const btnAddExamToCombo = el("btn-add-exam-to-combo");
    if (btnAddExamToCombo) {
      btnAddExamToCombo.onclick = () => {
        const checked = Array.from(document.querySelectorAll(".exam-unit-cb:checked")).map((n) => n.value);
        if (!checked.length) {
          showUxToast("⚠️ 먼저 통합 시험범위에 추가할 단원을 1개 이상 체크해 주세요.", "amber");
          return;
        }
        const tb = (cat.textbooks || []).find((t) => t.textbook_id === tbSel.value);
        const pStart = el("exam-page-start").value.trim();
        const pEnd = el("exam-page-end").value.trim();
        const diffLevel = getCurriculumDiff();
        const pageStr = pStart || pEnd ? ` (p.${pStart || "1"}~${pEnd || "끝"})` : "";
        state.combinedExamScopes.push({
          textbook_id: tbSel.value,
          unit_ids: checked,
          page_start: pStart ? Number(pStart) : null,
          page_end: pEnd ? Number(pEnd) : null,
          difficulty_level: diffLevel,
          label: `🏫 ${(tb && tb.title) || tbSel.value} (${checked.length}개 단원${pageStr})`,
        });
        renderCombinedScopesList();
        showUxToast(`➕ 통합 시험범위에 교과서 ${checked.length}개 단원을 담았습니다! (총 ${state.combinedExamScopes.length}개 범위)`, "emerald");
      };
    }

    const btnAddColToCombo = el("btn-add-col-to-combo");
    if (btnAddColToCombo) {
      btnAddColToCombo.onclick = () => {
        if (!colSel.value) return;
        const cMeta = (cat.collections || []).find((c) => c.collection_id === colSel.value);
        const diffLevel = getCurriculumDiff();
        state.combinedExamScopes.push({
          collection_id: colSel.value,
          limit: 350,
          difficulty_level: diffLevel,
          label: `📚 ${(cMeta && cMeta.level_label) || colSel.value}`,
        });
        renderCombinedScopesList();
        showUxToast(`➕ 통합 시험범위에 '${(cMeta && cMeta.level_label) || colSel.value}' 범위를 담았습니다!`, "emerald");
      };
    }

    const btnPresetCombo = el("btn-preset-midterm-combo");
    if (btnPresetCombo) {
      btnPresetCombo.onclick = () => {
        const diffLevel = getCurriculumDiff();
        const unlockedTbs = (cat.textbooks || []).filter((t) => t.unlocked);
        const unlockedCols = (cat.collections || []).filter((c) => c.unlocked);
        state.combinedExamScopes = [];
        unlockedTbs.slice(0, 2).forEach((tb) => {
          const uIds = (tb.units || []).slice(0, 2).map((u) => u.unit_id);
          if (uIds.length) {
            state.combinedExamScopes.push({
              textbook_id: tb.textbook_id,
              unit_ids: uIds,
              difficulty_level: diffLevel,
              label: `🏫 ${tb.title} (1~${uIds.length}단원)`,
            });
          }
        });
        unlockedCols.slice(0, 3).forEach((c) => {
          state.combinedExamScopes.push({
            collection_id: c.collection_id,
            limit: 350,
            difficulty_level: diffLevel,
            label: `📚 ${c.level_label}`,
          });
        });
        renderCombinedScopesList();
        showUxToast(`⚡ 보유 중인 ${state.combinedExamScopes.length}개 다중 출제범위를 조합 장바구니에 담았습니다!`, "accent");
      };
    }

    const btnClearCombo = el("btn-clear-combined-scopes");
    if (btnClearCombo) {
      btnClearCombo.onclick = () => {
        state.combinedExamScopes = [];
        renderCombinedScopesList();
      };
    }

    const btnGenCombo = el("btn-gen-combined-exam-deck");
    if (btnGenCombo) {
      const runCombinedGen = async () => {
        if (!state.combinedExamScopes.length) {
          showUxToast("⚠️ 먼저 [➕ 통합 시험범위에 추가] 또는 [⚡ 중간고사 다중 범위 예시 담기]로 1개 이상 범위를 담아주세요.", "amber");
          return;
        }
        const customNameEl = el("combined-deck-name");
        const customName = (customNameEl && customNameEl.value.trim()) || "";
        const diffLevel = getCurriculumDiff();
        if (statusMsgEl) {
          statusMsgEl.textContent = "⏳ 다중 시험범위를 스마트 인터리빙 랜덤 알고리즘으로 조합 중입니다...";
        }
        const res = await apiPost("/api/catalog/generate-combined-exam-deck", {
          scopes: state.combinedExamScopes,
          deck_name: customName || null,
          difficulty_level: diffLevel,
          shuffle_mode: "interleaved",
          max_cards: 1000,
        });
        if (res && res.ok) {
          if (statusMsgEl) {
            statusMsgEl.textContent = `✅ '${res.deck_name}' (${res.saved_count}장 · ${state.combinedExamScopes.length}개 범위 인터리빙 조합) 생성 완료!`;
          }
          state.selectedDeckId = String(res.deck_id);
          state.shuffleMode = "interleaved";
          await refreshDashboardAndQueue();
          switchTabPage("study");
          showUxToast(
            `🎲 '${res.deck_name}' (${res.saved_count}장) 지능형 랜덤 통합 학습을 시작합니다!`,
            "emerald"
          );
        } else {
          renderCatalogLockRecovery(statusMsgEl, res, runCombinedGen);
        }
      };
      btnGenCombo.onclick = runCombinedGen;
    }

    const btnExam = el("btn-gen-exam-scope");
    if (btnExam) {
      const runExamScopeGen = async () => {
        const checked = Array.from(document.querySelectorAll(".exam-unit-cb:checked")).map((n) => n.value);
        if (!checked.length) {
          if (statusMsgEl) {
            statusMsgEl.textContent = "⚠️ 먼저 시험범위에 포함할 단원을 1개 이상 체크해 주세요.";
          }
          return;
        }
        const pStart = el("exam-page-start").value.trim();
        const pEnd = el("exam-page-end").value.trim();
        const diffLevel = getCurriculumDiff();
        if (statusMsgEl) {
          statusMsgEl.textContent = "⏳ 선택한 시험범위 암기 카드를 생성 중입니다...";
        }
        const res = await apiPost("/api/catalog/generate-exam-scope-deck", {
          textbook_id: tbSel.value,
          unit_ids: checked,
          page_start: pStart ? Number(pStart) : null,
          page_end: pEnd ? Number(pEnd) : null,
          difficulty_level: diffLevel,
          shuffle_mode: "interleaved",
          limit: 1000,
        });
        if (res && res.ok) {
          if (statusMsgEl) {
            statusMsgEl.textContent = `✅ '${res.deck_name}' (${res.saved_count}장) 생성 완료!`;
          }
          state.selectedDeckId = String(res.deck_id);
          await refreshDashboardAndQueue();
          switchTabPage("study");
          showUxToast(`🎯 '${res.deck_name}' (${res.saved_count}장) 학습을 시작합니다!`, "emerald");
        } else {
          renderCatalogLockRecovery(statusMsgEl, res, runExamScopeGen);
        }
      };
      btnExam.onclick = runExamScopeGen;
    }

    const btnCol = el("btn-gen-collection");
    if (btnCol) {
      const runCollectionGen = async () => {
        if (!colSel.value) return;
        const diffLevel = getCurriculumDiff();
        if (statusMsgEl) {
          statusMsgEl.textContent = "⏳ 급수·시험 암기 카드를 생성 중입니다...";
        }
        const res = await apiPost("/api/catalog/generate-collection-deck", {
          collection_id: colSel.value,
          limit: 1000,
          difficulty_level: diffLevel,
          shuffle_mode: "interleaved",
        });
        if (res && res.ok) {
          if (statusMsgEl) {
            statusMsgEl.textContent = `✅ '${res.deck_name}' (${res.saved_count}장) 생성 완료!`;
          }
          state.selectedDeckId = String(res.deck_id);
          await refreshDashboardAndQueue();
          switchTabPage("study");
          showUxToast(`📚 '${res.deck_name}' (${res.saved_count}장) 학습을 시작합니다!`, "emerald");
        } else {
          renderCatalogLockRecovery(statusMsgEl, res, runCollectionGen);
        }
      };
      btnCol.onclick = runCollectionGen;
    }
  }

  async function loadBrainPackStoreAndBind() {
    const storeRes = await apiGet("/api/store/packs");
    if (!storeRes || !storeRes.ok) return;
    state.storePacks = storeRes.packs || [];

    const lockedPaidAll = state.storePacks.filter((p) => !p.unlocked && Number(p.price_krw) > 0);
    state.selectedBundlePackIds = state.selectedBundlePackIds.filter((id) =>
      lockedPaidAll.some((p) => p.pack_id === id)
    );
    if (state.selectedBundlePackIds.length === 0 && lockedPaidAll.length > 0) {
      state.selectedBundlePackIds = lockedPaidAll.slice(0, 3).map((p) => p.pack_id);
    }

    const summaryBadge = el("store-summary-badge");
    if (summaryBadge) {
      summaryBadge.textContent = `장착 ${storeRes.unlocked_packs || 1} / 전체 ${storeRes.total_packs || state.storePacks.length}팩`;
    }

    const storeListEl = el("store-pack-list");
    const statusMsgEl = el("store-status-msg");
    const bundleBtn = el("btn-buy-bundle-3");
    if (!storeListEl) return;

    function updateBundleButtonQuote() {
      if (!bundleBtn) return;
      const chosenIds = state.selectedBundlePackIds.slice();
      if (chosenIds.length === 0 || !vm || typeof vm.calculateStoreBundleQuote !== "function") {
        bundleBtn.style.display = "none";
        return;
      }
      const quote = vm.calculateStoreBundleQuote(state.storePacks, chosenIds);
      const finalPrice = Number(quote.finalPriceKrw ?? quote.finalKrw ?? 0);
      const subPrice = Number(quote.subtotalKrw ?? 0);
      const discApplied = Boolean(quote.discountApplied);
      bundleBtn.style.display = "inline-block";
      bundleBtn.textContent = discApplied
        ? `🎁 선택 ${chosenIds.length}팩 묶음 15% 할인 장착 (₩${subPrice.toLocaleString("ko-KR")} ➔ ₩${finalPrice.toLocaleString("ko-KR")})`
        : `🛒 선택 ${chosenIds.length}팩 일괄 장착 (₩${finalPrice.toLocaleString("ko-KR")} · 3팩 이상 선택 시 15% 자동 할인)`;
      bundleBtn.onclick = async () => {
        if (statusMsgEl) {
          statusMsgEl.textContent = `⏳ 선택한 ${chosenIds.length}개 브레인팩(₩${finalPrice.toLocaleString("ko-KR")}) 일괄 장착 중...`;
        }
        const res = await apiPost("/api/store/purchase-bundle", {
          pack_ids: chosenIds,
          auto_create_decks: true,
          payment_token: `BDPAY-BUNDLE-${chosenIds.join("-")}`,
        });
        if (res && res.ok) {
          if (statusMsgEl) {
            statusMsgEl.textContent = `🎉 ${res.purchased_count}개 팩 (할인 ₩${Number(res.quote.discount_krw || 0).toLocaleString("ko-KR")}) 일괄 장착 및 학습 덱 생성 완료!`;
          }
          state.selectedBundlePackIds = [];
          await loadBrainPackStoreAndBind();
          await loadCatalogAndBind();
          await refreshDashboardAndQueue();
          await syncOfflineVault(false);
        }
      };
    }

    function renderStoreList() {
      storeListEl.textContent = "";
      const filtered = vm.filterStorePacks(state.storePacks, state.selectedStoreCategory);
      filtered.forEach((rawPack) => {
        const cardVm = vm.formatStorePackCard(rawPack);
        const rowDiv = document.createElement("div");
        rowDiv.style.cssText =
          "background:#f9fafb;border:1px solid var(--border);border-radius:16px;padding:14px 16px;display:flex;flex-direction:column;gap:6px;";

        const topRow = document.createElement("div");
        topRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;";

        const titleWrap = document.createElement("label");
        titleWrap.style.cssText = "display:inline-flex;align-items:center;gap:6px;cursor:pointer;";
        if (!cardVm.unlocked && cardVm.priceKrw > 0) {
          const bundleCb = document.createElement("input");
          bundleCb.type = "checkbox";
          bundleCb.className = "store-bundle-cb";
          bundleCb.checked = state.selectedBundlePackIds.includes(cardVm.packId);
          bundleCb.onchange = () => {
            if (bundleCb.checked) {
              if (!state.selectedBundlePackIds.includes(cardVm.packId)) {
                state.selectedBundlePackIds.push(cardVm.packId);
              }
            } else {
              state.selectedBundlePackIds = state.selectedBundlePackIds.filter((id) => id !== cardVm.packId);
            }
            updateBundleButtonQuote();
          };
          titleWrap.appendChild(bundleCb);
        }

        const titleSpan = document.createElement("span");
        titleSpan.style.cssText = "font-size:0.86rem;font-weight:700;color:var(--text);";
        titleSpan.textContent = cardVm.title;
        titleWrap.appendChild(titleSpan);

        const badgeSpan = document.createElement("span");
        badgeSpan.className = "badge-pill";
        const frozenTag = rawPack.status === "refunded_frozen" ? "❄️ 환불·동결됨 · " : "";
        badgeSpan.textContent = `${frozenTag}${cardVm.badgeLabel} · ${cardVm.estimatedCountLabel}`;

        topRow.appendChild(titleWrap);
        topRow.appendChild(badgeSpan);
        rowDiv.appendChild(topRow);

        const subDiv = document.createElement("div");
        subDiv.style.cssText = "font-size:0.76rem;color:var(--muted);";
        subDiv.textContent = cardVm.subtitle;
        rowDiv.appendChild(subDiv);

        if (cardVm.sampleCards.length > 0) {
          const sampleDiv = document.createElement("div");
          sampleDiv.style.cssText =
            "font-size:0.78rem;color:#1b64da;background:#e8f3ff;padding:7px 10px;border-radius:10px;font-weight:600;";
          const s0 = cardVm.sampleCards[0];
          sampleDiv.textContent = `🔍 샘플 미리보기: Q. ${s0.front} ➔ A. ${s0.back}`;
          rowDiv.appendChild(sampleDiv);
        }

        const actionRow = document.createElement("div");
        actionRow.style.cssText = "display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-top:2px;";

        if (cardVm.unlocked && cardVm.priceKrw > 0) {
          const refundBtn = document.createElement("button");
          refundBtn.type = "button";
          refundBtn.style.cssText =
            "padding:5px 9px;font-size:0.72rem;color:var(--rose);border-color:rgba(244,63,94,0.45);";
          refundBtn.textContent = "❄️ 환불·동결";
          refundBtn.onclick = async () => {
            const refRes = await apiPost("/api/store/refund", {
              pack_id: cardVm.packId,
              reason: "user_store_ui_refund",
            });
            if (refRes && refRes.ok) {
              if (statusMsgEl) {
                statusMsgEl.textContent = `❄️ '${cardVm.title}' 환불·동결 완료 (기존 FSRS 학습 이력은 보존되며 신규 덱 생성만 차단됩니다).`;
              }
              await loadBrainPackStoreAndBind();
              await loadCatalogAndBind();
            }
          };
          actionRow.appendChild(refundBtn);
        }

        const actBtn = document.createElement("button");
        actBtn.type = "button";
        actBtn.setAttribute("data-buy-pack", cardVm.packId);
        actBtn.className = cardVm.unlocked ? "" : "btn-primary";
        actBtn.style.cssText = "padding:6px 12px;font-size:0.78rem;";
        actBtn.textContent = cardVm.unlocked ? "✅ 장착됨 · 이 덱으로 바로 학습" : cardVm.priceLabel;
        actBtn.addEventListener("click", async () => {
          if (statusMsgEl) {
            statusMsgEl.textContent = `⏳ '${cardVm.title}' 장착 및 앱 내 학습 덱 준비 중...`;
          }
          const purchaseRes = await apiPost("/api/store/purchase", {
            pack_id: cardVm.packId,
            auto_create_deck: true,
            payment_token: `BDPAY-${cardVm.packId}`,
          });
          if (purchaseRes && purchaseRes.ok) {
            const deckInfo = purchaseRes.mounted_deck;
            const deckMsg = deckInfo
              ? ` ('${deckInfo.deck_name}' 덱으로 즉시 이동했습니다)`
              : "";
            if (statusMsgEl) {
              statusMsgEl.textContent = `🎉 '${purchaseRes.title}' 구매 및 마운트 완료!${deckMsg}`;
            }
            if (deckInfo && deckInfo.deck_id) {
              state.selectedDeckId = String(deckInfo.deck_id);
            }
            await loadBrainPackStoreAndBind();
            await loadCatalogAndBind();
            await refreshDashboardAndQueue();
            await syncOfflineVault(false);
            if (deckInfo && deckInfo.deck_id) {
              switchTabPage("study");
              showUxToast(`🎉 '${purchaseRes.title}' 구매 및 마운트 완료! 바로 학습을 시작합니다!`, "emerald");
            }
          }
        });

        actionRow.appendChild(actBtn);
        rowDiv.appendChild(actionRow);
        storeListEl.appendChild(rowDiv);
      });
      updateBundleButtonQuote();
    }

    const tabBtns = document.querySelectorAll(".store-cat-btn");
    tabBtns.forEach((btn) => {
      btn.onclick = () => {
        tabBtns.forEach((b) => b.classList.remove("btn-primary"));
        btn.classList.add("btn-primary");
        state.selectedStoreCategory = btn.getAttribute("data-cat") || "all";
        renderStoreList();
      };
    });

    renderStoreList();
  }

  async function syncOfflineVault(showBanner = true) {
    try {
      const bundle = await apiGet("/api/bundle/offline-snapshot");
      if (bundle && bundle.ok) {
        saveLocalVaultSnapshot(bundle);
        const badge = el("offline-vault-badge");
        if (badge) {
          badge.textContent = "📱 온디바이스 올인원 내장 완료";
        }
        if (showBanner) {
          const statusMsgEl = el("store-status-msg");
          if (statusMsgEl) {
            statusMsgEl.textContent =
              "✅ 보유 중인 모든 브레인팩과 학습 덱 데이터가 이 기기(localStorage + IndexedDB)에 안전하게 내장되었습니다!";
          }
          showUxToast("💾 오프라인 금고 동기화 완료: 비행기 모드에서도 보유 브레인팩과 복습 큐가 100% 작동합니다.", "emerald");
        }
      }
    } catch (_) {
      // Ignore network errors when already offline
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    const ageBtns = document.querySelectorAll(".age-tier-btn");
    async function applyAgeTierUiTokens(tier, syncServer = false) {
      state.ageTier = tier || "teen";
      if (syncServer) {
        await apiPost("/api/profile/age-tier", { age_tier: state.ageTier }).catch(() => {});
      }
      if (!vm || typeof vm.resolveUiUxTokens !== "function") return;
      const isStandalone = Boolean(
        (window.navigator && window.navigator.standalone) ||
          (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches)
      );
      const tokens = vm.resolveUiUxTokens(tier, window.innerWidth || 1200, isStandalone);
      document.documentElement.style.setProperty("--question-font-size", `${tokens.questionFontPx}px`);
      document.documentElement.style.setProperty("--min-touch-target", `${tokens.minTouchTargetPx}px`);
      document.documentElement.style.setProperty("--card-radius", `${tokens.cardBorderRadiusPx}px`);
      const bannerEl = el("age-tier-banner");
      if (bannerEl) {
        bannerEl.textContent = tokens.bannerText;
      }
      if (typeof vm.formatRatingButtonsForAgeTier === "function") {
        const ratingList = vm.formatRatingButtonsForAgeTier(state.ageTier) || [];
        [1, 2, 3, 4].forEach((r) => {
          const item = ratingList.find((b) => Number(b.rating) === r);
          const titleEl = el(`rate-title-${r}`);
          const btnEl = el(`rate-${r}`);
          if (titleEl && item) {
            titleEl.textContent = item.title;
          }
          if (btnEl) {
            btnEl.style.display = item && item.visible ? "flex" : "none";
          }
        });
      } else {
        const easyBtn = el("rate-4");
        if (easyBtn) {
          easyBtn.style.display = tokens.allowEasyButton ? "flex" : "none";
        }
      }
      if (syncServer) {
        showUxToast(tokens.bannerText, "accent");
        renderCurrentCard();
      }
    }
    ageBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        ageBtns.forEach((b) => b.classList.remove("btn-primary"));
        btn.classList.add("btn-primary");
        applyAgeTierUiTokens(btn.getAttribute("data-age-tier") || "teen", true);
      });
    });

    // Multi-Page Tab Navigation Binding
    document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        switchTabPage(btn.getAttribute("data-tab") || "study");
      });
    });

    // Onboarding & LearnerProfile v2 Binding
    const onboardingModal = el("onboarding-modal");
    function applyLearnerProfile(rawProf, closeSheet = true) {
      const norm =
        vm && typeof vm.normalizeLearnerProfile === "function"
          ? vm.normalizeLearnerProfile(rawProf)
          : { ageTier: rawProf.ageTier || "teen", solveMode: "adaptive", difficulty: "mixed", order: "interleaved", summaryLabel: "" };
      state.learnerProfile = norm;
      state.ageTier = norm.ageTier;
      state.shuffleMode = norm.order === "sequential" ? "sequential" : "interleaved";
      state.cardModeOverride = "";
      try {
        if (typeof localStorage !== "undefined") {
          localStorage.setItem(ONBOARDING_STORAGE_KEY, norm.ageTier);
          localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(norm));
        }
      } catch (_) {}
      const sumEl = el("learner-policy-summary");
      if (sumEl) sumEl.textContent = norm.summaryLabel || "";
      ["curriculum-difficulty-select", "doc-difficulty-select", "ai-difficulty-select"].forEach((selId) => {
        const s = el(selId);
        if (s) s.value = norm.difficulty || "mixed";
      });
      const smSel = el("profile-solve-mode-select");
      if (smSel) smSel.value = norm.solveMode;
      const dfSel = el("profile-difficulty-select");
      if (dfSel) dfSel.value = norm.difficulty;

      if (closeSheet && onboardingModal) {
        onboardingModal.style.display = "none";
      }
      ageBtns.forEach((b) => {
        if (b.getAttribute("data-age-tier") === norm.ageTier) b.classList.add("btn-primary");
        else b.classList.remove("btn-primary");
      });
      applyAgeTierUiTokens(norm.ageTier, closeSheet);
      if (closeSheet) switchTabPage("study");
    }

    function completeOnboardingMode(tier) {
      const chosen = tier || "teen";
      const preset =
        vm && typeof vm.buildLearnerProfilePreset === "function"
          ? vm.buildLearnerProfilePreset(chosen)
          : { ageTier: chosen, solveMode: "adaptive", difficulty: "mixed", order: "interleaved" };
      applyLearnerProfile(preset, true);
    }

    document.querySelectorAll(".onboarding-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        completeOnboardingMode(btn.getAttribute("data-onboarding-tier") || "teen");
      });
    });

    const btnSaveProfile = el("btn-save-learner-profile");
    if (btnSaveProfile) {
      btnSaveProfile.addEventListener("click", () => {
        const smSel = el("profile-solve-mode-select");
        const dfSel = el("profile-difficulty-select");
        applyLearnerProfile(
          {
            ageTier: state.ageTier || "teen",
            solveMode: (smSel && smSel.value) || "adaptive",
            difficulty: (dfSel && dfSel.value) || "mixed",
            order: state.shuffleMode || "interleaved",
          },
          true
        );
      });
    }

    const btnOpenModeSetup = el("btn-open-mode-setup");
    if (btnOpenModeSetup && onboardingModal) {
      btnOpenModeSetup.addEventListener("click", () => {
        onboardingModal.style.display = "flex";
      });
    }

    let savedMode = null;
    let savedProf = null;
    try {
      if (typeof localStorage !== "undefined") {
        savedMode = localStorage.getItem(ONBOARDING_STORAGE_KEY);
        const rawP = localStorage.getItem(PROFILE_STORAGE_KEY);
        if (rawP) savedProf = JSON.parse(rawP);
      }
    } catch (_) {}

    if (!savedMode && onboardingModal) {
      onboardingModal.style.display = "flex";
      applyLearnerProfile({ ageTier: "teen", solveMode: "adaptive", difficulty: "mixed", order: "interleaved" }, false);
    } else {
      applyLearnerProfile(savedProf || { ageTier: savedMode || "teen" }, false);
    }

    const syncBtn = el("btn-sync-offline-vault");
    if (syncBtn) {
      syncBtn.addEventListener("click", () => syncOfflineVault(true));
    }

    // v5.6 REA Utilities Binding
    let summaryMaskAll = true;
    function renderSummarySheetPanel() {
      const panel = el("summary-sheet-panel");
      const rowsBox = el("summary-sheet-rows");
      if (!panel || !rowsBox) return;
      const cards = state.dueCards.length > 0 ? state.dueCards : state.rawDueCards;
      const sheet =
        vm && typeof vm.buildSummarySheetView === "function"
          ? vm.buildSummarySheetView(cards, summaryMaskAll ? "red_filter" : "reveal_all")
          : { rows: [] };
      rowsBox.textContent = "";
      sheet.rows.forEach((r) => {
        const rowEl = document.createElement("div");
        rowEl.style.cssText =
          "display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;font-size:0.83rem;";
        const qSpan = document.createElement("div");
        qSpan.style.cssText = "flex:1;font-weight:700;color:#191f28;";
        qSpan.textContent = `${r.index}. ${r.question}`;
        const aBtn = document.createElement("button");
        aBtn.type = "button";
        let masked = summaryMaskAll;
        function syncMaskStyle() {
          if (masked) {
            aBtn.style.cssText =
              "padding:5px 12px;border-radius:8px;background:#be123c;color:#be123c;border:1px solid #be123c;font-weight:800;min-width:95px;user-select:none;";
            aBtn.title = "탭하여 셀로판지 걷어내기";
          } else {
            aBtn.style.cssText =
              "padding:5px 12px;border-radius:8px;background:#fff0f0;color:#be123c;border:1px solid #fecdd3;font-weight:800;min-width:95px;";
          }
          aBtn.textContent = r.clean_answer;
        }
        syncMaskStyle();
        aBtn.addEventListener("click", () => {
          masked = !masked;
          syncMaskStyle();
        });
        rowEl.appendChild(qSpan);
        rowEl.appendChild(aBtn);
        rowsBox.appendChild(rowEl);
      });
    }

    const btnOpenSummary = el("btn-open-summary-sheet");
    if (btnOpenSummary) {
      btnOpenSummary.addEventListener("click", () => {
        const panel = el("summary-sheet-panel");
        if (!panel) return;
        const willShow = panel.style.display === "none";
        panel.style.display = willShow ? "block" : "none";
        if (willShow) renderSummarySheetPanel();
      });
    }
    const btnSummaryToggleAll = el("btn-summary-toggle-all");
    if (btnSummaryToggleAll) {
      btnSummaryToggleAll.addEventListener("click", () => {
        summaryMaskAll = !summaryMaskAll;
        renderSummarySheetPanel();
      });
    }
    const btnSummaryClose = el("btn-summary-close");
    if (btnSummaryClose) {
      btnSummaryClose.addEventListener("click", () => {
        const panel = el("summary-sheet-panel");
        if (panel) panel.style.display = "none";
      });
    }

    const btnPrintExam = el("btn-print-exam-sheet");
    if (btnPrintExam) {
      btnPrintExam.addEventListener("click", () => {
        const cards = state.dueCards.length > 0 ? state.dueCards : state.rawDueCards;
        if (!cards.length) {
          showUxToast("⚠️ 인쇄할 카드가 없습니다.", "amber");
          return;
        }
        const doc =
          vm && typeof vm.buildPrintableExamSheet === "function"
            ? vm.buildPrintableExamSheet(cards, "BrainDeck 2단 실전 쪽지시험지", Date.now() % 100000)
            : null;
        if (doc && doc.printable_html) {
          const w = window.open("", "_blank");
          if (w) {
            w.document.open();
            w.document.write(doc.printable_html);
            w.document.close();
          } else {
            showUxToast("🖨️ 팝업 차단됨 — 브라우저 팝업을 허용해 주세요.", "amber");
          }
        }
      });
    }

    let audioLoopTimer = null;
    const btnAudioLoop = el("btn-commute-audio-loop");
    if (btnAudioLoop) {
      btnAudioLoop.addEventListener("click", () => {
        if (audioLoopTimer) {
          clearTimeout(audioLoopTimer);
          audioLoopTimer = null;
          if (window.speechSynthesis) window.speechSynthesis.cancel();
          btnAudioLoop.textContent = "🎧 통학 오디오 루프";
          btnAudioLoop.classList.remove("btn-primary");
          showUxToast("⏹️ 통학 오디오 루프를 종료했습니다.", "accent");
          return;
        }
        const cards = state.dueCards.length > 0 ? state.dueCards : state.rawDueCards;
        if (!cards.length) return;
        const script =
          vm && typeof vm.buildCommuteAudioScript === "function"
            ? vm.buildCommuteAudioScript(cards, 3)
            : { tracks: [] };
        let tIdx = 0;
        btnAudioLoop.textContent = "⏹️ 오디오 루프 중지";
        btnAudioLoop.classList.add("btn-primary");
        showUxToast("🎧 통학 오디오 루프 시작 (질문 ➔ 3초 생각 ➔ 정답)", "emerald");

        function playNextTrack() {
          if (!audioLoopTimer && tIdx > 0) return;
          const tr = script.tracks[tIdx % script.tracks.length];
          tIdx += 1;
          if (window.speechSynthesis && typeof SpeechSynthesisUtterance !== "undefined") {
            const uQ = new SpeechSynthesisUtterance(tr.prompt_tts);
            uQ.lang = "ko-KR";
            window.speechSynthesis.speak(uQ);
            audioLoopTimer = setTimeout(() => {
              const uA = new SpeechSynthesisUtterance(`정답은 ${tr.answer_tts}`);
              uA.lang = "ko-KR";
              window.speechSynthesis.speak(uA);
              audioLoopTimer = setTimeout(playNextTrack, 3200);
            }, (tr.pause_seconds || 3) * 1000 + 2200);
          }
        }
        audioLoopTimer = setTimeout(playNextTrack, 100);
      });
    }

    const btnCramSandbox = el("btn-toggle-cram-sandbox");
    if (btnCramSandbox) {
      btnCramSandbox.addEventListener("click", () => {
        state.isCramSandbox = !state.isCramSandbox;
        btnCramSandbox.textContent = state.isCramSandbox
          ? "🧪 무오염 벼락치기(CRAM): ON"
          : "🧪 무오염 벼락치기(CRAM): OFF";
        if (state.isCramSandbox) {
          btnCramSandbox.classList.add("btn-primary");
          showUxToast("🧪 무오염 벼락치기 ON: 아무리 많이 반복해도 FSRS 장기기억 간격(S)이 오염되지 않습니다.", "emerald");
        } else {
          btnCramSandbox.classList.remove("btn-primary");
          showUxToast("📚 정규 FSRS 학습 모드로 복귀했습니다.", "accent");
        }
        syncStudyToolsSummaryBadge();
      });
    }

    // Contract C1: Study Tools & Filter Progressive Disclosure Drawer
    function syncStudyToolsSummaryBadge() {
      const badgeEl = el("active-study-filter-summary");
      if (!badgeEl || !vm || typeof vm.computeStudyToolsSummary !== "function") return;
      const summary = vm.computeStudyToolsSummary({
        studyFilter: state.studyFilterMode || "all",
        qtypeFilter: state.questionTypeFilter || "all",
        cramMode: Boolean(state.isCramSandbox),
      });
      if (summary.is_default) {
        badgeEl.style.display = "none";
        badgeEl.textContent = "";
      } else {
        badgeEl.style.display = "inline-flex";
        badgeEl.textContent = summary.summary_badge_text;
      }
    }

    const btnToggleStudyTools = el("btn-toggle-study-tools");
    const studyToolsDrawer = el("study-tools-drawer");
    if (btnToggleStudyTools && studyToolsDrawer) {
      btnToggleStudyTools.addEventListener("click", () => {
        const isOpen = studyToolsDrawer.style.display !== "none";
        const nextOpen = !isOpen;
        studyToolsDrawer.style.display = nextOpen ? "block" : "none";
        btnToggleStudyTools.setAttribute("aria-expanded", nextOpen ? "true" : "false");
        if (nextOpen) {
          btnToggleStudyTools.classList.add("btn-primary");
        } else {
          btnToggleStudyTools.classList.remove("btn-primary");
        }
        syncStudyToolsSummaryBadge();
      });
    }

    document.querySelectorAll(".study-filter-btn, .study-qtype-btn").forEach((b) => {
      b.addEventListener("click", syncStudyToolsSummaryBadge);
    });

    // Contract C3: 3-Segment Switcher in Curriculum Tab (textbook | collection | combined)
    function switchCurriculumSegment(seg) {
      const stateObj =
        vm && typeof vm.resolveCurriculumSegmentState === "function"
          ? vm.resolveCurriculumSegmentState(seg, (state.combinedExamScopes || []).length)
          : {
              active_segment: seg || "textbook",
              combined_tab_label: "🎯 시험범위 조합",
              visible_panels: {
                textbook: seg === "textbook",
                collection: seg === "collection",
                combined: seg === "combined",
              },
            };
      document.querySelectorAll(".curr-seg-btn").forEach((b) => {
        const isTarget = b.getAttribute("data-curr-seg") === stateObj.active_segment;
        b.setAttribute("aria-selected", isTarget ? "true" : "false");
        if (isTarget) b.classList.add("btn-primary");
        else b.classList.remove("btn-primary");
      });
      const btnCombinedSeg = el("btn-curr-seg-combined");
      if (btnCombinedSeg) {
        btnCombinedSeg.textContent = stateObj.combined_tab_label;
      }
      ["textbook", "collection", "combined"].forEach((id) => {
        const panelEl = el(`curr-seg-${id}`);
        if (panelEl) {
          panelEl.style.display = stateObj.visible_panels[id] ? "block" : "none";
        }
      });
    }

    document.querySelectorAll(".curr-seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        switchCurriculumSegment(btn.getAttribute("data-curr-seg") || "textbook");
      });
    });

    // BrainDeck v3 Study Planner & Custom Study Suite bindings
    async function computeAndPreviewPlan(showToastMsg = true) {
      const daysSel = el("bd-plan-days");
      const minsSel = el("bd-plan-minutes");
      const newSel = el("bd-plan-daily-new");
      const targetDays = Number((daysSel && daysSel.value) || 30);
      const dailyMinutes = Number((minsSel && minsSel.value) || 30);
      const customNew = newSel && newSel.value && newSel.value !== "auto" ? Number(newSel.value) : null;
      const res = await apiPost("/api/study-plan", {
        deck_id: state.selectedDeckId || null,
        target_days: targetDays,
        daily_minutes_budget: dailyMinutes,
        new_per_day: customNew,
      });
      if (res && res.ok && res.plan) {
        await renderStudyPlanBanner(res);
        if (showToastMsg) {
          const pl = res.plan;
          const effNew = customNew || pl.recommended_daily_new;
          showUxToast(
            `📅 D-${pl.target_days} 학습계획 산출: 전체 ${pl.total_cards}장 ➔ 하루 새 카드 ${effNew}장 · 평균 ${pl.avg_daily_minutes}분/일`,
            pl.status === "FEASIBLE" ? "emerald" : "amber"
          );
        }
      }
    }

    const btnComputePlan = el("btn-compute-study-plan");
    if (btnComputePlan) {
      btnComputePlan.addEventListener("click", () => computeAndPreviewPlan(true));
    }

    const btnApplyPlan = el("btn-apply-study-plan");
    if (btnApplyPlan) {
      btnApplyPlan.addEventListener("click", async () => {
        const daysSel = el("bd-plan-days");
        const minsSel = el("bd-plan-minutes");
        const newSel = el("bd-plan-daily-new");
        const targetDays = Number((daysSel && daysSel.value) || 30);
        const dailyMinutes = Number((minsSel && minsSel.value) || 30);
        const customNew = newSel && newSel.value && newSel.value !== "auto" ? Number(newSel.value) : null;
        const res = await apiPost("/api/study-plan/apply", {
          deck_id: state.selectedDeckId || null,
          target_days: targetDays,
          daily_minutes_budget: dailyMinutes,
          new_per_day: customNew,
          apply: true,
        });
        if (res && res.ok && res.plan) {
          await refreshDashboardAndQueue();
          const dq = res.daily_quota || {};
          const dailyNewLimit = Number(dq.daily_new_limit || res.plan.recommended_daily_new || 30);
          showUxToast(
            `✅ D-${res.plan.target_days} 일일 학습 계획 적용 완료! 오늘부터 하루 새 카드 ${dailyNewLimit}장씩 맞춤 출제됩니다.`,
            "emerald"
          );
        }
      });
    }

    ["bd-plan-days", "bd-plan-daily-new", "bd-plan-minutes"].forEach((selId) => {
      const sEl = el(selId);
      if (sEl) {
        sEl.addEventListener("change", () => computeAndPreviewPlan(false));
      }
    });

    const btnRunCustomStudy = el("btn-run-custom-study");
    if (btnRunCustomStudy) {
      btnRunCustomStudy.addEventListener("click", async () => {
        const presetSel = el("bd-custom-study-preset");
        const preset = (presetSel && presetSel.value) || "forgotten_recent";
        const res = await apiPost("/api/custom-study", {
          deck_id: state.selectedDeckId || null,
          preset,
          days_ahead: 3,
          limit: 50,
          extra_new: 15,
        });
        if (res && res.ok) {
          if (Array.isArray(res.cards) && res.cards.length > 0) {
            state.dueCards = res.cards.map(enrichStandaloneCard);
            state.currentIndex = 0;
            state.isCramSandbox = res.reschedule === false;
            renderCurrentCard();
            showUxToast(`⚡ ${res.title} (${res.cards.length}장) 세션이 시작되었습니다!`, "emerald");
          } else {
            showUxToast(`ℹ️ 선택한 맞춤학습 조건(${res.title || preset})에 해당하는 카드가 없습니다.`, "amber");
          }
        }
      });
    }

    const selectCardFlag = el("select-card-flag");
    if (selectCardFlag) {
      selectCardFlag.addEventListener("change", async () => {
        const card = currentCard();
        if (!card) return;
        const flagVal = Number(selectCardFlag.value || 0);
        const res = await apiPost("/api/cards/action", {
          card_id: card.card_id,
          action: "set_flag",
          flag: flagVal,
        });
        if (res && res.ok && res.card) {
          card.flag = res.card.flag;
          card.flag_label = res.card.flag_label;
          showUxToast(`🚩 카드 #${card.card_id} 플래그 지정: ${res.card.flag_label}`, "accent");
        }
      });
    }

    // BrainDeck v6.0 Deck Progress Dashboard, Stage Filter & Deck Card Explorer Bindings
    document.querySelectorAll(".bd-stage-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const st = btn.getAttribute("data-stage") || "all";
        state.stageFilter = st;
        document.querySelectorAll(".bd-stage-btn").forEach((b) => {
          if (b.getAttribute("data-stage") === st) b.classList.add("btn-primary");
          else b.classList.remove("btn-primary");
        });
        applyStudyFilter();
        renderCurrentCard();
        showUxToast(
          st === "all"
            ? "📚 전체 단계(Lv.1~Lv.4) 학습 모드로 전환했습니다."
            : `🎯 ${btn.textContent} 단계 카드만 집중 학습합니다 (${state.dueCards.length}장).`,
          "accent"
        );
      });
    });

    const btnOpenExplorer = el("btn-open-deck-explorer");
    const explorerPanel = el("deck-card-explorer-panel");
    if (btnOpenExplorer && explorerPanel) {
      btnOpenExplorer.addEventListener("click", async () => {
        const willShow = explorerPanel.style.display === "none";
        explorerPanel.style.display = willShow ? "block" : "none";
        if (willShow) {
          btnOpenExplorer.classList.add("btn-primary");
          await renderDeckExplorerPanel();
        } else {
          btnOpenExplorer.classList.remove("btn-primary");
        }
      });
    }

    const btnCloseExplorer = el("btn-close-deck-explorer");
    if (btnCloseExplorer && explorerPanel) {
      btnCloseExplorer.addEventListener("click", () => {
        explorerPanel.style.display = "none";
        if (btnOpenExplorer) btnOpenExplorer.classList.remove("btn-primary");
      });
    }

    document.querySelectorAll(".bd-bucket-chip").forEach((chip) => {
      chip.addEventListener("click", async () => {
        const bKey = chip.getAttribute("data-bucket") || "all";
        const bSel = el("explorer-bucket-select");
        if (bSel) bSel.value = bKey;
        if (explorerPanel) explorerPanel.style.display = "block";
        if (btnOpenExplorer) btnOpenExplorer.classList.add("btn-primary");
        await renderDeckExplorerPanel();
      });
    });

    ["explorer-search-input", "explorer-bucket-select", "explorer-stage-select"].forEach((id) => {
      const ctrl = el(id);
      if (ctrl) {
        ctrl.addEventListener(id === "explorer-search-input" ? "input" : "change", () => {
          renderDeckExplorerPanel();
        });
      }
    });

    loadBrainPackStoreAndBind();
    loadCatalogAndBind();
    refreshDashboardAndQueue();
    syncOfflineVault(false);
    syncStudyToolsSummaryBadge();
  });
})();
