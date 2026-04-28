# Transparency Public API

Public endpoints for verifying IA batch attestations and transparency log entries.

## Endpoints

### GET /verify/receipt/{receipt_id}

Verify a receipt bundle's cryptographic integrity.

**Request:**
```bash
curl -s https://<backend>/verify/receipt/<receipt_id>
```

**Response (200):**
```json
{
  "receipt_id": "602d92e5-24ca-334b-d7bb-85c313d5df0a",
  "status": "valid",
  "verification_timestamp": "2026-03-14T20:59:59.725681Z",
  "checks": {
    "signature_valid": true,
    "anchor_valid": true,
    "artifact_integrity": true,
    "replay_protection": true
  },
  "failure_reasons": [],
  "_links": {
    "manifest": "gs://ia-test-receipts-us-central1/receipts/.../manifest.json"
  }
}
```

**Security headers:**
- `Cache-Control: no-store, no-cache, must-revalidate`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`

**Error responses:**
- `404` -- receipt not found
- `429` -- rate limit exceeded

---

### GET /transparency/proof/{entry_id}

Retrieve a Merkle inclusion proof for a transparency log entry.

**Request:**
```bash
curl -s https://<backend>/transparency/proof/<receipt_id>
```

**Response (200):**
```json
{
  "found": true,
  "entry_id": "602d92e5-24ca-334b-d7bb-85c313d5df0a",
  "leaf_index": 56,
  "leaf_hash": "0f2fe80da51086487325f457aff5c663...",
  "tree_size": 58,
  "inclusion_proof": [
    {"hash": "e560d8ba3c5a27d7...", "direction": "right"},
    {"hash": "33576bd0be6e2183...", "direction": "left"},
    {"hash": "018bc96a1f5c1fa5...", "direction": "left"},
    {"hash": "ff065187e9dd007e...", "direction": "left"}
  ],
  "root_hash": "7e3956ea8abd75ed6dfd49e7f9815ef1...",
  "root_timestamp": "2026-03-14T20:59:06.222403Z"
}
```

**Fields:**
- `leaf_hash` -- SHA-256 of the JCS-canonicalized leaf payload (pre-tree value)
- `inclusion_proof` -- path from leaf to root; `direction` indicates where the sibling sits
- `root_hash` -- tree root at the time the proof was generated

---

### GET /transparency/latest-root

Get the current tree root and latest published root metadata.

**Request:**
```bash
curl -s https://<backend>/transparency/latest-root
```

**Response (200):**
```json
{
  "tree_size": 58,
  "root_hash": "7e3956ea8abd75ed6dfd49e7f9815ef1...",
  "latest_published": {
    "tree_size": 57,
    "root_hash": "f2a5fbe8790efd5f...",
    "signature": "<base64-encoded-signature>",
    "timestamp": "2026-03-14T20:59:06.222403Z"
  }
}
```

---

## Offline Verification Flow

```
1. Obtain receipt    -->  GET /verify/receipt/{receipt_id}
                          (or use a receipt.json manifest)

2. Obtain proof      -->  GET /transparency/proof/{receipt_id}

3. Obtain root       -->  GET /transparency/latest-root

4. Verify offline    -->  python3 verify_example.py receipt.json proof.json root.json

5. Confirm verdict   -->  VALID
```

### Merkle Proof Verification Algorithm (RFC 6962)

The transparency log uses RFC 6962 domain-separated hashing:

1. **Leaf hashing**: `H_leaf(x) = SHA256(0x00 || x)`
2. **Node hashing**: `H_node(l, r) = SHA256(0x01 || l || r)`

To verify an inclusion proof:

```python
import hashlib

def verify(leaf_hash_hex, inclusion_proof, expected_root_hex):
    # Apply leaf prefix (tree stores H_leaf(raw_leaf) at level 0)
    current = hashlib.sha256(b"\x00" + bytes.fromhex(leaf_hash_hex)).digest()

    for step in inclusion_proof:
        sibling = bytes.fromhex(step["hash"])
        if step["direction"] == "left":
            current = hashlib.sha256(b"\x01" + sibling + current).digest()
        else:
            current = hashlib.sha256(b"\x01" + current + sibling).digest()

    return current.hex() == expected_root_hex
```

The `leaf_hash` in the proof response is the **pre-tree value** (before `H_leaf` is applied). The verifier must apply `H_leaf` before walking the proof path.
