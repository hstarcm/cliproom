"""Presence/WebSocket connection registry (FR-16, FR-18).

One process-local hub; the deployment runs a single uvicorn worker (§5), so an
in-memory registry is sufficient. Room IDs never leave this process in
telemetry — events carry only member data and item data.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectedMember:
    member_id: str
    name: str
    color: str
    room_id: str
    last_heartbeat: float = field(default_factory=time.monotonic)


class WSHub:
    """Tracks connected sockets per room and broadcasts JSON events."""

    IDLE_DROP_SECONDS = 5 * 60  # FR-18: idle > 5 min drops presence

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # room_id -> member_id -> (websocket, ConnectedMember)
        self._rooms: dict[str, dict[str, tuple[Any, ConnectedMember]]] = {}
        self._last_presence_check = 0.0

    async def connect(self, room_id: str, member: ConnectedMember, websocket) -> None:
        async with self._lock:
            self._rooms.setdefault(room_id, {})[member.member_id] = (websocket, member)

    async def disconnect(self, room_id: str, member_id: str) -> ConnectedMember | None:
        async with self._lock:
            room = self._rooms.get(room_id)
            if not room:
                return None
            entry = room.pop(member_id, None)
            if not room:
                self._rooms.pop(room_id, None)
            return entry[1] if entry else None

    async def members_of(self, room_id: str) -> list[ConnectedMember]:
        async with self._lock:
            return [m for _, m in self._rooms.get(room_id, {}).values()]

    def members_snapshot(self, room_id: str) -> list[ConnectedMember]:
        """Lock-free read for sync routes (single event loop + GIL: safe)."""
        room = self._rooms.get(room_id, {})
        return [m for _, m in room.values()]

    async def heartbeat(self, room_id: str, member_id: str) -> None:
        async with self._lock:
            room = self._rooms.get(room_id)
            if room and member_id in room:
                room[member_id][1].last_heartbeat = time.monotonic()

    async def drop_idle(self, now: float | None = None) -> list[tuple[str, ConnectedMember]]:
        """Remove members idle beyond IDLE_DROP_SECONDS; returns (room_id, member)."""
        now = now if now is not None else time.monotonic()
        dropped: list[tuple[str, ConnectedMember]] = []
        async with self._lock:
            for room_id in list(self._rooms):
                for member_id, (_, member) in list(self._rooms[room_id].items()):
                    if now - member.last_heartbeat > self.IDLE_DROP_SECONDS:
                        dropped.append((room_id, self._rooms[room_id].pop(member_id)[1]))
                if not self._rooms[room_id]:
                    self._rooms.pop(room_id)
        return dropped

    async def broadcast(self, room_id: str, event: dict, exclude: str | None = None) -> None:
        async with self._lock:
            sockets = [ws for mid, (ws, _) in self._rooms.get(room_id, {}).items() if mid != exclude]
        for ws in sockets:
            try:
                await ws.send_json(event)
            except Exception:
                # dead socket; presence sweep will clean it up
                pass


hub = WSHub()
