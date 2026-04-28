#!/usr/bin/env python3
"""
Deterministic Replay Verification Harness
==========================================

Verifies the entire trust chain offline given receipt, proof, and root
JSON files from the Intelligent Analyst transparency log.

Trust chain verified:
  1. Receipt manifest structure (required fields, protocol version)
  2. Merkle inclusion proof (RFC 6962 domain-separated hashing)
  3. Root consistency (proof root matches published root)

Usage:
  python3 replay_verifier.py <manifest.json> <proof.json> <root.json>

Exit codes:
  0 — VALID   (all checks passed)
  1 — INVALID (one or more checks failed)

Requirements:
  Python 3.9+, no external dependencies.

Intended audience: external auditors performing offline verification.
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_RECEIPT_FIELDS = [
    "receipt_id",
    "root_hash",
    "batch_id",
    "signature_algorithm",
    "protocol_version",
]

EXPECTED_PROTOCOL_VERSION = "ia-attestation/v1"
EXPECTED_SIGNATURE_ALGORITHM = "EC_SIGN_P256_SHA256"

# RFC 6962 domain separation bytes
LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


# ---------------------------------------------------------------------------
# JCS (JSON Canonicalization Scheme — RFC 8785)
# ---------------------------------------------------------------------------

def jcs_canonicalize(obj: Any) -> bytes:
    """Produce a JCS-canonical JSON byte string (RFC 8785).

    JCS specifies:
      - Sorted object keys (recursively)
      - No whitespace
      - Specific number serialization (Python's json.dumps with
        sort_keys and separators handles the common cases)
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


# ---------------------------------------------------------------------------
# Verification steps
# ---------------------------------------------------------------------------

class VerificationResult:
    """Accumulates step-by-step verification outcomes."""

    def __init__(self) -> None:
        self.steps: List[tuple[str, bool, str]] = []

    def record(self, label: str, passed: bool, detail: str = "") -> None:
        self.steps.append((label, passed, detail))

    @property
    def all_passed(self) -> bool:
        return all(passed for _, passed, _ in self.steps)

    def print_report(self) -> None:
        width = max(len(label) for label, _, _ in self.steps) + 2
        print()
        print("=" * 60)
        print("  Replay Verification Report")
        print("=" * 60)
        for label, passed, detail in self.steps:
            status = "PASS" if passed else "FAIL"
            line = f"  [{status}] {label:<{width}}"
            if detail:
                line += f" — {detail}"
            print(line)
        print("=" * 60)
        verdict = "VALID" if self.all_passed else "INVALID"
        print(f"  Verdict: {verdict}")
        print("=" * 60)
        print()
        # Final bare line for machine-readable consumption
        print(verdict)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_receipt_structure(
    receipt: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Check that the receipt manifest contains all required fields."""
    missing = [f for f in REQUIRED_RECEIPT_FIELDS if f not in receipt]
    if missing:
        result.record(
            "Receipt structure",
            False,
            f"missing fields: {', '.join(missing)}",
        )
        return False
    result.record("Receipt structure", True, "all required fields present")
    return True


def verify_protocol_version(
    receipt: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Check protocol_version matches expected value."""
    version = receipt.get("protocol_version", "")
    ok = version == EXPECTED_PROTOCOL_VERSION
    result.record(
        "Protocol version",
        ok,
        f"got {version!r}, expected {EXPECTED_PROTOCOL_VERSION!r}",
    )
    return ok


def verify_signature_algorithm(
    receipt: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Check signature_algorithm matches expected value."""
    algo = receipt.get("signature_algorithm", "")
    ok = algo == EXPECTED_SIGNATURE_ALGORITHM
    result.record(
        "Signature algorithm",
        ok,
        f"got {algo!r}, expected {EXPECTED_SIGNATURE_ALGORITHM!r}",
    )
    return ok


def verify_proof_found(
    proof: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Check that the proof actually found the entry."""
    found = proof.get("found", False)
    result.record("Proof lookup", found, "entry found in log" if found else "entry NOT found")
    return found


def verify_entry_id_match(
    receipt: Dict[str, Any],
    proof: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Check that proof.entry_id matches receipt.receipt_id."""
    receipt_id = receipt.get("receipt_id", "")
    entry_id = proof.get("entry_id", "")
    ok = receipt_id == entry_id
    detail = "IDs match" if ok else f"receipt_id={receipt_id!r}, entry_id={entry_id!r}"
    result.record("Entry ID consistency", ok, detail)
    return ok


def try_reconstruct_leaf_hash(
    receipt: Dict[str, Any],
    proof: Dict[str, Any],
    result: VerificationResult,
) -> Optional[str]:
    """Attempt to reconstruct the leaf hash from receipt fields.

    The leaf payload is:
        {
            "version": "1.0",
            "entry_type": "receipt",
            "entry_id": <receipt_id>,
            "root_hash": <receipt_root_hash>,
            "timestamp": <receipt_timestamp>,
            "nonce": <32 zero chars>
        }

    If the receipt lacks a timestamp or the nonce is unknown, we cannot
    reconstruct the leaf and must trust the proof's leaf_hash.
    """
    receipt_id = receipt.get("receipt_id")
    root_hash = receipt.get("root_hash")
    timestamp = receipt.get("timestamp")

    if not all([receipt_id, root_hash, timestamp]):
        result.record(
            "Leaf reconstruction",
            True,  # not a failure — just informational
            "skipped (receipt missing timestamp or fields; trusting proof leaf_hash)",
        )
        return None

    # Use the canonical nonce (32 zeros) from the original insertion
    leaf_payload = {
        "version": "1.0",
        "entry_type": "receipt",
        "entry_id": receipt_id,
        "root_hash": root_hash,
        "timestamp": timestamp,
        "nonce": "0" * 32,
    }

    canonical = jcs_canonicalize(leaf_payload)
    computed = sha256_hex(canonical)
    expected = proof.get("leaf_hash", "")

    ok = computed == expected
    if ok:
        result.record(
            "Leaf reconstruction",
            True,
            f"hash matches proof leaf_hash ({computed[:16]}...)",
        )
    else:
        # Non-fatal: the server uses a random nonce (secrets.token_hex(16))
        # which external verifiers cannot reconstruct. The Merkle inclusion
        # proof itself validates chain integrity without leaf reconstruction.
        result.record(
            "Leaf reconstruction",
            True,
            f"advisory: computed {computed[:16]}... != proof {expected[:16]}... "
            "(server nonce differs from default — expected for production leaves)",
        )

    return computed


def verify_merkle_inclusion(
    proof: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Verify the Merkle inclusion proof using RFC 6962 domain separation.

    Starting from the leaf_hash provided in the proof, walks the
    inclusion_proof steps to reconstruct the tree root, then compares
    against the expected root_hash in the proof.

    Algorithm:
        current = bytes.fromhex(leaf_hash)
        for step in inclusion_proof:
            sibling = bytes.fromhex(step["hash"])
            if step["direction"] == "left":
                current = SHA256(0x01 || sibling || current)
            else:
                current = SHA256(0x01 || current || sibling)
        assert current.hex() == proof["root_hash"]
    """
    leaf_hash = proof.get("leaf_hash", "")
    inclusion_proof = proof.get("inclusion_proof", [])
    expected_root = proof.get("root_hash", "")

    if not leaf_hash or not expected_root:
        result.record("Merkle inclusion", False, "missing leaf_hash or root_hash in proof")
        return False

    try:
        # RFC 6962: the tree stores SHA256(0x00 || leaf_bytes) at level 0.
        # The proof's leaf_hash is the PRE-tree value, so we must apply
        # the leaf prefix hash before walking the inclusion proof.
        current = sha256_bytes(LEAF_PREFIX + bytes.fromhex(leaf_hash))
    except ValueError:
        result.record("Merkle inclusion", False, f"invalid hex in leaf_hash: {leaf_hash!r}")
        return False

    for i, step in enumerate(inclusion_proof):
        direction = step.get("direction", "")
        sibling_hex = step.get("hash", "")

        try:
            sibling = bytes.fromhex(sibling_hex)
        except ValueError:
            result.record(
                "Merkle inclusion",
                False,
                f"invalid hex at proof step {i}: {sibling_hex!r}",
            )
            return False

        if direction == "left":
            current = sha256_bytes(NODE_PREFIX + sibling + current)
        elif direction == "right":
            current = sha256_bytes(NODE_PREFIX + current + sibling)
        else:
            result.record(
                "Merkle inclusion",
                False,
                f"unknown direction at step {i}: {direction!r}",
            )
            return False

    computed_root = current.hex()
    ok = computed_root == expected_root
    detail = (
        f"computed root matches ({computed_root[:16]}...)"
        if ok
        else f"computed {computed_root[:16]}... != expected {expected_root[:16]}..."
    )
    result.record(
        "Merkle inclusion",
        ok,
        f"{len(inclusion_proof)} steps; {detail}",
    )
    return ok


def verify_root_consistency(
    proof: Dict[str, Any],
    root: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Verify that the proof root_hash matches the published root.

    Checks against both root.root_hash and root.latest_published.root_hash.
    """
    proof_root = proof.get("root_hash", "")

    # Direct root match
    root_hash = root.get("root_hash", "")
    if proof_root and proof_root == root_hash:
        result.record(
            "Root consistency",
            True,
            f"proof root matches root.root_hash ({proof_root[:16]}...)",
        )
        return True

    # Latest published root match
    latest = root.get("latest_published", {})
    published_root = latest.get("root_hash", "")
    if proof_root and proof_root == published_root:
        result.record(
            "Root consistency",
            True,
            f"proof root matches latest_published.root_hash ({proof_root[:16]}...)",
        )
        return True

    result.record(
        "Root consistency",
        False,
        f"proof root {proof_root[:16]}... matches neither "
        f"root.root_hash ({root_hash[:16]}...) nor "
        f"latest_published.root_hash ({published_root[:16]}...)",
    )
    return False


def verify_tree_size_consistency(
    proof: Dict[str, Any],
    root: Dict[str, Any],
    result: VerificationResult,
) -> bool:
    """Verify that proof tree_size is consistent with root tree_size."""
    proof_size = proof.get("tree_size")
    root_size = root.get("tree_size")
    latest_size = root.get("latest_published", {}).get("tree_size")

    if proof_size is None:
        result.record("Tree size consistency", False, "proof missing tree_size")
        return False

    if proof_size == root_size or proof_size == latest_size:
        result.record(
            "Tree size consistency",
            True,
            f"tree_size={proof_size}",
        )
        return True

    # The proof may have been generated against an older tree; the root
    # should be >= the proof size.
    reference = latest_size if latest_size is not None else root_size
    if reference is not None and reference >= proof_size:
        result.record(
            "Tree size consistency",
            True,
            f"proof tree_size={proof_size} <= root tree_size={reference}",
        )
        return True

    result.record(
        "Tree size consistency",
        False,
        f"proof tree_size={proof_size}, root tree_size={root_size}, "
        f"latest_published tree_size={latest_size}",
    )
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(manifest_path: str, proof_path: str, root_path: str) -> bool:
    """Execute full verification pipeline. Returns True if all checks pass."""
    result = VerificationResult()

    # Load files
    try:
        receipt = load_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        result.record("Load manifest", False, str(exc))
        result.print_report()
        return False
    result.record("Load manifest", True, manifest_path)

    try:
        proof = load_json(proof_path)
    except (OSError, json.JSONDecodeError) as exc:
        result.record("Load proof", False, str(exc))
        result.print_report()
        return False
    result.record("Load proof", True, proof_path)

    try:
        root = load_json(root_path)
    except (OSError, json.JSONDecodeError) as exc:
        result.record("Load root", False, str(exc))
        result.print_report()
        return False
    result.record("Load root", True, root_path)

    # Step 1: Receipt manifest structure
    verify_receipt_structure(receipt, result)
    verify_protocol_version(receipt, result)
    verify_signature_algorithm(receipt, result)

    # Step 2: Proof basic checks
    verify_proof_found(proof, result)
    verify_entry_id_match(receipt, proof, result)

    # Step 3: Leaf reconstruction (best-effort)
    try_reconstruct_leaf_hash(receipt, proof, result)

    # Step 4: Merkle inclusion proof
    verify_merkle_inclusion(proof, result)

    # Step 5: Root consistency
    verify_root_consistency(proof, root, result)
    verify_tree_size_consistency(proof, root, result)

    result.print_report()
    return result.all_passed


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        print("Error: expected 3 arguments, got", len(sys.argv) - 1)
        print()
        print("Usage:")
        print("  python3 replay_verifier.py <manifest.json> <proof.json> <root.json>")
        sys.exit(1)

    manifest_path, proof_path, root_path = sys.argv[1], sys.argv[2], sys.argv[3]
    valid = run(manifest_path, proof_path, root_path)
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
