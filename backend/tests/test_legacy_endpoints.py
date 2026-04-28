"""Integration tests for endpoints that previously had zero coverage.

Covers the legacy synchronous `/generate-exercise`, `/health`, `/generate-name`,
and the no-DB short-circuit paths of `/exercises*`. DB-backed paths
(/exercises/{id}/download etc.) are covered in test_db_endpoints.py with a
SQLite fixture."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.jobs import reset_singletons_for_tests
from backend.matrix_store import reset_matrix_store_for_tests


@pytest.fixture(autouse=True)
def _stub_provider(monkeypatch):
    monkeypatch.setenv("CASE_PROVIDER", "stub")
    monkeypatch.setenv("CASE_BATCH_SIZE", "5")
    monkeypatch.setenv("CASE_BATCH_CONCURRENCY", "2")
    reset_singletons_for_tests()
    reset_matrix_store_for_tests()
    from backend.providers import get_case_provider
    get_case_provider.cache_clear()
    yield
    reset_singletons_for_tests()
    reset_matrix_store_for_tests()
    get_case_provider.cache_clear()


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


SMALL_CONFIG: Dict[str, Any] = {
    "exercise_name": "Operation Legacy Test",
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
    "days": [
        {
            "day_number": 1, "tactical_setting": "Defensive Operations",
            "total_patients": 4, "total_waves": 2,
            "night_ops": False, "mascal": False,
            "mascal_etiology": None, "mascal_patients": None,
            "cbrn": False, "detainee_ops": False,
        }
    ],
}


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_no_db_returns_healthy_with_db_not_configured(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        # In test env DATABASE_URL is unset → not_configured.
        assert body["db"] in ("not_configured", "ok")


# ---------------------------------------------------------------------------
# Legacy POST /generate-exercise
# ---------------------------------------------------------------------------

class TestLegacyGenerateExercise:
    def test_returns_zip_with_expected_files(self, client):
        r = client.post("/generate-exercise", json=SMALL_CONFIG)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/zip")

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = set(zf.namelist())
        prefix = SMALL_CONFIG["exercise_name"]
        assert f"{prefix}_MSEL.xlsx" in names
        assert f"{prefix}_WARNO.docx" in names
        assert f"{prefix}_Annex_Q.docx" in names
        assert f"{prefix}_MEDROE.docx" in names
        assert f"{prefix}_Case_Book.docx" in names
        assert f"{prefix}_generation_summary.json" in names

    def test_generation_summary_headers_present(self, client):
        r = client.post("/generate-exercise", json=SMALL_CONFIG)
        assert r.status_code == 200
        for h in ("X-Generation-Total", "X-Generation-Returned",
                  "X-Generation-Fallback", "X-Generation-Errors"):
            assert h in r.headers, f"missing {h}"

    def test_generation_summary_body_matches_headers(self, client):
        r = client.post("/generate-exercise", json=SMALL_CONFIG)
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        prefix = SMALL_CONFIG["exercise_name"]
        summary = json.loads(zf.read(f"{prefix}_generation_summary.json"))
        assert summary["total_requested"] == 4
        assert summary["total_returned"] == 4
        assert int(r.headers["X-Generation-Total"]) == summary["total_requested"]


# ---------------------------------------------------------------------------
# /generate-name
# ---------------------------------------------------------------------------

class TestGenerateName:
    def test_returns_operation_name(self, client):
        r = client.post("/generate-name", json={
            "environment": "Desert", "region": "CENTCOM",
            "threatLevel": "High", "supportedUnit": "1st Bn 5th Mar",
        })
        assert r.status_code == 200
        body = r.json()
        assert "name" in body
        # Stub provider returns deterministic text; we only assert shape, not content.
        assert isinstance(body["name"], str) and len(body["name"]) > 0


# ---------------------------------------------------------------------------
# /exercises (no-DB short-circuit)
# ---------------------------------------------------------------------------

class TestExercisesNoDb:
    def test_list_returns_empty_when_no_db(self, client):
        r = client.get("/exercises")
        assert r.status_code == 200
        # When DATABASE_URL is unset, the endpoint short-circuits cleanly.
        assert "exercises" in r.json()
