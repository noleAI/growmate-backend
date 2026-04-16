from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from core.lives_engine import check_regen, lose_life, regen_life
from core.security import get_bearer_token, get_current_user

router = APIRouter()


def _require_user_id(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier",
        )
    return user_id


@router.get("/lives")
async def get_lives(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)

    try:
        status_payload = await check_regen(user_id=user_id, access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load lives: {exc}",
        ) from exc

    return status_payload


@router.post("/lives/lose")
async def consume_life(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)

    try:
        status_payload = await lose_life(user_id=user_id, access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update lives: {exc}",
        ) from exc

    return {
        "remaining": status_payload["current"],
        **status_payload,
    }


@router.post("/lives/regen")
async def regenerate_life(
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    user_id = _require_user_id(user)

    try:
        status_payload = await regen_life(user_id=user_id, access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate lives: {exc}",
        ) from exc

    return status_payload
