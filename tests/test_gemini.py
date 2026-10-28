"""Gemini failure handling: classification, retired-model recovery, safety blocks, visible fallbacks."""
import os
from types import SimpleNamespace

os.environ["EXERCISE_BUCKET"] = ""  # tests must never reach AWS
os.environ.pop("DATABASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from google.genai import errors  # noqa: E402

from backend import main  # noqa: E402


def _err(cls, code, msg="x"):
    return cls(code, {"error": {"code": code, "message": msg, "status": "X"}}, None)


def _response(text="OK", finish="STOP", with_candidate=True, block_reason=None):
    cands = [SimpleNamespace(finish_reason=SimpleNamespace(name=finish),
                             content=SimpleNamespace(parts=[SimpleNamespace(text=text)] if text else []))] if with_candidate else []
    return SimpleNamespace(text=text, candidates=cands, prompt_feedback=SimpleNamespace(block_reason=block_reason),
                           usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=2,
                                                          thoughts_token_count=0))


class FakeModels:
    def __init__(self, behave, models=()):
        self.behave, self.calls, self._models = behave, [], list(models)

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "config": config})
        return self.behave(model)

    def list(self):
        return iter(self._models)


@pytest.fixture
def fake(monkeypatch):
    def install(behave, models=()):
        client = SimpleNamespace(models=FakeModels(behave, models))
        monkeypatch.setattr(main, "get_client", lambda: client)
        monkeypatch.setattr(main, "_active_model", main.GEMINI_MODEL)
        return client.models
    return install


@pytest.mark.parametrize("exc,kind", [
    (_err(errors.ClientError, 404), "model_not_found"),
    (_err(errors.ClientError, 403), "auth_or_ip"),
    (_err(errors.ClientError, 400, "API key not valid"), "auth_or_ip"),
    (_err(errors.ClientError, 400, "bad schema"), "bad_request"),
    (_err(errors.ClientError, 429), "quota"),
    (_err(errors.ServerError, 503), "unavailable"),
    (TimeoutError("slow"), "unavailable"),
    (ValueError("nope"), "other"),
])
def test_classification(exc, kind):
    assert main._classify_ai_error(exc) == kind


def test_failures_become_classified_errors_and_are_recorded(fake):
    def behave(model):
        raise _err(errors.ServerError, 503)
    fake(behave)
    with pytest.raises(main.AIError) as info:
        main._call_model("hi", "case")
    assert info.value.kind == "unavailable"
    assert main._ai_state["ok"] is False and main._ai_state["kind"] == "unavailable"


def test_retired_model_switches_to_newest_stable_flash(fake):
    models = [SimpleNamespace(name=f"models/{n}", supported_actions=["generateContent"]) for n in (
        "gemini-2.5-flash", "gemini-3-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-2.0-flash")]
    models.append(SimpleNamespace(name="models/gemini-9-flash", supported_actions=["embedContent"]))  # wrong action

    def behave(model):
        if model == main.GEMINI_MODEL:
            raise _err(errors.ClientError, 404, "model is not found")
        return _response()
    m = fake(behave, models)
    main._call_model("hi", "case")
    assert [c["model"] for c in m.calls] == [main.GEMINI_MODEL, "gemini-3-flash"]
    assert main._active_model == "gemini-3-flash"
    main._call_model("again", "case")  # later calls go straight to the replacement
    assert m.calls[-1]["model"] == "gemini-3-flash" and len(m.calls) == 3
    assert main._ai_state["ok"] is True


def test_retired_model_with_no_replacement_is_a_clear_error(fake):
    def behave(model):
        raise _err(errors.ClientError, 404)
    fake(behave, models=[])
    with pytest.raises(main.AIError) as info:
        main._call_model("hi", "case")
    assert info.value.kind == "model_not_found"


def test_safety_block_is_classified_not_a_json_crash(fake):
    fake(lambda model: _response(text="", finish="SAFETY"))
    with pytest.raises(main.AIError) as info:
        main._call_model("hi", "case", json_mode=True)
    assert info.value.kind == "blocked"
    fake(lambda model: _response(text="", with_candidate=False, block_reason="PROHIBITED_CONTENT"))
    with pytest.raises(main.AIError) as info:
        main._call_model("hi", "case", json_mode=True)
    assert info.value.kind == "blocked"


def test_cut_off_json_is_flagged_but_cut_off_prose_is_kept(fake):
    fake(lambda model: _response(text='{"a": ', finish="MAX_TOKENS"))
    with pytest.raises(main.AIError) as info:
        main._call_model("hi", "case", json_mode=True)
    assert info.value.kind == "truncated"
    assert main._call_model("hi", "orders").text  # plain-text documents are still usable


def test_safety_filters_are_relaxed_by_default(fake):
    m = fake(lambda model: _response())
    main._call_model("hi", "case")
    assert len(m.calls[0]["config"]["safety_settings"]) == 4


def test_fallback_case_records_why(monkeypatch):
    def boom(*a, **k):
        raise main.AIError("quota", "429")
    monkeypatch.setattr(main, "generate_case_sync", boom)
    case = main._generate_one((1, "GSW right thigh", "IED/Blast", True, False), "Jungle", "Indo-Pacific")
    assert case["_fallback"] == "quota"
    assert "quota" in main.AI_KIND_TEXT["quota"]


def test_health_ai_reports_without_calling_gemini(fake):
    m = fake(lambda model: _response())
    body = TestClient(main.app).get("/health/ai").json()
    assert body["active_model"] == main.GEMINI_MODEL and "probe" not in body
    assert m.calls == []  # the free form never spends a call


def test_health_ai_probe_reports_success_and_failure(fake):
    main._rate_hits.clear()
    fake(lambda model: _response())
    ok = TestClient(main.app).get("/health/ai?probe=1").json()
    assert ok["probe"]["ok"] is True and ok["last_call"]["ok"] is True

    def behave(model):
        raise _err(errors.ClientError, 403, "IP address restriction")
    fake(behave)
    bad = TestClient(main.app).get("/health/ai?probe=1").json()
    assert bad["probe"] == {"ok": False, "kind": "auth_or_ip", "meaning": main.AI_KIND_TEXT["auth_or_ip"],
                            "error_type": "ClientError", "http_code": 403, "status": "X"}
    assert "IP address restriction" not in str(bad)  # error text from Google is never echoed to callers


def test_probe_fingerprints_non_api_failures(fake):
    """An unclassifiable error still says what class it was, so 'other' is diagnosable without logs."""
    main._rate_hits.clear()

    def behave(model):
        raise RuntimeError("secret account detail")
    fake(behave)
    body = TestClient(main.app).get("/health/ai?probe=1").json()
    assert body["probe"]["kind"] == "other" and body["probe"]["error_type"] == "RuntimeError"
    assert body["probe"]["http_code"] is None
    assert "secret account detail" not in str(body)
    assert body["last_call"]["error_type"] == "RuntimeError"


def test_health_ai_probe_is_rate_limited(fake):
    main._rate_hits.clear()
    fake(lambda model: _response())
    c = TestClient(main.app)
    codes = [c.get("/health/ai?probe=1").status_code for _ in range(7)]
    assert codes[:6] == [200] * 6 and codes[6] == 429
    main._rate_hits.clear()
