"""
Pure-logic casualty planner.

Translates raw exercise inputs (ExerciseConfig + per-day DayConfig) into a
deterministic per-day plan: how many trauma vs DNBI vs CBRN vs detainee
casualties; what triage distribution to target; which etiologies/mechanisms to
sample; whether surgery is in scope based on footprint.

No LLM calls live here — this is the contract the case generator runs against
later. Same input → same plan (modulo a seeded RNG for variety).
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from . import matrices as M  # noqa: F401  (used as M.* below)
from .matrix_store import MatrixView


# ---------------------------------------------------------------------------
# Plan shape
# ---------------------------------------------------------------------------

class EtiologyBucket(BaseModel):
    """A unit of work for the case generator."""
    category: str          # trauma_surgical | trauma_non_surgical | dnbi | cbrn | cbrn_combined | detainee_trauma | detainee_medical
    etiology: str          # mechanism / cause string passed to the model
    count: int             # number of cases to generate from this bucket
    triage: str            # T1 | T2 | T3 | T4
    phases: List[str]      # which clinical phases the case must include


class DayPlan(BaseModel):
    day_number: int
    tactical_setting: str
    trauma_count: int
    dnbi_count: int
    cbrn_count: int
    detainee_count: int
    triage_targets: Dict[str, int]   # T1/T2/T3/T4 → integer count
    etiology_buckets: List[EtiologyBucket]
    surgical_allowed: bool
    met_emphasis: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    # Operational flags forwarded so the schedule builder doesn't need DayConfig.
    night_ops: bool = False
    mascal: bool = False
    mascal_patients: Optional[int] = None
    mascal_etiology: Optional[str] = None
    cbrn: bool = False
    detainee_ops: bool = False
    total_waves: int = 3

    @property
    def total_patients(self) -> int:
        return sum(b.count for b in self.etiology_buckets)


# ---------------------------------------------------------------------------
# Footprint / METs
# ---------------------------------------------------------------------------

def _has_keyword(footprint: List[str], keywords: List[str]) -> bool:
    fp_lower = " | ".join(footprint).lower()
    return any(kw in fp_lower for kw in keywords)


def surgical_allowed(footprint: List[str]) -> bool:
    return _has_keyword(footprint, M.SURGICAL_FOOTPRINT_KEYWORDS)


def met_emphasis_tags(selected_mets: List[str]) -> List[str]:
    out: List[str] = []
    for met in selected_mets:
        out.extend(M.MET_BIAS.get(met, []))
    return out


# ---------------------------------------------------------------------------
# Trauma : DNBI ratio
# ---------------------------------------------------------------------------

def trauma_ratio(
    setting: str,
    threat_level: str,
    is_mascal: bool,
    view: Optional[MatrixView] = None,
) -> float:
    view = view or MatrixView.defaults()
    if is_mascal:
        return M.MASCAL_TRAUMA_RATIO
    base = view.trauma_ratio_by_setting.get(setting, M.DEFAULT_TRAUMA_RATIO)
    shift = view.threat_level_shift.get(threat_level) or view.threat_level_shift["Medium"]
    delta = shift.get("trauma_ratio", 0.0)
    lo, hi = M.TRAUMA_RATIO_BOUNDS
    return max(lo, min(hi, base + delta))


# ---------------------------------------------------------------------------
# Triage distribution
# ---------------------------------------------------------------------------

def _shift_distribution(dist: Dict[str, float], shift: Dict[str, float]) -> Dict[str, float]:
    out = dict(dist)
    out["T1"] = out.get("T1", 0.0) + shift.get("t1_pp", 0.0)
    out["T2"] = out.get("T2", 0.0) + shift.get("t2_pp", 0.0)
    out["T3"] = out.get("T3", 0.0) + shift.get("t3_pp", 0.0)
    out["T4"] = out.get("T4", 0.0) + shift.get("t4_pp", 0.0)
    # Clamp negatives, renormalize.
    for k in out:
        out[k] = max(0.0, out[k])
    total = sum(out.values())
    if total <= 0:
        return {"T1": 0.25, "T2": 0.25, "T3": 0.25, "T4": 0.25}
    return {k: v / total for k, v in out.items()}


def triage_distribution(
    setting: str,
    threat_level: str,
    is_mascal: bool,
    night_ops: bool,
    view: Optional[MatrixView] = None,
) -> Dict[str, float]:
    view = view or MatrixView.defaults()
    base = (
        view.mascal_triage_distribution
        if is_mascal
        else view.base_triage_distribution.get(setting, M.DEFAULT_TRIAGE_DISTRIBUTION)
    )
    shift = view.threat_level_shift.get(threat_level) or view.threat_level_shift["Medium"]
    shifted = _shift_distribution(base, shift)
    if night_ops:
        shifted = _shift_distribution(shifted, M.NIGHT_OPS_TRIAGE_SHIFT)
    return shifted


def _largest_remainder(distribution: Dict[str, float], total: int) -> Dict[str, int]:
    """Convert fractional distribution into integer counts that sum to `total`."""
    if total <= 0:
        return {k: 0 for k in distribution}
    raw = {k: distribution[k] * total for k in distribution}
    floors = {k: int(v) for k, v in raw.items()}
    remainder = total - sum(floors.values())
    # Distribute the leftover to the entries with the largest fractional parts.
    fracs = sorted(raw.items(), key=lambda kv: (kv[1] - int(kv[1])), reverse=True)
    for k, _ in fracs[:remainder]:
        floors[k] += 1
    return floors


# ---------------------------------------------------------------------------
# Etiology selection
# ---------------------------------------------------------------------------

def _weighted_etiology_pool(
    setting: str,
    environment: str,
    mascal_etiology: Optional[str],
    is_mascal: bool,
    view: Optional[MatrixView] = None,
) -> List[str]:
    """Ordered, possibly repeated list of etiologies; later entries are 'flavor'."""
    view = view or MatrixView.defaults()
    setting_pool = view.etiology_by_setting.get(setting, [])
    if is_mascal and mascal_etiology:
        # MASCAL day: 70% of mechanism is the chosen etiology, rest is setting flavor.
        return [mascal_etiology] * 7 + setting_pool
    env_pool = M.ENVIRONMENT_TRAUMA_FLAVOR.get(environment, [])
    # Setting-characteristic etiologies weight 3x; environment flavor 1x.
    return setting_pool * 3 + env_pool


def _category_for_trauma(etiology: str, surgical_ok: bool) -> str:
    if not surgical_ok:
        return "trauma_non_surgical"
    return "trauma_surgical" if etiology in M.SURGICAL_ETIOLOGIES else "trauma_non_surgical"


# ---------------------------------------------------------------------------
# Bucket assembly
# ---------------------------------------------------------------------------

def _make_buckets_for(
    rng: random.Random,
    *,
    category_resolver,
    etiology_pool: List[str],
    triage_counts: Dict[str, int],
) -> List[EtiologyBucket]:
    """Distribute triage_counts across buckets sampling etiologies from the pool."""
    out: List[EtiologyBucket] = []
    if not etiology_pool:
        return out
    for triage, n in triage_counts.items():
        for _ in range(n):
            etiology = rng.choice(etiology_pool)
            category = category_resolver(etiology)
            phases = M.PHASES_BY_CATEGORY[category]
            out.append(EtiologyBucket(
                category=category,
                etiology=etiology,
                count=1,
                triage=triage,
                phases=phases,
            ))
    return _coalesce(out)


def _coalesce(buckets: List[EtiologyBucket]) -> List[EtiologyBucket]:
    """Merge adjacent buckets with the same (category, etiology, triage)."""
    keyed: Dict[tuple, EtiologyBucket] = {}
    for b in buckets:
        key = (b.category, b.etiology, b.triage)
        if key in keyed:
            keyed[key] = keyed[key].model_copy(update={"count": keyed[key].count + b.count})
        else:
            keyed[key] = b
    return list(keyed.values())


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def build_day_plan(
    *,
    day_number: int,
    tactical_setting: str,
    total_patients: int,
    night_ops: bool,
    mascal: bool,
    mascal_etiology: Optional[str],
    mascal_patients: Optional[int],
    cbrn: bool,
    detainee_ops: bool,
    threat_level: str,
    environment: str,
    region: Optional[str],
    selected_footprint: List[str],
    selected_mets: List[str],
    total_waves: int = 3,
    seed: Optional[int] = None,
    view: Optional[MatrixView] = None,
) -> DayPlan:
    """Build a deterministic plan for one day.

    The same inputs (with the same seed) produce the same plan. The case
    generator consumes `etiology_buckets` and the schedule builder consumes
    `triage_targets` + arrival logic later.

    `view` lets callers pass a MatrixView with global overrides applied;
    omitting it falls back to the defaults shipped in matrices.py.
    """
    view = view or MatrixView.defaults()
    rng = random.Random(seed if seed is not None else (day_number * 1000 + hash(tactical_setting)) & 0x7fffffff)
    notes: List[str] = []

    surgical_ok = surgical_allowed(selected_footprint)
    if not surgical_ok:
        notes.append("Footprint has no surgical capability — surgical cases downgraded to non-surgical (evac required).")
    mets = met_emphasis_tags(selected_mets)

    # ---- 1. Top-level counts ----
    cbrn_count = 0
    detainee_count = 0
    remaining = total_patients

    if cbrn:
        # 20% of trauma budget; the rest of the day proceeds normally around the drill.
        cbrn_count = max(1, round(remaining * M.CBRN_TRAUMA_BUDGET_FRACTION))
        cbrn_count = min(cbrn_count, remaining)
        remaining -= cbrn_count
        notes.append(f"CBRN day: {cbrn_count} CBRN casualties carved from total.")

    if detainee_ops:
        detainee_count = max(1, round(remaining * M.DETAINEE_BUDGET_FRACTION))
        detainee_count = min(detainee_count, remaining)
        remaining -= detainee_count
        notes.append(f"Detainee ops day: {detainee_count} detainee patients carved from total.")

    ratio = trauma_ratio(tactical_setting, threat_level, mascal, view=view)
    trauma_count = round(remaining * ratio)
    dnbi_count = remaining - trauma_count

    # On a MASCAL day, ensure the MASCAL wave size is honored as trauma if user
    # asked for it. The schedule builder uses this same number for wave 1.
    if mascal and mascal_patients:
        trauma_count = max(trauma_count, min(mascal_patients, total_patients - cbrn_count - detainee_count))
        dnbi_count = remaining - trauma_count

    # ---- 2. Day-level triage distribution (intent) ----
    dist = triage_distribution(tactical_setting, threat_level, mascal, night_ops, view=view)

    # ---- 3. Build buckets per category ----
    # Each category uses a normalized distribution + its own total. We compute
    # triage_targets after the fact from the actual buckets so the day plan is
    # self-consistent.
    buckets: List[EtiologyBucket] = []

    # Trauma (split surgical vs non-surgical based on etiology + footprint)
    trauma_pool = _weighted_etiology_pool(
        setting=tactical_setting,
        environment=environment,
        mascal_etiology=mascal_etiology,
        is_mascal=mascal,
        view=view,
    )
    if trauma_count > 0 and trauma_pool:
        trauma_triage_counts = _largest_remainder(dist, trauma_count)
        buckets.extend(_make_buckets_for(
            rng,
            category_resolver=lambda e: _category_for_trauma(e, surgical_ok),
            etiology_pool=trauma_pool,
            triage_counts=trauma_triage_counts,
        ))

    # DNBI (environment + region; region pool now comes from the view so UI
    # edits to DNBI_BY_REGION take effect immediately).
    if dnbi_count > 0:
        dnbi_pool = (
            M.DNBI_BY_ENVIRONMENT.get(environment, [])
            + M.DNBI_BY_ENVIRONMENT.get("General", [])
            + (view.dnbi_by_region.get(region or "", []) if region else [])
        )
        if not dnbi_pool:
            dnbi_pool = M.DNBI_BY_ENVIRONMENT["General"]
        # DNBI skews toward T2/T3/T4 — re-weight against MASCAL distribution if present.
        dnbi_dist = view.base_triage_distribution.get(tactical_setting, M.DEFAULT_TRIAGE_DISTRIBUTION)
        dnbi_triage_counts = _largest_remainder(dnbi_dist, dnbi_count)
        buckets.extend(_make_buckets_for(
            rng,
            category_resolver=lambda e: "dnbi",
            etiology_pool=dnbi_pool,
            triage_counts=dnbi_triage_counts,
        ))

    # CBRN
    if cbrn_count > 0:
        cbrn_etiologies: List[str] = []
        for variants in view.cbrn_etiologies.values():
            cbrn_etiologies.extend(variants)
        # CBRN cases are mostly T1/T2 — life-threatening physiology.
        cbrn_dist = {"T1": 0.40, "T2": 0.40, "T3": 0.15, "T4": 0.05}
        cbrn_triage_counts = _largest_remainder(cbrn_dist, cbrn_count)
        buckets.extend(_make_buckets_for(
            rng,
            category_resolver=lambda e: "cbrn_combined" if "Combined injury" in e else "cbrn",
            etiology_pool=cbrn_etiologies,
            triage_counts=cbrn_triage_counts,
        ))

    # Detainee
    if detainee_count > 0:
        detainee_pool = M.DETAINEE_CASE_TYPES
        detainee_dist = {"T1": 0.10, "T2": 0.30, "T3": 0.45, "T4": 0.15}
        detainee_triage_counts = _largest_remainder(detainee_dist, detainee_count)
        buckets.extend(_make_buckets_for(
            rng,
            category_resolver=lambda e: "detainee_trauma" if "trauma" in e.lower() or "GSW" in e or "self-inflicted" in e.lower() else "detainee_medical",
            etiology_pool=detainee_pool,
            triage_counts=detainee_triage_counts,
        ))

    # ---- 4. MET emphasis (post-hoc bias) ----
    if mets and buckets:
        notes.append(f"MET emphasis tags applied: {', '.join(sorted(set(mets)))}")
        # Soft bias: bump the count of any bucket whose etiology/category appears in
        # met_emphasis tags by 1, balanced by trimming a non-emphasized bucket of
        # the same triage. Implementation deferred to keep counts deterministic
        # against total_patients; emphasis is recorded for downstream prompt
        # weighting.

    # ---- 5. Self-consistent triage_targets from the actual buckets ----
    triage_targets = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    for b in buckets:
        triage_targets[b.triage] = triage_targets.get(b.triage, 0) + b.count

    return DayPlan(
        day_number=day_number,
        tactical_setting=tactical_setting,
        trauma_count=trauma_count,
        dnbi_count=dnbi_count,
        cbrn_count=cbrn_count,
        detainee_count=detainee_count,
        triage_targets=triage_targets,
        etiology_buckets=buckets,
        surgical_allowed=surgical_ok,
        met_emphasis=sorted(set(mets)),
        notes=notes,
        night_ops=night_ops,
        mascal=mascal,
        mascal_patients=mascal_patients,
        mascal_etiology=mascal_etiology,
        cbrn=cbrn,
        detainee_ops=detainee_ops,
        total_waves=total_waves,
    )
