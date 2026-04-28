"""
Matrix overrides store.

Phase 6 lets instructors edit the casualty-mix and triage matrices through the
UI. The model:

- `MatrixView` is the merged result the planner reads (defaults + overrides).
- `MatrixOverrides` is a sparse Pydantic model with optional fields per table;
  unset fields fall back to the defaults shipped in `matrices.py`.
- `MatrixStore` persists a single global override row (Postgres or in-memory).
- Each generated exercise also carries a snapshot of the merged view it used
  (stored on the Exercise row) so /history shows what was active.

No auth on the store-level reads/writes — that's intentional for v1
(documented in STRATEGY.md). Lock down when auth lands.
"""

from __future__ import annotations

import abc
import asyncio
import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from . import matrices as M


_TRIAGE_KEYS = {"T1", "T2", "T3", "T4"}
_SHIFT_KEYS_NUMERIC = {"trauma_ratio", "t1_pp", "t2_pp", "t3_pp", "t4_pp"}


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _validate_distribution(d: Dict[str, float], label: str) -> Dict[str, float]:
    if set(d.keys()) != _TRIAGE_KEYS:
        raise ValueError(f"{label}: keys must be exactly {_TRIAGE_KEYS}, got {set(d.keys())}")
    for k, v in d.items():
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"{label}.{k}: must be in [0,1], got {v}")
    total = sum(d.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"{label}: triage shares must sum to 1.0 (got {total:.3f})")
    return d


def _validate_ratio(v: float, label: str) -> float:
    if not (0.0 <= v <= 1.0):
        raise ValueError(f"{label}: must be in [0,1], got {v}")
    return v


# ---------------------------------------------------------------------------
# Override schema (sparse; missing fields fall back to defaults)
# ---------------------------------------------------------------------------

class MatrixOverrides(BaseModel):
    """All fields are optional. Missing entries inherit defaults at merge time."""

    # Numeric (headline)
    trauma_ratio_by_setting: Optional[Dict[str, float]] = None
    threat_level_shift: Optional[Dict[str, Dict[str, float]]] = None
    base_triage_distribution: Optional[Dict[str, Dict[str, float]]] = None
    mascal_triage_distribution: Optional[Dict[str, float]] = None

    # List editors
    etiology_by_setting: Optional[Dict[str, List[str]]] = None
    dnbi_by_region: Optional[Dict[str, List[str]]] = None
    cbrn_etiologies: Optional[Dict[str, List[str]]] = None

    @field_validator("trauma_ratio_by_setting")
    @classmethod
    def _check_ratios(cls, v):
        if v is None:
            return v
        return {k: _validate_ratio(val, f"trauma_ratio_by_setting[{k}]") for k, val in v.items()}

    @field_validator("base_triage_distribution")
    @classmethod
    def _check_base_triage(cls, v):
        if v is None:
            return v
        return {k: _validate_distribution(d, f"base_triage_distribution[{k}]") for k, d in v.items()}

    @field_validator("mascal_triage_distribution")
    @classmethod
    def _check_mascal_triage(cls, v):
        if v is None:
            return v
        return _validate_distribution(v, "mascal_triage_distribution")

    @field_validator("threat_level_shift")
    @classmethod
    def _check_threat_shift(cls, v):
        if v is None:
            return v
        for level, deltas in v.items():
            extra = set(deltas.keys()) - _SHIFT_KEYS_NUMERIC
            if extra:
                raise ValueError(f"threat_level_shift[{level}]: unknown keys {extra}")
        return v


# ---------------------------------------------------------------------------
# Merged view (defaults + overrides) — the planner reads from this
# ---------------------------------------------------------------------------

class MatrixView(BaseModel):
    """Snapshot of every matrix value the planner needs.

    Construct with `MatrixView.from_overrides(overrides)`. Stored verbatim on
    each Exercise row (via Exercise.matrix_snapshot) so /history can show what
    was active when the exercise was generated.
    """

    trauma_ratio_by_setting: Dict[str, float]
    threat_level_shift: Dict[str, Dict[str, float]]
    base_triage_distribution: Dict[str, Dict[str, float]]
    mascal_triage_distribution: Dict[str, float]
    etiology_by_setting: Dict[str, List[str]]
    dnbi_by_region: Dict[str, List[str]]
    cbrn_etiologies: Dict[str, List[str]]

    @classmethod
    def defaults(cls) -> "MatrixView":
        """Snapshot of the matrices.py module statics."""
        return cls(
            trauma_ratio_by_setting=dict(M.TRAUMA_RATIO_BY_SETTING),
            threat_level_shift={k: dict(v) for k, v in M.THREAT_LEVEL_SHIFT.items()},
            base_triage_distribution={k: dict(v) for k, v in M.BASE_TRIAGE_DISTRIBUTION.items()},
            mascal_triage_distribution=dict(M.MASCAL_TRIAGE_DISTRIBUTION),
            etiology_by_setting={k: list(v) for k, v in M.ETIOLOGY_BY_SETTING.items()},
            dnbi_by_region={k: list(v) for k, v in M.DNBI_BY_REGION.items()},
            cbrn_etiologies={k: list(v) for k, v in M.CBRN_ETIOLOGIES.items()},
        )

    @classmethod
    def from_overrides(cls, overrides: Optional[MatrixOverrides]) -> "MatrixView":
        view = cls.defaults()
        if overrides is None:
            return view
        if overrides.trauma_ratio_by_setting is not None:
            view.trauma_ratio_by_setting = {**view.trauma_ratio_by_setting, **overrides.trauma_ratio_by_setting}
        if overrides.threat_level_shift is not None:
            merged = {k: dict(v) for k, v in view.threat_level_shift.items()}
            for level, deltas in overrides.threat_level_shift.items():
                merged.setdefault(level, {}).update(deltas)
            view.threat_level_shift = merged
        if overrides.base_triage_distribution is not None:
            merged = {k: dict(v) for k, v in view.base_triage_distribution.items()}
            for setting, dist in overrides.base_triage_distribution.items():
                merged[setting] = dict(dist)
            view.base_triage_distribution = merged
        if overrides.mascal_triage_distribution is not None:
            view.mascal_triage_distribution = dict(overrides.mascal_triage_distribution)
        if overrides.etiology_by_setting is not None:
            merged = {k: list(v) for k, v in view.etiology_by_setting.items()}
            for setting, etiologies in overrides.etiology_by_setting.items():
                merged[setting] = list(etiologies)
            view.etiology_by_setting = merged
        if overrides.dnbi_by_region is not None:
            merged = {k: list(v) for k, v in view.dnbi_by_region.items()}
            for region, items in overrides.dnbi_by_region.items():
                merged[region] = list(items)
            view.dnbi_by_region = merged
        if overrides.cbrn_etiologies is not None:
            merged = {k: list(v) for k, v in view.cbrn_etiologies.items()}
            for cat, items in overrides.cbrn_etiologies.items():
                merged[cat] = list(items)
            view.cbrn_etiologies = merged
        return view


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class MatrixStore(abc.ABC):
    @abc.abstractmethod
    async def get_overrides(self) -> MatrixOverrides: ...

    @abc.abstractmethod
    async def set_overrides(self, overrides: MatrixOverrides) -> None: ...

    @abc.abstractmethod
    async def clear_overrides(self) -> None: ...


class InMemoryMatrixStore(MatrixStore):
    def __init__(self) -> None:
        self._overrides = MatrixOverrides()
        self._lock = asyncio.Lock()

    async def get_overrides(self) -> MatrixOverrides:
        async with self._lock:
            return self._overrides.model_copy()

    async def set_overrides(self, overrides: MatrixOverrides) -> None:
        async with self._lock:
            self._overrides = overrides

    async def clear_overrides(self) -> None:
        async with self._lock:
            self._overrides = MatrixOverrides()


class PostgresMatrixStore(MatrixStore):
    """Persists a single-row override blob in `matrix_settings` (id=1)."""

    SINGLETON_ID = 1

    def __init__(self, session_factory) -> None:
        self._SessionLocal = session_factory

    async def get_overrides(self) -> MatrixOverrides:
        return await asyncio.to_thread(self._get_sync)

    def _get_sync(self) -> MatrixOverrides:
        from .db import MatrixSetting
        db = self._SessionLocal()
        try:
            row = db.query(MatrixSetting).filter(MatrixSetting.id == self.SINGLETON_ID).first()
            if row is None or not row.overrides:
                return MatrixOverrides()
            return MatrixOverrides(**row.overrides)
        finally:
            db.close()

    async def set_overrides(self, overrides: MatrixOverrides) -> None:
        await asyncio.to_thread(self._set_sync, overrides)

    def _set_sync(self, overrides: MatrixOverrides) -> None:
        from .db import MatrixSetting
        db = self._SessionLocal()
        try:
            row = db.query(MatrixSetting).filter(MatrixSetting.id == self.SINGLETON_ID).first()
            payload = overrides.model_dump(exclude_none=True)
            now = datetime.utcnow()
            if row is None:
                row = MatrixSetting(id=self.SINGLETON_ID, overrides=payload, updated_at=now)
                db.add(row)
            else:
                row.overrides = payload
                row.updated_at = now
            db.commit()
        finally:
            db.close()

    async def clear_overrides(self) -> None:
        await asyncio.to_thread(self._clear_sync)

    def _clear_sync(self) -> None:
        from .db import MatrixSetting
        db = self._SessionLocal()
        try:
            row = db.query(MatrixSetting).filter(MatrixSetting.id == self.SINGLETON_ID).first()
            if row is None:
                return
            row.overrides = {}
            row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Singleton + helpers
# ---------------------------------------------------------------------------

_store: Optional[MatrixStore] = None


def get_matrix_store() -> MatrixStore:
    global _store
    if _store is None:
        from .db import SessionLocal
        if SessionLocal is not None:
            _store = PostgresMatrixStore(SessionLocal)
        else:
            _store = InMemoryMatrixStore()
    return _store


def reset_matrix_store_for_tests() -> None:
    global _store
    _store = None


async def get_active_view() -> MatrixView:
    """Convenience: read overrides from the store, merge with defaults, return
    the view the planner should use. Save this view onto the Exercise row at
    generate time so /history shows what was active."""
    overrides = await get_matrix_store().get_overrides()
    return MatrixView.from_overrides(overrides)
