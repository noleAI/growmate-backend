import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict

from supabase import create_client

from agents.base import SessionState
from core.supabase_client import (
    get_learning_session_by_id,
    update_learning_session_progress,
)

logger = logging.getLogger("core.state_manager")


class StateManager:
    def __init__(self, supabase_url: str, supabase_key: str, ws_manager):
        self.supabase = create_client(supabase_url, supabase_key)
        self.ws = ws_manager
        self.cache: Dict[str, SessionState] = {}
        self.sync_counter: Dict[str, int] = {}
        self.last_sync_at: Dict[str, datetime] = {}
        self.session_context: Dict[str, Dict[str, str]] = {}
        self.auto_save_interval_sec = 30
        self.idle_timeout_sec = 180
        self._autosave_tasks: Dict[str, asyncio.Task] = {}
        self._sync_locks: Dict[str, asyncio.Lock] = {}

    async def load_or_init(self, session_id: str) -> SessionState:
        if session_id in self.cache:
            logger.debug("Session state cache hit session_id=%s", session_id)
            return self.cache[session_id]

        restored = await self._load_state_from_snapshot(session_id)
        self.cache[session_id] = restored or SessionState(session_id=session_id)
        if restored is not None:
            logger.info(
                "Session state loaded source=snapshot session_id=%s step=%s last_question_index=%s progress_percent=%s",
                session_id,
                int(self.cache[session_id].step or 0),
                int(self.cache[session_id].strategy_state.get("last_question_index", 0) or 0),
                int(self.cache[session_id].strategy_state.get("progress_percent", 0) or 0),
            )
        else:
            logger.info("Session state loaded source=fresh session_id=%s", session_id)

        self.sync_counter[session_id] = 0
        self.last_sync_at[session_id] = datetime.now(UTC)

        self._start_autosave_task(session_id)
        return self.cache[session_id]

    async def _load_state_from_snapshot(self, session_id: str) -> SessionState | None:
        context = self.session_context.get(session_id, {})
        student_id = str(context.get("student_id") or "").strip() or None
        access_token = str(context.get("access_token") or "").strip() or None

        try:
            row = await get_learning_session_by_id(
                session_id=session_id,
                student_id=student_id,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to rehydrate session=%s from snapshot: %s",
                session_id,
                exc,
            )
            return None

        if not isinstance(row, dict):
            return None

        snapshot = row.get("state_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {}

        state = SessionState(session_id=session_id)

        academic_state = snapshot.get("academic_state")
        if isinstance(academic_state, dict):
            state.academic_state = academic_state

        empathy_state = snapshot.get("empathy_state")
        if isinstance(empathy_state, dict):
            state.empathy_state = empathy_state

        strategy_state = snapshot.get("strategy_state")
        if isinstance(strategy_state, dict):
            state.strategy_state = dict(strategy_state)
        else:
            state.strategy_state = {}

        persisted_total = self._safe_int(
            row.get("total_questions"),
            default=self._safe_int(state.strategy_state.get("total_questions"), default=10),
        )
        if persisted_total <= 0:
            persisted_total = 10

        persisted_index = self._safe_int(
            row.get("last_question_index"),
            default=self._safe_int(
                state.strategy_state.get("last_question_index"),
                default=self._safe_int(state.strategy_state.get("current_question_index"), default=0),
            ),
        )
        persisted_index = max(0, min(persisted_total, persisted_index))

        persisted_progress = self._safe_int(
            row.get("progress_percent"),
            default=self._safe_int(
                state.strategy_state.get("progress_percent"),
                default=int(round((persisted_index / max(1, persisted_total)) * 100)),
            ),
        )
        persisted_progress = max(0, min(100, persisted_progress))

        state.strategy_state["total_questions"] = persisted_total
        state.strategy_state["last_question_index"] = persisted_index
        state.strategy_state["progress_percent"] = persisted_progress

        restored_step = self._safe_int(snapshot.get("step"), default=persisted_index)
        state.step = max(0, max(restored_step, persisted_index))

        restored_mode = str(
            snapshot.get("mode")
            or state.strategy_state.get("mode")
            or "normal"
        ).strip()
        state.mode = restored_mode or "normal"
        state.strategy_state["mode"] = state.mode

        state.user_classification_level = str(
            snapshot.get("user_classification_level")
            or state.strategy_state.get("classification_level")
            or "intermediate"
        ).strip() or "intermediate"
        state.strategy_state["classification_level"] = state.user_classification_level

        state.pause_state = bool(snapshot.get("pause_state", False))
        pause_reason = snapshot.get("pause_reason")
        state.pause_reason = str(pause_reason).strip() if pause_reason else None
        pause_ts = snapshot.get("pause_timestamp")
        state.pause_timestamp = str(pause_ts).strip() if pause_ts else None
        state.off_topic_counter = max(
            0,
            self._safe_int(snapshot.get("off_topic_counter"), default=0),
        )
        state.hitl_pending = bool(snapshot.get("hitl_pending", False))

        signal_history = snapshot.get("signal_history")
        if isinstance(signal_history, list):
            state.signal_history = [item for item in signal_history if isinstance(item, dict)][-5:]
        last_signal_time = snapshot.get("last_signal_time")
        if last_signal_time:
            state.last_signal_time = str(last_signal_time)

        interaction_time = self._parse_datetime(
            row.get("last_interaction_at")
            or state.strategy_state.get("last_interaction_at")
        )
        state.last_interaction_timestamp = interaction_time
        if interaction_time is not None:
            state.strategy_state["last_interaction_at"] = interaction_time.isoformat()

        if student_id:
            state.strategy_state["student_id"] = student_id

        return state

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
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
            except ValueError:
                return None
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

        return None

    def register_session_context(
        self,
        session_id: str,
        student_id: str | None,
        access_token: str | None,
    ) -> None:
        context = self.session_context.setdefault(session_id, {})

        normalized_student_id = str(student_id or "").strip()
        if normalized_student_id:
            context["student_id"] = normalized_student_id

        normalized_access_token = str(access_token or "").strip()
        if normalized_access_token:
            context["access_token"] = normalized_access_token

    async def sync_to_supabase(
        self,
        session_id: str,
        state: SessionState,
        *,
        force: bool = False,
        reason: str | None = None,
    ):
        if session_id not in self.sync_counter:
            self.sync_counter[session_id] = 0

        lock = self._sync_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            self.sync_counter[session_id] += 1

            now = datetime.now(UTC)
            last_sync = self.last_sync_at.get(session_id)
            due_by_step = self.sync_counter[session_id] % 3 == 0
            due_by_interval = False
            if last_sync is None:
                due_by_interval = True
            else:
                due_by_interval = (
                    now - last_sync
                ).total_seconds() >= self.auto_save_interval_sec

            due_by_idle = self._is_idle(state, now)

            if not (force or due_by_step or due_by_interval or due_by_idle):
                return

            sync_reason = reason
            if not sync_reason:
                if due_by_idle:
                    sync_reason = "idle_timeout"
                elif force or due_by_interval:
                    sync_reason = "periodic_30s"
                else:
                    sync_reason = "step_threshold"

            await self._sync_agent_state(session_id, state)
            await self._sync_learning_session_progress(session_id, state, sync_reason)

            self.last_sync_at[session_id] = now
            if due_by_step or force or due_by_idle:
                self.sync_counter[session_id] = 0

    async def broadcast_ws(self, session_id: str, payload: Dict[str, Any]):
        await self.ws.send_to_session(session_id, json.dumps(payload))

    async def _sync_agent_state(self, session_id: str, state: SessionState) -> None:
        empathy_state = state.empathy_state
        await self._db_upsert(
            "agent_state",
            {
                "session_id": session_id,
                "belief_dist": json.dumps(state.academic_state.get("belief_dist", {})),
                "particles": json.dumps(
                    empathy_state.get("particle_cloud", empathy_state.get("particles", []))
                ),
                "weights": json.dumps(empathy_state.get("weights", [])),
                "ess": empathy_state.get("ess", 0.0),
                "uncertainty": empathy_state.get("uncertainty", 1.0),
                "confusion": empathy_state.get("confusion", 0.0),
                "fatigue": empathy_state.get("fatigue", 0.0),
                "q_state": empathy_state.get("q_state", ""),
                "belief_distribution": json.dumps(
                    empathy_state.get("belief_distribution", {})
                ),
                "particle_distribution": json.dumps(
                    empathy_state.get("particle_distribution", [])
                ),
                "eu_values": json.dumps(empathy_state.get("eu_values", {})),
                "recommended_action": empathy_state.get("recommended_action", ""),
                "hitl_triggered": bool(empathy_state.get("hitl_triggered", False)),
                "q_values": json.dumps(state.strategy_state.get("q_table", {})),
            },
        )

    async def _sync_learning_session_progress(
        self,
        session_id: str,
        state: SessionState,
        reason: str,
    ) -> None:
        context = self.session_context.get(session_id, {})
        student_id = str(context.get("student_id") or "").strip()
        if not student_id:
            student_id = str(state.strategy_state.get("student_id") or "").strip()

        if not student_id:
            return

        access_token = str(context.get("access_token") or "").strip() or None

        last_question_index, total_questions, progress_percent = self._derive_progress(state)
        last_interaction_at = state.last_interaction_timestamp

        snapshot = {
            "step": int(state.step or 0),
            "mode": str(state.mode or "normal"),
            "user_classification_level": str(
                state.user_classification_level or "intermediate"
            ),
            "pause_state": bool(state.pause_state),
            "pause_reason": state.pause_reason,
            "off_topic_counter": int(state.off_topic_counter or 0),
            "hitl_pending": bool(state.hitl_pending),
            "sync_reason": reason,
            "academic_state": state.academic_state,
            "empathy_state": state.empathy_state,
            "strategy_state": state.strategy_state,
        }

        try:
            await update_learning_session_progress(
                session_id=session_id,
                student_id=student_id,
                last_question_index=last_question_index,
                total_questions=total_questions,
                progress_percent=progress_percent,
                last_interaction_at=last_interaction_at,
                state_snapshot=snapshot,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Learning session autosave failed session_id=%s student_id=%s reason=%s error=%s",
                session_id,
                student_id,
                reason,
                exc,
            )

    def _derive_progress(self, state: SessionState) -> tuple[int, int, int]:
        strategy_state = state.strategy_state if isinstance(state.strategy_state, dict) else {}

        total_questions = int(strategy_state.get("total_questions", 10) or 10)
        if total_questions <= 0:
            total_questions = 10

        explicit_index = strategy_state.get("last_question_index")
        if explicit_index is None:
            explicit_index = strategy_state.get("current_question_index")

        if explicit_index is None:
            last_question_index = int(state.step or 0)
        else:
            last_question_index = int(explicit_index or 0)

        if last_question_index < 0:
            last_question_index = 0
        if last_question_index > total_questions:
            last_question_index = total_questions

        explicit_progress = strategy_state.get("progress_percent")
        if explicit_progress is None:
            progress_percent = int(round((last_question_index / total_questions) * 100))
        else:
            progress_percent = int(explicit_progress or 0)

        progress_percent = max(0, min(100, progress_percent))
        return last_question_index, total_questions, progress_percent

    def _start_autosave_task(self, session_id: str) -> None:
        current = self._autosave_tasks.get(session_id)
        if current and not current.done():
            return

        try:
            self._autosave_tasks[session_id] = asyncio.create_task(
                self._autosave_loop(session_id)
            )
        except RuntimeError:
            logger.debug(
                "Cannot start autosave loop for session_id=%s because no running loop",
                session_id,
            )

    async def _autosave_loop(self, session_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(self.auto_save_interval_sec)
                state = self.cache.get(session_id)
                if state is None:
                    return

                now = datetime.now(UTC)
                reason = "idle_timeout" if self._is_idle(state, now) else "periodic_30s"
                await self.sync_to_supabase(
                    session_id,
                    state,
                    force=True,
                    reason=reason,
                )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Autosave loop crashed for session_id=%s error=%s",
                session_id,
                exc,
            )

    def _is_idle(self, state: SessionState, now: datetime) -> bool:
        last_interaction = state.last_interaction_timestamp
        if last_interaction is None:
            return False

        if isinstance(last_interaction, str):
            normalized = last_interaction.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                last_dt = datetime.fromisoformat(normalized)
            except ValueError:
                return False
        elif isinstance(last_interaction, datetime):
            last_dt = last_interaction
        else:
            return False

        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)

        return (now - last_dt.astimezone(UTC)) >= timedelta(seconds=self.idle_timeout_sec)

    async def _db_upsert(self, table: str, data: Dict[str, Any]):
        retries = 2
        for attempt in range(retries + 1):
            try:
                await asyncio.to_thread(
                    lambda: self.supabase.table(table).upsert(data).execute()
                )
                return
            except Exception as exc:  # noqa: BLE001
                if attempt >= retries:
                    logger.warning(
                        "Supabase upsert failed table=%s session_id=%s error=%s",
                        table,
                        data.get("session_id", ""),
                        exc,
                    )
                    return

                await asyncio.sleep(min(0.1 * (2**attempt), 1.0))
