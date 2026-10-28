"""Scenario-bounded, per-exercise case mix: envelopes, draws, severity-first assignment, care policy, and wiring."""
import json
import os
import random
import statistics
from types import SimpleNamespace

os.environ["EXERCISE_BUCKET"] = ""  # tests must never reach AWS

from backend import casemix, main, redteam  # noqa: E402


def day(n, setting="Defensive Operations", pts=20, **kw):
    return main.DayConfig(day_number=n, tactical_setting=setting, total_patients=pts, total_waves=2, **kw)


def cfg(days, threat="Hybrid", env="Desert", **kw):
    return main.ExerciseConfig(exercise_name="T", duration=len(days), supported_unit="CLB", environment=env,
                               threat_level=threat, region="Indo-Pacific", selected_mets=[], selected_footprint=["FRSS"],
                               specialists={}, days=days, **kw)


def run(config, seed=0):
    draw = casemix.draw_parameters(config, random.Random(seed))
    tasks = main._build_case_tasks(config, draw)
    return draw, tasks, casemix.assign_profiles(tasks, config, draw)


def mean_share(config, key, value, runs=15):
    shares = []
    for seed in range(runs):
        _, _, prof = run(config, seed)
        shares.append(sum(p[key] == value for p in prof) / len(prof))
    return statistics.mean(shares)


LSCO = cfg([day(1, "Frontal Attack"), day(2, "Retrograde Operations")], threat="Peer/Near-Peer")
PERMISSIVE = cfg([day(1, "Humanitarian Assistance"), day(2, "Stability Operations")], threat="HADR/Permissive")
NEUTRAL = cfg([day(1, "Convoy Operations", pts=30), day(2, "Convoy Operations", pts=30)], threat="Irregular")


# --- bounded by the scenario, different every time -----------------------------------------------------------

def test_every_draw_lies_inside_its_scenario_envelope():
    for config in (LSCO, PERMISSIVE, NEUTRAL):
        for seed in range(40):
            draw = casemix.draw_parameters(config, random.Random(seed))
            for name, value in draw["params"].items():
                lo, mode, hi = draw["envelopes"][name]
                assert lo <= value <= hi and lo <= mode <= hi, (name, lo, value, hi)


def test_no_two_exercises_are_the_same_but_a_draw_reproduces_itself():
    draws = [casemix.draw_parameters(NEUTRAL, random.Random(s)) for s in range(30)]
    assert len({json.dumps(d["params"], sort_keys=True) for d in draws}) == 30
    a, b = run(NEUTRAL, 5), run(NEUTRAL, 5)
    assert a[0] == b[0] and a[1] == b[1] and a[2] == b[2]  # same seed: same draw, same cases, same assignments
    assert run(NEUTRAL, 5)[1] != run(NEUTRAL, 6)[1]


def test_scenario_conditions_move_the_envelopes():
    def env(config, name):
        return casemix.draw_parameters(config, random.Random(0))["envelopes"][name]
    assert env(LSCO, "serious_share.routine")[2] > env(NEUTRAL, "serious_share.routine")[2] > env(PERMISSIVE, "serious_share.routine")[2]
    blast = cfg([day(1, mascal=True, mascal_etiology="IED/Blast", mascal_patients=10)])
    rollover = cfg([day(1, mascal=True, mascal_etiology="Vehicle Rollover", mascal_patients=10)])
    assert env(blast, "serious_share.mascal")[2] > env(rollover, "serious_share.mascal")[2]
    assert env(LSCO, "expectant_given_critical")[2] > env(PERMISSIVE, "expectant_given_critical")[2]
    assert env(PERMISSIVE, "civilian_share")[2] > env(NEUTRAL, "civilian_share")[2]


def test_severity_mix_follows_the_published_role_2_distribution():
    """Kotwal 2018 (9,557 battle-injured at Role 2): ~8% critical, ~11% severe, ~24% moderate, ~55% mild."""
    shares = {s: [] for s in casemix.SEVERITIES}
    for seed in range(30):
        _, _, prof = run(NEUTRAL, seed)
        for s in shares:
            shares[s].append(sum(p["severity"] == s for p in prof) / len(prof))
    mean = {s: statistics.mean(v) for s, v in shares.items()}
    assert 0.04 <= mean["critical"] <= 0.12 and 0.06 <= mean["severe"] <= 0.16
    assert 0.18 <= mean["moderate"] <= 0.32 and 0.45 <= mean["mild"] <= 0.68


def test_high_acuity_switch_raises_the_serious_share_within_bounds():
    high = cfg([day(1, "Convoy Operations", pts=30), day(2, "Convoy Operations", pts=30)], threat="Irregular", casualty_acuity="high")
    base = statistics.mean(sum(p["severity"] in ("critical", "severe") for p in run(NEUTRAL, s)[2]) for s in range(15))
    more = statistics.mean(sum(p["severity"] in ("critical", "severe") for p in run(high, s)[2]) for s in range(15))
    assert more > 1.8 * base
    for seed in range(20):
        draw = casemix.draw_parameters(high, random.Random(seed))
        assert draw["params"]["serious_share.routine"] <= draw["envelopes"]["serious_share.routine"][2] <= 0.95


# --- evacuation access and outcomes -------------------------------------------------------------------------

def test_evac_access_tracks_the_apps_own_threat_scale():
    d = day(1, "Convoy Operations")
    threats = ("HADR/Permissive", "Irregular", "Hybrid", "Peer/Near-Peer")
    scores = [casemix.evac_access(cfg([d], threat=t), d) for t in threats]
    assert scores == sorted(scores, reverse=True) and len(set(scores)) == 4
    mult = [main._threat_evac_mult(t) for t in threats]
    assert mult == sorted(mult)  # the transit-time model orders the threats the same way


def test_lsco_holds_and_loses_casualties_while_permissive_evacuates():
    assert mean_share(LSCO, "disposition", "Evac to Role 3") < 0.15
    assert mean_share(LSCO, "disposition", "Hold at Role 2") > 0.30
    assert mean_share(LSCO, "disposition", "Died of Wounds") > 0.04
    assert mean_share(PERMISSIVE, "disposition", "Evac to Role 3") > 0.35
    assert mean_share(PERMISSIVE, "disposition", "Hold at Role 2") < 0.10
    assert mean_share(PERMISSIVE, "disposition", "Died of Wounds") < 0.06


def test_serious_casualties_are_never_returned_to_duty_and_mild_ones_mostly_are():
    config = cfg([day(1, pts=30, mascal=True, mascal_etiology="GSW/Small Arms", mascal_patients=15)], threat="HADR/Permissive")
    mild_rtd = []
    for seed in range(15):
        _, _, prof = run(config, seed)
        assert all(p["disposition"] != "RTD" for p in prof if p["severity"] in ("critical", "severe"))
        mild = [p for p in prof if p["severity"] == "mild"]
        mild_rtd.append(sum(p["disposition"] == "RTD" for p in mild) / max(len(mild), 1))
    assert statistics.mean(mild_rtd) > 0.5


def test_triage_labels_and_dispositions_are_exact_and_follow_severity():
    for seed in range(10):
        _, _, prof = run(LSCO, seed)
        assert all(p["triage"] in casemix.TRIAGE and p["disposition"] in casemix.DISPOSITION for p in prof)
        assert all(p["triage"] == "T1" or p["triage"] == "Expectant" for p in prof if p["severity"] == "critical")
        assert all(p["triage"] in ("T2", "T3") for p in prof if p["severity"] in ("moderate", "mild"))


# --- case types follow severity ------------------------------------------------------------------------------

def test_case_types_come_from_the_pool_for_their_severity_without_repeats_until_used_up():
    config = cfg([day(1, "Frontal Attack", pts=60)], threat="Irregular")
    _, tasks, _ = run(config, 2)
    tiers = main.GENERAL_TRAUMA_TIERS
    seen = {}
    for t in tasks:
        if not t[3]:
            continue
        tier = "serious" if t[5] in ("critical", "severe") else t[5]
        assert t[1] in tiers[tier]
        seen.setdefault(tier, []).append(t[1])
    for tier, picked in seen.items():
        first = picked[: len(tiers[tier])]
        assert len(set(first)) == len(first)  # no repeat before the whole pool has been used


def test_assigned_mild_and_moderate_casualties_never_get_a_surgery_phase():
    assert main.determine_case_phases("Superficial fragment wounds", "IED/Blast", True, "mild") == ["DCR", "PCC"]
    assert main.determine_case_phases("Fragment wounds to the extremities", "IED/Blast", True, "moderate") == ["DCR", "PCC"]
    assert "DCS" in main.determine_case_phases("Penetrating neck trauma", "IED/Blast", False, "severe")


def test_surgical_classifier_no_longer_loses_the_surgery_phase():
    for case_type in ("Junctional hemorrhage from drone-dropped munition fragments", "Penetrating neck trauma",
                      "TBI with penetrating fragment", "Severe burns with TBI", "Multiple penetrating fragment wounds"):
        assert "DCS" in main.determine_case_phases(case_type, "IED/Blast", False), case_type
    for case_type in ("Penetrating eye injury", "Dengue hemorrhagic fever", "Blast injury with TM rupture",
                      "Traumatic brain injury - moderate", "Burn injury 15% TBSA"):
        assert "DCS" not in main.determine_case_phases(case_type, "IED/Blast", False), case_type


# --- care policy and population -----------------------------------------------------------------------------

def test_care_policy_derives_from_the_days_and_can_be_overridden():
    plain = cfg([day(1)])
    assert casemix.care_policy(plain)["enemy_combatants"] is False and casemix.care_policy(plain)["civilians"] is False
    assert casemix.care_policy(cfg([day(1, detainee_ops=True)]))["enemy_combatants"] is True
    assert casemix.care_policy(cfg([day(1, "Humanitarian Assistance")]))["civilians"] is True
    forced = cfg([day(1)], treat_enemy_combatants=True, treat_civilians=True)
    assert casemix.care_policy(forced)["enemy_combatants"] and casemix.care_policy(forced)["civilians"]
    assert casemix.care_policy(cfg([day(1, detainee_ops=True)], treat_enemy_combatants=False))["enemy_combatants"] is False


def test_policy_text_states_the_same_policy_the_case_mix_uses():
    on = casemix.policy_text({"enemy_combatants": True, "civilians": False})
    assert "Enemy combatants / detainees (EPW): AUTHORIZED" in on
    assert "Host-nation civilians: NOT part of this exercise" in on and "one or two" in on


def test_authorized_populations_appear_and_unauthorized_ones_only_once_or_twice():
    config = cfg([day(1, detainee_ops=True), day(2, "Stability Operations"), day(3)], threat="Irregular")
    for seed in range(15):
        _, tasks, prof = run(config, seed)
        assert sum(p["population"] == "enemy" for p in prof) >= 1 and sum(p["population"] == "civilian" for p in prof) >= 1
        assert [p for p, t in zip(prof, tasks) if t[0] == 1 and p["population"] == "enemy"]  # on the Detainee Ops day
    neither = cfg([day(1), day(2), day(3)], threat="Irregular")
    for seed in range(15):
        stray = sum(p["population"] in ("civilian", "enemy") for p in run(neither, seed)[2])
        assert 1 <= stray <= 2
    only_enemy = cfg([day(1, detainee_ops=True), day(2)], threat="Irregular")
    for seed in range(15):
        assert sum(p["population"] == "civilian" for p in run(only_enemy, seed)[2]) <= 2


def test_civilian_share_stays_inside_the_published_bounds():
    for seed in range(20):
        draw, tasks, prof = run(cfg([day(1, pts=40), day(2, pts=40)], threat="Irregular", treat_civilians=True), seed)
        share = sum(p["population"] == "civilian" for p in prof) / len(prof)
        assert share <= draw["envelopes"]["civilian_share"][2] + 0.03  # rounding on small groups


def test_tiny_exercises_do_not_overflow_the_exception_rule():
    assert sum(p["population"] in ("civilian", "enemy") for p in run(cfg([day(1, pts=4)]), 1)[2]) <= 1


def test_night_cases_match_the_schedulers_night_wave_share():
    config = cfg([day(1, pts=20, night_ops=True), day(2, pts=20)])
    for seed in range(5):
        _, tasks, prof = run(config, seed)
        night = [(t, p) for t, p in zip(tasks, prof) if p["night"]]
        assert len(night) == round(20 * casemix.NIGHT_SHARE) and all(t[0] == 1 and not t[4] for t, _ in night)


# --- generator wiring -----------------------------------------------------------------------------------

PROFILE = {"severity": "moderate", "triage": "T2", "disposition": "Hold at Role 2", "population": "civilian", "night": True,
           "evac_access": 0.3}


def test_assigned_profile_is_in_the_prompt_and_enforced_on_the_case(monkeypatch):
    seen = {}

    def fake_model(prompt, kind, system=None, json_mode=False):
        seen["prompt"] = prompt
        return SimpleNamespace(text=json.dumps({"zmist": {"zap": "0"}, "triage_category": "T1 Immediate", "disposition": "RTD"}))
    monkeypatch.setattr(main, "_call_model", fake_model)
    case = main.generate_case_sync("Blast injury with TM rupture", "IED/Blast", "Desert", "CENTCOM", True, None,
                                   PROFILE, {"setting": "Defensive Operations", "threat": "Peer/Near-Peer"})
    p = seen["prompt"]
    assert "ASSIGNED SEVERITY: moderate" in p and "ASSIGNED TRIAGE: T2" in p and "ASSIGNED DISPOSITION: Hold at Role 2" in p
    assert "host-nation civilian" in p and "Peer/Near-Peer" in p and "ARRIVAL: at night" in p and "largely denied" in p
    assert "does NOT require surgery" in p and "no resuscitation is needed" in p  # moderate, even in a MASCAL wave
    assert case["triage_category"] == "T2" and case["disposition"] == "Hold at Role 2"  # the model's values are overridden
    assert case["patient_population"] == "civilian" and case["arrival_window"] == "night" and case["severity"] == "moderate"


def test_fallback_cases_honour_the_assignment_too(monkeypatch):
    def boom(*a, **k):
        raise main.AIError("billing")
    monkeypatch.setattr(main, "generate_case_sync", boom)
    case = main._generate_one((1, "Blast injury", "IED/Blast", True, False, "moderate"), "Desert", "CENTCOM", None, PROFILE, None)
    assert case["triage_category"] == "T2" and case["_fallback"] == "billing"


def test_medroe_prompt_carries_the_care_policy(monkeypatch):
    seen = {}
    monkeypatch.setattr(main, "_call_model", lambda prompt, kind, **k: seen.update(prompt=prompt) or SimpleNamespace(text="x"))
    main.generate_medroe(cfg([day(1, detainee_ops=True)]))
    assert "ELIGIBILITY POLICY" in seen["prompt"]
    assert "Enemy combatants / detainees (EPW): AUTHORIZED" in seen["prompt"]
    assert "Host-nation civilians: NOT part of this exercise" in seen["prompt"]


def test_night_cases_fill_the_night_wave_in_the_schedule():
    config = cfg([day(1, pts=20, night_ops=True)])
    _, tasks, prof = run(config, 3)
    cases = []
    for t, p in zip(tasks, prof):
        c = main.create_fallback_case(t[1], t[2], t[3])
        main._enforce_profile(c, p)
        cases.append(c)
    pools = {}
    for t, c in zip(tasks, cases):
        pools.setdefault((t[0], t[4]), []).append(c)
    schedule, ordered = main.generate_schedule(config, pools)
    rows = [r for r in schedule if str(r.get("case_num", "")).startswith("Case ")]
    assert len(rows) == 20 and sum(c.get("arrival_window") == "night" for c in ordered) == 7
    for r in rows:
        case, hour = ordered[int(r["case_num"].split()[1]) - 1], int(str(r["time"])[:2])
        assert (case.get("arrival_window") == "night") == (hour >= 20 or hour <= 2), (r["time"], case.get("arrival_window"))


def test_the_draw_is_saved_with_the_exercise(monkeypatch):
    saved = {}
    monkeypatch.setattr(main, "SessionLocal", None)
    monkeypatch.setattr(main.archive, "BUCKET", "test-bucket")
    monkeypatch.setattr(main.archive, "save", lambda **kw: saved.update(kw) or 1)

    def model(prompt, kind, system=None, json_mode=False):
        if kind == "orders":
            return SimpleNamespace(text="Order text.")
        raise main.AIError("billing")  # every case and controller falls back to its template
    monkeypatch.setattr(main, "_call_model", model)
    config = cfg([day(1, pts=4)], threat="HADR/Permissive")
    main._job_create("job-draw")
    main._run_generation(config, "job-draw")
    assert main._jobs["job-draw"]["status"] == "complete", main._jobs["job-draw"]
    mix = saved["config"]["case_mix"]
    assert mix["version"] == 2 and mix["seed"] and set(mix["params"]) == set(casemix.PARAMS)
    assert all(lo <= mix["params"][n] <= hi for n, (lo, _m, hi) in mix["envelopes"].items())
    assert "billing" in main._jobs["job-draw"]["progress"].lower() or "credit" in main._jobs["job-draw"]["progress"].lower()


# --- vitals anchor and cached-token metering ------------------------------------------------------------

def _ctrl(hr, sbp, spo2):
    return {"vitals_tracks": {"green": [{"t": 0, "hr": hr, "sbp": sbp, "spo2": spo2}], "red": []}}


CASE = {"phases": {"dcr": {"vitals_trend": [{"time": "0", "hr": "120", "bp": "90/50", "spo2": "94%"}]}}}


def test_green_track_must_start_at_the_case_arrival_vitals():
    assert redteam.check_arrival_vitals(_ctrl(122, 92, 95), CASE) == []
    found = redteam.check_arrival_vitals(_ctrl(80, 130, 99), CASE)
    assert len(found) == 1 and found[0]["severity"] == "low" and "hr case 120" in found[0]["issue"]
    assert redteam.check_arrival_vitals(_ctrl(80, 130, 99), {"phases": {}}) == []  # no case vitals: nothing to compare


def test_cached_prompt_tokens_are_recorded(monkeypatch):
    usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=50, thoughts_token_count=0,
                            cached_content_token_count=700)
    response = SimpleNamespace(text="OK", candidates=[], prompt_feedback=None, usage_metadata=usage)
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **k: response))
    monkeypatch.setattr(main, "get_client", lambda: client)
    budget = main._Budget(max_calls=10, max_usd=1.0)
    main._tl.budget = budget
    try:
        main._call_model("hi", "case")
    finally:
        main._tl.budget = None
    assert budget.summary()["cached_tokens"] == 700 and budget.summary()["input_tokens"] == 1000
