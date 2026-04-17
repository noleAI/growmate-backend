import logging
from typing import Any, Dict, Optional

from core.supabase_client import (
    insert_episodic_memory,
    insert_reasoning_trace,
    insert_reflection,
    list_recent_episodic_memory,
    upsert_q_table_entry,
)

logger = logging.getLogger("core.memory_store")


class MemoryStore:
    def __init__(self):
        # In a real environment, this might use Redis or a cache layer syncing with Supabase
        self._store: Dict[str, Dict[str, Any]] = {}

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        return self._store.get(session_id, {})

    def save_session_state(self, session_id: str, state: Dict[str, Any]) -> None:
        self._store[session_id] = state

    async def log_episodic_memory(
        self,
        session_id: str,
        student_id: Optional[str],
        state: Dict[str, Any],
        action: str,
        outcome: Dict[str, Any],
        reward: float,
    ) -> None:
        """Asynchronously flush to the 'episodic_memory' table within Supabase"""
        if not student_id:
            logger.debug(
                "Skip episodic memory sync for session=%s because student_id is missing",
                session_id,
            )
            return

        try:
            await insert_episodic_memory(
                student_id=student_id,
                session_id=session_id,
                state=state,
                action=action,
                outcome=outcome,
                reward=reward,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Episodic memory sync failed for session=%s student_id=%s: %s",
                session_id,
                student_id,
                exc,
            )

    async def upsert_q_value(
        self,
        student_id: Optional[str],
        state_discretized: str,
        action: str,
        q_value: float,
        visit_count: int,
    ) -> None:
        """Upsert one Q-table entry asynchronously."""
        if not student_id:
            logger.debug(
                "Skip q_table sync for state=%s action=%s because student_id is missing",
                state_discretized,
                action,
            )
            return

        try:
            await upsert_q_table_entry(
                student_id=student_id,
                state_discretized=state_discretized,
                action=action,
                q_value=q_value,
                visit_count=visit_count,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "q_table sync failed for student_id=%s state=%s action=%s: %s",
                student_id,
                state_discretized,
                action,
                exc,
            )

    async def log_reasoning_trace(
        self,
        session_id: str,
        step: int,
        reasoning_mode: str,
        tools_called: list[dict[str, Any]],
        reasoning_text: str,
        final_action: str,
        confidence: float,
        latency_ms: int,
        fallback_used: bool = False,
        student_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> None:
        try:
            await insert_reasoning_trace(
                session_id=session_id,
                student_id=student_id,
                step=step,
                reasoning_mode=reasoning_mode,
                tools_called=tools_called,
                reasoning_text=reasoning_text,
                final_action=final_action,
                confidence=confidence,
                latency_ms=latency_ms,
                fallback_used=fallback_used,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reasoning trace sync failed for session=%s step=%s: %s",
                session_id,
                step,
                exc,
            )

    async def log_reflection(
        self,
        session_id: str,
        step: int,
        reflection: dict[str, Any],
        student_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> None:
        try:
            await insert_reflection(
                session_id=session_id,
                student_id=student_id,
                step=step,
                reflection=reflection,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reflection sync failed for session=%s step=%s: %s",
                session_id,
                step,
                exc,
            )

    async def get_recent_episodes(
        self,
        session_id: str,
        limit: int = 5,
        student_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        try:
            return await list_recent_episodic_memory(
                session_id=session_id,
                limit=limit,
                student_id=student_id,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load episodic history for session=%s: %s",
                session_id,
                exc,
            )
            return []


memory_store = MemoryStore()
