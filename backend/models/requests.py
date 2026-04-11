from typing import Any, Dict, Optional

from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    subject: str
    topic: str


class InteractionRequest(BaseModel):
    action_type: str
    quiz_id: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None


class HitlResponseRequest(BaseModel):
    intervention_type: str
    accepted: bool


class UpdateSessionRequest(BaseModel):
    status: str
