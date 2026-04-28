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

from ..prompts import CASE_SYSTEM_PROMPT, case_user_prompt
from .base import CaseProvider, inject_stable_ids

_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


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
        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=_MODEL,
            contents=prompt,
            config={
                "system_instruction": CASE_SYSTEM_PROMPT,
                "response_mime_type": "application/json",
            },
        )
        case = _parse_json(response.text)
        if target_triage:
            case["triage_category"] = target_triage
        return inject_stable_ids(case)

    async def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        config = {"system_instruction": system} if system else None
        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text


def _parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        raise
