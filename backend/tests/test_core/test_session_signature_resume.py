import pytest
from fastapi import HTTPException

from api.routes import session as session_route
from core.runtime_metrics import get_metrics_snapshot, reset_metrics
from models.requests import InteractionRequest


class _RequestStub:
    method = "POST"

    class _URL:
        path = "/api/v1/sessions/sess-signature/interact"

    url = _URL()
    headers: dict = {}

    async def body(self) -> bytes:
        return b"{}"


class _OrchestratorStub:
    async def run_session_step(self, session_id: str, payload: dict) -> dict:
        del session_id, payload
        return {
            "action": "show_hint",
            "payload": {"text": "hint text"},
            "dashboard_update": {"academic": {"entropy": 0.21}},
        }


@pytest.mark.asyncio
async def test_interact_applies_signature_resume_grace(monkeypatch) -> None:
    reset_metrics()
    verify_calls: list[int] = []

    async def _verify_stub(http_request, secret: str | None, ttl_seconds: int) -> None:
        del http_request, secret
        verify_calls.append(int(ttl_seconds))
        if len(verify_calls) == 1:
            raise HTTPException(status_code=401, detail="signature_expired")

    monkeypatch.setattr(session_route, "verify_quiz_signature", _verify_stub)
    monkeypatch.setattr(session_route, "_resolve_signature_config", lambda: ("secret", 300))
    monkeypatch.setattr(session_route, "_resolve_signature_resume_grace_seconds", lambda: 1800)
    monkeypatch.setattr(
        session_route,
        "get_orchestrator",
        lambda session_id=None: _OrchestratorStub(),
    )

    response = await session_route.interact(
        http_request=_RequestStub(),
        session_id="sess-signature",
        request=InteractionRequest(
            action_type="submit_answer",
            mode="explore",
            resume=True,
            response_data={"answer": "A"},
        ),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert response.next_node_type == "show_hint"
    assert verify_calls == [300, 1800]
    metrics = get_metrics_snapshot()
    assert metrics.get("signature_expired_total", 0) >= 1
    assert metrics.get("resume_signature_grace_used_total", 0) >= 1
    assert metrics.get("resume_success_total", 0) >= 1


@pytest.mark.asyncio
async def test_interact_signature_expired_without_resume_still_rejected(monkeypatch) -> None:
    reset_metrics()
    async def _verify_stub(http_request, secret: str | None, ttl_seconds: int) -> None:
        del http_request, secret, ttl_seconds
        raise HTTPException(status_code=401, detail="signature_expired")

    monkeypatch.setattr(session_route, "verify_quiz_signature", _verify_stub)
    monkeypatch.setattr(session_route, "_resolve_signature_config", lambda: ("secret", 300))

    with pytest.raises(HTTPException) as exc_info:
        await session_route.interact(
            http_request=_RequestStub(),
            session_id="sess-signature-2",
            request=InteractionRequest(
                action_type="submit_answer",
                mode="explore",
                resume=False,
                response_data={"answer": "A"},
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "signature_expired"
    metrics = get_metrics_snapshot()
    assert metrics.get("signature_expired_total", 0) >= 1
