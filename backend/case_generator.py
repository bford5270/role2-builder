"""
Async, batched case generation orchestrator.

Replaces the sequential per-case loop in `main.generate_exercise`. Fans out
batches of cases through a `CaseProvider` with bounded concurrency and per-batch
retry/backoff. Failures are surfaced as structured `GenerationError`s rather
than silently masked by `create_fallback_case` (Phase 2 behavior was that
half-degraded ZIPs looked fine to the user).

The provider abstraction means the same code runs against Gemini today and
Bedrock-Claude on GovCloud later; the only thing that changes is which
`generate_batch` implementation runs underneath.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .casualty_planner import DayPlan, EtiologyBucket
from .providers.base import BatchItem, CaseProvider


_LOG = logging.getLogger(__name__)

_MAX_BATCH_ATTEMPTS = 3
_INITIAL_BACKOFF_S = 0.5

_Key = Tuple[int, int, int]  # (day_number, bucket_pos, patient_index_within_bucket)


@dataclass
class GenerationError:
    key: _Key
    case_type: str
    mechanism: str
    category: str
    error: str
    attempts: int


@dataclass
class GenerationResult:
    cases_by_day: Dict[int, List[Dict[str, Any]]]
    errors: List[GenerationError] = field(default_factory=list)
    total_requested: int = 0
    total_returned: int = 0
    total_fallback: int = 0
    cancelled: bool = False


# ---------------------------------------------------------------------------
# Per-batch retry
# ---------------------------------------------------------------------------

async def _run_batch_with_retry(
    provider: CaseProvider,
    batch: List[BatchItem],
    *,
    max_attempts: int = _MAX_BATCH_ATTEMPTS,
    initial_backoff: float = _INITIAL_BACKOFF_S,
) -> Tuple[List[Optional[Dict[str, Any]]], Dict[int, str]]:
    """Try `generate_batch` first. If that fails after retries, fall back to
    individual `generate_case` calls per item (also with retry).

    Returns `(results, errors)` where results is the same length as `batch`
    (None for failed slots) and errors maps `batch` indices to error messages.
    """
    last_err: Optional[BaseException] = None
    for attempt in range(max_attempts):
        try:
            cases = await provider.generate_batch(batch)
            if len(cases) != len(batch):
                raise ValueError(f"batch size mismatch: got {len(cases)}, expected {len(batch)}")
            return list(cases), {}
        except Exception as e:
            last_err = e
            _LOG.warning("Batch attempt %d/%d failed: %s", attempt + 1, max_attempts, e)
            if attempt < max_attempts - 1:
                await asyncio.sleep(initial_backoff * (2 ** attempt))

    # Batch path exhausted — fall back to per-item single calls.
    _LOG.warning("Batch path exhausted after %d attempts; falling back to per-item.", max_attempts)
    results: List[Optional[Dict[str, Any]]] = [None] * len(batch)
    errors: Dict[int, str] = {}
    for i, item in enumerate(batch):
        single_err: Optional[BaseException] = None
        for attempt in range(max_attempts):
            try:
                results[i] = await provider.generate_case(
                    case_type=item.case_type,
                    mechanism=item.mechanism,
                    environment=item.environment,
                    region=item.region,
                    phases=item.phases,
                    target_triage=item.target_triage,
                )
                single_err = None
                break
            except Exception as e:
                single_err = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(initial_backoff * (2 ** attempt))
        if results[i] is None:
            errors[i] = str(single_err) if single_err else (str(last_err) if last_err else "unknown")
    return results, errors


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_all_cases(
    plans: List[DayPlan],
    provider: CaseProvider,
    *,
    environment: str,
    region: str,
    bucket_to_case_inputs: Callable[[EtiologyBucket, str], Tuple[str, str]],
    fallback_factory: Optional[Callable[[BatchItem], Dict[str, Any]]] = None,
    batch_size: int = 5,
    concurrency: int = 3,
    on_progress: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], Awaitable[bool]]] = None,
    max_attempts: int = _MAX_BATCH_ATTEMPTS,
    initial_backoff: float = _INITIAL_BACKOFF_S,
) -> GenerationResult:
    """Generate every case the schedule needs, in parallel batches, with retry.

    Args:
        plans: per-day plans from `casualty_planner.build_day_plan`.
        provider: the CaseProvider implementation (Gemini today; Bedrock later).
        environment, region: forwarded into prompts.
        bucket_to_case_inputs: maps an EtiologyBucket → (case_type, mechanism)
            for the LLM. Lives in main.py since it's product-specific.
        fallback_factory: called per-item when the provider exhausts retries.
            If None, failed items are omitted (the schedule builder's A13
            validation will refuse the resulting plan/case mismatch).
        batch_size: cases per LLM call (1 disables batching).
        concurrency: max in-flight batches.
        on_progress: optional callback `(completed, total)` invoked after each
            batch settles. Phase 4 will hook this to the ExerciseJob row.

    Returns:
        GenerationResult with `cases_by_day` (ordered to match plan buckets) and
        a structured `errors` list. Callers should not silently ignore errors.
    """
    items: List[BatchItem] = []
    for plan in plans:
        for bp, bucket in enumerate(plan.etiology_buckets):
            for p in range(bucket.count):
                case_type, mechanism = bucket_to_case_inputs(bucket, environment)
                items.append(BatchItem(
                    key=(plan.day_number, bp, p),
                    case_type=case_type,
                    mechanism=mechanism,
                    environment=environment,
                    region=region,
                    phases=bucket.phases,
                    target_triage=bucket.triage,
                    category=bucket.category,
                ))

    total = len(items)
    if total == 0:
        return GenerationResult(cases_by_day={p.day_number: [] for p in plans}, total_requested=0)

    # Chunk items into batches of `batch_size` without crossing day boundaries.
    # That keeps progress reporting honest per-day and contains the blast radius
    # of a bad batch to a single day.
    batches: List[List[BatchItem]] = []
    current: List[BatchItem] = []
    current_day: Optional[int] = None
    for item in items:
        day = item.key[0]
        if current and (day != current_day or len(current) >= batch_size):
            batches.append(current)
            current = []
        current.append(item)
        current_day = day
    if current:
        batches.append(current)

    sem = asyncio.Semaphore(max(1, concurrency))
    results_by_key: Dict[_Key, Dict[str, Any]] = {}
    errors: List[GenerationError] = []
    fallback_count = 0
    completed = 0
    state_lock = asyncio.Lock()

    async def run_one_batch(batch: List[BatchItem]) -> None:
        nonlocal completed, fallback_count
        # Graceful cancel: skip batches that haven't started yet. Already
        # in-flight batches finish (so the LLM call isn't orphaned). Up to ~1
        # batch worth of latency before the worker sees the cancel.
        if is_cancelled is not None and await is_cancelled():
            return
        async with sem:
            if is_cancelled is not None and await is_cancelled():
                return
            cases, batch_errors = await _run_batch_with_retry(
                provider, batch,
                max_attempts=max_attempts,
                initial_backoff=initial_backoff,
            )

        local_fallback = 0
        local_errors: List[GenerationError] = []
        for i, case in enumerate(cases):
            item = batch[i]
            if case is None:
                err_msg = batch_errors.get(i, "unknown error")
                local_errors.append(GenerationError(
                    key=item.key,
                    case_type=item.case_type,
                    mechanism=item.mechanism,
                    category=item.category,
                    error=err_msg,
                    attempts=_MAX_BATCH_ATTEMPTS,
                ))
                if fallback_factory is not None:
                    case = fallback_factory(item)
                    local_fallback += 1
            if case is not None:
                results_by_key[item.key] = case

        async with state_lock:
            errors.extend(local_errors)
            fallback_count += local_fallback
            completed += len(batch)
            if on_progress is not None:
                try:
                    on_progress(completed, total)
                except Exception:
                    _LOG.exception("on_progress callback raised; ignoring")

    await asyncio.gather(*(run_one_batch(b) for b in batches))

    # Reassemble cases_by_day in plan order.
    cases_by_day: Dict[int, List[Dict[str, Any]]] = {}
    for plan in plans:
        day_cases: List[Dict[str, Any]] = []
        for bp, bucket in enumerate(plan.etiology_buckets):
            for p in range(bucket.count):
                got = results_by_key.get((plan.day_number, bp, p))
                if got is not None:
                    day_cases.append(got)
        cases_by_day[plan.day_number] = day_cases

    cancelled_now = bool(is_cancelled is not None and await is_cancelled())
    return GenerationResult(
        cases_by_day=cases_by_day,
        errors=errors,
        total_requested=total,
        total_returned=sum(len(v) for v in cases_by_day.values()),
        total_fallback=fallback_count,
        cancelled=cancelled_now,
    )
