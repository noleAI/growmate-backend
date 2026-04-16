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


def test_reward_xp_modifiers() -> None:
    reward = compute_reward(
        {"response_time_ms": 7000},
        {"is_correct": False, "streak_no_improvement": 0},
        {"fatigue": 0.2},
        xp_data={
            "recent_xp_gain": 80,
            "streak_days": 4,
            "daily_xp_rate": 35,
            "prev_daily_xp_rate": 35,
        },
    )
    assert reward == 0.6


def test_reward_declining_xp_penalty() -> None:
    reward = compute_reward(
        {"response_time_ms": 7000},
        {"is_correct": True, "streak_no_improvement": 0},
        {"fatigue": 0.2},
        xp_data={
            "recent_xp_gain": 10,
            "streak_days": 1,
            "daily_xp_rate": 10,
            "prev_daily_xp_rate": 20,
        },
    )
    assert reward == 1.0


def test_reward_backward_compat_without_xp_data() -> None:
    without_xp = compute_reward(
        {"response_time_ms": 7000},
        {"is_correct": False, "streak_no_improvement": 0},
        {"fatigue": 0.2},
    )
    with_empty_xp = compute_reward(
        {"response_time_ms": 7000},
        {"is_correct": False, "streak_no_improvement": 0},
        {"fatigue": 0.2},
        xp_data={},
    )
    assert without_xp == with_empty_xp


def test_reward_exam_mode_speed_bonus() -> None:
    normal = compute_reward(
        {"response_time_ms": 5000},
        {"is_correct": False, "streak_no_improvement": 0},
        {"fatigue": 0.5},
        mode="normal",
    )
    exam = compute_reward(
        {"response_time_ms": 5000},
        {"is_correct": False, "streak_no_improvement": 0},
        {"fatigue": 0.5},
        mode="exam_prep",
    )
    assert exam > normal


def test_reward_explore_mode_hint_bonus() -> None:
    no_hint = compute_reward(
        {"response_time_ms": 9000, "hint_used": False},
        {"is_correct": False, "streak_no_improvement": 0},
        {"fatigue": 0.5},
        mode="explore",
    )
    with_hint = compute_reward(
        {"response_time_ms": 9000, "hint_used": True},
        {"is_correct": False, "streak_no_improvement": 0},
        {"fatigue": 0.5},
        mode="explore",
    )
    assert with_hint > no_hint


def test_resolve_mastery_level_from_entropy(config: dict) -> None:
    agent = QLearningAgent(config)

    assert agent._resolve_mastery_level({"entropy": 0.2}) == "high_mastery"
    assert agent._resolve_mastery_level({"entropy": 0.8}) == "low_mastery"


def test_resolve_mastery_level_from_belief_dist(config: dict) -> None:
    agent = QLearningAgent(config)

    high_certainty = {
        "belief_dist": {
            "H01_Trig": 0.92,
            "H02_ExpLog": 0.04,
            "H03_Chain": 0.02,
            "H04_Rules": 0.02,
        }
    }
    low_certainty = {
        "belief_dist": {
            "H01_Trig": 0.25,
            "H02_ExpLog": 0.25,
            "H03_Chain": 0.25,
            "H04_Rules": 0.25,
        }
    }

    assert agent._resolve_mastery_level(high_certainty) == "high_mastery"
    assert agent._resolve_mastery_level(low_certainty) == "low_mastery"


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
async def test_process_uses_xp_data_in_reward(config: dict) -> None:
    agent = QLearningAgent(config)
    output = await agent.process(
        AgentInput(
            session_id="sess-strategy-xp",
            behavior_signals={"response_time_ms": 7000},
            current_state={
                "academic_state": {"is_correct": False, "mastery_level": "low_mastery"},
                "empathy_state": {"q_state": "S1", "fatigue": 0.2},
                "strategy_state": {
                    "xp_data": {
                        "recent_xp_gain": 80,
                        "streak_days": 4,
                        "daily_xp_rate": 35,
                        "prev_daily_xp_rate": 35,
                    }
                },
            },
        )
    )
    assert output.payload["reward"] == 0.6


def test_select_action_mode_biases_when_supported_actions() -> None:
    agent = QLearningAgent(
        {
            "epsilon_start": 0.0,
            "epsilon_decay": 1.0,
            "min_epsilon": 0.0,
            "actions": ["show_hint", "drill_practice", "continue_quiz"],
            "state_keys": ["S"],
        }
    )

    # Baseline preference slightly favors show_hint.
    agent.Q[0] = np.array([0.6, 0.55, 0.4], dtype=np.float32)

    exam_action, _ = agent.select_action("S", mode="exam_prep")
    explore_action, _ = agent.select_action("S", mode="explore")

    assert exam_action == "drill_practice"
    assert explore_action == "show_hint"


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
