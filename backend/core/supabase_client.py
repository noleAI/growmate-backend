import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable, Dict, Optional, TypeVar

from supabase import Client, create_client

from core.config import get_settings

logger = logging.getLogger("core.supabase_client")
_client: Optional[Client] = None
T = TypeVar("T")


def get_supabase_client(access_token: str | None = None) -> Client:
    # Initialize the client. In a real environment, this would handle
    # connection pooling or instantiation carefully.
    if access_token:
        token = access_token.strip()
        if token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1].strip()

        settings = get_settings()
        client = create_client(settings.supabase_url, settings.supabase_key)
        client.postgrest.auth(token)
        return client

    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


async def _run_with_retry(
    operation_name: str,
    func: Callable[[], T],
    retries: int = 2,
    timeout_sec: float = 2.0,
) -> T:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(asyncio.to_thread(func), timeout=timeout_sec)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= retries:
                break
            backoff_sec = min(0.1 * (2**attempt), 1.0)
            logger.warning(
                "Supabase operation '%s' failed on attempt %d/%d: %s",
                operation_name,
                attempt + 1,
                retries + 1,
                exc,
            )
            await asyncio.sleep(backoff_sec)

    if last_error is not None:
        logger.error(
            "Supabase operation '%s' failed after %d attempts",
            operation_name,
            retries + 1,
        )
        raise last_error

    raise RuntimeError(f"Supabase operation '{operation_name}' failed unexpectedly")


async def insert_learning_session(
    session_id: str,
    student_id: str,
    status: str = "active",
    access_token: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "id": session_id,
        "student_id": student_id,
        "status": status,
    }

    def _insert():
        return (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .insert(payload)
            .execute()
        )

    response = await _run_with_retry("insert_learning_session", _insert)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }


async def update_learning_session(
    session_id: str,
    student_id: str,
    status: str,
    end_time: str | None = None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "status": status,
        "end_time": end_time,
    }

    def _update():
        return (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .update(payload)
            .eq("id", session_id)
            .eq("student_id", student_id)
            .execute()
        )

    response = await _run_with_retry("update_learning_session", _update)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }


async def update_learning_session_progress(
    session_id: str,
    student_id: str,
    last_question_index: int,
    total_questions: int,
    progress_percent: int,
    last_interaction_at: datetime | str | None,
    state_snapshot: Dict[str, Any] | None = None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    safe_total_questions = max(1, int(total_questions or 1))
    safe_last_question_index = max(0, int(last_question_index or 0))
    safe_progress_percent = max(0, min(100, int(progress_percent or 0)))
    if safe_last_question_index > safe_total_questions:
        safe_last_question_index = safe_total_questions

    interaction_dt = _parse_optional_datetime(last_interaction_at)
    payload = {
        "last_question_index": safe_last_question_index,
        "total_questions": safe_total_questions,
        "progress_percent": safe_progress_percent,
        "last_interaction_at": (
            interaction_dt.astimezone(UTC).isoformat() if interaction_dt else None
        ),
        "state_snapshot": state_snapshot if isinstance(state_snapshot, dict) else {},
        "updated_at": datetime.now(UTC).isoformat(),
    }

    def _update():
        return (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .update(payload)
            .eq("id", session_id)
            .eq("student_id", student_id)
            .execute()
        )

    response = await _run_with_retry("update_learning_session_progress", _update)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }


async def get_latest_active_learning_session(
    student_id: str,
    access_token: str | None = None,
) -> Dict[str, Any] | None:
    def _select_full():
        return (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .select(
                "id,student_id,start_time,end_time,status,last_question_index,total_questions,progress_percent,last_interaction_at,state_snapshot"
            )
            .eq("student_id", student_id)
            .eq("status", "active")
            .order("last_interaction_at", desc=True)
            .order("start_time", desc=True)
            .limit(1)
            .execute()
        )

    def _select_basic():
        return (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .select("id,student_id,start_time,end_time,status")
            .eq("student_id", student_id)
            .eq("status", "active")
            .order("start_time", desc=True)
            .limit(1)
            .execute()
        )

    try:
        response = await _run_with_retry(
            "get_latest_active_learning_session",
            _select_full,
        )
    except Exception:
        response = await _run_with_retry(
            "get_latest_active_learning_session_basic",
            _select_basic,
        )

    rows = getattr(response, "data", []) or []
    if rows and isinstance(rows[0], dict):
        return rows[0]

    return None


async def get_learning_session_by_id(
    session_id: str,
    student_id: str | None = None,
    access_token: str | None = None,
) -> Dict[str, Any] | None:
    def _select_full():
        query = (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .select(
                "id,student_id,start_time,end_time,status,last_question_index,total_questions,progress_percent,last_interaction_at,state_snapshot"
            )
            .eq("id", session_id)
        )
        if student_id:
            query = query.eq("student_id", student_id)
        return query.limit(1).execute()

    def _select_basic():
        query = (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .select("id,student_id,start_time,end_time,status")
            .eq("id", session_id)
        )
        if student_id:
            query = query.eq("student_id", student_id)
        return query.limit(1).execute()

    try:
        response = await _run_with_retry("get_learning_session_by_id", _select_full)
    except Exception:
        response = await _run_with_retry(
            "get_learning_session_by_id_basic",
            _select_basic,
        )

    rows = getattr(response, "data", []) or []
    if rows and isinstance(rows[0], dict):
        return rows[0]

    return None


async def list_learning_sessions(
    student_id: str,
    statuses: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    access_token: str | None = None,
) -> list[Dict[str, Any]]:
    normalized_statuses = [
        str(value).strip().lower() for value in (statuses or []) if str(value).strip()
    ]

    def _select():
        query = (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .select(
                "id,student_id,start_time,end_time,status,last_question_index,total_questions,progress_percent,last_interaction_at,state_snapshot"
            )
            .eq("student_id", student_id)
            .order("start_time", desc=True)
            .range(max(0, int(offset or 0)), max(0, int(offset or 0)) + max(1, int(limit or 1)) - 1)
        )
        if normalized_statuses:
            query = query.in_("status", normalized_statuses)
        return query.execute()

    response = await _run_with_retry("list_learning_sessions", _select, timeout_sec=5.0)
    rows = getattr(response, "data", []) or []
    return [row for row in rows if isinstance(row, dict)]


async def insert_quiz_question_attempt(
    student_id: str,
    session_id: str,
    question_template_id: str,
    question_type: str,
    user_answer: Dict[str, Any],
    evaluation: Dict[str, Any],
    score: float,
    max_score: float,
    is_correct: bool,
    submitted_at: datetime | str | None = None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    submitted_dt = _parse_optional_datetime(submitted_at) or datetime.now(UTC)
    payload = {
        "student_id": student_id,
        "session_id": session_id,
        "question_template_id": question_template_id,
        "question_type": question_type,
        "user_answer": user_answer if isinstance(user_answer, dict) else {},
        "evaluation": evaluation if isinstance(evaluation, dict) else {},
        "score": float(score),
        "max_score": float(max(0.0, max_score)),
        "is_correct": bool(is_correct),
        "submitted_at": submitted_dt.astimezone(UTC).isoformat(),
    }

    def _insert():
        return (
            get_supabase_client(access_token)
            .table("quiz_question_attempts")
            .insert(payload)
            .execute()
        )

    response = await _run_with_retry("insert_quiz_question_attempt", _insert)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }


async def list_quiz_question_attempts(
    session_id: str,
    student_id: str,
    limit: int = 100,
    access_token: str | None = None,
) -> list[Dict[str, Any]]:
    safe_limit = max(1, int(limit or 1))

    def _select():
        return (
            get_supabase_client(access_token)
            .table("quiz_question_attempts")
            .select(
                "id,student_id,session_id,question_template_id,question_type,user_answer,evaluation,score,max_score,is_correct,submitted_at"
            )
            .eq("session_id", session_id)
            .eq("student_id", student_id)
            .order("submitted_at", desc=False)
            .limit(safe_limit)
            .execute()
        )

    response = await _run_with_retry("list_quiz_question_attempts", _select, timeout_sec=5.0)
    rows = getattr(response, "data", []) or []
    return [row for row in rows if isinstance(row, dict)]


async def list_learning_session_ids(
    student_id: str,
    limit: int = 30,
    access_token: str | None = None,
) -> list[str]:
    def _select():
        return (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .select("id")
            .eq("student_id", student_id)
            .limit(max(1, int(limit)))
            .execute()
        )

    response = await _run_with_retry("list_learning_session_ids", _select)
    rows = getattr(response, "data", []) or []

    result: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        session_id = str(row.get("id", "")).strip()
        if session_id:
            result.append(session_id)

    return result


async def count_daily_learning_sessions(
    student_id: str,
    usage_date: date,
    access_token: str | None = None,
) -> int:
    day_start = datetime.combine(usage_date, datetime.min.time(), tzinfo=UTC)
    next_day = day_start + timedelta(days=1)

    def _count():
        return (
            get_supabase_client(access_token)
            .table("learning_sessions")
            .select("id", count="exact")
            .eq("student_id", student_id)
            .gte("start_time", day_start.isoformat())
            .lt("start_time", next_day.isoformat())
            .limit(1)
            .execute()
        )

    response = await _run_with_retry("count_daily_learning_sessions", _count)
    count = getattr(response, "count", None)
    return int(count or 0)


async def list_agent_state_rows(
    session_ids: list[str],
    access_token: str | None = None,
) -> list[Dict[str, Any]]:
    normalized_ids = [str(value).strip() for value in session_ids if str(value).strip()]
    if not normalized_ids:
        return []

    def _select():
        return (
            get_supabase_client(access_token)
            .table("agent_state")
            .select("session_id,belief_dist,updated_at")
            .in_("session_id", normalized_ids)
            .limit(max(1, len(normalized_ids) * 3))
            .execute()
        )

    response = await _run_with_retry("list_agent_state_rows", _select, timeout_sec=5.0)
    rows = getattr(response, "data", []) or []
    return [row for row in rows if isinstance(row, dict)]


async def insert_episodic_memory(
    student_id: str,
    session_id: str,
    state: Dict[str, Any],
    action: str,
    outcome: Dict[str, Any],
    reward: float,
) -> Dict[str, Any]:
    payload = {
        "student_id": student_id,
        "session_id": session_id,
        "state": state,
        "action": action,
        "outcome": outcome,
        "reward": float(reward),
    }

    def _insert():
        return get_supabase_client().table("episodic_memory").insert(payload).execute()

    response = await _run_with_retry("insert_episodic_memory", _insert)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }


async def upsert_q_table_entry(
    student_id: str,
    state_discretized: str,
    action: str,
    q_value: float,
    visit_count: int,
) -> Dict[str, Any]:
    payload = {
        "student_id": student_id,
        "state_discretized": state_discretized,
        "action": action,
        "q_value": float(q_value),
        "visit_count": int(max(0, visit_count)),
        "updated_at": datetime.now(UTC).isoformat(),
    }

    def _upsert():
        return (
            get_supabase_client()
            .table("q_table")
            .upsert(payload, on_conflict="student_id,state_discretized,action")
            .execute()
        )

    response = await _run_with_retry("upsert_q_table_entry", _upsert)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }


async def get_user_token_usage(
    user_id: str,
    usage_date: date,
    access_token: str | None = None,
) -> Dict[str, Any]:
    date_value = usage_date.isoformat()

    def _select():
        return (
            get_supabase_client(access_token)
            .table("user_token_usage")
            .select("user_id,date,call_count,total_tokens")
            .eq("user_id", user_id)
            .eq("date", date_value)
            .limit(1)
            .execute()
        )

    response = await _run_with_retry("get_user_token_usage", _select)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return rows[0]

    return {
        "user_id": user_id,
        "date": date_value,
        "call_count": 0,
        "total_tokens": 0,
    }


async def increment_user_token_usage(
    user_id: str,
    tokens_used: int,
    usage_date: date,
    access_token: str | None = None,
) -> Dict[str, Any]:
    current = await get_user_token_usage(
        user_id=user_id,
        usage_date=usage_date,
        access_token=access_token,
    )

    next_call_count = int(current.get("call_count", 0)) + 1
    next_total_tokens = int(current.get("total_tokens", 0)) + int(max(tokens_used, 0))

    payload = {
        "user_id": user_id,
        "date": usage_date.isoformat(),
        "call_count": next_call_count,
        "total_tokens": next_total_tokens,
    }

    def _upsert():
        return (
            get_supabase_client(access_token)
            .table("user_token_usage")
            .upsert(payload, on_conflict="user_id,date")
            .execute()
        )

    response = await _run_with_retry("increment_user_token_usage", _upsert)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return rows[0]

    return payload


async def get_user_xp(
    user_id: str,
    access_token: str | None = None,
) -> Dict[str, Any]:
    def _select():
        return (
            get_supabase_client(access_token)
            .table("user_xp")
            .select(
                "user_id,weekly_xp,total_xp,current_streak,longest_streak,last_active_date,updated_at"
            )
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

    response = await _run_with_retry("get_user_xp", _select)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return rows[0]

    return {
        "user_id": user_id,
        "weekly_xp": 0,
        "total_xp": 0,
        "current_streak": 0,
        "longest_streak": 0,
        "last_active_date": None,
        "updated_at": None,
    }


async def upsert_user_xp(
    user_id: str,
    weekly_xp: int,
    total_xp: int,
    current_streak: int,
    longest_streak: int,
    last_active_date: date | None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "weekly_xp": int(max(0, weekly_xp)),
        "total_xp": int(max(0, total_xp)),
        "current_streak": int(max(0, current_streak)),
        "longest_streak": int(max(0, longest_streak)),
        "last_active_date": last_active_date.isoformat() if last_active_date else None,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    def _upsert():
        return (
            get_supabase_client(access_token)
            .table("user_xp")
            .upsert(payload, on_conflict="user_id")
            .execute()
        )

    response = await _run_with_retry("upsert_user_xp", _upsert)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return rows[0]

    return payload


def _apply_leaderboard_order(query: Any, period: str):
    if period in {"all_time", "monthly"}:
        return query.order("total_xp", desc=True).order("weekly_xp", desc=True)

    return query.order("weekly_xp", desc=True).order("total_xp", desc=True)


async def list_user_xp_rows(
    period: str,
    limit: int,
    access_token: str | None = None,
) -> list[Dict[str, Any]]:
    def _select():
        query = (
            get_supabase_client(access_token)
            .table("user_xp")
            .select("user_id,weekly_xp,total_xp,current_streak,longest_streak,updated_at")
            .limit(max(1, int(limit)))
        )
        return _apply_leaderboard_order(query, period).execute()

    response = await _run_with_retry("list_user_xp_rows", _select)
    rows = getattr(response, "data", []) or []
    return [row for row in rows if isinstance(row, dict)]


async def list_all_user_xp_rows(
    period: str,
    access_token: str | None = None,
) -> list[Dict[str, Any]]:
    def _select():
        query = get_supabase_client(access_token).table("user_xp").select(
            "user_id,weekly_xp,total_xp,current_streak,longest_streak,updated_at"
        )
        return _apply_leaderboard_order(query, period).execute()

    response = await _run_with_retry("list_all_user_xp_rows", _select, timeout_sec=5.0)
    rows = getattr(response, "data", []) or []
    return [row for row in rows if isinstance(row, dict)]


async def count_user_xp_rows(access_token: str | None = None) -> int:
    def _count():
        return (
            get_supabase_client(access_token)
            .table("user_xp")
            .select("user_id", count="exact")
            .limit(1)
            .execute()
        )

    response = await _run_with_retry("count_user_xp_rows", _count)
    count = getattr(response, "count", None)
    return int(count or 0)


async def list_user_badges(
    user_id: str,
    access_token: str | None = None,
) -> list[Dict[str, Any]]:
    def _select():
        return (
            get_supabase_client(access_token)
            .table("user_badges")
            .select("id,user_id,badge_type,badge_name,earned_at")
            .eq("user_id", user_id)
            .order("earned_at", desc=True)
            .execute()
        )

    response = await _run_with_retry("list_user_badges", _select)
    rows = getattr(response, "data", []) or []
    return [row for row in rows if isinstance(row, dict)]


async def get_user_badge_by_type(
    user_id: str,
    badge_type: str,
    access_token: str | None = None,
) -> Dict[str, Any] | None:
    def _select():
        return (
            get_supabase_client(access_token)
            .table("user_badges")
            .select("id,user_id,badge_type,badge_name,earned_at")
            .eq("user_id", user_id)
            .eq("badge_type", badge_type)
            .limit(1)
            .execute()
        )

    response = await _run_with_retry("get_user_badge_by_type", _select)
    rows = getattr(response, "data", []) or []
    if rows and isinstance(rows[0], dict):
        return rows[0]
    return None


async def create_user_badge(
    user_id: str,
    badge_type: str,
    badge_name: str,
    access_token: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "badge_type": badge_type,
        "badge_name": badge_name,
    }

    def _insert():
        return (
            get_supabase_client(access_token)
            .table("user_badges")
            .insert(payload)
            .execute()
        )

    response = await _run_with_retry("create_user_badge", _insert)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return rows[0]

    return payload


async def get_user_lives(
    user_id: str,
    access_token: str | None = None,
) -> Dict[str, Any]:
    def _select():
        return (
            get_supabase_client(access_token)
            .table("user_lives")
            .select("user_id,current_lives,last_life_lost_at,last_regen_at,updated_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

    response = await _run_with_retry("get_user_lives", _select)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return rows[0]

    return {
        "user_id": user_id,
        "current_lives": 3,
        "last_life_lost_at": None,
        "last_regen_at": None,
        "updated_at": None,
    }


async def upsert_user_lives(
    user_id: str,
    current_lives: int,
    last_life_lost_at: datetime | None,
    last_regen_at: datetime | None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "current_lives": int(max(0, min(3, current_lives))),
        "last_life_lost_at": (
            last_life_lost_at.astimezone(UTC).isoformat() if last_life_lost_at else None
        ),
        "last_regen_at": (
            last_regen_at.astimezone(UTC).isoformat() if last_regen_at else None
        ),
        "updated_at": datetime.now(UTC).isoformat(),
    }

    def _upsert():
        return (
            get_supabase_client(access_token)
            .table("user_lives")
            .upsert(payload, on_conflict="user_id")
            .execute()
        )

    response = await _run_with_retry("upsert_user_lives", _upsert)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return rows[0]

    return payload


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    return None


def _default_user_profile(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "display_name": None,
        "avatar_url": None,
        "user_level": "beginner",
        "study_goal": None,
        "daily_minutes": 15,
        "onboarded_at": None,
        "created_at": None,
        "updated_at": None,
    }


async def list_user_profiles_by_ids(
    user_ids: list[str],
    access_token: str | None = None,
) -> Dict[str, Dict[str, Any]]:
    normalized_ids = list({str(value).strip() for value in user_ids if str(value).strip()})
    if not normalized_ids:
        return {}

    def _select():
        return (
            get_supabase_client(access_token)
            .table("user_profiles")
            .select("user_id,display_name,avatar_url")
            .in_("user_id", normalized_ids)
            .execute()
        )

    response = await _run_with_retry(
        "list_user_profiles_by_ids",
        _select,
        timeout_sec=5.0,
    )
    rows = getattr(response, "data", []) or []

    profiles: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        profile_user_id = str(row.get("user_id", "")).strip()
        if not profile_user_id:
            continue
        profiles[profile_user_id] = {
            "user_id": profile_user_id,
            "display_name": row.get("display_name"),
            "avatar_url": row.get("avatar_url"),
        }

    return profiles


async def get_user_profile(
    user_id: str,
    access_token: str | None = None,
) -> Dict[str, Any]:
    def _select():
        return (
            get_supabase_client(access_token)
            .table("user_profiles")
            .select(
                "user_id,display_name,avatar_url,user_level,study_goal,daily_minutes,onboarded_at,created_at,updated_at"
            )
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

    response = await _run_with_retry("get_user_profile", _select)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        row = rows[0]
        return {
            **_default_user_profile(user_id),
            **row,
            "daily_minutes": int(row.get("daily_minutes", 15) or 15),
            "user_level": str(row.get("user_level") or "beginner"),
        }

    return _default_user_profile(user_id)


async def upsert_user_profile(
    user_id: str,
    display_name: str | None,
    avatar_url: str | None,
    user_level: str,
    study_goal: str | None,
    daily_minutes: int,
    onboarded_at: datetime | str | None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    onboarded_dt = _parse_optional_datetime(onboarded_at)
    payload = {
        "user_id": user_id,
        "display_name": str(display_name).strip() if display_name else None,
        "avatar_url": str(avatar_url).strip() if avatar_url else None,
        "user_level": str(user_level or "beginner").strip().lower(),
        "study_goal": str(study_goal).strip().lower() if study_goal else None,
        "daily_minutes": int(max(5, min(180, daily_minutes))),
        "onboarded_at": (
            onboarded_dt.astimezone(UTC).isoformat() if onboarded_dt else None
        ),
        "updated_at": datetime.now(UTC).isoformat(),
    }

    def _upsert():
        return (
            get_supabase_client(access_token)
            .table("user_profiles")
            .upsert(payload, on_conflict="user_id")
            .execute()
        )

    response = await _run_with_retry("upsert_user_profile", _upsert)
    rows = getattr(response, "data", []) or []

    if rows and isinstance(rows[0], dict):
        return {
            **_default_user_profile(user_id),
            **rows[0],
            "daily_minutes": int(rows[0].get("daily_minutes", 15) or 15),
            "user_level": str(rows[0].get("user_level") or "beginner"),
        }

    return {
        **_default_user_profile(user_id),
        **payload,
    }


async def list_recent_episodic_memory(
    session_id: str,
    limit: int = 5,
    student_id: str | None = None,
    access_token: str | None = None,
) -> list[Dict[str, Any]]:
    safe_limit = max(1, int(limit or 1))
    normalized_student_id = str(student_id or "").strip()

    def _select():
        query = (
            get_supabase_client(access_token)
            .table("episodic_memory")
            .select("id,student_id,session_id,state,action,outcome,reward,created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(safe_limit)
        )
        if normalized_student_id:
            query = query.eq("student_id", normalized_student_id)
        return query.execute()

    response = await _run_with_retry("list_recent_episodic_memory", _select)
    rows = getattr(response, "data", []) or []
    return [row for row in rows if isinstance(row, dict)]


async def insert_reasoning_trace(
    session_id: str,
    step: int,
    reasoning_mode: str,
    tools_called: list[Dict[str, Any]],
    reasoning_text: str,
    final_action: str,
    confidence: float,
    latency_ms: int,
    fallback_used: bool = False,
    student_id: str | None = None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "session_id": session_id,
        "student_id": student_id,
        "step": int(step),
        "reasoning_mode": reasoning_mode,
        "tools_called": tools_called,
        "reasoning_text": reasoning_text,
        "final_action": final_action,
        "confidence": float(confidence),
        "latency_ms": int(latency_ms),
        "fallback_used": bool(fallback_used),
    }

    def _insert():
        return (
            get_supabase_client(access_token)
            .table("reasoning_traces")
            .insert(payload)
            .execute()
        )

    response = await _run_with_retry("insert_reasoning_trace", _insert)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }


async def insert_reflection(
    session_id: str,
    step: int,
    reflection: Dict[str, Any],
    student_id: str | None = None,
    access_token: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "session_id": session_id,
        "student_id": student_id,
        "step": int(step),
        "effectiveness": reflection.get("effectiveness"),
        "entropy_trend": reflection.get("entropy_trend"),
        "accuracy_trend": reflection.get("accuracy_trend"),
        "emotion_trend": reflection.get("emotion_trend"),
        "should_change": bool(reflection.get("should_change_strategy", False)),
        "recommendation": reflection.get("recommendation"),
        "priority_action": reflection.get("priority_action"),
        "reasoning": reflection.get("reasoning"),
    }

    def _insert():
        return (
            get_supabase_client(access_token)
            .table("session_reflections")
            .insert(payload)
            .execute()
        )

    response = await _run_with_retry("insert_reflection", _insert)
    return {
        "data": getattr(response, "data", []),
        "count": getattr(response, "count", None),
    }
