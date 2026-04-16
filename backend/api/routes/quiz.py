from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from core.learning_mode import normalize_learning_mode
from core.lives_engine import check_regen, lose_life
from core.quiz_service import quiz_service
from core.security import (
    get_bearer_token,
    get_current_user,
    require_quiz_signature,
)
from core.supabase_client import count_daily_learning_sessions

router = APIRouter()


class QuizSubmitRequest(BaseModel):
    session_id: str
    question_id: str
    selected_option: str | None = None
    answer: str | None = None
    answers: dict[str, Any] | None = None
    time_taken_sec: float | None = None
    mode: str | None = None


def _require_user_id(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )
    return user_id


def _normalize_mode_or_400(raw_mode: str | None) -> str:
    normalized = normalize_learning_mode(raw_mode, default="explore")
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mode. Allowed values: exam_prep, explore",
        )
    return normalized


@router.get("/quiz/next")
async def get_next_question(
    request: Request,
    session_id: str = Query(..., min_length=1),
    index: int = Query(default=0, ge=0),
    total_questions: int = Query(default=10, ge=1, le=30),
    mode: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    del request
    user_id = _require_user_id(user)
    normalized_mode = _normalize_mode_or_400(mode)

    # Soft guard for session abuse: keep at most 5 quiz sessions/day/user in exam mode.
    if normalized_mode == "exam_prep":
        usage_date = datetime.now(UTC).date()
        try:
            daily_sessions = await count_daily_learning_sessions(
                student_id=user_id,
                usage_date=usage_date,
                access_token=access_token,
            )
        except Exception:
            daily_sessions = 0

        if int(daily_sessions) >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="quiz_rate_limit",
            )

    question = quiz_service.get_question_for_session(
        session_id=session_id,
        mode=normalized_mode,
        index=index,
        total_questions=total_questions,
    )
    if question is None:
        return {
            "status": "completed",
            "session_id": session_id,
            "next_question": None,
        }

    timer_sec = 45 if normalized_mode == "exam_prep" else None

    return {
        "status": "ok",
        "mode": normalized_mode,
        "timer_sec": timer_sec,
        "next_question": question,
    }


@router.post("/quiz/submit", dependencies=[Depends(require_quiz_signature)])
async def submit_quiz_answer(
    request: Request,
    payload: QuizSubmitRequest,
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    del request
    user_id = _require_user_id(user)
    normalized_mode = _normalize_mode_or_400(payload.mode)

    try:
        result = quiz_service.submit_answer(
            session_id=payload.session_id,
            question_id=payload.question_id,
            selected_option=payload.selected_option,
            short_answer=payload.answer,
            cluster_answers=payload.answers,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    response = {
        "session_id": payload.session_id,
        "question_id": payload.question_id,
        "is_correct": bool(result["is_correct"]),
        "explanation": result["explanation"],
    }

    if normalized_mode != "explore" and not result["is_correct"]:
        try:
            lives_status = await lose_life(user_id=user_id, access_token=access_token)
            response["lives_remaining"] = int(lives_status.get("current", 0) or 0)
            response["can_play"] = bool(lives_status.get("can_play", False))
            response["next_regen_in_seconds"] = int(
                lives_status.get("next_regen_in_seconds", 0) or 0
            )
        except Exception:
            regen_status = await check_regen(user_id=user_id, access_token=access_token)
            response["lives_remaining"] = int(regen_status.get("current", 0) or 0)
            response["can_play"] = bool(regen_status.get("can_play", False))

    return response
