"""
Chatbot route — Free Q&A for high-school students.

POST /api/v1/chatbot/chat
  • Requires Bearer token (Supabase JWT)
  • Enforces daily chat quota (free plan)
  • Saves conversation history to Supabase (table: chat_history)
  • Content policy is embedded in the system prompt
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from core.llm_service import LLMService
from core.security import get_bearer_token, get_current_user
from core.supabase_client import (
    _run_with_retry,
    get_supabase_client,
    get_user_token_usage,
    increment_user_token_usage,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────────────────
_daily_limit_raw = os.getenv("DAILY_CHAT_LIMIT_FREE", "30")
try:
    DAILY_CHAT_LIMIT_FREE = max(1, int(_daily_limit_raw))
except ValueError:
    DAILY_CHAT_LIMIT_FREE = 30

CHAT_QUOTA_UNLIMITED = os.getenv("CHAT_QUOTA_UNLIMITED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
UNLIMITED_REMAINING_QUOTA = 2_147_483_647
HISTORY_SIGNING_CONCURRENCY = max(1, int(os.getenv("HISTORY_SIGNING_CONCURRENCY", "8")))
STORAGE_REMOVE_BATCH_SIZE = 100
MAX_HISTORY_TURNS = 10              # rolling window sent to LLM
MAX_MESSAGE_LENGTH = 1000           # characters
VN_TZ = timezone(timedelta(hours=7))
CHAT_IMAGE_BUCKET = os.getenv("CHAT_IMAGE_BUCKET", "chat-images")
_signed_url_ttl_raw = os.getenv("CHAT_IMAGE_SIGNED_URL_TTL_SEC", "3600")
try:
    CHAT_IMAGE_SIGNED_URL_TTL_SEC = max(60, int(_signed_url_ttl_raw))
except ValueError:
    CHAT_IMAGE_SIGNED_URL_TTL_SEC = 3600

_chat_image_bucket_missing_notified = False
_ALLOWED_IMAGE_EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

# ── System prompt ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT_TEMPLATE = """Bạn là GrowMate AI — gia sư trực tuyến thông minh dành riêng cho học sinh THPT Việt Nam (lớp 10, 11, 12).

THÔNG TIN HIỆN TẠI:
- Ngày giờ hiện tại (giờ Việt Nam): {current_datetime}

PHẠM VI TRỢ GIÚP (chỉ trả lời các chủ đề sau):
- Toán học: đại số, hình học, giải tích, thống kê, xác suất
- Vật lý, Hóa học, Sinh học (chương trình THPT)
- Ngữ văn, Lịch sử, Địa lý, GDCD (chương trình THPT)
- Tiếng Anh (ngữ pháp, từ vựng, kỹ năng cơ bản)
- Tin học (lập trình cơ bản, thuật toán, cấu trúc dữ liệu cơ bản)
- Phương pháp học tập, kỹ năng ôn thi THPT Quốc gia
- Giải thích khái niệm, hướng dẫn giải bài tập (gợi ý phương pháp, KHÔNG đưa đáp án trực tiếp)
- Câu hỏi về thời gian, lịch học, kế hoạch ôn thi

QUY TẮC BẮT BUỘC:
1. Xưng "mình", gọi học sinh là "bạn". Thân thiện, khích lệ, ngắn gọn.
2. Nếu bị hỏi về: y khoa chuyên sâu, tình dục, bạo lực, ma túy, chính trị nhạy cảm, pháp lý, tài chính/đầu tư, tôn giáo, hoặc bất kỳ chủ đề nào NGOÀI chương trình THPT → Từ chối lịch sự và gợi ý câu hỏi phù hợp hơn.
3. KHÔNG bịa đặt thông tin. Nếu không chắc, hãy nói "Mình không chắc về điều này, bạn nên hỏi thầy/cô để được giải đáp chính xác nhé!"
4. Khuyến khích tư duy thay vì đưa đáp án thẳng.
5. Trả lời bằng tiếng Việt trừ khi học sinh hỏi bằng tiếng Anh.
6. Bạn có khả năng tìm kiếm thông tin trên Google để trả lời các câu hỏi cần thông tin cập nhật."""


def _build_system_prompt() -> str:
    """Build system prompt with current date/time injected."""
    now_vn = datetime.now(VN_TZ)
    weekdays_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    weekday = weekdays_vi[now_vn.weekday()]
    current_datetime = now_vn.strftime(f"{weekday}, ngày %d tháng %m năm %Y, %H:%M")
    return _SYSTEM_PROMPT_TEMPLATE.format(current_datetime=current_datetime)


def _is_quota_exceeded(used: int) -> bool:
    if CHAT_QUOTA_UNLIMITED:
        return False
    return used >= DAILY_CHAT_LIMIT_FREE


def _remaining_quota(used: int) -> int:
    if CHAT_QUOTA_UNLIMITED:
        return UNLIMITED_REMAINING_QUOTA
    return max(0, DAILY_CHAT_LIMIT_FREE - used - 1)


# ── Pydantic schemas ───────────────────────────────────────────────────────────
class HistoryItem(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    history: list[HistoryItem] = Field(default_factory=list)


class ChatProcessingInfo(BaseModel):
    mode: str = Field(..., pattern="^(text|image)$")
    summary: str
    tags: list[str] = Field(default_factory=list)
    history_source: str | None = None
    history_turns_used: int = 0
    used_search: bool = False
    image_analyzed: bool = False


class ChatResponse(BaseModel):
    reply: str
    is_blocked: bool = False
    remaining_quota: int
    processing: ChatProcessingInfo | None = None


def _build_text_chat_processing(
    *,
    history_source: str,
    history_turns_used: int,
    used_search: bool,
) -> ChatProcessingInfo:
    tags: list[str] = []

    if history_source == "database":
        tags.append("Lịch sử chat")
    elif history_source == "request":
        tags.append("Ngữ cảnh từ app")
    else:
        tags.append("Không dùng lịch sử")

    if history_turns_used > 0:
        tags.append(f"{history_turns_used} lượt ngữ cảnh")

    if used_search:
        tags.append("Google Search")

    if history_source == "database":
        base_summary = "Đã dùng lịch sử chat gần đây"
    elif history_source == "request":
        base_summary = "Đã dùng ngữ cảnh hội thoại mà ứng dụng vừa gửi"
    else:
        base_summary = "Đã trả lời trực tiếp từ câu hỏi hiện tại"

    if used_search:
        summary = f"{base_summary} và Google Search để soạn câu trả lời."
    elif history_source == "none":
        summary = f"{base_summary}."
    else:
        summary = f"{base_summary} để soạn câu trả lời."

    return ChatProcessingInfo(
        mode="text",
        summary=summary,
        tags=tags,
        history_source=history_source,
        history_turns_used=history_turns_used,
        used_search=used_search,
        image_analyzed=False,
    )


def _build_image_chat_processing(*, image_mime_type: str | None = None) -> ChatProcessingInfo:
    tags = ["Phân tích ảnh"]
    if image_mime_type:
        tags.append(image_mime_type.replace("image/", "").upper())

    return ChatProcessingInfo(
        mode="image",
        summary="Đã phân tích ảnh bạn gửi và tạo câu trả lời từ nội dung trong ảnh.",
        tags=tags,
        history_source=None,
        history_turns_used=0,
        used_search=False,
        image_analyzed=True,
    )


# ── Supabase helpers ───────────────────────────────────────────────────────────
async def _save_chat_messages(
    user_id: str,
    user_message: str,
    ai_reply: str,
    access_token: str,
    user_attachment: dict[str, Any] | None = None,
) -> None:
    """Persist both turns to the chat_history table (best-effort)."""
    # Preserve deterministic ordering (user turn before assistant turn)
    # even when loaded/re-sorted by timestamp.
    user_created_at = datetime.now(UTC)
    assistant_created_at = user_created_at + timedelta(microseconds=1)
    user_row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "role": "user",
        "content": user_message,
        "created_at": user_created_at.isoformat(),
    }
    if user_attachment:
        user_row.update(
            {
                "attachment_type": user_attachment.get("type"),
                "attachment_path": user_attachment.get("path"),
                "attachment_mime_type": user_attachment.get("mime_type"),
                "attachment_file_name": user_attachment.get("file_name"),
            }
        )

    rows = [
        user_row,
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "role": "assistant",
            "content": ai_reply,
            "created_at": assistant_created_at.isoformat(),
        },
    ]

    def _insert():
        return (
            get_supabase_client(access_token)
            .table("chat_history")
            .insert(rows)
            .execute()
        )

    try:
        await _run_with_retry("save_chat_messages", _insert)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to save chat history: %s", exc)


async def _load_recent_history(
    user_id: str,
    access_token: str,
    limit: int = MAX_HISTORY_TURNS * 2,
) -> list[dict[str, Any]]:
    """Load last N messages from Supabase for context (oldest first)."""

    def _select_with_attachments():
        return (
            get_supabase_client(access_token)
            .table("chat_history")
            .select(
                "role,content,created_at,attachment_type,attachment_path,"
                "attachment_mime_type,attachment_file_name"
            )
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    def _select_legacy():
        return (
            get_supabase_client(access_token)
            .table("chat_history")
            .select("role,content,created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows.sort(
            key=lambda r: (
                str(r.get("created_at") or ""),
                0 if str(r.get("role") or "") == "user" else 1,
            )
        )
        return rows

    try:
        response = await _run_with_retry("load_recent_history", _select_with_attachments)
    except Exception as exc:  # noqa: BLE001
        if not _is_missing_attachment_columns_error(exc):
            logger.warning("Failed to load chat history: %s", exc)
            return []

        logger.warning(
            "chat_history attachment columns are missing; using legacy select. "
            "Run supabase_chat_history_migration.sql to enable image attachments."
        )
        try:
            response = await _run_with_retry("load_recent_history_legacy", _select_legacy)
            rows = getattr(response, "data", []) or []
            valid_rows = [r for r in rows if isinstance(r, dict)]
            for row in valid_rows:
                row.setdefault("attachment_type", None)
                row.setdefault("attachment_path", None)
                row.setdefault("attachment_mime_type", None)
                row.setdefault("attachment_file_name", None)
            return _sort_rows(valid_rows)
        except Exception as legacy_exc:  # noqa: BLE001
            logger.warning("Failed to load legacy chat history: %s", legacy_exc)
            return []

    try:
        rows = getattr(response, "data", []) or []
        valid_rows = [r for r in rows if isinstance(r, dict)]
        return _sort_rows(valid_rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load chat history: %s", exc)
        return []


def _sanitize_filename(file_name: str | None) -> str:
    if not file_name:
        return "image.jpg"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name).strip("._")
    return cleaned or "image.jpg"


def _infer_extension(mime_type: str) -> str:
    # Derive extension from validated MIME type only. Do not trust filename extension.
    return _ALLOWED_IMAGE_EXTENSION_BY_MIME.get(str(mime_type or "").lower(), "jpg")


def _is_bucket_not_found_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "bucket not found" in message or (
        "statuscode" in message and "404" in message and "bucket" in message
    )


def _is_missing_attachment_columns_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "42703" in message:
        return True
    return "attachment_type" in message or "attachment_path" in message


async def _upload_chat_image_to_storage(
    *,
    user_id: str,
    image_bytes: bytes,
    image_mime_type: str,
    original_file_name: str | None,
    access_token: str,
) -> dict[str, str] | None:
    """Upload chat image to Supabase Storage and return attachment metadata."""
    global _chat_image_bucket_missing_notified

    safe_file_name = _sanitize_filename(original_file_name)
    extension = _infer_extension(image_mime_type)
    object_path = (
        f"{user_id}/chat_images/{datetime.now(UTC).strftime('%Y/%m/%d')}/"
        f"{uuid.uuid4().hex}.{extension}"
    )

    def _upload():
        return (
            get_supabase_client(access_token)
            .storage
            .from_(CHAT_IMAGE_BUCKET)
            .upload(
                path=object_path,
                file=image_bytes,
                file_options={
                    "content-type": image_mime_type,
                    "x-upsert": "false",
                },
            )
        )

    try:
        # Try once first to detect permanent errors (e.g., missing bucket)
        # and avoid noisy retries that cannot succeed.
        await asyncio.wait_for(asyncio.to_thread(_upload), timeout=6.0)
    except Exception as exc:  # noqa: BLE001
        if _is_bucket_not_found_error(exc):
            if not _chat_image_bucket_missing_notified:
                logger.error(
                    "Storage bucket '%s' not found. Run supabase_chat_history_migration.sql "
                    "or set CHAT_IMAGE_BUCKET to an existing bucket. Image upload skipped.",
                    CHAT_IMAGE_BUCKET,
                )
                _chat_image_bucket_missing_notified = True
            return None

        try:
            await _run_with_retry(
                "upload_chat_image_to_storage",
                _upload,
                timeout_sec=6.0,
            )
        except Exception as retry_exc:  # noqa: BLE001
            logger.warning("Failed to upload chat image to storage: %s", retry_exc)
            return None

    return {
        "type": "image",
        "path": object_path,
        "mime_type": image_mime_type,
        "file_name": safe_file_name,
    }


async def _create_chat_image_signed_url(
    *,
    object_path: str,
    access_token: str,
) -> str | None:
    """Create a short-lived signed URL for a stored chat image."""

    def _sign():
        return (
            get_supabase_client(access_token)
            .storage
            .from_(CHAT_IMAGE_BUCKET)
            .create_signed_url(
                path=object_path,
                expires_in=CHAT_IMAGE_SIGNED_URL_TTL_SEC,
            )
        )

    try:
        response = await _run_with_retry("create_chat_image_signed_url", _sign, timeout_sec=4.0)
        if isinstance(response, dict):
            return response.get("signedURL") or response.get("signedUrl")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create signed URL for chat image: %s", exc)
    return None


async def _build_history_attachment(
    message_row: dict[str, Any],
    access_token: str,
) -> dict[str, Any] | None:
    attachment_type = str(message_row.get("attachment_type") or "").strip()
    attachment_path = str(message_row.get("attachment_path") or "").strip()
    if attachment_type != "image" or not attachment_path:
        return None

    signed_url = await _create_chat_image_signed_url(
        object_path=attachment_path,
        access_token=access_token,
    )
    return {
        "type": "image",
        "path": attachment_path,
        "mime_type": message_row.get("attachment_mime_type"),
        "file_name": message_row.get("attachment_file_name"),
        "url": signed_url,
        "url_expires_in": CHAT_IMAGE_SIGNED_URL_TTL_SEC,
    }


async def _build_history_attachments_parallel(
    messages: list[dict[str, Any]],
    access_token: str,
) -> dict[int, dict[str, Any] | None]:
    semaphore = asyncio.Semaphore(HISTORY_SIGNING_CONCURRENCY)

    async def _build_for_index(index: int, row: dict[str, Any]):
        async with semaphore:
            attachment = await _build_history_attachment(row, access_token)
            return index, attachment

    tasks = [
        _build_for_index(i, row)
        for i, row in enumerate(messages)
        if str(row.get("attachment_type") or "").strip() == "image"
        and str(row.get("attachment_path") or "").strip()
    ]

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks)
    return {index: attachment for index, attachment in results}


async def _load_user_attachment_paths(
    user_id: str,
    access_token: str,
) -> list[str]:
    def _select():
        return (
            get_supabase_client(access_token)
            .table("chat_history")
            .select("attachment_path")
            .eq("user_id", user_id)
            .eq("attachment_type", "image")
            .execute()
        )

    response = await _run_with_retry("load_user_attachment_paths", _select, timeout_sec=6.0)
    rows = getattr(response, "data", []) or []
    paths: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("attachment_path") or "").strip()
        if path:
            paths.append(path)
    return paths


async def _delete_storage_objects(
    *,
    access_token: str,
    object_paths: list[str],
) -> None:
    unique_paths = list(dict.fromkeys(path for path in object_paths if path))
    if not unique_paths:
        return

    for start in range(0, len(unique_paths), STORAGE_REMOVE_BATCH_SIZE):
        batch = unique_paths[start : start + STORAGE_REMOVE_BATCH_SIZE]

        def _remove_batch():
            return (
                get_supabase_client(access_token)
                .storage
                .from_(CHAT_IMAGE_BUCKET)
                .remove(batch)
            )

        await _run_with_retry(
            "delete_chat_image_objects",
            _remove_batch,
            timeout_sec=8.0,
        )


# ── Main endpoint ──────────────────────────────────────────────────────────────
_llm_service: LLMService | None = None


def _get_llm() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user identifier",
        )

    # ── 1. Check daily quota (fail-safe: allow if DB unreachable) ─────────
    now_local = datetime.now(VN_TZ)
    used = 0
    try:
        usage = await get_user_token_usage(
            user_id=user_id,
            usage_date=now_local.date(),
            access_token=access_token,
        )
        used = max(0, int(usage.get("call_count", 0) or 0))
        if _is_quota_exceeded(used):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "chat_quota_exceeded",
                    "message": "Bạn đã dùng hết lượt chat hôm nay. Quay lại vào ngày mai nhé! 🌙",
                    "limit": DAILY_CHAT_LIMIT_FREE,
                    "used": used,
                },
            )
    except HTTPException:
        raise  # re-raise quota exceeded
    except Exception as exc:
        logger.warning("Quota check failed (allowing request): %s", exc)
        used = 0  # treat as fresh on DB error

    # ── 2. Load DB history (fallback to client-sent history) ───────────
    try:
        db_history = await _load_recent_history(user_id, access_token)
    except Exception as exc:
        logger.warning("History load failed (using client history): %s", exc)
        db_history = []

    if db_history:
        history_turns = db_history
    else:
        history_turns = [{"role": h.role, "content": h.content} for h in body.history]

    history_source = "database" if db_history else ("request" if body.history else "none")

    # Trim to rolling window
    history_turns = history_turns[-(MAX_HISTORY_TURNS * 2):]


    # ── 3. Build prompt and call LLM ──────────────────────────────────────
    llm = _get_llm()
    llm_result = await llm.generate_chat_response(
        system_prompt=_build_system_prompt(),   # ← injects current date/time
        history=history_turns,
        user_message=body.message,
        return_metadata=True,
    )
    if isinstance(llm_result, dict):
        reply = str(llm_result.get("reply") or "")
        llm_processing = llm_result.get("processing")
    else:
        reply = str(llm_result)
        llm_processing = None

    processing = _build_text_chat_processing(
        history_source=history_source,
        history_turns_used=len(history_turns),
        used_search=bool(
            isinstance(llm_processing, dict) and llm_processing.get("used_search")
        ),
    )

    # ── 4. Persist & update quota (best-effort, don't fail response) ────
    try:
        await _save_chat_messages(user_id, body.message, reply, access_token)
    except Exception as exc:
        logger.warning("Failed to save chat messages: %s", exc)

    try:
        await increment_user_token_usage(
            user_id=user_id,
            tokens_used=len(body.message) + len(reply),
            usage_date=now_local.date(),
            access_token=access_token,
        )
    except Exception as exc:
        logger.warning("Failed to increment quota: %s", exc)


    remaining = _remaining_quota(used)
    return ChatResponse(
        reply=reply,
        remaining_quota=remaining,
        processing=processing,
    )


@router.get("/quota")
async def get_chat_quota(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    """Return how many chat messages the user has left today."""
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user identifier")

    now_local = datetime.now(VN_TZ)
    usage = await get_user_token_usage(
        user_id=user_id,
        usage_date=now_local.date(),
        access_token=access_token,
    )
    used = max(0, int(usage.get("call_count", 0) or 0))
    if CHAT_QUOTA_UNLIMITED:
        remaining = UNLIMITED_REMAINING_QUOTA
        limit = UNLIMITED_REMAINING_QUOTA
    else:
        remaining = max(0, DAILY_CHAT_LIMIT_FREE - used)
        limit = DAILY_CHAT_LIMIT_FREE

    next_midnight = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "is_unlimited": CHAT_QUOTA_UNLIMITED,
        "reset_at": next_midnight.isoformat(),
    }


@router.get("/history")
async def get_chat_history(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
    limit: int = 40,
):
    """Return recent chat history for the authenticated user (oldest first)."""
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user identifier")

    messages = await _load_recent_history(user_id, access_token, limit=min(limit, 100))
    attachments_by_index = await _build_history_attachments_parallel(messages, access_token)

    formatted_messages: list[dict[str, Any]] = []
    for i, m in enumerate(messages):
        attachment = attachments_by_index.get(i)
        formatted_messages.append(
            {
                "role": m.get("role"),
                "content": m.get("content"),
                "created_at": m.get("created_at"),
                "attachment": attachment,
            }
        )

    return {"messages": formatted_messages}


@router.delete("/history")
async def delete_chat_history(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    """Delete all chat history for the authenticated user."""
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user identifier",
        )

    try:
        attachment_paths = await _load_user_attachment_paths(user_id, access_token)
        await _delete_storage_objects(
            access_token=access_token,
            object_paths=attachment_paths,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete chat storage objects: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat image attachments",
        ) from exc

    def _delete():
        return (
            get_supabase_client(access_token)
            .table("chat_history")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )

    try:
        await _run_with_retry("delete_chat_history", _delete, timeout_sec=6.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete chat history: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat history",
        ) from exc

    return {"status": "ok"}


MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post("/chat/image", response_model=ChatResponse)
@router.post("/chat_with_image", response_model=ChatResponse)
async def chat_with_image(
    message: str = Form(..., description="User's question about the image"),
    image: UploadFile = File(..., description="Image to analyze (JPEG/PNG/WEBP, max 5 MB)"),
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    """Analyze an uploaded image and answer the user's question using Gemini Vision."""
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user identifier")

    # Validate image
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type: {image.content_type}. Use JPEG, PNG, WEBP or GIF.",
        )

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty image upload is not allowed.",
        )

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large. Maximum size is 5 MB.",
        )

    # Check quota (fail-safe)
    now_local = datetime.now(VN_TZ)
    used = 0
    try:
        usage = await get_user_token_usage(
            user_id=user_id,
            usage_date=now_local.date(),
            access_token=access_token,
        )
        used = max(0, int(usage.get("call_count", 0) or 0))
        if _is_quota_exceeded(used):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "chat_quota_exceeded",
                    "message": "Bạn đã dùng hết lượt chat hôm nay. Quay lại vào ngày mai nhé! 🌙",
                    "limit": DAILY_CHAT_LIMIT_FREE,
                    "used": used,
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Quota check failed for image chat (allowing): %s", exc)

    # Upload image to storage (best-effort; chat still works if upload fails)
    user_attachment = await _upload_chat_image_to_storage(
        user_id=user_id,
        image_bytes=image_bytes,
        image_mime_type=image.content_type or "image/jpeg",
        original_file_name=image.filename,
        access_token=access_token,
    )

    # Call vision LLM
    llm = _get_llm()
    llm_result = await llm.generate_chat_response_with_image(
        system_prompt=_build_system_prompt(),
        user_message=message,
        image_bytes=image_bytes,
        image_mime_type=image.content_type or "image/jpeg",
        return_metadata=True,
    )
    if isinstance(llm_result, dict):
        reply = str(llm_result.get("reply") or "")
        llm_processing = llm_result.get("processing")
    else:
        reply = str(llm_result)
        llm_processing = None

    processing = _build_image_chat_processing(
        image_mime_type=(
            str(llm_processing.get("image_mime_type"))
            if isinstance(llm_processing, dict)
            else image.content_type
        ),
    )

    # Persist & update quota (best-effort)
    try:
        await _save_chat_messages(
            user_id,
            f"[Ảnh] {message}",
            reply,
            access_token,
            user_attachment=user_attachment,
        )
    except Exception as exc:
        logger.warning("Failed to save image chat messages: %s", exc)

    try:
        await increment_user_token_usage(
            user_id=user_id,
            tokens_used=len(message) + len(reply) + 500,  # extra for image tokens
            usage_date=now_local.date(),
            access_token=access_token,
        )
    except Exception as exc:
        logger.warning("Failed to increment quota for image chat: %s", exc)

    remaining = _remaining_quota(used)
    return ChatResponse(
        reply=reply,
        remaining_quota=remaining,
        processing=processing,
    )
