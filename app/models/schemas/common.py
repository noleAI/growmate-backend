"""Shared Pydantic schema primitives."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    """Base model configured for ORM / mapping use cases.

    All response schemas should inherit from this class so that instances can
    be constructed from asyncpg ``Record`` objects via ``model_validate``.
    """

    model_config = ConfigDict(from_attributes=True)
