"""Plant Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import Field

from app.models.schemas.common import OrmModel


class PlantBase(OrmModel):
    """Fields shared across plant create / update / response schemas."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Monstera"])
    species: str | None = Field(default=None, max_length=150, examples=["Monstera deliciosa"])
    location: str | None = Field(default=None, max_length=100, examples=["Living room"])
    notes: str | None = Field(default=None, max_length=2000)
    acquired_date: date | None = Field(default=None)


class PlantCreate(PlantBase):
    """Request body for creating a new plant."""


class PlantUpdate(OrmModel):
    """Request body for partially updating a plant (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    species: str | None = Field(default=None, max_length=150)
    location: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    acquired_date: date | None = Field(default=None)


class PlantResponse(PlantBase):
    """Full plant representation returned to the client."""

    plant_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
