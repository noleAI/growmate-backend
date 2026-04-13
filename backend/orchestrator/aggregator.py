from typing import Any, Dict

from orchestrator.schemas import (
    AcademicState,
    AggregatedState,
    EmpathyState,
    MemoryState,
)


class StateAggregator:
    def __init__(self, config: Dict[str, Any]):
        self.embedding_keys = config.get("embedding_keys", [])
        self.weights = config.get("embedding_weights", {})

    def aggregate(
        self,
        academic: AcademicState,
        empathy: EmpathyState,
        memory: MemoryState,
    ) -> AggregatedState:
        q_values = memory.q_values or {}
        memory_best_q = max(q_values.values()) if q_values else 0.0

        embedding = {
            "academic_entropy": float(academic.entropy),
            "academic_confidence": float(academic.confidence),
            "empathy_confusion": float(empathy.confusion),
            "empathy_fatigue": float(empathy.fatigue),
            "empathy_uncertainty": float(empathy.uncertainty),
            "memory_best_q": float(memory_best_q),
            "memory_avg_reward": float(memory.avg_reward),
        }

        for key in self.embedding_keys:
            if key not in embedding:
                embedding[key] = 0.0

        for key, weight in self.weights.items():
            if key in embedding:
                embedding[key] = float(embedding[key]) * float(weight)

        return AggregatedState(
            academic=academic,
            empathy=empathy,
            memory=memory,
            embedding=embedding,
        )
