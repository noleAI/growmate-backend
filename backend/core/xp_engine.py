from __future__ import annotations

from datetime import date, timedelta
from typing import Any

XP_RULES = {
    "correct_answer": 10,
    "streak_bonus": 5,
    "speed_bonus": 3,
    "daily_login": 20,
    "complete_quiz": 50,
    "perfect_score": 100,
}

VALID_XP_EVENTS = {
    "correct_answer",
    "daily_login",
    "complete_quiz",
    "perfect_score",
}


def parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def calculate_xp(
    event_type: str,
    extra_data: dict[str, Any] | None = None,
) -> dict[str, int]:
    event = str(event_type or "").strip().lower()
    if event not in VALID_XP_EVENTS:
        raise ValueError(f"Unsupported event_type: {event_type}")

    payload = extra_data if isinstance(extra_data, dict) else {}
    base_xp = XP_RULES[event]

    streak_bonus = 0
    speed_bonus = 0

    if event == "correct_answer":
        consecutive_correct = int(payload.get("consecutive_correct", 0) or 0)
        if consecutive_correct >= 2:
            streak_bonus = XP_RULES["streak_bonus"]

        time_taken_sec = payload.get("time_taken_sec")
        if time_taken_sec is None:
            time_taken_sec = payload.get("time_taken")
        if time_taken_sec is not None:
            try:
                if float(time_taken_sec) < 10:
                    speed_bonus = XP_RULES["speed_bonus"]
            except (TypeError, ValueError):
                speed_bonus = 0

    total_xp = base_xp + streak_bonus + speed_bonus

    return {
        "base_xp": int(base_xp),
        "streak_bonus": int(streak_bonus),
        "speed_bonus": int(speed_bonus),
        "total_xp": int(total_xp),
    }


def resolve_streak_update(
    current_streak: int,
    longest_streak: int,
    last_active_date: date | None,
    today: date,
    event_type: str,
) -> dict[str, Any]:
    current = max(0, int(current_streak or 0))
    longest = max(0, int(longest_streak or 0))
    event = str(event_type or "").strip().lower()

    # Daily streak is updated only on the daily_login event.
    if event != "daily_login":
        next_last_active = today if last_active_date is None else last_active_date
        return {
            "current_streak": current,
            "longest_streak": longest,
            "last_active_date": next_last_active,
        }

    if last_active_date is None:
        current = 1
    elif last_active_date == today:
        current = max(1, current)
    elif last_active_date == today - timedelta(days=1):
        current = max(1, current) + 1
    else:
        current = 1

    longest = max(longest, current)

    return {
        "current_streak": current,
        "longest_streak": longest,
        "last_active_date": today,
    }


def evaluate_badge_candidates(
    current_streak: int,
    weekly_rank: int | None,
    mastery_topics: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []

    if int(current_streak or 0) >= 7:
        badges.append(
            {
                "badge_type": "streak_7",
                "badge_name": "Kiên trì",
            }
        )

    if weekly_rank is not None and int(weekly_rank) <= 10:
        badges.append(
            {
                "badge_type": "top_10_weekly",
                "badge_name": "Siêu sao tuần",
            }
        )

    if isinstance(mastery_topics, dict):
        for topic_key, value in mastery_topics.items():
            try:
                mastery_percent = float(value)
            except (TypeError, ValueError):
                continue

            if mastery_percent < 100:
                continue

            normalized = str(topic_key or "").strip().lower()
            label = normalized.replace("_", " ").title() or "Topic"
            badges.append(
                {
                    "badge_type": f"mastery_{normalized}",
                    "badge_name": f"Chiến thần {label}",
                }
            )

    return badges
