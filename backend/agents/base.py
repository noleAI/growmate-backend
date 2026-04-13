from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    session_id: str
    student_id: Optional[str] = None
    question_id: Optional[str] = None
    user_response: Optional[Dict[str, Any]] = None
    behavior_signals: Optional[Dict[str, Any]] = None
    current_state: Dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.5
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
    academic_state: Dict[str, Any] = Field(default_factory=dict)
    empathy_state: Dict[str, Any] = Field(default_factory=dict)
    strategy_state: Dict[str, Any] = Field(default_factory=dict)
    hitl_pending: bool = False
    step: int = 0
