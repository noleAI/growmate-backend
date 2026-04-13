import logging
from typing import Any, Dict, Tuple

import numpy as np

from orchestrator.schemas import AggregatedState

logger = logging.getLogger("orchestrator.policy")


class PolicyEngine:
    def __init__(self, config: Dict[str, Any]):
        self.actions = config.get(
            "actions",
            ["next_question", "show_hint", "drill_practice", "de_stress", "hitl"],
        )
        self.utility_rules = config.get("utility_rules", {})

    def predict(self, state: AggregatedState) -> Tuple[str, Dict[str, float]]:
        u_scores: Dict[str, float] = {}

        for action in self.actions:
            rule = self.utility_rules.get(action, {})
            score = float(rule.get("base", 0.0))
            feature_weights = rule.get("feature_weights", {})

            if feature_weights:
                for feature_name, weight in feature_weights.items():
                    feature_value = float(state.embedding.get(feature_name, 0.0))
                    score += feature_value * float(weight)
            else:
                score += self._fallback_score(action, state)

            u_scores[action] = score

        values = np.array([u_scores[action] for action in self.actions], dtype=float)
        shifted = values - np.max(values)
        exp_values = np.exp(shifted)
        probs = exp_values / np.sum(exp_values)
        distribution = {
            action: float(prob)
            for action, prob in zip(self.actions, probs, strict=False)
        }

        best_action = max(u_scores, key=u_scores.get)
        logger.info("[orchestrator.policy] best_action=%s utility=%.3f", best_action, u_scores[best_action])
        return best_action, distribution

    def _fallback_score(self, action: str, state: AggregatedState) -> float:
        if action == "de_stress":
            return (
                0.2
                + (state.empathy.fatigue * 0.8)
                + (state.empathy.uncertainty * 0.2)
                - (state.academic.confidence * 0.4)
            )
        if action == "show_hint":
            return 0.1 + (state.academic.entropy * 0.7) + (state.empathy.confusion * 0.4)
        if action == "drill_practice":
            return 0.2 + (state.academic.confidence * 0.6) - (state.empathy.fatigue * 0.5)
        if action == "next_question":
            return 0.3 + (state.academic.confidence * 0.5) - (state.empathy.uncertainty * 0.5)
        if action == "hitl":
            return state.empathy.uncertainty + state.academic.entropy
        return 0.0
