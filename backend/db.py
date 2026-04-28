"""
SQLAlchemy models and DB lifecycle.

Pulled out of main.py so jobs.py can import Exercise/ExerciseJob without a
circular import. DATABASE_URL is still optional — when unset, `engine` and
`SessionLocal` are None and the in-memory stores handle persistence.

`init_db(database_url=None)` is idempotent and re-callable: tests use it to
swap in a SQLite database, production calls it once at startup. Callers that
need late binding (i.e. tests that swap the DB after `main` is imported)
should call `db.SessionLocal()` against the *module*, not `from db import
SessionLocal` — the symbol is module-level so attribute lookup picks up the
current value.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool


def _normalize_url(url: Optional[str]) -> Optional[str]:
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


# Module-level handles. Mutated by init_db(). Callers should access via
# `backend.db.SessionLocal` (attribute lookup at call time) rather than
# capturing the symbol at import.
DATABASE_URL: Optional[str] = None
engine = None
SessionLocal = None

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
    # Snapshot of the merged MatrixView active when this exercise was generated.
    # Lets /history show what casualty / triage matrices produced the cases.
    matrix_snapshot = Column(JSON, nullable=True)


class MatrixSetting(Base):
    """Single-row table holding the global MatrixOverrides JSON. id is always 1."""
    __tablename__ = "matrix_settings"
    id = Column(Integer, primary_key=True)  # always 1; no auto-increment
    overrides = Column(JSON, default=dict, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExerciseJob(Base):
    """Job tracking row for async exercise generation.

    Lives alongside Exercise (1:0..1) — `exercise_id` is populated when the
    job completes successfully. Failed/cancelled jobs leave it null and don't
    pollute the exercise list.
    """
    __tablename__ = "exercise_jobs"
    id = Column(String, primary_key=True)  # uuid
    status = Column(String, index=True)    # queued | running | complete | failed
    current_phase = Column(String)         # planning | generating_cases | generating_docs | packaging | complete | failed
    total_cases = Column(Integer, default=0)
    completed_cases = Column(Integer, default=0)
    config = Column(JSON)
    errors = Column(JSON, default=list)        # list of GenerationError dicts
    error_message = Column(Text, nullable=True)  # top-level error if status=failed
    generation_summary = Column(JSON, nullable=True)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db(database_url: Optional[str] = None) -> None:
    """Configure / reconfigure the DB. Safe to call multiple times.

    - If `database_url` is provided, use it.
    - Otherwise read `DATABASE_URL` from env.
    - If neither yields a URL, leave `engine` and `SessionLocal` as None
      (DB-less mode; in-memory stores take over).

    Always (re-)creates the schema on the current engine. SQLite (used by
    tests) needs `check_same_thread=False` so the FastAPI worker thread
    can hand sessions to background tasks.
    """
    global DATABASE_URL, engine, SessionLocal
    url = _normalize_url(database_url if database_url is not None else os.getenv("DATABASE_URL"))
    DATABASE_URL = url
    if url:
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            # In-memory SQLite gives each connection its own DB. StaticPool
            # keeps a single connection alive so sessions share the same one.
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
    else:
        engine = None
        SessionLocal = None


# Configure on import so the production code path (uvicorn boot) keeps working
# without an explicit init_db() call. Tests that need a different DB call
# init_db("sqlite:///...") again — it's idempotent.
init_db()
