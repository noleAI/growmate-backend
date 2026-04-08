"""FastAPI dependency providers.

These functions are consumed by route handlers via ``Depends()``.  They keep
route controllers thin by centralising auth, database, and service wiring.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.database import get_pool
from app.core.security import get_user_id_from_token
from app.repositories.growth_log_repository import GrowthLogRepository
from app.repositories.plant_repository import PlantRepository
from app.repositories.user_repository import UserRepository
from app.services.growth_log_service import GrowthLogService
from app.services.plant_service import PlantService
from app.services.user_service import UserService

_bearer = HTTPBearer(auto_error=True)


# ── Auth ───────────────────────────────────────────────────────────────────────


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> uuid.UUID:
    """Extract and validate the authenticated user's UUID from a Bearer token.

    This is the primary authentication dependency for every protected endpoint.
    Supabase issues the token; we verify the signature using the project's JWT
    secret stored in ``SUPABASE_JWT_SECRET``.

    Args:
        credentials: HTTP Bearer credentials extracted by FastAPI.

    Returns:
        The authenticated user's UUID.

    Raises:
        HTTPException 401: If the token is missing, expired, or invalid.
    """
    try:
        user_id_str = get_user_id_from_token(credentials.credentials)
        return uuid.UUID(user_id_str)
    except (JWTError, ValueError) as exc:
        raise JWTError("Invalid authentication credentials.") from exc


# ── Database pool ──────────────────────────────────────────────────────────────


def get_db_pool(pool: asyncpg.Pool = Depends(get_pool)) -> asyncpg.Pool:
    """Provide the shared asyncpg connection pool."""
    return pool


# ── Repository factories ───────────────────────────────────────────────────────


def get_user_repository(pool: asyncpg.Pool = Depends(get_db_pool)) -> UserRepository:
    """Provide a :class:`UserRepository` backed by the shared pool."""
    return UserRepository(pool)


def get_plant_repository(pool: asyncpg.Pool = Depends(get_db_pool)) -> PlantRepository:
    """Provide a :class:`PlantRepository` backed by the shared pool."""
    return PlantRepository(pool)


def get_growth_log_repository(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> GrowthLogRepository:
    """Provide a :class:`GrowthLogRepository` backed by the shared pool."""
    return GrowthLogRepository(pool)


# ── Service factories ──────────────────────────────────────────────────────────


def get_user_service(repo: UserRepository = Depends(get_user_repository)) -> UserService:
    """Provide a :class:`UserService` with its repository dependency wired."""
    return UserService(repo)


def get_plant_service(repo: PlantRepository = Depends(get_plant_repository)) -> PlantService:
    """Provide a :class:`PlantService` with its repository dependency wired."""
    return PlantService(repo)


def get_growth_log_service(
    log_repo: GrowthLogRepository = Depends(get_growth_log_repository),
    plant_repo: PlantRepository = Depends(get_plant_repository),
) -> GrowthLogService:
    """Provide a :class:`GrowthLogService` with both repository dependencies wired."""
    return GrowthLogService(log_repo, plant_repo)
