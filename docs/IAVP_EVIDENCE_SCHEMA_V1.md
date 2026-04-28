# IAVP Evidence Schema v1.0 — Chunk-Based (`chunk_v1`)

**Protocol:** IA-VP-1.0
**Schema Version:** `chunk_v1`
**Status:** Canonical
**Effective:** 2026-02-20

---

## 1. Overview

IAVP Evidence Schema v1.0 defines the chunk-based evidence storage format used
by the Intelligent Analyst Verification Protocol. This schema replaces the
per-record signed blob format (`row_sig_v1`) with a scalable chunk-based
architecture that maintains cryptographic integrity guarantees through digest
chains and batch-level attestation signatures.

**Per-record KMS signatures are not present in `chunk_v1`.** Integrity is
enforced via the digest chain and batch-level attestation signature.

---

## 2. Schema Identifier

Evidence artifacts conforming to this specification carry:

```json
{
  "schema_version": "chunk_v1"
}
```

The `schema_version` field is REQUIRED at the top level of every chunk artifact.
A `_chunk_digests` index document carries `schema_version: "chunk_digests_v1"`.

---

## 3. Chunk Artifact Structure

Each chunk artifact contains up to 500 records:

```json
{
  "schema_version": "chunk_v1",
  "batch_id": "<BATCH-XXXXXXXX>",
  "chunk_index": 0,
  "chunk_count": 10,
  "row_start": 0,
  "row_end": 500,
  "rows_in_chunk": 500,
  "config_version": "<sha256:...>",
  "sanitization_version": "<version>",
  "watchlist_version_hash": "<sha256:...>",
  "created_at_utc": "<ISO 8601>",
  "records": [ <per-record evidence entries> ],
  "chunk_digest": "<sha256 hex of canonical JSON before this field>"
}
```

### 3.1 Per-Record Evidence Entry

Each entry in `records` contains:

| Field | Type | Description |
|-------|------|-------------|
| `row_index` | int | Zero-based position in batch |
| `original_input` | string | Raw input as submitted |
| `sanitized_input` | string | Input after PII masking / normalization |
| `pii_detected` | list[str] | PII categories detected (may be empty) |
| `entity_type` | string | Classification (e.g., `COMPANY`, `PERSON`) |
| `decision_path` | string | Resolution path taken |
| `layer` | string | Final resolution layer (L0-L4) |
| `resolved_output` | string or null | Canonical match (null if unresolved) |
| `output_confidence` | float | Match confidence score |
| `match_type` | string | Match classification |
| `match_id` | string or null | Canonical identifier |
| `latency_ms` | float | Processing time for this record |
| `llm_used` | bool | Whether L3 LLM was invoked |
| `sustainability` | object or null | Energy/carbon estimates |

### 3.2 Chunk Digest Computation

The `chunk_digest` is computed BEFORE the field is inserted:

```
canonical_bytes = json.dumps(chunk_artifact, sort_keys=True, separators=(',', ':')).encode('utf-8')
chunk_digest = sha256(canonical_bytes).hexdigest()
```

The digest is then appended to the artifact for storage.

---

## 4. Chunk Digests Index Document

A single `_chunk_digests` document is stored per batch:

```json
{
  "schema_version": "chunk_digests_v1",
  "batch_id": "<BATCH-XXXXXXXX>",
  "chunk_count": 10,
  "row_count": 5000,
  "chunk_size": 500,
  "digests": ["<sha256>", "<sha256>", ...],
  "created_at_utc": "<ISO 8601>"
}
```

---

## 5. Integrity Chain

Cryptographic integrity flows through four layers:

```
Per-record data
    |
    v
Chunk artifacts (canonical JSON → SHA-256 digest per chunk)
    |
    v
Hash chain (STABLE_INPUT_ORDER_V2, SHA256_CHAIN_V1 → root_hash)
    |
    v
Batch-level attestation signature (ECDSA_P256_SHA256 via KMS)
    |
    v
External anchor (GCS immutable object binding root_hash)
```

### 5.1 What Is Hashed

- Each record's canonical JSON contributes to its chunk's digest.
- Each chunk's canonical JSON (including all records) is hashed to produce `chunk_digest`.
- The hash chain is computed over all records sorted by STABLE_INPUT_ORDER_V2,
  producing `root_hash`.

### 5.2 What Is Signed

The batch-level attestation manifest is signed via KMS (ECDSA_P256_SHA256).
The signed payload contains:

| Field | Source |
|-------|--------|
| `batch_id` | Batch trace ID |
| `root_hash` | Hash chain root |
| `artifact_mode` | `PRODUCTION_REAL` or `DEMO_SIMULATED` |
| `engine_version` | Server version |
| `environment` | `prod` or `test` |
| `protocol_version` | `IA-VP-1.0` |
| `config_hash` | SHA-256 of resolution config |
| `dataset_hash` | SHA-256 of input dataset |
| `key_id` | KMS key resource path |
| `metrics_hash` | SHA-256 of batch metrics |
| `record_count` | Total records processed |
| `signed_at_utc` | Signing timestamp |

The payload is JCS-canonicalized (RFC 8785) before signing.

### 5.3 What Is Anchored

The `root_hash` is written to an immutable GCS object:

```
gs://<anchor-bucket>/anchors/<tenant-hash>/<batch-id>.json
```

The anchor binds the root hash to an external, append-only store.

---

## 6. Verification Procedure

### 6.1 Schema Detection

The verifier MUST detect evidence schema before applying validation:

1. Retrieve evidence artifacts for the batch.
2. If any artifact contains `"schema_version": "chunk_v1"`, the batch uses
   `chunk_v1` evidence schema.
3. If artifacts contain `"signature"` sub-dicts with `evidence_hash_sha256`,
   the batch uses `row_sig_v1` (legacy per-row signed blobs).
4. If schema cannot be determined, the verifier MUST return `FAIL` with
   `failure_reason: "unknown_evidence_schema"`.

### 6.2 Verification Steps for `chunk_v1`

A batch PASSES verification when ALL of the following hold:

| # | Check | Field |
|---|-------|-------|
| 1 | Hash chain recomputed and matches stored root | `hash_chain.verified == true` |
| 2 | External anchor verified (if anchoring enabled) | `anchor.verified == true` |
| 3 | Attestation binding verified | `attestation_binding.verified == true` |

Per-record signature format checks are NOT APPLICABLE for `chunk_v1`.
The `evidence_integrity` section of the verification response MUST report:

```json
{
  "schema_version": "chunk_v1",
  "mode": "BATCH_ATTESTATION",
  "per_record_signatures": "NOT_APPLICABLE",
  "chunk_count": <int>,
  "total_records": <int>
}
```

### 6.3 Verification Steps for `row_sig_v1` (Legacy)

For legacy per-row evidence blobs, the existing per-record signature format
checks apply. Each sampled blob is checked for:

- `evidence_hash_sha256` present
- `signed_at_utc` present
- `service_identity` present
- `signature` field non-null (has KMS signature)

---

## 7. Backward Compatibility

| Schema | Status | Signing Model |
|--------|--------|---------------|
| `chunk_v1` | Canonical (current) | Batch attestation only |
| `row_sig_v1` | Legacy (supported) | Per-record KMS + batch |
| Unknown | Rejected | `FAIL: unknown_evidence_schema` |

Existing batches processed before the `chunk_v1` transition retain their
original evidence format and are verified using legacy rules.

---

## 8. Scalability Rationale

Per-record KMS signatures require one KMS API call per record (~100ms each).
For a 100,000-record batch, this would add ~2.8 hours of signing latency.

The `chunk_v1` schema achieves equivalent integrity guarantees with:

- 0 per-record KMS calls
- 2 batch-level KMS calls (attestation + legacy signature)
- SHA-256 digest per chunk (local computation, ~0ms overhead)
- Hash chain binding all records to a single root hash

The attestation signature over the root hash cryptographically binds all
records through the digest chain.
