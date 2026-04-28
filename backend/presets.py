"""
Preset bundles of MatrixOverrides shipped server-side.

Each preset is a JSON file in `preset_data/` whose contents validate against
MatrixOverrides. Loading a preset writes those overrides into the global
matrix store; the user can then generate exercises against the new matrix.

DRAFT presets — the values are illustrative starting points. They need SME
review before being held out as authoritative.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

from .matrix_store import MatrixOverrides, get_matrix_store


_PRESET_DIR = os.path.join(os.path.dirname(__file__), "preset_data")


def _read_preset_file(name: str) -> Dict:
    path = os.path.join(_PRESET_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_presets() -> List[Dict[str, str]]:
    """Return [{name, label, description}] for every JSON file in preset_data/.

    Reads all files at call time (cheap; few files, small payload). The wrapper
    JSON shape is `{"label": str, "description": str, "overrides": {...}}`.
    """
    out: List[Dict[str, str]] = []
    if not os.path.isdir(_PRESET_DIR):
        return out
    for fn in sorted(os.listdir(_PRESET_DIR)):
        if not fn.endswith(".json"):
            continue
        name = fn[:-5]
        try:
            data = _read_preset_file(name)
            out.append({
                "name": name,
                "label": data.get("label", name),
                "description": data.get("description", ""),
            })
        except Exception:
            # Skip malformed files; don't break /presets for one bad bundle.
            continue
    return out


async def apply_preset(name: str) -> MatrixOverrides:
    """Load the named preset, write it into the matrix store, return the new
    overrides. Raises FileNotFoundError if the preset doesn't exist or
    ValueError if it doesn't validate."""
    data = _read_preset_file(name)
    overrides_payload = data.get("overrides", {})
    overrides = MatrixOverrides(**overrides_payload)  # validates
    await get_matrix_store().set_overrides(overrides)
    return overrides
