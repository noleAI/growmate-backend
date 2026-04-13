"""
HTN Executor: Primitive task dispatch registry.

Maps primitive task IDs (P01–P12) to async handler functions.
Provides execute_primitive() as the single dispatch entry point.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

logger = logging.getLogger("htn_executor")

# Type alias for primitive handlers
PrimitiveHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


# ---------------------------------------------------------------------------
# Default primitive stubs (placeholder implementations)
# Each returns {"status": "success", "payload": {...}} or raises on error.
# Replace with real backend calls as they are implemented.
# ---------------------------------------------------------------------------


async def _serve_mcq(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "payload": {"q_id": ctx.get("question_id", "q_default")},
    }


async def _record_response(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"recorded": True}}


async def _update_beliefs(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"entropy": ctx.get("entropy", 0.5)}}


async def _select_next_question(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"question_id": "q_next"}}


async def _generate_hint(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "payload": {"hint_text": "Try applying the chain rule step by step."},
    }


async def _deliver_hint(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"delivered": True}}


async def _start_drill(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"drill_session_id": "drill_001"}}


async def _check_fatigue(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"fatigue": ctx.get("fatigue", 0.3)}}


async def _trigger_de_stress(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"pause_active": True}}


async def _log_plan_step(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"log_id": "log_001"}}


async def _backtrack_repair(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"repaired": True}}


async def _trigger_hitl(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "payload": {"hitl_status": "pending"}}


# ---------------------------------------------------------------------------
# PRIMITIVE_REGISTRY: the authoritative mapping of task IDs → handlers
# ---------------------------------------------------------------------------

PRIMITIVE_REGISTRY: Dict[str, PrimitiveHandler] = {
    "P01_serve_mcq": _serve_mcq,
    "P02_record_response": _record_response,
    "P03_update_beliefs": _update_beliefs,
    "P04_select_next_question": _select_next_question,
    "P05_generate_hint": _generate_hint,
    "P06_deliver_hint": _deliver_hint,
    "P07_start_drill": _start_drill,
    "P08_check_fatigue": _check_fatigue,
    "P09_trigger_de_stress": _trigger_de_stress,
    "P10_log_plan_step": _log_plan_step,
    "P11_backtrack_repair": _backtrack_repair,
    "P12_trigger_hitl": _trigger_hitl,
}


async def execute_primitive(task_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch a primitive task by ID.

    Args:
        task_id: The primitive task identifier (e.g. "P01_serve_mcq").
        context: Runtime context dict passed to the handler.

    Returns:
        Dict with at least {"status": "success"|"failed", ...}
    """
    handler = PRIMITIVE_REGISTRY.get(task_id)
    if handler is None:
        logger.error(f"Unknown primitive task: {task_id}")
        return {"status": "failed", "error": f"Unknown primitive: {task_id}"}

    try:
        result = await handler(context)
        logger.info(f"[HTN Executor] {task_id} → {result.get('status', 'unknown')}")
        return result
    except Exception as e:
        logger.error(f"[HTN Executor] {task_id} raised exception: {e}")
        return {"status": "failed", "error": str(e)}
