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
