from typing import Any, Dict, Optional

import numpy as np


def compute_reward(
    signals: Dict[str, Any],
    academic_outcome: Dict[str, Any],
    pf_state: Dict[str, Any],
    xp_data: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
) -> float:
    """Compute bounded reward in [-1, 1] from performance, engagement, and fatigue."""
    reward = 0.0
    effective_mode = str(mode or signals.get("mode", "normal")).lower()

    if academic_outcome.get("is_correct"):
        reward += 1.0
        if float(academic_outcome.get("confidence_delta", 0.0)) > 0.1:
            reward += 0.5

    response_time_ms = float(signals.get("response_time_ms", 10000))
    if 2000 < response_time_ms < 15000:
        reward += 0.2
    elif response_time_ms > 20000 and effective_mode != "explore":
        reward -= 0.3

    if effective_mode == "exam_prep":
        if response_time_ms <= 7000:
            reward += 0.1
        elif response_time_ms > 18000:
            reward -= 0.2
    elif effective_mode == "explore":
        if bool(signals.get("hint_used", False)):
            reward += 0.2
        if response_time_ms > 30000:
            reward -= 0.05

    fatigue = float(pf_state.get("fatigue", 0.0))
    if fatigue > 0.7:
        reward -= 0.4
    elif fatigue < 0.3:
        reward += 0.1

    if int(academic_outcome.get("streak_no_improvement", 0)) >= 3:
        reward -= 0.5

    # Optional XP signals for gamification-aware reward shaping.
    if xp_data:
        recent_xp_gain = float(xp_data.get("recent_xp_gain", 0.0))
        if recent_xp_gain > 50.0:
            reward += 0.2

        streak_days = int(xp_data.get("streak_days", 0))
        if streak_days >= 3:
            reward += 0.1

        daily_xp_rate = float(xp_data.get("daily_xp_rate", 0.0))
        previous_daily_xp_rate = float(xp_data.get("prev_daily_xp_rate", 0.0))
        if previous_daily_xp_rate > 0 and daily_xp_rate < (previous_daily_xp_rate * 0.8):
            reward -= 0.2

    bounded = float(np.clip(reward, -1.0, 1.0))
    return round(bounded, 2)
