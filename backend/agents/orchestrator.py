import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.empathy_agent.particle_filter import ParticleFilter
from core.llm_service import LLMService
from core.payload_formatter import format_dashboard_payload
from core.state_manager import StateManager
from orchestrator.engine import OrchestratorEngine
from orchestrator.schemas import OrchestratorDecision

logger = logging.getLogger("orchestrator")


class AgenticOrchestrator:
    def __init__(
        self, agents: Dict[str, IAgent], state_mgr: StateManager, llm: LLMService
    ):
        self.agents = agents
        self.state_mgr = state_mgr
        self.llm = llm
        self.config = self._load_agent_config()
        self.self_monitor_cfg = self.config.get("orchestrator", {}).get("self_monitor", {})
        orchestrator_cfg = self._load_orchestrator_config()
        self.decision_engine = OrchestratorEngine(orchestrator_cfg.get("orchestrator", {}))

        self.ENTROPY_THRESHOLD = float(self.self_monitor_cfg.get("entropy_threshold", 0.75))
        self.FATIGUE_THRESHOLD = float(self.self_monitor_cfg.get("fatigue_threshold", 0.8))
        self.Q_STAGNATION_STEPS = int(self.self_monitor_cfg.get("q_stagnation_steps", 3))
        self.PF_COLLAPSE_THRESHOLD = float(
            self.self_monitor_cfg.get("pf_collapse_threshold", 0.15)
        )
        self.MAX_HTL_RETRIES = 3

        pf_config = self.config.get("empathy", {}).get("particle_filter", {})
        self.empathy_override_threshold = float(
            pf_config.get("uncertainty_override_threshold", 0.75)
        )
        self.pf_agent = ParticleFilter(config=pf_config)

    async def run_session_step(
        self, session_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Luồng xử lý chính cho mỗi bước tương tác"""
        start_time = time.time()
        state = await self.state_mgr.load_or_init(session_id)
        student_id = payload.get("student_id")

        # 1. Chuẩn bị input chung
        agent_input = AgentInput(
            session_id=session_id,
            student_id=student_id,
            question_id=payload.get("question_id"),
            user_response=payload.get("response"),
            behavior_signals=payload.get("behavior_signals"),
            current_state=state.model_dump(),
        )

        # 2. Chạy Agent Pipeline
        academic_out = await self.agents["academic"].process(agent_input)
        empathy_out = await self.agents["empathy"].process(agent_input)

        if not self._is_pf_payload(empathy_out.payload):
            empathy_out = await self.pf_agent.process(agent_input)

        if self._is_pf_unstable(empathy_out.payload):
            self.pf_agent.reset(explicit_feedback={"confusion": 0.5, "fatigue": 0.5})
            logger.warning("PF reset due to instability for session=%s", session_id)
            empathy_out = await self.pf_agent.process(agent_input)

        # 3. Merge state
        state.academic_state.update(academic_out.payload)
        state.empathy_state.update(empathy_out.payload)

        strategy_input = agent_input.model_copy(update={"current_state": state.model_dump()})
        strategy_out = await self.agents["strategy"].process(strategy_input)
        state.strategy_state.update(strategy_out.payload)

        q_state = state.empathy_state.get("q_state")
        if q_state:
            state.strategy_state["q_state"] = q_state

        state.step += 1

        orchestrator_decision = self.decision_engine.run_step(
            academic_state=state.academic_state,
            empathy_state=state.empathy_state,
            memory_state=state.strategy_state,
        )
        state.strategy_state["orchestrator_decision"] = orchestrator_decision.model_dump()

        # 4. Self-Monitor & HITL Check
        hitl_triggered = await self._check_self_monitor(state, orchestrator_decision)
        if hitl_triggered and not state.hitl_pending:
            state.hitl_pending = True
            await self._trigger_hitl(session_id, state)

        # 5. Select Final Action (ưu tiên: HITL > Strategy > Academic Fallback)
        final_action = self._resolve_action(
            academic_out,
            empathy_out,
            strategy_out,
            state.hitl_pending,
            orchestrator_decision,
        )

        # 6. LLM Augmentation (nếu cần)
        if final_action in ["hint", "show_hint", "de_stress", "hitl_brief"]:
            llm_response = await self._call_llm_with_fallback(final_action, state)
            final_action_payload = {
                "text": llm_response.text,
                "fallback_used": llm_response.fallback_used,
            }
        else:
            final_action_payload = {}

        # 7. Format & Broadcast
        dashboard_payload = format_dashboard_payload(
            state,
            final_action,
            final_action_payload,
            orchestrator_decision=orchestrator_decision.model_dump(),
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

    async def _check_self_monitor(
        self,
        state: SessionState,
        decision: Optional[OrchestratorDecision] = None,
    ) -> bool:
        entropy = float(state.academic_state.get("entropy", 0.0))
        fatigue = float(state.empathy_state.get("fatigue", 0.0))
        ess = float(state.empathy_state.get("ess", 0.0))
        particle_count = len(state.empathy_state.get("particle_cloud", []))
        uncertainty = float(
            state.empathy_state.get(
                "uncertainty", state.empathy_state.get("uncertainty_score", 0.0)
            )
        )

        if decision and decision.hitl_triggered:
            return True

        if entropy >= self.ENTROPY_THRESHOLD:
            return True
        if fatigue >= self.FATIGUE_THRESHOLD:
            return True

        if particle_count > 0:
            ess_ratio = ess / particle_count
            if ess_ratio <= self.PF_COLLAPSE_THRESHOLD:
                return True

        if uncertainty > 0.9:
            return True

        return False

    async def _trigger_hitl(self, session_id: str, state: SessionState):
        entropy = float(state.academic_state.get("entropy", 0.0))
        fatigue = float(state.empathy_state.get("fatigue", 0.0))
        uncertainty = float(
            state.empathy_state.get(
                "uncertainty", state.empathy_state.get("uncertainty_score", 0.0)
            )
        )

        reason = "combined_uncertainty"
        if entropy >= self.ENTROPY_THRESHOLD:
            reason = "high_academic_entropy"
        elif fatigue >= self.FATIGUE_THRESHOLD:
            reason = "high_fatigue"
        elif uncertainty > 0.9:
            reason = "high_empathy_uncertainty"

        state.strategy_state["hitl_context"] = {
            "reason": reason,
            "step": state.step,
            "entropy": entropy,
            "fatigue": fatigue,
            "uncertainty": uncertainty,
        }

        notification = {
            "event": "hitl_triggered",
            "session_id": session_id,
            "step": state.step,
            "reason": reason,
            "metrics": {
                "entropy": entropy,
                "fatigue": fatigue,
                "uncertainty": uncertainty,
            },
        }

        try:
            await self.state_mgr.broadcast_ws(session_id, notification)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HITL WS notify failed for session=%s error=%s", session_id, exc)

        supabase_client = getattr(self.state_mgr, "supabase", None)
        if supabase_client is None:
            return

        audit_payload = {
            "session_id": session_id,
            "event_type": "hitl_trigger",
            "context": {
                "reason": reason,
                "step": state.step,
                "entropy": entropy,
                "fatigue": fatigue,
                "uncertainty": uncertainty,
            },
            "hitl_triggered": True,
        }

        try:
            await asyncio.to_thread(
                lambda: supabase_client.table("audit_logs").insert(audit_payload).execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "HITL audit insert failed for session=%s error=%s",
                session_id,
                exc,
            )

    def _resolve_action(
        self,
        academic: AgentOutput,
        empathy: AgentOutput,
        strategy: AgentOutput,
        hitl_pending: bool,
        decision: Optional[OrchestratorDecision] = None,
    ) -> str:
        if hitl_pending:
            return "hitl_pending"

        if decision and decision.action:
            if decision.action not in {"hitl", "hitl_pending"}:
                return str(decision.action)

        empathy_payload = empathy.payload or {}
        uncertainty = empathy_payload.get("uncertainty", empathy_payload.get("uncertainty_score", 0.0))
        override_action = empathy_payload.get("override_recommended_action")
        hitl_triggered = bool(empathy_payload.get("hitl_triggered", False))

        if self._is_finite_number(uncertainty):
            if float(uncertainty) >= self.empathy_override_threshold and override_action:
                return str(override_action)

        if hitl_triggered and override_action:
            return str(override_action)

        return strategy.action if strategy.action else academic.action

    async def _call_llm_with_fallback(self, action_type: str, state: SessionState):
        prompt = self._build_prompt(action_type, state)
        fallback = self._get_fallback_template(action_type)
        return await self.llm.generate(prompt, fallback)

    def _build_prompt(self, action_type: str, state: SessionState) -> str:
        top_hypothesis = str(state.academic_state.get("top_hypothesis", ""))
        entropy = float(state.academic_state.get("entropy", 0.0))
        confusion = float(state.empathy_state.get("confusion", 0.0))
        fatigue = float(state.empathy_state.get("fatigue", 0.0))
        uncertainty = float(
            state.empathy_state.get(
                "uncertainty", state.empathy_state.get("uncertainty_score", 0.0)
            )
        )

        return "\n".join(
            [
                "You are GrowMate tutor assistant.",
                f"Action type: {action_type}",
                f"Session: {state.session_id}",
                f"Step: {state.step}",
                "Current learner profile:",
                f"- Top hypothesis: {top_hypothesis or 'unknown'}",
                f"- Academic entropy: {entropy:.3f}",
                f"- Confusion: {confusion:.3f}",
                f"- Fatigue: {fatigue:.3f}",
                f"- Empathy uncertainty: {uncertainty:.3f}",
                "Generate short Vietnamese guidance that is supportive and actionable.",
            ]
        )

    def _get_fallback_template(self, action_type: str) -> str:
        fallback_templates = {
            "hint": "Thu nho bai toan thanh tung buoc nho. Hay bat dau bang viec xac dinh quy tac dao ham phu hop.",
            "show_hint": "Thu nho bai toan thanh tung buoc nho. Hay bat dau bang viec xac dinh quy tac dao ham phu hop.",
            "de_stress": "Ban dang co dau hieu met. Minh de xuat nghi 60 giay, uong nuoc, sau do quay lai voi 1 cau de hon.",
            "hitl_brief": "He thong da phat hien do bat dinh cao. Se chuyen yeu cau cho nguoi huong dan ho tro tiep theo.",
        }
        return fallback_templates.get(
            action_type,
            "Hay tiep tuc voi toc do vua phai. Neu can, minh co the dua them goi y tung buoc.",
        )

    def _is_pf_payload(self, payload: Dict[str, Any]) -> bool:
        required = {"confusion", "fatigue", "uncertainty", "ess", "particle_cloud", "weights"}
        return required.issubset(payload.keys())

    def _is_pf_unstable(self, payload: Dict[str, Any]) -> bool:
        uncertainty = payload.get("uncertainty")
        confusion = payload.get("confusion")
        fatigue = payload.get("fatigue")

        if uncertainty is None:
            return True
        if not self._is_finite_number(uncertainty):
            return True
        if not self._is_finite_number(confusion) or not self._is_finite_number(fatigue):
            return True
        return False

    def _is_finite_number(self, value: Any) -> bool:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        return numeric == numeric and numeric not in (float("inf"), float("-inf"))

    def _load_agent_config(self) -> Dict[str, Any]:
        config_path = Path(__file__).resolve().parents[1] / "configs" / "agents.yaml"
        if not config_path.exists():
            logger.warning("Missing config file at %s. Falling back to defaults.", config_path)
            return {}

        with config_path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def _load_orchestrator_config(self) -> Dict[str, Any]:
        config_path = Path(__file__).resolve().parents[1] / "configs" / "orchestrator.yaml"
        if not config_path.exists():
            logger.warning(
                "Missing orchestrator config at %s. Falling back to defaults.",
                config_path,
            )
            return {}

        with config_path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}
