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


def format_dashboard_payload(
    state, final_action: str, final_action_payload: dict
) -> dict:
    """
    Formats the complete dashboard update payload emitted via websockets.
    """
    return {
        "session_id": state.session_id,
        "step": state.step,
        "action": final_action,
        "action_payload": final_action_payload,
        "hitl_pending": state.hitl_pending,
        "academic": state.academic_state,
        "empathy": state.empathy_state,
        "strategy": state.strategy_state,
    }
