"""
================================================================================
INTELLIGENT ANALYST - EVIDENCE PACK BUNDLER (Days 17-20)
================================================================================

Assembles cryptographically-sealed evidence packs for compliance export.

A complete evidence pack includes:
- results.csv: All resolution results
- certificate.pdf: Nostrum-Grade forensic certificate
- manifest.json: SHA-256 hashes of all files for integrity verification
- audit_events.json: Full audit trail
- evidence_summary.json: Aggregated evidence metadata

The manifest.json is the cryptographic anchor - verify all file hashes match.

Usage:
    from reporting.bundler import build_evidence_pack

    zip_bytes, manifest = await build_evidence_pack(
        batch_id="BATCH-ABC123",
        tenant_context={"id": "nostrum-energy", "name": "Nostrum Energy"},
        include_raw_evidence=False  # Only for legal hold scenarios
    )

================================================================================
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# PDF engine for certificate generation
from .pdf_engine import build_evidence_certificate


# ============================================================================
# CONSTANTS
# ============================================================================

BUNDLER_VERSION = "1.0.0"
SYSTEM_NAME = "Intelligent Analyst"
SYSTEM_VERSION = "8.2.2"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 of bytes and return hex string."""
    return hashlib.sha256(data).hexdigest()


def _sha256_file(file_bytes: bytes) -> str:
    """Compute SHA-256 of file content."""
    return _sha256_bytes(file_bytes)


def _generate_results_csv(results: List[Dict]) -> str:
    """
    Generate CSV from resolution results.

    Handles both company and person mode results.
    """
    if not results:
        return "original,resolved,match_type,confidence,layer,decision_path\n"

    # Detect mode from first result
    first = results[0]

    # Person mode columns
    if "sanitized_name" in first or "match_type" in first:
        headers = [
            "row_index", "original_name", "resolved", "match_type",
            "match_id", "confidence", "layer", "decision_path"
        ]
        lines = [",".join(headers)]

        for r in results:
            row = [
                _csv_escape(r.get("row_index", "")),
                _csv_escape(r.get("original_name") or r.get("original", "")),
                _csv_escape(r.get("resolved") or r.get("sanitized_name", "")),
                _csv_escape(r.get("match_type")),
                _csv_escape(r.get("match_id")),
                _csv_escape(r.get("confidence", "")),
                _csv_escape(r.get("layer")),
                _csv_escape(r.get("decision_path") or r.get("layer", "")),
            ]
            lines.append(",".join(row))

        return "\n".join(lines)

    # Company mode columns
    headers = [
        "row_index", "original", "resolved", "match_type",
        "confidence", "layer", "decision_path", "reason"
    ]
    lines = [",".join(headers)]

    for r in results:
        row = [
            _csv_escape(r.get("row_index") or r.get("index", "")),
            _csv_escape(r.get("original") or r.get("company_raw", "")),
            _csv_escape(r.get("resolved") or r.get("canonical", "")),
            _csv_escape(r.get("match_type")),
            _csv_escape(r.get("confidence") or r.get("similarity", "")),
            _csv_escape(r.get("layer") or r.get("layer_used", "")),
            _csv_escape(r.get("decision_path")),
            _csv_escape(r.get("reason")),
        ]
        lines.append(",".join(row))

    return "\n".join(lines)


def _csv_escape(value: Any) -> str:
    """Escape value for CSV (handle commas, quotes, newlines)."""
    if value is None:
        return ""
    s = str(value)
    if "," in s or '"' in s or "\n" in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


# ============================================================================
# EVIDENCE PACK BUILDER
# ============================================================================

async def build_evidence_pack(
    batch_id: str,
    tenant_context: Dict[str, Any],
    results: List[Dict],
    audit_events: List[Dict],
    batch_doc: Dict[str, Any],
    verification_data: Optional[Dict[str, Any]] = None,
    evidence_blobs: Optional[List[Dict]] = None,
    include_raw_evidence: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Build a complete evidence pack as a ZIP file.

    Args:
        batch_id: Batch trace ID
        tenant_context: {"id": "...", "name": "Nostrum Energy"}
        results: List of resolution results
        audit_events: List of audit events
        batch_doc: Batch document from Firestore
        verification_data: Verification endpoint response
        evidence_blobs: Optional raw evidence blobs (for legal hold)
        include_raw_evidence: Whether to include full evidence blobs

    Returns:
        Tuple of (zip_bytes, manifest_dict)
    """
    generated_at = datetime.now(timezone.utc)
    files: Dict[str, bytes] = {}
    file_hashes: Dict[str, str] = {}

    company_name = tenant_context.get("name", tenant_context.get("id", "Unknown"))
    tenant_id = tenant_context.get("id", "unknown")

    # ========================================================================
    # 1. RESULTS CSV
    # ========================================================================

    csv_content = _generate_results_csv(results)
    csv_bytes = csv_content.encode("utf-8")
    files["results.csv"] = csv_bytes
    file_hashes["results.csv"] = _sha256_file(csv_bytes)

    # ========================================================================
    # 2. CERTIFICATE PDF
    # ========================================================================

    pdf_bytes, pdf_metadata = build_evidence_certificate(
        batch_id=batch_id,
        tenant_context=tenant_context,
        forensic_data=verification_data or {},
        signature_info=batch_doc.get("signature"),
        batch_stats=batch_doc.get("stats") or batch_doc.get("counts"),
        config_snapshot=batch_doc.get("config_snapshot"),
        events=audit_events,
    )
    files["certificate.pdf"] = pdf_bytes
    file_hashes["certificate.pdf"] = _sha256_file(pdf_bytes)

    # ========================================================================
    # 3. AUDIT EVENTS JSON
    # ========================================================================

    audit_json = json.dumps({
        "batch_id": batch_id,
        "tenant_id": tenant_id,
        "exported_at": generated_at.isoformat(),
        "total_events": len(audit_events),
        "events": audit_events,
    }, indent=2, ensure_ascii=False, default=str)
    audit_bytes = audit_json.encode("utf-8")
    files["audit_events.json"] = audit_bytes
    file_hashes["audit_events.json"] = _sha256_file(audit_bytes)

    # ========================================================================
    # 4. EVIDENCE SUMMARY JSON
    # ========================================================================

    stats = batch_doc.get("stats") or batch_doc.get("counts") or {}

    summary = {
        "batch_id": batch_id,
        "tenant_id": tenant_id,
        "company_name": company_name,
        "exported_at": generated_at.isoformat(),
        "system_version": f"{SYSTEM_NAME} v{SYSTEM_VERSION}",
        "bundler_version": BUNDLER_VERSION,

        # Processing summary
        "processing": {
            "total_records": stats.get("total", len(results)),
            "started_at": batch_doc.get("started_at") or batch_doc.get("timestamp"),
            "finished_at": batch_doc.get("finished_at"),
            "duration_seconds": batch_doc.get("duration_seconds") or stats.get("duration_seconds"),
            "status": batch_doc.get("status", "completed"),
        },

        # Layer breakdown
        "resolution_breakdown": {
            "l0_garbage": stats.get("layer_0_garbage", 0) or stats.get("l0_garbage", 0),
            "l1_exact": stats.get("layer_1_exact", 0) or stats.get("l1_exact", 0),
            "l1_norm": stats.get("layer_1_norm", 0) or stats.get("l1_norm", 0),
            "l2_vector": stats.get("layer_2_vector", 0) or stats.get("l2_vector", 0),
            "l3_llm": stats.get("layer_3_llm", 0) or stats.get("l3_llm", 0),
            "l4_human": stats.get("layer_4_human", 0) or stats.get("l4_human", 0),
        },

        # Energy/ESG metrics
        "energy_metrics": {
            "rating": pdf_metadata.get("energy_rating"),
            "badge": pdf_metadata.get("energy_badge"),
            "efficiency_ratio": pdf_metadata.get("energy_ratio"),
        },

        # Cryptographic verification
        "cryptographic_verification": {
            "signature_verified": pdf_metadata.get("signature_verified", False),
            "certificate_hash": pdf_metadata.get("certificate_hash"),
            "kms_key_id": pdf_metadata.get("kms_key_id"),
            "signature_hash": pdf_metadata.get("signature_hash"),
        },

        # Hash chain (if available)
        "hash_chain": verification_data.get("hash_chain") if verification_data else None,

        # Legal hold status
        "legal_hold": batch_doc.get("legal_hold"),

        # Config at processing time
        "config_snapshot": batch_doc.get("config_snapshot"),
    }

    summary_json = json.dumps(summary, indent=2, ensure_ascii=False, default=str)
    summary_bytes = summary_json.encode("utf-8")
    files["evidence_summary.json"] = summary_bytes
    file_hashes["evidence_summary.json"] = _sha256_file(summary_bytes)

    # ========================================================================
    # 5. RAW EVIDENCE BLOBS (Optional - Legal Hold Only)
    # ========================================================================

    if include_raw_evidence and evidence_blobs:
        evidence_dir = "evidence/"
        for blob in evidence_blobs:
            row_index = blob.get("evidence", {}).get("row_index", 0)
            blob_json = json.dumps(blob, indent=2, ensure_ascii=False, default=str)
            blob_bytes = blob_json.encode("utf-8")
            filename = f"{evidence_dir}row_{row_index:06d}.json"
            files[filename] = blob_bytes
            file_hashes[filename] = _sha256_file(blob_bytes)

    # ========================================================================
    # 6. MANIFEST.JSON (Cryptographic Anchor)
    # ========================================================================

    manifest = {
        "version": BUNDLER_VERSION,
        "batch_id": batch_id,
        "tenant_id": tenant_id,
        "company_name": company_name,
        "generated_at": generated_at.isoformat(),
        "generator": f"{SYSTEM_NAME} v{SYSTEM_VERSION}",

        # File inventory with SHA-256 hashes
        "files": [
            {
                "path": path,
                "sha256": hash_val,
                "size_bytes": len(files[path]),
            }
            for path, hash_val in sorted(file_hashes.items())
        ],

        # Pack-level integrity
        "integrity": {
            "algorithm": "SHA-256",
            "total_files": len(files),
            "total_bytes": sum(len(f) for f in files.values()),
        },

        # Certificate hash (for cross-reference)
        "certificate_hash": pdf_metadata.get("certificate_hash"),

        # Verification instructions
        "verification": {
            "method": "Compare SHA-256 hash of each file against manifest",
            "command": "sha256sum <filename>",
            "api_endpoint": f"/batches/{batch_id}/verify",
        },
    }

    # Compute manifest hash (before adding manifest to files)
    manifest_content = json.dumps(manifest, indent=2, ensure_ascii=False, default=str)
    manifest_bytes = manifest_content.encode("utf-8")
    manifest_hash = _sha256_file(manifest_bytes)

    # Add manifest hash to itself (for verification)
    manifest["integrity"]["manifest_hash"] = manifest_hash

    # Re-serialize with hash included
    manifest_final = json.dumps(manifest, indent=2, ensure_ascii=False, default=str)
    manifest_bytes = manifest_final.encode("utf-8")
    files["manifest.json"] = manifest_bytes

    # ========================================================================
    # 7. BUILD ZIP FILE
    # ========================================================================

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add files in sorted order for reproducibility
        for filename in sorted(files.keys()):
            zf.writestr(filename, files[filename])

    zip_bytes = zip_buffer.getvalue()
    zip_buffer.close()

    return zip_bytes, manifest


# ============================================================================
# SYNC WRAPPER
# ============================================================================

def build_evidence_pack_sync(
    batch_id: str,
    tenant_context: Dict[str, Any],
    results: List[Dict],
    audit_events: List[Dict],
    batch_doc: Dict[str, Any],
    verification_data: Optional[Dict[str, Any]] = None,
    evidence_blobs: Optional[List[Dict]] = None,
    include_raw_evidence: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """Synchronous wrapper for build_evidence_pack."""
    return asyncio.get_event_loop().run_until_complete(
        build_evidence_pack(
            batch_id=batch_id,
            tenant_context=tenant_context,
            results=results,
            audit_events=audit_events,
            batch_doc=batch_doc,
            verification_data=verification_data,
            evidence_blobs=evidence_blobs,
            include_raw_evidence=include_raw_evidence,
        )
    )


# ============================================================================
# VERIFICATION HELPER
# ============================================================================

def verify_evidence_pack(zip_path_or_bytes: Any) -> Dict[str, Any]:
    """
    Verify integrity of an evidence pack.

    Args:
        zip_path_or_bytes: Path to ZIP file or bytes

    Returns:
        {
            "valid": bool,
            "manifest": {...},
            "file_results": [{"path": ..., "expected": ..., "actual": ..., "valid": bool}],
            "errors": [...]
        }
    """
    if isinstance(zip_path_or_bytes, (str, bytes)):
        if isinstance(zip_path_or_bytes, str):
            with open(zip_path_or_bytes, "rb") as f:
                zip_bytes = f.read()
        else:
            zip_bytes = zip_path_or_bytes
    else:
        raise ValueError("Expected file path or bytes")

    results = {
        "valid": True,
        "manifest": None,
        "file_results": [],
        "errors": [],
    }

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            # Read manifest
            if "manifest.json" not in zf.namelist():
                results["valid"] = False
                results["errors"].append("Missing manifest.json")
                return results

            manifest_bytes = zf.read("manifest.json")
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            results["manifest"] = manifest

            # Verify each file
            for file_info in manifest.get("files", []):
                path = file_info["path"]
                expected_hash = file_info["sha256"]

                if path not in zf.namelist():
                    results["file_results"].append({
                        "path": path,
                        "expected": expected_hash,
                        "actual": None,
                        "valid": False,
                        "error": "File missing from archive",
                    })
                    results["valid"] = False
                    continue

                file_bytes = zf.read(path)
                actual_hash = _sha256_file(file_bytes)

                valid = actual_hash == expected_hash
                results["file_results"].append({
                    "path": path,
                    "expected": expected_hash,
                    "actual": actual_hash,
                    "valid": valid,
                })

                if not valid:
                    results["valid"] = False

    except Exception as e:
        results["valid"] = False
        results["errors"].append(str(e))

    return results


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    import asyncio

    # Test data
    test_results = [
        {"row_index": 0, "original": "Microsoft Corp", "resolved": "MICROSOFT CORPORATION", "confidence": 1.0, "layer": "L1_EXACT"},
        {"row_index": 1, "original": "MSFT Inc", "resolved": "MICROSOFT CORPORATION", "confidence": 0.95, "layer": "L2_VECTOR"},
        {"row_index": 2, "original": "Unknown Company", "resolved": None, "confidence": 0.0, "layer": "L4_HUMAN"},
    ]

    test_events = [
        {"event_type": "batch_started", "timestamp": "2026-02-15T10:00:00Z"},
        {"event_type": "batch_completed", "timestamp": "2026-02-15T10:01:00Z"},
    ]

    test_batch = {
        "trace_id": "BATCH-BUNDLER-TEST",
        "tenant_id": "nostrum-energy",
        "stats": {
            "total": 3,
            "layer_1_exact": 1,
            "layer_2_vector": 1,
            "layer_4_human": 1,
        },
        "signature": {
            "signing_key_id": "projects/test/locations/us/keyRings/test/cryptoKeys/test/cryptoKeyVersions/1",
            "evidence_hash_sha256": "abc123",
        },
    }

    test_tenant = {
        "id": "nostrum-energy",
        "name": "Nostrum Energy",
    }

    async def test():
        zip_bytes, manifest = await build_evidence_pack(
            batch_id="BATCH-BUNDLER-TEST",
            tenant_context=test_tenant,
            results=test_results,
            audit_events=test_events,
            batch_doc=test_batch,
        )

        print(f"Evidence Pack Generated:")
        print(f"  ZIP Size: {len(zip_bytes):,} bytes")
        print(f"  Files: {len(manifest['files'])}")
        print(f"  Certificate Hash: {manifest['certificate_hash'][:32]}...")

        # Save and verify
        with open("/tmp/evidence_pack_test.zip", "wb") as f:
            f.write(zip_bytes)
        print(f"  Saved to: /tmp/evidence_pack_test.zip")

        # Verify
        verification = verify_evidence_pack(zip_bytes)
        print(f"\nVerification:")
        print(f"  Valid: {verification['valid']}")
        for fr in verification["file_results"]:
            status = "OK" if fr["valid"] else "FAIL"
            print(f"  [{status}] {fr['path']}")

    asyncio.run(test())
