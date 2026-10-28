"""S3 exercise archive: round-trips, ids, index, and the endpoints that sit on top of it."""
import io
import json

os_env = __import__("os").environ
os_env.pop("GEMINI_API_KEY", None)
os_env.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend import archive, main  # noqa: E402


class _NoSuchKey(Exception):
    pass


class FakeS3:
    class exceptions:
        NoSuchKey = _NoSuchKey

    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise _NoSuchKey(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[Key] = Body


def _use_fake(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(archive, "BUCKET", "test-bucket")
    monkeypatch.setattr(archive, "_client", fake)
    return fake


CONFIG = {"exercise_name": "KS27", "duration": 3, "environment": "Desert", "region": "CENTCOM",
          "threat_level": "High", "supported_unit": "1-1 IN", "days": [{"day": 1}, {"day": 2}]}


def test_save_get_and_list(monkeypatch):
    fake = _use_fake(monkeypatch)
    first = archive.save(name="KS27", config=CONFIG, cases=[{"a": 1}, {"a": 2}], msel_data=[], fragos=[])
    second = archive.save(name="KS28", config=CONFIG, cases=[{"a": 1}], msel_data=[], fragos=[])
    assert (first, second) == (1, 2)
    assert "exercises/1.json.gz" in fake.objects and "index.json" in fake.objects
    ex = archive.get(1)
    assert ex.name == "KS27" and len(ex.cases) == 2
    listing = archive.list_summaries()
    assert [r["id"] for r in listing] == [2, 1]  # newest first
    assert listing[1]["total_cases"] == 2 and listing[1]["days"] == 2 and listing[1]["environment"] == "Desert"
    assert archive.get(99) is None


def test_put_preserves_ids_and_handles_text_json(monkeypatch):
    """Railway rows hold config/cases as JSON text; they must come back as real JSON."""
    _use_fake(monkeypatch)
    archive.put({"id": 36, "name": "KS27", "created_at": "2026-09-24T12:09:54",
                 "config": json.dumps(CONFIG), "cases": json.dumps([{"x": 1}] * 4), "msel_data": "[]"})
    assert archive.list_summaries()[0]["total_cases"] == 4
    assert archive.save(name="next", config=CONFIG, cases=[], msel_data=[]) == 37


def test_endpoints_serve_archive(monkeypatch):
    _use_fake(monkeypatch)
    monkeypatch.setattr(main, "SessionLocal", None)
    archive.put({"id": 5, "name": "KS27", "created_at": "2026-09-24T12:09:54", "config": CONFIG,
                 "cases": [{"x": 1}], "msel_data": []})
    c = TestClient(main.app)
    assert c.get("/exercises").json()["exercises"][0]["id"] == 5
    body = c.get("/exercises/5").json()
    assert body["name"] == "KS27" and body["cases"] == [{"x": 1}]
    assert c.get("/exercises/6").status_code == 404
    assert c.get("/exercises/5/document/nonsense").status_code == 400


def test_disabled_without_bucket(monkeypatch):
    monkeypatch.setattr(archive, "BUCKET", "")
    monkeypatch.setattr(main, "SessionLocal", None)
    c = TestClient(main.app)
    assert c.get("/exercises").json() == {"exercises": []}
    assert c.get("/exercises/1").status_code == 404
