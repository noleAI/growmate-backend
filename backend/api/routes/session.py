import copy
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from agents.academic_agent.bayesian_tracker import bayesian_tracker
from agents.academic_agent.htn_planner import htn_planner
from api.routes.orchestrator_runtime import get_orchestrator
from core.memory_store import memory_store
from core.security import get_bearer_token, get_current_user
from core.supabase_client import insert_learning_session, update_learning_session
from core.user_classifier import classify
from models.requests import (
    InteractionRequest,
    SessionCreateRequest,
    UpdateSessionRequest,
)
from models.responses import InteractionResponse, SessionResponse

# TODO: from agents.orchestrator import orchestrator

router = APIRouter()
logger = logging.getLogger("api.session")
current_user_dependency = Depends(get_current_user)
VALID_SESSION_STATUSES = {"active", "completed", "abandoned"}


@router.post("", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    user: dict = current_user_dependency,
    access_token: str = Depends(get_bearer_token),
):
    session_id = str(uuid.uuid4())
    student_id = str(user.get("sub", ""))

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

    mode = request.mode or "normal"

    state = {
        "subject": request.subject,
        "topic": request.topic,
        "beliefs": copy.deepcopy(bayesian_tracker.beliefs),
        "student_id": student_id,
        "classification_level": classification_level,
        "mode": mode,
    }
    memory_store.save_session_state(session_id, state)

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


@router.post("/{session_id}/interact", response_model=InteractionResponse)
async def interact(
    session_id: str,
    request: InteractionRequest,
    user: dict = current_user_dependency,
):
    response_data = request.response_data or {}
    behavior_signals = response_data.get("behavior_signals", {})
    if not isinstance(behavior_signals, dict):
        behavior_signals = {}

    orchestrator = get_orchestrator(session_id=session_id)
    payload = {
        "question_id": request.quiz_id or request.action_type,
        "response": response_data,
        "behavior_signals": behavior_signals,
        "xp_data": request.xp_data,
        "mode": request.mode,
        "classification_level": request.classification_level,
        "onboarding_results": request.onboarding_results,
        "analytics_data": request.analytics_data,
        "is_off_topic": request.is_off_topic,
        "resume": request.resume,
        "student_id": str(user.get("sub", "")),
    }

    try:
        result = await orchestrator.run_session_step(session_id, payload)
        next_node_type = str(result.get("action", "hint"))
        content = str(
            result.get("payload", {}).get("text")
            or f"Next action selected: {next_node_type}"
        )
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
