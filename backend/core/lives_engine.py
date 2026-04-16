from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

from core.supabase_client import get_user_lives, upsert_user_lives

MAX_LIVES = 3
REGEN_HOURS = 8
REGEN_INTERVAL = timedelta(hours=REGEN_HOURS)


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def _clamp_lives(value: Any) -> int:
    return max(0, min(MAX_LIVES, int(value or 0)))


def _build_status(
    current_lives: int,
    next_regen_at: datetime | None,
    next_regen_in_seconds: int,
) -> dict[str, Any]:
    return {
        "current": current_lives,
        "max": MAX_LIVES,
        "can_play": current_lives > 0,
        "next_regen_in_seconds": max(0, int(next_regen_in_seconds or 0)),
        "next_regen_at": next_regen_at.isoformat() if next_regen_at else None,
    }


def _calculate_regeneration(
    current_lives: int,
    last_life_lost_at: datetime | None,
    last_regen_at: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    current = _clamp_lives(current_lives)

    if current >= MAX_LIVES:
        return {
            "current": MAX_LIVES,
            "regen_applied": 0,
            "last_regen_at": last_regen_at,
            "next_regen_at": None,
            "next_regen_in_seconds": 0,
        }

    anchor = last_regen_at or last_life_lost_at or now
    if anchor > now:
        anchor = now

    elapsed_seconds = (now - anchor).total_seconds()
    regen_steps = int(elapsed_seconds // REGEN_INTERVAL.total_seconds())

    if regen_steps <= 0:
        next_regen_at = anchor + REGEN_INTERVAL
        next_regen_in_seconds = max(1, ceil((next_regen_at - now).total_seconds()))
        return {
            "current": current,
            "regen_applied": 0,
            "last_regen_at": last_regen_at,
            "next_regen_at": next_regen_at,
            "next_regen_in_seconds": next_regen_in_seconds,
        }

    next_current = min(MAX_LIVES, current + regen_steps)
    regen_applied = next_current - current
    updated_last_regen = anchor + REGEN_INTERVAL * regen_applied

    if next_current >= MAX_LIVES:
        next_regen_at = None
        next_regen_in_seconds = 0
    else:
        next_regen_at = updated_last_regen + REGEN_INTERVAL
        next_regen_in_seconds = max(1, ceil((next_regen_at - now).total_seconds()))

    return {
        "current": next_current,
        "regen_applied": regen_applied,
        "last_regen_at": updated_last_regen,
        "next_regen_at": next_regen_at,
        "next_regen_in_seconds": next_regen_in_seconds,
    }


async def check_regen(
    user_id: str,
    access_token: str | None = None,
) -> dict[str, Any]:
    row = await get_user_lives(user_id=user_id, access_token=access_token)

    now = datetime.now(UTC)
    current_lives = _clamp_lives(row.get("current_lives", MAX_LIVES))
    last_life_lost_at = parse_iso_datetime(row.get("last_life_lost_at"))
    last_regen_at = parse_iso_datetime(row.get("last_regen_at"))

    regen_state = _calculate_regeneration(
        current_lives=current_lives,
        last_life_lost_at=last_life_lost_at,
        last_regen_at=last_regen_at,
        now=now,
    )

    missing_row = row.get("updated_at") is None
    if missing_row or regen_state["regen_applied"] > 0:
        await upsert_user_lives(
            user_id=user_id,
            current_lives=regen_state["current"],
            last_life_lost_at=last_life_lost_at,
            last_regen_at=regen_state["last_regen_at"],
            access_token=access_token,
        )

    return _build_status(
        current_lives=regen_state["current"],
        next_regen_at=regen_state["next_regen_at"],
        next_regen_in_seconds=regen_state["next_regen_in_seconds"],
    )


async def can_play(
    user_id: str,
    access_token: str | None = None,
) -> bool:
    status = await check_regen(user_id=user_id, access_token=access_token)
    return bool(status["can_play"])


async def lose_life(
    user_id: str,
    access_token: str | None = None,
) -> dict[str, Any]:
    status = await check_regen(user_id=user_id, access_token=access_token)
    if status["current"] <= 0:
        return status

    now = datetime.now(UTC)
    remaining = max(0, int(status["current"]) - 1)

    await upsert_user_lives(
        user_id=user_id,
        current_lives=remaining,
        last_life_lost_at=now,
        last_regen_at=now,
        access_token=access_token,
    )

    return await check_regen(user_id=user_id, access_token=access_token)


async def regen_life(
    user_id: str,
    access_token: str | None = None,
) -> dict[str, Any]:
    status = await check_regen(user_id=user_id, access_token=access_token)
    if status["current"] >= MAX_LIVES:
        return status

    now = datetime.now(UTC)
    regenerated = min(MAX_LIVES, int(status["current"]) + 1)

    await upsert_user_lives(
        user_id=user_id,
        current_lives=regenerated,
        last_life_lost_at=now,
        last_regen_at=now,
        access_token=access_token,
    )

    return await check_regen(user_id=user_id, access_token=access_token)
