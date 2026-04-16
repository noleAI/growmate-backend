import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from agents.base import AgentInput, AgentOutput, IAgent, SessionState
from agents.empathy_agent.particle_filter import ParticleFilter
from core.data_packages import DataPackagesService
from core.formula_recommender import FormulaRecommender
from core.llm_service import LLMService
from core.payload_formatter import format_dashboard_payload
from core.state_manager import StateManager
from core.supabase_client import increment_user_token_usage
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

    async def run_session_step(
        self, session_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Luồng xử lý chính cho mỗi bước tương tác"""
        start_time = time.time()
        state = await self.state_mgr.load_or_init(session_id)
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

        if bool(payload.get("resume", False)):
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
        if spam_detected or afk_detected:
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

        # 5. Select Final Action with pause and off-topic safeguards.
        if state.off_topic_counter >= 3:
            final_action = "gentle_redirect"
            state.off_topic_counter = 0
            state.strategy_state["off_topic_counter"] = 0
        elif state.pause_state:
            final_action = "pause_quiz"
        else:
            final_action = self._resolve_action(
                academic_out,
                empathy_out,
                strategy_out,
                state.hitl_pending,
                orchestrator_decision,
            )

        # 6. LLM Augmentation (nếu cần)
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

        # 7. Format & Broadcast
        dashboard_payload = format_dashboard_payload(
            state,
            final_action,
            final_action_payload,
            orchestrator_decision=orchestrator_decision.model_dump(),
        )
        if data_driven_payload:
            dashboard_payload["data_driven"] = data_driven_payload
        await self.state_mgr.broadcast_ws(session_id, dashboard_payload)

        # 8. Async Sync & Return
        asyncio.create_task(self.state_mgr.sync_to_supabase(session_id, state))
        latency_ms = int((time.time() - start_time) * 1000)

        return {
            "action": final_action,
            "payload": final_action_payload,
            "data_driven": data_driven_payload,
            "dashboard_update": dashboard_payload,
            "latency_ms": latency_ms,
        }

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
    ) -> None:
        user_id = str(student_id or "").strip()
        if not user_id:
            return

        tokens_used = self._estimate_tokens(response_text)
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
