"""Degraded mode manager — tracks active degradation modes.

Each mode adds X-Degraded-Mode header to responses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DegradedMode(str, Enum):
    """All known degraded modes from resilience.md."""
    LLM_DEGRADED = "llm_degraded"
    READ_ONLY = "read_only"
    STORAGE_DEGRADED = "storage_degraded"
    AUTH_DEGRADED = "auth_degraded"
    EXPORT_DEGRADED = "export_degraded"


class DegradationManager:
    """Tracks which degraded modes are currently active."""

    def __init__(self) -> None:
        self._active: dict[DegradedMode, dict[str, Any]] = {}

    @property
    def active_modes(self) -> set[DegradedMode]:
        return set(self._active.keys())

    @property
    def is_degraded(self) -> bool:
        return len(self._active) > 0

    def enter_mode(self, mode: DegradedMode, reason: str) -> None:
        """Enter a degraded mode."""
        self._active[mode] = {
            "entered_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }

    def exit_mode(self, mode: DegradedMode) -> None:
        """Exit a degraded mode."""
        self._active.pop(mode, None)

    def is_mode_active(self, mode: DegradedMode) -> bool:
        return mode in self._active

    def get_response_headers(self) -> dict[str, str]:
        """Return X-Degraded-Mode headers for the current response."""
        if not self._active:
            return {}
        modes = ",".join(sorted(m.value for m in self._active))
        return {"X-Degraded-Mode": modes}

    def get_status(self) -> dict[str, Any]:
        """Get full degradation status for health probes."""
        return {
            "is_degraded": self.is_degraded,
            "active_modes": [
                {"mode": m.value, **info}
                for m, info in self._active.items()
            ],
        }
