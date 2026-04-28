"""Auto-assignment logic — round-robin with capacity limits.

Kill switch `kill.review_assignment` disables auto-assignment.
"""

from __future__ import annotations

from typing import Any


class ReviewAssigner:
    """Assigns cases to reviewers using round-robin with capacity limits."""

    def __init__(
        self,
        max_active_per_reviewer: int = 10,
        assignment_enabled: bool = True,
    ) -> None:
        self._max_active = max_active_per_reviewer
        self._enabled = assignment_enabled
        self._last_assigned_index = -1

    @property
    def enabled(self) -> bool:
        return self._enabled

    def disable(self) -> None:
        """Disable auto-assignment (kill switch engaged)."""
        self._enabled = False

    def enable(self) -> None:
        """Re-enable auto-assignment."""
        self._enabled = True

    def assign(
        self,
        reviewers: list[dict[str, Any]],
        active_counts: dict[str, int],
    ) -> str | None:
        """Select next reviewer using round-robin with capacity check.

        Args:
            reviewers: List of reviewer dicts with 'user_id'.
            active_counts: Map of reviewer_id → current active case count.

        Returns:
            reviewer_id to assign to, or None if no reviewer available
            or assignment is disabled.
        """
        if not self._enabled:
            return None

        if not reviewers:
            return None

        n = len(reviewers)
        for i in range(n):
            idx = (self._last_assigned_index + 1 + i) % n
            reviewer_id = reviewers[idx]["user_id"]
            current_load = active_counts.get(reviewer_id, 0)
            if current_load < self._max_active:
                self._last_assigned_index = idx
                return reviewer_id

        return None  # All at capacity
