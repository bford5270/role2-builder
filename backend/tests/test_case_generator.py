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
