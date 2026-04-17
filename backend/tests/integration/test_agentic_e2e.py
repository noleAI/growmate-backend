from dataclasses import dataclass
from typing import Any, Dict

import pytest

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.orchestrator import AgenticOrchestrator


@dataclass
class _LLMResult:
    text: str
    fallback_used: bool


class _AgenticLLMStub:
    async def generate(self, prompt: str, fallback: str) -> _LLMResult:
        del prompt, fallback
        return _LLMResult(text="ok", fallback_used=False)

    async def run_agentic_reasoning(self, **kwargs):
        del kwargs
        return {
            "action": "show_hint",
            "content": "Hay nhin lai chain rule truoc khi lam tiep.",
            "reasoning": "confusion high and entropy high",
            "confidence": 0.82,
            "reasoning_trace": [
                {
                    "step": 1,
                    "tool": "get_academic_beliefs",
                    "args": {"session_id": "sess-e2e"},
                    "result_summary": "Top weakness: chain rule",
                },
                {
                    "step": 2,
                    "tool": "get_empathy_state",
                    "args": {"session_id": "sess-e2e"},
                    "result_summary": "Learner is very confused",
                },
            ],
            "llm_steps": 2,
            "fallback": False,
        }


class _FailingAgenticLLMStub(_AgenticLLMStub):
    async def run_agentic_reasoning(self, **kwargs):
        del kwargs
        raise RuntimeError("llm unavailable")


class _AcademicAgent(IAgent):
    @property
    def name(self) -> str:
        return "academic"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="academic_ok",
            payload={
                "entropy": 0.78,
                "confidence": 0.22,
                "belief_dist": {
                    "H01_Trig": 0.1,
                    "H02_ExpLog": 0.1,
                    "H03_Chain": 0.7,
                    "H04_Rules": 0.1,
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
            action="empathy_ok",
            payload={
                "confusion": 0.82,
                "fatigue": 0.25,
                "uncertainty": 0.6,
                "ess": 10.0,
                "particle_cloud": [[0.8, 0.2]] * 10,
                "weights": [0.1] * 10,
                "spam_detected": False,
                "afk_detected": False,
            },
        )


class _StrategyAgent(IAgent):
    @property
    def name(self) -> str:
        return "strategy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="continue_quiz",
            payload={"mode": "exam_prep", "selected_action": "show_hint"},
        )


class _StateManagerStub:
    def __init__(self) -> None:
        self.cache: Dict[str, SessionState] = {}
        self.broadcasts: list[dict[str, Any]] = []

    def register_session_context(self, session_id: str, student_id: str | None, access_token: str | None) -> None:
        del session_id, student_id, access_token

    async def load_or_init(self, session_id: str) -> SessionState:
        if session_id not in self.cache:
            self.cache[session_id] = SessionState(session_id=session_id)
        return self.cache[session_id]

    async def broadcast_ws(self, session_id: str, payload: dict[str, Any]) -> None:
        del session_id
        self.broadcasts.append(payload)

    async def sync_to_supabase(
        self,
        session_id: str,
        state: SessionState,
        force: bool = False,
        reason: str = "",
    ) -> None:
        del session_id, state, force, reason


@pytest.mark.asyncio
async def test_agentic_e2e_returns_reasoning_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_REASONING", "true")

    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=_StateManagerStub(),
        llm=_AgenticLLMStub(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-e2e",
        payload={
            "action_type": "submit_answer",
            "question_id": "MATH_DERIV_1",
            "response": {
                "selected": "A",
                "is_correct": False,
                "correct_answer": "B",
            },
            "behavior_signals": {"response_time_ms": 18000, "idle_time_ratio": 0.4},
            "mode": "exam_prep",
            "student_id": "student-1",
        },
    )

    assert result["reasoning_mode"] == "agentic"
    assert result["action"] == "show_hint"
    assert len(result["reasoning_trace"]) >= 1
    assert "reasoning_confidence" in result


@pytest.mark.asyncio
async def test_agentic_e2e_fallback_when_llm_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_REASONING", "true")

    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=_StateManagerStub(),
        llm=_FailingAgenticLLMStub(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-e2e-fallback",
        payload={
            "action_type": "submit_answer",
            "question_id": "MATH_DERIV_1",
            "response": {"selected": "A", "is_correct": False},
            "mode": "exam_prep",
            "student_id": "student-1",
        },
    )

    assert result["reasoning_mode"] == "adaptive"
    assert result["action"] in {
        "next_question",
        "show_hint",
        "drill_practice",
        "de_stress",
        "hitl",
        "hitl_pending",
        "pause_quiz",
    }
