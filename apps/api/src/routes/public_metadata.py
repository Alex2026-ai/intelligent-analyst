"""Public Metadata Controller API endpoints.

Admin (tenant_admin+):
  POST /v1/public-metadata/evaluate, /emit, /approve/{id}, /publish/{id}, /revoke/{id}
  GET  /v1/public-metadata/admin/samples?status=draft&limit=20&offset=0
Public (no auth):
  GET /v1/public-metadata/sample/{id}
  GET /v1/public-metadata/feed?limit=20&offset=0
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from apps.api.src.dependencies import AuthContext, Role, require_role
from apps.api.src.public_metadata.emitter import emit_sample
from apps.api.src.public_metadata.events import emit_publication_event
from apps.api.src.public_metadata.models import SampleStatus
from apps.api.src.public_metadata.config import load_policy
from apps.api.src.public_metadata.policy_evaluator import evaluate
from apps.api.src.public_metadata.store import PublicMetadataStore

router = APIRouter(prefix="/v1/public-metadata", tags=["public-metadata"])

# Pagination constants
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

_PUBLIC_SAFE_FIELDS = frozenset({
    "public_sample_id", "sample_type", "status", "headline", "summary",
    "outcome_class", "workflow_stages", "public_spec_anchors",
    "proof_summary", "redaction_profile_version", "source_kind",
    "integrity_hash", "emitted_at",
})


def _get_store(request: Request) -> PublicMetadataStore:
    return PublicMetadataStore(request.app.state.firestore_client)


def _strip(sample: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in sample.items() if k in _PUBLIC_SAFE_FIELDS}


def _validate_pagination(limit: int, offset: int) -> tuple[int, int]:
    """Validate and clamp pagination params. Fail-closed on invalid values."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    return min(limit, MAX_LIMIT), offset


# --- Admin endpoints ---

@router.post("/evaluate")
async def evaluate_eligibility(
    request: Request, body: dict[str, Any],
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict[str, Any]:
    decision = evaluate(body.get("source", {}), auth.tenant_id, await load_policy(request.app.state.firestore_client), body.get("source_anchors", []))
    await _get_store(request).save_decision(decision)
    return decision.model_dump()


@router.post("/emit")
async def emit_public_sample(
    request: Request, body: dict[str, Any],
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict[str, Any]:
    source, anchors = body.get("source", {}), body.get("source_anchors", [])
    policy = await load_policy(request.app.state.firestore_client)
    decision = evaluate(source, auth.tenant_id, policy, anchors)
    store = _get_store(request)
    await store.save_decision(decision)
    sample = emit_sample(source, auth.tenant_id, policy, decision, anchors)
    if sample is None:
        return {"emitted": False, "decision": decision.model_dump(), "reason": "; ".join(decision.reasons)}
    await store.save_sample(sample)
    return {"emitted": True, "decision": decision.model_dump(), "sample": sample.model_dump()}


@router.post("/approve/{sample_id}")
async def approve_sample(
    sample_id: str, request: Request,
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict[str, Any]:
    emit_publication_event("approve", "attempted", sample_id)
    store = _get_store(request)
    sample = await store.get_sample(sample_id)
    if sample is None:
        emit_publication_event("approve", "failed", sample_id, "not found")
        raise HTTPException(status_code=404, detail="Sample not found")
    if not await store.approve_sample(sample_id):
        emit_publication_event("approve", "failed", sample_id, f"invalid from {sample.get('status')}")
        raise HTTPException(status_code=409, detail=f"Cannot approve sample in state '{sample.get('status')}'")
    emit_publication_event("approve", "succeeded", sample_id)
    return {"approved": True, "sample_id": sample_id}


@router.post("/publish/{sample_id}")
async def publish_sample(
    sample_id: str, request: Request,
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict[str, Any]:
    emit_publication_event("publish", "attempted", sample_id)
    store = _get_store(request)
    sample = await store.get_sample(sample_id)
    if sample is None:
        emit_publication_event("publish", "failed", sample_id, "not found")
        raise HTTPException(status_code=404, detail="Sample not found")
    if not await store.publish_sample(sample_id):
        emit_publication_event("publish", "failed", sample_id, f"invalid from {sample.get('status')}")
        raise HTTPException(status_code=409, detail=f"Cannot publish sample in state '{sample.get('status')}'")
    emit_publication_event("publish", "succeeded", sample_id)
    return {"published": True, "sample_id": sample_id}


@router.post("/revoke/{sample_id}")
async def revoke_sample(
    sample_id: str, request: Request,
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict[str, Any]:
    emit_publication_event("revoke", "attempted", sample_id)
    store = _get_store(request)
    sample = await store.get_sample(sample_id)
    if sample is None:
        emit_publication_event("revoke", "failed", sample_id, "not found")
        raise HTTPException(status_code=404, detail="Sample not found")
    if not await store.revoke_sample(sample_id):
        emit_publication_event("revoke", "failed", sample_id, f"invalid from {sample.get('status')}")
        raise HTTPException(status_code=409, detail=f"Cannot revoke sample in state '{sample.get('status')}'")
    emit_publication_event("revoke", "succeeded", sample_id)
    return {"revoked": True, "sample_id": sample_id}


# --- Admin listing ---

@router.get("/admin/samples")
async def admin_list_samples(
    request: Request,
    status: str | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict[str, Any]:
    limit, offset = _validate_pagination(limit, offset)
    store = _get_store(request)
    filter_status = None
    if status:
        try:
            filter_status = SampleStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    all_items = await store.list_by_status(filter_status)
    page = [_strip(s) for s in all_items[offset:offset + limit]]
    return {"samples": page, "count": len(page), "total": len(all_items), "limit": limit, "offset": offset}


# --- Public read (no auth) ---

@router.get("/sample/{public_sample_id}")
async def get_public_sample(public_sample_id: str, request: Request) -> dict[str, Any]:
    store = _get_store(request)
    sample = await store.get_sample(public_sample_id)
    if sample is None or sample.get("status") != SampleStatus.PUBLISHED.value:
        raise HTTPException(status_code=404, detail="Public sample not found")
    return _strip(sample)


@router.get("/feed")
async def public_trust_feed(
    request: Request,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """Public Trust Feed — paginated, published-only, newest first. Cacheable."""
    limit, offset = _validate_pagination(limit, offset)
    store = _get_store(request)
    all_published = await store.list_published()
    page = [_strip(s) for s in all_published[offset:offset + limit]]
    body = {"samples": page, "count": len(page), "total": len(all_published), "limit": limit, "offset": offset}
    return JSONResponse(content=body, headers={"Cache-Control": "public, max-age=60"})
