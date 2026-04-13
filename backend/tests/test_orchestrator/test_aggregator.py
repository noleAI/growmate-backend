from orchestrator.aggregator import StateAggregator
from orchestrator.schemas import AcademicState, EmpathyState, MemoryState


def test_aggregate_builds_embedding_with_weights() -> None:
    aggregator = StateAggregator(
        {
            "embedding_keys": ["custom_metric"],
            "embedding_weights": {"academic_entropy": 2.0},
        }
    )

    aggregated = aggregator.aggregate(
        academic=AcademicState(entropy=0.3, confidence=0.7),
        empathy=EmpathyState(confusion=0.4, fatigue=0.5, uncertainty=0.6),
        memory=MemoryState(q_values={"a": 0.2, "b": 0.8}, avg_reward=0.1),
    )

    assert aggregated.embedding["academic_entropy"] == 0.6
    assert aggregated.embedding["memory_best_q"] == 0.8
    assert aggregated.embedding["custom_metric"] == 0.0
