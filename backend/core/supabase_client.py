import asyncio
import logging
from datetime import UTC, datetime
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
    print(f"Inserting learning session with payload: {payload}")

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
