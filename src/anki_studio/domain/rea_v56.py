"""BrainDeck v5.6 Pure Domain Engine (WORKORDER-BRAINDECK-V56).

Implements the 4-Model (Gemini · Claude Opus 5.5 · Codex GPT-6.1 Sol · Grok 4.7)
REA (Reverse Engineering Analysis & Resource-Event-Agent) Master Specification:
- Phase 1: ReviewEvent Append-Only Fold (`1e-6` quantized), CRAM vs REVIEW_AHEAD,
           Exam Countdown Autopilot (`plan_exam`), & FSRS Load Balancer (`balance_due`)
- Phase 2: 1 Note -> N Facet Cards (`generate_note_facets`, `diff_facets` delayed GC),
           OCR Bounding Box Auto Image Occlusion (`build_image_occlusion_cards`),
           Incremental Reading Lineage & Context Breadcrumb (`build_context_breadcrumb`)
- Phase 3: Directional Confusion Graph (`ConfusableEdge`, `interleave_contrastive`),
           Prerequisite DAG (`find_cycles` Tarjan SCC, `check_prereq_gate`),
           Keyword Rubric Scoring (`RubricSpec`, `score_rubric`),
           7-Card Micro-Sprints & 60s 4x3 Matching Board
- Phase 4: Electronic Red-Cellophane Summary Sheet, 2-Column Printable Exam Worksheet
           & Answer Key Generator, Commute Hands-Free Audio Loop, QR Scope Snapshot,
           Parent Completion Report, & Streak Shield Evaluator.

Zero-I/O Invariant: This module has zero external I/O, DB, or network dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import html
import json
import math
import re
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Set, Tuple

from anki_studio.domain.ai_learning import extract_clean_target_answer


# ============================================================================
# PHASE 1: CORE LEDGER & SCHEDULE
# ============================================================================

DAY_MS = 86_400_000


def quantize_1e6(val: float) -> float:
    """Quantize floating-point values to 1e-6 precision for 3-platform (Py/JS/Kotlin) parity (T35)."""
    if not math.isfinite(val):
        raise ValueError(f"Non-finite float encountered in quantize_1e6: {val}")
    return round(round(float(val) * 1_000_000.0) / 1_000_000.0, 6)


@dataclass(frozen=True)
class ReviewEvent:
    event_id: str
    card_id: str
    kind: Literal["REVIEW", "REVIEW_AHEAD", "CRAM", "VOID"]
    rating: Optional[int]
    ts_ms: int
    device_id: str
    idem_key: str
    voids: Optional[str] = None


@dataclass(frozen=True)
class CardStateV56:
    s: float
    d: float
    due_ms: int
    last_ts_ms: Optional[int]
    reps: int
    lapses: int


# Standard FSRS-5 19-parameter default tuple shared across Python, JS, and Kotlin
DEFAULT_FSRS5_PARAMS: Tuple[float, ...] = (
    0.40255,
    1.18385,
    3.17300,
    15.69105,
    7.19490,
    0.53450,
    1.46040,
    0.00460,
    1.54575,
    0.11920,
    1.01925,
    1.93950,
    0.11000,
    0.29605,
    2.26980,
    0.23150,
    2.98980,
    0.51655,
    0.66210,
)


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def fold_review_events(
    events: Sequence[ReviewEvent],
    params: Sequence[float] = DEFAULT_FSRS5_PARAMS,
) -> CardStateV56:
    """Pure, deterministic fold over append-only `ReviewEvent` stream with `1e-6` quantization (T35, T36).

    Invariants:
    1. Permutation Invariance: Events are canonically ordered by `(ts_ms, event_id)`.
    2. Idempotency: Duplicate `idem_key` values are deduplicated via First-Writer-Wins.
    3. Non-Destructive Undo (`VOID`): Any event whose `event_id` is referenced by a `VOID` event is skipped.
    4. Non-Destructive `CRAM`: `CRAM` events never mutate `(s, d, due_ms, last_ts_ms, reps, lapses)`.
    """
    w = tuple(float(x) for x in params)
    if len(w) < 19:
        raise ValueError("FSRS-5 params must contain 19 weights")

    # Canonical sort by (ts_ms, event_id)
    ordered = sorted(events, key=lambda e: (int(e.ts_ms), str(e.event_id)))

    # First-Writer-Wins deduplication on idem_key & validation
    deduped: List[ReviewEvent] = []
    seen_idem: Set[str] = set()
    voided_event_ids: Set[str] = set()

    for ev in ordered:
        if not str(ev.event_id).strip() or not str(ev.idem_key).strip():
            raise ValueError("event_id and idem_key must be non-empty")
        if int(ev.ts_ms) <= 0:
            raise ValueError(f"Invalid ts_ms: {ev.ts_ms}")
        if ev.kind not in ("REVIEW", "REVIEW_AHEAD", "CRAM", "VOID"):
            raise ValueError(f"Unsupported ReviewEvent kind: {ev.kind}")
        if ev.kind in ("REVIEW", "REVIEW_AHEAD"):
            if ev.rating is None or int(ev.rating) not in (1, 2, 3, 4):
                raise ValueError(f"rating must be 1..4 for {ev.kind}, got {ev.rating}")
        elif ev.kind == "CRAM":
            if ev.rating is not None and int(ev.rating) not in (1, 2, 3, 4):
                raise ValueError(f"rating must be 1..4 for CRAM, got {ev.rating}")

        if ev.idem_key in seen_idem:
            continue
        seen_idem.add(ev.idem_key)
        if ev.kind == "VOID":
            if ev.voids:
                voided_event_ids.add(str(ev.voids))
            continue
        deduped.append(ev)

    s = 0.0
    d = 0.0
    due_ms = 0
    last_ts_ms: Optional[int] = None
    reps = 0
    lapses = 0

    for ev in deduped:
        if ev.event_id in voided_event_ids:
            continue
        if ev.kind == "CRAM":
            # Non-destructive cram invariant: state is byte-for-byte unchanged
            continue

        g = int(ev.rating or 3)
        now_ms = int(ev.ts_ms)

        if reps == 0 or last_ts_ms is None or s <= 0.0:
            # Initial FSRS-5 stability & difficulty
            s = quantize_1e6(max(0.1, w[g - 1]))
            d0 = w[4] - math.exp(w[5] * (g - 1)) + 1.0
            d = quantize_1e6(_clamp(d0, 1.0, 10.0))
            reps = 1
            last_ts_ms = now_ms
            ivl_days = max(1, int(round(s)))
            due_ms = now_ms + ivl_days * DAY_MS
            continue

        elapsed_days = max(0.0, (now_ms - last_ts_ms) / float(DAY_MS))
        # Retrievability R(t, S) = (1 + 19/81 * t / S)^(-0.5)
        r_now = quantize_1e6(math.pow(1.0 + (19.0 / 81.0) * (elapsed_days / max(0.1, s)), -0.5))

        # Update difficulty D' with mean reversion toward D0(3)
        d0_good = w[4] - math.exp(w[5] * 2.0) + 1.0
        delta_d = -w[6] * (g - 3.0)
        d_prime = d + delta_d * ((10.0 - d) / 9.0)
        d_next = quantize_1e6(_clamp(w[7] * d0_good + (1.0 - w[7]) * d_prime, 1.0, 10.0))

        if elapsed_days < 1.0 and ev.kind == "REVIEW_AHEAD":
            # Same-day short-term FSRS-5 update: S' = S * exp(w17 * (G - 3 + w18))
            s_next = quantize_1e6(_clamp(s * math.exp(w[17] * (g - 3.0 + w[18])), 0.1, 36500.0))
            if g == 1:
                lapses += 1
        elif g == 1:
            # Post-lapse stability S'_f
            lapses += 1
            s_fail = (
                w[11]
                * math.pow(d_next, -w[12])
                * (math.pow(s + 1.0, w[13]) - 1.0)
                * math.exp(w[14] * (1.0 - r_now))
            )
            s_next = quantize_1e6(_clamp(min(s, s_fail), 0.1, 36500.0))
        else:
            # Recall stability S'_r
            hard_penalty = w[15] if g == 2 else 1.0
            easy_bonus = w[16] if g == 4 else 1.0
            inc = (
                math.exp(w[8])
                * (11.0 - d_next)
                * math.pow(s, -w[9])
                * (math.exp(w[10] * (1.0 - r_now)) - 1.0)
                * hard_penalty
                * easy_bonus
            )
            # For REVIEW_AHEAD when t < I, r_now is close to 1.0, so exp(w10*(1-r_now))-1 naturally scales down gain!
            s_next = quantize_1e6(_clamp(s * (1.0 + inc), 0.1, 36500.0))

        s = s_next
        d = d_next
        reps += 1
        last_ts_ms = now_ms
        ivl_days = 1 if g == 1 else max(1, int(round(s)))
        due_ms = now_ms + ivl_days * DAY_MS

    return CardStateV56(
        s=s,
        d=d,
        due_ms=due_ms,
        last_ts_ms=last_ts_ms,
        reps=reps,
        lapses=lapses,
    )


@dataclass(frozen=True)
class ExamPlan:
    plan_id: str
    scope: Tuple[str, ...]
    exam_ms: int
    target_r: float
    status: Literal["ACTIVE", "BLOCKED", "DONE"]
    reason: Optional[str] = None
    phase: str = "coverage"
    allow_new_cards: bool = True
    today_queue: Tuple[Dict[str, Any], ...] = ()


def find_cycles(edges: Mapping[str, Sequence[str]]) -> List[frozenset[str]]:
    """Detect directed cycles (|SCC| > 1 or self-loop u -> u) using Tarjan's SCC algorithm (T40)."""
    index = 0
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    stack: List[str] = []
    on_stack: Set[str] = set()
    cycles: List[frozenset[str]] = []

    nodes: Set[str] = set(edges.keys())
    for targets in edges.values():
        for t in targets:
            nodes.add(str(t))

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in edges.get(v, ()):
            w_str = str(w)
            if w_str not in indices:
                strongconnect(w_str)
                lowlink[v] = min(lowlink[v], lowlink[w_str])
            elif w_str in on_stack:
                lowlink[v] = min(lowlink[v], indices[w_str])

        if lowlink[v] == indices[v]:
            scc: Set[str] = set()
            while True:
                w_pop = stack.pop()
                on_stack.remove(w_pop)
                scc.add(w_pop)
                if w_pop == v:
                    break
            has_self_loop = v in [str(x) for x in edges.get(v, ())]
            if len(scc) > 1 or has_self_loop:
                cycles.append(frozenset(scc))

    for n in sorted(nodes):
        if n not in indices:
            strongconnect(n)

    return cycles


def plan_exam(
    cards: Sequence[Mapping[str, Any]],
    now_ms: int,
    exam_ms: int,
    daily_cap: int,
    prereq: Mapping[str, Sequence[str]],
) -> ExamPlan:
    """Exam Countdown Autopilot scheduler (D-14 -> D-7 -> D-1 -> D-0 warmup) with Fail-Closed gates (T37)."""
    scope_ids = tuple(str(c.get("card_id") or idx) for idx, c in enumerate(cards))
    plan_id = f"exam-{exam_ms}-{len(scope_ids)}"

    if int(exam_ms) < int(now_ms):
        return ExamPlan(
            plan_id=plan_id,
            scope=scope_ids,
            exam_ms=int(exam_ms),
            target_r=0.90,
            status="BLOCKED",
            reason="past_exam_date",
        )

    if not cards:
        return ExamPlan(
            plan_id=plan_id,
            scope=(),
            exam_ms=int(exam_ms),
            target_r=0.90,
            status="BLOCKED",
            reason="empty_scope",
        )

    if int(daily_cap) <= 0:
        return ExamPlan(
            plan_id=plan_id,
            scope=scope_ids,
            exam_ms=int(exam_ms),
            target_r=0.90,
            status="BLOCKED",
            reason="capacity_exceeded",
        )

    if find_cycles(prereq):
        return ExamPlan(
            plan_id=plan_id,
            scope=scope_ids,
            exam_ms=int(exam_ms),
            target_r=0.90,
            status="BLOCKED",
            reason="dag_cycle_detected",
        )

    days_left = max(0, int((int(exam_ms) - int(now_ms)) // DAY_MS))
    total_budget = max(1, days_left + 1) * int(daily_cap)
    if len(cards) > total_budget:
        return ExamPlan(
            plan_id=plan_id,
            scope=scope_ids,
            exam_ms=int(exam_ms),
            target_r=0.90,
            status="BLOCKED",
            reason="capacity_exceeded",
        )

    # Dynamic target retention clamped to [0.70, 0.97]
    load_ratio = len(cards) / float(total_budget)
    raw_target_r = 0.96 - (0.004 * min(days_left, 30)) - (0.04 * load_ratio)
    target_r = quantize_1e6(_clamp(raw_target_r, 0.70, 0.97))

    if days_left >= 10:
        phase = "coverage"
        allow_new = True
        filtered = [dict(c) for c in cards]
        filtered.sort(key=lambda c: (0 if str(c.get("state")) == "new" else 1, float(c.get("s", 1.0))))
        queue = filtered[: int(daily_cap)]
    elif days_left >= 3:
        phase = "weakness_interleave"
        allow_new = False
        filtered = [dict(c) for c in cards if str(c.get("state", "review")) != "new"]
        filtered.sort(key=lambda c: (-int(c.get("lapses", 0)), float(c.get("s", 1.0))))
        queue = filtered[: int(daily_cap)]
    elif days_left >= 1:
        phase = "high_risk_review"
        allow_new = False
        filtered = [dict(c) for c in cards if str(c.get("state", "review")) != "new"]
        filtered.sort(key=lambda c: (float(c.get("s", 1.0)), -int(c.get("lapses", 0))))
        queue = filtered[: int(daily_cap)]
    else:
        phase = "morning_warmup"
        allow_new = False
        warmup_cap = min(20, int(daily_cap))
        filtered = [dict(c) for c in cards if str(c.get("state", "review")) != "new"]
        filtered.sort(key=lambda c: (-int(c.get("lapses", 0)), float(c.get("s", 1.0))))
        queue = filtered[:warmup_cap]

    return ExamPlan(
        plan_id=plan_id,
        scope=scope_ids,
        exam_ms=int(exam_ms),
        target_r=target_r,
        status="ACTIVE",
        reason=None,
        phase=phase,
        allow_new_cards=allow_new,
        today_queue=tuple(queue),
    )


def balance_due(
    ivl_days: float,
    load: Mapping[date, int],
    weights: Mapping[date, float],
    today: date,
) -> date:
    """FSRS Load Balancer & Easy Days selector within `[0.95*I, 1.05*I]` fuzz range (T37).

    Picks the candidate date `d` minimizing `load[d] / weight[d]`.
    Ties are broken deterministically by picking the earliest date.
    """
    if ivl_days <= 0:
        raise ValueError(f"ivl_days must be > 0, got {ivl_days}")

    min_days = max(1, int(math.floor(float(ivl_days) * 0.95)))
    max_days = max(min_days, int(math.ceil(float(ivl_days) * 1.05)))

    best_date: Optional[date] = None
    best_score: float = float("inf")

    for offset in range(min_days, max_days + 1):
        cand = today + timedelta(days=offset)
        w = float(weights.get(cand, 1.0))
        if w <= 0.0 or w > 1.0 or not math.isfinite(w):
            raise ValueError(f"Easy day weight must be in (0.0, 1.0], got {w} for {cand}")
        day_load = max(0, int(load.get(cand, 0)))
        effective_score = day_load / w
        if effective_score < best_score - 1e-9:
            best_score = effective_score
            best_date = cand

    return best_date or (today + timedelta(days=int(round(ivl_days))))


# ============================================================================
# PHASE 2: RESOURCE GRAPH, FACET RECONCILIATION, & AUTO IMAGE OCCLUSION
# ============================================================================


@dataclass(frozen=True)
class FacetSpec:
    note_id: str
    facet_key: str
    template: str
    front_text: str
    back_text: str
    note_type: str
    tags: Tuple[str, ...]


def generate_note_facets(
    note_id: str,
    term: str,
    answer: str,
    sentence: str = "",
    explain: str = "",
    enabled_facets: Sequence[str] = ("forward", "reverse", "listening_tts", "context_cloze"),
) -> List[FacetSpec]:
    """Derive N multi-directional facet cards from 1 source Note with shared `concept:<note_id>` tag (REA-R1, T38)."""
    nid = str(note_id).strip()
    clean_term = str(term).strip()
    clean_ans = str(answer).strip()
    if not nid or not clean_term or not clean_ans:
        raise ValueError("note_id, term, and answer are required")

    concept_tag = f"concept:{nid}"
    explain_suffix = f"\n\n💡 해설: {explain.strip()}" if explain and explain.strip() else ""
    specs: List[FacetSpec] = []

    for fkey in enabled_facets:
        if fkey == "forward":
            specs.append(
                FacetSpec(
                    note_id=nid,
                    facet_key="forward",
                    template="term_to_meaning",
                    front_text=f"📘 [정방향] '{clean_term}'의 핵심 뜻·의미는?",
                    back_text=f"{clean_ans}{explain_suffix}",
                    note_type="basic",
                    tags=(concept_tag, "facet:forward"),
                )
            )
        elif fkey == "reverse":
            specs.append(
                FacetSpec(
                    note_id=nid,
                    facet_key="reverse",
                    template="meaning_to_term",
                    front_text=f"🔄 [역방향 인출] 뜻이 '{clean_ans}'에 해당하는 핵심 용어·표현을 쓰시오.",
                    back_text=f"{clean_term}{explain_suffix}",
                    note_type="basic",
                    tags=(concept_tag, "facet:reverse"),
                )
            )
        elif fkey == "listening_tts":
            specs.append(
                FacetSpec(
                    note_id=nid,
                    facet_key="listening_tts",
                    template="audio_to_meaning_and_spelling",
                    front_text=f"🎧 [리스닝·발음 인출] 발음({clean_term})을 듣고 정확한 철자와 뜻을 말하거나 입력하시오.",
                    back_text=f"{clean_term} — {clean_ans}{explain_suffix}",
                    note_type="speaking",
                    tags=(concept_tag, "facet:listening_tts"),
                )
            )
        elif fkey == "context_cloze":
            if sentence and clean_term.lower() in sentence.lower():
                pattern = re.compile(re.escape(clean_term), re.IGNORECASE)
                cloze_sent = pattern.sub(f"{{{{c1::{clean_term}::{clean_ans}}}}}", sentence, count=1)
            else:
                cloze_sent = f"{{{{c1::{clean_term}::{clean_ans}}}}} — {sentence or clean_ans}"
            specs.append(
                FacetSpec(
                    note_id=nid,
                    facet_key="context_cloze",
                    template="sentence_cloze",
                    front_text=f"🧩 [문맥 빈칸] {cloze_sent}",
                    back_text=f"{clean_term}: {clean_ans}{explain_suffix}",
                    note_type="cloze",
                    tags=(concept_tag, "facet:context_cloze"),
                )
            )
    return specs


def diff_facets(
    expected: Set[str],
    existing: Mapping[str, Mapping[str, Any]],
    now_ms: int,
    grace_ms: int,
) -> List[Dict[str, Any]]:
    """Reconcile expected facets against existing facet states without losing `card_id` or `review_events` (T38).

    State transitions:
    - Present in `expected`:
      - New -> `ACTIVE` (allocates deterministic `card_id` if missing)
      - Existing (`ACTIVE`, `RETIRED`, or `TOMBSTONED`) -> `ACTIVE` (resurrects original `card_id`, clears retired/tombstoned timestamps)
    - Missing from `expected`:
      - `ACTIVE` -> `RETIRED` (`retired_at_ms = now_ms`)
      - `RETIRED` with `now_ms >= retired_at_ms + grace_ms` -> `TOMBSTONED` (`tombstoned_at_ms = now_ms`)
      - `RETIRED` within grace period -> stays `RETIRED`
      - `TOMBSTONED` -> stays `TOMBSTONED`
    """
    all_keys = sorted(set(expected) | set(existing.keys()))
    transitions: List[Dict[str, Any]] = []

    for fkey in all_keys:
        prev = existing.get(fkey)
        card_id = str(prev["card_id"]) if prev and prev.get("card_id") else f"card-{fkey}"
        if fkey in expected:
            transitions.append(
                {
                    "facet_key": fkey,
                    "card_id": card_id,
                    "state": "ACTIVE",
                    "retired_at_ms": None,
                    "tombstoned_at_ms": None,
                    "resurrected": bool(prev and prev.get("state") in ("RETIRED", "TOMBSTONED")),
                }
            )
        else:
            if not prev:
                continue
            prev_state = str(prev.get("state") or "ACTIVE")
            prev_retired = prev.get("retired_at_ms")
            prev_tomb = prev.get("tombstoned_at_ms")

            if prev_state == "ACTIVE":
                transitions.append(
                    {
                        "facet_key": fkey,
                        "card_id": card_id,
                        "state": "RETIRED",
                        "retired_at_ms": int(now_ms),
                        "tombstoned_at_ms": None,
                        "resurrected": False,
                    }
                )
            elif prev_state == "RETIRED":
                ret_ms = int(prev_retired if prev_retired is not None else now_ms)
                if int(now_ms) >= ret_ms + int(grace_ms):
                    transitions.append(
                        {
                            "facet_key": fkey,
                            "card_id": card_id,
                            "state": "TOMBSTONED",
                            "retired_at_ms": ret_ms,
                            "tombstoned_at_ms": int(now_ms),
                            "resurrected": False,
                        }
                    )
                else:
                    transitions.append(
                        {
                            "facet_key": fkey,
                            "card_id": card_id,
                            "state": "RETIRED",
                            "retired_at_ms": ret_ms,
                            "tombstoned_at_ms": None,
                            "resurrected": False,
                        }
                    )
            else:
                transitions.append(
                    {
                        "facet_key": fkey,
                        "card_id": card_id,
                        "state": "TOMBSTONED",
                        "retired_at_ms": prev_retired,
                        "tombstoned_at_ms": prev_tomb or int(now_ms),
                        "resurrected": False,
                    }
                )

    return transitions


@dataclass(frozen=True)
class OcrBoundingBox:
    label: str
    x: float
    y: float
    w: float
    h: float
    confidence: float = 0.90


def build_image_occlusion_cards(
    image_bytes: bytes,
    mime: str,
    ocr_boxes: Sequence[OcrBoundingBox],
    mode: Literal["hide_all_guess_one", "hide_one_guess_one"] = "hide_all_guess_one",
    deck_title: str = "도표·이미지 빈칸 덱",
    min_confidence: float = 0.60,
) -> List[Dict[str, Any]]:
    """Generate Zero-Click Image Occlusion cards from OCR bounding boxes and CAS sha256 media hash (REA-R2, T39)."""
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")
    if mode not in ("hide_all_guess_one", "hide_one_guess_one"):
        raise ValueError(f"Unsupported occlusion mode: {mode}")

    media_sha256 = hashlib.sha256(image_bytes).hexdigest()

    valid_boxes: List[OcrBoundingBox] = []
    for b in ocr_boxes:
        lbl = str(b.label or "").strip()
        if len(lbl) < 1 or float(b.confidence) < min_confidence:
            continue
        if b.x < 0.0 or b.y < 0.0 or b.w <= 0.0 or b.h <= 0.0:
            continue
        if (b.x + b.w) > 1.0001 or (b.y + b.h) > 1.0001:
            continue
        valid_boxes.append(b)

    cards: List[Dict[str, Any]] = []
    for target_idx, target_box in enumerate(valid_boxes):
        rects_svg: List[str] = []
        for idx, box in enumerate(valid_boxes):
            is_target = idx == target_idx
            if mode == "hide_one_guess_one" and not is_target:
                continue
            fill = "#e11d48" if is_target else "#1e293b"
            stroke = "#ffffff"
            tag_text = "❓ [ ? ]" if is_target else "███"
            rx = round(box.x * 100.0, 2)
            ry = round(box.y * 100.0, 2)
            rw = round(box.w * 100.0, 2)
            rh = round(box.h * 100.0, 2)
            rects_svg.append(
                f'<g data-mask-idx="{idx}" data-target="{str(is_target).lower()}">'
                f'<rect x="{rx}%" y="{ry}%" width="{rw}%" height="{rh}%" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
                f'<text x="{round(rx + rw / 2, 2)}%" y="{round(ry + rh / 2, 2)}%" fill="#ffffff" font-size="10" text-anchor="middle" dominant-baseline="middle">{tag_text}</text>'
                f"</g>"
            )

        svg_overlay = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" class="occlusion-overlay">'
            + "".join(rects_svg)
            + "</svg>"
        )
        mask_sha256 = hashlib.sha256(svg_overlay.encode("utf-8")).hexdigest()
        mode_badge = "전부 가리고 1개 맞추기" if mode == "hide_all_guess_one" else "1개만 가리고 맞추기"
        cards.append(
            {
                "mask_id": f"occ-{media_sha256[:10]}-{target_idx + 1}",
                "media_sha256": media_sha256,
                "mask_sha256": mask_sha256,
                "mime": mime,
                "mode": mode,
                "target_label": target_box.label.strip(),
                "target_bbox": {
                    "x": round(target_box.x, 4),
                    "y": round(target_box.y, 4),
                    "w": round(target_box.w, 4),
                    "h": round(target_box.h, 4),
                },
                "svg_mask": svg_overlay,
                "front_text": f"🖼️ [{deck_title} · {mode_badge}] 그림의 빨간색 [ ❓ #{target_idx + 1} ] 영역에 들어갈 핵심 명칭은?",
                "back_text": f"{target_box.label.strip()}\n\n💡 도표 전체 라벨 ({len(valid_boxes)}개): "
                + ", ".join(b.label.strip() for b in valid_boxes),
                "note_type": "image_occlusion",
                "tags": ("image-occlusion", mode, f"media:{media_sha256[:12]}"),
            }
        )

    return cards


def build_context_breadcrumb(hierarchy_path: Sequence[str], source_page: Optional[int] = None) -> str:
    """Format hierarchical concept outline breadcrumb header to prevent context isolation (REA-A1, T39)."""
    parts = [str(p).strip() for p in hierarchy_path if str(p).strip()]
    if not parts:
        base = "📚 일반 학습 노트"
    else:
        base = "📚 " + " > ".join(parts)
    if source_page is not None and int(source_page) > 0:
        return f"{base} (p.{int(source_page)})"
    return base


# ============================================================================
# PHASE 3: ACTIVE RECALL 2.0 — CONFUSION GRAPH, PREREQ DAG, RUBRIC, MICRO-SPRINT
# ============================================================================


@dataclass(frozen=True)
class ConfusableEdge:
    src: str
    dst: str
    weight: float
    count: int
    last_ts_ms: int


def record_confusion_observation(
    edges: Mapping[Tuple[str, str], ConfusableEdge],
    asked_concept_id: str,
    answered_concept_id: str,
    ts_ms: int,
    decay_half_life_days: float = 14.0,
) -> Dict[Tuple[str, str], ConfusableEdge]:
    """Update directional confusion edge `src -> dst` when user answers `dst` for prompt `src` (REA-D3, T40).

    Invariant: `src -> dst != dst -> src` (asymmetric) and `src != dst` (no self-loop).
    """
    src = str(asked_concept_id).strip()
    dst = str(answered_concept_id).strip()
    if not src or not dst:
        raise ValueError("asked_concept_id and answered_concept_id must be non-empty")
    if src == dst:
        raise ValueError("self-confusion edge (src == dst) is forbidden")

    updated = dict(edges)
    key = (src, dst)
    prev = updated.get(key)
    if prev is None:
        updated[key] = ConfusableEdge(src=src, dst=dst, weight=1.0, count=1, last_ts_ms=int(ts_ms))
    else:
        elapsed_days = max(0.0, (int(ts_ms) - int(prev.last_ts_ms)) / float(DAY_MS))
        decay = math.pow(0.5, elapsed_days / max(1.0, float(decay_half_life_days)))
        new_weight = quantize_1e6(prev.weight * decay + 1.0)
        updated[key] = ConfusableEdge(
            src=src,
            dst=dst,
            weight=new_weight,
            count=prev.count + 1,
            last_ts_ms=int(ts_ms),
        )
    return updated


def generate_contrastive_card(
    concept_a: Mapping[str, str],
    concept_b: Mapping[str, str],
) -> Dict[str, Any]:
    """Synthesize a discriminative Contrastive Card (`[A vs B 구별]`) for a confused concept pair (REA-D3)."""
    term_a = str(concept_a.get("term") or concept_a.get("id") or "개념 A").strip()
    ans_a = str(concept_a.get("answer") or "").strip()
    term_b = str(concept_b.get("term") or concept_b.get("id") or "개념 B").strip()
    ans_b = str(concept_b.get("answer") or "").strip()
    pair_id = f"contrast:{concept_a.get('id', term_a)}:{concept_b.get('id', term_b)}"

    return {
        "contrast_pair_id": pair_id,
        "note_type": "basic",
        "front_text": f"⚡ [혼동 주의 · A vs B 핵심 구별]\n'{term_a}'와(과) '{term_b}'의 결정적 차이를 각각 구별하시오.",
        "back_text": f"• {term_a}: {ans_a}\n• {term_b}: {ans_b}\n\n💡 팁: 두 개념을 헷갈린 이력이 감지되어 인접 비교 카드로 출제되었습니다.",
        "tags": ("contrastive-drill", pair_id),
    }


def interleave_contrastive(
    queue: List[str],
    edges: Sequence[ConfusableEdge],
    max_gap: int = 2,
) -> List[str]:
    """Place confused concept pairs `(src, dst)` within `<= max_gap` slots in the session queue (REA-D3, T40)."""
    if len(queue) <= 2 or not edges:
        return list(queue)

    gap = max(1, int(max_gap))
    result = list(queue)
    ranked_edges = sorted(edges, key=lambda e: (-e.weight, -e.count, e.src, e.dst))

    for edge in ranked_edges:
        if edge.src in result and edge.dst in result:
            idx_src = result.index(edge.src)
            idx_dst = result.index(edge.dst)
            if abs(idx_src - idx_dst) > gap:
                result.pop(idx_dst)
                idx_src_now = result.index(edge.src)
                target_pos = min(len(result), idx_src_now + 1)
                result.insert(target_pos, edge.dst)

    return result


def check_prereq_gate(
    card_id: str,
    prereq_parents: Mapping[str, Sequence[str]],
    parent_retentions: Mapping[str, float],
    was_unlocked: bool = False,
    open_threshold: float = 0.85,
    close_threshold: float = 0.75,
) -> Dict[str, Any]:
    """Evaluate Prerequisite DAG unlock gate with hysteresis (`open >= 0.85`, `close < 0.75`) (REA-D2, T40)."""
    parents = [str(p) for p in prereq_parents.get(card_id, ())]
    if not parents:
        return {"card_id": card_id, "unlocked": True, "blocking_parents": []}

    threshold = float(close_threshold if was_unlocked else open_threshold)
    blocking: List[str] = []
    for p in parents:
        r_val = float(parent_retentions.get(p, 0.0))
        if r_val + 1e-9 < threshold:
            blocking.append(p)

    return {
        "card_id": card_id,
        "unlocked": len(blocking) == 0,
        "threshold_applied": threshold,
        "blocking_parents": blocking,
    }


def diagnose_prereq_deficit(
    failed_card_id: str,
    prereq_parents: Mapping[str, Sequence[str]],
    parent_retentions: Mapping[str, float],
    remediation_threshold: float = 0.80,
) -> Dict[str, Any]:
    """Before decomposing a Leech card, check if any prerequisite parent card has low retention (REA-D2)."""
    parents = [str(p) for p in prereq_parents.get(failed_card_id, ())]
    deficit = [p for p in parents if float(parent_retentions.get(p, 0.0)) < remediation_threshold]
    if deficit:
        return {
            "card_id": failed_card_id,
            "action": "remediate_prerequisites_first",
            "deficit_parents": deficit,
        }
    return {
        "card_id": failed_card_id,
        "action": "decompose_leech_atomic",
        "deficit_parents": [],
    }


@dataclass(frozen=True)
class RubricSpec:
    required: Tuple[str, ...]
    bonus: Tuple[str, ...] = ()
    forbidden: Tuple[str, ...] = ()
    pass_ratio: float = 0.80


def score_rubric(
    answer: Optional[str],
    spec: RubricSpec,
    stt_status: str = "ok",
) -> Dict[str, Any]:
    """Grade constructed-response / oral interview answers against keyword rubric (GRK-3, T41).

    Fail-Closed Invariant:
    - If `stt_status` is not `'ok'` (e.g. `'timeout'`, `'error'`, `'not_run'`) or `answer` is None/blank,
      return `status="SCORE_UNAVAILABLE"` and `should_record_event=False` (never record a fake 0 or pass!).
    - Any match in `spec.forbidden` (misconception keywords) forces `passed=False` and `recommended_rating=1`.
    """
    if str(stt_status or "ok").strip().lower() != "ok":
        return {
            "status": "SCORE_UNAVAILABLE",
            "reason": f"stt_{stt_status}",
            "should_record_event": False,
            "passed": False,
            "score_pct": None,
            "recommended_rating": None,
        }

    if answer is None or not str(answer).strip():
        return {
            "status": "SCORE_UNAVAILABLE",
            "reason": "empty_answer",
            "should_record_event": False,
            "passed": False,
            "score_pct": None,
            "recommended_rating": None,
        }

    norm_ans = re.sub(r"\s+", "", str(answer).lower())
    req_hits = tuple(kw for kw in spec.required if re.sub(r"\s+", "", kw.lower()) in norm_ans)
    req_missed = tuple(kw for kw in spec.required if kw not in req_hits)
    bonus_hits = tuple(kw for kw in spec.bonus if re.sub(r"\s+", "", kw.lower()) in norm_ans)
    forbid_hits = tuple(kw for kw in spec.forbidden if re.sub(r"\s+", "", kw.lower()) in norm_ans)

    total_req = max(1, len(spec.required))
    base_ratio = len(req_hits) / float(total_req)
    bonus_boost = 0.10 * len(bonus_hits)
    forbid_penalty = 0.50 * len(forbid_hits)
    final_ratio = _clamp(base_ratio + bonus_boost - forbid_penalty, 0.0, 1.0)
    score_pct = int(round(final_ratio * 100.0))

    passed = (len(forbid_hits) == 0) and (base_ratio + 1e-9 >= float(spec.pass_ratio))
    if forbid_hits or base_ratio < 0.50:
        rec_rating = 1
    elif not passed:
        rec_rating = 2
    elif len(req_hits) == len(spec.required) and len(bonus_hits) > 0:
        rec_rating = 4
    else:
        rec_rating = 3

    return {
        "status": "SCORED",
        "should_record_event": True,
        "passed": passed,
        "score_pct": score_pct,
        "required_hits": req_hits,
        "required_missed": req_missed,
        "bonus_hits": bonus_hits,
        "forbidden_hits": forbid_hits,
        "recommended_rating": rec_rating,
    }


def chunk_micro_sprints(
    cards: Sequence[Mapping[str, Any]],
    sprint_size: int = 7,
) -> List[Dict[str, Any]]:
    """Chunk a study queue into 7-card micro-sprint rounds with intermediate fanfare checkpoints (QZ-1, T41)."""
    step = max(1, int(sprint_size))
    items = [dict(c) for c in cards]
    total_sprints = max(1, math.ceil(len(items) / float(step))) if items else 0
    sprints: List[Dict[str, Any]] = []

    for idx in range(total_sprints):
        chunk = items[idx * step : (idx + 1) * step]
        sprints.append(
            {
                "sprint_index": idx + 1,
                "total_sprints": total_sprints,
                "card_count": len(chunk),
                "checkpoint_label": f"🏁 스프린트 {idx + 1} / {total_sprints} ({len(chunk)}장)",
                "cards": chunk,
            }
        )
    return sprints


def build_matching_board_round(
    cards: Sequence[Mapping[str, Any]],
    pair_count: int = 6,
    seed: int = 42,
) -> Dict[str, Any]:
    """Build a 60-second 4x3 Speed Matching Board game round (`event_kind='CRAM'`) (QZ-2, T41)."""
    selected = [dict(c) for c in cards[: max(1, int(pair_count))]]
    tiles: List[Dict[str, Any]] = []

    for idx, c in enumerate(selected, start=1):
        cid = c.get("card_id", idx)
        front = str(c.get("front_text") or c.get("front") or f"질문 {idx}").strip()
        back = str(c.get("back_text") or c.get("back") or f"정답 {idx}").strip()
        clean_ans, _ = extract_clean_target_answer(front, back)
        tiles.append({"tile_id": f"q-{cid}", "pair_key": str(cid), "kind": "prompt", "text": front[:60]})
        tiles.append({"tile_id": f"a-{cid}", "pair_key": str(cid), "kind": "answer", "text": (clean_ans or back)[:45]})

    def _tile_hash(tile: Mapping[str, Any]) -> int:
        raw = f"{tile['tile_id']}:{seed}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")

    tiles.sort(key=_tile_hash)
    return {
        "pair_count": len(selected),
        "time_limit_sec": 60,
        "event_kind": "CRAM",
        "tiles": tiles,
    }


# ============================================================================
# PHASE 4: VIEW & VIRAL UTILITY — SUMMARY SHEET, PRINTABLE EXAM PDF/HTML, AUDIO, QR, STREAK
# ============================================================================


def build_summary_sheet_view(
    cards: Sequence[Mapping[str, Any]],
    mask_mode: Literal["red_filter", "reveal_all"] = "red_filter",
) -> Dict[str, Any]:
    """Build Electronic Red-Cellophane Summary Sheet view for 5-minute pre-exam review (RN-1, T42)."""
    rows: List[Dict[str, Any]] = []
    for idx, c in enumerate(cards, start=1):
        front = str(c.get("front_text") or c.get("front") or "").strip()
        back = str(c.get("back_text") or c.get("back") or "").strip()
        clean_ans, extra_exp = extract_clean_target_answer(front, back)
        base_ans = clean_ans or back
        m_paren = re.match(r"^(.+?)\s*\(([^()]+)\)\s*$", base_ans)
        if m_paren:
            base_ans = m_paren.group(1).strip()
            if not extra_exp:
                extra_exp = m_paren.group(2).strip()
        rows.append(
            {
                "index": idx,
                "card_id": c.get("card_id", idx),
                "prompt": front,
                "clean_answer": base_ans,
                "explanation": extra_exp,
                "masked": mask_mode == "red_filter",
            }
        )
    return {
        "mask_mode": mask_mode,
        "total_rows": len(rows),
        "rows": rows,
    }


def build_printable_exam_sheet(
    cards: Sequence[Mapping[str, Any]],
    title: str = "BrainDeck 학교·학원 대비 단원 쪽지시험지",
    seed: int = 20261022,
) -> Dict[str, Any]:
    """Generate a 2-column Printable Exam Worksheet + separate Answer Key with identical seed ordering (CC-1, T42)."""
    items = [dict(c) for c in cards]

    def _seed_rank(c: Mapping[str, Any], i: int) -> int:
        cid = c.get("card_id", i)
        raw = f"{cid}:{c.get('front_text', '')}:{seed}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")

    ordered = [c for _, c in sorted(enumerate(items), key=lambda pair: _seed_rank(pair[1], pair[0]))]
    question_sheet: List[Dict[str, Any]] = []
    answer_key: List[Dict[str, Any]] = []

    q_html_rows: List[str] = []
    a_html_rows: List[str] = []

    for num, c in enumerate(ordered, start=1):
        front = str(c.get("front_text") or c.get("front") or "").strip()
        back = str(c.get("back_text") or c.get("back") or "").strip()
        clean_ans, extra_exp = extract_clean_target_answer(front, back)
        ans_text = clean_ans or back

        question_sheet.append({"number": num, "card_id": c.get("card_id", num), "question": front, "blank": "____________________"})
        answer_key.append({"number": num, "card_id": c.get("card_id", num), "answer": ans_text, "explanation": extra_exp})

        q_html_rows.append(
            f'<div class="exam-item"><span class="q-num">{num}.</span> '
            f'<span class="q-text">{html.escape(front)}</span>'
            f'<div class="q-blank">답: ____________________________</div></div>'
        )
        a_html_rows.append(
            f'<div class="ans-item"><strong>{num}번 정답:</strong> {html.escape(ans_text)}'
            + (f' <span class="ans-exp">({html.escape(extra_exp)})</span>' if extra_exp else "")
            + "</div>"
        )

    safe_title = html.escape(title)
    printable_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<title>{safe_title}</title>
<style>
  body {{ font-family: "Pretendard", -apple-system, sans-serif; color: #111827; padding: 24px; }}
  h1 {{ font-size: 1.35rem; margin-bottom: 6px; border-bottom: 2px solid #111827; padding-bottom: 8px; }}
  .meta {{ font-size: 0.85rem; color: #4b5563; margin-bottom: 18px; display: flex; justify-content: space-between; }}
  .two-col {{ column-count: 2; column-gap: 28px; }}
  .exam-item {{ break-inside: avoid; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px dashed #d1d5db; font-size: 0.92rem; }}
  .q-num {{ font-weight: 800; color: #1d4ed8; }}
  .q-blank {{ margin-top: 6px; color: #374151; font-weight: 600; }}
  .page-break {{ page-break-before: always; margin-top: 36px; border-top: 2px solid #111827; padding-top: 18px; }}
  .ans-item {{ break-inside: avoid; margin-bottom: 8px; font-size: 0.88rem; }}
  .ans-exp {{ color: #6b7280; font-size: 0.8rem; }}
</style>
</head>
<body>
  <h1>📝 {safe_title} (문제지)</h1>
  <div class="meta"><span>문항 수: {len(ordered)}문항 · 시드: #{seed}</span><span>이름: ____________  점수: _____ / {len(ordered)}</span></div>
  <div class="two-col">{"".join(q_html_rows)}</div>
  <div class="page-break">
    <h1>✅ {safe_title} (정답 및 해설지)</h1>
    <div class="two-col">{"".join(a_html_rows)}</div>
  </div>
</body>
</html>"""

    return {
        "title": title,
        "seed": int(seed),
        "column_count": 2,
        "items": len(ordered),
        "question_sheet": question_sheet,
        "answer_key": answer_key,
        "printable_html": printable_html,
    }


def build_commute_audio_script(
    cards: Sequence[Mapping[str, Any]],
    think_seconds: int = 3,
) -> Dict[str, Any]:
    """Build hands-free Commute / Driving Audio Loop playlist (`Question TTS -> Think Pause -> Answer TTS`) (MV-1, T42)."""
    pause_sec = max(1, min(15, int(think_seconds)))
    tracks: List[Dict[str, Any]] = []
    for idx, c in enumerate(cards, start=1):
        front = str(c.get("front_text") or c.get("front") or "").strip()
        back = str(c.get("back_text") or c.get("back") or "").strip()
        clean_ans, extra_exp = extract_clean_target_answer(front, back)
        tracks.append(
            {
                "track_number": idx,
                "card_id": c.get("card_id", idx),
                "question_tts": re.sub(r"\{\{c\d+::([^:}]+)(?:::[^}]+)?\}\}", "빈칸", front),
                "pause_seconds": pause_sec,
                "answer_tts": clean_ans or back,
                "explanation_tts": extra_exp,
            }
        )
    return {
        "mode": "commute_hands_free",
        "think_seconds": pause_sec,
        "total_tracks": len(tracks),
        "tracks": tracks,
    }


def encode_scope_snapshot_qr(
    deck_rev: str,
    scope_ids: Sequence[str],
    exam_ms: int,
    expires_ms: int,
) -> Dict[str, Any]:
    """Encode a PII-free Exam Scope Snapshot token for QR / short-code sharing (GRK-2, T42)."""
    canonical_scopes = sorted(str(s).strip() for s in scope_ids if str(s).strip())
    if not canonical_scopes:
        raise ValueError("scope_ids must not be empty")
    if int(expires_ms) <= int(exam_ms):
        raise ValueError("expires_ms must be greater than exam_ms")

    scope_hash = hashlib.sha256("|".join(canonical_scopes).encode("utf-8")).hexdigest()[:12]
    payload = {
        "v": "5.6",
        "deck_rev": str(deck_rev).strip(),
        "scope_hash": scope_hash,
        "scopes": canonical_scopes,
        "exam_ms": int(exam_ms),
        "expires_ms": int(expires_ms),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    short_code = f"BD56-{scope_hash[:6].upper()}"
    return {
        "code": short_code,
        "scope_hash": scope_hash,
        "payload": payload,
        "payload_json": payload_json,
    }


def build_parent_completion_report(
    scope_title: str,
    exam_ms: int,
    daily_logs: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build Parent/Teacher Completion Report Card with zero fabricated ranks/scores (GRK-2, T42)."""
    if not daily_logs:
        return {
            "scope_title": scope_title,
            "exam_ms": int(exam_ms),
            "status_label": "집계 없음",
            "assigned_total": 0,
            "completed_total": 0,
            "completion_pct": None,
            "streak_days": 0,
            "last_studied_at": None,
        }

    assigned_total = sum(max(0, int(row.get("assigned", 0))) for row in daily_logs)
    completed_total = sum(max(0, int(row.get("completed_review", 0))) for row in daily_logs)
    pct = round((completed_total / float(assigned_total)) * 100.0, 1) if assigned_total > 0 else 0.0
    streak_info = evaluate_streak_shield(daily_logs, available_shields=0)

    return {
        "scope_title": scope_title,
        "exam_ms": int(exam_ms),
        "status_label": f"할당 완료율 {pct}%",
        "assigned_total": assigned_total,
        "completed_total": completed_total,
        "completion_pct": pct,
        "streak_days": streak_info["current_streak_days"],
        "last_studied_at": str(daily_logs[-1].get("date") or ""),
    }


def evaluate_streak_shield(
    daily_logs: Sequence[Mapping[str, Any]],
    available_shields: int = 0,
) -> Dict[str, Any]:
    """Evaluate completion-based Streak & Streak Shield consumption (GRK-4, T42).

    Invariants:
    1. A day counts as completed ONLY if `assigned > 0` and `completed_review >= assigned`.
    2. `CRAM` activity (`cram_count`) never substitutes for `completed_review`.
    3. A pre-held `Streak Shield` bridges at most a single-day gap (`consecutive_misses == 1`).
    """
    shields = max(0, int(available_shields))
    streak = 0
    consecutive_misses = 0

    for row in daily_logs:
        assigned = max(0, int(row.get("assigned", 0)))
        completed_rev = max(0, int(row.get("completed_review", 0)))
        is_completed = assigned > 0 and completed_rev >= assigned

        if is_completed:
            streak += 1
            consecutive_misses = 0
        else:
            consecutive_misses += 1
            if consecutive_misses == 1 and shields > 0:
                shields -= 1
            else:
                streak = 0

    return {
        "current_streak_days": streak,
        "shields_remaining": shields,
    }


# ============================================================================
# PHASE 5 (GATE T43): TYPE-HOMOGENEOUS 4-CHOICE DISTRACTORS & QUESTION TYPE ORGANIZER
# ============================================================================

TYPE_FALLBACK_DISTRACTOR_BANK: Dict[str, Tuple[str, ...]] = {
    "eng_vocab_meaning": (
        "소개하다",
        "가장 좋아하는",
        "악기",
        "자원봉사하다",
        "의사소통하다",
        "경험하다",
        "균형 잡힌",
        "전통적인",
    ),
    "eng_vocab_word": (
        "introduce",
        "favorite",
        "instrument",
        "volunteer",
        "communicate",
        "experience",
        "traditional",
        "ancient",
    ),
    "eng_grammar": (
        "doesn't (does not) + 동사원형",
        "Did + 주어 + 동사원형? / didn't + 동사원형",
        "There is + 단수명사 / There are + 복수명사",
        "to부정사 (to + 동사원형, 명사적 용법)",
        "동명사 (V-ing)",
        "형용사 (부사 -ly 사용 불가)",
    ),
    "hanja_hun_eum": (
        "배울 학",
        "학교 교",
        "날 생",
        "나라 국",
        "백성 민",
        "가르칠 교",
        "집 가",
        "마음 심",
    ),
    "hanja_char": ("學", "校", "生", "國", "民", "敎", "家", "心"),
    "idiom": (
        "큰 그릇은 늦게 이루어진다",
        "처지를 바꾸어 생각함",
        "준비가 있으면 근심이 없다",
        "돌 하나로 새 두 마리를 잡음",
    ),
    "history": (
        "강화도 조약",
        "갑신정변",
        "동학 농민 운동",
        "독립협회",
        "훈민정음",
        "경국대전",
        "함무라비 법전",
    ),
    "science": (
        "공유 결합",
        "이온 결합",
        "활성화 에너지",
        "미토콘드리아",
        "V = I × R",
        "원자성·일관성·격리성·지속성",
    ),
    "ko_dictation": (
        "맑고 따뜻합니다",
        "할머니께 썼습니다",
        "조용히 읽어요",
        "꽃이 활짝",
    ),
    "general_concept": (
        "핵심 원리 및 개념 정의",
        "상호 배제와 동기화 조건",
        "원인과 결과의 상관관계",
        "필수 성립 요건 및 예외 조항",
        "구조적 특징과 작동 원리",
    ),
}

_GRAMMAR_KEYWORDS: Tuple[str, ...] = (
    "핵심문법",
    "[문법",
    "동사원형",
    "현재진행형",
    "과거시제",
    "수일치",
    "to부정사",
    "동명사",
    "비교급",
    "최상급",
    "감각동사",
    "there is",
    "there are",
    "v-ing",
    "부정문",
    "의문문",
)


def _clean_concise_choice_answer(front_text: str, back_text: str, explicit_target: str = "") -> str:
    raw, _ = extract_clean_target_answer(front_text, back_text)
    ans = (explicit_target or raw or back_text or "").strip()
    ans = ans.splitlines()[0].strip() if ans else ""
    # Strip trailing POS tags like '(동사)', '(명사)', '(형용사)', '(부사)', '(숙어)', '(부수: ...)'
    ans = re.sub(
        r"\s*\((?:동사|명사|형용사|부사|숙어|전치사|접속사|부수:[^)]+|조일수호조규[^)]*|1[0-9]{3}[^)]*)\)\s*$",
        "",
        ans,
    ).strip()
    if " — " in ans and not any(k in front_text for k in ("핵심문법", "문법")):
        parts = [p.strip() for p in ans.split(" — ") if p.strip()]
        if len(parts) == 2 and all(ord(c) < 128 for c in parts[0]):
            if "{{" in front_text and all(ord(c) < 128 for c in front_text.replace("{{", "").replace("}}", "")[:15]):
                ans = parts[0]
            else:
                ans = parts[1]
    return ans or (raw or back_text).strip()


def classify_card_question_type(card: Mapping[str, Any]) -> Dict[str, str]:
    """Deterministically classify a card into its exact Question/Answer Facet & Category (T43).

    Categories:
    - `vocab`: English/Korean vocabulary & dictation (`eng_vocab_meaning`, `eng_vocab_word`, `ko_dictation`)
    - `grammar`: English grammar & syntax rules (`eng_grammar`)
    - `hanja`: Hanja & 4-character idioms (`hanja_hun_eum`, `hanja_char`, `idiom`)
    - `history_sci`: History, Science, Law, & CS concepts (`history`, `science`)
    """
    front = str(card.get("front_text") or card.get("front") or card.get("rendered_question") or "").strip()
    back = str(card.get("back_text") or card.get("back") or card.get("rendered_answer") or "").strip()
    raw_tags = card.get("tags") or card.get("tags_json") or []
    if isinstance(raw_tags, str):
        tags_str = raw_tags.lower()
    elif isinstance(raw_tags, Sequence):
        tags_str = " ".join(str(t).lower() for t in raw_tags)
    else:
        tags_str = ""

    clean_ans = _clean_concise_choice_answer(front, back, str(card.get("target_answer") or ""))
    combined_lower = f"{front} {back} {tags_str}".lower()

    # 1. Grammar check (highest priority so grammar rules NEVER leak into vocab!)
    if "role:key_grammar" in tags_str or "grammar" in tags_str or any(kw in combined_lower for kw in _GRAMMAR_KEYWORDS):
        return {
            "facet_key": "eng_grammar",
            "category_key": "grammar",
            "badge_label": "📐 영문법 규칙",
        }

    # 2. Hanja & Idiom check
    has_cjk = any(0x4E00 <= ord(ch) <= 0x9FFF or 0xF900 <= ord(ch) <= 0xFAFF for ch in (front + back))
    if "idiom" in tags_str or "사자성어" in combined_lower:
        return {
            "facet_key": "idiom",
            "category_key": "hanja",
            "badge_label": "📜 사자성어",
        }
    if "hanja" in tags_str or has_cjk:
        if len(clean_ans) == 1 and any(0x4E00 <= ord(ch) <= 0x9FFF for ch in clean_ans):
            return {
                "facet_key": "hanja_char",
                "category_key": "hanja",
                "badge_label": "漢字 한자 자형",
            }
        return {
            "facet_key": "hanja_hun_eum",
            "category_key": "hanja",
            "badge_label": "漢字 한자 훈음",
        }

    # 3. Korean Dictation check
    if "dictation" in tags_str or "받아쓰기" in combined_lower or "맞춤법" in combined_lower:
        return {
            "facet_key": "ko_dictation",
            "category_key": "vocab",
            "badge_label": "✏️ 받아쓰기·맞춤법",
        }

    # 4. History check
    if (
        "hist" in tags_str
        or "khist" in tags_str
        or "한국사" in combined_lower
        or "역사" in combined_lower
        or any(w in combined_lower for w in ("조약", "정변", "운동", "법전", "훈민정음", "카스트제", "왕조", "세조", "세종"))
    ):
        return {
            "facet_key": "history",
            "category_key": "history_sci",
            "badge_label": "🏛️ 역사 핵심 개념",
        }

    # 5. Science / Law / IT check
    if (
        "sci" in tags_str
        or "law" in tags_str
        or "cert" in tags_str
        or any(w in combined_lower for w in ("결합", "에너지", "미토콘드리아", "법칙", "헌법", "트랜잭션", "교착상태", "계층", "정규화"))
    ):
        return {
            "facet_key": "science",
            "category_key": "history_sci",
            "badge_label": "🔬 과학·전공 개념",
        }

    # 6. English Vocabulary: distinguish English-word answer vs Korean-meaning answer vs General Korean Concept!
    ans_is_ascii_english = bool(clean_ans) and all(ord(ch) < 128 for ch in clean_ans) and any("a" <= ch.lower() <= "z" for ch in clean_ans)
    if ans_is_ascii_english:
        return {
            "facet_key": "eng_vocab_word",
            "category_key": "vocab",
            "badge_label": "🔠 영단어·빈칸 인출",
        }

    front_Without_cloze = re.sub(r"\{\{c\d+::|::[^}]*\}\}|\}\}", " ", front)
    has_english_in_front = any("a" <= ch.lower() <= "z" for ch in front_Without_cloze)
    has_vocab_signal = (
        has_english_in_front
        or any(k in tags_str for k in ("eng", "vocab", "word", "toeic", "teps", "toefl", "opic", "lang", "mid1", "elem"))
        or any(k in front for k in ("영단어", "어휘", "단어", "숙어"))
    )
    if not has_vocab_signal:
        return {
            "facet_key": "general_concept",
            "category_key": "history_sci",
            "badge_label": "💡 핵심 개념·정의",
        }

    return {
        "facet_key": "eng_vocab_meaning",
        "category_key": "vocab",
        "badge_label": "📘 영단어 뜻 인출",
    }


def filter_cards_by_question_type(
    cards: Sequence[Mapping[str, Any]],
    category_filter: str = "all",
) -> List[Dict[str, Any]]:
    """Filter study queue cards by high-level question category (`all` | `vocab` | `grammar` | `hanja` | `history_sci`)."""
    norm = (category_filter or "all").strip().lower()
    if norm in ("all", "all_types", ""):
        return [dict(c) for c in cards]
    return [dict(c) for c in cards if classify_card_question_type(c)["category_key"] == norm]


def compute_question_type_counts(cards: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Compute card counts per question category (`all`, `vocab`, `grammar`, `hanja`, `history_sci`)."""
    counts = {"all": len(cards), "vocab": 0, "grammar": 0, "hanja": 0, "history_sci": 0}
    for c in cards:
        cat = classify_card_question_type(c)["category_key"]
        if cat in counts:
            counts[cat] += 1
    return counts


def build_type_matched_quiz_options(
    target_card: Mapping[str, Any],
    pool_cards: Sequence[Mapping[str, Any]],
    desired_total: int = 4,
) -> Dict[str, Any]:
    """Build 4-choice options strictly restricted to the SAME `facet_key` so grammar never leaks into vocab (T43)."""
    qtype = classify_card_question_type(target_card)
    facet_key = qtype["facet_key"]
    front = str(target_card.get("front_text") or target_card.get("front") or "")
    back = str(target_card.get("back_text") or target_card.get("back") or "")
    target_ans = _clean_concise_choice_answer(front, back, str(target_card.get("target_answer") or ""))

    distractors: List[str] = []
    seen_norm: Set[str] = {target_ans.lower().strip()}

    # 1. Pull all unique candidate answers from pool cards that have the EXACT SAME facet_key
    pool_candidates: List[str] = []
    for cand in pool_cards:
        if cand.get("card_id") == target_card.get("card_id") and cand.get("card_id") is not None:
            continue
        cand_type = classify_card_question_type(cand)
        if cand_type["facet_key"] != facet_key:
            continue
        c_front = str(cand.get("front_text") or cand.get("front") or "")
        c_back = str(cand.get("back_text") or cand.get("back") or "")
        c_ans = _clean_concise_choice_answer(c_front, c_back, str(cand.get("target_answer") or ""))
        norm_c = c_ans.lower().strip()
        if c_ans and norm_c not in seen_norm:
            seen_norm.add(norm_c)
            pool_candidates.append(c_ans)

    cid_num = 1
    raw_cid = target_card.get("card_id")
    if isinstance(raw_cid, int):
        cid_num = raw_cid
    elif raw_cid is not None:
        digits = "".join(ch for ch in str(raw_cid) if ch.isdigit())
        cid_num = int(digits) if digits else 1
    reps_num = max(0, int(target_card.get("reps") or 0))

    def _seeded_fisher_yates(items: List[str], seed_val: int) -> List[str]:
        arr = list(items)
        state = (abs(seed_val) * 1664525 + 1013904223) % 4294967296
        for idx in range(len(arr) - 1, 0, -1):
            state = (state * 1664525 + 1013904223) % 4294967296
            j = state % (idx + 1)
            arr[idx], arr[j] = arr[j], arr[idx]
        return arr

    if len(pool_candidates) > 1:
        pool_candidates = _seeded_fisher_yates(pool_candidates, cid_num * 31 + reps_num * 997 + 17)
    distractors.extend(pool_candidates[: max(0, desired_total - 1)])

    # 2. Fill remaining slots from the curated Type-Specific Fallback Bank for this exact facet_key
    fallback_bank = list(
        TYPE_FALLBACK_DISTRACTOR_BANK.get(facet_key, TYPE_FALLBACK_DISTRACTOR_BANK["eng_vocab_meaning"])
    )
    if len(fallback_bank) > 1:
        fallback_bank = _seeded_fisher_yates(fallback_bank, cid_num * 73 + reps_num * 389 + 53)
    for fb in fallback_bank:
        if len(distractors) >= desired_total - 1:
            break
        norm_fb = fb.lower().strip()
        if norm_fb not in seen_norm:
            seen_norm.add(norm_fb)
            distractors.append(fb)

    raw_options = [target_ans, *distractors[: desired_total - 1]]
    shuffled_options = _seeded_fisher_yates(raw_options, cid_num * 131 + reps_num * 521 + 2026)

    return {
        "ok": True,
        "mode": "multiple_choice",
        "question_type": qtype,
        "question_facet": qtype["badge_label"],
        "target_answer": target_ans,
        "options": shuffled_options,
    }

