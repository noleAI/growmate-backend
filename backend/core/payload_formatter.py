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
