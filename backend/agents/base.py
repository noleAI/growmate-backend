from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    session_id: str
    student_id: Optional[str] = None
    question_id: Optional[str] = None
    user_response: Optional[Dict[str, Any]] = None
    behavior_signals: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None
    classification_level: Optional[str] = None
    signal_history: Optional[list[Dict[str, Any]]] = None
    last_signal_time: Optional[str] = None
    analytics_data: Optional[Dict[str, Any]] = None
    off_topic_counter: int = 0
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
    mode: str = "normal"
    user_classification_level: str = "intermediate"
    signal_history: list[Dict[str, Any]] = Field(default_factory=list)
    last_signal_time: Optional[str] = None
    pause_state: bool = False
    pause_reason: Optional[str] = None
    pause_timestamp: Optional[str] = None
    off_topic_counter: int = 0
    last_interaction_timestamp: Optional[datetime] = None
    hitl_pending: bool = False
    step: int = 0
