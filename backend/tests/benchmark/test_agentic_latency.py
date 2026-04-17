from dataclasses import dataclass
from time import perf_counter
from typing import Any, Dict

import pytest

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.orchestrator import AgenticOrchestrator


@dataclass
class _LLMResult:
    text: str
    fallback_used: bool


class _LLMStub:
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
                "uncertainty": 0.1,
                "ess": 10.0,
                "particle_cloud": [[0.1, 0.1]] * 10,
                "weights": [0.1] * 10,
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

    async def load_or_init(self, session_id: str) -> SessionState:
        if session_id not in self.cache:
            self.cache[session_id] = SessionState(session_id=session_id)
        return self.cache[session_id]

    async def broadcast_ws(self, session_id: str, payload: Dict[str, Any]) -> None:
        del session_id, payload

    async def sync_to_supabase(self, session_id: str, state: SessionState) -> None:
        del session_id, state


@pytest.mark.asyncio
async def test_agentic_latency_p95_under_5_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_REASONING", "false")

    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=_StateManagerStub(),
        llm=_LLMStub(),
    )

    latencies = []
    for idx in range(25):
        start = perf_counter()
        await orchestrator.run_session_step(
            session_id="bench-session",
            payload={"question_id": f"q{idx}", "response": {"answer": "A"}},
        )
        latencies.append(perf_counter() - start)

    p95_index = max(0, int(len(latencies) * 0.95) - 1)
    p95 = sorted(latencies)[p95_index]
    assert p95 < 5.0
