"""Bedrock-Claude implementation of CaseProvider.

Talks to AWS Bedrock via the `bedrock-runtime` client + the Converse API
(modern, schema-stable across model families). Same prompts as the Gemini
provider — only the transport changes.

Why Converse vs InvokeModel:
- Converse normalizes the request/response shape across Anthropic, Amazon
  Titan, Meta Llama, etc., so swapping models is a model_id change.
- Cleaner system-prompt support; native message-list shape.

Configuration (env vars):
- AWS_REGION: Bedrock region. us-east-1 in commercial AWS for now;
  us-gov-west-1 once GovCloud onboarding is done.
- BEDROCK_MODEL_ID: explicit Bedrock model id. Required — provider raises
  on first use if unset, with a pointer to the AWS console / docs.
- AWS credentials: standard boto3 resolution chain (env vars, instance role,
  ~/.aws/credentials).
- BEDROCK_REQUEST_TIMEOUT_S: per-request timeout, default 60s. Same wait_for
  protection as the Gemini provider.

Required IAM action for the calling principal:
  bedrock:InvokeModel  on the resolved model arn / inference profile.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from ..prompts import CASE_SYSTEM_PROMPT, case_batch_prompt, case_user_prompt
from .base import BatchItem, CaseProvider, inject_stable_ids


_REQUEST_TIMEOUT_S = float(os.getenv("BEDROCK_REQUEST_TIMEOUT_S", "120"))
# Token ceiling per case. A typical Role 2 case from Sonnet 4.6 lands around
# 3000-4500 output tokens of JSON; 5000 leaves headroom for the verbose end
# of the distribution. Below 5000 we saw silent mid-JSON truncation in field
# testing — Bedrock returns stopReason=max_tokens but our code used to blindly
# json.loads the truncated text and report a confusing JSONDecodeError. The
# truncation check in _converse below surfaces a clear error instead.
# Bedrock-Claude bills on output tokens, so this is also a cost cap.
_MAX_OUTPUT_TOKENS_PER_CASE = int(os.getenv("BEDROCK_MAX_OUTPUT_TOKENS_PER_CASE", "5000"))
# Hard ceiling override. If set, no call will exceed this. Useful for cost
# clamping in budget-sensitive deployments. Unset by default.
_MAX_OUTPUT_TOKENS_HARD_CAP = int(os.getenv("BEDROCK_MAX_OUTPUT_TOKENS", "0")) or None
# Generation temperature. Slightly creative for case variety.
_TEMPERATURE = float(os.getenv("BEDROCK_TEMPERATURE", "0.7"))


def _budget_max_tokens(num_cases: int) -> int:
    """Compute maxTokens for a Bedrock call covering `num_cases` cases.

    Per-case budget + a small buffer for the JSON wrapper. Honor the optional
    hard cap if set. Single-case path passes num_cases=1.
    """
    estimated = _MAX_OUTPUT_TOKENS_PER_CASE * max(1, num_cases) + 500
    if _MAX_OUTPUT_TOKENS_HARD_CAP is not None:
        return min(estimated, _MAX_OUTPUT_TOKENS_HARD_CAP)
    return estimated


class BedrockCaseProvider(CaseProvider):
    name = "bedrock"

    def __init__(
        self,
        *,
        region: Optional[str] = None,
        model_id: Optional[str] = None,
        client: Any = None,  # injected for tests; real callers leave None
    ) -> None:
        self._region = region or os.getenv("AWS_REGION", "us-east-1")
        self._model_id = model_id or os.getenv("BEDROCK_MODEL_ID")
        if not self._model_id:
            raise RuntimeError(
                "BEDROCK_MODEL_ID env var is required when CASE_PROVIDER=bedrock. "
                "Set it to the inference profile / model id from your AWS account "
                "(e.g. 'us.anthropic.claude-sonnet-4-5-20250929-v1:0' for "
                "cross-region inference; check the Bedrock console for what's "
                "available in your region)."
            )
        if client is not None:
            self._client = client
        else:
            # Soft import so installs without boto3 don't break unrelated code.
            try:
                import boto3
                from botocore.config import Config
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "boto3 is required for the Bedrock provider. "
                    "pip install boto3, or set CASE_PROVIDER=gemini|stub."
                ) from e
            # Critical: boto3's default read_timeout is 60s, which is too tight
            # for case-generation calls that stream ~60-120s of output. With the
            # default config the call would hit boto3's HTTP read_timeout, boto3
            # would silently retry (default retry policy = 5 attempts), and our
            # asyncio.wait_for would fire before any retry completed — giving
            # the symptom of a hard timeout at exactly our wait_for ceiling.
            # We disable boto3's retry layer entirely (max_attempts=1) because
            # the case_generator already retries at the application level.
            client_config = Config(
                read_timeout=_REQUEST_TIMEOUT_S + 30,  # generous buffer above wait_for
                connect_timeout=10,
                retries={"max_attempts": 1, "mode": "standard"},
            )
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
                config=client_config,
            )

    # ------------------------------------------------------------------
    # CaseProvider contract
    # ------------------------------------------------------------------

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
        text = await self._converse(prompt, system=CASE_SYSTEM_PROMPT, max_tokens=_budget_max_tokens(1))
        case = _parse_json(text)
        if target_triage:
            case["triage_category"] = target_triage
        return inject_stable_ids(case)

    async def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        return await self._converse(prompt, system=system, max_tokens=_budget_max_tokens(1))

    async def generate_batch(self, items: List[BatchItem]) -> List[Dict[str, Any]]:
        if not items:
            return []
        if len(items) == 1:
            item = items[0]
            return [
                await self.generate_case(
                    case_type=item.case_type,
                    mechanism=item.mechanism,
                    environment=item.environment,
                    region=item.region,
                    phases=item.phases,
                    target_triage=item.target_triage,
                )
            ]
        prompt = case_batch_prompt(items)
        text = await self._converse(
            prompt,
            system=CASE_SYSTEM_PROMPT,
            max_tokens=_budget_max_tokens(len(items)),
        )
        parsed = _parse_json(text)
        cases = parsed.get("cases") if isinstance(parsed, dict) else None
        if not isinstance(cases, list) or len(cases) != len(items):
            raise ValueError(
                f"Bedrock batch returned {len(cases) if isinstance(cases, list) else 'invalid'} "
                f"cases, expected {len(items)}"
            )
        out: List[Dict[str, Any]] = []
        for item, case in zip(items, cases):
            if item.target_triage:
                case["triage_category"] = item.target_triage
            out.append(inject_stable_ids(case))
        return out

    # ------------------------------------------------------------------
    # Internal: single Converse call with timeout protection
    # ------------------------------------------------------------------

    async def _converse(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "modelId": self._model_id,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {
                "maxTokens": max_tokens or _budget_max_tokens(1),
                "temperature": _TEMPERATURE,
            },
        }
        if system:
            kwargs["system"] = [{"text": system}]
        # Mirror the Gemini provider's freeze-protection pattern.
        response = await asyncio.wait_for(
            asyncio.to_thread(self._client.converse, **kwargs),
            timeout=_REQUEST_TIMEOUT_S,
        )
        # Converse response shape:
        #   {"output": {"message": {"role": "assistant",
        #                           "content": [{"text": "..."}]}}, ...}
        try:
            text = response["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(
                f"unexpected Bedrock Converse response shape: {e}; got {response!r}"
            ) from e

        # Surface mid-output truncation as a clear error instead of letting
        # downstream json.loads fail with a confusing JSONDecodeError. Bedrock
        # signals truncation via stopReason='max_tokens'; we know the output
        # is incomplete and won't parse.
        stop_reason = response.get("stopReason")
        if stop_reason == "max_tokens":
            usage = response.get("usage", {}) or {}
            cap = kwargs["inferenceConfig"]["maxTokens"]
            raise ValueError(
                f"Bedrock truncated output at maxTokens={cap} "
                f"(stopReason=max_tokens, output_tokens={usage.get('outputTokens')}). "
                f"Increase BEDROCK_MAX_OUTPUT_TOKENS_PER_CASE."
            )
        return text


# ---------------------------------------------------------------------------
# JSON parsing — Bedrock-Claude doesn't guarantee strict JSON on output;
# we strip prose framing if present.
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        raise
