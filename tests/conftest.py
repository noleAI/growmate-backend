"""Shared pytest fixtures for GrowMate backend tests.

Unit tests use mocked repositories so no database is required.
API tests use an in-process TestClient with all database interactions mocked.
"""

from __future__ import annotations

# ── Set required env vars BEFORE any app module is imported ───────────────────
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-that-is-long-enough")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("APP_ENV", "test")
# ─────────────────────────────────────────────────────────────────────────────

import uuid
from datetime import UTC, datetime, date
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_current_user_id,
    get_growth_log_service,
    get_plant_service,
    get_user_service,
)
from app.main import create_app
from app.models.schemas.growth_log import GrowthLogResponse
from app.models.schemas.plant import PlantResponse
from app.models.schemas.user import UserResponse

# ── Shared test constants ──────────────────────────────────────────────────────

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_PLANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TEST_LOG_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


# ── Fixture: sample domain objects ────────────────────────────────────────────


@pytest.fixture()
def sample_plant() -> PlantResponse:
    return PlantResponse(
        plant_id=TEST_PLANT_ID,
        user_id=TEST_USER_ID,
        name="Monstera",
        species="Monstera deliciosa",
        location="Living room",
        notes=None,
        acquired_date=date(2023, 1, 15),
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture()
def sample_log() -> GrowthLogResponse:
    return GrowthLogResponse(
        log_id=TEST_LOG_ID,
        plant_id=TEST_PLANT_ID,
        user_id=TEST_USER_ID,
        height_cm=25.0,
        leaf_count=6,
        notes="Looking healthy",
        photo_url="https://cdn.example.com/photo.jpg",
        logged_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture()
def sample_user() -> UserResponse:
    return UserResponse(
        user_id=TEST_USER_ID,
        display_name="Alice Green",
        email="alice@example.com",
        created_at=NOW,
        updated_at=NOW,
    )


# ── Fixture: mock services ─────────────────────────────────────────────────────


@pytest.fixture()
def mock_plant_service() -> MagicMock:
    svc = MagicMock()
    svc.create_plant = AsyncMock()
    svc.list_plants = AsyncMock()
    svc.get_plant = AsyncMock()
    svc.update_plant = AsyncMock()
    svc.delete_plant = AsyncMock()
    return svc


@pytest.fixture()
def mock_growth_log_service() -> MagicMock:
    svc = MagicMock()
    svc.create_log = AsyncMock()
    svc.list_logs = AsyncMock()
    svc.get_log = AsyncMock()
    svc.update_log = AsyncMock()
    svc.delete_log = AsyncMock()
    return svc


@pytest.fixture()
def mock_user_service() -> MagicMock:
    svc = MagicMock()
    svc.upsert_profile = AsyncMock()
    svc.get_profile = AsyncMock()
    return svc


# ── Fixture: test client with overridden deps ─────────────────────────────────


@pytest.fixture()
def test_client(
    mock_plant_service: MagicMock,
    mock_growth_log_service: MagicMock,
    mock_user_service: MagicMock,
) -> TestClient:
    """Return a TestClient with auth and service dependencies overridden."""
    app = create_app()

    # Override auth – always return TEST_USER_ID
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID

    # Override services – return mock objects
    app.dependency_overrides[get_plant_service] = lambda: mock_plant_service
    app.dependency_overrides[get_growth_log_service] = lambda: mock_growth_log_service
    app.dependency_overrides[get_user_service] = lambda: mock_user_service

    return TestClient(app, raise_server_exceptions=True)
