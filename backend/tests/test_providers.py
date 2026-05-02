"""Tests for the CaseProvider abstraction and stable-ID injection."""

import asyncio
import re

import pytest

from backend.providers.base import inject_stable_ids
from backend.providers.stub import StubCaseProvider


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class TestStableIDs:
    def test_injects_case_id(self):
        case = inject_stable_ids({"phases": {}})
        assert UUID_RE.match(case["case_id"])

    def test_idempotent(self):
        case = inject_stable_ids({"phases": {}})
        original = case["case_id"]
        inject_stable_ids(case)
        assert case["case_id"] == original

    def test_stamps_actions_contingencies_vitals(self):
        case = inject_stable_ids({
            "phases": {
                "dcr": {
                    "expected_actions": [{"text": "primary survey"}, {"text": "iv"}],
                    "vitals_trend": [{"time": "0:00", "hr": "100"}, {"time": "0:05", "hr": "110"}],
                    "contingencies": [{"condition": "BP<90"}],
                },
                "dcs": None,
                "pcc": {"expected_actions": [{"text": "reassess"}]},
            }
        })
        dcr = case["phases"]["dcr"]
        assert all(UUID_RE.match(a["action_id"]) for a in dcr["expected_actions"])
        assert all(UUID_RE.match(v["vitals_id"]) for v in dcr["vitals_trend"])
        assert all(UUID_RE.match(c["contingency_id"]) for c in dcr["contingencies"])
        assert dcr["phase_id"].endswith(":dcr")

    def test_skips_string_actions(self):
        # Older fallback uses strings — shouldn't crash.
        case = inject_stable_ids({
            "phases": {"dcr": {"expected_actions": ["primary survey", "iv"]}}
        })
        assert case["phases"]["dcr"]["expected_actions"] == ["primary survey", "iv"]


class TestStubProvider:
    def test_round_trip(self):
        provider = StubCaseProvider()
        case = asyncio.run(provider.generate_case(
            case_type="Penetrating chest trauma",
            mechanism="GSW/Small Arms",
            environment="Desert",
            region="CENTCOM",
            phases=["DCR", "DCS", "PCC"],
            target_triage="T1",
        ))
        assert case["triage_category"] == "T1"
        assert case["phases"]["dcs"] is not None
        assert UUID_RE.match(case["case_id"])
        assert case["zmist"]["zap"].isdigit() and len(case["zmist"]["zap"]) == 5

    def test_no_dcs_when_phase_excluded(self):
        provider = StubCaseProvider()

        async def run():
            return await provider.generate_case(
                case_type="Heat stroke",
                mechanism="DNBI - Desert",
                environment="Desert",
                region="CENTCOM",
                phases=["DCR", "PCC"],
            )

        case = asyncio.run(run())
        assert case["phases"]["dcs"] is None
