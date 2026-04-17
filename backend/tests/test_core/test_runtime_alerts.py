import urllib.request

from core.runtime_alerts import (
    dispatch_runtime_alerts,
    evaluate_runtime_alerts,
    reset_runtime_alert_state,
)


class _ResponseStub:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


def test_evaluate_runtime_alerts_uses_thresholds(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_ALERT_SIGNATURE_EXPIRED_THRESHOLD", "2")
    monkeypatch.setenv("RUNTIME_ALERT_RESULT_FETCH_FAILURE_THRESHOLD", "3")
    monkeypatch.setenv("RUNTIME_ALERT_RESUME_GRACE_USAGE_THRESHOLD", "4")

    alerts = evaluate_runtime_alerts(
        {
            "signature_expired_total": 2,
            "quiz_result_fetch_failures_total": 5,
            "resume_signature_grace_used_total": 1,
        }
    )

    metrics = {alert["metric"] for alert in alerts}
    assert "signature_expired_total" in metrics
    assert "quiz_result_fetch_failures_total" in metrics
    assert "resume_signature_grace_used_total" not in metrics


def test_dispatch_runtime_alerts_without_webhook_is_skipped() -> None:
    reset_runtime_alert_state()
    alerts = [
        {
            "name": "runtime_metric_signature_expired_total",
            "metric": "signature_expired_total",
            "value": 10,
            "threshold": 2,
        }
    ]

    result = dispatch_runtime_alerts(
        alerts,
        metrics={"signature_expired_total": 10},
        webhook_url="",
    )

    assert result["count"] == 1
    assert result["sent"] == 0
    assert result["skipped_no_webhook"] == 1


def test_dispatch_runtime_alerts_applies_rate_limit(monkeypatch) -> None:
    reset_runtime_alert_state()
    monkeypatch.setenv("RUNTIME_ALERT_MIN_INTERVAL_SECONDS", "999")

    sent_calls: list[urllib.request.Request] = []

    def _urlopen_stub(request, timeout=0):
        del timeout
        sent_calls.append(request)
        return _ResponseStub()

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_stub)

    alerts = [
        {
            "name": "runtime_metric_signature_expired_total",
            "metric": "signature_expired_total",
            "value": 10,
            "threshold": 2,
        }
    ]

    first = dispatch_runtime_alerts(
        alerts,
        metrics={"signature_expired_total": 10},
        webhook_url="https://example.com/alert",
    )
    second = dispatch_runtime_alerts(
        alerts,
        metrics={"signature_expired_total": 10},
        webhook_url="https://example.com/alert",
    )

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert second["skipped_rate_limited"] == 1
    assert len(sent_calls) == 1
