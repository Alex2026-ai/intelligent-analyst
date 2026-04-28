#!/usr/bin/env python3
"""
================================================================================
INTELLIGENT ANALYST - INDEPENDENT VERIFICATION CLI
================================================================================

Verifies evidence blob integrity independently of the IA backend.

Usage:
    ia-verify --trace <trace_id> --file evidence.json
    ia-verify --file evidence.json --pubkey pubkey.pem

Verifications:
1. Signature verification (ECDSA P-256 SHA-256)
2. Evidence hash verification
3. Hash chain verification (if chain file provided)
4. Anchor verification (if anchor file provided)

Exit codes:
    0 = PASS (all verifications succeeded)
    1 = FAIL (one or more verifications failed)
    2 = ERROR (invalid arguments or missing dependencies)

================================================================================
"""

import argparse
import json
import hashlib
import base64
import sys
from typing import Dict, Any, Optional, Tuple

# Try to import cryptography for signature verification
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    print("WARNING: cryptography not installed. Signature verification disabled.", file=sys.stderr)


def canonicalize_json(obj: Any) -> bytes:
    """
    Produce canonical JSON bytes matching the server implementation.
    """
    def _sort_recursive(item):
        if isinstance(item, dict):
            return {k: _sort_recursive(v) for k, v in sorted(item.items())}
        elif isinstance(item, list):
            return [_sort_recursive(v) for v in item]
        elif isinstance(item, float):
            if item == int(item):
                return int(item)
            return round(item, 10)
        return item

    sorted_obj = _sort_recursive(obj)
    return json.dumps(sorted_obj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes, return hex string."""
    return hashlib.sha256(data).hexdigest()


def verify_evidence_hash(evidence_blob: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify evidence_hash_sha256 matches computed hash.

    Returns: (passed, message)
    """
    evidence_core = evidence_blob.get("evidence", {})
    signature_block = evidence_blob.get("signature", {})

    stored_hash = signature_block.get("evidence_hash_sha256")
    if not stored_hash:
        return False, "FAIL: evidence_hash_sha256 not found"

    # Compute hash of evidence core
    canonical = canonicalize_json(evidence_core)
    computed_hash = sha256_bytes(canonical)

    if computed_hash == stored_hash:
        return True, f"PASS: evidence_hash verified ({computed_hash[:16]}...)"
    else:
        return False, f"FAIL: hash mismatch (stored={stored_hash[:16]}..., computed={computed_hash[:16]}...)"


def verify_signature(
    evidence_blob: Dict[str, Any],
    public_key_pem: str
) -> Tuple[bool, str]:
    """
    Verify ECDSA signature using public key.

    Returns: (passed, message)
    """
    if not HAS_CRYPTO:
        return False, "SKIP: cryptography library not available"

    evidence_core = evidence_blob.get("evidence", {})
    signature_block = evidence_blob.get("signature", {})

    signature_b64 = signature_block.get("signature")
    if not signature_b64:
        return False, "FAIL: signature not found"

    try:
        # Decode signature
        signature_bytes = base64.b64decode(signature_b64)

        # Load public key
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode('utf-8'),
            backend=default_backend()
        )

        # Compute digest of evidence core
        canonical = canonicalize_json(evidence_core)
        digest = hashlib.sha256(canonical).digest()

        # Verify signature
        public_key.verify(
            signature_bytes,
            digest,
            ec.ECDSA(hashes.Prehashed(hashes.SHA256()))
        )

        return True, "PASS: signature verified"

    except InvalidSignature:
        return False, "FAIL: invalid signature"
    except Exception as e:
        return False, f"FAIL: verification error - {str(e)}"


def verify_hash_chain(
    events: list,
    chain_entries: list,
    expected_root: str
) -> Tuple[bool, str]:
    """
    Verify hash chain integrity.

    Returns: (passed, message)
    """
    GENESIS_HASH = "0" * 64

    if len(events) != len(chain_entries):
        return False, f"FAIL: chain length mismatch (events={len(events)}, chain={len(chain_entries)})"

    if not events:
        if expected_root == GENESIS_HASH:
            return True, "PASS: empty chain verified"
        return False, "FAIL: empty chain but root != genesis"

    prev_hash = GENESIS_HASH

    for i, (event, entry) in enumerate(zip(events, chain_entries)):
        # Verify prev_hash link
        if entry.get("prev_hash") != prev_hash:
            return False, f"FAIL: prev_hash link broken at index {i}"

        # Normalize event for hashing (must match server implementation)
        normalized = {
            "original": event.get("original", ""),
            "resolved": event.get("resolved"),
            "layer": event.get("layer", ""),
            "confidence": round(event.get("confidence", 0.0), 6),
            "entity_type": event.get("entity_type", ""),
            "decision_path": event.get("decision_path", ""),
        }

        canonical = canonicalize_json(normalized)
        combined = f"{prev_hash}:{canonical.decode('utf-8')}".encode('utf-8')
        computed_hash = hashlib.sha256(combined).hexdigest()

        stored_hash = entry.get("event_hash")
        if computed_hash != stored_hash:
            return False, f"FAIL: event_hash mismatch at index {i}"

        prev_hash = computed_hash

    # Check root hash
    if prev_hash != expected_root:
        return False, f"FAIL: root hash mismatch (computed={prev_hash[:16]}..., expected={expected_root[:16]}...)"

    return True, f"PASS: hash chain verified ({len(events)} events, root={expected_root[:16]}...)"


def verify_anchor(
    anchor_record: Dict[str, Any],
    computed_root: str
) -> Tuple[bool, str]:
    """
    Verify anchor record matches computed root hash.

    Returns: (passed, message)
    """
    stored_hash = anchor_record.get("batch_root_hash")
    if not stored_hash:
        return False, "FAIL: anchor batch_root_hash not found"

    if stored_hash == computed_root:
        return True, f"PASS: anchor verified (root={stored_hash[:16]}...)"
    else:
        return False, f"FAIL: anchor root mismatch (stored={stored_hash[:16]}..., computed={computed_root[:16]}...)"


def load_json_file(filepath: str) -> Optional[Dict[str, Any]]:
    """Load JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load {filepath}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Verify Intelligent Analyst evidence blob integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    ia-verify --file evidence.json --pubkey pubkey.pem
    ia-verify --file evidence.json --pubkey pubkey.pem --chain chain.json --anchor anchor.json
        """
    )
    parser.add_argument("--file", required=True, help="Evidence blob JSON file")
    parser.add_argument("--pubkey", help="Public key PEM file for signature verification")
    parser.add_argument("--chain", help="Hash chain JSON file for chain verification")
    parser.add_argument("--events", help="Events JSON file (results) for chain verification")
    parser.add_argument("--anchor", help="Anchor record JSON file for anchor verification")
    parser.add_argument("--root", help="Expected root hash (for chain/anchor verification)")
    parser.add_argument("--quiet", action="store_true", help="Only output PASS/FAIL")

    args = parser.parse_args()

    # Load evidence blob
    evidence_blob = load_json_file(args.file)
    if not evidence_blob:
        print("ERROR: Failed to load evidence file", file=sys.stderr)
        sys.exit(2)

    results = []
    all_passed = True

    # 1. Verify evidence hash
    hash_passed, hash_msg = verify_evidence_hash(evidence_blob)
    results.append(("Evidence Hash", hash_passed, hash_msg))
    if not hash_passed:
        all_passed = False

    # 2. Verify signature (if pubkey provided)
    if args.pubkey:
        try:
            with open(args.pubkey, 'r') as f:
                pubkey_pem = f.read()
            sig_passed, sig_msg = verify_signature(evidence_blob, pubkey_pem)
            results.append(("Signature", sig_passed, sig_msg))
            if not sig_passed:
                all_passed = False
        except Exception as e:
            results.append(("Signature", False, f"FAIL: could not load pubkey - {e}"))
            all_passed = False
    else:
        results.append(("Signature", None, "SKIP: no pubkey provided"))

    # 3. Verify hash chain (if chain and events provided)
    if args.chain and args.events:
        chain_data = load_json_file(args.chain)
        events_data = load_json_file(args.events)
        if chain_data and events_data:
            root = args.root or chain_data.get("batch_root_hash", "")
            chain_entries = chain_data.get("chain_entries", chain_data if isinstance(chain_data, list) else [])
            events = events_data if isinstance(events_data, list) else events_data.get("events", [])
            chain_passed, chain_msg = verify_hash_chain(events, chain_entries, root)
            results.append(("Hash Chain", chain_passed, chain_msg))
            if not chain_passed:
                all_passed = False
        else:
            results.append(("Hash Chain", False, "FAIL: could not load chain/events"))
            all_passed = False
    else:
        results.append(("Hash Chain", None, "SKIP: no chain/events provided"))

    # 4. Verify anchor (if provided)
    if args.anchor:
        anchor_data = load_json_file(args.anchor)
        if anchor_data:
            # Need computed root for anchor verification
            computed_root = args.root
            if not computed_root and args.chain:
                chain_data = load_json_file(args.chain)
                if chain_data:
                    computed_root = chain_data.get("batch_root_hash", "")
            if computed_root:
                anchor_passed, anchor_msg = verify_anchor(anchor_data, computed_root)
                results.append(("Anchor", anchor_passed, anchor_msg))
                if not anchor_passed:
                    all_passed = False
            else:
                results.append(("Anchor", False, "FAIL: no root hash for anchor verification"))
                all_passed = False
        else:
            results.append(("Anchor", False, "FAIL: could not load anchor"))
            all_passed = False
    else:
        results.append(("Anchor", None, "SKIP: no anchor provided"))

    # Output results
    if not args.quiet:
        print("=" * 60)
        print("INTELLIGENT ANALYST - VERIFICATION RESULTS")
        print("=" * 60)
        print(f"Evidence File: {args.file}")
        print()

    for name, passed, msg in results:
        if args.quiet:
            if passed is not None:
                status = "PASS" if passed else "FAIL"
                print(f"{name}: {status}")
        else:
            print(f"[{name}] {msg}")

    if not args.quiet:
        print()
        print("=" * 60)

    if all_passed:
        print("OVERALL: PASS")
        sys.exit(0)
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
