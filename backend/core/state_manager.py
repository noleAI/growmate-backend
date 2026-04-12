import json
from typing import Any, Dict

from supabase import create_client

from agents.base import SessionState


class StateManager:
    def __init__(self, supabase_url: str, supabase_key: str, ws_manager):
        self.supabase = create_client(supabase_url, supabase_key)
        self.ws = ws_manager
        self.cache: Dict[str, SessionState] = {}
        self.sync_counter: Dict[str, int] = {}

    async def load_or_init(self, session_id: str) -> SessionState:
        if session_id not in self.cache:
            # TODO: Ưu tiên load từ cache, nếu miss thì query Supabase
            self.cache[session_id] = SessionState(session_id=session_id)
            self.sync_counter[session_id] = 0
        return self.cache[session_id]

    async def sync_to_supabase(self, session_id: str, state: SessionState):
        self.sync_counter[session_id] += 1
        if self.sync_counter[session_id] % 3 == 0:  # Sync mỗi 3 bước
            empathy_state = state.empathy_state
            await self._db_upsert(
                "agent_state",
                {
                    "session_id": session_id,
                    "belief_dist": json.dumps(
                        state.academic_state.get("belief_dist", {})
                    ),
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
                    "updated_at": "now()",
                },
            )
            self.sync_counter[session_id] = 0

    async def broadcast_ws(self, session_id: str, payload: Dict[str, Any]):
        await self.ws.send_to_session(session_id, json.dumps(payload))

    async def _db_upsert(self, table: str, data: Dict[str, Any]):
        # TODO: Implement Supabase upsert với retry
        pass
