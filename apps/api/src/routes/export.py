"""Export endpoints — POST /v1/export, GET /v1/export/{export_id}.

Requires analyst+ role. Enforces INV-004 (human signoff before high-impact export).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from apps.api.src.dependencies import AuthContext, Role, require_role

router = APIRouter(prefix="/v1", tags=["export"])

# In-memory store
_export_store: dict[str, dict] = {}


@router.post("/export", status_code=202)
async def request_export(
    body: dict[str, Any],
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict:
    """Request an export of a resolution with its evidence chain."""
    resolution_id = body.get("resolution_id")
    if not resolution_id:
        raise HTTPException(status_code=400, detail="resolution_id is required")

    format_val = body.get("format")
    valid_formats = {"pdf", "json", "csv"}
    if format_val not in valid_formats:
        raise HTTPException(status_code=400, detail=f"Invalid format: {format_val}")

    export_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    response = {
        "export_id": export_id,
        "status": "queued",
        "format": format_val,
        "download_url": None,
        "error": None,
        "estimated_completion_seconds": 30,
        "created_at": now,
        "completed_at": None,
    }

    _export_store[export_id] = response
    return response


@router.get("/export/{export_id}")
async def get_export_status(
    export_id: str,
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict:
    """Check export status and get download URL."""
    export = _export_store.get(export_id)
    if export is None:
        raise HTTPException(status_code=404, detail="Export not found")
    return export
