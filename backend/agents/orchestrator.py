import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.empathy_agent.particle_filter import ParticleFilter
from core.data_packages import DataPackagesService
from core.formula_recommender import FormulaRecommender
from core.llm_service import LLMService
from core.memory_store import memory_store
from core.payload_formatter import format_dashboard_payload
from core.state_manager import StateManager
from core.supabase_client import increment_user_token_usage
from core.tool_handlers import (
    get_academic_beliefs,
    get_empathy_state,
    get_formula_bank,
    get_orchestrator_score,
    get_strategy_suggestion,
    get_student_history,
    search_knowledge,
)
from core.tool_registry import ToolDefinition, ToolRegistry
from core.user_classifier import classify
from orchestrator.engine import OrchestratorEngine
from orchestrator.schemas import OrchestratorDecision

logger = logging.getLogger("orchestrator")
VN_TZ = timezone(timedelta(hours=7))


class AgenticOrchestrator:
    def __init__(
        self,
        agents: Dict[str, IAgent],
        state_mgr: StateManager,
        llm: LLMService,
        data_packages: Optional[DataPackagesService] = None,
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
        self.MAX_HITL_RETRIES = 3

        pf_config = self.config.get("empathy", {}).get("particle_filter", {})
        self.empathy_override_threshold = float(
            pf_config.get("uncertainty_override_threshold", 0.75)
        )
        self.pf_agent = ParticleFilter(config=pf_config)

        # Data-driven bundles (Package 2/3/4). Accept an already-loaded shared instance when
        # available (e.g. injected from startup); otherwise create and load a private one so
        # the orchestrator degrades gracefully when running outside the full app context.
        if data_packages is not None:
            self.data_packages = data_packages
        else:
            self.data_packages = DataPackagesService.from_default_paths()
            self.data_packages.load()

        self.formula_recommender = FormulaRecommender()
        self.memory_store = memory_store

        agentic_cfg = orchestrator_cfg.get("agentic", {})
        env_use_llm = os.getenv("USE_LLM_REASONING")
        if env_use_llm is not None:
            self.use_llm_reasoning = env_use_llm.lower() == "true"
        else:
            self.use_llm_reasoning = bool(
                agentic_cfg.get("enabled", False)
                and agentic_cfg.get("llm_reasoning", {}).get("enabled", False)
            )

        self.agentic_capable = callable(getattr(self.llm, "run_agentic_reasoning", None))
        if self.use_llm_reasoning and not self.agentic_capable:
            logger.warning(
                "USE_LLM_REASONING requested but injected LLM does not support "
                "run_agentic_reasoning; falling back to adaptive mode"
            )
            self.use_llm_reasoning = False

        self.agentic_max_steps = int(
            os.getenv(
                "AGENTIC_MAX_STEPS",
                agentic_cfg.get("llm_reasoning", {}).get("max_steps", 5),
            )
            or 5
        )
        self.agentic_timeout_ms = int(
            os.getenv(
                "AGENTIC_TIMEOUT_MS",
                agentic_cfg.get("llm_reasoning", {}).get("timeout_ms", 8000),
            )
            or 8000
        )
        self.agentic_tool_timeout_ms = int(
            os.getenv("AGENTIC_TOOL_TIMEOUT_MS", self.agentic_timeout_ms)
            or self.agentic_timeout_ms
        )

        planning_cfg = agentic_cfg.get("planning", {})
        self.planning_enabled = bool(
            os.getenv(
                "PLANNING_ENABLED",
                str(planning_cfg.get("enabled", False)),
            ).lower()
            == "true"
        )
        self.planning_max_length = int(
            os.getenv(
                "PLANNING_MAX_LENGTH",
                planning_cfg.get("max_plan_length", 5),
            )
            or 5
        )
        self.reflection_enabled = bool(
            os.getenv(
                "REFLECTION_ENABLED",
                str(agentic_cfg.get("reflection", {}).get("enabled", True)),
            ).lower()
            == "true"
        )
        self.reflection_interval = int(
            os.getenv(
                "REFLECTION_INTERVAL",
                agentic_cfg.get("reflection", {}).get("interval", 5),
            )
            or 5
        )

        self.knowledge_retriever = None
        self.tool_registry: ToolRegistry | None = None
        self.reflection_engine = None
        self.reasoning_engine = None
        self.dynamic_planner = None

        if self.planning_enabled:
            try:
                from agents.academic_agent.htn_planner import htn_planner

                self.dynamic_planner = htn_planner
            except Exception as exc:  # noqa: BLE001
                logger.warning("Dynamic planner init skipped: %s", exc)

        if self.use_llm_reasoning:
            try:
                from core.knowledge_retriever import KnowledgeRetriever

                self.knowledge_retriever = KnowledgeRetriever(
                    supabase_client=getattr(self.state_mgr, "supabase", None)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Knowledge retriever init skipped: %s", exc)

            self.tool_registry = self._build_tool_registry()

            try:
                from agents.reasoning_loop import ReActEngine

                self.reasoning_engine = ReActEngine(
                    llm_service=self.llm,
                    tool_registry=self.tool_registry,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("ReAct engine init skipped: %s", exc)

            if self.reflection_enabled:
                try:
                    from agents.reflection_engine import ReflectionEngine

                    self.reflection_engine = ReflectionEngine(
                        llm_service=self.llm,
                        memory_store=self.memory_store,
                        state_manager=self.state_mgr,
                        interval=self.reflection_interval,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Reflection engine init skipped: %s", exc)

    async def run_session_step(
        self, session_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Luồng xử lý chính cho mỗi bước tương tác"""
        start_time = time.time()
        student_id = payload.get("student_id")
        access_token_raw = payload.get("access_token")
        access_token = access_token_raw if isinstance(access_token_raw, str) else None

        register_context = getattr(self.state_mgr, "register_session_context", None)
        if callable(register_context):
            register_context(
                session_id=session_id,
                student_id=student_id,
                access_token=access_token,
            )

        state = await self.state_mgr.load_or_init(session_id)

        mode = str(payload.get("mode") or state.mode or state.strategy_state.get("mode", "normal"))
        classification_level = payload.get("classification_level")
        onboarding_results = payload.get("onboarding_results")
        if not classification_level and isinstance(onboarding_results, dict):
            classification_level = classify(onboarding_results).value
        if not classification_level:
            classification_level = state.user_classification_level or state.strategy_state.get(
                "classification_level", "intermediate"
            )
        classification_level = str(classification_level)

        state.mode = mode
        state.user_classification_level = classification_level
        state.strategy_state["mode"] = mode
        state.strategy_state["classification_level"] = classification_level
        state.strategy_state["student_id"] = str(student_id or "").strip()

        resume_requested = bool(payload.get("resume", False))
        if resume_requested:
            state.pause_state = False
            state.pause_reason = None
            state.pause_timestamp = None

        if bool(payload.get("is_off_topic", False)):
            state.off_topic_counter += 1
        state.strategy_state["off_topic_counter"] = state.off_topic_counter

        behavior_signals = payload.get("behavior_signals")
        if not isinstance(behavior_signals, dict):
            behavior_signals = {}

        previous_signal_time = state.last_signal_time
        if behavior_signals:
            signal_entry = dict(behavior_signals)
            signal_entry["timestamp"] = datetime.now(UTC).isoformat()
            history = list(state.signal_history or [])
            history.append(signal_entry)
            state.signal_history = history[-5:]
            state.last_signal_time = signal_entry["timestamp"]

        state.last_interaction_timestamp = datetime.now(UTC)
        state.strategy_state["last_interaction_at"] = (
            state.last_interaction_timestamp.isoformat()
        )

        academic_agent = self.agents.get("academic")
        apply_profile_prior = getattr(academic_agent, "apply_profile_prior", None)
        if callable(apply_profile_prior) and state.step == 0:
            try:
                profile_beliefs = apply_profile_prior(classification_level)
                if isinstance(profile_beliefs, dict):
                    state.academic_state["belief_dist"] = profile_beliefs
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to apply profile prior for session=%s level=%s error=%s",
                    session_id,
                    classification_level,
                    exc,
                )

        xp_data = payload.get("xp_data")
        if isinstance(xp_data, dict):
            state.strategy_state["xp_data"] = xp_data

        # 1. Chuẩn bị input chung
        agent_input = AgentInput(
            session_id=session_id,
            student_id=student_id,
            question_id=payload.get("question_id"),
            user_response=payload.get("response"),
            behavior_signals=behavior_signals,
            mode=mode,
            classification_level=classification_level,
            signal_history=list(state.signal_history or []),
            last_signal_time=previous_signal_time,
            analytics_data=payload.get("analytics_data"),
            off_topic_counter=state.off_topic_counter,
            current_state=state.model_dump(),
        )

        # 2. Chạy Agent Pipeline
        academic_out = await self.agents["academic"].process(agent_input)

        error_chain = payload.get("error_chain")
        if error_chain is None and isinstance(payload.get("response"), dict):
            error_chain = payload["response"].get("error_chain")
        if isinstance(error_chain, list):
            update_from_error_chain = getattr(self.agents["academic"], "update_from_error_chain", None)
            if callable(update_from_error_chain):
                try:
                    updated_beliefs = update_from_error_chain(error_chain)
                    if isinstance(updated_beliefs, dict):
                        academic_out.payload["belief_dist"] = updated_beliefs
                        get_entropy = getattr(self.agents["academic"], "get_entropy", None)
                        if callable(get_entropy):
                            academic_out.payload["entropy"] = float(get_entropy())
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Error-chain update failed for session=%s error=%s",
                        session_id,
                        exc,
                    )

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

        spam_detected = bool(state.empathy_state.get("spam_detected", False))
        afk_detected = bool(state.empathy_state.get("afk_detected", False))
        pause_transition = False
        if spam_detected or afk_detected:
            pause_transition = not state.pause_state
            state.pause_state = True
            state.pause_reason = "spam" if spam_detected else "afk"
            state.pause_timestamp = datetime.now(UTC).isoformat()

        strategy_input = agent_input.model_copy(update={"current_state": state.model_dump()})
        strategy_out = await self.agents["strategy"].process(strategy_input)
        state.strategy_state.update(strategy_out.payload)

        q_state = state.empathy_state.get("q_state")
        if q_state:
            state.strategy_state["q_state"] = q_state

        state.step += 1
        total_questions = int(state.strategy_state.get("total_questions", 10) or 10)
        if total_questions <= 0:
            total_questions = 10
        state.strategy_state["total_questions"] = total_questions
        state.strategy_state["last_question_index"] = min(
            total_questions,
            max(0, int(state.step or 0)),
        )
        state.strategy_state["progress_percent"] = min(
            100,
            int(
                round(
                    (
                        state.strategy_state["last_question_index"]
                        / max(1, total_questions)
                    )
                    * 100
                )
            ),
        )

        if self.planning_enabled and self.dynamic_planner is not None:
            await self._maybe_generate_dynamic_plan(
                session_id=session_id,
                state=state,
            )

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

        # 5. Select final action with safeguards, then optional agentic reasoning.
        reasoning_mode = "adaptive"
        reasoning_trace: list[dict[str, Any]] = []
        reasoning_content = ""
        reasoning_confidence = 0.5
        agentic_content = ""
        agentic_fallback_used = False

        final_action = ""
        if state.off_topic_counter >= 3:
            final_action = "gentle_redirect"
            state.off_topic_counter = 0
            state.strategy_state["off_topic_counter"] = 0
        elif state.pause_state:
            final_action = "pause_quiz"
        elif self.use_llm_reasoning and self.tool_registry is not None:
            try:
                student_context = self._build_student_context(payload, state)
                if self.reasoning_engine is not None:
                    react_result = await asyncio.wait_for(
                        self.reasoning_engine.reason(
                            session_id=session_id,
                            student_input=student_context,
                            max_steps=self.agentic_max_steps,
                        ),
                        timeout=self.agentic_timeout_ms / 1000,
                    )
                    if react_result.fallback_used:
                        raise RuntimeError("ReAct fallback requested")

                    final_action = self._normalize_action_name(str(react_result.action))
                    reasoning_mode = "agentic"
                    reasoning_trace = [
                        {
                            "step": item.step,
                            "tool": item.action,
                            "args": item.action_args,
                            "result_summary": item.observation,
                        }
                        for item in react_result.steps
                    ]
                    reasoning_content = react_result.reasoning
                    reasoning_confidence = float(react_result.confidence)
                    agentic_content = react_result.content.strip()
                    agentic_fallback_used = bool(react_result.fallback_used)

                    state.strategy_state["agentic_result"] = {
                        "action": final_action,
                        "confidence": reasoning_confidence,
                        "llm_steps": len(react_result.steps),
                        "tool_count": len(react_result.steps),
                        "fallback": agentic_fallback_used,
                    }
                else:
                    agentic_result = await asyncio.wait_for(
                        self.llm.run_agentic_reasoning(
                            session_id=session_id,
                            student_input=student_context,
                            tool_registry=self.tool_registry,
                            max_steps=self.agentic_max_steps,
                            timeout_ms=self.agentic_timeout_ms,
                            tool_timeout_ms=self.agentic_tool_timeout_ms,
                        ),
                        timeout=self.agentic_timeout_ms / 1000,
                    )

                    if bool(agentic_result.get("fallback", False)):
                        raise RuntimeError("LLM agentic fallback requested")

                    final_action = self._normalize_action_name(
                        str(agentic_result.get("action", "next_question"))
                    )
                    reasoning_mode = "agentic"
                    reasoning_trace = list(agentic_result.get("reasoning_trace", []))
                    reasoning_content = str(agentic_result.get("reasoning", ""))
                    reasoning_confidence = float(
                        agentic_result.get("confidence", 0.5) or 0.5
                    )
                    agentic_content = str(agentic_result.get("content", "")).strip()
                    agentic_fallback_used = bool(agentic_result.get("fallback", False))

                    state.strategy_state["agentic_result"] = {
                        "action": final_action,
                        "confidence": reasoning_confidence,
                        "llm_steps": int(agentic_result.get("llm_steps", 0) or 0),
                        "tool_count": len(reasoning_trace),
                        "fallback": agentic_fallback_used,
                    }
                if reasoning_mode == "agentic":
                    llm_steps = int(
                        state.strategy_state.get("agentic_result", {}).get(
                            "llm_steps",
                            len(reasoning_trace),
                        )
                        or 1
                    )
                    await self._track_llm_usage(
                        student_id=student_id,
                        session_id=session_id,
                        response_text=f"{agentic_content}\n{reasoning_content}".strip(),
                        access_token=access_token,
                        token_multiplier=max(1, llm_steps),
                    )
            except asyncio.TimeoutError:
                logger.warning(
                    "Agentic reasoning timed out for session=%s timeout_ms=%s",
                    session_id,
                    self.agentic_timeout_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Agentic reasoning failed for session=%s error=%s",
                    session_id,
                    exc,
                )

        if not final_action:
            planned_action = self._consume_dynamic_plan_action(state)
            if planned_action:
                final_action = planned_action

        if not final_action:
            final_action = self._resolve_action(
                academic_out,
                empathy_out,
                strategy_out,
                state.hitl_pending,
                orchestrator_decision,
            )
            reasoning_mode = "adaptive"

        # 6. Action payload generation.
        if final_action == "pause_quiz":
            reason = state.pause_reason or "manual"
            final_action_payload = {
                "reason": reason,
                "text": (
                    "Phiên học đã tạm dừng do phát hiện thao tác bất thường."
                    if reason == "spam"
                    else "Bạn đã tạm nghỉ quá lâu. Bấm tiếp tục khi sẵn sàng học lại."
                ),
            }
        elif final_action == "gentle_redirect":
            final_action_payload = {
                "reason": "off_topic",
                "text": "Mình sẽ đưa cuộc trò chuyện quay lại bài học đạo hàm để học hiệu quả hơn.",
            }
        elif reasoning_mode == "agentic" and agentic_content:
            final_action_payload = {
                "text": agentic_content,
                "fallback_used": agentic_fallback_used,
            }
        elif final_action in ["hint", "show_hint", "de_stress", "hitl_brief"]:
            llm_response = await self._call_llm_with_fallback(
                final_action,
                state,
                student_id=student_id,
                access_token=access_token,
            )
            final_action_payload = {
                "text": llm_response.text,
                "fallback_used": llm_response.fallback_used,
            }
        else:
            final_action_payload = {}

        data_driven_payload = self._build_data_driven_payload(
            state=state,
            decision=orchestrator_decision,
            final_action=final_action,
        )
        if data_driven_payload:
            final_action_payload["data_driven"] = data_driven_payload
            state.strategy_state["data_driven"] = data_driven_payload

        latency_ms = int((time.time() - start_time) * 1000)
        llm_steps = int(
            state.strategy_state.get("agentic_result", {}).get(
                "llm_steps",
                len(reasoning_trace),
            )
            or 0
        )
        tool_count = int(
            state.strategy_state.get("agentic_result", {}).get(
                "tool_count",
                len(reasoning_trace),
            )
            or 0
        )

        logger.info(
            "Decision summary session=%s mode=%s action=%s llm_steps=%s tool_count=%s fallback_used=%s",
            session_id,
            reasoning_mode,
            final_action,
            llm_steps,
            tool_count,
            agentic_fallback_used,
        )

        log_reasoning_trace = getattr(self.memory_store, "log_reasoning_trace", None)
        if callable(log_reasoning_trace):
            asyncio.create_task(
                log_reasoning_trace(
                    session_id=session_id,
                    step=int(state.step or 0),
                    reasoning_mode=reasoning_mode,
                    tools_called=reasoning_trace,
                    reasoning_text=reasoning_content,
                    final_action=final_action,
                    confidence=reasoning_confidence,
                    latency_ms=latency_ms,
                    fallback_used=agentic_fallback_used,
                )
            )

        if (
            self.use_llm_reasoning
            and self.reflection_engine is not None
            and self.reflection_enabled
            and state.step > 0
            and state.step % max(1, self.reflection_interval) == 0
        ):
            asyncio.create_task(
                self.reflection_engine.maybe_reflect(
                    session_id=session_id,
                    current_step=state.step,
                )
            )

        # 7. Format & Broadcast
        dashboard_payload = format_dashboard_payload(
            state,
            final_action,
            final_action_payload,
            orchestrator_decision=orchestrator_decision.model_dump(),
            reasoning_mode=reasoning_mode,
            reasoning_trace=reasoning_trace,
            reasoning_content=reasoning_content,
            reasoning_confidence=reasoning_confidence,
        )
        if data_driven_payload:
            dashboard_payload["data_driven"] = data_driven_payload
        await self.state_mgr.broadcast_ws(session_id, dashboard_payload)

        # 8. Sync & Return
        action_type = str(payload.get("action_type") or "").strip().lower()
        force_sync_reason = ""
        if action_type in {"submit_quiz", "submit_answer"}:
            force_sync_reason = "quiz_submit"
        elif pause_transition:
            force_sync_reason = "pause_transition"
        elif resume_requested:
            force_sync_reason = "resume_transition"

        if force_sync_reason:
            try:
                await self.state_mgr.sync_to_supabase(
                    session_id,
                    state,
                    force=True,
                    reason=force_sync_reason,
                )
            except TypeError:
                # Backward compatibility for test stubs or legacy state managers.
                await self.state_mgr.sync_to_supabase(session_id, state)
        else:
            asyncio.create_task(self.state_mgr.sync_to_supabase(session_id, state))

        return {
            "action": final_action,
            "payload": final_action_payload,
            "data_driven": data_driven_payload,
            "dashboard_update": dashboard_payload,
            "reasoning_mode": reasoning_mode,
            "reasoning_trace": reasoning_trace,
            "reasoning_content": reasoning_content,
            "reasoning_confidence": reasoning_confidence,
            "llm_steps": llm_steps,
            "tool_count": tool_count,
            "fallback_used": agentic_fallback_used,
            "latency_ms": latency_ms,
        }

    def _normalize_action_name(self, action: str) -> str:
        mapping = {
            "continue_quiz": "next_question",
            "suggest_break": "de_stress",
            "trigger_hitl": "hitl",
            "hint": "show_hint",
            "hitl_pending": "hitl",
            "hitl_brief": "hitl",
        }
        normalized = mapping.get(action, action)
        allowed = {
            "next_question",
            "show_hint",
            "drill_practice",
            "de_stress",
            "hitl",
            "pause_quiz",
            "gentle_redirect",
            "hitl_pending",
        }
        if normalized not in allowed:
            return "next_question"
        return normalized

    def _build_student_context(self, payload: Dict[str, Any], state: SessionState) -> Dict[str, Any]:
        response = payload.get("response")
        if not isinstance(response, dict):
            response = {}

        return {
            "question_text": payload.get("question_text") or payload.get("question_id", ""),
            "student_answer": response.get("selected") or response.get("answer", ""),
            "correct_answer": response.get("correct_answer", ""),
            "is_correct": response.get("is_correct"),
            "behavior_signals": payload.get("behavior_signals", {}),
            "step": state.step,
            "mode": state.mode,
        }

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        session_schema = {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Learning session id",
                }
            },
            "required": ["session_id"],
        }

        registry.register(
            ToolDefinition(
                name="get_academic_beliefs",
                description="Get Bayesian academic belief distribution and entropy.",
                parameters=session_schema,
                handler=partial(get_academic_beliefs, state_manager=self.state_mgr),
            )
        )

        registry.register(
            ToolDefinition(
                name="get_empathy_state",
                description="Get current empathy state including confusion and fatigue.",
                parameters=session_schema,
                handler=partial(get_empathy_state, state_manager=self.state_mgr),
            )
        )

        registry.register(
            ToolDefinition(
                name="get_strategy_suggestion",
                description="Get Q-learning strategy suggestion for next action.",
                parameters=session_schema,
                handler=partial(get_strategy_suggestion, state_manager=self.state_mgr),
            )
        )

        registry.register(
            ToolDefinition(
                name="get_student_history",
                description="Get recent learning episodes and short accuracy trend.",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Learning session id"},
                        "n": {"type": "integer", "description": "Number of recent episodes"},
                    },
                    "required": ["session_id"],
                },
                handler=partial(
                    get_student_history,
                    memory_store=self.memory_store,
                    state_manager=self.state_mgr,
                ),
            )
        )

        registry.register(
            ToolDefinition(
                name="get_formula_bank",
                description="Get formula recommendations by hypothesis or topic.",
                parameters={
                    "type": "object",
                    "properties": {
                        "hypothesis": {"type": "string", "description": "Hypothesis id"},
                        "topic": {"type": "string", "description": "Free-form topic"},
                    },
                },
                handler=partial(get_formula_bank, formula_recommender=self.formula_recommender),
            )
        )

        registry.register(
            ToolDefinition(
                name="get_orchestrator_score",
                description="Get deterministic orchestrator decision as fallback reference.",
                parameters=session_schema,
                handler=partial(get_orchestrator_score, orchestrator=self),
            )
        )

        if self.knowledge_retriever is not None:
            registry.register(
                ToolDefinition(
                    name="search_knowledge",
                    description="Search Math knowledge chunks via vector retrieval.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "top_k": {
                                "type": "integer",
                                "description": "Max number of returned chunks",
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Learning session id used for local tool budget",
                            },
                            "source": {
                                "type": "string",
                                "description": "Optional source filter",
                                "enum": [
                                    "sgk_toan_12",
                                    "cong_thuc",
                                    "bai_giai_mau",
                                    "loi_thuong_gap",
                                ],
                            },
                        },
                        "required": ["query"],
                    },
                    handler=partial(search_knowledge, retriever=self.knowledge_retriever),
                )
            )

        return registry

    def _build_data_driven_payload(
        self,
        state: SessionState,
        decision: OrchestratorDecision,
        final_action: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.data_packages.is_ready():
            return None

        academic_state = state.academic_state
        empathy_state = state.empathy_state

        entropy = float(academic_state.get("entropy", 0.0))
        confidence = float(academic_state.get("confidence", max(0.0, min(1.0, 1.0 - entropy))))
        uncertainty = float(decision.total_uncertainty)

        risk_band = self.data_packages.get_risk_band(uncertainty)
        confidence_band = self.data_packages.get_confidence_band(confidence)
        hitl_by_threshold = self.data_packages.should_trigger_hitl(uncertainty, confidence)

        mode = self._resolve_data_mode(
            final_action=final_action,
            hitl_by_threshold=hitl_by_threshold,
            hitl_pending=state.hitl_pending,
            fatigue=float(empathy_state.get("fatigue", 0.0)),
        )

        diagnosis = self.data_packages.resolve_diagnosis(
            mode=mode,
            risk_level=risk_band,
        )

        fallback_rule_applied: Optional[str] = None
        if diagnosis is None:
            diagnosis = self.data_packages.resolve_diagnosis(
                mode="recovery",
                risk_level="medium",
                prefer_fallback_safe=True,
            )
            fallback_rule_applied = "missingDiagnosisScenario"

        intervention_plan = []
        if diagnosis:
            raw_plan = diagnosis.get("interventionPlan", [])
            if isinstance(raw_plan, list):
                intervention_plan = [str(item) for item in raw_plan]

        interventions = self.data_packages.resolve_interventions(intervention_plan)
        if not interventions:
            fallback_id = self.data_packages.get_fallback_intervention_id(
                mode=mode,
                missing_plan=True,
            )
            if fallback_id:
                interventions = self.data_packages.resolve_interventions([fallback_id])
                fallback_rule_applied = "missingInterventionPlan"

        selected_intervention = interventions[0] if interventions else None

        belief_dist = academic_state.get("belief_dist")
        if not isinstance(belief_dist, dict):
            belief_dist = academic_state.get("belief_distribution", {})
        formula_recommendations = self.formula_recommender.recommend_formulas(
            belief_dist=belief_dist if isinstance(belief_dist, dict) else {},
            threshold=0.3,
            limit=3,
        )

        final_mode = str(diagnosis.get("mode", mode)) if diagnosis else mode
        requires_hitl = (
            bool(diagnosis.get("requiresHITL", False))
            if diagnosis
            else bool(final_mode == "hitl_pending")
        )

        system_behavior = {
            "riskBandFromThresholds": risk_band,
            "confidenceBandFromThresholds": confidence_band,
            "hitlTriggered": bool(hitl_by_threshold or state.hitl_pending),
            "fallbackRuleApplied": fallback_rule_applied,
            "finalMode": final_mode,
            "requiresHITL": requires_hitl,
        }

        return {
            "diagnosis": diagnosis,
            "interventions": interventions,
            "selectedIntervention": selected_intervention,
            "formulaRecommendations": formula_recommendations,
            "systemBehavior": system_behavior,
        }

    def _resolve_data_mode(
        self,
        final_action: str,
        hitl_by_threshold: bool,
        hitl_pending: bool,
        fatigue: float,
    ) -> str:
        if hitl_pending or final_action in {"hitl", "hitl_pending"} or hitl_by_threshold:
            return "hitl_pending"

        if final_action in {"de_stress", "suggest_break"} or fatigue >= self.FATIGUE_THRESHOLD:
            return "recovery"

        return "normal"

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

    async def _call_llm_with_fallback(
        self,
        action_type: str,
        state: SessionState,
        student_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        prompt = self._build_prompt(action_type, state)
        fallback = self._get_fallback_template(action_type)
        response = await self.llm.generate(prompt, fallback)
        await self._track_llm_usage(
            student_id=student_id,
            session_id=state.session_id,
            response_text=response.text,
            access_token=access_token,
        )
        return response

    async def _track_llm_usage(
        self,
        student_id: Optional[str],
        session_id: str,
        response_text: str,
        access_token: Optional[str],
        token_multiplier: int = 1,
    ) -> None:
        user_id = str(student_id or "").strip()
        if not user_id:
            return

        tokens_used = self._estimate_tokens(response_text) * max(1, int(token_multiplier or 1))
        usage_date = datetime.now(VN_TZ).date()

        try:
            await increment_user_token_usage(
                user_id=user_id,
                tokens_used=tokens_used,
                usage_date=usage_date,
                access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to increment token usage for user=%s session=%s: %s",
                user_id,
                session_id,
                exc,
            )

    def _estimate_tokens(self, text: str) -> int:
        cleaned = text.strip()
        if not cleaned:
            return 0
        # Use a simple approximation when provider token metadata is unavailable.
        return max(1, len(cleaned) // 4)

    async def _maybe_generate_dynamic_plan(
        self,
        session_id: str,
        state: SessionState,
    ) -> None:
        if not self.planning_enabled or self.dynamic_planner is None:
            return

        plan = state.strategy_state.get("dynamic_plan")
        if isinstance(plan, list) and plan:
            return

        generate_dynamic_plan = getattr(self.dynamic_planner, "generate_dynamic_plan", None)
        if not callable(generate_dynamic_plan):
            return

        try:
            generated_plan = await asyncio.wait_for(
                generate_dynamic_plan(
                    session_id=session_id,
                    context=self._build_planning_context(state),
                    llm_service=self.llm,
                ),
                timeout=self.agentic_timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Dynamic plan generation timed out for session=%s",
                session_id,
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Dynamic plan generation failed for session=%s error=%s",
                session_id,
                exc,
            )
            return

        if not isinstance(generated_plan, list):
            return

        normalized_plan = [
            self._normalize_action_name(str(item))
            for item in generated_plan
            if str(item).strip()
        ]
        if not normalized_plan:
            return

        state.strategy_state["dynamic_plan"] = normalized_plan[: max(1, self.planning_max_length)]
        state.strategy_state["dynamic_plan_generated_at_step"] = state.step

    def _build_planning_context(self, state: SessionState) -> Dict[str, Any]:
        beliefs = state.academic_state.get("belief_dist", {})
        top_hypothesis = "unknown"
        if isinstance(beliefs, dict) and beliefs:
            top_hypothesis = str(max(beliefs, key=lambda key: float(beliefs.get(key, 0.0))))

        return {
            "confidence": float(state.academic_state.get("confidence", 0.0) or 0.0),
            "confusion": float(state.empathy_state.get("confusion", 0.0) or 0.0),
            "fatigue": float(state.empathy_state.get("fatigue", 0.0) or 0.0),
            "entropy": float(state.academic_state.get("entropy", 1.0) or 1.0),
            "top_hypothesis": top_hypothesis,
            "accuracy_recent": float(
                state.strategy_state.get("accuracy_recent", 0.0)
                or state.strategy_state.get("avg_reward_10", 0.0)
                or 0.0
            ),
            "step": int(state.step or 0),
        }

    def _consume_dynamic_plan_action(self, state: SessionState) -> str:
        if not self.planning_enabled:
            return ""

        raw_plan = state.strategy_state.get("dynamic_plan")
        if not isinstance(raw_plan, list) or not raw_plan:
            return ""

        next_action = self._normalize_action_name(str(raw_plan[0]))
        state.strategy_state["dynamic_plan"] = raw_plan[1:]
        state.strategy_state["dynamic_plan_last_used_step"] = state.step
        return next_action

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
            "hint": "Thử nhỏ bài toán thành từng bước nhỏ. Hãy bắt đầu bằng việc xác định quy tắc đạo hàm phù hợp.",
            "show_hint": "Thử nhỏ bài toán thành từng bước nhỏ. Hãy bắt đầu bằng việc xác định quy tắc đạo hàm phù hợp.",
            "de_stress": "Bạn đang có dấu hiệu mệt. Mình đề xuất nghỉ 60 giây, uống nước, sau đó quay lại với 1 câu dễ hơn.",
            "hitl_brief": "Hệ thống đã phát hiện độ bất định cao. Sẽ chuyển yêu cầu cho người hướng dẫn hỗ trợ tiếp theo.",
        }
        return fallback_templates.get(
            action_type,
            "Hãy tiếp tục với tốc độ vừa phải. Nếu cần, mình có thể đưa thêm gợi ý từng bước.",
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
