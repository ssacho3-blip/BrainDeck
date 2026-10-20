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
      parent_card_id: card.card_id,
      auto_save: true,
    });
    if (res && res.ok) {
      const box = el("hint-box");
      const suspendedLabel = res.parent_suspended ? " (원본 복합 카드 자동 정지)" : "";
      box.textContent = `🧬 [AI Leech 원자 분할 완료] 복합 카드를 ${res.cards.length}개의 단일 개념 마이크로 카드로 쪼개어 현재 덱에 추가했습니다!${suspendedLabel}`;
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
        const providerBadge = res.provider === "llm" ? `🤖 LLM 생성 (${res.engine})` : `⚡ 결정론적 NLP 추출 (${res.fallback_reason || "zero-quota"})`;
        el("ai-gen-status").textContent = `✅ ${res.generated_count}장 생성 및 저장 완료! [${providerBadge} · ${res.latency_ms}ms]`;
        el("ai-raw-text").value = "";
        await refreshDashboardAndQueue();
      }
    });

    // Photo & PDF Auto-Deck Builder events
    const dropzone = el("doc-dropzone");
    const fileInput = el("doc-file-input");

    async function handleDocumentFile(file) {
      if (!file) return;
      const banner = el("doc-ingest-banner");
      const previewContainer = el("doc-preview-container");
      banner.style.display = "block";
      banner.style.borderColor = "var(--accent)";
      banner.style.color = "var(--text)";
      banner.textContent = `⏳ '${file.name}' (${(file.size / 1024).toFixed(1)}KB) OCR 및 구조 분석 중...`;
      previewContainer.style.display = "none";

      const deckName = el("doc-deck-name").value.trim();
      const autoSave = el("doc-auto-save").checked ? "1" : "0";
      const params = new URLSearchParams({ auto_save: autoSave, max_cards: "30" });
      if (deckName) params.set("deck_name", deckName);

      const mime = file.type || (file.name.toLowerCase().endsWith(".pdf") ? "application/pdf" : "image/png");
      const buf = await file.arrayBuffer();
      const resp = await fetch(`/api/ai/ingest-document?${params.toString()}`, {
        method: "POST",
        headers: { "Content-Type": mime },
        body: buf,
      });
      const res = await resp.json();
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
              "background:rgba(15,23,42,0.85);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:0.8rem;display:flex;flex-direction:column;gap:5px;";

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

  async function loadCatalogAndBind() {
    const cat = await apiGet("/api/catalog");
    if (!cat || !cat.ok) return;
    state.catalog = cat;

    const tbSel = el("catalog-textbook-select");
    const unitsBox = el("catalog-units-box");
    const colSel = el("catalog-collection-select");
    if (!tbSel || !unitsBox || !colSel) return;

    tbSel.textContent = "";
    (cat.textbooks || []).forEach((tb) => {
      const opt = document.createElement("option");
      opt.value = tb.textbook_id;
      opt.textContent = `${tb.title} (${tb.publisher_name} · ${tb.curriculum_revision} 개정)`;
      tbSel.appendChild(opt);
    });

    function renderUnitsForSelectedTextbook() {
      unitsBox.textContent = "";
      const tb = (cat.textbooks || []).find((t) => t.textbook_id === tbSel.value);
      if (!tb || !tb.units) return;
      tb.units.forEach((u, idx) => {
        const lbl = document.createElement("label");
        lbl.style.cssText =
          "display:inline-flex;align-items:center;gap:4px;font-size:0.76rem;padding:4px 8px;border-radius:6px;background:rgba(30,41,59,0.9);border:1px solid var(--border);cursor:pointer;";
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

    tbSel.addEventListener("change", renderUnitsForSelectedTextbook);
    renderUnitsForSelectedTextbook();

    colSel.textContent = "";
    (cat.collections || []).forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.collection_id;
      opt.textContent = `${c.level_label} (${c.item_count}문항 · ${c.collection_id})`;
      colSel.appendChild(opt);
    });

    const btnExam = el("btn-gen-exam-scope");
    if (btnExam) {
      btnExam.addEventListener("click", async () => {
        const checked = Array.from(document.querySelectorAll(".exam-unit-cb:checked")).map((n) => n.value);
        if (!checked.length) return;
        const pStart = el("exam-page-start").value.trim();
        const pEnd = el("exam-page-end").value.trim();
        el("catalog-status-msg").textContent = "⏳ 선택한 시험범위 암기 카드를 생성 중입니다...";
        const res = await apiPost("/api/catalog/generate-exam-scope-deck", {
          textbook_id: tbSel.value,
          unit_ids: checked,
          page_start: pStart ? Number(pStart) : null,
          page_end: pEnd ? Number(pEnd) : null,
        });
        if (res && res.ok) {
          el("catalog-status-msg").textContent = `✅ '${res.deck_name}' (${res.saved_count}장) 생성 완료!`;
          state.selectedDeckId = String(res.deck_id);
          await refreshDashboardAndQueue();
        }
      });
    }

    const btnCol = el("btn-gen-collection");
    if (btnCol) {
      btnCol.addEventListener("click", async () => {
        if (!colSel.value) return;
        el("catalog-status-msg").textContent = "⏳ 급수·시험 암기 카드를 생성 중입니다...";
        const res = await apiPost("/api/catalog/generate-collection-deck", {
          collection_id: colSel.value,
          limit: 30,
        });
        if (res && res.ok) {
          el("catalog-status-msg").textContent = `✅ '${res.deck_name}' (${res.saved_count}장) 생성 완료!`;
          state.selectedDeckId = String(res.deck_id);
          await refreshDashboardAndQueue();
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadCatalogAndBind();
    refreshDashboardAndQueue();
  });
})();
