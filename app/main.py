"""GrowMate FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import close_pool, create_pool, set_pool
from app.exceptions.handlers import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown lifecycle events.

    Creates the asyncpg connection pool on startup and closes it on shutdown,
    ensuring no connections are leaked between requests.
    """
    pool = await create_pool()
    set_pool(pool)
    yield
    await close_pool(pool)


def create_app() -> FastAPI:
    """Application factory – constructs and configures the FastAPI instance.

    Using a factory function rather than a module-level object makes it easy
    to create isolated test instances with different settings.

    Returns:
        A fully configured :class:`FastAPI` application.
    """
    settings = get_settings()

    application = FastAPI(
        title="GrowMate API",
        description=(
            "Backend for the GrowMate plant-growth tracking app. "
            "Authenticate via Supabase and track your plant collection."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    register_exception_handlers(application)

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(api_v1_router)

    # ── Health check ──────────────────────────────────────────────────────────
    @application.get("/health", tags=["health"], include_in_schema=False)
    async def health() -> dict[str, str]:
        """Liveness probe for Cloud Run / load balancer health checks."""
        return {"status": "ok"}

    return application


app = create_app()
