from collections import defaultdict
from typing import DefaultDict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class DashboardConnectionManager:
    def __init__(self):
        self.active_connections: DefaultDict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if websocket in self.active_connections.get(session_id, []):
            self.active_connections[session_id].remove(websocket)
        if not self.active_connections.get(session_id):
            self.active_connections.pop(session_id, None)

    async def send_to_session(self, session_id: str, payload: str) -> None:
        targets = list(self.active_connections.get(session_id, []))
        targets.extend(self.active_connections.get("*", []))

        stale: list[tuple[str, WebSocket]] = []
        for websocket in targets:
            try:
                await websocket.send_text(payload)
            except Exception:  # noqa: BLE001
                stale.append((session_id, websocket))

        for stale_session, websocket in stale:
            self.disconnect(stale_session, websocket)


manager = DashboardConnectionManager()


@router.websocket("/stream")
async def websocket_dashboard_all(websocket: WebSocket):
    await manager.connect("*", websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect("*", websocket)


@router.websocket("/stream/{session_id}")
async def websocket_dashboard_session(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
