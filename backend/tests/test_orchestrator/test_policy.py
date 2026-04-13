import pytest

from orchestrator.policy import PolicyEngine
from orchestrator.schemas import (
    AcademicState,
    AggregatedState,
    EmpathyState,
    MemoryState,
)


def test_policy_predict_normalizes_distribution() -> None:
    policy = PolicyEngine(
        {
            "actions": ["show_hint", "next_question"],
            "utility_rules": {
                "show_hint": {
                    "base": 0.1,
                    "feature_weights": {"academic_entropy": 1.0},
                },
                "next_question": {
                    "base": 0.1,
                    "feature_weights": {"academic_confidence": 1.0},
                },
            },
        }
    )

    state = AggregatedState(
        academic=AcademicState(entropy=0.8, confidence=0.2),
        empathy=EmpathyState(confusion=0.6, fatigue=0.4, uncertainty=0.5),
        memory=MemoryState(q_values={"show_hint": 0.4}, avg_reward=0.0),
        embedding={"academic_entropy": 0.8, "academic_confidence": 0.2},
    )

    best_action, distribution = policy.predict(state)

    assert best_action == "show_hint"
    assert set(distribution.keys()) == {"show_hint", "next_question"}
    assert sum(distribution.values()) == pytest.approx(1.0)
