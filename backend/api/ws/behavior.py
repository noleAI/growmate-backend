import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
                # Update Particle Filter with observation
                particle_filter.update(payload)
                particle_filter.systematic_resample()

                # Check metrics
                state_summary = particle_filter.get_state_summary()
                if (
                    state_summary.get("uncertainty_score", 0)
                    > settings.hitl_uncertainty_threshold
                ):
                    await manager.send_personal_message(
                        json.dumps(
                            {
                                "event": "intervention_proposed",
                                "type": "recovery_mode",
                                "confidence": 0.88,
                            }
                        ),
                        websocket,
                    )

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
