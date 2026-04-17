from dataclasses import dataclass
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

import agents.orchestrator as orchestrator_module
from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.orchestrator import AgenticOrchestrator


@dataclass
class _LLMResult:
    text: str
    fallback_used: bool


class _LLMAdaptiveOnly:
    async def generate(self, prompt: str, fallback: str) -> _LLMResult:
        del prompt, fallback
        return _LLMResult(text="ok", fallback_used=False)


class _LLMFailingAgentic(_LLMAdaptiveOnly):
    async def run_agentic_reasoning(self, **kwargs):
        del kwargs
        raise RuntimeError("agentic failed")


class _LLMSlowAgentic(_LLMAdaptiveOnly):
    async def run_agentic_reasoning(self, **kwargs):
        del kwargs
        import asyncio

        await asyncio.sleep(0.05)
        return {
            "action": "show_hint",
            "content": "x",
            "reasoning": "x",
            "confidence": 0.5,
            "reasoning_trace": [],
        }


class _AcademicAgent(IAgent):
    @property
    def name(self) -> str:
        return "academic"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="academic_ok",
            payload={
                "entropy": 0.1,
                "confidence": 0.9,
                "belief_dist": {
                    "H01_Trig": 0.25,
                    "H02_ExpLog": 0.25,
                    "H03_Chain": 0.25,
                    "H04_Rules": 0.25,
                },
            },
        )


class _EmpathyAgent(IAgent):
    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="empathy_tracked",
            payload={
                "confusion": 0.2,
                "fatigue": 0.1,
                "uncertainty": 0.2,
                "ess": 10.0,
                "particle_cloud": [[0.2, 0.2]] * 10,
                "weights": [0.1] * 10,
                "q_state": "low_confusion_low_fatigue",
                "spam_detected": False,
                "afk_detected": False,
                "pause_recommended": False,
            },
        )


class _StrategyAgent(IAgent):
    @property
    def name(self) -> str:
        return "strategy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(action="continue_quiz", payload={"mode": "normal"})


class _StateManagerStub:
    def __init__(self):
        self.cache: Dict[str, SessionState] = {}
        self.broadcasts: list[dict] = []

    async def load_or_init(self, session_id: str) -> SessionState:
        if session_id not in self.cache:
            self.cache[session_id] = SessionState(session_id=session_id)
        return self.cache[session_id]

    async def broadcast_ws(self, session_id: str, payload: Dict[str, Any]) -> None:
        del session_id
        self.broadcasts.append(payload)

    async def sync_to_supabase(self, session_id: str, state: SessionState) -> None:
        del session_id, state


class _DynamicPlannerStub:
    async def generate_dynamic_plan(self, session_id: str, context: dict, llm_service) -> list[str]:
        del session_id, context, llm_service
        return ["de_stress", "next_question"]


@pytest.mark.asyncio
async def test_fallback_to_adaptive_when_agentic_reasoning_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_LLM_REASONING", "true")
    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_LLMFailingAgentic(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-agentic-fail",
        payload={"question_id": "q1", "response": {"answer": "A"}},
    )

    assert result["reasoning_mode"] == "adaptive"
    assert "llm_steps" in result
    assert "tool_count" in result
    assert "fallback_used" in result
    assert result["action"] in {
        "next_question",
        "show_hint",
        "drill_practice",
        "de_stress",
        "hitl",
        "hitl_pending",
    }


@pytest.mark.asyncio
async def test_planning_feature_flag_uses_dynamic_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_REASONING", "false")
    monkeypatch.setenv("PLANNING_ENABLED", "true")

    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_LLMAdaptiveOnly(),
    )
    orchestrator.dynamic_planner = _DynamicPlannerStub()

    result = await orchestrator.run_session_step(
        session_id="sess-plan",
        payload={"question_id": "q1", "response": {"answer": "A"}},
    )

    assert result["action"] == "de_stress"
    state = state_mgr.cache["sess-plan"]
    assert state.strategy_state["dynamic_plan"] == ["next_question"]


@pytest.mark.asyncio
async def test_agentic_timeout_falls_back_to_adaptive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_REASONING", "true")
    monkeypatch.setenv("AGENTIC_TIMEOUT_MS", "10")

    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_LLMSlowAgentic(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-agentic-timeout",
        payload={"question_id": "q1", "response": {"answer": "A"}},
    )

    assert result["reasoning_mode"] == "adaptive"


@pytest.mark.asyncio
async def test_track_llm_usage_applies_token_multiplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_LLM_REASONING", "false")
    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_LLMAdaptiveOnly(),
    )

    mocked_increment = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "increment_user_token_usage", mocked_increment)

    await orchestrator._track_llm_usage(
        student_id="user-1",
        session_id="sess-1",
        response_text="a" * 40,
        access_token=None,
        token_multiplier=3,
    )

    assert mocked_increment.await_count == 1
    kwargs = mocked_increment.await_args.kwargs
    assert kwargs["user_id"] == "user-1"
    assert kwargs["tokens_used"] == 30
