"""Tests for MatrixOverrides validation, MatrixView merge, MatrixStore CRUD,
the planner reading overrides, and the /settings/matrices endpoints."""

import asyncio
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.casualty_planner import build_day_plan, trauma_ratio, triage_distribution
from backend.matrix_store import (
    InMemoryMatrixStore,
    MatrixOverrides,
    MatrixView,
    reset_matrix_store_for_tests,
)
from backend.jobs import reset_singletons_for_tests


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_triage_distribution_must_sum_to_one(self):
        with pytest.raises(Exception):
            MatrixOverrides(base_triage_distribution={
                "Frontal Attack": {"T1": 0.5, "T2": 0.4, "T3": 0.0, "T4": 0.0}
            })

    def test_triage_distribution_keys_must_be_T1_T4(self):
        with pytest.raises(Exception):
            MatrixOverrides(base_triage_distribution={
                "Frontal Attack": {"T1": 0.5, "T2": 0.5}
            })

    def test_trauma_ratio_must_be_in_range(self):
        with pytest.raises(Exception):
            MatrixOverrides(trauma_ratio_by_setting={"Frontal Attack": 1.5})

    def test_threat_level_unknown_keys_rejected(self):
        with pytest.raises(Exception):
            MatrixOverrides(threat_level_shift={"High": {"unknown_key": 0.1}})

    def test_empty_overrides_validates(self):
        o = MatrixOverrides()
        assert o.trauma_ratio_by_setting is None


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

class TestMerge:
    def test_defaults_view_matches_module(self):
        from backend import matrices as M
        view = MatrixView.defaults()
        assert view.trauma_ratio_by_setting == M.TRAUMA_RATIO_BY_SETTING
        assert view.base_triage_distribution["Frontal Attack"] == M.BASE_TRIAGE_DISTRIBUTION["Frontal Attack"]

    def test_overrides_replace_specific_settings(self):
        overrides = MatrixOverrides(
            trauma_ratio_by_setting={"Convoy Operations": 0.85}
        )
        view = MatrixView.from_overrides(overrides)
        assert view.trauma_ratio_by_setting["Convoy Operations"] == 0.85
        # Untouched settings keep their default value.
        assert view.trauma_ratio_by_setting["Defensive Operations"] == 0.55

    def test_etiology_pool_replacement(self):
        overrides = MatrixOverrides(
            etiology_by_setting={"Convoy Operations": ["Custom Mechanism"]}
        )
        view = MatrixView.from_overrides(overrides)
        assert view.etiology_by_setting["Convoy Operations"] == ["Custom Mechanism"]


# ---------------------------------------------------------------------------
# Store CRUD
# ---------------------------------------------------------------------------

class TestInMemoryMatrixStore:
    def test_get_initial_is_empty(self):
        store = InMemoryMatrixStore()
        o = asyncio.run(store.get_overrides())
        assert o.trauma_ratio_by_setting is None

    def test_set_and_get(self):
        store = InMemoryMatrixStore()
        asyncio.run(store.set_overrides(
            MatrixOverrides(trauma_ratio_by_setting={"Convoy Operations": 0.80})
        ))
        o = asyncio.run(store.get_overrides())
        assert o.trauma_ratio_by_setting == {"Convoy Operations": 0.80}

    def test_clear(self):
        store = InMemoryMatrixStore()
        asyncio.run(store.set_overrides(
            MatrixOverrides(trauma_ratio_by_setting={"Convoy Operations": 0.80})
        ))
        asyncio.run(store.clear_overrides())
        o = asyncio.run(store.get_overrides())
        assert o.trauma_ratio_by_setting is None


# ---------------------------------------------------------------------------
# Planner reads overrides
# ---------------------------------------------------------------------------

class TestPlannerWithOverrides:
    def test_trauma_ratio_uses_override(self):
        overrides = MatrixOverrides(trauma_ratio_by_setting={"Defensive Operations": 0.95})
        view = MatrixView.from_overrides(overrides)
        r = trauma_ratio("Defensive Operations", "Medium", is_mascal=False, view=view)
        assert r == 0.95

    def test_triage_distribution_uses_override(self):
        overrides = MatrixOverrides(base_triage_distribution={
            "Defensive Operations": {"T1": 0.50, "T2": 0.30, "T3": 0.15, "T4": 0.05}
        })
        view = MatrixView.from_overrides(overrides)
        d = triage_distribution("Defensive Operations", "Medium", is_mascal=False, night_ops=False, view=view)
        assert d["T1"] == pytest.approx(0.50, abs=0.01)

    def test_build_day_plan_with_override_changes_mix(self):
        overrides = MatrixOverrides(trauma_ratio_by_setting={"Defensive Operations": 0.90})
        view = MatrixView.from_overrides(overrides)
        plan = build_day_plan(
            day_number=1, tactical_setting="Defensive Operations", total_patients=20,
            night_ops=False, mascal=False, mascal_etiology=None, mascal_patients=None,
            cbrn=False, detainee_ops=False,
            threat_level="Medium", environment="General", region=None,
            selected_footprint=["FRSS Surgical Team"], selected_mets=[],
            total_waves=3, seed=1, view=view,
        )
        # With trauma_ratio bumped to 0.90, trauma should dominate.
        assert plan.trauma_count >= 16  # round(0.90 * 20) = 18, but mascal etc. may shift slightly


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_provider_and_singletons(monkeypatch):
    monkeypatch.setenv("CASE_PROVIDER", "stub")
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


class TestSettingsEndpoints:
    def test_get_initial(self, client):
        r = client.get("/settings/matrices")
        assert r.status_code == 200
        body = r.json()
        assert body["overrides"] == {}
        assert "view" in body
        assert "defaults" in body
        assert body["view"]["trauma_ratio_by_setting"]["Frontal Attack"] == 0.80

    def test_put_then_get_roundtrip(self, client):
        payload = {"trauma_ratio_by_setting": {"Convoy Operations": 0.78}}
        r = client.put("/settings/matrices", json=payload)
        assert r.status_code == 200
        assert r.json()["overrides"] == payload
        r2 = client.get("/settings/matrices")
        assert r2.json()["view"]["trauma_ratio_by_setting"]["Convoy Operations"] == 0.78

    def test_put_invalid_400(self, client):
        bad = {"base_triage_distribution": {"Frontal Attack": {"T1": 0.9, "T2": 0.5, "T3": 0.0, "T4": 0.0}}}
        r = client.put("/settings/matrices", json=bad)
        assert r.status_code == 422  # Pydantic validation error

    def test_delete_resets(self, client):
        client.put("/settings/matrices", json={"trauma_ratio_by_setting": {"Convoy Operations": 0.78}})
        r = client.delete("/settings/matrices")
        assert r.status_code == 200
        body = r.json()
        assert body["reset"] is True
        # Defaults are back
        from backend import matrices as M
        assert body["view"]["trauma_ratio_by_setting"]["Convoy Operations"] == M.TRAUMA_RATIO_BY_SETTING["Convoy Operations"]

    def test_list_presets(self, client):
        r = client.get("/settings/matrices/presets")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["presets"]]
        assert "usmc_default" in names
        assert "permissive_humanitarian" in names
        assert "high_intensity_contingency" in names

    def test_apply_preset_unknown_404(self, client):
        r = client.post("/settings/matrices/presets/no_such_preset/apply")
        assert r.status_code == 404

    def test_apply_high_intensity_preset(self, client):
        r = client.post("/settings/matrices/presets/high_intensity_contingency/apply")
        assert r.status_code == 200
        body = r.json()
        assert body["applied"] == "high_intensity_contingency"
        assert body["view"]["trauma_ratio_by_setting"]["Frontal Attack"] == 0.90
