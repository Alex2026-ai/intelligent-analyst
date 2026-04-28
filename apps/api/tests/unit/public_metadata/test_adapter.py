"""Tests for the PMC domain adapter."""

from apps.api.src.public_metadata.adapter import adapt_engine_result


def _resolution(**overrides) -> dict:
    defaults = {
        "resolution_id": "r-gold-001",
        "status": "resolved",
        "confidence": 0.95,
        "layer_used": 3,
        "review_reason": None,
        "document_type": "financial",
        "evidence_chain_id": "ec-001",
        # Fields that must NOT pass through:
        "resolution": "APPROVED — James Benson lease at 401 E Jackson St",
        "content": "SSN: 999-55-4444",
        "raw_response": "LLM raw output here",
        "tenant_id": "tampa_re",
    }
    defaults.update(overrides)
    return defaults


class TestAdapterExtraction:
    def test_known_fields_extracted(self):
        r = adapt_engine_result(_resolution(), "tampa_re")
        assert r.valid
        assert r.source["resolution_id"] == "r-gold-001"
        assert r.source["status"] == "resolved"
        assert r.source["confidence"] == 0.95

    def test_unknown_fields_dropped(self):
        r = adapt_engine_result(_resolution(), "tampa_re")
        assert "resolution" not in r.source  # raw text dropped
        assert "content" not in r.source
        assert "raw_response" not in r.source

    def test_layer_mapped_to_stage_summary(self):
        r = adapt_engine_result(_resolution(layer_used=1), "t1")
        assert r.source["stage_summary"] == "Deterministic rule match"

        r2 = adapt_engine_result(_resolution(layer_used=3), "t1")
        assert r2.source["stage_summary"] == "LLM-assisted analysis"

    def test_review_reason_generalized(self):
        r = adapt_engine_result(_resolution(review_reason="low_confidence"), "t1")
        assert "escalation" in r.source["justification_fragment"].lower()

    def test_correlation_id_passthrough(self):
        r = adapt_engine_result(_resolution(), "t1", correlation_id="cmd_abc123")
        assert r.source["correlation_id"] == "cmd_abc123"


class TestAdapterValidation:
    def test_missing_resolution_id_invalid(self):
        r = adapt_engine_result({"status": "resolved"}, "t1")
        assert not r.valid
        assert "resolution_id" in r.error

    def test_missing_status_invalid(self):
        r = adapt_engine_result({"resolution_id": "r1"}, "t1")
        assert not r.valid

    def test_empty_dict_invalid(self):
        r = adapt_engine_result({}, "t1")
        assert not r.valid


class TestAdapterAnchors:
    def test_anchors_from_evidence_records(self):
        records = [
            {"data": {"step": "l1_rule_match", "matched": True}},
            {"data": {"step": "pii_mask", "tokens": 3}},
            {"data": {"step": "routing_decision", "route_to_review": True}},
        ]
        r = adapt_engine_result(_resolution(), "t1", evidence_records=records)
        assert "INV-002" in r.anchors
        assert "INV-005" in r.anchors
        assert "INV-006" in r.anchors

    def test_no_evidence_no_anchors(self):
        r = adapt_engine_result(_resolution(), "t1")
        assert r.anchors == []

    def test_deduplicates_anchors(self):
        records = [
            {"data": {"step": "pii_mask"}},
            {"data": {"step": "pii_mask"}},
        ]
        r = adapt_engine_result(_resolution(), "t1", evidence_records=records)
        assert r.anchors.count("INV-006") == 1
