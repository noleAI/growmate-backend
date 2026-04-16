from datetime import date, timedelta

import pytest

from core import xp_engine


def test_calculate_xp_with_streak_and_speed_bonus() -> None:
    result = xp_engine.calculate_xp(
        event_type="correct_answer",
        extra_data={"consecutive_correct": 3, "time_taken_sec": 7},
    )

    assert result["base_xp"] == 10
    assert result["streak_bonus"] == 5
    assert result["speed_bonus"] == 3
    assert result["total_xp"] == 18


def test_calculate_xp_rejects_unsupported_event() -> None:
    with pytest.raises(ValueError):
        xp_engine.calculate_xp(event_type="unknown", extra_data={})


def test_resolve_streak_update_increments_on_consecutive_day() -> None:
    today = date.today()
    state = xp_engine.resolve_streak_update(
        current_streak=4,
        longest_streak=6,
        last_active_date=today - timedelta(days=1),
        today=today,
        event_type="daily_login",
    )

    assert state["current_streak"] == 5
    assert state["longest_streak"] == 6
    assert state["last_active_date"] == today


def test_evaluate_badge_candidates_returns_expected_types() -> None:
    candidates = xp_engine.evaluate_badge_candidates(
        current_streak=7,
        weekly_rank=3,
        mastery_topics={"chain_rule": 100},
    )

    badge_types = {badge["badge_type"] for badge in candidates}
    assert "streak_7" in badge_types
    assert "top_10_weekly" in badge_types
    assert "mastery_chain_rule" in badge_types
