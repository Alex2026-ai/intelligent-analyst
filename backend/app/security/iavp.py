"""
================================================================================
INTELLIGENT ANALYST - IAVP v1.0 COMPLIANCE MODULE
================================================================================

Implements IAVP v1.0 (Intelligent Analyst Verification Protocol) primitives:
- STABLE_INPUT_ORDER_V2: Deterministic record ordering
- JCS Canonicalization (RFC 8785)
- Timestamp normalization (RFC3339 UTC, 6 fractional digits)
- Replay verification mechanism

Protocol Version: IA-VP-1.0
================================================================================
"""

import hashlib
import json
import time
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
import re

# Protocol constants
IAVP_PROTOCOL_VERSION = "IA-VP-1.0"
IAVP_ARTIFACT_VERSION = "1.0"
IAVP_HASH_CHAIN_METHOD = "SHA256_CHAIN_V1"
IAVP_ORDERING_METHOD = "STABLE_INPUT_ORDER_V2"
IAVP_REPLAY_METHOD = "FULL_BATCH_REPROCESS_UNDER_IDENTICAL_CONFIG"
IAVP_ATTESTED_SCOPE = "FULL_BATCH_MANIFEST"

# Required replay runs for variance detection
IAVP_REPLAY_RUNS = 3

# Layer canonicalization: cache-topology variants → canonical layer for deterministic hashing.
_LAYER_CANONICAL = {
    "L3_CACHED": "L3_LLM",
    "L3_FIRESTORE_CACHED": "L3_LLM",
    "L3_PERSON_CACHED": "L3_PERSON_LLM",
}


def _canonicalize_layer(layer: str) -> str:
    """Map cache-variant layer names to their canonical form for hashing."""
    return _LAYER_CANONICAL.get(layer, layer)


# =============================================================================
# JCS CANONICALIZATION (RFC 8785)
# =============================================================================

def jcs_canonicalize(obj: Any) -> bytes:
    """
    JSON Canonicalization Scheme (JCS) per RFC 8785.

    Rules:
    1. Object keys sorted lexicographically by UTF-16 code units
    2. No whitespace
    3. Numbers: no leading zeros, no trailing zeros after decimal
    4. Strings: minimal escaping (only required chars)
    5. UTF-8 output encoding

    Returns:
        Canonical JSON as UTF-8 bytes
    """
    def _serialize(item: Any) -> str:
        if item is None:
            return "null"
        elif isinstance(item, bool):
            return "true" if item else "false"
        elif isinstance(item, int):
            return str(item)
        elif isinstance(item, float):
            # JCS: Remove trailing zeros, handle -0
            if item == 0:
                return "0"
            # Use repr for consistent representation, then clean up
            s = repr(item)
            # Handle scientific notation for large/small numbers
            if 'e' in s or 'E' in s:
                return s.lower()
            # Remove trailing zeros after decimal
            if '.' in s:
                s = s.rstrip('0').rstrip('.')
            return s
        elif isinstance(item, str):
            # Minimal JSON string escaping
            return json.dumps(item, ensure_ascii=False)
        elif isinstance(item, list):
            elements = ",".join(_serialize(v) for v in item)
            return f"[{elements}]"
        elif isinstance(item, dict):
            # Sort keys by UTF-16 code units (lexicographic)
            sorted_keys = sorted(item.keys(), key=lambda k: k.encode('utf-16-be'))
            pairs = ",".join(
                f"{json.dumps(k, ensure_ascii=False)}:{_serialize(item[k])}"
                for k in sorted_keys
            )
            return "{" + pairs + "}"
        else:
            # Fallback for unknown types
            return json.dumps(item, ensure_ascii=False)

    canonical_str = _serialize(obj)
    return canonical_str.encode('utf-8')


def jcs_sha256(obj: Any) -> str:
    """
    Compute SHA-256 hash of JCS-canonicalized object.

    Returns:
        Lowercase hex digest
    """
    canonical = jcs_canonicalize(obj)
    return hashlib.sha256(canonical).hexdigest().lower()


# =============================================================================
# TIMESTAMP NORMALIZATION (RFC3339 UTC)
# =============================================================================

# Regex for RFC3339 timestamp validation
RFC3339_PATTERN = re.compile(
    r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)


def normalize_timestamp_rfc3339(ts: Any) -> str:
    """
    Normalize timestamp to RFC3339 UTC format with 6 fractional digits.

    Format: YYYY-MM-DDTHH:MM:SS.ffffffZ

    Args:
        ts: Timestamp as string, datetime, or float (unix timestamp)

    Returns:
        Normalized RFC3339 UTC string

    Raises:
        ValueError: If timestamp is non-UTC or invalid format
    """
    if ts is None:
        # Generate current timestamp
        dt = datetime.now(timezone.utc)
    elif isinstance(ts, datetime):
        if ts.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC required)")
        # Convert to UTC
        dt = ts.astimezone(timezone.utc)
    elif isinstance(ts, (int, float)):
        # Unix timestamp
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    elif isinstance(ts, str):
        # Parse RFC3339 string
        match = RFC3339_PATTERN.match(ts)
        if not match:
            raise ValueError(f"Invalid RFC3339 timestamp format: {ts}")

        # Check if UTC (Z suffix or +00:00)
        tz_part = match.group(8)
        if tz_part not in ('Z', '+00:00', '-00:00'):
            raise ValueError(f"Non-UTC timestamp rejected: {ts}")

        # Parse to datetime
        # Handle variable fractional digits
        frac = match.group(7) or ""
        if frac:
            # Normalize to 6 digits
            frac = frac[1:]  # Remove leading dot
            frac = (frac + "000000")[:6]
        else:
            frac = "000000"

        normalized_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}T{match.group(4)}:{match.group(5)}:{match.group(6)}.{frac}+00:00"
        dt = datetime.fromisoformat(normalized_str)
    else:
        raise ValueError(f"Unsupported timestamp type: {type(ts)}")

    # Format with exactly 6 fractional digits
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'


# =============================================================================
# SOURCE SYSTEM ID NORMALIZATION
# =============================================================================

def normalize_source_system_id(system_id: str) -> str:
    """
    Normalize source_system_id per STABLE_INPUT_ORDER_V1.

    Steps:
    1. Unicode NFC normalization
    2. Strip leading/trailing whitespace
    3. Collapse internal whitespace to single space
    4. Lowercase

    Returns:
        Normalized source_system_id
    """
    if not system_id:
        return ""

    # Unicode NFC normalization
    normalized = unicodedata.normalize('NFC', system_id)

    # Strip and collapse whitespace
    normalized = ' '.join(normalized.split())

    # Lowercase for consistent sorting
    normalized = normalized.lower()

    return normalized


def generate_source_system_id(batch_trace_id: str, row_index: int) -> str:
    """
    Generate deterministic source_system_id for a record.

    Format: {batch_trace_id}:{row_index:08d}

    This ensures uniqueness within a batch while maintaining
    deterministic ordering.
    """
    return f"{batch_trace_id}:{row_index:08d}"


# =============================================================================
# RECORD HASH COMPUTATION
# =============================================================================

def compute_record_hash(record: Dict[str, Any]) -> str:
    """
    Compute record hash per IAVP v1.0.

    Uses JCS canonicalization + SHA-256.

    Returns:
        Lowercase hex digest
    """
    # Extract minimal stable fields for hashing
    normalized = {
        "original": str(record.get("original", "")),
        "resolved": record.get("resolved"),  # Can be None
        "layer": str(record.get("layer", "")),
        "confidence": round(float(record.get("confidence", 0.0)), 6),
        "entity_type": str(record.get("entity_type", "")),
        "decision_path": str(record.get("decision_path", "")),
    }

    return jcs_sha256(normalized)


# =============================================================================
# STABLE_INPUT_ORDER_V2 SORTING
# =============================================================================

def sort_records_stable_order(
    records: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Sort records per STABLE_INPUT_ORDER_V2.

    Sort order (ascending):
    1. source_timestamp (RFC3339 string comparison)
    2. SHA256(original_input) — data-intrinsic, batch-ID-independent
    3. row_index (enumerate position = file order)

    V2 fixes TS-02 collision jitter: V1 used source_system_id (which
    embeds batch_trace_id) as the secondary key, causing different sort
    orders across uploads of the same dataset.

    Args:
        records: List of records with source_timestamp

    Returns:
        Tuple of (sorted_records, original_indices)
        - sorted_records: Records in stable order
        - original_indices: Mapping from sorted position to original index
    """
    if not records:
        return [], []

    # Build sort keys for each record
    indexed_records = []
    for i, record in enumerate(records):
        # Normalize timestamp
        ts_raw = record.get("source_timestamp")
        try:
            ts_normalized = normalize_timestamp_rfc3339(ts_raw)
        except ValueError:
            # If timestamp invalid, use epoch (sorts first)
            ts_normalized = "1970-01-01T00:00:00.000000Z"

        # V2: SHA256 of original input (data-intrinsic, no batch_trace_id dependency)
        original_input = str(record.get("original", ""))
        original_hash = hashlib.sha256(original_input.encode('utf-8')).hexdigest()

        # Normalize source_system_id (still needed for chain entry data, not for sorting)
        ssid_raw = record.get("source_system_id", "")
        ssid_normalized = normalize_source_system_id(ssid_raw)

        # Compute record hash (still needed for chain entry data)
        record_hash = compute_record_hash(record)

        # Store normalized values back for chain computation
        record["_normalized_timestamp"] = ts_normalized
        record["_normalized_ssid"] = ssid_normalized
        record["_record_hash"] = record_hash

        # V2 sort key: (timestamp, original_hash, row_index)
        indexed_records.append((ts_normalized, original_hash, i, record))

    # Sort by (timestamp, original_hash, row_index)
    sorted_indexed = sorted(indexed_records, key=lambda x: (x[0], x[1], x[2]))

    # Extract sorted records and original indices
    sorted_records = [item[3] for item in sorted_indexed]
    original_indices = [item[2] for item in sorted_indexed]

    return sorted_records, original_indices


def prepare_records_for_chain(
    records: List[Dict[str, Any]],
    batch_trace_id: str,
    ingestion_timestamp: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Prepare records for hash chain construction per IAVP v1.0.

    Steps:
    1. Assign source_timestamp if missing (use ingestion time)
    2. Assign source_system_id if missing (use batch_trace_id:row_index)
    3. Normalize all values
    4. Sort per STABLE_INPUT_ORDER_V2

    Args:
        records: Raw resolution results
        batch_trace_id: Batch identifier
        ingestion_timestamp: Timestamp to use for records (defaults to now)

    Returns:
        Records in stable order, ready for chain computation
    """
    if not records:
        return []

    # Default ingestion timestamp
    if ingestion_timestamp is None:
        ingestion_timestamp = datetime.now(timezone.utc)

    ingestion_ts_str = normalize_timestamp_rfc3339(ingestion_timestamp)

    # Assign missing fields
    for i, record in enumerate(records):
        if not record.get("source_timestamp"):
            record["source_timestamp"] = ingestion_ts_str

        if not record.get("source_system_id"):
            record["source_system_id"] = generate_source_system_id(batch_trace_id, i)

    # Sort per STABLE_INPUT_ORDER_V2
    sorted_records, _ = sort_records_stable_order(records)

    return sorted_records


# =============================================================================
# DECISION LEDGER
# =============================================================================

def build_decision_ledger(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract immutable decision fields from resolved records.

    The ledger contains ONLY the intrinsic fields needed for hash chain
    computation and sorting. This avoids expensive deepcopy of full
    result dicts (which may contain audit trails, PII metadata, etc.)
    during replay verification.

    Fields:
        - original, resolved, layer, confidence, entity_type, decision_path
          (decision fields, used by compute_event_hash)
        - source_timestamp, source_system_id
          (ordering fields, used by sort_records_stable_order)
    """
    ledger = []
    for r in records:
        ledger.append({
            "original": str(r.get("original", "")),
            "resolved": r.get("resolved"),
            "layer": _canonicalize_layer(str(r.get("layer", ""))),
            "confidence": round(float(r.get("confidence", 0.0)), 6),
            "entity_type": str(r.get("entity_type", "")),
            "decision_path": str(r.get("decision_path", "")),
            "source_timestamp": r.get("source_timestamp"),
            "source_system_id": r.get("source_system_id"),
        })
    return ledger


# =============================================================================
# REPLAY VERIFICATION
# =============================================================================

class ReplayVerificationResult:
    """Result of replay verification."""

    def __init__(self):
        self.runs: List[str] = []  # Root hashes from each run
        self.variance: int = 0  # Count of mismatched runs
        self.passed: bool = False
        self.method: str = IAVP_REPLAY_METHOD

    def add_run(self, root_hash: str):
        """Add a replay run result."""
        self.runs.append(root_hash)

        # Check variance after each run
        if len(self.runs) > 1:
            expected = self.runs[0]
            self.variance = sum(1 for h in self.runs if h != expected)
            self.passed = self.variance == 0
        else:
            self.passed = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for manifest."""
        return {
            "replay_runs": len(self.runs),
            "replay_variance": self.variance,
            "replay_method": self.method,
            "replay_passed": self.passed,
            "run_hashes": self.runs,
        }


def verify_determinism(
    records: List[Dict[str, Any]],
    batch_trace_id: str,
    compute_chain_fn,
    runs: int = IAVP_REPLAY_RUNS,
    ledger: Optional[List[Dict[str, Any]]] = None
) -> ReplayVerificationResult:
    """
    Verify hash chain determinism through replay.

    Performs `runs` independent computations and compares root hashes.
    Uses a pre-built decision ledger (minimal intrinsic fields) to avoid
    expensive deepcopy of full result dicts.

    Args:
        records: Raw resolution results (fallback if ledger not provided)
        batch_trace_id: Batch identifier
        compute_chain_fn: Function(sorted_records) -> root_hash
        runs: Number of replay runs (default: 3)
        ledger: Pre-built decision ledger (preferred, avoids deepcopy)

    Returns:
        ReplayVerificationResult with variance count
    """
    result = ReplayVerificationResult()

    # Use ledger if provided (shallow copy per run), fall back to deepcopy
    use_ledger = ledger is not None

    for run_idx in range(runs):
        if use_ledger:
            # Shallow copy of minimal dicts — O(n) with small constant
            records_copy = [dict(entry) for entry in ledger]
        else:
            import copy
            records_copy = copy.deepcopy(records)

        # Prepare records (assigns timestamps, sorts)
        sorted_records = prepare_records_for_chain(
            records_copy,
            batch_trace_id
        )

        # Compute chain and get root hash
        root_hash = compute_chain_fn(sorted_records)
        result.add_run(root_hash)

        # Structured log: per-replay-run hash (inline to keep iavp.py self-contained)
        print(json.dumps({
            "severity": "INFO", "trace_id": batch_trace_id,
            "phase": "replay", "event": "replay_run_complete",
            "ts": time.time(), "run_index": run_idx, "run_total": runs,
            "root_hash": root_hash, "variance": result.variance,
            "replay_mode": "ledger_rehash" if use_ledger else "deepcopy_legacy",
        }, default=str), flush=True)

    return result


# =============================================================================
# CONFIG HASH COMPUTATION
# =============================================================================

def compute_config_hash(config_dict: Dict[str, Any]) -> str:
    """
    Compute SHA-256 hash of configuration snapshot.

    Uses JCS canonicalization for determinism.

    Returns:
        Lowercase hex digest
    """
    return jcs_sha256(config_dict)


def compute_dataset_hash(records: List[Dict[str, Any]]) -> str:
    """
    Compute SHA-256 hash of input dataset.

    Hash is computed over the 'original' field of each record
    in STABLE_INPUT_ORDER_V2 order.

    Returns:
        Lowercase hex digest
    """
    if not records:
        return hashlib.sha256(b"").hexdigest()

    # Sort records first
    sorted_records, _ = sort_records_stable_order(records)

    # Concatenate original values
    originals = [str(r.get("original", "")) for r in sorted_records]
    combined = "\n".join(originals)

    return hashlib.sha256(combined.encode('utf-8')).hexdigest().lower()


# =============================================================================
# ARTIFACT MODE ENFORCEMENT
# =============================================================================

class ArtifactMode:
    """Artifact mode constants."""
    DEMO_SIMULATED = "DEMO_SIMULATED"
    PRODUCTION_REAL = "PRODUCTION_REAL"


class ArtifactModeViolationError(Exception):
    """Raised when artifact_mode doesn't match environment."""
    pass


def validate_artifact_mode(
    artifact_mode: str,
    is_production: bool
) -> None:
    """
    Validate artifact_mode matches environment.

    Rules:
    - Production environment: MUST be PRODUCTION_REAL
    - Demo environment: MUST be DEMO_SIMULATED

    Raises:
        ArtifactModeViolationError: If mismatch detected
    """
    if is_production:
        if artifact_mode != ArtifactMode.PRODUCTION_REAL:
            raise ArtifactModeViolationError(
                f"Production environment requires artifact_mode=PRODUCTION_REAL, "
                f"got: {artifact_mode}"
            )
    else:
        if artifact_mode != ArtifactMode.DEMO_SIMULATED:
            raise ArtifactModeViolationError(
                f"Demo environment requires artifact_mode=DEMO_SIMULATED, "
                f"got: {artifact_mode}"
            )


def get_artifact_mode(is_production: bool) -> str:
    """
    Get artifact_mode for current environment.

    Returns:
        PRODUCTION_REAL or DEMO_SIMULATED
    """
    return ArtifactMode.PRODUCTION_REAL if is_production else ArtifactMode.DEMO_SIMULATED


# =============================================================================
# KEY SEPARATION ENFORCEMENT
# =============================================================================

# Demo key fingerprint prefix (for detection)
DEMO_KEY_FINGERPRINT_PREFIX = "demo-"


class KeySeparationViolationError(Exception):
    """Raised when demo key is used in production environment."""
    pass


def validate_key_separation(
    key_id: str,
    key_fingerprint: str,
    is_production: bool
) -> None:
    """
    Validate key separation between demo and production.

    Rules:
    - Production: key_id MUST contain 'prod' and NOT contain 'demo'
    - Demo: key_id MUST contain 'demo' or 'test'

    Raises:
        KeySeparationViolationError: If violation detected
    """
    key_id_lower = key_id.lower()

    if is_production:
        # Check for demo key in production
        if 'demo' in key_id_lower or 'test' in key_id_lower:
            raise KeySeparationViolationError(
                f"Demo/test key detected in production environment: {key_id}"
            )

        # Verify production key identifier
        if 'prod' not in key_id_lower:
            raise KeySeparationViolationError(
                f"Production key must contain 'prod' in key_id: {key_id}"
            )

        # Check fingerprint doesn't match demo prefix
        if key_fingerprint.startswith(DEMO_KEY_FINGERPRINT_PREFIX):
            raise KeySeparationViolationError(
                f"Demo key fingerprint detected in production: {key_fingerprint}"
            )
    else:
        # Demo environment - should NOT use production keys
        if 'prod' in key_id_lower and 'demo' not in key_id_lower:
            raise KeySeparationViolationError(
                f"Production key detected in demo environment: {key_id}"
            )


# =============================================================================
# MANIFEST BUILDER
# =============================================================================

def build_iavp_manifest(
    batch_id: str,
    artifact_type: str,
    artifact_mode: str,
    engine_version: str,
    config_hash: str,
    dataset_hash: str,
    root_hash: str,
    record_count: int,
    metrics: Dict[str, Any],
    replay_result: ReplayVerificationResult,
    key_id: str,
    pubkey_fingerprint: str,
    generated_at: Optional[datetime] = None,
    tenant_id_hash: Optional[str] = None,
    tenant_region: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build IAVP v1.0 compliant attestation manifest.

    All required fields per IAVP v1.0 specification.

    Returns:
        Complete manifest dictionary
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    manifest = {
        "protocol_version": IAVP_PROTOCOL_VERSION,
        "artifact_type": artifact_type,
        "artifact_version": IAVP_ARTIFACT_VERSION,
        "artifact_mode": artifact_mode,
        "attested_scope": IAVP_ATTESTED_SCOPE,
        "batch_id": batch_id,
        "generated_at_utc": normalize_timestamp_rfc3339(generated_at),
        "tenant_id_hash_sha256": tenant_id_hash,
        "tenant_region": tenant_region,
        "engine_version": engine_version,
        "config_hash_sha256": config_hash,
        "dataset_hash_sha256": dataset_hash,
        "hash_chain": {
            "method": IAVP_HASH_CHAIN_METHOD,
            "ordering": IAVP_ORDERING_METHOD,
            "root_hash_sha256": root_hash,
            "record_count": record_count,
        },
        "metrics": {
            "l1_pct": metrics.get("l1_pct", 0.0),
            "l2_pct": metrics.get("l2_pct", 0.0),
            "l3_pct": metrics.get("l3_pct", 0.0),
            "l4_pct": metrics.get("l4_pct", 0.0),
            "replay_runs": replay_result.to_dict()["replay_runs"],
            "replay_variance": replay_result.to_dict()["replay_variance"],
            "replay_method": replay_result.to_dict()["replay_method"],
        },
        "key": {
            "key_id": key_id,
            "pubkey_fingerprint_sha256": pubkey_fingerprint,
        },
    }

    return manifest


def validate_manifest_schema(manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate manifest against IAVP v1.0 required fields.

    Returns:
        (valid, missing_fields)
    """
    required_fields = [
        "protocol_version",
        "artifact_type",
        "artifact_version",
        "artifact_mode",
        "attested_scope",
        "batch_id",
        "generated_at_utc",
        "engine_version",
        "config_hash_sha256",
        "dataset_hash_sha256",
    ]

    required_hash_chain = [
        "method",
        "ordering",
        "root_hash_sha256",
        "record_count",
    ]

    required_metrics = [
        "l1_pct",
        "l2_pct",
        "l3_pct",
        "l4_pct",
        "replay_runs",
        "replay_variance",
        "replay_method",
    ]

    required_key = [
        "key_id",
        "pubkey_fingerprint_sha256",
    ]

    missing = []

    # Check top-level fields
    for field in required_fields:
        if field not in manifest:
            missing.append(field)

    # Check hash_chain fields
    hash_chain = manifest.get("hash_chain", {})
    for field in required_hash_chain:
        if field not in hash_chain:
            missing.append(f"hash_chain.{field}")

    # Check metrics fields
    metrics = manifest.get("metrics", {})
    for field in required_metrics:
        if field not in metrics:
            missing.append(f"metrics.{field}")

    # Check key fields
    key = manifest.get("key", {})
    for field in required_key:
        if field not in key:
            missing.append(f"key.{field}")

    return len(missing) == 0, missing


# =============================================================================
# ATTESTATION PAYLOAD (FE-5.2 Binding Upgrade)
# =============================================================================

ATTESTATION_PAYLOAD_VERSION = "1.2"


def build_attestation_payload(
    batch_id: str,
    root_hash: str,
    artifact_mode: str,
    engine_version: str,
    environment: str,
    protocol_version: str,
    config_hash: Optional[str],
    dataset_hash: Optional[str],
    key_id: str,
    metrics_hash: Optional[str],
    record_count: int,
    signed_at_utc: str,
    tenant_id_hash: Optional[str] = None,
    tenant_region: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the attestation payload that will be JCS-canonicalized and signed.

    All fields are binding — modifying any field post-signature will
    invalidate the ECDSA signature. This fixes FE-5.2 (metadata spoof)
    by binding artifact_mode, config_hash, environment, etc. to the
    cryptographic signature instead of signing only root_hash.

    Returns:
        Dictionary with stable field names (will be JCS-canonicalized).
    """
    return {
        "attestation_version": ATTESTATION_PAYLOAD_VERSION,
        "artifact_mode": artifact_mode,
        "batch_id": batch_id,
        "config_hash_sha256": config_hash,
        "dataset_hash_sha256": dataset_hash,
        "engine_version": engine_version,
        "environment": environment,
        "key_id": key_id,
        "metrics_hash_sha256": metrics_hash,
        "protocol_version": protocol_version,
        "record_count": record_count,
        "root_hash_sha256": root_hash,
        "signed_at_utc": signed_at_utc,
        "tenant_id_hash_sha256": tenant_id_hash,
        "tenant_region": tenant_region,
    }
