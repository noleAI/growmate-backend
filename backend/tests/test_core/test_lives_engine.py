from datetime import UTC, datetime, timedelta

import pytest

from core import lives_engine


@pytest.mark.asyncio
async def test_check_regen_initializes_default_row(monkeypatch) -> None:
    captured: dict = {}

    async def _get_lives_stub(**kwargs) -> dict:
        del kwargs
        return {
            "user_id": "student-1",
            "current_lives": 3,
            "last_life_lost_at": None,
            "last_regen_at": None,
            "updated_at": None,
        }

    async def _upsert_stub(**kwargs) -> dict:
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(lives_engine, "get_user_lives", _get_lives_stub)
    monkeypatch.setattr(lives_engine, "upsert_user_lives", _upsert_stub)

    status = await lives_engine.check_regen(user_id="student-1", access_token="token")

    assert status["current"] == 3
    assert status["max"] == 3
    assert status["can_play"] is True
    assert status["next_regen_in_seconds"] == 0
    assert captured["current_lives"] == 3


@pytest.mark.asyncio
async def test_check_regen_applies_hourly_regen(monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 16, 9, 0, 0, tzinfo=UTC)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz else fixed_now.replace(tzinfo=None)

    captured: dict = {}

    async def _get_lives_stub(**kwargs) -> dict:
        del kwargs
        return {
            "user_id": "student-1",
            "current_lives": 1,
            "last_life_lost_at": (fixed_now - timedelta(hours=12)).isoformat(),
            "last_regen_at": (fixed_now - timedelta(hours=9)).isoformat(),
            "updated_at": "2026-04-15T00:00:00+00:00",
        }

    async def _upsert_stub(**kwargs) -> dict:
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(lives_engine, "datetime", _FixedDateTime)
    monkeypatch.setattr(lives_engine, "get_user_lives", _get_lives_stub)
    monkeypatch.setattr(lives_engine, "upsert_user_lives", _upsert_stub)

    status = await lives_engine.check_regen(user_id="student-1", access_token="token")

    assert status["current"] == 2
    assert status["can_play"] is True
    assert 25190 <= status["next_regen_in_seconds"] <= 25210
    assert captured["current_lives"] == 2


@pytest.mark.asyncio
async def test_lose_life_decrements_remaining(monkeypatch) -> None:
    state = {
        "user_id": "student-1",
        "current_lives": 2,
        "last_life_lost_at": None,
        "last_regen_at": None,
        "updated_at": "2026-04-15T00:00:00+00:00",
    }

    async def _get_lives_stub(**kwargs) -> dict:
        del kwargs
        return dict(state)

    async def _upsert_stub(**kwargs) -> dict:
        state["current_lives"] = kwargs["current_lives"]
        state["last_life_lost_at"] = kwargs["last_life_lost_at"].isoformat()
        state["last_regen_at"] = kwargs["last_regen_at"].isoformat()
        state["updated_at"] = datetime.now(UTC).isoformat()
        return dict(state)

    monkeypatch.setattr(lives_engine, "get_user_lives", _get_lives_stub)
    monkeypatch.setattr(lives_engine, "upsert_user_lives", _upsert_stub)

    status = await lives_engine.lose_life(user_id="student-1", access_token="token")

    assert status["current"] == 1
    assert status["can_play"] is True
    assert status["next_regen_in_seconds"] > 0


@pytest.mark.asyncio
async def test_can_play_returns_false_when_empty(monkeypatch) -> None:
    async def _get_lives_stub(**kwargs) -> dict:
        del kwargs
        return {
            "user_id": "student-1",
            "current_lives": 0,
            "last_life_lost_at": datetime.now(UTC).isoformat(),
            "last_regen_at": datetime.now(UTC).isoformat(),
            "updated_at": "2026-04-15T00:00:00+00:00",
        }

    async def _upsert_stub(**kwargs) -> dict:
        return kwargs

    monkeypatch.setattr(lives_engine, "get_user_lives", _get_lives_stub)
    monkeypatch.setattr(lives_engine, "upsert_user_lives", _upsert_stub)

    result = await lives_engine.can_play(user_id="student-1", access_token="token")

    assert result is False
