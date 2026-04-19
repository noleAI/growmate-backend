from __future__ import annotations

from typing import Any

import pytest

from core.llm_service import LLMService


def _service_with_no_model(monkeypatch: pytest.MonkeyPatch) -> LLMService:
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCLOUD_PROJECT", raising=False)
    return LLMService()


def _mark_ready(service: LLMService) -> None:
    # `_ready` only checks for non-None client.
    service._client = object()


def test_generate_tutor_response_success(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    monkeypatch.setattr(
        service,
        "_call_model",
        lambda *_args, **_kwargs: '{"message_to_student":"ok","ui_action":"continue"}',
    )

    result = service.generate_tutor_response(
        {"ui_action": "continue", "action": "next_question"},
        {"fatigue": 0.1},
    )

    assert result == {
        "message_to_student": "ok",
        "ui_action": "continue",
    }


def test_generate_tutor_response_parse_failure_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    monkeypatch.setattr(service, "_call_model", lambda *_args, **_kwargs: "not-json")

    result = service.generate_tutor_response(
        {"ui_action": "show_break"},
        {"fatigue": 0.8},
    )

    assert result["ui_action"] == "show_break"
    assert "Hệ thống đang bận" in result["message_to_student"]


def test_generate_tutor_response_model_failure_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    def _raise(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_call_model", _raise)

    result = service.generate_tutor_response({"ui_action": "continue"}, {})

    assert result["ui_action"] == "continue"
    assert "Hệ thống đang bận" in result["message_to_student"]


@pytest.mark.asyncio
async def test_generate_chat_response_not_ready_returns_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)

    result = await service.generate_chat_response(
        system_prompt="sys",
        history=[],
        user_message="hello",
        fallback="fb",
    )

    assert result == "fb"


@pytest.mark.asyncio
async def test_generate_chat_response_success_without_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    monkeypatch.setattr(service, "_call_model", lambda *_args, **_kwargs: "assistant-answer")

    result = await service.generate_chat_response(
        system_prompt="sys",
        history=[{"role": "user", "content": "q1"}],
        user_message="q2",
        use_search=False,
    )

    assert result == "assistant-answer"


@pytest.mark.asyncio
async def test_generate_chat_response_empty_model_output_returns_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    monkeypatch.setattr(service, "_call_model", lambda *_args, **_kwargs: "")

    result = await service.generate_chat_response(
        system_prompt="sys",
        history=[],
        user_message="q",
        fallback="fb",
        use_search=False,
    )

    assert result == "fb"


@pytest.mark.asyncio
async def test_generate_chat_response_exception_returns_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    def _raise(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("model error")

    monkeypatch.setattr(service, "_call_model", _raise)

    result = await service.generate_chat_response(
        system_prompt="sys",
        history=[],
        user_message="q",
        fallback="fb",
        use_search=False,
    )

    assert result == "fb"


@pytest.mark.asyncio
async def test_generate_chat_response_retries_without_search_on_tool_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    calls: list[list | None] = []

    def _call_model(*_args: Any, **kwargs: Any) -> str:
        tools = kwargs.get("tools")
        calls.append(tools)
        if tools is not None:
            raise RuntimeError("search tool unsupported")
        return "assistant-retry-answer"

    monkeypatch.setattr(service, "_call_model", _call_model)

    result = await service.generate_chat_response(
        system_prompt="sys",
        history=[],
        user_message="q",
        fallback="fb",
        use_search=True,
    )

    assert result == "assistant-retry-answer"
    assert len(calls) == 2
    assert calls[0] is not None
    assert calls[1] is None


@pytest.mark.asyncio
async def test_generate_chat_response_retries_without_search_then_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    def _raise(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("model error")

    monkeypatch.setattr(service, "_call_model", _raise)

    result = await service.generate_chat_response(
        system_prompt="sys",
        history=[],
        user_message="q",
        fallback="fb",
        use_search=True,
    )

    assert result == "fb"


@pytest.mark.asyncio
async def test_generate_chat_response_with_image_not_ready_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)

    result = await service.generate_chat_response_with_image(
        system_prompt="sys",
        user_message="q",
        image_bytes=b"123",
        fallback="fb",
    )

    assert result == "fb"


@pytest.mark.asyncio
async def test_generate_chat_response_with_image_success(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    monkeypatch.setattr(service, "_call_model", lambda *_args, **_kwargs: "vision-answer")

    result = await service.generate_chat_response_with_image(
        system_prompt="sys",
        user_message="q",
        image_bytes=b"123",
    )

    assert result == "vision-answer"


@pytest.mark.asyncio
async def test_generate_chat_response_with_image_exception_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    _mark_ready(service)

    def _raise(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("vision error")

    monkeypatch.setattr(service, "_call_model", _raise)

    result = await service.generate_chat_response_with_image(
        system_prompt="sys",
        user_message="q",
        image_bytes=b"123",
        fallback="fb",
    )

    assert result == "fb"


@pytest.mark.asyncio
async def test_generate_wrapper_sets_fallback_true_when_message_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    monkeypatch.setattr(
        service,
        "generate_tutor_response",
        lambda *_args, **_kwargs: {"message_to_student": "   "},
    )

    result = await service.generate("p", "fb")

    assert result.text == "fb"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_generate_wrapper_sets_fallback_false_when_message_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_with_no_model(monkeypatch)
    monkeypatch.setattr(
        service,
        "generate_tutor_response",
        lambda *_args, **_kwargs: {"message_to_student": "hello"},
    )

    result = await service.generate("p", "fb")

    assert result.text == "hello"
    assert result.fallback_used is False


def test_extract_text_from_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    class _Part:
        def __init__(self, text: str | None):
            self.text = text

    class _Content:
        def __init__(self, parts: list[object]):
            self.parts = parts

    class _Candidate:
        def __init__(self, parts: list[object]):
            self.content = _Content(parts)

    response = type(
        "Resp",
        (),
        {
            "text": None,
            "candidates": [_Candidate([_Part("line1"), _Part("line2")])],
        },
    )()

    assert service._extract_text(response) == "line1\nline2"


def test_parse_agentic_decision_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    parsed = service._parse_agentic_decision("")

    assert parsed["fallback"] is True
    assert "Empty LLM response" in parsed["reasoning"]


def test_resolve_timeout_ms_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    assert service._resolve_timeout_ms(
        override=25,
        env_name="AGENTIC_TIMEOUT_MS",
        default=8000,
    ) == 25

    monkeypatch.setenv("AGENTIC_TIMEOUT_MS", "15")
    assert service._resolve_timeout_ms(
        override=None,
        env_name="AGENTIC_TIMEOUT_MS",
        default=8000,
    ) == 15

    monkeypatch.setenv("AGENTIC_TIMEOUT_MS", "oops")
    assert service._resolve_timeout_ms(
        override=None,
        env_name="AGENTIC_TIMEOUT_MS",
        default=8000,
    ) == 8000


def test_build_gemini_tools_handles_registry_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    class _Registry:
        def to_gemini_tools(self):
            raise RuntimeError("boom")

    assert service._build_gemini_tools(_Registry()) is None


def test_invoke_model_fallback_signatures(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)

    class _Model:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1 and kwargs:
                raise TypeError("kwargs unsupported")
            if self.calls == 2 and len(args) == 2:
                raise TypeError("two-arg unsupported")
            return {"ok": True, "args": args, "kwargs": kwargs}

    service.model = _Model()

    result = service._invoke_model(
        "prompt",
        generation_config={"temperature": 0.3},
        tools=[{"name": "t"}],
    )

    assert result["ok"] is True


def test_invoke_model_when_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_with_no_model(monkeypatch)
    service.model = None

    with pytest.raises(RuntimeError, match="Model is not initialized"):
        service._invoke_model("prompt")
