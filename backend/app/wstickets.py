"""One-time WebSocket tickets (SR-7): member tokens never appear in WS URLs
or access logs — clients exchange the token for a short-lived ticket."""

from __future__ import annotations

import secrets
import time

TICKET_TTL_SECONDS = 60


class TicketStore:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._tickets: dict[str, tuple[str, str, float]] = {}  # ticket -> (room_id, member_id, expires)

    def issue(self, room_id: str, member_id: str) -> str:
        self._evict()
        ticket = secrets.token_urlsafe(32)
        self._tickets[ticket] = (room_id, member_id, self._clock() + TICKET_TTL_SECONDS)
        return ticket

    def redeem(self, ticket: str) -> tuple[str, str] | None:
        """Single-use: returns (room_id, member_id) or None if invalid/expired."""
        self._evict()
        entry = self._tickets.pop(ticket, None)
        if entry is None or entry[2] < self._clock():
            return None
        return entry[0], entry[1]

    def _evict(self) -> None:
        now = self._clock()
        for t in [t for t, e in self._tickets.items() if e[2] < now]:
            self._tickets.pop(t, None)


tickets = TicketStore()
