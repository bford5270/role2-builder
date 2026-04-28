"""Bedrock-Claude implementation of CaseProvider (GovCloud target).

Stub for now. When GovCloud work starts:
  - Use boto3 with the bedrock-runtime client.
  - Region defaults to us-gov-west-1 (or us-gov-east-1 for failover).
  - Model id will be the Claude Sonnet/Opus on Bedrock at the time of GovCloud
    onboarding.
  - Same CASE_SYSTEM_PROMPT and case_user_prompt as Gemini.
  - Same inject_stable_ids hook on the parsed response.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import CaseProvider


class BedrockCaseProvider(CaseProvider):
    name = "bedrock"

    def __init__(self) -> None:
        raise NotImplementedError(
            "Bedrock provider not yet implemented. Set CASE_PROVIDER=gemini "
            "until GovCloud onboarding begins."
        )

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
        raise NotImplementedError

    async def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        raise NotImplementedError
