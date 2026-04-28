"""Behavioral tests for casualty_planner.

Each test maps to a row in STRATEGY.md §2 B-table — the inputs that previously
had no effect on the case mix.
"""

from backend.casualty_planner import (
    DayPlan,
    build_day_plan,
    surgical_allowed,
    trauma_ratio,
    triage_distribution,
)


def _plan(**overrides) -> DayPlan:
    defaults = dict(
        day_number=1,
        tactical_setting="Defensive Operations",
        total_patients=20,
        night_ops=False,
        mascal=False,
        mascal_etiology=None,
        mascal_patients=None,
        cbrn=False,
        detainee_ops=False,
        threat_level="Medium",
        environment="General",
        region=None,
        selected_footprint=["FRSS Surgical Team", "Whole Blood", "ICU Holding"],
        selected_mets=[],
        seed=42,
    )
    defaults.update(overrides)
    return build_day_plan(**defaults)


class TestTotals:
    def test_buckets_sum_to_total_patients(self):
        plan = _plan(total_patients=20)
        assert plan.total_patients == 20

    def test_works_with_small_totals(self):
        for n in (1, 2, 3, 5, 7):
            plan = _plan(total_patients=n)
            assert plan.total_patients == n, f"failed for total_patients={n}"

    def test_triage_targets_sum_to_total(self):
        plan = _plan(total_patients=20)
        assert sum(plan.triage_targets.values()) == 20


class TestThreatLevel:
    """B2: threat_level should shift trauma ratio."""

    def test_high_threat_more_trauma_than_low(self):
        low = trauma_ratio("Convoy Operations", "Low", is_mascal=False)
        high = trauma_ratio("Convoy Operations", "High", is_mascal=False)
        assert high > low

    def test_high_threat_more_critical_triage(self):
        low_dist = triage_distribution("Convoy Operations", "Low", is_mascal=False, night_ops=False)
        high_dist = triage_distribution("Convoy Operations", "High", is_mascal=False, night_ops=False)
        assert high_dist["T1"] > low_dist["T1"]


class TestEnvironment:
    """B3: environment should also flavor trauma, not just DNBI."""

    def test_desert_adds_rollover_flavor(self):
        plan = _plan(tactical_setting="Defensive Operations", environment="Desert", total_patients=30)
        trauma_etiologies = {b.etiology for b in plan.etiology_buckets if b.category.startswith("trauma")}
        assert "Vehicle Rollover" in trauma_etiologies or any("Burns" in e for e in trauma_etiologies)


class TestRegion:
    """B4: region should add endemic disease patterns."""

    def test_centcom_adds_leishmaniasis_pool(self):
        plan = _plan(environment="Desert", region="CENTCOM", total_patients=30, threat_level="Low")
        # DNBI buckets should be drawn from a pool that included region entries.
        dnbi_etiologies = {b.etiology for b in plan.etiology_buckets if b.category == "dnbi"}
        # Stochastic — assert that *some* run produces a region-flavored case across seeds.
        found = "Cutaneous leishmaniasis" in dnbi_etiologies
        if not found:
            for seed in range(10):
                p = _plan(environment="Desert", region="CENTCOM", total_patients=30, threat_level="Low", seed=seed)
                etiologies = {b.etiology for b in p.etiology_buckets if b.category == "dnbi"}
                if "Cutaneous leishmaniasis" in etiologies:
                    found = True
                    break
        assert found, "region-specific DNBI never appeared across 10 seeds"


class TestNightOps:
    """B5: night_ops should shift triage toward T1/T2."""

    def test_night_ops_more_critical(self):
        day = triage_distribution("Convoy Operations", "Medium", is_mascal=False, night_ops=False)
        night = triage_distribution("Convoy Operations", "Medium", is_mascal=False, night_ops=True)
        assert night["T1"] >= day["T1"]
        assert night["T3"] <= day["T3"]


class TestCBRN:
    """B6: cbrn flag should produce real CBRN cases, not just a drill row."""

    def test_cbrn_day_creates_cbrn_buckets(self):
        plan = _plan(cbrn=True, total_patients=20)
        cbrn_buckets = [b for b in plan.etiology_buckets if b.category in ("cbrn", "cbrn_combined")]
        assert cbrn_buckets, "cbrn=True produced no CBRN buckets"
        assert plan.cbrn_count > 0

    def test_no_cbrn_means_no_cbrn_buckets(self):
        plan = _plan(cbrn=False, total_patients=20)
        cbrn_buckets = [b for b in plan.etiology_buckets if b.category in ("cbrn", "cbrn_combined")]
        assert not cbrn_buckets


class TestDetainee:
    """B7: detainee_ops should produce detainee patients."""

    def test_detainee_day_creates_detainee_buckets(self):
        plan = _plan(detainee_ops=True, total_patients=20)
        det_buckets = [b for b in plan.etiology_buckets if b.category.startswith("detainee")]
        assert det_buckets
        assert plan.detainee_count > 0


class TestFootprint:
    """B8: footprint without surgical team should suppress surgical cases."""

    def test_no_surgical_footprint_disables_dcs(self):
        plan = _plan(
            tactical_setting="Frontal Attack",
            selected_footprint=["Triage Team", "Limited Holding"],
            total_patients=20,
        )
        assert not plan.surgical_allowed
        for b in plan.etiology_buckets:
            if b.category.startswith("trauma"):
                assert b.category == "trauma_non_surgical"
                assert "DCS" not in b.phases

    def test_surgical_footprint_enables_dcs(self):
        plan = _plan(
            tactical_setting="Frontal Attack",
            selected_footprint=["FRSS Surgical Team", "Anesthesia"],
            total_patients=20,
        )
        assert plan.surgical_allowed
        # At least one trauma_surgical bucket should appear given the etiology bias.
        surgical_buckets = [b for b in plan.etiology_buckets if b.category == "trauma_surgical"]
        assert surgical_buckets

    def test_helper_function(self):
        assert surgical_allowed(["FRSS Surgical Team"]) is True
        assert surgical_allowed(["Triage Team"]) is False


class TestMETs:
    """B9: selected METs should at least be recorded as emphasis tags."""

    def test_met_emphasis_recorded(self):
        plan = _plan(selected_mets=["Conduct Damage Control Surgery"])
        assert "surgical" in plan.met_emphasis

    def test_unknown_met_ignored(self):
        plan = _plan(selected_mets=["Conduct Underwater Basket Weaving"])
        assert plan.met_emphasis == []


class TestMASCAL:
    def test_mascal_forces_high_trauma_ratio(self):
        plan = _plan(mascal=True, mascal_etiology="IED/Blast", mascal_patients=12, total_patients=20)
        assert plan.trauma_count >= 12

    def test_mascal_etiology_dominates(self):
        plan = _plan(mascal=True, mascal_etiology="VBIED", mascal_patients=10, total_patients=20)
        trauma_etiologies = [b.etiology for b in plan.etiology_buckets if b.category.startswith("trauma")]
        assert "VBIED" in trauma_etiologies


class TestPhaseDerivation:
    """B11: phase derivation should be category-driven, not keyword-driven."""

    def test_penetrating_tbi_gets_dcs_when_surgical(self):
        # Etiology IED/Blast is in SURGICAL_ETIOLOGIES. With surgical footprint,
        # it must produce trauma_surgical -> includes DCS.
        plan = _plan(
            tactical_setting="Convoy Operations",
            mascal=True,
            mascal_etiology="IED/Blast",
            mascal_patients=8,
            total_patients=10,
        )
        ied_buckets = [b for b in plan.etiology_buckets if b.etiology == "IED/Blast"]
        assert ied_buckets
        for b in ied_buckets:
            assert b.category == "trauma_surgical"
            assert "DCS" in b.phases


class TestDeterminism:
    def test_same_seed_same_plan(self):
        a = _plan(seed=123, total_patients=20)
        b = _plan(seed=123, total_patients=20)
        assert [bk.model_dump() for bk in a.etiology_buckets] == [bk.model_dump() for bk in b.etiology_buckets]
