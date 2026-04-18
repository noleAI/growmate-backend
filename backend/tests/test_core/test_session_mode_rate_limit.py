import pytest
from fastapi import HTTPException

from api.routes import session as session_route


class _RequestStub:
    method = "POST"

    class _URL:
        path = "/api/v1/sessions/sess/interact"

    url = _URL()
    headers = {}

    async def body(self) -> bytes:
        return b"{}"


@pytest.mark.asyncio
async def test_create_session_rejects_invalid_mode() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await session_route.create_session(
            request=session_route.SessionCreateRequest(
                subject="math",
                topic="derivative",
                mode="invalid",
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_session_rate_limited(monkeypatch) -> None:
    async def _daily_count_stub(**kwargs) -> int:
        del kwargs
        return 5

    async def _pending_stub(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(session_route, "count_daily_learning_sessions", _daily_count_stub)
    monkeypatch.setattr(
        session_route,
        "get_latest_active_learning_session",
        _pending_stub,
    )

    with pytest.raises(HTTPException) as exc_info:
        await session_route.create_session(
            request=session_route.SessionCreateRequest(
                subject="math",
                topic="derivative",
                mode="explore",
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "quiz_rate_limit"


@pytest.mark.asyncio
async def test_create_session_reuses_pending_active_session(monkeypatch) -> None:
    async def _pending_stub(**kwargs):
        del kwargs
        return {
            "id": "sess-existing-1",
            "status": "active",
            "start_time": "2026-04-17T08:00:00+00:00",
            "state_snapshot": {
                "mode": "explore",
                "user_classification_level": "intermediate",
                "strategy_state": {
                    "mode": "explore",
                    "classification_level": "intermediate",
                },
            },
        }

    monkeypatch.setattr(
        session_route,
        "get_latest_active_learning_session",
        _pending_stub,
    )

    response = await session_route.create_session(
        request=session_route.SessionCreateRequest(
            subject="math",
            topic="derivative",
            mode="explore",
        ),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert response.session_id == "sess-existing-1"
    assert response.status == "active"


@pytest.mark.asyncio
async def test_session_interact_rejects_invalid_mode() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await session_route.interact(
            http_request=_RequestStub(),
            session_id="sess-invalid-mode",
            request=session_route.InteractionRequest(
                action_type="request_hint",
                mode="invalid",
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400
