"""Property-based tests for the casualty planner using Hypothesis.

The planner has many invariants that are hard to enumerate by example:
- The bucket counts always match the day's intended trauma/DNBI/CBRN/detainee
  splits (no off-by-one rounding leaks).
- Triage counts in `triage_targets` always sum to `total_patients`.
- No bucket has a negative or zero count.
- MASCAL day forces trauma_count >= mascal_patients (when set).
- A 0-patient day produces a valid empty plan (no crash).

Hypothesis explores combinations example tests would never reach."""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from backend.casualty_planner import build_day_plan
from backend.matrices import (
    BASE_TRIAGE_DISTRIBUTION,
    DNBI_BY_ENVIRONMENT,
    ETIOLOGY_BY_SETTING,
)


# Reuse the actual setting / environment / threat / region strings the planner
# already understands so we test real code paths, not invented ones.
_SETTINGS = sorted(BASE_TRIAGE_DISTRIBUTION.keys())
_ENVIRONMENTS = sorted(DNBI_BY_ENVIRONMENT.keys())
_THREATS = ["Low", "Medium", "High"]
_REGIONS = ["CENTCOM", "INDOPACOM", "EUCOM", "AFRICOM", "SOUTHCOM", "NORTHCOM", None]
_MASCAL_ETIOLOGIES = sorted(ETIOLOGY_BY_SETTING.get("Frontal Attack", []))

setting_strategy = st.sampled_from(_SETTINGS)
env_strategy = st.sampled_from(_ENVIRONMENTS)
threat_strategy = st.sampled_from(_THREATS)
region_strategy = st.sampled_from(_REGIONS)
mascal_etiology_strategy = st.one_of(st.none(), st.sampled_from(_MASCAL_ETIOLOGIES or ["IED/Blast"]))


def _build(
    *,
    setting,
    environment,
    threat,
    region,
    total,
    night,
    mascal,
    mascal_etiology,
    mascal_patients,
    cbrn,
    detainee,
    waves,
    seed,
):
    """Thin wrapper so individual @given tests don't repeat the kwargs."""
    return build_day_plan(
        day_number=1,
        tactical_setting=setting,
        total_patients=total,
        night_ops=night,
        mascal=mascal,
        mascal_etiology=mascal_etiology,
        mascal_patients=mascal_patients,
        cbrn=cbrn,
        detainee_ops=detainee,
        threat_level=threat,
        environment=environment,
        region=region,
        selected_footprint=["FRSS Surgical Team", "Whole Blood"],
        selected_mets=[],
        total_waves=max(1, waves),
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Core invariants on a "regular" day (no MASCAL, no CBRN, no detainee)
# ---------------------------------------------------------------------------

@settings(max_examples=80, deadline=None)
@given(
    setting=setting_strategy,
    environment=env_strategy,
    threat=threat_strategy,
    region=region_strategy,
    total=st.integers(min_value=1, max_value=120),
    night=st.booleans(),
    waves=st.integers(min_value=1, max_value=8),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_regular_day_invariants(setting, environment, threat, region, total, night, waves, seed):
    plan = _build(
        setting=setting, environment=environment, threat=threat, region=region,
        total=total, night=night,
        mascal=False, mascal_etiology=None, mascal_patients=None,
        cbrn=False, detainee=False, waves=waves, seed=seed,
    )

    # All counts non-negative.
    assert plan.trauma_count >= 0
    assert plan.dnbi_count >= 0
    assert plan.cbrn_count == 0
    assert plan.detainee_count == 0

    # Sum across categories matches the day's total.
    assert plan.trauma_count + plan.dnbi_count == total

    # Buckets only ever carry positive counts (zero buckets are pruned).
    for b in plan.etiology_buckets:
        assert b.count > 0
        assert b.triage in ("T1", "T2", "T3", "T4")

    # The total inferred from buckets matches the day's total.
    assert plan.total_patients == total

    # triage_targets sum to total.
    assert sum(plan.triage_targets.values()) == total

    # No negative triage targets.
    assert all(v >= 0 for v in plan.triage_targets.values())


# ---------------------------------------------------------------------------
# MASCAL day: mascal_patients constraint honored when set
# ---------------------------------------------------------------------------

@settings(max_examples=60, deadline=None)
@given(
    setting=setting_strategy,
    environment=env_strategy,
    threat=threat_strategy,
    total=st.integers(min_value=10, max_value=120),
    mascal_patients=st.integers(min_value=1, max_value=80),
    mascal_etiology=st.sampled_from(["IED/Blast", "VBIED", "Indirect Fire/Mortar"]),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_mascal_day_honors_mascal_patients(
    setting, environment, threat, total, mascal_patients, mascal_etiology, seed,
):
    plan = _build(
        setting=setting, environment=environment, threat=threat, region=None,
        total=total, night=False,
        mascal=True, mascal_etiology=mascal_etiology, mascal_patients=mascal_patients,
        cbrn=False, detainee=False, waves=3, seed=seed,
    )

    # MASCAL trauma must cover at least min(mascal_patients, total).
    expected_floor = min(mascal_patients, total)
    assert plan.trauma_count >= expected_floor, (
        f"MASCAL day: trauma_count={plan.trauma_count} "
        f"< expected_floor={expected_floor} (mascal_patients={mascal_patients}, total={total})"
    )
    # Total still adds up.
    assert plan.trauma_count + plan.dnbi_count == total
    assert sum(plan.triage_targets.values()) == total


# ---------------------------------------------------------------------------
# CBRN day: cbrn budget carved cleanly from total
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None)
@given(
    setting=setting_strategy,
    environment=env_strategy,
    threat=threat_strategy,
    total=st.integers(min_value=5, max_value=120),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_cbrn_day_carves_cleanly(setting, environment, threat, total, seed):
    plan = _build(
        setting=setting, environment=environment, threat=threat, region=None,
        total=total, night=False,
        mascal=False, mascal_etiology=None, mascal_patients=None,
        cbrn=True, detainee=False, waves=3, seed=seed,
    )
    assert plan.cbrn_count >= 1  # always at least one CBRN case on a CBRN day
    assert plan.cbrn_count <= total
    # The four categories partition the day cleanly.
    assert plan.trauma_count + plan.dnbi_count + plan.cbrn_count + plan.detainee_count == total
    assert sum(plan.triage_targets.values()) == total


# ---------------------------------------------------------------------------
# Detainee day
# ---------------------------------------------------------------------------

@settings(max_examples=40, deadline=None)
@given(
    setting=setting_strategy,
    environment=env_strategy,
    threat=threat_strategy,
    total=st.integers(min_value=5, max_value=120),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_detainee_day_carves_cleanly(setting, environment, threat, total, seed):
    plan = _build(
        setting=setting, environment=environment, threat=threat, region=None,
        total=total, night=False,
        mascal=False, mascal_etiology=None, mascal_patients=None,
        cbrn=False, detainee=True, waves=3, seed=seed,
    )
    assert plan.detainee_count >= 1
    assert plan.detainee_count <= total
    assert plan.trauma_count + plan.dnbi_count + plan.cbrn_count + plan.detainee_count == total


# ---------------------------------------------------------------------------
# Edge case: zero patients
# ---------------------------------------------------------------------------

@settings(max_examples=20, deadline=None)
@given(
    setting=setting_strategy,
    environment=env_strategy,
    threat=threat_strategy,
)
def test_zero_patient_day_does_not_crash(setting, environment, threat):
    plan = _build(
        setting=setting, environment=environment, threat=threat, region=None,
        total=0, night=False,
        mascal=False, mascal_etiology=None, mascal_patients=None,
        cbrn=False, detainee=False, waves=1, seed=42,
    )
    assert plan.trauma_count == 0
    assert plan.dnbi_count == 0
    assert plan.etiology_buckets == []
    assert sum(plan.triage_targets.values()) == 0


# ---------------------------------------------------------------------------
# Determinism: same inputs + seed → same plan
# ---------------------------------------------------------------------------

@settings(max_examples=30, deadline=None)
@given(
    setting=setting_strategy,
    environment=env_strategy,
    threat=threat_strategy,
    total=st.integers(min_value=5, max_value=60),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_same_seed_produces_same_plan(setting, environment, threat, total, seed):
    a = _build(
        setting=setting, environment=environment, threat=threat, region=None,
        total=total, night=False,
        mascal=False, mascal_etiology=None, mascal_patients=None,
        cbrn=False, detainee=False, waves=3, seed=seed,
    )
    b = _build(
        setting=setting, environment=environment, threat=threat, region=None,
        total=total, night=False,
        mascal=False, mascal_etiology=None, mascal_patients=None,
        cbrn=False, detainee=False, waves=3, seed=seed,
    )
    assert a.trauma_count == b.trauma_count
    assert a.dnbi_count == b.dnbi_count
    assert a.triage_targets == b.triage_targets
    assert [bk.model_dump() for bk in a.etiology_buckets] == [bk.model_dump() for bk in b.etiology_buckets]
