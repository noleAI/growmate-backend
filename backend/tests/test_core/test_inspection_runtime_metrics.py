import pytest

from api.routes import inspection as inspection_route
from core.runtime_metrics import increment_metric, reset_metrics


@pytest.mark.asyncio
async def test_get_runtime_metrics_returns_snapshot() -> None:
    reset_metrics()
    increment_metric("resume_success_total", 2)

    result = await inspection_route.get_runtime_metrics(user={"sub": "student-1"})

    assert "metrics" in result
    assert result["metrics"].get("resume_success_total") == 2


@pytest.mark.asyncio
async def test_get_runtime_alerts_preview() -> None:
    reset_metrics()
    increment_metric("signature_expired_total", 1)

    result = await inspection_route.get_runtime_alerts(
        dispatch=False,
        user={"sub": "student-1"},
    )

    assert result["dispatch"] is False
    assert "alerts" in result
    assert "metrics" in result


@pytest.mark.asyncio
async def test_get_runtime_alerts_dispatch(monkeypatch) -> None:
    async def _dispatch_stub(*, trigger=None, metrics=None):
        assert trigger == "inspection_runtime_alerts_endpoint"
        assert isinstance(metrics, dict)
        return {
            "alerts": [],
            "count": 0,
            "attempted": 0,
            "sent": 0,
            "failed": 0,
            "skipped_rate_limited": 0,
            "skipped_no_webhook": 0,
            "webhook_configured": False,
            "metrics": metrics,
        }

    monkeypatch.setattr(inspection_route, "maybe_emit_runtime_alerts", _dispatch_stub)

    result = await inspection_route.get_runtime_alerts(
        dispatch=True,
        user={"sub": "student-1"},
    )

    assert result["dispatch"] is True
    assert "metrics" in result
