"""Fixes that came out of the first real-Gemini smoke test: visible template fallbacks, outcome-driven time in Role 2,
severity-aware red-team rules, and skipping the AI review for mild casualties."""
import io
import json
import os
import random
import statistics

os.environ["EXERCISE_BUCKET"] = ""  # tests must never reach AWS

from backend import casemix, main, redteam, scenario  # noqa: E402


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


def schedule_for(config, draw, tasks, prof):
    cases = []
    for t, p in zip(tasks, prof):
        c = main.create_fallback_case(t[1], t[2], t[3])
        main._enforce_profile(c, p)
        cases.append(c)
    pools = {}
    for t, c in zip(tasks, cases):
        pools.setdefault((t[0], t[4]), []).append(c)
    return main.generate_schedule(config, pools, draw)


PROFILE = {"severity": "moderate", "triage": "T2", "disposition": "Hold at Role 2", "population": "civilian", "night": False,
           "evac_access": 0.3}


def test_a_failed_case_says_it_is_a_template_and_why(monkeypatch):
    def broken(*a, **k):
        raise TypeError("the JSON object must be str, bytes or bytearray, not NoneType")
    monkeypatch.setattr(main, "generate_case_sync", broken)
    case = main._generate_one((1, "Penetrating neck trauma", "Frontal Attack", True, False, "critical"), "Urban", "r", None, PROFILE, None)
    assert case["generation"] == "template" and case["generation_error"].startswith("TypeError: the JSON object")

    def google_failure(*a, **k):
        raise main.AIError("billing", "account 12345 details")
    monkeypatch.setattr(main, "generate_case_sync", google_failure)
    case = main._generate_one((1, "x", "y", True, False, "mild"), "Urban", "r", None, PROFILE, None)
    assert case["generation_error"] == "billing" and "12345" not in json.dumps(case)  # Google's text is never stored


def test_the_case_list_flags_template_cases_and_trees(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import archive
    store = {}

    class S3:
        class exceptions:
            class NoSuchKey(Exception):
                pass

        def get_object(self, Bucket, Key):
            if Key not in store:
                raise self.exceptions.NoSuchKey(Key)
            return {"Body": io.BytesIO(store[Key])}

        def put_object(self, Bucket, Key, Body, **kw):
            store[Key] = Body
    monkeypatch.setattr(archive, "BUCKET", "test-bucket")
    monkeypatch.setattr(archive, "_client", S3())
    monkeypatch.setattr(main, "SessionLocal", None)
    cases = [{"zmist": {"zap": "1"}, "generation": "template", "controller": {"quality": {"source": "template"}}},
             {"zmist": {"zap": "2"}, "controller": {"quality": {"source": "ai"}}}]
    archive.put({"id": 9, "name": "t", "created_at": "2026-01-01T00:00:00", "config": {}, "cases": cases, "msel_data": []})
    rows = TestClient(main.app).get("/exercises/9/cases").json()["cases"]
    assert (rows[0]["template"], rows[0]["tree_template"]) == (True, True)
    assert (rows[1]["template"], rows[1]["tree_template"]) == (False, False)


def test_clear_surgical_cases_in_the_pools_are_surgical():
    for case_type in ("GSW right thigh with femoral artery injury", "Multi-system blunt trauma"):
        assert "DCS" in main.determine_case_phases(case_type, "General", False, "severe"), case_type
    assert "Penetrating eye injury" not in main.TRAUMA_TIERS["Indirect Fire/Mortar"]["serious"]
    assert "Penetrating eye injury" in main.TRAUMA_TIERS["Indirect Fire/Mortar"]["moderate"]
    assert main.dnbi_tier("Acute asthma exacerbation") == "moderate"
    assert main.dnbi_tier("Ankle sprain with possible fracture") == "mild"


def test_time_in_role_2_follows_the_outcome():
    draw = casemix.draw_parameters(cfg([day(1, "Frontal Attack")], threat="Peer/Near-Peer"), random.Random(1))
    rng = random.Random(0)
    minutes = {d: [casemix.dwell_minutes(d, 90, 0.3, draw["params"], rng) for _ in range(200)] for d in casemix.DISPOSITION}
    mean = {d: statistics.mean(v) for d, v in minutes.items()}
    assert mean["Hold at Role 2"] > 6 * 60 > mean["RTD"] + 60  # holds run for hours; observation before RTD is short
    assert max(minutes["Hold at Role 2"]) <= 72 * 60  # doctrine ceiling for Role 2 holding
    assert mean["Evac to Role 3"] > 90 + 60  # waiting for a scarce evacuation adds time
    permissive = [casemix.dwell_minutes("Evac to Role 3", 90, 1.0, draw["params"], random.Random(s)) for s in range(50)]
    assert max(permissive) < 90 + 40  # no wait when evacuation is fully permissive


def test_schedule_census_reflects_holds():
    lsco = cfg([day(1, "Frontal Attack"), day(2, "Retrograde Operations")], threat="Peer/Near-Peer")
    permissive = cfg([day(1, "Humanitarian Assistance"), day(2, "Stability Operations")], threat="HADR/Permissive")

    def peak_census(config, seed):
        draw, tasks, prof = run(config, seed)
        schedule, _ = schedule_for(config, draw, tasks, prof)
        main.annotate_pace_states(schedule, config)
        return max(r["r2_census"] for r in schedule if "r2_census" in r)
    assert statistics.mean(peak_census(lsco, s) for s in range(5)) > 1.5 * statistics.mean(peak_census(permissive, s) for s in range(5))


def test_a_casualty_held_overnight_still_counts_the_next_day():
    rows = [{"day": 1, "arr_raw": 1300, "cleared_raw": 1300 + 20 * 60, "triage_cat": "T1"},   # held 20 h, still here on day 2
            {"day": 2, "arr_raw": 6 * 60, "cleared_raw": 7 * 60, "triage_cat": "T2"}]
    config = cfg([day(1), day(2)], threat="Irregular")
    main.annotate_pace_states(rows, config)
    assert rows[1]["r2_census"] == 2


def test_minor_casualties_are_not_forced_to_deteriorate():
    track = lambda hr, sbp, avpu: {"hr": hr, "sbp": sbp, "dbp": 70, "spo2": 98, "avpu": avpu}
    flat = {"vitals_tracks": {"green": [dict(track(90, 120, "A"), t=0), dict(track(80, 122, "A"), t=60)],
                              "red": [dict(track(90, 120, "A"), t=0), dict(track(92, 121, "A"), t=25)]},
            "critical_actions": [{"id": "ca1", "leg_id": "R2"}]}
    sev = lambda level: {f["severity"] for f in redteam.check_vitals(flat, {"severity": level}) if "deteriorate" in f["issue"]}
    assert sev("critical") == {"high"} and sev("severe") == {"high"}
    assert sev("mild") == {"low"} and sev("moderate") == {"low"}  # advisory, so it no longer forces a template


def test_the_ai_review_is_skipped_for_mild_casualties_only(monkeypatch):
    config = cfg([day(1, pts=12)], threat="Irregular")
    draw, tasks, prof = run(config, 4)
    schedule, ordered = schedule_for(config, draw, tasks, prof)
    calls = {"controller": 0, "review": 0, "revise": 0}

    def llm(prompt, system):
        if system is scenario.CONTROLLER_SYSTEM_PROMPT:
            calls["controller"] += 1
            legs = json.loads(prompt.split("CARE CHAIN LEGS (build one tree per leg, same ids):\n")[1].split("\nFOCUS LEG")[0])
            chain = {"nodes": [], "legs": [{"id": l["leg_id"], "title": l["title"], "capability": l["capability"],
                                            "focus": l["focus"], "from": "", "to": ""} for l in legs]}
            ctrl = scenario.fallback_controller({}, chain, prompt.split("PATHWAY: ", 1)[1].split(" ", 1)[0])
            ctrl.pop("_fallback")
            return json.dumps(ctrl)
        if system is redteam.CRITIC_SYSTEM_PROMPT:
            calls["review"] += 1
            return json.dumps({"ok": True})
        calls["revise"] += 1
        return json.dumps({})
    monkeypatch.setattr(main, "_llm_json", llm)
    main._build_controller_layers(config, schedule, ordered, scenario.generate_fragos(config), None, main._Budget(100, 100.0))
    mild = sum(c.get("severity") == "mild" for c in ordered)
    assert mild and calls["controller"] == len(ordered) and calls["review"] == len(ordered) - mild

    monkeypatch.setattr(main, "REVIEW_MILD", True)  # AI_REVIEW_MILD=1 reviews every case
    calls.update(controller=0, review=0, revise=0)
    main._build_controller_layers(config, schedule, ordered, scenario.generate_fragos(config), None, main._Budget(100, 100.0))
    assert calls["review"] == len(ordered)
