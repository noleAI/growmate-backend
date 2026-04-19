from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.security import get_bearer_token, get_current_user
from core.supabase_client import (
    count_user_xp_rows,
    create_user_badge,
    get_user_badge_by_type,
    get_user_profile,
    get_user_xp,
    list_all_user_xp_rows,
    list_user_badges,
    list_user_profiles_by_ids,
    list_user_xp_rows,
    upsert_user_xp,
)
from core.xp_engine import (
    calculate_xp,
    evaluate_badge_candidates,
    parse_iso_date,
    resolve_streak_update,
)

router = APIRouter()

VN_TZ = timezone(timedelta(hours=7))
ALLOWED_PERIODS = {"weekly", "monthly", "all_time"}

BADGE_CATALOG: dict[str, dict[str, str]] = {
    "streak_7": {
        "badge_name": "Kiên trì",
        "description": "Học 7 ngày liên tiếp.",
        "icon": "🔥",
    },
    "top_10_weekly": {
        "badge_name": "Siêu sao tuần",
        "description": "Lọt Top 10 bảng xếp hạng tuần.",
        "icon": "⭐",
    },
}


class XpAddRequest(BaseModel):
    event_type: str
    extra_data: dict[str, Any] = Field(default_factory=dict)


def _require_user_id(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )
    return user_id


def _normalize_period(period: str) -> str:
    normalized = str(period or "weekly").strip().lower()
    if normalized not in ALLOWED_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid period. Allowed values: weekly, monthly, all_time",
        )
    return normalized


def _as_int(value: Any) -> int:
    return int(value or 0)


def _resolve_rank(ranked_rows: list[dict[str, Any]], user_id: str) -> int | None:
    for index, row in enumerate(ranked_rows, start=1):
        if str(row.get("user_id", "")) == user_id:
            return index
    return None


def _format_leaderboard_row(
    row: dict[str, Any],
    rank: int,
    period: str,
    badge_count: int,
    display_name: str | None = None,
    avatar_url: str | None = None,
) -> dict[str, Any]:
    weekly_xp = _as_int(row.get("weekly_xp"))
    total_xp = _as_int(row.get("total_xp"))
    ranking_xp = total_xp if period in {"all_time", "monthly"} else weekly_xp

    return {
        "rank": rank,
        "user_id": str(row.get("user_id", "")),
        "display_name": display_name,
        "avatar_url": avatar_url,
        "xp": ranking_xp,
        "streak": _as_int(row.get("current_streak")),
        "badge_count": badge_count,
        "weekly_xp": weekly_xp,
        "total_xp": total_xp,
        "current_streak": _as_int(row.get("current_streak")),
        "longest_streak": _as_int(row.get("longest_streak")),
    }


def _resolve_badge_meta(
    badge_type: str,
    fallback_name: str | None = None,
) -> dict[str, str | None]:
    normalized_badge_type = str(badge_type or "").strip().lower()
    catalog = BADGE_CATALOG.get(normalized_badge_type)
    if catalog:
        return {
            "badge_type": normalized_badge_type,
            "badge_name": str(fallback_name or catalog["badge_name"]),
            "description": catalog["description"],
            "icon": catalog["icon"],
        }

    if normalized_badge_type.startswith("mastery_"):
        topic_key = normalized_badge_type.removeprefix("mastery_").strip()
        topic_label = topic_key.replace("_", " ").strip()
        topic_title = topic_label.title() if topic_label else "Chủ đề"
        return {
            "badge_type": normalized_badge_type,
            "badge_name": str(fallback_name or f"Chiến thần {topic_title}"),
            "description": f"Đạt 100% mastery cho {topic_label or 'chủ đề này'}.",
            "icon": "🏆",
        }

    return {
        "badge_type": normalized_badge_type,
        "badge_name": str(fallback_name or normalized_badge_type),
        "description": None,
        "icon": None,
    }


def _build_available_badges(earned_types: set[str]) -> list[dict[str, Any]]:
    available: list[dict[str, Any]] = []
    for badge_type in sorted(BADGE_CATALOG.keys()):
        if badge_type in earned_types:
            continue
        meta = _resolve_badge_meta(badge_type)
        available.append(
            {
                "badge_type": meta["badge_type"],
                "badge_name": meta["badge_name"],
                "description": meta["description"],
                "icon": meta["icon"],
            }
        )
    return available


@router.get("/leaderboard")
async def get_leaderboard(
    period: str = Query(default="weekly"),
    limit: int = Query(default=20, ge=1, le=100),
    _user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    normalized_period = _normalize_period(period)

    try:
        rows = await list_user_xp_rows(
            period=normalized_period,
            limit=limit,
            access_token=access_token,
        )
        total_players = await count_user_xp_rows(access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load leaderboard: {exc}",
        ) from exc

    badge_lists = await asyncio.gather(
        *[
            list_user_badges(
                user_id=str(row.get("user_id", "")),
                access_token=access_token,
            )
            for row in rows
        ]
    )

    user_ids = [str(row.get("user_id", "")).strip() for row in rows]
    try:
        profiles_by_id = await list_user_profiles_by_ids(
            user_ids=user_ids,
            access_token=access_token,
        )
    except Exception:
        profiles_by_id = {}

    leaderboard = [
        _format_leaderboard_row(
            row=row,
            rank=index,
            period=normalized_period,
            badge_count=len(badge_lists[index - 1]),
            display_name=(
                profiles_by_id.get(str(row.get("user_id", "")), {}).get("display_name")
            ),
            avatar_url=(
                profiles_by_id.get(str(row.get("user_id", "")), {}).get("avatar_url")
            ),
        )
        for index, row in enumerate(rows, start=1)
    ]

    return {
        "period": normalized_period,
        "total_players": total_players,
        "leaderboard": leaderboard,
    }


@router.get("/leaderboard/me")
async def get_my_rank(
    period: str = Query(default="weekly"),
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    normalized_period = _normalize_period(period)
    user_id = _require_user_id(user)

    try:
        ranked_rows = await list_all_user_xp_rows(
            period=normalized_period,
        )
        badges = await list_user_badges(
            user_id=user_id,
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load user rank: {exc}",
        ) from exc

    rank = _resolve_rank(ranked_rows, user_id)
    profile_row = None
    if rank is not None:
        profile_row = ranked_rows[rank - 1]
    else:
        profile_row = await get_user_xp(user_id=user_id, access_token=access_token)

    try:
        user_profile = await get_user_profile(user_id=user_id, access_token=access_token)
    except Exception:
        user_profile = {"display_name": None, "avatar_url": None}

    return {
        "period": normalized_period,
        "rank": rank,
        "user_id": user_id,
        "display_name": user_profile.get("display_name"),
        "avatar_url": user_profile.get("avatar_url"),
        "weekly_xp": _as_int(profile_row.get("weekly_xp")),
        "total_xp": _as_int(profile_row.get("total_xp")),
        "current_streak": _as_int(profile_row.get("current_streak")),
        "longest_streak": _as_int(profile_row.get("longest_streak")),
        "badge_count": len(badges),
    }


@router.post("/xp/add")
async def add_xp(
    request: XpAddRequest,
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)
    today = datetime.now(VN_TZ).date()
    event_type = str(request.event_type or "").strip().lower()

    try:
        current = await get_user_xp(user_id=user_id, access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load current xp: {exc}",
        ) from exc

    last_active = parse_iso_date(current.get("last_active_date"))
    if event_type == "daily_login" and last_active == today:
        return {
            "xp_added": 0,
            "breakdown": {
                "base_xp": 0,
                "streak_bonus": 0,
                "speed_bonus": 0,
                "total_xp": 0,
            },
            "weekly_xp": _as_int(current.get("weekly_xp")),
            "total_xp": _as_int(current.get("total_xp")),
            "current_streak": _as_int(current.get("current_streak")),
            "new_badges": [],
        }

    try:
        xp_breakdown = calculate_xp(event_type, request.extra_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        current_streak = _as_int(current.get("current_streak"))
        longest_streak = _as_int(current.get("longest_streak"))

        streak_state = resolve_streak_update(
            current_streak=current_streak,
            longest_streak=longest_streak,
            last_active_date=last_active,
            today=today,
            event_type=event_type,
        )

        next_weekly_xp = _as_int(current.get("weekly_xp")) + xp_breakdown["total_xp"]
        next_total_xp = _as_int(current.get("total_xp")) + xp_breakdown["total_xp"]

        persisted = await upsert_user_xp(
            user_id=user_id,
            weekly_xp=next_weekly_xp,
            total_xp=next_total_xp,
            current_streak=_as_int(streak_state.get("current_streak")),
            longest_streak=_as_int(streak_state.get("longest_streak")),
            last_active_date=streak_state.get("last_active_date"),
            access_token=access_token,
        )

        ranked_rows = await list_all_user_xp_rows(
            period="weekly",
            access_token=access_token,
        )
        weekly_rank = _resolve_rank(ranked_rows, user_id)

        mastery_topics = request.extra_data.get("mastery_topics")
        if not isinstance(mastery_topics, dict):
            mastery_topics = None

        candidates = evaluate_badge_candidates(
            current_streak=_as_int(persisted.get("current_streak")),
            weekly_rank=weekly_rank,
            mastery_topics=mastery_topics,
        )

        new_badges: list[dict[str, Any]] = []
        for candidate in candidates:
            badge_type = candidate["badge_type"]
            existing = await get_user_badge_by_type(
                user_id=user_id,
                badge_type=badge_type,
                access_token=access_token,
            )
            if existing:
                continue

            created = await create_user_badge(
                user_id=user_id,
                badge_type=badge_type,
                badge_name=candidate["badge_name"],
                access_token=access_token,
            )
            resolved_badge_type = str(created.get("badge_type", badge_type))
            resolved_badge_name = str(
                created.get("badge_name", candidate["badge_name"])
            )
            badge_meta = _resolve_badge_meta(
                badge_type=resolved_badge_type,
                fallback_name=resolved_badge_name,
            )
            new_badges.append(
                {
                    "badge_type": badge_meta["badge_type"],
                    "badge_name": badge_meta["badge_name"],
                    "description": badge_meta["description"],
                    "icon": badge_meta["icon"],
                    "earned_at": created.get("earned_at"),
                }
            )

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add xp: {exc}",
        ) from exc

    return {
        "xp_added": xp_breakdown["total_xp"],
        "breakdown": xp_breakdown,
        "weekly_xp": _as_int(persisted.get("weekly_xp")),
        "total_xp": _as_int(persisted.get("total_xp")),
        "current_streak": _as_int(persisted.get("current_streak")),
        "new_badges": new_badges,
    }


@router.get("/badges")
async def get_badges(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)

    try:
        badges = await list_user_badges(user_id=user_id, access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load badges: {exc}",
        ) from exc

    earned = [
        {
            **_resolve_badge_meta(
                badge_type=str(row.get("badge_type", "")),
                fallback_name=str(row.get("badge_name", "")),
            ),
            "earned_at": row.get("earned_at"),
        }
        for row in badges
    ]

    earned_types = {
        str(item.get("badge_type", "")).strip().lower() for item in earned if item.get("badge_type")
    }
    available = _build_available_badges(earned_types=earned_types)

    return {
        "earned": earned,
        "available": available,
        "badges": earned,
    }
