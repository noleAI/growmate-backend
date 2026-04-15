from dataclasses import dataclass
from typing import Any, Dict

import pytest

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.orchestrator import AgenticOrchestrator


@dataclass
class _LLMResult:
    text: str
    fallback_used: bool


class _DummyLLM:
    async def generate(self, prompt: str, fallback: str) -> _LLMResult:
        del prompt, fallback
        return _LLMResult(text="ok", fallback_used=False)


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


class _SpamEmpathyAgent(IAgent):
    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="empathy_tracked",
            payload={
                "confusion": 0.2,
                "fatigue": 0.2,
                "uncertainty": 0.2,
                "ess": 10.0,
                "particle_cloud": [[0.2, 0.2]] * 10,
                "weights": [0.1] * 10,
                "q_state": "low_confusion_low_fatigue",
                "spam_detected": True,
                "afk_detected": False,
                "pause_recommended": True,
            },
        )


class _NormalEmpathyAgent(IAgent):
    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="empathy_tracked",
            payload={
                "confusion": 0.2,
                "fatigue": 0.2,
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


@pytest.mark.asyncio
async def test_orchestrator_pauses_quiz_when_spam_detected() -> None:
    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _SpamEmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_DummyLLM(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-spam-pause",
        payload={
            "question_id": "q1",
            "response": {"answer": "A"},
            "behavior_signals": {"response_time_ms": 1200},
        },
    )

    assert result["action"] == "pause_quiz"
    assert result["payload"]["reason"] == "spam"
    assert result["dashboard_update"]["pause_state"] is True


@pytest.mark.asyncio
async def test_orchestrator_gently_redirects_after_three_off_topic_events() -> None:
    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _NormalEmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_DummyLLM(),
    )

    for step in range(2):
        result = await orchestrator.run_session_step(
            session_id="sess-off-topic",
            payload={
                "question_id": f"q{step}",
                "response": {"answer": "A"},
                "behavior_signals": {"response_time_ms": 6000},
                "is_off_topic": True,
            },
        )
        assert result["action"] != "gentle_redirect"

    final_result = await orchestrator.run_session_step(
        session_id="sess-off-topic",
        payload={
            "question_id": "q2",
            "response": {"answer": "B"},
            "behavior_signals": {"response_time_ms": 6000},
            "is_off_topic": True,
        },
    )

    assert final_result["action"] == "gentle_redirect"
    assert final_result["payload"]["reason"] == "off_topic"
