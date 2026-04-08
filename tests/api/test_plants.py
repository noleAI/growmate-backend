"""API integration tests for plant endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.exceptions.handlers import NotFoundError
from app.models.schemas.plant import PlantCreate
from tests.conftest import TEST_PLANT_ID, TEST_USER_ID


class TestCreatePlant:
    def test_returns_201_on_success(
        self, test_client: TestClient, mock_plant_service: MagicMock, sample_plant
    ) -> None:
        mock_plant_service.create_plant.return_value = sample_plant

        resp = test_client.post(
            "/api/v1/plants",
            json={"name": "Monstera", "species": "Monstera deliciosa"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Monstera"
        assert body["plant_id"] == str(TEST_PLANT_ID)

    def test_returns_422_when_name_missing(self, test_client: TestClient) -> None:
        resp = test_client.post("/api/v1/plants", json={})
        assert resp.status_code == 422


class TestListPlants:
    def test_returns_200_with_list(
        self, test_client: TestClient, mock_plant_service: MagicMock, sample_plant
    ) -> None:
        mock_plant_service.list_plants.return_value = [sample_plant]

        resp = test_client.get("/api/v1/plants")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_returns_empty_list(
        self, test_client: TestClient, mock_plant_service: MagicMock
    ) -> None:
        mock_plant_service.list_plants.return_value = []

        resp = test_client.get("/api/v1/plants")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetPlant:
    def test_returns_200_when_found(
        self, test_client: TestClient, mock_plant_service: MagicMock, sample_plant
    ) -> None:
        mock_plant_service.get_plant.return_value = sample_plant

        resp = test_client.get(f"/api/v1/plants/{TEST_PLANT_ID}")

        assert resp.status_code == 200
        assert resp.json()["plant_id"] == str(TEST_PLANT_ID)

    def test_returns_404_when_not_found(
        self, test_client: TestClient, mock_plant_service: MagicMock
    ) -> None:
        mock_plant_service.get_plant.side_effect = NotFoundError("not found")

        resp = test_client.get(f"/api/v1/plants/{TEST_PLANT_ID}")

        assert resp.status_code == 404


class TestUpdatePlant:
    def test_returns_200_on_success(
        self, test_client: TestClient, mock_plant_service: MagicMock, sample_plant
    ) -> None:
        updated = sample_plant.model_copy(update={"name": "Updated"})
        mock_plant_service.update_plant.return_value = updated

        resp = test_client.patch(
            f"/api/v1/plants/{TEST_PLANT_ID}", json={"name": "Updated"}
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    def test_returns_404_when_not_found(
        self, test_client: TestClient, mock_plant_service: MagicMock
    ) -> None:
        mock_plant_service.update_plant.side_effect = NotFoundError("not found")

        resp = test_client.patch(
            f"/api/v1/plants/{TEST_PLANT_ID}", json={"name": "X"}
        )

        assert resp.status_code == 404


class TestDeletePlant:
    def test_returns_204_on_success(
        self, test_client: TestClient, mock_plant_service: MagicMock
    ) -> None:
        mock_plant_service.delete_plant.return_value = None

        resp = test_client.delete(f"/api/v1/plants/{TEST_PLANT_ID}")

        assert resp.status_code == 204

    def test_returns_404_when_not_found(
        self, test_client: TestClient, mock_plant_service: MagicMock
    ) -> None:
        mock_plant_service.delete_plant.side_effect = NotFoundError("not found")

        resp = test_client.delete(f"/api/v1/plants/{TEST_PLANT_ID}")

        assert resp.status_code == 404
