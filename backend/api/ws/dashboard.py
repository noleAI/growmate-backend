from collections import defaultdict
from typing import DefaultDict, List

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from core.security import get_current_user_ws

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
        # Build list of (origin_key, websocket) so we can remove stale sockets
        session_targets = [ (session_id, ws) for ws in list(self.active_connections.get(session_id, [])) ]
        global_targets = [ ("*", ws) for ws in list(self.active_connections.get("*", [])) ]
        targets = session_targets + global_targets

        stale: list[tuple[str, WebSocket]] = []
        for origin_key, websocket in targets:
            try:
                await websocket.send_text(payload)
            except Exception:  # noqa: BLE001
                stale.append((origin_key, websocket))

        for origin_key, websocket in stale:
            # Disconnect using the originating key so global subscribers are removed from the "*" list
            self.disconnect(origin_key, websocket)


manager = DashboardConnectionManager()


@router.websocket("/stream")
async def websocket_dashboard_all(
    websocket: WebSocket,
    user: dict = Depends(get_current_user_ws),
):
    del user
    await manager.connect("*", websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect("*", websocket)


@router.websocket("/stream/{session_id}")
async def websocket_dashboard_session(
    websocket: WebSocket,
    session_id: str,
    user: dict = Depends(get_current_user_ws),
):
    del user
    await manager.connect(session_id, websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
