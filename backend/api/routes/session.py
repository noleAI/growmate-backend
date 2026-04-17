import asyncio
import copy
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from agents.academic_agent.bayesian_tracker import bayesian_tracker
from agents.academic_agent.htn_planner import htn_planner
from api.routes.orchestrator_runtime import get_orchestrator
from core.config import get_settings
from core.learning_mode import normalize_learning_mode
from core.lives_engine import can_play, check_regen
from core.memory_store import memory_store
from core.runtime_alerts import maybe_emit_runtime_alerts
from core.runtime_metrics import increment_metric
from core.security import (
    get_bearer_token,
    get_current_user,
    verify_quiz_signature,
)
from core.supabase_client import (
    count_daily_learning_sessions,
    get_latest_active_learning_session,
    insert_learning_session,
    update_learning_session,
    update_learning_session_progress,
)
from core.user_classifier import classify
from models.requests import (
    InteractionRequest,
    SessionCreateRequest,
    UpdateSessionRequest,
)
from models.responses import InteractionResponse, SessionResponse

router = APIRouter()
logger = logging.getLogger("api.session")
current_user_dependency = Depends(get_current_user)
VALID_SESSION_STATUSES = {"active", "completed", "abandoned"}
QUIZ_LIFE_ACTIONS = {"submit_quiz", "submit_answer"}


def _normalize_mode_or_400(raw_mode: str | None) -> str:
    normalized = normalize_learning_mode(raw_mode, default="explore")
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mode. Allowed values: exam_prep, explore",
        )
    return normalized


def _resolve_quiz_daily_limit() -> int:
    try:
        return int(max(1, get_settings().quiz_daily_session_limit))
    except Exception:
        return 5


def _resolve_signature_config() -> tuple[str | None, int]:
    try:
        settings = get_settings()
        return settings.quiz_hmac_secret, int(settings.quiz_signature_ttl_seconds)
    except Exception:
        return None, 300


def _resolve_signature_resume_grace_seconds() -> int:
    try:
        return int(max(1, get_settings().quiz_signature_resume_grace_seconds))
    except Exception:
        return 1800


async def _verify_signature_with_resume_grace(
    *,
    http_request: Request,
    secret: str | None,
    ttl_seconds: int,
    resume_requested: bool,
    session_id: str,
    action_type: str,
) -> str:
    try:
        await verify_quiz_signature(
            http_request,
            secret=secret,
            ttl_seconds=ttl_seconds,
        )
        return "default"
    except HTTPException as exc:
        is_expired = (
            exc.status_code == status.HTTP_401_UNAUTHORIZED
            and str(exc.detail) == "signature_expired"
        )
        if is_expired:
            increment_metric("signature_expired_total")
            asyncio.create_task(
                maybe_emit_runtime_alerts(trigger="signature_expired")
            )
        if not (resume_requested and is_expired):
            raise

        resume_grace_ttl = max(ttl_seconds, _resolve_signature_resume_grace_seconds())
        if resume_grace_ttl <= ttl_seconds:
            raise

        logger.info(
            "Applying signature resume grace session_id=%s action_type=%s base_ttl=%s grace_ttl=%s",
            session_id,
            action_type,
            ttl_seconds,
            resume_grace_ttl,
        )
        await verify_quiz_signature(
            http_request,
            secret=secret,
            ttl_seconds=resume_grace_ttl,
        )
        increment_metric("resume_signature_grace_used_total")
        return "resume_grace"


def _build_pending_session_payload(row: dict) -> dict:
    total_questions = int(row.get("total_questions", 10) or 10)
    if total_questions <= 0:
        total_questions = 10

    last_question_index = int(row.get("last_question_index", 0) or 0)
    if last_question_index < 0:
        last_question_index = 0
    if last_question_index > total_questions:
        last_question_index = total_questions

    progress_percent = row.get("progress_percent")
    if progress_percent is None:
        progress_percent = int(round((last_question_index / total_questions) * 100))
    else:
        progress_percent = int(progress_percent or 0)
    progress_percent = max(0, min(100, progress_percent))

    snapshot = row.get("state_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}

    strategy_state = snapshot.get("strategy_state")
    if not isinstance(strategy_state, dict):
        strategy_state = {}

    mode = str(
        snapshot.get("mode")
        or strategy_state.get("mode")
        or "explore"
    ).strip() or "explore"

    pause_state = bool(snapshot.get("pause_state", False))
    pause_reason = snapshot.get("pause_reason")
    if pause_reason is not None:
        pause_reason = str(pause_reason).strip() or None

    next_question_index = min(total_questions, max(0, last_question_index))

    return {
        "session_id": str(row.get("id", "")),
        "status": str(row.get("status") or "active"),
        "last_question_index": last_question_index,
        "next_question_index": next_question_index,
        "total_questions": total_questions,
        "progress_percent": progress_percent,
        "mode": mode,
        "pause_state": pause_state,
        "pause_reason": pause_reason,
        "resume_context_version": 1,
        "last_active_at": row.get("last_interaction_at") or row.get("start_time"),
        "abandoned_at": row.get("end_time"),
    }


@router.post("", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    user: dict = current_user_dependency,
    access_token: str = Depends(get_bearer_token),
):
    student_id = str(user.get("sub", ""))
    mode = _normalize_mode_or_400(request.mode)

    if student_id:
        try:
            pending_row = await get_latest_active_learning_session(
                student_id=student_id,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to check pending session for student_id=%s before create: %s",
                student_id,
                exc,
            )
            pending_row = None

        if isinstance(pending_row, dict) and pending_row.get("id"):
            existing_session_id = str(pending_row.get("id")).strip()
            existing_state = memory_store.get_session_state(existing_session_id)
            snapshot = pending_row.get("state_snapshot")
            if not isinstance(snapshot, dict):
                snapshot = {}
            snapshot_strategy = snapshot.get("strategy_state")
            if not isinstance(snapshot_strategy, dict):
                snapshot_strategy = {}

            initial_state = existing_state or {
                "subject": request.subject,
                "topic": request.topic,
                "beliefs": copy.deepcopy(bayesian_tracker.beliefs),
                "student_id": student_id,
                "classification_level": str(
                    snapshot.get("user_classification_level")
                    or snapshot_strategy.get("classification_level")
                    or request.classification_level
                    or "intermediate"
                ),
                "mode": str(
                    snapshot.get("mode")
                    or snapshot_strategy.get("mode")
                    or mode
                ),
            }
            memory_store.save_session_state(existing_session_id, initial_state)

            return SessionResponse(
                session_id=existing_session_id,
                status=str(pending_row.get("status") or "active"),
                start_time=str(
                    pending_row.get("start_time")
                    or datetime.now(UTC).isoformat()
                ),
                initial_state=initial_state,
            )

    session_id = str(uuid.uuid4())

    daily_limit = _resolve_quiz_daily_limit()
    if student_id:
        today = datetime.now(UTC).date()
        try:
            daily_sessions = await count_daily_learning_sessions(
                student_id=student_id,
                usage_date=today,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to read daily session count for student_id=%s: %s",
                student_id,
                exc,
            )
            daily_sessions = 0

        if int(daily_sessions) >= int(daily_limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="quiz_rate_limit",
            )

    if student_id:
        try:
            await insert_learning_session(
                session_id=session_id,
                student_id=student_id,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to insert learning_session for session_id=%s student_id=%s: %s",
                session_id,
                student_id,
                exc,
            )

    # Initialize basic state with a defensive copy of mutable tracker data
    classification_level = request.classification_level
    if not classification_level and isinstance(request.onboarding_results, dict):
        classification_level = classify(request.onboarding_results).value
    if not classification_level:
        classification_level = "intermediate"

    state = {
        "subject": request.subject,
        "topic": request.topic,
        "beliefs": copy.deepcopy(bayesian_tracker.beliefs),
        "student_id": student_id,
        "classification_level": classification_level,
        "mode": mode,
    }
    memory_store.save_session_state(session_id, state)

    if student_id:
        initial_snapshot = {
            "step": 0,
            "mode": mode,
            "user_classification_level": classification_level,
            "pause_state": False,
            "pause_reason": None,
            "off_topic_counter": 0,
            "hitl_pending": False,
            "subject": request.subject,
            "topic": request.topic,
            "strategy_state": {
                "mode": mode,
                "classification_level": classification_level,
                "student_id": student_id,
                "total_questions": 10,
                "last_question_index": 0,
                "progress_percent": 0,
            },
            "academic_state": {
                "belief_dist": copy.deepcopy(bayesian_tracker.beliefs),
            },
            "empathy_state": {},
        }
        try:
            await update_learning_session_progress(
                session_id=session_id,
                student_id=student_id,
                last_question_index=0,
                total_questions=10,
                progress_percent=0,
                last_interaction_at=datetime.now(UTC),
                state_snapshot=initial_snapshot,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to persist initial session snapshot for session_id=%s student_id=%s: %s",
                session_id,
                student_id,
                exc,
            )

    return SessionResponse(
        session_id=session_id,
        status="active",
        start_time=datetime.now(UTC).isoformat(),
        initial_state=state,
    )


@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    user: dict = current_user_dependency,
    access_token: str = Depends(get_bearer_token),
):
    raw_student_id = user.get("sub")
    student_id = raw_student_id.strip() if isinstance(raw_student_id, str) else ""
    if not student_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )
    
    status_value = request.status.strip().lower()

    if status_value not in VALID_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session status. Allowed values: active, completed, abandoned",
        )

    end_time = (
        datetime.now(UTC).isoformat()
        if status_value in {"completed", "abandoned"}
        else None
    )

    try:
        result = await update_learning_session(
            session_id=session_id,
            student_id=student_id,
            status=status_value,
            end_time=end_time,
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to update learning_session for session_id=%s student_id=%s: %s",
            session_id,
            student_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session",
        ) from exc

    rows = result.get("data") or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    cached_state = memory_store.get_session_state(session_id)
    if cached_state:
        cached_state["session_status"] = status_value
        cached_state["end_time"] = end_time
        memory_store.save_session_state(session_id, cached_state)

    return {
        "status": "success",
        "session_id": session_id,
        "session_status": status_value,
    }


@router.get("/pending")
async def get_pending_session(
    user: dict = current_user_dependency,
    access_token: str = Depends(get_bearer_token),
):
    raw_student_id = user.get("sub")
    student_id = raw_student_id.strip() if isinstance(raw_student_id, str) else ""
    if not student_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )

    try:
        pending_row = await get_latest_active_learning_session(
            student_id=student_id,
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load pending session for student_id=%s: %s",
            student_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load pending session",
        ) from exc

    if not pending_row:
        return {
            "has_pending": False,
            "session": None,
        }

    return {
        "has_pending": True,
        "session": _build_pending_session_payload(pending_row),
    }


@router.post("/{session_id}/interact", response_model=InteractionResponse)
async def interact(
    http_request: Request,
    session_id: str,
    request: InteractionRequest,
    user: dict = current_user_dependency,
    access_token: str = Depends(get_bearer_token),
):
    response_data = request.response_data or {}
    behavior_signals = response_data.get("behavior_signals", {})
    if not isinstance(behavior_signals, dict):
        behavior_signals = {}

    action_type = str(request.action_type or "").strip().lower()
    student_id = str(user.get("sub", "")).strip()
    effective_mode = _normalize_mode_or_400(request.mode)
    if action_type in QUIZ_LIFE_ACTIONS:
        secret, ttl = _resolve_signature_config()
        signature_mode = await _verify_signature_with_resume_grace(
            http_request=http_request,
            secret=secret,
            ttl_seconds=ttl,
            resume_requested=bool(request.resume),
            session_id=session_id,
            action_type=action_type,
        )
        if signature_mode != "default":
            logger.info(
                "Signature verification mode switched session_id=%s action_type=%s mode=%s",
                session_id,
                action_type,
                signature_mode,
            )

    orchestrator = get_orchestrator(session_id=session_id)
    payload = {
        "action_type": action_type,
        "question_id": request.quiz_id or request.action_type,
        "response": response_data,
        "behavior_signals": behavior_signals,
        "xp_data": request.xp_data,
        "mode": effective_mode,
        "classification_level": request.classification_level,
        "onboarding_results": request.onboarding_results,
        "analytics_data": request.analytics_data,
        "is_off_topic": request.is_off_topic,
        "resume": request.resume,
        "student_id": str(user.get("sub", "")),
        "access_token": access_token,
    }

    if action_type in QUIZ_LIFE_ACTIONS and effective_mode != "explore" and student_id:
        try:
            if not await can_play(user_id=student_id, access_token=access_token):
                lives_status = await check_regen(
                    user_id=student_id,
                    access_token=access_token,
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": "no_lives_remaining",
                        "message": (
                            "Bạn đã hết tim! Hãy chờ hồi sinh hoặc xem lại bài cũ nhé."
                        ),
                        "next_regen_in_seconds": int(
                            lives_status.get("next_regen_in_seconds", 0) or 0
                        ),
                        "next_regen_at": lives_status.get("next_regen_at"),
                    },
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Lives guard check failed for session_id=%s student_id=%s: %s",
                session_id,
                student_id,
                exc,
            )

    try:
        result = await orchestrator.run_session_step(session_id, payload)
        next_node_type = str(result.get("action", "hint"))
        content = str(
            result.get("payload", {}).get("text")
            or f"Next action selected: {next_node_type}"
        )
        if bool(request.resume):
            increment_metric("resume_success_total")
        entropy = float(
            result.get("dashboard_update", {})
            .get("academic", {})
            .get("entropy", bayesian_tracker.get_entropy())
        )
        repaired = next_node_type in {"backtrack_repair", "hitl_pending"}
        return InteractionResponse(
            next_node_type=next_node_type,
            content=content,
            plan_repaired=repaired,
            belief_entropy=entropy,
            data_driven=result.get("data_driven"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Orchestrator interact failed for session_id=%s: %s. Falling back to legacy route.",
            session_id,
            exc,
        )

    # Legacy fallback path
    _ = bayesian_tracker.update_beliefs(request.action_type, response_data)
    entropy = bayesian_tracker.get_entropy()
    repaired = False
    if entropy > 0.8:
        _, repaired = htn_planner.repair_plan(
            "concept_a", "low_confidence", {"concept_a_retries": 0}
        )

    return InteractionResponse(
        next_node_type="hint",
        content="Here is a hint for your next step based on our analysis...",
        plan_repaired=repaired,
        belief_entropy=entropy,
    )
