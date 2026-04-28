"""Domain adapter — maps resolution/story outputs into PMC source format.

Accepts both typed EngineResult/EvidenceRecord objects and plain dicts.
Deterministic. Unknown fields dropped. Fail-closed on missing required fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.api.src.resolver.base import EvidenceRecord
    from apps.api.src.resolver.engine import EngineResult

# Fields we explicitly extract from resolution domain objects.
# Everything else is dropped (PMC-INV-003: fail-closed on unknown).
_KNOWN_SOURCE_FIELDS: frozenset[str] = frozenset({
    "resolution_id", "status", "confidence", "layer_used",
    "review_reason", "document_type", "evidence_chain_id",
})

_LAYER_LABELS: dict[int, str] = {
    1: "Deterministic rule match",
    2: "Precedent-based matching",
    3: "LLM-assisted analysis",
    4: "LLM with extended context",
}

_REASON_FRAGMENTS: dict[str, str] = {
    "low_confidence": "Confidence below threshold — preserved escalation",
    "high_impact": "High-impact classification — human review required",
    "force_review": "Manual review requested by submitter",
    "llm_unavailable": "LLM provider unavailable — fail-safe escalation",
}


@dataclass(frozen=True)
class AdapterResult:
    """Output of the domain adapter.

    source: PMC-compatible dict with only known safe fields.
    anchors: Spec anchor IDs extracted from evidence records.
    valid: False if required fields are missing.
    error: Reason string if invalid.
    """

    source: dict[str, Any]
    anchors: list[str]
    valid: bool
    error: str = ""


def _extract_anchors_from_typed(records: list[Any]) -> list[str]:
    """Extract spec anchors from typed EvidenceRecord objects or dicts."""
    anchors: list[str] = []
    for record in records:
        # Support both typed EvidenceRecord (dataclass) and plain dict
        if hasattr(record, "node_type") and hasattr(record, "data"):
            data = record.data
        elif isinstance(record, dict):
            data = record.get("data", {})
        else:
            continue

        if not isinstance(data, dict):
            continue

        anchor = data.get("spec_anchor", {})
        if isinstance(anchor, dict) and "spec_id" in anchor:
            anchors.append(anchor["spec_id"])

        step = data.get("step", "")
        if step == "l1_rule_match":
            anchors.append("INV-002")
        if step == "routing_decision" and data.get("route_to_review"):
            anchors.append("INV-005")
        if "pii" in step.lower() or "mask" in step.lower():
            anchors.append("INV-006")

    return sorted(set(anchors))


def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert a typed domain object or dict to a plain dict for field extraction."""
    if isinstance(obj, dict):
        return obj
    # dataclass (EngineResult, etc.)
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    # Pydantic model
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return {}


def adapt_engine_result(
    engine_result: Any,
    tenant_id: str,
    correlation_id: str | None = None,
    evidence_records: list[Any] | None = None,
) -> AdapterResult:
    """Map a resolution artifact into PMC source format.

    Accepts:
    - EngineResult dataclass (from resolver engine)
    - dict (from API response or test fixture)

    Unknown fields are dropped. Required: resolution_id, status.
    """
    raw = _to_dict(engine_result)

    resolution_id = raw.get("resolution_id")
    status = raw.get("status")

    if not resolution_id or not status:
        return AdapterResult(
            source={}, anchors=[], valid=False,
            error="Missing required fields: resolution_id and status",
        )

    source: dict[str, Any] = {}
    for field in _KNOWN_SOURCE_FIELDS:
        if field in raw:
            source[field] = raw[field]

    layer = raw.get("layer_used")
    if isinstance(layer, int) and layer in _LAYER_LABELS:
        source["stage_summary"] = _LAYER_LABELS[layer]

    reason = raw.get("review_reason")
    if reason and reason in _REASON_FRAGMENTS:
        source["justification_fragment"] = _REASON_FRAGMENTS[reason]

    if correlation_id:
        source["correlation_id"] = correlation_id

    # Extract anchors — also pull from evidence_chain if present on typed object
    all_records: list[Any] = list(evidence_records or [])
    if hasattr(engine_result, "evidence") and engine_result.evidence:
        all_records.extend(engine_result.evidence)

    anchors = _extract_anchors_from_typed(all_records)

    return AdapterResult(source=source, anchors=anchors, valid=True)
