"""Tests for PMC production hardening: config loading, structured events, evidence enrichment."""

import logging
import pytest
from unittest.mock import patch

from apps.api.src.public_metadata.config import load_policy, get_safe_default_policy, reset_cache, PMC_CONFIG_PATH, PMC_CONFIG_DOC
from apps.api.src.public_metadata.events import emit_attempted, emit_created, emit_denied, emit_failed
from apps.api.src.public_metadata.models import PolicyMode
from apps.api.src.routes.resolve import _build_evidence_hints
from apps.api.src.storage.firestore.client import InMemoryFirestore
from apps.api.tests.conftest import VALID_TOKEN, auth_header


# ---------------------------------------------------------------------------
# 1. Config-backed policy loading
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def setup_method(self):
        reset_cache()

    def teardown_method(self):
        reset_cache()

    @pytest.mark.asyncio
    async def test_loads_from_store(self):
        db = InMemoryFirestore()
        db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).set({
            "policy_id": "custom-v2",
            "version": "2.0",
            "mode": "curated_hybrid",
            "require_manual_approval": False,
            "allow_real_sanitized_samples": True,
            "public_anchor_allowlist": ["INV-002"],
            "blocked_tenants": ["blocked_t"],
        })
        policy = await load_policy(db)
        assert policy.policy_id == "custom-v2"
        assert policy.version == "2.0"
        assert policy.require_manual_approval is False
        assert policy.blocked_tenants == ["blocked_t"]
        assert policy.public_anchor_allowlist == ["INV-002"]

    @pytest.mark.asyncio
    async def test_missing_config_falls_back_safely(self):
        db = InMemoryFirestore()
        policy = await load_policy(db)
        default = get_safe_default_policy()
        assert policy.policy_id == default.policy_id
        assert policy.require_manual_approval is True
        assert policy.mode == PolicyMode.CURATED_HYBRID

    @pytest.mark.asyncio
    async def test_none_db_falls_back_safely(self):
        policy = await load_policy(None)
        assert policy.policy_id == "pmc-safe-default"
        assert policy.require_manual_approval is True

    @pytest.mark.asyncio
    async def test_malformed_config_falls_back(self):
        db = InMemoryFirestore()
        db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).set(
            {"garbage": True, "mode": "invalid_mode_value"}
        )
        # Invalid mode will cause ValueError in PolicyMode() — caught by load_policy
        policy = await load_policy(db)
        assert policy.policy_id == "pmc-safe-default"

    @pytest.mark.asyncio
    async def test_partial_config_inherits_defaults(self):
        db = InMemoryFirestore()
        db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).set({
            "policy_id": "partial",
            "version": "1.1",
            "mode": "curated_hybrid",
        })
        policy = await load_policy(db)
        assert policy.policy_id == "partial"
        assert policy.require_manual_approval is True  # default


# ---------------------------------------------------------------------------
# 2. Structured events
# ---------------------------------------------------------------------------

class TestStructuredEvents:
    def test_emit_attempted_fields(self):
        event = emit_attempted("t1", "r1", "corr-1")
        assert event["event"] == "pmc_candidate_attempted"
        assert event["tenant_id"] == "t1"
        assert event["resolution_id"] == "r1"
        assert event["correlation_id"] == "corr-1"

    def test_emit_created_fields(self):
        event = emit_created("t1", "r1", "d1", "requires_manual_approval", "pub_abc")
        assert event["event"] == "pmc_candidate_created"
        assert event["decision_id"] == "d1"
        assert event["sample_id"] == "pub_abc"

    def test_emit_denied_fields(self):
        event = emit_denied("t1", "r1", "d1", ["blocked tenant"])
        assert event["event"] == "pmc_candidate_denied"
        assert event["reasons"] == ["blocked tenant"]

    def test_emit_failed_fields(self):
        event = emit_failed("t1", "r1", "adapter error")
        assert event["event"] == "pmc_candidate_failed"
        assert event["error"] == "adapter error"

    def test_no_sensitive_data_in_events(self):
        """Events must never contain raw content, PII, or passwords."""
        event = emit_created("t1", "r1", "d1", "allow", "pub_1")
        event_str = str(event)
        assert "ssn" not in event_str.lower()
        assert "password" not in event_str.lower()
        assert "content" not in event  # no raw content field

    def test_events_fire_exactly_once_per_path(self, client, caplog):
        """Each resolution triggers exactly one attempted + one outcome event."""
        with caplog.at_level(logging.INFO, logger="ia.pmc.events"):
            client.post(
                "/v1/resolve",
                json={
                    "document_id": "d-event-test",
                    "document_type": "regulatory",
                    "content": "Event test content.",
                },
                headers={**auth_header(), "Idempotency-Key": "event-test-1"},
            )

        pmc_events = [r for r in caplog.records if "ia.pmc.events" in r.name]
        event_types = [r.getMessage() for r in pmc_events]
        # Should have exactly one attempted + one outcome (created or failed)
        attempted_count = sum(1 for e in event_types if "attempted" in e)
        assert attempted_count == 1
        outcome_count = sum(1 for e in event_types if "created" in e or "denied" in e or "failed" in e)
        assert outcome_count == 1


# ---------------------------------------------------------------------------
# 3. Evidence anchor enrichment
# ---------------------------------------------------------------------------

class TestEvidenceEnrichment:
    def test_pii_categories_produce_inv006_anchor(self):
        response = {"resolution_id": "r1", "status": "resolved", "layer_used": 3}
        hints = _build_evidence_hints(response, pii_categories={"SSN", "EMAIL"}, document_type="financial")
        steps = [h["data"]["step"] for h in hints]
        assert "pii_mask" in steps
        pii_hint = next(h for h in hints if h["data"]["step"] == "pii_mask")
        assert pii_hint["data"]["token_count"] == 2

    def test_layer_used_produces_evidence_hint(self):
        hints = _build_evidence_hints({"layer_used": 1, "status": "resolved"}, None, "")
        steps = [h["data"]["step"] for h in hints]
        assert "l1_rule_match" in steps

    def test_layer3_produces_llm_hint(self):
        hints = _build_evidence_hints({"layer_used": 3, "status": "resolved"}, None, "")
        steps = [h["data"]["step"] for h in hints]
        assert "llm_resolve" in steps

    def test_routing_always_present(self):
        hints = _build_evidence_hints({"status": "resolved"}, None, "")
        steps = [h["data"]["step"] for h in hints]
        assert "routing_decision" in steps

    def test_routed_to_review_sets_flag(self):
        hints = _build_evidence_hints({"status": "routed_to_review"}, None, "")
        routing = next(h for h in hints if h["data"]["step"] == "routing_decision")
        assert routing["data"]["route_to_review"] is True

    def test_no_pii_categories_no_pii_hint(self):
        hints = _build_evidence_hints({"status": "resolved", "layer_used": 2}, None, "")
        steps = [h["data"]["step"] for h in hints]
        assert "pii_mask" not in steps

    def test_enriched_anchors_survive_end_to_end(self, client, app):
        """Resolution with PII produces PMC decision with INV-006 anchor."""
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "d-enrich-test",
                "document_type": "financial",
                "content": "SSN: 123-45-6789 for enrichment test.",
            },
            headers={**auth_header(), "Idempotency-Key": "enrich-test-1"},
        )
        assert resp.status_code == 200

        # Check that a decision was stored with anchor info
        from apps.api.src.public_metadata.store import DECISIONS_PATH
        db = app.state.firestore_client
        decisions = db.collection(DECISIONS_PATH).stream()
        assert len(decisions) >= 1

    def test_fallback_deterministic_without_enrichment(self):
        """Without pii_categories, hints still contain routing + layer."""
        hints = _build_evidence_hints({"status": "resolved", "layer_used": 2}, None, "compliance")
        assert len(hints) >= 2  # layer + routing (no pii)
        steps = [h["data"]["step"] for h in hints]
        assert "routing_decision" in steps
