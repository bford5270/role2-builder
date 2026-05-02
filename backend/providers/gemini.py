"""Gemini implementation of CaseProvider.

Wraps the existing google.genai client. Same prompts as before, just behind
the interface so we can swap to Bedrock for GovCloud without touching callers.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from google import genai

from ..prompts import CASE_SYSTEM_PROMPT, case_batch_prompt, case_user_prompt
from .base import BatchItem, CaseProvider, inject_stable_ids

_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Per-request timeout. The Gemini SDK's HTTP layer has its own timeout, but
# it has been observed to stall silently on intermittent service issues —
# leaving the to_thread call hanging forever, which would in turn deadlock
# the worker's asyncio.gather across batches. asyncio.wait_for guarantees a
# stalled call surfaces as TimeoutError, which the retry layer catches and
# eventually rolls into a fallback case.
_REQUEST_TIMEOUT_S = float(os.getenv("GEMINI_REQUEST_TIMEOUT_S", "60"))


class GeminiCaseProvider(CaseProvider):
    name = "gemini"

    def __init__(self, client: Optional[genai.Client] = None):
        self._client = client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
        prompt = case_user_prompt(
            case_type=case_type,
            mechanism=mechanism,
            environment=environment,
            region=region,
            phases=phases,
            target_triage=target_triage,
        )
        response = await asyncio.wait_for(
            asyncio.to_thread(
                self._client.models.generate_content,
                model=_MODEL,
                contents=prompt,
                config={
                    "system_instruction": CASE_SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                },
            ),
            timeout=_REQUEST_TIMEOUT_S,
        )
        case = _parse_json(response.text)
        if target_triage:
            case["triage_category"] = target_triage
        return inject_stable_ids(case)

    async def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        config = {"system_instruction": system} if system else None
        response = await asyncio.wait_for(
            asyncio.to_thread(
                self._client.models.generate_content,
                model=_MODEL,
                contents=prompt,
                config=config,
            ),
            timeout=_REQUEST_TIMEOUT_S,
        )
        return response.text

    async def generate_batch(self, items: List[BatchItem]) -> List[Dict[str, Any]]:
        """One Gemini call returning N cases as a JSON array."""
        if not items:
            return []
        if len(items) == 1:
            # No batching benefit — fall back to single-case path.
            item = items[0]
            return [await self.generate_case(
                case_type=item.case_type,
                mechanism=item.mechanism,
                environment=item.environment,
                region=item.region,
                phases=item.phases,
                target_triage=item.target_triage,
            )]

        prompt = case_batch_prompt(items)
        response = await asyncio.wait_for(
            asyncio.to_thread(
                self._client.models.generate_content,
                model=_MODEL,
                contents=prompt,
                config={
                    "system_instruction": CASE_SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                },
            ),
            timeout=_REQUEST_TIMEOUT_S,
        )
        parsed = _parse_json(response.text)
        cases = parsed.get("cases") if isinstance(parsed, dict) else None
        if not isinstance(cases, list) or len(cases) != len(items):
            raise ValueError(
                f"Gemini batch returned {len(cases) if isinstance(cases, list) else 'invalid'} "
                f"cases, expected {len(items)}"
            )
        out: List[Dict[str, Any]] = []
        for item, case in zip(items, cases):
            if item.target_triage:
                case["triage_category"] = item.target_triage
            out.append(inject_stable_ids(case))
        return out


def _parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        raise
