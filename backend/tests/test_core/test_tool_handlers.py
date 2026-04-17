from dataclasses import dataclass
from typing import Any

import pytest

from agents.base import SessionState
import core.tool_handlers as tool_handlers_module
from core.tool_handlers import (
    get_academic_beliefs,
    get_empathy_state,
    get_formula_bank,
    get_orchestrator_score,
    get_strategy_suggestion,
    get_student_history,
    search_knowledge,
)


class _StateManagerStub:
    def __init__(self, state: SessionState):
        self._state = state
        self.session_context: dict[str, dict[str, str]] = {}

    async def load_or_init(self, session_id: str) -> SessionState:
        del session_id
        return self._state


class _MemoryStoreStub:
    def __init__(self, episodes: list[dict[str, Any]]):
        self._episodes = episodes

    async def get_recent_episodes(
        self,
        session_id: str,
        limit: int = 5,
        student_id: str | None = None,
        access_token: str | None = None,
    ) -> list[dict[str, Any]]:
        del session_id, student_id, access_token
        return self._episodes[:limit]


class _FormulaRecommenderStub:
    def __init__(self):
        self.last_belief_dist: dict[str, float] | None = None

    def recommend_formulas(
        self,
        belief_dist: dict[str, float],
        threshold: float,
        limit: int,
    ) -> list[dict[str, str]]:
        del threshold, limit
        self.last_belief_dist = belief_dist
        return [{"id": "f01", "name": "chain rule"}] if belief_dist else []


@dataclass
class _Decision:
    action: str
    action_distribution: dict[str, float]
    total_uncertainty: float
    hitl_triggered: bool
    rationale: str


class _DecisionEngineStub:
    def run_step(
        self,
        academic_state: dict[str, Any],
        empathy_state: dict[str, Any],
        memory_state: dict[str, Any],
    ) -> _Decision:
        del academic_state, empathy_state, memory_state
        return _Decision(
            action="hint",
            action_distribution={"hint": 0.7, "next_question": 0.3},
            total_uncertainty=0.42,
            hitl_triggered=False,
            rationale="entropy high",
        )


class _OrchestratorStub:
    def __init__(self, state: SessionState):
        self.state_mgr = _StateManagerStub(state)
        self.decision_engine = _DecisionEngineStub()


class _RetrieverStub:
    def __init__(self):
        self.calls: list[tuple[str, int, str | None]] = []

    async def search(
        self,
        query: str,
        top_k: int = 3,
        source_filter: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((query, top_k, source_filter))
        return {"chunks": [], "count": 0, "interpretation": "ok"}


@pytest.mark.asyncio
async def test_get_academic_beliefs_with_distribution() -> None:
    state = SessionState(
        session_id="s1",
        academic_state={
            "belief_dist": {
                "H01_Trig": 0.1,
                "H02_ExpLog": 0.2,
                "H03_Chain": 0.6,
                "H04_Rules": 0.1,
            },
            "entropy": 0.34,
        },
    )

    result = await get_academic_beliefs(_StateManagerStub(state), "s1")

    assert result["top_hypothesis"] == "H03_Chain"
    assert result["entropy"] == 0.34
    assert "Top weakness" in result["interpretation"]


@pytest.mark.asyncio
async def test_get_empathy_state_interpretation() -> None:
    state = SessionState(
        session_id="s1",
        empathy_state={"confusion": 0.8, "fatigue": 0.85, "q_state": "high_high"},
    )

    result = await get_empathy_state(_StateManagerStub(state), "s1")

    assert result["q_state"] == "high_high"
    assert "very tired" in result["interpretation"]
    assert "very confused" in result["interpretation"]


@pytest.mark.asyncio
async def test_get_strategy_suggestion_normalizes_action() -> None:
    state = SessionState(
        session_id="s1",
        strategy_state={
            "selected_action": "continue_quiz",
            "q_values": {"continue_quiz": 1.2},
            "epsilon": 0.1,
            "avg_reward": 0.5,
        },
    )

    result = await get_strategy_suggestion(_StateManagerStub(state), "s1")

    assert result["recommended_action"] == "next_question"
    assert result["raw_action"] == "continue_quiz"


@pytest.mark.asyncio
async def test_get_student_history_accuracy() -> None:
    episodes = [
        {"action": "show_hint", "outcome": {"is_correct": False}},
        {"action": "next_question", "outcome": {"is_correct": True}},
        {"action": "drill_practice", "outcome": {"is_correct": True}},
    ]

    state_manager = _StateManagerStub(SessionState(session_id="s1"))
    state_manager.session_context["s1"] = {
        "student_id": "student-1",
        "access_token": "token",
    }

    result = await get_student_history(
        _MemoryStoreStub(episodes),
        state_manager,
        "s1",
        n=3,
    )

    assert result["total"] == 3
    assert result["accuracy"] == 0.67
    assert "Recent accuracy=67%" in result["interpretation"]


@pytest.mark.asyncio
async def test_get_student_history_without_student_context() -> None:
    state_manager = _StateManagerStub(SessionState(session_id="s1"))

    result = await get_student_history(
        _MemoryStoreStub([{"action": "next_question", "outcome": {"is_correct": True}}]),
        state_manager,
        "s1",
        n=3,
    )

    assert result["total"] == 0
    assert result["history"] == []


@pytest.mark.asyncio
async def test_get_formula_bank_resolves_topic_to_hypothesis() -> None:
    formula = _FormulaRecommenderStub()

    result = await get_formula_bank(formula, hypothesis=None, topic="sin cos")

    assert result["hypothesis"] == "H01_Trig"
    assert result["count"] == 1
    assert formula.last_belief_dist == {"H01_Trig": 0.0}


@pytest.mark.asyncio
async def test_get_orchestrator_score_normalizes_hint_action() -> None:
    state = SessionState(session_id="s1")
    orchestrator = _OrchestratorStub(state)

    result = await get_orchestrator_score(orchestrator, "s1")

    assert result["recommended_action"] == "show_hint"
    assert result["total_uncertainty"] == 0.42
    assert "Deterministic orchestrator suggests show_hint" in result["interpretation"]


@pytest.mark.asyncio
async def test_search_knowledge_passes_through_parameters() -> None:
    retriever = _RetrieverStub()

    result = await search_knowledge(retriever, query="chain rule", top_k=0, source="sgk_toan_12")

    assert result["interpretation"] == "ok"
    assert retriever.calls == [("chain rule", 1, "sgk_toan_12")]


@pytest.mark.asyncio
async def test_search_knowledge_rate_limit_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever = _RetrieverStub()
    monkeypatch.setattr(tool_handlers_module, "_SEARCH_KNOWLEDGE_LIMIT", 1)
    tool_handlers_module._search_knowledge_counter.clear()

    first = await search_knowledge(
        retriever,
        query="first",
        top_k=2,
        source="sgk_toan_12",
        session_id="sess-limit",
    )
    second = await search_knowledge(
        retriever,
        query="second",
        top_k=2,
        source="sgk_toan_12",
        session_id="sess-limit",
    )

    assert "error" not in first
    assert second["error"] == "rate_limited"
