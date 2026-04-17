"""Tool handlers that expose existing backend capabilities to the LLM."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.orchestrator import AgenticOrchestrator
    from core.formula_recommender import FormulaRecommender
    from core.knowledge_retriever import KnowledgeRetriever
    from core.memory_store import MemoryStore
    from core.state_manager import StateManager


_HYPOTHESIS_LABELS = {
    "H01_Trig": "Dao ham luong giac",
    "H02_ExpLog": "Dao ham ham mu va logarit",
    "H03_Chain": "Quy tac chain rule",
    "H04_Rules": "Cong thuc dao ham co ban",
}

_SEARCH_KNOWLEDGE_LIMIT = max(
    1,
    int(os.getenv("SEARCH_KNOWLEDGE_LIMIT", "5") or 5),
)
_search_knowledge_counter: dict[str, int] = {}


def _normalize_action_name(action: str) -> str:
    mapping = {
        "continue_quiz": "next_question",
        "suggest_break": "de_stress",
        "trigger_hitl": "hitl",
        "hint": "show_hint",
        "hitl_pending": "hitl",
    }
    return mapping.get(action, action)


def _topic_to_hypothesis(topic: str | None) -> str | None:
    if not topic:
        return None

    normalized = topic.lower()
    if any(word in normalized for word in ("trig", "sin", "cos", "tan", "luong giac")):
        return "H01_Trig"
    if any(word in normalized for word in ("exp", "log", "mu", "ln", "e^")):
        return "H02_ExpLog"
    if any(word in normalized for word in ("chain", "ham hop", "f(g(x))")):
        return "H03_Chain"
    if any(
        word in normalized
        for word in ("tong", "hieu", "tich", "thuong", "co ban", "rules")
    ):
        return "H04_Rules"
    return None


async def get_academic_beliefs(
    state_manager: StateManager,
    session_id: str,
) -> dict[str, Any]:
    state = await state_manager.load_or_init(session_id)
    academic = state.academic_state or {}

    beliefs = academic.get("belief_dist")
    if not isinstance(beliefs, dict):
        beliefs = {}

    entropy = float(academic.get("entropy", 1.0) or 1.0)
    confidence = float(academic.get("confidence", max(0.0, 1.0 - entropy)) or 0.0)

    if beliefs:
        top_hypothesis = max(beliefs, key=lambda key: float(beliefs.get(key, 0.0)))
        top_probability = float(beliefs.get(top_hypothesis, 0.0))
        topic_label = _HYPOTHESIS_LABELS.get(top_hypothesis, top_hypothesis)
        interpretation = (
            f"Top weakness: {topic_label} (P={top_probability:.2f}, entropy={entropy:.2f})"
        )
    else:
        top_hypothesis = "unknown"
        interpretation = "No academic belief data available for this session."

    return {
        "belief_distribution": beliefs,
        "entropy": round(entropy, 3),
        "confidence": round(confidence, 3),
        "top_hypothesis": top_hypothesis,
        "interpretation": interpretation,
    }


async def get_empathy_state(
    state_manager: StateManager,
    session_id: str,
) -> dict[str, Any]:
    state = await state_manager.load_or_init(session_id)
    empathy = state.empathy_state or {}

    confusion = float(empathy.get("confusion", 0.0) or 0.0)
    fatigue = float(empathy.get("fatigue", 0.0) or 0.0)
    uncertainty = float(
        empathy.get("uncertainty", empathy.get("uncertainty_score", 0.0)) or 0.0
    )

    status_parts: list[str] = []
    if fatigue >= 0.8:
        status_parts.append("Learner is very tired")
    elif fatigue >= 0.5:
        status_parts.append("Learner shows mild fatigue")

    if confusion >= 0.7:
        status_parts.append("Learner is very confused")
    elif confusion >= 0.3:
        status_parts.append("Learner shows mild confusion")

    if not status_parts:
        status_parts.append("Learner appears stable")

    return {
        "confusion": round(confusion, 3),
        "fatigue": round(fatigue, 3),
        "uncertainty": round(uncertainty, 3),
        "q_state": str(empathy.get("q_state", "unknown")),
        "interpretation": ". ".join(status_parts),
    }


async def get_strategy_suggestion(
    state_manager: StateManager,
    session_id: str,
) -> dict[str, Any]:
    state = await state_manager.load_or_init(session_id)
    strategy = state.strategy_state or {}

    selected_action = str(strategy.get("selected_action") or strategy.get("action") or "next_question")
    normalized_action = _normalize_action_name(selected_action)

    q_values = strategy.get("q_values", strategy.get("q_table", {}))
    if not isinstance(q_values, dict):
        q_values = {}

    epsilon = float(strategy.get("epsilon", 0.3) or 0.3)
    avg_reward = float(strategy.get("avg_reward_10", strategy.get("avg_reward", 0.0)) or 0.0)

    return {
        "recommended_action": normalized_action,
        "raw_action": selected_action,
        "q_values": q_values,
        "q_state": str(strategy.get("q_state", "unknown")),
        "epsilon": round(epsilon, 3),
        "avg_reward": round(avg_reward, 3),
        "interpretation": (
            f"Q-learning suggests {normalized_action} "
            f"(raw={selected_action}, epsilon={epsilon:.2f}, avg_reward={avg_reward:.2f})"
        ),
    }


async def get_student_history(
    memory_store: MemoryStore,
    session_id: str,
    n: int = 5,
) -> dict[str, Any]:
    episodes = await memory_store.get_recent_episodes(session_id, limit=max(1, int(n)))
    if not episodes:
        return {
            "history": [],
            "total": 0,
            "accuracy": 0.0,
            "interpretation": "No recent episodes found for this session.",
        }

    correct_count = 0
    summaries: list[str] = []
    for episode in episodes:
        outcome = episode.get("outcome", {}) if isinstance(episode, dict) else {}
        is_correct = bool(outcome.get("is_correct", outcome.get("correct", False)))
        if is_correct:
            correct_count += 1

        action = str((episode or {}).get("action", "unknown"))
        summaries.append(f"{action}:{'correct' if is_correct else 'wrong'}")

    accuracy = correct_count / len(episodes)

    return {
        "history": episodes,
        "total": len(episodes),
        "accuracy": round(accuracy, 2),
        "interpretation": (
            f"Recent accuracy={accuracy:.0%} ({correct_count}/{len(episodes)}), "
            f"latest={'; '.join(summaries[:3])}"
        ),
    }


async def get_formula_bank(
    formula_recommender: FormulaRecommender,
    hypothesis: str | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    chosen_hypothesis = hypothesis or _topic_to_hypothesis(topic)
    belief_dist: dict[str, float] = {}
    if chosen_hypothesis:
        belief_dist[chosen_hypothesis] = 0.0

    formulas = formula_recommender.recommend_formulas(
        belief_dist=belief_dist,
        threshold=0.3,
        limit=5,
    )

    return {
        "formulas": formulas,
        "count": len(formulas),
        "hypothesis": chosen_hypothesis,
        "interpretation": (
            f"Found {len(formulas)} relevant formulas"
            if formulas
            else "No formulas matched this query"
        ),
    }


async def get_orchestrator_score(
    orchestrator: AgenticOrchestrator,
    session_id: str,
) -> dict[str, Any]:
    state = await orchestrator.state_mgr.load_or_init(session_id)
    decision = orchestrator.decision_engine.run_step(
        academic_state=state.academic_state,
        empathy_state=state.empathy_state,
        memory_state=state.strategy_state,
    )

    action = _normalize_action_name(str(decision.action))

    return {
        "recommended_action": action,
        "action_distribution": decision.action_distribution,
        "total_uncertainty": round(float(decision.total_uncertainty), 3),
        "hitl_triggered": bool(decision.hitl_triggered),
        "rationale": decision.rationale,
        "interpretation": (
            f"Deterministic orchestrator suggests {action} "
            f"(uncertainty={decision.total_uncertainty:.2f}, hitl={decision.hitl_triggered})"
        ),
    }


async def search_knowledge(
    retriever: KnowledgeRetriever,
    query: str,
    top_k: int = 3,
    source: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    session_key = str(session_id or "global")
    used = _search_knowledge_counter.get(session_key, 0)
    if used >= _SEARCH_KNOWLEDGE_LIMIT:
        return {
            "chunks": [],
            "count": 0,
            "interpretation": "search_knowledge rate limit reached for this session.",
            "error": "rate_limited",
        }

    _search_knowledge_counter[session_key] = used + 1
    return await retriever.search(
        query=query,
        top_k=max(1, int(top_k)),
        source_filter=source,
    )
