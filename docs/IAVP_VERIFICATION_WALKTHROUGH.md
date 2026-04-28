# IAVP v1.0 Verification Walkthrough

**Protocol:** IA-VP-1.0
**Evidence Schema:** chunk_v1
**Date:** 2026-02-20

---

## Purpose

This document provides a step-by-step procedure for verifying the
integrity of an IAVP v1.0 batch. Each step is independently
reproducible using standard tools (curl, Python, openssl).

---

## Prerequisites

- Access to the Intelligent Analyst API (`$API_BASE`)
- Valid authentication token (Firebase Bearer token or API key)
- Python 3.8+ with `hashlib` and `json` standard libraries
- A JCS (RFC 8785) implementation (e.g., `python-jcs` package or
  equivalent)

```bash
pip install jcs
```

---

## Step 1: Prepare Input File

Create a CSV file with entity names to resolve:

```csv
company_name
Apple Inc.
Gogle
MSFT
unknown_entity_12345
```

Save as `test_input.csv`.

---

## Step 2: Submit Batch

```bash
TRACE_ID=$(curl -s -X POST "$API_BASE/batch-upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_input.csv" \
  -F "mode=company" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['trace_id'])")

echo "Trace ID: $TRACE_ID"
```

The batch enters the processing pipeline. Poll for completion:

```bash
curl -s "$API_BASE/batches" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for b in data.get('batches', []):
    if b['trace_id'] == '$TRACE_ID':
        print(f\"Status: {b['status']}\")
"
```

Wait until status is `completed`.

---

## Step 3: Retrieve Forensic Summary

```bash
curl -s "$API_BASE/audit/$TRACE_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
summary = data.get('forensic_summary', {})
print(json.dumps(summary, indent=2))
"
```

Key fields to inspect:

```json
{
  "verification": {
    "status": "PASS",
    "protocol_version": "IA-VP-1.0"
  },
  "replay": {
    "determinism": "VERIFIED",
    "runs": 3,
    "variance": 0,
    "replay_root_hash": "<hex>"
  },
  "crypto": {
    "root_hash": "<hex>",
    "hash_chain_method": "SHA256_CHAIN_V1",
    "input_ordering": "STABLE_INPUT_ORDER_V2"
  }
}
```

Record the `root_hash` — this is the value you will independently
recompute.

---

## Step 4: Call the Verify Endpoint

```bash
curl -s "$API_BASE/batches/$TRACE_ID/verify" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
print(json.dumps(json.load(sys.stdin), indent=2))
"
```

Expected response for a valid batch:

```json
{
  "status": "PASS",
  "evidence_schema": "chunk_v1",
  "hash_chain": {
    "verified": true,
    "root_hash_match": true
  },
  "anchor": {
    "verified": true,
    "root_hash_match": true
  },
  "attestation_binding": {
    "verified": true
  },
  "evidence_integrity": {
    "schema_version": "chunk_v1",
    "mode": "BATCH_ATTESTATION",
    "chunk_count": 1,
    "chunks_with_digest": 1,
    "valid": true
  }
}
```

This is the platform's own verification. The following steps show
how to verify independently.

---

## Step 5: Retrieve Evidence Blobs

```bash
curl -s "$API_BASE/audit/$TRACE_ID/evidence" \
  -H "Authorization: Bearer $TOKEN" \
  -o evidence.json
```

Parse the evidence:

```python
import json

with open("evidence.json") as f:
    data = json.load(f)

blobs = data.get("evidence_blobs", data.get("blobs", []))
chunks = [b for b in blobs if b.get("schema_version") == "chunk_v1"]
digest_index = [b for b in blobs if b.get("schema_version") == "chunk_digests_v1"]

print(f"Chunks: {len(chunks)}")
print(f"Digest index entries: {len(digest_index)}")
```

---

## Step 6: Independently Recompute Chunk Digests

For each chunk, compute the SHA-256 digest of its JCS-canonicalized
JSON:

```python
import hashlib
import jcs  # RFC 8785 implementation

def compute_chunk_digest(chunk: dict) -> str:
    """Compute SHA-256 of JCS-canonicalized chunk."""
    canonical_bytes = jcs.canonicalize(chunk)
    return hashlib.sha256(canonical_bytes).hexdigest()

for chunk in sorted(chunks, key=lambda c: c["chunk_index"]):
    computed = compute_chunk_digest(chunk)
    stored = chunk.get("chunk_digest", "")
    match = "MATCH" if computed == stored else "MISMATCH"
    print(f"Chunk {chunk['chunk_index']}: {match}")
    if computed != stored:
        print(f"  Computed: {computed}")
        print(f"  Stored:   {stored}")
```

If any chunk shows MISMATCH, the evidence has been modified after
creation. Verification fails.

---

## Step 7: Independently Recompute Root Hash

Recompute the hash chain from the verified chunk digests:

```python
def compute_root_hash(chunk_digests: list) -> str:
    """
    Compute SHA256_CHAIN_V1 root hash.

    chain[0] = SHA-256(digests[0])
    chain[i] = SHA-256(chain[i-1] || digests[i])
    """
    if not chunk_digests:
        return ""

    # Sort by chunk_index
    ordered = sorted(chunk_digests, key=lambda d: d["chunk_index"])
    digests = [d["digest"] for d in ordered]

    chain = hashlib.sha256(digests[0].encode()).hexdigest()
    for i in range(1, len(digests)):
        combined = chain + digests[i]
        chain = hashlib.sha256(combined.encode()).hexdigest()

    return chain

# Use digest index if available, otherwise use computed digests
if digest_index:
    digest_entries = digest_index[0]["chunk_digests"]
else:
    digest_entries = [
        {"chunk_index": c["chunk_index"], "digest": compute_chunk_digest(c)}
        for c in chunks
    ]

computed_root = compute_root_hash(digest_entries)
print(f"Computed root hash: {computed_root}")
```

Compare with the root hash from the forensic summary (Step 3). If
they match, the hash chain is independently verified.

---

## Step 8: Verify Attestation Signature (Advanced)

The attestation signature binds the root hash to the batch metadata.
To verify independently:

```python
# 1. Retrieve the attestation manifest from the forensic summary
manifest = data.get("forensic_summary", {}).get("attestation", {}).get("manifest", {})

# 2. Canonicalize with JCS
manifest_bytes = jcs.canonicalize(manifest)

# 3. The signature and key ID are in the attestation section
signature_b64 = data["forensic_summary"]["attestation"]["signature"]
key_id = data["forensic_summary"]["attestation"]["key_id"]

# 4. Retrieve the public key from KMS
#    (requires GCP credentials with cloudkms.cryptoKeyVersions.getPublicKey)
#
#    gcloud kms keys versions get-public-key 1 \
#      --key=<key_name> --keyring=<keyring> --location=<location> \
#      --output-file=public_key.pem

# 5. Verify with openssl
#    echo -n '<manifest_bytes>' | openssl dgst -sha256 \
#      -verify public_key.pem -signature <signature_der>
```

Note: Full attestation verification requires access to the KMS
public key. The public key can be retrieved by any party with
`cloudkms.cryptoKeyVersions.getPublicKey` permission. The private
key is never exposed.

---

## Step 9: Verify External Anchor (Advanced)

The anchor is stored in an immutable GCS bucket:

```bash
# Retrieve anchor (requires GCS read access to anchor bucket)
gsutil cat gs://$ANCHOR_BUCKET/$TRACE_ID.json | python3 -c "
import sys, json
anchor = json.load(sys.stdin)
print(f\"Anchor root_hash: {anchor['root_hash']}\")
print(f\"Anchor batch_id:  {anchor['batch_id']}\")
"
```

Compare the anchor's `root_hash` with your independently computed
root hash from Step 7. If they match, the anchor confirms the batch
output has not been modified since anchoring.

---

## What Each Step Proves

| Step | What It Proves |
|------|---------------|
| Step 6 — Chunk digest recomputation | No chunk artifact has been modified after creation |
| Step 7 — Root hash recomputation | No chunk has been added, removed, or reordered |
| Step 8 — Attestation verification | The platform signed this specific root hash with a specific key at a specific time |
| Step 9 — Anchor verification | An independent external record confirms the root hash, beyond the platform's control |
| Step 3 — Replay (from forensic summary) | Three independent runs produced the same root hash — the process is deterministic |

Together, these steps establish:

1. **The output has not been tampered with** (hash chain + anchor)
2. **The platform committed to this output** (attestation signature)
3. **The process is repeatable** (replay verification)

These are the three properties that `verification.status = PASS`
attests to.

---

## Troubleshooting

### Chunk digest mismatch
The chunk artifact was modified after evidence generation. This
could indicate data corruption, unauthorized modification, or a
deserialization issue. Compare the raw JSON byte-for-byte.

### Root hash mismatch
A chunk was added, removed, or reordered. Verify that your chunk
ordering matches `chunk_index` ascending. Verify that you are using
hex-encoded string concatenation (not raw byte concatenation).

### Attestation verification failure
The manifest was modified after signing, or the wrong public key is
being used. Confirm the `key_id` in the attestation matches the key
you retrieved.

### Anchor missing
The anchor may not have been written (anchoring disabled) or the
bucket may require specific GCP credentials. Check the forensic
summary for `anchoring.enabled` status.

---

## Document Control

| Version | Date | Author | Status |
|---------|------|--------|--------|
| 1.0 | 2026-02-20 | Engineering | Published |
