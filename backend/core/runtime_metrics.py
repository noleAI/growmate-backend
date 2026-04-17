from collections import Counter
from threading import Lock

_metric_lock = Lock()
_metrics: Counter[str] = Counter()


def increment_metric(name: str, value: int = 1) -> None:
    metric_name = str(name or "").strip()
    if not metric_name:
        return

    safe_value = int(value or 0)
    if safe_value == 0:
        return

    with _metric_lock:
        _metrics[metric_name] += safe_value


def get_metrics_snapshot() -> dict[str, int]:
    with _metric_lock:
        return {key: int(val) for key, val in _metrics.items()}


def reset_metrics() -> None:
    with _metric_lock:
        _metrics.clear()
