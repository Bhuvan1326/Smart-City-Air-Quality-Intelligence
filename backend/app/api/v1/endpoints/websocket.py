from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.database import AsyncSessionLocal
from app.core.websocket import ws_manager

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/live/{city}")
async def websocket_live(
    websocket: WebSocket,
    city: str,
    token: str = Query(...),
) -> None:
    """
    WebSocket endpoint for live AQI updates, anomaly alerts, and officer tracking.
    Client connects with: ws://host/api/v1/ws/live/{city}?token=<jwt>

    Authentication must only accept a valid ACCESS token (never a refresh
    token) belonging to an existing, active user. `AuthService.get_current_user`
    already enforces: signature -> expiration -> type == "access" -> user
    exists -> user is active.
    """
    from app.services.auth import AuthService

    async with AsyncSessionLocal() as session:
        try:
            auth_service = AuthService(session)
            await auth_service.get_current_user(token)
        except ValueError:
            await websocket.close(code=4001, reason="Invalid token")
            return

    await ws_manager.connect(websocket, city)
    try:
        while True:
            # Client can send heartbeat or filter commands
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, city)
