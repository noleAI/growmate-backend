from types import SimpleNamespace

import pytest

from agents.academic_agent.htn_planner import HTNPlanner


class _LLMServiceStub:
    def __init__(self, text: str):
        self.model = SimpleNamespace(
            generate_content=lambda prompt, generation_config: SimpleNamespace(text=text)
        )


@pytest.mark.asyncio
async def test_generate_dynamic_plan_fallback_when_llm_unavailable() -> None:
    planner = HTNPlanner()

    result = await planner.generate_dynamic_plan(
        session_id="s1",
        context={"confidence": 0.4},
        llm_service=None,
    )

    assert result == ["next_question", "show_hint", "next_question"]


@pytest.mark.asyncio
async def test_generate_dynamic_plan_parses_and_normalizes_actions() -> None:
    planner = HTNPlanner()
    llm = _LLMServiceStub('["show_hint", "drill_practice", "drill_practice", "drill_practice", "hitl"]')

    result = await planner.generate_dynamic_plan(
        session_id="s1",
        context={
            "fatigue": 0.8,
            "accuracy_recent": 0.2,
            "entropy": 0.6,
            "confusion": 0.4,
        },
        llm_service=llm,
    )

    assert result[0] == "de_stress"
    assert result[-1] == "next_question"
    assert len(result) <= 5

    drill_streak = 0
    for action in result:
        if action == "drill_practice":
            drill_streak += 1
            assert drill_streak <= 2
        else:
            drill_streak = 0


def test_normalize_dynamic_plan_filters_invalid_actions() -> None:
    planner = HTNPlanner()

    normalized = planner._normalize_dynamic_plan(
        ["invalid", "next_question", "show_hint", "unknown"],
        context={"fatigue": 0.1, "accuracy_recent": 0.8},
        max_length=5,
    )

    assert normalized == ["next_question", "show_hint", "next_question"]
