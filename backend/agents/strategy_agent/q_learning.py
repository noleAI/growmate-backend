import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

from agents.base import AgentInput, AgentOutput, IAgent
from agents.strategy_agent.reward_engine import compute_reward
from core.memory_store import memory_store

logger = logging.getLogger("strategy.q_learning")


class EpisodicMemory:
    """Stores online experience tuples for current MVP and future replay extensions."""

    def __init__(self):
        self.log: List[Dict[str, Any]] = []

    def store(
        self, state: str, action: str, reward: float, outcome: str, ts: datetime
    ) -> None:
        self.log.append(
            {
                "state": state,
                "action": action,
                "reward": reward,
                "outcome": outcome,
                "timestamp": ts.isoformat(),
            }
        )


class QLearningAgent(IAgent):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or self._load_strategy_config()

        self.alpha = float(cfg.get("alpha", 0.15))
        self.gamma = float(cfg.get("gamma", 0.9))
        self.epsilon = float(cfg.get("epsilon_start", 0.3))
        self.epsilon_decay = float(cfg.get("epsilon_decay", 0.995))
        self.min_epsilon = float(cfg.get("min_epsilon", cfg.get("epsilon_min", 0.05)))

        self.actions: List[str] = cfg.get(
            "actions",
            [
                "show_hint",
                "drill_practice",
                "suggest_break",
                "continue_quiz",
                "trigger_hitl",
            ],
        )
        self.n_actions = len(self.actions)

        self.state_keys: List[str] = cfg.get(
            "state_keys",
            [
                "low_confusion_low_fatigue_low_mastery",
                "low_confusion_low_fatigue_high_mastery",
                "high_confusion_low_fatigue_low_mastery",
                "high_confusion_low_fatigue_high_mastery",
                "low_confusion_high_fatigue_low_mastery",
                "low_confusion_high_fatigue_high_mastery",
                "high_confusion_high_fatigue_low_mastery",
                "high_confusion_high_fatigue_high_mastery",
            ],
        )
        self.n_states = len(self.state_keys)
        self.state_to_idx = {state_key: i for i, state_key in enumerate(self.state_keys)}

        self.Q = np.zeros((self.n_states, self.n_actions), dtype=np.float32)
        self._bootstrap_expert_init(cfg.get("expert_init", []))

        self.memory = EpisodicMemory()
        self.reward_history: List[float] = []
        self.delta_q_log: List[Dict[str, Any]] = []
        self.q_visit_counter: Dict[str, int] = {}
        self.step = 0

    @property
    def name(self) -> str:
        return "strategy"

    @property
    def q_table(self) -> Dict[str, Dict[str, float]]:
        return self._serialize_q_table()

    async def process(self, input_data: AgentInput) -> AgentOutput:
        state = input_data.current_state or {}
        empathy_state = state.get("empathy_state", {})
        academic_state = state.get("academic_state", {})
        signals = input_data.behavior_signals or {}

        mastery_level = self._resolve_mastery_level(academic_state)
        q_state = str(empathy_state.get("q_state", "low_confusion_low_fatigue"))
        state_key = f"{q_state}_{mastery_level}"

        action, explored = self.select_action(state_key)
        reward = compute_reward(signals, academic_state, empathy_state)

        next_mastery = str(academic_state.get("next_mastery", mastery_level))
        next_q_state = str(empathy_state.get("next_q_state", q_state))
        next_state_key = f"{next_q_state}_{next_mastery}"
        student_id = input_data.student_id or state.get("student_id")

        self.update(state_key, action, reward, next_state_key)
        self.log_experience(
            state_key,
            action,
            reward,
            str(academic_state.get("outcome_type", "step_outcome")),
        )
        self.step += 1

        action_q_value = self.get_q_values(state_key).get(action, 0.0)
        visit_count = self._increment_visit_count(state_key, action)
        asyncio.create_task(
            memory_store.upsert_q_value(
                student_id=student_id,
                state_discretized=state_key,
                action=action,
                q_value=float(action_q_value),
                visit_count=visit_count,
            )
        )

        if self.step % 5 == 0:
            asyncio.create_task(
                memory_store.log_episodic_memory(
                    input_data.session_id,
                    student_id,
                    {
                        "state_key": state_key,
                        "next_state_key": next_state_key,
                    },
                    action,
                    {
                        "outcome": str(academic_state.get("outcome_type", "step_outcome")),
                        "is_correct": bool(academic_state.get("is_correct", False)),
                    },
                    float(reward),
                )
            )

        # Safe fallback when Q-table becomes unstable.
        selected_action = action
        if np.any(np.isnan(self.Q)) or self.epsilon > 0.8:
            selected_action = "show_hint"
            logger.warning("Q-table unstable, falling back to safe action")

        avg_reward_10 = (
            self.get_learning_curve(window=10)[-1] if self.reward_history else 0.0
        )

        payload = {
            "q_table": self._serialize_q_table(),
            "q_values": self.get_q_values(state_key),
            "selected_action": selected_action,
            "explored": explored,
            "avg_reward_10": avg_reward_10,
            "delta_q": self.delta_q_log[-1] if self.delta_q_log else {},
            "epsilon": float(self.epsilon),
            "state_key": state_key,
            "next_state_key": next_state_key,
            "reward": float(reward),
        }

        logger.info(
            "[strategy] step=%s epsilon=%.3f action=%s reward=%.2f",
            self.step,
            self.epsilon,
            selected_action,
            reward,
        )

        return AgentOutput(
            action=selected_action,
            payload=payload,
            confidence=float(np.clip(1.0 - self.epsilon, 0.0, 1.0)),
        )

    def _get_state_idx(self, state_key: str) -> int:
        if state_key not in self.state_to_idx:
            logger.warning("Unknown state '%s', falling back to idx 0", state_key)
            return 0
        return self.state_to_idx[state_key]

    def select_action(self, state_key: str) -> Tuple[str, bool]:
        """Select action using epsilon-greedy policy."""
        state_idx = self._get_state_idx(state_key)
        if float(np.random.random()) < self.epsilon:
            action_idx = int(np.random.randint(self.n_actions))
            return self.actions[action_idx], True
        return self.actions[int(np.argmax(self.Q[state_idx]))], False

    def update(
        self, state_key: str, action: str, reward: float, next_state_key: str
    ) -> None:
        """Q(s,a) ← Q(s,a) + α[r + γ max_a' Q(s',a') - Q(s,a)]."""
        state_idx = self._get_state_idx(state_key)
        next_state_idx = self._get_state_idx(next_state_key)

        if action not in self.actions:
            logger.warning("Unknown action '%s', update skipped", action)
            return

        action_idx = self.actions.index(action)
        bounded_reward = float(np.clip(reward, -1.0, 1.0))

        current_q = float(self.Q[state_idx, action_idx])
        max_next_q = float(np.max(self.Q[next_state_idx]))
        td_error = bounded_reward + self.gamma * max_next_q - current_q
        new_q = current_q + self.alpha * td_error
        self.Q[state_idx, action_idx] = float(new_q)

        self.delta_q_log.append(
            {
                "state": state_key,
                "action": action,
                "delta_q": float(td_error),
                "new_q": float(new_q),
            }
        )
        self.reward_history.append(bounded_reward)
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)

    def update_q_value(
        self, state: str, action: str, reward: float, next_state: str
    ) -> None:
        """Compatibility wrapper for old callers."""
        self.update(state, action, reward, next_state)

    def log_experience(
        self, state: str, action: str, reward: float, outcome: str
    ) -> None:
        self.memory.store(state, action, reward, outcome, datetime.now(UTC))

    def get_q_values(self, state_key: str) -> Dict[str, float]:
        state_idx = self._get_state_idx(state_key)
        return {
            action: float(value)
            for action, value in zip(self.actions, self.Q[state_idx], strict=False)
        }

    def get_learning_curve(self, window: int = 10) -> List[float]:
        if len(self.reward_history) < window:
            return [float(value) for value in self.reward_history]
        return [
            float(np.mean(self.reward_history[max(0, i - window) : i + 1]))
            for i in range(len(self.reward_history))
        ]

    def _resolve_mastery_level(self, academic_state: Dict[str, Any]) -> str:
        mastery = academic_state.get("mastery_level")
        if mastery in {"high_mastery", "low_mastery"}:
            return mastery

        proficient_prob = float(academic_state.get("belief_dist", {}).get("H08_Proficient", 0.0))
        return "high_mastery" if proficient_prob >= 0.5 else "low_mastery"

    def _bootstrap_expert_init(self, expert_init: List[List[Any]]) -> None:
        for row in expert_init:
            if len(row) != 3:
                continue
            state_key, action, value = row
            if state_key not in self.state_to_idx or action not in self.actions:
                continue
            self.Q[self.state_to_idx[state_key], self.actions.index(action)] = float(value)

    def _serialize_q_table(self) -> Dict[str, Dict[str, float]]:
        table: Dict[str, Dict[str, float]] = {}
        for state_key, state_idx in self.state_to_idx.items():
            table[state_key] = {
                action: float(value)
                for action, value in zip(
                    self.actions, self.Q[state_idx], strict=False
                )
            }
        return table

    def _increment_visit_count(self, state_key: str, action: str) -> int:
        key = f"{state_key}::{action}"
        next_count = self.q_visit_counter.get(key, 0) + 1
        self.q_visit_counter[key] = next_count
        return next_count

    def _load_strategy_config(self) -> Dict[str, Any]:
        config_path = Path(__file__).resolve().parents[2] / "configs" / "strategy.yaml"
        if not config_path.exists():
            logger.warning("Missing strategy config at %s. Using defaults.", config_path)
            return {}

        with config_path.open("r", encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream) or {}
        return loaded.get("strategy", loaded)


q_learning = QLearningAgent()
