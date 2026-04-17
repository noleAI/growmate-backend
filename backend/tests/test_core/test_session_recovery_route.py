import pytest
from fastapi import HTTPException

from api.routes import session_recovery as session_recovery_route


@pytest.mark.asyncio
async def test_get_pending_session_returns_empty_when_no_active_session(monkeypatch) -> None:
    async def _pending_stub(**kwargs):
        assert kwargs["student_id"] == "student-1"
        return None

    monkeypatch.setattr(
        session_recovery_route,
        "get_latest_active_learning_session",
        _pending_stub,
    )

    result = await session_recovery_route.get_pending_session(
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["has_pending"] is False
    assert result["session"] is None


@pytest.mark.asyncio
async def test_get_pending_session_returns_payload(monkeypatch) -> None:
    async def _pending_stub(**kwargs):
        del kwargs
        return {
            "id": "sess-1",
            "status": "active",
            "last_question_index": 4,
            "total_questions": 10,
            "progress_percent": 40,
            "last_interaction_at": "2026-04-16T09:20:00+00:00",
            "end_time": None,
        }

    monkeypatch.setattr(
        session_recovery_route,
        "get_latest_active_learning_session",
        _pending_stub,
    )

    result = await session_recovery_route.get_pending_session(
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["has_pending"] is True
    assert result["session"]["session_id"] == "sess-1"
    assert result["session"]["last_question_index"] == 4
    assert result["session"]["next_question_index"] == 4
    assert result["session"]["progress_percent"] == 40
    assert result["session"]["resume_context_version"] == 1


@pytest.mark.asyncio
async def test_get_pending_session_requires_student_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await session_recovery_route.get_pending_session(
            user={},
            access_token="token",
        )

    assert exc_info.value.status_code == 401
