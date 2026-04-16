from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.formula_handbook_service import formula_handbook_service
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


@router.get("/formulas")
async def get_formulas(
    category: str = Query(default="all"),
    search: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
    access_token: str = Depends(get_bearer_token),
):
    normalized_category = formula_handbook_service.normalize_category(category)
    if not normalized_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid category. Allowed values: all, basic_derivatives, "
                "arithmetic_rules, basic_trig, exp_log, chain_rule"
            ),
        )

    user_id = _require_user_id(user)

    try:
        categories = await formula_handbook_service.get_catalog_for_user(
            user_id=user_id,
            category=normalized_category,
            search=search,
            access_token=access_token,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load formulas: {exc}",
        ) from exc

    if normalized_category == "all":
        return {
            "category": "all",
            "categories": categories,
        }

    selected = categories[0] if categories else {
        "id": normalized_category,
        "name": normalized_category,
        "description": "",
        "formula_count": 0,
        "mastery_percent": 0,
        "formulas": [],
    }

    return {
        "category": normalized_category,
        "formulas": selected["formulas"],
        "categories": categories,
    }
