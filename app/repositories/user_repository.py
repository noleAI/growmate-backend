"""User repository – database access layer for user profiles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import asyncpg

from app.models.schemas.user import UserCreate, UserResponse
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """CRUD operations for the ``user_profiles`` table."""

    async def upsert(self, user_id: uuid.UUID, data: UserCreate) -> UserResponse:
        """Insert or update a user profile.

        Uses an ``ON CONFLICT`` clause to handle re-auth flows gracefully.

        Args:
            user_id: UUID from the verified JWT ``sub`` claim.
            data: Display name and email coming from the JWT payload.

        Returns:
            The persisted :class:`UserResponse`.

        Time complexity: O(1) – single indexed write.
        """
        now = datetime.now(UTC)
        row: asyncpg.Record = await self._pool.fetchrow(
            """
            INSERT INTO user_profiles (user_id, display_name, email, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $4)
            ON CONFLICT (user_id)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                email        = EXCLUDED.email,
                updated_at   = EXCLUDED.updated_at
            RETURNING *
            """,
            user_id,
            data.display_name,
            str(data.email),
            now,
        )
        return UserResponse.model_validate(dict(row))

    async def get_by_id(self, user_id: uuid.UUID) -> UserResponse | None:
        """Fetch a user profile by primary key.

        Args:
            user_id: UUID of the user to retrieve.

        Returns:
            :class:`UserResponse` if found, ``None`` otherwise.

        Time complexity: O(1) – primary-key lookup.
        """
        row: asyncpg.Record | None = await self._pool.fetchrow(
            "SELECT * FROM user_profiles WHERE user_id = $1",
            user_id,
        )
        return UserResponse.model_validate(dict(row)) if row else None
