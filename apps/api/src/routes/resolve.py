"""Resolution endpoints — POST /v1/resolve, POST /v1/resolve/batch.

Requires analyst+ role. Idempotency-Key header required (INV-001).
PII masking before LLM calls (INV-006). OTel child span for LLM latency.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.src.dependencies import (
    AuthContext,
    Role,
    get_idempotency_key,
    get_idempotency_repo,
    require_role,
)
from apps.api.src.pii.masker import PIIMasker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["resolution"])

_masker = PIIMasker()


def _get_tracer():
    """Lazy OTel tracer — returns None if SDK not available."""
    try:
        from opentelemetry import trace
        return trace.get_tracer("ia.routes.resolve")
    except ImportError:
        return None


async def _call_llm(request: Request, masked_content: str, document_type: str) -> dict[str, Any]:
    """Call the LLM provider with PII-masked content inside an OTel span.

    Returns dict with resolution, confidence, layer_used, provider, model, prompt_version.
    Falls back to stub values if no LLM provider is configured.
    """
    llm = getattr(request.app.state, "llm_primary", None)
    if llm is None:
        return {
            "resolution": "No LLM provider configured",
            "confidence": 0.0,
            "layer_used": None,
            "provider": "none",
            "model": "none",
            "prompt_version": "1.0",
            "latency_ms": 0,
        }

    tracer = _get_tracer()
    context = {"document_type": document_type}

    if tracer is not None:
        with tracer.start_as_current_span(
            "llm.anthropic.resolve",
            attributes={
                "llm.provider": getattr(llm, "name", "unknown"),
                "llm.document_type": document_type,
                "llm.content_length": len(masked_content),
            },
        ) as span:
            try:
                response = await llm.resolve(masked_content, context, "1.0")
                span.set_attribute("llm.confidence", response.confidence)
                span.set_attribute("llm.latency_ms", response.latency_ms)
                span.set_attribute("llm.model", response.model)
            except Exception as e:
                span.set_attribute("llm.error", str(e))
                logger.warning("LLM call failed: %s", e)
                return {
                    "resolution": None,
                    "confidence": 0.0,
                    "layer_used": None,
                    "provider": getattr(llm, "name", "unknown"),
                    "model": "error",
                    "prompt_version": "1.0",
                    "latency_ms": 0,
                }
    else:
        try:
            response = await llm.resolve(masked_content, context, "1.0")
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
            return {
                "resolution": None,
                "confidence": 0.0,
                "layer_used": None,
                "provider": getattr(llm, "name", "unknown"),
                "model": "error",
                "prompt_version": "1.0",
                "latency_ms": 0,
            }

    return {
        "resolution": response.resolution,
        "confidence": response.confidence,
        "layer_used": 3,
        "provider": response.provider,
        "model": response.model,
        "prompt_version": response.prompt_version,
        "latency_ms": response.latency_ms,
    }


@router.post("/resolve")
async def resolve_single(
    request: Request,
    body: dict[str, Any],
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
    idempotency_key: str | None = Depends(get_idempotency_key),
) -> dict:
    """Submit a single document for resolution."""
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    # Check idempotency via persistent store (INV-001)
    idem_repo = get_idempotency_repo(request)
    cached = await idem_repo.get(idempotency_key)
    if cached is not None:
        return cached

    # Validate required fields
    for field in ("document_id", "document_type", "content"):
        if field not in body:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    valid_types = {"regulatory", "compliance", "financial", "medical"}
    if body["document_type"] not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid document_type: {body['document_type']}")

    content = body["content"]
    if len(content.encode("utf-8")) > 50 * 1024:
        raise HTTPException(status_code=400, detail="Document content exceeds 50KB limit")

    # PII masking before any external call (INV-006)
    masked_content, vault, pii_categories = _masker.mask(content)

    # Call LLM with masked content (wrapped in OTel span)
    llm_result = await _call_llm(request, masked_content, body["document_type"])

    # Unmask PII in LLM response
    resolution_text = llm_result["resolution"]
    if resolution_text and vault.token_count > 0:
        resolution_text = _masker.unmask(resolution_text, vault)

    # Destroy vault — PII mappings must not persist (INV-006)
    vault.clear()

    resolution_id = str(uuid.uuid4())
    evidence_chain_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Determine status based on confidence
    confidence = llm_result["confidence"]
    status = "resolved" if confidence >= 0.7 else "routed_to_review"
    review_reason = "low_confidence" if status == "routed_to_review" else None

    response = {
        "resolution_id": resolution_id,
        "status": status,
        "layer_used": llm_result["layer_used"],
        "confidence": confidence,
        "resolution": resolution_text,
        "review_reason": review_reason,
        "evidence_chain_id": evidence_chain_id,
        "created_at": now,
    }

    await idem_repo.put(idempotency_key, response)

    # --- PMC lifecycle hook: create pending public sample candidate ---
    # Runs only for finalized single resolutions (status != failed).
    # Fail-safe: PMC errors are captured internally, never block resolution flow.
    if status in ("resolved", "routed_to_review"):
        await _try_pmc_candidate(
            request, response, auth.tenant_id,
            pii_categories=pii_categories, document_type=body["document_type"],
        )

    return response


async def _try_pmc_candidate(
    request: Request,
    response: dict[str, Any],
    tenant_id: str,
    pii_categories: set[str] | None = None,
    document_type: str = "",
) -> None:
    """Guarded PMC candidate creation with config loading, structured events,
    and evidence enrichment. Errors are logged via structured events, never propagated."""
    from apps.api.src.public_metadata import events

    resolution_id = response.get("resolution_id", "")

    try:
        from apps.api.src.public_metadata.config import load_policy
        from apps.api.src.public_metadata.orchestrator import (
            create_public_sample_candidate_from_resolution,
        )
        from apps.api.src.public_metadata.store import PublicMetadataStore

        db = getattr(request.app.state, "firestore_client", None)
        if db is None:
            return

        events.emit_attempted(tenant_id, resolution_id)

        policy = await load_policy(db)
        store = PublicMetadataStore(db)
        evidence_records = _build_evidence_hints(response, pii_categories, document_type)

        result = await create_public_sample_candidate_from_resolution(
            resolution=response,
            tenant_id=tenant_id,
            policy=policy,
            store=store,
            evidence_records=evidence_records,
        )

        if not result.success:
            events.emit_failed(tenant_id, resolution_id, result.error)
        elif result.decision and result.decision.decision.value == "deny":
            events.emit_denied(
                tenant_id, resolution_id,
                result.decision.decision_id, result.decision.reasons,
            )
        elif result.decision:
            events.emit_created(
                tenant_id, resolution_id,
                result.decision.decision_id, result.decision.decision.value,
                sample_id=result.sample.public_sample_id if result.sample else "",
            )
    except Exception as e:
        events.emit_failed(tenant_id, resolution_id, str(e))


def _build_evidence_hints(
    response: dict[str, Any],
    pii_categories: set[str] | None,
    document_type: str,
) -> list[dict[str, Any]]:
    """Synthesize evidence-like records from data available at the hook point.

    No upstream re-architecture. Each hint maps to a spec invariant:
    - pii_categories → INV-006 (PII masking)
    - layer_used → INV-002 (evidence lineage)
    - routing status → INV-005 (tenant isolation / routing decision)
    """
    hints: list[dict[str, Any]] = []

    if pii_categories:
        hints.append({"data": {
            "step": "pii_mask",
            "categories": sorted(pii_categories),
            "token_count": len(pii_categories),
        }})

    layer = response.get("layer_used")
    if layer is not None:
        hints.append({"data": {
            "step": "l1_rule_match" if layer == 1 else "llm_resolve",
            "layer_used": layer,
        }})

    hints.append({"data": {
        "step": "routing_decision",
        "route_to_review": response.get("status") == "routed_to_review",
    }})

    return hints


@router.post("/resolve/batch")
async def resolve_batch(
    request: Request,
    body: dict[str, Any],
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
    idempotency_key: str | None = Depends(get_idempotency_key),
) -> dict:
    """Submit multiple documents for resolution."""
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    idem_repo = get_idempotency_repo(request)
    cached = await idem_repo.get(idempotency_key)
    if cached is not None:
        return cached

    documents = body.get("documents", [])
    if not documents:
        raise HTTPException(status_code=400, detail="documents array is required and cannot be empty")
    if len(documents) > 100:
        raise HTTPException(status_code=400, detail="Batch exceeds 100 document maximum")

    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    resolved_count = 0
    review_count = 0
    failed_count = 0
    results = []

    for doc in documents:
        doc_content = doc.get("content", "")
        doc_type = doc.get("document_type", "regulatory")

        # PII masking per document (INV-006)
        masked, vault, _ = _masker.mask(doc_content)

        try:
            llm_result = await _call_llm(request, masked, doc_type)
            confidence = llm_result["confidence"]
            doc_status = "resolved" if confidence >= 0.7 else "routed_to_review"
            if doc_status == "resolved":
                resolved_count += 1
            else:
                review_count += 1

            results.append({
                "document_id": doc.get("document_id", ""),
                "resolution_id": str(uuid.uuid4()),
                "status": doc_status,
                "layer_used": llm_result["layer_used"],
                "confidence": confidence,
                "error": None,
            })
        except Exception as e:
            failed_count += 1
            results.append({
                "document_id": doc.get("document_id", ""),
                "resolution_id": str(uuid.uuid4()),
                "status": "failed",
                "layer_used": None,
                "confidence": None,
                "error": str(e),
            })
        finally:
            vault.clear()

    response = {
        "batch_id": batch_id,
        "total": len(documents),
        "resolved": resolved_count,
        "routed_to_review": review_count,
        "failed": failed_count,
        "results": results,
        "created_at": now,
    }

    await idem_repo.put(idempotency_key, response)
    return response
