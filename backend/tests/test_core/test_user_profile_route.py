import pytest
from fastapi import HTTPException

from api.routes import user_profile as user_profile_route


@pytest.mark.asyncio
async def test_get_profile_returns_serialized_payload(monkeypatch) -> None:
    async def _get_profile_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-1"
        return {
            "user_id": "student-1",
            "display_name": "Student One",
            "avatar_url": None,
            "user_level": "intermediate",
            "study_goal": "exam_prep",
            "daily_minutes": 25,
            "onboarded_at": "2026-04-16T08:00:00+00:00",
            "created_at": "2026-04-15T08:00:00+00:00",
            "updated_at": "2026-04-16T08:00:00+00:00",
        }

    monkeypatch.setattr(user_profile_route, "get_user_profile", _get_profile_stub)

    result = await user_profile_route.get_profile(
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["user_id"] == "student-1"
    assert result["user_level"] == "intermediate"
    assert result["daily_minutes"] == 25


@pytest.mark.asyncio
async def test_update_profile_updates_partial_fields(monkeypatch) -> None:
    async def _get_profile_stub(**kwargs) -> dict:
        del kwargs
        return {
            "user_id": "student-1",
            "display_name": "Old Name",
            "avatar_url": None,
            "user_level": "beginner",
            "study_goal": "explore",
            "daily_minutes": 15,
            "onboarded_at": None,
            "created_at": None,
            "updated_at": None,
        }

    async def _upsert_profile_stub(**kwargs) -> dict:
        assert kwargs["display_name"] == "New Name"
        assert kwargs["study_goal"] == "exam_prep"
        assert kwargs["daily_minutes"] == 30
        return {
            "user_id": kwargs["user_id"],
            "display_name": kwargs["display_name"],
            "avatar_url": kwargs["avatar_url"],
            "user_level": kwargs["user_level"],
            "study_goal": kwargs["study_goal"],
            "daily_minutes": kwargs["daily_minutes"],
            "onboarded_at": kwargs["onboarded_at"],
            "created_at": None,
            "updated_at": "2026-04-16T08:00:00+00:00",
        }

    monkeypatch.setattr(user_profile_route, "get_user_profile", _get_profile_stub)
    monkeypatch.setattr(user_profile_route, "upsert_user_profile", _upsert_profile_stub)

    result = await user_profile_route.update_profile(
        request=user_profile_route.UserProfileUpdateRequest(
            display_name="New Name",
            study_goal="exam_prep",
            daily_minutes=30,
        ),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["status"] == "updated"
    assert result["display_name"] == "New Name"
    assert result["study_goal"] == "exam_prep"
    assert result["daily_minutes"] == 30


@pytest.mark.asyncio
async def test_update_profile_rejects_invalid_study_goal() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await user_profile_route.update_profile(
            request=user_profile_route.UserProfileUpdateRequest(study_goal="invalid"),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_profile_requires_student_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await user_profile_route.get_profile(user={}, access_token="token")

    assert exc_info.value.status_code == 401
