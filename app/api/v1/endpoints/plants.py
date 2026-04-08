"""Plant endpoints – CRUD for a user's plant collection."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_current_user_id, get_plant_service
from app.models.schemas.plant import PlantCreate, PlantResponse, PlantUpdate
from app.services.plant_service import PlantService

router = APIRouter(prefix="/plants", tags=["plants"])


@router.post(
    "",
    response_model=PlantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new plant",
)
async def create_plant(
    body: PlantCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: PlantService = Depends(get_plant_service),
) -> PlantResponse:
    """Add a new plant to the authenticated user's collection.

    Args:
        body: Validated plant creation payload.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`PlantService`.

    Returns:
        The newly created :class:`PlantResponse` with HTTP 201.
    """
    return await service.create_plant(user_id, body)


@router.get(
    "",
    response_model=list[PlantResponse],
    status_code=status.HTTP_200_OK,
    summary="List all plants",
)
async def list_plants(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: PlantService = Depends(get_plant_service),
) -> list[PlantResponse]:
    """Return all plants owned by the authenticated user.

    Args:
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`PlantService`.

    Returns:
        List of :class:`PlantResponse` objects (may be empty).
    """
    return await service.list_plants(user_id)


@router.get(
    "/{plant_id}",
    response_model=PlantResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single plant",
)
async def get_plant(
    plant_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: PlantService = Depends(get_plant_service),
) -> PlantResponse:
    """Return a specific plant by ID, scoped to the authenticated user.

    Args:
        plant_id: UUID of the plant to retrieve.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`PlantService`.

    Returns:
        :class:`PlantResponse`.

    Raises:
        HTTP 404: If the plant does not exist or is not owned by the user.
    """
    return await service.get_plant(plant_id, user_id)


@router.patch(
    "/{plant_id}",
    response_model=PlantResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update a plant",
)
async def update_plant(
    plant_id: uuid.UUID,
    body: PlantUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: PlantService = Depends(get_plant_service),
) -> PlantResponse:
    """Apply a partial update to a plant.

    Args:
        plant_id: UUID of the plant to update.
        body: Fields to update (unset fields are ignored).
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`PlantService`.

    Returns:
        Updated :class:`PlantResponse`.

    Raises:
        HTTP 404: If the plant does not exist or is not owned by the user.
    """
    return await service.update_plant(plant_id, user_id, body)


@router.delete(
    "/{plant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a plant",
)
async def delete_plant(
    plant_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: PlantService = Depends(get_plant_service),
) -> Response:
    """Permanently delete a plant and all of its growth logs.

    Args:
        plant_id: UUID of the plant to delete.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`PlantService`.

    Returns:
        HTTP 204 No Content on success.

    Raises:
        HTTP 404: If the plant does not exist or is not owned by the user.
    """
    await service.delete_plant(plant_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
