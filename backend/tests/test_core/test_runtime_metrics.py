from core.runtime_metrics import get_metrics_snapshot, increment_metric, reset_metrics


def test_runtime_metrics_counter_basic() -> None:
    reset_metrics()
    increment_metric("resume_success_total")
    increment_metric("resume_success_total", 2)
    increment_metric("quiz_result_fetch_failures_total", 1)

    snapshot = get_metrics_snapshot()
    assert snapshot["resume_success_total"] == 3
    assert snapshot["quiz_result_fetch_failures_total"] == 1


def test_runtime_metrics_ignore_invalid_names_and_zero() -> None:
    reset_metrics()
    increment_metric("", 1)
    increment_metric("   ", 1)
    increment_metric("valid_metric", 0)

    snapshot = get_metrics_snapshot()
    assert snapshot == {}
