"""API v1 router – aggregates all endpoint routers under ``/api/v1``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.growth_logs import router as growth_logs_router
from app.api.v1.endpoints.plants import router as plants_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(plants_router)
api_v1_router.include_router(growth_logs_router)
