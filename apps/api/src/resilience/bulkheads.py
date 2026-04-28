"""Bulkhead pattern — separate resource pools to prevent cross-contamination.

Uses asyncio Semaphores to limit concurrent operations per pool.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class BulkheadConfig:
    """Configuration for a single bulkhead."""
    max_concurrent: int


class Bulkhead:
    """A single bulkhead with a concurrency semaphore."""

    def __init__(self, name: str, max_concurrent: int) -> None:
        self.name = name
        self._max = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0

    @property
    def active_count(self) -> int:
        return self._active

    @property
    def available(self) -> int:
        return self._max - self._active

    @property
    def is_full(self) -> bool:
        return self._active >= self._max

    async def acquire(self) -> bool:
        """Try to acquire a slot. Returns False if full."""
        if self._active >= self._max:
            return False
        await self._semaphore.acquire()
        self._active += 1
        return True

    def release(self) -> None:
        """Release a slot."""
        if self._active > 0:
            self._active -= 1
            self._semaphore.release()


# Default bulkhead configurations
DEFAULT_BULKHEADS: dict[str, int] = {
    "resolution": 50,
    "review": 20,
    "admin": 5,
    "background": 10,
}


class BulkheadRegistry:
    """Registry of all bulkheads."""

    def __init__(self, configs: dict[str, int] | None = None) -> None:
        configs = configs or DEFAULT_BULKHEADS
        self._bulkheads = {
            name: Bulkhead(name, max_concurrent)
            for name, max_concurrent in configs.items()
        }

    def get(self, name: str) -> Bulkhead:
        return self._bulkheads[name]

    def get_all_status(self) -> dict[str, dict[str, int]]:
        return {
            name: {"active": b.active_count, "available": b.available}
            for name, b in self._bulkheads.items()
        }
