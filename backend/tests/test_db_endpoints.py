"""Integration tests for the DB-backed `/exercises/*` endpoints.

These were the deferred "DB endpoint" tests from the production-readiness
pass. We now have the late-init refactor of `db.py`, so we can spin up an
in-memory SQLite database per test, generate an exercise through the legacy
sync endpoint, and then exercise list / get / download / per-document
endpoints against the persisted row.

Each test runs in isolation: an autouse fixture calls `init_db("sqlite://")`
to swap the engine + SessionLocal, then resets to the env-based config in
teardown.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.jobs import reset_singletons_for_tests
from backend.matrix_store import reset_matrix_store_for_tests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _sqlite_db(monkeypatch):
    """Swap in a per-test SQLite DB. Resets all dependent singletons so the
    Postgres-backed JobStore / MatrixStore pick up the new SessionLocal.
    Each test gets a fresh DB; nothing leaks across tests."""
    monkeypatch.setenv("CASE_PROVIDER", "stub")
    monkeypatch.setenv("CASE_BATCH_SIZE", "5")
    monkeypatch.setenv("CASE_BATCH_CONCURRENCY", "2")

    # In-memory SQLite — fastest, isolated. shared cache lets the same engine
    # see the schema across short-lived sessions within one test.
    db.init_db("sqlite:///:memory:")

    reset_singletons_for_tests()
    reset_matrix_store_for_tests()
    from backend.providers import get_case_provider
    get_case_provider.cache_clear()

    yield

    # Teardown: drop the SQLite engine, return to env-based config.
    db.init_db()
    reset_singletons_for_tests()
    reset_matrix_store_for_tests()
    get_case_provider.cache_clear()


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


SMALL_CONFIG: Dict[str, Any] = {
    "exercise_name": "Operation DB Test",
    "duration": 1,
    "supported_unit": "Test Unit",
    "environment": "Desert",
    "threat_level": "Medium",
    "region": "CENTCOM",
    "selected_mets": [],
    "selected_footprint": ["FRSS Surgical Team", "Whole Blood"],
    "specialists": {
        "General Surgery": 1, "Orthopaedic Surgery": 1, "Anesthesiology": 1,
        "Emergency Medicine": 2, "Family Physician": 1,
        "ER Nurse": 2, "ICU Nurse": 1, "Med Surg Nurse": 1,
    },
    "days": [{
        "day_number": 1, "tactical_setting": "Defensive Operations",
        "total_patients": 4, "total_waves": 2,
        "night_ops": False, "mascal": False,
        "mascal_etiology": None, "mascal_patients": None,
        "cbrn": False, "detainee_ops": False,
    }],
}


def _generate_and_get_id(client: TestClient) -> int:
    """Helper: hit the legacy sync endpoint, then look up the just-saved id."""
    r = client.post("/generate-exercise", json=SMALL_CONFIG)
    assert r.status_code == 200, r.text
    listing = client.get("/exercises").json()
    assert listing["exercises"], "expected at least one exercise after generation"
    return listing["exercises"][0]["id"]


# ---------------------------------------------------------------------------
# /health (DB ping branch)
# ---------------------------------------------------------------------------

class TestHealthWithDb:
    def test_health_pings_db_when_configured(self, client):
        # Sanity: the autouse fixture should have set a live SessionLocal.
        assert db.SessionLocal is not None, "fixture did not configure SQLite"
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["db"] == "ok"


# ---------------------------------------------------------------------------
# /exercises list
# ---------------------------------------------------------------------------

class TestExercisesList:
    def test_list_starts_empty(self, client):
        r = client.get("/exercises")
        assert r.status_code == 200
        assert r.json() == {"exercises": []}

    def test_list_returns_persisted_exercise(self, client):
        client.post("/generate-exercise", json=SMALL_CONFIG)
        r = client.get("/exercises")
        body = r.json()
        assert len(body["exercises"]) == 1
        ex = body["exercises"][0]
        assert ex["name"] == SMALL_CONFIG["exercise_name"]
        assert ex["environment"] == SMALL_CONFIG["environment"]
        assert ex["total_cases"] == 4

    def test_list_orders_newest_first(self, client):
        client.post("/generate-exercise", json={**SMALL_CONFIG, "exercise_name": "First"})
        client.post("/generate-exercise", json={**SMALL_CONFIG, "exercise_name": "Second"})
        names = [e["name"] for e in client.get("/exercises").json()["exercises"]]
        assert names[0] == "Second"
        assert names[1] == "First"


# ---------------------------------------------------------------------------
# /exercises/{id}
# ---------------------------------------------------------------------------

class TestExerciseDetail:
    def test_404_for_unknown_id(self, client):
        r = client.get("/exercises/9999")
        assert r.status_code == 404

    def test_returns_full_payload(self, client):
        ex_id = _generate_and_get_id(client)
        r = client.get(f"/exercises/{ex_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == ex_id
        assert body["name"] == SMALL_CONFIG["exercise_name"]
        assert isinstance(body["cases"], list) and len(body["cases"]) == 4
        assert isinstance(body["msel_data"], list)


# ---------------------------------------------------------------------------
# /exercises/{id}/download
# ---------------------------------------------------------------------------

class TestExerciseDownload:
    def test_404_when_unknown(self, client):
        r = client.get("/exercises/9999/download")
        assert r.status_code == 404

    def test_rebuilds_zip_with_all_documents(self, client):
        ex_id = _generate_and_get_id(client)
        r = client.get(f"/exercises/{ex_id}/download")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/zip")

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        prefix = SMALL_CONFIG["exercise_name"]
        for ext in ("_MSEL.xlsx", "_WARNO.docx", "_Annex_Q.docx", "_MEDROE.docx", "_Case_Book.docx"):
            assert f"{prefix}{ext}" in names, f"missing {prefix}{ext}"


# ---------------------------------------------------------------------------
# /exercises/{id}/document/{type}
# ---------------------------------------------------------------------------

class TestSingleDocumentDownload:
    @pytest.mark.parametrize("doc_type,suffix,mime_prefix", [
        ("msel",      "_MSEL.xlsx",      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("warno",     "_WARNO.docx",     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("annex_q",   "_Annex_Q.docx",   "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("medroe",    "_MEDROE.docx",    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("case_book", "_Case_Book.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ])
    def test_per_document_download(self, client, doc_type, suffix, mime_prefix):
        ex_id = _generate_and_get_id(client)
        r = client.get(f"/exercises/{ex_id}/document/{doc_type}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith(mime_prefix)
        prefix = SMALL_CONFIG["exercise_name"]
        assert suffix in r.headers["content-disposition"]
        assert prefix in r.headers["content-disposition"]
        # File body is non-trivially sized.
        assert len(r.content) > 1000

    def test_invalid_doc_type_400(self, client):
        ex_id = _generate_and_get_id(client)
        r = client.get(f"/exercises/{ex_id}/document/bogus")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# /jobs/{id}/download routes through /exercises/{id}/download when DB is set
# ---------------------------------------------------------------------------

class TestJobDownloadEndToEnd:
    def test_completed_job_zip_download(self, client):
        """Submit via /jobs, wait for complete, hit /jobs/{id}/download.
        With DB available, the response is a real ZIP rebuilt from the
        persisted Exercise row."""
        import time
        r = client.post("/jobs/generate-exercise", json=SMALL_CONFIG)
        job_id = r.json()["job_id"]

        # Wait for completion.
        deadline = time.time() + 15
        while time.time() < deadline:
            status = client.get(f"/jobs/{job_id}").json()
            if status["status"] in ("complete", "failed", "cancelled"):
                break
            time.sleep(0.05)
        assert status["status"] == "complete", status

        r2 = client.get(f"/jobs/{job_id}/download")
        assert r2.status_code == 200
        assert r2.headers["content-type"].startswith("application/zip")
        zf = zipfile.ZipFile(io.BytesIO(r2.content))
        prefix = SMALL_CONFIG["exercise_name"]
        assert f"{prefix}_Case_Book.docx" in zf.namelist()


# ---------------------------------------------------------------------------
# matrix_snapshot persistence
# ---------------------------------------------------------------------------

class TestMatrixSnapshotPersisted:
    def test_snapshot_round_trips_through_db(self, client):
        # 1. Set an override.
        client.put("/settings/matrices", json={"trauma_ratio_by_setting": {"Defensive Operations": 0.91}})

        # 2. Generate an exercise.
        ex_id = _generate_and_get_id(client)

        # 3. Read the persisted Exercise row directly to confirm matrix_snapshot
        #    landed on it.
        from backend.db import Exercise
        session = db.SessionLocal()
        try:
            ex = session.query(Exercise).filter(Exercise.id == ex_id).first()
            assert ex is not None
            assert ex.matrix_snapshot is not None
            assert ex.matrix_snapshot["trauma_ratio_by_setting"]["Defensive Operations"] == 0.91
        finally:
            session.close()
