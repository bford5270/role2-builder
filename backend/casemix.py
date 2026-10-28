"""Scenario-conditioned case mix.

Instead of letting the model pick each casualty's triage, outcome and population on its own (which gave
a narrow, repetitive mix and ignored the MEDROE), the pipeline assigns them here, in code, from the
scenario the user selected, and hands them to the case prompt as requirements.

  * Triage mix is conditioned on the case's group: DNBI, routine trauma by tactical setting, or MASCAL
    by etiology, and on its acuity tier (surgical / non-surgical trauma). Baseline rates come from
    casemix_data.json, derived from archived exercises by scripts/derive_case_mix.py.
  * Disposition is conditioned on triage and tier.
  * Patient population (US / partner / host-nation civilian / enemy combatant-EPW) follows the care
    policy: if the exercise is meant to treat civilians or enemy combatants there are some, otherwise
    there are one or two. The same policy is written into the MEDROE prompt, so the two cannot disagree.
  * Night arrivals match the share the scheduler puts in the night wave.

Every exercise draws its own mix: each baseline weight is jittered by up to +/-JITTER (relative), and
counts are allocated per group (largest remainder) so the totals track the targets.

FLOORS and TIER_MULT are PROVISIONAL clinical assumptions (the archive has no Expectant or Died of
Wounds cases at all, because the old prompt never produced them). They need clinician review.
"""
import json
import random
from pathlib import Path
from typing import Callable, Dict, List, Optional

DATA = json.loads((Path(__file__).with_name("casemix_data.json")).read_text(encoding="utf-8"))

TRIAGE = ("T1", "T2", "T3", "Expectant")
DISPOSITION = ("RTD", "Evac to Role 3", "Hold at Role 2", "Died of Wounds", "Expectant")
POPULATIONS = ("us", "partner", "civilian", "enemy")
HUMANITARIAN = {"Humanitarian Assistance", "Stability Operations"}

JITTER = 0.15          # each baseline weight varies by up to +/-15% (relative) per exercise
NIGHT_SHARE = 0.35     # must match generate_schedule's night wave (round(total_patients * 0.35))

# Acuity tier multipliers on the baseline triage weights (trauma only). The archive baseline mixes
# surgical and non-surgical cases, so these push surgical cases toward T1 and non-surgical toward T2/T3.
TIER_MULT = {
    "surgical": {"T1": 1.15, "T2": 0.60, "T3": 0.15, "Expectant": 1.0},
    "nonsurgical": {"T1": 0.70, "T2": 1.30, "T3": 2.00, "Expectant": 1.0},
}
# Minimum absolute shares (added before normalising), keyed by (group kind, tier).
TRIAGE_FLOOR = {
    ("mascal", "surgical"): {"Expectant": 0.05},
    ("routine", "surgical"): {"Expectant": 0.03},
    ("routine", "nonsurgical"): {"T3": 0.10},
    ("mascal", "nonsurgical"): {"T3": 0.08},
    ("dnbi", "dnbi"): {"T3": 0.10},
}
# Minimum absolute disposition shares, keyed by (trauma/dnbi group, triage).
DISPOSITION_FLOOR = {
    ("trauma", "T1"): {"Died of Wounds": 0.04, "Hold at Role 2": 0.05},
    ("trauma", "T2"): {"Hold at Role 2": 0.08},
    ("trauma", "T3"): {"RTD": 0.35, "Hold at Role 2": 0.15},
    ("trauma", "Expectant"): {"Expectant": 0.70, "Died of Wounds": 0.30},
    ("dnbi", "T1"): {"Hold at Role 2": 0.05},
    ("dnbi", "T3"): {"RTD": 0.30},
    ("dnbi", "Expectant"): {"Expectant": 0.70, "Died of Wounds": 0.30},
}
# Population shares not in the archive (it has essentially no enemy-combatant patients).
ENEMY_SHARE_DETAINEE_DAY = 0.12   # of a Detainee Ops day's patients; at least one per such day
ENEMY_SHARE_OTHER = 0.08          # when enemy care is enabled but no day has Detainee Ops

# --- evacuation access: how realistic is onward evacuation to Role 3 on a given day? -------------------
# Mirrors main._threat_evac_mult (Peer/Near-Peer 3.0, Hybrid 2.0, Irregular 1.5, else 1.0) so the case mix
# and the FRAGOs agree about how contested the corridor is. 1.0 = permissive; lower = denied or scarce.
_THREAT_ACCESS = (("peer", 1 / 3.0), ("hybrid", 1 / 2.0), ("irregular", 1 / 1.5))
_SETTING_ACCESS = {
    "Retrograde Operations": 0.80, "Frontal Attack": 0.85, "Amphibious Assault": 0.85,
    "Defensive Operations": 0.90, "Convoy Operations": 0.95,
    "Stability Operations": 1.10, "Humanitarian Assistance": 1.20,
}
ACCESS_EXPONENT = 1.5   # how steeply Role 3 evacuation falls off as access falls (provisional)


def evac_access(config, day) -> float:
    """~0.2 (large-scale combat, denied corridor) to 1.2 (permissive HADR); 1.0 = ordinary."""
    threat = (getattr(config, "threat_level", "") or "").lower()
    base = next((v for k, v in _THREAT_ACCESS if k in threat), 1.0)
    access = base * _SETTING_ACCESS.get(getattr(day, "tactical_setting", ""), 1.0)
    if (getattr(config, "environment", "") or "").lower() == "maritime":
        access *= 0.9
    return round(max(0.2, min(1.2, access)), 2)


POPULATION_PROMPT = {
    "us": "a US service member",
    "partner": "a partner-force soldier",
    "civilian": "a host-nation civilian (non-combatant); apply the civilian-care provisions of the MEDROE",
    "enemy": ("an enemy combatant held as a detainee/EPW; apply the detainee-care provisions of the MEDROE and "
              "make 9-line line 8 show enemy/detainee status"),
}


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


# --- helpers ---------------------------------------------------------------------------------------

def _jitter(weights: Dict[str, float], rng: random.Random, amount: float = JITTER) -> Dict[str, float]:
    out = {k: max(v, 0.0) * (1 + rng.uniform(-amount, amount)) for k, v in weights.items()}
    total = sum(out.values()) or 1.0
    return {k: v / total for k, v in out.items()}


def _normalise(w: Dict[str, float]) -> Dict[str, float]:
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}


def _with_floor(weights: Dict[str, float], floor: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Raise each floored key to at least its floor, taking the difference proportionally from the others."""
    w = dict(weights)
    for k, f in (floor or {}).items():
        if w.get(k, 0.0) < f:
            deficit = f - w.get(k, 0.0)
            others = {o: v for o, v in w.items() if o != k}
            pool = sum(others.values())
            for o in others:
                w[o] = max(0.0, w[o] - deficit * (w[o] / pool if pool else 0))
            w[k] = f
    return _normalise(w)


def _counts(n: int, weights: Dict[str, float]) -> Dict[str, int]:
    """Largest-remainder allocation of n items across weights."""
    raw = {k: n * v for k, v in weights.items()}
    base = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)[: n - sum(base.values())]:
        base[k] += 1
    return base


def _group(task, is_surgical: bool):
    _day, _case_type, mech, is_trauma, is_mascal = task[:5]
    if not is_trauma:
        return "dnbi", "_pooled", "dnbi"
    kind = "mascal" if is_mascal else "routine"
    return kind, mech, ("surgical" if is_surgical else "nonsurgical")


def _triage_weights(kind: str, key: str, tier: str, access: float = 1.0) -> Dict[str, float]:
    table = DATA["triage"][kind]
    row = table.get(key) or table["_pooled"]
    w = {t: float(row.get(t, 0.0)) for t in TRIAGE}
    if tier in TIER_MULT:
        w = _normalise({t: w[t] * TIER_MULT[tier][t] for t in TRIAGE})
    floor = dict(TRIAGE_FLOOR.get((kind, tier)) or {})
    if "Expectant" in floor:
        # Where resources and evacuation are scarce, more casualties are triaged expectant.
        floor["Expectant"] *= 1 + 2 * max(0.0, 1.0 - access)
    return _with_floor(w, floor)


def _disposition_weights(group: str, triage: str, tier: str, access: float = 1.0) -> Dict[str, float]:
    row = DATA["disposition"][group][triage]
    w = {d: float(row.get(d, 0.0)) for d in DISPOSITION}
    if tier == "surgical":
        w["RTD"] = 0.0  # a surgical casualty is never returned to duty from Role 2
    w = _normalise(w)
    # Evacuation access scales how many go on to Role 3. When it is scarce (large-scale combat) the rest are held
    # at Role 2 for prolonged care, and the sickest die of wounds; when permissive, fewer need to be held.
    f = access ** ACCESS_EXPONENT
    if f < 1.0:
        moved = w["Evac to Role 3"] * (1.0 - f)
        w["Evac to Role 3"] -= moved
        if triage == "T1":
            w["Hold at Role 2"] += moved * 0.80
            w["Died of Wounds"] += moved * 0.20
        elif triage in ("T2", "T3") and group == "dnbi":
            w["Hold at Role 2"] += moved * 0.70
            w["RTD"] += moved * 0.30 if tier != "surgical" else 0.0
        else:
            w["Hold at Role 2"] += moved
    elif f > 1.0:
        moved = w["Hold at Role 2"] * min(0.5, (f - 1.0))
        w["Hold at Role 2"] -= moved
        w["Evac to Role 3"] += moved
    return _with_floor(_normalise(w), DISPOSITION_FLOOR.get((group, triage)))


# --- the assignment --------------------------------------------------------------------------------

def assign_profiles(tasks: List[tuple], config, surgical_fn: Callable[[str, str, bool], bool],
                    rng: Optional[random.Random] = None) -> List[Dict]:
    """One profile per task: {triage, disposition, population, night, tier}.

    tasks are (day_number, case_type, mechanism, is_trauma, is_mascal). surgical_fn(case_type, mechanism,
    is_mascal) says whether the case needs surgery (it decides the acuity tier)."""
    rng = rng or random.Random()
    n = len(tasks)
    profiles: List[Dict] = [{} for _ in tasks]
    tiers = [_group(t, surgical_fn(t[1], t[2], t[4]))[2] for t in tasks]
    days = {d.day_number: d for d in config.days}
    access = [evac_access(config, days[t[0]]) if t[0] in days else 1.0 for t in tasks]

    # 1. triage, allocated per (kind, key, tier, evacuation access) group with a jittered baseline
    groups: Dict[tuple, List[int]] = {}
    for i, t in enumerate(tasks):
        kind, key, tier = _group(t, tiers[i] == "surgical")
        groups.setdefault((kind, key, tier, access[i]), []).append(i)
    for (kind, key, tier, acc), idx in groups.items():
        w = _jitter(_triage_weights(kind, key, tier, acc), rng)
        labels = [lab for lab, c in _counts(len(idx), w).items() for _ in range(c)]
        rng.shuffle(labels)
        for i, lab in zip(idx, labels):
            profiles[i].update(triage=lab, tier=tier, evac_access=acc)

    # 2. disposition given triage, tier and evacuation access (weights jittered once per combination)
    cache: Dict[tuple, Dict[str, float]] = {}
    for i, t in enumerate(tasks):
        grp = "trauma" if t[3] else "dnbi"
        key = (grp, profiles[i]["triage"], profiles[i]["tier"], access[i])
        if key not in cache:
            cache[key] = _jitter(_disposition_weights(*key), rng)
        w = cache[key]
        profiles[i]["disposition"] = rng.choices(list(w), weights=list(w.values()))[0]

    # 3. patient population, following the care policy
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
                    k = max(1, round(len(cand) * ENEMY_SHARE_DETAINEE_DAY * (1 + rng.uniform(-JITTER, JITTER))))
                    take(cand, min(k, len(cand)), "enemy")
        elif routine:
            take(routine, max(1, round(len(routine) * ENEMY_SHARE_OTHER * (1 + rng.uniform(-JITTER, JITTER)))), "enemy")
    if policy["civilians"]:
        for d, idx in by_day.items():
            daytype = "humanitarian" if getattr(days.get(d), "tactical_setting", "") in HUMANITARIAN else "other"
            share = DATA["population"][daytype]["civilian"] * (1 + rng.uniform(-JITTER, JITTER))
            take(idx, round(len(idx) * share), "civilian")
        if n and "civilian" not in pop:
            take(list(range(n)), 1, "civilian")  # "some", even in a small exercise
    # Partner forces are always eligible; their share comes from the archive.
    for d, idx in by_day.items():
        daytype = "humanitarian" if getattr(days.get(d), "tactical_setting", "") in HUMANITARIAN else "other"
        share = DATA["population"][daytype]["partner"] * (1 + rng.uniform(-JITTER, JITTER))
        take(idx, round(len(idx) * share), "partner")
    # A population the policy does not cover appears only once or twice (emergency stabilization of a walk-in).
    excluded = [lab for lab, on in (("enemy", policy["enemy_combatants"]), ("civilian", policy["civilians"])) if not on]
    if excluded and routine:
        k = rng.choice([1, 2]) if n >= 12 else (1 if n >= 4 else 0)
        for _ in range(k):
            take(routine, 1, rng.choice(excluded))
    for i in range(n):
        profiles[i]["population"] = pop[i]

    # 4. night arrivals: the same share of each Night Ops day's routine patients the scheduler puts in its night wave
    for d, idx in by_day.items():
        if getattr(days.get(d), "night_ops", False):
            cand = [i for i in idx if not tasks[i][4]]
            count = min(max(1, round(getattr(days[d], "total_patients", len(cand)) * NIGHT_SHARE)), len(cand))
            rng.shuffle(cand)
            for i in cand[:count]:
                profiles[i]["night"] = True
    for p in profiles:
        p.setdefault("night", False)
    return profiles


def summarize(profiles: List[Dict]) -> Dict:
    """Counts per triage / disposition / population, for logs and previews."""
    out: Dict[str, Dict[str, int]] = {"triage": {}, "disposition": {}, "population": {}, "night": {}}
    for p in profiles:
        for k, v in (("triage", p["triage"]), ("disposition", p["disposition"]),
                     ("population", p["population"]), ("night", "night" if p["night"] else "day")):
            out[k][v] = out[k].get(v, 0) + 1
    return out
