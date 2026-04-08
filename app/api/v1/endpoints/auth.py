"""Auth endpoints – profile resolution after Supabase authentication."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user_id, get_user_service
from app.models.schemas.user import UserCreate, UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Upsert the authenticated user's profile",
)
async def upsert_me(
    body: UserCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Create or refresh the profile of the currently authenticated user.

    This endpoint should be called by the client immediately after obtaining a
    JWT from Supabase Auth.  Passing display name and email from the token
    payload lets the backend maintain an up-to-date ``user_profiles`` record.

    Args:
        body: Display name and email for the user profile.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`UserService`.

    Returns:
        Up-to-date :class:`UserResponse` for the authenticated user.
    """
    return await service.upsert_profile(user_id, body)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the authenticated user's profile",
)
async def get_me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Return the profile of the currently authenticated user.

    Args:
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`UserService`.

    Returns:
        :class:`UserResponse` for the authenticated user.
    """
    return await service.get_profile(user_id)
