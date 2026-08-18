"""Tracks connected WebSocket clients and broadcasts to them."""
import asyncio

from fastapi import WebSocket


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        """Send to every connected client, dropping any that have gone
        away. A dead connection must not break delivery to the rest."""
        async with self._lock:
            targets = list(self._connections)

        dead = []
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)

        if dead:
            async with self._lock:
                for websocket in dead:
                    self._connections.discard(websocket)

    def count(self) -> int:
        return len(self._connections)


hub = ConnectionHub()