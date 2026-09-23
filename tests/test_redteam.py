import json
import pathlib

from backend import redteam

FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "erss_ship_sim_dcs.json").read_text())


def _findings():
    return redteam.run_rules(FIX["controller"], FIX["case"])


def _has(findings, category, text):
    return any(f["category"] == category and text.lower() in f["issue"].lower() for f in findings)


def test_flags_scapula_laterality_against_body_map():
    assert _has(_findings(), "laterality", "L Scapula")


def test_flags_efast_side_against_hemothorax_side():
    assert _has(_findings(), "laterality", "R effected side")


def test_flags_moulage_gcs_vs_vitals_table():
    assert _has(_findings(), "gcs", "Moulage GCS 10")


def test_flags_chest_tube_threshold_drift():
    assert _has(_findings(), "threshold", "200 mL/hr")


def test_flags_turnover_vs_arrival_vitals():
    assert _has(_findings(), "handover", "Turnover vitals differ")


def test_flags_burns_template_leftover():
    assert _has(_findings(), "template", "Burns block")


def test_accepts_sound_parts_of_the_reference():
    f = _findings()
    assert not _has(f, "tree", "unreachable")
    assert not _has(f, "vitals", "does not deteriorate")
    assert not _has(f, "capability", "")
    assert not _has(f, "medication", "")


def test_surgery_on_non_surgical_leg_is_flagged():
    ctrl = json.loads(json.dumps(FIX["controller"]))
    ctrl["legs"][1]["capability"] = ["DCR"]
    assert _has(redteam.run_rules(ctrl, FIX["case"]), "capability", "no DCS capability")
