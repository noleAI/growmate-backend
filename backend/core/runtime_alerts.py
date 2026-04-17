from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from core.config import get_settings
from core.runtime_metrics import get_metrics_snapshot

_alert_lock = Lock()
_last_sent_at: dict[str, float] = {}


def _get_settings_or_none() -> Any | None:
    try:
        return get_settings()
    except Exception:
        return None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def get_alert_thresholds() -> dict[str, int]:
    settings = _get_settings_or_none()
    default_signature_threshold = int(
        getattr(settings, "runtime_alert_signature_expired_threshold", 20)
    )
    default_result_failure_threshold = int(
        getattr(settings, "runtime_alert_result_fetch_failure_threshold", 10)
    )
    default_resume_grace_threshold = int(
        getattr(settings, "runtime_alert_resume_grace_usage_threshold", 15)
    )

    return {
        "signature_expired_total": max(
            1,
            _safe_int(
                os.getenv(
                    "RUNTIME_ALERT_SIGNATURE_EXPIRED_THRESHOLD",
                    default_signature_threshold,
                ),
                default_signature_threshold,
            ),
        ),
        "quiz_result_fetch_failures_total": max(
            1,
            _safe_int(
                os.getenv(
                    "RUNTIME_ALERT_RESULT_FETCH_FAILURE_THRESHOLD",
                    default_result_failure_threshold,
                ),
                default_result_failure_threshold,
            ),
        ),
        "resume_signature_grace_used_total": max(
            1,
            _safe_int(
                os.getenv(
                    "RUNTIME_ALERT_RESUME_GRACE_USAGE_THRESHOLD",
                    default_resume_grace_threshold,
                ),
                default_resume_grace_threshold,
            ),
        ),
    }


def evaluate_runtime_alerts(
    metrics: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    snapshot = metrics if isinstance(metrics, dict) else get_metrics_snapshot()
    thresholds = get_alert_thresholds()

    alerts: list[dict[str, Any]] = []
    for metric_name, threshold in thresholds.items():
        value = _safe_int(snapshot.get(metric_name, 0), 0)
        if value < threshold:
            continue

        alerts.append(
            {
                "name": f"runtime_metric_{metric_name}",
                "metric": metric_name,
                "value": value,
                "threshold": threshold,
                "severity": "warning",
                "message": (
                    f"Metric '{metric_name}' reached {value} (threshold={threshold})."
                ),
            }
        )

    return alerts


def _resolve_webhook_url(override: str | None = None) -> str | None:
    if override is not None:
        value = str(override).strip()
        return value or None

    settings = _get_settings_or_none()
    env_value = os.getenv("RUNTIME_ALERT_WEBHOOK_URL", "")
    if env_value.strip():
        return env_value.strip()

    setting_value = str(getattr(settings, "runtime_alert_webhook_url", "") or "").strip()
    return setting_value or None


def _resolve_min_interval_seconds() -> int:
    settings = _get_settings_or_none()
    default_interval = int(getattr(settings, "runtime_alert_min_interval_seconds", 300))
    return max(
        1,
        _safe_int(
            os.getenv(
                "RUNTIME_ALERT_MIN_INTERVAL_SECONDS",
                default_interval,
            ),
            default_interval,
        ),
    )


def _allow_dispatch(alert_name: str, now: float, min_interval_sec: int) -> bool:
    with _alert_lock:
        last_sent = _last_sent_at.get(alert_name)
        if last_sent is not None and (now - last_sent) < min_interval_sec:
            return False
    return True


def _mark_dispatched(alert_name: str, timestamp: float) -> None:
    with _alert_lock:
        _last_sent_at[alert_name] = timestamp


def reset_runtime_alert_state() -> None:
    with _alert_lock:
        _last_sent_at.clear()


def dispatch_runtime_alerts(
    alerts: list[dict[str, Any]],
    *,
    metrics: dict[str, int] | None = None,
    trigger: str | None = None,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    snapshot = metrics if isinstance(metrics, dict) else get_metrics_snapshot()
    resolved_webhook = _resolve_webhook_url(webhook_url)
    min_interval = _resolve_min_interval_seconds()

    result = {
        "alerts": alerts,
        "count": len(alerts),
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "skipped_rate_limited": 0,
        "skipped_no_webhook": 0,
        "webhook_configured": bool(resolved_webhook),
    }

    if not alerts:
        return result

    if not resolved_webhook:
        result["skipped_no_webhook"] = len(alerts)
        return result

    for alert in alerts:
        alert_name = str(alert.get("name") or alert.get("metric") or "runtime_alert")
        now = time.time()
        if not _allow_dispatch(alert_name, now, min_interval):
            result["skipped_rate_limited"] += 1
            continue

        result["attempted"] += 1
        payload = {
            "source": "growmate-backend",
            "trigger": str(trigger or "runtime_metrics"),
            "alert": alert,
            "metrics": snapshot,
            "sent_at": datetime.now(UTC).isoformat(),
        }
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            resolved_webhook,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                status_code = int(getattr(response, "status", 200) or 200)
                if 200 <= status_code < 300:
                    result["sent"] += 1
                    _mark_dispatched(alert_name, now)
                else:
                    result["failed"] += 1
        except (urllib.error.URLError, TimeoutError, ValueError):
            result["failed"] += 1

    return result


def check_and_dispatch_runtime_alerts(
    *,
    metrics: dict[str, int] | None = None,
    trigger: str | None = None,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    snapshot = metrics if isinstance(metrics, dict) else get_metrics_snapshot()
    alerts = evaluate_runtime_alerts(snapshot)
    dispatch_result = dispatch_runtime_alerts(
        alerts,
        metrics=snapshot,
        trigger=trigger,
        webhook_url=webhook_url,
    )
    dispatch_result["metrics"] = snapshot
    return dispatch_result


async def maybe_emit_runtime_alerts(
    *,
    trigger: str | None = None,
    metrics: dict[str, int] | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        check_and_dispatch_runtime_alerts,
        metrics=metrics,
        trigger=trigger,
    )
