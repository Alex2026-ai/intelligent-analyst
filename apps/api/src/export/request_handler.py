"""Export request handling — validate and publish."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class ExportRequestHandler:
    """Handles export requests: validates preconditions, creates export record."""

    def __init__(self, event_publisher: Any = None) -> None:
        self._publisher = event_publisher
        self._exports: dict[str, dict[str, Any]] = {}

    def request_export(
        self,
        resolution_id: str,
        format: str,
        include_evidence: bool = True,
        include_source_document: bool = False,
        requested_by: str = "",
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Create an export request and publish event."""
        export_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        export_record = {
            "export_id": export_id,
            "resolution_id": resolution_id,
            "format": format,
            "status": "queued",
            "include_evidence": include_evidence,
            "include_source_document": include_source_document,
            "requested_by": requested_by,
            "tenant_id": tenant_id,
            "created_at": now,
            "completed_at": None,
            "download_url": None,
            "error": None,
        }

        self._exports[export_id] = export_record

        # Publish event (in production, to Pub/Sub)
        if self._publisher:
            self._publisher.publish({
                "event_type": "export.requested",
                "export_id": export_id,
                "resolution_id": resolution_id,
                "format": format,
                "tenant_id": tenant_id,
            })

        return export_record

    def get_status(self, export_id: str) -> dict[str, Any] | None:
        return self._exports.get(export_id)

    def update_status(
        self, export_id: str, status: str, download_url: str | None = None, error: str | None = None
    ) -> None:
        export = self._exports.get(export_id)
        if export:
            export["status"] = status
            if download_url:
                export["download_url"] = download_url
            if error:
                export["error"] = error
            if status in ("complete", "failed"):
                export["completed_at"] = datetime.now(timezone.utc).isoformat()
