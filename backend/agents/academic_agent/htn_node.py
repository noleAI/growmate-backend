"""
HTN Node: FSM-based execution node for the HTN Planner.

State transitions follow HTN_MODEL.md:
  Pending → CheckPreconditions → Executing → EvaluateOutcome → Success/Failed → Completed
  Failed → Repairing → RetryNode(Pending) | Escalating(HITL)
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger("htn_node")


class NodeState(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    REPAIRING = "repairing"
    ESCALATING = "escalating"
    COMPLETED = "completed"


class HTNNode(BaseModel):
    task_id: str
    task_type: str  # 'primitive' or 'compound'
    preconditions: Optional[str] = None
    method_sequence: List[str] = []
    max_retries: int = 2
    state: NodeState = NodeState.PENDING
    retry_count: int = 0
    current_method: Optional[str] = None
    repair_log: List[Dict[str, Any]] = []

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute this node through its FSM lifecycle.
        Pending → CheckPreconditions → Executing → EvaluateOutcome
        """
        logger.info(f"[HTN FSM] {self.task_id} {self.state} → checking preconditions")

        # Step 1: Check Preconditions
        if not self._check_preconditions(context):
            self.state = NodeState.REPAIRING
            logger.info(
                f"[HTN FSM] {self.task_id} PENDING → REPAIRING (preconditions failed)"
            )
            return await self._handle_repair(context)

        # Step 2: Execute
        self.state = NodeState.EXECUTING
        logger.info(f"[HTN FSM] {self.task_id} PENDING → EXECUTING")
        exec_result = await self._execute_primitive(context)

        # Step 3: Evaluate Outcome
        if exec_result.get("status") == "success":
            self.state = NodeState.SUCCESS
            logger.info(f"[HTN FSM] {self.task_id} EXECUTING → SUCCESS")
            return exec_result
        else:
            # Unexpected outcome → Repairing
            self.state = NodeState.REPAIRING
            self.retry_count += 1
            logger.info(
                f"[HTN FSM] {self.task_id} EXECUTING → REPAIRING"
                f" (retry_count={self.retry_count})"
            )
            return await self._handle_repair(context)

    def _check_preconditions(self, context: Dict[str, Any]) -> bool:
        """Evaluate preconditions string against context."""
        if not self.preconditions:
            return True
        from agents.academic_agent.htn_utils import safe_eval_precondition

        return safe_eval_precondition(self.preconditions, context)

    async def _execute_primitive(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the primitive task. Override or mock in tests."""
        from agents.academic_agent.htn_executor import execute_primitive

        if self.method_sequence:
            task_id = self.method_sequence[0]
            return await execute_primitive(task_id, context)
        return {"status": "failed", "error": "No tasks in sequence"}

    async def _handle_repair(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempt repair: swap method if under retry limit, else escalate.
        """
        if self.retry_count >= self.max_retries:
            # Escalate to HITL
            self.state = NodeState.ESCALATING
            logger.info(
                f"[HTN FSM] {self.task_id} REPAIRING → ESCALATING"
                f" (retry_count={self.retry_count} >= max={self.max_retries})"
            )
            return await self._trigger_hitl(context)

        # Select repair strategy
        strategy = self._select_repair_strategy(context)
        self.repair_log.append(
            {
                "retry": self.retry_count,
                "strategy": strategy,
                "reason": "Unexpected",
            }
        )

        # Apply repair
        repaired = self._apply_repair(context)
        if repaired:
            self.retry_count += 1
            logger.info(f"[HTN FSM] {self.task_id} REPAIRING → PENDING (retry)")
            # Retry by re-running
            self.state = NodeState.PENDING
            return await self.run(context)
        else:
            # Repair failed, escalate
            self.state = NodeState.ESCALATING
            return await self._trigger_hitl(context)

    def _select_repair_strategy(self, context: Dict[str, Any]) -> str:
        """Select repair strategy based on available fallbacks."""
        fallback_map = context.get(
            "FALLBACK_METHOD_MAP",
            {
                "M03_info_gain_drill": "M03_q_policy_drill",
                "M04_hint_first": "M04_direct_drill",
                "M02_quick_mcq": "M04_hint_first",
            },
        )
        if self.method_sequence:
            current = self.method_sequence[0]
            if current in fallback_map:
                return "AltMethod"
        return "InsertTask"

    def _apply_repair(self, context: Dict[str, Any]) -> bool:
        """
        Apply the repair: swap current method to its fallback.
        Returns True if repair was applied, False otherwise.
        """
        fallback_map = context.get(
            "FALLBACK_METHOD_MAP",
            {
                "M03_info_gain_drill": "M03_q_policy_drill",
                "M04_hint_first": "M04_direct_drill",
                "M02_quick_mcq": "M04_hint_first",
            },
        )
        if self.method_sequence:
            current = self.method_sequence[0]
            new_method = fallback_map.get(current)
            if new_method:
                self.method_sequence[0] = new_method
                self.current_method = new_method
                return True
        return False

    async def _trigger_hitl(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push session to HITL queue and wait for timeout.
        Falls back to P09_trigger_de_stress on timeout.
        """
        import asyncio

        hitl_client = context.get("hitl_client")
        if hitl_client:
            await hitl_client.push(
                {
                    "task_id": self.task_id,
                    "retry_count": self.retry_count,
                    "state": self.state.value,
                }
            )

        # Wait for HITL timeout (3s)
        await asyncio.sleep(3)

        return {
            "status": "hitl_escalated",
            "payload": {"fallback": "P09_trigger_de_stress"},
        }
