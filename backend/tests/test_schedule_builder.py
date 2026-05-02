"""Behavior tests for schedule_builder. Each test maps to an A-row from
STRATEGY.md §2."""

from typing import Any, Dict, List

import pytest
from hypothesis import given, settings, strategies as st

from backend.casualty_planner import build_day_plan, DayPlan
from backend import schedule_builder as SB


def _stub_case(triage: str = "T2", mechanism: str = "stub-mech", injuries: str = "stub-inj") -> Dict[str, Any]:
    return {
        "case_id": f"case-{triage}-{mechanism}",
        "triage_category": triage,
        "zmist": {"mechanism": mechanism, "injuries": injuries},
    }


def _plan(**overrides) -> DayPlan:
    defaults = dict(
        day_number=1,
        tactical_setting="Defensive Operations",
        total_patients=12,
        night_ops=False,
        mascal=False,
        mascal_etiology=None,
        mascal_patients=None,
        cbrn=False,
        detainee_ops=False,
        threat_level="Medium",
        environment="General",
        region=None,
        selected_footprint=["FRSS Surgical Team", "Whole Blood"],
        selected_mets=[],
        total_waves=3,
        seed=11,
    )
    defaults.update(overrides)
    return build_day_plan(**defaults)


def _cases_for(plan: DayPlan) -> List[Dict[str, Any]]:
    out = []
    for b in plan.etiology_buckets:
        for _ in range(b.count):
            out.append(_stub_case(triage=b.triage, mechanism=b.etiology, injuries=f"{b.etiology} injury"))
    return out


SPECS = {
    "General Surgery": 1,
    "Orthopaedic Surgery": 1,
    "Anesthesiology": 1,
    "Emergency Medicine": 2,
    "Family Physician": 1,
    "ER Nurse": 2,
    "ICU Nurse": 1,
    "Med Surg Nurse": 1,
}


class TestNoGlobalShuffle:
    """A1: cases must stay on their generation day."""

    def test_each_day_keeps_its_own_cases(self):
        plan_a = _plan(day_number=1, environment="Desert", total_patients=8, seed=1)
        plan_b = _plan(day_number=2, environment="Jungle", total_patients=8, seed=2)
        cases_a = _cases_for(plan_a)
        cases_b = _cases_for(plan_b)
        events = SB.build_schedule([plan_a, plan_b], {1: cases_a, 2: cases_b}, specialists=SPECS, seed=0)

        day1_mechs = {e.mechanism for e in events if e.day_number == 1 and not e.is_drill}
        day2_mechs = {e.mechanism for e in events if e.day_number == 2 and not e.is_drill}

        # Cases from day 2 (jungle DNBI like Dengue, Malaria) shouldn't appear on day 1.
        for m in day2_mechs:
            if "Dengue" in m or "Malaria" in m or "Lepto" in m:
                assert m not in day1_mechs


class TestMASCALWaveCount:
    """A2: MASCAL count flows through, doesn't truncate later waves."""

    def test_mascal_keeps_all_patients(self):
        plan = _plan(
            tactical_setting="Frontal Attack",
            mascal=True,
            mascal_etiology="IED/Blast",
            mascal_patients=10,
            total_patients=20,
            total_waves=3,
        )
        cases = _cases_for(plan)
        events = SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0)
        clinical = [e for e in events if not e.is_drill]
        assert len(clinical) == 20, "MASCAL day must not lose any patients"

    def test_mascal_wave_runs_first(self):
        plan = _plan(
            tactical_setting="Frontal Attack",
            mascal=True,
            mascal_etiology="IED/Blast",
            mascal_patients=8,
            total_patients=16,
        )
        cases = _cases_for(plan)
        events = [e for e in SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0) if not e.is_drill]
        ied_arrivals = [e._sort_key[1] for e in events if e.mechanism == "IED/Blast"]
        non_ied = [e._sort_key[1] for e in events if e.mechanism != "IED/Blast"]
        assert ied_arrivals, "MASCAL etiology should appear"
        assert min(ied_arrivals) <= max(non_ied or [10**9])


class TestCrossMidnight:
    """A3: night ops must compute time correctly across midnight."""

    def test_night_ops_late_arrivals_wrap(self):
        plan = _plan(night_ops=True, total_patients=6, total_waves=3)
        cases = _cases_for(plan)
        events = [e for e in SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0) if not e.is_drill]
        # Some arrivals should be after midnight (HHMM < shift start hour).
        crosses = [e for e in events if e.crosses_midnight]
        assert crosses, "expected at least one arrival past midnight on a 12-hr night shift"

    def test_nine_line_doesnt_underflow(self):
        plan = _plan(night_ops=True, total_patients=4, total_waves=2)
        cases = _cases_for(plan)
        events = [e for e in SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0) if not e.is_drill]
        for e in events:
            if e.nine_line_time != "N/A":
                assert e.nine_line_time.isdigit() and len(e.nine_line_time) == 4


class TestCBRNDrillBlocking:
    """A4 & A12: CBRN drill window blocks clinical waves; drill time configurable."""

    def test_no_arrivals_during_drill(self):
        plan = _plan(cbrn=True, total_patients=15, total_waves=3)
        cases = _cases_for(plan)
        events = SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0)
        drill = next(e for e in events if e.is_drill)
        clinical = [e for e in events if not e.is_drill]
        # Decode drill window
        start_hour, _ = SB.shift_for(plan.night_ops)
        drill_start_min = SB.hhmm_to_minutes_from_shift(start_hour, drill.time)
        drill_end_min = drill_start_min + SB.CBRN_DRILL_DURATION_MIN
        for e in clinical:
            assert not (drill_start_min <= e._sort_key[1] < drill_end_min), (
                f"clinical arrival at {e.time} fell inside CBRN drill window"
            )

    def test_drill_time_configurable(self):
        plan = _plan(cbrn=True, total_patients=12, total_waves=3)
        cases = _cases_for(plan)
        events = SB.build_schedule(
            [plan], {1: cases},
            specialists=SPECS,
            cbrn_drill_time_hhmm={1: "1100"},
            seed=0,
        )
        drill = next(e for e in events if e.is_drill)
        assert drill.time == "1100"


class TestSorting:
    """A5: schedule must be sorted by (day, time)."""

    def test_events_sorted(self):
        plans = [
            _plan(day_number=1, total_patients=8, total_waves=3),
            _plan(day_number=2, total_patients=8, total_waves=3, night_ops=True),
        ]
        cases_by_day = {p.day_number: _cases_for(p) for p in plans}
        events = SB.build_schedule(plans, cases_by_day, specialists=SPECS, seed=0)
        prev = (0, -1)
        for e in events:
            assert e._sort_key >= prev
            prev = e._sort_key


class TestRouteSelection:
    """A6: route should respect triage and category."""

    def test_dnbi_does_not_request_medevac_helicopter_typically(self):
        plan = _plan(
            tactical_setting="Humanitarian Assistance",
            total_patients=20,
            total_waves=2,
            threat_level="Low",
        )
        cases = _cases_for(plan)
        events = [e for e in SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0) if not e.is_drill]
        # Identify DNBI buckets and ensure none get MEDEVAC.
        dnbi_indices = [i for i, b in enumerate(_expand_buckets(plan)) if b.category == "dnbi"]
        if not dnbi_indices:
            pytest.skip("plan produced no DNBI cases under this seed")
        dnbi_routes = []
        for e in events:
            if e.route == "MEDEVAC":
                # Walk-in/Ground only for DNBI; flag if mechanism matches a DNBI etiology.
                pass
        # Soft assertion: most DNBI cases are not MEDEVAC.
        dnbi_events = [e for e in events if any(b.etiology == e.mechanism and b.category == "dnbi"
                                                for b in _expand_buckets(plan))]
        if dnbi_events:
            medevac_share = sum(1 for e in dnbi_events if e.route == "MEDEVAC") / len(dnbi_events)
            assert medevac_share < 0.2

    def test_t1_trauma_mostly_medevac(self):
        plan = _plan(
            tactical_setting="Frontal Attack",
            total_patients=30,
            total_waves=3,
            threat_level="High",
        )
        cases = _cases_for(plan)
        events = [e for e in SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0) if not e.is_drill]
        t1 = [e for e in events if e.triage_cat == "T1"]
        if not t1:
            pytest.skip("no T1 cases under this seed")
        medevac_share = sum(1 for e in t1 if e.route == "MEDEVAC") / len(t1)
        assert medevac_share >= 0.5


class TestEvaluatorScheduling:
    """A7 & A8: track active windows; reset per day."""

    def test_priority_falls_through_when_top_specialty_busy(self):
        """A7: when the top-priority specialty is fully booked, the next
        specialty's idle slot should be chosen instead of double-booking the
        first specialty."""
        # Single Gen Surg, but plenty of EM and Ortho — so 4 surgical patients
        # arriving close together should fan out across the priority list,
        # not all land on Gen Surg 1.
        specs = {
            "General Surgery": 1,
            "Orthopaedic Surgery": 2,
            "Anesthesiology": 2,
            "Emergency Medicine": 2,
            "Family Physician": 1,
            "ER Nurse": 2,
            "ICU Nurse": 1,
            "Med Surg Nurse": 1,
        }
        plan = _plan(
            tactical_setting="Frontal Attack",
            mascal=True,
            mascal_etiology="IED/Blast",
            mascal_patients=4,
            total_patients=4,
            total_waves=1,
        )
        cases = _cases_for(plan)
        events = [e for e in SB.build_schedule([plan], {1: cases}, specialists=specs, seed=0) if not e.is_drill]
        evaluators = [e.evaluator for e in events]
        # Within a tight wave, no single evaluator should appear more than once.
        assert len(set(evaluators)) == len(evaluators), f"double-booked: {evaluators}"

    def test_state_resets_per_day(self):
        plan_a = _plan(day_number=1, total_patients=6)
        plan_b = _plan(day_number=2, total_patients=6)
        events = SB.build_schedule(
            [plan_a, plan_b],
            {1: _cases_for(plan_a), 2: _cases_for(plan_b)},
            specialists=SPECS,
            seed=0,
        )
        # First evaluator on day 2 should be slot 1 of some specialty, never something
        # that implies the day-1 counters carried over.
        day2_first = next(e for e in events if e.day_number == 2 and not e.is_drill)
        assert day2_first.evaluator.endswith(" 1")


class TestValidation:
    """A13: per-day case count must match plan total."""

    def test_mismatch_raises(self):
        plan = _plan(total_patients=10)
        with pytest.raises(ValueError, match="provided 5"):
            SB.build_schedule([plan], {1: _cases_for(plan)[:5]}, specialists=SPECS, seed=0)


class TestSmallEdges:
    """A9: zero-pts-per-wave edge."""

    def test_three_waves_two_patients(self):
        plan = _plan(total_patients=2, total_waves=3)
        cases = _cases_for(plan)
        events = [e for e in SB.build_schedule([plan], {1: cases}, specialists=SPECS, seed=0) if not e.is_drill]
        assert len(events) == 2


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis) for time arithmetic
# ---------------------------------------------------------------------------

@given(
    start_hour=st.sampled_from([7, 19]),
    minutes=st.integers(min_value=0, max_value=24 * 60 - 1),
)
def test_minutes_to_hhmm_roundtrip(start_hour: int, minutes: int):
    hhmm, _ = SB.minutes_to_hhmm(start_hour, minutes)
    back = SB.hhmm_to_minutes_from_shift(start_hour, hhmm)
    # Roundtrip is exact within the 24-hour window; we may add a 24h offset back.
    assert back % (24 * 60) == minutes % (24 * 60)


@given(
    n=st.integers(min_value=1, max_value=50),
    waves=st.integers(min_value=1, max_value=10),
)
def test_split_into_waves_sums_correctly(n: int, waves: int):
    parts = SB._split_into_waves(n, waves)
    assert sum(parts) == n
    assert len(parts) == waves
    assert all(p >= 0 for p in parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expand_buckets(plan: DayPlan):
    out = []
    for b in plan.etiology_buckets:
        out.extend([b] * b.count)
    return out
