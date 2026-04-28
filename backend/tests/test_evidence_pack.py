"""
Regression tests for evidence pack export (bundler.py).

Covers:
- CSV generation with None fields (root cause of HTTP 500)
- Evidence pack ZIP assembly
- Required file presence in ZIP
- Missing/optional metadata handling
"""

import asyncio
import io
import json
import zipfile
from typing import Dict, List, Tuple

import pytest

# Import the modules under test
from app.reporting.bundler import (
    _csv_escape,
    _generate_results_csv,
    build_evidence_pack,
    verify_evidence_pack,
)


# ============================================================================
# FIXTURES
# ============================================================================

def _make_company_results(count: int = 5, include_none_fields: bool = False) -> List[Dict]:
    """Build synthetic company-mode results."""
    results = []
    layers = [
        ("L1_EXACT", "APPLE INC.", 1.0, "Exact match"),
        ("L2_VECTOR", "MICROSOFT CORPORATION", 0.92, "Vector similarity"),
        ("L3_LLM", "ALPHABET INC.", 0.85, "LLM resolved"),
        ("L4_HUMAN", None, 0.0, None),
        ("L0_GARBAGE", None, 0.0, "Too short"),
    ]
    for i in range(count):
        layer_name, resolved, confidence, reason = layers[i % len(layers)]
        r = {
            "row_index": i,
            "original": f"Test Company {i}",
            "resolved": resolved,
            "confidence": confidence,
            "layer": layer_name,
            "reason": reason,
        }
        if include_none_fields:
            r["match_type"] = None
            r["decision_path"] = None
        results.append(r)
    return results


def _make_person_results(count: int = 5, include_none_fields: bool = False) -> List[Dict]:
    """Build synthetic person-mode results."""
    results = []
    entries = [
        ("FUZZY_MATCH", "SDN-12345", "John Smith", 0.95, "L2_PERSON"),
        ("POSSIBLE_MATCH", "SDN-67890", "Jane Doe", 0.91, "L2_PERSON"),
        ("NO_MATCH", None, None, 0.0, "L4_HUMAN"),
        ("NO_MATCH", None, None, 0.0, "L4_HUMAN"),
        ("EXACT_MATCH", "SDN-11111", "Kim Jong Un", 1.0, "L1_PERSON"),
    ]
    for i in range(count):
        match_type, match_id, resolved, confidence, layer = entries[i % len(entries)]
        r = {
            "row_index": i,
            "original_name": f"Test Person {i}",
            "sanitized_name": f"test person {i}",
            "match_type": match_type if not include_none_fields else None,
            "match_id": match_id,
            "resolved": resolved,
            "confidence": confidence,
            "layer": layer,
        }
        if include_none_fields:
            r["decision_path"] = None
        results.append(r)
    return results


def _make_batch_doc(trace_id: str = "BATCH-TEST-PACK") -> Dict:
    """Build a minimal batch document."""
    return {
        "trace_id": trace_id,
        "tenant_id": "test-tenant",
        "status": "completed",
        "total": 5,
        "started_at": "2026-02-20T10:00:00Z",
        "finished_at": "2026-02-20T10:00:05Z",
        "duration_seconds": 5.0,
        "stats": {
            "total": 5,
            "layer_1_exact": 2,
            "layer_2_vector": 1,
            "layer_3_llm": 1,
            "layer_4_human": 1,
        },
        "signature": {
            "signing_key_id": "projects/test/locations/us/keyRings/test/cryptoKeys/test/cryptoKeyVersions/1",
            "evidence_hash_sha256": "abc123def456",
        },
    }


def _make_tenant_context() -> Dict:
    return {"id": "test-tenant", "name": "Test Tenant"}


def _make_audit_events() -> List[Dict]:
    return [
        {"event_type": "batch_started", "timestamp": "2026-02-20T10:00:00Z"},
        {"event_type": "batch_completed", "timestamp": "2026-02-20T10:00:05Z"},
    ]


async def _build_pack(**overrides) -> Tuple[bytes, Dict]:
    """Helper to build an evidence pack with defaults."""
    kwargs = {
        "batch_id": "BATCH-TEST-PACK",
        "tenant_context": _make_tenant_context(),
        "results": _make_company_results(),
        "audit_events": _make_audit_events(),
        "batch_doc": _make_batch_doc(),
    }
    kwargs.update(overrides)
    return await build_evidence_pack(**kwargs)


# ============================================================================
# TEST: _csv_escape
# ============================================================================

class TestCsvEscape:
    def test_none_returns_empty(self):
        assert _csv_escape(None) == ""

    def test_string_passthrough(self):
        assert _csv_escape("hello") == "hello"

    def test_commas_quoted(self):
        assert _csv_escape("a,b") == '"a,b"'

    def test_quotes_escaped(self):
        assert _csv_escape('say "hi"') == '"say ""hi"""'

    def test_newlines_quoted(self):
        assert _csv_escape("line1\nline2") == '"line1\nline2"'

    def test_number_to_string(self):
        assert _csv_escape(42) == "42"
        assert _csv_escape(0.95) == "0.95"


# ============================================================================
# TEST: _generate_results_csv — None field regression
# ============================================================================

class TestGenerateResultsCsvNoneFields:
    """Regression tests for the HTTP 500 caused by None in join()."""

    def test_company_mode_with_none_resolved(self):
        """L4_HUMAN records have resolved=None. Must not crash."""
        results = [
            {
                "row_index": 0,
                "original": "Unknown Corp",
                "resolved": None,
                "confidence": 0.0,
                "layer": "L4_HUMAN",
                "reason": None,
                "match_type": None,
                "decision_path": None,
            }
        ]
        csv = _generate_results_csv(results)
        assert "Unknown Corp" in csv
        assert csv.count("\n") >= 1  # header + 1 row

    def test_person_mode_with_none_match_id(self):
        """Person NO_MATCH records have match_id=None. This was the original crash."""
        results = [
            {
                "row_index": 0,
                "original_name": "John Nobody",
                "sanitized_name": "john nobody",
                "match_type": "NO_MATCH",
                "match_id": None,
                "resolved": None,
                "confidence": 0.0,
                "layer": "L4_HUMAN",
                "decision_path": None,
            }
        ]
        csv = _generate_results_csv(results)
        assert "John Nobody" in csv

    def test_person_mode_sequence_item_4_regression(self):
        """
        Exact reproduction of the HTTP 500:
        sequence item 4: expected str instance, NoneType found

        Item 4 in person mode row is match_id. When match_id is None
        and the key exists in the dict, .get("match_id", "") returns
        None (not ""), causing join() to fail.
        """
        results = _make_person_results(count=10, include_none_fields=True)
        # This must not raise TypeError
        csv = _generate_results_csv(results)
        lines = csv.strip().split("\n")
        assert len(lines) == 11  # 1 header + 10 data rows

    def test_company_mode_all_none_optional_fields(self):
        """Every optional field is explicitly None."""
        results = _make_company_results(count=5, include_none_fields=True)
        csv = _generate_results_csv(results)
        lines = csv.strip().split("\n")
        assert len(lines) == 6  # 1 header + 5 rows

    def test_empty_results(self):
        """Empty results should return header only."""
        csv = _generate_results_csv([])
        assert "original" in csv

    def test_all_fields_none_except_required(self):
        """Absolute worst case — every non-key field is None."""
        results = [
            {
                "row_index": None,
                "original": None,
                "resolved": None,
                "confidence": None,
                "layer": None,
                "reason": None,
                "match_type": None,
                "decision_path": None,
            }
        ]
        csv = _generate_results_csv(results)
        assert csv.count("\n") >= 1


# ============================================================================
# TEST: Evidence pack ZIP assembly
# ============================================================================

class TestEvidencePackAssembly:
    """Tests for full evidence pack build."""

    def test_pack_returns_zip_and_manifest(self):
        zip_bytes, manifest = asyncio.get_event_loop().run_until_complete(
            _build_pack()
        )
        assert isinstance(zip_bytes, bytes)
        assert len(zip_bytes) > 0
        assert isinstance(manifest, dict)
        assert "files" in manifest
        assert "integrity" in manifest

    def test_zip_contains_required_files(self):
        """Evidence pack MUST contain these four files."""
        zip_bytes, _ = asyncio.get_event_loop().run_until_complete(
            _build_pack()
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = set(zf.namelist())

        assert "results.csv" in names
        assert "certificate.pdf" in names
        assert "manifest.json" in names
        assert "audit_events.json" in names
        assert "evidence_summary.json" in names

    def test_manifest_json_parseable(self):
        zip_bytes, _ = asyncio.get_event_loop().run_until_complete(
            _build_pack()
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            manifest = json.loads(zf.read("manifest.json"))

        assert manifest["batch_id"] == "BATCH-TEST-PACK"
        assert len(manifest["files"]) >= 4

    def test_results_csv_in_zip_has_rows(self):
        zip_bytes, _ = asyncio.get_event_loop().run_until_complete(
            _build_pack()
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_content = zf.read("results.csv").decode("utf-8")

        lines = csv_content.strip().split("\n")
        assert len(lines) == 6  # header + 5 results

    def test_audit_events_json_in_zip(self):
        zip_bytes, _ = asyncio.get_event_loop().run_until_complete(
            _build_pack()
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            audit = json.loads(zf.read("audit_events.json"))

        assert audit["batch_id"] == "BATCH-TEST-PACK"
        assert audit["total_events"] == 2

    def test_verify_evidence_pack_passes(self):
        """Built pack should verify successfully."""
        zip_bytes, _ = asyncio.get_event_loop().run_until_complete(
            _build_pack()
        )
        result = verify_evidence_pack(zip_bytes)
        assert result["valid"] is True
        assert len(result["errors"]) == 0


# ============================================================================
# TEST: Missing metadata robustness
# ============================================================================

class TestMissingMetadataRobustness:
    """Pack builder must not crash when optional metadata is absent."""

    def test_no_signature_info(self):
        """Batch doc with no signature field."""
        batch = _make_batch_doc()
        batch.pop("signature", None)
        zip_bytes, manifest = asyncio.get_event_loop().run_until_complete(
            _build_pack(batch_doc=batch)
        )
        assert len(zip_bytes) > 0

    def test_no_stats(self):
        """Batch doc with no stats field."""
        batch = _make_batch_doc()
        batch.pop("stats", None)
        zip_bytes, manifest = asyncio.get_event_loop().run_until_complete(
            _build_pack(batch_doc=batch)
        )
        assert len(zip_bytes) > 0

    def test_no_verification_data(self):
        """No verification_data passed."""
        zip_bytes, manifest = asyncio.get_event_loop().run_until_complete(
            _build_pack(verification_data=None)
        )
        assert len(zip_bytes) > 0

    def test_empty_audit_events(self):
        """Empty audit events list."""
        zip_bytes, manifest = asyncio.get_event_loop().run_until_complete(
            _build_pack(audit_events=[])
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            audit = json.loads(zf.read("audit_events.json"))
        assert audit["total_events"] == 0

    def test_person_mode_with_none_fields_builds_pack(self):
        """Full pack build with person-mode results containing None fields."""
        results = _make_person_results(count=10, include_none_fields=True)
        zip_bytes, manifest = asyncio.get_event_loop().run_until_complete(
            _build_pack(results=results)
        )
        assert len(zip_bytes) > 0
        result = verify_evidence_pack(zip_bytes)
        assert result["valid"] is True

    def test_minimal_batch_doc(self):
        """Batch doc with absolute minimum fields."""
        batch = {
            "trace_id": "BATCH-MINIMAL",
            "tenant_id": "t",
            "status": "completed",
        }
        zip_bytes, manifest = asyncio.get_event_loop().run_until_complete(
            _build_pack(
                batch_id="BATCH-MINIMAL",
                batch_doc=batch,
                results=_make_company_results(count=1),
            )
        )
        assert len(zip_bytes) > 0
