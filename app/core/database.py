"""Async PostgreSQL connection pool using asyncpg.

The pool is created once on application startup and closed on shutdown.
All repository methods receive a pool from the FastAPI dependency system so
that no connection is ever leaked.
"""

from __future__ import annotations

import asyncpg

from app.core.config import get_settings

# Module-level pool reference set by lifespan events in main.py
_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    Time complexity: O(1) – opens a fixed number of connections.
    Space complexity: O(n) – where n is the pool size.
    """
    settings = get_settings()
    pool: asyncpg.Pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout=60,
    )
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    """Gracefully close all connections in the pool."""
    await pool.close()


def set_pool(pool: asyncpg.Pool) -> None:
    """Store the pool reference for use by the ``get_pool`` dependency."""
    global _pool  # noqa: PLW0603
    _pool = pool


def get_pool() -> asyncpg.Pool:
    """FastAPI dependency that yields the active connection pool.

    Raises:
        RuntimeError: If the pool has not been initialised (startup not run).
    """
    if _pool is None:
        raise RuntimeError("Database pool has not been initialised.")
    return _pool
