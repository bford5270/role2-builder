"""Planning requirements flow into the orders, cases and trees; the schedule tracks the cases; malformed JSON is repaired."""
import json
import os
import random
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["EXERCISE_BUCKET"] = ""  # tests must never reach AWS

import pytest  # noqa: E402

from backend import casemix, jsonfix, main, scenario  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_exercise  # noqa: E402


def day(n, setting="Defensive Operations", pts=20, **kw):
    return main.DayConfig(day_number=n, tactical_setting=setting, total_patients=pts, total_waves=2, **kw)


def cfg(days, threat="Hybrid", env="Desert", **kw):
    return main.ExerciseConfig(exercise_name="T", duration=len(days), supported_unit="CLB", environment=env,
                               threat_level=threat, region="Indo-Pacific", selected_mets=[], selected_footprint=["FRSS"],
                               specialists={}, days=days, **kw)


def build(config, seed=0):
    draw = casemix.draw_parameters(config, random.Random(seed))
    tasks = main._build_case_tasks(config, draw)
    prof = casemix.assign_profiles(tasks, config, draw)
    cases = []
    for t, p in zip(tasks, prof):
        c = main.create_fallback_case(t[1], t[2], t[3])
        main._enforce_profile(c, p)
        cases.append(c)
    pools = {}
    for t, c in zip(tasks, cases):
        pools.setdefault((t[0], t[4]), []).append(c)
    schedule, ordered = main.generate_schedule(config, pools, draw)
    return draw, schedule, ordered


# --- malformed JSON ------------------------------------------------------------------------------------------

def test_a_missing_comma_and_a_truncated_ending_are_repaired():
    assert jsonfix.loads_lenient('{"a": 1, "b": {"c": [1, 2]}}') == {"a": 1, "b": {"c": [1, 2]}}
    assert jsonfix.loads_lenient('{"a": "x"\n  "b": 2}') == {"a": "x", "b": 2}  # the failure seen live: Expecting ',' delimiter
    assert jsonfix.loads_lenient('{"a": [1, 2], "b": {"c": "cut off here') == {"a": [1, 2], "b": {"c": "cut off here"}}
    assert jsonfix.loads_lenient('Sure! {"a": 1} hope that helps') == {"a": 1}
    for bad in (None, "", "no json here"):
        with pytest.raises(ValueError):
            jsonfix.loads_lenient(bad)


def test_a_case_that_comes_back_broken_twice_is_retried_once_then_given_up(monkeypatch):
    texts = iter(['{"zmist": {"zap": "0"}, "triage_category": ', '{"zmist": {"zap": "0"}, "x": 1}'])
    calls = []
    monkeypatch.setattr(main, "_call_model", lambda *a, **k: calls.append(1) or SimpleNamespace(text=next(texts)))
    case = main.generate_case_sync("Laceration requiring repair", "Frontal Attack", "Urban", "r")
    assert len(calls) == 2 and case["x"] == 1  # the retry succeeded

    calls.clear()
    monkeypatch.setattr(main, "_call_model", lambda *a, **k: calls.append(1) or SimpleNamespace(text="not json at all"))
    with pytest.raises(ValueError):
        main.generate_case_sync("Laceration requiring repair", "Frontal Attack", "Urban", "r")
    assert len(calls) == 2  # never more than one retry


# --- blood follows severity -------------------------------------------------------------------------------------

def blood(sev, text="", dcs=False, triage="T2"):
    case = {"severity": sev, "triage_category": triage, "zmist": {"injuries": text, "mechanism": "", "treatment": ""},
            "phases": {"dcr": {}, "dcs": {} if dcs else None}}
    return main._blood_units(case)


def test_blood_follows_severity_and_ignores_negations():
    assert blood("mild", "contusions, no active hemorrhage, bilateral arms") == 0   # the live bug: 24 units for a contusion
    assert blood("mild", "gunshot wound graze") == 0
    assert blood("moderate", "closed fracture, no hemorrhage") == 0
    assert blood("moderate", "pelvic fracture with hemorrhage") == main._BLOOD_WBE["submassive"]
    assert blood("severe", "penetrating abdominal trauma", dcs=True) == main._BLOOD_WBE["massive"]
    assert blood("critical", "bilateral traumatic amputation", dcs=True, triage="T1") == main._BLOOD_WBE["ultramassive"]
    assert blood("critical", "bilateral hand burns, stable") == main._BLOOD_WBE["massive"]  # "bilateral" alone is not ultramassive
    assert blood(None, "gunshot wound abdomen", triage="T1") >= main._BLOOD_WBE["massive"]  # older cases without a severity


# --- schedule timing ------------------------------------------------------------------------------------------

def test_walk_ins_have_no_evacuation_leg_and_the_detainee_inject_is_a_real_case():
    config = cfg([day(1, pts=20, detainee_ops=True, night_ops=True)], threat="Peer/Near-Peer")
    for seed in range(4):
        draw, schedule, ordered = build(config, seed)
        for r in (r for r in schedule if "arr_raw" in r):
            if str(r.get("route", "")).lower().startswith("walk"):
                assert r["arr_raw"] - r["arr_raw"] + int(r["transit_min"]) <= 10
        inject = next(r for r in schedule if r.get("event") == "INJECT")
        enemy = [r for r in schedule if str(r.get("case_num", "")).startswith("Case ")
                 and ordered[int(r["case_num"].split()[1]) - 1].get("patient_population") == "enemy"]
        assert enemy and inject["time"] == enemy[0]["time"] and "(Case " in inject["brief_description"]


def test_the_audit_finds_nothing_high_in_a_generated_schedule():
    config = cfg([day(1, "Frontal Attack", pts=20, detainee_ops=True, night_ops=True),
                  day(2, "Retrograde Operations", pts=20, cbrn=True, mascal=True, mascal_etiology="IED/Blast", mascal_patients=10),
                  day(3, "Stability Operations", pts=16)], threat="Peer/Near-Peer")
    for seed in range(5):
        draw, schedule, ordered = build(config, seed)
        findings = audit_exercise.audit_schedule(json.loads(config.json()), ordered, schedule, scenario.generate_fragos(config))
        high = [f for f in findings if f[0] == "high"]
        assert not high, high


# --- one set of planning numbers for every document, case and tree ------------------------------------------

def test_the_three_orders_state_the_same_planning_factors_and_the_schedule_load(monkeypatch):
    prompts = {}

    def capture(name):
        def fn(prompt, kind, **k):
            prompts[name] = prompt
            return SimpleNamespace(text="x")
        return fn
    config = cfg([day(1, detainee_ops=True)], threat="Peer/Near-Peer", env="Urban")
    facts = main._facts_text(main._planning_facts(config))
    assert "Urgent 90 min, Priority 180 min, Routine 360 min" in facts and "72 hours" in facts and "30 units LTOWB" in facts
    for name, fn in (("warno", main.generate_warno), ("annex", main.generate_annex_q), ("medroe", main.generate_medroe)):
        monkeypatch.setattr(main, "_call_model", capture(name))
        fn(config, None, "LOAD-MARKER") if name != "medroe" else fn(config, "LOAD-MARKER")
        assert facts in prompts[name] and "LOAD-MARKER" in prompts[name], name


def test_the_schedule_load_states_what_the_schedule_actually_carries():
    config = cfg([day(1, "Frontal Attack", pts=20, night_ops=True)], threat="Peer/Near-Peer")
    draw, schedule, ordered = build(config, 2)
    text = main._schedule_facts(schedule, ordered, config)
    assert f"{len([r for r in schedule if 'arr_raw' in r])} casualties" in text and "Peak Role 2 census" in text
    assert "Night arrivals: 7" in text and "Whole blood" in text and "planning capacity" in text


PROFILE = {"severity": "critical", "triage": "T1", "disposition": "Hold at Role 2", "population": "us", "night": False,
          "evac_access": 0.3}


def test_each_case_is_told_the_provisions_that_bear_on_it():
    facts = main._planning_facts(cfg([day(1)], threat="Peer/Near-Peer", env="Urban"))
    prompt = lambda **over: main._orders_prompt(dict(PROFILE, **over), facts)
    p = prompt()
    assert "Holding limit 72 h" in p and "30 units of LTOWB" in p and "walking blood bank" in p
    assert "expectant policy" in prompt(triage="Expectant", disposition="Expectant")
    assert "died-of-wounds procedures" in prompt(disposition="Died of Wounds")
    evac = prompt(disposition="Evac to Role 3")
    assert "Urgent 90 min" in evac and "Holding limit" not in evac
    quiet = prompt(severity="mild", triage="T3", disposition="RTD")
    assert "ORDERS IN FORCE" in quiet and "LTOWB" not in quiet and "Holding limit" not in quiet
    assert main._orders_prompt(PROFILE, None) == ""  # no facts, no block


def test_the_decision_tree_prompt_carries_the_situation_at_arrival():
    config = cfg([day(1, pts=12)], threat="Peer/Near-Peer")
    draw, schedule, ordered = build(config, 1)
    row = next(r for r in schedule if "arr_raw" in r)
    situation = main._situation_text(row, config)
    assert "SITUATION AT ARRIVAL: Role 2 census" in situation and "whole blood on hand" in situation and "72 h" in situation
    chain = scenario.chain_for(config, config.days[0], 600, [], 180)
    assert situation in scenario.controller_prompt(ordered[0], chain, "DCR_HOLD", [], False, situation)
    assert "SITUATION AT ARRIVAL" in scenario.CONTROLLER_SYSTEM_PROMPT


def test_the_case_prompt_reaches_the_model_with_the_orders_block(monkeypatch):
    seen = {}
    monkeypatch.setattr(main, "_call_model", lambda prompt, kind, **k: seen.update(prompt=prompt) or SimpleNamespace(
        text=json.dumps({"zmist": {"zap": "0"}})))
    ctx = {"setting": "Frontal Attack", "threat": "Peer/Near-Peer", "facts": main._planning_facts(cfg([day(1)], threat="Peer/Near-Peer", env="Urban"))}
    main.generate_case_sync("Penetrating neck trauma", "Frontal Attack", "Urban", "r", False, None, PROFILE, ctx)
    assert "ORDERS IN FORCE" in seen["prompt"] and "Holding limit 72 h" in seen["prompt"] and "ASSIGNED SEVERITY: critical" in seen["prompt"]


def test_a_t1_casualty_is_always_called_in_as_urgent():
    for evac in ({"priority": "Priority"}, {}, None, "garbage"):
        case = {"evacuation": evac}
        main._enforce_profile(case, dict(PROFILE, triage="T1"))
        assert case["evacuation"]["priority"] == "Urgent"
    case = {"evacuation": {"priority": "Priority"}}
    main._enforce_profile(case, dict(PROFILE, triage="T2", severity="moderate"))
    assert case["evacuation"]["priority"] == "Priority"  # only T1 is forced
