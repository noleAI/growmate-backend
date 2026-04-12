from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel


class AgentInput(BaseModel):
    session_id: str
    student_id: Optional[str] = None
    question_id: Optional[str] = None
    user_response: Optional[Dict[str, Any]] = None
    behavior_signals: Optional[Dict[str, Any]] = None
    current_state: Dict[str, Any] = {}


class AgentOutput(BaseModel):
    action: str
    payload: Dict[str, Any] = {}
    confidence: float = 0.5
    metadata: Dict[str, Any] = {}


class IAgent(ABC):
    @abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class SessionState(BaseModel):
    session_id: str
    academic_state: Dict[str, Any] = {}
    empathy_state: Dict[str, Any] = {}
    strategy_state: Dict[str, Any] = {}
    hitl_pending: bool = False
    step: int = 0
