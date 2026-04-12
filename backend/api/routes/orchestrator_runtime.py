from typing import Optional

from agents.academic_agent.bayesian_tracker import BayesianTracker
from agents.base import IAgent
from agents.empathy_agent.particle_filter import ParticleFilter
from agents.orchestrator import AgenticOrchestrator
from agents.strategy_agent.q_learning import QLearningAgent
from api.ws.dashboard import manager as dashboard_ws_manager
from core.config import get_settings
from core.llm_service import LLMService
from core.state_manager import StateManager

_orchestrators_by_session: dict[str, AgenticOrchestrator] = {}
_shared_state_manager: Optional[StateManager] = None
_shared_llm: Optional[LLMService] = None


def _build_shared_dependencies() -> tuple[StateManager, LLMService]:
    global _shared_state_manager, _shared_llm
    if _shared_state_manager is not None and _shared_llm is not None:
        return _shared_state_manager, _shared_llm

    settings = get_settings()
    _shared_state_manager = StateManager(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_key,
        ws_manager=dashboard_ws_manager,
    )
    _shared_llm = LLMService()
    return _shared_state_manager, _shared_llm


def _build_session_agents() -> dict[str, IAgent]:
    return {
        "academic": BayesianTracker(),
        "empathy": ParticleFilter(),
        "strategy": QLearningAgent(),
    }


def get_orchestrator(session_id: Optional[str] = None) -> AgenticOrchestrator:
    session_key = session_id or "default"
    if session_key in _orchestrators_by_session:
        return _orchestrators_by_session[session_key]

    state_mgr, llm = _build_shared_dependencies()
    orchestrator = AgenticOrchestrator(
        agents=_build_session_agents(),
        state_mgr=state_mgr,
        llm=llm,
    )
    _orchestrators_by_session[session_key] = orchestrator
    return orchestrator
