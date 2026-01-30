import os
import random
import json
import zipfile
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from google import genai
import pandas as pd
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

app = FastAPI(title="Role 2 Exercise Builder API")

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

class Exercise(Base):
    __tablename__ = "exercises"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    config = Column(JSON)
    cases = Column(JSON)
    msel_data = Column(JSON)
    warno_text = Column(Text)
    annex_q_text = Column(Text)
    medroe_text = Column(Text)

if engine:
    Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Pydantic Models
class DayConfig(BaseModel):
    day_number: int
    tactical_setting: str
    total_patients: int
    total_waves: int
    night_ops: bool = False
    mascal: bool = False
    mascal_etiology: Optional[str] = None
    mascal_patients: Optional[int] = None
    cbrn: bool = False
    detainee_ops: bool = False

class ExerciseConfig(BaseModel):
    exercise_name: str
    duration: int
    supported_unit: str
    environment: str
    threat_level: str
    region: str
    selected_mets: List[str]
    selected_footprint: List[str]
    specialists: Dict[str, int]
    days: List[DayConfig]

# Case data
DNBI_BY_ENVIRONMENT = {
    "Jungle": ["Dengue hemorrhagic fever", "Malaria", "Snake envenomation", "Cellulitis", "Heat exhaustion", "Leptospirosis"],
    "Desert": ["Heat stroke", "Severe dehydration", "Scorpion envenomation", "Sand fly fever", "Rhabdomyolysis"],
    "Arctic": ["Severe frostbite", "Hypothermia", "Trench foot", "Cold urticaria"],
    "Maritime": ["Near-drowning", "Decompression sickness", "Marine envenomation", "Saltwater aspiration"],
    "Urban": ["Crush injury", "Smoke inhalation", "MSK overuse", "CO poisoning"],
    "Mountain": ["HAPE", "HACE", "Acute mountain sickness", "Fall with fractures"],
    "Littoral": ["Near-drowning", "Jellyfish envenomation", "Coral cuts with infection", "Heat exhaustion"],
    "General": ["Combat stress reaction", "Dental emergency", "Acute appendicitis", "Kidney stones", "Pneumonia", "Gastroenteritis"]
}

TRAUMA_BY_ETIOLOGY = {
    "IED/Blast": ["Traumatic bilateral lower extremity amputation", "TBI with penetrating fragment", "Blast lung injury", "Penetrating abdominal trauma with evisceration", "Severe burns with blast injury"],
    "Vehicle Rollover": ["Blunt abdominal trauma with splenic laceration", "C-spine fracture", "Bilateral femur fractures", "Flail chest", "Pelvic fracture with hemorrhage"],
    "GSW/Small Arms": ["Penetrating chest trauma with hemothorax", "GSW abdomen with liver laceration", "GSW extremity with vascular injury", "GSW neck with airway compromise"],
    "Aviation Mishap": ["Multi-system blunt trauma", "Severe burns (>40% TBSA)", "Spinal cord injury", "Traumatic brain injury"],
    "Indirect Fire/Mortar": ["Multiple penetrating fragment wounds", "TBI from blast", "Traumatic amputation", "Penetrating eye injury"],
    "Structural Collapse": ["Crush syndrome", "Compartment syndrome", "Traumatic asphyxiation", "Multiple long bone fractures"],
    "Burns/Fire": ["Severe thermal burns (>30% TBSA)", "Inhalation injury", "CO poisoning", "Facial burns with airway compromise"],
    "Drowning (Amphibious)": ["Near-drowning with aspiration", "Hypothermia with near-drowning", "Trauma from vessel impact"],
    "VBIED": ["Multi-system blast trauma", "Severe burns with TBI", "Traumatic amputation bilateral", "Penetrating torso wounds"],
}

GENERAL_TRAUMA = [
    "GSW right thigh with femoral artery injury", "Penetrating abdominal trauma", "Blunt chest trauma with rib fractures",
    "Open tibia-fibula fracture", "Traumatic brain injury - moderate", "Blast injury with TM rupture",
    "Penetrating neck trauma", "GSW chest with pneumothorax", "Pelvic fracture - stable", "Burn injury 15% TBSA"
]

def determine_case_phases(case_type: str, mechanism: str) -> List[str]:
    surgical = ["amputation", "evisceration", "vascular", "laceration", "hemothorax", "fasciotomy", 
                "thoracotomy", "GSW abdomen", "penetrating chest", "pelvic fracture with", "compartment", "crush syndrome", "burns (>30%", "burns (>40%"]
    medical = ["dengue", "malaria", "fever", "heat stroke", "hypothermia", "envenomation", "drowning", 
               "decompression", "altitude", "HAPE", "HACE", "pneumonia", "gastroenteritis", "appendicitis", 
               "kidney stones", "combat stress", "dental", "TBI", "concussion", "closed head"]
    
    case_lower = (case_type + " " + mechanism).lower()
    
    for kw in surgical:
        if kw.lower() in case_lower:
            return ["DCR", "DCS", "PCC"]
    for kw in medical:
        if kw.lower() in case_lower:
            return ["DCR", "PCC"]
    return ["DCR", "DCS", "PCC"]

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
}"""

def generate_case_sync(case_type: str, mechanism: str, environment: str, region: str) -> Dict:
    phases = determine_case_phases(case_type, mechanism)
    phase_instr = "This case does NOT require surgery. Only DCR and PCC. Set dcs to null." if phases == ["DCR", "PCC"] else "This case requires surgery. Include DCR, DCS, and PCC."
    
    prompt = f"CONTEXT: Role 2 in {environment}, {region}.\nCASE: {case_type}\nMECHANISM: {mechanism}\n{phase_instr}\nGenerate the case now."
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={"system_instruction": CASE_SYSTEM_PROMPT, "response_mime_type": "application/json"}
    )
    
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        text = response.text
        start, end = text.find('{'), text.rfind('}') + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        raise

def create_fallback_case(case_type: str, mechanism: str, is_trauma: bool = True) -> Dict:
    return {
        "meta": {"title": case_type, "estimated_duration": "30-45 min" if is_trauma else "20-30 min", "personnel": "Medical Team", "target_specialty": "Emergency Medicine" if is_trauma else "Family Physician"},
        "learning_objectives": ["Perform primary survey", "Initiate resuscitation", "Determine evacuation priority"],
        "zmist": {"zap": str(random.randint(10000, 99999)), "mechanism": mechanism, "injuries": case_type, "signs": "HR 110, BP 100/70" if is_trauma else "HR 88, BP 120/80", "treatment": "IV, O2, monitoring"},
        "nine_line": {"line1_location": "Grid TBD", "line2_freq": "Pri: 123.45", "line3_patients_precedence": "1 Alpha" if is_trauma else "1 Charlie", "line4_equipment": "None", "line5_patients_type": "1 Litter" if is_trauma else "1 Ambulatory", "line6_security": "Secure", "line7_marking": "VS-17", "line8_nationality": "US Military", "line9_nbc_terrain": "None"},
        "patient_data": {"demographics": f"{random.randint(19, 35)} yo male Marine", "history": "No PMH", "allergies": "NKDA"},
        "triage_category": "T2" if is_trauma else "T3",
        "phases": {"dcr": {"title": "Damage Control Resuscitation", "narrative": "Patient arrives...", "expected_actions": ["Primary survey", "IV access"], "vitals_trend": [{"time": "0:00", "hr": "110", "bp": "100/70", "rr": "20", "spo2": "95%", "gcs": "14"}], "contingencies": [{"condition": "BP <90", "consequence": "Shock", "intervention": "Blood products"}]}, "dcs": None, "pcc": {"title": "Prolonged Casualty Care", "narrative": "Post-resuscitation...", "expected_actions": ["Monitor", "Pain management"], "vitals_trend": [], "contingencies": []}},
        "labs": {"hgb": "11.2", "ph": "7.32", "lactate": "3.1", "base_excess": "-4", "inr": "1.1"},
        "evacuation": {"transport_type": "MEDEVAC", "priority": "Priority" if is_trauma else "Routine", "considerations": "Monitor vitals", "handover_notes": f"Stable s/p {case_type}"},
        "debrief_questions": ["What were key findings?", "Was resuscitation adequate?", "What would you change?"]
    }

# Document generation
def generate_warno(config: ExerciseConfig) -> str:
    prompt = f"""Generate USMC WARNO (5-paragraph order) for:
Exercise: {config.exercise_name}, Duration: {config.duration} days
Unit: {config.supported_unit}, Environment: {config.environment}, Region: {config.region}
Threat: {config.threat_level}, Footprint: {', '.join(config.selected_footprint)}
Days: {'; '.join([f"Day {d.day_number}: {d.tactical_setting}, {d.total_patients} cas, {'MASCAL '+d.mascal_etiology if d.mascal else 'No MASCAL'}, {'CBRN' if d.cbrn else ''}, {'Night' if d.night_ops else 'Day'}" for d in config.days])}

Include: 1.SITUATION 2.MISSION 3.EXECUTION 4.ADMIN/LOG 5.CMD/SIG"""
    
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text

def generate_annex_q(config: ExerciseConfig) -> str:
    total_cas = sum(d.total_patients for d in config.days)
    prompt = f"""Generate Annex Q (Medical Services) for:
Exercise: {config.exercise_name}, Environment: {config.environment}, Region: {config.region}
Total Casualties: {total_cas}, Footprint: {', '.join(config.selected_footprint)}
Specialists: {json.dumps(config.specialists)}

Include: HSS concept, MTFs, MEDEVAC, Class VIII, blood support, dental, combat stress, PVNTMED"""
    
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text

def generate_medroe(config: ExerciseConfig) -> str:
    has_cbrn = any(d.cbrn for d in config.days)
    has_detainee = any(d.detainee_ops for d in config.days)
    
    prompt = f"""Generate MEDROE for:
Exercise: {config.exercise_name}, Environment: {config.environment}
CBRN: {has_cbrn}, Detainee Ops: {has_detainee}

Include: Treatment priorities, evacuation priorities, holding policy, blood products, documentation, MASCAL procedures"""
    
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text

# Schedule generation
def assign_evaluator(case: Dict, specialists: Dict[str, int], assigned_counts: Dict[str, int]) -> str:
    needs_surgery = case.get("phases", {}).get("dcs") is not None
    triage = case.get("triage_category", "T2")
    
    if needs_surgery:
        priority = ["General Surgery", "Orthopaedic Surgery", "Anesthesiology", "Emergency Medicine"]
    elif triage in ["T1", "T2"]:
        priority = ["Emergency Medicine", "Family Physician", "ER Nurse", "ERC Nurse"]
    else:
        priority = ["ICU Nurse", "Med Surg Nurse", "ER Nurse", "Family Physician"]
    
    abbrev = {"General Surgery": "Gen Surg", "Orthopaedic Surgery": "Ortho", "Emergency Medicine": "EM", "Family Physician": "FP", "Anesthesiology": "Anes", "ERC Nurse": "ERC", "ER Nurse": "ER RN", "ICU Nurse": "ICU RN", "Med Surg Nurse": "MS RN"}
    
    for spec in priority:
        if specialists.get(spec, 0) > 0:
            assigned_counts[spec] = assigned_counts.get(spec, 0) + 1
            num = ((assigned_counts[spec] - 1) % specialists[spec]) + 1
            return f"{abbrev.get(spec, spec)} {num}"
    return "Unassigned"

def generate_schedule(config: ExerciseConfig, cases: List[Dict]) -> List[Dict]:
    schedule = []
    case_idx = 0
    assigned_counts = {}
    
    for day in config.days:
        start_hour, total_hours = (19, 12) if day.night_ops else (7, 12)
        
        if day.cbrn:
            cbrn_time = 9 if not day.night_ops else 21
            schedule.append({"day": day.day_number, "time": f"{cbrn_time:02d}00", "nine_line_time": "N/A", "route": "N/A", "triage_cat": "N/A", "mechanism": "CBRN DRILL", "brief_description": "1-hour CBRN exercise - All clinical ops paused", "evaluator": "All Hands", "case_num": "DRILL"})
        
        num_waves = day.total_waves
        pts_per_wave = day.total_patients // num_waves
        remainder = day.total_patients % num_waves
        wave_interval = total_hours / (num_waves + 1)
        
        for wave in range(num_waves):
            wave_hour = (start_hour + int(wave_interval * (wave + 1))) % 24 if day.night_ops else start_hour + int(wave_interval * (wave + 1))
            wave_pts = pts_per_wave + (1 if wave < remainder else 0)
            time_spread = 45 if day.mascal and wave == 0 else 60
            if day.mascal and wave == 0 and day.mascal_patients:
                wave_pts = day.mascal_patients
            
            for p in range(wave_pts):
                if case_idx >= len(cases):
                    break
                case = cases[case_idx]
                
                min_offset = int((p / max(wave_pts, 1)) * time_spread)
                arr_hour, arr_min = wave_hour, min_offset
                if arr_min >= 60:
                    arr_hour += 1
                    arr_min -= 60
                
                route = random.choice(["MEDEVAC", "Ground", "Walk-in"]) if not day.mascal else random.choice(["MEDEVAC", "Ground", "Litter"])
                if route == "Walk-in":
                    nine_time = "N/A"
                else:
                    nine_hr, nine_min = arr_hour, arr_min - 30
                    if nine_min < 0:
                        nine_hr -= 1
                        nine_min += 60
                    if nine_hr < 0:
                        nine_hr += 24
                    nine_time = f"{nine_hr:02d}{nine_min:02d}"
                
                schedule.append({
                    "day": day.day_number,
                    "time": f"{arr_hour:02d}{arr_min:02d}",
                    "nine_line_time": nine_time,
                    "route": route,
                    "triage_cat": case.get("triage_category", "T2"),
                    "mechanism": case.get("zmist", {}).get("mechanism", "Unknown")[:50],
                    "brief_description": case.get("zmist", {}).get("injuries", "")[:80],
                    "evaluator": assign_evaluator(case, config.specialists, assigned_counts),
                    "case_num": f"Case {case_idx + 1}"
                })
                case_idx += 1
    
    return schedule

# Document creation
def create_docx(title: str, subtitle: str, content: str) -> BytesIO:
    doc = Document()
    h = doc.add_heading(title, 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s = doc.add_paragraph(subtitle)
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s.runs[0].bold = True
    doc.add_paragraph(f'DTG: {datetime.now().strftime("%d%H%MZ %b %Y").upper()}')
    doc.add_paragraph('CLASSIFICATION: UNCLASSIFIED // FOR TRAINING ONLY')
    doc.add_paragraph()
    for line in content.split('\n'):
        if line.strip():
            p = doc.add_paragraph(line)
            if any(line.strip().startswith(f'{i}.') for i in range(1, 10)) or line.strip().isupper():
                if p.runs:
                    p.runs[0].bold = True
    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output

def create_case_book(cases: List[Dict], config: ExerciseConfig) -> BytesIO:
    doc = Document()
    
    # Title
    h = doc.add_heading(config.exercise_name.upper(), 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s = doc.add_paragraph('SIMULATION CASE BOOK')
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s.runs[0].bold = True
    s.runs[0].font.size = Pt(18)
    doc.add_paragraph()
    doc.add_paragraph(f'Environment: {config.environment} | Region: {config.region}').alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f'Duration: {config.duration} days | Total Cases: {len(cases)}').alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f'Generated: {datetime.now().strftime("%d %b %Y %H%M")}')
    doc.add_page_break()
    
    # TOC
    doc.add_heading('TABLE OF CONTENTS', level=1)
    for i, case in enumerate(cases):
        doc.add_paragraph(f'Case {i+1}: {case.get("meta", {}).get("title", "Untitled")} (ZAP: {case.get("zmist", {}).get("zap", "00000")})')
    doc.add_page_break()
    
    # Cases
    for i, case in enumerate(cases):
        meta = case.get("meta", {})
        doc.add_heading(f'CASE {i+1}: {meta.get("title", "Untitled")}', level=1)
        
        # Meta
        t = doc.add_table(rows=2, cols=4)
        t.style = 'Table Grid'
        t.rows[0].cells[0].text = 'Duration'
        t.rows[0].cells[1].text = meta.get("estimated_duration", "N/A")
        t.rows[0].cells[2].text = 'Personnel'
        t.rows[0].cells[3].text = meta.get("personnel", "N/A")
        t.rows[1].cells[0].text = 'Specialty'
        t.rows[1].cells[1].text = meta.get("target_specialty", "N/A")
        t.rows[1].cells[2].text = 'Triage'
        t.rows[1].cells[3].text = case.get("triage_category", "N/A")
        doc.add_paragraph()
        
        # Learning Objectives
        doc.add_heading('Learning Objectives', level=2)
        for obj in case.get("learning_objectives", []):
            doc.add_paragraph(f'• {obj}')
        
        # Z-MIST
        doc.add_heading('Z-MIST Report', level=2)
        zmist = case.get("zmist", {})
        zt = doc.add_table(rows=5, cols=2)
        zt.style = 'Table Grid'
        for idx, (lbl, key) in enumerate([('Z - Zap Number', 'zap'), ('M - Mechanism', 'mechanism'), ('I - Injuries', 'injuries'), ('S - Signs', 'signs'), ('T - Treatment', 'treatment')]):
            zt.rows[idx].cells[0].text = lbl
            zt.rows[idx].cells[1].text = str(zmist.get(key, ""))
        doc.add_paragraph()
        
        # 9-Line
        doc.add_heading('9-Line MEDEVAC Request', level=2)
        nl = case.get("nine_line", {})
        nt = doc.add_table(rows=9, cols=2)
        nt.style = 'Table Grid'
        for idx, (lbl, key) in enumerate([('Line 1 - Location', 'line1_location'), ('Line 2 - Frequency', 'line2_freq'), ('Line 3 - Patients/Precedence', 'line3_patients_precedence'), ('Line 4 - Equipment', 'line4_equipment'), ('Line 5 - Patient Type', 'line5_patients_type'), ('Line 6 - Security', 'line6_security'), ('Line 7 - Marking', 'line7_marking'), ('Line 8 - Nationality', 'line8_nationality'), ('Line 9 - NBC/Terrain', 'line9_nbc_terrain')]):
            nt.rows[idx].cells[0].text = lbl
            nt.rows[idx].cells[1].text = str(nl.get(key, ""))
        doc.add_paragraph()
        
        # Patient
        doc.add_heading('Patient Information', level=2)
        pt = case.get("patient_data", {})
        doc.add_paragraph(f'Demographics: {pt.get("demographics", "N/A")}')
        doc.add_paragraph(f'Medical History: {pt.get("history", "N/A")}')
        doc.add_paragraph(f'Allergies: {pt.get("allergies", "NKDA")}')
        
        # Labs
        labs = case.get("labs", {})
        if labs and any(labs.values()):
            doc.add_heading('Initial Labs', level=2)
            lt = doc.add_table(rows=2, cols=5)
            lt.style = 'Table Grid'
            for c, h in enumerate(['Hgb', 'pH', 'Lactate', 'Base Excess', 'INR']):
                lt.rows[0].cells[c].text = h
            for c, k in enumerate(['hgb', 'ph', 'lactate', 'base_excess', 'inr']):
                lt.rows[1].cells[c].text = str(labs.get(k, ""))
        doc.add_paragraph()
        
        # Phases
        phases = case.get("phases", {})
        for pk in ["dcr", "dcs", "pcc"]:
            phase = phases.get(pk)
            if not phase:
                continue
            doc.add_heading(phase.get("title", pk.upper()), level=2)
            doc.add_paragraph(phase.get("narrative", ""))
            
            doc.add_paragraph('Expected Actions:')
            for act in phase.get("expected_actions", []):
                doc.add_paragraph(f'☐ {act}')
            
            vitals = phase.get("vitals_trend", [])
            if vitals:
                doc.add_paragraph()
                doc.add_paragraph('Vitals Trend:')
                vt = doc.add_table(rows=len(vitals)+1, cols=6)
                vt.style = 'Table Grid'
                for c, h in enumerate(['Time', 'HR', 'BP', 'RR', 'SpO2', 'GCS']):
                    vt.rows[0].cells[c].text = h
                for r, v in enumerate(vitals):
                    for c, k in enumerate(['time', 'hr', 'bp', 'rr', 'spo2', 'gcs']):
                        vt.rows[r+1].cells[c].text = str(v.get(k, ""))
            
            cont = phase.get("contingencies", [])
            if cont:
                doc.add_paragraph()
                doc.add_paragraph('Contingencies (If/Then):')
                for c in cont:
                    doc.add_paragraph(f'IF: {c.get("condition", "")}')
                    doc.add_paragraph(f'   → CONSEQUENCE: {c.get("consequence", "")}')
                    doc.add_paragraph(f'   → INTERVENTION: {c.get("intervention", "")}')
            doc.add_paragraph()
        
        # Evacuation
        doc.add_heading('Evacuation / En Route Care', level=2)
        evac = case.get("evacuation", {})
        doc.add_paragraph(f'Transport: {evac.get("transport_type", "N/A")}')
        doc.add_paragraph(f'Priority: {evac.get("priority", "N/A")}')
        doc.add_paragraph(f'Considerations: {evac.get("considerations", "")}')
        doc.add_paragraph(f'Handover: {evac.get("handover_notes", "")}')
        
        # Debrief
        doc.add_heading('Debrief Questions', level=2)
        for q in case.get("debrief_questions", []):
            doc.add_paragraph(f'• {q}')
        
        if i < len(cases) - 1:
            doc.add_page_break()
    
    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output

def create_msel(schedule: List[Dict], config: ExerciseConfig) -> BytesIO:
    df = pd.DataFrame(schedule)
    df = df[['day', 'time', 'nine_line_time', 'route', 'triage_cat', 'mechanism', 'brief_description', 'evaluator', 'case_num']]
    df.columns = ['Day', 'Time', '9-Line Time', 'Route', 'Triage', 'Mechanism', 'Description', 'Evaluator', 'Case #']
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='MSEL')
        ws = writer.sheets['MSEL']
        for idx, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            ws.column_dimensions[chr(65 + idx)].width = min(max_len, 50)
    output.seek(0)
    return output

# API Endpoints
@app.get("/")
async def root():
    return {"status": "Role 2 Exercise Builder API", "version": "2.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/generate-name")
async def generate_name_endpoint(data: dict):
    env = data.get("environment", "General")
    region = data.get("region", "")
    threat = data.get("threatLevel", "")
    unit = data.get("supportedUnit", "Medical")
    
    prompt = f"Generate one USMC exercise name for {unit} in {env}, {region}, {threat}. Two tactical words. Format: 'Operation [Word] [Word]'. Avoid: Crimson, Steel, Iron, Thunder, Eagle. Return ONLY the name. Seed: {random.random()}"
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    name = response.text.strip().replace('"', '').replace("'", "")
    if not name.startswith("Operation"):
        name = f"Operation {name}"
    return {"name": name}

@app.post("/generate-exercise")
async def generate_exercise(config: ExerciseConfig):
    try:
        cases = []
        
        for day in config.days:
            trauma_ratio = 0.85 if day.mascal or day.tactical_setting in ["Frontal Attack", "Amphibious Assault"] else 0.50
            num_trauma = int(day.total_patients * trauma_ratio)
            num_dnbi = day.total_patients - num_trauma
            
            # Trauma
            for _ in range(num_trauma):
                inj_types = TRAUMA_BY_ETIOLOGY.get(day.mascal_etiology, GENERAL_TRAUMA) if day.mascal and day.mascal_etiology else GENERAL_TRAUMA
                case_type = random.choice(inj_types)
                mech = day.mascal_etiology if day.mascal else day.tactical_setting
                try:
                    cases.append(generate_case_sync(case_type, mech, config.environment, config.region))
                except:
                    cases.append(create_fallback_case(case_type, mech, True))
            
            # DNBI
            env_dnbi = DNBI_BY_ENVIRONMENT.get(config.environment, []) + DNBI_BY_ENVIRONMENT.get("General", [])
            for _ in range(num_dnbi):
                case_type = random.choice(env_dnbi)
                try:
                    cases.append(generate_case_sync(case_type, f"DNBI - {config.environment}", config.environment, config.region))
                except:
                    cases.append(create_fallback_case(case_type, f"DNBI - {config.environment}", False))
        
        random.shuffle(cases)
        schedule = generate_schedule(config, cases)
        warno = generate_warno(config)
        annex = generate_annex_q(config)
        medroe = generate_medroe(config)
        
        # Save
        if SessionLocal:
            db = SessionLocal()
            try:
                ex = Exercise(name=config.exercise_name, config=config.dict(), cases=cases, msel_data=schedule, warno_text=warno, annex_q_text=annex, medroe_text=medroe)
                db.add(ex)
                db.commit()
            finally:
                db.close()
        
        # ZIP
        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{config.exercise_name}_MSEL.xlsx", create_msel(schedule, config).getvalue())
            zf.writestr(f"{config.exercise_name}_WARNO.docx", create_docx("WARNING ORDER", config.exercise_name.upper(), warno).getvalue())
            zf.writestr(f"{config.exercise_name}_Annex_Q.docx", create_docx("ANNEX Q (MEDICAL SERVICES)", f"TO OPORD {config.exercise_name.upper()}", annex).getvalue())
            zf.writestr(f"{config.exercise_name}_MEDROE.docx", create_docx("MEDICAL RULES OF ENGAGEMENT", config.exercise_name.upper(), medroe).getvalue())
            zf.writestr(f"{config.exercise_name}_Case_Book.docx", create_case_book(cases, config).getvalue())
        zip_buf.seek(0)
        
        return Response(zip_buf.getvalue(), headers={'Content-Disposition': f'attachment; filename="{config.exercise_name}_Package.zip"'}, media_type='application/zip')
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/exercises")
async def list_exercises():
    if not SessionLocal:
        return {"exercises": []}
    db = SessionLocal()
    try:
        exs = db.query(Exercise).order_by(Exercise.created_at.desc()).all()
        exercises_list = []
        for e in exs:
            try:
                config = e.config or {}
                cases = e.cases or []
                exercises_list.append({
                    "id": e.id,
                    "name": e.name,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "duration": config.get("duration") if isinstance(config, dict) else None,
                    "environment": config.get("environment") if isinstance(config, dict) else None,
                    "total_cases": len(cases) if isinstance(cases, list) else 0
                })
            except Exception as ex:
                # Log but skip malformed exercises
                exercises_list.append({
                    "id": e.id,
                    "name": e.name or "Unknown",
                    "created_at": None,
                    "duration": None,
                    "environment": None,
                    "total_cases": 0
                })
        return {"exercises": exercises_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        db.close()

@app.get("/exercises/{exercise_id}")
async def get_exercise(exercise_id: int):
    if not SessionLocal:
        raise HTTPException(status_code=404, detail="DB not configured")
    db = SessionLocal()
    try:
        ex = db.query(Exercise).filter(Exercise.id == exercise_id).first()
        if not ex:
            raise HTTPException(status_code=404, detail="Not found")
        return {"id": ex.id, "name": ex.name, "created_at": ex.created_at.isoformat() if ex.created_at else None, "config": ex.config, "cases": ex.cases, "msel_data": ex.msel_data}
    finally:
        db.close()

@app.get("/exercises/{exercise_id}/download")
async def download_exercise(exercise_id: int):
    if not SessionLocal:
        raise HTTPException(status_code=404, detail="DB not configured")
    db = SessionLocal()
    try:
        ex = db.query(Exercise).filter(Exercise.id == exercise_id).first()
        if not ex:
            raise HTTPException(status_code=404, detail="Not found")
        config = ExerciseConfig(**ex.config)
        
        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{config.exercise_name}_MSEL.xlsx", create_msel(ex.msel_data, config).getvalue())
            zf.writestr(f"{config.exercise_name}_WARNO.docx", create_docx("WARNING ORDER", config.exercise_name.upper(), ex.warno_text).getvalue())
            zf.writestr(f"{config.exercise_name}_Annex_Q.docx", create_docx("ANNEX Q (MEDICAL SERVICES)", f"TO OPORD {config.exercise_name.upper()}", ex.annex_q_text).getvalue())
            zf.writestr(f"{config.exercise_name}_MEDROE.docx", create_docx("MEDICAL RULES OF ENGAGEMENT", config.exercise_name.upper(), ex.medroe_text).getvalue())
            zf.writestr(f"{config.exercise_name}_Case_Book.docx", create_case_book(ex.cases, config).getvalue())
        zip_buf.seek(0)
        return Response(zip_buf.getvalue(), headers={'Content-Disposition': f'attachment; filename="{config.exercise_name}_Package.zip"'}, media_type='application/zip')
    finally:
        db.close()

@app.get("/exercises/{exercise_id}/document/{doc_type}")
async def download_document(exercise_id: int, doc_type: str):
    if not SessionLocal:
        raise HTTPException(status_code=404, detail="DB not configured")
    if doc_type not in ["msel", "warno", "annex_q", "medroe", "case_book"]:
        raise HTTPException(status_code=400, detail="Invalid doc type")
    
    db = SessionLocal()
    try:
        ex = db.query(Exercise).filter(Exercise.id == exercise_id).first()
        if not ex:
            raise HTTPException(status_code=404, detail="Not found")
        config = ExerciseConfig(**ex.config)
        
        if doc_type == "msel":
            buf, fn, mt = create_msel(ex.msel_data, config), f"{config.exercise_name}_MSEL.xlsx", 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif doc_type == "warno":
            buf, fn, mt = create_docx("WARNING ORDER", config.exercise_name.upper(), ex.warno_text), f"{config.exercise_name}_WARNO.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif doc_type == "annex_q":
            buf, fn, mt = create_docx("ANNEX Q", f"TO OPORD {config.exercise_name.upper()}", ex.annex_q_text), f"{config.exercise_name}_Annex_Q.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif doc_type == "medroe":
            buf, fn, mt = create_docx("MEDROE", config.exercise_name.upper(), ex.medroe_text), f"{config.exercise_name}_MEDROE.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            buf, fn, mt = create_case_book(ex.cases, config), f"{config.exercise_name}_Case_Book.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        
        return Response(buf.getvalue(), headers={'Content-Disposition': f'attachment; filename="{fn}"'}, media_type=mt)
    finally:
        db.close()