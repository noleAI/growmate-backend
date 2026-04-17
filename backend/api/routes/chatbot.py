"""
Chatbot route — Free Q&A for high-school students.

POST /api/v1/chatbot/chat
  • Requires Bearer token (Supabase JWT)
  • Enforces daily chat quota (free plan)
  • Saves conversation history to Supabase (table: chat_history)
  • Content policy is embedded in the system prompt
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.llm_service import LLMService
from core.security import get_bearer_token, get_current_user
from core.supabase_client import (
    get_supabase_client,
    get_user_token_usage,
    increment_user_token_usage,
    _run_with_retry,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────────────────
DAILY_CHAT_LIMIT_FREE = 30          # messages per day (free plan)
MAX_HISTORY_TURNS = 10              # rolling window sent to LLM
MAX_MESSAGE_LENGTH = 1000           # characters
VN_TZ = timezone(timedelta(hours=7))

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


# ── Pydantic schemas ───────────────────────────────────────────────────────────
class HistoryItem(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    history: list[HistoryItem] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    is_blocked: bool = False
    remaining_quota: int


# ── Supabase helpers ───────────────────────────────────────────────────────────
async def _save_chat_messages(
    user_id: str,
    user_message: str,
    ai_reply: str,
    access_token: str,
) -> None:
    """Persist both turns to the chat_history table (best-effort)."""
    now = datetime.now(UTC).isoformat()
    rows = [
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "role": "user",
            "content": user_message,
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "role": "assistant",
            "content": ai_reply,
            "created_at": now,
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

    def _select():
        return (
            get_supabase_client(access_token)
            .table("chat_history")
            .select("role,content,created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    try:
        response = await _run_with_retry("load_recent_history", _select)
        rows = getattr(response, "data", []) or []
        # Reverse so oldest → newest
        return list(reversed([r for r in rows if isinstance(r, dict)]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load chat history: %s", exc)
        return []


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
        if used >= DAILY_CHAT_LIMIT_FREE:
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

    # Trim to rolling window
    history_turns = history_turns[-(MAX_HISTORY_TURNS * 2):]


    # ── 3. Build prompt and call LLM ──────────────────────────────────────
    llm = _get_llm()
    reply = await llm.generate_chat_response(
        system_prompt=_build_system_prompt(),   # ← injects current date/time
        history=history_turns,
        user_message=body.message,
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


    remaining = max(0, DAILY_CHAT_LIMIT_FREE - used - 1)
    return ChatResponse(reply=reply, remaining_quota=remaining)


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
    remaining = max(0, DAILY_CHAT_LIMIT_FREE - used)

    next_midnight = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    return {
        "used": used,
        "limit": DAILY_CHAT_LIMIT_FREE,
        "remaining": remaining,
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
    return {
        "messages": [
            {"role": m.get("role"), "content": m.get("content"), "created_at": m.get("created_at")}
            for m in messages
        ]
    }

