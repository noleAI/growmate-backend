"""Unit tests for PlantService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exceptions.handlers import NotFoundError
from app.models.schemas.plant import PlantCreate, PlantUpdate
from app.services.plant_service import PlantService
from tests.conftest import TEST_PLANT_ID, TEST_USER_ID


def make_plant_service(repo: MagicMock) -> PlantService:
    return PlantService(repo)


@pytest.fixture()
def plant_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.list_for_user = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    return repo


class TestCreatePlant:
    async def test_delegates_to_repo(self, plant_repo: MagicMock, sample_plant) -> None:
        plant_repo.create.return_value = sample_plant
        service = make_plant_service(plant_repo)
        data = PlantCreate(name="Monstera", species="Monstera deliciosa")

        result = await service.create_plant(TEST_USER_ID, data)

        plant_repo.create.assert_awaited_once_with(TEST_USER_ID, data)
        assert result == sample_plant


class TestListPlants:
    async def test_returns_list(self, plant_repo: MagicMock, sample_plant) -> None:
        plant_repo.list_for_user.return_value = [sample_plant]
        service = make_plant_service(plant_repo)

        result = await service.list_plants(TEST_USER_ID)

        assert result == [sample_plant]

    async def test_returns_empty_list(self, plant_repo: MagicMock) -> None:
        plant_repo.list_for_user.return_value = []
        service = make_plant_service(plant_repo)

        result = await service.list_plants(TEST_USER_ID)

        assert result == []


class TestGetPlant:
    async def test_returns_plant_when_found(self, plant_repo: MagicMock, sample_plant) -> None:
        plant_repo.get_by_id.return_value = sample_plant
        service = make_plant_service(plant_repo)

        result = await service.get_plant(TEST_PLANT_ID, TEST_USER_ID)

        assert result == sample_plant

    async def test_raises_not_found_when_missing(self, plant_repo: MagicMock) -> None:
        plant_repo.get_by_id.return_value = None
        service = make_plant_service(plant_repo)

        with pytest.raises(NotFoundError):
            await service.get_plant(TEST_PLANT_ID, TEST_USER_ID)


class TestUpdatePlant:
    async def test_returns_updated_plant(self, plant_repo: MagicMock, sample_plant) -> None:
        updated = sample_plant.model_copy(update={"name": "Big Monstera"})
        plant_repo.update.return_value = updated
        service = make_plant_service(plant_repo)
        data = PlantUpdate(name="Big Monstera")

        result = await service.update_plant(TEST_PLANT_ID, TEST_USER_ID, data)

        assert result.name == "Big Monstera"

    async def test_raises_not_found_when_missing(self, plant_repo: MagicMock) -> None:
        plant_repo.update.return_value = None
        service = make_plant_service(plant_repo)

        with pytest.raises(NotFoundError):
            await service.update_plant(TEST_PLANT_ID, TEST_USER_ID, PlantUpdate())


class TestDeletePlant:
    async def test_succeeds_when_deleted(self, plant_repo: MagicMock) -> None:
        plant_repo.delete.return_value = True
        service = make_plant_service(plant_repo)

        await service.delete_plant(TEST_PLANT_ID, TEST_USER_ID)  # should not raise

    async def test_raises_not_found_when_missing(self, plant_repo: MagicMock) -> None:
        plant_repo.delete.return_value = False
        service = make_plant_service(plant_repo)

        with pytest.raises(NotFoundError):
            await service.delete_plant(TEST_PLANT_ID, TEST_USER_ID)
