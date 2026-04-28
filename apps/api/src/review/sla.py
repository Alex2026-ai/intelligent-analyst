"""SLA tracking — deadline computation and breach detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# Default SLA hours by priority (INV-011: from config, not hardcoded)
DEFAULT_SLA_HOURS: dict[str, int] = {
    "standard": 24,
    "high": 4,
    "urgent": 1,
}


def compute_sla_deadline(
    priority: str,
    created_at: str,
    sla_hours_override: dict[str, int] | None = None,
) -> str:
    """Compute SLA deadline based on priority.

    Args:
        priority: Case priority (standard, high, urgent).
        created_at: ISO 8601 creation timestamp.
        sla_hours_override: Optional per-tenant SLA configuration.

    Returns:
        ISO 8601 deadline timestamp.
    """
    sla_hours = (sla_hours_override or DEFAULT_SLA_HOURS).get(
        priority, DEFAULT_SLA_HOURS["standard"]
    )
    created = datetime.fromisoformat(created_at)
    deadline = created + timedelta(hours=sla_hours)
    return deadline.isoformat()


def is_breached(sla_deadline: str) -> bool:
    """Check if an SLA deadline has been breached."""
    deadline = datetime.fromisoformat(sla_deadline)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > deadline


def find_breached_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find cases that have breached their SLA deadline.

    Only checks cases with status 'pending' or 'assigned'.
    """
    return [
        c for c in cases
        if c.get("status") in ("pending", "assigned")
        and is_breached(c["sla_deadline"])
    ]
