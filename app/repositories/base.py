"""Base repository providing a shared asyncpg pool reference."""

from __future__ import annotations

import asyncpg


class BaseRepository:
    """Thin base class that every concrete repository inherits from.

    Args:
        pool: The shared asyncpg connection pool injected via FastAPI's
              dependency system.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
