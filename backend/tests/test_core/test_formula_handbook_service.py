import pytest

from core import formula_handbook_service as handbook_module


async def _noop_async(**kwargs):
    del kwargs
    return None


async def _empty_sessions(**kwargs):
    del kwargs
    return []


async def _empty_states(**kwargs):
    del kwargs
    return []


async def _xp_mid(**kwargs):
    del kwargs
    return {
        "total_xp": 800,
        "current_streak": 2,
    }


async def _sessions_with_data(**kwargs):
    del kwargs
    return ["sess-1", "sess-2"]


async def _state_rows(**kwargs):
    del kwargs
    return [
        {
            "session_id": "sess-1",
            "belief_dist": {
                "H01_Trig": 0.2,
                "H02_ExpLog": 0.3,
                "H03_Chain": 0.1,
                "H04_Rules": 0.4,
            },
        },
        {
            "session_id": "sess-2",
            "belief_dist": (
                '{"H01_Trig": 0.4, "H02_ExpLog": 0.2, '
                '"H03_Chain": 0.2, "H04_Rules": 0.2}'
            ),
        },
    ]


async def _xp_unused(**kwargs):
    del kwargs
    return {"total_xp": 0, "current_streak": 0}


def test_normalize_category() -> None:
    service = handbook_module.FormulaHandbookService()

    assert service.normalize_category("basic_trig") == "basic_trig"
    assert service.normalize_category("ALL") == "all"
    assert service.normalize_category("invalid") == ""


@pytest.mark.asyncio
async def test_mastery_fallback_from_xp(monkeypatch) -> None:
    service = handbook_module.FormulaHandbookService()

    monkeypatch.setattr(handbook_module, "list_learning_session_ids", _empty_sessions)
    monkeypatch.setattr(handbook_module, "list_agent_state_rows", _empty_states)
    monkeypatch.setattr(handbook_module, "get_user_xp", _xp_mid)

    mastery = await service.get_mastery_by_hypothesis("student-1", "token")

    assert mastery["H01_Trig"] == 64
    assert mastery["H02_ExpLog"] == 64
    assert mastery["H03_Chain"] == 64
    assert mastery["H04_Rules"] == 64


@pytest.mark.asyncio
async def test_mastery_from_agent_state(monkeypatch) -> None:
    service = handbook_module.FormulaHandbookService()

    monkeypatch.setattr(handbook_module, "list_learning_session_ids", _sessions_with_data)
    monkeypatch.setattr(handbook_module, "list_agent_state_rows", _state_rows)
    monkeypatch.setattr(handbook_module, "get_user_xp", _xp_unused)

    mastery = await service.get_mastery_by_hypothesis("student-1", "token")

    assert mastery["H01_Trig"] == 70
    assert mastery["H02_ExpLog"] == 75
    assert mastery["H03_Chain"] == 85
    assert mastery["H04_Rules"] == 70
