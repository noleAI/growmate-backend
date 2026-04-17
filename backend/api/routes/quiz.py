from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from core.learning_mode import normalize_learning_mode
from core.lives_engine import check_regen, lose_life
from core.quiz_service import quiz_service
from core.runtime_alerts import maybe_emit_runtime_alerts
from core.runtime_metrics import increment_metric
from core.security import (
    get_bearer_token,
    get_current_user,
    require_quiz_signature,
)
from core.supabase_client import count_daily_learning_sessions
from core.supabase_client import (
    get_learning_session_by_id,
    insert_quiz_question_attempt,
    list_learning_sessions,
    list_quiz_question_attempts,
    update_learning_session_progress,
)

router = APIRouter()
logger = logging.getLogger("api.quiz")


class QuizSubmitRequest(BaseModel):
    session_id: str
    question_id: str
    selected_option: str | None = None
    answer: str | None = None
    answers: dict[str, Any] | None = None
    time_taken_sec: float | None = None
    mode: str | None = None
    question_index: int | None = None
    total_questions: int | None = None


def _normalize_total_questions(value: int | None, fallback: int = 10) -> int:
    safe = int(value or fallback)
    if safe <= 0:
        return int(max(1, fallback))
    return safe


def _build_quiz_summary(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    answered_count = len(attempts)
    total_score = float(sum(float(item.get("score") or 0.0) for item in attempts))
    total_max_score = float(
        sum(float(item.get("max_score") or 0.0) for item in attempts)
    )
    correct_count = int(sum(1 for item in attempts if bool(item.get("is_correct", False))))

    accuracy_percent = 0
    if answered_count > 0:
        accuracy_percent = int(round((correct_count / answered_count) * 100))

    return {
        "answered_count": int(answered_count),
        "correct_count": int(correct_count),
        "total_score": round(total_score, 4),
        "max_score": round(total_max_score, 4),
        "accuracy_percent": int(max(0, min(100, accuracy_percent))),
    }


def _parse_snapshot(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    snapshot = row.get("state_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _sanitize_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    evaluation = attempt.get("evaluation") if isinstance(attempt.get("evaluation"), dict) else {}
    return {
        "question_id": str(attempt.get("question_id") or ""),
        "question_template_id": str(attempt.get("question_template_id") or ""),
        "question_type": str(attempt.get("question_type") or ""),
        "is_correct": bool(attempt.get("is_correct", False)),
        "score": float(attempt.get("score") or 0.0),
        "max_score": float(attempt.get("max_score") or 0.0),
        "explanation": str(evaluation.get("explanation") or attempt.get("explanation") or ""),
        "user_answer": attempt.get("user_answer") if isinstance(attempt.get("user_answer"), dict) else {},
        "submitted_at": attempt.get("submitted_at"),
        "time_taken_sec": attempt.get("time_taken_sec"),
    }


def _extract_attempts_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    quiz_state = snapshot.get("quiz_state") if isinstance(snapshot, dict) else {}
    if not isinstance(quiz_state, dict):
        return []
    attempts = quiz_state.get("attempts")
    if not isinstance(attempts, list):
        return []
    return [item for item in attempts if isinstance(item, dict)]


def _extract_summary_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    quiz_state = snapshot.get("quiz_state") if isinstance(snapshot, dict) else {}
    if not isinstance(quiz_state, dict):
        return {}
    summary = quiz_state.get("summary")
    if not isinstance(summary, dict):
        return {}
    return summary


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
        "score": float(result.get("score") or 0.0),
        "max_score": float(result.get("max_score") or 0.0),
    }

    session_row: dict[str, Any] | None = None
    try:
        session_row = await get_learning_session_by_id(
            session_id=payload.session_id,
            student_id=user_id,
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load learning session before submit session_id=%s user_id=%s: %s",
            payload.session_id,
            user_id,
            exc,
        )

    total_questions = _normalize_total_questions(
        payload.total_questions,
        fallback=_normalize_total_questions(
            int((session_row or {}).get("total_questions", 10) or 10),
            fallback=10,
        ),
    )

    question_position = quiz_service.get_question_position(
        session_id=payload.session_id,
        mode=normalized_mode,
        total_questions=total_questions,
        question_id=payload.question_id,
    )
    if question_position is None and payload.question_index is not None:
        question_position = max(0, int(payload.question_index or 0))

    previous_index = 0
    if isinstance(session_row, dict):
        try:
            previous_index = max(0, int(session_row.get("last_question_index", 0) or 0))
        except Exception:
            previous_index = 0

    derived_index = previous_index
    if question_position is not None:
        derived_index = max(previous_index, int(question_position) + 1)
    else:
        derived_index = max(previous_index, 1)
    derived_index = min(total_questions, derived_index)

    progress_percent = int(round((derived_index / max(1, total_questions)) * 100))
    progress_percent = max(0, min(100, progress_percent))

    submitted_at = datetime.now(UTC).isoformat()
    attempt = {
        "question_id": str(payload.question_id),
        "question_template_id": str(result.get("question_template_id") or ""),
        "question_type": str(result.get("question_type") or ""),
        "is_correct": bool(result.get("is_correct", False)),
        "score": float(result.get("score") or 0.0),
        "max_score": float(result.get("max_score") or 0.0),
        "evaluation": result.get("evaluation") if isinstance(result.get("evaluation"), dict) else {},
        "explanation": str(result.get("explanation") or ""),
        "user_answer": result.get("user_answer") if isinstance(result.get("user_answer"), dict) else {},
        "time_taken_sec": payload.time_taken_sec,
        "submitted_at": submitted_at,
    }

    snapshot = _parse_snapshot(session_row)
    quiz_state = snapshot.get("quiz_state") if isinstance(snapshot.get("quiz_state"), dict) else {}
    existing_attempts = [item for item in quiz_state.get("attempts", []) if isinstance(item, dict)]
    filtered_attempts = [
        item for item in existing_attempts if str(item.get("question_id") or "") != str(payload.question_id)
    ]
    filtered_attempts.append(attempt)
    filtered_attempts.sort(key=lambda item: str(item.get("submitted_at") or ""))

    summary = _build_quiz_summary(filtered_attempts)
    quiz_state["attempts"] = filtered_attempts
    quiz_state["summary"] = summary
    quiz_state["updated_at"] = submitted_at
    snapshot["quiz_state"] = quiz_state

    # Keep top-level fields aligned for session resume and history views.
    snapshot["mode"] = normalized_mode
    snapshot["step"] = max(
        int(snapshot.get("step") or 0),
        int(derived_index),
    )
    strategy_state = snapshot.get("strategy_state") if isinstance(snapshot.get("strategy_state"), dict) else {}
    strategy_state["mode"] = normalized_mode
    strategy_state["total_questions"] = total_questions
    strategy_state["last_question_index"] = derived_index
    strategy_state["progress_percent"] = progress_percent
    strategy_state["last_interaction_at"] = submitted_at
    strategy_state["student_id"] = user_id
    snapshot["strategy_state"] = strategy_state

    if isinstance(session_row, dict):
        try:
            await update_learning_session_progress(
                session_id=payload.session_id,
                student_id=user_id,
                last_question_index=derived_index,
                total_questions=total_questions,
                progress_percent=progress_percent,
                last_interaction_at=submitted_at,
                state_snapshot=snapshot,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to persist quiz progress session_id=%s user_id=%s: %s",
                payload.session_id,
                user_id,
                exc,
            )

    question_template_id = str(result.get("question_template_id") or "").strip()
    if question_template_id:
        try:
            await insert_quiz_question_attempt(
                student_id=user_id,
                session_id=payload.session_id,
                question_template_id=question_template_id,
                question_type=str(result.get("question_type") or ""),
                user_answer=attempt["user_answer"],
                evaluation=attempt["evaluation"],
                score=float(result.get("score") or 0.0),
                max_score=float(result.get("max_score") or 0.0),
                is_correct=bool(result.get("is_correct", False)),
                submitted_at=submitted_at,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Best-effort attempt persistence failed session_id=%s question_id=%s user_id=%s: %s",
                payload.session_id,
                payload.question_id,
                user_id,
                exc,
            )

    response["progress_percent"] = progress_percent
    response["last_question_index"] = derived_index
    response["total_questions"] = total_questions
    response["quiz_summary"] = summary

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


@router.get("/quiz/sessions/{session_id}/result")
async def get_quiz_result(
    session_id: str,
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)

    session_row = await get_learning_session_by_id(
        session_id=session_id,
        student_id=user_id,
        access_token=access_token,
    )
    if not isinstance(session_row, dict):
        increment_metric("quiz_result_fetch_failures_total")
        asyncio.create_task(
            maybe_emit_runtime_alerts(trigger="quiz_result_fetch_failure")
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session_not_found",
        )

    snapshot = _parse_snapshot(session_row)
    attempts = _extract_attempts_from_snapshot(snapshot)
    if not attempts:
        attempts = await list_quiz_question_attempts(
            session_id=session_id,
            student_id=user_id,
            access_token=access_token,
        )

    sanitized_attempts = [_sanitize_attempt(item) for item in attempts]

    summary = _extract_summary_from_snapshot(snapshot)
    if not summary:
        summary = _build_quiz_summary(sanitized_attempts)

    increment_metric("quiz_result_fetch_success_total")

    return {
        "status": "ok",
        "session_id": session_id,
        "session_status": str(session_row.get("status") or "active"),
        "progress_percent": int(session_row.get("progress_percent", 0) or 0),
        "last_question_index": int(session_row.get("last_question_index", 0) or 0),
        "total_questions": int(session_row.get("total_questions", 10) or 10),
        "summary": summary,
        "attempts": sanitized_attempts,
        "started_at": session_row.get("start_time"),
        "ended_at": session_row.get("end_time"),
    }


@router.get("/quiz/history")
async def get_quiz_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)
    rows = await list_learning_sessions(
        student_id=user_id,
        statuses=["completed", "abandoned", "active"],
        limit=limit,
        offset=offset,
        access_token=access_token,
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        snapshot = _parse_snapshot(row)
        summary = _extract_summary_from_snapshot(snapshot)
        if not summary:
            summary = _build_quiz_summary(_extract_attempts_from_snapshot(snapshot))

        items.append(
            {
                "session_id": str(row.get("id") or ""),
                "status": str(row.get("status") or "active"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "progress_percent": int(row.get("progress_percent", 0) or 0),
                "last_question_index": int(row.get("last_question_index", 0) or 0),
                "total_questions": int(row.get("total_questions", 10) or 10),
                "summary": summary,
            }
        )

    return {
        "status": "ok",
        "total": len(items),
        "limit": int(limit),
        "offset": int(offset),
        "items": items,
    }
