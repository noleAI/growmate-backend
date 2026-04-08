"""Growth log repository – database access layer for growth logs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import asyncpg

from app.models.schemas.growth_log import (
    GrowthLogCreate,
    GrowthLogResponse,
    GrowthLogUpdate,
)
from app.repositories.base import BaseRepository


class GrowthLogRepository(BaseRepository):
    """CRUD operations for the ``growth_logs`` table."""

    async def create(
        self,
        plant_id: uuid.UUID,
        user_id: uuid.UUID,
        data: GrowthLogCreate,
    ) -> GrowthLogResponse:
        """Insert a new growth log entry.

        Args:
            plant_id: The plant this log belongs to.
            user_id: The authenticated user (stored for ownership checks).
            data: Validated growth log payload.

        Returns:
            The newly created :class:`GrowthLogResponse`.

        Time complexity: O(1).
        """
        now = datetime.now(UTC)
        logged_at = data.logged_at or now
        row: asyncpg.Record = await self._pool.fetchrow(
            """
            INSERT INTO growth_logs
                (log_id, plant_id, user_id, height_cm, leaf_count, notes,
                 photo_url, logged_at, created_at, updated_at)
            VALUES
                (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $8)
            RETURNING *
            """,
            plant_id,
            user_id,
            data.height_cm,
            data.leaf_count,
            data.notes,
            data.photo_url,
            logged_at,
            now,
        )
        return GrowthLogResponse.model_validate(dict(row))

    async def list_for_plant(
        self,
        plant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[GrowthLogResponse]:
        """Return all growth logs for a plant, scoped to the owner.

        Args:
            plant_id: The plant whose logs to retrieve.
            user_id: Owner guard.

        Returns:
            List of :class:`GrowthLogResponse` objects ordered by ``logged_at``
            descending.

        Time complexity: O(n) – indexed scan on (plant_id, user_id).
        """
        rows: list[asyncpg.Record] = await self._pool.fetch(
            """
            SELECT * FROM growth_logs
            WHERE plant_id = $1 AND user_id = $2
            ORDER BY logged_at DESC
            """,
            plant_id,
            user_id,
        )
        return [GrowthLogResponse.model_validate(dict(r)) for r in rows]

    async def get_by_id(
        self,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> GrowthLogResponse | None:
        """Fetch a single growth log entry by primary key, scoped to owner.

        Args:
            log_id: Primary key of the log.
            user_id: Owner guard.

        Returns:
            :class:`GrowthLogResponse` if found and owned, ``None`` otherwise.

        Time complexity: O(1).
        """
        row: asyncpg.Record | None = await self._pool.fetchrow(
            "SELECT * FROM growth_logs WHERE log_id = $1 AND user_id = $2",
            log_id,
            user_id,
        )
        return GrowthLogResponse.model_validate(dict(row)) if row else None

    async def update(
        self,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
        data: GrowthLogUpdate,
    ) -> GrowthLogResponse | None:
        """Partially update a growth log entry.

        Args:
            log_id: Primary key of the log.
            user_id: Owner guard.
            data: Partial update payload.

        Returns:
            Updated :class:`GrowthLogResponse`, or ``None`` if not found/owned.

        Time complexity: O(1).
        """
        now = datetime.now(UTC)
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return await self.get_by_id(log_id, user_id)

        set_clause = ", ".join(f"{col} = ${i + 3}" for i, col in enumerate(updates))
        values = list(updates.values())
        row: asyncpg.Record | None = await self._pool.fetchrow(
            f"""
            UPDATE growth_logs
            SET {set_clause}, updated_at = $2
            WHERE log_id = $1 AND user_id = ${len(values) + 3}
            RETURNING *
            """,  # noqa: S608
            log_id,
            now,
            *values,
            user_id,
        )
        return GrowthLogResponse.model_validate(dict(row)) if row else None

    async def delete(self, log_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a growth log entry.

        Args:
            log_id: Primary key of the log.
            user_id: Owner guard.

        Returns:
            ``True`` if a row was deleted, ``False`` if not found/owned.

        Time complexity: O(1).
        """
        result: str = await self._pool.execute(
            "DELETE FROM growth_logs WHERE log_id = $1 AND user_id = $2",
            log_id,
            user_id,
        )
        return result == "DELETE 1"
