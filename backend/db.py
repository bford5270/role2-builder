"""
SQLAlchemy models and DB lifecycle.

Pulled out of main.py so jobs.py can import Exercise/ExerciseJob without a
circular import. DATABASE_URL is still optional — when unset, `engine` and
`SessionLocal` are None and the in-memory job store handles persistence.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker


def _normalize_url(url: Optional[str]) -> Optional[str]:
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = _normalize_url(os.getenv("DATABASE_URL"))

# Engines are created lazily so unit tests can run without DATABASE_URL.
if DATABASE_URL:
    from sqlalchemy import create_engine
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
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


def init_db() -> None:
    if engine is not None:
        Base.metadata.create_all(bind=engine)
