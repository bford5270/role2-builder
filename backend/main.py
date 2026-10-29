import os
import re
import time
import random
import json
import zipfile
import threading
import uuid
from io import BytesIO
from types import SimpleNamespace
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, Response, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from google import genai
import pandas as pd
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

try:
    from backend import scenario, redteam, controller_docs, archive, casemix, jsonfix
except ImportError:  # running from inside backend/
    import scenario, redteam, controller_docs, archive, casemix, jsonfix

app = FastAPI(title="Role 2 Exercise Builder API")

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# NullPool: open a connection per session and close it after. Holding pooled
# connections open would keep the shared Aurora Serverless v2 cluster from
# auto-pausing (R2RA's docs/COST.md) and turn a ~$0 idle cost into a 24/7 ACU bill.
engine = create_engine(DATABASE_URL, poolclass=NullPool, pool_pre_ping=True) if DATABASE_URL else None
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
    road_to_war_text = Column(Text)
    fragos = Column(JSON)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    status = Column(String, default="running")
    progress = Column(String, default="Starting...")
    completed = Column(Integer, default=0)
    total = Column(Integer, default=0)
    token = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

from sqlalchemy import text as _sql_text

if engine:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as _e:
        print(f"WARNING: DB table creation failed: {_e}")
    # create_all does not ALTER existing tables — add newer columns idempotently.
    try:
        with engine.begin() as _conn:
            _conn.execute(_sql_text(
                "ALTER TABLE exercises ADD COLUMN IF NOT EXISTS road_to_war_text TEXT"
            ))
    except Exception as _e:
        print(f"WARNING: DB column migration (road_to_war_text) failed: {_e}")
    try:
        with engine.begin() as _conn:
            _conn.execute(_sql_text("ALTER TABLE exercises ADD COLUMN IF NOT EXISTS fragos JSON"))
    except Exception as _e:
        print(f"WARNING: DB column migration (fragos) failed: {_e}")

# Explicit allow-list. The API uses no cookies or auth headers, so
# credentials stay off and "*" is never the fallback.
_DEFAULT_ORIGINS = "https://www.role2builder.org,https://role2builder.org,http://localhost:3000"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")
                if o.strip() and o.strip() != "*"]
if not CORS_ORIGINS:
    # Env still set to "*" (the old default): fall back to the site, not to nothing.
    CORS_ORIGINS = _DEFAULT_ORIGINS.split(",")

# Vercel URLs for this project: the stable alias and per-deployment preview
# URLs, which carry the team suffix only this account's projects can use.
CORS_ORIGIN_REGEX = r"https://role2-builder(-[a-z0-9-]+-brians-projects-0545fc67)?\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Per-client limits on the endpoints that spend Gemini money, so one caller
# can't drain the shared daily cap (MAX_USD_PER_DAY) for everyone else.
# In-memory, single process — same model as the spend guards below.
MAX_EXERCISES_PER_CLIENT_PER_DAY = int(os.getenv("MAX_EXERCISES_PER_CLIENT_PER_DAY", "3"))
MAX_NAMES_PER_CLIENT_PER_HOUR = int(os.getenv("MAX_NAMES_PER_CLIENT_PER_HOUR", "30"))
_rate_lock = threading.Lock()
_rate_hits: Dict[str, List[datetime]] = {}


def _client_key(request: Request) -> str:
    # CloudFront appends the viewer address as the last X-Forwarded-For entry
    # and this container sits directly behind it, so use that entry.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _check_client_rate(request: Request, bucket: str, limit: int, window: timedelta, detail: str) -> None:
    now = datetime.utcnow()
    key = f"{bucket}:{_client_key(request)}"
    with _rate_lock:
        hits = [t for t in _rate_hits.get(key, []) if now - t < window]
        if len(hits) >= limit:
            _rate_hits[key] = hits
            raise HTTPException(status_code=429, detail=detail)
        hits.append(now)
        _rate_hits[key] = hits

_client = None

# Gemini model id. Centralized + env-overridable so a Google model retirement
# (e.g. gemini-2.0-flash was decommissioned with a 404) is a one-variable fix
# on Railway rather than a code change + redeploy.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_active_model = GEMINI_MODEL  # may move to a newer Flash model if the configured one is retired (see _switch_model)

# Every call gets a hard timeout (a hung request must not pin a worker thread forever) and a few
# SDK-level retries for rate limits and server errors. Failed requests are not billed.
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "120"))
GEMINI_ATTEMPTS = int(os.getenv("GEMINI_ATTEMPTS", "3"))
# Simulated combat-casualty content trips Gemini's default safety filters; relax them (as /generate-name
# already did). Set GEMINI_RELAX_SAFETY=0 to use Google's defaults.
GEMINI_RELAX_SAFETY = os.getenv("GEMINI_RELAX_SAFETY", "1") != "0"
# The AI expert-review call is skipped for mild casualties (the free rules still run): it costs a call per case and adds
# little for a minor injury. Set AI_REVIEW_MILD=1 to review every case.
REVIEW_MILD = os.getenv("AI_REVIEW_MILD", "0") == "1"

def get_client():
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY not set on server")
        from google.genai import types
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(
            timeout=int(GEMINI_TIMEOUT_S * 1000),
            retry_options=types.HttpRetryOptions(attempts=GEMINI_ATTEMPTS, initial_delay=1.0, max_delay=10.0,
                                                 http_status_codes=[429, 500, 502, 503, 504])))
    return _client


class AIError(RuntimeError):
    """A classified Gemini failure, so callers and /health/ai can say what went wrong."""
    def __init__(self, kind: str, detail: str = "", cause: Optional[BaseException] = None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind, self.detail = kind, detail
        # Safe-to-share fingerprints of the underlying failure (class name, HTTP code, Google's status enum).
        # Never the message text, which can contain account details.
        self.error_type = type(cause).__name__ if cause else None
        self.http_code = getattr(cause, "code", None) if isinstance(getattr(cause, "code", None), int) else None
        self.status = getattr(cause, "status", None) if isinstance(getattr(cause, "status", None), str) else None


# What to tell the user when cases fall back to templates, by failure kind.
AI_KIND_TEXT = {
    "model_not_found": "the AI model is unavailable (retired or renamed)",
    "auth_or_ip": "the AI key was rejected (invalid, or blocked by its IP restriction)",
    "billing": "the Google AI account is out of credit or at its spending cap — check billing for the API key's project",
    "quota": "the AI quota or rate limit was hit",
    "unavailable": "the AI service was unreachable or timed out",
    "blocked": "the AI safety filter blocked the response",
    "truncated": "the AI response was cut off",
    "budget": "the exercise AI budget was reached",
    "bad_request": "Google rejected the request (invalid parameters or unsupported location)",
}

def _classify_ai_error(e: Exception) -> str:
    code = getattr(e, "code", None)
    msg = str(e).lower()
    if isinstance(code, int):
        if code == 404:
            return "model_not_found"
        if code in (401, 403) or (code == 400 and "api key" in msg):
            return "auth_or_ip"
        if code == 402:
            return "billing"  # Google: prepaid credit used up or spending cap reached (status RESOURCE_EXHAUSTED)
        if code == 429:
            return "quota"
        if code in (408, 500, 502, 503, 504):
            return "unavailable"
        if code == 400:
            return "bad_request"
    if isinstance(e, (TimeoutError, ConnectionError)) or type(e).__name__ in (
            "ReadTimeout", "ConnectTimeout", "TimeoutException", "ConnectError", "RemoteProtocolError"):
        return "unavailable"
    return "other"

_ai_lock = threading.Lock()
_ai_state: Dict[str, Any] = {"ok": None, "kind": None, "model": GEMINI_MODEL, "ts": None}

def _note_ai(ok: bool, kind: Optional[str] = None, err: Optional["AIError"] = None) -> None:
    """Remember the outcome of the latest real model call for /health/ai."""
    with _ai_lock:
        _ai_state.update(ok=ok, kind=kind, model=_active_model, ts=datetime.utcnow().isoformat() + "Z",
                         error_type=getattr(err, "error_type", None), http_code=getattr(err, "http_code", None),
                         status=getattr(err, "status", None))

def _discover_model() -> Optional[str]:
    """Newest stable Flash model this key can call (ids like gemini-2.5-flash, never -lite/-preview/-exp)."""
    best = None
    for m in get_client().models.list():
        name = (getattr(m, "name", "") or "").replace("models/", "")
        found = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash", name)
        if found and "generateContent" in (getattr(m, "supported_actions", None) or []):
            if best is None or float(found.group(1)) > best[0]:
                best = (float(found.group(1)), name)
    return best[1] if best else None

def _switch_model(failed_model: str) -> bool:
    """The configured model returned 404 (retired): move to the newest stable Flash. True if it changed."""
    global _active_model
    with _ai_lock:
        if _active_model != failed_model:
            return True  # another thread already switched
        try:
            found = _discover_model()
        except Exception as e:
            print(f"WARNING: could not list Gemini models while recovering from a 404 on {failed_model}: {e}")
            return False
        if not found or found == failed_model:
            return False
        _active_model = found
    print(f"WARNING: Gemini model '{failed_model}' was not found; switched to '{found}'. "
          f"Set GEMINI_MODEL={found} to make this permanent and check pricing.")
    return True

def _safety_settings():
    from google.genai import types
    return [types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in (
        "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")]

def _response_text(response) -> str:
    """Safely pull text out of a Gemini response.

    response.text raises when the model returns no usable candidate (e.g. the
    prompt tripped a safety filter). Fall back to walking the candidate parts,
    and return "" rather than raising so callers can degrade gracefully.
    """
    try:
        text = response.text
        if text:
            return text.strip()
    except Exception:
        pass
    try:
        parts = []
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                if getattr(part, "text", None):
                    parts.append(part.text)
        return "".join(parts).strip()
    except Exception:
        return ""

# --- Cost control ------------------------------------------------------------
# gemini-2.5-flash bills hidden "thinking" tokens as output, and output is ~8x
# the price of input. Every pipeline call therefore gets an explicit thinking
# cap, and every call is metered against a per-exercise and a per-day ceiling so
# one large (or abusive) generation can never run up an open-ended bill.
def _env_num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default

PRICE_IN_PER_M = _env_num("GEMINI_PRICE_IN_PER_M", 0.30)    # USD / 1M input tokens
PRICE_OUT_PER_M = _env_num("GEMINI_PRICE_OUT_PER_M", 2.50)  # USD / 1M output + thinking tokens
MAX_USD_PER_EXERCISE = _env_num("MAX_USD_PER_EXERCISE", 5.0)
MAX_USD_PER_DAY = _env_num("MAX_USD_PER_DAY", 25.0)
MAX_CONCURRENT_JOBS = int(_env_num("MAX_CONCURRENT_JOBS", 2))
MAX_CALLS_PER_CASE = int(_env_num("MAX_CALLS_PER_CASE", 4))  # case + controller + review + revise

# Thinking-token caps per call kind (0 disables thinking on 2.5 Flash).
THINKING = {
    "case": int(_env_num("THINKING_CASE", 1024)),
    "controller": int(_env_num("THINKING_CONTROLLER", 2048)),
    "review": int(_env_num("THINKING_REVIEW", 1024)),
    "revise": int(_env_num("THINKING_REVISE", 512)),
    "orders": int(_env_num("THINKING_ORDERS", 1024)),
    "probe": 0,  # /health/ai: a one-word reply needs no thinking
}


class BudgetExceeded(RuntimeError):
    pass


class _Budget:
    """Per-exercise model-call meter. Non-essential calls (per-case work) stop
    once the call or dollar ceiling is reached and the pipeline falls back to
    templates; essential calls (the orders) always run."""

    def __init__(self, max_calls: int, max_usd: float):
        self.max_calls, self.max_usd = max_calls, max_usd
        self.calls = self.tok_in = self.tok_out = self.tok_cached = 0
        self.usd = 0.0
        self.exhausted = False
        self._lock = threading.Lock()

    def charge(self, essential: bool = False):
        with self._lock:
            if not essential and (self.calls >= self.max_calls or self.usd >= self.max_usd):
                self.exhausted = True
                raise BudgetExceeded(f"exercise AI budget reached ({self.calls} calls, ${self.usd:.2f})")
            self.calls += 1

    def record(self, tok_in: int, tok_out: int, usd: float, tok_cached: int = 0):
        with self._lock:
            self.tok_in += tok_in
            self.tok_cached += tok_cached
            self.tok_out += tok_out
            self.usd += usd

    def summary(self) -> Dict:
        return {"calls": self.calls, "input_tokens": self.tok_in, "cached_tokens": self.tok_cached,
                "output_tokens": self.tok_out, "est_usd": round(self.usd, 4)}


_tl = threading.local()  # .budget: the _Budget of the job this thread is working for
_spend_lock = threading.Lock()
_daily_spend = {"day": None, "usd": 0.0}


def _bound(budget: Optional["_Budget"], fn):
    """Run fn on a worker thread with the job's budget attached."""
    def run(*a, **k):
        _tl.budget = budget
        try:
            return fn(*a, **k)
        finally:
            _tl.budget = None
    return run


def _today_spend() -> float:
    with _spend_lock:
        return _daily_spend["usd"] if _daily_spend["day"] == datetime.utcnow().date() else 0.0


def _raise_if_unusable(response, json_mode: bool) -> None:
    """Turn a 200 response with no usable output (safety block, cut-off JSON) into a classified error."""
    cands = getattr(response, "candidates", None) or []
    if not cands:
        reason = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        if reason:
            raise AIError("blocked", str(reason))
        return
    finish = getattr(cands[0], "finish_reason", None)
    name = getattr(finish, "name", str(finish or ""))
    if name in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII") and not _response_text(response):
        raise AIError("blocked", name)
    if json_mode and name == "MAX_TOKENS":
        raise AIError("truncated", name)


def _call_model(prompt: str, kind: str, system: Optional[str] = None, json_mode: bool = False):
    """Every pipeline Gemini call goes through here: thinking cap, budget, meter."""
    budget = getattr(_tl, "budget", None)
    if budget:
        budget.charge(essential=(kind == "orders"))
    config: Dict[str, Any] = {"thinking_config": {"thinking_budget": THINKING[kind]}}
    if system:
        config["system_instruction"] = system
    if json_mode:
        config["response_mime_type"] = "application/json"
    if GEMINI_RELAX_SAFETY:
        config["safety_settings"] = _safety_settings()
    used = _active_model
    try:
        try:
            response = get_client().models.generate_content(model=used, contents=prompt, config=config)
        except HTTPException:
            raise
        except Exception as e:
            if _classify_ai_error(e) != "model_not_found" or not _switch_model(used):
                raise
            used = _active_model  # the configured model was retired: retry once on the replacement
            response = get_client().models.generate_content(model=used, contents=prompt, config=config)
        _raise_if_unusable(response, json_mode)
    except HTTPException:
        raise
    except AIError as e:
        _note_ai(False, e.kind, e)
        raise
    except Exception as e:
        err = AIError(_classify_ai_error(e), str(e)[:200], cause=e)
        _note_ai(False, err.kind, err)
        raise err from e
    _note_ai(True)
    u = getattr(response, "usage_metadata", None)
    tok_in = (getattr(u, "prompt_token_count", 0) or 0) if u else 0
    tok_out = ((getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0
    # Gemini caches repeated prompt prefixes automatically and bills those tokens at a discount. The estimate below
    # deliberately ignores the discount (conservative); the count is recorded so savings are visible in the log.
    tok_cached = (getattr(u, "cached_content_token_count", 0) or 0) if u else 0
    usd = tok_in / 1e6 * PRICE_IN_PER_M + tok_out / 1e6 * PRICE_OUT_PER_M
    if budget:
        budget.record(tok_in, tok_out, usd, tok_cached)
    with _spend_lock:
        today = datetime.utcnow().date()
        if _daily_spend["day"] != today:
            _daily_spend.update(day=today, usd=0.0)
        _daily_spend["usd"] += usd
    return response


# System prompt → call kind, so the thinking cap follows the job being done.
_LLM_KIND = {
    scenario.CONTROLLER_SYSTEM_PROMPT: "controller",
    redteam.CRITIC_SYSTEM_PROMPT: "review",
    scenario.REVISE_SYSTEM_PROMPT: "revise",
}


def _llm_json(prompt: str, system: str) -> str:
    """JSON-mode Gemini call used by the scenario controller layer and red team."""
    response = _call_model(prompt, _LLM_KIND.get(system, "review"), system=system, json_mode=True)
    text = _response_text(response)
    if not text:
        raise ValueError("empty model response")
    return text

# Curated pools mirror the /generate-name prompt so the offline fallback stays
# on-brand. None of these appear in the prompt's banned-word list.
_NAME_DESCRIPTORS = [
    "Silent", "Relentless", "Fractured", "Bleeding", "Stalking", "Burning",
    "Severed", "Hollow", "Bitter", "Fading", "Broken", "Restless", "Savage",
    "Grim", "Fallen", "Rising", "Distant", "Shattered", "Quiet", "Vigilant",
]
_NAME_NOUNS_LAND = [
    "Jackal", "Wolverine", "Lynx", "Mantis", "Fury", "Wrath", "Valor",
    "Resolve", "Defiance", "Reckoning", "Rampart", "Bastion", "Crucible",
    "Gauntlet", "Threshold", "Salient", "Bulwark", "Sentinel", "Vanguard",
]
_NAME_NOUNS_MARITIME = ["Mako", "Condor", "Viper", "Barracuda", "Kraken", "Tempest"]

def _local_exercise_name(region: str = "") -> str:
    """Deterministic-random offline name so the endpoint never fails to fetch."""
    nouns = list(_NAME_NOUNS_LAND)
    if any(w in (region or "").lower() for w in ("marit", "pacific", "naval", "littoral", "coast", "sea")):
        nouns = nouns + _NAME_NOUNS_MARITIME
    return f"Operation {random.choice(_NAME_DESCRIPTORS)} {random.choice(nouns)}"

# Short-lived store for completed zip packages keyed by download token.
# Entries carry a timestamp so stale packages (never downloaded) get purged
# instead of accumulating for the life of the process.
_packages: Dict[str, Dict[str, Any]] = {}
_PACKAGE_TTL = timedelta(hours=6)
_JOB_TTL = timedelta(hours=24)

def _purge_stale_stores():
    now = datetime.utcnow()
    for tok in [t for t, p in _packages.items() if now - p["ts"] > _PACKAGE_TTL]:
        _packages.pop(tok, None)
    for jid in [j for j, v in _jobs.items()
                if v.get("ts") and now - v["ts"] > _JOB_TTL]:
        _jobs.pop(jid, None)

# ZAP numbers key every sheet in the package (MSEL, T&EO, Blood Ledger, Case
# Book) — independent random draws collide surprisingly often at exercise
# scale, so allocate them from a process-wide set instead.
_zap_lock = threading.Lock()
_used_zaps: set = set()

_ZAP_RESET_AT = 45000  # half of the 90,000-number space

def _new_zap() -> str:
    with _zap_lock:
        if len(_used_zaps) >= _ZAP_RESET_AT:
            # Only uniqueness within one package matters. Reset instead of growing for the
            # life of the process, and so the loop below can never run out of free numbers.
            _used_zaps.clear()
        while True:
            z = str(random.randint(10000, 99999))
            if z not in _used_zaps:
                _used_zaps.add(z)
                return z

# Pydantic Models
class DayConfig(BaseModel):
    day_number: int = Field(ge=1, le=30)
    tactical_setting: str = Field(max_length=500)
    total_patients: int = Field(ge=0, le=60)
    total_waves: int = Field(ge=1, le=12)
    night_ops: bool = False
    mascal: bool = False
    mascal_etiology: Optional[str] = Field(default=None, max_length=80)
    mascal_patients: Optional[int] = Field(default=None, ge=1, le=30)
    cbrn: bool = False
    detainee_ops: bool = False

class ExerciseConfig(BaseModel):
    exercise_name: str = Field(max_length=120)
    duration: int = Field(ge=1, le=30)
    supported_unit: str = Field(max_length=120)
    environment: str = Field(max_length=40)
    threat_level: str = Field(max_length=40)
    region: str = Field(max_length=120)
    selected_mets: List[str] = Field(max_length=100)
    selected_footprint: List[str] = Field(max_length=50)
    specialists: Dict[str, int] = Field(max_length=50)
    days: List[DayConfig] = Field(max_length=30)
    # Who the exercise is meant to treat beyond friendly forces. None = derive from the days (Detainee Ops -> enemy
    # combatants/EPW; Humanitarian or Stability days -> civilians). One policy drives both the MEDROE and the case mix.
    treat_enemy_combatants: Optional[bool] = None
    treat_civilians: Optional[bool] = None
    # "realistic" follows published Role 2 casualty severity; "high" is a training emphasis with 2-3x the critical/severe share.
    casualty_acuity: str = Field(default="realistic", pattern="^(realistic|high)$")

# Case data
DNBI_BY_ENVIRONMENT = {
    "Jungle": ["Dengue hemorrhagic fever", "Malaria", "Snake envenomation", "Cellulitis", "Heat exhaustion", "Leptospirosis"],
    "Desert": ["Heat stroke", "Severe dehydration", "Scorpion envenomation", "Sand fly fever", "Rhabdomyolysis"],
    "Arctic": ["Severe frostbite", "Hypothermia", "Trench foot", "Cold urticaria"],
    "Maritime": ["Near-drowning", "Decompression sickness", "Marine envenomation", "Saltwater aspiration"],
    "Urban": ["Crush injury", "Smoke inhalation", "MSK overuse", "CO poisoning"],
    "Mountain": ["HAPE", "HACE", "Acute mountain sickness", "Fall with fractures"],
    "Littoral": ["Near-drowning", "Jellyfish envenomation", "Coral cuts with infection", "Heat exhaustion"],
    "General": ["Combat stress reaction", "Dental emergency", "Acute appendicitis", "Kidney stones", "Pneumonia", "Gastroenteritis",
                "Acute asthma exacerbation", "Moderate dehydration with vomiting", "Ankle sprain with possible fracture"]
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
    "UAS/Drone Strike": ["Multiple small deep fragment wounds to head/neck and posterior torso", "Traumatic below-knee amputation from FPV drone strike", "Junctional hemorrhage from drone-dropped munition fragments", "Blast TBI with penetrating facial fragments", "Extremity fragment wounds with prolonged tourniquet time and wound contamination"],
}

# Mechanism-specific context injected into the case-generation prompt so the
# model grounds the scenario in observed casualty patterns for that etiology.
MECHANISM_CONTEXT = {
    "UAS/Drone Strike": (
        "UAS CASUALTY PATTERN (per Russo-Ukrainian war experience, where UAS became "
        "the leading cause of combat casualties): strikes are FPV attack drones with "
        "RPG-type shaped-charge warheads or drone-dropped VOG-type grenades detonating "
        "overhead. Expect multiple small, deep penetrating fragments concentrated in "
        "the head/neck, posterior torso, and extremities (body armor spares the anterior "
        "torso; overhead cover is often absent); traumatic amputations from direct FPV "
        "hits; and combined blast TBI. Drones interdict evacuation routes and re-attack "
        "casualty collection points ('double-tap'), so casualties frequently arrive at "
        "Role 2 hours late after prolonged field care — build in prolonged tourniquet "
        "times with reperfusion/conversion decisions, wound contamination with early "
        "infection risk, hypothermia, and under-resuscitation on arrival."
    ),
}

GENERAL_TRAUMA = [
    "GSW right thigh with femoral artery injury", "Penetrating abdominal trauma", "Blunt chest trauma with rib fractures",
    "Open tibia-fibula fracture", "Traumatic brain injury - moderate", "Blast injury with TM rupture",
    "Penetrating neck trauma", "GSW chest with pneumothorax", "Pelvic fracture - stable", "Burn injury 15% TBSA"
]

# Severity-tiered case pools. "serious" is for critical and severe casualties (the original lists); "moderate" and "mild"
# were added so the mix can follow the literature, where most Role 2 casualties are mild or moderate. The moderate and
# mild entries are PROVISIONAL and need clinician review (docs/case-mix-assumptions.md).
GENERAL_TRAUMA_TIERS = {
    "serious": ["GSW right thigh with femoral artery injury", "Penetrating abdominal trauma", "Penetrating neck trauma",
                "GSW chest with pneumothorax", "Traumatic lower-extremity amputation"],
    "moderate": ["Blunt chest trauma with rib fractures", "Open tibia-fibula fracture", "Traumatic brain injury - moderate",
                 "Pelvic fracture - stable", "Burn injury 15% TBSA", "GSW to the extremity without vascular injury",
                 "Closed femur fracture", "Facial fractures with a patent airway"],
    "mild": ["Blast injury with TM rupture", "Concussion, mild TBI", "Laceration requiring repair", "Closed ankle fracture",
             "Contusions and abrasions", "Minor burns under 5% TBSA", "Eye foreign body", "Hand crush injury without fracture"],
}
_ETIOLOGY_LESS_SEVERE = {
    "IED/Blast": (["Blast TBI, moderate, with TM rupture", "Fragment wounds to the extremities without vascular injury",
                   "Closed lower-extremity fracture from the blast wave"],
                  ["Concussion with tinnitus", "Superficial fragment wounds to the arms and face", "Acoustic trauma with bilateral TM perforation"]),
    "Vehicle Rollover": (["Closed femur fracture", "Rib fractures with pulmonary contusion", "Clavicle and scapular fractures"],
                         ["Cervical strain", "Contusions and abrasions", "Minor head laceration"]),
    "GSW/Small Arms": (["GSW to the extremity without vascular injury", "GSW to the flank, hemodynamically stable", "Through-and-through GSW to the shoulder"],
                       ["Graze wound to the arm", "Superficial fragment wound to the leg", "Minor ricochet wound"]),
    "Aviation Mishap": (["Lumbar compression fracture", "Multiple stable closed fractures", "Traumatic brain injury - moderate"],
                        ["Back strain", "Contusions and abrasions", "Minor lacerations"]),
    "Indirect Fire/Mortar": (["Fragment wounds to the extremities", "Blast TBI, moderate", "Small pneumothorax from a fragment"],
                             ["Superficial fragment wounds", "Concussion", "Acoustic trauma"]),
    "Structural Collapse": (["Crush injury to the leg without compartment syndrome", "Stable pelvic ring fracture", "Multiple rib fractures"],
                            ["Dust and eye irritation", "Contusions and abrasions", "Ankle injury"]),
    "Burns/Fire": (["Partial-thickness burns 10-20% TBSA", "Facial burns with a patent airway", "Hand burns"],
                   ["Minor burns under 5% TBSA", "Smoke exposure, asymptomatic", "Blistering of the forearm"]),
    "Drowning (Amphibious)": (["Near-drowning with aspiration, responsive to oxygen", "Moderate hypothermia", "Marine laceration at risk of infection"],
                              ["Mild hypothermia", "Coral cuts", "Swallowed-water episode, asymptomatic"]),
    "VBIED": (["Blast TBI with TM rupture", "Fragment wounds to the extremities", "Closed fractures from the blast wave"],
              ["Concussion", "Superficial glass lacerations", "Acoustic trauma"]),
    "UAS/Drone Strike": (["Small fragment wounds to the extremities without vascular injury", "Blast TBI, moderate", "Extremity wounds with a tourniquet already applied"],
                         ["Superficial fragment wounds", "Acoustic trauma", "Concussion"]),
}
# An eye injury is sight-threatening and evacuated, not life-threatening: it belongs with the moderate casualties.
_EYE = "penetrating eye"
TRAUMA_TIERS = {e: {"serious": [c for c in TRAUMA_BY_ETIOLOGY[e] if _EYE not in c.lower()],
                    "moderate": mod + [c for c in TRAUMA_BY_ETIOLOGY[e] if _EYE in c.lower()], "mild": mild}
                for e, (mod, mild) in _ETIOLOGY_LESS_SEVERE.items() if e in TRAUMA_BY_ETIOLOGY}

_DNBI_SERIOUS_KW = ("hemorrhagic", "heat stroke", "hape", "hace", "hypothermia", "near-drowning", "decompression", "crush",
                    "smoke", "co poisoning", "rhabdo", "appendicitis", "frostbite", "envenomation", "leptospirosis",
                    "fall with fractures", "aspiration")
_DNBI_MILD_KW = ("exhaustion", "dental", "stress", "sprain", "msk", "urticaria", "coral", "gastroenteritis",
                 "mountain sickness", "sand fly", "trench foot")

def dnbi_tier(case_type: str) -> str:
    """serious / moderate / mild for a DNBI condition, from its name (provisional)."""
    t = case_type.lower()
    if any(k in t for k in _DNBI_SERIOUS_KW):
        return "serious"
    return "mild" if any(k in t for k in _DNBI_MILD_KW) else "moderate"

# Contain a surgical word but do not call for damage-control surgery at Role 2 (eye injuries are shielded and
# evacuated; dengue "hemorrhagic" fever is medical).
_NOT_DCS_DESPITE_SURGICAL_WORDS = ("penetrating eye", "hemorrhagic fever")
# Added to the surgical list: any penetrating torso/neck/face/fragment injury, junctional hemorrhage, severe burns.
# PROVISIONAL: clinician review requested (see docs/case-mix-assumptions.md).
_SURGICAL_KW_EXTRA = ["penetrating", "junctional", "fragment wounds", "severe burns", "artery injury", "arterial injury",
                      "multi-system"]

def determine_case_phases(case_type: str, mechanism: str, is_mascal: bool = False, severity: Optional[str] = None) -> List[str]:
    if severity in ("mild", "moderate"):
        return ["DCR", "PCC"]  # an assigned mild or moderate casualty never needs damage-control surgery
    surgical_kw = [
        "amputation", "evisceration", "vascular injury", "hemothorax", "fasciotomy",
        "thoracotomy", "GSW abdomen", "penetrating chest", "penetrating abdominal",
        "pelvic fracture with hemorrhage", "compartment syndrome", "crush syndrome",
        "burns (>30%", "burns (>40%", "severe thermal burns",
        "liver laceration", "splenic laceration", "bilateral femur",
        "penetrating torso", "multi-system blast trauma", "airway compromise",
        "long bone fracture",
    ]
    non_surgical_kw = [
        # Environmental / DNBI
        "dengue", "malaria", "fever", "heat stroke", "hypothermia", "altitude",
        "HAPE", "HACE", "pneumonia", "gastroenteritis", "appendicitis",
        "kidney stones", "combat stress", "dental", "rhabdomyolysis",
        "decompression sickness", "sand fly", "leptospirosis", "cold urticaria",
        # Neuro / head
        "TBI", "concussion", "closed head", "traumatic brain injury",
        # Pulmonary / inhalation (medical management, not DCS)
        "blast lung", "inhalation injury", "CO poisoning", "smoke inhalation",
        "near-drowning", "drowning", "aspiration", "saltwater aspiration",
        # Envenomation / marine
        "envenomation", "jellyfish", "coral",
        # Spinal (stabilisation, not immediate DCS)
        "spinal cord", "C-spine",
    ]

    case_lower = (case_type + " " + mechanism).lower()

    # Precedence matters. The broad non-surgical words ("TBI", "blast lung") used to win, so "TBI with
    # penetrating fragment" and "Junctional hemorrhage ... fragments" lost their surgery phase and, with it,
    # their DCS care pathway. Now: named exceptions, then surgical terms, then the broad non-surgical words.
    for kw in _NOT_DCS_DESPITE_SURGICAL_WORDS:
        if kw in case_lower:
            return ["DCR", "PCC"]
    for kw in surgical_kw + _SURGICAL_KW_EXTRA:
        if kw.lower() in case_lower:
            return ["DCR", "DCS", "PCC"]
    for kw in non_surgical_kw:
        if kw.lower() in case_lower:
            return ["DCR", "PCC"]

    # MASCAL waves produce high-acuity trauma — unmatched defaults to surgical.
    # Routine waves are mixed-acuity — unmatched defaults to non-surgical.
    return ["DCR", "DCS", "PCC"] if is_mascal else ["DCR", "PCC"]

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

CLINICAL FIDELITY REQUIREMENTS:
- Vitals trends must follow the physiology of the injuries and respond to the
  treatments listed in the same phase (e.g., hemorrhage: rising HR and
  narrowing pulse pressure before BP falls, improvement after blood products;
  severe TBI: consider Cushing response; airway compromise: falling SpO2
  before bradycardia). Every timestamp must be explainable by the clinical
  course — no arbitrary numbers.
- Triage uses NATO categories: T1 Immediate, T2 Delayed, T3 Minimal, and
  Expectant (the T4 equivalent). Output exactly one of T1/T2/T3/Expectant.
- Vary patient demographics realistically across cases — age, sex, and
  population (US forces, partner forces, host-nation civilians where the
  scenario supports it). Do not default every patient to a young male Marine.

Set triage_category to "Expectant" only for injuries not survivable with the
resources at hand; use it sparingly. Set disposition to the realistic outcome
after Role 2 care for THIS casualty (RTD for minor, Evac to Role 3 for surgical/
serious, Hold at Role 2 for short observation, Died of Wounds or Expectant for
non-survivable). Do NOT include blood unit counts — those are computed by a
planning factor, not per case.

JSON STRUCTURE:
{
  "meta": {"title": "String", "estimated_duration": "String", "personnel": "String", "target_specialty": "String"},
  "learning_objectives": ["String"],
  "zmist": {"zap": "USE EXACT VALUE PROVIDED IN PROMPT", "mechanism": "String", "injuries": "String", "signs": "String", "treatment": "String"},
  "nine_line": {"line1_location": "String", "line2_freq": "String", "line3_patients_precedence": "String", "line4_equipment": "String", "line5_patients_type": "String", "line6_security": "String", "line7_marking": "String", "line8_nationality": "String", "line9_nbc_terrain": "String"},
  "patient_data": {"demographics": "String", "history": "String", "allergies": "String"},
  "triage_category": "T1/T2/T3/Expectant",
  "disposition": "One of: RTD | Evac to Role 3 | Hold at Role 2 | Died of Wounds | Expectant",
  "phases": {
    "dcr": {"title": "Damage Control Resuscitation", "narrative": "String", "expected_actions": ["String"], "vitals_trend": [{"time": "String", "hr": "String", "bp": "String", "rr": "String", "spo2": "String", "gcs": "String"}], "contingencies": [{"condition": "String", "consequence": "String", "intervention": "String"}]},
    "dcs": null or {"title": "Damage Control Surgery", "narrative": "String", "expected_actions": ["String"], "vitals_trend": [...], "contingencies": [...]},
    "pcc": {"title": "Prolonged Casualty Care", "narrative": "String", "expected_actions": ["String"], "vitals_trend": [...], "contingencies": [...]}
  },
  "labs": {"hgb": "String", "ph": "String", "lactate": "String", "base_excess": "String", "inr": "String"},
  "evacuation": {"transport_type": "String", "priority": "String", "considerations": "String", "handover_notes": "String"},
  "debrief_questions": ["String"]
}"""

def _orders_prompt(profile: Dict, facts: Optional[Dict]) -> str:
    """The provisions of this exercise's MEDROE and Annex Q that bear on this casualty, so the care in the case follows them."""
    if not facts:
        return ""
    e = facts["evac_min"]
    lines = ["ORDERS IN FORCE: the exercise's MEDROE and Annex Q govern the care. Where it is clinically natural, show the team "
             "applying them and name the provision they are using."]
    if profile["disposition"] == "Hold at Role 2":
        lines.append(f"- Holding limit {facts['hold_limit_h']} h (MEDROE): plan reassessments and a disposition before it.")
    if profile["severity"] in ("critical", "severe"):
        lines.append(f"- Blood (Annex Q): {facts['ltowb']} units of LTOWB at the Role 2 at the start; the walking blood bank activates once "
                     "stock is exhausted. Show product choice and transfusion decisions under that constraint.")
    if profile["triage"] == "Expectant":
        lines.append("- MEDROE expectant policy: comfort care, reassess as resources allow, no resuscitation resources diverted.")
    if profile["disposition"] == "Died of Wounds":
        lines.append("- MEDROE died-of-wounds procedures: pronouncement, documentation and handling of remains.")
    if profile["disposition"] == "Evac to Role 3":
        lines.append(f"- Evacuation to Role 3 is requested by precedence (Annex Q): Urgent {e['Urgent']} min, Priority {e['Priority']} min, "
                     f"Routine {e['Routine']} min from the point of injury under this threat posture.")
    return "\n".join(lines) + "\n"

def _profile_prompt(profile: Optional[Dict], ctx: Optional[Dict]) -> str:
    """Requirements assigned in code (see casemix.py) that the model must write the case around."""
    if not profile:
        return ""
    ctx = ctx or {}
    access = profile.get("evac_access", 1.0)
    evac = ("onward evacuation to Role 3 is largely denied or badly delayed; expect prolonged casualty care at Role 2"
            if access < 0.5 else "onward evacuation to Role 3 is contested and limited" if access < 0.8
            else "onward evacuation to Role 3 is available")
    return (
        _orders_prompt(profile, ctx.get("facts")) +
        f"ASSIGNED SEVERITY: {casemix.SEVERITY_PROMPT[profile['severity']]}.\n"
        f"ASSIGNED TRIAGE: {profile['triage']}. Write an injury pattern and physiology that genuinely fit this "
        f"category; triage_category must be exactly \"{profile['triage']}\".\n"
        f"ASSIGNED DISPOSITION: {profile['disposition']}. The case's course must lead there; disposition must be exactly "
        f"\"{profile['disposition']}\".\n"
        f"PATIENT: {casemix.POPULATION_PROMPT[profile['population']]}.\n"
        + (f"OPERATIONAL CONTEXT: {ctx['setting']}; threat level {ctx['threat']}. Make the 9-line security and marking "
           f"lines consistent with it.\n" if ctx.get("setting") else "")
        + f"EVACUATION: {evac}.\n"
        + ("ARRIVAL: at night. Low-light, NVG or blackout conditions affect the LZ marking, what is found on exam and "
           "the care that can be given.\n" if profile.get("night") else "")
    )


def _enforce_profile(data: Dict, profile: Optional[Dict]) -> Dict:
    """The assignment is authoritative: set it on the case whatever the model wrote."""
    if profile:
        data["triage_category"] = profile["triage"]
        data["disposition"] = profile["disposition"]
        data["patient_population"] = profile["population"]
        data["severity"] = profile["severity"]
        if profile["triage"] == "T1":  # a T1 is called in as Urgent, whatever the model wrote
            ev = data.get("evacuation")
            if not isinstance(ev, dict):
                ev = data["evacuation"] = {}
            if "urgent" not in str(ev.get("priority", "")).lower():
                ev["priority"] = "Urgent"
        if profile.get("night"):
            data["arrival_window"] = "night"
    return data


def generate_case_sync(case_type: str, mechanism: str, environment: str, region: str, is_mascal: bool = False, mets: Optional[List[str]] = None,
                       profile: Optional[Dict] = None, ctx: Optional[Dict] = None) -> Dict:
    severity = (profile or {}).get("severity")
    phases = determine_case_phases(case_type, mechanism, is_mascal, severity)
    phase_instr = "This case does NOT require surgery. Only DCR and PCC. Set dcs to null." if phases == ["DCR", "PCC"] else "This case requires surgery. Include DCR, DCS, and PCC."
    if severity in ("mild", "moderate"):
        phase_instr += (f" This is a {severity} injury: keep the DCR phase to initial assessment and treatment (no "
                        f"resuscitation is needed) and keep PCC brief.")

    zap = _new_zap()

    mech_context = MECHANISM_CONTEXT.get(mechanism)
    mets_line = (
        f"Where clinically natural, tie learning objectives to these unit METL tasks: {', '.join(mets[:6])}.\n"
        if mets else ""
    )

    prompt = (
        f"CONTEXT: Role 2 in {environment}, {region}.\n"
        f"CASE: {case_type}\n"
        f"MECHANISM: {mechanism}\n"
        + (f"{mech_context}\n" if mech_context else "")
        + _profile_prompt(profile, ctx)
        + mets_line
        + f"{phase_instr}\n"
        f"ZAP NUMBER: Use exactly '{zap}' as the zap field — do not change it.\n"
        f"Generate the case now."
    )

    data = None
    for attempt in (1, 2):
        response = _call_model(prompt, "case", system=CASE_SYSTEM_PROMPT, json_mode=True)
        try:
            data = jsonfix.loads_lenient(response.text)
            if isinstance(data, dict):
                break
            raise ValueError("case JSON is not an object")
        except (ValueError, TypeError):  # still broken after repair: ask once more before falling back to a template
            if attempt == 2:
                raise
    if isinstance(data.get("zmist"), dict):
        data["zmist"]["zap"] = zap
    return _enforce_profile(data, profile)

def create_fallback_case(case_type: str, mechanism: str, is_trauma: bool = True) -> Dict:
    return {
        "meta": {"title": case_type, "estimated_duration": "30-45 min" if is_trauma else "20-30 min", "personnel": "Medical Team", "target_specialty": "Emergency Medicine" if is_trauma else "Family Physician"},
        "learning_objectives": ["Perform primary survey", "Initiate resuscitation", "Determine evacuation priority"],
        "zmist": {"zap": _new_zap(), "mechanism": mechanism, "injuries": case_type, "signs": "HR 110, BP 100/70" if is_trauma else "HR 88, BP 120/80", "treatment": "IV, O2, monitoring"},
        "nine_line": {"line1_location": "Grid TBD", "line2_freq": "Pri: 123.45", "line3_patients_precedence": "1 Alpha" if is_trauma else "1 Charlie", "line4_equipment": "None", "line5_patients_type": "1 Litter" if is_trauma else "1 Ambulatory", "line6_security": "Secure", "line7_marking": "VS-17", "line8_nationality": "US Military", "line9_nbc_terrain": "None"},
        "patient_data": {"demographics": f"{random.randint(19, 35)} yo male Marine", "history": "No PMH", "allergies": "NKDA"},
        "triage_category": "T2" if is_trauma else "T3",
        "disposition": "Evac to Role 3" if is_trauma else "RTD",
        "phases": {"dcr": {"title": "Damage Control Resuscitation", "narrative": "Patient arrives...", "expected_actions": ["Primary survey", "IV access"], "vitals_trend": [{"time": "0:00", "hr": "110", "bp": "100/70", "rr": "20", "spo2": "95%", "gcs": "14"}], "contingencies": [{"condition": "BP <90", "consequence": "Shock", "intervention": "Blood products"}]}, "dcs": None, "pcc": {"title": "Prolonged Casualty Care", "narrative": "Post-resuscitation...", "expected_actions": ["Monitor", "Pain management"], "vitals_trend": [], "contingencies": []}},
        "labs": {"hgb": "11.2", "ph": "7.32", "lactate": "3.1", "base_excess": "-4", "inr": "1.1"},
        "evacuation": {"transport_type": "MEDEVAC", "priority": "Priority" if is_trauma else "Routine", "considerations": "Monitor vitals", "handover_notes": f"Stable s/p {case_type}"},
        "debrief_questions": ["What were key findings?", "Was resuscitation adequate?", "What would you change?"]
    }

# Document generation
def _day_patients(day) -> int:
    """Effective casualties for a day: routine load plus the MASCAL surge."""
    return day.total_patients + ((day.mascal_patients or 0) if day.mascal else 0)

def _day_waves(day) -> int:
    """Effective wave count: routine waves plus one MASCAL wave when enabled."""
    return day.total_waves + (1 if day.mascal else 0)

def _care_chain_block(config: ExerciseConfig, fragos: Optional[List[Dict]]) -> str:
    if fragos is None:
        return ""
    return ("\nCare chain (patient flow) the exercise cases are built on — describe exactly these echelons, and "
            "note that the listed FRAGOs will modify them:\n"
            + scenario.chain_summary(config, fragos, _transit_min("Priority", config)) + "\n")

def _planning_facts(config: ExerciseConfig) -> Dict:
    """Numbers the schedule is built on. One source for the WARNO, Annex Q, MEDROE, the case prompts and the tree prompts,
    so the documents cannot contradict each other or the exercise."""
    return {"evac_min": {lvl: _transit_min(lvl, config) for lvl in ("Urgent", "Priority", "Routine")},
            "hold_limit_h": casemix.HOLD_LIMIT_HOURS, "ltowb": STARTING_LTOWB_UNITS}

def _facts_text(f: Dict) -> str:
    e = f["evac_min"]
    return ("PLANNING FACTORS (authoritative: every order must state these exactly and must not contradict them):\n"
            f"- Evacuation precedence, point of injury to Role 2 under this threat posture: Urgent {e['Urgent']} min, "
            f"Priority {e['Priority']} min, Routine {e['Routine']} min.\n"
            f"- Role 2 holding limit: {f['hold_limit_h']} hours, then evacuate, return to duty, or manage as expectant / died of wounds.\n"
            f"- Blood: {f['ltowb']} units LTOWB at the Role 2 at the start; the walking blood bank activates once stock is exhausted.\n"
            "- Expectant casualties receive comfort care and are reassessed as resources allow; deaths follow the MEDROE died-of-wounds procedures.")

def _schedule_facts(schedule: List[Dict], cases: List[Dict], config: ExerciseConfig) -> str:
    """What the finished schedule actually asks of the Role 2, written into the orders so they plan for the real load."""
    rows = [r for r in schedule if "arr_raw" in r]
    if not rows:
        return ""
    count = lambda key: {k: sum(1 for c in cases if c.get(key) == k) for k in sorted({c.get(key) for c in cases if c.get(key)})}
    peak = max(rows, key=lambda r: r.get("r2_census", 0))
    held = [int(r.get("r2_dwell") or 0) for r, c in zip(rows, cases) if c.get("disposition") == "Hold at Role 2"]
    serious_blood = sum(int(r.get("blood_units") or 0) for r in rows)
    wbb = next((r for r in rows if r.get("blood_source") == "Walking Blood Bank"), None)
    mascal = [r for r in rows if str(r.get("event", "")).startswith("MASCAL")]
    lines = ["EXERCISE LOAD (from the schedule these orders accompany; plan for these numbers):",
             f"- {len(rows)} casualties. Outcomes: {count('disposition')}. Severity: {count('severity')}.",
             f"- Peak Role 2 census {peak.get('r2_census')} (day {peak['day']}, {peak['time']}) against a planning capacity of {_r2_capacity(config)}.",
             (f"- {len(held)} casualties are held at Role 2; the longest hold is {max(held) / 60:.0f} hours." if held else "- No casualty is held at Role 2."),
             f"- Whole blood: {serious_blood} units drawn in total; " + (f"the LTOWB stock is exhausted at day {wbb['day']} {wbb['time']} and the walking blood bank is in use from then." if wbb else "the LTOWB stock is not exhausted."),
             f"- Night arrivals: {sum(1 for c in cases if c.get('arrival_window') == 'night')}."]
    if mascal:
        lines.append(f"- Mass-casualty surge: {len(mascal)} casualties beginning day {mascal[0]['day']} {mascal[0]['time']}.")
    pop = count("patient_population")
    lines.append(f"- Patients by population: {pop}.")
    return "\n".join(lines) + "\n"

def _situation_text(row: Dict, config: ExerciseConfig) -> str:
    """The Role 2's real state when this casualty arrives, for the decision-tree prompt."""
    before = int(row.get("blood_on_hand") or 0) + int(row.get("blood_units") or 0)
    blood = f"{before} units LTOWB" if before > 0 else "none (LTOWB exhausted, walking blood bank)"
    return (f"SITUATION AT ARRIVAL: Role 2 census {row.get('r2_census')} of a planning capacity of {_r2_capacity(config)}; PACE state "
            f"{row.get('pace_state')} ({row.get('pace_driver')}); whole blood on hand {blood}; holding limit {casemix.HOLD_LIMIT_HOURS} h; "
            "expectant casualties get comfort care per the MEDROE.\n")

def generate_warno(config: ExerciseConfig, fragos: Optional[List[Dict]] = None, load: str = "") -> str:
    prompt = f"""Generate USMC WARNO (5-paragraph order) for:
Exercise: {config.exercise_name}, Duration: {config.duration} days
Unit: {config.supported_unit}, Environment: {config.environment}, Region: {config.region}
Threat: {config.threat_level}, Footprint: {', '.join(config.selected_footprint)}
Days: {'; '.join([f"Day {d.day_number}: {d.tactical_setting}, {_day_patients(d)} cas, {'MASCAL '+d.mascal_etiology if d.mascal else 'No MASCAL'}, {'CBRN' if d.cbrn else ''}, {'Night' if d.night_ops else 'Day'}" for d in config.days])}

{_care_chain_block(config, fragos)}
{_facts_text(_planning_facts(config))}
{load}
Include: 1.SITUATION 2.MISSION 3.EXECUTION 4.ADMIN/LOG 5.CMD/SIG"""
    
    response = _call_model(prompt, "orders")
    return response.text

def generate_annex_q(config: ExerciseConfig, fragos: Optional[List[Dict]] = None, load: str = "") -> str:
    total_cas = sum(_day_patients(d) for d in config.days)
    # Feed the annex the same planning factors the MSEL timeline is built on so
    # the published document can't contradict the schedule it accompanies.
    urgent_t = _transit_min("Urgent", config)
    priority_t = _transit_min("Priority", config)
    routine_t = _transit_min("Routine", config)
    prompt = f"""Generate Annex Q (Health Service Support / Medical Services) to the OPORD for:
Exercise: {config.exercise_name}, Environment: {config.environment}, Region: {config.region}
Threat: {config.threat_level}
Total Casualties: {total_cas} across {config.duration} days, Footprint: {', '.join(config.selected_footprint)}
Specialists: {json.dumps(config.specialists)}

{_facts_text(_planning_facts(config))}
{load}
{_care_chain_block(config, fragos)}
Structure per JP 4-02 / MCWP conventions:
1. SITUATION — medical threat assessment incl. expected DNBI for {config.environment} terrain
2. MISSION
3. EXECUTION — concept of HSS support by phase; MEDEVAC (air/ground platforms, precedence criteria, contested-evacuation mitigations); patient movement and medical regulating; hospitalization and Role 2 holding policy
4. CLASS VIII RESUPPLY AND BLOOD MANAGEMENT — incl. walking blood bank procedures
5. PREVENTIVE MEDICINE
6. DENTAL SERVICES
7. COMBAT AND OPERATIONAL STRESS CONTROL
8. MEDICAL REPORTING AND DOCUMENTATION"""

    response = _call_model(prompt, "orders")
    return response.text

def generate_medroe(config: ExerciseConfig, load: str = "") -> str:
    has_cbrn = any(d.cbrn for d in config.days)
    has_detainee = any(d.detainee_ops for d in config.days)

    prompt = f"""Generate MEDROE (Medical Rules of Engagement) for:
Exercise: {config.exercise_name}, Environment: {config.environment}, Threat: {config.threat_level}
CBRN play: {has_cbrn}, Detainee Ops: {has_detainee}
{casemix.policy_text(casemix.care_policy(config))}
{_facts_text(_planning_facts(config))}
{load}

Include:
- Eligibility and treatment priorities, stating the ELIGIBILITY POLICY above exactly: US forces, partner forces, host-nation civilians, detainee/EPW — care rendered by clinical need per the Geneva Conventions
- Evacuation precedence criteria (Urgent / Priority / Routine) and who may request each
- Role 2 holding policy (maximum holding hours before evacuation or RTD)
- Blood product release authority, incl. walking blood bank activation criteria
- Expectant-casualty management and Died of Wounds procedures
- Documentation requirements
- MASCAL declaration authority and procedures{chr(10) + '- CBRN casualty decontamination-before-treatment rules' if has_cbrn else ''}{chr(10) + '- Detainee care, custody, and medical documentation rules' if has_detainee else ''}"""
    
    response = _call_model(prompt, "orders")
    return response.text

def _road_to_war_fallback(config: "ExerciseConfig") -> str:
    """Templated Road to War video prompt used when the AI call is unavailable."""
    total_cas = sum(_day_patients(d) for d in config.days)
    settings = "; ".join(
        f"Day {d.day_number}: {d.tactical_setting}"
        + (f" — MASCAL ({d.mascal_etiology})" if d.mascal else "")
        for d in config.days
    )
    return f"""ROAD TO WAR — VIDEO GENERATION PROMPT
Exercise: {config.exercise_name}

Paste the block below into Claude to generate an animated "Road to War"
scenario-setting video for this exercise. Edit any bracketed notes first.

------------------------------------------------------------------------
Build a single, self-contained ANIMATED HTML file (inline CSS + JS, no external
files or network requests) that plays as a 90-120 second cinematic "Road to War"
video for the training exercise "{config.exercise_name}". It briefs participants
on the geopolitical backstory leading up to the medical/HSS mission they are
about to rehearse. This is animated HTML — NOT footage from a video-generation
model and no stock video.

SCENARIO FACTS (ground every scene in these):
- Operation: {config.exercise_name}
- Region / theater: {config.region or "[region]"}
- Environment: {config.environment}
- Supported unit: {config.supported_unit}
- Threat level: {config.threat_level}
- Medical footprint deployed: {", ".join(config.selected_footprint) or "[footprint]"}
- Projected casualty load: {total_cas} patients across {len(config.days)} day(s)
- Daily flashpoints: {settings}

HOW TO BUILD IT:
- Animate with CSS keyframes/transitions and animated inline SVG: kinetic
  typography, animated title cards, an animated map (forces massing, sea/air
  lanes closing, weapon-engagement rings), and simple motion graphics.
- VOICEOVER: use the browser Web Speech API (window.speechSynthesis) to read the
  narration aloud, timing the on-screen scenes to the speech. Include a
  full-screen "Begin brief" start button (browsers block autoplay audio) that
  starts both the voiceover and the animation. Show the narration as on-screen
  captions too.
- Desaturated cinematic palette; per-scene durations summing to ~90-120s.
- Optional background music only via the Web Audio API (no external audio).

For EVERY scene, provide the complete word-for-word NARRATION (voiceover) the
speechSynthesis engine will read — the actual lines, not a description.

STRUCTURE:
1. COLD OPEN (~0:00-0:10) — a tense, quiet establishing beat of the {config.environment}
   theater; animated title card "{config.exercise_name}". Include narration.
2. GEOPOLITICAL BACKSTORY (~0:10-0:40) — how tensions in {config.region or "the region"}
   escalated toward conflict; animated map showing forces massing. Include narration.
3. THE FLASHPOINT (~0:40-1:00) — the triggering event that commits the
   {config.supported_unit}; rising tempo, a {config.threat_level} adversary. Include narration.
4. THE MEDICAL PICTURE (~1:00-1:30) — pivot to the HSS challenge: casualty
   flow, MEDEVAC, and the Role 2 mission the audience must be ready for.
   Draw specifics from the exercise's Annex Q (medical concept of support). Include narration.
5. CALL TO ACTION (~1:30-end) — "This is the fight you are training for." Include narration.

MANDATORY: one self-contained animated HTML file with a spoken voiceover and a
full word-for-word narration script (every scene has its spoken lines). Keep it
unclassified and fictional — this is for a training exercise.
------------------------------------------------------------------------
"""

def generate_road_to_war_prompt(config: "ExerciseConfig", annex_text: str = "") -> str:
    """Produce a ready-to-use prompt the user can hand to Claude to generate a
    'Road to War' video tailored to this exercise's Annex Q."""
    total_cas = sum(_day_patients(d) for d in config.days)
    settings = "; ".join(
        f"Day {d.day_number}: {d.tactical_setting}"
        + (f", MASCAL: {d.mascal_etiology}" if d.mascal else "")
        + (", CBRN" if d.cbrn else "")
        for d in config.days
    )
    annex_excerpt = (annex_text or "")[:2500]
    prompt = f"""You are writing a prompt that another person will paste into Claude to
generate a 90-120 second "Road to War" scenario-setting video for a USMC medical
(HSS) training exercise. The video will be produced BY Claude as a single,
self-contained ANIMATED HTML file with a spoken voiceover — NOT footage from a
video-generation model. Write ONLY that prompt — do not write the video/HTML
itself, and do not add commentary before or after.

The prompt you write must:
- Instruct Claude to output ONE self-contained .html file (inline CSS + JS, no
  external files, no network/CDN requests) that plays as an animated Road to War
  video: it establishes the geopolitical backstory escalating to conflict, then
  pivots to the medical threat picture the trainees must be ready for.
- Require the animation to be done with CSS keyframes/transitions and animated
  inline SVG — kinetic typography, animated title cards, an animated map (forces
  massing, sea/air lanes, weapon-engagement rings), and simple motion graphics.
  There is NO live-action footage; do not reference stock video or a video model.
- Require a SPOKEN VOICEOVER using the browser Web Speech API
  (window.speechSynthesis) that reads the narration aloud, advancing/timing the
  on-screen scenes to match the speech. Because browsers block autoplay audio,
  require a full-screen "Begin brief" start button that kicks off both the
  voiceover and the animation on click. Also render the narration as on-screen
  captions/subtitles for accessibility.
- REQUIRE a complete, word-for-word NARRATION (voiceover) script for EVERY
  scene — the actual lines the speechSynthesis engine will read, not a summary.
  This is mandatory: no scene may be left without its spoken narration text.
- Also specify: the scene-by-scene structure (cold open, backstory, flashpoint,
  medical picture, call to action) with per-scene durations that sum to
  ~90-120s, on-screen text/title cards, the desaturated cinematic palette, and
  pacing. (Background music is optional and, if used, must be generated in-page
  via the Web Audio API — no external audio files.)
- Draw the medical picture (casualty flow, MEDEVAC, Role 2 capability) from
  the Annex Q summary provided.
- State that the content is unclassified, fictional, and for training only.

EXERCISE FACTS:
- Operation: {config.exercise_name}
- Region/theater: {config.region}
- Environment: {config.environment}
- Supported unit: {config.supported_unit}
- Threat level: {config.threat_level}
- Medical footprint: {", ".join(config.selected_footprint)}
- Total casualties: {total_cas} across {len(config.days)} day(s)
- Daily settings: {settings}

ANNEX Q (MEDICAL CONCEPT OF SUPPORT) SUMMARY:
{annex_excerpt}

Now write the Road to War video-generation prompt."""
    try:
        response = _call_model(prompt, "orders")
        text = _response_text(response)
        if text:
            header = f"ROAD TO WAR — VIDEO GENERATION PROMPT\nExercise: {config.exercise_name}\n\nPaste the prompt below into Claude to generate the Road to War video.\n\n"
            return header + text
    except HTTPException:
        raise
    except Exception as e:
        print(f"WARNING: road-to-war prompt AI call failed, using fallback: {e}")
    return _road_to_war_fallback(config)

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

def _clock(total_minutes: int) -> str:
    """Minutes-from-midnight -> HHMM, wrapping across midnight."""
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}{total_minutes % 60:02d}"

# --- Evidence-based blood consumption model -------------------------------
# Blood use is right-skewed: most transfused casualties take a few units while a
# minority hit massive / ultra-massive transfusion and consume the majority of
# supply. We model that tail with severity tiers rather than a flat mean.
# Fixed clinical thresholds: massive transfusion (MT) = >=10 RBC units/24h;
# ultra-massive (UMT) = >20 units (StatPearls, Massive Transfusion, NCBI
# Bookshelf NBK499929). Per-casualty planning factors: "The thin red line:
# Blood planning factors...", J Trauma Acute Care Surg 2024 (PMID 38996415).
# Tier values (whole-blood-equivalent) are representative points inside each
# evidence-defined band.
_BLOOD_WBE = {"none": 0, "submassive": 4, "massive": 12, "ultramassive": 24}

# Starting Role 2 low-titer O whole blood (LTOWB) on hand; usage is tracked
# cumulatively against this, and the walking blood bank is flagged once spent.
STARTING_LTOWB_UNITS = 30

# Only clinically hemorrhaging casualties draw blood — derived from the case.
_HEMORRHAGE_KW = ("hemorrhage", "haemorrhage", "amputation", "exsanguination",
                  "junctional", "evisceration", "hemothorax", "haemothorax",
                  "vascular", "gsw", "gunshot", "splenic", "hepatic", "aortic",
                  "pelvic fracture", "mangled", "penetrating abdominal",
                  "penetrating torso", "penetrating chest")
_UMT_KW = ("bilateral", "mangled", "multiple amputation", "multiple amputations",
           "dismounted complex blast", "multi-cavity", "multi cavity", "triple amputation")
_MT_KW = ("amputation", "junctional", "evisceration", "hemothorax", "haemothorax",
          "vascular", "splenic", "hepatic", "aortic", "pelvic fracture",
          "exsanguination", "penetrating abdominal", "penetrating torso", "penetrating chest")

_EXPLICIT_BLEEDING_KW = ("hemorrhage", "haemorrhage", "bleeding", "hemothorax", "haemothorax", "vascular", "splenic", "hepatic",
                       "aortic", "exsanguination")
_NEGATED = re.compile(r"\b(no|not|without|denies|negative for|absence of|ruled out)\b[^.;:]{0,45}?"
                      r"(hemorrhag\w*|haemorrhag\w*|bleeding|hemothorax|haemothorax|amputation|vascular)", re.I)

def _case_text(case: Dict) -> str:
    z = case.get("zmist", {})
    text = f"{z.get('injuries','')} {z.get('mechanism','')} {z.get('treatment','')}"
    return _NEGATED.sub(" ", text).lower()  # "no active hemorrhage" must not read as hemorrhage

def _requires_blood(case: Dict) -> bool:
    """A casualty needs blood if it goes to surgery, is critical or severe, or its injuries describe hemorrhage. Severity
    leads: a mild casualty never draws blood. Derived from the case, never rolled."""
    sev = case.get("severity")
    if sev == "mild":
        return False
    if case.get("phases", {}).get("dcs") is not None:
        return True
    if sev in ("critical", "severe"):
        return True
    if sev is None and case.get("triage_category") == "T1":
        return True
    text = _case_text(case)
    if sev == "moderate":  # an injury name alone ("stable pelvic fracture") is not bleeding: it needs explicit evidence
        return any(k in text for k in _EXPLICIT_BLEEDING_KW)
    return any(k in text for k in _HEMORRHAGE_KW)

def _blood_tier(case: Dict) -> str:
    """Classify transfusion severity from case clinical facts."""
    if not _requires_blood(case):
        return "none"
    text = _case_text(case)
    sev = case.get("severity")
    surgical = case.get("phases", {}).get("dcs") is not None
    major = any(k in text for k in _MT_KW)
    if any(k in text for k in _UMT_KW) and major and sev in (None, "critical"):
        return "ultramassive"  # e.g. bilateral amputation: needs both a multiplicity word and a major-hemorrhage term
    if sev == "moderate":
        return "submassive"
    if sev == "critical" or surgical or major or (sev is None and case.get("triage_category") == "T1"):
        return "massive"
    return "submassive"

def _blood_units(case: Dict) -> int:
    return _BLOOD_WBE[_blood_tier(case)]

# --- Evacuation transit + Role 2 dwell, driven by exercise parameters ------
# A few discrete options selected from the overall exercise parameters, not
# fixed brackets: contested/near-peer theaters and harsh terrain lengthen the
# POI->Role 2 timeline; MASCAL surge lengthens Role 2 holding.
def _threat_evac_mult(threat: str) -> float:
    t = (threat or "").lower()
    if "peer" in t:        # Peer/Near-Peer — contested/denied MEDEVAC
        return 3.0
    if "hybrid" in t:
        return 2.0
    if "irregular" in t:
        return 1.5
    return 1.0             # HADR/Permissive

_TERRAIN_ADD = {"urban": 0, "desert": 10, "littoral": 20, "maritime": 30,
                "jungle": 30, "mountain": 40, "arctic": 45}

def _transit_min(precedence: str, config) -> int:
    """POI->Role 2 transit: precedence base x threat posture + terrain."""
    p = (precedence or "").lower()
    base = 30 if "urgent" in p else 60 if "priority" in p else 120
    add = _TERRAIN_ADD.get((getattr(config, "environment", "") or "").lower(), 15)
    return int(round(base * _threat_evac_mult(getattr(config, "threat_level", "")) + add))

def _dwell_min(case: Dict, is_mascal_wave: bool = False) -> int:
    """Role 2 treatment/OR occupancy; MASCAL surge degrades throughput."""
    phases = case.get("phases", {}) or {}
    base = 150 if phases.get("dcs") else 90 if phases.get("pcc") else 45
    return int(round(base * (1.5 if is_mascal_wave else 1.0)))

# --- CSC PACE state (see docs/csc-pace/README.md) -------------------------
# Recommended Role 2 care state on the running timeline, per the unit's CSC PACE
# framework: PRIMARY / ALTERNATE / CONTINGENCY / EMERGENCY (JTS best / better /
# minimum / below-minimum). Each transition trigger maps to a signal the exercise
# already computes; the state at any point is the worst trigger tripped ("OR"
# logic). Resupply/comms triggers aren't exercise inputs, so contested logistics
# is inferred from threat level (framework Assumption 1). Role 2 capacity for the
# saturation trigger is derived from footprint + surgical/nursing staff.
_PACE_STATES = ["PRIMARY", "ALTERNATE", "CONTINGENCY", "EMERGENCY"]

# Baseline conditions (theater-level, capped at ALTERNATE): a degraded corridor,
# contested resupply, or a gapped surgical billet is a starting posture, not by
# itself an allocation (CONTINGENCY) decision. CONTINGENCY and above come from
# the DYNAMIC triggers — MASCAL patient load exceeding throughput, and blood
# supply exhaustion — which is what the framework actually keys those states on.
def _logistics_pace(config) -> int:
    """Contested resupply inferred from threat (framework Assumption 1): peer/
    hybrid theaters assume resupply slipping past doctrinal -> ALTERNATE floor."""
    t = (getattr(config, "threat_level", "") or "").lower()
    return 1 if ("peer" in t or "hybrid" in t) else 0

def _evac_corridor_pace(config) -> int:
    """Evac-corridor condition from threat posture + terrain (a reference-priority
    transit), capped at ALTERNATE — 'evac slipping doctrinal'."""
    return 1 if _transit_min("Priority", config) > 90 else 0

def _staff_pace_floor(config) -> int:
    """PRIMARY requires dual surgical teams; a single team is a gapped billet."""
    surgeons = (getattr(config, "specialists", {}) or {}).get("General Surgery", 0)
    return 0 if surgeons >= 2 else 1

def _r2_capacity(config) -> int:
    """Concurrent Role 2 holding capacity from footprint + staff (OR tables from
    surgical teams, nursing-held beds). Planning estimate for the saturation
    trigger only."""
    spec = getattr(config, "specialists", {}) or {}
    or_tables = max(1, spec.get("General Surgery", 0))
    nurses = sum(spec.get(k, 0) for k in ("ICU Nurse", "ER Nurse", "ERC Nurse", "Med Surg Nurse"))
    footprint = len(getattr(config, "selected_footprint", []) or [])
    return max(4, or_tables * 2 + nurses + footprint)

def _blood_pace(source: str, blood_cum: int) -> int:
    """WBB active = ALTERNATE; sustained deficit beyond a second stock = allocation
    (CONTINGENCY)."""
    if source == "Walking Blood Bank":
        return 2 if blood_cum > 2 * STARTING_LTOWB_UNITS else 1
    return 0

def annotate_pace_states(schedule: List[Dict], config) -> None:
    """Second pass: assign each casualty row a recommended PACE state + the trigger
    that set it, using the whole timeline for concurrent Role 2 census."""
    capacity = _r2_capacity(config)
    base_sigs = {
        "contested logistics": _logistics_pace(config),
        "evac corridor": _evac_corridor_pace(config),
        "staff (single surgical team)": _staff_pace_floor(config),
    }
    loaded = [r for r in schedule if "arr_raw" in r]

    def at(row: Dict, key: str) -> int:  # absolute minute, so a casualty held overnight still counts the next day
        return (row["day"] - 1) * 24 * 60 + row[key]
    for r in schedule:
        if "arr_raw" not in r:  # CBRN/detainee inject rows carry no clinical load
            continue
        census = sum(1 for o in loaded if at(o, "arr_raw") <= at(r, "arr_raw") < at(o, "cleared_raw"))
        sigs = dict(base_sigs)
        sigs["blood/WBB"] = _blood_pace(r.get("blood_source", ""), r.get("blood_cum", 0))
        if census > capacity:  # MASCAL / patient load exceeds throughput
            sigs[f"saturation {census}/{capacity}"] = 2
        score = max(sigs.values())
        r["pace_state"] = _PACE_STATES[score]
        r["pace_driver"] = ", ".join(k for k, v in sigs.items() if v == score and v > 0) or "nominal"
        r["r2_census"] = census

def _route_and_inbound(case: Dict, is_mascal_wave: bool) -> tuple:
    """Decide route + whether the casualty is called in to the COC, using only
    facts already in the case (triage, surgical need, stated transport). No dice:
    minor DNBI (T3/T4, non-surgical) self-present as walking wounded; everyone
    else — and all MASCAL casualties — are inbound with a COC call + 9-line.
    Expectant casualties never self-present: they arrive by litter, called in."""
    triage = case.get("triage_category", "T2")
    surgical = case.get("phases", {}).get("dcs") is not None
    transport = (case.get("evacuation", {}).get("transport_type") or "").strip()
    inbound = is_mascal_wave or surgical or triage in ("T1", "T2", "T4", "Expectant")
    if not inbound:
        return "Walk-in", False
    if transport and not any(w in transport.lower() for w in ("walk", "ambul", "self")):
        return transport, True
    return ("Litter" if is_mascal_wave else "MEDEVAC"), True

def _case_teo(case: Dict, is_mascal_wave: bool = False) -> Dict:
    """Flatten the case's own clinical detail for the T&EO sheet. Pulls straight
    from the generated case — nothing is invented here."""
    phases = case.get("phases", {}) or {}
    def _collect(field):
        out = []
        for pk in ("dcr", "dcs", "pcc"):
            ph = phases.get(pk)
            if isinstance(ph, dict):
                out += ph.get(field, []) or []
        return out
    care_level = "DCR" + ("+DCS" if phases.get("dcs") else "") + ("+PCC" if phases.get("pcc") else "")
    contingencies = [c for c in _collect("contingencies") if isinstance(c, dict)]
    evac = case.get("evacuation", {}) or {}
    tier = _blood_tier(case)
    return {
        "zap": case.get("zmist", {}).get("zap", ""),
        "surgical": "Yes" if phases.get("dcs") else "No",
        "care_level": care_level,
        "disposition": case.get("disposition", ""),
        "blood_units": _BLOOD_WBE[tier],
        "blood_tier": {"none": "", "submassive": "Submassive", "massive": "Massive (MT)", "ultramassive": "Ultramassive (UMT)"}[tier],
        "r2_dwell": _dwell_min(case, is_mascal_wave),
        "evac_precedence": evac.get("priority", ""),
        "onward": evac.get("transport_type", ""),
        "signs": case.get("zmist", {}).get("signs", ""),
        "handover": evac.get("handover_notes", ""),
        "expected": " • ".join(str(a) for a in _collect("expected_actions")),
        "contingencies": " | ".join(
            f"IF {c.get('condition','')} → {c.get('consequence','')} → {c.get('intervention','')}"
            for c in contingencies
        ),
        "debrief": " • ".join(case.get("debrief_questions", []) or []),
    }

def generate_schedule(config: ExerciseConfig, case_pools: Dict[tuple, List[Dict]], draw: Optional[Dict] = None) -> tuple:
    """Build the MSEL timeline, drawing each slot's case from the pool it was
    generated for: (day_number, is_mascal) -> cases. This keeps MASCAL-etiology
    cases inside that day's MASCAL wave (a UAS-strike case never fills a
    routine DNBI slot and vice versa). All timing math is unchanged — pooling
    only decides WHICH case fills a slot, never WHEN the slot occurs.

    Returns (schedule, ordered_cases): ordered_cases lists cases in schedule
    order so 'Case N' serials in the MSEL match Case N in the case book."""
    schedule = []
    ordered_cases: List[Dict] = []
    assigned_counts = {}
    blood_used = 0  # cumulative whole-blood-equivalent units drawn, exercise-wide

    def _draw(day_number: int, is_mascal: bool, night: bool = False) -> Optional[Dict]:
        pool = case_pools.get((day_number, is_mascal))
        if pool:
            # Cases written for night arrival fill the night wave and the rest fill the day waves.
            for k in range(len(pool) - 1, -1, -1):
                if (pool[k].get("arrival_window") == "night") == night:
                    return pool.pop(k)
            return pool.pop()
        # Defensive: never drop a scheduled slot — borrow from any non-empty pool.
        for p in case_pools.values():
            if p:
                return p.pop()
        return None

    for day in config.days:
        if day.cbrn:
            schedule.append({"day": day.day_number, "event": "DRILL", "coc_hit_time": "N/A", "time": "0900", "nine_line_time": "N/A", "route": "N/A", "triage_cat": "N/A", "mechanism": "CBRN DRILL", "brief_description": "1-hour CBRN exercise - All clinical ops paused", "evaluator": "All Hands", "case_num": "DRILL"})
        if day.detainee_ops:
            schedule.append({"day": day.day_number, "event": "INJECT", "coc_hit_time": "N/A", "time": "1300", "nine_line_time": "N/A", "route": "N/A", "triage_cat": "N/A", "mechanism": "DETAINEE / EPW", "brief_description": "Detainee/EPW presents for care — apply detainee handling + MEDROE", "evaluator": "All Hands", "case_num": "INJECT"})

        # Night ops means SOME casualties arrive at night, not all care at night:
        # carve a share of the routine load into a dedicated night wave.
        night_pts = min(max(1, round(day.total_patients * 0.35)), day.total_patients) if day.night_ops else 0
        day_pts = day.total_patients - night_pts

        # Routine day waves carry the daytime load; a MASCAL adds one more wave
        # on top with its own surge count (additive, not an override).
        base_waves = max(day.total_waves, 1)
        pts_per_wave = day_pts // base_waves
        remainder = day_pts % base_waves
        day_waves = [{"pts": pts_per_wave + (1 if w < remainder else 0), "mascal": False}
                     for w in range(base_waves)]
        if day.mascal and day.mascal_patients:
            day_waves.append({"pts": day.mascal_patients, "mascal": True})
        night_waves = [{"pts": night_pts, "mascal": False, "night": True}] if night_pts else []

        # Day window 0700-1900 (12h); night window 2000-0200 (6h).
        for group, start_min, span_min in ((day_waves, 7 * 60, 12 * 60), (night_waves, 20 * 60, 6 * 60)):
            interval = span_min / (len(group) + 1) if group else 0
            for k, w in enumerate(group):
                w["start_min"] = start_min + int(interval * (k + 1))

        # Emit chronologically: day waves, then the night wave.
        for w in day_waves + night_waves:
            wave_pts = w["pts"]
            is_mascal_wave = w["mascal"]
            time_spread = 45 if is_mascal_wave else 60

            for p in range(wave_pts):
                case = _draw(day.day_number, is_mascal_wave, w.get("night", False))
                if case is None:
                    break

                # MASCAL is a compressed spike then a tail (front-loaded); routine
                # casualties spread evenly across the wave.
                frac = p / max(wave_pts, 1)
                offset = int((frac ** 2) * 40) if is_mascal_wave else int(frac * 60)
                arr_total = w["start_min"] + offset

                # Route + COC call are derived from the case, not rolled at random.
                route, inbound = _route_and_inbound(case, is_mascal_wave)
                if inbound:
                    coc_hit_time = _clock(arr_total - 45)
                    nine_time = _clock(arr_total - 30)
                else:
                    coc_hit_time = "N/A"
                    nine_time = "N/A"

                if is_mascal_wave:
                    event = f"MASCAL ({day.mascal_etiology})" if day.mascal_etiology else "MASCAL"
                else:
                    event = "Routine"

                teo = _case_teo(case, is_mascal_wave)
                if draw:  # time in Role 2 follows the assigned outcome (hold, return to duty, wait for evacuation, death)
                    zap = int(re.sub(r"\D", "", str((case.get("zmist") or {}).get("zap", ""))) or 0)
                    teo["r2_dwell"] = casemix.dwell_minutes(case.get("disposition", ""), teo["r2_dwell"],
                                                            casemix.evac_access(config, day), draw["params"],
                                                            random.Random(draw["seed"] * 31 + zap))
                # Timeline: point of injury (golden-hour anchor) back from arrival
                # by the parameter-driven transit; Role 2 cleared = arrival + dwell.
                transit = _transit_min(teo["evac_precedence"], config) if inbound else 10  # a walk-in has no MEDEVAC leg
                poi_time = _clock(arr_total - transit)
                cleared_raw = arr_total + teo["r2_dwell"]
                cleared = _clock(cleared_raw)

                # Running blood ledger: draw against LTOWB stock, then walking
                # blood bank once the on-hand supply is spent.
                units = teo["blood_units"]
                blood_used += units
                on_hand = max(0, STARTING_LTOWB_UNITS - blood_used)
                if units == 0:
                    blood_source = ""
                elif blood_used <= STARTING_LTOWB_UNITS:
                    blood_source = "LTOWB"
                else:
                    blood_source = "Walking Blood Bank"

                schedule.append({
                    "day": day.day_number,
                    "event": event,
                    "poi_time": poi_time,
                    "cleared": cleared,
                    "coc_hit_time": coc_hit_time,
                    "time": _clock(arr_total),
                    "nine_line_time": nine_time,
                    "route": route,
                    "triage_cat": case.get("triage_category", "T2"),
                    "mechanism": case.get("zmist", {}).get("mechanism", "Unknown")[:50],
                    "brief_description": case.get("zmist", {}).get("injuries", "")[:80],
                    "evaluator": assign_evaluator(case, config.specialists, assigned_counts),
                    "case_num": f"Case {len(ordered_cases) + 1}",
                    "blood_cum": blood_used,
                    "blood_on_hand": on_hand,
                    "blood_source": blood_source,
                    "transit_min": transit,
                    "arr_raw": arr_total,
                    "cleared_raw": cleared_raw,
                    **teo,
                })
                ordered_cases.append(case)

    # A Detainee/EPW inject is the day's first enemy-combatant case, not a separate event hours away from it.
    case_rows = [r for r in schedule if str(r.get("case_num", "")).startswith("Case ")]
    for inj in (r for r in schedule if r.get("event") == "INJECT"):
        for row in case_rows:
            n = int(row["case_num"].split()[1])
            if row["day"] == inj["day"] and ordered_cases[n - 1].get("patient_population") == "enemy":
                inj["time"] = row["time"]
                inj["brief_description"] += f" (Case {n})"
                break
    annotate_pace_states(schedule, config)
    return schedule, ordered_cases

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

def _autosize(ws, df):
    for idx, col in enumerate(df.columns):
        body = df[col].astype(str).map(len).max() if len(df) else 0
        max_len = max(int(body or 0), len(str(col))) + 2
        ws.column_dimensions[chr(65 + idx)].width = min(max_len, 60)

def _sheet(df: pd.DataFrame, source_cols, labels) -> pd.DataFrame:
    """Select/relabel columns, filling any missing ones (older stored exercises
    predate some keys) so re-download never breaks."""
    for c in source_cols:
        if c not in df.columns:
            df[c] = ""
    out = df[source_cols].copy()
    # Inject rows (CBRN/detainee) lack the clinical keys -> NaN; blank them.
    out = out.fillna("")
    out.columns = labels
    return out

def _parse_hhmm(s) -> Optional[int]:
    """HHMM clock string -> minutes. Times before 0400 are treated as
    past-midnight (night wave runs 2000-0200) so same-day interval math works."""
    try:
        s = str(s).strip()
        if len(s) == 4 and s.isdigit():
            m = int(s[:2]) * 60 + int(s[2:])
            return m + 24 * 60 if m < 4 * 60 else m
    except Exception:
        pass
    return None

def _capacity_analysis(schedule: List[Dict], config: ExerciseConfig) -> pd.DataFrame:
    """Planner-facing capacity vs demand roll-up, computed purely from the
    arrival/dwell times already on the schedule — it reports on the timeline,
    it never changes it."""
    specialists = config.specialists or {}
    surgeons = specialists.get("General Surgery", 0) + specialists.get("Orthopaedic Surgery", 0)

    by_day: Dict[Any, List[tuple]] = {}
    eval_load: Dict[Any, Dict[str, int]] = {}
    for r in schedule:
        if str(r.get("case_num", "")).upper() in ("DRILL", "INJECT"):
            continue
        arr = _parse_hhmm(r.get("time"))
        if arr is None:
            continue
        try:
            dwell = int(float(r.get("r2_dwell") or 0))
        except (TypeError, ValueError):
            dwell = 0
        if not dwell:
            clr = _parse_hhmm(r.get("cleared"))
            dwell = (clr - arr) if (clr is not None and clr > arr) else 60
        surgical = str(r.get("surgical", "")).strip().lower() == "yes"
        by_day.setdefault(r.get("day"), []).append((arr, arr + dwell, surgical))
        ev = r.get("evaluator") or ""
        if ev and ev not in ("All Hands", "Unassigned"):
            eval_load.setdefault(r.get("day"), {})[ev] = eval_load.setdefault(r.get("day"), {}).get(ev, 0) + 1

    # Peak (worst) recommended PACE state per day, with the trigger that set it.
    day_pace: Dict[Any, tuple] = {}
    for r in schedule:
        ps = r.get("pace_state")
        if not ps or ps not in _PACE_STATES:
            continue
        idx = _PACE_STATES.index(ps)
        if idx >= day_pace.get(r.get("day"), (-1, ""))[0]:
            day_pace[r.get("day")] = (idx, r.get("pace_driver", ""))

    rows = []
    for day in sorted(by_day):
        intervals = by_day[day]
        # Sweep-line over arrival/cleared events for peak concurrent load.
        events = sorted([(a, 1, s) for a, c, s in intervals] + [(c, -1, s) for a, c, s in intervals],
                        key=lambda e: (e[0], e[1]))
        cur = peak = cur_s = peak_s = 0
        peak_t = peak_s_t = 0
        for t, d, s in events:
            cur += d
            if s:
                cur_s += d
            if cur > peak:
                peak, peak_t = cur, t
            if cur_s > peak_s:
                peak_s, peak_s_t = cur_s, t
        if day in day_pace:
            idx, drv = day_pace[day]
            rows.append({"Day": day, "Metric": "Recommended PACE state (peak)",
                         "Value": f"{_PACE_STATES[idx]}" + (f" — {drv}" if drv else ""),
                         "Flag": "DEGRADED" if idx >= 2 else ("ELEVATED" if idx == 1 else "")})
        rows.append({"Day": day, "Metric": "Peak concurrent census",
                     "Value": f"{peak} patients at {_clock(peak_t)}", "Flag": ""})
        rows.append({"Day": day, "Metric": "Peak concurrent surgical cases",
                     "Value": f"{peak_s} at {_clock(peak_s_t)} (surgeons on hand: {surgeons})",
                     "Flag": "EXCEEDS SURGEON COUNT" if surgeons and peak_s > surgeons else ""})
        if eval_load.get(day):
            ev, n = max(eval_load[day].items(), key=lambda kv: kv[1])
            rows.append({"Day": day, "Metric": "Busiest evaluator",
                         "Value": f"{ev} — {n} cases", "Flag": "HIGH LOAD" if n > 6 else ""})

    total_blood = 0
    for r in schedule:
        try:
            total_blood += int(float(r.get("blood_units") or 0))
        except (TypeError, ValueError):
            pass
    deficit = max(0, total_blood - STARTING_LTOWB_UNITS)
    rows.append({"Day": "All", "Metric": "Blood demand vs LTOWB stock",
                 "Value": f"{total_blood} WBE units vs {STARTING_LTOWB_UNITS} on hand",
                 "Flag": f"WALKING BLOOD BANK — {deficit} u shortfall" if deficit else ""})
    return pd.DataFrame(rows) if rows else pd.DataFrame({"Day": [], "Metric": [], "Value": [], "Flag": []})

def create_msel(schedule: List[Dict], config: ExerciseConfig) -> BytesIO:
    raw = pd.DataFrame(schedule)

    # Inject rows lack the numeric blood/dwell keys -> NaN floats the column and
    # casualty counts render like "24.0". Show clean ints, blank for injects.
    for col in ("blood_units", "blood_cum", "blood_on_hand", "r2_dwell", "r2_census"):
        if col in raw.columns:
            raw[col] = raw[col].map(lambda v: "" if (v is None or (isinstance(v, float) and pd.isna(v)) or v == "") else int(float(v)))

    # Sheet 1 — MSEL timeline (what EXCON runs the exercise from). The PACE column
    # is the recommended Role 2 CSC state at that point on the timeline.
    msel = _sheet(
        raw,
        ['day', 'event', 'pace_state', 'poi_time', 'coc_hit_time', 'nine_line_time', 'time', 'route', 'evac_precedence', 'triage_cat', 'surgical', 'disposition', 'zap', 'mechanism', 'brief_description', 'evaluator', 'case_num'],
        ['Day', 'Event', 'PACE', 'POI Time', 'COC Hit Time', '9-Line Time', 'Arrival', 'Route', 'Precedence', 'Triage', 'Surgical', 'Disposition', 'ZAP #', 'Mechanism', 'Description', 'Evaluator', 'Serial'],
    )

    # Sheet 2 — T&EO / Controller detail (per-casualty, straight from the case).
    teo = _sheet(
        raw,
        ['day', 'time', 'cleared', 'pace_state', 'pace_driver', 'r2_census', 'zap', 'triage_cat', 'pathway', 'care_chain', 'fragos_in_force', 'care_level', 'surgical', 'blood_units', 'blood_tier', 'r2_dwell', 'disposition', 'signs', 'onward', 'handover', 'expected', 'contingencies', 'debrief', 'evaluator'],
        ['Day', 'Arrival', 'R2 Cleared', 'PACE', 'PACE Trigger', 'R2 Census', 'ZAP #', 'Triage', 'Pathway', 'Care Chain', 'FRAGOs', 'Care Level', 'Surgical', 'Blood (WBE u)', 'Blood Tier', 'R2 Dwell (min)', 'Disposition', 'Initial Signs', 'Onward Tpt', 'Handover', 'Expected Key Actions', 'Contingencies (If/Then)', 'Debrief Prompts', 'Evaluator'],
    )

    # Sheet 3 — Blood Ledger (chronological running consumption vs LTOWB stock).
    if "blood_units" in raw.columns:
        drew = raw[pd.to_numeric(raw["blood_units"], errors="coerce").fillna(0) > 0].copy()
    else:
        drew = raw.iloc[0:0].copy()
    ledger = _sheet(
        drew,
        ['day', 'time', 'zap', 'triage_cat', 'blood_tier', 'blood_units', 'blood_cum', 'blood_on_hand', 'blood_source'],
        ['Day', 'Arrival', 'ZAP #', 'Triage', 'Tier', 'Units', 'Cum Used', 'On Hand', 'Source'],
    )

    # Sheet 4 — Objectives (exercise METL / footprint / personnel + blood summary).
    obj_data = []
    for m in config.selected_mets:
        obj_data.append({"Category": "METL Task", "Item": m})
    for f in config.selected_footprint:
        obj_data.append({"Category": "Footprint", "Item": f})
    for k, v in (config.specialists or {}).items():
        if v:
            obj_data.append({"Category": "Personnel", "Item": f"{k}: {v}"})
    if "blood_units" in raw.columns:
        bu = pd.to_numeric(raw["blood_units"], errors="coerce").fillna(0)
        total_blood = int(bu.sum())
        transfused = int((bu > 0).sum())
        tiers = raw.get("blood_tier")
        mt = int((tiers == "Massive (MT)").sum()) if tiers is not None else 0
        umt = int((tiers == "Ultramassive (UMT)").sum()) if tiers is not None else 0
        deficit = max(0, total_blood - STARTING_LTOWB_UNITS)
        obj_data.append({"Category": "Blood Supply", "Item": f"On hand at start: {STARTING_LTOWB_UNITS} u LTOWB"})
        obj_data.append({"Category": "Blood Demand", "Item": f"{total_blood} WBE units — {transfused} transfused ({mt} MT, {umt} UMT)"})
        obj_data.append({"Category": "Blood Status", "Item": (
            f"Walking Blood Bank REQUIRED — {deficit} u shortfall beyond stock" if deficit > 0
            else f"Within stock — {STARTING_LTOWB_UNITS - total_blood} u remaining")})
    objectives = pd.DataFrame(obj_data) if obj_data else pd.DataFrame({"Category": [], "Item": []})

    # Sheet 5 — Planner Analysis (capacity vs demand, derived from the timeline).
    analysis = _capacity_analysis(schedule, config)

    # Sheet 6 — PACE Posture reference: the pre-briefed actions per CSC state
    # (from docs/csc-pace). Static; links a timeline PACE state to what each
    # actor does. Marked with which states the exercise actually reached.
    reached = {r.get("pace_state") for r in schedule if r.get("pace_state")}
    posture = pd.DataFrame([
        {"PACE State": "PRIMARY", "JTS Tier": "Best", "Reached": "◀ reached" if "PRIMARY" in reached else "",
         "Command": "Green on COP; standard authorities; no deviation from CPG",
         "Provider": "Standard care per JTS CPG; full surgical capability; component blood per MTP",
         "Logistics": "Routine resupply request; Class VIII <24h cycle; no prioritization needed"},
        {"PACE State": "ALTERNATE", "JTS Tier": "Better", "Reached": "◀ reached" if "ALTERNATE" in reached else "",
         "Command": "Yellow on COP; substitution brief filed; trigger thresholds armed",
         "Provider": "Pre-briefed substitutions; LTOWB if components short; capability conserved",
         "Logistics": "Targeted request for named shortfall items; walking blood bank activated"},
        {"PACE State": "CONTINGENCY", "JTS Tier": "Minimum", "Reached": "◀ reached" if "CONTINGENCY" in reached else "",
         "Command": "Red on COP; CO/CMO activates allocation authority; decision-maker engaged",
         "Provider": "Reverse triage active; advanced care withdrawn per protocol; allocation framework anchors decisions",
         "Logistics": "Critical asset request; priority on evac corridor; cross-loading evaluated"},
        {"PACE State": "EMERGENCY", "JTS Tier": "Below minimum", "Reached": "◀ reached" if "EMERGENCY" in reached else "",
         "Command": "Black on COP; CO/CMO pre-brief in full effect; recovery triggers monitored",
         "Provider": "Survivability care only; pre-briefed boundaries; document for recovery",
         "Logistics": "No outbound request possible; operating autonomously; recovery cued to first restored channel"},
    ])

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for name, d in (('MSEL', msel), ('T&EO', teo), ('Blood Ledger', ledger), ('Objectives', objectives), ('Planner Analysis', analysis), ('PACE Posture', posture)):
            d.to_excel(writer, index=False, sheet_name=name)
            _autosize(writer.sheets[name], d)
    output.seek(0)
    return output

# API Endpoints
@app.get("/")
async def root():
    return {"status": "Role 2 Exercise Builder API", "version": "2.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/health/ai")
def ai_health(request: Request, probe: bool = False):
    """Is Gemini working? Without ?probe=1 this only reports the outcome of the latest real call (free).
    With it, make one tiny live call (about $0.00001; limited to 6 an hour per client) and say what failed."""
    result: Dict[str, Any] = {"configured_model": GEMINI_MODEL, "active_model": _active_model}
    if probe:
        _check_client_rate(request, "aiprobe", 6, timedelta(hours=1), "AI probe limit reached — try again later.")
        started = time.monotonic()
        try:
            _call_model("Reply with the single word OK.", "probe")
            result["probe"] = {"ok": True, "ms": round((time.monotonic() - started) * 1000)}
        except HTTPException as e:  # e.g. GEMINI_API_KEY not set
            result["probe"] = {"ok": False, "kind": "no_key" if e.status_code == 503 else "other"}
        except AIError as e:
            result["probe"] = {"ok": False, "kind": e.kind, "meaning": AI_KIND_TEXT.get(e.kind, "an AI error occurred"),
                               "error_type": e.error_type, "http_code": e.http_code, "status": e.status}
        result["active_model"] = _active_model
    with _ai_lock:
        result["last_call"] = dict(_ai_state)
    return result

class NameRequest(BaseModel):
    environment: str = Field(default="General", max_length=40)
    region: str = Field(default="", max_length=80)
    threatLevel: str = Field(default="", max_length=40)
    supportedUnit: str = Field(default="Medical", max_length=80)


@app.post("/generate-name")
async def generate_name_endpoint(data: NameRequest, request: Request):
    _check_client_rate(request, "name", MAX_NAMES_PER_CLIENT_PER_HOUR, timedelta(hours=1),
                       "Too many name requests — try again later.")
    env = data.environment
    region = data.region
    threat = data.threatLevel
    unit = data.supportedUnit
    
    prompt = f"""Generate one military exercise name for a USMC {unit} HSS training exercise in {env} terrain, {region}, facing a {threat} threat.

Format: "Operation [Descriptor] [Noun]" — 2 words after Operation, or occasionally 3 if it flows well.

Structure:
- Descriptor: an adjective that evokes the operational environment or tempo (e.g., Silent, Relentless, Fractured, Bleeding, Stalking, Burning, Severed, Hollow, Bitter)
- Noun: pick ONE category — fierce animal (Viper, Jackal, Condor, Wolverine, Mako, Lynx, Mantis), masculine emotion (Fury, Wrath, Valor, Resolve, Defiance, Reckoning, Anguish), or military/defense concept (Rampart, Bastion, Crucible, Gauntlet, Threshold, Salient, Bulwark)

Banned words: Iron, Steel, Crimson, Eagle, Thunder, Guardian, Shield, Ghost, Phantom, Storm, Black, Red, Blue, Dragon, Tiger, Wolf, Hawk, Viper (if region is not maritime)

Return ONLY the operation name. Nothing else. Seed: {random.random()}"""
    # The violent descriptors in this prompt can trip Gemini's safety filters,
    # which makes response.text raise and the endpoint 500 ("not fetching").
    # Relax the filters where allowed, extract text safely, and fall back to a
    # curated local name so the button always returns a usable result.
    name = ""
    try:
        try:
            from google.genai import types
            gen_config = types.GenerateContentConfig(
                temperature=1.3,
                safety_settings=[
                    types.SafetySetting(category=c, threshold="BLOCK_NONE")
                    for c in (
                        "HARM_CATEGORY_HARASSMENT",
                        "HARM_CATEGORY_HATE_SPEECH",
                        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "HARM_CATEGORY_DANGEROUS_CONTENT",
                    )
                ],
            )
            response = get_client().models.generate_content(
                model=_active_model, contents=prompt, config=gen_config
            )
        except Exception:
            # Older/newer SDKs may not accept the config shape above — retry plain.
            response = get_client().models.generate_content(
                model=_active_model, contents=prompt
            )
        name = _response_text(response).replace('"', '').replace("'", "")
        _note_ai(bool(name), None if name else "blocked")
        # Models sometimes return a short explanation before the name.
        name = name.splitlines()[0].strip() if name else ""
    except HTTPException:
        raise  # e.g. GEMINI_API_KEY missing — surface it as-is
    except Exception as e:
        _note_ai(False, _classify_ai_error(e))
        print(f"WARNING: generate-name AI call failed, using local fallback: {e}")

    if not name:
        name = _local_exercise_name(region)
    if not name.startswith("Operation"):
        name = f"Operation {name}"
    return {"name": name}

class _Deck:
    """Draw from a list without replacement: a repeat only occurs once every entry has been used, then it reshuffles."""
    def __init__(self, items: List[str], rng: Optional[random.Random] = None):
        self.items, self._pile, self._rng = list(items), [], rng or random

    def draw(self) -> str:
        if not self._pile:
            self._pile = self._rng.sample(self.items, len(self.items))
        return self._pile.pop()


def _build_case_tasks(config: ExerciseConfig, draw: Optional[Dict] = None) -> List[tuple]:
    """Return one (day_number, case_type, mechanism, is_trauma, is_mascal, severity) tuple per patient.

    Severity is assigned first, from the exercise's drawn case-mix parameters (casemix.py), and the case type is then
    picked from a pool of that severity. Day-tagged so scheduling can keep each case in the pool (day, routine/MASCAL)
    it was generated for."""
    draw = draw or casemix.draw_parameters(config)
    env_dnbi = DNBI_BY_ENVIRONMENT.get(config.environment, []) + DNBI_BY_ENVIRONMENT.get("General", [])
    slots = []  # (day_number, kind, mechanism, is_trauma, is_mascal, etiology)
    for day in config.days:
        # Routine casualty load for the day (not part of any MASCAL surge).
        routine_ratio = 0.85 if day.tactical_setting in ["Frontal Attack", "Amphibious Assault"] else 0.50
        num_trauma = int(day.total_patients * routine_ratio)
        num_dnbi = day.total_patients - num_trauma
        slots += [(day.day_number, "routine", day.tactical_setting, True, False, None)] * num_trauma
        slots += [(day.day_number, "dnbi", f"DNBI - {config.environment}", False, False, None)] * num_dnbi
        # MASCAL surge: additive extra casualties, trauma-heavy, tagged is_mascal.
        if day.mascal and day.mascal_patients:
            m_trauma = int(day.mascal_patients * 0.85)
            slots += [(day.day_number, "mascal", day.mascal_etiology or day.tactical_setting, True, True,
                       day.mascal_etiology)] * m_trauma
            slots += [(day.day_number, "dnbi", f"DNBI - {config.environment}", False, True, None)] * (day.mascal_patients - m_trauma)
    severities = casemix.assign_severities([sl[1] for sl in slots], draw)
    decks: Dict[tuple, _Deck] = {}
    deck_rng = random.Random(draw["seed"] + 2)  # the same draw reproduces the same case types
    tasks = []
    for (day_no, _kind, mech, is_trauma, is_mascal, etiology), sev in zip(slots, severities):
        tier = "serious" if sev in ("critical", "severe") else sev
        if is_trauma:
            pool = (TRAUMA_TIERS.get(etiology) if etiology else None) or GENERAL_TRAUMA_TIERS
            pool = pool[tier]
        else:
            pool = [c for c in env_dnbi if dnbi_tier(c) == tier] or env_dnbi
        tasks.append((day_no, decks.setdefault(tuple(pool), _Deck(pool, deck_rng)).draw(), mech, is_trauma, is_mascal, sev))
    return tasks

def _generate_one(task: tuple, environment: str, region: str, mets: Optional[List[str]] = None,
                  profile: Optional[Dict] = None, ctx: Optional[Dict] = None) -> Dict:
    _day, case_type, mech, is_trauma, is_mascal = task[:5]
    try:
        return generate_case_sync(case_type, mech, environment, region, is_mascal, mets, profile, ctx)
    except Exception as e:
        print(f"WARNING: case generation failed ({case_type}): {e} — using offline fallback")
        case = _enforce_profile(create_fallback_case(case_type, mech, is_trauma), profile)
        # Truthy marker that also records why, so the job message can say what went wrong.
        kind = getattr(e, "kind", None) or ("budget" if isinstance(e, BudgetExceeded) else "other")
        case["_fallback"] = kind
        # Persisted so the history page can say which cases are templates and why. A Google error contributes only its kind,
        # never its text (which can carry account details); anything else is our own error, safe to keep.
        case["generation"] = "template"
        if isinstance(e, AIError):
            case["generation_error"] = kind + (f" [{e.error_type} {e.http_code} {e.status}]" if e.error_type else "")
        else:
            case["generation_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return case

# In-memory job store — always used as primary, DB synced as best-effort
_jobs: Dict[str, Dict] = {}

def _job_create(job_id: str):
    _jobs[job_id] = {"status": "running", "progress": "Starting...", "completed": 0, "total": 0,
                     "ts": datetime.utcnow()}
    if SessionLocal:
        try:
            db = SessionLocal()
            try:
                db.add(Job(id=job_id))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"DB job create failed (using memory only): {e}")

def _job_update(job_id: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)
    if SessionLocal:
        try:
            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    for k, v in kwargs.items():
                        setattr(job, k, v)
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"DB job update failed: {e}")

def _job_get(job_id: str):
    # Memory first (fast, same-instance), DB as cross-instance fallback
    if job_id in _jobs:
        return _jobs[job_id]
    if SessionLocal:
        try:
            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    return {"status": job.status, "progress": job.progress,
                            "completed": job.completed, "total": job.total,
                            "token": job.token, "filename": job.filename, "error": job.error}
            finally:
                db.close()
        except Exception as e:
            print(f"DB job get failed: {e}")
    return None

def _build_controller_layers(config: ExerciseConfig, schedule: List[Dict], cases: List[Dict],
                             fragos: List[Dict], progress=None, budget: Optional[_Budget] = None) -> None:
    """Attach a red-teamed controller layer to every scheduled case, built on the
    care chain in force (WARNO base chain + active FRAGOs) at its arrival time."""
    rows = [r for r in schedule if "arr_raw" in r]
    days = {d.day_number: d for d in config.days}
    tp = _transit_min("Priority", config)

    def one(i: int) -> Dict:
        case, row = cases[i], rows[i]
        day = days[row["day"]]
        chain = scenario.chain_for(config, day, row["arr_raw"], fragos, tp)
        pathway = scenario.determine_pathway(case, chain)
        in_force = [f for f in fragos if f["number"] in chain["fragos"]]
        maritime = scenario._is_maritime(config, day)
        template = lambda: scenario.fallback_controller(case, chain, pathway)
        try:
            first = scenario.generate_controller(case, chain, pathway, in_force, maritime, _llm_json,
                                                 _situation_text(row, config))
        except Exception as e:
            print(f"WARNING: controller layer generation failed (case {i + 1}): {e} — using template")
            return redteam.finalize(template(), case, fallback=template, source="template")
        # One expert review-and-repair call; one targeted revision only if the
        # rules still fail; template last. At most 3 model calls per layer.
        skip_review = case.get("severity") == "mild" and not REVIEW_MILD
        return redteam.finalize(first, case,
                                review=None if skip_review else (lambda c, f: scenario.review_controller(c, case, f, _llm_json)),
                                revise=lambda c, f: scenario.revise_controller(c, f, _llm_json),
                                fallback=template)

    n = len(rows)
    done = 0
    with ThreadPoolExecutor(max_workers=min(5, max(n, 1))) as pool:
        futures = {pool.submit(_bound(budget, one), i): i for i in range(n)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                ctrl = fut.result()
            except Exception as e:  # never let one case sink the package
                print(f"WARNING: controller layer failed (case {i + 1}): {e}")
                row = rows[i]
                chain = scenario.chain_for(config, days[row["day"]], row["arr_raw"], fragos, tp)
                ctrl = redteam.finalize(scenario.fallback_controller(
                    cases[i], chain, scenario.determine_pathway(cases[i], chain)), cases[i], source="template")
            cases[i]["controller"] = ctrl
            rows[i].update({
                "pathway": ctrl["pathway"],
                "care_chain": " → ".join(nd["name"] for nd in ctrl["chain"]["nodes"]),
                "fragos_in_force": ", ".join(f"FRAGO {k:02d}" for k in ctrl["chain"]["fragos"]),
            })
            done += 1
            if progress:
                progress(done, n)


def _package_files(config: ExerciseConfig, schedule: List[Dict], cases: List[Dict], warno: str, annex: str,
                   medroe: str, road_to_war: str, fragos: Optional[List[Dict]]) -> List[tuple]:
    name = config.exercise_name
    files = [
        (f"{name}_MSEL.xlsx", create_msel(schedule, config).getvalue()),
        (f"{name}_WARNO.docx", create_docx("WARNING ORDER", name.upper(), warno).getvalue()),
        (f"{name}_Annex_Q.docx", create_docx("ANNEX Q (MEDICAL SERVICES)", f"TO OPORD {name.upper()}", annex).getvalue()),
        (f"{name}_MEDROE.docx", create_docx("MEDICAL RULES OF ENGAGEMENT", name.upper(), medroe).getvalue()),
        (f"{name}_Case_Book.docx", create_case_book(cases, config).getvalue()),
        (f"{name}_Road_to_War_Prompt.docx", create_docx("ROAD TO WAR — VIDEO PROMPT", name.upper(), road_to_war).getvalue()),
    ]
    if fragos is not None:
        files.append((f"{name}_FRAGOs.docx", create_docx("FRAGMENTARY ORDERS", f"TO OPORD {name.upper()}",
                                                         scenario.fragos_text(fragos, name)).getvalue()))
    if any(c.get("controller") for c in cases):
        files.append((f"{name}_Controller_Packet.docx",
                      controller_docs.create_controller_packet(cases, schedule, config, fragos or []).getvalue()))
        files.append((f"{name}_Controller_Vitals.xlsx",
                      controller_docs.create_controller_vitals(cases, schedule, config).getvalue()))
        files.append((f"{name}_cases.json", json.dumps(_controller_export(config, schedule, cases, fragos),
                                                       indent=1).encode()))
    return files


def _controller_export(config: ExerciseConfig, schedule: List[Dict], cases: List[Dict],
                       fragos: Optional[List[Dict]]) -> Dict:
    """Self-contained file the live controller page loads (no server storage needed)."""
    rows = [r for r in schedule if "arr_raw" in r]
    return {
        "format": "role2builder.cases.v1",
        "exercise": config.exercise_name,
        "generated": datetime.utcnow().isoformat() + "Z",
        "fragos": fragos or [],
        "cases": [{"case_num": i + 1, "day": rows[i].get("day") if i < len(rows) else None,
                   "arrival": rows[i].get("time") if i < len(rows) else None,
                   "event": rows[i].get("event") if i < len(rows) else None, "case": c}
                  for i, c in enumerate(cases)],
    }


def _run_generation(config: ExerciseConfig, job_id: str):
    try:
        draw = casemix.draw_parameters(config)  # this exercise's draw from the scenario's envelopes; saved with it
        tasks = _build_case_tasks(config, draw)
        total = len(tasks)
        profiles = casemix.assign_profiles(tasks, config, draw)
        days_by_no = {d.day_number: d for d in config.days}
        facts = _planning_facts(config)
        ctxs = [{"setting": days_by_no[t[0]].tactical_setting if t[0] in days_by_no else "", "threat": config.threat_level,
                 "facts": facts} for t in tasks]
        print(f"Case mix for '{config.exercise_name}' (seed {draw['seed']}): {casemix.summarize(profiles)}; "
              f"care policy {casemix.care_policy(config)}")
        budget = _Budget(max_calls=MAX_CALLS_PER_CASE * total, max_usd=MAX_USD_PER_EXERCISE)
        _tl.budget = budget
        _job_update(job_id, progress="Generating cases...", completed=0, total=total)

        cases_results: Dict[int, Dict] = {}
        with ThreadPoolExecutor(max_workers=min(5, max(total, 1))) as pool:
            futures = {pool.submit(_bound(budget, _generate_one), t, config.environment, config.region,
                                   config.selected_mets, profiles[i], ctxs[i]): i
                       for i, t in enumerate(tasks)}
            completed = 0
            for future in as_completed(futures):
                cases_results[futures[future]] = future.result()
                completed += 1
                _job_update(job_id, progress=f"Generating cases: {completed} / {total}", completed=completed)

        cases = [cases_results[i] for i in range(total)]
        fallback_reasons = [c.pop("_fallback") for c in cases if c.get("_fallback")]
        fallback_count = len(fallback_reasons)
        fallback_why = ""
        if fallback_count:
            top = max(set(fallback_reasons), key=fallback_reasons.count)
            fallback_why = AI_KIND_TEXT.get(top, "an AI error occurred")
            if top == "other":
                errs = [c.get("generation_error", "").split(":")[0] for c in cases if c.get("generation")]
                if errs:
                    fallback_why += f" ({max(set(errs), key=errs.count)})"
            print(f"WARNING: {fallback_count}/{total} cases used the offline fallback ({top})")
        _job_update(job_id, progress="Generating documents...", completed=total)

        # Pool cases by (day, MASCAL) so each schedule slot draws a case that
        # was generated for it; shuffle within pools to mix trauma/DNBI order.
        case_pools: Dict[tuple, List[Dict]] = {}
        for t, c in zip(tasks, cases):
            case_pools.setdefault((t[0], t[4]), []).append(c)
        for p in case_pools.values():
            random.shuffle(p)

        schedule, cases = generate_schedule(config, case_pools, draw)

        # Care chain + FRAGOs → per-case decision trees, vitals tracks, red team.
        fragos = scenario.generate_fragos(config)
        _job_update(job_id, progress="Building decision trees (red team + fixes)...")
        _build_controller_layers(
            config, schedule, cases, fragos,
            lambda d, n: _job_update(job_id, progress=f"Decision trees (red-teamed and fixed): {d} / {n}"),
            budget)

        _job_update(job_id, progress="Generating orders...")
        with ThreadPoolExecutor(max_workers=3) as pool:
            load = _schedule_facts(schedule, cases, config)  # the orders plan for the load the schedule actually carries
            f_warno = pool.submit(_bound(budget, generate_warno), config, fragos, load)
            f_annex = pool.submit(_bound(budget, generate_annex_q), config, fragos, load)
            f_medroe = pool.submit(_bound(budget, generate_medroe), config, load)
            warno = f_warno.result()
            annex = f_annex.result()
            medroe = f_medroe.result()

        # Road to War video prompt is derived from the freshly generated Annex Q.
        _job_update(job_id, progress="Writing Road to War prompt...")
        road_to_war = generate_road_to_war_prompt(config, annex)

        _job_update(job_id, progress="Assembling package...")

        if SessionLocal:
            db = SessionLocal()
            try:
                ex = Exercise(name=config.exercise_name, config=dict(config.dict(), case_mix=draw), cases=cases,
                              msel_data=schedule, warno_text=warno, annex_q_text=annex, medroe_text=medroe,
                              road_to_war_text=road_to_war, fragos=fragos)
                db.add(ex)
                db.commit()
            finally:
                db.close()
        elif archive.enabled():
            try:
                archive.save(name=config.exercise_name, config=dict(config.dict(), case_mix=draw), cases=cases, msel_data=schedule,
                             warno_text=warno, annex_q_text=annex, medroe_text=medroe,
                             road_to_war_text=road_to_war, fragos=fragos)
            except Exception as e:  # never lose the generated package over an archive failure
                print(f"WARNING: archiving exercise failed: {e}")

        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname, data in _package_files(config, schedule, cases, warno, annex, medroe, road_to_war, fragos):
                zf.writestr(fname, data)
        zip_buf.seek(0)

        token = str(uuid.uuid4())
        _packages[token] = {"data": zip_buf.getvalue(), "ts": datetime.utcnow()}
        templated = sum(1 for c in cases if (c.get("controller") or {}).get("quality", {}).get("source") == "template")
        if templated:
            print(f"WARNING: {templated}/{total} controller layers shipped as the pathway template")
        usage = budget.summary()
        print(f"AI usage for '{config.exercise_name}' ({total} cases): {usage['calls']} calls, "
              f"{usage['input_tokens']} in ({usage['cached_tokens']} cached) / {usage['output_tokens']} out tokens, est ${usage['est_usd']:.2f}")
        done_msg = "Package ready!" if not fallback_count else (
            f"Package ready — NOTE: {fallback_count} of {total} cases used the offline "
            f"fallback template ({fallback_why}); review the case book before use.")
        if budget.exhausted:
            done_msg += (f" The exercise hit its AI spending cap (${MAX_USD_PER_EXERCISE:.2f}); remaining cases "
                         f"and decision trees used templates.")
        _job_update(job_id, status="complete", progress=done_msg,
                    completed=total, total=total, token=token, usage=usage,
                    filename=f"{config.exercise_name}_Package.zip")
    except Exception as e:
        import traceback
        traceback.print_exc()
        _job_update(job_id, status="error", progress=str(e), error=str(e))
    finally:
        _tl.budget = None


@app.post("/generate-exercise")
async def generate_exercise(config: ExerciseConfig, request: Request):
    _purge_stale_stores()
    _check_client_rate(request, "exercise", MAX_EXERCISES_PER_CLIENT_PER_DAY, timedelta(days=1),
                       "Exercise generation limit reached for today — try again tomorrow.")
    if sum(1 for j in _jobs.values() if j.get("status") == "running") >= MAX_CONCURRENT_JOBS:
        raise HTTPException(status_code=429, detail="Another exercise is still generating — try again in a few minutes.")
    if _today_spend() >= MAX_USD_PER_DAY:
        raise HTTPException(status_code=429, detail="Daily AI generation limit reached — try again tomorrow (UTC).")
    job_id = str(uuid.uuid4())
    _job_create(job_id)
    threading.Thread(target=_run_generation, args=(config, job_id), daemon=True).start()
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = _job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/download/{token}")
async def download_package(token: str):
    pkg = _packages.pop(token, None)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found or already downloaded")
    return Response(pkg["data"], media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=package.zip"})

@app.get("/exercises")
async def list_exercises():
    if not SessionLocal:
        if archive.enabled():
            try:
                return {"exercises": archive.list_summaries()}
            except Exception as e:
                print(f"Archive list failed: {e}")
                raise HTTPException(status_code=500, detail="Archive unavailable")
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

def _load_exercise(exercise_id: int):
    """Fetch one saved exercise from whichever store is configured (database, else S3 archive)."""
    if SessionLocal:
        db = SessionLocal()
        try:
            e = db.query(Exercise).filter(Exercise.id == exercise_id).first()
            if not e:
                raise HTTPException(status_code=404, detail="Not found")
            return SimpleNamespace(id=e.id, name=e.name, created_at=e.created_at.isoformat() if e.created_at else None,
                                   config=e.config, cases=e.cases, msel_data=e.msel_data, warno_text=e.warno_text,
                                   annex_q_text=e.annex_q_text, medroe_text=e.medroe_text,
                                   road_to_war_text=e.road_to_war_text, fragos=e.fragos)
        finally:
            db.close()
    if archive.enabled():
        try:
            e = archive.get(exercise_id)
        except Exception as ex:
            print(f"Archive get failed for exercise {exercise_id}: {ex}")
            raise HTTPException(status_code=500, detail="Archive unavailable")
        if not e:
            raise HTTPException(status_code=404, detail="Not found")
        return e
    raise HTTPException(status_code=404, detail="DB not configured")


@app.get("/exercises/{exercise_id}")
async def get_exercise(exercise_id: int):
    ex = _load_exercise(exercise_id)
    return {"id": ex.id, "name": ex.name, "created_at": ex.created_at, "config": ex.config, "cases": ex.cases, "msel_data": ex.msel_data, "fragos": ex.fragos or []}

def _json_list(value: Any) -> List[Any]:
    """Archived rows from Railway hold JSON columns as text; accept either form."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []

def _obj(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}

def _clip(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"

@app.get("/exercises/{exercise_id}/cases")
async def list_exercise_cases(exercise_id: int):
    """One compact row per case for the history viewer (a few KB instead of the 2 MB record)."""
    ex = _load_exercise(exercise_id)
    rows = []
    for i, c in enumerate(_json_list(ex.cases)):
        c = _obj(c)
        meta, zmist = _obj(c.get("meta")), _obj(c.get("zmist"))
        rows.append({
            "index": i, "zap": zmist.get("zap"), "title": meta.get("title"),
            "triage": c.get("triage_category"), "disposition": c.get("disposition"),
            "specialty": meta.get("target_specialty"), "duration": meta.get("estimated_duration"),
            "population": c.get("patient_population"), "night": c.get("arrival_window") == "night",
            "severity": c.get("severity"), "template": c.get("generation") == "template",
            "tree_template": _obj(_obj(c.get("controller")).get("quality")).get("source") == "template",
            "mechanism": _clip(zmist.get("mechanism"), 220), "injuries": _clip(zmist.get("injuries"), 160),
        })
    return {"id": ex.id, "name": ex.name, "cases": rows}

@app.get("/exercises/{exercise_id}/cases/{case_index}")
async def get_exercise_case(exercise_id: int, case_index: int):
    """One full case, without the large controller decision-tree layer, plus its MSEL row."""
    ex = _load_exercise(exercise_id)
    cases = _json_list(ex.cases)
    if not 0 <= case_index < len(cases):
        raise HTTPException(status_code=404, detail="Case not found")
    case = _obj(cases[case_index])
    zap = _obj(case.get("zmist")).get("zap")
    schedule = next((_obj(s) for s in _json_list(ex.msel_data) if zap and _obj(s).get("zap") == zap), None)
    return {"index": case_index, "has_controller": "controller" in case, "schedule": schedule,
            "case": {k: v for k, v in case.items() if k != "controller"}}

@app.get("/exercises/{exercise_id}/download")
async def download_exercise(exercise_id: int):
    ex = _load_exercise(exercise_id)

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

    road_to_war = getattr(ex, "road_to_war_text", None) or generate_road_to_war_prompt(config, ex.annex_q_text or "")
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, data in _package_files(config, msel_data, cases, ex.warno_text, ex.annex_q_text,
                                          ex.medroe_text, road_to_war, getattr(ex, "fragos", None)):
            zf.writestr(fname, data)
    zip_buf.seek(0)
    return Response(zip_buf.getvalue(), headers={'Content-Disposition': f'attachment; filename="{config.exercise_name}_Package.zip"'}, media_type='application/zip')

@app.get("/exercises/{exercise_id}/document/{doc_type}")
async def download_document(exercise_id: int, doc_type: str):
    if doc_type not in ["msel", "warno", "annex_q", "medroe", "case_book", "road_to_war", "fragos",
                        "controller_packet", "controller_vitals", "cases_json"]:
        raise HTTPException(status_code=400, detail="Invalid doc type")
    
    ex = _load_exercise(exercise_id)

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
    elif doc_type == "road_to_war":
        rtw = getattr(ex, "road_to_war_text", None) or generate_road_to_war_prompt(config, ex.annex_q_text or "")
        buf, fn, mt = create_docx("ROAD TO WAR — VIDEO PROMPT", config.exercise_name.upper(), rtw), f"{config.exercise_name}_Road_to_War_Prompt.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif doc_type == "fragos":
        buf, fn, mt = create_docx("FRAGMENTARY ORDERS", f"TO OPORD {config.exercise_name.upper()}", scenario.fragos_text(ex.fragos or [], config.exercise_name)), f"{config.exercise_name}_FRAGOs.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif doc_type == "controller_packet":
        buf, fn, mt = controller_docs.create_controller_packet(cases, msel_data, config, ex.fragos or []), f"{config.exercise_name}_Controller_Packet.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif doc_type == "controller_vitals":
        buf, fn, mt = controller_docs.create_controller_vitals(cases, msel_data, config), f"{config.exercise_name}_Controller_Vitals.xlsx", 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif doc_type == "cases_json":
        buf, fn, mt = BytesIO(json.dumps(_controller_export(config, msel_data, cases, ex.fragos)).encode()), f"{config.exercise_name}_cases.json", 'application/json'
    else:
        buf, fn, mt = create_case_book(cases, config), f"{config.exercise_name}_Case_Book.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    
    return Response(buf.getvalue(), headers={'Content-Disposition': f'attachment; filename="{fn}"'}, media_type=mt)
