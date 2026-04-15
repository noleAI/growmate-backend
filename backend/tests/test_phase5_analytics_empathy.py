from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pytest

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.empathy_agent.particle_filter import ParticleFilter
from agents.orchestrator import AgenticOrchestrator


@pytest.mark.asyncio
async def test_particle_filter_derives_signals_from_analytics_data() -> None:
    captured: Dict[str, float] = {}

    def _recording_likelihood(particles: np.ndarray, signals: Dict[str, float]) -> np.ndarray:
        del particles
        captured.clear()
        captured.update(signals)
        return np.zeros(60, dtype=float)

    np.random.seed(13)
    pf = ParticleFilter(config={"n_particles": 60}, likelihood_fn=_recording_likelihood)

    output = await pf.process(
        AgentInput(
            session_id="sess-analytics-derive",
            behavior_signals={},
            analytics_data={
                "accuracy_rate": 0.6,
                "engagement_score": 0.2,
                "session_time_minutes": 60,
            },
        )
    )

    assert captured["error_rate"] == pytest.approx(0.4)
    assert captured["confidence_slider"] == pytest.approx(0.2)
    assert captured["idle_time_ratio"] == pytest.approx(0.8)
    assert output.metadata["analytics_signals_used"] is True


@pytest.mark.asyncio
async def test_particle_filter_blends_behavior_and_analytics_signals() -> None:
    captured: Dict[str, float] = {}

    def _recording_likelihood(particles: np.ndarray, signals: Dict[str, float]) -> np.ndarray:
        del particles
        captured.clear()
        captured.update(signals)
        return np.zeros(40, dtype=float)

    np.random.seed(17)
    pf = ParticleFilter(config={"n_particles": 40}, likelihood_fn=_recording_likelihood)

    await pf.process(
        AgentInput(
            session_id="sess-analytics-blend",
            behavior_signals={"error_rate": 0.2},
            analytics_data={"accuracy_rate": 0.0},
        )
    )

    # 0.7 * behavior + 0.3 * analytics-derived
    assert captured["error_rate"] == pytest.approx(0.44)


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
        return AgentOutput(action="academic_ok", payload={"entropy": 0.1, "confidence": 0.9})


class _AnalyticsAwareEmpathyAgent(IAgent):
    def __init__(self) -> None:
        self.seen_analytics_data: Dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.seen_analytics_data = dict(input_data.analytics_data or {})
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
            },
        )


class _StrategyAgent(IAgent):
    @property
    def name(self) -> str:
        return "strategy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(action="next_question", payload={})


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
async def test_orchestrator_forwards_analytics_data_to_empathy_agent() -> None:
    state_mgr = _StateManagerStub()
    empathy = _AnalyticsAwareEmpathyAgent()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": empathy,
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_DummyLLM(),
    )

    analytics_payload = {
        "accuracy_rate": 0.55,
        "engagement_score": 0.35,
        "session_time_minutes": 48,
    }

    await orchestrator.run_session_step(
        session_id="sess-forward-analytics",
        payload={
            "question_id": "q-analytics",
            "response": {"answer": "A"},
            "behavior_signals": {"response_time_ms": 4000},
            "analytics_data": analytics_payload,
        },
    )

    assert empathy.seen_analytics_data == analytics_payload
