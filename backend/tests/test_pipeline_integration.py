"""End-to-end integration: build_day_plan + StubCaseProvider + build_schedule.

This is the same pipeline generate_exercise runs, with the LLM stubbed out.
It guards against the wiring drifting between the three phases of work.
"""

import asyncio

from backend.casualty_planner import build_day_plan
from backend.providers.stub import StubCaseProvider
from backend.schedule_builder import build_schedule


SPECS = {
    "General Surgery": 2,
    "Orthopaedic Surgery": 1,
    "Anesthesiology": 1,
    "Emergency Medicine": 2,
    "Family Physician": 1,
    "ER Nurse": 2,
    "ICU Nurse": 1,
    "Med Surg Nurse": 1,
}


def _build_plans():
    return [
        build_day_plan(
            day_number=1,
            tactical_setting="Convoy Operations",
            total_patients=12,
            night_ops=False,
            mascal=False,
            mascal_etiology=None,
            mascal_patients=None,
            cbrn=False,
            detainee_ops=False,
            threat_level="Medium",
            environment="Desert",
            region="CENTCOM",
            selected_footprint=["FRSS Surgical Team", "Whole Blood", "ICU Holding"],
            selected_mets=["Conduct Damage Control Surgery"],
            total_waves=3,
            seed=7,
        ),
        build_day_plan(
            day_number=2,
            tactical_setting="Frontal Attack",
            total_patients=20,
            night_ops=True,
            mascal=True,
            mascal_etiology="IED/Blast",
            mascal_patients=10,
            cbrn=True,
            detainee_ops=False,
            threat_level="High",
            environment="Desert",
            region="CENTCOM",
            selected_footprint=["FRSS Surgical Team", "Whole Blood", "ICU Holding"],
            selected_mets=["Conduct Damage Control Surgery", "Manage MASCAL"],
            total_waves=3,
            seed=8,
        ),
    ]


async def _generate_cases(plans):
    provider = StubCaseProvider()
    cases_by_day = {}
    for plan in plans:
        day_cases = []
        for bucket in plan.etiology_buckets:
            for _ in range(bucket.count):
                case = await provider.generate_case(
                    case_type=bucket.etiology,
                    mechanism=bucket.etiology,
                    environment="Desert",
                    region="CENTCOM",
                    phases=bucket.phases,
                    target_triage=bucket.triage,
                )
                day_cases.append(case)
        cases_by_day[plan.day_number] = day_cases
    return cases_by_day


def test_full_pipeline_runs_clean():
    plans = _build_plans()
    cases_by_day = asyncio.run(_generate_cases(plans))

    # Each day has the right number of cases.
    for plan in plans:
        assert len(cases_by_day[plan.day_number]) == plan.total_patients

    events = build_schedule(plans, cases_by_day, specialists=SPECS, seed=99)

    # 12 + 20 clinical events plus one CBRN drill on day 2.
    drill_count = sum(1 for e in events if e.is_drill)
    clinical_count = sum(1 for e in events if not e.is_drill)
    assert drill_count == 1
    assert clinical_count == 32

    # Day-2 events stay on day 2 (no global shuffle).
    day2_events = [e for e in events if e.day_number == 2]
    assert len(day2_events) == 21  # 20 clinical + 1 drill

    # Sorting is by (day, minute).
    keys = [e._sort_key for e in events]
    assert keys == sorted(keys)

    # Every event has a stable case_id back-reference (except the drill).
    for e in events:
        if not e.is_drill:
            assert e.case_id, f"missing case_id on {e}"


def test_cbrn_drill_does_not_collide_with_arrivals():
    plans = _build_plans()
    cases_by_day = asyncio.run(_generate_cases(plans))
    events = build_schedule(plans, cases_by_day, specialists=SPECS, seed=99)

    drill = next(e for e in events if e.is_drill)
    drill_day = drill.day_number
    drill_min = drill._sort_key[1]

    for e in events:
        if e.day_number != drill_day or e.is_drill:
            continue
        # Drill window is [drill_min, drill_min + 60).
        assert not (drill_min <= e._sort_key[1] < drill_min + 60)
