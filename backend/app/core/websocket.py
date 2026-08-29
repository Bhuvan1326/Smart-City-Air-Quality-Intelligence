import json
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from app.core.logging import logger


class ConnectionManager:
    def __init__(self) -> None:
        # city -> list of websockets
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, city: str) -> None:
        await websocket.accept()
        if city not in self._connections:
            self._connections[city] = []
        self._connections[city].append(websocket)
        logger.info("ws.connected", city=city, total=len(self._connections[city]))

    def disconnect(self, websocket: WebSocket, city: str) -> None:
        if city in self._connections:
            self._connections[city] = [
                ws for ws in self._connections[city] if ws != websocket
            ]
        logger.info(
            "ws.disconnected", city=city, total=len(self._connections.get(city, []))
        )

    async def broadcast_to_city(self, city: str, event_type: str, data: Any) -> None:
        if city not in self._connections:
            return
        message = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            default=str,
        )

        dead = []
        for ws in self._connections[city]:
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 -- any send failure means socket is dead
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws, city)

    async def broadcast_all(self, event_type: str, data: Any) -> None:
        for city in list(self._connections.keys()):
            await self.broadcast_to_city(city, event_type, data)


ws_manager = ConnectionManager()
