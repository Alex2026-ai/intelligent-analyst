"""Tests for export artifact generator."""

import pytest
from apps.worker.src.export.generator import generate_export


SAMPLE_RESOLUTION = {
    "resolution_id": "r1",
    "status": "resolved",
    "confidence": 0.95,
    "layer_used": 2,
    "resolution": "Matched to canonical entity",
}

SAMPLE_NODES = [
    {"node_id": "n1", "node_type": "source_artifact", "sequence": 1, "timestamp": "2026-03-21T10:00:00Z"},
    {"node_id": "n2", "node_type": "retrieval_result", "sequence": 2, "timestamp": "2026-03-21T10:00:01Z"},
]


class TestGenerator:
    def test_json_format(self):
        result = generate_export(SAMPLE_RESOLUTION, SAMPLE_NODES, "json")
        assert isinstance(result, bytes)
        import json
        data = json.loads(result)
        assert data["resolution"]["resolution_id"] == "r1"
        assert data["evidence_chain"]["node_count"] == 2

    def test_csv_format(self):
        result = generate_export(SAMPLE_RESOLUTION, SAMPLE_NODES, "csv")
        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "resolution_id" in text
        assert "r1" in text

    def test_pdf_format(self):
        result = generate_export(SAMPLE_RESOLUTION, SAMPLE_NODES, "pdf")
        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "RESOLUTION REPORT" in text
        assert "r1" in text

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported"):
            generate_export(SAMPLE_RESOLUTION, SAMPLE_NODES, "docx")

    def test_json_without_evidence(self):
        result = generate_export(SAMPLE_RESOLUTION, SAMPLE_NODES, "json", include_evidence=False)
        import json
        data = json.loads(result)
        assert "excluded" in data["evidence_chain"]["note"]

    def test_csv_without_evidence(self):
        result = generate_export(SAMPLE_RESOLUTION, [], "csv", include_evidence=False)
        text = result.decode("utf-8")
        assert "resolution_id" in text

    def test_pdf_without_evidence(self):
        result = generate_export(SAMPLE_RESOLUTION, [], "pdf", include_evidence=False)
        text = result.decode("utf-8")
        assert "EVIDENCE CHAIN" not in text
