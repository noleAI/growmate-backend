import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel

from agents.base import AgentInput, AgentOutput, IAgent

logger = logging.getLogger("htn_planner")


class HTNNode(BaseModel):
    task_id: str
    type: str  # 'primitive' or 'compound'
    status: str = "pending"  # 'pending', 'active', 'success', 'failed'
    retry_count: int = 0
    current_method: Optional[str] = None
    children: List["HTNNode"] = []


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
        if not precondition_str:
            return True
        try:
            # Replace AND/OR for Python eval
            py_cond = precondition_str.replace("AND", "and").replace("OR", "or")
            safe_dict = {"__builtins__": {}}
            safe_dict.update(context)
            result = eval(py_cond, safe_dict)
            return bool(result)
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
            "P10_log_plan_step": "log_plan_step",
            "P11_backtrack_repair": "backtrack_repair",
            "P12_trigger_hitl": "trigger_hitl",
        }
        mapped_action = mapping.get(task_id, task_id)
        return AgentOutput(
            action=mapped_action, payload={"task_id": task_id, "status": "executed"}
        )


htn_planner = HTNPlanner()
