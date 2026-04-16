from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from core.security import get_bearer_token, get_current_user
from core.supabase_client import get_user_token_usage

router = APIRouter()

DAILY_QUOTA_FREE = 20
VN_TZ = timezone(timedelta(hours=7))


def _build_reset_at(now_local: datetime) -> str:
    next_midnight = (now_local + timedelta(days=1)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return next_midnight.isoformat()


@router.get("/quota")
async def get_quota(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )

    now_local = datetime.now(VN_TZ)

    try:
        usage = await get_user_token_usage(
            user_id=user_id,
            usage_date=now_local.date(),
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read quota usage: {exc}",
        ) from exc

    used = max(0, int(usage.get("call_count", 0) or 0))
    remaining = max(0, DAILY_QUOTA_FREE - used)

    return {
        "used": used,
        "limit": DAILY_QUOTA_FREE,
        "remaining": remaining,
        "reset_at": _build_reset_at(now_local),
    }
