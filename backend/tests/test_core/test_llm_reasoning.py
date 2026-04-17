import asyncio
import time
from types import SimpleNamespace

import pytest

from core.llm_service import LLMService
from core.tool_registry import ToolRegistry
from core.tool_registry import ToolDefinition


class _FunctionCall:
    def __init__(self, name: str, args: object):
        self.name = name
        self.args = args


class _Part:
    def __init__(self, function_call: object | None = None, text: str | None = None):
        self.function_call = function_call
        self.text = text


class _Content:
    def __init__(self, parts: list[object]):
        self.parts = parts


class _Candidate:
    def __init__(self, parts: list[object]):
        self.content = _Content(parts)


class _ModelStub:
    def __init__(self, response: object):
        self._response = response

    def generate_content(self, *args, **kwargs):
        del args, kwargs
        return self._response


class _SlowModelStub:
    def __init__(self, sleep_seconds: float = 0.05):
        self.sleep_seconds = sleep_seconds

    def generate_content(self, *args, **kwargs):
        del args, kwargs
        time.sleep(self.sleep_seconds)
        return SimpleNamespace(function_calls=[], candidates=[], text="{}")


def _service_with_no_model(monkeypatch: pytest.MonkeyPatch) -> LLMService:
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    return LLMService()


def test_parse_agentic_decision_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    parsed = service._parse_agentic_decision('{"action": "show_hint"}')

    assert parsed["action"] == "show_hint"
    assert parsed["content"] == "Hay tiep tuc voi cau tiep theo nhe!"
    assert parsed["reasoning"] == "Structured response parsed"
    assert parsed["confidence"] == 0.6


def test_parse_agentic_decision_from_free_text(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    parsed = service._parse_agentic_decision("I suggest show_hint because confusion is high")

    assert parsed["action"] == "show_hint"
    assert parsed["confidence"] == 0.5


def test_parse_agentic_decision_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    parsed = service._parse_agentic_decision("No valid action keyword here")

    assert parsed["action"] == "next_question"
    assert parsed["parse_error"] is True


def test_coerce_args_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    assert service._coerce_args({"a": 1}) == {"a": 1}
    assert service._coerce_args(None) == {}
    assert service._coerce_args([("a", 1)]) == {"a": 1}

    class _Bad:
        def items(self):
            raise RuntimeError("bad")

    assert service._coerce_args(_Bad()) == {}


def test_extract_function_calls_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)
    response = SimpleNamespace(
        function_calls=[_FunctionCall("get_empathy_state", {"x": 1})],
        candidates=[
            _Candidate(parts=[_Part(function_call=_FunctionCall("get_empathy_state", {"x": 1}))]),
            _Candidate(parts=[_Part(function_call=_FunctionCall("get_strategy_suggestion", {"y": 2}))]),
        ],
    )

    calls = service._extract_function_calls(response)

    assert calls == [
        ("get_empathy_state", {"x": 1}),
        ("get_strategy_suggestion", {"y": 2}),
    ]


def test_format_student_input(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    text = service._format_student_input(
        {
            "question_text": "Q1",
            "student_answer": "A",
            "correct_answer": "B",
            "is_correct": False,
            "behavior_signals": {"response_time_ms": 1200, "idle_time_ratio": 0.1},
            "mode": "normal",
            "step": 3,
        }
    )

    assert "Cau hoi: Q1" in text
    assert "Ket qua: SAI" in text
    assert "mode=normal" in text
    assert "step=3" in text


@pytest.mark.asyncio
async def test_run_agentic_reasoning_fallback_when_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    result = await service.run_agentic_reasoning(
        session_id="s1",
        student_input={},
        tool_registry=ToolRegistry(),
        max_steps=3,
    )

    assert result["fallback"] is True
    assert result["action"] == "next_question"


@pytest.mark.asyncio
async def test_run_agentic_reasoning_unknown_tool_path(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)
    unknown_tool_response = SimpleNamespace(
        function_calls=[_FunctionCall("missing_tool", {})],
        candidates=[],
        text="",
    )
    service.model = _ModelStub(unknown_tool_response)

    result = await service.run_agentic_reasoning(
        session_id="s1",
        student_input={"question_text": "Q"},
        tool_registry=ToolRegistry(),
        max_steps=2,
    )

    assert result["fallback"] is True
    assert "Unknown tool" in result["reasoning"]
    assert result["reasoning_trace"]


@pytest.mark.asyncio
async def test_run_agentic_reasoning_initial_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)
    service.model = _SlowModelStub(sleep_seconds=0.05)

    result = await service.run_agentic_reasoning(
        session_id="s1",
        student_input={"question_text": "Q"},
        tool_registry=ToolRegistry(),
        max_steps=2,
        timeout_ms=10,
    )

    assert result["fallback"] is True
    assert "timed out" in result["reasoning"].lower()


@pytest.mark.asyncio
async def test_run_agentic_reasoning_tool_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)
    response = SimpleNamespace(
        function_calls=[_FunctionCall("slow_tool", {})],
        candidates=[],
        text="",
    )
    service.model = _ModelStub(response)

    async def _slow_tool(**kwargs):
        del kwargs
        await asyncio.sleep(0.05)
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="slow_tool",
            description="slow",
            parameters={"type": "object", "properties": {}},
            handler=_slow_tool,
        )
    )

    result = await service.run_agentic_reasoning(
        session_id="s1",
        student_input={"question_text": "Q"},
        tool_registry=registry,
        max_steps=2,
        timeout_ms=200,
        tool_timeout_ms=10,
    )

    assert result["fallback"] is True
    assert "tool timeout" in result["reasoning"].lower()


@pytest.mark.asyncio
async def test_run_agentic_reasoning_overrides_model_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)

    class _SequentialModel:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *args, **kwargs):
            del args, kwargs
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    function_calls=[
                        _FunctionCall(
                            "echo_session",
                            {"session_id": "attacker-session"},
                        )
                    ],
                    candidates=[],
                    text="",
                )
            return SimpleNamespace(function_calls=[], candidates=[], text='{"action": "next_question"}')

    service.model = _SequentialModel()
    captured_args: dict[str, object] = {}

    async def _echo_session(**kwargs):
        captured_args.update(kwargs)
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo_session",
            description="Echo session id",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            handler=_echo_session,
        )
    )

    result = await service.run_agentic_reasoning(
        session_id="trusted-session",
        student_input={"question_text": "Q"},
        tool_registry=registry,
        max_steps=3,
    )

    assert captured_args.get("session_id") == "trusted-session"
    assert result["action"] == "next_question"
