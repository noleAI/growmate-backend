from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.onboarding_service import onboarding_service
from core.security import get_bearer_token, get_current_user
from core.supabase_client import get_user_profile, upsert_user_profile

router = APIRouter()

ALLOWED_STUDY_GOALS = {"exam_prep", "explore"}


class OnboardingAnswer(BaseModel):
    question_id: str
    selected: str
    time_taken_sec: float | None = None


class OnboardingSubmitRequest(BaseModel):
    answers: list[OnboardingAnswer]
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


def _level_message(user_level: str) -> str:
    if user_level == "beginner":
        return "Bạn đang ở level Beginner. Mình cùng học chậm mà chắc nhé!"
    if user_level == "advanced":
        return "Bạn đang ở level Advanced. Sẵn sàng cho mục tiêu cao hơn!"
    return "Bạn đang ở level Intermediate. Cùng tiếp tục để tăng tốc nhé!"


@router.get("/questions")
async def get_onboarding_questions(
    _user: dict = Depends(get_current_user),
):
    questions = onboarding_service.get_questions_for_client()
    return {
        "topic": "derivative",
        "total_questions": len(questions),
        "questions": questions,
    }


@router.post("/submit")
async def submit_onboarding(
    request: OnboardingSubmitRequest,
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)
    normalized_study_goal = _normalize_study_goal(request.study_goal)
    normalized_daily_minutes = _normalize_daily_minutes(request.daily_minutes)

    try:
        evaluation = onboarding_service.evaluate_answers(
            [answer.model_dump() for answer in request.answers]
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate onboarding result: {exc}",
        ) from exc

    study_plan = dict(evaluation["study_plan"])
    if normalized_daily_minutes is not None:
        study_plan["daily_minutes"] = normalized_daily_minutes

    try:
        current_profile = await get_user_profile(
            user_id=user_id,
            access_token=access_token,
        )
        await upsert_user_profile(
            user_id=user_id,
            display_name=current_profile.get("display_name"),
            avatar_url=current_profile.get("avatar_url"),
            user_level=str(evaluation["user_level"]),
            study_goal=(
                normalized_study_goal
                if normalized_study_goal is not None
                else current_profile.get("study_goal")
            ),
            daily_minutes=int(study_plan["daily_minutes"]),
            onboarded_at=datetime.now(UTC),
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist onboarding profile: {exc}",
        ) from exc

    summary = evaluation["summary"]

    return {
        "user_level": evaluation["user_level"],
        "accuracy_percent": summary["accuracy_percent"],
        "study_plan": study_plan,
        "message": _level_message(str(evaluation["user_level"])),
        "onboarding_summary": {
            "total_questions": summary["total_questions"],
            "answered_questions": summary["answered_questions"],
            "correct_answers": summary["correct_answers"],
            "avg_response_time_ms": summary["avg_response_time_ms"],
        },
    }
