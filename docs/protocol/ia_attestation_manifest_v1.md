# IA Attestation Manifest v1 — Canonical Schema Specification

**Status**: FROZEN v1
**Date**: 2026-03-13 (frozen: 2026-03-13)
**Author**: Intelligent Analyst Engineering
**Scope**: Schema freeze candidate for Phase 23

---

## 1. Manifest Object

### 1.1 Canonical Field Order

Fields are defined in **lexicographic order** (RFC 8785 JCS requirement). This ordering is normative — implementations MUST serialize fields in this order.

```json
{
  "anchor_ref": {},
  "artifact_hashes": [],
  "artifact_mode": "",
  "batch_id": "",
  "config_hash": "",
  "dataset_hash": "",
  "engine_version": "",
  "environment": "",
  "key_id": "",
  "metrics": {},
  "protocol_version": "ia-attestation/v1",
  "receipt_id": "",
  "registry_hash": "",
  "root_hash": "",
  "signature_algorithm": "",
  "source_blob_hash": "",
  "tenant_scope": "",
  "timestamp": ""
}
```

### 1.2 Field Definitions

| # | Field | Type | Required | Description |
|---|-------|------|----------|-------------|
| 1 | `anchor_ref` | object | REQUIRED | Binding to GCS anchor object (see §5) |
| 2 | `artifact_hashes` | array | REQUIRED | Per-artifact integrity records (see §6). Empty array `[]` if no artifacts. |
| 3 | `artifact_mode` | string | REQUIRED | `"PRODUCTION_REAL"` or `"DEMO_SIMULATED"` |
| 4 | `batch_id` | string | REQUIRED | Batch trace ID (e.g., `"BATCH-D8917A6A"`) |
| 5 | `config_hash` | string | REQUIRED | SHA-256 hex of JCS-canonicalized config snapshot |
| 6 | `dataset_hash` | string | REQUIRED | SHA-256 hex of JCS-canonicalized input array (see §1.5) |
| 7 | `engine_version` | string | REQUIRED | Semantic version (e.g., `"8.2.2"`) |
| 8 | `environment` | string | REQUIRED | `"prod"` or `"test"` |
| 9 | `key_id` | string | REQUIRED | Full KMS key resource path |
| 10 | `metrics` | object | REQUIRED | Resolution layer distribution (see §1.4) |
| 11 | `protocol_version` | string | REQUIRED | Fixed: `"ia-attestation/v1"` |
| 12 | `receipt_id` | string | REQUIRED | Unique receipt identifier (UUID v4) |
| 13 | `registry_hash` | string | REQUIRED | SHA-256 hex of canonical company registry |
| 14 | `root_hash` | string | REQUIRED | Batch root hash from hash-chain computation |
| 15 | `signature_algorithm` | string | REQUIRED | `"EC_SIGN_P256_SHA256"` |
| 16 | `source_blob_hash` | string | OPTIONAL | SHA-256 hex of the raw uploaded file bytes before parsing. `null` if batch was submitted via JSON `/batch` endpoint. |
| 17 | `tenant_scope` | string | REQUIRED | Pseudonymous scope token: `HMAC-SHA256(tenant_id, scope_key)[:16]` (see §1.6) |
| 18 | `timestamp` | string | REQUIRED | RFC 3339 UTC with microseconds (e.g., `"2026-03-13T00:18:16.608540Z"`) |

17 REQUIRED fields + 1 OPTIONAL (`source_blob_hash`). When `source_blob_hash` is absent, serialize as `null`. No extension fields.

### 1.3 Field Value Constraints

| Field | Constraint |
|-------|------------|
| `protocol_version` | Literal `"ia-attestation/v1"`. Any other value → reject. |
| `artifact_mode` | Enum: `"PRODUCTION_REAL"` \| `"DEMO_SIMULATED"`. Must match environment. |
| `environment` | Enum: `"prod"` \| `"test"`. |
| `signature_algorithm` | Literal `"EC_SIGN_P256_SHA256"`. Matches existing IA KMS signing. |
| `root_hash` | 64-char lowercase hex string (SHA-256). |
| `config_hash` | 64-char lowercase hex string (SHA-256). |
| `dataset_hash` | 64-char lowercase hex string (SHA-256). See §1.5 for computation. |
| `registry_hash` | 64-char lowercase hex string (SHA-256). |
| `source_blob_hash` | 64-char lowercase hex string (SHA-256) or `null`. |
| `tenant_scope` | 16-char lowercase hex string. Derived via HMAC, not raw SHA-256. See §1.6. |
| `timestamp` | RFC 3339 with `Z` suffix. Microsecond precision. |
| `receipt_id` | UUID v4 format (`xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`). |
| `batch_id` | Pattern: `BATCH-[A-F0-9]{8}`. |
| `key_id` | Non-empty string. Must match KMS key path format for `PRODUCTION_REAL`. |
| `engine_version` | Semantic version (`X.Y.Z`). |

### 1.4 Metrics Object

```json
{
  "l1_pct": 0.85,
  "l2_pct": 0.08,
  "l3_pct": 0.02,
  "l4_pct": 0.05,
  "record_count": 5000,
  "replay_method": "STABLE_INPUT_ORDER_V2",
  "replay_runs": 3,
  "replay_variance": 0
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `l1_pct` | number | REQUIRED | L1 deterministic resolution percentage (0.0–1.0) |
| `l2_pct` | number | REQUIRED | L2 vector resolution percentage (0.0–1.0) |
| `l3_pct` | number | REQUIRED | L3 LLM resolution percentage (0.0–1.0) |
| `l4_pct` | number | REQUIRED | L4 human review percentage (0.0–1.0) |
| `record_count` | integer | REQUIRED | Total records in batch |
| `replay_method` | string | REQUIRED | `"STABLE_INPUT_ORDER_V2"` |
| `replay_runs` | integer | REQUIRED | Number of replay verification runs |
| `replay_variance` | integer | REQUIRED | Mismatched replay runs (must be 0 for valid attestation) |

Percentages MUST sum to 1.0 (±0.01 tolerance for rounding).

### 1.5 Dataset Hash Computation

`dataset_hash` commits to the exact input the engine processed, independent of upload format.

```
1. Collect all input records in STABLE_INPUT_ORDER_V2 sort order:
     sort by (source_timestamp ASC, SHA256(original_input) ASC, row_index ASC)

2. For each record, extract the raw `original` string (pre-sanitization,
   pre-PII-masking — the string the user submitted).

3. Build a JSON array of the sorted original strings:
     input_array = ["record_0.original", "record_1.original", ..., "record_N.original"]

4. JCS-canonicalize the array (RFC 8785):
     canonical_bytes = JCS( input_array )

5. Compute:
     dataset_hash = lowercase_hex( SHA-256( canonical_bytes ) )
```

**Properties**:
- Deterministic: same inputs in same order → same hash, regardless of file format (CSV, XLSX, JSON).
- Order-sensitive: reordering inputs changes the hash (array position is significant under JCS).
- Pre-masking: PII masking is not applied before hashing. The hash commits to the actual submitted data.
- JCS-native: uses the same canonicalization function as every other hash in the manifest, eliminating a class of serialization bugs (newline handling, encoding, escaping).

**Relationship to `source_blob_hash`**: `dataset_hash` is always computed (even for JSON `/batch` submissions). `source_blob_hash` is only present when a raw file was uploaded. They serve different purposes — `dataset_hash` proves _what was processed_, `source_blob_hash` proves _what was received_.

### 1.6 Tenant Scope (Pseudonymous)

`tenant_scope` is a pseudonymous, non-reversible token derived from the internal `tenant_id`. It allows correlation across receipts for the same tenant without exposing the tenant identity.

```
scope_key      = HMAC_SCOPE_KEY environment variable (32-byte secret, per-environment)
tenant_scope   = lowercase_hex( HMAC-SHA256( key=scope_key, msg=UTF-8(tenant_id) ) )[:16]
```

**Properties**:
- **Not reversible**: HMAC output cannot recover `tenant_id` without the key.
- **Not correlatable across environments**: different `scope_key` per environment means the same tenant produces different `tenant_scope` values in TEST vs PROD.
- **Stable within environment**: same tenant always produces the same `tenant_scope` in the same environment.
- **16 hex chars**: 64 bits of entropy. Sufficient for pseudonymous grouping, not a security identifier.

**Migration from raw SHA-256**: The previous design used `SHA256(tenant_id)[:16]` which is deterministic without a key — an attacker with a candidate tenant_id list could enumerate and match. HMAC adds a secret key, making offline enumeration infeasible.

**Key management**: `HMAC_SCOPE_KEY` is a new secret. It MUST be stored in Secret Manager alongside existing secrets. Loss of this key does not break signature verification — it only prevents the server from generating new `tenant_scope` values that match historical ones. Existing manifests remain valid.

---

## 2. Canonicalization Rule

### 2.1 Standard

**RFC 8785 — JSON Canonicalization Scheme (JCS)**

### 2.2 Rules

1. Object keys sorted lexicographically by **UTF-16 code units** (not byte order).
2. No whitespace between tokens.
3. Numbers: no leading zeros, no unnecessary trailing zeros after decimal point, no positive sign, no `e` notation for integers.
4. Strings: minimal JSON escaping (`\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t`, `\uXXXX` for control characters only).
5. Output encoding: **UTF-8**.
6. `null`, `true`, `false` rendered as literals.
7. Arrays preserve insertion order.

### 2.3 Invariant

```
same manifest object → same JCS bytes → same SHA-256 hash → same signature
```

This is the foundational determinism guarantee. Any implementation that produces different bytes for the same logical object is non-conformant.

### 2.4 Existing Implementation

The IA engine already implements JCS via `jcs_canonicalize()` in `backend/app/security/iavp.py` (lines 52–116). The attestation manifest MUST use this same function.

---

## 3. Signature Rule

### 3.1 Signature Computation

```
canonical_bytes  = JCS( manifest_object )
digest           = SHA-256( canonical_bytes )
signature        = ECDSA_P256_Sign( digest, kms_private_key )
signature_b64    = Base64Encode( signature )
```

### 3.2 Signing Key

| Property | Value |
|----------|-------|
| Algorithm | `EC_SIGN_P256_SHA256` (ECDSA with P-256 curve, SHA-256 digest) |
| Provider | Google Cloud KMS |
| Key path | Value of `key_id` field in manifest |
| PROD key | Must contain `"prod"` in key path (key separation enforcement) |
| TEST key | Must contain `"demo"` or `"test"` in key path |

This is the **same signing key** already used for evidence blob signatures and batch attestation in the existing IA pipeline. No new key is introduced.

### 3.3 Signature Envelope

The signature is NOT embedded in the manifest. It is stored alongside:

```json
{
  "manifest": { ... },
  "signature": {
    "value": "<base64-encoded ECDSA signature>",
    "algorithm": "EC_SIGN_P256_SHA256",
    "key_id": "<KMS key resource path>",
    "signed_at_utc": "<RFC 3339 timestamp>"
  }
}
```

**Rationale**: Embedding the signature inside the manifest would change the manifest bytes, breaking the hash. The signature MUST be external to the signed object.

### 3.4 Signature Verification

```
canonical_bytes  = JCS( manifest_object )
digest           = SHA-256( canonical_bytes )
valid            = ECDSA_P256_Verify( digest, signature_bytes, public_key )
```

Public key is retrievable from `GET /security/public-key`.

---

## 4. Verification Endpoint

### 4.1 Endpoint

```
GET /verify/{receipt_id}
```

**Authentication**: None required. Verification is public by design — any holder of a receipt_id can verify it.

### 4.2 Response Schema

The `/verify` response returns a **public-safe projection** of the manifest. Internal infrastructure details (GCS bucket names, object paths, KMS key resource paths) are redacted. The signature is verified server-side against the full internal manifest.

```json
{
  "receipt_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "manifest_public": {
    "anchor_ref": {
      "anchor_hash": "sha256-hex-of-anchor-object",
      "anchor_timestamp": "2026-03-13T00:18:16.608540Z"
    },
    "artifact_hashes": [ ... ],
    "artifact_mode": "PRODUCTION_REAL",
    "batch_id": "BATCH-D8917A6A",
    "config_hash": "abc123...",
    "dataset_hash": "def456...",
    "engine_version": "8.2.2",
    "environment": "prod",
    "metrics": { ... },
    "protocol_version": "ia-attestation/v1",
    "receipt_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "registry_hash": "789abc...",
    "root_hash": "fedcba...",
    "signature_algorithm": "EC_SIGN_P256_SHA256",
    "source_blob_hash": null,
    "tenant_scope": "a7c3e19b04f2d816",
    "timestamp": "2026-03-13T00:18:16.608540Z"
  },
  "signature_valid": true,
  "anchor_valid": true,
  "artifact_integrity": true,
  "replayable": true,
  "verification_timestamp": "2026-03-13T01:00:00.000000Z"
}
```

### 4.3 Public Projection Rules

The `manifest_public` object is derived from the full manifest with these redactions:

| Full Manifest Field | Public Projection |
|---------------------|-------------------|
| `anchor_ref.bucket` | **REDACTED** — not included |
| `anchor_ref.object_path` | **REDACTED** — not included |
| `anchor_ref.anchor_hash` | Included (verifiable hash, no infrastructure leak) |
| `anchor_ref.anchor_timestamp` | Included |
| `key_id` | **REDACTED** — not included (reveals KMS key path / GCP project structure) |
| All other fields | Included as-is |

**Rationale**: `bucket` and `object_path` reveal GCS bucket naming conventions and tenant directory structure. `key_id` reveals the full KMS resource path including GCP project ID, region, keyring name, and key version. None of these are needed by external verifiers — the server performs anchor and signature verification internally and reports boolean results.

### 4.4 Response Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `receipt_id` | string | Echo of the requested receipt ID |
| `manifest_public` | object | Public-safe projection of the manifest (infrastructure fields redacted) |
| `signature_valid` | boolean | ECDSA signature verified server-side against full internal manifest JCS bytes |
| `anchor_valid` | boolean | `anchor_ref.anchor_hash` matches recomputed hash of GCS anchor object, and `root_hash` matches anchor's `batch_root_hash` |
| `artifact_integrity` | boolean | Every entry in `artifact_hashes` matches the actual artifact SHA-256 |
| `replayable` | boolean | `metrics.replay_variance == 0` and replay verification passed |
| `verification_timestamp` | string | RFC 3339 UTC timestamp of when verification was performed |

### 4.5 Failure Response

If any check fails:

```json
{
  "receipt_id": "a1b2c3d4-...",
  "manifest_public": { ... },
  "signature_valid": false,
  "anchor_valid": true,
  "artifact_integrity": true,
  "replayable": true,
  "verification_timestamp": "2026-03-13T01:00:00.000000Z",
  "failures": [
    {
      "check": "signature_valid",
      "reason": "ECDSA signature verification failed"
    }
  ]
}
```

The `failures` array is present only when at least one check is `false`. Each entry names the failed check and a human-readable reason. No internal data (key material, file paths, stack traces) is ever included.

### 4.6 Error Responses

| HTTP Status | Condition |
|-------------|-----------|
| 200 | Verification completed (even if checks fail — failures are in the body) |
| 404 | `receipt_id` not found |
| 500 | Internal verification error |

### 4.7 No Internal Data Leaks

The `/verify` response MUST NOT include:

- Tenant ID (only pseudonymous `tenant_scope` HMAC token is exposed)
- Raw company names or resolution results
- GCS bucket names or object paths (redacted from `anchor_ref`)
- KMS key resource paths (redacted — `key_id` not in public projection)
- GCP project IDs, regions, or keyring names
- KMS key material or private key data
- Stack traces or internal error details
- Evidence blob contents
- Internal IP addresses or service URLs

---

## 5. Anchor Binding

### 5.1 Anchor Reference Object

```json
{
  "anchor_hash": "sha256-hex-of-anchor-object",
  "anchor_timestamp": "2026-03-13T00:18:16.608540Z",
  "bucket": "ia-anchor-{environment}",
  "object_path": "anchors/f62a772b405ee176/BATCH-D8917A6A.json"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `anchor_hash` | string | REQUIRED | SHA-256 hex of the serialized anchor JSON object in GCS |
| `anchor_timestamp` | string | REQUIRED | RFC 3339 UTC timestamp from anchor `created_at_utc` |
| `bucket` | string | REQUIRED | GCS bucket name |
| `object_path` | string | REQUIRED | GCS object path within bucket |

### 5.2 Binding Rules

1. `anchor_ref.anchor_hash` MUST equal `SHA-256(GCS_object_bytes)` — the hash of the raw bytes stored in GCS.
2. The anchor object stored in GCS MUST contain a `batch_root_hash` field that equals the manifest's `root_hash`.
3. The anchor bucket MUST have `objectCreator`-only permissions (no delete, no overwrite) to guarantee append-only semantics.

### 5.3 Verification Procedure

```
anchor_bytes     = GCS_Read( bucket, object_path )
anchor_object    = JSON_Parse( anchor_bytes )

CHECK 1: SHA-256( anchor_bytes ) == anchor_ref.anchor_hash
CHECK 2: anchor_object.batch_root_hash == manifest.root_hash
CHECK 3: anchor_object.created_at_utc == anchor_ref.anchor_timestamp
```

All three checks must pass for `anchor_valid = true`.

---

## 6. Artifact Hashes

### 6.1 Array Structure

```json
[
  {
    "artifact_type": "evidence_pack",
    "hash": "sha256-hex-of-artifact-bytes",
    "size_bytes": 1048576
  },
  {
    "artifact_type": "certificate_pdf",
    "hash": "sha256-hex-of-artifact-bytes",
    "size_bytes": 24576
  },
  {
    "artifact_type": "audit_events",
    "hash": "sha256-hex-of-artifact-bytes",
    "size_bytes": 65536
  }
]
```

### 6.2 Artifact Entry Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `artifact_type` | string | REQUIRED | Artifact type identifier (see §6.3) |
| `hash` | string | REQUIRED | SHA-256 hex of the artifact bytes |
| `size_bytes` | integer | REQUIRED | Byte length of the artifact |

### 6.3 Artifact Types

| Type | Description |
|------|-------------|
| `evidence_pack` | ZIP bundle from evidence pack generation |
| `certificate_pdf` | Forensic transparency certificate PDF |
| `audit_events` | JSON array of audit events |
| `hash_chain` | Serialized hash chain entries |
| `anchor_record` | GCS anchor JSON object |

### 6.4 Verification Procedure

For each entry in `artifact_hashes`:

```
artifact_bytes = retrieve_artifact( artifact_type, batch_id )
CHECK: SHA-256( artifact_bytes ) == entry.hash
CHECK: len( artifact_bytes ) == entry.size_bytes
```

All entries must pass for `artifact_integrity = true`.

---

## 7. Reference Verifier

### 7.1 Overview

A minimal, standalone Python script that verifies an attestation manifest without requiring access to the IA backend.

### 7.2 File

```
tools/verify_receipt.py
```

### 7.3 Inputs

| Input | Source | Required |
|-------|--------|----------|
| `manifest.json` | Exported manifest file | REQUIRED |
| `signature.bin` | Raw ECDSA signature bytes (or base64 in JSON envelope) | REQUIRED |
| `public_key.pem` | ECDSA P-256 public key from `/security/public-key` | REQUIRED |
| Artifact files | Individual artifacts for hash verification | OPTIONAL |

### 7.4 Dependencies

```
cryptography>=41.0.0   # ECDSA verification
```

No IA-internal imports. No network calls. Fully offline.

### 7.5 Verification Steps

```
1. Parse manifest.json → validate 17 required fields + 1 optional
2. Validate protocol_version == "ia-attestation/v1"
3. JCS-canonicalize manifest object
4. SHA-256 digest of canonical bytes
5. ECDSA P-256 verify( digest, signature, public_key )
6. If artifact files provided:
   a. For each artifact: SHA-256(file_bytes) == manifest.artifact_hashes[i].hash
   b. For each artifact: len(file_bytes) == manifest.artifact_hashes[i].size_bytes
7. Print VALID or INVALID with details
```

### 7.6 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | `VALID` — signature and all artifact hashes verified |
| 1 | `INVALID` — signature verification failed |
| 2 | `INVALID` — artifact hash mismatch |
| 3 | `INVALID` — malformed manifest (missing fields, wrong types, invalid protocol_version) |

### 7.7 Usage

```bash
# Signature verification only
python tools/verify_receipt.py \
  --manifest manifest.json \
  --signature signature.json \
  --public-key public_key.pem

# With artifact verification
python tools/verify_receipt.py \
  --manifest manifest.json \
  --signature signature.json \
  --public-key public_key.pem \
  --artifacts evidence_pack.zip certificate.pdf audit_events.json
```

### 7.8 Output

```
[VALID] Manifest signature verified.
  receipt_id:   a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
  batch_id:     BATCH-D8917A6A
  root_hash:    fedcba9876543210...
  artifacts:    3/3 verified
  exit code:    0
```

Or:

```
[INVALID] Signature verification FAILED.
  receipt_id:   a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
  reason:       ECDSA signature does not match manifest digest
  exit code:    1
```

---

## 8. Tamper Test Matrix

| # | Test Case | Mutation | Expected | Exit Code |
|---|-----------|----------|----------|-----------|
| T1 | Change `root_hash` | Flip one hex char in `root_hash` | INVALID — signature mismatch | 1 |
| T2 | Change `timestamp` | Alter microsecond digit | INVALID — signature mismatch | 1 |
| T3 | Change `engine_version` | `"8.2.2"` → `"8.2.3"` | INVALID — signature mismatch | 1 |
| T4 | Change `config_hash` | Replace with different SHA-256 | INVALID — signature mismatch | 1 |
| T5 | Change artifact hash | Alter one entry in `artifact_hashes[0].hash` | INVALID — artifact hash mismatch | 2 |
| T6 | Wrong public key | Use a different P-256 key | INVALID — signature mismatch | 1 |
| T7 | Modified signature | Flip one byte in signature | INVALID — signature mismatch | 1 |
| T8 | Remove required field | Delete `batch_id` | INVALID — malformed manifest | 3 |
| T9 | Add extra field | Insert `"extra": "field"` | INVALID — signature mismatch (JCS changes) | 1 |
| T10 | Change `artifact_mode` | `"PRODUCTION_REAL"` → `"DEMO_SIMULATED"` | INVALID — signature mismatch | 1 |
| T11 | Change `tenant_scope` | Alter tenant hash | INVALID — signature mismatch | 1 |
| T12 | Change `metrics.record_count` | `5000` → `5001` | INVALID — signature mismatch | 1 |
| T13 | Reorder JSON keys | Non-JCS key ordering | VALID — JCS normalizes key order | 0 |
| T14 | Add whitespace | Pretty-print JSON | VALID — JCS strips whitespace | 0 |
| T15 | Null signature | Empty or missing signature | INVALID — signature mismatch | 1 |
| T16 | Change artifact `size_bytes` | `1048576` → `1048577` | INVALID — artifact hash mismatch (if artifacts provided) or signature mismatch | 1 or 2 |

T13 and T14 are **positive tests** — they confirm JCS canonicalization works correctly. The verifier must normalize before checking.

---

## 9. Implementation Order

| Phase | Step | Description | Depends On |
|-------|------|-------------|------------|
| 1 | **Schema freeze** | Merge this document. Lock field names, types, ordering. | — |
| 2 | **Manifest generation** | Add `build_attestation_manifest_v1()` to `iavp.py`. Called during batch finalization after hash-chain + anchoring complete. | Phase 1 |
| 3 | **`/verify/{receipt_id}` endpoint** | Add to `server_enterprise_golden.py`. Reads manifest from Firestore, re-verifies signature + anchor + artifacts. | Phase 2 |
| 4 | **Reference verifier** | Create `tools/verify_receipt.py`. Offline, no backend dependency. | Phase 1 |
| 5 | **Tamper tests** | Create `tests/test_attestation_tamper.py`. Run T1–T16 matrix. | Phase 2, Phase 4 |
| 6 | **External receipt alignment** | If an external system emits a receipt, IA records only the agreed manifest fields and preserves its own receipt namespace. | Phase 3 |

Phases 2–4 can partially overlap. Phase 5 requires both the generator and verifier. Phase 6 is integration work after IA-side is complete.

---

## 10. Risks

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | **JCS implementation divergence** | HIGH | The reference verifier MUST use the same JCS library or a byte-identical reimplementation. Test with cross-implementation vectors. |
| R2 | **KMS key rotation** | MEDIUM | Manifests signed with old key versions remain valid — KMS retains old versions. The `key_id` field includes the version number. Verifier must accept any version. |
| R3 | **Anchor bucket deletion** | HIGH | If GCS anchor object is deleted, `anchor_valid` becomes unverifiable. Mitigation: bucket has no-delete IAM policy. Add object versioning as defense-in-depth. |
| R4 | **Manifest storage durability** | MEDIUM | Manifests stored in Firestore. If Firestore data is lost, `/verify` returns 404. Mitigation: manifest hash is embedded in anchor record (cross-reference). |
| R5 | **Clock skew** | LOW | `timestamp` is server-generated UTC. KMS signing also records a timestamp. Drift >1s between `timestamp` and KMS `signed_at_utc` should trigger a warning, not a failure. |
| R6 | **Large batch artifact size** | LOW | Evidence packs for 100K-row batches may be >100MB. `artifact_hashes` verification requires re-downloading artifacts. Verifier should support streaming SHA-256. |
| R7 | **Schema evolution** | MEDIUM | `protocol_version` field enables future versions. v1 verifiers MUST reject manifests with `protocol_version != "ia-attestation/v1"`. New versions get new verifier logic. |
| R8 | **HMAC scope key provisioning** | MEDIUM | `HMAC_SCOPE_KEY` is a new secret required before implementation. Must be provisioned in Secret Manager for both TEST and PROD with different values. Loss does not break existing manifests but prevents consistent `tenant_scope` generation. |

---

## 11. Compatibility with Existing IA Infrastructure

### 11.1 What This Replaces

The attestation manifest v1 **supersedes** the existing 15-field attestation payload (`build_attestation_payload()` in `iavp.py`). The new manifest:

- Adds `anchor_ref` (binding to GCS anchor)
- Adds `artifact_hashes` (independent artifact verification)
- Adds `receipt_id` (unique receipt identifier, previously absent)
- Renames `attestation_version` → `protocol_version` with new format
- Renames `signed_at_utc` → `timestamp`
- Renames `root_hash_sha256` → `root_hash`
- Renames `config_hash_sha256` → `config_hash`
- Renames `dataset_hash_sha256` → `dataset_hash`
- Drops `record_count` from top level (moved into `metrics`)
- Drops `tenant_region` (not attestation-relevant)
- Adds `registry_hash` (company canonical registry integrity)
- Adds `source_blob_hash` (optional — raw uploaded file integrity)
- Replaces `tenant_id_hash_sha256` (raw SHA-256) with `tenant_scope` (HMAC-based pseudonymous token)

### 11.2 What This Preserves

- Same signing algorithm (`EC_SIGN_P256_SHA256`)
- Same KMS key infrastructure
- Same JCS canonicalization function
- Same hash-chain computation
- Same anchor storage (GCS append-only bucket)
- Same evidence blob format

### 11.3 Migration Path

During implementation, both the old 15-field attestation and the new v1 manifest will be generated in parallel. The old attestation remains until IA dashboards and any explicitly supported external consumers have migrated to the new schema. Removal of the old attestation is a Phase 24+ task.

---

## 12. Readiness Verdict

**READY FOR IMPLEMENTATION** with the following prerequisites:

1. **Schema review complete** — This document must be reviewed and approved before any code is written.
2. **No runtime code changes in this phase** — This document is the deliverable.
3. **Existing infrastructure is sufficient** — JCS canonicalization, ECDSA signing, GCS anchoring, and evidence generation are all production-proven.
4. **One new secret required** — `HMAC_SCOPE_KEY` must be provisioned in Secret Manager (TEST + PROD, different values) before manifest generation is implemented. No new KMS keys needed.
5. **Backward compatible** — The old attestation payload continues to be generated alongside the new manifest during migration.

**Blockers**: `HMAC_SCOPE_KEY` secret provisioning (R8). All other building blocks exist in production today.
