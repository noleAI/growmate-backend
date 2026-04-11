import asyncio
import logging
import time
from typing import Any, Dict

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from core.llm_service import LLMService
from core.payload_formatter import format_dashboard_payload
from core.state_manager import StateManager

logger = logging.getLogger("orchestrator")


class AgenticOrchestrator:
    def __init__(
        self, agents: Dict[str, IAgent], state_mgr: StateManager, llm: LLMService
    ):
        self.agents = agents
        self.state_mgr = state_mgr
        self.llm = llm
        # TODO: Điền threshold từ configs/agents.yaml sau
        self.ENTROPY_THRESHOLD = 0.0
        self.FATIGUE_THRESHOLD = 0.0
        self.Q_STAGNATION_STEPS = 0
        self.MAX_HTL_RETRIES = 3

    async def run_session_step(
        self, session_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Luồng xử lý chính cho mỗi bước tương tác"""
        start_time = time.time()
        state = await self.state_mgr.load_or_init(session_id)

        # 1. Chuẩn bị input chung
        agent_input = AgentInput(
            session_id=session_id,
            question_id=payload.get("question_id"),
            user_response=payload.get("response"),
            behavior_signals=payload.get("behavior_signals"),
            current_state=state.model_dump(),
        )

        # 2. Chạy Agent Pipeline (có thể điều chỉnh thành gather nếu độc lập)
        academic_out = await self.agents["academic"].process(agent_input)
        empathy_out = await self.agents["empathy"].process(agent_input)
        strategy_out = await self.agents["strategy"].process(agent_input)

        # 3. Merge state
        state.academic_state.update(academic_out.payload)
        state.empathy_state.update(empathy_out.payload)
        state.strategy_state.update(strategy_out.payload)
        state.step += 1

        # 4. Self-Monitor & HITL Check
        hitl_triggered = await self._check_self_monitor(state)
        if hitl_triggered and not state.hitl_pending:
            state.hitl_pending = True
            await self._trigger_hitl(session_id, state)

        # 5. Select Final Action (ưu tiên: HITL > Strategy > Academic Fallback)
        final_action = self._resolve_action(
            academic_out, empathy_out, strategy_out, state.hitl_pending
        )

        # 6. LLM Augmentation (nếu cần)
        if final_action in ["hint", "de_stress", "hitl_brief"]:
            llm_response = await self._call_llm_with_fallback(final_action, state)
            final_action_payload = {
                "text": llm_response.text,
                "fallback_used": llm_response.fallback_used,
            }
        else:
            final_action_payload = {}

        # 7. Format & Broadcast
        dashboard_payload = format_dashboard_payload(
            state, final_action, final_action_payload
        )
        await self.state_mgr.broadcast_ws(session_id, dashboard_payload)

        # 8. Async Sync & Return
        asyncio.create_task(self.state_mgr.sync_to_supabase(session_id, state))
        latency_ms = int((time.time() - start_time) * 1000)

        return {
            "action": final_action,
            "payload": final_action_payload,
            "dashboard_update": dashboard_payload,
            "latency_ms": latency_ms,
        }

    async def _check_self_monitor(self, state: SessionState) -> bool:
        # TODO: Điền logic kiểm tra entropy, PF collapse, Q-stagnation sau
        return False

    async def _trigger_hitl(self, session_id: str, state: SessionState):
        # TODO: Push to Supabase hitl_queue + WS notify
        pass

    def _resolve_action(
        self,
        academic: AgentOutput,
        empathy: AgentOutput,
        strategy: AgentOutput,
        hitl_pending: bool,
    ) -> str:
        if hitl_pending:
            return "hitl_pending"
        return strategy.action  # Ưu tiên Q-policy, fallback academic.action

    async def _call_llm_with_fallback(self, action_type: str, state: SessionState):
        prompt = self._build_prompt(action_type, state)
        fallback = self._get_fallback_template(action_type)
        return await self.llm.generate(prompt, fallback)

    # TODO: Thêm _build_prompt() và _get_fallback_template() sau
    def _build_prompt(self, action_type: str, state: SessionState) -> str:
        return ""

    def _get_fallback_template(self, action_type: str) -> str:
        return ""
