from typing import Any, Dict, Optional


def format_belief_distribution(raw_beliefs: dict) -> list[dict]:
    """
    Transforms the raw belief dict from the Bayesian Tracker
    into a structured list for the dashboard API.
    """
    return [{"concept": k, "probability": v} for k, v in raw_beliefs.items()]


def format_particle_state(particles: list) -> dict:
    """
    Aggregates particle filter data into a summary.
    """
    return {
        "particle_count": len(particles),
        "mean_state": sum(particles) / len(particles) if particles else 0,
    }


def format_pf_payload(pf_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "component": "empathy_agent",
        "estimation": {
            "confusion": round(float(pf_state.get("confusion", 0.0)), 3),
            "fatigue": round(float(pf_state.get("fatigue", 0.0)), 3),
            "uncertainty": round(float(pf_state.get("uncertainty", 1.0)), 3),
        },
        "particle_cloud": pf_state.get("particle_cloud", []),
        "weights": pf_state.get("weights", []),
        "ess": round(float(pf_state.get("ess", 0.0)), 1),
        "step": int(pf_state.get("step", 0)),
        "q_state": pf_state.get("q_state", ""),
        "belief_distribution": pf_state.get("belief_distribution", {}),
        "particle_distribution": pf_state.get("particle_distribution", []),
        "eu_values": pf_state.get("eu_values", {}),
        "recommended_action": pf_state.get("recommended_action", ""),
        "hitl_triggered": bool(pf_state.get("hitl_triggered", False)),
    }


def format_dashboard_payload(
    state,
    final_action: str,
    final_action_payload: dict,
    orchestrator_decision: Optional[Dict[str, Any]] = None,
    reasoning_mode: Optional[str] = None,
    reasoning_trace: Optional[list[Dict[str, Any]]] = None,
    reasoning_content: Optional[str] = None,
    reasoning_confidence: Optional[float] = None,
) -> dict:
    """
    Formats the complete dashboard update payload emitted via websockets.
    """
    empathy_state = state.empathy_state
    if {
        "confusion",
        "fatigue",
        "uncertainty",
        "ess",
        "particle_cloud",
        "weights",
    }.issubset(empathy_state.keys()):
        empathy_state = format_pf_payload(empathy_state)

    payload = {
        "session_id": state.session_id,
        "step": state.step,
        "action": final_action,
        "action_payload": final_action_payload,
        "hitl_pending": state.hitl_pending,
        "pause_state": bool(getattr(state, "pause_state", False)),
        "pause_reason": getattr(state, "pause_reason", None),
        "off_topic_counter": int(getattr(state, "off_topic_counter", 0)),
        "academic": state.academic_state,
        "empathy": empathy_state,
        "strategy": state.strategy_state,
    }

    if orchestrator_decision:
        payload["orchestrator"] = {
            "component": "orchestrator",
            "decision": {
                "action": orchestrator_decision.get("action", ""),
                "action_distribution": orchestrator_decision.get(
                    "action_distribution", {}
                ),
                "total_uncertainty": orchestrator_decision.get(
                    "total_uncertainty", 0.0
                ),
                "hitl_triggered": bool(
                    orchestrator_decision.get("hitl_triggered", False)
                ),
                "rationale": orchestrator_decision.get("rationale", ""),
            },
            "monitoring": orchestrator_decision.get("monitoring", {}),
        }

    if reasoning_mode:
        payload["reasoning_mode"] = reasoning_mode
    if reasoning_trace is not None:
        payload["reasoning_trace"] = reasoning_trace
    if reasoning_content:
        payload["reasoning_content"] = reasoning_content
    if reasoning_confidence is not None:
        payload["reasoning_confidence"] = float(reasoning_confidence)

    return payload
