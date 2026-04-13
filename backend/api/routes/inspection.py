from fastapi import APIRouter, Depends

from api.routes.orchestrator_runtime import get_orchestrator
from core.security import get_current_user

router = APIRouter()


@router.get("/belief-state/{session_id}")
async def get_belief_state(session_id: str, user: dict = Depends(get_current_user)):
    # Used by the Inspection Dashboard to view Bayesian confidence.
    orch = get_orchestrator(session_id)
    academic = orch.agents.get("academic") if orch and getattr(orch, "agents", None) else None
    beliefs = getattr(academic, "beliefs", {}) if academic is not None else {}
    return {"session_id": session_id, "beliefs": beliefs}


@router.get("/particle-state/{session_id}")
async def get_particle_state(session_id: str, user: dict = Depends(get_current_user)):
    orch = get_orchestrator(session_id)
    empathy = orch.agents.get("empathy") if orch and getattr(orch, "agents", None) else None
    state_summary = {}
    if empathy is not None and hasattr(empathy, "get_state_summary"):
        try:
            state_summary = empathy.get_state_summary()
        except Exception:
            state_summary = {}

    return {"session_id": session_id, "state_summary": state_summary}


@router.get("/q-values")
async def get_q_values(user: dict = Depends(get_current_user)):
    # No session_id here: return global default (fallback) or empty table.
    orch = get_orchestrator(None)
    strategy = orch.agents.get("strategy") if orch and getattr(orch, "agents", None) else None
    q_table = getattr(strategy, "q_table", {}) if strategy is not None else {}
    return {"q_table": q_table}


@router.get("/audit-logs/{session_id}")
async def get_audit_logs(session_id: str, user: dict = Depends(get_current_user)):
    return {"session_id": session_id, "logs": []}
