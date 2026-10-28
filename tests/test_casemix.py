"""Scenario-conditioned case mix: care policy, evacuation access, assignment, and the generator wiring."""
import json
import os
import random
import statistics
from types import SimpleNamespace

os.environ["EXERCISE_BUCKET"] = ""  # tests must never reach AWS

import pytest  # noqa: E402

from backend import casemix, main, redteam  # noqa: E402


def day(n, setting="Defensive Operations", pts=20, **kw):
    return main.DayConfig(day_number=n, tactical_setting=setting, total_patients=pts, total_waves=2, **kw)


def cfg(days, threat="Hybrid", env="Desert", **kw):
    return main.ExerciseConfig(exercise_name="T", duration=len(days), supported_unit="CLB", environment=env,
                               threat_level=threat, region="Indo-Pacific", selected_mets=[], selected_footprint=["FRSS"],
                               specialists={}, days=days, **kw)


def surgical(case_type, mechanism, is_mascal):
    return "DCS" in main.determine_case_phases(case_type, mechanism, is_mascal)


def run(config, seed=0):
    tasks = main._build_case_tasks(config)
    return tasks, casemix.assign_profiles(tasks, config, surgical, random.Random(seed))


def mean_share(config, key, value, runs=15):
    shares = []
    for seed in range(runs):
        _, prof = run(config, seed)
        shares.append(sum(p[key] == value for p in prof) / len(prof))
    return statistics.mean(shares)


# --- evacuation access --------------------------------------------------------------------------------

def test_evac_access_tracks_the_apps_own_threat_scale():
    d = day(1, "Convoy Operations")
    scores = [casemix.evac_access(cfg([d], threat=t), d) for t in ("HADR/Permissive", "Irregular", "Hybrid", "Peer/Near-Peer")]
    assert scores == sorted(scores, reverse=True) and len(set(scores)) == 4
    # same ordering as the multiplier that lengthens transit times in main
    mult = [main._threat_evac_mult(t) for t in ("HADR/Permissive", "Irregular", "Hybrid", "Peer/Near-Peer")]
    assert mult == sorted(mult)


def test_lsco_holds_and_loses_casualties_while_permissive_evacuates():
    lsco = cfg([day(1, "Frontal Attack"), day(2, "Retrograde Operations")], threat="Peer/Near-Peer")
    permissive = cfg([day(1, "Humanitarian Assistance"), day(2, "Stability Operations")], threat="HADR/Permissive")
    assert mean_share(lsco, "disposition", "Evac to Role 3") < 0.25
    assert mean_share(lsco, "disposition", "Hold at Role 2") > 0.50
    assert mean_share(lsco, "disposition", "Died of Wounds") > 0.04
    assert mean_share(permissive, "disposition", "Evac to Role 3") > 0.75
    assert mean_share(permissive, "disposition", "Died of Wounds") < 0.04


def test_surgical_cases_are_never_returned_to_duty():
    for threat in ("HADR/Permissive", "Peer/Near-Peer"):
        config = cfg([day(1, pts=30, mascal=True, mascal_etiology="GSW/Small Arms", mascal_patients=15)], threat=threat)
        for seed in range(10):
            _, prof = run(config, seed)
            assert all(p["disposition"] != "RTD" for p in prof if p["tier"] == "surgical")


# --- care policy and population -----------------------------------------------------------------------

def test_care_policy_derives_from_the_days_and_can_be_overridden():
    plain = cfg([day(1)])
    assert casemix.care_policy(plain)["enemy_combatants"] is False and casemix.care_policy(plain)["civilians"] is False
    assert casemix.care_policy(cfg([day(1, detainee_ops=True)]))["enemy_combatants"] is True
    assert casemix.care_policy(cfg([day(1, "Humanitarian Assistance")]))["civilians"] is True
    forced = cfg([day(1)], treat_enemy_combatants=True, treat_civilians=True)
    assert casemix.care_policy(forced)["enemy_combatants"] and casemix.care_policy(forced)["civilians"]
    off = cfg([day(1, detainee_ops=True)], treat_enemy_combatants=False)
    assert casemix.care_policy(off)["enemy_combatants"] is False


def test_policy_text_states_the_same_policy_the_case_mix_uses():
    on = casemix.policy_text({"enemy_combatants": True, "civilians": False})
    assert "Enemy combatants / detainees (EPW): AUTHORIZED" in on
    assert "Host-nation civilians: NOT part of this exercise" in on and "one or two" in on


def test_authorized_populations_appear_and_unauthorized_ones_only_once_or_twice():
    config = cfg([day(1, detainee_ops=True), day(2, "Stability Operations"), day(3)], threat="Irregular")
    for seed in range(15):
        tasks, prof = run(config, seed)
        enemies = sum(p["population"] == "enemy" for p in prof)
        civilians = sum(p["population"] == "civilian" for p in prof)
        assert enemies >= 1 and civilians >= 1  # both authorized: "some"
        det_day = [p for p, t in zip(prof, tasks) if t[0] == 1 and p["population"] == "enemy"]
        assert det_day  # enemy cases sit on the Detainee Ops day
    neither = cfg([day(1), day(2), day(3)], threat="Irregular")
    for seed in range(15):
        _, prof = run(neither, seed)
        stray = sum(p["population"] in ("civilian", "enemy") for p in prof)
        assert 1 <= stray <= 2
    only_enemy = cfg([day(1, detainee_ops=True), day(2)], threat="Irregular")
    for seed in range(15):
        _, prof = run(only_enemy, seed)
        assert sum(p["population"] == "civilian" for p in prof) <= 2


def test_tiny_exercises_do_not_overflow_the_exception_rule():
    _, prof = run(cfg([day(1, pts=4)]), 1)
    assert sum(p["population"] in ("civilian", "enemy") for p in prof) <= 1


# --- the rest of the assignment -------------------------------------------------------------------------

def test_labels_are_exact_and_mixes_vary_between_exercises():
    config = cfg([day(1, pts=25), day(2, pts=25, mascal=True, mascal_etiology="IED/Blast", mascal_patients=12)])
    seen = set()
    for seed in range(12):
        _, prof = run(config, seed)
        assert all(p["triage"] in casemix.TRIAGE and p["disposition"] in casemix.DISPOSITION for p in prof)
        seen.add(json.dumps(casemix.summarize(prof), sort_keys=True))
    assert len(seen) > 6  # the small random variation really does vary the mix


def test_night_cases_match_the_schedulers_night_wave_share():
    config = cfg([day(1, pts=20, night_ops=True), day(2, pts=20)])
    for seed in range(5):
        tasks, prof = run(config, seed)
        night = [(t, p) for t, p in zip(tasks, prof) if p["night"]]
        assert len(night) == round(20 * casemix.NIGHT_SHARE) and all(t[0] == 1 and not t[4] for t, _ in night)


def test_case_types_do_not_repeat_until_the_list_is_used_up():
    deck = main._Deck(["a", "b", "c", "d"])
    first_pass = [deck.draw() for _ in range(4)]
    assert sorted(first_pass) == ["a", "b", "c", "d"]
    tasks = main._build_case_tasks(cfg([day(1, "Frontal Attack", pts=40)]))
    trauma = [t[1] for t in tasks if t[3]]
    assert len(trauma) == 34 and len(set(trauma[:10])) == 10  # GENERAL_TRAUMA has 10 entries


# --- generator wiring -----------------------------------------------------------------------------------

def test_surgical_classifier_no_longer_loses_the_surgery_phase():
    for case_type in ("Junctional hemorrhage from drone-dropped munition fragments", "Penetrating neck trauma",
                      "TBI with penetrating fragment", "Severe burns with TBI", "Multiple penetrating fragment wounds"):
        assert "DCS" in main.determine_case_phases(case_type, "IED/Blast", False), case_type
    for case_type in ("Penetrating eye injury", "Dengue hemorrhagic fever", "Blast injury with TM rupture",
                      "Traumatic brain injury - moderate", "Burn injury 15% TBSA"):
        assert "DCS" not in main.determine_case_phases(case_type, "IED/Blast", False), case_type


PROFILE = {"triage": "T2", "disposition": "Hold at Role 2", "population": "civilian", "night": True, "tier": "nonsurgical",
           "evac_access": 0.3}


def test_assigned_profile_is_in_the_prompt_and_enforced_on_the_case(monkeypatch):
    seen = {}

    def fake_model(prompt, kind, system=None, json_mode=False):
        seen["prompt"] = prompt
        return SimpleNamespace(text=json.dumps({"zmist": {"zap": "0"}, "triage_category": "T1 Immediate", "disposition": "RTD"}))
    monkeypatch.setattr(main, "_call_model", fake_model)
    case = main.generate_case_sync("Blast injury with TM rupture", "IED/Blast", "Desert", "CENTCOM", False, None,
                                   PROFILE, {"setting": "Defensive Operations", "threat": "Peer/Near-Peer"})
    p = seen["prompt"]
    assert 'ASSIGNED TRIAGE: T2' in p and 'ASSIGNED DISPOSITION: Hold at Role 2' in p
    assert "host-nation civilian" in p and "Peer/Near-Peer" in p and "ARRIVAL: at night" in p
    assert "largely denied" in p  # access 0.3
    assert case["triage_category"] == "T2" and case["disposition"] == "Hold at Role 2"  # the model's values are overridden
    assert case["patient_population"] == "civilian" and case["arrival_window"] == "night"


def test_fallback_cases_honour_the_assignment_too(monkeypatch):
    def boom(*a, **k):
        raise main.AIError("billing")
    monkeypatch.setattr(main, "generate_case_sync", boom)
    case = main._generate_one((1, "Blast injury", "IED/Blast", True, False), "Desert", "CENTCOM", None, PROFILE, None)
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
    tasks, prof = run(config, 3)
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
        is_night_slot = hour >= 20 or hour <= 2
        assert (case.get("arrival_window") == "night") == is_night_slot, (r["time"], case.get("arrival_window"))


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
