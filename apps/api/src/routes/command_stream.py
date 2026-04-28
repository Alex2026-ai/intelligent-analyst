"""SSE stream for real-time command execution status.

Emits stage transitions as server-sent events. The frontend
CommandReceipt listens to this instead of using timers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/v1", tags=["command"])

# In-memory stage store (production: Firestore + Pub/Sub)
_stage_store: dict[str, list[dict[str, Any]]] = {}


def _merkle_hash(data: str) -> str:
    """Compute a short merkle-style hash for spec anchoring."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def emit_stage(correlation_id: str, stage: str, detail: dict[str, Any] | None = None) -> None:
    """Push a stage event for a correlation ID. Called by the resolve pipeline."""
    if correlation_id not in _stage_store:
        _stage_store[correlation_id] = []

    event = {
        "stage": stage,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detail": detail or {},
    }

    # Attach spec anchors for key stages
    if stage == "pii_masking":
        event["spec_anchor"] = {
            "spec_id": "INV-006",
            "version": "1.0",
            "title": "PII Masking Before External Calls",
            "merkle_hash": _merkle_hash("INV-006:PII must be masked before any data leaves the application boundary"),
        }
    elif stage == "llm_resolve":
        event["spec_anchor"] = {
            "spec_id": "PHASE-8",
            "version": "1.0",
            "title": "LLM Provider Abstraction",
            "merkle_hash": _merkle_hash("PHASE-8:AnthropicProvider with circuit breaker and kill switch"),
        }
    elif stage == "evidence_chain":
        event["spec_anchor"] = {
            "spec_id": "INV-002",
            "version": "1.0",
            "title": "Complete Evidence Lineage",
            "merkle_hash": _merkle_hash("INV-002:Every resolution traceable through unbroken evidence chain"),
        }
    elif stage == "tenant_scope":
        event["spec_anchor"] = {
            "spec_id": "INV-005",
            "version": "1.0",
            "title": "Tenant Isolation",
            "merkle_hash": _merkle_hash("INV-005:No API call ever leaks data across tenant boundaries"),
        }

    _stage_store[correlation_id].append(event)


def get_stages(correlation_id: str) -> list[dict[str, Any]]:
    """Get all stages for a correlation ID."""
    return list(_stage_store.get(correlation_id, []))


async def _stream_stages(
    correlation_id: str, request: Request
) -> AsyncGenerator[str, None]:
    """SSE generator — yields events as stages arrive."""
    sent = 0
    idle_ticks = 0
    max_idle = 60  # 30 seconds at 0.5s intervals

    while idle_ticks < max_idle:
        if await request.is_disconnected():
            break

        stages = _stage_store.get(correlation_id, [])

        # Emit any new stages
        while sent < len(stages):
            event = stages[sent]
            yield f"event: stage\ndata: {json.dumps(event)}\n\n"
            sent += 1
            idle_ticks = 0

            # If completed, send done and exit
            if event["stage"] == "completed":
                yield f"event: done\ndata: {json.dumps({'correlation_id': correlation_id})}\n\n"
                return

        idle_ticks += 1
        await asyncio.sleep(0.5)

    # Timeout — send close
    yield f"event: timeout\ndata: {json.dumps({'correlation_id': correlation_id})}\n\n"


@router.get("/command/stream/{correlation_id}")
async def stream_command_status(correlation_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint for real-time command execution status.

    Events:
        event: stage   — {stage, timestamp, detail, spec_anchor?}
        event: done    — stream complete
        event: timeout — no activity for 30s
    """
    return StreamingResponse(
        _stream_stages(correlation_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
