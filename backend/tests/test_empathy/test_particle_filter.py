from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import numpy as np
import pytest

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.empathy_agent.particle_filter import ParticleFilter
from agents.orchestrator import AgenticOrchestrator


@pytest.fixture
def pf() -> ParticleFilter:
    np.random.seed(7)
    config = {
        "n_particles": 50,
        "process_noise": 0.05,
        "jitter_sigma": 0.01,
        "ess_threshold_ratio": 0.5,
    }
    return ParticleFilter(config=config)


def test_init_bounds(pf: ParticleFilter) -> None:
    assert pf.particles.shape == (50, 2)
    assert np.all((pf.particles >= 0.0) & (pf.particles <= 1.0))
    assert np.isclose(np.sum(pf.weights), 1.0)


def test_predict_preserves_bounds(pf: ParticleFilter) -> None:
    pf.predict()
    assert np.all((pf.particles >= 0.0) & (pf.particles <= 1.0))


def test_update_shifts_weight(pf: ParticleFilter) -> None:
    pf.particles = np.column_stack((np.linspace(0.0, 1.0, pf.n), np.linspace(0.0, 1.0, pf.n)))

    def mock_likelihood(particles: np.ndarray, signals: Dict[str, float]) -> np.ndarray:
        del signals
        fatigue = particles[:, 1]
        return -((1.0 - fatigue) ** 2) / 0.2

    pf.update({"response_time_ms": 16000.0}, mock_likelihood)
    weighted_fatigue = float(np.average(pf.particles[:, 1], weights=pf.weights))
    assert weighted_fatigue > 0.55


def test_resample_maintains_count(pf: ParticleFilter) -> None:
    pf.weights[0] = 0.99
    pf.weights[1:] = 0.01 / (pf.n - 1)
    pf.resample()
    assert len(pf.particles) == pf.n
    assert np.isclose(np.sum(pf.weights), 1.0)


def test_discretize_logic(pf: ParticleFilter) -> None:
    pf.particles[:, 0] = 0.7
    pf.particles[:, 1] = 0.3
    pf.weights = np.ones(pf.n, dtype=float) / pf.n
    assert pf.discretize_for_q() == "high_confusion_low_fatigue"


@pytest.mark.asyncio
async def test_process_emits_bridge_fields(pf: ParticleFilter) -> None:
    output = await pf.process(
        AgentInput(
            session_id="sess-bridge-1",
            behavior_signals={
                "response_time_ms": 9500,
                "error_rate": 0.5,
                "correction_rate": 0.3,
                "idle_time_ratio": 0.2,
            },
        )
    )

    payload = output.payload
    assert "q_state" in payload
    assert payload["q_state"] in {
        "low_confusion_low_fatigue",
        "low_confusion_high_fatigue",
        "high_confusion_low_fatigue",
        "high_confusion_high_fatigue",
    }
    assert "belief_distribution" in payload
    assert set(payload["belief_distribution"].keys()) == {
        "focused",
        "confused",
        "exhausted",
        "frustrated",
    }
    assert "eu_values" in payload
    assert "recommended_action" in payload
    assert "hitl_triggered" in payload


def test_fallback_on_nan_weights(pf: ParticleFilter) -> None:
    def invalid_likelihood(particles: np.ndarray, signals: Dict[str, float]) -> np.ndarray:
        del particles, signals
        return np.full(pf.n, np.nan)

    pf.update({}, invalid_likelihood)
    assert np.allclose(pf.weights, np.ones(pf.n) / pf.n)


def test_should_resample_when_ess_low(pf: ParticleFilter) -> None:
    pf.weights = np.zeros(pf.n, dtype=float)
    pf.weights[0] = 1.0
    assert pf.should_resample()


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
        return AgentOutput(action="academic_ok", payload={"entropy": 0.1})


class _LegacyEmpathyAgent(IAgent):
    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(action="legacy", payload={"particles": [0.1, 0.2, 0.3]})


class _StrategyAgent(IAgent):
    @property
    def name(self) -> str:
        return "strategy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        q_state = input_data.current_state.get("empathy_state", {}).get("q_state", "")
        return AgentOutput(action="next_question", payload={"q_state_seen": q_state})


class _OverrideEmpathyAgent(IAgent):
    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="empathy_tracked",
            payload={
                "confusion": 0.8,
                "fatigue": 0.9,
                "uncertainty": 0.95,
                "ess": 4.0,
                "particle_cloud": [[0.8, 0.9]] * 8,
                "weights": [0.125] * 8,
                "q_state": "high_confusion_high_fatigue",
                "recommended_action": "suggest_break",
                "override_recommended_action": "de_stress",
                "hitl_triggered": True,
            },
        )


class _SupabaseTableStub:
    def __init__(self, sink: list[dict]):
        self.sink = sink

    def insert(self, payload: dict):
        self.sink.append(payload)
        return self

    def execute(self):
        return {"status": "ok"}


class _SupabaseStub:
    def __init__(self):
        self.audit_logs: list[dict] = []

    def table(self, table_name: str) -> _SupabaseTableStub:
        assert table_name == "audit_logs"
        return _SupabaseTableStub(self.audit_logs)


class _StateManagerStub:
    def __init__(self):
        self.cache: Dict[str, SessionState] = {}
        self.broadcasts: list[dict] = []
        self.supabase = _SupabaseStub()

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
async def test_orchestrator_runs_pf_fallback_pipeline() -> None:
    state_mgr = _StateManagerStub()
    agents: Dict[str, IAgent] = {
        "academic": _AcademicAgent(),
        "empathy": _LegacyEmpathyAgent(),
        "strategy": _StrategyAgent(),
    }
    orchestrator = AgenticOrchestrator(agents=agents, state_mgr=state_mgr, llm=_DummyLLM())

    result = await orchestrator.run_session_step(
        session_id="sess-pf-1",
        payload={
            "question_id": "q-1",
            "response": {"answer": "A"},
            "behavior_signals": {
                "response_time_ms": 9000,
                "incorrect_attempts": 1,
                "confidence_slider": 0.4,
            },
        },
    )

    state = await state_mgr.load_or_init("sess-pf-1")

    assert result["action"] in {"next_question", "de_stress"}
    assert state.step == 1
    assert "confusion" in state.empathy_state
    assert "fatigue" in state.empathy_state
    assert "ess" in state.empathy_state
    assert "q_state" in state.strategy_state
    assert "belief_distribution" in state.empathy_state
    assert "eu_values" in state.empathy_state
    assert state_mgr.broadcasts
    assert state_mgr.broadcasts[0]["empathy"]["component"] == "empathy_agent"


@pytest.mark.asyncio
async def test_orchestrator_applies_empathy_override() -> None:
    state_mgr = _StateManagerStub()
    agents: Dict[str, IAgent] = {
        "academic": _AcademicAgent(),
        "empathy": _OverrideEmpathyAgent(),
        "strategy": _StrategyAgent(),
    }
    orchestrator = AgenticOrchestrator(agents=agents, state_mgr=state_mgr, llm=_DummyLLM())

    result = await orchestrator.run_session_step(
        session_id="sess-pf-override",
        payload={
            "question_id": "q-override",
            "response": {"answer": "B"},
            "behavior_signals": {"response_time_ms": 14000},
        },
    )

    assert result["action"] in {"de_stress", "hitl_pending"}


@pytest.mark.asyncio
async def test_orchestrator_hitl_emits_ws_and_audit_log() -> None:
    state_mgr = _StateManagerStub()
    agents: Dict[str, IAgent] = {
        "academic": _AcademicAgent(),
        "empathy": _OverrideEmpathyAgent(),
        "strategy": _StrategyAgent(),
    }
    orchestrator = AgenticOrchestrator(agents=agents, state_mgr=state_mgr, llm=_DummyLLM())

    result = await orchestrator.run_session_step(
        session_id="sess-pf-hitl",
        payload={
            "question_id": "q-hitl",
            "response": {"answer": "C"},
            "behavior_signals": {"response_time_ms": 18000},
        },
    )

    assert result["action"] == "hitl_pending"
    assert any(msg.get("event") == "hitl_triggered" for msg in state_mgr.broadcasts)
    assert state_mgr.supabase.audit_logs
    assert state_mgr.supabase.audit_logs[0]["event_type"] == "hitl_trigger"


def test_detect_spam_with_fast_low_accuracy_signals(pf: ParticleFilter) -> None:
    signals = [
        {"response_time_ms": 1200, "is_correct": False},
        {"response_time_ms": 1500, "is_correct": False},
        {"response_time_ms": 1600, "is_correct": False},
    ]
    assert pf.detect_spam(signals) is True


def test_detect_afk_after_threshold(pf: ParticleFilter) -> None:
    last_signal_time = (datetime.now(timezone.utc) - timedelta(seconds=220)).isoformat()
    assert pf.detect_afk(last_signal_time) is True


@pytest.mark.asyncio
async def test_process_sets_pause_flags_when_spam_detected(pf: ParticleFilter) -> None:
    output = await pf.process(
        AgentInput(
            session_id="sess-spam",
            behavior_signals={"response_time_ms": 1100, "is_correct": False},
            signal_history=[
                {"response_time_ms": 1200, "is_correct": False},
                {"response_time_ms": 1300, "is_correct": False},
            ],
        )
    )

    assert output.payload["spam_detected"] is True
    assert output.payload["pause_recommended"] is True
