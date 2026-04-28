"""
Centralized logging configuration.

One call to `configure_logging()` at app startup wires:
- The standard library `logging` module (root logger → stderr).
- A consistent format including timestamp + level + logger name + message.
- Optional JSON output when `LOG_FORMAT=json` (for log aggregators).
- A `LoggerAdapter` factory that attaches a correlation id to every record
  emitted from a worker, so you can grep one job's full trace.

Modules use `get_logger(__name__)` everywhere; the job worker upgrades to
`get_job_logger(job_id)` so progress / phase / failure lines all carry the
job id without callers having to remember.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Mapping


_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Surface anything attached via LoggerAdapter `extra=`.
        for key in ("job_id", "phase", "exercise_name"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def configure_logging() -> None:
    """Idempotent — safe to call multiple times (FastAPI reloads, tests)."""
    global _configured
    if _configured:
        return
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    if os.getenv("LOG_FORMAT", "").lower() == "json":
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))

    root = logging.getLogger()
    # Replace any handlers Uvicorn / pytest may have installed so output stays
    # consistent across run modes.
    root.handlers = [handler]
    root.setLevel(level)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


class _CtxAdapter(logging.LoggerAdapter):
    """LoggerAdapter that merges the bound context into every record."""

    def process(self, msg: str, kwargs: Mapping[str, Any]):
        extra = dict(kwargs.get("extra") or {})
        extra.update(self.extra or {})
        new_kwargs = dict(kwargs)
        new_kwargs["extra"] = extra
        return msg, new_kwargs


def get_job_logger(job_id: str, **extra: Any) -> logging.LoggerAdapter:
    """Logger that auto-attaches job_id (and any other context) to every record.

    Usage:
        log = get_job_logger(job_id, exercise_name=cfg.exercise_name)
        log.info("phase=generating_cases")
    """
    base = get_logger("backend.jobs.worker")
    ctx: dict[str, Any] = {"job_id": job_id}
    ctx.update(extra)
    return _CtxAdapter(base, ctx)
