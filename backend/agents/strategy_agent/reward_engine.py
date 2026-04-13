from typing import Any, Dict

import numpy as np


def compute_reward(
    signals: Dict[str, Any], academic_outcome: Dict[str, Any], pf_state: Dict[str, Any]
) -> float:
    """Compute bounded reward in [-1, 1] from performance, engagement, and fatigue."""
    reward = 0.0

    if academic_outcome.get("is_correct"):
        reward += 1.0
        if float(academic_outcome.get("confidence_delta", 0.0)) > 0.1:
            reward += 0.5

    response_time_ms = float(signals.get("response_time_ms", 10000))
    if 2000 < response_time_ms < 15000:
        reward += 0.2
    elif response_time_ms > 20000:
        reward -= 0.3

    fatigue = float(pf_state.get("fatigue", 0.0))
    if fatigue > 0.7:
        reward -= 0.4
    elif fatigue < 0.3:
        reward += 0.1

    if int(academic_outcome.get("streak_no_improvement", 0)) >= 3:
        reward -= 0.5

    bounded = float(np.clip(reward, -1.0, 1.0))
    return round(bounded, 2)
