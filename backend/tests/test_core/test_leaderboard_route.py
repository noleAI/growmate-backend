from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from api.routes import leaderboard as leaderboard_route


def test_require_user_id_rejects_missing_sub() -> None:
    with pytest.raises(HTTPException) as exc_info:
        leaderboard_route._require_user_id({})

    assert exc_info.value.status_code == 401


def test_normalize_period_rejects_invalid_value() -> None:
    with pytest.raises(HTTPException) as exc_info:
        leaderboard_route._normalize_period("yearly")

    assert exc_info.value.status_code == 400


def test_resolve_badge_meta_for_mastery_topic() -> None:
    result = leaderboard_route._resolve_badge_meta("mastery_linear_algebra")

    assert result["badge_type"] == "mastery_linear_algebra"
    assert "Linear Algebra" in str(result["badge_name"])
    assert result["description"] is not None
    assert result["icon"] is not None


@pytest.mark.asyncio
async def test_get_leaderboard_returns_ranked_rows(monkeypatch) -> None:
    async def _rows_stub(**kwargs) -> list[dict]:
        assert kwargs["period"] == "weekly"
        return [
            {
                "user_id": "u1",
                "weekly_xp": 120,
                "total_xp": 400,
                "current_streak": 2,
                "longest_streak": 4,
            },
            {
                "user_id": "u2",
                "weekly_xp": 90,
                "total_xp": 380,
                "current_streak": 1,
                "longest_streak": 2,
            },
        ]

    async def _count_stub(**kwargs) -> int:
        del kwargs
        return 2

    async def _badges_stub(**kwargs) -> list[dict]:
        del kwargs
        return []

    async def _profiles_stub(**kwargs) -> dict:
        del kwargs
        return {
            "u1": {"display_name": "User 1", "avatar_url": None},
            "u2": {"display_name": "User 2", "avatar_url": None},
        }

    monkeypatch.setattr(leaderboard_route, "list_user_xp_rows", _rows_stub)
    monkeypatch.setattr(leaderboard_route, "count_user_xp_rows", _count_stub)
    monkeypatch.setattr(leaderboard_route, "list_user_badges", _badges_stub)
    monkeypatch.setattr(leaderboard_route, "list_user_profiles_by_ids", _profiles_stub)

    result = await leaderboard_route.get_leaderboard(
        period="weekly",
        limit=20,
        _user={"sub": "u1"},
        access_token="token",
    )

    assert result["period"] == "weekly"
    assert result["total_players"] == 2
    assert len(result["leaderboard"]) == 2
    assert result["leaderboard"][0]["rank"] == 1
    assert result["leaderboard"][0]["xp"] == 120
    assert result["leaderboard"][0]["display_name"] == "User 1"


@pytest.mark.asyncio
async def test_get_leaderboard_falls_back_when_profile_lookup_fails(monkeypatch) -> None:
    async def _rows_stub(**kwargs) -> list[dict]:
        del kwargs
        return [
            {
                "user_id": "u1",
                "weekly_xp": 120,
                "total_xp": 400,
                "current_streak": 2,
                "longest_streak": 4,
            }
        ]

    async def _count_stub(**kwargs) -> int:
        del kwargs
        return 1

    async def _badges_stub(**kwargs) -> list[dict]:
        del kwargs
        return []

    async def _profiles_stub(**kwargs) -> dict:
        del kwargs
        raise RuntimeError("profiles unavailable")

    monkeypatch.setattr(leaderboard_route, "list_user_xp_rows", _rows_stub)
    monkeypatch.setattr(leaderboard_route, "count_user_xp_rows", _count_stub)
    monkeypatch.setattr(leaderboard_route, "list_user_badges", _badges_stub)
    monkeypatch.setattr(leaderboard_route, "list_user_profiles_by_ids", _profiles_stub)

    result = await leaderboard_route.get_leaderboard(
        period="weekly",
        limit=20,
        _user={"sub": "u1"},
        access_token="token",
    )

    assert result["leaderboard"][0]["display_name"] is None
    assert result["leaderboard"][0]["avatar_url"] is None


@pytest.mark.asyncio
async def test_get_leaderboard_wraps_data_error(monkeypatch) -> None:
    async def _rows_stub(**kwargs) -> list[dict]:
        del kwargs
        raise RuntimeError("db down")

    monkeypatch.setattr(leaderboard_route, "list_user_xp_rows", _rows_stub)

    with pytest.raises(HTTPException) as exc_info:
        await leaderboard_route.get_leaderboard(
            period="weekly",
            limit=20,
            _user={"sub": "u1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 500
    assert "Failed to load leaderboard" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_my_rank_returns_fallback_when_not_ranked(monkeypatch) -> None:
    async def _all_rows_stub(**kwargs) -> list[dict]:
        del kwargs
        return [
            {
                "user_id": "u1",
                "weekly_xp": 100,
                "total_xp": 500,
                "current_streak": 3,
                "longest_streak": 5,
            }
        ]

    async def _badges_stub(**kwargs) -> list[dict]:
        del kwargs
        return [{"badge_type": "streak_7"}]

    async def _xp_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "missing-user"
        return {
            "user_id": "missing-user",
            "weekly_xp": 0,
            "total_xp": 0,
            "current_streak": 0,
            "longest_streak": 0,
        }

    async def _profile_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "missing-user"
        return {
            "display_name": "Missing User",
            "avatar_url": None,
        }

    monkeypatch.setattr(leaderboard_route, "list_all_user_xp_rows", _all_rows_stub)
    monkeypatch.setattr(leaderboard_route, "list_user_badges", _badges_stub)
    monkeypatch.setattr(leaderboard_route, "get_user_xp", _xp_stub)
    monkeypatch.setattr(leaderboard_route, "get_user_profile", _profile_stub)

    result = await leaderboard_route.get_my_rank(
        period="weekly",
        user={"sub": "missing-user"},
        access_token="token",
    )

    assert result["rank"] is None
    assert result["weekly_xp"] == 0
    assert result["badge_count"] == 1
    assert result["display_name"] == "Missing User"


@pytest.mark.asyncio
async def test_get_my_rank_uses_ranked_row_and_profile_fallback(monkeypatch) -> None:
    async def _all_rows_stub(**kwargs) -> list[dict]:
        del kwargs
        return [
            {
                "user_id": "ranked-user",
                "weekly_xp": 140,
                "total_xp": 540,
                "current_streak": 4,
                "longest_streak": 7,
            }
        ]

    async def _badges_stub(**kwargs) -> list[dict]:
        del kwargs
        return []

    async def _should_not_call_get_user_xp(**kwargs) -> dict:
        del kwargs
        raise AssertionError("get_user_xp should not be used when rank exists")

    async def _profile_stub(**kwargs) -> dict:
        del kwargs
        raise RuntimeError("profile unavailable")

    monkeypatch.setattr(leaderboard_route, "list_all_user_xp_rows", _all_rows_stub)
    monkeypatch.setattr(leaderboard_route, "list_user_badges", _badges_stub)
    monkeypatch.setattr(leaderboard_route, "get_user_xp", _should_not_call_get_user_xp)
    monkeypatch.setattr(leaderboard_route, "get_user_profile", _profile_stub)

    result = await leaderboard_route.get_my_rank(
        period="weekly",
        user={"sub": "ranked-user"},
        access_token="token",
    )

    assert result["rank"] == 1
    assert result["weekly_xp"] == 140
    assert result["display_name"] is None
    assert result["avatar_url"] is None


@pytest.mark.asyncio
async def test_add_xp_updates_totals_and_awards_badges(monkeypatch) -> None:
    today = date.today()

    async def _get_user_xp_stub(**kwargs) -> dict:
        del kwargs
        return {
            "user_id": "student-1",
            "weekly_xp": 100,
            "total_xp": 1000,
            "current_streak": 6,
            "longest_streak": 6,
            "last_active_date": (today - timedelta(days=1)).isoformat(),
        }

    async def _upsert_user_xp_stub(**kwargs) -> dict:
        return {
            "user_id": kwargs["user_id"],
            "weekly_xp": kwargs["weekly_xp"],
            "total_xp": kwargs["total_xp"],
            "current_streak": kwargs["current_streak"],
            "longest_streak": kwargs["longest_streak"],
        }

    async def _all_rows_stub(**kwargs) -> list[dict]:
        del kwargs
        return [
            {"user_id": "u-top-1", "weekly_xp": 999, "total_xp": 9999},
            {"user_id": "u-top-2", "weekly_xp": 800, "total_xp": 9000},
            {"user_id": "student-1", "weekly_xp": 120, "total_xp": 1020},
        ]

    async def _existing_badge_stub(**kwargs):
        del kwargs
        return None

    async def _create_badge_stub(**kwargs) -> dict:
        return {
            "badge_type": kwargs["badge_type"],
            "badge_name": kwargs["badge_name"],
            "earned_at": "2026-04-15T10:00:00Z",
        }

    monkeypatch.setattr(leaderboard_route, "get_user_xp", _get_user_xp_stub)
    monkeypatch.setattr(leaderboard_route, "upsert_user_xp", _upsert_user_xp_stub)
    monkeypatch.setattr(leaderboard_route, "list_all_user_xp_rows", _all_rows_stub)
    monkeypatch.setattr(leaderboard_route, "get_user_badge_by_type", _existing_badge_stub)
    monkeypatch.setattr(leaderboard_route, "create_user_badge", _create_badge_stub)

    result = await leaderboard_route.add_xp(
        request=leaderboard_route.XpAddRequest(event_type="daily_login", extra_data={}),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["xp_added"] == 20
    assert result["weekly_xp"] == 120
    assert result["total_xp"] == 1020
    assert result["current_streak"] == 7
    badge_types = {item["badge_type"] for item in result["new_badges"]}
    assert "streak_7" in badge_types
    assert "top_10_weekly" in badge_types


@pytest.mark.asyncio
async def test_add_xp_rejects_unsupported_event(monkeypatch) -> None:
    async def _get_user_xp_stub(**kwargs) -> dict:
        del kwargs
        return {
            "user_id": "student-1",
            "weekly_xp": 0,
            "total_xp": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "last_active_date": None,
        }

    monkeypatch.setattr(leaderboard_route, "get_user_xp", _get_user_xp_stub)

    with pytest.raises(HTTPException) as exc_info:
        await leaderboard_route.add_xp(
            request=leaderboard_route.XpAddRequest(
                event_type="invalid_event",
                extra_data={},
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_add_xp_returns_zero_for_duplicate_daily_login(monkeypatch) -> None:
    today = leaderboard_route.datetime.now(leaderboard_route.VN_TZ).date()

    async def _get_user_xp_stub(**kwargs) -> dict:
        del kwargs
        return {
            "user_id": "student-1",
            "weekly_xp": 33,
            "total_xp": 333,
            "current_streak": 5,
            "longest_streak": 9,
            "last_active_date": today.isoformat(),
        }

    monkeypatch.setattr(leaderboard_route, "get_user_xp", _get_user_xp_stub)

    result = await leaderboard_route.add_xp(
        request=leaderboard_route.XpAddRequest(event_type="daily_login", extra_data={}),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["xp_added"] == 0
    assert result["weekly_xp"] == 33
    assert result["total_xp"] == 333
    assert result["new_badges"] == []


@pytest.mark.asyncio
async def test_get_badges_returns_rows(monkeypatch) -> None:
    async def _badges_stub(**kwargs) -> list[dict]:
        assert kwargs["user_id"] == "student-1"
        return [
            {
                "badge_type": "streak_7",
                "badge_name": "Kien tri",
                "earned_at": "2026-04-15T10:00:00Z",
            }
        ]

    monkeypatch.setattr(leaderboard_route, "list_user_badges", _badges_stub)

    result = await leaderboard_route.get_badges(
        user={"sub": "student-1"},
        access_token="token",
    )

    assert len(result["badges"]) == 1
    assert result["badges"][0]["badge_type"] == "streak_7"
    assert result["badges"][0]["description"] is not None
    assert len(result["available"]) >= 1


@pytest.mark.asyncio
async def test_get_badges_wraps_data_error(monkeypatch) -> None:
    async def _badges_stub(**kwargs) -> list[dict]:
        del kwargs
        raise RuntimeError("query failed")

    monkeypatch.setattr(leaderboard_route, "list_user_badges", _badges_stub)

    with pytest.raises(HTTPException) as exc_info:
        await leaderboard_route.get_badges(
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 500
    assert "Failed to load badges" in str(exc_info.value.detail)
