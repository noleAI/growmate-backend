import pytest

from agents.reasoning_loop import ReActEngine


class _LLMStub:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run_agentic_reasoning(
        self,
        session_id: str,
        student_input: dict,
        tool_registry,
        max_steps: int,
    ):
        self.calls.append((session_id, student_input, tool_registry, max_steps))
        return self.result


@pytest.mark.asyncio
async def test_react_engine_maps_result_and_trace() -> None:
    llm = _LLMStub(
        {
            "action": "show_hint",
            "content": "hint text",
            "reasoning": "high confusion",
            "confidence": 0.81,
            "reasoning_trace": [
                {
                    "tool": "get_empathy_state",
                    "args": {"session_id": "s1"},
                    "result_summary": "confusion high",
                }
            ],
            "fallback": False,
        }
    )
    engine = ReActEngine(llm_service=llm, tool_registry=object())

    result = await engine.reason(
        session_id="s1",
        student_input={"question_text": "q1"},
        max_steps=4,
    )

    assert result.action == "show_hint"
    assert result.content == "hint text"
    assert result.reasoning == "high confusion"
    assert result.confidence == 0.81
    assert result.fallback_used is False
    assert len(result.steps) == 1
    assert result.steps[0].action == "get_empathy_state"
    assert llm.calls[0][3] == 4


@pytest.mark.asyncio
async def test_react_engine_fallback_when_llm_raises() -> None:
    class _FailingLLM:
        async def run_agentic_reasoning(self, **kwargs):
            del kwargs
            raise RuntimeError("llm failed")

    engine = ReActEngine(llm_service=_FailingLLM(), tool_registry=object())

    result = await engine.reason(
        session_id="s1",
        student_input={"question_text": "q1"},
        max_steps=2,
    )

    assert result.action == "next_question"
    assert result.fallback_used is True
    assert "ReAct error" in result.reasoning
