"""API integration tests for growth log endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.exceptions.handlers import NotFoundError
from tests.conftest import TEST_LOG_ID, TEST_PLANT_ID


class TestCreateLog:
    def test_returns_201_on_success(
        self, test_client: TestClient, mock_growth_log_service: MagicMock, sample_log
    ) -> None:
        mock_growth_log_service.create_log.return_value = sample_log

        resp = test_client.post(
            f"/api/v1/plants/{TEST_PLANT_ID}/logs",
            json={"height_cm": 25.0, "leaf_count": 6, "notes": "Looking healthy"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["height_cm"] == 25.0
        assert body["log_id"] == str(TEST_LOG_ID)

    def test_returns_404_when_plant_not_found(
        self, test_client: TestClient, mock_growth_log_service: MagicMock
    ) -> None:
        mock_growth_log_service.create_log.side_effect = NotFoundError("plant not found")

        resp = test_client.post(
            f"/api/v1/plants/{TEST_PLANT_ID}/logs",
            json={"height_cm": 10.0},
        )

        assert resp.status_code == 404


class TestListLogs:
    def test_returns_200_with_list(
        self, test_client: TestClient, mock_growth_log_service: MagicMock, sample_log
    ) -> None:
        mock_growth_log_service.list_logs.return_value = [sample_log]

        resp = test_client.get(f"/api/v1/plants/{TEST_PLANT_ID}/logs")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_returns_404_when_plant_not_found(
        self, test_client: TestClient, mock_growth_log_service: MagicMock
    ) -> None:
        mock_growth_log_service.list_logs.side_effect = NotFoundError("plant not found")

        resp = test_client.get(f"/api/v1/plants/{TEST_PLANT_ID}/logs")

        assert resp.status_code == 404


class TestGetLog:
    def test_returns_200_when_found(
        self, test_client: TestClient, mock_growth_log_service: MagicMock, sample_log
    ) -> None:
        mock_growth_log_service.get_log.return_value = sample_log

        resp = test_client.get(f"/api/v1/plants/{TEST_PLANT_ID}/logs/{TEST_LOG_ID}")

        assert resp.status_code == 200
        assert resp.json()["log_id"] == str(TEST_LOG_ID)

    def test_returns_404_when_not_found(
        self, test_client: TestClient, mock_growth_log_service: MagicMock
    ) -> None:
        mock_growth_log_service.get_log.side_effect = NotFoundError("not found")

        resp = test_client.get(f"/api/v1/plants/{TEST_PLANT_ID}/logs/{TEST_LOG_ID}")

        assert resp.status_code == 404


class TestUpdateLog:
    def test_returns_200_on_success(
        self, test_client: TestClient, mock_growth_log_service: MagicMock, sample_log
    ) -> None:
        updated = sample_log.model_copy(update={"height_cm": 30.0})
        mock_growth_log_service.update_log.return_value = updated

        resp = test_client.patch(
            f"/api/v1/plants/{TEST_PLANT_ID}/logs/{TEST_LOG_ID}",
            json={"height_cm": 30.0},
        )

        assert resp.status_code == 200
        assert resp.json()["height_cm"] == 30.0

    def test_returns_404_when_not_found(
        self, test_client: TestClient, mock_growth_log_service: MagicMock
    ) -> None:
        mock_growth_log_service.update_log.side_effect = NotFoundError("not found")

        resp = test_client.patch(
            f"/api/v1/plants/{TEST_PLANT_ID}/logs/{TEST_LOG_ID}",
            json={"height_cm": 30.0},
        )

        assert resp.status_code == 404


class TestDeleteLog:
    def test_returns_204_on_success(
        self, test_client: TestClient, mock_growth_log_service: MagicMock
    ) -> None:
        mock_growth_log_service.delete_log.return_value = None

        resp = test_client.delete(
            f"/api/v1/plants/{TEST_PLANT_ID}/logs/{TEST_LOG_ID}"
        )

        assert resp.status_code == 204

    def test_returns_404_when_not_found(
        self, test_client: TestClient, mock_growth_log_service: MagicMock
    ) -> None:
        mock_growth_log_service.delete_log.side_effect = NotFoundError("not found")

        resp = test_client.delete(
            f"/api/v1/plants/{TEST_PLANT_ID}/logs/{TEST_LOG_ID}"
        )

        assert resp.status_code == 404
