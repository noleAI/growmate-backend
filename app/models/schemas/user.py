"""User profile Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.models.schemas.common import OrmModel


class UserBase(OrmModel):
    """Fields shared by all user representations."""

    display_name: str = Field(..., min_length=1, max_length=100, examples=["Alice Green"])
    email: EmailStr = Field(..., examples=["alice@example.com"])


class UserCreate(UserBase):
    """Payload for upserting a user profile from Supabase Auth data.

    The ``user_id`` comes from the validated JWT ``sub`` claim and is never
    supplied by the client body.
    """


class UserResponse(UserBase):
    """Full user profile returned to the client."""

    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
