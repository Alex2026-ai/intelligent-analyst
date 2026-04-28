"""
================================================================================
INTELLIGENT ANALYST - EVIDENCE BLOB MODULE (Phase 1)
================================================================================

Builds cryptographically signed evidence blobs for each resolution decision.
Evidence blobs provide deterministic replay capability and tamper detection.

Each evidence blob includes:
- Input: original + sanitized
- Routing: decision + signals
- Output: structured fields
- Config: snapshot at decision time
- Runtime: latency, cost, timestamp
- LLM: prompt/response hashes (or full text if enabled)
- Signature: KMS-signed hash

================================================================================
"""

import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from .signing import (
    canonicalize_json, sha256_bytes, sha256_str,
    sign_bytes_kms, build_signature_metadata,
    build_llm_replay_metadata
)
from .sbom import get_sbom_for_evidence

# Config
EVIDENCE_STORE_FULL_LLM_TEXT = os.getenv("EVIDENCE_STORE_FULL_LLM_TEXT", "false").lower() == "true"


def build_evidence_blob(
    trace_id: str,
    row_index: int,
    tenant_id: str,
    # Input
    original_input: str,
    sanitized_input: str,
    pii_detected: List[str],
    # Routing
    entity_type: str,
    classification_confidence: float,
    classification_flags: List[str],
    decision_path: str,
    layer: str,
    # Output
    resolved_output: Optional[str],
    output_confidence: float,
    output_fields: Dict[str, Any],
    # Config snapshot
    config_version: str,
    sanitization_version: str,
    watchlist_version_hash: str,
    # Runtime
    latency_ms: float,
    # LLM metadata (optional)
    llm_used: bool = False,
    llm_prompt: Optional[str] = None,
    llm_response: Optional[str] = None,
    llm_cost_usd: float = 0.0,
    llm_output_tokens: Optional[int] = None,
    llm_provider: str = "anthropic",
    llm_model: str = "claude-3-haiku-20240307",
    llm_temperature: float = 0.0,
    llm_top_p: float = 1.0,
    llm_seed: Optional[int] = None,
    llm_seed_supported: bool = False,
    # Sustainability metadata (optional - must be computed before calling)
    sustainability: Optional[Dict[str, Any]] = None,
    # Additional metadata
    additional_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a complete evidence blob for a single resolution decision.

    This function is called exactly ONCE per resolved record.
    The blob is immediately hashed and signed.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build core evidence (excluding signature fields)
    evidence_core = {
        # Identity
        "trace_id": trace_id,
        "row_index": row_index,
        "tenant_id": tenant_id,
        "timestamp": timestamp,

        # Input
        "input": {
            "original": original_input,
            "sanitized": sanitized_input,
            "pii_detected": pii_detected,
        },

        # Routing Decision
        "routing": {
            "entity_type": entity_type,
            "classification_confidence": classification_confidence,
            "classification_flags": classification_flags,
            "decision_path": decision_path,
            "layer": layer,
        },

        # Output
        "output": {
            "resolved": resolved_output,
            "confidence": output_confidence,
            "fields": output_fields,
        },

        # Config Snapshot
        "config_snapshot": {
            "config_version": config_version,
            "sanitization_version": sanitization_version,
            "watchlist_version_hash": watchlist_version_hash,
        },

        # Runtime Metrics
        "runtime": {
            "latency_ms": latency_ms,
            "processed_at": timestamp,
        },

        # SBOM
        "sbom": get_sbom_for_evidence(),
    }

    # LLM Metadata (if used)
    if llm_used:
        llm_meta = build_llm_replay_metadata(
            provider=llm_provider,
            model=llm_model,
            temperature=llm_temperature,
            top_p=llm_top_p,
            seed=llm_seed,
            seed_supported=llm_seed_supported
        )

        # Hash prompt/response
        llm_meta["prompt_hash"] = sha256_str(llm_prompt) if llm_prompt else None
        llm_meta["response_hash"] = sha256_str(llm_response) if llm_response else None
        llm_meta["cost_usd"] = llm_cost_usd

        # Store full text only if enabled by policy
        if EVIDENCE_STORE_FULL_LLM_TEXT:
            llm_meta["prompt_text"] = llm_prompt
            llm_meta["response_text"] = llm_response

        evidence_core["llm"] = llm_meta
    else:
        evidence_core["llm"] = None

    # Sustainability metadata (MUST be added BEFORE hash computation)
    # This binds energy/carbon estimates to the forensic evidence chain
    if sustainability:
        evidence_core["sustainability"] = sustainability

    # Additional metadata
    if additional_metadata:
        evidence_core["metadata"] = additional_metadata

    # Compute hash of evidence core (before signature)
    canonical_bytes = canonicalize_json(evidence_core)
    evidence_hash = sha256_bytes(canonical_bytes)

    # Sign the evidence hash
    signature_b64, sign_error = sign_bytes_kms(canonical_bytes)

    # Build signature metadata
    signature_meta = build_signature_metadata(
        evidence_hash=evidence_hash,
        signature_b64=signature_b64,
        sign_error=sign_error
    )

    # Combine evidence with signature
    evidence_blob = {
        "evidence": evidence_core,
        "signature": signature_meta,
        "version": "1.0.0",
    }

    return evidence_blob


def extract_evidence_summary(evidence_blob: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a summary of an evidence blob for API responses.
    Excludes sensitive fields like full LLM text.
    """
    evidence = evidence_blob.get("evidence", {})
    signature = evidence_blob.get("signature", {})

    return {
        "trace_id": evidence.get("trace_id"),
        "row_index": evidence.get("row_index"),
        "timestamp": evidence.get("timestamp"),
        "layer": evidence.get("routing", {}).get("layer"),
        "decision_path": evidence.get("routing", {}).get("decision_path"),
        "resolved": evidence.get("output", {}).get("resolved"),
        "confidence": evidence.get("output", {}).get("confidence"),
        "evidence_hash": signature.get("evidence_hash_sha256"),
        "signed": signature.get("signature") is not None,
        "signed_at": signature.get("signed_at_utc"),
    }


def verify_evidence_signature_format(evidence_blob: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that an evidence blob has valid signature format.
    Does NOT verify cryptographic signature (that requires public key).

    Returns verification result with fields present check.
    Only applicable to row_sig_v1 evidence blobs (legacy per-row signed).
    """
    signature = evidence_blob.get("signature", {})

    required_fields = [
        "evidence_hash_sha256",
        "signed_at_utc",
        "service_identity",
    ]

    missing_fields = [f for f in required_fields if not signature.get(f)]

    has_signature = signature.get("signature") is not None

    return {
        "valid_format": len(missing_fields) == 0,
        "has_signature": has_signature,
        "missing_fields": missing_fields,
        "signature_error": signature.get("signature_error"),
    }


# =============================================================================
# IAVP Evidence Schema Detection + Chunk-Based Verification
# =============================================================================

EVIDENCE_SCHEMA_CHUNK_V1 = "chunk_v1"
EVIDENCE_SCHEMA_ROW_SIG_V1 = "row_sig_v1"
EVIDENCE_SCHEMA_UNKNOWN = "unknown"


def detect_evidence_schema(evidence_blobs: List[Dict[str, Any]]) -> str:
    """
    Detect which evidence schema a batch uses by inspecting stored artifacts.

    Returns one of:
      - "chunk_v1"    — chunk-based evidence (IAVP Evidence Schema v1.0)
      - "row_sig_v1"  — legacy per-row signed evidence blobs
      - "unknown"     — schema could not be determined
    """
    if not evidence_blobs:
        return EVIDENCE_SCHEMA_UNKNOWN

    for blob in evidence_blobs:
        # chunk_v1: artifacts carry schema_version field
        sv = blob.get("schema_version", "")
        if sv in ("chunk_v1", "chunk_digests_v1"):
            return EVIDENCE_SCHEMA_CHUNK_V1

        # row_sig_v1: artifacts carry top-level "evidence" + "signature" dicts
        if "evidence" in blob and "signature" in blob:
            return EVIDENCE_SCHEMA_ROW_SIG_V1

    return EVIDENCE_SCHEMA_UNKNOWN


def verify_chunk_v1_evidence(evidence_blobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate chunk_v1 evidence artifacts.

    For chunk_v1, per-record signatures are NOT APPLICABLE.
    Integrity is enforced via chunk digests → hash chain → batch attestation.

    Returns a verification result dict for the evidence_integrity section.
    """
    chunk_blobs = [
        b for b in evidence_blobs
        if b.get("schema_version") == "chunk_v1"
    ]
    digest_blobs = [
        b for b in evidence_blobs
        if b.get("schema_version") == "chunk_digests_v1"
    ]

    chunk_count = len(chunk_blobs)
    total_records = sum(b.get("rows_in_chunk", 0) for b in chunk_blobs)

    # Verify each chunk has a digest
    chunks_with_digest = sum(1 for b in chunk_blobs if b.get("chunk_digest"))
    has_digest_index = len(digest_blobs) > 0

    return {
        "schema_version": EVIDENCE_SCHEMA_CHUNK_V1,
        "mode": "BATCH_ATTESTATION",
        "per_record_signatures": "NOT_APPLICABLE",
        "chunk_count": chunk_count,
        "total_records": total_records,
        "chunks_with_digest": chunks_with_digest,
        "has_digest_index": has_digest_index,
        "valid": chunks_with_digest == chunk_count and chunk_count > 0,
    }
