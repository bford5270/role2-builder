"""End-to-end package build with the model stubbed out: fallback base cases,
a fake controller-layer LLM, and the red team — asserts every deliverable is
produced and the care chain follows the FRAGOs."""
import io
import json
import zipfile

import pytest

from backend import main, scenario


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


def _fake_llm(prompt, system):
    if system is scenario.CONTROLLER_SYSTEM_PROMPT:
        # Return a structurally complete layer (reuse the template) with one planted error.
        legs = json.loads(prompt.split("CARE CHAIN LEGS (build one tree per leg, same ids):\n")[1].split("\nFOCUS LEG")[0])
        chain = {"nodes": [], "legs": [{"id": l["leg_id"], "title": l["title"], "capability": l["capability"],
                                        "focus": l["focus"], "from": "", "to": ""} for l in legs]}
        ctrl = scenario.fallback_controller({}, chain, "DCR_HOLD")
        ctrl.pop("_fallback")
        ctrl["moulage"] = "Confused, GCS 9 (E3, V3, M4)"  # planted: 3+3+4=10
        return json.dumps(ctrl)
    if "red team" in system:
        return json.dumps({"findings": [{"severity": "low", "category": "clinical", "location": "x",
                                         "issue": "stub", "fix": "stub"}]})
    return json.dumps({})  # revision: forces the "keep original" branch


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
        assert ctrl["red_team"]["status"] == "auto_checked"
        if ai:
            assert any(f["category"] == "gcs" for f in ctrl["red_team"]["open"])  # planted error caught
        else:
            assert ctrl.get("_fallback")
