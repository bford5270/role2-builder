"""Sanity checks on the default casualty-mix matrices.

These are not domain-correctness tests — those need SME review. They guard
against typos that would break the planner's math (distributions that don't
sum to 1, ratios outside [0,1], etc.).
"""

from backend import matrices as M


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


class TestTraumaRatios:
    def test_all_ratios_in_range(self):
        for setting, ratio in M.TRAUMA_RATIO_BY_SETTING.items():
            assert 0.0 <= ratio <= 1.0, f"{setting} ratio out of range: {ratio}"

    def test_default_in_range(self):
        assert 0.0 <= M.DEFAULT_TRAUMA_RATIO <= 1.0

    def test_mascal_high(self):
        assert M.MASCAL_TRAUMA_RATIO >= 0.85, "MASCAL day should be trauma-dominant"

    def test_threat_level_keys(self):
        for level in ("Low", "Medium", "High"):
            shift = M.THREAT_LEVEL_SHIFT[level]
            assert "trauma_ratio" in shift
            assert "t1_pp" in shift
            assert "t3_pp" in shift

    def test_threat_levels_are_ordered(self):
        low = M.THREAT_LEVEL_SHIFT["Low"]["trauma_ratio"]
        med = M.THREAT_LEVEL_SHIFT["Medium"]["trauma_ratio"]
        high = M.THREAT_LEVEL_SHIFT["High"]["trauma_ratio"]
        assert low < med <= high


class TestTriageDistributions:
    def test_per_setting_sums_to_one(self):
        for setting, dist in M.BASE_TRIAGE_DISTRIBUTION.items():
            total = sum(dist.values())
            assert _close(total, 1.0), f"{setting} sums to {total}, not 1.0"
            assert set(dist.keys()) == {"T1", "T2", "T3", "T4"}

    def test_default_sums_to_one(self):
        assert _close(sum(M.DEFAULT_TRIAGE_DISTRIBUTION.values()), 1.0)

    def test_mascal_sums_to_one(self):
        assert _close(sum(M.MASCAL_TRIAGE_DISTRIBUTION.values()), 1.0)

    def test_mascal_skews_critical(self):
        assert M.MASCAL_TRIAGE_DISTRIBUTION["T1"] >= 0.25, "MASCAL should have many T1s"


class TestEtiologyTables:
    def test_every_setting_has_etiology(self):
        for setting in M.TRAUMA_RATIO_BY_SETTING:
            assert setting in M.ETIOLOGY_BY_SETTING, f"missing etiology pool for {setting}"
            assert M.ETIOLOGY_BY_SETTING[setting], f"empty etiology pool for {setting}"

    def test_phase_categories_complete(self):
        required = {"trauma_surgical", "trauma_non_surgical", "dnbi", "cbrn", "detainee_trauma", "detainee_medical"}
        assert required.issubset(M.PHASES_BY_CATEGORY.keys())

    def test_surgical_categories_have_dcs(self):
        for cat in ("trauma_surgical", "cbrn_combined", "detainee_trauma"):
            assert "DCS" in M.PHASES_BY_CATEGORY[cat]

    def test_non_surgical_categories_have_no_dcs(self):
        for cat in ("trauma_non_surgical", "dnbi", "cbrn", "detainee_medical"):
            assert "DCS" not in M.PHASES_BY_CATEGORY[cat]


class TestCBRNAndDetainee:
    def test_cbrn_budget_fraction_in_range(self):
        assert 0.0 < M.CBRN_TRAUMA_BUDGET_FRACTION < 1.0

    def test_detainee_budget_fraction_in_range(self):
        assert 0.0 < M.DETAINEE_BUDGET_FRACTION < 1.0

    def test_cbrn_etiologies_non_empty(self):
        assert M.CBRN_ETIOLOGIES
        for variants in M.CBRN_ETIOLOGIES.values():
            assert variants

    def test_detainee_pool_non_empty(self):
        assert M.DETAINEE_CASE_TYPES
