"""Tests for BedrockCaseProvider — fully mocked, no real AWS calls.

The actual call to Bedrock would require AWS credentials; we substitute a
fake client and assert the contract:
- Required env var check fires on missing model id.
- Converse request payload has the right shape (model id, messages, system).
- Response parsing extracts the assistant text correctly.
- Single-case and batch paths both work.
- Timeouts surface as TimeoutError (regression for the freeze that hit
  Gemini in the field; same pattern in Bedrock provider).
- Batch size mismatch raises ValueError (caught by the retry layer upstream).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

import pytest

from backend.providers.base import BatchItem
from backend.providers.bedrock import BedrockCaseProvider


def _wrap_converse_response(text: str) -> Dict[str, Any]:
    """Mimic the Bedrock Converse API response shape."""
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 50, "totalTokens": 60},
    }


class _FakeBedrockClient:
    """Captures the last converse() call and returns a canned response."""

    def __init__(self, response_text: str = "{}", delay: float = 0.0):
        self._text = response_text
        self._delay = delay
        self.last_kwargs: Dict[str, Any] = {}
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._delay:
            time.sleep(self._delay)
        return _wrap_converse_response(self._text)


class _StallingBedrockClient:
    """Sleeps long enough that wait_for definitely fires, but short enough
    that the orphaned thread doesn't drag pytest's cleanup. The thread runs
    to completion in the background; the test only cares that the awaiter
    sees TimeoutError."""

    def converse(self, **kwargs):
        time.sleep(2.0)  # wait_for timeout in the test is 0.05s
        return _wrap_converse_response("{}")


# ---------------------------------------------------------------------------
# Init / config
# ---------------------------------------------------------------------------

class TestBedrockInit:
    def test_missing_model_id_raises_helpful_error(self, monkeypatch):
        monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
        with pytest.raises(RuntimeError, match="BEDROCK_MODEL_ID"):
            BedrockCaseProvider(client=_FakeBedrockClient())

    def test_explicit_model_id_overrides_env(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "from-env")
        p = BedrockCaseProvider(model_id="explicit", client=_FakeBedrockClient())
        assert p._model_id == "explicit"


# ---------------------------------------------------------------------------
# Single case
# ---------------------------------------------------------------------------

CANONICAL_CASE_JSON = """
{
  "meta": {"title": "Test Case", "estimated_duration": "30 min", "personnel": "Team", "target_specialty": "Emergency Medicine"},
  "learning_objectives": ["x"],
  "zmist": {"zap": "12345", "mechanism": "GSW", "injuries": "i", "signs": "s", "treatment": "t"},
  "nine_line": {"line1_location": "x", "line2_freq": "x", "line3_patients_precedence": "1A", "line4_equipment": "none", "line5_patients_type": "1L", "line6_security": "ok", "line7_marking": "VS-17", "line8_nationality": "US", "line9_nbc_terrain": "none"},
  "patient_data": {"demographics": "23 yo male", "history": "n/a", "allergies": "NKDA"},
  "triage_category": "T2",
  "phases": {"dcr": {"title": "DCR", "narrative": "...", "expected_actions": [], "vitals_trend": [], "contingencies": []}, "dcs": null, "pcc": {"title": "PCC", "narrative": "...", "expected_actions": [], "vitals_trend": [], "contingencies": []}},
  "labs": {},
  "evacuation": {"transport_type": "air", "priority": "urgent", "considerations": "x", "handover_notes": "x"},
  "debrief_questions": ["q1"]
}
""".strip()


class TestGenerateCase:
    def test_returns_parsed_case_with_stable_ids(self):
        client = _FakeBedrockClient(CANONICAL_CASE_JSON)
        p = BedrockCaseProvider(model_id="test-model", client=client)
        case = asyncio.run(p.generate_case(
            case_type="GSW chest", mechanism="GSW/Small Arms",
            environment="Urban", region="CENTCOM",
            phases=["DCR", "PCC"], target_triage="T2",
        ))
        # inject_stable_ids ran.
        assert "case_id" in case
        # target_triage forced.
        assert case["triage_category"] == "T2"

    def test_request_payload_includes_system_and_user(self):
        client = _FakeBedrockClient(CANONICAL_CASE_JSON)
        p = BedrockCaseProvider(model_id="test-model", client=client)
        asyncio.run(p.generate_case(
            case_type="GSW", mechanism="GSW", environment="Urban",
            region="CENTCOM", phases=["DCR", "PCC"],
        ))
        kw = client.last_kwargs
        assert kw["modelId"] == "test-model"
        assert isinstance(kw["system"], list) and "Role 2" in kw["system"][0]["text"]
        assert kw["messages"][0]["role"] == "user"
        assert "GSW" in kw["messages"][0]["content"][0]["text"]
        assert kw["inferenceConfig"]["maxTokens"] >= 1024

    def test_handles_prose_framed_json(self):
        # Claude sometimes wraps JSON in prose despite the system instruction.
        framed = "Here is the case:\n\n" + CANONICAL_CASE_JSON + "\n\nLet me know if you need adjustments."
        client = _FakeBedrockClient(framed)
        p = BedrockCaseProvider(model_id="test-model", client=client)
        case = asyncio.run(p.generate_case(
            case_type="x", mechanism="x", environment="x",
            region="x", phases=["DCR", "PCC"],
        ))
        assert "case_id" in case


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def _items(n: int) -> List[BatchItem]:
    return [
        BatchItem(
            key=(1, 0, i), case_type=f"case-{i}", mechanism="GSW",
            environment="Urban", region="CENTCOM",
            phases=["DCR", "PCC"], target_triage="T2", category="trauma_surgical",
        )
        for i in range(n)
    ]


class TestGenerateBatch:
    def test_empty_batch_returns_empty(self):
        p = BedrockCaseProvider(model_id="test-model", client=_FakeBedrockClient(CANONICAL_CASE_JSON))
        assert asyncio.run(p.generate_batch([])) == []

    def test_single_item_uses_single_path(self):
        client = _FakeBedrockClient(CANONICAL_CASE_JSON)
        p = BedrockCaseProvider(model_id="test-model", client=client)
        out = asyncio.run(p.generate_batch(_items(1)))
        assert len(out) == 1
        assert client.calls == 1

    def test_multi_item_returns_array(self):
        # Bedrock returns the cases under a top-level "cases" key per the
        # batch prompt's schema instruction.
        batch_json = '{"cases": [' + CANONICAL_CASE_JSON + "," + CANONICAL_CASE_JSON + "]}"
        client = _FakeBedrockClient(batch_json)
        p = BedrockCaseProvider(model_id="test-model", client=client)
        out = asyncio.run(p.generate_batch(_items(2)))
        assert len(out) == 2
        assert client.calls == 1  # one converse call for the whole batch

    def test_size_mismatch_raises(self):
        # Two requested, one returned — retry layer upstream catches this.
        batch_json = '{"cases": [' + CANONICAL_CASE_JSON + "]}"
        client = _FakeBedrockClient(batch_json)
        p = BedrockCaseProvider(model_id="test-model", client=client)
        with pytest.raises(ValueError, match="expected 2"):
            asyncio.run(p.generate_batch(_items(2)))


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestBedrockTimeout:
    def test_stalled_call_raises_timeout(self, monkeypatch):
        # Tighten the timeout for the test so we don't wait 60s.
        monkeypatch.setattr("backend.providers.bedrock._REQUEST_TIMEOUT_S", 0.05)
        p = BedrockCaseProvider(model_id="test-model", client=_StallingBedrockClient())
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(p.generate_text("hello"))


class TestTruncationDetection:
    """Bedrock signals mid-output truncation via stopReason='max_tokens'.
    Without explicit detection, the truncated text falls through to
    json.loads and produces a confusing JSONDecodeError; the regression in
    Apr 2026 made this opaque. The provider now raises a clear ValueError."""

    def test_max_tokens_stop_reason_raises_clear_error(self):
        class _TruncatingClient:
            def converse(self, **kwargs):
                # Return a "truncated" partial JSON with stopReason=max_tokens.
                return {
                    "output": {"message": {"role": "assistant", "content": [{"text": "{\"meta\": {\"title\": \"truncat"}]}},
                    "stopReason": "max_tokens",
                    "usage": {"inputTokens": 100, "outputTokens": 5000, "totalTokens": 5100},
                }
        p = BedrockCaseProvider(model_id="test-model", client=_TruncatingClient())
        with pytest.raises(ValueError, match="truncated output at maxTokens"):
            asyncio.run(p.generate_text("hello"))

    def test_end_turn_stop_reason_returns_text(self):
        # Sanity: normal completion path still works.
        client = _FakeBedrockClient(CANONICAL_CASE_JSON)
        p = BedrockCaseProvider(model_id="test-model", client=client)
        text = asyncio.run(p.generate_text("hello"))
        assert "meta" in text  # got the canonical JSON back unchanged


# ---------------------------------------------------------------------------
# generate_text
# ---------------------------------------------------------------------------

class TestGenerateText:
    def test_returns_response_text(self):
        client = _FakeBedrockClient("WARNO body here")
        p = BedrockCaseProvider(model_id="test-model", client=client)
        out = asyncio.run(p.generate_text("Generate a WARNO", system="You are a USMC officer."))
        assert out == "WARNO body here"
        assert client.last_kwargs["system"][0]["text"] == "You are a USMC officer."

    def test_no_system_omitted(self):
        client = _FakeBedrockClient("plain")
        p = BedrockCaseProvider(model_id="test-model", client=client)
        asyncio.run(p.generate_text("hello"))
        assert "system" not in client.last_kwargs

    def test_unexpected_response_shape_raises(self):
        # Use a custom client with malformed output.
        class _BrokenClient:
            def converse(self, **kwargs):
                return {"output": {"wrong_key": "..."}}
        p = BedrockCaseProvider(model_id="test-model", client=_BrokenClient())
        with pytest.raises(ValueError, match="unexpected Bedrock"):
            asyncio.run(p.generate_text("hello"))
