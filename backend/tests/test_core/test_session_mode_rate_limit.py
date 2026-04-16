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

    monkeypatch.setattr(session_route, "count_daily_learning_sessions", _daily_count_stub)

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
