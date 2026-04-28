"""Export status polling."""

from __future__ import annotations

from typing import Any


def format_export_status(export: dict[str, Any]) -> dict[str, Any]:
    """Format export record for API response."""
    return {
        "export_id": export["export_id"],
        "status": export["status"],
        "format": export["format"],
        "download_url": export.get("download_url"),
        "error": export.get("error"),
        "estimated_completion_seconds": 30 if export["status"] == "queued" else None,
        "created_at": export["created_at"],
        "completed_at": export.get("completed_at"),
    }
