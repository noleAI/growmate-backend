import pytest
from fastapi import HTTPException

from api.routes import formulas as formulas_route


@pytest.mark.asyncio
async def test_get_formulas_all(monkeypatch) -> None:
    async def _catalog_stub(**kwargs) -> list[dict]:
        assert kwargs["category"] == "all"
        return [
            {
                "id": "basic_trig",
                "name": "Đạo hàm lượng giác",
                "description": "",
                "formula_count": 1,
                "mastery_percent": 80,
                "formulas": [{"id": "sin_derivative"}],
            }
        ]

    monkeypatch.setattr(
        formulas_route.formula_handbook_service,
        "get_catalog_for_user",
        _catalog_stub,
    )

    result = await formulas_route.get_formulas(
        category="all",
        search=None,
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["category"] == "all"
    assert len(result["categories"]) == 1


@pytest.mark.asyncio
async def test_get_formulas_single_category(monkeypatch) -> None:
    async def _catalog_stub(**kwargs) -> list[dict]:
        assert kwargs["category"] == "basic_trig"
        return [
            {
                "id": "basic_trig",
                "name": "Đạo hàm lượng giác",
                "description": "",
                "formula_count": 1,
                "mastery_percent": 80,
                "formulas": [{"id": "sin_derivative"}],
            }
        ]

    monkeypatch.setattr(
        formulas_route.formula_handbook_service,
        "get_catalog_for_user",
        _catalog_stub,
    )

    result = await formulas_route.get_formulas(
        category="basic_trig",
        search="sin",
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["category"] == "basic_trig"
    assert len(result["formulas"]) == 1


@pytest.mark.asyncio
async def test_get_formulas_invalid_category() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await formulas_route.get_formulas(
            category="unknown",
            search=None,
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_formulas_requires_user_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await formulas_route.get_formulas(
            category="all",
            search=None,
            user={},
            access_token="token",
        )

    assert exc_info.value.status_code == 401
