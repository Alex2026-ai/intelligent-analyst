"""Tests for Public Metadata Controller — comprehensive coverage.

Covers: policy denial, tenant blocking, anchor filtering, identifier removal,
name generalization, raw evidence blocking, manual approval flow, emission,
storage separation, integrity metadata, fail-closed on malformed input.
"""

import pytest

from apps.api.src.public_metadata.models import (
    Decision,
    ManualApprovalStatus,
    PolicyMode,
    PublicMetadataPolicy,
    SampleStatus,
)
from apps.api.src.public_metadata.policy_evaluator import evaluate, filter_anchors
from apps.api.src.public_metadata.emitter import emit_sample
from apps.api.src.public_metadata.redaction import (
    classify_field,
    redact_source,
    scrub_text,
    FieldAction,
)
from apps.api.src.public_metadata.store import PublicMetadataStore, SAMPLES_PATH, DECISIONS_PATH
from apps.api.src.storage.firestore.client import InMemoryFirestore


def _policy(**overrides) -> PublicMetadataPolicy:
    defaults = {
        "policy_id": "test-policy",
        "version": "1.0",
        "mode": PolicyMode.CURATED_HYBRID,
        "allow_real_sanitized_samples": True,
        "require_manual_approval": True,
        "public_anchor_allowlist": ["INV-002", "INV-005", "INV-006"],
        "blocked_tenants": [],
    }
    defaults.update(overrides)
    return PublicMetadataPolicy(**defaults)


def _source(**overrides) -> dict:
    defaults = {
        "resolution_id": "r-test-001",
        "status": "resolved",
        "confidence": 0.95,
        "layer_used": 3,
        "tenant_id": "tampa_re",
        "name": "James Benson",
        "document_type": "financial",
        "content": "SSN: 999-55-4444, 401 E Jackson St, Tampa FL",
    }
    defaults.update(overrides)
    return defaults


class TestPolicyDenials:
    @pytest.mark.asyncio
    async def test_deny_when_policy_missing(self):
        decision = evaluate(_source(), "t1", policy=None)
        assert decision.decision == Decision.DENY
        assert "No PublicMetadataPolicy" in decision.reasons[0]

    @pytest.mark.asyncio
    async def test_deny_when_tenant_blocked(self):
        policy = _policy(blocked_tenants=["blocked_tenant"])
        decision = evaluate(_source(), "blocked_tenant", policy)
        assert decision.decision == Decision.DENY
        assert "blocked" in decision.reasons[0].lower()

    @pytest.mark.asyncio
    async def test_deny_when_mode_deny_all(self):
        policy = _policy(mode=PolicyMode.DENY_ALL)
        decision = evaluate(_source(), "t1", policy)
        assert decision.decision == Decision.DENY

    @pytest.mark.asyncio
    async def test_deny_on_empty_source(self):
        decision = evaluate({}, "t1", _policy())
        assert decision.decision == Decision.DENY
        assert "Missing" in decision.reasons[0]


class TestAnchorFiltering:
    @pytest.mark.asyncio
    async def test_unknown_anchor_dropped(self):
        decision = evaluate(
            _source(), "t1", _policy(),
            source_anchors=["INV-002", "INV-999", "PHASE-8"],
        )
        assert "Unknown anchors dropped" in decision.reasons[0]

    @pytest.mark.asyncio
    async def test_only_allowed_anchors_pass(self):
        allowed = filter_anchors(
            ["INV-002", "INV-005", "INV-006", "INV-010", "PHASE-8"],
            frozenset({"INV-002", "INV-005", "INV-006"}),
        )
        assert set(allowed) == {"INV-002", "INV-005", "INV-006"}

    @pytest.mark.asyncio
    async def test_empty_anchors(self):
        assert filter_anchors([], frozenset({"INV-002"})) == []


class TestRedaction:
    @pytest.mark.asyncio
    async def test_direct_identifiers_dropped(self):
        source = _source()
        _, dropped, _ = redact_source(source)
        assert "tenant_id" in dropped
        assert "content" in dropped
        assert "resolution_id" in dropped
        assert "name" not in dropped  # name is generalized, not dropped

    @pytest.mark.asyncio
    async def test_names_generalized(self):
        source = _source()
        sanitized, _, generalized = redact_source(source)
        assert "name" in generalized
        assert sanitized.get("name") == "an individual"

    @pytest.mark.asyncio
    async def test_raw_evidence_never_in_output(self):
        source = _source(content="Secret raw evidence text")
        sanitized, dropped, _ = redact_source(source)
        assert "content" in dropped
        assert "Secret" not in str(sanitized)

    @pytest.mark.asyncio
    async def test_unknown_fields_dropped(self):
        action = classify_field("some_random_internal_field")
        assert action == FieldAction.DROP

    @pytest.mark.asyncio
    async def test_scrub_text_removes_names(self):
        text = "James Benson applied for a lease. Maria Garcia was the reviewer."
        result = scrub_text(text)
        assert "James Benson" not in result
        assert "Maria Garcia" not in result
        assert "the individual" in result

    @pytest.mark.asyncio
    async def test_scrub_text_removes_ssn(self):
        assert "999-55-4444" not in scrub_text("SSN: 999-55-4444")

    @pytest.mark.asyncio
    async def test_scrub_text_removes_uuid(self):
        result = scrub_text("ID: 550e8400-e29b-41d4-a716-446655440000")
        assert "550e8400" not in result


class TestManualApproval:
    @pytest.mark.asyncio
    async def test_requires_manual_approval_when_policy_says_so(self):
        policy = _policy(require_manual_approval=True)
        decision = evaluate(_source(), "t1", policy)
        assert decision.decision == Decision.REQUIRES_MANUAL_APPROVAL
        assert decision.manual_approval_required is True
        assert decision.manual_approval_status == ManualApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_emission_blocked_until_approved(self):
        policy = _policy(require_manual_approval=True)
        decision = evaluate(_source(), "t1", policy)
        sample = emit_sample(_source(), "t1", policy, decision, ["INV-002"])
        assert sample is None  # Blocked — approval still PENDING

    @pytest.mark.asyncio
    async def test_approved_flow_emits(self):
        policy = _policy(require_manual_approval=True)
        decision = evaluate(_source(), "t1", policy)
        # Simulate approval
        decision.manual_approval_status = ManualApprovalStatus.APPROVED
        sample = emit_sample(_source(), "t1", policy, decision, ["INV-002", "INV-005"])
        assert sample is not None
        assert sample.headline
        assert sample.summary
        assert sample.integrity_hash

    @pytest.mark.asyncio
    async def test_denied_decision_blocks_emission(self):
        decision = evaluate(_source(), "t1", policy=None)  # DENY
        sample = emit_sample(_source(), "t1", None, decision, [])
        assert sample is None


class TestPublicSampleContent:
    @pytest.mark.asyncio
    async def test_sample_contains_only_allowed_anchors(self):
        policy = _policy(require_manual_approval=False, allow_real_sanitized_samples=True)
        decision = evaluate(_source(), "t1", policy, ["INV-002", "INV-005", "INV-010"])
        sample = emit_sample(
            _source(), "t1", policy, decision,
            ["INV-002", "INV-005", "INV-010"],
        )
        assert sample is not None
        assert "INV-010" not in sample.public_spec_anchors
        assert "INV-002" in sample.public_spec_anchors
        assert "INV-005" in sample.public_spec_anchors

    @pytest.mark.asyncio
    async def test_sample_has_no_tenant_id(self):
        policy = _policy(require_manual_approval=False, allow_real_sanitized_samples=True)
        decision = evaluate(_source(), "t1", policy)
        sample = emit_sample(_source(), "t1", policy, decision, ["INV-002"])
        assert sample is not None
        sample_dict = sample.model_dump()
        assert "tenant_id" not in sample_dict
        assert "tampa_re" not in str(sample_dict)

    @pytest.mark.asyncio
    async def test_sample_has_no_names(self):
        policy = _policy(require_manual_approval=False, allow_real_sanitized_samples=True)
        decision = evaluate(_source(), "t1", policy)
        sample = emit_sample(_source(), "t1", policy, decision, ["INV-006"])
        assert sample is not None
        sample_str = str(sample.model_dump())
        assert "James Benson" not in sample_str
        assert "Maria Garcia" not in sample_str

    @pytest.mark.asyncio
    async def test_integrity_hash_present(self):
        policy = _policy(require_manual_approval=False, allow_real_sanitized_samples=True)
        decision = evaluate(_source(), "t1", policy)
        sample = emit_sample(_source(), "t1", policy, decision, ["INV-002"])
        assert sample is not None
        assert len(sample.integrity_hash) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_workflow_stages_are_generic(self):
        policy = _policy(require_manual_approval=False, allow_real_sanitized_samples=True)
        decision = evaluate(_source(), "t1", policy)
        sample = emit_sample(_source(), "t1", policy, decision, ["INV-002"])
        assert sample is not None
        for stage in sample.workflow_stages:
            assert "tenant" not in stage.lower()
            assert "james" not in stage.lower()


class TestStorageSeparation:
    @pytest.mark.asyncio
    async def test_public_samples_stored_outside_tenant_path(self):
        assert "tenants/" not in SAMPLES_PATH
        assert "tenants/" not in SAMPLES_PATH

    @pytest.mark.asyncio
    async def test_decisions_stored_outside_tenant_path(self):
        assert "tenants/" not in DECISIONS_PATH
        assert "tenants/" not in DECISIONS_PATH

    @pytest.mark.asyncio
    async def test_save_and_retrieve_sample(self):
        db = InMemoryFirestore()
        store = PublicMetadataStore(db)
        policy = _policy(require_manual_approval=False, allow_real_sanitized_samples=True)
        decision = evaluate(_source(), "t1", policy)
        sample = emit_sample(_source(), "t1", policy, decision, ["INV-002"])
        assert sample is not None
        await store.save_sample(sample)
        retrieved = await store.get_sample(sample.public_sample_id)
        assert retrieved is not None
        assert retrieved["headline"] == sample.headline

    @pytest.mark.asyncio
    async def test_approval_updates_decision(self):
        db = InMemoryFirestore()
        store = PublicMetadataStore(db)
        policy = _policy(require_manual_approval=True)
        decision = evaluate(_source(), "t1", policy)
        await store.save_decision(decision)
        result = await store.approve_decision(decision.decision_id)
        assert result is True
        updated = await store.get_decision(decision.decision_id)
        assert updated["manual_approval_status"] == ManualApprovalStatus.APPROVED.value


class TestFailClosed:
    @pytest.mark.asyncio
    async def test_malformed_source_denied(self):
        decision = evaluate({"garbage": True}, "t1", _policy())
        assert decision.decision == Decision.DENY

    @pytest.mark.asyncio
    async def test_none_source_denied(self):
        decision = evaluate({}, "t1", _policy())
        assert decision.decision == Decision.DENY

    @pytest.mark.asyncio
    async def test_decision_has_provenance(self):
        decision = evaluate(_source(), "t1", _policy())
        assert decision.decision_id
        assert decision.created_at
        assert decision.integrity_hash
        assert decision.policy_version == "1.0"
