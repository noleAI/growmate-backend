from datetime import datetime

import pytest
from fastapi import HTTPException

from api.routes import quota as quota_route


@pytest.mark.asyncio
async def test_get_quota_returns_usage_payload(monkeypatch) -> None:
    async def _usage_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-1"
        return {
            "user_id": "student-1",
            "date": "2026-04-15",
            "call_count": 7,
            "total_tokens": 350,
        }

    monkeypatch.setattr(quota_route, "get_user_token_usage", _usage_stub)

    result = await quota_route.get_quota(
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["used"] == 7
    assert result["limit"] == 20
    assert result["remaining"] == 13
    reset_at = datetime.fromisoformat(result["reset_at"])
    assert reset_at.hour == 0
    assert reset_at.minute == 0
    assert reset_at.second == 0
    assert reset_at.tzinfo is not None


@pytest.mark.asyncio
async def test_get_quota_requires_student_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await quota_route.get_quota(user={"sub": ""}, access_token="token")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_quota_returns_500_when_storage_fails(monkeypatch) -> None:
    async def _usage_stub(**kwargs) -> dict:
        del kwargs
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(quota_route, "get_user_token_usage", _usage_stub)

    with pytest.raises(HTTPException) as exc_info:
        await quota_route.get_quota(user={"sub": "student-2"}, access_token="token")

    assert exc_info.value.status_code == 500
    assert "Failed to read quota usage" in str(exc_info.value.detail)
