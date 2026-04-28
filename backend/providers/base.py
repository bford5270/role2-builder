"""
CaseProvider interface.

Why an interface: the long-term home of this product is AWS GovCloud, which
cannot call the public Gemini API. Bedrock-Claude (FedRAMP High / IL5) will be
the GovCloud target. Same prompts, same response shape, different transport.

Methods are async so the case_generator can fan them out via asyncio.Semaphore.
"""

from __future__ import annotations

import abc
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BatchItem:
    """One requested case in a generate_batch call.

    `key` is opaque to the provider; the case_generator uses it to map results
    back to the right (day_number, bucket_index, patient_index) slot.

    `category` is the planner bucket category (e.g. trauma_surgical, dnbi);
    providers ignore it but the fallback_factory uses it to choose the right
    template when generation fails.
    """
    key: Any
    case_type: str
    mechanism: str
    environment: str
    region: str
    phases: List[str]
    target_triage: Optional[str] = None
    category: str = ""


class CaseProvider(abc.ABC):
    """Abstract case generator. One implementation per model backend."""

    name: str = "abstract"

    @abc.abstractmethod
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
        """Return one case as a dict matching the CASE_SYSTEM_PROMPT schema."""

    @abc.abstractmethod
    async def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        """Free-text generation for WARNO / Annex Q / MEDROE."""

    async def generate_batch(self, items: List[BatchItem]) -> List[Dict[str, Any]]:
        """Generate N cases in one go.

        Default implementation fans out to generate_case in parallel. Concrete
        providers (e.g. Gemini, Bedrock) should override this to send a single
        prompt that returns a JSON array of N cases — fewer round trips.

        Returns cases in the same order as `items`. Failures bubble up as
        exceptions; the case_generator handles retry + fallback.
        """
        coros = [
            self.generate_case(
                case_type=item.case_type,
                mechanism=item.mechanism,
                environment=item.environment,
                region=item.region,
                phases=item.phases,
                target_triage=item.target_triage,
            )
            for item in items
        ]
        return await asyncio.gather(*coros)


# ---------------------------------------------------------------------------
# Stable-ID injection
# ---------------------------------------------------------------------------
# Server-side, so models can't drift on UUID format. Run on every parsed case
# in every provider.

def inject_stable_ids(case: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp UUIDs onto every assessable element of a case in place.

    The R2 Assessment Vehicle and the future tablet runner both reference
    cases and individual expected actions / contingencies / vitals points by
    ID. Generating IDs server-side guarantees uniqueness and stability across
    re-renders and re-downloads.
    """
    case.setdefault("case_id", str(uuid.uuid4()))

    phases = case.get("phases") or {}
    for phase_key in ("dcr", "dcs", "pcc"):
        phase = phases.get(phase_key)
        if not phase:
            continue
        phase.setdefault("phase_id", f"{case['case_id']}:{phase_key}")
        for action in phase.get("expected_actions") or []:
            if isinstance(action, dict):
                action.setdefault("action_id", str(uuid.uuid4()))
            # If a string, leave as-is — caller may upgrade to dict later.
        for vitals in phase.get("vitals_trend") or []:
            if isinstance(vitals, dict):
                vitals.setdefault("vitals_id", str(uuid.uuid4()))
        for cont in phase.get("contingencies") or []:
            if isinstance(cont, dict):
                cont.setdefault("contingency_id", str(uuid.uuid4()))

    return case
