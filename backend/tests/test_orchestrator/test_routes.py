import pytest

from api.routes import orchestrator as orchestrator_route
from api.routes import session as session_route
from api.routes.orchestrator import OrchestratorStepRequest, run_orchestrator_step
from models.requests import InteractionRequest


class _OrchestratorStub:
    async def run_session_step(self, session_id: str, payload: dict) -> dict:
        del session_id, payload
        return {
            "action": "show_hint",
            "payload": {"text": "hint text"},
            "dashboard_update": {"academic": {"entropy": 0.33}},
            "latency_ms": 4,
        }


@pytest.mark.asyncio
async def test_orchestrator_route_invokes_runtime(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator_route, "get_orchestrator", lambda: _OrchestratorStub())

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
async def test_session_interact_uses_orchestrator(monkeypatch) -> None:
    monkeypatch.setattr(session_route, "get_orchestrator", lambda: _OrchestratorStub())

    response = await session_route.interact(
        session_id="sess-2",
        request=InteractionRequest(action_type="submit_answer", response_data={"answer": "A"}),
        user={"sub": "student-1"},
    )

    assert response.next_node_type == "show_hint"
    assert response.content == "hint text"
    assert response.belief_entropy == 0.33
