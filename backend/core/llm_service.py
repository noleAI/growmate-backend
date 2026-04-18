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
import json
import logging
import os
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMResponseBase(BaseModel):
    text: str
    fallback_used: bool = False


class LLMService:
    """Thin wrapper around google-genai SDK (Vertex AI backend)."""

    def __init__(self) -> None:
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID", "")
        self.gcp_location = os.getenv("GCP_LOCATION", "us-central1")
        self.model_name = os.getenv("VERTEX_MODEL_NAME", "gemini-2.5-flash")
        self._client: Any = None
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
