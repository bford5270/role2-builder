"""
Job tracking for async exercise generation.

Two backends with the same interface:
- PostgresJobStore: persists to the exercise_jobs table; survives restart.
- InMemoryJobStore: dict-backed; lost on restart, used when DATABASE_URL is
  unset (consistent with the rest of the app's "DB optional" contract).

The /jobs HTTP endpoints in main.py read/write through this layer, never
directly through SQLAlchemy.
"""

from __future__ import annotations

import abc
import asyncio
import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"


# Statuses that allow a cancel request to take effect. Once a job is complete
# or failed, cancel is a no-op.
CANCELLABLE_STATUSES = {JobStatus.queued, JobStatus.running}


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    current_phase: str = "queued"
    total_cases: int = 0
    completed_cases: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = None
    generation_summary: Optional[Dict[str, Any]] = None
    exercise_id: Optional[int] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @property
    def progress(self) -> float:
        if self.total_cases <= 0:
            return 0.0
        return min(1.0, self.completed_cases / self.total_cases)


# ---------------------------------------------------------------------------
# Abstract store
# ---------------------------------------------------------------------------

class JobStore(abc.ABC):
    @abc.abstractmethod
    async def create(self, *, total_cases: int, config: Dict[str, Any]) -> JobRecord: ...

    @abc.abstractmethod
    async def get(self, job_id: str) -> Optional[JobRecord]: ...

    @abc.abstractmethod
    async def update_progress(
        self,
        job_id: str,
        *,
        completed: Optional[int] = None,
        current_phase: Optional[str] = None,
    ) -> None: ...

    @abc.abstractmethod
    async def append_errors(self, job_id: str, errors: List[Dict[str, Any]]) -> None: ...

    @abc.abstractmethod
    async def mark_running(self, job_id: str) -> None: ...

    @abc.abstractmethod
    async def mark_complete(
        self,
        job_id: str,
        *,
        exercise_id: Optional[int],
        generation_summary: Dict[str, Any],
    ) -> None: ...

    @abc.abstractmethod
    async def mark_failed(self, job_id: str, error_message: str) -> None: ...

    @abc.abstractmethod
    async def mark_cancelled(self, job_id: str) -> None: ...

    @abc.abstractmethod
    async def request_cancel(self, job_id: str) -> bool:
        """Mark the job as cancelled if it is currently queued or running.

        Returns True if the request was accepted, False if the job is already
        complete/failed (no-op) or unknown.
        """

    @abc.abstractmethod
    async def list_recent(self, limit: int = 20) -> List[JobRecord]: ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------

class InMemoryJobStore(JobStore):
    """Process-local store. Lost on restart. Used when DATABASE_URL is unset."""

    def __init__(self) -> None:
        self._records: Dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, *, total_cases: int, config: Dict[str, Any]) -> JobRecord:
        async with self._lock:
            now = datetime.utcnow()
            record = JobRecord(
                id=str(uuid.uuid4()),
                status=JobStatus.queued,
                current_phase="queued",
                total_cases=total_cases,
                config=config,
                created_at=now,
                updated_at=now,
            )
            self._records[record.id] = record
            return record.model_copy()

    async def get(self, job_id: str) -> Optional[JobRecord]:
        async with self._lock:
            r = self._records.get(job_id)
            return r.model_copy() if r else None

    async def update_progress(
        self,
        job_id: str,
        *,
        completed: Optional[int] = None,
        current_phase: Optional[str] = None,
    ) -> None:
        async with self._lock:
            r = self._records.get(job_id)
            if not r:
                return
            if completed is not None:
                r.completed_cases = completed
            if current_phase is not None:
                r.current_phase = current_phase
            r.updated_at = datetime.utcnow()

    async def append_errors(self, job_id: str, errors: List[Dict[str, Any]]) -> None:
        async with self._lock:
            r = self._records.get(job_id)
            if not r:
                return
            r.errors = list(r.errors) + list(errors)
            r.updated_at = datetime.utcnow()

    async def mark_running(self, job_id: str) -> None:
        async with self._lock:
            r = self._records.get(job_id)
            if not r:
                return
            r.status = JobStatus.running
            r.current_phase = "planning"
            r.updated_at = datetime.utcnow()

    async def mark_complete(
        self,
        job_id: str,
        *,
        exercise_id: Optional[int],
        generation_summary: Dict[str, Any],
    ) -> None:
        async with self._lock:
            r = self._records.get(job_id)
            if not r:
                return
            r.status = JobStatus.complete
            r.current_phase = "complete"
            r.exercise_id = exercise_id
            r.generation_summary = generation_summary
            r.updated_at = datetime.utcnow()

    async def mark_failed(self, job_id: str, error_message: str) -> None:
        async with self._lock:
            r = self._records.get(job_id)
            if not r:
                return
            r.status = JobStatus.failed
            r.current_phase = "failed"
            r.error_message = error_message
            r.updated_at = datetime.utcnow()

    async def mark_cancelled(self, job_id: str) -> None:
        async with self._lock:
            r = self._records.get(job_id)
            if not r:
                return
            r.status = JobStatus.cancelled
            r.current_phase = "cancelled"
            r.updated_at = datetime.utcnow()

    async def request_cancel(self, job_id: str) -> bool:
        async with self._lock:
            r = self._records.get(job_id)
            if r is None:
                return False
            if r.status not in CANCELLABLE_STATUSES:
                return False
            r.status = JobStatus.cancelled
            # current_phase preserved so the UI can show "cancelled during X".
            r.updated_at = datetime.utcnow()
            return True

    async def list_recent(self, limit: int = 20) -> List[JobRecord]:
        async with self._lock:
            ordered = sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)
            return [r.model_copy() for r in ordered[:limit]]


# ---------------------------------------------------------------------------
# Postgres implementation
# ---------------------------------------------------------------------------

class PostgresJobStore(JobStore):
    """Persists jobs to the exercise_jobs table. Each call opens a short-lived
    session — no long-running transactions across the worker's batch cycles.
    """

    def __init__(self, session_factory) -> None:
        self._SessionLocal = session_factory

    def _to_record(self, row) -> JobRecord:
        return JobRecord(
            id=row.id,
            status=JobStatus(row.status),
            current_phase=row.current_phase or "queued",
            total_cases=row.total_cases or 0,
            completed_cases=row.completed_cases or 0,
            errors=row.errors or [],
            error_message=row.error_message,
            generation_summary=row.generation_summary,
            exercise_id=row.exercise_id,
            config=row.config or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def create(self, *, total_cases: int, config: Dict[str, Any]) -> JobRecord:
        from .db import ExerciseJob
        return await asyncio.to_thread(self._create_sync, total_cases, config, ExerciseJob)

    def _create_sync(self, total_cases: int, config: Dict[str, Any], ExerciseJob) -> JobRecord:
        db = self._SessionLocal()
        try:
            job_id = str(uuid.uuid4())
            now = datetime.utcnow()
            row = ExerciseJob(
                id=job_id,
                status=JobStatus.queued.value,
                current_phase="queued",
                total_cases=total_cases,
                completed_cases=0,
                config=config,
                errors=[],
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._to_record(row)
        finally:
            db.close()

    async def get(self, job_id: str) -> Optional[JobRecord]:
        from .db import ExerciseJob
        return await asyncio.to_thread(self._get_sync, job_id, ExerciseJob)

    def _get_sync(self, job_id: str, ExerciseJob) -> Optional[JobRecord]:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            return self._to_record(row) if row else None
        finally:
            db.close()

    async def update_progress(
        self,
        job_id: str,
        *,
        completed: Optional[int] = None,
        current_phase: Optional[str] = None,
    ) -> None:
        from .db import ExerciseJob
        await asyncio.to_thread(self._update_progress_sync, job_id, completed, current_phase, ExerciseJob)

    def _update_progress_sync(self, job_id, completed, current_phase, ExerciseJob) -> None:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            if not row:
                return
            if completed is not None:
                row.completed_cases = completed
            if current_phase is not None:
                row.current_phase = current_phase
            row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def append_errors(self, job_id: str, errors: List[Dict[str, Any]]) -> None:
        from .db import ExerciseJob
        await asyncio.to_thread(self._append_errors_sync, job_id, errors, ExerciseJob)

    def _append_errors_sync(self, job_id, errors, ExerciseJob) -> None:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            if not row:
                return
            row.errors = list(row.errors or []) + list(errors)
            row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def mark_running(self, job_id: str) -> None:
        from .db import ExerciseJob
        await asyncio.to_thread(self._mark_running_sync, job_id, ExerciseJob)

    def _mark_running_sync(self, job_id, ExerciseJob) -> None:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            if not row:
                return
            row.status = JobStatus.running.value
            row.current_phase = "planning"
            row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def mark_complete(
        self,
        job_id: str,
        *,
        exercise_id: Optional[int],
        generation_summary: Dict[str, Any],
    ) -> None:
        from .db import ExerciseJob
        await asyncio.to_thread(self._mark_complete_sync, job_id, exercise_id, generation_summary, ExerciseJob)

    def _mark_complete_sync(self, job_id, exercise_id, generation_summary, ExerciseJob) -> None:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            if not row:
                return
            row.status = JobStatus.complete.value
            row.current_phase = "complete"
            row.exercise_id = exercise_id
            row.generation_summary = generation_summary
            row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def mark_failed(self, job_id: str, error_message: str) -> None:
        from .db import ExerciseJob
        await asyncio.to_thread(self._mark_failed_sync, job_id, error_message, ExerciseJob)

    def _mark_failed_sync(self, job_id, error_message, ExerciseJob) -> None:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            if not row:
                return
            row.status = JobStatus.failed.value
            row.current_phase = "failed"
            row.error_message = error_message
            row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def mark_cancelled(self, job_id: str) -> None:
        from .db import ExerciseJob
        await asyncio.to_thread(self._mark_cancelled_sync, job_id, ExerciseJob)

    def _mark_cancelled_sync(self, job_id, ExerciseJob) -> None:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            if not row:
                return
            row.status = JobStatus.cancelled.value
            row.current_phase = "cancelled"
            row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def request_cancel(self, job_id: str) -> bool:
        from .db import ExerciseJob
        return await asyncio.to_thread(self._request_cancel_sync, job_id, ExerciseJob)

    def _request_cancel_sync(self, job_id, ExerciseJob) -> bool:
        db = self._SessionLocal()
        try:
            row = db.query(ExerciseJob).filter(ExerciseJob.id == job_id).first()
            if row is None:
                return False
            if row.status not in {JobStatus.queued.value, JobStatus.running.value}:
                return False
            row.status = JobStatus.cancelled.value
            row.updated_at = datetime.utcnow()
            db.commit()
            return True
        finally:
            db.close()

    async def list_recent(self, limit: int = 20) -> List[JobRecord]:
        from .db import ExerciseJob
        return await asyncio.to_thread(self._list_recent_sync, limit, ExerciseJob)

    def _list_recent_sync(self, limit, ExerciseJob) -> List[JobRecord]:
        db = self._SessionLocal()
        try:
            rows = (
                db.query(ExerciseJob)
                .order_by(ExerciseJob.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._to_record(r) for r in rows]
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Singleton + global serialization
# ---------------------------------------------------------------------------

_store: Optional[JobStore] = None
_JOB_SEMAPHORE: Optional[asyncio.Semaphore] = None


def get_job_store() -> JobStore:
    """Return a singleton JobStore: PostgresJobStore if DATABASE_URL is set,
    InMemoryJobStore otherwise."""
    global _store
    if _store is None:
        from .db import SessionLocal
        if SessionLocal is not None:
            _store = PostgresJobStore(SessionLocal)
        else:
            _store = InMemoryJobStore()
    return _store


def get_job_semaphore() -> asyncio.Semaphore:
    """Lazily-initialized global semaphore that serializes job execution.

    Created on first use (avoids capturing the wrong event loop at import
    time). Concurrency is fixed at 1 per the Phase 4 product decision —
    additional submissions queue with status='queued' until their turn.
    """
    global _JOB_SEMAPHORE
    if _JOB_SEMAPHORE is None:
        _JOB_SEMAPHORE = asyncio.Semaphore(1)
    return _JOB_SEMAPHORE


def reset_singletons_for_tests() -> None:
    """Test hook only. Clears the cached singletons."""
    global _store, _JOB_SEMAPHORE
    _store = None
    _JOB_SEMAPHORE = None
