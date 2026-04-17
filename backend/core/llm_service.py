import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.tool_registry import ToolRegistry


AGENTIC_SYSTEM_PROMPT = """Ban la gia su AI GrowMate cho hoc sinh Toan THPT Viet Nam.

Muc tieu:
- Khong doan mo, luon goi tool de lay du lieu truoc khi quyet dinh.
- Chon action tiep theo dua tren tri thuc hoc tap + trang thai cam xuc.
- Tao noi dung ngan gon, than thien, ca nhan hoa.

Quy trinh uu tien:
1. Goi get_academic_beliefs
2. Goi get_empathy_state
3. Co the goi get_strategy_suggestion, get_student_history, get_formula_bank, search_knowledge
4. Chon action cuoi cung

Actions hop le:
- next_question
- show_hint
- drill_practice
- de_stress
- hitl

Quy tac:
- fatigue >= 0.8 thi uu tien de_stress.
- confusion >= 0.7 va entropy cao thi uu tien show_hint.
- accuracy thap trong lich su gan day thi uu tien drill_practice.
- Neu khong chac chan, co the chon hitl.

Tra ve JSON:
{
    "action": "<action>",
    "content": "<noi dung cho hoc sinh>",
    "reasoning": "<ly do ngan>",
    "confidence": <0.0-1.0>
}
"""


class LLMResponseBase(BaseModel):
    text: str
    fallback_used: bool = False


class LLMService:
    def __init__(self):
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID", "")
        self.gcp_location = os.getenv("GCP_LOCATION", "us-central1")
        self.model_name = os.getenv("VERTEX_MODEL_NAME", "gemini-2.5-flash")
        self.model: Any = None
        self._init_error: str | None = None

        try:
            if not self.gcp_project_id:
                raise ValueError("Missing GCP_PROJECT_ID environment variable")

            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(project=self.gcp_project_id, location=self.gcp_location)
            self.model = GenerativeModel(self.model_name)
            logger.info(
                "Vertex AI initialized: project=%s location=%s model=%s",
                self.gcp_project_id,
                self.gcp_location,
                self.model_name,
            )
        except Exception as exc:  # noqa: BLE001
            self._init_error = str(exc)
            logger.exception("Vertex AI initialization failed: %s", exc)

    # ------------------------------------------------------------------
    # Static fallback — trả về khi API lỗi, bảo vệ hệ thống
    # ------------------------------------------------------------------
    def _fallback_response(self, agent_decision: dict) -> dict:
        return {
            "message_to_student": "Hệ thống đang bận. Bạn nghỉ 5 phút rồi thử lại nhé!",
            "ui_action": agent_decision.get("ui_action", "show_break"),
        }

    # ------------------------------------------------------------------
    # Hàm chính
    # ------------------------------------------------------------------
    def generate_tutor_response(
        self, agent_decision: dict, question_context: dict
    ) -> dict:
        """
        Gọi Vertex AI để tạo phản hồi gia sư GrowMate.

        Args:
            agent_decision: Quyết định từ orchestrator (chứa ui_action, action, ...).
            question_context: Ngữ cảnh câu hỏi / trạng thái học sinh.

        Returns:
            dict với 2 key: "message_to_student" và "ui_action".
        """
        if self.model is None:
            logger.warning("Model not initialized (%s), using fallback.", self._init_error)
            return self._fallback_response(agent_decision)

        # --- Xây dựng prompt ---
        ui_action = agent_decision.get("ui_action", "continue")
        action = agent_decision.get("action", "")
        is_tired = float(question_context.get("fatigue", 0)) >= 0.7

        prompt = f"""Bạn là gia sư GrowMate.
Nguyên tắc bắt buộc:
- Rất ngắn gọn (dưới 30 chữ).
- Xưng 'mình', gọi học sinh là 'bạn'.
- Tuyệt đối KHÔNG giải ra đáp án cuối cùng. Chỉ gợi ý phương pháp.
- Nếu học sinh đang mệt (fatigue cao), hãy khuyên nghỉ ngơi ngắn.

Trạng thái học sinh:
{json.dumps(question_context, ensure_ascii=False, indent=2)}

Quyết định hệ thống:
- action: {action}
- ui_action: {ui_action}
- Học sinh đang mệt: {is_tired}

Hãy trả về JSON với đúng 2 key:
{{
  "message_to_student": "<lời nhắn ngắn cho học sinh>",
  "ui_action": "{ui_action}"
}}
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )

            raw_text = (getattr(response, "text", "") or "").strip()
            if not raw_text:
                raise ValueError("Empty response from Vertex AI")

            parsed = json.loads(raw_text)

            if not isinstance(parsed, dict):
                raise ValueError("Model output is not a JSON object")
            if "message_to_student" not in parsed or "ui_action" not in parsed:
                raise ValueError(f"Missing required keys in response: {list(parsed.keys())}")

            return {
                "message_to_student": str(parsed["message_to_student"]),
                "ui_action": parsed.get("ui_action", ui_action),
            }

        except json.JSONDecodeError as exc:
            logger.error("JSON decode error from Vertex AI response: %s", exc)
            return self._fallback_response(agent_decision)
        except Exception as exc:  # noqa: BLE001
            logger.exception("generate_tutor_response failed: %s", exc)
            return self._fallback_response(agent_decision)

    # ------------------------------------------------------------------
    # Async wrapper — dùng bởi orchestrator (non-blocking)
    # ------------------------------------------------------------------
    async def generate(self, prompt: str, fallback: str) -> LLMResponseBase:
        """
        Async wrapper cho orchestrator.
        Gọi generate_tutor_response trong thread pool để không block event loop.
        """
        agent_decision = {"ui_action": "continue", "action": "legacy_generate"}
        question_context = {"prompt": prompt}

        result = await asyncio.to_thread(
            self.generate_tutor_response, agent_decision, question_context
        )

        message = result.get("message_to_student", "").strip()
        if not message:
            return LLMResponseBase(text=fallback, fallback_used=True)

        return LLMResponseBase(text=message, fallback_used=False)

    async def run_agentic_reasoning(
        self,
        session_id: str,
        student_input: dict[str, Any],
        tool_registry: "ToolRegistry",
        max_steps: int = 5,
        timeout_ms: int | None = None,
        tool_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Run iterative tool-calling reasoning and return a structured decision."""
        if self.model is None:
            return self._agentic_fallback("Model is not initialized")

        reasoning_timeout_ms = max(
            1,
            int(timeout_ms or os.getenv("AGENTIC_TIMEOUT_MS", "8000") or 8000),
        )
        tool_call_timeout_ms = max(
            1,
            int(tool_timeout_ms or os.getenv("AGENTIC_TOOL_TIMEOUT_MS", str(reasoning_timeout_ms)) or reasoning_timeout_ms),
        )

        prompt = "\n\n".join(
            [
                AGENTIC_SYSTEM_PROMPT,
                "Du lieu nguoi hoc:\n" + self._format_student_input(student_input),
            ]
        )
        reasoning_trace: list[dict[str, Any]] = []

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.model.generate_content(
                        prompt,
                        generation_config={
                            "temperature": 0.3,
                            "max_output_tokens": 1024,
                        },
                        tools=tool_registry.to_gemini_tools(),
                    )
                )
                ,
                timeout=reasoning_timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            logger.warning("Initial agentic call timed out after %sms", reasoning_timeout_ms)
            return self._agentic_fallback("Agentic initial call timed out")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Initial agentic call failed: %s", exc)
            return self._agentic_fallback(str(exc))

        step = 0
        while step < max_steps:
            step += 1
            calls = self._extract_function_calls(response)
            if not calls:
                decision = self._parse_agentic_decision(self._extract_text(response))
                decision["reasoning_trace"] = reasoning_trace
                decision["llm_steps"] = step
                return decision

            # Execute the first call only to keep loop deterministic and bounded.
            tool_name, tool_args = calls[0]
            tool = tool_registry.get(tool_name)
            if tool is None:
                reasoning_trace.append(
                    {
                        "step": step,
                        "tool": tool_name,
                        "args": tool_args,
                        "result_summary": f"Tool '{tool_name}' not registered",
                    }
                )
                return self._agentic_fallback(f"Unknown tool: {tool_name}", reasoning_trace)

            tool_args = dict(tool_args)
            if self._tool_requires_session_id(tool_registry, tool_name):
                # Never trust model-supplied session ids; enforce current session context.
                tool_args["session_id"] = session_id

            try:
                tool_result = await asyncio.wait_for(
                    tool_registry.execute(tool_name, **tool_args),
                    timeout=tool_call_timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Tool call timed out for tool=%s after %sms",
                    tool_name,
                    tool_call_timeout_ms,
                )
                return self._agentic_fallback(
                    f"Tool timeout: {tool_name}",
                    reasoning_trace,
                )

            result_summary = str(
                tool_result.get("interpretation")
                if isinstance(tool_result, dict)
                else tool_result
            )

            reasoning_trace.append(
                {
                    "step": step,
                    "tool": tool_name,
                    "args": tool_args,
                    "result_summary": result_summary[:300],
                }
            )

            try:
                from vertexai.generative_models import Part

                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.model.generate_content(
                            [
                                prompt,
                                Part.from_function_response(
                                    name=tool_name,
                                    response={
                                        "result": json.dumps(
                                            tool_result,
                                            ensure_ascii=False,
                                            default=str,
                                        )
                                    },
                                ),
                            ],
                            generation_config={
                                "temperature": 0.2,
                                "max_output_tokens": 1024,
                            },
                            tools=tool_registry.to_gemini_tools(),
                        )
                    )
                    ,
                    timeout=reasoning_timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                logger.warning("Agentic follow-up call timed out after %sms", reasoning_timeout_ms)
                return self._agentic_fallback("Agentic follow-up call timed out", reasoning_trace)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agentic follow-up call failed: %s", exc)
                return self._agentic_fallback(str(exc), reasoning_trace)

        return {
            **self._agentic_fallback("Reached max reasoning steps"),
            "reasoning_trace": reasoning_trace,
            "llm_steps": step,
        }

    def _tool_requires_session_id(
        self,
        tool_registry: "ToolRegistry",
        tool_name: str,
    ) -> bool:
        tool = tool_registry.get(tool_name)
        if tool is None:
            return False
        props = tool.parameters.get("properties", {})
        return isinstance(props, dict) and "session_id" in props

    def _extract_function_calls(self, response: Any) -> list[tuple[str, dict[str, Any]]]:
        calls: list[tuple[str, dict[str, Any]]] = []

        direct_calls = getattr(response, "function_calls", None)
        if isinstance(direct_calls, list):
            for call in direct_calls:
                name = str(getattr(call, "name", "") or "").strip()
                args = self._coerce_args(getattr(call, "args", {}))
                if name:
                    calls.append((name, args))

        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, list):
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    fn_call = getattr(part, "function_call", None)
                    if fn_call is None:
                        continue
                    name = str(getattr(fn_call, "name", "") or "").strip()
                    args = self._coerce_args(getattr(fn_call, "args", {}))
                    if name:
                        calls.append((name, args))

        deduped: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for name, args in calls:
            marker = f"{name}:{json.dumps(args, sort_keys=True, default=str)}"
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append((name, args))
        return deduped

    def _coerce_args(self, raw_args: Any) -> dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args

        if raw_args is None:
            return {}

        items = getattr(raw_args, "items", None)
        if callable(items):
            try:
                return {str(key): value for key, value in items()}
            except Exception:  # noqa: BLE001
                return {}

        try:
            return dict(raw_args)
        except Exception:  # noqa: BLE001
            return {}

    def _extract_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, list):
            collected: list[str] = []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if isinstance(part_text, str) and part_text.strip():
                        collected.append(part_text.strip())
            if collected:
                return "\n".join(collected)

        return ""

    def _format_student_input(self, student_input: dict[str, Any]) -> str:
        question = str(student_input.get("question_text", "N/A"))
        answer = str(student_input.get("student_answer", "N/A"))
        correct = str(student_input.get("correct_answer", ""))
        is_correct = student_input.get("is_correct")

        lines = [
            f"Cau hoi: {question}",
            f"Hoc sinh tra loi: {answer}",
        ]

        if correct:
            lines.append(f"Dap an dung: {correct}")

        if is_correct is not None:
            lines.append(f"Ket qua: {'DUNG' if bool(is_correct) else 'SAI'}")

        signals = student_input.get("behavior_signals")
        if isinstance(signals, dict) and signals:
            response_time_ms = signals.get("response_time_ms")
            idle_ratio = signals.get("idle_time_ratio")
            lines.append(f"response_time_ms={response_time_ms}")
            lines.append(f"idle_time_ratio={idle_ratio}")

        mode = student_input.get("mode")
        if mode:
            lines.append(f"mode={mode}")

        step = student_input.get("step")
        if step is not None:
            lines.append(f"step={step}")

        return "\n".join(lines)

    def _parse_agentic_decision(self, text: str) -> dict[str, Any]:
        if not text:
            return self._agentic_fallback("Empty LLM response")

        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end])
                if isinstance(parsed, dict):
                    parsed.setdefault("action", "next_question")
                    parsed.setdefault(
                        "content",
                        "Hay tiep tuc voi cau tiep theo nhe!",
                    )
                    parsed.setdefault("reasoning", "Structured response parsed")
                    parsed.setdefault("confidence", 0.6)
                    return parsed
        except Exception:  # noqa: BLE001
            logger.warning("Failed to parse structured agentic response")

        valid_actions = [
            "next_question",
            "show_hint",
            "drill_practice",
            "de_stress",
            "hitl",
        ]
        lowered = text.lower()
        for action in valid_actions:
            if action in lowered:
                return {
                    "action": action,
                    "content": text[:400],
                    "reasoning": "Parsed from free text response",
                    "confidence": 0.5,
                }

        return {
            "action": "next_question",
            "content": text[:400],
            "reasoning": "Could not parse structured response",
            "confidence": 0.4,
            "parse_error": True,
        }

    def _agentic_fallback(
        self,
        reason: str,
        reasoning_trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "action": "next_question",
            "content": "Hay thu cau tiep theo nhe!",
            "reasoning": reason,
            "confidence": 0.4,
            "reasoning_trace": reasoning_trace or [],
            "fallback": True,
        }
