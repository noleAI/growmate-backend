"""Structured ReAct wrapper on top of LLM function-calling reasoning."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("agents.reasoning_loop")


@dataclass
class ReActStep:
    step: int
    action: str = ""
    action_args: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    timestamp_ms: int = 0


@dataclass
class ReActResult:
    action: str
    content: str
    reasoning: str
    confidence: float
    steps: list[ReActStep] = field(default_factory=list)
    latency_ms: int = 0
    fallback_used: bool = False


class ReActEngine:
    """Thin typed wrapper around LLMService.run_agentic_reasoning."""

    MAX_STEPS = 5

    def __init__(self, llm_service: Any, tool_registry: Any):
        self.llm = llm_service
        self.tools = tool_registry

    async def reason(
        self,
        session_id: str,
        student_input: dict[str, Any],
        max_steps: int | None = None,
    ) -> ReActResult:
        start = time.monotonic()
        trace_steps: list[ReActStep] = []

        try:
            result = await self.llm.run_agentic_reasoning(
                session_id=session_id,
                student_input=student_input,
                tool_registry=self.tools,
                max_steps=int(max_steps or self.MAX_STEPS),
            )

            trace = result.get("reasoning_trace", [])
            if isinstance(trace, list):
                for idx, item in enumerate(trace, start=1):
                    if not isinstance(item, dict):
                        continue
                    trace_steps.append(
                        ReActStep(
                            step=idx,
                            action=str(item.get("tool", "")),
                            action_args=item.get("args", {})
                            if isinstance(item.get("args"), dict)
                            else {},
                            observation=str(item.get("result_summary", "")),
                            timestamp_ms=int((time.monotonic() - start) * 1000),
                        )
                    )

            latency_ms = int((time.monotonic() - start) * 1000)
            return ReActResult(
                action=str(result.get("action", "next_question")),
                content=str(result.get("content", "")),
                reasoning=str(result.get("reasoning", "")),
                confidence=float(result.get("confidence", 0.5) or 0.5),
                steps=trace_steps,
                latency_ms=latency_ms,
                fallback_used=bool(result.get("fallback", False)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ReAct reasoning failed: %s", exc)
            latency_ms = int((time.monotonic() - start) * 1000)
            return ReActResult(
                action="next_question",
                content="Hay thu cau tiep theo nhe!",
                reasoning=f"ReAct error: {exc}",
                confidence=0.3,
                steps=trace_steps,
                latency_ms=latency_ms,
                fallback_used=True,
            )
