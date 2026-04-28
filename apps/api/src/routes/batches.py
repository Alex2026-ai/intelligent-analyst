"""Batch read endpoints — shared-read over monolith-written Firestore data.

GET /v1/batches           — list batches for the authenticated tenant (paginated)
GET /v1/batches/{trace_id} — single batch by trace_id

Both read from the `batches/` collection written by the monolith
(server_enterprise_golden.py). Read-only. No mutations. Tenant-isolated (INV-005).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from apps.api.src.dependencies import AuthContext, Role, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["batches"])

# Fields safe to return to authenticated operators.
# Excludes internal Firestore metadata and cost fields for non-admin.
_SAFE_FIELDS = frozenset({
    "trace_id", "status", "filename", "total", "total_records",
    "timestamp", "finished_at", "duration_seconds", "duration_ms",
    "dataset_type", "config_version", "protocol_version",
    "auto_resolved_pct", "sharded", "shard_count",
    "counts", "stats",
    "classification_meta", "column_selection",
    "tenant_id",
})

_ADMIN_EXTRA_FIELDS = frozenset({
    "llm_budget_summary", "credits_reserved_usd", "credits_spent_usd",
    "cost_usd",
})


def _strip_batch(batch: dict[str, Any], is_admin: bool) -> dict[str, Any]:
    """Return only safe fields from a batch document."""
    allowed = _SAFE_FIELDS | _ADMIN_EXTRA_FIELDS if is_admin else _SAFE_FIELDS
    return {k: v for k, v in batch.items() if k in allowed}


async def _collect_stream(results: Any) -> list[dict[str, Any]]:
    """Collect items from sync list or async stream into a plain list of dicts."""
    items: list[dict[str, Any]] = []
    if hasattr(results, "__aiter__"):
        async for item in results:
            doc = item.to_dict() if hasattr(item, "to_dict") else item
            if doc:
                items.append(doc)
    else:
        for item in results:
            doc = item[1] if isinstance(item, tuple) else (item.to_dict() if hasattr(item, "to_dict") else item)
            if doc:
                items.append(doc)
    return items


@router.get("/batches/")
async def list_batches(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    """List recent batches for the authenticated tenant.

    Reads from the monolith's `batches/` Firestore collection.
    Fetches recent docs and filters by tenant in memory (matches monolith
    strategy to avoid composite index requirements).
    """
    db = getattr(request.app.state, "firestore_client", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        results = db.collection("batches").stream()
    except Exception as e:
        logger.error("Firestore batch list query failed: %s", e)
        raise HTTPException(status_code=503, detail="Database query failed")

    all_docs = await _collect_stream(results)

    # Tenant isolation (INV-005): non-admin sees only own tenant
    is_admin = auth.role in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN)
    if is_admin:
        filtered = all_docs
    else:
        filtered = [d for d in all_docs if d.get("tenant_id") == auth.tenant_id]

    # Sort by timestamp descending (newest first), handling missing timestamps
    filtered.sort(key=lambda d: d.get("timestamp", ""), reverse=True)

    # Apply limit
    page = filtered[:limit]

    # Map PRE roles to monolith role names for dashboard compatibility
    _ROLE_MAP = {"analyst": "user", "tenant_admin": "admin", "reviewer": "auditor"}
    dashboard_role = _ROLE_MAP.get(auth.role.value, auth.role.value)

    return {
        "batches": [_strip_batch(b, is_admin) for b in page],
        "count": len(page),
        "total": len(filtered),
        "limit": limit,
        "role": dashboard_role,
        "demo_mode": False,
        "firestore_available": True,
    }


@router.get("/batches/{trace_id}")
async def get_batch(
    trace_id: str,
    request: Request,
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    """Retrieve a single batch by trace_id.

    Reads from the monolith's `batches/` Firestore collection.
    Tenant-isolated: non-admin users can only read their own tenant's batches.
    """
    if not trace_id or len(trace_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid trace_id")

    db = getattr(request.app.state, "firestore_client", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Query the monolith's batches collection by trace_id
    try:
        results = db.collection("batches").where("trace_id", "==", trace_id).stream()
    except Exception as e:
        logger.error("Firestore query failed for trace_id=%s: %s", trace_id, e)
        raise HTTPException(status_code=503, detail="Database query failed")

    docs = await _collect_stream(results)
    batch_doc = docs[0] if docs else None

    if batch_doc is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Tenant isolation (INV-005): non-admin can only read own tenant
    batch_tenant = batch_doc.get("tenant_id", "")
    is_admin = auth.role in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN)
    if not is_admin and batch_tenant != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: tenant mismatch")

    return _strip_batch(batch_doc, is_admin)


# Forensic metadata fields — stored on the batch document by the monolith.
# These are read-only attestation/chain/anchor metadata, NOT re-verification.
_FORENSIC_FIELDS = frozenset({
    "trace_id", "status",
    "signature", "hash_chain", "anchor", "attestation",
    "legal_hold", "iavp_manifest", "receipt",
})


def _strip_forensic(batch: dict[str, Any]) -> dict[str, Any]:
    """Return only forensic metadata fields from a batch document."""
    result: dict[str, Any] = {}
    for k in _FORENSIC_FIELDS:
        if k in batch:
            result[k] = batch[k]
    # Derive summary booleans from raw fields
    sig = batch.get("signature", {}) or {}
    chain = batch.get("hash_chain", {}) or {}
    anchor_data = batch.get("anchor", {}) or {}
    att = batch.get("attestation", {}) or {}
    result["summary"] = {
        "signature_present": bool(sig.get("signature") or att.get("signature_b64")),
        "hash_chain_present": bool(chain.get("batch_root_hash")),
        "anchor_present": bool(anchor_data.get("anchored")),
        "legal_hold_active": batch.get("legal_hold", {}).get("status") == "ACTIVE",
    }
    return result


@router.get("/batches/{trace_id}/forensic")
async def get_batch_forensic(
    trace_id: str,
    request: Request,
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    """Read-only forensic metadata for a batch.

    Returns stored signature, hash_chain, anchor, attestation, and legal_hold
    fields from the batch document. Does NOT re-verify — just returns what the
    monolith wrote. For verification, use the monolith /batches/{id}/verify.
    """
    if not trace_id or len(trace_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid trace_id")

    db = getattr(request.app.state, "firestore_client", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    docs = await _collect_stream(
        db.collection("batches").where("trace_id", "==", trace_id).stream()
    )
    batch_doc = docs[0] if docs else None
    if batch_doc is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    is_admin = auth.role in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN)
    if not is_admin and batch_doc.get("tenant_id", "") != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: tenant mismatch")

    return _strip_forensic(batch_doc)


# Fields safe to expose per result row (no internal processing metadata)
_SAFE_RESULT_FIELDS = frozenset({
    "original", "resolved", "canonical_name", "sanitized_name",
    "layer", "confidence", "sanitization_confidence",
    "reason", "match_reason", "garbage_reason",
    "row_index", "match_type", "match_id", "decision",
})


def _strip_result(row: dict[str, Any]) -> dict[str, Any]:
    """Return only safe fields from a result row."""
    return {k: v for k, v in row.items() if k in _SAFE_RESULT_FIELDS}


@router.get("/batches/{trace_id}/results")
async def get_batch_results(
    trace_id: str,
    request: Request,
    limit: int = Query(default=250, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    """Paginated batch results — reads from monolith's results_chunks subcollection.

    Each chunk document has {start_index, rows: [...]}. Chunks are ordered by
    start_index and concatenated into a flat list, then paginated.
    """
    if not trace_id or len(trace_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid trace_id")

    db = getattr(request.app.state, "firestore_client", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # First verify batch exists and tenant has access
    batch_docs = await _collect_stream(
        db.collection("batches").where("trace_id", "==", trace_id).stream()
    )
    batch_doc = batch_docs[0] if batch_docs else None
    if batch_doc is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    is_admin = auth.role in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN)
    if not is_admin and batch_doc.get("tenant_id", "") != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: tenant mismatch")

    # Read results_chunks subcollection
    try:
        chunks_stream = db.collection("batches").document(trace_id).collection("results_chunks").stream()
    except Exception as e:
        logger.error("Firestore results query failed for %s: %s", trace_id, e)
        raise HTTPException(status_code=503, detail="Results query failed")

    chunk_docs = await _collect_stream(chunks_stream)

    # Sort chunks by start_index and flatten rows
    chunk_docs.sort(key=lambda c: c.get("start_index", 0))
    all_rows: list[dict[str, Any]] = []
    for chunk in chunk_docs:
        all_rows.extend(chunk.get("rows", []))

    # Paginate
    total = len(all_rows)
    page = all_rows[offset:offset + limit]

    return {
        "trace_id": trace_id,
        "total": total,
        "offset": offset,
        "limit": limit,
        "count": len(page),
        "results": [_strip_result(r) for r in page],
    }


# Safe fields for audit event rows
_SAFE_AUDIT_FIELDS = frozenset({
    "row_index", "original", "resolved", "canonical_name",
    "layer", "confidence", "reason", "match_reason", "garbage_reason",
    "decision", "decision_path", "match_type",
    "event_type", "timestamp",
})


def _strip_audit(event: dict[str, Any]) -> dict[str, Any]:
    """Return only safe fields from an audit event."""
    return {k: v for k, v in event.items() if k in _SAFE_AUDIT_FIELDS}


@router.get("/batches/{trace_id}/audit")
async def get_batch_audit(
    trace_id: str,
    request: Request,
    limit: int = Query(default=1000, ge=1, le=10000),
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    """Audit events for a batch — reads from monolith's audit_events subcollection.

    Returns per-row audit events ordered by row_index. Read-only.
    """
    if not trace_id or len(trace_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid trace_id")

    db = getattr(request.app.state, "firestore_client", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Verify batch exists and tenant access
    batch_docs = await _collect_stream(
        db.collection("batches").where("trace_id", "==", trace_id).stream()
    )
    batch_doc = batch_docs[0] if batch_docs else None
    if batch_doc is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    is_admin = auth.role in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN)
    if not is_admin and batch_doc.get("tenant_id", "") != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: tenant mismatch")

    # Read audit_events subcollection
    try:
        audit_stream = db.collection("batches").document(trace_id).collection("audit_events").stream()
    except Exception as e:
        logger.error("Firestore audit query failed for %s: %s", trace_id, e)
        raise HTTPException(status_code=503, detail="Audit query failed")

    events = await _collect_stream(audit_stream)

    # Sort by row_index (matches monolith order_by behavior)
    events.sort(key=lambda e: e.get("row_index", 0))

    # Apply limit
    events = events[:limit]

    return {
        "trace_id": trace_id,
        "total": len(events),
        "events": [_strip_audit(e) for e in events],
    }
