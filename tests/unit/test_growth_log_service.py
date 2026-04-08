"""Unit tests for GrowthLogService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exceptions.handlers import NotFoundError
from app.models.schemas.growth_log import GrowthLogCreate, GrowthLogUpdate
from app.services.growth_log_service import GrowthLogService
from tests.conftest import TEST_LOG_ID, TEST_PLANT_ID, TEST_USER_ID


def make_service(log_repo: MagicMock, plant_repo: MagicMock) -> GrowthLogService:
    return GrowthLogService(log_repo, plant_repo)


@pytest.fixture()
def plant_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    return repo


@pytest.fixture()
def log_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.list_for_plant = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    return repo


class TestCreateLog:
    async def test_creates_log_when_plant_owned(
        self, log_repo: MagicMock, plant_repo: MagicMock, sample_plant, sample_log
    ) -> None:
        plant_repo.get_by_id.return_value = sample_plant
        log_repo.create.return_value = sample_log
        service = make_service(log_repo, plant_repo)
        data = GrowthLogCreate(height_cm=25.0, leaf_count=6)

        result = await service.create_log(TEST_PLANT_ID, TEST_USER_ID, data)

        assert result == sample_log
        plant_repo.get_by_id.assert_awaited_once_with(TEST_PLANT_ID, TEST_USER_ID)

    async def test_raises_not_found_when_plant_missing(
        self, log_repo: MagicMock, plant_repo: MagicMock
    ) -> None:
        plant_repo.get_by_id.return_value = None
        service = make_service(log_repo, plant_repo)

        with pytest.raises(NotFoundError):
            await service.create_log(TEST_PLANT_ID, TEST_USER_ID, GrowthLogCreate())


class TestListLogs:
    async def test_returns_logs(
        self, log_repo: MagicMock, plant_repo: MagicMock, sample_plant, sample_log
    ) -> None:
        plant_repo.get_by_id.return_value = sample_plant
        log_repo.list_for_plant.return_value = [sample_log]
        service = make_service(log_repo, plant_repo)

        result = await service.list_logs(TEST_PLANT_ID, TEST_USER_ID)

        assert result == [sample_log]

    async def test_raises_not_found_when_plant_missing(
        self, log_repo: MagicMock, plant_repo: MagicMock
    ) -> None:
        plant_repo.get_by_id.return_value = None
        service = make_service(log_repo, plant_repo)

        with pytest.raises(NotFoundError):
            await service.list_logs(TEST_PLANT_ID, TEST_USER_ID)


class TestGetLog:
    async def test_returns_log_when_found(
        self, log_repo: MagicMock, plant_repo: MagicMock, sample_log
    ) -> None:
        log_repo.get_by_id.return_value = sample_log
        service = make_service(log_repo, plant_repo)

        result = await service.get_log(TEST_LOG_ID, TEST_USER_ID)

        assert result == sample_log

    async def test_raises_not_found_when_missing(
        self, log_repo: MagicMock, plant_repo: MagicMock
    ) -> None:
        log_repo.get_by_id.return_value = None
        service = make_service(log_repo, plant_repo)

        with pytest.raises(NotFoundError):
            await service.get_log(TEST_LOG_ID, TEST_USER_ID)


class TestUpdateLog:
    async def test_returns_updated_log(
        self, log_repo: MagicMock, plant_repo: MagicMock, sample_log
    ) -> None:
        updated = sample_log.model_copy(update={"height_cm": 30.0})
        log_repo.update.return_value = updated
        service = make_service(log_repo, plant_repo)

        result = await service.update_log(TEST_LOG_ID, TEST_USER_ID, GrowthLogUpdate(height_cm=30.0))

        assert result.height_cm == 30.0

    async def test_raises_not_found_when_missing(
        self, log_repo: MagicMock, plant_repo: MagicMock
    ) -> None:
        log_repo.update.return_value = None
        service = make_service(log_repo, plant_repo)

        with pytest.raises(NotFoundError):
            await service.update_log(TEST_LOG_ID, TEST_USER_ID, GrowthLogUpdate())


class TestDeleteLog:
    async def test_succeeds_when_deleted(
        self, log_repo: MagicMock, plant_repo: MagicMock
    ) -> None:
        log_repo.delete.return_value = True
        service = make_service(log_repo, plant_repo)

        await service.delete_log(TEST_LOG_ID, TEST_USER_ID)  # should not raise

    async def test_raises_not_found_when_missing(
        self, log_repo: MagicMock, plant_repo: MagicMock
    ) -> None:
        log_repo.delete.return_value = False
        service = make_service(log_repo, plant_repo)

        with pytest.raises(NotFoundError):
            await service.delete_log(TEST_LOG_ID, TEST_USER_ID)
