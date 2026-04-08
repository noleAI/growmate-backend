from fastapi import APIRouter, Depends, HTTPException
import uuid
from typing import Any, Dict
from datetime import datetime

from models.requests import SessionCreateRequest, InteractionRequest, UpdateSessionRequest
from models.responses import SessionResponse, InteractionResponse
from core.security import get_current_user
from core.memory_store import memory_store
from agents.academic_agent.bayesian_tracker import bayesian_tracker
from agents.academic_agent.htn_planner import htn_planner
from agents.orchestrator import orchestrator

router = APIRouter()

@router.post("", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest, user: dict = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    
    # Initialize basic state
    state = {
        "subject": request.subject,
        "topic": request.topic,
        "beliefs": bayesian_tracker.beliefs
    }
    memory_store.save_session_state(session_id, state)
    
    return SessionResponse(
        session_id=session_id,
        status="active",
        start_time=datetime.utcnow().isoformat(),
        initial_state=state
    )

@router.patch("/{session_id}")
async def update_session(session_id: str, request: UpdateSessionRequest, user: dict = Depends(get_current_user)):
    return {"status": "success", "session_id": session_id}

@router.post("/{session_id}/interact", response_model=InteractionResponse)
async def interact(session_id: str, request: InteractionRequest, user: dict = Depends(get_current_user)):
    # Standard interact loop
    updated_beliefs = bayesian_tracker.update_beliefs(request.action_type, request.response_data or {})
    entropy = bayesian_tracker.get_entropy()
    
    repaired = False
    # If entropy is high, trigger plan repair mock
    if entropy > 0.8:
        repaired = htn_planner.repair_plan("concept_a", "low_confidence")
        
    return InteractionResponse(
        next_node_type="hint",
        content="Here is a hint for your next step based on our analysis...",
        plan_repaired=repaired,
        belief_entropy=entropy
    )
