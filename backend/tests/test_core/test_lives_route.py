import pytest
from fastapi import HTTPException

from api.routes import lives as lives_route


@pytest.mark.asyncio
async def test_get_lives_returns_status(monkeypatch) -> None:
    async def _check_regen_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-1"
        return {
            "current": 2,
            "max": 3,
            "can_play": True,
            "next_regen_in_seconds": 14400,
            "next_regen_at": "2026-04-16T12:00:00+00:00",
        }

    monkeypatch.setattr(lives_route, "check_regen", _check_regen_stub)

    result = await lives_route.get_lives(user={"sub": "student-1"}, access_token="token")

    assert result["current"] == 2
    assert result["max"] == 3
    assert result["can_play"] is True


@pytest.mark.asyncio
async def test_consume_life_returns_remaining(monkeypatch) -> None:
    async def _lose_life_stub(**kwargs) -> dict:
        del kwargs
        return {
            "current": 1,
            "max": 3,
            "can_play": True,
            "next_regen_in_seconds": 28800,
            "next_regen_at": "2026-04-16T20:00:00+00:00",
        }

    monkeypatch.setattr(lives_route, "lose_life", _lose_life_stub)

    result = await lives_route.consume_life(
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["remaining"] == 1
    assert result["current"] == 1


@pytest.mark.asyncio
async def test_regenerate_life_returns_status(monkeypatch) -> None:
    async def _regen_life_stub(**kwargs) -> dict:
        del kwargs
        return {
            "current": 3,
            "max": 3,
            "can_play": True,
            "next_regen_in_seconds": 0,
            "next_regen_at": None,
        }

    monkeypatch.setattr(lives_route, "regen_life", _regen_life_stub)

    result = await lives_route.regenerate_life(
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["current"] == 3
    assert result["next_regen_in_seconds"] == 0


@pytest.mark.asyncio
async def test_get_lives_requires_student_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await lives_route.get_lives(user={}, access_token="token")

    assert exc_info.value.status_code == 401
