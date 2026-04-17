"""Periodic self-reflection for strategy adjustment."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger("agents.reflection_engine")

REFLECTION_PROMPT = """You are GrowMate reflective tutor.
Review the last {n} interactions and return JSON only.

History:
{history_summary}

Current state:
- beliefs: {beliefs}
- confusion: {confusion:.2f}
- fatigue: {fatigue:.2f}
- accuracy_recent: {accuracy:.0%}
- step: {step}

Output JSON schema:
{{
  "effectiveness": "effective|neutral|ineffective",
  "entropy_trend": "decreasing|stable|increasing",
  "accuracy_trend": "improving|stable|declining",
  "emotion_trend": "improving|stable|worsening",
  "should_change_strategy": true,
  "recommendation": "...",
  "priority_action": "next_question|show_hint|drill_practice|de_stress|hitl",
  "reasoning": "..."
}}
"""


class ReflectionEngine:
    def __init__(
        self,
        llm_service: Any,
        memory_store: Any,
        state_manager: Any,
        interval: int = 5,
    ):
        self.llm = llm_service
        self.memory = memory_store
        self.state_mgr = state_manager
        self.interval = max(1, int(interval))

    async def maybe_reflect(
        self,
        session_id: str,
        current_step: int,
    ) -> Optional[dict[str, Any]]:
        if current_step < self.interval:
            return None
        if current_step % self.interval != 0:
            return None

        try:
            state = await self.state_mgr.load_or_init(session_id)
            history = await self.memory.get_recent_episodes(
                session_id=session_id,
                limit=self.interval,
            )

            correct_count = 0
            lines: list[str] = []
            for episode in history:
                if not isinstance(episode, dict):
                    continue
                outcome = episode.get("outcome", {})
                if isinstance(outcome, dict) and bool(
                    outcome.get("is_correct", outcome.get("correct", False))
                ):
                    correct_count += 1

                action = str(episode.get("action", "unknown"))
                reward = float(episode.get("reward", 0.0) or 0.0)
                lines.append(f"- action={action} reward={reward:.2f}")

            accuracy = (correct_count / len(history)) if history else 0.0

            prompt = REFLECTION_PROMPT.format(
                n=self.interval,
                history_summary="\n".join(lines) if lines else "- no history",
                beliefs=state.academic_state.get("belief_dist", {}),
                confusion=float(state.empathy_state.get("confusion", 0.0) or 0.0),
                fatigue=float(state.empathy_state.get("fatigue", 0.0) or 0.0),
                accuracy=accuracy,
                step=current_step,
            )

            response = await asyncio.to_thread(
                lambda: self.llm.model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.2, "max_output_tokens": 512},
                )
            )

            text = str(getattr(response, "text", "") or "").strip()
            reflection = self._parse_reflection(text)

            log_reflection = getattr(self.memory, "log_reflection", None)
            if callable(log_reflection):
                await log_reflection(
                    session_id=session_id,
                    step=current_step,
                    reflection=reflection,
                )

            if reflection.get("should_change_strategy"):
                state.strategy_state["reflection_override"] = reflection.get("priority_action")
                state.strategy_state["reflection_reasoning"] = reflection.get("reasoning", "")
                state.strategy_state["reflection_updated_at_step"] = current_step

            return reflection
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reflection failed for session=%s: %s", session_id, exc)
            return None

    def _parse_reflection(self, text: str) -> dict[str, Any]:
        if not text:
            return {
                "effectiveness": "neutral",
                "should_change_strategy": False,
                "reasoning": "empty reflection output",
            }

        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                payload = json.loads(text[start:end])
                if isinstance(payload, dict):
                    payload.setdefault("effectiveness", "neutral")
                    payload.setdefault("should_change_strategy", False)
                    payload.setdefault("reasoning", "reflection parsed")
                    return payload
        except Exception:  # noqa: BLE001
            logger.warning("Unable to parse reflection JSON")

        return {
            "effectiveness": "neutral",
            "should_change_strategy": False,
            "reasoning": text[:300],
        }
