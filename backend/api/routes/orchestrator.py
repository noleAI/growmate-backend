from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.routes.orchestrator_runtime import get_orchestrator
from core.security import get_current_user

router = APIRouter()
current_user_dependency = Depends(get_current_user)


class OrchestratorStepRequest(BaseModel):
    session_id: str
    question_id: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
    behavior_signals: Optional[Dict[str, Any]] = None


@router.post("/step")
async def run_orchestrator_step(
    request: OrchestratorStepRequest,
    user: dict = current_user_dependency,
):
    orchestrator = get_orchestrator()
    payload = {
        "question_id": request.question_id,
        "response": request.response,
        "behavior_signals": request.behavior_signals,
        "student_id": str(user.get("sub", "")),
    }
    result = await orchestrator.run_session_step(request.session_id, payload)
    return {"status": "ok", "result": result}
