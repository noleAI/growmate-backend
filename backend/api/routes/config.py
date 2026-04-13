from fastapi import APIRouter, Depends

from core.security import get_current_user

router = APIRouter()


@router.get("/{category}")
async def get_config(category: str, user: dict = Depends(get_current_user)):
    return {"category": category, "version": "v1.0", "payload": {}}


@router.post("/{category}")
async def upload_config(
    category: str, payload: dict, user: dict = Depends(get_current_user)
):
    # Admin only check would go here based on user['role']
    return {"category": category, "status": "updated"}
