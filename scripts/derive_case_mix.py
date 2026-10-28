"""Summarise the OLD generator's case mix from an export of archived exercises (comparison data only, not used at runtime).

    python scripts/derive_case_mix.py path/to/exercises.json [--max-id 36]

Groups every archived case by the scenario selections that produced it (DNBI, routine trauma by
tactical setting, MASCAL by etiology) and records the triage mix, the disposition mix given triage,
and the share of civilian / partner-force patients. Small groups are pulled toward their pooled
parent so a handful of cases cannot swing a percentage.

Use --max-id to pin the export to exercises generated BEFORE the case-mix assignment existed, so the
tables are not trained on their own output.
"""
import collections as C
import json
import re
import sys
from datetime import date

SHRINK_K = 15  # a group of n cases counts as n/(n+K) of its own rate, the rest from its parent
TRIAGE = ("T1", "T2", "T3", "Expectant")
DISPO = ("RTD", "Evac to Role 3", "Hold at Role 2", "Died of Wounds", "Expectant")
HUMANITARIAN = {"Humanitarian Assistance", "Stability Operations"}


def J(v):
    return json.loads(v) if isinstance(v, str) else v


def triage_key(t):
    m = re.search(r"T\s*([1-4])", str(t or ""), re.I)
    if m:
        return {"1": "T1", "2": "T2", "3": "T3", "4": "Expectant"}[m.group(1)]
    return "Expectant" if "expect" in str(t or "").lower() else None


def dispo_key(d):
    d = str(d or "").lower()
    if d.startswith("rtd"):
        return "RTD"
    if d.startswith("evac"):
        return "Evac to Role 3"
    if d.startswith("hold"):
        return "Hold at Role 2"
    if "died" in d or d.startswith("dow"):
        return "Died of Wounds"
    if "expectant" in d:
        return "Expectant"
    return None


def population(case):
    t = " ".join(str(x) for x in ((case.get("patient_data") or {}).get("demographics"),
                                  (case.get("nine_line") or {}).get("line8_nationality"))).lower()
    if re.search(r"detainee|epw|enemy (combatant|prisoner|soldier|fighter)|insurgent|opfor|prisoner of war|captured", t):
        return "enemy"
    if re.search(r"civilian|host[- ]nation|local national|non-combatant|child|pediatric", t):
        return "civilian"
    if re.search(r"partner|allied|coalition|nato", t):
        return "partner"
    return "us"


def dist(counter, keys):
    n = sum(counter[k] for k in keys)
    return {k: (counter[k] / n if n else 0.0) for k in keys}


def shrink(own_counter, parent, keys, k=SHRINK_K):
    n = sum(own_counter[x] for x in keys)
    own = dist(own_counter, keys)
    return {x: (n * own[x] + k * parent[x]) / (n + k) for x in keys}, n


def main(path, max_id):
    rows = [r for r in J(open(path, encoding="utf-8").read()) if r["id"] <= max_id]
    tri = C.defaultdict(C.Counter)           # (kind, key) -> triage counts
    dis = C.defaultdict(C.Counter)           # (group, triage) -> disposition counts
    pop = C.defaultdict(C.Counter)           # daytype -> population counts
    for r in rows:
        cfg, msel, cases = J(r["config"]), J(r["msel_data"]), J(r["cases"])
        days = {d["day_number"]: d for d in cfg["days"]}
        by_zap = {str((c.get("zmist") or {}).get("zap")): c for c in cases}
        for m in msel:
            c = by_zap.get(str(m.get("zap")))
            if c is None:
                continue
            ev = str(m.get("event", ""))
            day = days.get(m.get("day"), {})
            dnbi = (m.get("pathway") == "MEDICAL"
                    or bool(re.match(r"\s*(dnbi|disease non)", str((c.get("zmist") or {}).get("mechanism", "")), re.I))
                    or "DNBI" in str(m.get("mechanism", "")))
            if ev.startswith("MASCAL") and not dnbi:
                kind, key = "mascal", (re.search(r"\((.*)\)", ev).group(1) if "(" in ev else "_generic")
            elif dnbi:
                kind, key = "dnbi", "_pooled"
            else:
                kind, key = "routine", day.get("tactical_setting", "_generic")
            t, d = triage_key(c.get("triage_category")), dispo_key(c.get("disposition"))
            if t:
                tri[(kind, key)][t] += 1
                if kind != "dnbi":
                    tri[(kind, "_pooled")][t] += 1
            group = "dnbi" if dnbi else "trauma"
            if t and d:
                dis[(group, t)][d] += 1
            daytype = "humanitarian" if day.get("tactical_setting") in HUMANITARIAN else "other"
            pop[daytype][population(c)] += 1

    out = {"derived_from": {"exercises": len(rows), "max_id": max_id, "date": str(date.today()),
                            "note": "Reflects the generator's output BEFORE case-mix assignment existed."},
           "triage": {"dnbi": {}, "routine": {}, "mascal": {}}, "disposition": {}, "population": {}}
    for kind in ("dnbi", "routine", "mascal"):
        pooled_counter = tri[(kind, "_pooled")]
        pooled = dist(pooled_counter, TRIAGE)
        out["triage"][kind]["_pooled"] = {"n": sum(pooled_counter.values()), **pooled}
        for (k, key), counter in tri.items():
            if k == kind and key != "_pooled":
                rate, n = shrink(counter, pooled, TRIAGE)
                out["triage"][kind][key] = {"n": n, **rate}
    for group in ("trauma", "dnbi"):
        all_counter = C.Counter()
        for (g, t), c in dis.items():
            if g == group:
                all_counter.update(c)
        parent = dist(all_counter, DISPO)
        out["disposition"][group] = {"_pooled": {"n": sum(all_counter.values()), **parent}}
        for t in TRIAGE:
            rate, n = shrink(dis[(group, t)], parent, DISPO)
            out["disposition"][group][t] = {"n": n, **rate}
    for daytype, counter in pop.items():
        d = dist(counter, ("us", "partner", "civilian", "enemy"))
        out["population"][daytype] = {"n": sum(counter.values()), **d}

    target = __file__.replace("scripts", "docs").replace("derive_case_mix.py", "archive_case_mix_baseline.json")
    json.dump(out, open(target, "w", encoding="utf-8"), indent=1)
    print("wrote", target)
    for kind in ("dnbi", "routine", "mascal"):
        for key, v in out["triage"][kind].items():
            print(f"  triage {kind:<8}{key:<26} n={v['n']:<4}", "  ".join(f"{t}={v[t]:.0%}" for t in TRIAGE))
    for group in ("trauma", "dnbi"):
        for t in TRIAGE:
            v = out["disposition"][group][t]
            print(f"  disposition {group:<7}{t:<10} n={v['n']:<4}", "  ".join(f"{k[:6]}={v[k]:.0%}" for k in DISPO))
    for k, v in out["population"].items():
        print(f"  population {k:<13} n={v['n']:<4}", "  ".join(f"{p}={v[p]:.0%}" for p in ("us", "partner", "civilian", "enemy")))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    mid = int(sys.argv[sys.argv.index("--max-id") + 1]) if "--max-id" in sys.argv else 10 ** 9
    main(args[0], mid)
