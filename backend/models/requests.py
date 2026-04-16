from typing import Any, Dict, Optional

from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    subject: str
    topic: str
    mode: Optional[str] = None
    classification_level: Optional[str] = None
    onboarding_results: Optional[Dict[str, Any]] = None


class InteractionRequest(BaseModel):
    action_type: str
    quiz_id: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    xp_data: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None
    classification_level: Optional[str] = None
    onboarding_results: Optional[Dict[str, Any]] = None
    analytics_data: Optional[Dict[str, Any]] = None
    is_off_topic: bool = False
    resume: bool = False


class HitlResponseRequest(BaseModel):
    intervention_type: str
    accepted: bool


class UpdateSessionRequest(BaseModel):
    status: str
