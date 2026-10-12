from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.database import AsyncSessionLocal
from app.core.websocket import ws_manager
from app.models.user import User, UserRole

router = APIRouter(prefix="/ws", tags=["WebSocket"])

_STAFF_ROLES: frozenset[UserRole] = frozenset(
    {
        UserRole.CITY_ADMINISTRATOR,
        UserRole.POLLUTION_CONTROL_OFFICER,
        UserRole.FIELD_INSPECTOR,
    }
)


def is_city_subscription_allowed(user: User, city: str) -> bool:

    if user.role in _STAFF_ROLES:
        return True
    if not user.city:
        return False
    return user.city.strip().lower() == city.strip().lower()


@router.websocket("/live/{city}")
async def websocket_live(
    websocket: WebSocket,
    city: str,
    token: str = Query(...),
) -> None:

    from app.services.auth import AuthService

    async with AsyncSessionLocal() as session:
        try:
            auth_service = AuthService(session)
            user = await auth_service.get_current_user(token)
        except ValueError:
            await websocket.close(code=4001, reason="Invalid token")
            return

    if not is_city_subscription_allowed(user, city):
        await websocket.close(code=4403, reason="Not authorized for this city")
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
