"""Tests that the matrix snapshot flows end-to-end through the pipeline.

Verified without a DB by calling `_run_exercise_pipeline` directly and
inspecting the artifacts dict. The DB persistence path
(`Exercise.matrix_snapshot` column) is exercised by the production code in
`_save_exercise_to_db`; this test ensures the upstream half is right."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from backend.jobs import reset_singletons_for_tests
from backend.matrix_store import (
    MatrixOverrides,
    get_matrix_store,
    reset_matrix_store_for_tests,
)


@pytest.fixture(autouse=True)
def _stub_provider(monkeypatch):
    monkeypatch.setenv("CASE_PROVIDER", "stub")
    reset_singletons_for_tests()
    reset_matrix_store_for_tests()
    from backend.providers import get_case_provider
    get_case_provider.cache_clear()
    yield
    reset_singletons_for_tests()
    reset_matrix_store_for_tests()
    get_case_provider.cache_clear()


def _config(**overrides) -> Any:
    from backend.main import ExerciseConfig
    base = {
        "exercise_name": "Snapshot Test",
        "duration": 1,
        "supported_unit": "Test Unit",
        "environment": "Desert",
        "threat_level": "Medium",
        "region": "CENTCOM",
        "selected_mets": [],
        "selected_footprint": ["FRSS Surgical Team"],
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
    base.update(overrides)
    return ExerciseConfig(**base)


class TestPipelineSnapshot:
    def test_artifacts_carry_default_snapshot_when_no_overrides(self):
        from backend.main import _run_exercise_pipeline

        artifacts = asyncio.run(_run_exercise_pipeline(_config()))

        assert artifacts.cancelled is False
        snap = artifacts.matrix_snapshot
        assert snap is not None
        # Snapshot covers every editable matrix.
        for key in (
            "trauma_ratio_by_setting", "threat_level_shift",
            "base_triage_distribution", "mascal_triage_distribution",
            "etiology_by_setting", "dnbi_by_region", "cbrn_etiologies",
        ):
            assert key in snap, f"snapshot missing {key}"
        # Defaults from matrices.py — Defensive Operations should be present.
        assert "Defensive Operations" in snap["trauma_ratio_by_setting"]

    def test_artifacts_snapshot_reflects_overrides(self):
        from backend.main import _run_exercise_pipeline

        # Push an override into the active matrix store, then generate.
        asyncio.run(
            get_matrix_store().set_overrides(
                MatrixOverrides(trauma_ratio_by_setting={"Defensive Operations": 0.99})
            )
        )

        artifacts = asyncio.run(_run_exercise_pipeline(_config()))
        assert artifacts.cancelled is False
        assert artifacts.matrix_snapshot["trauma_ratio_by_setting"]["Defensive Operations"] == 0.99

    def test_save_helper_passes_snapshot_to_orm(self, monkeypatch):
        """When DB is configured, `_save_exercise_to_db` writes
        `matrix_snapshot` onto the Exercise row. Without a real DB we
        intercept the SessionLocal to assert the field is included.

        Run the pipeline first (no DB → in-memory matrix store), then patch
        SessionLocal only for the persist step. Otherwise the matrix-store
        factory would pick up the fake too and try to .query() it.
        """
        from backend import db, main

        # Phase 1: build artifacts with no DB.
        artifacts = asyncio.run(main._run_exercise_pipeline(_config()))

        # Phase 2: patch SessionLocal and call the save helper directly.
        captured: Dict[str, Any] = {}

        class _FakeSession:
            def add(self, obj):
                captured["obj"] = obj
            def commit(self):
                pass
            def refresh(self, obj):
                obj.id = 42
            def close(self):
                pass

        monkeypatch.setattr(db, "SessionLocal", lambda: _FakeSession())
        new_id = main._save_exercise_to_db(_config(), artifacts)
        assert new_id == 42
        ex = captured["obj"]
        # The mocked Exercise carries the full snapshot.
        assert ex.matrix_snapshot is not None
        assert "trauma_ratio_by_setting" in ex.matrix_snapshot
