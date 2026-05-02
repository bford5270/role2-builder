"""Provider factory.

Selects a CaseProvider implementation by the CASE_PROVIDER env var. Defaults
to the Gemini implementation today; Bedrock will be the GovCloud target.
"""
from __future__ import annotations

import os
from functools import lru_cache

from .base import CaseProvider


@lru_cache(maxsize=1)
def get_case_provider() -> CaseProvider:
    name = os.getenv("CASE_PROVIDER", "gemini").lower()
    if name == "gemini":
        from .gemini import GeminiCaseProvider
        return GeminiCaseProvider()
    if name == "bedrock":
        from .bedrock import BedrockCaseProvider
        return BedrockCaseProvider()
    if name == "stub":
        from .stub import StubCaseProvider
        return StubCaseProvider()
    raise ValueError(f"Unknown CASE_PROVIDER={name!r}; expected gemini|bedrock|stub")
