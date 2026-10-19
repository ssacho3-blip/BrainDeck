/**
 * Client Controller for Anki Studio 2.0 (MVVM Binding + Web Speech TTS + AI Recall).
 */
(function () {
  "use strict";

  const vm = window.AnkiStudioViewModel;
  let state = {
    decks: [],
    selectedDeckId: "",
    dueCards: [],
    currentIndex: 0,
    isRevealed: false,
    hintLevel: 0,
  };

  const el = (id) => document.getElementById(id);

  async function apiGet(path) {
    const res = await fetch(path, { cache: "no-store" });
    return res.json();
  }

  async function apiPost(path, payload) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return res.json();
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

  function renderCurrentCard() {
    const card = currentCard();
    state.isRevealed = false;
    state.hintLevel = 0;
    clearRecommendedGlow();

    el("card-answer").style.display = "none";
    el("hint-box").style.display = "none";
    el("eval-box").style.display = "none";
    el("recall-input").value = "";

    if (!card) {
      el("card-meta").textContent = "복습 완료";
      el("card-fsrs-meta").textContent = "Due: 0";
      el("card-question").textContent = "🎉 현재 선택한 덱의 복습 대기 카드를 모두 완료했습니다!";
      el("leech-banner").style.display = "none";
      return;
    }

    el("card-meta").textContent = `${card.deck_name} · #${state.currentIndex + 1}/${state.dueCards.length} (${card.note_type.toUpperCase()})`;
    const rPct = ((Number(card.retrievability) || 1) * 100).toFixed(1);
    el("card-fsrs-meta").textContent = `S: ${Number(card.stability).toFixed(1)}d · D: ${Number(card.difficulty).toFixed(1)} · R: ${rPct}%`;
    el("card-question").textContent = card.rendered_question;
    el("card-answer").textContent = card.rendered_answer;

    const leech = vm.formatLeechBadge(card.leech_status, card.lapses);
    if (leech.visible) {
      el("leech-banner").textContent = leech.label;
      el("leech-banner").style.display = "block";
    } else {
      el("leech-banner").style.display = "none";
    }

    const p = card.button_previews || {};
    el("preview-1").textContent = (p.again && p.again.label) || "10m";
    el("preview-2").textContent = (p.hard && p.hard.label) || "1d";
    el("preview-3").textContent = (p.good && p.good.label) || "3d";
    el("preview-4").textContent = (p.easy && p.easy.label) || "16d";
  }

  async function refreshDashboardAndQueue() {
    const status = await apiGet("/api/status");
    if (status && status.ok) {
      const s = status.stats;
      el("stat-due").textContent = `${s.due_now}장`;
      el("stat-total").textContent = `${s.total_cards}장 / 오늘 ${s.reviews_today}회`;
      const badge = vm.formatRetentionBadge(s.true_retention_pct);
      el("stat-retention").textContent = badge.label;
      el("stat-stability").textContent = `${s.avg_stability_days}일 · Leech ${s.leech_cards}건`;

      const points = vm.buildForgettingCurveSvgPoints(s.forgetting_curve, 480, 120);
      el("curve-polyline").setAttribute("points", points);

      state.decks = status.decks || [];
      const sel = el("deck-select");
      const prevVal = state.selectedDeckId;
      sel.innerHTML = `<option value="">전체 덱 (${s.due_now}장 대기)</option>`;
      state.decks.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = String(d.deck_id);
        opt.textContent = `${d.name} (${d.due_cards}/${d.total_cards})`;
        sel.appendChild(opt);
      });
      sel.value = prevVal;
    }

    const q = state.selectedDeckId ? `?deck_id=${encodeURIComponent(state.selectedDeckId)}` : "";
    const dueRes = await apiGet(`/api/due${q}`);
    state.dueCards = (dueRes && dueRes.cards) || [];
    state.currentIndex = 0;
    renderCurrentCard();
  }

  function revealAnswer() {
    const card = currentCard();
    if (!card) return;
    state.isRevealed = true;
    el("card-answer").style.display = "block";
  }

  async function submitRating(rating) {
    const card = currentCard();
    if (!card) return;
    await apiPost("/api/review", { card_id: card.card_id, rating: Number(rating) });
    await refreshDashboardAndQueue();
  }

  async function requestSocraticHint() {
    const card = currentCard();
    if (!card) return;
    state.hintLevel = Math.min(2, state.hintLevel + 1);
    const res = await apiPost("/api/ai/hint", {
      question_text: card.rendered_question,
      target_answer: card.rendered_answer,
      lapses: card.lapses || 0,
      level: state.hintLevel,
    });
    if (res && res.ok) {
      const box = el("hint-box");
      box.textContent = `🧭 [단계 ${res.level}] ${res.structural_cue}\n❓ 소크라테스 질문: ${res.socratic_question}\n${res.mnemonic_tip}`;
      box.style.display = "block";
    }
  }

  async function evaluateFreeRecall() {
    const card = currentCard();
    if (!card) return;
    const ans = el("recall-input").value.trim();
    const res = await apiPost("/api/ai/evaluate", {
      user_answer: ans,
      expected_answer: card.rendered_answer,
      question_text: card.rendered_question,
    });
    if (res && res.ok) {
      revealAnswer();
      clearRecommendedGlow();
      const recBtn = el(`rate-${res.recommended_rating}`);
      if (recBtn) recBtn.classList.add("recommended-glow");
      const box = el("eval-box");
      box.textContent = `🎯 AI 인출 정확도: ${res.score_pct}% (추천 등급: ${res.recommended_label})\n${res.feedback}`;
      box.style.display = "block";
    }
  }

  async function decomposeCurrentLeech() {
    const card = currentCard();
    if (!card) return;
    const res = await apiPost("/api/ai/decompose-leech", {
      front_text: card.front_text,
      back_text: card.back_text,
      deck_id: card.deck_id,
      auto_save: true,
    });
    if (res && res.ok) {
      const box = el("hint-box");
      box.textContent = `🧬 [AI Leech 원자 분할 완료] 복합 카드를 ${res.cards.length}개의 단일 개념 마이크로 카드로 쪼개어 현재 덱에 추가했습니다!`;
      box.style.display = "block";
      await refreshDashboardAndQueue();
    }
  }

  function speakCurrentCard() {
    const card = currentCard();
    if (!card || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const textToSpeak = state.isRevealed ? card.rendered_answer : card.rendered_question;
    const cleanText = textToSpeak.replace(/[【】\[\]]/g, " ");
    const utter = new SpeechSynthesisUtterance(cleanText);
    const hasKorean = /[가-힣]/.test(cleanText);
    utter.lang = hasKorean ? "ko-KR" : "en-US";
    utter.rate = 0.96;
    window.speechSynthesis.speak(utter);
  }

  function bindEvents() {
    el("deck-select").addEventListener("change", (e) => {
      state.selectedDeckId = e.target.value;
      refreshDashboardAndQueue();
    });

    el("btn-reveal").addEventListener("click", revealAnswer);
    el("btn-hint").addEventListener("click", requestSocraticHint);
    el("btn-decompose").addEventListener("click", decomposeCurrentLeech);
    el("btn-tts").addEventListener("click", speakCurrentCard);
    el("btn-eval").addEventListener("click", evaluateFreeRecall);

    el("recall-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        evaluateFreeRecall();
      }
    });

    [1, 2, 3, 4].forEach((r) => {
      el(`rate-${r}`).addEventListener("click", () => submitRating(r));
    });

    el("btn-generate-cards").addEventListener("click", async () => {
      const rawText = el("ai-raw-text").value.trim();
      if (!rawText) return;
      const mode = el("ai-domain-mode").value;
      const targetDeck = state.selectedDeckId ? Number(state.selectedDeckId) : null;
      el("ai-gen-status").textContent = "AI 카드 생성 중...";
      const res = await apiPost("/api/ai/generate-cards", {
        raw_text: rawText,
        domain_mode: mode,
        deck_id: targetDeck,
        auto_save: true,
      });
      if (res && res.ok) {
        el("ai-gen-status").textContent = `✅ ${res.generated_count}장의 스마트 카드 생성 및 저장 완료! (${res.engine})`;
        el("ai-raw-text").value = "";
        await refreshDashboardAndQueue();
      }
    });

    el("btn-decompress").addEventListener("click", async () => {
      const targetDeck = state.selectedDeckId ? Number(state.selectedDeckId) : null;
      const res = await apiPost("/api/backlog/decompress", {
        deck_id: targetDeck,
        daily_cap: 25,
        horizon_days: 7,
      });
      if (res && res.ok) {
        alert(
          `🏖️ 복습 폭탄 평탄화 완료!\n• 평가된 대기 카드: ${res.total_due_evaluated}장\n• 오늘 최우선 유지(저-R 위험군): ${res.kept_today}장\n• 향후 ${res.horizon_days}일로 안전 분산: ${res.deferred_across_days}장`
        );
        await refreshDashboardAndQueue();
      }
    });

    window.addEventListener("keydown", (e) => {
      const activeTag = (document.activeElement && document.activeElement.tagName) || "";
      const isTyping = activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT";
      const cmd = vm.mapKeyboardShortcut(e.key, state.isRevealed, isTyping);
      if (!cmd) return;
      e.preventDefault();
      if (cmd.action === "reveal") revealAnswer();
      else if (cmd.action === "rate") submitRating(cmd.rating);
      else if (cmd.action === "hint") requestSocraticHint();
      else if (cmd.action === "tts") speakCurrentCard();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    refreshDashboardAndQueue();
  });
})();
