"""Growth log endpoints – tracking plant measurements over time."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_current_user_id, get_growth_log_service
from app.models.schemas.growth_log import (
    GrowthLogCreate,
    GrowthLogResponse,
    GrowthLogUpdate,
)
from app.services.growth_log_service import GrowthLogService

router = APIRouter(prefix="/plants/{plant_id}/logs", tags=["growth-logs"])


@router.post(
    "",
    response_model=GrowthLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a growth log entry",
)
async def create_log(
    plant_id: uuid.UUID,
    body: GrowthLogCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: GrowthLogService = Depends(get_growth_log_service),
) -> GrowthLogResponse:
    """Record a new growth measurement for the specified plant.

    Args:
        plant_id: UUID of the parent plant.
        body: Validated growth log payload.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`GrowthLogService`.

    Returns:
        The newly created :class:`GrowthLogResponse` with HTTP 201.

    Raises:
        HTTP 404: If the plant is not found or not owned by the user.
    """
    return await service.create_log(plant_id, user_id, body)


@router.get(
    "",
    response_model=list[GrowthLogResponse],
    status_code=status.HTTP_200_OK,
    summary="List growth logs for a plant",
)
async def list_logs(
    plant_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: GrowthLogService = Depends(get_growth_log_service),
) -> list[GrowthLogResponse]:
    """Return all growth log entries for the specified plant.

    Args:
        plant_id: UUID of the parent plant.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`GrowthLogService`.

    Returns:
        List of :class:`GrowthLogResponse` objects ordered by ``logged_at``
        descending.

    Raises:
        HTTP 404: If the plant is not found or not owned by the user.
    """
    return await service.list_logs(plant_id, user_id)


@router.get(
    "/{log_id}",
    response_model=GrowthLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single growth log entry",
)
async def get_log(
    plant_id: uuid.UUID,
    log_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: GrowthLogService = Depends(get_growth_log_service),
) -> GrowthLogResponse:
    """Return a specific growth log entry.

    Args:
        plant_id: UUID of the parent plant (used to verify route coherence).
        log_id: UUID of the growth log entry.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`GrowthLogService`.

    Returns:
        :class:`GrowthLogResponse`.

    Raises:
        HTTP 404: If the log is not found or not owned by the user.
    """
    return await service.get_log(log_id, user_id)


@router.patch(
    "/{log_id}",
    response_model=GrowthLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update a growth log entry",
)
async def update_log(
    plant_id: uuid.UUID,
    log_id: uuid.UUID,
    body: GrowthLogUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: GrowthLogService = Depends(get_growth_log_service),
) -> GrowthLogResponse:
    """Apply a partial update to a growth log entry.

    Args:
        plant_id: UUID of the parent plant (route context).
        log_id: UUID of the growth log entry to update.
        body: Fields to update (unset fields are ignored).
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`GrowthLogService`.

    Returns:
        Updated :class:`GrowthLogResponse`.

    Raises:
        HTTP 404: If the log is not found or not owned by the user.
    """
    return await service.update_log(log_id, user_id, body)


@router.delete(
    "/{log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a growth log entry",
)
async def delete_log(
    plant_id: uuid.UUID,
    log_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: GrowthLogService = Depends(get_growth_log_service),
) -> Response:
    """Permanently delete a growth log entry.

    Args:
        plant_id: UUID of the parent plant (route context).
        log_id: UUID of the growth log entry to delete.
        user_id: Extracted from the verified Supabase JWT.
        service: Injected :class:`GrowthLogService`.

    Returns:
        HTTP 204 No Content on success.

    Raises:
        HTTP 404: If the log is not found or not owned by the user.
    """
    await service.delete_log(log_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
