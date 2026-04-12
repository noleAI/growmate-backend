import asyncio
import importlib
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.base import AgentInput
from agents.strategy_agent.q_learning import QLearningAgent
from agents.strategy_agent.reward_engine import compute_reward

q_learning_module = importlib.import_module("agents.strategy_agent.q_learning")


@pytest.fixture
def config() -> dict:
    return {
        "alpha": 0.2,
        "gamma": 0.9,
        "epsilon_start": 0.5,
        "epsilon_decay": 0.9,
        "min_epsilon": 0.1,
        "actions": ["A", "B"],
        "state_keys": ["S1", "S2"],
        "expert_init": [["S1", "A", 0.5]],
    }


def test_q_update_formula(config: dict) -> None:
    agent = QLearningAgent(config)
    agent.update("S1", "A", 1.0, "S2")
    expected = 0.5 + 0.2 * (1.0 + 0.9 * 0.0 - 0.5)
    assert np.isclose(agent.Q[0, 0], expected)


def test_epsilon_greedy(config: dict) -> None:
    np.random.seed(42)
    agent = QLearningAgent(config)
    actions = {agent.select_action("S1")[0] for _ in range(100)}
    assert "B" in actions


def test_reward_bound() -> None:
    reward = compute_reward(
        {"response_time_ms": 25000},
        {"is_correct": False, "confidence_delta": -0.1, "streak_no_improvement": 4},
        {"fatigue": 0.8},
    )
    assert -1.0 <= reward <= 1.0


@pytest.mark.asyncio
async def test_process_payload_structure(config: dict) -> None:
    agent = QLearningAgent(config)
    output = await agent.process(
        AgentInput(
            session_id="sess-strategy-1",
            behavior_signals={"response_time_ms": 7000},
            current_state={
                "academic_state": {"is_correct": True, "mastery_level": "low_mastery"},
                "empathy_state": {"q_state": "S1", "fatigue": 0.2},
            },
        )
    )
    assert output.action in {"A", "B", "show_hint"}
    assert "q_table" in output.payload
    assert "q_values" in output.payload
    assert "delta_q" in output.payload
    assert "epsilon" in output.payload


@pytest.mark.asyncio
async def test_process_schedules_q_table_upsert(config: dict, monkeypatch) -> None:
    agent = QLearningAgent(config)
    upsert_mock = AsyncMock()
    monkeypatch.setattr(q_learning_module.memory_store, "upsert_q_value", upsert_mock)

    await agent.process(
        AgentInput(
            session_id="sess-strategy-qsync",
            student_id="student-uuid-1",
            behavior_signals={"response_time_ms": 3000},
            current_state={
                "academic_state": {"is_correct": True, "mastery_level": "low_mastery"},
                "empathy_state": {"q_state": "S1", "fatigue": 0.1},
            },
        )
    )
    await asyncio.sleep(0)

    assert upsert_mock.await_count == 1
    kwargs = upsert_mock.await_args.kwargs
    assert kwargs["student_id"] == "student-uuid-1"
    assert kwargs["state_discretized"] == "S1_low_mastery"
    assert kwargs["action"] in {"A", "B"}
    assert isinstance(kwargs["q_value"], float)
    assert kwargs["visit_count"] == 1


@pytest.mark.asyncio
async def test_process_schedules_episodic_insert_every_five_steps(
    config: dict, monkeypatch
) -> None:
    agent = QLearningAgent(config)
    agent.step = 4

    upsert_mock = AsyncMock()
    episodic_mock = AsyncMock()
    monkeypatch.setattr(q_learning_module.memory_store, "upsert_q_value", upsert_mock)
    monkeypatch.setattr(q_learning_module.memory_store, "log_episodic_memory", episodic_mock)

    await agent.process(
        AgentInput(
            session_id="sess-strategy-episodic",
            student_id="student-uuid-2",
            behavior_signals={"response_time_ms": 5000},
            current_state={
                "academic_state": {"is_correct": False, "mastery_level": "low_mastery"},
                "empathy_state": {"q_state": "S1", "fatigue": 0.3},
            },
        )
    )
    await asyncio.sleep(0)

    assert upsert_mock.await_count == 1
    assert episodic_mock.await_count == 1
    args = episodic_mock.await_args.args
    assert args[0] == "sess-strategy-episodic"
    assert args[1] == "student-uuid-2"
