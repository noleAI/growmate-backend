import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from agents.academic_agent.bayesian_tracker import bayesian_tracker
from agents.academic_agent.htn_planner import htn_planner
from api.routes.orchestrator_runtime import get_orchestrator
from core.memory_store import memory_store
from core.security import get_current_user
from core.supabase_client import insert_learning_session
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


@router.post("", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    user: dict = current_user_dependency,
):
    session_id = str(uuid.uuid4())
    student_id = str(user.get("sub", ""))

    if student_id:
        try:
            await insert_learning_session(session_id=session_id, student_id=student_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to insert learning_session for session_id=%s student_id=%s: %s",
                session_id,
                student_id,
                exc,
            )

    # Initialize basic state
    state = {
        "subject": request.subject,
        "topic": request.topic,
        "beliefs": bayesian_tracker.beliefs,
        "student_id": student_id,
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
):
    return {"status": "success", "session_id": session_id}


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
