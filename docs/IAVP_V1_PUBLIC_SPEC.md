# IAVP v1.0 Public Specification

**Protocol Identifier:** IA-VP-1.0
**Evidence Schema:** chunk_v1
**Status:** Frozen
**Freeze Tag:** `iavp-v1.0-protocol-frozen`
**Freeze Commit:** `1f816f761db8751211266e10a0f72a9fc8e5c5c2`
**Date:** 2026-02-20

---

## 1. Scope

This document defines the Intelligent Analyst Verification Protocol
(IAVP) version 1.0. IAVP specifies the procedures for computing,
attesting, anchoring, and verifying the integrity of batch decision
outputs produced by a conforming implementation.

IAVP does not specify the resolution logic that produces decision
outputs. It specifies the verification envelope applied to those
outputs.

A conforming implementation MUST implement all procedures defined in
this specification to claim IAVP v1.0 compatibility.

---

## 2. Normative References

| Reference | Description |
|-----------|-------------|
| RFC 8785 | JSON Canonicalization Scheme (JCS) |
| RFC 3339 | Date and Time on the Internet: Timestamps |
| FIPS 186-4 | Digital Signature Standard (ECDSA) |
| FIPS 180-4 | Secure Hash Standard (SHA-256) |
| FIPS 140-2 | Security Requirements for Cryptographic Modules |
| Unicode Standard, NFC | Canonical Decomposition followed by Canonical Composition |

---

## 3. Definitions

**Batch.** A set of input records submitted for processing in a single
operation, identified by a unique batch identifier (Trace ID).

**Record.** A single input item within a batch. Each record contains
at minimum a source identifier and the data to be resolved.

**Decision Output.** The result of processing a single record through
the resolution pipeline. Includes the resolved value, the layer that
produced the resolution, and associated metadata.

**Chunk.** A group of up to 500 decision output records stored as a
single evidence artifact under the `chunk_v1` schema.

**Chunk Digest.** The SHA-256 hash of the JCS-canonicalized JSON
representation of a chunk artifact.

**Hash Chain.** An ordered sequence of hash computations linking all
chunk digests into a single root hash.

**Root Hash.** The final output of the hash chain computation. A
unique identifier for the complete set of decision outputs in a batch.

**Attestation.** A cryptographic signature over a manifest that binds
the root hash to the batch metadata, configuration, and execution
environment.

**Anchor.** An immutable external record containing the root hash,
stored independently of the processing system.

**Replay.** An independent re-execution of the full processing
pipeline over the same input dataset and configuration.

**Verification.** The procedure of confirming determinism, integrity,
attestation validity, and anchor consistency for a completed batch.

---

## 4. Evidence Schema: chunk_v1

### 4.1 Chunk Artifact

Each chunk artifact MUST contain the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | MUST be `"chunk_v1"` |
| `batch_id` | string | Batch identifier (Trace ID) |
| `chunk_index` | integer | Zero-based chunk position within the batch |
| `rows_in_chunk` | integer | Number of records in this chunk (1–500) |
| `chunk_digest` | string | SHA-256 hex digest of the JCS-canonicalized chunk |
| `records` | array | Array of decision output records |
| `created_at` | string | RFC 3339 timestamp of chunk creation |

The maximum number of records per chunk is 500. Implementations MUST
NOT exceed this limit.

### 4.2 Chunk Digest Index

A batch MUST include one chunk digest index artifact with the
following fields:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | MUST be `"chunk_digests_v1"` |
| `batch_id` | string | Batch identifier (Trace ID) |
| `total_chunks` | integer | Total number of chunk artifacts in the batch |
| `chunk_digests` | array | Array of `{chunk_index, digest}` objects |
| `created_at` | string | RFC 3339 timestamp of index creation |

The `chunk_digests` array MUST be ordered by `chunk_index` ascending.

### 4.3 Per-Record Signatures

The `chunk_v1` schema does NOT include per-record cryptographic
signatures. Integrity of individual records is established through the
chunk digest chain and the batch-level attestation signature. This is
a deliberate architectural decision for scalability.

---

## 5. Canonicalization

### 5.1 JSON Canonicalization

All JSON structures subject to hashing MUST be canonicalized using
JCS (RFC 8785) prior to hash computation. This ensures deterministic
byte-level representation regardless of serialization order.

### 5.2 Timestamp Canonicalization

All timestamps used in sorting or hashing MUST be represented in
RFC 3339 format, UTC timezone, with exactly six fractional digits:

```
YYYY-MM-DDTHH:MM:SS.ffffffZ
```

Examples:
- `2026-02-20T14:30:00.000000Z` (valid)
- `2026-02-20T14:30:00Z` (invalid — missing fractional digits)
- `2026-02-20T14:30:00.000000+00:00` (invalid — must use Z suffix)

### 5.3 String Normalization

The `source_system_id` field MUST be normalized to Unicode NFC form
before use in sorting or hashing. The normalized string MUST be
encoded as UTF-8 bytes for comparison and hashing.

---

## 6. Hash Chain: SHA256_CHAIN_V1

### 6.1 Input Ordering: STABLE_INPUT_ORDER_V2

Before hash chain computation, all records MUST be sorted using the
following composite sort key, applied lexicographically:

1. `source_timestamp` — RFC 3339 UTC, 6 fractional digits (Section 5.2)
2. `source_system_id` — Unicode NFC normalized, compared as UTF-8 bytes (Section 5.3)
3. `record_hash` — SHA-256 hex digest of the JCS-canonicalized record, lowercase

Sorting is ascending on all three components. If two records share
identical values for all three components, they are considered
duplicates and the implementation MAY reject the batch or apply a
deterministic tiebreaker.

### 6.2 Record Hash

The hash of a single record is computed as:

```
record_hash = SHA-256(JCS(record_json))
```

Where `record_json` is the complete decision output record including
all metadata fields. The result MUST be represented as a lowercase
hexadecimal string.

### 6.3 Chunk Digest

The digest of a chunk is computed as:

```
chunk_digest = SHA-256(JCS(chunk_artifact))
```

Where `chunk_artifact` is the complete chunk JSON object including
the `schema_version`, `batch_id`, `chunk_index`, `rows_in_chunk`,
`records` array, and `created_at` fields.

### 6.4 Chain Computation

The hash chain is computed iteratively over the sorted chunk digests:

```
chain[0] = SHA-256(chunk_digests[0])
chain[i] = SHA-256(chain[i-1] || chunk_digests[i])    for i > 0
```

Where `||` denotes byte concatenation of the hex-encoded digest
strings.

The root hash is the final element of the chain:

```
root_hash = chain[N-1]    where N = total number of chunks
```

### 6.5 Root Hash

The root hash uniquely identifies the complete ordered set of
decision outputs for a batch. Any modification to any record in any
chunk produces a different root hash.

The root hash MUST be represented as a lowercase hexadecimal SHA-256
digest (64 characters).

---

## 7. Attestation: ATTESTATION_BINDING_V1

### 7.1 Attestation Manifest

The attestation manifest is a JSON object containing the following
fields:

| Field | Type | Description |
|-------|------|-------------|
| `batch_id` | string | Batch identifier |
| `root_hash` | string | Root hash from Section 6.5 |
| `config_hash` | string | SHA-256 of the processing configuration |
| `dataset_hash` | string | SHA-256 of the input dataset |
| `engine_version` | string | Version identifier of the processing engine |
| `environment` | string | Execution environment identifier |
| `record_count` | integer | Total number of records in the batch |
| `artifact_mode` | string | `PRODUCTION_REAL` or `DEMO_SIMULATED` |
| `protocol_version` | string | `IA-VP-1.0` |
| `key_id` | string | Identifier of the signing key |
| `metrics_hash` | string | SHA-256 of the batch metrics object |
| `signed_at_utc` | string | RFC 3339 timestamp of signature creation |

### 7.2 Signature Computation

The attestation signature is computed as:

```
manifest_bytes = JCS(attestation_manifest)
signature = ECDSA_P256_SHA256(signing_key, manifest_bytes)
```

The signing key MUST be an ECDSA P-256 key managed by a
cryptographic module conforming to FIPS 140-2 Level 3 or higher.

### 7.3 Key Management

Signing keys MUST be managed by a hardware security module (HSM) or
cloud KMS service. Private key material MUST NOT be exportable.

Production deployments MUST use keys that are distinct from
non-production keys. Key separation MUST be enforced at deployment
time.

---

## 8. External Anchoring

### 8.1 Anchor Record

An anchor record MUST be written to an immutable external store
after successful attestation. The anchor MUST contain:

| Field | Type | Description |
|-------|------|-------------|
| `batch_id` | string | Batch identifier |
| `root_hash` | string | Root hash from Section 6.5 |
| `attestation_hash` | string | SHA-256 of the signed attestation |
| `anchored_at` | string | RFC 3339 timestamp of anchor creation |

### 8.2 Immutability Requirements

The external store MUST enforce write-once semantics. Once an anchor
record is written, it MUST NOT be modifiable or deletable for the
duration of the retention period.

Implementations using Google Cloud Storage MUST configure a retention
policy on the anchor bucket. Implementations using other storage
systems MUST provide equivalent immutability guarantees.

### 8.3 Independence

The anchor store MUST be logically independent of the processing
system. Compromise of the processing system MUST NOT enable
modification of existing anchor records.

---

## 9. Replay Verification

### 9.1 Procedure

Replay verification re-executes the full processing pipeline over
the original input dataset using the original configuration. Each
replay run is independent — no cached results from prior runs are
used.

### 9.2 Requirements

| Parameter | Value | Notes |
|-----------|-------|-------|
| Minimum replay runs | 3 | Configurable upward, not downward |
| Required variance | 0 | All runs MUST produce identical root hashes |

### 9.3 Replay Result

A replay verification produces:

| Field | Type | Description |
|-------|------|-------------|
| `runs` | integer | Number of replay runs executed |
| `variance` | integer | Number of distinct root hashes observed |
| `determinism` | string | `VERIFIED` if variance == 0, `FAILED` otherwise |
| `replay_root_hash` | string | Root hash from the final replay run |

If `variance > 0`, the batch MUST be marked as failed. The system
MUST NOT produce a PASS verification status for a batch with
non-zero replay variance.

---

## 10. Verification Procedure

A verifier MUST execute the following steps in order to determine
the verification status of a batch.

### Step 1: Retrieve Evidence

Retrieve all chunk artifacts and the chunk digest index for the
batch. If tenant encryption is enabled, decrypt using the
appropriate tenant key.

### Step 2: Detect Evidence Schema

Inspect the `schema_version` field of retrieved artifacts. If the
schema is `chunk_v1` or `chunk_digests_v1`, proceed with chunk_v1
verification (Steps 3–7). If the schema is unrecognized, return
FAIL with reason `unknown_evidence_schema`.

### Step 3: Verify Chunk Integrity

For each chunk artifact:
1. Recompute `SHA-256(JCS(chunk_artifact))`
2. Compare with the stored `chunk_digest`
3. If any digest does not match, return FAIL

### Step 4: Verify Hash Chain

1. Sort chunk digests by `chunk_index` ascending
2. Recompute the hash chain per Section 6.4
3. Compare the computed root hash with the stored `root_hash`
4. If they do not match, return FAIL

### Step 5: Verify Attestation

1. Retrieve the attestation manifest and signature
2. Canonicalize the manifest using JCS
3. Verify the ECDSA P-256 SHA-256 signature using the stated
   public key
4. Confirm the `root_hash` in the manifest matches the computed
   root hash from Step 4
5. If verification fails, return FAIL

### Step 6: Verify Anchor

1. Retrieve the anchor record from the external store
2. Confirm the `root_hash` in the anchor matches the computed
   root hash from Step 4
3. If the anchor is missing or does not match, return FAIL

### Step 7: Verify Replay

1. Confirm `replay.runs >= 3`
2. Confirm `replay.variance == 0`
3. Confirm `replay.determinism == "VERIFIED"`
4. Confirm `replay_root_hash == root_hash`
5. If any condition fails, return FAIL

---

## 11. PASS Conditions

A batch receives `verification.status = PASS` if and only if ALL of
the following hold:

1. Evidence schema is recognized (`chunk_v1`)
2. All chunk digests are valid (Step 3)
3. Hash chain root hash matches stored root hash (Step 4)
4. Attestation signature is valid and binds to the correct root
   hash (Step 5)
5. External anchor exists and matches the root hash (Step 6)
6. Replay verification confirms determinism with zero variance
   (Step 7)

---

## 12. FAIL Conditions

A batch receives `verification.status = FAIL` if ANY of the
following hold:

1. Evidence schema is unrecognized
2. Any chunk digest does not match its recomputed value
3. Hash chain root hash does not match stored root hash
4. Attestation signature is invalid or binds to a different root hash
5. External anchor is missing or contains a different root hash
6. Replay variance is non-zero
7. Fewer than 3 replay runs were executed
8. Replay root hash does not match the chain root hash

The verification response MUST include a `failure_reason` field
identifying the first failing condition.

---

## 13. Backward Compatibility

### 13.1 Frozen Artifacts

Batch artifacts produced under IAVP v1.0 remain valid indefinitely.
A future protocol version MUST NOT invalidate verification of
artifacts produced under v1.0.

### 13.2 Schema Versioning

The evidence schema version (`chunk_v1`) is embedded in each
artifact. Verification implementations MUST inspect the schema
version and apply the verification procedure corresponding to that
schema version.

### 13.3 Protocol Version Coexistence

A verification implementation MAY support multiple protocol versions
simultaneously. The protocol version is recorded in the attestation
manifest (`protocol_version` field). The verifier MUST apply the
verification rules of the stated protocol version.

### 13.4 Minimum Support Period

Implementations claiming IAVP compatibility MUST support
verification of v1.0 artifacts for a minimum of 24 months after a
successor protocol version is released.

---

## 14. Security Considerations

### 14.1 Hash Algorithm

SHA-256 is used for all hash computations. If SHA-256 is
deprecated by NIST, a successor protocol version MUST specify a
replacement algorithm. Existing v1.0 artifacts remain valid under
their original algorithm.

### 14.2 Signature Algorithm

ECDSA P-256 with SHA-256 is used for attestation signatures. The
same deprecation policy as Section 14.1 applies.

### 14.3 Key Compromise

If a signing key is compromised, all attestations signed by that
key are suspect. The anchor record provides an independent
verification point: if the anchor root hash matches the chain root
hash, the decision outputs have not been tampered with, regardless
of key compromise. However, the attestation binding (which key
signed which batch) can no longer be trusted.

Key rotation procedures are outside the scope of this specification.

### 14.4 Replay Limitations

Replay verification confirms that the processing pipeline is
deterministic under the same configuration. It does not verify that
the configuration is correct, complete, or appropriate for any
particular use case.

---

## 15. Protocol References

| Identifier | Value |
|------------|-------|
| Protocol Version | IA-VP-1.0 |
| Evidence Schema | chunk_v1 |
| Digest Index Schema | chunk_digests_v1 |
| Hash Chain Method | SHA256_CHAIN_V1 |
| Input Ordering | STABLE_INPUT_ORDER_V2 |
| Signature Algorithm | ECDSA_P256_SHA256 |
| Attestation Version | ATTESTATION_BINDING_V1 |
| Canonicalization | RFC 8785 (JCS) |
| Minimum Replay Runs | 3 |
| Required Replay Variance | 0 |
| Maximum Chunk Size | 500 records |
| Freeze Tag | `iavp-v1.0-protocol-frozen` |
| Freeze Commit | `1f816f761db8751211266e10a0f72a9fc8e5c5c2` |

---

## Document Control

| Version | Date | Author | Status |
|---------|------|--------|--------|
| 1.0 | 2026-02-20 | Engineering | Frozen |

This specification is the normative reference for IAVP v1.0. The
protocol freeze tag in the source repository marks the exact
implementation commit corresponding to this specification.
