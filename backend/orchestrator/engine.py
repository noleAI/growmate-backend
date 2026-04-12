from typing import Any, Dict, List

from orchestrator.aggregator import StateAggregator
from orchestrator.monitoring import MonitoringEngine
from orchestrator.policy import PolicyEngine
from orchestrator.schemas import (
    AcademicState,
    EmpathyState,
    MemoryState,
    OrchestratorDecision,
)


class OrchestratorEngine:
    def __init__(self, config: Dict[str, Any]):
        self.aggregator = StateAggregator(config.get("aggregator", {}))
        self.policy = PolicyEngine(config.get("policy", {}))
        self.monitor = MonitoringEngine(config.get("monitoring", {}))

    def run_step(
        self,
        academic_state: Dict[str, Any],
        empathy_state: Dict[str, Any],
        memory_state: Dict[str, Any],
    ) -> OrchestratorDecision:
        academic = self._to_academic_state(academic_state)
        empathy = self._to_empathy_state(empathy_state)
        memory = self._to_memory_state(memory_state)

        agg_state = self.aggregator.aggregate(academic, empathy, memory)
        total_uncertainty, hitl_needed = self.monitor.check_uncertainty(agg_state)

        best_action, action_distribution = self.policy.predict(agg_state)
        final_action = best_action
        hitl_payload = None

        if hitl_needed:
            final_action = "hitl"
            hitl_payload = {
                "reason": "High Uncertainty",
                "total_uncertainty": total_uncertainty,
                "suggested_action": best_action,
                "message": "The system is uncertain and recommends human review.",
            }

        return OrchestratorDecision(
            action=final_action,
            action_distribution=action_distribution,
            total_uncertainty=total_uncertainty,
            hitl_triggered=hitl_needed,
            hitl_payload=hitl_payload,
            rationale=self._get_rationale(agg_state, best_action),
            monitoring={
                "academic_entropy": float(academic.entropy),
                "empathy_uncertainty": float(empathy.uncertainty),
                "threshold": float(self.monitor.uncertainty_threshold),
            },
        )

    def _to_academic_state(self, state: Dict[str, Any]) -> AcademicState:
        belief_distribution = state.get("belief_dist", {})
        entropy = float(state.get("entropy", 0.0))
        if entropy <= 0.0 and belief_distribution:
            entropy = self._normalized_entropy(list(belief_distribution.values()))

        top_hypothesis = ""
        if belief_distribution:
            top_hypothesis = max(belief_distribution, key=belief_distribution.get)

        confidence = float(state.get("confidence", 1.0 - entropy))
        return AcademicState(
            belief_distribution=belief_distribution,
            entropy=max(0.0, min(1.0, entropy)),
            top_hypothesis=top_hypothesis,
            confidence=max(0.0, min(1.0, confidence)),
        )

    def _to_empathy_state(self, state: Dict[str, Any]) -> EmpathyState:
        particle_distribution = state.get("belief_distribution")
        if not isinstance(particle_distribution, dict):
            particle_distribution = {}

        uncertainty = state.get("uncertainty", state.get("uncertainty_score", 1.0))
        return EmpathyState(
            confusion=float(state.get("confusion", 0.0)),
            fatigue=float(state.get("fatigue", 0.0)),
            uncertainty=float(max(0.0, min(1.0, float(uncertainty)))),
            particle_distribution={
                str(k): float(v) for k, v in particle_distribution.items()
            },
        )

    def _to_memory_state(self, state: Dict[str, Any]) -> MemoryState:
        q_values = state.get("q_values", {})
        if not q_values and state.get("q_table"):
            q_state_key = state.get("state_key", state.get("q_state", ""))
            q_table = state.get("q_table", {})
            if q_state_key and isinstance(q_table, dict):
                q_values = q_table.get(q_state_key, {})

        avg_reward = float(state.get("avg_reward_10", state.get("avg_reward", 0.0)))
        return MemoryState(
            q_values={str(k): float(v) for k, v in (q_values or {}).items()},
            avg_reward=avg_reward,
        )

    def _normalized_entropy(self, probs: List[float]) -> float:
        valid = [float(max(0.0, p)) for p in probs if p is not None]
        total = sum(valid)
        if total <= 0.0:
            return 0.0

        normalized = [p / total for p in valid if p > 0.0]
        if not normalized:
            return 0.0

        import math

        entropy = -sum(p * math.log(p) for p in normalized)
        max_entropy = math.log(len(normalized)) if len(normalized) > 1 else 1.0
        return float(entropy / max_entropy) if max_entropy > 0 else 0.0

    def _get_rationale(self, state, action: str) -> str:
        if action == "de_stress":
            return f"Fatigue is high ({state.empathy.fatigue:.2f}); recommending stress recovery."
        if action == "show_hint":
            return f"Academic uncertainty is elevated (H={state.academic.entropy:.2f}); hint is preferred."
        if action == "drill_practice":
            return "Confidence is adequate for guided practice."
        if action == "next_question":
            return "Current state supports progression to the next question."
        if action == "hitl":
            return "Combined uncertainty exceeded threshold; escalating to HITL."
        return f"Action '{action}' has the highest deterministic utility."
