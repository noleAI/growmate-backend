"""User service – business logic for user profile management."""

from __future__ import annotations

import uuid

from app.exceptions.handlers import NotFoundError
from app.models.schemas.user import UserCreate, UserResponse
from app.repositories.user_repository import UserRepository


class UserService:
    """Orchestrates user-profile operations.

    Delegates all persistence to :class:`UserRepository` and applies any
    business rules that cross-cut multiple repository calls.

    Args:
        repo: The :class:`UserRepository` instance (injected).
    """

    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def upsert_profile(self, user_id: uuid.UUID, data: UserCreate) -> UserResponse:
        """Create or refresh a user profile after JWT verification.

        Called during the ``/auth/me`` flow once the Supabase JWT has been
        decoded and the ``sub`` claim extracted.

        Args:
            user_id: UUID from the JWT ``sub`` claim.
            data: Display name and email from the token payload.

        Returns:
            Up-to-date :class:`UserResponse`.
        """
        return await self._repo.upsert(user_id, data)

    async def get_profile(self, user_id: uuid.UUID) -> UserResponse:
        """Retrieve a user profile, raising 404 if not found.

        Args:
            user_id: The authenticated user's UUID.

        Returns:
            :class:`UserResponse`.

        Raises:
            NotFoundError: If no profile exists for *user_id*.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        return user
