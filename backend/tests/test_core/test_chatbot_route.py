from io import BytesIO

import pytest
from starlette.datastructures import Headers, UploadFile

from api.routes import chatbot as chatbot_route


class _LLMStub:
    def __init__(self) -> None:
        self.last_history: list[dict] | None = None

    async def generate_chat_response(
        self,
        *,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        return_metadata: bool,
    ) -> dict:
        assert system_prompt
        assert user_message == "Giải thích đạo hàm là gì"
        assert return_metadata is True
        self.last_history = history
        return {
            "reply": "Đạo hàm mô tả tốc độ thay đổi của hàm số.",
            "processing": {"used_search": True},
        }

    async def generate_chat_response_with_image(
        self,
        *,
        system_prompt: str,
        user_message: str,
        image_bytes: bytes,
        image_mime_type: str,
        return_metadata: bool,
    ) -> dict:
        assert system_prompt
        assert user_message == "Phân tích ảnh này"
        assert image_bytes == b"png-bytes"
        assert image_mime_type == "image/png"
        assert return_metadata is True
        return {
            "reply": "Đây là đồ thị hàm số bậc hai.",
            "processing": {"image_mime_type": image_mime_type},
        }


@pytest.mark.asyncio
async def test_chat_returns_processing_payload(monkeypatch) -> None:
    llm = _LLMStub()

    async def _usage_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-1"
        return {"call_count": 4}

    async def _history_stub(*args, **kwargs) -> list[dict]:
        del args, kwargs
        return [
            {"role": "user", "content": "Xin chào", "created_at": "2026-04-19T10:00:00+00:00"},
            {"role": "assistant", "content": "Chào bạn", "created_at": "2026-04-19T10:00:01+00:00"},
        ]

    async def _save_stub(*args, **kwargs) -> None:
        del args, kwargs

    async def _increment_stub(**kwargs) -> None:
        del kwargs

    monkeypatch.setattr(chatbot_route, "get_user_token_usage", _usage_stub)
    monkeypatch.setattr(chatbot_route, "_load_recent_history", _history_stub)
    monkeypatch.setattr(chatbot_route, "_save_chat_messages", _save_stub)
    monkeypatch.setattr(chatbot_route, "increment_user_token_usage", _increment_stub)
    monkeypatch.setattr(chatbot_route, "_get_llm", lambda: llm)

    result = await chatbot_route.chat(
        body=chatbot_route.ChatRequest(message="Giải thích đạo hàm là gì"),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result.reply == "Đạo hàm mô tả tốc độ thay đổi của hàm số."
    assert result.remaining_quota == chatbot_route._remaining_quota(4)
    assert result.processing is not None
    assert result.processing.mode == "text"
    assert result.processing.history_source == "database"
    assert "Lịch sử chat" in result.processing.tags
    assert "Google Search" in result.processing.tags
    assert llm.last_history is not None
    assert len(llm.last_history) == 2


@pytest.mark.asyncio
async def test_get_chat_quota_returns_expected_shape(monkeypatch) -> None:
    async def _usage_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-2"
        return {"call_count": 7}

    monkeypatch.setattr(chatbot_route, "get_user_token_usage", _usage_stub)

    result = await chatbot_route.get_chat_quota(
        user={"sub": "student-2"},
        access_token="token",
    )

    assert result["used"] == 7
    assert result["limit"] >= 7
    assert result["remaining"] == max(0, result["limit"] - 7)
    assert result["reset_at"]


@pytest.mark.asyncio
async def test_get_chat_history_formats_image_attachment(monkeypatch) -> None:
    async def _history_stub(*args, **kwargs) -> list[dict]:
        del args, kwargs
        return [
            {
                "role": "assistant",
                "content": "Đây là ảnh minh họa.",
                "created_at": "2026-04-19T11:00:00+00:00",
                "attachment_type": "image",
                "attachment_path": "chat/student-1/example.png",
                "attachment_mime_type": "image/png",
                "attachment_file_name": "example.png",
            }
        ]

    async def _attachments_stub(messages: list[dict], access_token: str) -> dict[int, dict]:
        assert access_token == "token"
        assert len(messages) == 1
        return {
            0: {
                "type": "image",
                "mime_type": "image/png",
                "file_name": "example.png",
                "url": "https://example.com/example.png",
                "url_expires_in": 3600,
            }
        }

    monkeypatch.setattr(chatbot_route, "_load_recent_history", _history_stub)
    monkeypatch.setattr(
        chatbot_route,
        "_build_history_attachments_parallel",
        _attachments_stub,
    )

    result = await chatbot_route.get_chat_history(
        user={"sub": "student-1"},
        access_token="token",
        limit=40,
    )

    assert len(result["messages"]) == 1
    message = result["messages"][0]
    assert message["role"] == "assistant"
    assert message["content"] == "Đây là ảnh minh họa."
    assert message["attachment"]["type"] == "image"
    assert message["attachment"]["mime_type"] == "image/png"
    assert message["attachment"]["file_name"] == "example.png"
    assert message["attachment"]["url"] == "https://example.com/example.png"


@pytest.mark.asyncio
async def test_chat_with_image_returns_processing_payload(monkeypatch) -> None:
    llm = _LLMStub()
    captured_attachment: dict | None = None

    async def _usage_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-3"
        return {"call_count": 1}

    async def _upload_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-3"
        return {
            "type": "image",
            "path": "chat/student-3/example.png",
            "mime_type": "image/png",
            "file_name": "example.png",
        }

    async def _save_stub(*args, **kwargs) -> None:
        nonlocal captured_attachment
        captured_attachment = kwargs.get("user_attachment")

    async def _increment_stub(**kwargs) -> None:
        del kwargs

    monkeypatch.setattr(chatbot_route, "get_user_token_usage", _usage_stub)
    monkeypatch.setattr(
        chatbot_route,
        "_upload_chat_image_to_storage",
        _upload_stub,
    )
    monkeypatch.setattr(chatbot_route, "_save_chat_messages", _save_stub)
    monkeypatch.setattr(chatbot_route, "increment_user_token_usage", _increment_stub)
    monkeypatch.setattr(chatbot_route, "_get_llm", lambda: llm)

    image = UploadFile(
        file=BytesIO(b"png-bytes"),
        filename="example.png",
        headers=Headers({"content-type": "image/png"}),
    )

    result = await chatbot_route.chat_with_image(
        message="Phân tích ảnh này",
        image=image,
        user={"sub": "student-3"},
        access_token="token",
    )

    assert result.reply == "Đây là đồ thị hàm số bậc hai."
    assert result.processing is not None
    assert result.processing.mode == "image"
    assert result.processing.image_analyzed is True
    assert "Phân tích ảnh" in result.processing.tags
    assert "PNG" in result.processing.tags
    assert captured_attachment == {
        "type": "image",
        "path": "chat/student-3/example.png",
        "mime_type": "image/png",
        "file_name": "example.png",
    }