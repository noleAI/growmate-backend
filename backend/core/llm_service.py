"""
LLMService — upgraded to google-genai SDK (Vertex AI backend).

Migration from deprecated `vertexai` SDK to `google-genai` SDK as recommended
by Google (see https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk).

Public API (unchanged so existing callers keep working):
  - generate_tutor_response(agent_decision, question_context) -> dict
  - generate(prompt, fallback) -> LLMResponseBase          [async]
  - generate_chat_response(system_prompt, history, user_message, ...) -> str  [async]
"""

from __future__ import annotations

import asyncio
import inspect
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


class _LegacyModelAdapter:
    """Expose a `generate_content` API compatible with legacy tests/callers."""

    def __init__(self, client: Any, model_name: str) -> None:
        self._client = client
        self._model_name = model_name

    def generate_content(
        self,
        contents: Any,
        generation_config: dict[str, Any] | None = None,
        tools: list | None = None,
    ) -> Any:
        from google.genai import types as genai_types  # type: ignore[import]

        config_kwargs = dict(generation_config or {})
        if tools is not None:
            config_kwargs["tools"] = tools

        config = (
            genai_types.GenerateContentConfig(**config_kwargs)
            if config_kwargs
            else None
        )

        return self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )


class LLMService:
    """Thin wrapper around google-genai SDK (Vertex AI backend)."""

    def __init__(self) -> None:
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID", "")
        self.gcp_location = os.getenv("GCP_LOCATION", "us-central1")
        self.model_name = os.getenv("VERTEX_MODEL_NAME", "gemini-2.5-flash")
        self._client: Any = None
        self.model: Any = None
        self._init_error: str | None = None

        try:
            if not self.gcp_project_id:
                raise ValueError("Missing GCP_PROJECT_ID environment variable")

            import google.genai as genai  # type: ignore[import]

            self._client = genai.Client(
                vertexai=True,
                project=self.gcp_project_id,
                location=self.gcp_location,
            )
            # Keep a legacy-compatible model object used by historical tests.
            self.model = _LegacyModelAdapter(self._client, self.model_name)
            logger.info(
                "google-genai client initialized: project=%s location=%s model=%s",
                self.gcp_project_id,
                self.gcp_location,
                self.model_name,
            )
        except Exception as exc:  # noqa: BLE001
            self._init_error = str(exc)
            logger.exception("google-genai initialization failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _ready(self) -> bool:
        return self._client is not None

    def _fallback_response(self, agent_decision: dict) -> dict:
        """Static fallback — returned when the model is unavailable."""
        return {
            "message_to_student": "Hệ thống đang bận. Bạn nghỉ 5 phút rồi thử lại nhé!",
            "ui_action": agent_decision.get("ui_action", "show_break"),
        }

    def _call_model(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_mime_type: str | None = None,
        tools: list | None = None,
        image_bytes: bytes | None = None,
        image_mime_type: str = "image/jpeg",
    ) -> str:
        """Synchronous model call — run inside asyncio.to_thread.
        Supports multimodal (vision) requests when image_bytes is provided."""
        from google.genai import types as genai_types  # type: ignore[import]

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type
        if tools:
            config_kwargs["tools"] = tools

        # Build content — multimodal if image provided
        if image_bytes is not None:
            contents = [
                genai_types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=image_mime_type,
                ),
                genai_types.Part.from_text(text=prompt),
            ]
        else:
            contents = prompt

        response = self._client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=genai_types.GenerateContentConfig(**config_kwargs),
        )
        return (response.text or "").strip()

    # ------------------------------------------------------------------
    # Tutor response — used by orchestrator
    # ------------------------------------------------------------------

    def generate_tutor_response(
        self, agent_decision: dict, question_context: dict
    ) -> dict:
        """
        Generate a short tutor message for the orchestrator.
        Returns dict with "message_to_student" and "ui_action".
        """
        if not self._ready:
            logger.warning("Client not initialized (%s), using fallback.", self._init_error)
            return self._fallback_response(agent_decision)

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
            raw_text = self._call_model(
                prompt,
                temperature=0.3,
                max_tokens=256,
                response_mime_type="application/json",
            )
            if not raw_text:
                raise ValueError("Empty response from model")

            parsed = json.loads(raw_text)
            if not isinstance(parsed, dict):
                raise ValueError("Model output is not a JSON object")
            if "message_to_student" not in parsed or "ui_action" not in parsed:
                raise ValueError(f"Missing required keys: {list(parsed.keys())}")

            return {
                "message_to_student": str(parsed["message_to_student"]),
                "ui_action": parsed.get("ui_action", ui_action),
            }

        except json.JSONDecodeError as exc:
            logger.error("JSON decode error: %s", exc)
            return self._fallback_response(agent_decision)
        except Exception as exc:  # noqa: BLE001
            logger.exception("generate_tutor_response failed: %s", exc)
            return self._fallback_response(agent_decision)

    # ------------------------------------------------------------------
    # Free chatbot — system prompt + history + Google Search grounding
    # ------------------------------------------------------------------

    async def generate_chat_response(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        fallback: str = "Xin lỗi, mình chưa thể trả lời lúc này. Bạn thử lại sau nhé! 🙏",
        use_search: bool = True,
    ) -> str:
        """
        Generate a free-form chat reply with optional Google Search grounding.

        Args:
            system_prompt: Content policy / persona instructions.
            history: [{"role": "user"|"assistant", "content": str}, ...].
            user_message: Latest user message.
            fallback: Returned when the model is unavailable.
            use_search: Enable Google Search grounding (default True).
        """
        if not self._ready:
            logger.warning("Client not initialized (%s), returning fallback.", self._init_error)
            return fallback

        # Build prompt
        history_text = ""
        for turn in history:
            role_label = "Học sinh" if turn.get("role") == "user" else "GrowMate AI"
            history_text += f"{role_label}: {turn.get('content', '')}\n"

        full_prompt = (
            f"{system_prompt}\n\n"
            f"--- Lịch sử hội thoại ---\n"
            f"{history_text}"
            f"Học sinh: {user_message}\n"
            f"GrowMate AI:"
        )

        # Build search tool if requested
        tools: list | None = None
        if use_search:
            try:
                from google.genai import types as genai_types  # type: ignore[import]
                tools = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
                logger.debug("Google Search grounding enabled.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not build search tool: %s", exc)

        try:
            raw = await asyncio.to_thread(
                self._call_model,
                full_prompt,
                temperature=0.7,
                max_tokens=1024,
                tools=tools,
            )
            if not raw:
                raise ValueError("Empty response from model")
            logger.info(
                "Chat response generated%s.",
                " with Google Search" if tools else "",
            )
            return raw
        except Exception as exc:  # noqa: BLE001
            logger.exception("generate_chat_response failed: %s", exc)
            return fallback

    # ------------------------------------------------------------------
    # Vision chatbot — image + text → answer
    # ------------------------------------------------------------------

    async def generate_chat_response_with_image(
        self,
        system_prompt: str,
        user_message: str,
        image_bytes: bytes,
        image_mime_type: str = "image/jpeg",
        fallback: str = "Xin lỗi, mình chưa thể phân tích ảnh lúc này. Bạn thử lại sau nhé! 🙏",
    ) -> str:
        """
        Analyze an image and respond to the user's question about it.

        Args:
            system_prompt: Content policy / persona instructions.
            user_message: User's question about the image.
            image_bytes: Raw image bytes (JPEG/PNG/WEBP/GIF).
            image_mime_type: MIME type of the image.
            fallback: Returned when the model is unavailable.
        """
        if not self._ready:
            logger.warning("Client not initialized (%s), returning fallback.", self._init_error)
            return fallback

        vision_prompt = (
            f"{system_prompt}\n\n"
            f"Học sinh gửi một bức ảnh và hỏi: {user_message}\n\n"
            f"Hãy phân tích nội dung trong ảnh và trả lời câu hỏi của học sinh một cách chi tiết, "
            f"dễ hiểu. Nếu ảnh chứa bài tập, hãy gợi ý phương pháp giải (không đưa đáp án thẳng). "
            f"Nếu ảnh không liên quan đến học tập, hãy từ chối lịch sự.\n\n"
            f"GrowMate AI:"
        )

        try:
            raw = await asyncio.to_thread(
                self._call_model,
                vision_prompt,
                temperature=0.5,
                max_tokens=1500,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
            )
            if not raw:
                raise ValueError("Empty response from model")
            logger.info("Vision chat response generated successfully.")
            return raw
        except Exception as exc:  # noqa: BLE001
            logger.exception("generate_chat_response_with_image failed: %s", exc)
            return fallback

    # ------------------------------------------------------------------
    # Async wrapper — used by orchestrator (non-blocking)
    # ------------------------------------------------------------------

    async def generate(self, prompt: str, fallback: str) -> LLMResponseBase:
        """Async wrapper for orchestrator — runs tutor response in thread pool."""
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

        reasoning_timeout_ms = self._resolve_timeout_ms(
            override=timeout_ms,
            env_name="AGENTIC_TIMEOUT_MS",
            default=8000,
        )
        tool_call_timeout_ms = self._resolve_timeout_ms(
            override=tool_timeout_ms,
            env_name="AGENTIC_TOOL_TIMEOUT_MS",
            default=reasoning_timeout_ms,
        )

        prompt = "\n\n".join(
            [
                AGENTIC_SYSTEM_PROMPT,
                "Du lieu nguoi hoc:\n" + self._format_student_input(student_input),
            ]
        )
        reasoning_trace: list[dict[str, Any]] = []
        gemini_tools = self._build_gemini_tools(tool_registry)

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._invoke_model,
                    prompt,
                    generation_config={
                        "temperature": 0.3,
                        "max_output_tokens": 1024,
                    },
                    tools=gemini_tools,
                ),
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

            # Keep deterministic behavior by executing the first tool call only.
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
                return self._agentic_fallback(
                    f"Unknown tool: {tool_name}",
                    reasoning_trace,
                )

            if self._tool_requires_session_id(tool_registry, tool_name):
                # Security hardening: always enforce the caller session_id.
                tool_args["session_id"] = session_id

            try:
                tool_result = await asyncio.wait_for(
                    self._execute_tool(tool_registry, tool_name, tool_args),
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
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tool execution failed for tool=%s error=%s", tool_name, exc)
                return self._agentic_fallback(
                    f"Tool error: {tool_name}",
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

            followup_contents = self._build_followup_contents(
                prompt=prompt,
                tool_name=tool_name,
                tool_result=tool_result,
            )

            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._invoke_model,
                        followup_contents,
                        generation_config={
                            "temperature": 0.2,
                            "max_output_tokens": 1024,
                        },
                        tools=gemini_tools,
                    ),
                    timeout=reasoning_timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                logger.warning("Agentic follow-up call timed out after %sms", reasoning_timeout_ms)
                return self._agentic_fallback(
                    "Agentic follow-up call timed out",
                    reasoning_trace,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agentic follow-up call failed: %s", exc)
                return self._agentic_fallback(str(exc), reasoning_trace)

        return {
            **self._agentic_fallback("Reached max reasoning steps"),
            "reasoning_trace": reasoning_trace,
            "llm_steps": step,
        }

    def _resolve_timeout_ms(
        self,
        *,
        override: int | None,
        env_name: str,
        default: int,
    ) -> int:
        if override is not None:
            return max(1, int(override))

        raw = os.getenv(env_name)
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                logger.warning("Invalid %s value '%s', fallback to %s", env_name, raw, default)

        return max(1, int(default))

    def _build_gemini_tools(self, tool_registry: "ToolRegistry") -> list | None:
        to_gemini_tools = getattr(tool_registry, "to_gemini_tools", None)
        if callable(to_gemini_tools):
            try:
                return to_gemini_tools()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to build Gemini tools from registry: %s", exc)
        return None

    def _invoke_model(
        self,
        contents: Any,
        *,
        generation_config: dict[str, Any] | None = None,
        tools: list | None = None,
    ) -> Any:
        if self.model is None:
            raise RuntimeError("Model is not initialized")

        kwargs: dict[str, Any] = {}
        if generation_config is not None:
            kwargs["generation_config"] = generation_config
        if tools is not None:
            kwargs["tools"] = tools

        try:
            return self.model.generate_content(contents, **kwargs)
        except TypeError:
            # Compatibility path for fake models in tests with simpler signatures.
            if generation_config is not None:
                try:
                    return self.model.generate_content(contents, generation_config)
                except TypeError:
                    return self.model.generate_content(contents)
            return self.model.generate_content(contents)

    async def _execute_tool(
        self,
        tool_registry: "ToolRegistry",
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> Any:
        execute = getattr(tool_registry, "execute", None)
        if not callable(execute):
            raise RuntimeError("Tool registry does not provide execute()")

        if inspect.iscoroutinefunction(execute):
            return await execute(tool_name, **tool_args)

        result = await asyncio.to_thread(execute, tool_name, **tool_args)
        if inspect.isawaitable(result):
            return await result
        return result

    def _tool_requires_session_id(
        self,
        tool_registry: "ToolRegistry",
        tool_name: str,
    ) -> bool:
        tool = tool_registry.get(tool_name)
        if tool is None:
            return False

        parameters = getattr(tool, "parameters", None)
        if parameters is None and isinstance(tool, dict):
            parameters = tool.get("parameters")
        if not isinstance(parameters, dict):
            return False

        properties = parameters.get("properties")
        return isinstance(properties, dict) and "session_id" in properties

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

    def _build_followup_contents(
        self,
        *,
        prompt: str,
        tool_name: str,
        tool_result: Any,
    ) -> Any:
        result_json = json.dumps(tool_result, ensure_ascii=False, default=str)

        try:
            from google.genai import types as genai_types  # type: ignore[import]

            return [
                prompt,
                genai_types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result_json},
                ),
            ]
        except Exception:
            return [
                prompt,
                f"Tool {tool_name} returned: {result_json}",
            ]

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
