from orchestrator.engine import OrchestratorEngine


def test_engine_returns_hitl_decision_when_uncertain() -> None:
    engine = OrchestratorEngine(
        {
            "policy": {
                "actions": ["next_question", "hitl"],
                "utility_rules": {
                    "next_question": {
                        "base": 0.0,
                        "feature_weights": {"academic_confidence": 1.0},
                    },
                    "hitl": {
                        "base": 0.0,
                        "feature_weights": {
                            "academic_entropy": 1.0,
                            "empathy_uncertainty": 1.0,
                        },
                    },
                },
            },
            "monitoring": {
                "uncertainty_threshold": 0.5,
                "uncertainty_weights": {"academic": 0.5, "empathy": 0.5},
            },
        }
    )

    decision = engine.run_step(
        academic_state={"belief_dist": {"A": 0.5, "B": 0.5}, "entropy": 0.9},
        empathy_state={"uncertainty": 0.8, "confusion": 0.7, "fatigue": 0.6},
        memory_state={"q_values": {"next_question": 0.2}},
    )

    assert decision.hitl_triggered is True
    assert decision.action == "hitl"
    assert decision.hitl_payload is not None
    assert decision.total_uncertainty >= 0.5


def test_engine_returns_non_hitl_when_stable() -> None:
    engine = OrchestratorEngine({})
    decision = engine.run_step(
        academic_state={"belief_dist": {"A": 1.0}, "entropy": 0.1, "confidence": 0.9},
        empathy_state={"uncertainty": 0.1, "confusion": 0.2, "fatigue": 0.2},
        memory_state={"q_values": {"next_question": 0.9}, "avg_reward_10": 0.4},
    )

    assert decision.hitl_triggered is False
    assert decision.action in {"next_question", "show_hint", "drill_practice", "de_stress", "hitl"}
