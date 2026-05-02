"""
Master schedule builder.

Consumes the per-day DayPlans produced by `casualty_planner` plus the cases
generated for each day, and emits a list of ScheduleEvents suitable for the
MSEL workbook.

Fixes A1–A13 from STRATEGY.md §2:
- A1  Cases stay on their generation day. No global shuffle here.
- A2  MASCAL wave size flows through total patients without truncation.
- A3  Cross-midnight times computed from absolute minute offsets.
- A4  CBRN drill window blocks clinical waves.
- A5  Final list is sorted by (day, absolute minute) before emit.
- A6  Route selection respects triage and case category.
- A7  Evaluator selection tracks active windows so the same person isn't
       double-booked on overlapping arrivals.
- A8  Evaluator state resets per day.
- A9  Zero-pts-per-wave edge handled (waves are capped at remaining patients).
- A10 MASCAL `time_spread` scales with `mascal_patients` (capacity-aware).
- A11 Time math uses absolute minutes; the dead `arr_min >= 60` branch is gone.
- A12 CBRN drill time is configurable (defaults documented).
- A13 build_schedule() validates that case counts match plan totals.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .casualty_planner import DayPlan, EtiologyBucket


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAY_SHIFT = (7, 12 * 60)            # (start_hour_24h, total_minutes)
NIGHT_SHIFT = (19, 12 * 60)         # 1900-0700 next morning

DEFAULT_CBRN_HOUR_DAY = 9           # 0900 in day shift
DEFAULT_CBRN_HOUR_NIGHT = 21        # 2100 in night shift
CBRN_DRILL_DURATION_MIN = 60

NINE_LINE_LEAD_MIN = 30             # 9-line called ~30 min before MEDEVAC arrival

# How long a single patient ties up an evaluator at Role 2.
# DRAFT — pending SME tuning.
EVAL_DURATION_MIN = {"T1": 90, "T2": 60, "T3": 30, "T4": 20}

# Default per-wave window if MASCAL is not in play.
DEFAULT_WAVE_SPREAD_MIN = 60


# ---------------------------------------------------------------------------
# Data shape
# ---------------------------------------------------------------------------

@dataclass
class ScheduleEvent:
    day_number: int
    time: str               # arrival, "HHMM" wall clock
    nine_line_time: str     # "HHMM" or "N/A"
    route: str              # MEDEVAC | Ground | Walk-in | Litter | "N/A"
    triage_cat: str         # T1/T2/T3/T4 or "N/A" (drill)
    mechanism: str
    brief_description: str
    evaluator: str
    case_num: str
    case_id: Optional[str] = None
    is_drill: bool = False
    crosses_midnight: bool = False  # True if arrival is on the calendar day after shift start
    _sort_key: Tuple[int, int] = field(default=(0, 0), repr=False)  # (day, minutes_from_shift_start)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day_number,
            "time": self.time,
            "nine_line_time": self.nine_line_time,
            "route": self.route,
            "triage_cat": self.triage_cat,
            "mechanism": self.mechanism,
            "brief_description": self.brief_description,
            "evaluator": self.evaluator,
            "case_num": self.case_num,
            "case_id": self.case_id,
            "is_drill": self.is_drill,
            "crosses_midnight": self.crosses_midnight,
        }


# ---------------------------------------------------------------------------
# Time utilities
# ---------------------------------------------------------------------------

def shift_for(night_ops: bool) -> Tuple[int, int]:
    return NIGHT_SHIFT if night_ops else DAY_SHIFT


def minutes_to_hhmm(start_hour: int, minutes_from_shift_start: int) -> Tuple[str, bool]:
    """Return ('HHMM', crosses_midnight) for a clock time that may roll past midnight."""
    abs_minutes = start_hour * 60 + minutes_from_shift_start
    crosses = abs_minutes >= 24 * 60
    abs_minutes %= 24 * 60
    h, m = divmod(abs_minutes, 60)
    return f"{h:02d}{m:02d}", crosses


def hhmm_to_minutes_from_shift(start_hour: int, hhmm: str) -> int:
    """Inverse: 'HHMM' on the operational day → minutes from shift_start.
    Used for placing the CBRN drill at a configurable wall-clock time.
    """
    h = int(hhmm[:2])
    m = int(hhmm[2:])
    abs_minutes = h * 60 + m
    start = start_hour * 60
    if abs_minutes < start:
        # wrapped past midnight
        abs_minutes += 24 * 60
    return abs_minutes - start


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def choose_route(
    rng: random.Random,
    triage: str,
    category: str,
    is_mascal_wave: bool,
) -> str:
    """Route selection respects triage and case category (A6).

    DNBI and detainee_medical patients tend to walk in or arrive by ground.
    MASCAL trauma is heavy on litter/MEDEVAC. T1 trauma almost always MEDEVAC.
    """
    if category in ("dnbi", "detainee_medical"):
        return rng.choices(["Walk-in", "Ground"], weights=[0.6, 0.4])[0]
    if is_mascal_wave:
        return rng.choices(["MEDEVAC", "Ground", "Litter"], weights=[0.45, 0.35, 0.20])[0]
    if triage == "T1":
        return rng.choices(["MEDEVAC", "Ground"], weights=[0.85, 0.15])[0]
    if triage == "T2":
        return rng.choices(["MEDEVAC", "Ground"], weights=[0.55, 0.45])[0]
    if triage == "T3":
        return rng.choices(["Ground", "Walk-in"], weights=[0.55, 0.45])[0]
    # T4
    return rng.choices(["Walk-in", "Ground"], weights=[0.7, 0.3])[0]


# ---------------------------------------------------------------------------
# Evaluator scheduling
# ---------------------------------------------------------------------------

# Specialty priority by case category and triage. Same intent as the original
# `assign_evaluator` but expressed as data, not branchy code.

_SURGICAL_PRIORITY = ["General Surgery", "Orthopaedic Surgery", "Anesthesiology", "Emergency Medicine"]
_CRITICAL_NON_SURG = ["Emergency Medicine", "Family Physician", "ER Nurse", "ERC Nurse"]
_ROUTINE_PRIORITY = ["ICU Nurse", "Med Surg Nurse", "ER Nurse", "Family Physician"]

_SPECIALIST_ABBREV = {
    "General Surgery": "Gen Surg",
    "Orthopaedic Surgery": "Ortho",
    "Emergency Medicine": "EM",
    "Family Physician": "FP",
    "Anesthesiology": "Anes",
    "ERC Nurse": "ERC",
    "ER Nurse": "ER RN",
    "ICU Nurse": "ICU RN",
    "Med Surg Nurse": "MS RN",
}


def _priority_for(category: str, triage: str) -> List[str]:
    if "DCS" in category or category == "trauma_surgical" or category == "detainee_trauma":
        return _SURGICAL_PRIORITY
    if triage in ("T1", "T2"):
        return _CRITICAL_NON_SURG
    return _ROUTINE_PRIORITY


@dataclass
class _EvalState:
    """Per-day evaluator scheduling. Tracks which (specialty, slot) is busy
    until what minute. Slots are 1..N where N == specialists[specialty]."""

    specialists: Dict[str, int]
    busy_until: Dict[Tuple[str, int], int] = field(default_factory=dict)

    def assign(self, category: str, triage: str, arrival_min: int, duration_min: int) -> str:
        priority = _priority_for(category, triage)

        # Pass 1: walk the priority list, take the first idle slot. This is the
        # fix for A7 — without it, if the top priority's slots are all busy we
        # used to re-pick the same busy slot instead of falling through.
        for specialty in priority:
            n_slots = self.specialists.get(specialty, 0)
            for slot in range(1, n_slots + 1):
                key = (specialty, slot)
                if self.busy_until.get(key, 0) <= arrival_min:
                    self.busy_until[key] = arrival_min + duration_min
                    return f"{_SPECIALIST_ABBREV.get(specialty, specialty)} {slot}"

        # Pass 2: nothing idle anywhere in the priority list — the patient
        # queues for whichever priority slot frees up first.
        best: Optional[Tuple[str, int, int]] = None
        for specialty in priority:
            n_slots = self.specialists.get(specialty, 0)
            for slot in range(1, n_slots + 1):
                key = (specialty, slot)
                free_at = self.busy_until.get(key, 0)
                if best is None or free_at < best[2]:
                    best = (specialty, slot, free_at)
        if best is not None:
            specialty, slot, free_at = best
            self.busy_until[(specialty, slot)] = max(arrival_min, free_at) + duration_min
            return f"{_SPECIALIST_ABBREV.get(specialty, specialty)} {slot}"
        return "Unassigned"


# ---------------------------------------------------------------------------
# Wave assignment
# ---------------------------------------------------------------------------

def _split_into_waves(num_cases: int, num_waves: int) -> List[int]:
    """Distribute num_cases as evenly as possible across num_waves.

    Handles the A9 edge: if num_cases < num_waves, leading waves get 1, the rest get 0.
    """
    if num_waves <= 0:
        return [num_cases]
    base = num_cases // num_waves
    rem = num_cases % num_waves
    return [base + (1 if i < rem else 0) for i in range(num_waves)]


def _order_cases_for_day(
    plan: DayPlan,
    cases: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return cases in arrival-friendly order: MASCAL etiology first on MASCAL
    days, then trauma_surgical, trauma_non_surgical, cbrn, detainee, dnbi.

    Uses the bucket category attached on the plan to sort the matching cases.
    Cases are already aligned 1:1 with plan.etiology_buckets in order, so we
    sort by the bucket's category/etiology.
    """
    # Build (priority, bucket_idx, case) tuples.
    PRIORITY = {
        "trauma_surgical":     2,
        "trauma_non_surgical": 3,
        "cbrn_combined":       4,
        "cbrn":                5,
        "detainee_trauma":     6,
        "detainee_medical":    7,
        "dnbi":                8,
    }
    expanded_buckets: List[EtiologyBucket] = []
    for b in plan.etiology_buckets:
        expanded_buckets.extend([b] * b.count)

    if len(cases) != len(expanded_buckets):
        raise ValueError(
            f"Day {plan.day_number}: case count {len(cases)} != plan total {len(expanded_buckets)}"
        )

    decorated = []
    for idx, (bucket, case) in enumerate(zip(expanded_buckets, cases)):
        is_mascal_etiology = (
            plan.mascal
            and plan.mascal_etiology is not None
            and bucket.etiology == plan.mascal_etiology
        )
        priority = 1 if is_mascal_etiology else PRIORITY.get(bucket.category, 9)
        decorated.append((priority, idx, bucket, case))
    decorated.sort(key=lambda t: (t[0], t[1]))
    return [(b, c) for _, _, b, c in decorated]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_schedule(
    plans: List[DayPlan],
    cases_by_day: Dict[int, List[Dict[str, Any]]],
    *,
    specialists: Dict[str, int],
    cbrn_drill_time_hhmm: Optional[Dict[int, str]] = None,
    seed: Optional[int] = None,
) -> List[ScheduleEvent]:
    """Build the master schedule.

    Args:
        plans: list of DayPlan, one per exercise day.
        cases_by_day: case dicts keyed by day_number; each list is ordered to
            match `plan.etiology_buckets` expanded by count.
        specialists: counts of each specialty available at the Role 2.
        cbrn_drill_time_hhmm: optional per-day override of the CBRN drill
            wall-clock time ("HHMM"). Defaults: 0900 (day) / 2100 (night).
        seed: optional RNG seed for deterministic route selection.

    Returns:
        Sorted (by day, then arrival minute) list of ScheduleEvents.
    """
    rng = random.Random(seed if seed is not None else 0xC0FFEE)
    cbrn_drill_time_hhmm = cbrn_drill_time_hhmm or {}
    events: List[ScheduleEvent] = []

    for plan in plans:
        # ---- A13: validate case count matches plan ----
        day_cases = cases_by_day.get(plan.day_number, [])
        if len(day_cases) != plan.total_patients:
            raise ValueError(
                f"Day {plan.day_number}: provided {len(day_cases)} cases but plan "
                f"requires {plan.total_patients}"
            )

        ordered = _order_cases_for_day(plan, day_cases)
        start_hour, total_min = shift_for(plan.night_ops)

        # ---- CBRN drill block ----
        drill_start: Optional[int] = None
        drill_end: Optional[int] = None
        if plan.cbrn:
            override = cbrn_drill_time_hhmm.get(plan.day_number)
            if override:
                drill_start = hhmm_to_minutes_from_shift(start_hour, override)
            else:
                default_hour = DEFAULT_CBRN_HOUR_NIGHT if plan.night_ops else DEFAULT_CBRN_HOUR_DAY
                drill_start = hhmm_to_minutes_from_shift(start_hour, f"{default_hour:02d}00")
            drill_end = drill_start + CBRN_DRILL_DURATION_MIN

            drill_hhmm, drill_crosses = minutes_to_hhmm(start_hour, drill_start)
            events.append(ScheduleEvent(
                day_number=plan.day_number,
                time=drill_hhmm,
                nine_line_time="N/A",
                route="N/A",
                triage_cat="N/A",
                mechanism="CBRN DRILL",
                brief_description=f"{CBRN_DRILL_DURATION_MIN}-minute CBRN exercise — clinical ops paused",
                evaluator="All Hands",
                case_num="DRILL",
                is_drill=True,
                crosses_midnight=drill_crosses,
                _sort_key=(plan.day_number, drill_start),
            ))

        # ---- Wave plan ----
        # On a MASCAL day, wave 0 takes the MASCAL volume up front; remaining
        # patients distribute across waves 1..N-1 (A2: no truncation).
        num_waves = max(1, plan.total_waves)
        if plan.mascal and plan.mascal_patients:
            wave0 = min(plan.mascal_patients, plan.total_patients)
            rest = plan.total_patients - wave0
            other_waves = max(1, num_waves - 1)
            wave_sizes = [wave0] + _split_into_waves(rest, other_waves)
        else:
            wave_sizes = _split_into_waves(plan.total_patients, num_waves)

        # Wave centers evenly spaced through the shift, avoiding shift edges.
        actual_waves = len(wave_sizes)
        wave_centers = [
            int(total_min * (i + 1) / (actual_waves + 1))
            for i in range(actual_waves)
        ]

        eval_state = _EvalState(specialists=dict(specialists))  # A8: per-day reset
        cursor = 0  # index into ordered cases

        for wave_idx, (wave_center, wave_size) in enumerate(zip(wave_centers, wave_sizes)):
            if wave_size <= 0:
                continue
            is_mascal_wave = plan.mascal and wave_idx == 0 and bool(plan.mascal_patients)

            # A10: MASCAL spread scales with size (cap density at ~1 patient / 4 min).
            if is_mascal_wave:
                spread = max(15, min(90, wave_size * 4))
            else:
                spread = DEFAULT_WAVE_SPREAD_MIN

            wave_start = max(0, wave_center - spread // 2)
            wave_end = min(total_min, wave_start + spread)

            for p in range(wave_size):
                if cursor >= len(ordered):
                    break  # defensive; A13 guards against this in practice

                bucket, case = ordered[cursor]
                cursor += 1

                # Arrival minute (linear within wave window).
                if wave_size == 1:
                    arrival_min = wave_start
                else:
                    arrival_min = wave_start + int((p / max(wave_size - 1, 1)) * (wave_end - wave_start))

                # A4: shift any arrival that lands inside the CBRN drill window.
                if drill_start is not None and drill_end is not None:
                    if drill_start <= arrival_min < drill_end:
                        arrival_min = drill_end + (p * 2)  # stagger 2 min apart after drill ends
                        arrival_min = min(arrival_min, total_min - 1)

                triage = case.get("triage_category", bucket.triage)
                category = bucket.category

                route = choose_route(rng, triage, category, is_mascal_wave)

                arrival_hhmm, arr_crosses = minutes_to_hhmm(start_hour, arrival_min)

                if route == "Walk-in":
                    nine_line_time = "N/A"
                else:
                    nine_min = max(0, arrival_min - NINE_LINE_LEAD_MIN)
                    nl_hhmm, _ = minutes_to_hhmm(start_hour, nine_min)
                    nine_line_time = nl_hhmm

                duration = EVAL_DURATION_MIN.get(triage, 45)
                evaluator = eval_state.assign(category, triage, arrival_min, duration)

                events.append(ScheduleEvent(
                    day_number=plan.day_number,
                    time=arrival_hhmm,
                    nine_line_time=nine_line_time,
                    route=route,
                    triage_cat=triage,
                    mechanism=str(case.get("zmist", {}).get("mechanism", bucket.etiology))[:50],
                    brief_description=str(case.get("zmist", {}).get("injuries", bucket.etiology))[:80],
                    evaluator=evaluator,
                    case_num=case.get("case_id") or f"D{plan.day_number}-{cursor}",
                    case_id=case.get("case_id"),
                    is_drill=False,
                    crosses_midnight=arr_crosses,
                    _sort_key=(plan.day_number, arrival_min),
                ))

    # A5: stable sort by (day, minute-from-shift-start).
    events.sort(key=lambda e: e._sort_key)
    return events
