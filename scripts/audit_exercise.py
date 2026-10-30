"""Audit a finished exercise: does the schedule track the cases, the FRAGOs and the orders?

    python scripts/audit_exercise.py record.json [--docs DIR]

record.json is the output of GET /exercises/{id} (config, cases, msel_data, fragos). With --docs DIR (holding medroe.txt,
annex_q.txt, warno.txt extracted from the .docx files) it also checks the orders against the schedule and the cases.
Prints one line per finding, most serious first, and exits 1 if any is high.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import casemix, main, scenario  # noqa: E402

J = lambda v: json.loads(v) if isinstance(v, str) else v
HIGH, MED, LOW = "high", "medium", "low"


def audit_schedule(config, cases, msel, fragos):
    out = []
    add = lambda sev, area, msg: out.append((sev, area, msg))
    rows = [r for r in msel if "arr_raw" in r]
    by_case = {int(str(r["case_num"]).split()[1]): r for r in rows}
    days = {d["day_number"]: d for d in config["days"]}

    # --- completeness -------------------------------------------------------------------------------
    want = sum(d["total_patients"] + (d.get("mascal_patients") or 0 if d.get("mascal") else 0) for d in config["days"])
    if len(rows) != len(cases) or len(rows) != want:
        add(HIGH, "completeness", f"{len(rows)} schedule rows, {len(cases)} cases, {want} patients configured")
    zaps = [str(r.get("zap")) for r in rows]
    if len(set(zaps)) != len(zaps):
        add(HIGH, "completeness", "duplicate ZAP numbers in the schedule")
    if sorted(by_case) != list(range(1, len(rows) + 1)):
        add(HIGH, "completeness", "case numbers are not 1..N")

    # --- chronology ----------------------------------------------------------------------------------
    keys = [(r["day"], r["arr_raw"]) for r in rows]
    if keys != sorted(keys):
        add(MED, "chronology", "schedule rows are not in arrival order")
    for r in rows:
        arr = r["arr_raw"]
        poi = arr - int(r.get("transit_min") or 0)
        if str(r.get("route", "")).lower().startswith("walk"):
            gap = arr - poi if r.get("transit_min") else 0
            if gap > 60:
                add(MED, "chronology", f"{r['case_num']}: a walk-in with point of injury {gap // 60}h{gap % 60:02d} before arrival (evacuation transit applied to a walk-in)")
        if str(r.get("clinical_hour_bad", "")):
            pass
    for r in rows:
        case = cases[int(str(r["case_num"]).split()[1]) - 1]
        hour = (r["arr_raw"] % 1440) // 60
        is_night = hour >= 20 or hour < 3
        if (case.get("arrival_window") == "night") != is_night:
            add(MED, "night", f"{r['case_num']}: written for {'night' if case.get('arrival_window') == 'night' else 'day'} arrival but scheduled at {r['time']}")

    # --- case <-> row consistency --------------------------------------------------------------------
    for i, case in enumerate(cases):
        r = by_case.get(i + 1)
        if not r:
            continue
        if str(r.get("triage_cat")) != str(case.get("triage_category")):
            add(HIGH, "consistency", f"{r['case_num']}: schedule triage {r.get('triage_cat')} vs case {case.get('triage_category')}")
        if str(r.get("disposition")) != str(case.get("disposition")):
            add(HIGH, "consistency", f"{r['case_num']}: schedule disposition {r.get('disposition')} vs case {case.get('disposition')}")
        if (r.get("surgical") == "Yes") != (case.get("phases", {}).get("dcs") is not None):
            add(HIGH, "consistency", f"{r['case_num']}: schedule surgical flag disagrees with the case's surgery phase")
        prec, disp, trg = str(r.get("evac_precedence", "")).lower(), str(case.get("disposition")), str(case.get("triage_category"))
        has_prec = bool(prec) and not prec.startswith(("n/a", "not appl", "none"))
        # Evacuation precedence is how the casualty was called in (point of injury to Role 2), so RTD and expectant casualties
        # legitimately carry one; only a T1 evacuated at less than Urgent is suspect.
        if trg == "T1" and disp.startswith("Evac") and "urgent" not in prec:
            add(MED, "evacuation", f"{r['case_num']}: T1 evacuated with precedence '{r.get('evac_precedence')}' (expected Urgent)")
        if disp.startswith(("Evac", "Hold")) and not has_prec and case.get("severity") in ("critical", "severe"):
            add(MED, "evacuation", f"{r['case_num']}: a {case.get('severity')} casualty has no evacuation precedence")

    # --- outcome <-> time in Role 2 ----------------------------------------------------------------------
    for r in rows:
        case = cases[int(str(r["case_num"]).split()[1]) - 1]
        if int(r.get("cleared_raw", 0)) - int(r["arr_raw"]) != int(r.get("r2_dwell") or 0):
            add(MED, "dwell", f"{r['case_num']}: cleared time is not arrival + dwell")
    dw = {}
    for r in rows:
        case = cases[int(str(r["case_num"]).split()[1]) - 1]
        dw.setdefault(case.get("disposition"), []).append(int(r.get("r2_dwell") or 0))
    if dw and len({round(sum(v) / len(v)) for v in dw.values()}) == 1 and len(dw) > 1:
        add(HIGH, "dwell", "every outcome has the same time in Role 2: holds, returns to duty and deaths occupy the same bed time")

    # --- blood -----------------------------------------------------------------------------------------
    used = 0
    for r in rows:
        case = cases[int(str(r["case_num"]).split()[1]) - 1]
        units = int(r.get("blood_units") or 0)
        used += units
        sev = case.get("severity")
        if units and sev in ("mild", "moderate") and r.get("surgical") != "Yes":
            add(HIGH, "blood", f"{r['case_num']}: {sev} casualty ({case.get('meta', {}).get('title')}) draws {units} units of whole blood")
        if units and str(case.get("disposition")) == "RTD":
            add(HIGH, "blood", f"{r['case_num']}: returned to duty but draws {units} units")
    if used > main.STARTING_LTOWB_UNITS:
        serious = sum(int(r.get("blood_units") or 0) for r in rows
                      if cases[int(str(r["case_num"]).split()[1]) - 1].get("severity") in ("critical", "severe"))
        if serious <= main.STARTING_LTOWB_UNITS:
            add(HIGH, "blood", f"stock of {main.STARTING_LTOWB_UNITS} units is exhausted ({used} used) only because minor casualties draw blood; serious casualties use {serious}")

    # --- FRAGOs and care chain ---------------------------------------------------------------------------
    for r in (r for r in rows if r.get("care_chain")):  # the care chain is filled in when the decision trees are built
        active = [f["number"] for f in scenario.active_fragos(fragos, r["day"], r["arr_raw"])]
        shown = [int(x) for x in re.findall(r"FRAGO (\d+)", str(r.get("fragos_in_force", "")))]
        if sorted(active) != sorted(shown):
            add(MED, "fragos", f"{r['case_num']}: FRAGOs in force at {r['time']} are {active} but the row shows {shown}")
        denied = any(f["effect"] == "evac_denied" and f["number"] in active for f in fragos)
        if denied and "Holding" not in str(r.get("care_chain", "")):
            add(MED, "fragos", f"{r['case_num']}: evacuation is denied at {r['time']} but the care chain has no holding node")

    # --- CBRN drill and detainee inject --------------------------------------------------------------------
    for r in msel:
        if r.get("event") == "DRILL":
            lo = int(str(r["time"])[:2]) * 60 + int(str(r["time"])[2:])
            for c in rows:
                if c["day"] == r["day"] and lo <= c["arr_raw"] % 1440 < lo + 60:
                    add(MED, "cbrn", f"{c['case_num']} arrives at {c['time']} during the 1-hour CBRN drill that pauses all clinical operations")
        if r.get("event") == "INJECT":
            enemy = [int(str(x['case_num']).split()[1]) for x in rows if x["day"] == r["day"]
                     and cases[int(str(x['case_num']).split()[1]) - 1].get("patient_population") == "enemy"]
            t0 = int(str(r["time"])[:2]) * 60 + int(str(r["time"])[2:])
            if not enemy:
                add(MED, "detainee", f"day {r['day']} has a Detainee/EPW inject but no enemy-combatant case")
            elif min(abs(by_case[n]["arr_raw"] - t0) for n in enemy) > 90:
                add(MED, "detainee", f"day {r['day']}: the Detainee/EPW inject at {r['time']} is not tied to an enemy case (nearest arrives {min(abs(by_case[n]['arr_raw'] - t0) for n in enemy)} min away)")

    # --- census -------------------------------------------------------------------------------------------
    at = lambda row, k: (row["day"] - 1) * 1440 + row[k]
    for r in rows:
        census = sum(1 for o in rows if at(o, "arr_raw") <= at(r, "arr_raw") < at(o, "cleared_raw"))
        if census != r.get("r2_census"):
            add(MED, "census", f"{r['case_num']}: census {r.get('r2_census')} but recomputed {census}")
            break
    return out


def audit_orders(config, cases, msel, docs):
    out = []
    add = lambda sev, area, msg: out.append((sev, area, msg))
    medroe, annex = docs.get("medroe", ""), docs.get("annex_q", "")
    days = config["days"]
    enemy_on = config.get("treat_enemy_combatants")
    enemy_on = any(d.get("detainee_ops") for d in days) if enemy_on is None else enemy_on
    civ_on = config.get("treat_civilians")
    civ_on = any(d["tactical_setting"] in casemix.HUMANITARIAN for d in days) if civ_on is None else civ_on
    for who, on, pat in (("Enemy combatants", enemy_on, r"enemy combatants[^\n]{0,80}?(AUTHORIZED|NOT part)"),
                         ("Host-nation civilians", civ_on, r"host-nation civilians[^\n]{0,80}?(AUTHORIZED|NOT part)")):
        m = re.search(pat, medroe, re.I)
        if not m:
            add(MED, "medroe", f"the MEDROE does not state the {who.lower()} policy in the exercise's own words")
        elif (m.group(1).upper() == "AUTHORIZED") != bool(on):
            add(HIGH, "medroe", f"the MEDROE says {who.lower()} are {m.group(1)} but the exercise policy is {'on' if on else 'off'}")

    def timings(text):
        found = {}
        for lvl in ("urgent", "priority", "routine"):
            m = re.search(rf"{lvl}[^\n]{{0,80}}?(\d+)\s*(minutes|min|hours|hrs|hr)", text, re.I)
            if m:
                found[lvl] = int(m.group(1)) * (60 if m.group(2).lower().startswith("h") else 1)
        return found
    tm, ta = timings(medroe), timings(annex)
    for lvl in sorted(set(tm) & set(ta)):
        if tm[lvl] != ta[lvl]:
            add(HIGH, "orders", f"the MEDROE and Annex Q disagree on {lvl} evacuation: {tm[lvl]} min vs {ta[lvl]} min")
    hold = lambda t: [int(x) for x in re.findall(r"(?:maximum|max\.?|up to)[^\n]{0,90}?(\d+)\s*\**\s*hours", t, re.I)]
    hm, ha = hold(medroe), hold(annex)
    longest = max((int(r.get("r2_dwell") or 0) for r in msel if "arr_raw" in r), default=0) / 60
    if hm and ha and set(hm) != set(ha):
        add(MED, "orders", f"the MEDROE holding limit {sorted(set(hm))} h differs from Annex Q {sorted(set(ha))} h")
    if hm and longest > max(hm):
        add(HIGH, "orders", f"a casualty is held {longest:.0f} h but the MEDROE limits holding to {max(hm)} h")

    # do the cases use the orders?
    def cited(case, pat):
        return bool(re.search(pat, json.dumps([case.get(k) for k in ("phases", "evacuation", "learning_objectives", "debrief_questions", "patient_data")]), re.I))
    classes = {
        "expectant casualties cite expectant management / comfort care": ([c for c in cases if c.get("triage_category") == "Expectant"], r"expectant|comfort|palliat"),
        "enemy combatants cite detainee handling, custody or the Geneva Conventions": ([c for c in cases if c.get("patient_population") == "enemy"], r"detainee|custody|guard|geneva|epw|security"),
        "civilians cite civilian-care provisions or host-nation handover": ([c for c in cases if c.get("patient_population") == "civilian"], r"civilian|host[- ]nation|hand ?over|transfer"),
        "held casualties cite the holding policy / limit": ([c for c in cases if c.get("disposition") == "Hold at Role 2"], r"hold(ing)?|72|prolonged|pcc"),
        "casualties drawing blood cite whole blood, LTOWB or the walking blood bank": ([c for c, r in zip(cases, [x for x in msel if 'arr_raw' in x]) if int(r.get("blood_units") or 0) >= 4], r"whole blood|ltowb|walking blood|wbb|blood product"),
    }
    for label, (group, pat) in classes.items():
        if group:
            n = sum(cited(c, pat) for c in group)
            if n < len(group) / 2:
                add(MED, "cases", f"only {n} of {len(group)} {label}")
    return out


def main_cli():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    rec = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    config, cases, msel = J(rec["config"]), J(rec["cases"]), J(rec["msel_data"])
    findings = audit_schedule(config, cases, msel, rec.get("fragos") or [])
    if "--docs" in sys.argv:
        d = Path(sys.argv[sys.argv.index("--docs") + 1])
        docs = {k: (d / f"{k}.txt").read_text(encoding="utf-8") for k in ("medroe", "annex_q", "warno") if (d / f"{k}.txt").exists()}
        findings += audit_orders(config, cases, msel, docs)
    order = {HIGH: 0, MED: 1, LOW: 2}
    findings.sort(key=lambda f: order[f[0]])
    for sev, area, msg in findings:
        print(f"[{sev:<6}] {area:<13} {msg}")
    print(f"\n{len(findings)} findings: " + ", ".join(f"{sum(1 for f in findings if f[0] == s)} {s}" for s in (HIGH, MED, LOW)))
    sys.exit(1 if any(f[0] == HIGH for f in findings) else 0)


if __name__ == "__main__":
    main_cli()
