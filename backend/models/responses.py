from typing import Any, Dict, List

from pydantic import BaseModel, Field


class FormulaRecommendationResponse(BaseModel):
    formulaId: str
    title: str
    formula: str
    hypothesis: str
    belief: float
    relevanceScore: float
    reason: str


class DataDrivenResponse(BaseModel):
    diagnosis: Dict[str, Any]
    interventions: List[Dict[str, Any]]
    selectedIntervention: Dict[str, Any] | None = None
    formulaRecommendations: List[FormulaRecommendationResponse] = Field(default_factory=list)
    systemBehavior: Dict[str, Any]


class SessionResponse(BaseModel):
    session_id: str
    status: str
    start_time: str
    initial_state: Dict[str, Any]


class InteractionResponse(BaseModel):
    next_node_type: str
    content: str
    plan_repaired: bool
    belief_entropy: float
    data_driven: DataDrivenResponse | None = None


class ConfigResponse(BaseModel):
    category: str
    version: str
    payload: Dict[str, Any]


class InspectionBeliefResponse(BaseModel):
    session_id: str
    beliefs: List[Dict[str, Any]]
