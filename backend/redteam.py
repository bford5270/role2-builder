"""Red team for the controller layer: deterministic checks that catch the
consistency errors expert reviewers find by hand (laterality, GCS math,
threshold drift, physiology, tree integrity, capability-vs-echelon), plus an
LLM critic pass. Findings are dicts:

    {"severity": "high|medium|low", "category": str, "location": str,
     "issue": str, "fix": str, "source": "rules|ai"}
"""
import json
import re
from typing import Callable, Dict, Iterable, List, Optional

_SIDE_WORDS = {"left": "L", "l": "L", "lt": "L", "right": "R", "r": "R", "rt": "R"}
_REGIONS = ("chest", "hemithorax", "lung", "scapula", "thigh", "arm", "leg", "flank", "abdomen",
            "shoulder", "neck", "axilla", "buttock", "groin", "hand", "foot", "knee", "forearm")
_REGION_FAMILY = {"hemithorax": "chest", "lung": "chest", "axilla": "chest"}
_LAT_RE = re.compile(
    r"\b(left|right|lt|rt|l|r)\b\.?\s+(?:[a-z-]+\s+){0,2}?(" + "|".join(_REGIONS) + r")\b", re.I)
_AFFECTED_RE = re.compile(r"\b(left|right|l|r)\b\s+(?:affected|effected|injured)\s+side", re.I)
_HEMO_RE = re.compile(r"\b(left|right|l|r)\b\.?\s+(?:chest|hemithorax)?\s*(?:with\s+)?(?:hemo\s*/?\s*pneumothorax|hemopneumothorax|hemothorax)", re.I)
_EBL_RE = re.compile(r"\b(l|r|left|right)\b\s+\d{3,4}\s*m[lL]\s*EBL", re.I)
_GCS_RE = re.compile(r"GCS\s*(\d{1,2})\s*\(\s*E\s*=?\s*[a-z ]*?(\d)[^)]*?V\s*=?\s*[a-z ]*?(\d)[^)]*?M\s*=?\s*[a-z ]*?(\d)", re.I)
_EVM_RE = re.compile(r"\bE(\d)\s*,?\s*V(\d)\s*,?\s*M(\d)\b")
_ML_HR_RE = re.compile(r"(\d{2,4})\s*m[lL]\s*/\s*h(?:r|our)", re.I)
_TXA_RE = re.compile(r"\bTXA\b[^.;\n]*?(\d+(?:\.\d+)?)\s*(g|gm|mg)\b", re.I)
_BURN_RE = re.compile(r"burn|tbsa|thermal", re.I)
_DCS_RE = re.compile(r"\b(DCS|damage control surgery|thoracotomy|laparotomy|laparatomy|sternotomy)\b", re.I)

_AVPU_RANK = {"A": 0, "V": 1, "P": 2, "U": 3}


def _f(sev, cat, loc, issue, fix) -> Dict:
    return {"severity": sev, "category": cat, "location": loc, "issue": issue, "fix": fix, "source": "rules"}


def _strings(obj, path="") -> Iterable[tuple]:
    """Yield (path, text) for every string in a nested structure."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("chain", "red_team", "review"):
                continue
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")


def _region_key(r: str) -> str:
    r = (r or "").lower()
    for reg in _REGIONS:
        if reg in r:
            return _REGION_FAMILY.get(reg, reg)
    if "back" in r:
        return "scapula" if "upper" in r else r
    return r


def _wound_sides(ctrl: Dict) -> Dict[str, set]:
    sides: Dict[str, set] = {}
    for w in ctrl.get("wounds") or []:
        side = (w.get("side") or "").strip().lower()
        s = {"l": {"L"}, "left": {"L"}, "r": {"R"}, "right": {"R"},
             "bilateral": {"L", "R"}, "bilat": {"L", "R"}}.get(side)
        if s is None:
            continue
        key = _region_key(w.get("region", ""))
        sides.setdefault(key, set()).update(s)
        if key in ("thigh", "leg", "knee", "foot"):  # lower extremity family
            for k in ("thigh", "leg", "knee", "foot"):
                sides.setdefault(k, set()).update(s)
    return sides


def check_laterality(ctrl: Dict, case: Optional[Dict] = None) -> List[Dict]:
    out = []
    wound_sides = _wound_sides(ctrl)
    injured_chest = wound_sides.get("chest", set())
    texts = list(_strings(ctrl))
    if case:
        texts += list(_strings({"zmist": case.get("zmist")}))
    seen = set()
    for path, text in texts:
        for m in _LAT_RE.finditer(text):
            side = _SIDE_WORDS[m.group(1).lower().rstrip(".")]
            region = _REGION_FAMILY.get(m.group(2).lower(), m.group(2).lower())
            known = wound_sides.get(region)
            if known and side not in known and (path, region) not in seen:
                seen.add((path, region))
                out.append(_f("high", "laterality", path,
                              f"'{m.group(0)}' contradicts the wounds list ({region}: {'/'.join(sorted(known))}).",
                              "Make every mention of this region use the side in the wounds list / body map."))
        for m in _AFFECTED_RE.finditer(text):
            side = _SIDE_WORDS[m.group(1).lower()]
            if injured_chest and side not in injured_chest and (path, "affected") not in seen:
                seen.add((path, "affected"))
                out.append(_f("high", "laterality", path,
                              f"'{m.group(0)}' but the chest wound is {'/'.join(sorted(injured_chest))}.",
                              "Correct the affected side."))
    # The side of the hemothorax (named pathology, or the side draining blood)
    # must match every "affected side" reference.
    hemo_sides = set()
    for _, text in texts:
        for m in _HEMO_RE.finditer(text):
            hemo_sides.add(_SIDE_WORDS[m.group(1).lower()])
        for m in _EBL_RE.finditer(text):
            hemo_sides.add(_SIDE_WORDS[m.group(1).lower()])
    if len(hemo_sides) == 1:
        for path, text in texts:
            for m in _AFFECTED_RE.finditer(text):
                side = _SIDE_WORDS[m.group(1).lower()]
                if side not in hemo_sides:
                    out.append(_f("medium", "laterality", path,
                                  f"'{m.group(0)}' but the hemothorax is {next(iter(hemo_sides))}.",
                                  "Confirm which side the E-FAST/affected-side finding refers to and make it match."))
    return out


def check_gcs(ctrl: Dict) -> List[Dict]:
    out = []
    for path, text in _strings(ctrl):
        for m in _GCS_RE.finditer(text):
            total, e, v, mo = (int(x) for x in m.groups())
            if e + v + mo != total:
                out.append(_f("high", "gcs", path,
                              f"GCS {total} stated but E{e}+V{v}+M{mo} = {e + v + mo}.",
                              "Fix the total or the components so they agree, and match the vitals table."))
        for m in _EVM_RE.finditer(text):
            e, v, mo = (int(x) for x in m.groups())
            if not (1 <= e <= 4 and 1 <= v <= 5 and 1 <= mo <= 6):
                out.append(_f("high", "gcs", path, f"Impossible GCS component in '{m.group(0)}'.",
                              "E is 1-4, V 1-5, M 1-6."))
    tracks = ctrl.get("vitals_tracks") or {}
    for name, pts in tracks.items():
        for p in pts or []:
            e, v, mo = p.get("gcs_e"), p.get("gcs_v"), p.get("gcs_m")
            if None in (e, v, mo):
                continue
            if not (1 <= e <= 4 and 1 <= v <= 5 and 1 <= mo <= 6):
                out.append(_f("high", "gcs", f"vitals_tracks.{name}@{p.get('t')}",
                              f"Impossible GCS E{e} V{v} M{mo}.", "E is 1-4, V 1-5, M 1-6."))
    # Moulage/text GCS vs the track at t=0
    g0 = (tracks.get("green") or [{}])[0]
    if None not in (g0.get("gcs_e"), g0.get("gcs_v"), g0.get("gcs_m")):
        t0 = g0["gcs_e"] + g0["gcs_v"] + g0["gcs_m"]
        for path, text in _strings({"moulage": ctrl.get("moulage", "")}):
            for m in _GCS_RE.finditer(text):
                if int(m.group(1)) != t0:
                    out.append(_f("medium", "gcs", path,
                                  f"Moulage GCS {m.group(1)} differs from the initial vitals GCS {t0} "
                                  f"(E{g0['gcs_e']} V{g0['gcs_v']} M{g0['gcs_m']}).",
                                  "Make the moulage brief and the vitals table show the same initial GCS."))
    return out


def check_thresholds(ctrl: Dict) -> List[Dict]:
    vals = {}
    for path, text in _strings(ctrl):
        for m in _ML_HR_RE.finditer(text):
            vals.setdefault(int(m.group(1)), []).append(path)
    if len(vals) > 1:
        listed = ", ".join(f"{k} mL/hr" for k in sorted(vals))
        return [_f("medium", "threshold", "; ".join(p for v in vals.values() for p in v[:1]),
                   f"Hourly output threshold differs between documents: {listed}.",
                   "Use one threshold everywhere (JTS: >200 mL/hr for 2-4 h, or >=1500 mL initial).")]
    return []


def check_meds(ctrl: Dict) -> List[Dict]:
    out = []
    for path, text in _strings(ctrl):
        for m in _TXA_RE.finditer(text):
            dose, unit = float(m.group(1)), m.group(2).lower()
            grams = dose / 1000 if unit == "mg" else dose
            if grams not in (1.0, 2.0):
                out.append(_f("medium", "medication", path, f"TXA dose '{m.group(0)}' is not 1 g or 2 g.",
                              "TCCC/JTS: TXA 2 g IV/IO (or 1 g + 1 g)."))
    for leg in ctrl.get("legs") or []:
        for med in (leg.get("handover") or {}).get("meds") or []:
            if "txa" in (med.get("drug") or "").lower():
                m = re.search(r"(\d+(?:\.\d+)?)\s*(g|gm|mg)", med.get("dose") or "", re.I)
                if m:
                    grams = float(m.group(1)) / (1000 if m.group(2).lower() == "mg" else 1)
                    if grams not in (1.0, 2.0):
                        out.append(_f("medium", "medication", f"legs[{leg['leg_id']}].handover.meds",
                                      f"TXA {med.get('dose')} is not a standard dose.", "Use TXA 2 g IV/IO."))
    return out


def _map(p: Dict) -> Optional[float]:
    if p.get("sbp") is None or p.get("dbp") is None:
        return None
    return (p["sbp"] + 2 * p["dbp"]) / 3


def check_vitals(ctrl: Dict) -> List[Dict]:
    out = []
    tracks = ctrl.get("vitals_tracks") or {}
    green, red = tracks.get("green") or [], tracks.get("red") or []
    if not green:
        return [_f("high", "vitals", "vitals_tracks.green", "No green vitals track.",
                   "Add the 0-60 min course if the critical actions are performed.")]
    bounds = {"hr": (20, 220), "sbp": (30, 250), "dbp": (10, 160), "rr": (0, 60), "spo2": (40, 100),
              "temp_f": (80, 108)}
    for name, pts in (("green", green), ("red", red)):
        for p in pts:
            loc = f"vitals_tracks.{name}@{p.get('t')}"
            for k, (lo, hi) in bounds.items():
                v = p.get(k)
                if v is not None and not (lo <= v <= hi):
                    out.append(_f("high", "vitals", loc, f"{k}={v} is outside a survivable/plausible range.",
                                  "Correct the value or make the arrest explicit."))
            if p.get("sbp") is not None and p.get("dbp") is not None and p["dbp"] >= p["sbp"]:
                out.append(_f("high", "vitals", loc, f"Diastolic {p['dbp']} >= systolic {p['sbp']}.",
                              "Fix the blood pressure."))
        for a, b in zip(pts, pts[1:]):
            for k, jump in (("hr", 40), ("sbp", 35), ("spo2", 15)):
                if a.get(k) is not None and b.get(k) is not None and abs(b[k] - a[k]) > jump:
                    out.append(_f("low", "vitals", f"vitals_tracks.{name}@{b.get('t')}",
                                  f"{k} jumps {a[k]}→{b[k]} in one 5-min step.",
                                  "Confirm an intervention or event explains the jump, or smooth the change."))
    if red:
        if green[0].get("t", 0) == red[0].get("t", 0):
            diffs = [k for k in ("hr", "sbp", "dbp", "rr", "spo2") if green[0].get(k) != red[0].get(k)]
            if diffs:
                out.append(_f("medium", "vitals", "vitals_tracks.red@0",
                              f"Red and green tracks differ at t=0 ({', '.join(diffs)}).",
                              "Both tracks start from the same arrival vitals."))
        m0, m1 = _map(red[0]), _map(red[-1])
        worse_avpu = _AVPU_RANK.get(str(red[-1].get("avpu", "A"))[:1], 0) > _AVPU_RANK.get(str(red[0].get("avpu", "A"))[:1], 0)
        if m0 is not None and m1 is not None and m1 >= m0 and not worse_avpu:
            out.append(_f("high", "vitals", "vitals_tracks.red",
                          "The red (missed-intervention) track does not deteriorate.",
                          "The red track should show falling MAP/SpO2 and falling mental status."))
        gm, rm = _map(green[-1]), _map(red[-1])
        if gm is not None and rm is not None and gm <= rm:
            out.append(_f("medium", "vitals", "vitals_tracks",
                          "The green track ends no better than the red track.",
                          "Green should show a response to correct care."))
    elif ctrl.get("critical_actions"):
        out.append(_f("high", "vitals", "vitals_tracks.red", "Critical actions exist but there is no red track.",
                      "Add the deterioration course for a missed critical action."))
    # Shock recognition: shock index >1 at arrival demands a resuscitation action
    g0 = green[0]
    if g0.get("hr") and g0.get("sbp") and g0["hr"] / max(g0["sbp"], 1) > 1.0:
        acts = " ".join(a.get("action", "") for a in ctrl.get("critical_actions") or []).lower()
        if not re.search(r"blood|resus|transfus|hemorrhage|dcr", acts):
            out.append(_f("medium", "critical_actions", "critical_actions",
                          f"Shock index {g0['hr'] / g0['sbp']:.1f} at arrival but no resuscitation critical action.",
                          "Add recognition/treatment of shock as a critical action."))
    return out


def check_handover(ctrl: Dict) -> List[Dict]:
    focus = next((l for l in ctrl.get("legs") or [] if l.get("focus")), None)
    green = (ctrl.get("vitals_tracks") or {}).get("green") or []
    if not focus or not green:
        return []
    hv = (focus.get("handover") or {}).get("vitals") or {}
    g0 = green[0]
    diffs = []
    for k, tol in (("hr", 10), ("sbp", 10)):
        a, b = _num(hv.get(k)), g0.get(k)
        if a is not None and b is not None and abs(a - b) > tol:
            diffs.append(f"{k} {a}→{b}")
    summary = (focus.get("handover") or {}).get("summary", "").lower()
    if diffs and not re.search(r"deteriorat|declin|worsen|decompensat|en route|en-route|during transport", summary):
        return [_f("medium", "handover", f"legs[{focus['leg_id']}].handover",
                   f"Turnover vitals differ from arrival vitals ({'; '.join(diffs)}) with no explanation.",
                   "Match them, or say in the turnover summary what changed en route.")]
    return []


def _num(v):
    if isinstance(v, (int, float)):
        return v
    m = re.search(r"-?\d+(\.\d+)?", str(v or ""))
    return float(m.group()) if m else None


def check_trees(ctrl: Dict) -> List[Dict]:
    out = []
    pathway = ctrl.get("pathway", "")
    for leg in ctrl.get("legs") or []:
        loc = f"legs[{leg.get('leg_id')}].tree"
        nodes = (leg.get("tree") or {}).get("nodes") or []
        edges = (leg.get("tree") or {}).get("edges") or []
        if not nodes:
            out.append(_f("high", "tree", loc, "Leg has no decision tree.", "Build the tree for this leg."))
            continue
        ids = [n.get("id") for n in nodes]
        if len(set(ids)) != len(ids):
            out.append(_f("high", "tree", loc, "Duplicate node ids.", "Give every node a unique id."))
        idset = set(ids)
        for e in edges:
            if e.get("from") not in idset or e.get("to") not in idset:
                out.append(_f("high", "tree", loc, f"Edge {e.get('from')}→{e.get('to')} references a missing node.",
                              "Fix the edge or add the node."))
        adj: Dict[str, List[str]] = {}
        for e in edges:
            adj.setdefault(e.get("from"), []).append(e.get("to"))
        seen, stack = set(), [ids[0]]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj.get(n, []))
        orphans = [i for i in ids if i not in seen]
        if orphans:
            out.append(_f("medium", "tree", loc, f"Nodes unreachable from the start: {', '.join(orphans[:6])}.",
                          "Connect them to the tree or remove them."))
        if not any(n.get("type") == "outcome" for n in nodes):
            out.append(_f("medium", "tree", loc, "Tree has no outcome node.",
                          "End the tree in a disposition/outcome (DCS, holding, evac, handover)."))
        if leg.get("focus") and not any(n.get("failure") for n in nodes):
            out.append(_f("medium", "tree", loc, "Focus-leg tree has no failure (red) path.",
                          "Add what happens when the critical intervention is missed."))
        cap = leg.get("capability") or []
        mentions_dcs = any(_DCS_RE.search(f"{n.get('label', '')} {n.get('detail', '')}")
                           and n.get("type") in ("intervention", "outcome") and not n.get("failure")
                           and not re.search(r"evac|transfer|move|to surgical|higher|handover|hand off|handoff|for DCS", f"{n.get('label', '')} {n.get('detail', '')}", re.I)
                           for n in nodes)
        if mentions_dcs and "DCS" not in cap:
            out.append(_f("high", "capability", loc,
                          f"Tree performs surgery but {leg.get('title')} has no DCS capability ({', '.join(cap)}).",
                          "Replace with evacuation to surgical capability, or move surgery to a DCS-capable leg."))
        if leg.get("focus") and pathway in ("DCR_HOLD", "DCR_PCC", "MEDICAL") and mentions_dcs:
            out.append(_f("high", "pathway", loc, f"Pathway {pathway} is non-surgical but the tree reaches DCS.",
                          "Remove the DCS outcome or change the pathway."))
        if leg.get("focus") and pathway == "DCR_DCS" and not mentions_dcs:
            out.append(_f("medium", "pathway", loc, "Pathway DCR_DCS but the tree never reaches surgery.",
                          "Add the DCS outcome node."))
    return out


def check_structure(ctrl: Dict, case: Dict) -> List[Dict]:
    out = []
    zap = str((case.get("zmist") or {}).get("zap", ""))
    if not re.fullmatch(r"\d{5}", zap):
        out.append(_f("low", "format", "zmist.zap", f"ZAP '{zap}' is not 5 digits.", "Use a 5-digit ZAP."))
    leg_ids = {l.get("leg_id") for l in ctrl.get("legs") or []}
    for a in ctrl.get("critical_actions") or []:
        if a.get("leg_id") not in leg_ids:
            out.append(_f("medium", "critical_actions", f"critical_actions.{a.get('id')}",
                          f"Critical action references unknown leg '{a.get('leg_id')}'.", "Use a leg id from the chain."))
        if not a.get("if_missed"):
            out.append(_f("low", "critical_actions", f"critical_actions.{a.get('id')}",
                          "Critical action has no consequence if missed.", "State what the red track represents."))
    injuries = f"{(case.get('zmist') or {}).get('injuries', '')} {(case.get('meta') or {}).get('title', '')}"
    burns = ctrl.get("burns")
    if burns and not _BURN_RE.search(injuries):
        out.append(_f("medium", "template", "burns", "Burns block present on a non-burn case.",
                      "Remove the burns section (template leftover)."))
    disp = (case.get("disposition") or "").lower()
    if disp == "rtd" and ctrl.get("pathway") in ("DCR_DCS", "DCR_DEFERRED_DCS"):
        out.append(_f("high", "disposition", "disposition", "Surgical pathway with an RTD disposition.",
                      "Make the disposition evacuation or holding."))
    for w in ctrl.get("wounds") or []:
        if (w.get("side") or "").lower() not in ("l", "r", "left", "right", "midline", "bilateral", "bilat"):
            out.append(_f("low", "wounds", f"wounds.{w.get('id')}", f"Wound side '{w.get('side')}' is unclear.",
                          "Use L, R, midline or bilateral."))
    return out


def run_rules(ctrl: Dict, case: Dict) -> List[Dict]:
    findings = []
    for check in (check_laterality, check_gcs, check_thresholds, check_meds, check_vitals, check_handover,
                  check_trees):
        try:
            findings += check(ctrl, case) if check is check_laterality else check(ctrl)
        except Exception as e:  # a broken check must never sink a package
            findings.append(_f("low", "checker", check.__name__, f"Check failed to run: {e}", "Review manually."))
    findings += check_structure(ctrl, case)
    return findings


CRITIC_SYSTEM_PROMPT = """You are a red team of expert military medical simulation personnel — a trauma
surgeon, an emergency physician, a CRNA, an ERC/flight nurse and a simulation technician — reviewing ONE
casualty's controller layer before it is used in a Role 2 exercise. You review AND repair in a single pass.

Check:
1. Physiology: do the green/red vitals follow from the injuries and the care given? Is deterioration
   believable in pace and pattern (hemorrhagic, obstructive, neurologic)?
2. Clinical guidance: JTS CPGs (DCR, hemorrhagic shock, thoracic trauma, TXA, calcium, hypothermia,
   prolonged casualty care, analgesia/sedation) and TCCC for prehospital legs.
3. Echelon realism: is every intervention in each leg's tree available at that node's capability?
4. Completeness: are the likely team errors on the failure paths (e.g., positive-pressure ventilation
   without decompression, missed posterior wound, under-resuscitation, hypothermia)?
5. Consistency: laterality, GCS, thresholds, times, doses, turnover vs arrival.
6. Moulage: can the sim tech build what is described, and do the findings support the decisions asked?

Also fix every RULES FINDING you are given (these are deterministic checks and are always real).

Only act on errors that would teach the wrong thing or break play. Do NOT rewrite for style, do NOT add
optional detail, do NOT report minor issues — the layer ships as-is unless something is wrong.

Return JSON only, in one of two forms:
- Sound as written (and no rules findings given): {"ok": true}
- Needs fixes: {"ok": false,
    "findings": [{"category": "String", "location": "String", "issue": "String"}],
    "patch": { ONLY the top-level fields you changed, each given in full: any of "wounds", "moulage",
               "critical_decisions", "critical_actions", "vitals_tracks", "controller_note", "burns";
               plus "legs": [ONLY the legs you changed, each a full leg object with its exact "leg_id"] } }
Keep the patch minimal: unchanged fields and unchanged legs must be left out."""

# Fields a patch may replace. Everything else (chain, pathway, focus_leg,
# quality) is owned by the pipeline, never by the model.
_PATCHABLE = ("wounds", "moulage", "critical_decisions", "critical_actions", "vitals_tracks",
              "controller_note", "burns")


def _parse(text: str) -> Dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}") + 1
        return json.loads(text[s:e]) if s != -1 and e > s else {}


def apply_patch(ctrl: Dict, patch: Dict) -> Dict:
    """Merge a partial controller layer into ctrl: listed top-level fields are
    replaced, legs are replaced field-by-field by leg_id. A full layer is a
    valid patch too."""
    out = json.loads(json.dumps(ctrl))
    if not isinstance(patch, dict):
        return out
    for k in _PATCHABLE:
        if k in patch:
            out[k] = patch[k]
    by_id = {l.get("leg_id"): l for l in patch.get("legs") or [] if isinstance(l, dict)}
    for leg in out.get("legs") or []:
        got = by_id.get(leg.get("leg_id"))
        if got:
            for k in ("handover", "tree", "considerations"):
                if k in got:
                    leg[k] = got[k]
    return out


def _review_body(ctrl: Dict) -> Dict:
    return {k: v for k, v in ctrl.items()
            if k not in ("chain", "pathway", "focus_leg", "quality", "red_team", "review")}


def ai_review(ctrl: Dict, case: Dict, rules_findings: List[Dict], llm: Callable[[str, str], str]) -> Dict:
    """One call: the expert critic reviews the layer and returns a minimal patch
    for anything wrong (including the rules findings), or {"ok": true}.
    Returns the patch ({} when sound)."""
    prompt = (f"CASE Z-MIST: {json.dumps(case.get('zmist'))}\nTRIAGE: {case.get('triage_category')} "
              f"DISPOSITION: {case.get('disposition')}\nCARE CHAIN: "
              + " → ".join(n["name"] for n in (ctrl.get("chain") or {}).get("nodes", []))
              + "\n\nRULES FINDINGS TO FIX:\n"
              + (json.dumps([{k: f.get(k) for k in ("category", "location", "issue", "fix")}
                             for f in rules_findings], indent=1) if rules_findings else "none")
              + f"\n\nCONTROLLER LAYER:\n{json.dumps(_review_body(ctrl), separators=(',', ':'))}")
    data = _parse(llm(prompt, CRITIC_SYSTEM_PROMPT))
    if data.get("ok") is True and not data.get("patch"):
        return {}
    return data.get("patch") or {}


def summarize(findings: List[Dict]) -> Dict:
    return {s: sum(1 for f in findings if f["severity"] == s) for s in ("high", "medium", "low")}


def _blocking(findings: List[Dict]) -> List[Dict]:
    """What must be fixed before a case ships: every rules finding rated high or
    medium, and any AI finding rated high. (The AI review repairs what it finds
    in the same call, so its findings normally never reach this gate.)"""
    return [f for f in findings
            if (f["source"] == "rules" and f["severity"] in ("high", "medium"))
            or (f["source"] == "ai" and f["severity"] == "high")]


def autofix(ctrl: Dict, case: Dict) -> Dict:
    """Deterministic repairs that need no judgment."""
    ctrl = json.loads(json.dumps(ctrl))
    injuries = f"{(case.get('zmist') or {}).get('injuries', '')} {(case.get('meta') or {}).get('title', '')}"
    if ctrl.get("burns") and not _BURN_RE.search(injuries):
        ctrl["burns"] = None
    tracks = ctrl.get("vitals_tracks") or {}
    green, red = tracks.get("green") or [], tracks.get("red") or []
    if green and red and red[0].get("t", 0) == green[0].get("t", 0):
        red[0] = dict(green[0])
    focus = next((l for l in ctrl.get("legs") or [] if l.get("focus")), None)
    if focus and green and check_handover(ctrl):
        # Turnover and arrival vitals legitimately differ when the patient
        # worsens en route — keep the author's card, and say so on it.
        hv = focus.setdefault("handover", {})
        if not hv.get("vitals"):
            hv["vitals"] = {k: green[0].get(k) for k in ("hr", "sbp", "dbp", "rr", "spo2", "avpu")}
        else:
            g0 = green[0]
            hv["summary"] = (hv.get("summary", "").rstrip() + f" Deteriorated en route; on arrival HR {g0.get('hr')}, "
                             f"BP {g0.get('sbp')}/{g0.get('dbp')}.").strip()
    for leg in ctrl.get("legs") or []:
        for med in (leg.get("handover") or {}).get("meds") or []:
            if "txa" in (med.get("drug") or "").lower():
                m = re.search(r"(\d+(?:\.\d+)?)\s*(g|gm|mg)", med.get("dose") or "", re.I)
                if m and float(m.group(1)) / (1000 if m.group(2).lower() == "mg" else 1) not in (1.0, 2.0):
                    med["dose"] = "2 g"
    return ctrl


def finalize(ctrl: Dict, case: Dict,
             review: Optional[Callable[[Dict, List[Dict]], Dict]] = None,
             revise: Optional[Callable[[Dict, List[Dict]], Dict]] = None,
             fallback: Optional[Callable[[], Dict]] = None,
             source: str = "ai") -> Dict:
    """Red-team a controller layer and FIX it so the case ships as a final
    draft, spending at most two model calls:

      1. deterministic autofix + rules (free)
      2. one expert review-and-repair call that also fixes the rules findings
         (returns a minimal patch, or nothing when the layer is sound)
      3. only if rules findings survive: one targeted revision (patch)
      4. still not clean → the pathway template

    Returns the clean layer with a small `quality` record; no findings are
    attached."""
    rounds = 0
    cur = autofix(ctrl, case)
    if review:
        rounds += 1
        try:
            cur = autofix(review(cur, _blocking(run_rules(cur, case))), case)
        except Exception as e:
            print(f"WARNING: AI review failed: {e}")
    left = _blocking(run_rules(cur, case))
    if left and revise:
        rounds += 1
        try:
            cur = autofix(revise(cur, left), case)
            left = _blocking(run_rules(cur, case))
        except Exception as e:
            print(f"WARNING: revision failed: {e}")
    if not left:
        cur.pop("_fallback", None)
        cur["quality"] = {"source": source, "rounds": rounds}
        return cur
    if fallback is None:
        raise ValueError("controller layer could not be made clean and no template was given")
    cur = autofix(fallback(), case)
    cur.pop("_fallback", None)
    left = _blocking(run_rules(cur, case))
    if left:
        print(f"WARNING: template still has {len(left)} rules finding(s): {[f['issue'] for f in left]}")
    cur["quality"] = {"source": "template", "rounds": rounds}
    return cur
