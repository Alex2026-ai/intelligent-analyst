"""PMC orchestrator — end-to-end candidate creation from resolution artifacts.

Accepts both typed EngineResult objects and plain dicts.
Single entrypoint: create_public_sample_candidate_from_resolution().
Fail-closed. Manual approval required by default.
Async-safe for production Firestore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from apps.api.src.public_metadata.adapter import AdapterResult, adapt_engine_result
from apps.api.src.public_metadata.emitter import emit_sample
from apps.api.src.public_metadata.models import (
    PublicAuthoritySample,
    PublicMetadataDecision,
    PublicMetadataPolicy,
)
from apps.api.src.public_metadata.policy_evaluator import evaluate
from apps.api.src.public_metadata.store import PublicMetadataStore


@dataclass(frozen=True)
class CandidateResult:
    success: bool
    decision: PublicMetadataDecision | None = None
    sample: PublicAuthoritySample | None = None
    error: str = ""


async def create_public_sample_candidate_from_resolution(
    resolution: Any,
    tenant_id: str,
    policy: PublicMetadataPolicy,
    store: PublicMetadataStore,
    correlation_id: str | None = None,
    evidence_records: list[Any] | None = None,
) -> CandidateResult:
    """End-to-end: resolution → adapter → evaluate → redact → emit → store."""
    adapted: AdapterResult = adapt_engine_result(
        engine_result=resolution,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        evidence_records=evidence_records,
    )

    if not adapted.valid:
        return CandidateResult(success=False, error=f"Adapter failed: {adapted.error}")

    decision: PublicMetadataDecision = evaluate(
        source=adapted.source,
        tenant_id=tenant_id,
        policy=policy,
        source_anchors=adapted.anchors,
    )

    await store.save_decision(decision)

    sample: PublicAuthoritySample | None = emit_sample(
        source=adapted.source,
        tenant_id=tenant_id,
        policy=policy,
        decision=decision,
        source_anchors=adapted.anchors,
    )

    if sample is not None:
        await store.save_sample(sample)

    return CandidateResult(
        success=True,
        decision=decision,
        sample=sample,
    )
