"""Pure-Domain Anki v3 Study Planner, D-Day Workload Simulator & Power Scheduler.

Implements authentic Anki v3 / FSRS-5 deck management and study planning algorithms:
1. D-Day Study Planner & Multi-Day FSRS Review Cascade Simulator (`compute_anki_study_plan`)
2. Anki v3 Daily Queue Builder with Sibling Burying, Review Sort Orders & Mix Modes (`build_anki_v3_daily_queue`)
3. Overdue Backlog Catch-Up Planner (`plan_backlog_catchup`)
4. Anki Leech Detector & Auto-Suspension Policy (`evaluate_leech_status`)
5. Anki Card Browser/Reviewer Actions (`apply_anki_card_action`: Suspend, Bury, 7 Color Flags, Forget/Reset, Set Due Date)
6. Anki Custom Study / Filtered Deck Session Builder (`build_custom_study_session`)

Zero-I/O Invariant: Pure domain module with zero external I/O, DB, or network dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from anki_studio.domain.fsrs_math import compute_retrievability


ANKI_FLAG_LABELS: Dict[int, str] = {
    0: "플래그 없음",
    1: "🔴 집중 요주의 (Red)",
    2: "🟠 시험 전 재확인 (Orange)",
    3: "🟢 암기 완료 후보 (Green)",
    4: "🔵 예문·문맥 보충 (Blue)",
    5: "🩷 오답 노트 (Pink)",
    6: "🩵 발음·듣기 체크 (Turquoise)",
    7: "💜 심화·함정 변별 (Purple)",
}


@dataclass(frozen=True)
class AnkiDeckOptions:
    """Anki v3 Deck Preset Options."""

    new_per_day: int = 30
    max_reviews_per_day: int = 200
    learning_steps_mins: Tuple[int, ...] = (1, 10)
    relearning_steps_mins: Tuple[int, ...] = (10,)
    new_card_gather_order: str = "deck"  # 'deck' | 'ascending_difficulty' | 'descending_difficulty'
    new_review_mix_mode: str = "mix"  # 'mix' | 'reviews_first' | 'new_first'
    review_sort_order: str = "retrievability_asc"  # 'retrievability_asc' | 'retrievability_desc' | 'due_date_asc' | 'difficulty_desc'
    leech_threshold: int = 8
    leech_action: str = "suspend"  # 'suspend' | 'tag_only'
    bury_new_siblings: bool = True
    bury_review_siblings: bool = True
    desired_retention: float = 0.90


def _extract_concept_group(card: Mapping[str, Any]) -> str:
    """Extract sibling group identifier (`concept:<id>` tag or `note_id`) for Anki Sibling Burying."""
    note_id = str(card.get("note_id") or "").strip()
    if note_id:
        return f"note:{note_id}"
    tags = card.get("tags") or ()
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    for t in tags:
        ts = str(t).strip()
        if ts.startswith("concept:") and len(ts) > 8:
            return ts
    fact_key = str(card.get("fact_key") or "").strip()
    if fact_key:
        return f"concept:{fact_key}"
    return ""


def _card_retrievability(card: Mapping[str, Any]) -> float:
    s = float(card.get("s", card.get("stability", 0.0)) or 0.0)
    elapsed = float(card.get("elapsed_days", 0.0) or 0.0)
    if elapsed <= 0.0 and "due_days" in card:
        due_days = int(card.get("due_days") or 0)
        if due_days < 0 and s > 0.0:
            elapsed = s + abs(due_days)
        elif s > 0.0:
            elapsed = max(0.0, s - due_days)
    if s <= 0.0:
        return 0.0
    return compute_retrievability(max(0.0, elapsed), max(0.1, s))


def compute_anki_study_plan(
    total_cards: int,
    new_count: int,
    learning_count: int,
    review_due_count: int,
    target_days: int = 30,
    daily_minutes_budget: int = 30,
    desired_retention: float = 0.90,
    avg_sec_per_new: float = 18.0,
    avg_sec_per_review: float = 8.0,
    avg_sec_per_learning: float = 12.0,
) -> Dict[str, Any]:
    """Compute an Anki v3 + FSRS-5 D-Day study plan & day-by-day workload forecast for large (1,000+) decks."""
    if not isinstance(target_days, int) or target_days <= 0 or target_days > 3650:
        raise ValueError(f"target_days must be in 1..3650, got {target_days}")
    if total_cards < 0 or new_count < 0 or learning_count < 0 or review_due_count < 0:
        raise ValueError("card counts must be non-negative")
    if not math.isfinite(desired_retention) or not (0.70 <= desired_retention <= 0.99):
        raise ValueError(f"desired_retention must be in [0.70, 0.99], got {desired_retention}")
    if daily_minutes_budget <= 0:
        raise ValueError(f"daily_minutes_budget must be > 0, got {daily_minutes_budget}")

    # Reserve last ~20% (2..7 days when target_days >= 7) as pure consolidation review buffer before D-Day
    if target_days >= 7:
        consolidation_days = min(7, max(2, int(round(target_days * 0.20))))
    elif target_days >= 4:
        consolidation_days = 1
    else:
        consolidation_days = 0

    new_intake_days = max(1, target_days - consolidation_days)
    recommended_daily_new = int(math.ceil(new_count / float(new_intake_days))) if new_count > 0 else 0

    # FSRS retention interval multiplier: higher desired_retention compresses intervals and increases review load
    retention_load_factor = ((0.90 / desired_retention) ** 1.35)
    # In FSRS-5, newly learned cards trigger follow-up reviews around offsets +1d, +3d, +7d, +16d, +35d
    cascade_offsets: Tuple[Tuple[int, float], ...] = (
        (1, 0.92 * retention_load_factor),
        (3, 0.78 * retention_load_factor),
        (7, 0.65 * retention_load_factor),
        (15, 0.50 * retention_load_factor),
        (30, 0.35 * retention_load_factor),
    )

    daily_new_schedule: List[int] = []
    remaining_new = int(new_count)
    for d_idx in range(target_days):
        if d_idx < new_intake_days and remaining_new > 0:
            today_new = min(remaining_new, recommended_daily_new)
            daily_new_schedule.append(today_new)
            remaining_new -= today_new
        else:
            daily_new_schedule.append(0)
    if remaining_new > 0 and daily_new_schedule:
        daily_new_schedule[new_intake_days - 1] += remaining_new

    # Spread any existing due/backlog reviews across the first min(5, target_days) days if large
    backlog_spread_days = min(5, target_days) if review_due_count > 120 else 1
    base_mature_cards = max(0, total_cards - new_count - learning_count)

    daily_forecast: List[Dict[str, Any]] = []
    for d_idx in range(target_days):
        day_no = d_idx + 1
        n_new = daily_new_schedule[d_idx]
        n_learn = learning_count if d_idx == 0 else int(round(daily_new_schedule[max(0, d_idx - 1)] * 0.25))

        # Reviews from existing cards + backlog
        backlog_part = (
            int(math.ceil(review_due_count / float(backlog_spread_days)))
            if d_idx < backlog_spread_days
            else int(round(base_mature_cards * 0.06 * retention_load_factor))
        )

        # Reviews cascading from earlier days' new cards
        cascade_reviews = 0.0
        for offset, weight in cascade_offsets:
            src_idx = d_idx - offset
            if 0 <= src_idx < len(daily_new_schedule):
                cascade_reviews += daily_new_schedule[src_idx] * weight

        n_rev = int(round(backlog_part + cascade_reviews))
        est_seconds = (
            n_new * avg_sec_per_new
            + n_learn * avg_sec_per_learning
            + n_rev * avg_sec_per_review
        )
        est_minutes = round(est_seconds / 60.0, 1)
        phase = "consolidation_review" if d_idx >= new_intake_days else ("initial_coverage" if d_idx < new_intake_days // 2 else "deep_coverage")

        daily_forecast.append(
            {
                "day": day_no,
                "phase": phase,
                "new_cards": n_new,
                "learning_cards": n_learn,
                "review_cards": n_rev,
                "total_workload": n_new + n_learn + n_rev,
                "estimated_minutes": est_minutes,
            }
        )

    peak_daily_minutes = max((d["estimated_minutes"] for d in daily_forecast), default=0.0)
    avg_daily_minutes = round(
        sum(d["estimated_minutes"] for d in daily_forecast) / float(len(daily_forecast)),
        1,
    )
    peak_daily_reviews = max((d["review_cards"] for d in daily_forecast), default=0)

    if (
        avg_daily_minutes <= daily_minutes_budget * 1.05
        and peak_daily_minutes <= daily_minutes_budget * 1.25
        and recommended_daily_new <= 60
    ):
        status = "FEASIBLE"
    elif (
        avg_daily_minutes <= daily_minutes_budget * 1.65
        and peak_daily_minutes <= daily_minutes_budget * 2.0
        and recommended_daily_new <= 100
    ):
        status = "TIGHT_SCHEDULE"
    else:
        status = "OVERLOAD_WARNING"

    min_comfortable_days = max(
        target_days,
        int(math.ceil((new_count * avg_sec_per_new * 2.4) / max(60.0, daily_minutes_budget * 60.0))) + consolidation_days,
    )

    recommendations: List[str] = []
    if status == "FEASIBLE":
        recommendations.append(
            f"하루 새 카드 {recommended_daily_new}장 + 복습 중심(평균 {avg_daily_minutes}분/일)으로 D-{target_days} 내 안정적 완주가 가능합니다."
        )
    elif status == "TIGHT_SCHEDULE":
        recommendations.append(
            f"피크 구간 일일 학습량이 약 {peak_daily_minutes}분(목표 {daily_minutes_budget}분)에 달합니다. 주말 보충 학습(Custom Study)을 병행하세요."
        )
    else:
        recommendations.append(
            f"하루 새 카드 {recommended_daily_new}장(피크 {peak_daily_minutes}분/일)은 번아웃 위험이 큽니다. 목표 기간을 최소 {min_comfortable_days}일로 늘리거나 중요도 핵심 단원부터 분할 학습하세요."
        )
    if consolidation_days > 0:
        recommendations.append(
            f"시험 직전 마지막 {consolidation_days}일은 새 카드 진도를 멈추고(0장/일) 취약·오답 카드만 집중 인출하는 '안키 총정리 구간(Consolidation)'으로 자동 배정되었습니다."
        )

    return {
        "status": status,
        "total_cards": total_cards,
        "new_count": new_count,
        "learning_count": learning_count,
        "review_due_count": review_due_count,
        "target_days": target_days,
        "new_intake_days": new_intake_days,
        "consolidation_days": consolidation_days,
        "recommended_daily_new": recommended_daily_new,
        "recommended_max_reviews": max(200, peak_daily_reviews + 20),
        "daily_minutes_budget": daily_minutes_budget,
        "avg_daily_minutes": avg_daily_minutes,
        "peak_daily_minutes": peak_daily_minutes,
        "peak_daily_reviews": peak_daily_reviews,
        "min_comfortable_days": min_comfortable_days,
        "desired_retention": desired_retention,
        "daily_forecast": daily_forecast,
        "recommendations": recommendations,
    }


def build_anki_v3_daily_queue(
    cards: Sequence[Mapping[str, Any]],
    options: AnkiDeckOptions = AnkiDeckOptions(),
) -> Dict[str, Any]:
    """Build today's study queue following Anki v3 scheduler rules (caps, sibling burying, sort orders, mix modes)."""
    learning_bucket: List[Dict[str, Any]] = []
    review_candidates: List[Dict[str, Any]] = []
    new_candidates: List[Dict[str, Any]] = []
    suspended_ids: List[str] = []
    buried_today_ids: List[str] = []

    for raw in cards:
        c = dict(raw)
        cid = str(c.get("card_id") or c.get("id") or "")
        c["card_id"] = cid
        state = str(c.get("state") or "new").strip().lower()
        tags = [str(t).strip() for t in (c.get("tags") or ()) if str(t).strip()]
        if state == "suspended" or bool(c.get("suspended")) or "suspended" in tags:
            suspended_ids.append(cid)
            continue
        if state == "buried" or bool(c.get("buried_today")) or "buried_today" in tags:
            buried_today_ids.append(cid)
            continue

        c["retrievability"] = round(_card_retrievability(c), 4)
        c["concept_group"] = _extract_concept_group(c)

        if state in ("learning", "relearning"):
            learning_bucket.append(c)
        elif state == "review":
            due_days = int(c.get("due_days", 0) or 0)
            if due_days <= 0:
                review_candidates.append(c)
        else:
            c["state"] = "new"
            new_candidates.append(c)

    # Sort learning/relearning by due_days ascending, then lapses descending
    learning_bucket.sort(key=lambda x: (int(x.get("due_days", 0) or 0), -int(x.get("lapses", 0) or 0)))

    # Sort review candidates per Anki v3 review_sort_order
    sort_order = (options.review_sort_order or "retrievability_asc").strip().lower()
    if sort_order == "retrievability_desc":
        review_candidates.sort(key=lambda x: (-float(x["retrievability"]), int(x.get("due_days", 0) or 0)))
    elif sort_order == "due_date_asc":
        review_candidates.sort(key=lambda x: (int(x.get("due_days", 0) or 0), float(x["retrievability"])))
    elif sort_order == "difficulty_desc":
        review_candidates.sort(key=lambda x: (-float(x.get("d", x.get("difficulty", 5.0)) or 5.0), float(x["retrievability"])))
    else:
        # Default Anki FSRS Relative Overdueness: lowest retrievability first
        review_candidates.sort(key=lambda x: (float(x["retrievability"]), int(x.get("due_days", 0) or 0)))

    # Sort new candidates per new_card_gather_order
    gather_order = (options.new_card_gather_order or "deck").strip().lower()
    if gather_order == "ascending_difficulty":
        new_candidates.sort(key=lambda x: float(x.get("d", x.get("difficulty", 5.0)) or 5.0))
    elif gather_order == "descending_difficulty":
        new_candidates.sort(key=lambda x: -float(x.get("d", x.get("difficulty", 5.0)) or 5.0))

    seen_concepts: Set[str] = set()
    for lc in learning_bucket:
        cg = lc.get("concept_group") or ""
        if cg:
            seen_concepts.add(cg)

    buried_sibling_ids: List[str] = []

    selected_reviews: List[Dict[str, Any]] = []
    for rc in review_candidates:
        if len(selected_reviews) >= max(0, int(options.max_reviews_per_day)):
            break
        cg = rc.get("concept_group") or ""
        if options.bury_review_siblings and cg and cg in seen_concepts:
            buried_sibling_ids.append(rc["card_id"])
            continue
        if cg:
            seen_concepts.add(cg)
        selected_reviews.append(rc)

    selected_new: List[Dict[str, Any]] = []
    for nc in new_candidates:
        if len(selected_new) >= max(0, int(options.new_per_day)):
            break
        cg = nc.get("concept_group") or ""
        if options.bury_new_siblings and cg and cg in seen_concepts:
            buried_sibling_ids.append(nc["card_id"])
            continue
        if cg:
            seen_concepts.add(cg)
        selected_new.append(nc)

    mix_mode = (options.new_review_mix_mode or "mix").strip().lower()
    if mix_mode == "reviews_first":
        interday_queue = selected_reviews + selected_new
    elif mix_mode == "new_first":
        interday_queue = selected_new + selected_reviews
    else:
        # Interleave review and new cards evenly across the session
        interday_queue = []
        r_idx = 0
        n_idx = 0
        r_len = len(selected_reviews)
        n_len = len(selected_new)
        stride = max(1, int(round(r_len / float(max(1, n_len))))) if r_len >= n_len else 1
        while r_idx < r_len or n_idx < n_len:
            for _ in range(stride):
                if r_idx < r_len:
                    interday_queue.append(selected_reviews[r_idx])
                    r_idx += 1
            if n_idx < n_len:
                interday_queue.append(selected_new[n_idx])
                n_idx += 1

    final_queue = learning_bucket + interday_queue
    return {
        "queue": final_queue,
        "counts": {
            "learning": len(learning_bucket),
            "review": len(selected_reviews),
            "new": len(selected_new),
            "total": len(final_queue),
        },
        "buried_sibling_ids": buried_sibling_ids,
        "suspended_ids": suspended_ids,
        "buried_today_ids": buried_today_ids,
    }


def plan_backlog_catchup(
    overdue_cards: Sequence[Mapping[str, Any]],
    catchup_days: int = 7,
    regular_daily_reviews: int = 60,
    max_safe_daily_reviews: int = 150,
) -> Dict[str, Any]:
    """Create a structured Anki Backlog Catch-Up plan ordered by FSRS Retrievability urgency."""
    days = max(1, int(catchup_days))
    enriched: List[Dict[str, Any]] = []
    for raw in overdue_cards:
        c = dict(raw)
        c["card_id"] = str(c.get("card_id") or c.get("id") or "")
        c["retrievability"] = _card_retrievability(c)
        enriched.append(c)

    # Lowest retrievability (most at risk of complete forgetting) first
    enriched.sort(key=lambda x: (float(x["retrievability"]), -int(x.get("lapses", 0) or 0)))

    total_overdue = len(enriched)
    daily_quota = int(math.ceil(total_overdue / float(days))) if total_overdue > 0 else 0
    projected_daily_total = int(regular_daily_reviews) + daily_quota

    day_buckets: List[Dict[str, Any]] = []
    for d in range(days):
        slice_cards = enriched[d * daily_quota : (d + 1) * daily_quota]
        avg_r = (
            round(sum(float(x["retrievability"]) for x in slice_cards) / float(len(slice_cards)), 4)
            if slice_cards
            else 1.0
        )
        day_buckets.append(
            {
                "day": d + 1,
                "backlog_cards": len(slice_cards),
                "projected_total_reviews": int(regular_daily_reviews) + len(slice_cards),
                "avg_retrievability": avg_r,
                "card_ids": [x["card_id"] for x in slice_cards],
            }
        )

    return {
        "overdue_total": total_overdue,
        "catchup_days": days,
        "daily_backlog_quota": daily_quota,
        "regular_daily_reviews": int(regular_daily_reviews),
        "projected_daily_total": projected_daily_total,
        "within_safe_cap": projected_daily_total <= int(max_safe_daily_reviews),
        "day_buckets": day_buckets,
    }


def evaluate_leech_status(
    lapses: int,
    leech_threshold: int = 8,
    leech_action: str = "suspend",
    existing_tags: Sequence[str] = (),
) -> Dict[str, Any]:
    """Evaluate Anki Leech status after a review lapse."""
    threshold = max(2, int(leech_threshold))
    half_step = max(1, threshold // 2)
    cur_lapses = max(0, int(lapses))
    tags = [str(t).strip() for t in existing_tags if str(t).strip()]

    is_leech = cur_lapses >= threshold or ("leech" in tags)
    just_triggered = cur_lapses >= threshold and ((cur_lapses - threshold) % half_step == 0)
    action_norm = (leech_action or "suspend").strip().lower()
    should_suspend = bool(just_triggered and action_norm == "suspend")

    if is_leech and "leech" not in tags:
        tags.append("leech")
    if should_suspend and "suspended" not in tags:
        tags.append("suspended")

    coaching = (
        f"거머리 카드(Leech) 감지 ({cur_lapses}회 오답): 단서를 더 작게 쪼개거나 초성·어원 연상 힌트를 보강하세요."
        if is_leech
        else ""
    )
    return {
        "is_leech": is_leech,
        "just_triggered": just_triggered,
        "should_suspend": should_suspend,
        "lapses": cur_lapses,
        "leech_threshold": threshold,
        "tags": tags,
        "coaching_message": coaching,
    }


def apply_anki_card_action(
    card: Mapping[str, Any],
    action: str,
    *,
    flag: int = 0,
    due_days: int = 0,
) -> Dict[str, Any]:
    """Apply an Anki Reviewer/Browser action to a card state dictionary."""
    updated = dict(card)
    act = (action or "").strip().lower()
    raw_tags = updated.get("tags") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]

    if act == "set_flag":
        f_val = int(flag)
        if f_val not in ANKI_FLAG_LABELS:
            raise ValueError(f"flag must be in 0..7, got {flag}")
        tags = [t for t in tags if not t.startswith("flag:")]
        if f_val > 0:
            tags.append(f"flag:{f_val}")
        updated["flag"] = f_val
        updated["flag_label"] = ANKI_FLAG_LABELS[f_val]
    elif act == "suspend":
        if "suspended" not in tags:
            tags.append("suspended")
        updated["suspended"] = True
    elif act == "unsuspend":
        tags = [t for t in tags if t != "suspended"]
        updated["suspended"] = False
        if updated.get("state") == "suspended":
            updated["state"] = "review" if int(updated.get("reps", 0) or 0) > 0 else "new"
    elif act == "bury":
        if "buried_today" not in tags:
            tags.append("buried_today")
        updated["buried_today"] = True
    elif act == "unbury":
        tags = [t for t in tags if t != "buried_today"]
        updated["buried_today"] = False
    elif act == "forget_reset":
        tags = [t for t in tags if t not in ("leech", "suspended", "buried_today")]
        updated["state"] = "new"
        updated["reps"] = 0
        updated["lapses"] = 0
        updated["s"] = 0.0
        updated["d"] = 0.0
        updated["stability"] = 0.0
        updated["difficulty"] = 0.0
        updated["due_days"] = 0
        updated["suspended"] = False
        updated["buried_today"] = False
    elif act == "set_due_days":
        d_days = max(0, int(due_days))
        updated["due_days"] = d_days
        if updated.get("state") == "new":
            updated["state"] = "review"
            updated["s"] = max(1.0, float(d_days))
            updated["stability"] = max(1.0, float(d_days))
    else:
        raise ValueError(f"Unsupported Anki card action: {action}")

    updated["tags"] = tags
    return updated


def build_custom_study_session(
    cards: Sequence[Mapping[str, Any]],
    preset: str,
    *,
    days_ahead: int = 3,
    extra_new: int = 20,
    limit: int = 50,
    tag_filter: str = "",
) -> Dict[str, Any]:
    """Build an Anki Custom Study / Filtered Deck session."""
    preset_norm = (preset or "").strip().lower()
    cap = max(1, int(limit))
    pool: List[Dict[str, Any]] = []
    for raw in cards:
        c = dict(raw)
        c["card_id"] = str(c.get("card_id") or c.get("id") or "")
        raw_tags = c.get("tags") or []
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else [str(t).strip() for t in raw_tags if str(t).strip()]
        c["tags"] = tags
        if "suspended" in tags or c.get("state") == "suspended":
            continue
        if tag_filter and tag_filter not in tags:
            continue
        pool.append(c)

    selected: List[Dict[str, Any]] = []
    event_kind = "REVIEW"
    reschedule = True
    title = "커스텀 학습 세션"

    if preset_norm == "forgotten_recent":
        title = "🔥 최근 오답·망각 카드 집중 복습 (Forgotten Cards)"
        candidates = [
            c
            for c in pool
            if int(c.get("lapses", 0) or 0) > 0
            or int(c.get("last_rating") or 0) == 1
            or str(c.get("state") or "") == "relearning"
        ]
        candidates.sort(key=lambda x: (-int(x.get("lapses", 0) or 0), float(_card_retrievability(x))))
        selected = candidates[:cap]
        event_kind = "REVIEW"
        reschedule = True
    elif preset_norm == "review_ahead":
        title = f"⏩ 시험 대비 {days_ahead}일분 미리 복습 (Review Ahead)"
        horizon = max(1, int(days_ahead))
        candidates = [
            c
            for c in pool
            if str(c.get("state") or "") in ("review", "learning", "relearning")
            and 0 < int(c.get("due_days", 0) or 0) <= horizon
        ]
        candidates.sort(key=lambda x: (int(x.get("due_days", 0) or 0), float(_card_retrievability(x))))
        selected = candidates[:cap]
        event_kind = "REVIEW_AHEAD"
        reschedule = True
    elif preset_norm == "preview_new":
        title = "👀 새 카드 스케줄 비파괴 미리보기 (Preview New)"
        candidates = [c for c in pool if str(c.get("state") or "new") == "new"]
        selected = candidates[:cap]
        event_kind = "CRAM"
        reschedule = False
    elif preset_norm == "cram_flagged_or_leech":
        title = "🩺 플래그(🔴/🟠)·거머리(Leech) 약점 클리닉"
        candidates = [
            c
            for c in pool
            if int(c.get("flag", 0) or 0) > 0
            or "leech" in c["tags"]
            or any(t.startswith("flag:") for t in c["tags"])
        ]
        candidates.sort(key=lambda x: (-int(x.get("lapses", 0) or 0), -int(x.get("flag", 0) or 0)))
        selected = candidates[:cap]
        event_kind = "CRAM"
        reschedule = False
    elif preset_norm == "increase_new_quota":
        boost = max(1, int(extra_new))
        title = f"➕ 오늘의 새 카드 한도 +{boost}장 추가 학습"
        candidates = [c for c in pool if str(c.get("state") or "new") == "new"]
        selected = candidates[: min(cap, boost)]
        event_kind = "REVIEW"
        reschedule = True
    else:
        raise ValueError(f"Unsupported custom study preset: {preset}")

    return {
        "preset": preset_norm,
        "title": title,
        "event_kind": event_kind,
        "reschedule": reschedule,
        "count": len(selected),
        "cards": selected,
    }
