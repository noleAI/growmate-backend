"""Growth log service – business logic for growth tracking."""

from __future__ import annotations

import uuid

from app.exceptions.handlers import NotFoundError
from app.models.schemas.growth_log import (
    GrowthLogCreate,
    GrowthLogResponse,
    GrowthLogUpdate,
)
from app.repositories.growth_log_repository import GrowthLogRepository
from app.repositories.plant_repository import PlantRepository


class GrowthLogService:
    """Orchestrates growth-log CRUD operations.

    Verifies plant ownership before any log operation to prevent cross-user
    data leakage.

    Args:
        log_repo: The :class:`GrowthLogRepository` instance (injected).
        plant_repo: The :class:`PlantRepository` instance (injected) used for
                    plant-ownership verification.
    """

    def __init__(self, log_repo: GrowthLogRepository, plant_repo: PlantRepository) -> None:
        self._log_repo = log_repo
        self._plant_repo = plant_repo

    async def _assert_plant_owned(self, plant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Raise :class:`NotFoundError` if the plant is not owned by *user_id*.

        Args:
            plant_id: Plant to check.
            user_id: Expected owner.

        Raises:
            NotFoundError: If the plant does not exist or belongs to another user.
        """
        plant = await self._plant_repo.get_by_id(plant_id, user_id)
        if plant is None:
            raise NotFoundError(f"Plant {plant_id} not found.")

    async def create_log(
        self,
        plant_id: uuid.UUID,
        user_id: uuid.UUID,
        data: GrowthLogCreate,
    ) -> GrowthLogResponse:
        """Add a new growth log entry to a plant.

        Args:
            plant_id: Target plant.
            user_id: Authenticated owner.
            data: Validated log payload.

        Returns:
            The persisted :class:`GrowthLogResponse`.

        Raises:
            NotFoundError: If the plant is not found or not owned.
        """
        await self._assert_plant_owned(plant_id, user_id)
        return await self._log_repo.create(plant_id, user_id, data)

    async def list_logs(
        self,
        plant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[GrowthLogResponse]:
        """List all growth logs for a plant.

        Args:
            plant_id: Target plant.
            user_id: Owner guard.

        Returns:
            List of :class:`GrowthLogResponse` objects (may be empty).

        Raises:
            NotFoundError: If the plant is not found or not owned.
        """
        await self._assert_plant_owned(plant_id, user_id)
        return await self._log_repo.list_for_plant(plant_id, user_id)

    async def get_log(
        self,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> GrowthLogResponse:
        """Retrieve a single growth log entry.

        Args:
            log_id: Primary key of the log.
            user_id: Owner guard.

        Returns:
            :class:`GrowthLogResponse`.

        Raises:
            NotFoundError: If the log is not found or not owned.
        """
        log = await self._log_repo.get_by_id(log_id, user_id)
        if log is None:
            raise NotFoundError(f"Growth log {log_id} not found.")
        return log

    async def update_log(
        self,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
        data: GrowthLogUpdate,
    ) -> GrowthLogResponse:
        """Partially update a growth log entry.

        Args:
            log_id: Primary key of the log.
            user_id: Owner guard.
            data: Partial update payload.

        Returns:
            Updated :class:`GrowthLogResponse`.

        Raises:
            NotFoundError: If the log is not found or not owned.
        """
        log = await self._log_repo.update(log_id, user_id, data)
        if log is None:
            raise NotFoundError(f"Growth log {log_id} not found.")
        return log

    async def delete_log(self, log_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete a growth log entry.

        Args:
            log_id: Primary key of the log.
            user_id: Owner guard.

        Raises:
            NotFoundError: If the log is not found or not owned.
        """
        deleted = await self._log_repo.delete(log_id, user_id)
        if not deleted:
            raise NotFoundError(f"Growth log {log_id} not found.")
