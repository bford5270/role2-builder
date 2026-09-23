"""Scenario layer: care chain (legs) from operational context, FRAGOs that
change it mid-exercise, care pathways, and the controller layer each case
carries — per-leg decision trees, turnover cards, critical actions, and
green/red vitals tracks for the Role 2 leg.

Everything here is duck-typed against ExerciseConfig / DayConfig and takes the
LLM as a callable, so it has no import dependency on main.py.
"""
import json
import re
from typing import Callable, Dict, List, Optional

# --- Care chain ------------------------------------------------------------
# A chain is an ordered list of nodes; a leg is the care delivered at one node
# up to handoff to the next. The Role 2 leg (care AT the surgical/resuscitative
# node) is the "focus" leg the exercise is played on and carries vitals tracks.

def _node(nid: str, name: str, capability: List[str], role2: bool = False) -> Dict:
    return {"id": nid, "name": name, "capability": list(capability), "role2": role2}


def _is_maritime(config, day) -> bool:
    env = (getattr(config, "environment", "") or "").lower()
    return env == "maritime" or getattr(day, "tactical_setting", "") == "Amphibious Assault"


def _en_route_care(config, day, transit_priority_min: int) -> bool:
    """ERC (en route care) replaces a Role 1 BAS stop when evacuation is over
    water or long enough to be flown with an en route care team."""
    env = (getattr(config, "environment", "") or "").lower()
    return env in ("maritime", "littoral") or _is_maritime(config, day) or transit_priority_min > 60


def _role2_node(config, day) -> Dict:
    fp = set(getattr(config, "selected_footprint", []) or [])
    if "FRSS" in fp:
        if _is_maritime(config, day):
            return _node("R2", "ERSS (afloat)", ["DCR", "DCS"], role2=True)
        name = "STP/FRSS" if "STP" in fp else "FRSS"
        return _node("R2", name, ["DCR", "DCS"], role2=True)
    if "STP" in fp:
        return _node("R2", "STP", ["DCR"], role2=True)
    return _node("R2", "Role 2 (resuscitative)", ["DCR"], role2=True)


def base_chain(config, day, transit_priority_min: int) -> List[Dict]:
    fp = set(getattr(config, "selected_footprint", []) or [])
    nodes = [_node("POI", "POI/CCP", ["TCCC"])]
    if _en_route_care(config, day, transit_priority_min):
        nodes.append(_node("ERC1", "ERC", ["TCCC", "DCR-limited"]))
    else:
        nodes.append(_node("BAS", "BAS (Role 1)", ["TCCC", "DCR-limited"]))
    nodes.append(_role2_node(config, day))
    if "Holding" in fp:
        nodes.append(_node("HOLD", "Holding", ["PCC"]))
    nodes.append(_node("ERC2", "ERC (onward)", ["TCCC", "DCR-limited"]))
    nodes.append(_node("R3", "FOB / Role 3", ["DCR", "DCS", "Definitive"]))
    return nodes


def chain_to_legs(nodes: List[Dict]) -> List[Dict]:
    legs = []
    for a, b in zip(nodes, nodes[1:]):
        legs.append({
            "id": f"{a['id']}-{b['id']}",
            "from": a["name"], "to": b["name"],
            "title": f"{a['name']} to {b['name']}",
            "capability": a["capability"],
            "focus": a.get("role2", False),
        })
    return legs


# --- FRAGOs ---------------------------------------------------------------
# Deterministic from the exercise parameters so the orders, the MSEL and the
# case trees can never disagree. Times are minutes from D-day midnight (values
# past 1440 are the early hours of the next morning, matching the MSEL).

def _hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}{m % 60:02d}"


def generate_fragos(config) -> List[Dict]:
    fp = set(getattr(config, "selected_footprint", []) or [])
    threat = (getattr(config, "threat_level", "") or "").lower()
    contested = "peer" in threat or "hybrid" in threat
    days = list(getattr(config, "days", []) or [])
    out: List[Dict] = []

    def add(day, start, end, effect, title, situation, execution):
        out.append({"number": len(out) + 1, "day": day.day_number, "start": start, "end": end,
                    "effect": effect, "title": title, "situation": situation, "execution": execution})

    for i, day in enumerate(days):
        setting = getattr(day, "tactical_setting", "")
        if setting == "Amphibious Assault" and "FRSS" in fp:
            add(day, 13 * 60, 26 * 60, "phase_ashore",
                "Surgical capability phases ashore",
                "Beach landing sites secured; the ERSS/FRSS has completed its move ashore.",
                "From the effective time, casualties route POI/CCP → FRSS (ashore). "
                "Afloat surgical capability stops accepting new casualties; ERC shifts to shore-to-ship onward movement.")
        if setting in ("Retrograde Operations", "Frontal Attack") and "FRSS" in fp:
            add(day, 10 * 60, 14 * 60, "surgical_unavailable",
                "FRSS displaces (jump)",
                "The supported unit displaces; the FRSS breaks down to jump forward/rearward.",
                "During the window there is NO damage-control surgery at Role 2. Surgical candidates receive DCR "
                "and PCC, and move with priority to the next surgical capability.")
        mascal_day = bool(getattr(day, "mascal", False))
        if contested and (mascal_day or ("peer" in threat and len(days) > 1 and i == len(days) // 2)):
            add(day, 12 * 60, 18 * 60, "evac_denied",
                "MEDEVAC corridor denied",
                "Enemy air defense/UAS activity closes the evacuation corridor forward of Role 2.",
                "No onward rotary-wing evacuation from Role 2 during the window. Role 2 holds casualties "
                "under prolonged casualty care until the corridor reopens; report holding census hourly to the COC.")
        if getattr(day, "cbrn", False):
            add(day, 8 * 60, 12 * 60, "decon",
                "CBRN — decontamination before treatment",
                "Suspected chemical release in the supported unit's area.",
                "All casualties pass through a patient decontamination point before entering Role 2. "
                "Only life-saving interventions are performed in the hot/warm zone.")
        if getattr(day, "night_ops", False) and "permissive" not in threat:
            add(day, 20 * 60, 26 * 60, "night_delay",
                "Rotary-wing NVG restrictions",
                "Illumination and threat restrict rotary-wing flight to NVG profiles.",
                "Expect evacuation to take 30 min longer during the window; plan for more en route and holding care.")
    return out


def active_fragos(fragos: List[Dict], day_number: int, minute: int) -> List[Dict]:
    return [f for f in fragos if f["day"] == day_number and f["start"] <= minute < f["end"]]


def chain_for(config, day, minute: int, fragos: List[Dict], transit_priority_min: int) -> Dict:
    """Care chain in force for a casualty arriving on `day` at `minute`."""
    nodes = base_chain(config, day, transit_priority_min)
    notes: List[str] = []
    in_force = active_fragos(fragos, day.day_number, minute)
    for f in in_force:
        eff = f["effect"]
        if eff == "phase_ashore":
            for n in nodes:
                if n["id"] == "R2":
                    n["name"] = "FRSS (ashore)"
        elif eff == "surgical_unavailable":
            for n in nodes:
                if n["id"] == "R2":
                    n["name"] = f"{n['name'].split(' (')[0]} (FRSS displacing)"
                    n["capability"] = ["DCR"]
        elif eff == "evac_denied":
            if not any(n["id"] == "HOLD" for n in nodes):
                idx = next(i for i, n in enumerate(nodes) if n["id"] == "R2") + 1
                nodes.insert(idx, _node("HOLD", "Holding (PCC)", ["PCC"]))
            else:
                for n in nodes:
                    if n["id"] == "HOLD":
                        n["name"] = "Holding (PCC)"
            notes.append("Onward evacuation denied — expect prolonged holding at Role 2.")
        elif eff == "decon":
            idx = next(i for i, n in enumerate(nodes) if n["id"] == "R2")
            nodes.insert(idx, _node("DECON", "Patient decon point", ["TCCC"]))
        elif eff == "night_delay":
            notes.append("NVG restrictions: evacuation takes ~30 min longer.")
    return {"nodes": nodes, "legs": chain_to_legs(nodes), "fragos": [f["number"] for f in in_force],
            "notes": notes}


def fragos_text(fragos: List[Dict], exercise_name: str) -> str:
    if not fragos:
        return ("No FRAGOs were generated for this exercise. The care chain in the WARNO "
                "stays in force for the whole exercise.")
    parts = []
    for f in fragos:
        parts.append(
            f"FRAGO {f['number']:02d} TO OPORD {exercise_name.upper()} — {f['title'].upper()}\n"
            f"Effective: D{f['day']} {_hhmm(f['start'])} to {_hhmm(f['end'])}\n\n"
            f"1. SITUATION. {f['situation']}\n"
            f"2. MISSION. No change.\n"
            f"3. EXECUTION. {f['execution']}\n"
            f"4. ADMINISTRATION AND LOGISTICS. No change unless stated above. Medical regulating per Annex Q.\n"
            f"5. COMMAND AND SIGNAL. No change. Acknowledge.\n")
    return "\n\n".join(parts)


def chain_summary(config, fragos: List[Dict], transit_priority_min: int) -> str:
    """Plain-text care chain for the WARNO / Annex Q prompts so the orders
    describe the same legs the cases are built on."""
    lines = []
    for day in getattr(config, "days", []) or []:
        nodes = base_chain(config, day, transit_priority_min)
        lines.append(f"Day {day.day_number}: " + " → ".join(n["name"] for n in nodes))
    for f in fragos:
        lines.append(f"FRAGO {f['number']:02d} (D{f['day']} {_hhmm(f['start'])}-{_hhmm(f['end'])}): {f['title']}")
    return "\n".join(lines)


# --- Pathways ---------------------------------------------------------------

PATHWAYS = {
    "DCR_DCS": "DCR → damage control surgery → evacuation",
    "DCR_DEFERRED_DCS": "DCR + PCC; surgery needed but unavailable here → priority evac to surgical capability",
    "DCR_HOLD": "DCR → holding → evacuation (no surgery)",
    "DCR_PCC": "DCR → prolonged casualty care while onward evac is denied",
    "MEDICAL": "Medical/DNBI work-up and treatment → hold, evac, or RTD",
    "EXPECTANT": "Expectant — comfort care, reassess as resources allow",
}


def determine_pathway(case: Dict, chain: Dict) -> str:
    triage = case.get("triage_category", "")
    disposition = (case.get("disposition") or "").lower()
    surgical = (case.get("phases") or {}).get("dcs") is not None
    r2 = next((n for n in chain["nodes"] if n.get("role2")), None)
    can_dcs = bool(r2 and "DCS" in r2["capability"])
    holding_pcc = any(n["id"] == "HOLD" and "PCC" in n["name"] for n in chain["nodes"])
    if triage == "Expectant" or "expectant" in disposition:
        return "EXPECTANT"
    if surgical:
        return "DCR_DCS" if can_dcs else "DCR_DEFERRED_DCS"
    mech = ((case.get("zmist") or {}).get("mechanism") or "").lower()
    if mech.startswith("dnbi") or disposition == "rtd":
        return "MEDICAL"
    return "DCR_PCC" if holding_pcc else "DCR_HOLD"


PATHWAY_SKELETONS = {
    "DCR_DCS": "Primary survey → M (massive hemorrhage / blood sweep) → A → R → C → H (head/hypothermia) → "
               "log roll/posterior → failure branches (lettered connectors) → DCS outcome; transient response "
               "without DCS feeds the DCS node.",
    "DCR_DEFERRED_DCS": "As DCR_DCS, but the outcome is 'Priority evac to surgical capability' with PCC holding "
                        "measures; NO surgery at this node.",
    "DCR_HOLD": "Primary survey → MARCH → DCR (warmed blood, Ca per CPG, TXA if appropriate) → "
                "crystalloid/colloid or pharmacologic options if no blood → holding/evac outcome. No DCS node.",
    "DCR_PCC": "Primary survey → MARCH → DCR → PCC bundle (reassessment, analgesia/sedation, temp, lines, "
               "urine output, wound care, teleconsultation) → hold until corridor reopens → evac outcome.",
    "MEDICAL": "Initial assessment → focused history/exam → diagnostics available at this node → treatment → "
               "disposition (RTD / hold / evac); deterioration branch.",
    "EXPECTANT": "Triage decision → comfort care → periodic reassessment branch (upgrade if resources allow) → "
                 "outcome (DOW or upgrade).",
}


# --- Controller layer (LLM) -----------------------------------------------

CONTROLLER_SYSTEM_PROMPT = """You are an expert military medical simulation designer building the CONTROLLER
LAYER for one casualty: decision trees, turnover cards, critical actions and vitals tracks. Your output is
used by sim controllers during live play and is red-teamed by trauma surgeons, emergency physicians, CRNAs
and simulation technicians — write at that standard.

RULES
- One tree per leg you are given, using the exact leg ids. Trees follow primary-survey / MARCH order. A tree
  contains ONLY interventions available at that node's capability (an ERC cannot perform a thoracotomy; an
  STP has no DCS). Use lettered branch connectors (A, B, C) for findings that spawn a sub-path. Mark failure
  paths (what happens when the team misses or does the wrong thing) with "failure": true.
- Node types: assessment, finding, intervention, branch, outcome. Edge "condition" is the finding or
  threshold that sends play down that edge.
- Keep thresholds consistent everywhere (e.g., chest-tube output). Current JTS thoracic guidance: initial
  output >=1500 mL or ongoing >200 mL/hr for 2-4 h indicates operative control.
- Laterality must match the wounds list exactly across every text field.
- GCS must equal E+V+M (E1-4, V1-5, M1-6).
- Vitals tracks are for the FOCUS leg only, every 5 minutes. "green" runs 0-60 min: the course if the team
  performs the critical actions. "red" runs 0 to 20-30 min: the course if a critical action is missed, and
  must worsen physiologically (e.g., HR rises, then falls toward arrest; BP falls; SpO2 falls; AVPU drops).
  t=0 is identical in both tracks. Handover vitals at the focus leg should match green t=0; explain any
  difference in the handover summary.
- Each critical action gives the window in minutes before the red track starts, and how to rejoin green.
- Meds on the turnover card use realistic TCCC/JTS doses (TXA 2 g IV; calcium per CPG) with minutes-prior.
- Only include a burns block when the injuries involve burns.
- Every wound needs anatomic region, side (L, R, midline, bilateral), surface (anterior or posterior), type,
  and prehospital intervention.

EXPERT REFERENCE — focus-leg tree from an expert-built ERSS (afloat) DCS case, mortar strike, BLE amputations
with ineffective TQs, bilateral chest wounds, untreated posterior wound. Match this depth and style:
  Pt arrival/primary survey → Massive hemorrhage, blood sweep [finding: bleeding from BLE amputations continues
  until addressed] → Loose TQs x2 (tighten/replace) → Airway intact → Breathing diminished bilat
  → (A) +E-FAST bilateral → bilat ND: release of air, R>L improvement OR bilat finger thoracostomy/chest tube:
        release of air, L 1500 mL EBL, R scant → L chest tube output >200 mL/hr without DCS → DCS (L thoracotomy)
  → (B, failure) PPV without decompression = increased tension physiology → trend to PEA arrest → (A) → OR → DCS
  → Circulation: rapid weak radial pulse, CR >3 s → (C) DCR: rapid infusion of warmed blood, early WBB/resupply,
        Ca per CPG, TXA if appropriate → transient response without DCS → DCS
  → Log roll: posterior wound untreated at POI → other important considerations (C-spine, pelvic stability,
        lethal diamond, TXA/Abx/pain/sedation, temp) → DCS
A DCR-only reference (hemorrhage, ERC to FOB): primary survey → massive hemorrhage (TQ x3 effective, pelvic
binder) → airway → breathing per vent settings → circulation: rapid weak radial pulse → (A) DCR: warmed blood,
Ca per CPG, TXA if appropriate → consider crystalloid/colloid or pharmacologic interventions if no blood was
brought → other considerations incl. airway emergencies, elevation changes, platform stability, access, comms
with air crew/pilots/higher. No DCS node.

JSON STRUCTURE
{
  "wounds": [{"id": "w1", "region": "chest|abdomen|pelvis|head|face|neck|upper arm|forearm|hand|thigh|knee|lower leg|foot|scapula|upper back|lower back|flank|buttock|groin", "side": "L|R|midline|bilateral", "surface": "anterior|posterior", "type": "String", "intervention": "String", "effective": true}],
  "moulage": "String — what the sim tech builds, and the findings the manikin/actor presents",
  "critical_decisions": ["String"],
  "legs": [{
     "leg_id": "EXACT id provided",
     "handover": {"summary": "String", "vitals": {"hr": 0, "sbp": 0, "dbp": 0, "rr": 0, "spo2": 0, "avpu": "A|V|P|U"},
                  "meds": [{"drug": "String", "dose": "String", "route": "String", "minutes_prior": 0}],
                  "interventions": ["String"]},
     "tree": {"nodes": [{"id": "n1", "type": "assessment", "label": "Short box text", "detail": "String", "failure": false}],
              "edges": [{"from": "n1", "to": "n2", "condition": "String"}]},
     "considerations": ["String"]
  }],
  "critical_actions": [{"id": "ca1", "leg_id": "FOCUS leg id", "action": "String", "window_min": 10,
                        "if_missed": "String", "rejoin": "String"}],
  "vitals_tracks": {"green": [VITALS], "red": [VITALS]},
  "controller_note": "String — e.g. 'If they place a chest tube and continue DCR, stay on green; if not, move to red. Transient response until DCS. Once they perform the intervention, move to green and continue.'",
  "burns": null
}
VITALS = {"t": 0, "hr": 0, "sbp": 0, "dbp": 0, "rr": 0, "spo2": 0, "temp_f": 97.0, "etco2": null,
          "avpu": "A|V|P|U", "gcs_e": 4, "gcs_v": 5, "gcs_m": 6, "pupils": "Normal|Sluggish|Fixed|None"}
"""


def _case_brief(case: Dict) -> Dict:
    phases = case.get("phases") or {}
    return {
        "title": (case.get("meta") or {}).get("title"),
        "zmist": case.get("zmist"),
        "triage": case.get("triage_category"),
        "disposition": case.get("disposition"),
        "patient": case.get("patient_data"),
        "phases": {k: {"narrative": (v or {}).get("narrative"), "expected_actions": (v or {}).get("expected_actions")}
                   for k, v in phases.items() if v},
        "labs": case.get("labs"),
    }


def controller_prompt(case: Dict, chain: Dict, pathway: str, fragos_in_force: List[Dict],
                      is_maritime: bool) -> str:
    legs = [{"leg_id": l["id"], "title": l["title"], "capability": l["capability"], "focus": l["focus"]}
            for l in chain["legs"]]
    focus = next((l["id"] for l in chain["legs"] if l["focus"]), chain["legs"][0]["id"])
    frago_lines = "; ".join(f"FRAGO {f['number']:02d}: {f['title']} — {f['execution']}" for f in fragos_in_force)
    return (
        f"CASE:\n{json.dumps(_case_brief(case), indent=1)}\n\n"
        f"CARE CHAIN LEGS (build one tree per leg, same ids):\n{json.dumps(legs, indent=1)}\n"
        f"FOCUS LEG (vitals tracks + critical actions): {focus}\n"
        f"PATHWAY: {pathway} — {PATHWAYS[pathway]}\n"
        f"PATHWAY SKELETON for the focus leg: {PATHWAY_SKELETONS[pathway]}\n"
        + (f"FRAGOs IN FORCE: {frago_lines}\n" if frago_lines else "")
        + ("SETTING: afloat/amphibious — include elevation changes, platform stability, access and comms with "
           "air crew/pilots/higher in considerations where relevant.\n" if is_maritime else "")
        + "Generate the controller layer JSON now."
    )


REVISE_SYSTEM_PROMPT = """You are revising a medical simulation controller layer after red-team review.
Fix EVERY finding listed without changing anything that was not flagged. Return the full corrected JSON
in exactly the same structure you were given. Output JSON only."""


def _parse_json(text: str) -> Dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}") + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
        raise


_VITAL_KEYS = ("t", "hr", "sbp", "dbp", "rr", "spo2", "temp_f", "etco2", "gcs_e", "gcs_v", "gcs_m")


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return v
    m = re.search(r"-?\d+(\.\d+)?", str(v))
    if not m:
        return None
    f = float(m.group())
    return int(f) if f.is_integer() else f


def normalize_controller(ctrl: Dict, chain: Dict, pathway: str) -> Dict:
    """Coerce LLM output into the shape downstream code relies on."""
    ctrl = dict(ctrl or {})
    ctrl["pathway"] = pathway
    ctrl["chain"] = chain
    ctrl.setdefault("wounds", [])
    ctrl.setdefault("critical_decisions", [])
    ctrl.setdefault("critical_actions", [])
    ctrl.setdefault("controller_note", "")
    ctrl.setdefault("moulage", "")
    tracks = ctrl.get("vitals_tracks") or {}
    for k in ("green", "red"):
        pts = []
        for p in tracks.get(k) or []:
            if not isinstance(p, dict):
                continue
            q = dict(p)
            for key in _VITAL_KEYS:
                if key in q:
                    q[key] = _num(q[key])
            pts.append(q)
        tracks[k] = sorted(pts, key=lambda p: p.get("t") or 0)
    ctrl["vitals_tracks"] = tracks
    by_id = {l.get("leg_id"): l for l in ctrl.get("legs") or [] if isinstance(l, dict)}
    legs = []
    for leg in chain["legs"]:
        got = by_id.get(leg["id"], {})
        tree = got.get("tree") or {}
        legs.append({
            "leg_id": leg["id"], "title": leg["title"], "focus": leg["focus"], "capability": leg["capability"],
            "handover": got.get("handover") or {},
            "tree": {"nodes": [n for n in tree.get("nodes") or [] if isinstance(n, dict)],
                     "edges": [e for e in tree.get("edges") or [] if isinstance(e, dict)]},
            "considerations": got.get("considerations") or [],
        })
    ctrl["legs"] = legs
    ctrl["focus_leg"] = next((l["id"] for l in chain["legs"] if l["focus"]), chain["legs"][0]["id"])
    return ctrl


def generate_controller(case: Dict, chain: Dict, pathway: str, fragos_in_force: List[Dict],
                        is_maritime: bool, llm: Callable[[str, str], str]) -> Dict:
    text = llm(controller_prompt(case, chain, pathway, fragos_in_force, is_maritime), CONTROLLER_SYSTEM_PROMPT)
    return normalize_controller(_parse_json(text), chain, pathway)


def revise_controller(ctrl: Dict, findings: List[Dict], llm: Callable[[str, str], str]) -> Dict:
    body = {k: v for k, v in ctrl.items() if k not in ("chain", "pathway", "focus_leg", "quality")}
    prompt = ("FINDINGS TO FIX:\n" + json.dumps(findings, indent=1)
              + "\n\nCURRENT CONTROLLER LAYER:\n" + json.dumps(body, indent=1))
    revised = _parse_json(llm(prompt, REVISE_SYSTEM_PROMPT))
    return normalize_controller(revised, ctrl["chain"], ctrl["pathway"])


# --- Offline fallback -----------------------------------------------------

def _parse_bp(bp) -> tuple:
    m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", str(bp or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _initial_vitals(case: Dict) -> Dict:
    trend = ((case.get("phases") or {}).get("dcr") or {}).get("vitals_trend") or []
    v0 = trend[0] if trend else {}
    sbp, dbp = _parse_bp(v0.get("bp"))
    gcs = _num(v0.get("gcs")) or 15
    return {"hr": _num(v0.get("hr")) or 110, "sbp": sbp or 100, "dbp": dbp or 65,
            "rr": _num(v0.get("rr")) or 22, "spo2": _num(v0.get("spo2")) or 95, "gcs": int(gcs)}


def _gcs_parts(total: int) -> tuple:
    total = max(3, min(15, total))
    e = max(1, min(4, round(total * 4 / 15)))
    m = max(1, min(6, round(total * 6 / 15)))
    v = total - e - m
    if v < 1:
        m -= 1 - v
        v = 1
    if v > 5:
        m += v - 5
        v = 5
    return e, v, m


def _avpu(gcs: int) -> str:
    return "A" if gcs >= 14 else "V" if gcs >= 10 else "P" if gcs >= 6 else "U"


def _pt(t, hr, sbp, dbp, rr, spo2, temp, gcs, pupils="Normal"):
    e, v, m = _gcs_parts(gcs)
    return {"t": t, "hr": int(hr), "sbp": int(sbp), "dbp": int(dbp), "rr": int(rr), "spo2": int(spo2),
            "temp_f": round(temp, 1), "etco2": None, "avpu": _avpu(gcs), "gcs_e": e, "gcs_v": v, "gcs_m": m,
            "pupils": pupils}


def fallback_controller(case: Dict, chain: Dict, pathway: str) -> Dict:
    """Template controller layer used when AI generation fails. Structurally
    complete and internally consistent; flagged for expert review."""
    v = _initial_vitals(case)
    gcs = v["gcs"]
    green, red = [], []
    for i in range(13):
        t = i * 5
        f = min(1.0, t / 40)
        green.append(_pt(t, v["hr"] - (v["hr"] - 100) * f if v["hr"] > 100 else v["hr"],
                         v["sbp"] + max(0, 110 - v["sbp"]) * f, v["dbp"] + max(0, 70 - v["dbp"]) * f,
                         v["rr"] - max(0, v["rr"] - 18) * f, min(98, v["spo2"] + 3 * f), 96.8 + f, gcs))
    for i in range(5):
        t = i * 5
        late = i >= 3
        g = max(3, gcs - 2 * i)
        red.append(_pt(t, (v["hr"] + 6 * i) if not late else max(40, v["hr"] - 25 * (i - 2)),
                       max(40, v["sbp"] - 10 * i), max(25, v["dbp"] - 7 * i),
                       v["rr"] + 3 * i if not late else max(6, v["rr"] - 8), max(60, v["spo2"] - 4 * i),
                       96.8 - 0.3 * i, g, "Normal" if i < 2 else "Sluggish"))
    red[0] = dict(green[0])
    surgical_here = pathway == "DCR_DCS"
    legs = []
    for leg in chain["legs"]:
        nodes = [{"id": "n1", "type": "assessment", "label": "Primary survey", "detail": "", "failure": False},
                 {"id": "n2", "type": "intervention", "label": "Massive hemorrhage — blood sweep", "detail": "", "failure": False},
                 {"id": "n3", "type": "assessment", "label": "Airway", "detail": "", "failure": False},
                 {"id": "n4", "type": "assessment", "label": "Breathing / respirations", "detail": "", "failure": False},
                 {"id": "n5", "type": "assessment", "label": "Circulation", "detail": "", "failure": False},
                 {"id": "n6", "type": "intervention", "label": "Hypothermia / head injury", "detail": "", "failure": False}]
        if leg["focus"]:
            nodes.append({"id": "n7", "type": "intervention", "label": "DCR",
                          "detail": "Rapid infusion of warmed blood; Ca per CPG; TXA if appropriate", "failure": False})
            outcome = {"DCR_DCS": "DCS", "DCR_DEFERRED_DCS": "Priority evac to surgical capability",
                       "DCR_PCC": "PCC — hold until corridor reopens", "MEDICAL": "Disposition per work-up",
                       "EXPECTANT": "Comfort care / reassess"}.get(pathway, "Holding → evac")
            nodes.append({"id": "n8", "type": "outcome", "label": outcome, "detail": "", "failure": False})
            nodes.append({"id": "f1", "type": "finding", "label": "Critical action missed", "detail": "Move to red vitals", "failure": True})
        else:
            nodes.append({"id": "n7", "type": "outcome", "label": f"Handover to {leg['to']}", "detail": "", "failure": False})
        edges = [{"from": f"n{i}", "to": f"n{i + 1}", "condition": ""} for i in range(1, len([n for n in nodes if n["id"].startswith("n")]))]
        if leg["focus"]:
            edges.append({"from": "n5", "to": "f1", "condition": "Shock not treated"})
            edges.append({"from": "f1", "to": "n7", "condition": "Correct intervention performed"})
        legs.append({"leg_id": leg["id"], "handover": {"summary": "Template handover — expert review required.",
                     "vitals": {k: green[0][k] for k in ("hr", "sbp", "dbp", "rr", "spo2", "avpu")},
                     "meds": [], "interventions": []},
                     "tree": {"nodes": nodes, "edges": edges}, "considerations": ["C-spine", "Pelvic stability",
                     "Lethal diamond", "TXA, Abx, Pain, Sedation", "Temp"]})
    focus = next((l["id"] for l in chain["legs"] if l["focus"]), chain["legs"][0]["id"])
    ctrl = {
        "wounds": [], "moulage": (case.get("zmist") or {}).get("injuries", ""),
        "critical_decisions": ["Recognition of shock", "Treat shock with blood products (balanced resuscitation)"]
                              + (["Damage control surgery, initiate evac to higher"] if surgical_here else []),
        "legs": legs,
        "critical_actions": [{"id": "ca1", "leg_id": focus, "action": "Balanced resuscitation with warmed blood",
                              "window_min": 10, "if_missed": "Progressive shock — move to red",
                              "rejoin": "Once blood is running, return to green"}],
        "vitals_tracks": {"green": green, "red": red},
        "controller_note": "If they treat shock and continue DCR, stay on green; if not, move to red. "
                           "Once they perform the correct intervention, move to green and continue.",
        "burns": None, "_fallback": True,
    }
    return normalize_controller(ctrl, chain, pathway)
