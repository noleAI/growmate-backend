from orchestrator.monitoring import MonitoringEngine
from orchestrator.schemas import (
    AcademicState,
    AggregatedState,
    EmpathyState,
    MemoryState,
)


def test_monitoring_triggers_hitl_when_threshold_exceeded() -> None:
    monitor = MonitoringEngine(
        {
            "uncertainty_threshold": 0.6,
            "uncertainty_weights": {"academic": 0.4, "empathy": 0.6},
        }
    )

    state = AggregatedState(
        academic=AcademicState(entropy=0.8),
        empathy=EmpathyState(uncertainty=0.9),
        memory=MemoryState(),
        embedding={},
    )

    total_uncertainty, hitl = monitor.check_uncertainty(state)
    assert total_uncertainty == 0.86
    assert hitl is True
