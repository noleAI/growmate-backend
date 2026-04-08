"""Plant repository – database access layer for plants."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import asyncpg

from app.models.schemas.plant import PlantCreate, PlantResponse, PlantUpdate
from app.repositories.base import BaseRepository


class PlantRepository(BaseRepository):
    """CRUD operations for the ``plants`` table."""

    async def create(self, user_id: uuid.UUID, data: PlantCreate) -> PlantResponse:
        """Insert a new plant record.

        Args:
            user_id: Owner of the plant.
            data: Validated plant creation payload.

        Returns:
            The newly created :class:`PlantResponse`.

        Time complexity: O(1).
        """
        now = datetime.now(UTC)
        row: asyncpg.Record = await self._pool.fetchrow(
            """
            INSERT INTO plants (plant_id, user_id, name, species, location, notes,
                                acquired_date, created_at, updated_at)
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $7)
            RETURNING *
            """,
            user_id,
            data.name,
            data.species,
            data.location,
            data.notes,
            data.acquired_date,
            now,
        )
        return PlantResponse.model_validate(dict(row))

    async def list_for_user(self, user_id: uuid.UUID) -> list[PlantResponse]:
        """Return all plants owned by *user_id*, ordered by creation date.

        Args:
            user_id: Owner filter.

        Returns:
            List of :class:`PlantResponse` objects (may be empty).

        Time complexity: O(n) – full scan of user's plants (indexed on user_id).
        """
        rows: list[asyncpg.Record] = await self._pool.fetch(
            "SELECT * FROM plants WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
        return [PlantResponse.model_validate(dict(r)) for r in rows]

    async def get_by_id(self, plant_id: uuid.UUID, user_id: uuid.UUID) -> PlantResponse | None:
        """Fetch a single plant, ensuring it belongs to *user_id*.

        Args:
            plant_id: Primary key of the plant.
            user_id: Expected owner; prevents cross-user access.

        Returns:
            :class:`PlantResponse` if found and owned, ``None`` otherwise.

        Time complexity: O(1) – primary-key lookup.
        """
        row: asyncpg.Record | None = await self._pool.fetchrow(
            "SELECT * FROM plants WHERE plant_id = $1 AND user_id = $2",
            plant_id,
            user_id,
        )
        return PlantResponse.model_validate(dict(row)) if row else None

    async def update(
        self,
        plant_id: uuid.UUID,
        user_id: uuid.UUID,
        data: PlantUpdate,
    ) -> PlantResponse | None:
        """Partially update a plant, returning the updated record.

        Only non-``None`` fields in *data* are written to the database.

        Args:
            plant_id: Primary key of the plant.
            user_id: Owner guard.
            data: Partial update payload.

        Returns:
            Updated :class:`PlantResponse`, or ``None`` if not found / not owned.

        Time complexity: O(1).
        """
        now = datetime.now(UTC)
        # Build dynamic SET clause from supplied (non-None) fields
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return await self.get_by_id(plant_id, user_id)

        set_clause = ", ".join(f"{col} = ${i + 3}" for i, col in enumerate(updates))
        values = list(updates.values())
        row: asyncpg.Record | None = await self._pool.fetchrow(
            f"""
            UPDATE plants
            SET {set_clause}, updated_at = $2
            WHERE plant_id = $1 AND user_id = ${len(values) + 3}
            RETURNING *
            """,  # noqa: S608
            plant_id,
            now,
            *values,
            user_id,
        )
        return PlantResponse.model_validate(dict(row)) if row else None

    async def delete(self, plant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a plant and return whether a row was actually removed.

        Args:
            plant_id: Primary key of the plant.
            user_id: Owner guard.

        Returns:
            ``True`` if a row was deleted, ``False`` if not found / not owned.

        Time complexity: O(1).
        """
        result: str = await self._pool.execute(
            "DELETE FROM plants WHERE plant_id = $1 AND user_id = $2",
            plant_id,
            user_id,
        )
        return result == "DELETE 1"
