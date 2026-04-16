from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.security import get_bearer_token, get_current_user
from core.supabase_client import get_user_profile, upsert_user_profile

router = APIRouter()

ALLOWED_STUDY_GOALS = {"exam_prep", "explore"}


class UserProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    study_goal: str | None = None
    daily_minutes: int | None = None


def _require_user_id(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )
    return user_id


def _normalize_study_goal(study_goal: str | None) -> str | None:
    if study_goal is None:
        return None

    normalized = str(study_goal).strip().lower()
    if not normalized:
        return None

    if normalized not in ALLOWED_STUDY_GOALS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid study_goal. Allowed values: exam_prep, explore",
        )

    return normalized


def _normalize_daily_minutes(daily_minutes: int | None) -> int | None:
    if daily_minutes is None:
        return None

    value = int(daily_minutes)
    if value < 5 or value > 180:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="daily_minutes must be between 5 and 180",
        )

    return value


def _serialize_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": str(row.get("user_id", "")),
        "display_name": row.get("display_name"),
        "avatar_url": row.get("avatar_url"),
        "user_level": str(row.get("user_level") or "beginner"),
        "study_goal": row.get("study_goal"),
        "daily_minutes": int(row.get("daily_minutes", 15) or 15),
        "onboarded_at": row.get("onboarded_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.get("/user/profile")
async def get_profile(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)

    try:
        row = await get_user_profile(user_id=user_id, access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load user profile: {exc}",
        ) from exc

    return _serialize_profile(row)


@router.put("/user/profile")
async def update_profile(
    request: UserProfileUpdateRequest,
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)
    normalized_goal = _normalize_study_goal(request.study_goal)
    normalized_daily_minutes = _normalize_daily_minutes(request.daily_minutes)

    try:
        current = await get_user_profile(user_id=user_id, access_token=access_token)
        persisted = await upsert_user_profile(
            user_id=user_id,
            display_name=(
                request.display_name
                if request.display_name is not None
                else current.get("display_name")
            ),
            avatar_url=(
                request.avatar_url
                if request.avatar_url is not None
                else current.get("avatar_url")
            ),
            user_level=str(current.get("user_level") or "beginner"),
            study_goal=(
                normalized_goal
                if normalized_goal is not None
                else current.get("study_goal")
            ),
            daily_minutes=(
                int(normalized_daily_minutes)
                if normalized_daily_minutes is not None
                else int(current.get("daily_minutes", 15) or 15)
            ),
            onboarded_at=current.get("onboarded_at"),
            access_token=access_token,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user profile: {exc}",
        ) from exc

    return {
        "status": "updated",
        **_serialize_profile(persisted),
    }
