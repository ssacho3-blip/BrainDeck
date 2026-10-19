"""Pure-Domain FSRS-5 (DSR Memory Model) Scheduler & Cloze Parser.

Clean-Room implementation based strictly on the published FSRS-5 / DSR
(Difficulty, Stability, Retrievability) mathematical equations.
Zero external I/O (no sqlite3, http, socket, subprocess, or filesystem access).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import math
import re
from typing import Dict, List, Sequence, Tuple


# Power-law forgetting curve constants:
# R(t, S) = (1 + F * (t / S)) ** C, calibrated so R(S, S) = 0.90.
FSRS_FACTOR_F: float = 19.0 / 81.0
FSRS_DECAY_C: float = -0.5

# Standard FSRS-5 19-parameter default weight vector (published open benchmark weights)
DEFAULT_FSRS5_WEIGHTS: Tuple[float, ...] = (
    0.40255,   # w0: initial stability for Again (1)
    1.18385,   # w1: initial stability for Hard (2)
    3.17300,   # w2: initial stability for Good (3)
    15.69105,  # w3: initial stability for Easy (4)
    7.19490,   # w4: initial difficulty base
    0.53450,   # w5: initial difficulty exponential slope
    1.46040,   # w6: difficulty delta rate
    0.00460,   # w7: difficulty mean-reversion weight toward D0(4)
    1.54575,   # w8: recall stability gain exponent
    0.11920,   # w9: recall stability saturation power
    1.01925,   # w10: recall retrievability bonus slope
    1.93950,   # w11: forget stability base
    0.11000,   # w12: forget difficulty power
    0.29605,   # w13: forget stability power
    2.26980,   # w14: forget retrievability slope
    0.23150,   # w15: Hard penalty factor (< 1)
    2.98980,   # w16: Easy bonus factor (> 1)
    0.51655,   # w17: short-term stability slope
    0.66210,   # w18: short-term rating offset
)


class Rating(IntEnum):
    """4-grade active recall rating."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


@dataclass(frozen=True)
class CardMemoryState:
    """Immutable DSR memory state of a single card."""

    difficulty: float = 0.0
    stability: float = 0.0
    reps: int = 0
    lapses: int = 0
    state: str = "new"  # 'new' | 'learning' | 'review' | 'relearning'


@dataclass(frozen=True)
class ReviewOutcome:
    """Computed next memory state and interval after a single review."""

    rating: Rating
    memory: CardMemoryState
    retrievability_before: float
    scheduled_days: int
    scheduled_label: str


def _clamp(value: float, low: float, high: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"Non-finite value encountered in FSRS calculation: {value}")
    return max(low, min(high, value))


def compute_retrievability(elapsed_days: float, stability: float) -> float:
    """Compute memory retrievability R(t, S) in (0.0, 1.0].

    At elapsed_days == 0, R = 1.0.
    At elapsed_days == stability, R = 0.90.
    """
    if not math.isfinite(elapsed_days) or not math.isfinite(stability):
        raise ValueError("elapsed_days and stability must be finite numbers")
    if stability <= 0.0:
        return 0.0
    if elapsed_days <= 0.0:
        return 1.0
    r = (1.0 + FSRS_FACTOR_F * (elapsed_days / stability)) ** FSRS_DECAY_C
    return _clamp(r, 0.0001, 1.0)


def compute_next_interval(
    stability: float,
    desired_retention: float = 0.90,
    maximum_interval: int = 36500,
) -> int:
    """Compute optimal integer review interval I(S, R_req) in days."""
    if not math.isfinite(stability) or stability <= 0.0:
        raise ValueError(f"stability must be positive and finite, got {stability}")
    if not math.isfinite(desired_retention) or not (0.70 <= desired_retention <= 0.99):
        raise ValueError(f"desired_retention must be in [0.70, 0.99], got {desired_retention}")

    raw_interval = (stability / FSRS_FACTOR_F) * ((desired_retention ** (1.0 / FSRS_DECAY_C)) - 1.0)
    days = int(round(raw_interval))
    return max(1, min(maximum_interval, days))


def _initial_stability(rating: Rating, w: Sequence[float]) -> float:
    return max(0.1, float(w[int(rating) - 1]))


def _initial_difficulty(rating: Rating, w: Sequence[float]) -> float:
    # FSRS-5 initial difficulty: D0(G) = clip(w4 - exp(w5 * (G - 1)) + 1, 1, 10)
    d0 = w[4] - math.exp(w[5] * (int(rating) - 1.0)) + 1.0
    return _clamp(d0, 1.0, 10.0)


def _next_difficulty(d: float, rating: Rating, w: Sequence[float]) -> float:
    delta_d = -w[6] * (int(rating) - 3.0)
    d_damped = d + delta_d * ((10.0 - d) / 9.0)
    d0_easy = _initial_difficulty(Rating.EASY, w)
    # Mean reversion toward D0(4) prevents permanent Ease Hell
    d_next = w[7] * d0_easy + (1.0 - w[7]) * d_damped
    return _clamp(d_next, 1.0, 10.0)


def _next_recall_stability(
    d: float,
    s: float,
    r: float,
    rating: Rating,
    w: Sequence[float],
) -> float:
    hard_penalty = w[15] if rating == Rating.HARD else 1.0
    easy_bonus = w[16] if rating == Rating.EASY else 1.0
    inc = (
        math.exp(w[8])
        * (11.0 - d)
        * (s ** (-w[9]))
        * (math.exp(w[10] * (1.0 - r)) - 1.0)
        * hard_penalty
        * easy_bonus
    )
    return _clamp(s * (1.0 + inc), 0.1, 36500.0)


def _next_forget_stability(
    d: float,
    s: float,
    r: float,
    w: Sequence[float],
) -> float:
    s_f = (
        w[11]
        * (d ** (-w[12]))
        * (((s + 1.0) ** w[13]) - 1.0)
        * math.exp(w[14] * (1.0 - r))
    )
    return _clamp(min(s, s_f), 0.1, 36500.0)


def step_fsrs(
    memory: CardMemoryState,
    rating: Rating | int,
    elapsed_days: float = 0.0,
    desired_retention: float = 0.90,
    weights: Sequence[float] = DEFAULT_FSRS5_WEIGHTS,
) -> ReviewOutcome:
    """Advance card memory state by one review event using FSRS-5 equations."""
    grade = Rating(int(rating))
    if len(weights) < 19:
        raise ValueError(f"FSRS-5 requires 19 weights, got {len(weights)}")
    if elapsed_days < 0.0 or not math.isfinite(elapsed_days):
        raise ValueError(f"elapsed_days must be non-negative and finite, got {elapsed_days}")

    # First-time review of a brand-new card
    if memory.state == "new" or memory.reps <= 0 or memory.stability <= 0.0:
        d_new = _initial_difficulty(grade, weights)
        s_new = _initial_stability(grade, weights)
        if grade == Rating.AGAIN:
            next_state = "learning"
            scheduled_days = 0
            label = "10m"
        elif grade == Rating.HARD:
            next_state = "learning"
            scheduled_days = 1
            label = "1d"
        else:
            next_state = "review"
            scheduled_days = compute_next_interval(s_new, desired_retention)
            label = f"{scheduled_days}d"

        return ReviewOutcome(
            rating=grade,
            memory=CardMemoryState(
                difficulty=round(d_new, 4),
                stability=round(s_new, 4),
                reps=memory.reps + 1,
                lapses=memory.lapses,
                state=next_state,
            ),
            retrievability_before=1.0,
            scheduled_days=scheduled_days,
            scheduled_label=label,
        )

    # Subsequent review of an existing card
    r_now = compute_retrievability(elapsed_days, memory.stability)
    d_next = _next_difficulty(memory.difficulty, grade, weights)

    if grade == Rating.AGAIN:
        s_next = _next_forget_stability(memory.difficulty, memory.stability, r_now, weights)
        next_state = "relearning"
        scheduled_days = 0
        label = "10m"
        lapses = memory.lapses + 1
    else:
        s_next = _next_recall_stability(memory.difficulty, memory.stability, r_now, grade, weights)
        next_state = "review"
        scheduled_days = compute_next_interval(s_next, desired_retention)
        label = f"{scheduled_days}d"
        lapses = memory.lapses

    return ReviewOutcome(
        rating=grade,
        memory=CardMemoryState(
            difficulty=round(d_next, 4),
            stability=round(s_next, 4),
            reps=memory.reps + 1,
            lapses=lapses,
            state=next_state,
        ),
        retrievability_before=round(r_now, 4),
        scheduled_days=scheduled_days,
        scheduled_label=label,
    )


def preview_all_ratings(
    memory: CardMemoryState,
    elapsed_days: float = 0.0,
    desired_retention: float = 0.90,
    weights: Sequence[float] = DEFAULT_FSRS5_WEIGHTS,
) -> Dict[str, ReviewOutcome]:
    """Return outcomes for all 4 buttons (again, hard, good, easy) for UI preview."""
    return {
        "again": step_fsrs(memory, Rating.AGAIN, elapsed_days, desired_retention, weights),
        "hard": step_fsrs(memory, Rating.HARD, elapsed_days, desired_retention, weights),
        "good": step_fsrs(memory, Rating.GOOD, elapsed_days, desired_retention, weights),
        "easy": step_fsrs(memory, Rating.EASY, elapsed_days, desired_retention, weights),
    }


def forecast_forgetting_curve(
    stability: float,
    horizon_days: int = 30,
) -> List[Dict[str, float]]:
    """Generate daily retrievability curve points for visualization."""
    if stability <= 0.0:
        return [{"day": float(d), "retrievability": 0.0} for d in range(horizon_days + 1)]
    return [
        {
            "day": float(d),
            "retrievability": round(compute_retrievability(float(d), stability), 4),
        }
        for d in range(horizon_days + 1)
    ]


# Cloze Deletion Parser: {{c1::answer::optional_hint}}
_CLOZE_PATTERN = re.compile(r"\{\{c(\d+)::([^}:]+)(?:::([^}]+))?\}\}")


def extract_cloze_ordinals(text: str) -> List[int]:
    """Extract sorted unique Cloze deletion indices (e.g. [1, 2]) from note text."""
    ordinals = {int(match.group(1)) for match in _CLOZE_PATTERN.finditer(text or "") if int(match.group(1)) > 0}
    return sorted(ordinals)


def render_cloze_card(text: str, active_ordinal: int, reveal: bool = False) -> str:
    """Render a Cloze deletion note for a specific ordinal as question (reveal=False) or answer (reveal=True)."""
    if active_ordinal <= 0:
        raise ValueError(f"active_ordinal must be >= 1, got {active_ordinal}")

    def _replacer(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        answer = match.group(2).strip()
        hint = (match.group(3) or "").strip()
        if idx == active_ordinal:
            if reveal:
                return f"【{answer}】"
            placeholder = hint if hint else "..."
            return f"[{placeholder}]"
        return answer

    return _CLOZE_PATTERN.sub(_replacer, text or "")


def detect_leech_severity(reps: int, lapses: int, difficulty: float) -> str:
    """Classify card leech status based on lapses and difficulty.

    Returns 'healthy', 'warning', or 'critical_leech'.
    """
    if lapses < 0 or reps < 0 or not math.isfinite(difficulty):
        raise ValueError("Invalid parameters for leech detection")
    if lapses >= 4 or (lapses >= 2 and difficulty >= 8.5):
        return "critical_leech"
    if lapses >= 2:
        return "warning"
    return "healthy"


def plan_backlog_decompression(
    overdue_cards: Sequence[Dict[str, float | int]],
    daily_cap: int = 30,
    horizon_days: int = 7,
) -> List[Dict[str, int | float]]:
    """Redistribute a review backlog smoothly across `horizon_days` without exceeding `daily_cap`.

    Solves legacy Anki's 'post-vacation review bomb' by prioritizing cards with the
    lowest current retrievability R(t, S) (highest forgetting risk) on Day 0, while
    deferring higher-stability cards across subsequent days.
    """
    if daily_cap <= 0:
        raise ValueError(f"daily_cap must be >= 1, got {daily_cap}")
    if horizon_days <= 0:
        raise ValueError(f"horizon_days must be >= 1, got {horizon_days}")

    scored: List[Tuple[float, int, Dict[str, float | int]]] = []
    for item in overdue_cards:
        cid = int(item["card_id"])
        elapsed = max(0.0, float(item.get("elapsed_days", 0.0)))
        stability = max(0.1, float(item.get("stability", 1.0)))
        lapses = max(0, int(item.get("lapses", 0)))
        r_now = compute_retrievability(elapsed, stability)
        # Lower retrievability + higher lapses = more urgent (smaller sort key)
        urgency_key = r_now - min(0.15, lapses * 0.03)
        scored.append((urgency_key, cid, item))

    scored.sort(key=lambda x: (x[0], x[1]))

    plan: List[Dict[str, int | float]] = []
    for idx, (_, cid, item) in enumerate(scored):
        day_offset = min(horizon_days - 1, idx // daily_cap)
        elapsed = max(0.0, float(item.get("elapsed_days", 0.0)))
        stability = max(0.1, float(item.get("stability", 1.0)))
        plan.append(
            {
                "card_id": cid,
                "day_offset": int(day_offset),
                "retrievability": round(compute_retrievability(elapsed, stability), 4),
            }
        )
    return plan

