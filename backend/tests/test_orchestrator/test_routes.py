import pytest
from fastapi import HTTPException

from api.routes import orchestrator as orchestrator_route
from api.routes import session as session_route
from api.routes.orchestrator import OrchestratorStepRequest, run_orchestrator_step
from models.requests import InteractionRequest


class _OrchestratorStub:
    def __init__(self) -> None:
        self.last_payload: dict | None = None

    async def run_session_step(self, session_id: str, payload: dict) -> dict:
        del session_id
        self.last_payload = payload
        return {
            "action": "show_hint",
            "payload": {"text": "hint text"},
            "dashboard_update": {"academic": {"entropy": 0.33}},
            "latency_ms": 4,
        }


@pytest.mark.asyncio
async def test_orchestrator_route_invokes_runtime(monkeypatch) -> None:
    stub = _OrchestratorStub()
    monkeypatch.setattr(
        orchestrator_route,
        "get_orchestrator",
        lambda session_id=None: stub,
    )

    result = await run_orchestrator_step(
        OrchestratorStepRequest(
            session_id="sess-1",
            question_id="q1",
            response={"answer": "A"},
            behavior_signals={"response_time_ms": 8000},
        ),
        user={"sub": "student-1"},
    )

    assert result["status"] == "ok"
    assert result["result"]["action"] == "show_hint"


@pytest.mark.asyncio
async def test_orchestrator_route_forwards_xp_and_mode(monkeypatch) -> None:
    stub = _OrchestratorStub()
    monkeypatch.setattr(
        orchestrator_route,
        "get_orchestrator",
        lambda session_id=None: stub,
    )

    result = await run_orchestrator_step(
        OrchestratorStepRequest(
            session_id="sess-1b",
            question_id="q2",
            response={"answer": "B"},
            behavior_signals={"response_time_ms": 6100},
            xp_data={"recent_xp_gain": 80, "streak_days": 3},
            mode="explore",
            classification_level="advanced",
        ),
        user={"sub": "student-2"},
    )

    assert result["status"] == "ok"
    assert stub.last_payload is not None
    assert stub.last_payload["xp_data"] == {"recent_xp_gain": 80, "streak_days": 3}
    assert stub.last_payload["mode"] == "explore"
    assert stub.last_payload["classification_level"] == "advanced"


@pytest.mark.asyncio
async def test_session_interact_uses_orchestrator(monkeypatch) -> None:
    monkeypatch.setattr(
        session_route,
        "get_orchestrator",
        lambda session_id=None: _OrchestratorStub(),
    )

    response = await session_route.interact(
        session_id="sess-2",
        request=InteractionRequest(action_type="submit_answer", response_data={"answer": "A"}),
        user={"sub": "student-1"},
    )

    assert response.next_node_type == "show_hint"
    assert response.content == "hint text"
    assert response.belief_entropy == 0.33


@pytest.mark.asyncio
async def test_update_session_success(monkeypatch) -> None:
    async def _update_learning_session_stub(**kwargs) -> dict:
        del kwargs
        return {
            "data": [{"id": "sess-3", "status": "completed"}],
            "count": 1,
        }

    monkeypatch.setattr(
        session_route,
        "update_learning_session",
        _update_learning_session_stub,
    )

    result = await session_route.update_session(
        session_id="sess-3",
        request=session_route.UpdateSessionRequest(status="completed"),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["status"] == "success"
    assert result["session_id"] == "sess-3"
    assert result["session_status"] == "completed"


@pytest.mark.asyncio
async def test_update_session_rejects_invalid_status() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await session_route.update_session(
            session_id="sess-4",
            request=session_route.UpdateSessionRequest(status="paused"),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_update_session_not_found(monkeypatch) -> None:
    async def _update_learning_session_stub(**kwargs) -> dict:
        del kwargs
        return {"data": [], "count": 0}

    monkeypatch.setattr(
        session_route,
        "update_learning_session",
        _update_learning_session_stub,
    )

    with pytest.raises(HTTPException) as exc_info:
        await session_route.update_session(
            session_id="sess-5",
            request=session_route.UpdateSessionRequest(status="active"),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 404
