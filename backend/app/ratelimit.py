"""Per-IP fixed-window rate limiting (SR-3). Clock injectable for tests."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Window:
    count: int
    window_start: float


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock=time.monotonic) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[tuple[str, str], _Window] = {}

    def _key_window(self, bucket: str, key: str) -> _Window:
        k = (bucket, key)
        window = self._hits.get(k)
        now = self._clock()
        if window is None or now - window.window_start >= self.window_seconds:
            window = _Window(count=0, window_start=now)
            self._hits[k] = window
        return window

    def hit(self, bucket: str, key: str) -> bool:
        """Record one event. True = allowed, False = over the limit (429)."""
        window = self._key_window(bucket, key)
        if window.count >= self.limit:
            return False
        window.count += 1
        return True

    def allowed(self, bucket: str, key: str) -> bool:
        """Check without recording (peek)."""
        return self._key_window(bucket, key).count < self.limit

    def reset(self) -> None:
        self._hits.clear()
