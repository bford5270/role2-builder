"""Preflight diagnostic for the active CASE_PROVIDER.

Runs locally; checks every prereq and prints a green/red checklist before you
flip your production env var. Designed for the Bedrock onboarding case
specifically (most of the failure modes there are silent), but also covers
Gemini and the stub.

Usage:
  python -m backend.scripts.doctor                # checks $CASE_PROVIDER (default gemini)
  CASE_PROVIDER=bedrock python -m backend.scripts.doctor

Exit codes:
  0  all checks passed
  1  one or more checks failed (details printed)

Bedrock checklist (in order):
  1. boto3 importable
  2. AWS credentials resolvable (boto3 chain: env vars / instance role / ~/.aws)
  3. AWS_REGION set
  4. BEDROCK_MODEL_ID set
  5. bedrock-runtime client constructible
  6. Real Converse call with a 1-token prompt (validates IAM + model id end-to-end)

Gemini checklist:
  1. google-genai importable
  2. GEMINI_API_KEY set
  3. Real generate_content call with a 1-token prompt

Stub: just confirms the provider constructs.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from typing import Callable, List, Tuple

# Output uses simple ASCII so it's safe in any terminal / CI log.
_OK = "[ OK ]"
_FAIL = "[FAIL]"
_SKIP = "[skip]"


class _Ctx:
    """Carries cumulative state across checks."""
    def __init__(self) -> None:
        self.failures: List[str] = []
        self.skipped: List[str] = []


def _check(label: str, fn: Callable[[], Tuple[bool, str]], ctx: _Ctx) -> bool:
    """Run one check, print result, accumulate failures."""
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    icon = _OK if ok else _FAIL
    print(f"  {icon} {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        ctx.failures.append(label)
    return ok


# ---------------------------------------------------------------------------
# Bedrock checks
# ---------------------------------------------------------------------------

def _check_bedrock(ctx: _Ctx) -> None:
    print("\n=== Bedrock provider ===")

    def _boto3_import() -> Tuple[bool, str]:
        import boto3  # noqa: F401
        return True, ""

    if not _check("boto3 importable", _boto3_import, ctx):
        return  # nothing else can run without boto3

    import boto3  # safe; just verified
    from botocore.exceptions import (
        ClientError, NoCredentialsError, NoRegionError, EndpointConnectionError,
    )

    def _aws_credentials() -> Tuple[bool, str]:
        session = boto3.Session()
        creds = session.get_credentials()
        if creds is None:
            return False, ("no credentials found via the boto3 chain. Set "
                           "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY, attach an "
                           "instance role, or run `aws configure`.")
        return True, f"resolved (method: {creds.method})"

    _check("AWS credentials resolvable", _aws_credentials, ctx)

    def _region_set() -> Tuple[bool, str]:
        region = os.getenv("AWS_REGION") or boto3.Session().region_name
        if not region:
            return False, "AWS_REGION env var unset and no default region in boto3 config"
        return True, region

    _check("AWS_REGION set", _region_set, ctx)

    def _model_id_set() -> Tuple[bool, str]:
        model_id = os.getenv("BEDROCK_MODEL_ID")
        if not model_id:
            return False, ("BEDROCK_MODEL_ID env var unset. Pull the exact id from "
                           "AWS Bedrock console -> Model access (prefer the cross-region "
                           "inference profile id with the `us.` prefix).")
        return True, model_id

    if not _check("BEDROCK_MODEL_ID set", _model_id_set, ctx):
        return  # can't make the real call without it

    def _client_constructible() -> Tuple[bool, str]:
        boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION"))
        return True, "bedrock-runtime client constructed"

    if not _check("bedrock-runtime client constructible", _client_constructible, ctx):
        return

    # Real Converse call. Use a tiny prompt to keep the cost trivial (~$0.0001).
    def _converse_smoke() -> Tuple[bool, str]:
        from backend.providers.bedrock import BedrockCaseProvider
        provider = BedrockCaseProvider()
        # Bypass the case-generation contract; we just want a real round trip.
        text = asyncio.run(provider.generate_text("Say only: ok"))
        text = (text or "").strip().lower()
        if "ok" not in text:
            return True, f"unexpected response (got '{text[:40]}…') — model is reachable but ignored the prompt"
        return True, "round-trip succeeded"

    try:
        _check("Converse smoke test (1-token prompt)", _converse_smoke, ctx)
    except Exception:
        # Surface specific actionable causes for the most common errors.
        exc_type, exc, _ = sys.exc_info()
        msg = str(exc)
        ctx.failures.append("Converse smoke test")
        if "AccessDeniedException" in msg or isinstance(exc, ClientError):
            print(f"  {_FAIL} Converse smoke test — IAM denied. Verify bedrock:InvokeModel on "
                  f"the resolved model arn. Full error: {msg}")
        elif "ValidationException" in msg:
            print(f"  {_FAIL} Converse smoke test — model id rejected. The id may not exist in "
                  f"AWS_REGION={os.getenv('AWS_REGION')}, or you don't have model access yet. "
                  f"Full error: {msg}")
        elif isinstance(exc, EndpointConnectionError):
            print(f"  {_FAIL} Converse smoke test — can't reach Bedrock endpoint. Network / "
                  f"region issue: {msg}")
        else:
            print(f"  {_FAIL} Converse smoke test — {type(exc).__name__}: {msg}")


# ---------------------------------------------------------------------------
# Gemini checks
# ---------------------------------------------------------------------------

def _check_gemini(ctx: _Ctx) -> None:
    print("\n=== Gemini provider ===")

    def _genai_import() -> Tuple[bool, str]:
        from google import genai  # noqa: F401
        return True, ""

    if not _check("google-genai importable", _genai_import, ctx):
        return

    def _api_key_set() -> Tuple[bool, str]:
        if not os.getenv("GEMINI_API_KEY"):
            return False, "GEMINI_API_KEY env var unset"
        return True, "set"

    if not _check("GEMINI_API_KEY set", _api_key_set, ctx):
        return

    def _gemini_smoke() -> Tuple[bool, str]:
        from backend.providers.gemini import GeminiCaseProvider
        provider = GeminiCaseProvider()
        text = asyncio.run(provider.generate_text("Say only: ok"))
        return True, f"round-trip succeeded ({len(text or '')} chars)"

    _check("Gemini smoke test (1-token prompt)", _gemini_smoke, ctx)


# ---------------------------------------------------------------------------
# Stub
# ---------------------------------------------------------------------------

def _check_stub(ctx: _Ctx) -> None:
    print("\n=== Stub provider ===")

    def _stub_constructs() -> Tuple[bool, str]:
        from backend.providers.stub import StubCaseProvider
        StubCaseProvider()
        return True, "no external dependencies"

    _check("StubCaseProvider constructs", _stub_constructs, ctx)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> int:
    provider = os.getenv("CASE_PROVIDER", "gemini").lower()
    print(f"Doctor — checking CASE_PROVIDER={provider}")

    ctx = _Ctx()

    if provider == "bedrock":
        _check_bedrock(ctx)
    elif provider == "gemini":
        _check_gemini(ctx)
    elif provider == "stub":
        _check_stub(ctx)
    else:
        print(f"\n{_FAIL} Unknown CASE_PROVIDER={provider!r}. Expected gemini|bedrock|stub.")
        return 1

    print()
    if ctx.failures:
        print(f"{len(ctx.failures)} check(s) failed:")
        for f in ctx.failures:
            print(f"  - {f}")
        print("\nFix the failures above, then re-run. See README.md → 'Switching to Bedrock' for context.")
        return 1
    print("All checks passed. You're good to set CASE_PROVIDER and go.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
