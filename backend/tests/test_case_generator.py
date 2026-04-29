"""Behavior tests for case_generator: batch + fan-out + retry + structured errors."""

import asyncio
from typing import Any, Dict, List

import pytest

from backend.case_generator import generate_all_cases, _run_batch_with_retry
from backend.casualty_planner import build_day_plan, EtiologyBucket
from backend.providers.base import BatchItem, CaseProvider, inject_stable_ids
from backend.providers.stub import StubCaseProvider


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _two_day_plans():
    return [
        build_day_plan(
            day_number=1, tactical_setting="Defensive Operations", total_patients=6,
            night_ops=False, mascal=False, mascal_etiology=None, mascal_patients=None,
            cbrn=False, detainee_ops=False, threat_level="Medium",
            environment="Desert", region="CENTCOM",
            selected_footprint=["FRSS Surgical Team"], selected_mets=[],
            total_waves=2, seed=1,
        ),
        build_day_plan(
            day_number=2, tactical_setting="Convoy Operations", total_patients=8,
            night_ops=True, mascal=True, mascal_etiology="IED/Blast", mascal_patients=4,
            cbrn=False, detainee_ops=False, threat_level="High",
            environment="Desert", region="CENTCOM",
            selected_footprint=["FRSS Surgical Team"], selected_mets=[],
            total_waves=2, seed=2,
        ),
    ]


def _bucket_to_inputs(bucket: EtiologyBucket, environment: str):
    return bucket.etiology, bucket.etiology  # simple: case_type == mechanism == etiology


def _fallback(item: BatchItem) -> Dict[str, Any]:
    return inject_stable_ids({
        "meta": {"title": f"Fallback: {item.case_type}"},
        "triage_category": item.target_triage or "T2",
        "phases": {"dcr": {}, "dcs": None, "pcc": {}},
        "zmist": {"mechanism": item.mechanism, "injuries": item.case_type},
    })


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_generates_all_cases_in_correct_order(self):
        plans = _two_day_plans()
        result = asyncio.run(generate_all_cases(
            plans, StubCaseProvider(),
            environment="Desert", region="CENTCOM",
            bucket_to_case_inputs=_bucket_to_inputs,
            fallback_factory=_fallback,
            batch_size=3, concurrency=2,
        ))
        assert result.total_requested == 14
        assert result.total_returned == 14
        assert result.total_fallback == 0
        assert not result.errors
        assert len(result.cases_by_day[1]) == 6
        assert len(result.cases_by_day[2]) == 8

    def test_progress_callback_fires(self):
        plans = _two_day_plans()
        progress: List[tuple] = []
        result = asyncio.run(generate_all_cases(
            plans, StubCaseProvider(),
            environment="Desert", region="CENTCOM",
            bucket_to_case_inputs=_bucket_to_inputs,
            fallback_factory=_fallback,
            batch_size=4, concurrency=1,
            on_progress=lambda c, t: progress.append((c, t)),
        ))
        assert progress, "on_progress was never called"
        assert progress[-1][0] == result.total_requested
        assert all(t == result.total_requested for _, t in progress)


# ---------------------------------------------------------------------------
# Failures, retries, fallbacks
# ---------------------------------------------------------------------------

class _FlakyProvider(CaseProvider):
    """Fails the batch path forever, succeeds on single calls. Used to verify
    that exhausted batch retries fall through to per-item generation."""

    name = "flaky"

    def __init__(self):
        self.batch_attempts = 0
        self.single_calls = 0
        self._stub = StubCaseProvider()

    async def generate_case(self, **kwargs):
        self.single_calls += 1
        return await self._stub.generate_case(**kwargs)

    async def generate_text(self, prompt, *, system=None):
        return ""

    async def generate_batch(self, items):
        self.batch_attempts += 1
        raise RuntimeError("simulated batch failure")


class _StallingProvider(CaseProvider):
    """Always raises asyncio.TimeoutError to simulate a stalled upstream call.

    Verifies the retry-and-fallback path treats TimeoutError like any other
    exception — without it, a single hung Gemini call would deadlock the
    worker (see Apr 2026 freeze report). This provider is the regression
    guard: if the retry layer silently swallows TimeoutError or fails to
    fall through to fallback_factory, generate_all_cases would never return.
    """

    name = "stalling"

    async def generate_case(self, **kwargs):
        raise asyncio.TimeoutError("simulated stall")

    async def generate_text(self, prompt, *, system=None):
        raise asyncio.TimeoutError("simulated stall")

    async def generate_batch(self, items):
        raise asyncio.TimeoutError("simulated stall")


class _BrokenProvider(CaseProvider):
    """Fails everything. Forces use of fallback_factory."""

    name = "broken"

    async def generate_case(self, **kwargs):
        raise RuntimeError("simulated total failure")

    async def generate_text(self, prompt, *, system=None):
        raise RuntimeError("simulated total failure")

    async def generate_batch(self, items):
        raise RuntimeError("simulated total failure")


class TestRetryAndFallback:
    def test_batch_failure_falls_through_to_single_calls(self):
        plans = _two_day_plans()
        provider = _FlakyProvider()
        result = asyncio.run(generate_all_cases(
            plans, provider,
            environment="Desert", region="CENTCOM",
            bucket_to_case_inputs=_bucket_to_inputs,
            fallback_factory=_fallback,
            batch_size=4, concurrency=2, initial_backoff=0.0,
        ))
        # Every case should still be present (single-call path succeeded).
        assert result.total_returned == 14
        assert result.total_fallback == 0
        assert provider.batch_attempts >= 3, "expected at least 3 batch retries before fall-through"
        assert provider.single_calls == 14

    def test_total_failure_uses_fallback_factory(self):
        plans = _two_day_plans()
        result = asyncio.run(generate_all_cases(
            plans, _BrokenProvider(),
            environment="Desert", region="CENTCOM",
            bucket_to_case_inputs=_bucket_to_inputs,
            fallback_factory=_fallback,
            batch_size=4, concurrency=2, initial_backoff=0.0,
        ))
        # All 14 fell back; structured errors logged for each.
        assert result.total_fallback == 14
        assert len(result.errors) == 14
        assert all("simulated total failure" in e.error for e in result.errors)

    def test_no_fallback_yields_missing_cases(self):
        """If the caller doesn't provide a fallback, failed cases are simply
        absent from cases_by_day. The schedule builder's A13 validation will
        catch the mismatch."""
        plans = _two_day_plans()
        result = asyncio.run(generate_all_cases(
            plans, _BrokenProvider(),
            environment="Desert", region="CENTCOM",
            bucket_to_case_inputs=_bucket_to_inputs,
            fallback_factory=None,
            batch_size=4, concurrency=2, initial_backoff=0.0,
        ))
        assert result.total_returned == 0
        assert result.total_fallback == 0
        assert len(result.errors) == 14

    def test_timeout_routes_to_fallback_without_hanging(self):
        """Regression for the Apr 2026 freeze report. When the provider stalls
        and surfaces TimeoutError (via the wait_for the Gemini provider now
        adds), the retry layer must catch it like any other exception and
        fall through to fallback_factory. If TimeoutError were swallowed or
        propagated past the retry layer, generate_all_cases would deadlock."""
        plans = _two_day_plans()
        # Give it a short overall time budget to confirm it returns promptly.
        result = asyncio.run(asyncio.wait_for(
            generate_all_cases(
                plans, _StallingProvider(),
                environment="Desert", region="CENTCOM",
                bucket_to_case_inputs=_bucket_to_inputs,
                fallback_factory=_fallback,
                batch_size=4, concurrency=2, initial_backoff=0.0,
            ),
            timeout=5.0,
        ))
        assert result.total_fallback == 14
        assert len(result.errors) == 14
        assert all("simulated stall" in e.error.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# _run_batch_with_retry direct tests
# ---------------------------------------------------------------------------

class TestRunBatchWithRetry:
    def test_succeeds_on_first_try(self):
        provider = StubCaseProvider()
        items = [BatchItem(
            key=(1, 0, 0), case_type="GSW", mechanism="GSW", environment="Desert",
            region="CENTCOM", phases=["DCR", "PCC"], target_triage="T2", category="trauma_non_surgical",
        )]
        cases, errors = asyncio.run(_run_batch_with_retry(provider, items, max_attempts=3, initial_backoff=0.0))
        assert cases[0] is not None
        assert errors == {}

    def test_returns_errors_when_everything_fails(self):
        items = [BatchItem(
            key=(1, 0, 0), case_type="GSW", mechanism="GSW", environment="Desert",
            region="CENTCOM", phases=["DCR", "PCC"], target_triage="T2", category="trauma_non_surgical",
        )]
        cases, errors = asyncio.run(_run_batch_with_retry(_BrokenProvider(), items, max_attempts=2, initial_backoff=0.0))
        assert cases == [None]
        assert 0 in errors


# ---------------------------------------------------------------------------
# Default base.generate_batch (gather-based) wraps generate_case
# ---------------------------------------------------------------------------

class TestDefaultBatch:
    def test_default_batch_calls_generate_case(self):
        provider = StubCaseProvider()
        items = [
            BatchItem(key=(1, 0, i), case_type=f"case-{i}", mechanism="m", environment="E",
                      region="R", phases=["DCR", "PCC"], target_triage="T3", category="dnbi")
            for i in range(3)
        ]
        cases = asyncio.run(provider.generate_batch(items))
        assert len(cases) == 3
        # Each case carries its own stable case_id (no collisions despite parallel calls).
        ids = {c["case_id"] for c in cases}
        assert len(ids) == 3


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

class _SlowProvider(CaseProvider):
    """Stub that pauses each batch so the cancel signal can win the race."""

    name = "slow"

    def __init__(self, delay_s: float = 0.05):
        self.delay_s = delay_s
        self._stub = StubCaseProvider()
        self.batches_started = 0
        self.batches_completed = 0

    async def generate_case(self, **kwargs):
        await asyncio.sleep(self.delay_s)
        return await self._stub.generate_case(**kwargs)

    async def generate_text(self, prompt, *, system=None):
        return ""

    async def generate_batch(self, items):
        self.batches_started += 1
        await asyncio.sleep(self.delay_s)
        result = await self._stub.generate_batch(items)
        self.batches_completed += 1
        return result


class TestCaseGeneratorCancellation:
    def test_cancel_skips_remaining_batches(self):
        plans = _two_day_plans()  # 14 cases total
        provider = _SlowProvider(delay_s=0.05)
        cancel_after_batches = 1
        flag = {"cancelled": False}

        async def is_cancelled():
            # Flip cancelled after the first batch completes.
            return provider.batches_completed >= cancel_after_batches

        async def run():
            return await generate_all_cases(
                plans, provider,
                environment="Desert", region="CENTCOM",
                bucket_to_case_inputs=_bucket_to_inputs,
                fallback_factory=_fallback,
                batch_size=4, concurrency=1,  # serial so the cancel timing is deterministic
                is_cancelled=is_cancelled,
                initial_backoff=0.0,
            )

        result = asyncio.run(run())
        assert result.cancelled is True
        # Some batches ran, but not all.
        assert result.total_returned > 0
        assert result.total_returned < result.total_requested

    def test_no_cancel_means_full_completion(self):
        plans = _two_day_plans()
        provider = _SlowProvider(delay_s=0.001)

        async def is_cancelled():
            return False

        result = asyncio.run(generate_all_cases(
            plans, provider,
            environment="Desert", region="CENTCOM",
            bucket_to_case_inputs=_bucket_to_inputs,
            fallback_factory=_fallback,
            batch_size=4, concurrency=2,
            is_cancelled=is_cancelled,
            initial_backoff=0.0,
        ))
        assert result.cancelled is False
        assert result.total_returned == result.total_requested
