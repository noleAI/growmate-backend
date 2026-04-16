import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.routes.session import _build_pending_session_payload
from core.security import get_bearer_token, get_current_user
from core.supabase_client import get_latest_active_learning_session

router = APIRouter()
logger = logging.getLogger("api.session_recovery")


@router.get("/session/pending")
async def get_pending_session(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    raw_student_id = user.get("sub")
    student_id = raw_student_id.strip() if isinstance(raw_student_id, str) else ""
    if not student_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )

    try:
        pending_row = await get_latest_active_learning_session(
            student_id=student_id,
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load pending session for student_id=%s: %s",
            student_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load pending session",
        ) from exc

    if not pending_row:
        return {
            "has_pending": False,
            "session": None,
        }

    return {
        "has_pending": True,
        "session": _build_pending_session_payload(pending_row),
    }
