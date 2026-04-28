"""Deterministic StubCaseProvider for tests and offline development.

Returns the same structure the real models produce, derived from the inputs.
Lets the rest of the system be tested without an LLM.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from .base import CaseProvider, inject_stable_ids


def _zap_for(seed: str) -> str:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return f"{(h % 90000) + 10000:05d}"


class StubCaseProvider(CaseProvider):
    name = "stub"

    async def generate_case(
        self,
        *,
        case_type: str,
        mechanism: str,
        environment: str,
        region: str,
        phases: List[str],
        target_triage: Optional[str] = None,
    ) -> Dict[str, Any]:
        triage = target_triage or "T2"
        zap = _zap_for(f"{case_type}|{mechanism}|{environment}|{region}|{triage}")
        case: Dict[str, Any] = {
            "meta": {
                "title": case_type,
                "estimated_duration": "30 min",
                "personnel": "Medical team",
                "target_specialty": "Emergency Medicine",
            },
            "learning_objectives": [
                "Stub objective 1",
                "Stub objective 2",
                "Stub objective 3",
            ],
            "zmist": {
                "zap": zap,
                "mechanism": mechanism,
                "injuries": case_type,
                "signs": "Stub vitals",
                "treatment": "Stub initial Tx",
            },
            "nine_line": {f"line{i}_x": "stub" for i in range(1, 10)},
            "patient_data": {"demographics": "Stub", "history": "Stub", "allergies": "NKDA"},
            "triage_category": triage,
            "phases": {
                "dcr": {
                    "title": "Damage Control Resuscitation",
                    "narrative": "Stub DCR.",
                    "expected_actions": [{"text": "Primary survey"}, {"text": "IV access"}],
                    "vitals_trend": [{"time": "0:00", "hr": "100", "bp": "110/70"}],
                    "contingencies": [{"condition": "BP<90", "consequence": "shock", "intervention": "blood"}],
                },
                "dcs": (
                    {
                        "title": "Damage Control Surgery",
                        "narrative": "Stub DCS.",
                        "expected_actions": [{"text": "Laparotomy"}],
                        "vitals_trend": [{"time": "0:30", "hr": "110", "bp": "100/60"}],
                        "contingencies": [],
                    }
                    if "DCS" in phases
                    else None
                ),
                "pcc": {
                    "title": "Prolonged Casualty Care",
                    "narrative": "Stub PCC.",
                    "expected_actions": [{"text": "Reassess"}],
                    "vitals_trend": [{"time": "1:00", "hr": "95", "bp": "115/72"}],
                    "contingencies": [],
                },
            },
            "labs": {"hgb": "11.0", "ph": "7.32", "lactate": "2.5", "base_excess": "-3", "inr": "1.1"},
            "evacuation": {
                "transport_type": "MEDEVAC",
                "priority": "Priority",
                "considerations": "Stub",
                "handover_notes": "Stub",
            },
            "debrief_questions": ["Stub q1?", "Stub q2?", "Stub q3?", "Stub q4?"],
        }
        return inject_stable_ids(case)

    async def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        return f"[stub-text] {prompt[:80]}"
