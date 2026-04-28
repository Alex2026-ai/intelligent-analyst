# External Verification Demo

Step-by-step walkthrough for an external party to independently verify an IA receipt.

## Prerequisites

- Python 3.8+
- `curl` (or any HTTP client)
- Access to the IA backend URL (or the pre-built verification pack)

## Option A: Using the Pre-Built Verification Pack

The verification pack at `verification_pack/public/v1.0/` contains sample artifacts ready for offline verification.

```bash
cd verification_pack/public/v1.0/

# Verify checksums (optional, for tamper detection)
shasum -a 256 -c SHA256SUMS

# Run offline verification
python3 verify_example.py receipt.json proof.json root.json
```

**Expected output:**

```
VALID
```

## Option B: Fetching Fresh Artifacts from the API

### Step 1: Obtain a receipt_id

After a batch is processed, the response includes a `receipt.id` field:

```bash
# Example: check a batch status
curl -s https://<backend>/batches?limit=1 \
  -H "X-API-Key: <api_key>" \
  -H "X-Tenant-Id: <tenant_id>"
```

Extract `receipt.id` from the batch detail.

### Step 2: Verify the receipt

```bash
RECEIPT_ID="<receipt_id>"
BACKEND="https://<backend>"

curl -s "$BACKEND/verify/receipt/$RECEIPT_ID" > receipt.json
```

Confirm `status: "valid"` and `artifact_integrity: true`.

### Step 3: Obtain the Merkle inclusion proof

```bash
curl -s "$BACKEND/transparency/proof/$RECEIPT_ID" > proof.json
```

Confirm `found: true`.

### Step 4: Obtain the published tree root

```bash
curl -s "$BACKEND/transparency/latest-root" > root.json
```

### Step 5: Run offline verification

```bash
python3 verify_example.py receipt.json proof.json root.json
```

### Step 6: Confirm verdict

The script outputs either:
- `VALID` -- the receipt is cryptographically anchored in the transparency log
- `INVALID` -- one or more verification checks failed (see report for details)

## What the Verification Proves

1. **Receipt integrity** -- the receipt manifest contains all required attestation fields
2. **Merkle inclusion** -- the receipt's leaf hash is included in the transparency tree via a valid RFC 6962 proof path
3. **Root consistency** -- the computed tree root matches the published root, confirming the receipt was logged before the root was signed

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `INVALID: Merkle inclusion` | Proof does not match root | Root may have advanced; re-fetch `root.json` |
| `INVALID: Root consistency` | Proof root differs from published | The tree has grown since proof was generated; re-fetch both `proof.json` and `root.json` |
| `INVALID: Receipt structure` | Missing fields | Ensure receipt was obtained from `/verify/receipt/` or batch detail |
| `Error loading files` | File not found | Check file paths |
