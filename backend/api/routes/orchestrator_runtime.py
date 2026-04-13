from typing import Optional, Any, Dict
import os
import asyncio
import logging
from collections import OrderedDict
from pathlib import Path

import yaml

from agents.academic_agent.bayesian_tracker import BayesianTracker
from agents.base import IAgent
from agents.empathy_agent.particle_filter import ParticleFilter
from agents.orchestrator import AgenticOrchestrator
from agents.strategy_agent.q_learning import QLearningAgent
from api.ws.dashboard import manager as dashboard_ws_manager
from core.config import get_settings
from core.llm_service import LLMService
from core.state_manager import StateManager

logger = logging.getLogger("orchestrator_runtime")

# LRU cache for orchestrators to avoid unbounded growth in long-lived processes.
# Configurable via Settings.orchestrator_max_sessions or ORCHESTRATOR_MAX_SESSIONS env var.
_ORCHESTRATOR_MAX_SESSIONS_DEFAULT = 1024
_orchestrators_by_session: OrderedDict[str, AgenticOrchestrator] = OrderedDict()
_shared_state_manager: Optional[StateManager] = None
_shared_llm: Optional[LLMService] = None

# Cache loaded agents config to avoid repeated IO
_agents_config_cache: Optional[Dict[str, Any]] = None


def _get_max_orchestrators() -> int:
    settings = get_settings()
    env_val = os.environ.get("ORCHESTRATOR_MAX_SESSIONS")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            logger.warning("Invalid ORCHESTRATOR_MAX_SESSIONS value: %s", env_val)
    return int(getattr(settings, "orchestrator_max_sessions", _ORCHESTRATOR_MAX_SESSIONS_DEFAULT))


def _cleanup_orchestrator(session_key: str, orchestrator: AgenticOrchestrator) -> None:
    """Attempt best-effort cleanup of an orchestrator instance before eviction."""
    try:
        for name in ("shutdown", "close", "stop"):
            fn = getattr(orchestrator, name, None)
            if callable(fn):
                try:
                    res = fn()
                except TypeError:
                    # Some APIs may require arguments; skip those.
                    continue
                if asyncio.iscoroutine(res):
                    try:
                        asyncio.create_task(res)
                    except RuntimeError:
                        # No running loop; best-effort only.
                        pass
                break
    except Exception as exc:  # pragma: no cover - best-effort cleanup
        logger.warning("Failed to cleanup orchestrator for session=%s: %s", session_key, exc)


def _evict_if_needed() -> None:
    """Evict least-recently-used orchestrators when cache exceeds configured size."""
    max_size = _get_max_orchestrators()
    while len(_orchestrators_by_session) >= max_size:
        old_key, old_orch = _orchestrators_by_session.popitem(last=False)
        logger.info(
            "Evicting orchestrator for session %s due to cache size limit (%d)",
            old_key,
            max_size,
        )
        _cleanup_orchestrator(old_key, old_orch)


def remove_orchestrator(session_id: str) -> None:
    """Remove and cleanup an orchestrator for a session (call when session ends)."""
    orch = _orchestrators_by_session.pop(session_id, None)
    if orch:
        _cleanup_orchestrator(session_id, orch)


def _load_agents_config() -> Dict[str, Any]:
    """Load and cache `configs/agents.yaml` from the backend root."""
    global _agents_config_cache
    if _agents_config_cache is not None:
        return _agents_config_cache

    config_path = Path(__file__).resolve().parents[2] / "configs" / "agents.yaml"
    if not config_path.exists():
        logger.warning("Missing agents config at %s. Falling back to defaults.", config_path)
        _agents_config_cache = {}
        return _agents_config_cache

    try:
        with config_path.open("r", encoding="utf-8") as stream:
            _agents_config_cache = yaml.safe_load(stream) or {}
    except Exception as exc:
        logger.warning("Failed to load agents config %s: %s", config_path, exc)
        _agents_config_cache = {}

    return _agents_config_cache


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
    cfg = _load_agents_config()

    empathy_cfg = cfg.get("empathy", {}).get("particle_filter", {})
    strategy_cfg = cfg.get("strategy", {}).get("q_learning", {})
    academic_prior = cfg.get("academic", {}).get("bayesian", {}).get("prior_weights")

    return {
        "academic": BayesianTracker(prior=academic_prior) if academic_prior else BayesianTracker(),
        "empathy": ParticleFilter(config=empathy_cfg),
        "strategy": QLearningAgent(config=strategy_cfg),
    }


def get_orchestrator(session_id: Optional[str] = None) -> AgenticOrchestrator:
    session_key = session_id or "default"
    if session_key in _orchestrators_by_session:
        # mark as recently used
        try:
            _orchestrators_by_session.move_to_end(session_key)
        except Exception:
            pass
        return _orchestrators_by_session[session_key]

    # Evict oldest entries if we're at capacity before creating a new orchestrator
    _evict_if_needed()

    state_mgr, llm = _build_shared_dependencies()
    orchestrator = AgenticOrchestrator(
        agents=_build_session_agents(),
        state_mgr=state_mgr,
        llm=llm,
    )
    _orchestrators_by_session[session_key] = orchestrator
    return orchestrator
