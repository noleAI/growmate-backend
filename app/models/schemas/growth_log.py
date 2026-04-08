"""Growth log Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.models.schemas.common import OrmModel


class GrowthLogBase(OrmModel):
    """Fields shared across growth-log create / update / response schemas."""

    height_cm: float | None = Field(default=None, gt=0, examples=[12.5])
    leaf_count: int | None = Field(default=None, gt=0, examples=[8])
    notes: str | None = Field(default=None, max_length=2000)
    photo_url: str | None = Field(default=None, max_length=500)
    logged_at: datetime | None = Field(
        default=None,
        description="ISO-8601 timestamp for when the measurement was taken; "
        "defaults to now if omitted.",
    )

    @field_validator("photo_url")
    @classmethod
    def validate_photo_url(cls, v: str | None) -> str | None:
        """Ensure the photo URL starts with https:// when provided."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("photo_url must use HTTPS.")
        return v


class GrowthLogCreate(GrowthLogBase):
    """Request body for adding a growth log entry to a plant."""


class GrowthLogUpdate(OrmModel):
    """Request body for partially updating a growth log entry."""

    height_cm: float | None = Field(default=None, gt=0)
    leaf_count: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=2000)
    photo_url: str | None = Field(default=None, max_length=500)
    logged_at: datetime | None = Field(default=None)

    @field_validator("photo_url")
    @classmethod
    def validate_photo_url(cls, v: str | None) -> str | None:
        """Ensure the photo URL starts with https:// when provided."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("photo_url must use HTTPS.")
        return v


class GrowthLogResponse(GrowthLogBase):
    """Full growth log entry returned to the client."""

    log_id: uuid.UUID
    plant_id: uuid.UUID
    user_id: uuid.UUID
    logged_at: datetime
    created_at: datetime
    updated_at: datetime
