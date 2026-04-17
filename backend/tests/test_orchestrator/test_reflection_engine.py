from types import SimpleNamespace

import pytest

from agents.base import SessionState
from agents.reflection_engine import ReflectionEngine


class _StateManagerStub:
    def __init__(self, state: SessionState):
        self.state = state
        self.calls = 0

    async def load_or_init(self, session_id: str) -> SessionState:
        del session_id
        self.calls += 1
        return self.state


class _MemoryStoreStub:
    def __init__(self, episodes):
        self.episodes = episodes
        self.logged = []

    async def get_recent_episodes(self, session_id: str, limit: int = 5):
        del session_id
        return self.episodes[:limit]

    async def log_reflection(self, session_id: str, step: int, reflection: dict):
        self.logged.append((session_id, step, reflection))


class _LLMStub:
    def __init__(self, text: str):
        self.model = SimpleNamespace(
            generate_content=lambda prompt, generation_config: SimpleNamespace(text=text)
        )


@pytest.mark.asyncio
async def test_reflection_interval_gate_skips_early_steps() -> None:
    state = SessionState(session_id="s1")
    state_mgr = _StateManagerStub(state)
    memory = _MemoryStoreStub([])
    engine = ReflectionEngine(
        llm_service=_LLMStub("{}"),
        memory_store=memory,
        state_manager=state_mgr,
        interval=5,
    )

    result = await engine.maybe_reflect(session_id="s1", current_step=4)

    assert result is None
    assert state_mgr.calls == 0
    assert memory.logged == []


@pytest.mark.asyncio
async def test_reflection_parses_json_and_updates_strategy_override() -> None:
    state = SessionState(
        session_id="s1",
        academic_state={"belief_dist": {"H03_Chain": 0.7}},
        empathy_state={"confusion": 0.8, "fatigue": 0.2},
    )
    state_mgr = _StateManagerStub(state)
    memory = _MemoryStoreStub(
        [
            {"action": "show_hint", "reward": 0.1, "outcome": {"is_correct": False}},
            {"action": "drill_practice", "reward": 0.3, "outcome": {"is_correct": True}},
        ]
    )

    llm_text = """
    {
      "effectiveness": "ineffective",
      "entropy_trend": "increasing",
      "accuracy_trend": "declining",
      "emotion_trend": "worsening",
      "should_change_strategy": true,
      "recommendation": "Use drill before next question",
      "priority_action": "drill_practice",
      "reasoning": "Recent errors persist"
    }
    """
    engine = ReflectionEngine(
        llm_service=_LLMStub(llm_text),
        memory_store=memory,
        state_manager=state_mgr,
        interval=5,
    )

    result = await engine.maybe_reflect(session_id="s1", current_step=5)

    assert result is not None
    assert result["effectiveness"] == "ineffective"
    assert state.strategy_state["reflection_override"] == "drill_practice"
    assert state.strategy_state["reflection_reasoning"] == "Recent errors persist"
    assert memory.logged


def test_parse_reflection_invalid_json_falls_back() -> None:
    engine = ReflectionEngine(
        llm_service=_LLMStub("{}"),
        memory_store=_MemoryStoreStub([]),
        state_manager=_StateManagerStub(SessionState(session_id="s1")),
        interval=5,
    )

    parsed = engine._parse_reflection("not-json text")

    assert parsed["effectiveness"] == "neutral"
    assert parsed["should_change_strategy"] is False
    assert "not-json" in parsed["reasoning"]


@pytest.mark.asyncio
async def test_reflection_returns_none_on_exception() -> None:
    class _BrokenStateManager:
        async def load_or_init(self, session_id: str):
            del session_id
            raise RuntimeError("state load failed")

    engine = ReflectionEngine(
        llm_service=_LLMStub("{}"),
        memory_store=_MemoryStoreStub([]),
        state_manager=_BrokenStateManager(),
        interval=5,
    )

    result = await engine.maybe_reflect(session_id="s1", current_step=5)

    assert result is None
