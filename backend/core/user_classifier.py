from enum import Enum
from typing import Any, Dict


class UserLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


def classify(onboarding_results: Dict[str, Any]) -> UserLevel:
    correct = float(onboarding_results.get("correct", 0))
    total = float(onboarding_results.get("total", 0))
    avg_response_time_ms = float(onboarding_results.get("avg_response_time_ms", 0))

    if total <= 0:
        return UserLevel.INTERMEDIATE

    accuracy = correct / total

    # Primary split by accuracy.
    if accuracy < 0.4:
        level = UserLevel.BEGINNER
    elif accuracy > 0.7:
        level = UserLevel.ADVANCED
    else:
        level = UserLevel.INTERMEDIATE

    # Secondary speed adjustment around boundaries.
    if level == UserLevel.INTERMEDIATE:
        if accuracy >= 0.65 and 0 < avg_response_time_ms <= 6000:
            return UserLevel.ADVANCED
        if accuracy <= 0.45 and avg_response_time_ms >= 12000:
            return UserLevel.BEGINNER

    return level


def get_study_plan(level: UserLevel) -> Dict[str, Any]:
    plans: Dict[UserLevel, Dict[str, Any]] = {
        UserLevel.BEGINNER: {
            "daily_minutes": 20,
            "difficulty": "easy",
            "starting_hypothesis": "H01_Trig",
            "hint_policy": "proactive",
        },
        UserLevel.INTERMEDIATE: {
            "daily_minutes": 25,
            "difficulty": "mixed",
            "starting_hypothesis": "H04_Rules",
            "hint_policy": "adaptive",
        },
        UserLevel.ADVANCED: {
            "daily_minutes": 30,
            "difficulty": "medium_hard",
            "starting_hypothesis": "H03_Chain",
            "hint_policy": "on_demand",
        },
    }
    return plans[level]
