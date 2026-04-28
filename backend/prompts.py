"""
Provider-agnostic prompts shared by all CaseProvider implementations.

Kept here (not in providers/) so the same wording feeds Gemini today and
Bedrock-Claude in GovCloud later — only the transport changes.
"""

CASE_SYSTEM_PROMPT = """You are an expert Military Medical Simulation Designer for Role 2 (Forward Surgical) care.
Generate a detailed simulation case with:
1. Z-MIST (Zap=EXACTLY 5 digits, Mechanism, Injuries, Signs, Treatment)
2. 9-Line Medevac (NATO format)
3. Clinical Phases (only include phases specified - some cases don't need surgery)
4. Vitals trends (3-4 timestamps per phase)
5. Contingencies (If/Then decision points)
6. Evacuation (transport type, considerations, handover notes)
7. Learning Objectives (3-5 specific, measurable)
8. Debrief Questions (4-6 thought-provoking)

If DCS not needed, set dcs to null.

JSON STRUCTURE:
{
  "meta": {"title": "String", "estimated_duration": "String", "personnel": "String", "target_specialty": "String"},
  "learning_objectives": ["String"],
  "zmist": {"zap": "5 digits", "mechanism": "String", "injuries": "String", "signs": "String", "treatment": "String"},
  "nine_line": {"line1_location": "String", "line2_freq": "String", "line3_patients_precedence": "String", "line4_equipment": "String", "line5_patients_type": "String", "line6_security": "String", "line7_marking": "String", "line8_nationality": "String", "line9_nbc_terrain": "String"},
  "patient_data": {"demographics": "String", "history": "String", "allergies": "String"},
  "triage_category": "T1/T2/T3/T4",
  "phases": {
    "dcr": {"title": "Damage Control Resuscitation", "narrative": "String", "expected_actions": ["String"], "vitals_trend": [{"time": "String", "hr": "String", "bp": "String", "rr": "String", "spo2": "String", "gcs": "String"}], "contingencies": [{"condition": "String", "consequence": "String", "intervention": "String"}]},
    "dcs": null or {"title": "Damage Control Surgery", "narrative": "String", "expected_actions": ["String"], "vitals_trend": [...], "contingencies": [...]},
    "pcc": {"title": "Prolonged Casualty Care", "narrative": "String", "expected_actions": ["String"], "vitals_trend": [...], "contingencies": [...]}
  },
  "labs": {"hgb": "String", "ph": "String", "lactate": "String", "base_excess": "String", "inr": "String"},
  "evacuation": {"transport_type": "String", "priority": "String", "considerations": "String", "handover_notes": "String"},
  "debrief_questions": ["String"]
}

Do not invent IDs. The server will inject stable IDs after parsing your response.
"""


def case_user_prompt(*, case_type: str, mechanism: str, environment: str, region: str, phases: list[str], target_triage: str | None = None) -> str:
    """User-facing prompt for a single case generation. Provider-agnostic."""
    if "DCS" in phases:
        phase_instr = "This case requires surgery. Include DCR, DCS, and PCC."
    else:
        phase_instr = "This case does NOT require surgery. Only DCR and PCC. Set dcs to null."

    triage_instr = (
        f"The patient should be triage category {target_triage}. Calibrate vitals, mechanism severity, "
        f"and clinical course to that category."
    ) if target_triage else ""

    return (
        f"CONTEXT: Role 2 in {environment}, {region}.\n"
        f"CASE: {case_type}\n"
        f"MECHANISM: {mechanism}\n"
        f"{phase_instr}\n"
        f"{triage_instr}\n"
        "Generate the case now."
    )
