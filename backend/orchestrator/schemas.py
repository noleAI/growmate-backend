from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AcademicState(BaseModel):
    belief_distribution: Dict[str, float] = Field(default_factory=dict)
    entropy: float = 0.0
    top_hypothesis: str = ""
    confidence: float = 0.0


class EmpathyState(BaseModel):
    confusion: float = 0.0
    fatigue: float = 0.0
    uncertainty: float = 1.0
    particle_distribution: Dict[str, float] = Field(default_factory=dict)


class MemoryState(BaseModel):
    q_values: Dict[str, float] = Field(default_factory=dict)
    avg_reward: float = 0.0


class AggregatedState(BaseModel):
    academic: AcademicState
    empathy: EmpathyState
    memory: MemoryState
    embedding: Dict[str, float] = Field(default_factory=dict)


class OrchestratorDecision(BaseModel):
    action: str
    action_distribution: Dict[str, float] = Field(default_factory=dict)
    total_uncertainty: float = 0.0
    hitl_triggered: bool = False
    hitl_payload: Optional[Dict[str, Any]] = None
    rationale: str = ""
    monitoring: Dict[str, float] = Field(default_factory=dict)
