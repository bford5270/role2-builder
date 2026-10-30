"""Why a decision tree became a template, rules for casualties who cannot be saved, and realistic time for minor ones."""
import os
import random
import sys
from pathlib import Path

os.environ["EXERCISE_BUCKET"] = ""  # tests must never reach AWS

from backend import casemix, main, redteam, scenario  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_exercise  # noqa: E402


def point(t, hr, sbp, avpu="A"):
    return {"t": t, "hr": hr, "sbp": sbp, "dbp": 40, "rr": 20, "spo2": 90, "avpu": avpu}


def ctrl(green_end, red_end):
    return {"vitals_tracks": {"green": [point(0, 130, 80), point(60, *green_end)], "red": [point(0, 130, 80), point(25, *red_end)]},
            "critical_actions": [{"id": "ca1", "leg_id": "R2"}]}


def test_a_casualty_who_cannot_be_saved_is_not_forced_to_show_recovery():
    declining_both = ctrl((150, 50, "U"), (140, 60, "V"))  # green ends no better than red: the patient dies despite correct care
    pick = lambda case: {f["severity"] for f in redteam.check_vitals(declining_both, case) if "no better" in f["issue"]}
    assert pick({"severity": "severe", "disposition": "Evac to Role 3"}) == {"medium"}
    assert pick({"severity": "severe", "disposition": "Died of Wounds"}) == {"low"}
    assert pick({"severity": "critical", "triage_category": "Expectant", "disposition": "Expectant"}) == {"low"}


def test_a_template_tree_records_what_blocked_the_ai_layer():
    fixture = Path(__file__).parent / "fixtures" / "erss_ship_sim_dcs.json"
    import json
    fix = json.loads(fixture.read_text())
    broken, case = fix["controller"], fix["case"]
    template = lambda: scenario.fallback_controller(case, broken["chain"], "DCR_DCS")
    out = redteam.finalize(broken, case, review=lambda c, f: c, revise=lambda c, f: c, fallback=template)
    assert out["quality"]["source"] == "template" and out["quality"]["reason"]  # says what the rules objected to
    early = redteam.finalize(template(), case, fallback=template, source="template", reason="generation failed: JSONDecodeError")
    assert early["quality"]["reason"] == "generation failed: JSONDecodeError"


def test_a_minor_casualty_does_not_spend_the_afternoon_in_role_2():
    config = main.ExerciseConfig(exercise_name="T", duration=1, supported_unit="CLB", environment="Urban", threat_level="Hybrid",
                                 region="r", selected_mets=[], selected_footprint=["FRSS"], specialists={},
                                 days=[main.DayConfig(day_number=1, tactical_setting="Defensive Operations", total_patients=10, total_waves=1)])
    p = casemix.draw_parameters(config, random.Random(3))["params"]
    mild = [casemix.dwell_minutes("RTD", 90, 1.0, p, random.Random(s), "mild") for s in range(100)]
    moderate = [casemix.dwell_minutes("RTD", 90, 1.0, p, random.Random(s), "moderate") for s in range(100)]
    assert max(mild) < 4 * 60 and sum(mild) / 100 < sum(moderate) / 100  # treated and released
    assert min(mild) >= 45  # never less than the treatment time


def test_the_audit_reads_a_holding_limit_written_in_bold():
    medroe = "**5. ROLE 2 HOLDING POLICY**\n*   **Holding Limit:** The maximum holding limit at the Role 2 medical facility is **72 hours**."
    annex = "Patients will be held for a maximum of **24 hours**."
    config = {"days": [{"tactical_setting": "Defensive Operations", "detainee_ops": False}]}
    found = audit_exercise.audit_orders(config, [], [], {"medroe": medroe, "annex_q": annex})
    assert any("holding limit [72] h differs from Annex Q [24] h" in f[2] for f in found)
