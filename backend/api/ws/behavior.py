import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agents.base import AgentInput
from agents.empathy_agent.particle_filter import particle_filter
from core.config import get_settings

router = APIRouter()
settings = get_settings()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)


manager = ConnectionManager()


@router.websocket("/{session_id}")
async def behavior_websocket(websocket: WebSocket, session_id: str):
    await manager.connect(websocket)
    try:
        while True:
            # Receive real-time telemetry (typing speed, correct_rate, etc.)
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                if not isinstance(payload, dict):
                    payload = {}

                pf_output = await particle_filter.process(
                    AgentInput(
                        session_id=session_id,
                        behavior_signals=payload,
                    )
                )

                state_payload = pf_output.payload
                uncertainty = float(
                    state_payload.get(
                        "uncertainty", state_payload.get("uncertainty_score", 1.0)
                    )
                )

                if uncertainty > settings.hitl_uncertainty_threshold:
                    await manager.send_personal_message(
                        json.dumps(
                            {
                                "event": "intervention_proposed",
                                "type": "recovery_mode",
                                "confidence": round(max(0.0, 1.0 - uncertainty), 3),
                                "session_id": session_id,
                                "state_summary": {
                                    "confusion": state_payload.get("confusion", 0.0),
                                    "fatigue": state_payload.get("fatigue", 0.0),
                                    "uncertainty": uncertainty,
                                },
                            }
                        ),
                        websocket,
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps(
                        {
                            "event": "invalid_payload",
                            "message": "Expected valid JSON payload.",
                        }
                    ),
                    websocket,
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
