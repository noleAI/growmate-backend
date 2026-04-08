from pydantic import BaseModel
from typing import Optional, Dict, Any, List

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

class ConfigResponse(BaseModel):
    category: str
    version: str
    payload: Dict[str, Any]
    
class InspectionBeliefResponse(BaseModel):
    session_id: str
    beliefs: List[Dict[str, Any]]
