"""End-to-end package build with the model stubbed out: fallback base cases,
a fake controller-layer LLM, and the red team — asserts every deliverable is
produced and the care chain follows the FRAGOs."""
import io
import json
import zipfile

import pytest

from backend import main, redteam, scenario


def _config(**over):
    days = [
        {"day_number": 1, "tactical_setting": "Amphibious Assault", "total_patients": 4, "total_waves": 2,
         "mascal": True, "mascal_etiology": "Indirect Fire/Mortar", "mascal_patients": 3, "night_ops": True},
        {"day_number": 2, "tactical_setting": "Retrograde Operations", "total_patients": 3, "total_waves": 1,
         "cbrn": True},
    ]
    cfg = dict(exercise_name="Operation Test", duration=2, supported_unit="Regiment", environment="Littoral",
               threat_level="Peer/Near-Peer", region="Indo-Pacific", selected_mets=["MET 2"],
               selected_footprint=["STP", "FRSS", "Holding", "COC"],
               specialists={"General Surgery": 1, "Emergency Medicine": 1, "ER Nurse": 2}, days=days)
    cfg.update(over)
    return main.ExerciseConfig(**cfg)


CALLS = {"controller": 0, "review": 0, "revise": 0}


def _fake_llm(prompt, system):
    if system is scenario.CONTROLLER_SYSTEM_PROMPT:
        CALLS["controller"] += 1
        # Return a structurally complete layer (reuse the template) with one planted error.
        legs = json.loads(prompt.split("CARE CHAIN LEGS (build one tree per leg, same ids):\n")[1].split("\nFOCUS LEG")[0])
        chain = {"nodes": [], "legs": [{"id": l["leg_id"], "title": l["title"], "capability": l["capability"],
                                        "focus": l["focus"], "from": "", "to": ""} for l in legs]}
        pathway = prompt.split("PATHWAY: ", 1)[1].split(" ", 1)[0]
        ctrl = scenario.fallback_controller({}, chain, pathway)
        ctrl.pop("_fallback")
        ctrl["moulage"] = "Alert, GCS 14 (E4, V5, M6)"  # planted: 4+5+6=15
        return json.dumps(ctrl)
    if system is redteam.CRITIC_SYSTEM_PROMPT:
        CALLS["review"] += 1
        # The review sees the rules finding and returns a minimal patch fixing it.
        assert "GCS" in prompt.split("RULES FINDINGS TO FIX:\n", 1)[1].split("CONTROLLER LAYER")[0]
        return json.dumps({"ok": False, "findings": [{"category": "gcs", "location": "moulage", "issue": "sum"}],
                           "patch": {"moulage": "Alert, GCS 15 (E4, V5, M6)"}})
    CALLS["revise"] += 1
    raise AssertionError("revision should not be needed when the review fixes everything")


def test_chain_follows_fragos():
    cfg = _config()
    fr = scenario.generate_fragos(cfg)
    titles = {(f["day"], f["title"]) for f in fr}
    assert (1, "Surgical capability phases ashore") in titles
    assert (2, "FRSS displaces (jump)") in titles
    assert (1, "MEDEVAC corridor denied") in titles
    d1, d2 = cfg.days
    tp = main._transit_min("Priority", cfg)
    assert scenario.chain_for(cfg, d1, 9 * 60, fr, tp)["nodes"][2]["name"] == "ERSS (afloat)"
    after = scenario.chain_for(cfg, d1, 14 * 60, fr, tp)
    assert after["nodes"][2]["name"] == "FRSS (ashore)"
    assert any(n["name"] == "Holding (PCC)" for n in after["nodes"])  # corridor denied 1200-1800
    jump = scenario.chain_for(cfg, d2, 11 * 60, fr, tp)
    r2 = next(n for n in jump["nodes"] if n.get("role2"))
    assert r2["capability"] == ["DCR"]
    assert any(n["id"] == "DECON" for n in jump["nodes"])  # CBRN window 0800-1200


def test_pathway_respects_capability():
    cfg = _config()
    fr = scenario.generate_fragos(cfg)
    tp = main._transit_min("Priority", cfg)
    surgical = {"phases": {"dcs": {}}, "triage_category": "T1", "disposition": "Evac to Role 3"}
    assert scenario.determine_pathway(surgical, scenario.chain_for(cfg, cfg.days[0], 9 * 60, fr, tp)) == "DCR_DCS"
    assert scenario.determine_pathway(surgical, scenario.chain_for(cfg, cfg.days[1], 11 * 60, fr, tp)) == "DCR_DEFERRED_DCS"
    hemorrhage = {"phases": {"dcs": None}, "triage_category": "T2", "disposition": "Evac to Role 3",
                  "zmist": {"mechanism": "IED/Blast"}}
    assert scenario.determine_pathway(hemorrhage, scenario.chain_for(cfg, cfg.days[1], 9 * 60, fr, tp)) == "DCR_HOLD"


@pytest.mark.parametrize("ai", [True, False])
def test_full_package(monkeypatch, ai):
    monkeypatch.setattr(main, "generate_case_sync", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(main, "generate_warno", lambda c, f=None: "WARNO text")
    monkeypatch.setattr(main, "generate_annex_q", lambda c, f=None: "Annex text")
    monkeypatch.setattr(main, "generate_medroe", lambda c: "MEDROE text")
    monkeypatch.setattr(main, "generate_road_to_war_prompt", lambda c, a="": "RTW text")
    for k in CALLS:
        CALLS[k] = 0
    if ai:
        monkeypatch.setattr(main, "_llm_json", _fake_llm)
    else:
        monkeypatch.setattr(main, "_llm_json", lambda p, s: (_ for _ in ()).throw(RuntimeError("no key")))
    monkeypatch.setattr(main, "SessionLocal", None)
    cfg = _config()
    main._job_create("t")
    main._run_generation(cfg, "t")
    job = main._jobs["t"]
    assert job["status"] == "complete", job
    z = zipfile.ZipFile(io.BytesIO(main._packages[job["token"]]["data"]))
    names = z.namelist()
    for suffix in ("_FRAGOs.docx", "_Controller_Packet.docx", "_Controller_Vitals.xlsx", "_cases.json", "_MSEL.xlsx"):
        assert any(n.endswith(suffix) for n in names), suffix
    export = json.loads(z.read("Operation Test_cases.json"))
    assert export["format"] == "role2builder.cases.v1"
    assert len(export["cases"]) == 10
    for c in export["cases"]:
        ctrl = c["case"]["controller"]
        assert ctrl["legs"] and ctrl["vitals_tracks"]["green"]
        assert "red_team" not in ctrl and "_fallback" not in ctrl  # final draft: no findings shipped
        assert not redteam._blocking(redteam.run_rules(ctrl, c["case"]))
        if ai:
            assert ctrl["quality"]["source"] == "ai"
            assert ctrl["moulage"] == "Alert, GCS 15 (E4, V5, M6)"  # planted error fixed, not reported
        else:
            assert ctrl["quality"]["source"] == "template"
    if ai:  # cost: exactly one generation + one review per layer, no rework loop
        assert CALLS == {"controller": 10, "review": 10, "revise": 0}


def test_unfixable_layer_falls_back_to_template_after_two_calls():
    import json as _json
    fix = _json.loads((__import__("pathlib").Path(__file__).parent / "fixtures" / "erss_ship_sim_dcs.json").read_text())
    broken, case = fix["controller"], fix["case"]
    calls = {"review": 0, "revise": 0}

    def review(c, f):
        calls["review"] += 1
        return c

    def revise(c, f):
        calls["revise"] += 1
        return c

    template = lambda: scenario.fallback_controller(case, broken["chain"], "DCR_DCS")
    out = redteam.finalize(broken, case, review=review, revise=revise, fallback=template)
    assert calls == {"review": 1, "revise": 1}
    assert out["quality"]["source"] == "template"
    assert not redteam._blocking(redteam.run_rules(out, case))


def test_patch_replaces_only_listed_fields_and_legs():
    import json as _json
    fix = _json.loads((__import__("pathlib").Path(__file__).parent / "fixtures" / "erss_ship_sim_dcs.json").read_text())
    ctrl = fix["controller"]
    leg0, leg1 = ctrl["legs"][0], ctrl["legs"][1]
    out = redteam.apply_patch(ctrl, {"moulage": "new", "chain": "ignored",
                                     "legs": [{"leg_id": leg1["leg_id"], "considerations": ["x"]}]})
    assert out["moulage"] == "new" and out["chain"] == ctrl["chain"]
    assert out["legs"][0] == leg0
    assert out["legs"][1]["considerations"] == ["x"] and out["legs"][1]["tree"] == leg1["tree"]


def test_budget_caps_per_case_calls_and_spares_orders():
    b = main._Budget(max_calls=2, max_usd=100)
    b.charge()
    b.charge()
    with pytest.raises(main.BudgetExceeded):
        b.charge()
    b.charge(essential=True)  # orders always run
    assert b.exhausted and b.calls == 3
    d = main._Budget(max_calls=100, max_usd=1.0)
    d.record(1000, 1000, 1.5)
    with pytest.raises(main.BudgetExceeded):
        d.charge()


def test_deterministic_fixes_clean_the_reference_where_no_judgment_is_needed():
    import json as _json
    fix = _json.loads((__import__("pathlib").Path(__file__).parent / "fixtures" / "erss_ship_sim_dcs.json").read_text())
    fixed = redteam.autofix(fix["controller"], fix["case"])
    cats = {f["category"] for f in redteam.run_rules(fixed, fix["case"])}
    assert "template" not in cats and "handover" not in cats  # burns leftover + turnover vitals repaired
