"""Plant service – business logic for plant management."""

from __future__ import annotations

import uuid

from app.exceptions.handlers import NotFoundError
from app.models.schemas.plant import PlantCreate, PlantResponse, PlantUpdate
from app.repositories.plant_repository import PlantRepository


class PlantService:
    """Orchestrates plant CRUD operations.

    Applies ownership and existence validation before delegating to
    :class:`PlantRepository`.

    Args:
        repo: The :class:`PlantRepository` instance (injected).
    """

    def __init__(self, repo: PlantRepository) -> None:
        self._repo = repo

    async def create_plant(self, user_id: uuid.UUID, data: PlantCreate) -> PlantResponse:
        """Create a new plant for the authenticated user.

        Args:
            user_id: Owner of the new plant.
            data: Validated creation payload.

        Returns:
            The persisted :class:`PlantResponse`.
        """
        return await self._repo.create(user_id, data)

    async def list_plants(self, user_id: uuid.UUID) -> list[PlantResponse]:
        """List all plants owned by *user_id*.

        Args:
            user_id: The authenticated user's UUID.

        Returns:
            List of :class:`PlantResponse` (may be empty).
        """
        return await self._repo.list_for_user(user_id)

    async def get_plant(self, plant_id: uuid.UUID, user_id: uuid.UUID) -> PlantResponse:
        """Retrieve a single plant, validating ownership.

        Args:
            plant_id: Primary key of the plant.
            user_id: Expected owner.

        Returns:
            :class:`PlantResponse`.

        Raises:
            NotFoundError: If the plant does not exist or is not owned by *user_id*.
        """
        plant = await self._repo.get_by_id(plant_id, user_id)
        if plant is None:
            raise NotFoundError(f"Plant {plant_id} not found.")
        return plant

    async def update_plant(
        self,
        plant_id: uuid.UUID,
        user_id: uuid.UUID,
        data: PlantUpdate,
    ) -> PlantResponse:
        """Partially update a plant.

        Args:
            plant_id: Primary key of the plant.
            user_id: Owner guard.
            data: Partial update payload.

        Returns:
            Updated :class:`PlantResponse`.

        Raises:
            NotFoundError: If the plant does not exist or is not owned by *user_id*.
        """
        plant = await self._repo.update(plant_id, user_id, data)
        if plant is None:
            raise NotFoundError(f"Plant {plant_id} not found.")
        return plant

    async def delete_plant(self, plant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete a plant, raising 404 if it does not exist.

        Args:
            plant_id: Primary key of the plant.
            user_id: Owner guard.

        Raises:
            NotFoundError: If the plant does not exist or is not owned by *user_id*.
        """
        deleted = await self._repo.delete(plant_id, user_id)
        if not deleted:
            raise NotFoundError(f"Plant {plant_id} not found.")
