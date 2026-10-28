"""S3-backed archive of generated exercises.

Used when no DATABASE_URL is configured and EXERCISE_BUCKET is non-empty. Each exercise
is one gzipped JSON object (exercises/<id>.json.gz) and index.json holds the small
per-exercise summaries the history page lists, so browsing never loads case blobs.
Cost is a few cents a year at this volume: no database, no always-on resources.
"""
import gzip
import json
import os
import threading
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

# The runtime contract passes the container no extra env vars, so the bucket name has a default.
# Set EXERCISE_BUCKET="" to turn the archive off (e.g. local dev without AWS credentials).
BUCKET = os.getenv("EXERCISE_BUCKET", "role2-exercises-885232248320").strip()
_INDEX_KEY = "index.json"
_lock = threading.Lock()
_client = None

_FIELDS = ("id", "name", "created_at", "config", "cases", "msel_data", "warno_text",
           "annex_q_text", "medroe_text", "road_to_war_text", "fragos")


def enabled() -> bool:
    return bool(BUCKET)


def _s3():
    global _client
    if _client is None:
        import boto3  # imported lazily so DB-only deployments and tests don't need it
        _client = boto3.client("s3", region_name=os.getenv("EXERCISE_BUCKET_REGION", "us-east-1"))
    return _client


def _key(exercise_id: int) -> str:
    return f"exercises/{int(exercise_id)}.json.gz"


def _get_bytes(key: str) -> Optional[bytes]:
    try:
        return _s3().get_object(Bucket=BUCKET, Key=key)["Body"].read()
    except _s3().exceptions.NoSuchKey:
        return None


def _put_json(key: str, obj: Any, compress: bool) -> None:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if compress:
        body = gzip.compress(body)
    _s3().put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/json",
                     ServerSideEncryption="AES256")


def _as_obj(value: Any) -> Any:
    """Rows migrated from Railway stored JSON columns as text; normalise to real JSON."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def summarize(rec: Dict[str, Any]) -> Dict[str, Any]:
    """The row shown in the history list. Extra fields beyond the original five are for filtering."""
    config = _as_obj(rec.get("config")) or {}
    cases = _as_obj(rec.get("cases")) or []
    if not isinstance(config, dict):
        config = {}
    days = config.get("days")
    return {
        "id": rec["id"],
        "name": rec.get("name") or "",
        "created_at": rec.get("created_at"),
        "duration": config.get("duration"),
        "environment": config.get("environment"),
        "total_cases": len(cases) if isinstance(cases, list) else 0,
        "region": config.get("region"),
        "threat_level": config.get("threat_level"),
        "supported_unit": config.get("supported_unit"),
        "days": len(days) if isinstance(days, list) else days,
    }


def _read_index() -> List[Dict[str, Any]]:
    raw = _get_bytes(_INDEX_KEY)
    return json.loads(raw)["exercises"] if raw else []


def list_summaries() -> List[Dict[str, Any]]:
    return sorted(_read_index(), key=lambda r: r.get("created_at") or "", reverse=True)


def get(exercise_id: int) -> Optional[SimpleNamespace]:
    raw = _get_bytes(_key(exercise_id))
    if raw is None:
        return None
    rec = json.loads(gzip.decompress(raw))
    for k in _FIELDS:
        rec.setdefault(k, None)
    return SimpleNamespace(**{k: rec[k] for k in _FIELDS})


def put(rec: Dict[str, Any]) -> int:
    """Store a record with an explicit id (used by the Railway import). Updates the index."""
    rec = {k: rec.get(k) for k in _FIELDS}
    with _lock:
        _put_json(_key(rec["id"]), rec, compress=True)
        index = [r for r in _read_index() if r["id"] != rec["id"]]
        index.append(summarize(rec))
        _put_json(_INDEX_KEY, {"exercises": sorted(index, key=lambda r: r["id"])}, compress=False)
    return rec["id"]


def save(**fields) -> int:
    """Store a newly generated exercise under the next free id."""
    from datetime import datetime
    with _lock:
        index = _read_index()
        new_id = max((r["id"] for r in index), default=0) + 1
        rec = {k: fields.get(k) for k in _FIELDS}
        rec["id"] = new_id
        rec["created_at"] = datetime.utcnow().isoformat()
        _put_json(_key(new_id), rec, compress=True)
        index.append(summarize(rec))
        _put_json(_INDEX_KEY, {"exercises": index}, compress=False)
    return new_id
