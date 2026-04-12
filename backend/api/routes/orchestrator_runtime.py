from typing import Optional

from agents.academic_agent.bayesian_tracker import bayesian_tracker
from agents.base import IAgent
from agents.empathy_agent.particle_filter import particle_filter
from agents.orchestrator import AgenticOrchestrator
from agents.strategy_agent.q_learning import q_learning
from core.config import get_settings
from core.llm_service import LLMService
from core.state_manager import StateManager

_orchestrator_instance: Optional[AgenticOrchestrator] = None


class _NoopWSManager:
    async def send_to_session(self, session_id: str, payload: str) -> None:
        del session_id, payload


def get_orchestrator() -> AgenticOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is not None:
        return _orchestrator_instance

    settings = get_settings()
    agents: dict[str, IAgent] = {
        "academic": bayesian_tracker,
        "empathy": particle_filter,
        "strategy": q_learning,
    }
    state_mgr = StateManager(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_key,
        ws_manager=_NoopWSManager(),
    )
    _orchestrator_instance = AgenticOrchestrator(
        agents=agents,
        state_mgr=state_mgr,
        llm=LLMService(),
    )
    return _orchestrator_instance
