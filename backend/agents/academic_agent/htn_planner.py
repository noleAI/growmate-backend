import logging
import os
import json
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field

from agents.base import AgentInput, AgentOutput, IAgent
from agents.academic_agent.htn_utils import safe_eval_precondition

logger = logging.getLogger("htn_planner")


class HTNNode(BaseModel):
    task_id: str
    type: str  # 'primitive' or 'compound'
    status: str = "pending"  # 'pending', 'active', 'success', 'failed'
    retry_count: int = 0
    current_method: Optional[str] = None
    children: List["HTNNode"] = Field(default_factory=list)


class HTNPlanner(IAgent):
    def __init__(self, rules_path: str = "configs/htn_rules.yaml"):
        # We need to construct the path relative to the current file
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.rules_path = os.path.join(base_dir, rules_path)
        self.config = {}
        self._load_rules()

    def _load_rules(self):
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f).get("htn_template", {})
            self.root_task_id = self.config.get(
                "root_task", "diagnose_derivative_mastery"
            )
            self.compound_tasks = self.config.get("compound_tasks", {})
            self.methods = self.config.get("methods", {})
            self.primitives = (
                {p["id"]: p for p in self.config.get("primitives", [])}
                if self.config.get("primitives")
                else {}
            )
            self.repair_limits = self.config.get("repair_limits", {})
            logger.info("HTN rules loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load HTN rules from {self.rules_path}: {e}")

    @property
    def name(self) -> str:
        return "htn_planner"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        try:
            state = input_data.current_state
            academic_state = state.get("academic_state", {})
            empathy_state = state.get("empathy_state", {})

            # Safe dict for evaluation
            context = {
                "entropy": academic_state.get("entropy", 0.0),
                "fatigue": empathy_state.get("fatigue", 0.0),
                "confusion": empathy_state.get("confusion", 0.0),
            }

            # Get next primitive from tree
            next_task = self._get_next_action(context)
            if next_task and next_task in self.primitives:
                return self._execute_primitive(next_task, context)

            return AgentOutput(
                action="plan_generated",
                payload={"tasks": [], "context": context},
                confidence=0.9,
            )

        except Exception as e:
            logger.error(f"[{self.name}] process error: {e}")
            return AgentOutput(action="fallback_action", payload={"error": str(e)})

    def _select_method(self, task_id: str, context: Dict[str, Any]) -> Optional[str]:
        methods_to_check = []
        if task_id == self.root_task_id:
            methods_to_check = list(self.methods.keys())
        elif task_id in self.compound_tasks:
            methods_to_check = self.compound_tasks[task_id].get("methods", [])

        for method_id in methods_to_check:
            # Methods can be globally defined or we might just use the string identifier
            method_config = self.methods.get(method_id, {})
            # If the method config does not exist at top-level, it might not have preconditions
            preconditions = method_config.get("preconditions")

            if not preconditions:
                return method_id  # If no preconditions, naturally select it

            if self._eval_preconditions(preconditions, context):
                return method_id

        return None

    def _eval_preconditions(
        self, precondition_str: str, context: Dict[str, Any]
    ) -> bool:
        try:
            return safe_eval_precondition(precondition_str, context)
        except Exception as e:
            logger.error(f"Error evaluating precondition '{precondition_str}': {e}")
            return False

    def _get_next_action(self, context: Dict[str, Any]) -> Optional[str]:
        # Minimal mock traversal to find next action
        method = self._select_method(self.root_task_id, context)
        if method:
            seq = self.methods.get(method, {}).get("sequence", [])
            if seq:
                # Pick first task in sequence as mock execution
                first_task = seq[0]
                sub_method = self._select_method(first_task, context)
                return sub_method if sub_method else first_task
        return None

    def repair_plan(
        self, failed_task: str, current_method: str, context: Dict[str, Any]
    ) -> Tuple[str, bool]:
        """
        Trả về: (new_method, should_continue)
        """
        retry_key = f"{failed_task}_retries"
        retries = context.get(retry_key, 0)

        limit = self.repair_limits.get("max_retries_per_node", 2)

        if retries < limit:
            fallback_map = {
                "M03_info_gain_drill": "M03_q_policy_drill",
                "M04_hint_first": "M04_direct_drill",
                "M02_quick_mcq": "M04_hint_first",
            }
            new_method = fallback_map.get(current_method, "M05_empathy_check")
            context[retry_key] = retries + 1
            return new_method, True
        else:
            return "hitl_escalation", False

    async def generate_dynamic_plan(
        self,
        session_id: str,
        context: Dict[str, Any],
        llm_service: Any,
    ) -> List[str]:
        """Generate a short dynamic action plan using LLM, with deterministic fallback."""
        del session_id

        prompt = f"""Plan 3-5 next tutoring actions as JSON array.

Student context:
- confidence: {float(context.get('confidence', 0.0) or 0.0):.2f}
- confusion: {float(context.get('confusion', 0.0) or 0.0):.2f}
- fatigue: {float(context.get('fatigue', 0.0) or 0.0):.2f}
- entropy: {float(context.get('entropy', 1.0) or 1.0):.2f}
- top_hypothesis: {context.get('top_hypothesis', 'unknown')}
- accuracy_recent: {float(context.get('accuracy_recent', 0.0) or 0.0):.2f}
- step: {int(context.get('step', 0) or 0)}

Allowed actions only:
["next_question", "show_hint", "drill_practice", "de_stress", "hitl"]

Rules:
- If fatigue > 0.7, first action should be de_stress.
- If accuracy_recent < 0.3, include drill_practice before next_question.
- Avoid more than 2 consecutive drill_practice.
- End with next_question when possible.

Return JSON array only.
"""

        try:
            if llm_service is None or getattr(llm_service, "model", None) is None:
                raise ValueError("LLM service is unavailable")

            response = llm_service.model.generate_content(
                prompt,
                generation_config={"temperature": 0.3, "max_output_tokens": 256},
            )
            text = str(getattr(response, "text", "") or "").strip()
            parsed = json.loads(text)

            if isinstance(parsed, list):
                normalized = self._normalize_dynamic_plan(
                    parsed,
                    context=context,
                    max_length=5,
                )
                if normalized:
                    return normalized[:5]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dynamic HTN plan generation failed: %s", exc)

        return ["next_question", "show_hint", "next_question"]

    def _normalize_dynamic_plan(
        self,
        raw_plan: List[Any],
        context: Dict[str, Any],
        max_length: int = 5,
    ) -> List[str]:
        allowed = {
            "next_question",
            "show_hint",
            "drill_practice",
            "de_stress",
            "hitl",
        }
        normalized: List[str] = []
        for item in raw_plan:
            action = str(item).strip()
            if action in allowed:
                normalized.append(action)

        if not normalized:
            return []

        max_len = max(1, int(max_length or 5))
        normalized = normalized[:max_len]

        # Enforce no more than 2 consecutive drill_practice actions.
        checked: List[str] = []
        drill_streak = 0
        for action in normalized:
            if action == "drill_practice":
                drill_streak += 1
                if drill_streak > 2:
                    checked.append("next_question")
                    drill_streak = 0
                    continue
            else:
                drill_streak = 0
            checked.append(action)
        normalized = checked

        fatigue = float(context.get("fatigue", 0.0) or 0.0)
        if fatigue > 0.7 and normalized[0] != "de_stress":
            normalized.insert(0, "de_stress")

        accuracy_recent = float(context.get("accuracy_recent", 0.0) or 0.0)
        if accuracy_recent < 0.3:
            next_idx = next(
                (idx for idx, action in enumerate(normalized) if action == "next_question"),
                None,
            )
            if next_idx is not None and "drill_practice" not in normalized[:next_idx]:
                normalized.insert(next_idx, "drill_practice")

        if normalized[-1] != "next_question":
            normalized.append("next_question")

        return normalized[:max_len]

    def _execute_primitive(self, task_id: str, context: Dict[str, Any]) -> AgentOutput:
        # Map ID to backend call action
        mapping = {
            "P01_serve_mcq": "serve_mcq",
            "P02_record_response": "record_response",
            "P03_update_beliefs": "update_beliefs",
            "P04_select_next_question": "select_next_question",
            "P05_generate_hint": "generate_hint",
            "P06_deliver_hint": "deliver_hint",
            "P07_start_drill": "start_drill",
            "P08_check_fatigue": "check_fatigue",
            "P09_trigger_de_stress": "trigger_de_stress",
            "P12_trigger_hitl": "trigger_hitl",
        }
        mapped_action = mapping.get(task_id, task_id)
        return AgentOutput(
            action=mapped_action, payload={"task_id": task_id, "status": "executed"}
        )


htn_planner = HTNPlanner()
