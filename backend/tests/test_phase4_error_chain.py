from dataclasses import dataclass
from typing import Any, Dict

import pytest

from agents.academic_agent.bayesian_tracker import BayesianTracker
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


class _AcademicWithErrorChain(IAgent):
    def __init__(self) -> None:
        self.error_chain_updated = False

    @property
    def name(self) -> str:
        return "academic"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="academic_ok",
            payload={
                "entropy": 0.95,
                "confidence": 0.05,
                "belief_dist": {
                    "H01_Trig": 0.25,
                    "H02_ExpLog": 0.25,
                    "H03_Chain": 0.25,
                    "H04_Rules": 0.25,
                },
            },
        )

    def update_from_error_chain(self, error_chain: list[dict]) -> dict:
        self.error_chain_updated = bool(error_chain)
        return {
            "H01_Trig": 0.7,
            "H02_ExpLog": 0.1,
            "H03_Chain": 0.1,
            "H04_Rules": 0.1,
        }

    def get_entropy(self) -> float:
        return 0.6


class _EmpathyAgent(IAgent):
    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="empathy_tracked",
            payload={
                "confusion": 0.1,
                "fatigue": 0.1,
                "uncertainty": 0.2,
                "ess": 10.0,
                "particle_cloud": [[0.1, 0.1]] * 10,
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


def test_bayesian_error_chain_weights_root_over_surface() -> None:
    tracker = BayesianTracker(
        prior={
            "H01_Trig": 0.25,
            "H02_ExpLog": 0.25,
            "H03_Chain": 0.25,
            "H04_Rules": 0.25,
        }
    )

    updated = tracker.update_from_error_chain(
        [
            {"level": "surface", "description": "operator misuse in derivative"},
            {"level": "root", "description": "trig derivative confusion with sin/cos"},
        ]
    )

    assert abs(sum(updated.values()) - 1.0) < 1e-6
    assert updated["H01_Trig"] > updated["H04_Rules"]


def test_bayesian_error_chain_propagates_foundation_chain_to_rules() -> None:
    tracker = BayesianTracker(
        prior={
            "H01_Trig": 0.25,
            "H02_ExpLog": 0.25,
            "H03_Chain": 0.25,
            "H04_Rules": 0.25,
        }
    )

    updated = tracker.update_from_error_chain(
        [{"level": "foundation", "description": "chain rule and inner function mismatch"}]
    )

    assert updated["H03_Chain"] > updated["H04_Rules"]
    assert updated["H04_Rules"] > updated["H01_Trig"]


@pytest.mark.asyncio
async def test_orchestrator_applies_error_chain_from_response_payload() -> None:
    state_mgr = _StateManagerStub()
    academic = _AcademicWithErrorChain()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": academic,
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_DummyLLM(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-error-chain",
        payload={
            "question_id": "q-ec",
            "response": {
                "answer": "A",
                "error_chain": [
                    {"level": "root", "description": "trig rule mismatch"},
                ],
            },
            "behavior_signals": {"response_time_ms": 5000},
        },
    )

    assert academic.error_chain_updated is True
    assert result["dashboard_update"]["academic"]["belief_dist"]["H01_Trig"] == pytest.approx(0.7)
    assert result["dashboard_update"]["academic"]["entropy"] == pytest.approx(0.6)
