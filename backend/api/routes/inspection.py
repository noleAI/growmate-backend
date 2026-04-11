from fastapi import APIRouter, Depends
from core.security import get_current_user
from agents.academic_agent.bayesian_tracker import bayesian_tracker
from agents.empathy_agent.particle_filter import particle_filter
from agents.strategy_agent.q_learning import q_learning

router = APIRouter()

@router.get("/belief-state/{session_id}")
async def get_belief_state(session_id: str, user: dict = Depends(get_current_user)):
    # Used by the Inspection Dashboard to view Bayesian confidence.
    return {"session_id": session_id, "beliefs": bayesian_tracker.beliefs}

@router.get("/particle-state/{session_id}")
async def get_particle_state(session_id: str, user: dict = Depends(get_current_user)):
    return {"session_id": session_id, "state_summary": particle_filter.get_state_summary()}

@router.get("/q-values")
async def get_q_values(user: dict = Depends(get_current_user)):
    return {"q_table": q_learning.q_table}

@router.get("/audit-logs/{session_id}")
async def get_audit_logs(session_id: str, user: dict = Depends(get_current_user)):
    return {"session_id": session_id, "logs": []}
