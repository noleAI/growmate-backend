"""Application configuration loaded from environment variables."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings class; values are sourced from environment variables.

    All secrets must be supplied via the environment (or a `.env` file that is
    **never** committed to version control).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    app_env: str = Field(default="production", pattern="^(development|production|test)$")
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Accept either a JSON array string or a plain list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    # ── Supabase ───────────────────────────────────────────────────────────────
    supabase_url: AnyHttpUrl = Field(...)
    supabase_anon_key: str = Field(...)
    supabase_jwt_secret: str = Field(...)

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(...)

    # ── Security ───────────────────────────────────────────────────────────────
    secret_key: str = Field(...)
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: Annotated[int, Field(gt=0)] = 30

    # ── Database pool ─────────────────────────────────────────────────────────
    db_pool_min_size: int = Field(default=2, gt=0)
    db_pool_max_size: int = Field(default=10, gt=0)


def get_settings() -> Settings:
    """Return a cached Settings instance.

    Uses ``lru_cache`` to ensure environment variables are only parsed once per
    process.  The decorator keeps the function testable – override it via
    ``app.core.config.get_settings.cache_clear()`` in tests.
    """
    return Settings()  # type: ignore[call-arg]


# Apply cache after definition so the function object is stable
import functools  # noqa: E402

get_settings = functools.lru_cache(maxsize=1)(get_settings)
