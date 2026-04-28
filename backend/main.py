import os
import random
import json
import asyncio
import zipfile
import traceback
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import BackgroundTasks, FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from backend.providers import get_case_provider
from backend.providers.base import BatchItem, inject_stable_ids
from backend.casualty_planner import EtiologyBucket, build_day_plan
from backend.schedule_builder import build_schedule
from backend.matrices import TRAUMA_BY_ETIOLOGY, GENERAL_TRAUMA
from backend.case_generator import generate_all_cases
from backend.db import Exercise, SessionLocal, init_db
from backend.jobs import JobStatus, get_job_semaphore, get_job_store

app = FastAPI(title="Role 2 Exercise Builder API")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def create_fallback_case(case_type: str, mechanism: str, is_trauma: bool = True) -> Dict:
    return inject_stable_ids({
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
    })

# Document generation — routed through CaseProvider.generate_text so the
# GovCloud transition only needs to swap the provider implementation, not main.

async def generate_warno(config: ExerciseConfig) -> str:
    days_summary = '; '.join([
        f"Day {d.day_number}: {d.tactical_setting}, {d.total_patients} cas, "
        f"{'MASCAL ' + (d.mascal_etiology or '') if d.mascal else 'No MASCAL'}, "
        f"{'CBRN' if d.cbrn else ''}, {'Night' if d.night_ops else 'Day'}"
        for d in config.days
    ])
    prompt = (
        f"Generate USMC WARNO (5-paragraph order) for:\n"
        f"Exercise: {config.exercise_name}, Duration: {config.duration} days\n"
        f"Unit: {config.supported_unit}, Environment: {config.environment}, Region: {config.region}\n"
        f"Threat: {config.threat_level}, Footprint: {', '.join(config.selected_footprint)}\n"
        f"Days: {days_summary}\n\n"
        f"Include: 1.SITUATION 2.MISSION 3.EXECUTION 4.ADMIN/LOG 5.CMD/SIG"
    )
    return await get_case_provider().generate_text(prompt)


async def generate_annex_q(config: ExerciseConfig) -> str:
    total_cas = sum(d.total_patients for d in config.days)
    prompt = (
        f"Generate Annex Q (Medical Services) for:\n"
        f"Exercise: {config.exercise_name}, Environment: {config.environment}, Region: {config.region}\n"
        f"Total Casualties: {total_cas}, Footprint: {', '.join(config.selected_footprint)}\n"
        f"Specialists: {json.dumps(config.specialists)}\n\n"
        f"Include: HSS concept, MTFs, MEDEVAC, Class VIII, blood support, dental, combat stress, PVNTMED"
    )
    return await get_case_provider().generate_text(prompt)


async def generate_medroe(config: ExerciseConfig) -> str:
    has_cbrn = any(d.cbrn for d in config.days)
    has_detainee = any(d.detainee_ops for d in config.days)
    prompt = (
        f"Generate MEDROE for:\n"
        f"Exercise: {config.exercise_name}, Environment: {config.environment}\n"
        f"CBRN: {has_cbrn}, Detainee Ops: {has_detainee}\n\n"
        f"Include: Treatment priorities, evacuation priorities, holding policy, blood products, documentation, MASCAL procedures"
    )
    return await get_case_provider().generate_text(prompt)

# Schedule generation now lives in backend.schedule_builder; assign_evaluator and
# generate_schedule were removed in favor of build_schedule(plans, cases_by_day, ...).


def _bucket_to_case_inputs(bucket: EtiologyBucket, environment: str) -> tuple[str, str]:
    """Resolve a planner bucket into (case_type, mechanism) for the LLM."""
    cat = bucket.category
    if cat in ("trauma_surgical", "trauma_non_surgical"):
        injuries = TRAUMA_BY_ETIOLOGY.get(bucket.etiology, GENERAL_TRAUMA)
        case_type = random.choice(injuries) if injuries else bucket.etiology
        return case_type, bucket.etiology
    if cat == "dnbi":
        return bucket.etiology, f"DNBI - {environment}"
    if cat in ("cbrn", "cbrn_combined"):
        return bucket.etiology, "CBRN exposure"
    if cat in ("detainee_trauma", "detainee_medical"):
        return bucket.etiology, "Detainee operations"
    return bucket.etiology, bucket.etiology

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
    text = await get_case_provider().generate_text(prompt)
    name = text.strip().replace('"', '').replace("'", "")
    if not name.startswith("Operation"):
        name = f"Operation {name}"
    return {"name": name}

def _trauma_categories():
    return {"trauma_surgical", "trauma_non_surgical", "cbrn_combined", "detainee_trauma"}


def _fallback_for(item: BatchItem) -> Dict:
    is_trauma = item.category in _trauma_categories()
    return create_fallback_case(item.case_type, item.mechanism, is_trauma)


def _log_progress(completed: int, total: int) -> None:
    # Phase 4 will hook this to the ExerciseJob row; for now, log to stdout.
    print(f"[case-gen] {completed}/{total}", flush=True)


async def _run_exercise_pipeline(
    config: ExerciseConfig,
    *,
    on_case_progress=None,
    on_phase=None,
    is_cancelled=None,
) -> Dict[str, Any]:
    """Plan -> generate cases -> schedule -> docs. No HTTP, no DB, no ZIP.

    Returns artifacts the caller can either ZIP up (legacy /generate-exercise)
    or persist + serve via /jobs. If `is_cancelled()` returns True between
    phases, the pipeline returns early with `cancelled=True` and whatever
    work has completed so far.
    """
    async def _cancelled() -> bool:
        return bool(is_cancelled is not None and await is_cancelled())

    if on_phase:
        await on_phase("planning")
    if await _cancelled():
        return {"cancelled": True}

    plans = []
    for day in config.days:
        plans.append(build_day_plan(
            day_number=day.day_number,
            tactical_setting=day.tactical_setting,
            total_patients=day.total_patients,
            night_ops=day.night_ops,
            mascal=day.mascal,
            mascal_etiology=day.mascal_etiology,
            mascal_patients=day.mascal_patients,
            cbrn=day.cbrn,
            detainee_ops=day.detainee_ops,
            threat_level=config.threat_level,
            environment=config.environment,
            region=config.region,
            selected_footprint=config.selected_footprint,
            selected_mets=config.selected_mets,
            total_waves=day.total_waves,
        ))

    if on_phase:
        await on_phase("generating_cases")
    provider = get_case_provider()
    result = await generate_all_cases(
        plans,
        provider,
        environment=config.environment,
        region=config.region,
        bucket_to_case_inputs=_bucket_to_case_inputs,
        fallback_factory=_fallback_for,
        batch_size=int(os.getenv("CASE_BATCH_SIZE", "5")),
        concurrency=int(os.getenv("CASE_BATCH_CONCURRENCY", "3")),
        on_progress=on_case_progress or _log_progress,
        is_cancelled=is_cancelled,
    )
    if result.cancelled or await _cancelled():
        return {"cancelled": True, "partial_cases": result.total_returned}

    cases_by_day = result.cases_by_day
    flat_cases: List[Dict] = []
    for plan in plans:
        flat_cases.extend(cases_by_day.get(plan.day_number, []))

    events = build_schedule(plans, cases_by_day, specialists=config.specialists)
    schedule = [e.to_dict() for e in events]

    if on_phase:
        await on_phase("generating_docs")
    if await _cancelled():
        return {"cancelled": True, "partial_cases": result.total_returned}
    warno = await generate_warno(config)
    annex = await generate_annex_q(config)
    medroe = await generate_medroe(config)

    generation_summary = {
        "total_requested": result.total_requested,
        "total_returned": result.total_returned,
        "total_fallback": result.total_fallback,
        "errors": [
            {
                "key": list(e.key),
                "case_type": e.case_type,
                "mechanism": e.mechanism,
                "category": e.category,
                "error": e.error[:300],
                "attempts": e.attempts,
            }
            for e in result.errors
        ],
    }

    return {
        "cases": flat_cases,
        "schedule": schedule,
        "warno": warno,
        "annex": annex,
        "medroe": medroe,
        "generation_summary": generation_summary,
        "cancelled": False,
    }


def _save_exercise_to_db(config: ExerciseConfig, artifacts: Dict[str, Any]) -> Optional[int]:
    """Persist artifacts to the exercises table. Returns the new id, or None
    if no DB is configured."""
    if not SessionLocal:
        return None
    db = SessionLocal()
    try:
        ex = Exercise(
            name=config.exercise_name,
            config=config.dict(),
            cases=artifacts["cases"],
            msel_data=artifacts["schedule"],
            warno_text=artifacts["warno"],
            annex_q_text=artifacts["annex"],
            medroe_text=artifacts["medroe"],
        )
        db.add(ex)
        db.commit()
        db.refresh(ex)
        return ex.id
    finally:
        db.close()


def _build_zip(config: ExerciseConfig, artifacts: Dict[str, Any]) -> BytesIO:
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{config.exercise_name}_MSEL.xlsx", create_msel(artifacts["schedule"], config).getvalue())
        zf.writestr(f"{config.exercise_name}_WARNO.docx", create_docx("WARNING ORDER", config.exercise_name.upper(), artifacts["warno"]).getvalue())
        zf.writestr(f"{config.exercise_name}_Annex_Q.docx", create_docx("ANNEX Q (MEDICAL SERVICES)", f"TO OPORD {config.exercise_name.upper()}", artifacts["annex"]).getvalue())
        zf.writestr(f"{config.exercise_name}_MEDROE.docx", create_docx("MEDICAL RULES OF ENGAGEMENT", config.exercise_name.upper(), artifacts["medroe"]).getvalue())
        zf.writestr(f"{config.exercise_name}_Case_Book.docx", create_case_book(artifacts["cases"], config).getvalue())
        zf.writestr(
            f"{config.exercise_name}_generation_summary.json",
            json.dumps(artifacts["generation_summary"], indent=2),
        )
    zip_buf.seek(0)
    return zip_buf


def _summary_headers(generation_summary: Dict[str, Any], filename: str) -> Dict[str, str]:
    return {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Generation-Total": str(generation_summary["total_requested"]),
        "X-Generation-Returned": str(generation_summary["total_returned"]),
        "X-Generation-Fallback": str(generation_summary["total_fallback"]),
        "X-Generation-Errors": str(len(generation_summary["errors"])),
    }


@app.post("/generate-exercise")
async def generate_exercise(config: ExerciseConfig):
    """Legacy synchronous endpoint. Builds the entire package in one request.
    For long exercises prefer POST /jobs/generate-exercise (Phase 4)."""
    try:
        artifacts = await _run_exercise_pipeline(config)
        # Sync path can't be cancelled (no separate cancel endpoint binds to
        # it), but stay defensive in case callers pass an is_cancelled hook
        # via some future plumbing.
        if artifacts.get("cancelled"):
            raise HTTPException(status_code=499, detail="exercise generation cancelled")
        _save_exercise_to_db(config, artifacts)
        zip_buf = _build_zip(config, artifacts)
        return Response(
            zip_buf.getvalue(),
            headers=_summary_headers(
                artifacts["generation_summary"],
                f"{config.exercise_name}_Package.zip",
            ),
            media_type="application/zip",
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Job-mode endpoints
# ---------------------------------------------------------------------------

async def _run_exercise_job_worker(job_id: str) -> None:
    """Background worker. Acquires the global semaphore so only one job runs
    at a time, drives the pipeline, and updates the job row as it goes."""
    store = get_job_store()
    sem = get_job_semaphore()
    record = await store.get(job_id)
    if record is None:
        print(f"[job {job_id}] vanished before worker could pick it up", flush=True)
        return
    try:
        config = ExerciseConfig(**record.config)
    except Exception as e:
        await store.mark_failed(job_id, f"invalid config: {e}")
        return

    async with sem:
        # If the user cancelled while the job was queued, honor it without
        # touching the LLM at all.
        latest = await store.get(job_id)
        if latest and latest.status == JobStatus.cancelled:
            return

        await store.mark_running(job_id)
        loop = asyncio.get_running_loop()

        def on_case_progress(completed: int, total: int) -> None:
            # case_generator's callback contract is sync; bridge to the async
            # store via run_coroutine_threadsafe so we don't block the batch loop.
            asyncio.run_coroutine_threadsafe(
                store.update_progress(job_id, completed=completed),
                loop,
            )

        async def on_phase(phase: str) -> None:
            # Avoid clobbering current_phase='cancelled' with a stale phase update.
            cur = await store.get(job_id)
            if cur and cur.status == JobStatus.cancelled:
                return
            await store.update_progress(job_id, current_phase=phase)

        async def is_cancelled() -> bool:
            cur = await store.get(job_id)
            return cur is not None and cur.status == JobStatus.cancelled

        try:
            artifacts = await _run_exercise_pipeline(
                config,
                on_case_progress=on_case_progress,
                on_phase=on_phase,
                is_cancelled=is_cancelled,
            )
            if artifacts.get("cancelled"):
                # Worker honored the cancel request; status was already set to
                # cancelled by the request_cancel call. Just leave it there.
                return

            await on_phase("packaging")
            exercise_id = await asyncio.to_thread(_save_exercise_to_db, config, artifacts)

            summary = artifacts["generation_summary"]
            if summary.get("errors"):
                await store.append_errors(job_id, summary["errors"])
            await store.mark_complete(
                job_id,
                exercise_id=exercise_id,
                generation_summary=summary,
            )
        except Exception as e:
            traceback.print_exc()
            await store.mark_failed(job_id, str(e)[:1000])


@app.post("/jobs/generate-exercise")
async def queue_exercise_job(config: ExerciseConfig, background_tasks: BackgroundTasks):
    """Queue an async exercise generation. Returns immediately with the job id.
    Poll GET /jobs/{id} for progress; download with GET /jobs/{id}/download
    once status == 'complete'."""
    total_cases = sum(d.total_patients for d in config.days)
    store = get_job_store()
    record = await store.create(total_cases=total_cases, config=config.dict())
    background_tasks.add_task(_run_exercise_job_worker, record.id)
    return {
        "job_id": record.id,
        "status": record.status,
        "total_cases": record.total_cases,
        "current_phase": record.current_phase,
        "created_at": record.created_at.isoformat(),
    }


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    record = await get_job_store().get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": record.id,
        "status": record.status,
        "current_phase": record.current_phase,
        "total_cases": record.total_cases,
        "completed_cases": record.completed_cases,
        "progress": round(record.progress, 4),
        "errors_count": len(record.errors),
        "exercise_id": record.exercise_id,
        "error_message": record.error_message,
        "generation_summary": record.generation_summary,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


@app.get("/jobs")
async def list_jobs(limit: int = 20):
    records = await get_job_store().list_recent(limit=limit)
    return {
        "jobs": [
            {
                "job_id": r.id,
                "status": r.status,
                "current_phase": r.current_phase,
                "total_cases": r.total_cases,
                "completed_cases": r.completed_cases,
                "progress": round(r.progress, 4),
                "exercise_id": r.exercise_id,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in records
        ]
    }


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Request graceful cancellation. The worker checks status between batches
    so the in-flight LLM call (if any) finishes before the worker exits.

    Returns 404 if the job doesn't exist, 409 if the job already finished
    (complete/failed), and {accepted: True} on successful cancel."""
    store = get_job_store()
    record = await store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    accepted = await store.request_cancel(job_id)
    if not accepted:
        raise HTTPException(
            status_code=409,
            detail=f"job not cancellable in current state ({record.status.value})",
        )
    fresh = await store.get(job_id)
    return {
        "accepted": True,
        "status": fresh.status if fresh else JobStatus.cancelled,
        "current_phase": fresh.current_phase if fresh else "cancelled",
    }


@app.get("/jobs/{job_id}/download")
async def download_job_zip(job_id: str):
    """Serve the ZIP for a completed job. Returns 409 if the job hasn't
    finished yet, 404 if the job/exercise doesn't exist."""
    record = await get_job_store().get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    if record.status != JobStatus.complete:
        raise HTTPException(status_code=409, detail=f"job not complete (status={record.status.value})")
    if record.exercise_id is None or not SessionLocal:
        raise HTTPException(status_code=404, detail="no exercise persisted for this job")
    return await download_exercise(record.exercise_id)

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
                # Parse JSON if stored as string
                config = e.config or {}
                if isinstance(config, str):
                    config = json.loads(config)
                cases = e.cases or []
                if isinstance(cases, str):
                    cases = json.loads(cases)

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

        # Parse JSON if stored as string
        config_data = ex.config
        if isinstance(config_data, str):
            config_data = json.loads(config_data)
        config = ExerciseConfig(**config_data)

        msel_data = ex.msel_data
        if isinstance(msel_data, str):
            msel_data = json.loads(msel_data)

        cases = ex.cases
        if isinstance(cases, str):
            cases = json.loads(cases)

        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{config.exercise_name}_MSEL.xlsx", create_msel(msel_data, config).getvalue())
            zf.writestr(f"{config.exercise_name}_WARNO.docx", create_docx("WARNING ORDER", config.exercise_name.upper(), ex.warno_text).getvalue())
            zf.writestr(f"{config.exercise_name}_Annex_Q.docx", create_docx("ANNEX Q (MEDICAL SERVICES)", f"TO OPORD {config.exercise_name.upper()}", ex.annex_q_text).getvalue())
            zf.writestr(f"{config.exercise_name}_MEDROE.docx", create_docx("MEDICAL RULES OF ENGAGEMENT", config.exercise_name.upper(), ex.medroe_text).getvalue())
            zf.writestr(f"{config.exercise_name}_Case_Book.docx", create_case_book(cases, config).getvalue())
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

        # Parse JSON if stored as string
        config_data = ex.config
        if isinstance(config_data, str):
            config_data = json.loads(config_data)
        config = ExerciseConfig(**config_data)

        msel_data = ex.msel_data
        if isinstance(msel_data, str):
            msel_data = json.loads(msel_data)

        cases = ex.cases
        if isinstance(cases, str):
            cases = json.loads(cases)

        if doc_type == "msel":
            buf, fn, mt = create_msel(msel_data, config), f"{config.exercise_name}_MSEL.xlsx", 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif doc_type == "warno":
            buf, fn, mt = create_docx("WARNING ORDER", config.exercise_name.upper(), ex.warno_text), f"{config.exercise_name}_WARNO.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif doc_type == "annex_q":
            buf, fn, mt = create_docx("ANNEX Q", f"TO OPORD {config.exercise_name.upper()}", ex.annex_q_text), f"{config.exercise_name}_Annex_Q.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif doc_type == "medroe":
            buf, fn, mt = create_docx("MEDROE", config.exercise_name.upper(), ex.medroe_text), f"{config.exercise_name}_MEDROE.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            buf, fn, mt = create_case_book(cases, config), f"{config.exercise_name}_Case_Book.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        
        return Response(buf.getvalue(), headers={'Content-Disposition': f'attachment; filename="{fn}"'}, media_type=mt)
    finally:
        db.close()