"""Compare case-generation quality across configured providers.

Runs the same set of canonical BatchItems through every provider you ask for,
captures both raw outputs and a diffable summary, and writes everything to a
timestamped directory under `out/`. Intended for eyeballing case quality
before flipping `CASE_PROVIDER` in production.

Usage:
  # Compare Gemini and Bedrock (default), 5 cases each
  python -m backend.scripts.compare_providers --providers gemini bedrock

  # Just Bedrock, with a non-default model id
  BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-7-20250929-v1:0 \\
    python -m backend.scripts.compare_providers --providers bedrock

  # Custom output directory
  python -m backend.scripts.compare_providers --out ./bench/2026-04-29

The script reads the same env vars the running server reads:
  GEMINI_API_KEY            (gemini provider)
  AWS_REGION + BEDROCK_MODEL_ID + AWS creds  (bedrock provider)

Outputs (per provider, in `<out>/<provider>/`):
  case_<idx>.json      — single-case path, raw provider output
  batch.json           — multi-case batch path output
  summary.json         — counts + timings + first-glance metrics

Plus a top-level `<out>/comparison.md` table that puts the providers
side-by-side on the metrics that matter for first-glance triage:
  - cases successfully parsed
  - mean / max latency per call
  - mean / median output length
  - presence of the required schema sections (zmist, nine_line, phases, ...)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.providers.base import BatchItem, CaseProvider


# A small but representative set of cases — covers trauma surgical, trauma
# non-surgical, DNBI, CBRN. Keep the count low: each call costs real money on
# Bedrock / Gemini paid tier, and the goal is qualitative comparison, not
# load testing.
CANONICAL_BATCH: List[BatchItem] = [
    BatchItem(
        key=("trauma_surgical", 0),
        case_type="Penetrating chest trauma with hemothorax",
        mechanism="GSW/Small Arms",
        environment="Urban",
        region="CENTCOM",
        phases=["DCR", "DCS", "PCC"],
        target_triage="T1",
        category="trauma_surgical",
    ),
    BatchItem(
        key=("trauma_surgical_drone", 1),
        case_type="Multiple penetrating fragment wounds (face/neck)",
        mechanism="Fragmentation Drones",
        environment="Desert",
        region="CENTCOM",
        phases=["DCR", "DCS", "PCC"],
        target_triage="T2",
        category="trauma_surgical",
    ),
    BatchItem(
        key=("trauma_non_surgical", 2),
        case_type="Traumatic brain injury - moderate",
        mechanism="Indirect Fire/Mortar",
        environment="Mountain",
        region="EUCOM",
        phases=["DCR", "PCC"],
        target_triage="T2",
        category="trauma_non_surgical",
    ),
    BatchItem(
        key=("dnbi", 3),
        case_type="Severe falciparum malaria with cerebral involvement",
        mechanism="DNBI - Jungle",
        environment="Jungle",
        region="AFRICOM",
        phases=["DCR", "PCC"],
        target_triage="T2",
        category="dnbi",
    ),
    BatchItem(
        key=("cbrn_combined", 4),
        case_type="Combined injury (trauma + radiation)",
        mechanism="CBRN exposure",
        environment="General",
        region="INDOPACOM",
        phases=["DCR", "DCS", "PCC"],
        target_triage="T1",
        category="cbrn_combined",
    ),
]


REQUIRED_SECTIONS = ("meta", "learning_objectives", "zmist", "nine_line",
                     "patient_data", "triage_category", "phases",
                     "evacuation", "debrief_questions")


def _load_provider(name: str) -> CaseProvider:
    """Construct a provider by env-var name. Routed through the same factory
    the server uses so behavior matches production exactly."""
    os.environ["CASE_PROVIDER"] = name
    from backend.providers import get_case_provider
    get_case_provider.cache_clear()
    return get_case_provider()


def _schema_score(case: Dict[str, Any]) -> Tuple[int, int]:
    """How many of the required top-level sections are present and non-empty."""
    if not isinstance(case, dict):
        return 0, len(REQUIRED_SECTIONS)
    present = sum(1 for k in REQUIRED_SECTIONS if case.get(k))
    return present, len(REQUIRED_SECTIONS)


def _output_size_chars(case: Dict[str, Any]) -> int:
    return len(json.dumps(case, separators=(",", ":")))


async def _run_single_case(provider: CaseProvider, item: BatchItem) -> Tuple[Optional[Dict[str, Any]], float, Optional[str]]:
    start = time.monotonic()
    try:
        case = await provider.generate_case(
            case_type=item.case_type,
            mechanism=item.mechanism,
            environment=item.environment,
            region=item.region,
            phases=item.phases,
            target_triage=item.target_triage,
        )
        return case, time.monotonic() - start, None
    except Exception as e:
        return None, time.monotonic() - start, f"{type(e).__name__}: {e}"


async def _run_batch(provider: CaseProvider, items: List[BatchItem]) -> Tuple[Optional[List[Dict[str, Any]]], float, Optional[str]]:
    start = time.monotonic()
    try:
        cases = await provider.generate_batch(items)
        return cases, time.monotonic() - start, None
    except Exception as e:
        return None, time.monotonic() - start, f"{type(e).__name__}: {e}"


async def _bench_one_provider(name: str, items: List[BatchItem], out_dir: Path) -> Dict[str, Any]:
    print(f"\n=== {name} ===", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "provider": name,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "single_calls": [],
        "batch": {},
    }
    try:
        provider = _load_provider(name)
    except Exception as e:
        print(f"  failed to construct provider: {type(e).__name__}: {e}", flush=True)
        summary["construct_error"] = f"{type(e).__name__}: {e}"
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return summary

    # Single-case path, one item at a time.
    schema_scores: List[float] = []
    sizes: List[int] = []
    latencies: List[float] = []
    for idx, item in enumerate(items):
        case, latency, err = await _run_single_case(provider, item)
        latencies.append(latency)
        record: Dict[str, Any] = {
            "idx": idx, "case_type": item.case_type,
            "latency_s": round(latency, 2),
        }
        if case is None:
            record["error"] = err
            print(f"  case[{idx}] {item.case_type[:50]}  FAILED ({latency:.1f}s): {err}", flush=True)
        else:
            present, total = _schema_score(case)
            size = _output_size_chars(case)
            schema_scores.append(present / total)
            sizes.append(size)
            record["schema_score"] = f"{present}/{total}"
            record["output_chars"] = size
            (out_dir / f"case_{idx}.json").write_text(json.dumps(case, indent=2))
            print(f"  case[{idx}] {item.case_type[:50]}  ok ({latency:.1f}s, {present}/{total} sections, {size} chars)", flush=True)
        summary["single_calls"].append(record)

    # Batch path, all items at once.
    print(f"  --- batch path ({len(items)} cases) ---", flush=True)
    batch_cases, batch_latency, batch_err = await _run_batch(provider, items)
    summary["batch"]["latency_s"] = round(batch_latency, 2)
    if batch_err:
        summary["batch"]["error"] = batch_err
        print(f"  batch FAILED ({batch_latency:.1f}s): {batch_err}", flush=True)
    else:
        (out_dir / "batch.json").write_text(json.dumps(batch_cases, indent=2))
        bsizes = [_output_size_chars(c) for c in batch_cases]
        bscores = [_schema_score(c)[0] / _schema_score(c)[1] for c in batch_cases]
        summary["batch"]["count"] = len(batch_cases)
        summary["batch"]["mean_schema_score"] = round(statistics.mean(bscores), 3)
        summary["batch"]["mean_output_chars"] = int(statistics.mean(bsizes)) if bsizes else 0
        print(f"  batch ok ({batch_latency:.1f}s, {len(batch_cases)} cases, mean schema {statistics.mean(bscores):.2f})", flush=True)

    # Aggregate single-call stats.
    if schema_scores:
        summary["single_calls_aggregate"] = {
            "n_succeeded": len(schema_scores),
            "mean_schema_score": round(statistics.mean(schema_scores), 3),
            "mean_latency_s": round(statistics.mean(latencies), 2),
            "max_latency_s": round(max(latencies), 2),
            "mean_output_chars": int(statistics.mean(sizes)) if sizes else 0,
            "median_output_chars": int(statistics.median(sizes)) if sizes else 0,
        }
    summary["finished_at"] = datetime.utcnow().isoformat() + "Z"
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _comparison_markdown(summaries: List[Dict[str, Any]]) -> str:
    """Format a side-by-side comparison table for at-a-glance triage."""
    lines = ["# Provider comparison\n"]
    lines.append(f"_Generated {datetime.utcnow().isoformat()}Z_\n")
    lines.append("## Single-call path\n")
    lines.append("| metric | " + " | ".join(s["provider"] for s in summaries) + " |")
    lines.append("|---|" + "|".join(["---"] * len(summaries)) + "|")

    def cell(s: Dict[str, Any], path: List[str], fmt: str = "{}") -> str:
        v: Any = s
        for k in path:
            if not isinstance(v, dict) or k not in v:
                return "—"
            v = v[k]
        return fmt.format(v) if v is not None else "—"

    rows = [
        ("succeeded / total", lambda s: f"{s.get('single_calls_aggregate', {}).get('n_succeeded', 0)} / {len(s.get('single_calls', []))}"),
        ("mean schema score", lambda s: cell(s, ["single_calls_aggregate", "mean_schema_score"])),
        ("mean latency (s)",  lambda s: cell(s, ["single_calls_aggregate", "mean_latency_s"])),
        ("max latency (s)",   lambda s: cell(s, ["single_calls_aggregate", "max_latency_s"])),
        ("mean output (chars)", lambda s: cell(s, ["single_calls_aggregate", "mean_output_chars"])),
    ]
    for label, fn in rows:
        lines.append(f"| {label} | " + " | ".join(str(fn(s)) for s in summaries) + " |")

    lines.append("\n## Batch path\n")
    lines.append("| metric | " + " | ".join(s["provider"] for s in summaries) + " |")
    lines.append("|---|" + "|".join(["---"] * len(summaries)) + "|")
    rows_b = [
        ("succeeded",           lambda s: "yes" if s.get("batch", {}).get("count") else "no"),
        ("count returned",      lambda s: cell(s, ["batch", "count"])),
        ("latency (s)",         lambda s: cell(s, ["batch", "latency_s"])),
        ("mean schema score",   lambda s: cell(s, ["batch", "mean_schema_score"])),
        ("mean output (chars)", lambda s: cell(s, ["batch", "mean_output_chars"])),
    ]
    for label, fn in rows_b:
        lines.append(f"| {label} | " + " | ".join(str(fn(s)) for s in summaries) + " |")

    lines.append("\n## How to read this\n")
    lines.append("- **schema score** is fraction of required top-level sections "
                 "(meta, zmist, nine_line, phases, …) that came back populated. "
                 "Higher is better; 1.0 means the model produced every section.\n")
    lines.append("- **latency** is wall-clock; lower is better but a 2× faster "
                 "model that drops a section is usually worse.\n")
    lines.append("- **output chars** is a rough proxy for verbosity / detail. "
                 "Compare against the schema score: high chars + low schema = "
                 "model is rambling instead of filling the structure.\n")
    lines.append("- For real qualitative judgment, open `<provider>/case_*.json` "
                 "and read the cases side-by-side.\n")
    return "\n".join(lines)


async def _main(args: argparse.Namespace) -> int:
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    for provider_name in args.providers:
        try:
            summary = await _bench_one_provider(
                provider_name, CANONICAL_BATCH, out_root / provider_name,
            )
            summaries.append(summary)
        except Exception:  # pragma: no cover  (defensive)
            traceback.print_exc()
            summaries.append({"provider": provider_name, "fatal": traceback.format_exc()})

    md = _comparison_markdown(summaries)
    (out_root / "comparison.md").write_text(md)
    print(f"\nWrote {out_root}/comparison.md", flush=True)
    print("\n" + md, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--providers", nargs="+", default=["gemini", "bedrock"],
        help="Provider names to compare (gemini, bedrock, stub). Default: gemini bedrock.",
    )
    default_out = f"out/compare_{datetime.utcnow():%Y%m%d_%H%M%S}"
    parser.add_argument(
        "--out", default=default_out,
        help=f"Output directory (default: {default_out})",
    )
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
