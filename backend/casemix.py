"""Scenario-bounded, per-exercise case mix.

How it works
------------
1. ENVELOPES. Every tunable number is a (min, mode, max) range, taken from the literature where one exists
   (see SOURCES) and labelled provisional where it does not. The scenario the user selected (threat level,
   tactical settings, MASCAL etiologies, Humanitarian days, evacuation access) widens or shifts each range.
   The scenario therefore BOUNDS what any exercise can look like.
2. DRAW. At the start of each exercise one value is drawn per parameter from its envelope (triangular
   distribution), from a fresh random seed. Two exercises with identical settings get different draws, so
   no two are the same, but every draw lies inside the scenario's envelope.
3. ASSIGN. Severity is assigned to every casualty slot first (critical / severe / moderate / mild), then the
   case type is picked from a pool of that severity, then triage, outcome, population and night arrival are
   assigned from the drawn parameters. The draw (seed, envelopes, values) is saved with the exercise, and the
   same draw reproduces the same mix.

The model then writes each case around its assigned requirements, and the code overrides the fields afterwards.
"""
import random
from typing import Dict, List, Optional, Tuple

TRIAGE = ("T1", "T2", "T3", "Expectant")
DISPOSITION = ("RTD", "Evac to Role 3", "Hold at Role 2", "Died of Wounds", "Expectant")
SEVERITIES = ("critical", "severe", "moderate", "mild")
POPULATIONS = ("us", "partner", "civilian", "enemy")
HUMANITARIAN = {"Humanitarian Assistance", "Stability Operations"}
HOLD_LIMIT_HOURS = 72   # doctrine: Role 2 / prolonged-care holding is planned for up to 72 h; the orders state it
NIGHT_SHARE = 0.35  # must match generate_schedule's night wave (round(total_patients * 0.35))
BLAST_FAMILY = {"IED/Blast", "VBIED", "UAS/Drone Strike", "Indirect Fire/Mortar"}

SOURCES = {
    "kotwal2018": "Kotwal RS et al. A US military Role 2 forward surgical team database study of combat mortality in "
                  "Afghanistan. J Trauma Acute Care Surg 2018;85:603-12 (n=9,557 battle-injured; PMID 29851907)",
    "kotwal2016": "Kotwal RS et al. The effect of a golden hour policy on the morbidity and mortality of combat casualties. "
                  "JAMA Surg 2016;151:15-24",
    "ews": "Emergency War Surgery (Borden Institute), triage chapter: 10-20% of casualties presenting to a surgical unit "
           "are emergent",
    "frykberg": "Frykberg ER. Triage: principles and practice. Scand J Surg 2005;94:272-8 (10-25% of blast casualties "
                "have life-threatening injuries)",
    "provisional": "No published figure found; bounded widely by judgment. Needs clinician review.",
}

# name: (min, mode, max, source). Severity shares are of each group's casualties.
PARAMS: Dict[str, Tuple[float, float, float, str]] = {
    # --- severity mix (kotwal2018 CMI-PH: ~8% critical, ~11% severe, ~24% moderate, ~55% mild among battle-injured at Role 2)
    "serious_share.routine": (0.14, 0.194, 0.25, "kotwal2018"),   # critical + severe; EWS 10-20% emergent
    # Provisional. Frykberg: 10-25% of blast casualties are life-threatening; a Role 2 receives the more seriously injured, so
    # the mass-casualty envelope deliberately sits above that and above the routine mix.
    "serious_share.mascal": (0.20, 0.30, 0.45, "provisional"),
    "serious_share.dnbi": (0.03, 0.08, 0.15, "provisional"),
    "critical_fraction": (0.30, 0.42, 0.55, "kotwal2018"),        # critical / (critical + severe) = 8.1/19.4
    "moderate_of_rest": (0.25, 0.30, 0.38, "kotwal2018"),         # moderate / (moderate + mild) ~ 24/79
    # --- mortality at Role 2 by severity (kotwal2018: 40.0% critical, 11.2% severe, 0.8% moderate, <0.1% mild)
    "mortality.critical": (0.30, 0.40, 0.50, "kotwal2018"),
    "mortality.severe": (0.08, 0.112, 0.15, "kotwal2018"),
    "mortality.moderate": (0.004, 0.008, 0.015, "kotwal2018"),
    "mortality.mild": (0.0, 0.0005, 0.001, "kotwal2018"),
    # kotwal2016: faster transport cut pre-hospital deaths but not died-of-wounds, and nothing quantifies what happens
    # when onward evacuation is denied. Directional only.
    "delay_mortality_slope": (0.0, 0.9, 1.8, "provisional"),
    "expectant_given_critical": (0.0, 0.05, 0.12, "provisional"),
    # --- onward movement and return to duty
    "evac_base": (0.80, 0.90, 0.97, "provisional"),               # share evacuated when evacuation is fully permissive
    "evac_exponent": (1.0, 1.5, 2.2, "provisional"),
    "rtd_mild": (0.50, 0.70, 0.90, "provisional"),
    "rtd_moderate": (0.10, 0.25, 0.40, "provisional"),
    # --- time in Role 2 by outcome, in hours. Doctrine plans Role 2 / prolonged-care holding for up to 72 h; nothing published
    # gives a distribution, so these are provisional and bounded widely.
    "hold_hours": (6.0, 24.0, 72.0, "provisional"),
    "rtd_observation_hours": (1.0, 3.0, 6.0, "provisional"),
    "evac_wait_hours": (2.0, 6.0, 12.0, "provisional"),   # times (1 - evacuation access)
    "dow_hours": (0.5, 2.0, 6.0, "provisional"),
    # --- who is treated (kotwal2018: 21.3% civilian/other, 37.4% US, 37.3% Afghan forces, 4.0% non-US coalition)
    "civilian_share": (0.12, 0.213, 0.30, "kotwal2018"),
    "partner_share": (0.08, 0.20, 0.41, "provisional"),            # ceiling from kotwal2018: Afghan forces + non-US coalition = 41%
    "enemy_share_detainee_day": (0.06, 0.12, 0.20, "provisional"),
    "enemy_share_other": (0.04, 0.08, 0.12, "provisional"),
}

NOT_A_PROBABILITY = {"delay_mortality_slope", "evac_exponent", "hold_hours", "rtd_observation_hours",
                     "evac_wait_hours", "dow_hours"}  # every other parameter is a 0-1 share or rate

# Severity -> triage. Provisional: the share of "severe" casualties sorted T1 vs T2, and so on.
SEVERITY_TO_TRIAGE = {
    "critical": {"T1": 1.0},
    "severe": {"T1": 0.70, "T2": 0.30},
    "moderate": {"T2": 0.85, "T3": 0.15},
    "mild": {"T3": 0.90, "T2": 0.10},
}
EXPECTANT_DISPOSITION_DIES = 0.30   # of casualties triaged expectant, the share recorded as Died of Wounds

# --- evacuation access: how realistic is onward evacuation to Role 3 on a given day? ----------------------
# Mirrors main._threat_evac_mult (Peer/Near-Peer 3.0, Hybrid 2.0, Irregular 1.5, else 1.0) so the case mix and the
# FRAGOs agree about how contested the corridor is. 1.0 = permissive; lower = denied or scarce.
_THREAT_ACCESS = (("peer", 1 / 3.0), ("hybrid", 1 / 2.0), ("irregular", 1 / 1.5))
_SETTING_ACCESS = {
    "Retrograde Operations": 0.80, "Frontal Attack": 0.85, "Amphibious Assault": 0.85,
    "Defensive Operations": 0.90, "Convoy Operations": 0.95,
    "Stability Operations": 1.10, "Humanitarian Assistance": 1.20,
}

POPULATION_PROMPT = {
    "us": "a US service member",
    "partner": "a partner-force soldier",
    "civilian": ("a host-nation civilian (non-combatant); apply the civilian-care provisions of the MEDROE: treat by clinical "
                 "need, then transfer or hand over to host-nation care when stable"),
    "enemy": ("an enemy combatant held as a detainee/EPW; apply the detainee-care provisions of the MEDROE: treat by clinical need, "
              "custody and security stay with the guard force, status is documented; make 9-line line 8 show enemy/detainee status"),
}
SEVERITY_PROMPT = {
    "critical": "critical: life-threatening and resuscitation-dependent, with high mortality even with prompt care",
    "severe": "severe: serious injuries needing surgery or intensive care, likely to survive with timely care",
    "moderate": "moderate: significant but physiologically stable; needs treatment, no resuscitation",
    "mild": "mild: minor injury; treat and release or observe; no resuscitation or surgery",
}


def evac_access(config, day) -> float:
    """~0.2 (large-scale combat, denied corridor) to 1.2 (permissive HADR); 1.0 = ordinary."""
    threat = (getattr(config, "threat_level", "") or "").lower()
    base = next((v for k, v in _THREAT_ACCESS if k in threat), 1.0)
    access = base * _SETTING_ACCESS.get(getattr(day, "tactical_setting", ""), 1.0)
    if (getattr(config, "environment", "") or "").lower() == "maritime":
        access *= 0.9
    return round(max(0.2, min(1.2, access)), 2)


# --- care policy: the single source of truth shared by the MEDROE text and the case mix ---------------

def care_policy(config) -> Dict:
    """Who this exercise is meant to treat beyond friendly forces.

    Enemy combatants / EPW: explicit config override, else on when any day has Detainee Ops.
    Host-nation civilians: explicit override, else on when any day is Humanitarian Assistance or Stability.
    """
    days = list(getattr(config, "days", []) or [])
    enemy = getattr(config, "treat_enemy_combatants", None)
    civ = getattr(config, "treat_civilians", None)
    derived_enemy = any(getattr(d, "detainee_ops", False) for d in days)
    derived_civ = any(getattr(d, "tactical_setting", "") in HUMANITARIAN for d in days)
    return {
        "enemy_combatants": derived_enemy if enemy is None else bool(enemy),
        "civilians": derived_civ if civ is None else bool(civ),
        "enemy_from": "override" if enemy is not None else ("Detainee Ops day" if derived_enemy else "default"),
        "civilians_from": "override" if civ is not None else ("Humanitarian/Stability day" if derived_civ else "default"),
    }


def policy_text(policy: Dict) -> str:
    """Authoritative eligibility statement injected into the MEDROE prompt."""
    def line(who: str, on: bool) -> str:
        if on:
            return (f"- {who}: AUTHORIZED. Care is rendered by clinical need; expect a meaningful share of this "
                    f"exercise's casualties to be {who.lower()}.")
        return (f"- {who}: NOT part of this exercise's casualty stream. Provide for emergency stabilization of any who "
                f"present, then transfer or hand over as directed; expect only one or two such cases.")
    return ("ELIGIBILITY POLICY (authoritative: the exercise's casualty mix is generated from this, so the MEDROE must "
            "state it exactly and consistently):\n"
            + line("Enemy combatants / detainees (EPW)", policy["enemy_combatants"]) + "\n"
            + line("Host-nation civilians", policy["civilians"]) + "\n"
            + "- US and partner-force personnel: authorized.")


# --- envelopes: the scenario bounds every parameter ------------------------------------------------------

def _scenario(config) -> Dict:
    days = list(getattr(config, "days", []) or [])
    threat = (getattr(config, "threat_level", "") or "").lower()
    access = [evac_access(config, d) for d in days] or [1.0]
    return {
        "threat": "peer" if "peer" in threat else "hybrid" if "hybrid" in threat else "irregular" if "irregular" in threat
        else "permissive",
        "humanitarian": any(getattr(d, "tactical_setting", "") in HUMANITARIAN for d in days),
        "etiologies": sorted({d.mascal_etiology for d in days if getattr(d, "mascal", False) and d.mascal_etiology}),
        "has_mascal": any(getattr(d, "mascal", False) for d in days),
        "high_acuity": getattr(config, "casualty_acuity", "realistic") == "high",
        "min_access": min(access), "mean_access": round(sum(access) / len(access), 2),
    }


def _mul(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return a[0] * b[0], a[1] * b[1]


def _threat(s: Dict, peer: Tuple[float, float], hybrid: Tuple[float, float]) -> Tuple[float, float]:
    return {"peer": peer, "hybrid": hybrid}.get(s["threat"], (1.0, 1.0))


# Scenario widening/shifting of each envelope: (low multiplier, high multiplier). Directional and provisional: the
# literature supports the direction (large-scale combat and blast mass-casualty events are more severe; humanitarian
# work is milder), not the size.
def _acuity(s: Dict) -> Tuple[float, float]:
    """casualty_acuity="high" is a training-emphasis switch: 2-3x as many critical and severe casualties."""
    return (2.0, 3.0) if s["high_acuity"] else (1.0, 1.0)


SCALE = {
    "serious_share.routine": lambda s: _mul(_mul(_threat(s, (1.0, 1.30), (1.0, 1.15)), (0.70, 0.90) if s["humanitarian"] else (1.0, 1.0)), _acuity(s)),
    "serious_share.mascal": lambda s: _mul(_mul(_threat(s, (1.0, 1.15), (1.0, 1.10)),
                                                (1.0, 1.20) if BLAST_FAMILY & set(s["etiologies"]) else (0.90, 1.0)), _acuity(s)),
    "serious_share.dnbi": _acuity,
    # Where evacuation is badly contested, held casualties stay longer.
    "hold_hours": lambda s: (1.5, 1.0) if s["min_access"] < 0.5 else (1.0, 1.0),
    "expectant_given_critical": lambda s: (1.0, 2.0) if s["threat"] in ("peer", "hybrid") else (1.0, 1.0),
    "civilian_share": lambda s: (1.0, 1.4) if s["humanitarian"] else (1.0, 1.0),
}


def _envelope(name: str, scenario: Dict) -> Tuple[float, float, float]:
    lo, mode, hi = PARAMS[name][:3]
    lo_m, hi_m = SCALE[name](scenario) if name in SCALE else (1.0, 1.0)
    lo, hi = lo * lo_m, hi * hi_m
    mode = min(max(mode * (lo_m + hi_m) / 2, lo), hi)
    if name not in NOT_A_PROBABILITY:
        lo, mode, hi = (min(max(v, 0.0), 0.95) for v in (lo, mode, hi))
    return round(lo, 4), round(mode, 4), round(hi, 4)


def draw_parameters(config, rng: Optional[random.Random] = None) -> Dict:
    """Draw one value per parameter from the scenario's envelopes. Saved with the exercise; reproducible from `seed`."""
    seed = (rng or random.Random()).randrange(2 ** 31)
    r = random.Random(seed)
    scenario = _scenario(config)
    envelopes = {n: list(_envelope(n, scenario)) for n in PARAMS}
    params = {n: round(r.triangular(lo, hi, mode), 4) for n, (lo, mode, hi) in envelopes.items()}
    return {"version": 2, "seed": seed, "scenario": scenario, "envelopes": envelopes, "params": params,
            "sources": {n: PARAMS[n][3] for n in PARAMS}}


# --- severity first --------------------------------------------------------------------------------------

def _counts(n: int, weights: Dict[str, float]) -> Dict[str, int]:
    """Largest-remainder allocation of n items across weights."""
    total = sum(weights.values()) or 1.0
    raw = {k: n * v / total for k, v in weights.items()}
    base = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)[: n - sum(base.values())]:
        base[k] += 1
    return base


def severity_weights(kind: str, p: Dict[str, float]) -> Dict[str, float]:
    serious = p[f"serious_share.{kind}"]
    rest = 1.0 - serious
    return {"critical": serious * p["critical_fraction"], "severe": serious * (1 - p["critical_fraction"]),
            "moderate": rest * p["moderate_of_rest"], "mild": rest * (1 - p["moderate_of_rest"])}


def assign_severities(kinds: List[str], draw: Dict, rng: Optional[random.Random] = None) -> List[str]:
    """One severity per casualty slot. kinds are 'routine' / 'mascal' / 'dnbi' (trauma groups use their own mix)."""
    rng = rng or random.Random(draw["seed"])
    out = [""] * len(kinds)
    for kind in ("routine", "mascal", "dnbi"):
        idx = [i for i, k in enumerate(kinds) if k == kind]
        labels = [s for s, c in _counts(len(idx), severity_weights(kind, draw["params"])).items() for _ in range(c)]
        rng.shuffle(labels)
        for i, s in zip(idx, labels):
            out[i] = s
    return out


# --- the rest of the assignment --------------------------------------------------------------------------

def _pick(weights: Dict[str, float], rng: random.Random) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _triage(severity: str, p: Dict[str, float], access: float, rng: random.Random) -> str:
    # Where resources and evacuation are scarce, more critical casualties are triaged expectant.
    if severity == "critical" and rng.random() < min(0.6, p["expectant_given_critical"] * (1 + 2 * max(0.0, 1.0 - access))):
        return "Expectant"
    return _pick(SEVERITY_TO_TRIAGE[severity], rng)


def _disposition(severity: str, triage: str, access: float, p: Dict[str, float], rng: random.Random) -> str:
    if triage == "Expectant":
        return "Died of Wounds" if rng.random() < EXPECTANT_DISPOSITION_DIES else "Expectant"
    mult = min(3.0, 1 + (1 - access) * p["delay_mortality_slope"])
    if rng.random() < min(0.85, p[f"mortality.{severity}"] * mult):
        return "Died of Wounds"
    rtd = {"mild": p["rtd_mild"], "moderate": p["rtd_moderate"]}.get(severity, 0.0)
    if rng.random() < rtd:
        return "RTD"
    evac = min(0.98, max(0.02, p["evac_base"] * access ** p["evac_exponent"]))
    return "Evac to Role 3" if rng.random() < evac else "Hold at Role 2"


def assign_profiles(tasks: List[tuple], config, draw: Dict, rng: Optional[random.Random] = None) -> List[Dict]:
    """One profile per task: {severity, triage, disposition, population, night, evac_access}.

    tasks are (day_number, case_type, mechanism, is_trauma, is_mascal, severity)."""
    p = draw["params"]
    rng = rng or random.Random(draw["seed"] + 1)
    n = len(tasks)
    days = {d.day_number: d for d in config.days}
    profiles: List[Dict] = []
    for t in tasks:
        access = evac_access(config, days[t[0]]) if t[0] in days else 1.0
        triage = _triage(t[5], p, access, rng)
        profiles.append({"severity": t[5], "triage": triage, "evac_access": access,
                         "disposition": _disposition(t[5], triage, access, p, rng)})

    # patient population, following the care policy
    policy = care_policy(config)
    by_day: Dict[int, List[int]] = {}
    for i, t in enumerate(tasks):
        by_day.setdefault(t[0], []).append(i)
    pop = ["us"] * n

    def take(candidates: List[int], count: int, label: str):
        free = [i for i in candidates if pop[i] == "us"]
        rng.shuffle(free)
        for i in free[:count]:
            pop[i] = label

    routine = [i for i, t in enumerate(tasks) if not t[4]]
    if policy["enemy_combatants"]:
        det_days = [d for d, day in days.items() if getattr(day, "detainee_ops", False)]
        if det_days:
            for d in det_days:
                cand = [i for i in by_day.get(d, []) if not tasks[i][4]]
                if cand:
                    take(cand, min(max(1, round(len(cand) * p["enemy_share_detainee_day"])), len(cand)), "enemy")
        elif routine:
            take(routine, max(1, round(len(routine) * p["enemy_share_other"])), "enemy")
    if policy["civilians"]:
        for d, idx in by_day.items():
            humanitarian = getattr(days.get(d), "tactical_setting", "") in HUMANITARIAN
            share = min(0.45, p["civilian_share"] * (1.3 if humanitarian else 1.0))
            take(idx, round(len(idx) * share), "civilian")
        if n and "civilian" not in pop:
            take(list(range(n)), 1, "civilian")  # "some", even in a small exercise
    for idx in by_day.values():  # partner forces are always eligible
        take(idx, round(len(idx) * p["partner_share"]), "partner")
    # A population the policy does not cover appears only once or twice (emergency stabilization of a walk-in).
    excluded = [lab for lab, on in (("enemy", policy["enemy_combatants"]), ("civilian", policy["civilians"])) if not on]
    if excluded and routine:
        k = rng.choice([1, 2]) if n >= 12 else (1 if n >= 4 else 0)
        for _ in range(k):
            take(routine, 1, rng.choice(excluded))
    for i in range(n):
        profiles[i]["population"] = pop[i]

    # night arrivals: the same share of each Night Ops day's routine patients the scheduler puts in its night wave
    for d, idx in by_day.items():
        if getattr(days.get(d), "night_ops", False):
            cand = [i for i in idx if not tasks[i][4]]
            count = min(max(1, round(getattr(days[d], "total_patients", len(cand)) * NIGHT_SHARE)), len(cand))
            rng.shuffle(cand)
            for i in cand[:count]:
                profiles[i]["night"] = True
    for prof in profiles:
        prof.setdefault("night", False)
    return profiles


def dwell_minutes(disposition: str, base: int, access: float, p: Dict[str, float], rng: random.Random) -> int:
    """Minutes a casualty occupies Role 2, given the assigned outcome. `base` is the treatment time the schedule already
    allowed (45, 90 or 150 minutes by surgery phase); holds, observation, waiting for evacuation and death add to it."""
    jitter = rng.uniform(0.6, 1.4)
    if disposition == "Hold at Role 2":
        return max(base, int(60 * min(float(HOLD_LIMIT_HOURS), p["hold_hours"] * jitter)))
    if disposition == "RTD":
        return base + int(60 * p["rtd_observation_hours"] * jitter)
    if disposition == "Evac to Role 3":
        return base + int(60 * (0.5 + p["evac_wait_hours"] * max(0.0, 1.0 - access) * jitter))
    if disposition == "Died of Wounds":
        return max(base, int(60 * p["dow_hours"] * jitter))
    if disposition == "Expectant":
        return int(60 * p["dow_hours"] * jitter * 1.5)  # comfort care while resources go to others
    return base


def summarize(profiles: List[Dict]) -> Dict:
    """Counts per severity / triage / disposition / population, for logs and previews."""
    out: Dict[str, Dict[str, int]] = {"severity": {}, "triage": {}, "disposition": {}, "population": {}, "night": {}}
    for pr in profiles:
        for k, v in (("severity", pr["severity"]), ("triage", pr["triage"]), ("disposition", pr["disposition"]),
                     ("population", pr["population"]), ("night", "night" if pr["night"] else "day")):
            out[k][v] = out[k].get(v, 0) + 1
    return out
