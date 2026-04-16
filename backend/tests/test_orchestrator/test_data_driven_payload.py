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
            payload={"entropy": 0.1, "confidence": 0.9},
        )


class _WeakAcademicAgent(IAgent):
    @property
    def name(self) -> str:
        return "academic"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        del input_data
        return AgentOutput(
            action="academic_ok",
            payload={
                "entropy": 0.6,
                "confidence": 0.4,
                "belief_dist": {
                    "H01_Trig": 0.12,
                    "H02_ExpLog": 0.18,
                    "H03_Chain": 0.52,
                    "H04_Rules": 0.18,
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
                "uncertainty": 0.2,
                "ess": 12.0,
                "particle_cloud": [[0.1, 0.1]] * 12,
                "weights": [1 / 12] * 12,
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
async def test_orchestrator_emits_data_driven_payload() -> None:
    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_DummyLLM(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-data-driven",
        payload={
            "question_id": "q-1",
            "response": {"answer": "A"},
            "behavior_signals": {"response_time_ms": 8000},
        },
    )

    assert result["data_driven"] is not None
    assert result["data_driven"]["diagnosis"]["diagnosisId"] == "MATH_DERIV_DIAG_NORMAL_SUCCESS"
    assert result["data_driven"]["systemBehavior"]["riskBandFromThresholds"] == "low"
    assert result["data_driven"]["selectedIntervention"]["interventionId"] == "INTV_REVIEW_DERIV_RULES"
    assert "formulaRecommendations" in result["data_driven"]
    assert isinstance(result["data_driven"]["formulaRecommendations"], list)
    assert "data_driven" in result["dashboard_update"]


@pytest.mark.asyncio
async def test_orchestrator_applies_missing_plan_fallback(monkeypatch) -> None:
    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _AcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_DummyLLM(),
    )

    def _fake_resolve_diagnosis(mode: str, risk_level: str, prefer_fallback_safe: bool = False) -> dict:
        del mode, risk_level, prefer_fallback_safe
        return {
            "diagnosisId": "FAKE_DIAG",
            "mode": "recovery",
            "requiresHITL": False,
            "interventionPlan": ["INTV_UNKNOWN"],
        }

    monkeypatch.setattr(
        orchestrator.data_packages,
        "resolve_diagnosis",
        _fake_resolve_diagnosis,
    )

    result = await orchestrator.run_session_step(
        session_id="sess-data-driven-fallback",
        payload={
            "question_id": "q-2",
            "response": {"answer": "B"},
            "behavior_signals": {"response_time_ms": 9000},
        },
    )

    data_driven = result["data_driven"]
    assert data_driven is not None
    assert data_driven["systemBehavior"]["fallbackRuleApplied"] == "missingInterventionPlan"
    assert data_driven["selectedIntervention"]["interventionId"] == "INTV_RECOVERY_LIGHT_RESTART"


@pytest.mark.asyncio
async def test_orchestrator_recommends_formulas_when_belief_is_low() -> None:
    state_mgr = _StateManagerStub()
    orchestrator = AgenticOrchestrator(
        agents={
            "academic": _WeakAcademicAgent(),
            "empathy": _EmpathyAgent(),
            "strategy": _StrategyAgent(),
        },
        state_mgr=state_mgr,
        llm=_DummyLLM(),
    )

    result = await orchestrator.run_session_step(
        session_id="sess-formula-rec",
        payload={
            "question_id": "q-3",
            "response": {"answer": "C"},
            "behavior_signals": {"response_time_ms": 8500},
        },
    )

    recommendations = result["data_driven"]["formulaRecommendations"]
    assert recommendations
    assert recommendations[0]["hypothesis"] in {"H01_Trig", "H02_ExpLog", "H04_Rules"}
