from typing import Any, Dict, Tuple

from orchestrator.schemas import AggregatedState


class MonitoringEngine:
    def __init__(self, config: Dict[str, Any]):
        self.uncertainty_threshold = float(config.get("uncertainty_threshold", 0.6))
        self.weights = config.get(
            "uncertainty_weights", {"academic": 0.4, "empathy": 0.6}
        )

    def check_uncertainty(self, state: AggregatedState) -> Tuple[float, bool]:
        u_academic = float(max(0.0, min(1.0, state.academic.entropy)))
        u_empathy = float(max(0.0, min(1.0, state.empathy.uncertainty)))

        total_uncertainty = (
            float(self.weights.get("academic", 0.4)) * u_academic
            + float(self.weights.get("empathy", 0.6)) * u_empathy
        )
        trigger_hitl = total_uncertainty > self.uncertainty_threshold
        return round(total_uncertainty, 3), trigger_hitl
