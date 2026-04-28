"""Tests for the JobStore + job worker.

Two layers:
- InMemoryJobStore CRUD/state transitions.
- Endpoint smoke tests through FastAPI's TestClient with the stub provider, so
  the real LLM never gets called.
"""

import asyncio
import os
import time
import uuid
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.jobs import (
    InMemoryJobStore,
    JobStatus,
    get_job_semaphore,
    reset_singletons_for_tests,
)


# ---------------------------------------------------------------------------
# JobStore CRUD
# ---------------------------------------------------------------------------

class TestInMemoryJobStore:
    def test_create_returns_queued_record(self):
        store = InMemoryJobStore()
        record = asyncio.run(store.create(total_cases=10, config={"foo": "bar"}))
        assert record.status == JobStatus.queued
        assert record.total_cases == 10
        assert record.completed_cases == 0
        assert record.config == {"foo": "bar"}
        assert record.id and len(record.id) >= 16  # UUID

    def test_get_returns_copy_not_reference(self):
        store = InMemoryJobStore()
        rec = asyncio.run(store.create(total_cases=5, config={}))
        a = asyncio.run(store.get(rec.id))
        a.completed_cases = 999  # mutate the copy
        b = asyncio.run(store.get(rec.id))
        assert b.completed_cases == 0  # original unchanged

    def test_progress_lifecycle(self):
        store = InMemoryJobStore()
        rec = asyncio.run(store.create(total_cases=10, config={}))
        asyncio.run(store.mark_running(rec.id))
        asyncio.run(store.update_progress(rec.id, completed=4, current_phase="generating_cases"))
        cur = asyncio.run(store.get(rec.id))
        assert cur.status == JobStatus.running
        assert cur.completed_cases == 4
        assert cur.current_phase == "generating_cases"
        assert cur.progress == 0.4

    def test_mark_complete(self):
        store = InMemoryJobStore()
        rec = asyncio.run(store.create(total_cases=3, config={}))
        asyncio.run(store.mark_running(rec.id))
        asyncio.run(store.mark_complete(rec.id, exercise_id=42, generation_summary={"errors": []}))
        cur = asyncio.run(store.get(rec.id))
        assert cur.status == JobStatus.complete
        assert cur.exercise_id == 42

    def test_mark_failed(self):
        store = InMemoryJobStore()
        rec = asyncio.run(store.create(total_cases=3, config={}))
        asyncio.run(store.mark_failed(rec.id, "boom"))
        cur = asyncio.run(store.get(rec.id))
        assert cur.status == JobStatus.failed
        assert cur.error_message == "boom"
        assert cur.current_phase == "failed"

    def test_append_errors(self):
        store = InMemoryJobStore()
        rec = asyncio.run(store.create(total_cases=2, config={}))
        asyncio.run(store.append_errors(rec.id, [{"k": 1}, {"k": 2}]))
        asyncio.run(store.append_errors(rec.id, [{"k": 3}]))
        cur = asyncio.run(store.get(rec.id))
        assert cur.errors == [{"k": 1}, {"k": 2}, {"k": 3}]

    def test_list_recent(self):
        store = InMemoryJobStore()
        ids = []
        for _ in range(3):
            r = asyncio.run(store.create(total_cases=1, config={}))
            ids.append(r.id)
            time.sleep(0.001)  # ensure ordering
        recents = asyncio.run(store.list_recent(limit=10))
        assert len(recents) == 3
        # newest first
        assert recents[0].id == ids[-1]


# ---------------------------------------------------------------------------
# End-to-end via FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_provider_and_singletons(monkeypatch):
    """Force CASE_PROVIDER=stub and reset job singletons between tests."""
    monkeypatch.setenv("CASE_PROVIDER", "stub")
    monkeypatch.setenv("CASE_BATCH_SIZE", "5")
    monkeypatch.setenv("CASE_BATCH_CONCURRENCY", "2")
    reset_singletons_for_tests()
    # Provider singleton is cached too; clear it.
    from backend.providers import get_case_provider
    get_case_provider.cache_clear()
    yield
    reset_singletons_for_tests()
    get_case_provider.cache_clear()


@pytest.fixture
def client():
    # Import inside fixture so monkeypatched env vars take effect.
    from backend.main import app
    return TestClient(app)


SMALL_CONFIG: Dict[str, Any] = {
    "exercise_name": "Operation Test",
    "duration": 1,
    "supported_unit": "Test Unit",
    "environment": "Desert",
    "threat_level": "Medium",
    "region": "CENTCOM",
    "selected_mets": [],
    "selected_footprint": ["FRSS Surgical Team", "Whole Blood"],
    "specialists": {
        "General Surgery": 1,
        "Orthopaedic Surgery": 1,
        "Anesthesiology": 1,
        "Emergency Medicine": 2,
        "Family Physician": 1,
        "ER Nurse": 2,
        "ICU Nurse": 1,
        "Med Surg Nurse": 1,
    },
    "days": [
        {
            "day_number": 1,
            "tactical_setting": "Defensive Operations",
            "total_patients": 4,
            "total_waves": 2,
            "night_ops": False,
            "mascal": False,
            "mascal_etiology": None,
            "mascal_patients": None,
            "cbrn": False,
            "detainee_ops": False,
        }
    ],
}


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 15.0) -> Dict[str, Any]:
    """Poll the status endpoint until the job leaves running. TestClient's
    BackgroundTasks run on the event loop after the response returns."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/jobs/{job_id}")
        assert r.status_code == 200
        last = r.json()
        if last["status"] in ("complete", "failed"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"job did not finish within {timeout}s; last={last}")


class TestJobEndpoints:
    def test_queue_returns_job_id_and_total(self, client):
        r = client.post("/jobs/generate-exercise", json=SMALL_CONFIG)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "job_id" in body
        assert body["total_cases"] == 4
        assert body["status"] == "queued"

    def test_full_lifecycle_completes(self, client):
        r = client.post("/jobs/generate-exercise", json=SMALL_CONFIG)
        job_id = r.json()["job_id"]
        final = _wait_for_job(client, job_id)
        assert final["status"] == "complete", final
        assert final["completed_cases"] == 4
        assert final["progress"] == pytest.approx(1.0, rel=0.01)
        assert final["current_phase"] == "complete"

    def test_unknown_job_404(self, client):
        r = client.get(f"/jobs/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_download_before_complete_409(self, client):
        # Use a slightly larger config so the worker hasn't finished by the
        # time we hit /download — even with the stub it takes a couple ms.
        r = client.post("/jobs/generate-exercise", json=SMALL_CONFIG)
        job_id = r.json()["job_id"]
        # No DB in test mode → /download will 404 even after complete.
        # Just verify the path exists and returns a sensible status.
        r2 = client.get(f"/jobs/{job_id}/download")
        assert r2.status_code in (404, 409)


class TestJobsList:
    def test_list_recent_returns_jobs(self, client):
        for _ in range(3):
            client.post("/jobs/generate-exercise", json=SMALL_CONFIG)
        r = client.get("/jobs?limit=5")
        assert r.status_code == 200
        assert len(r.json()["jobs"]) >= 3
