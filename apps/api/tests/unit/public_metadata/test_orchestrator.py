import pytest
"""Tests for the PMC orchestrator — end-to-end candidate creation."""

from apps.api.src.public_metadata.models import (
    Decision,
    ManualApprovalStatus,
    PolicyMode,
    PublicMetadataPolicy,
)
from apps.api.src.public_metadata.orchestrator import create_public_sample_candidate_from_resolution
from apps.api.src.public_metadata.store import PublicMetadataStore
from apps.api.src.storage.firestore.client import InMemoryFirestore


def _policy(**overrides) -> PublicMetadataPolicy:
    defaults = {
        "policy_id": "test-v1",
        "version": "1.0",
        "mode": PolicyMode.CURATED_HYBRID,
        "allow_real_sanitized_samples": True,
        "require_manual_approval": True,
        "public_anchor_allowlist": ["INV-002", "INV-005", "INV-006"],
        "blocked_tenants": [],
    }
    defaults.update(overrides)
    return PublicMetadataPolicy(**defaults)


def _resolution(**overrides) -> dict:
    defaults = {
        "resolution_id": "r-gold-001",
        "status": "resolved",
        "confidence": 0.95,
        "layer_used": 3,
        "document_type": "financial",
        "evidence_chain_id": "ec-001",
    }
    defaults.update(overrides)
    return defaults


def _evidence_records() -> list[dict]:
    return [
        {"data": {"step": "l1_rule_match"}},
        {"data": {"step": "pii_mask"}},
    ]


def _store() -> PublicMetadataStore:
    return PublicMetadataStore(InMemoryFirestore())


class TestSuccessfulCandidate:
    @pytest.mark.asyncio
    async def test_creates_candidate_from_valid_resolution(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution=_resolution(),
            tenant_id="tampa_re",
            policy=_policy(),
            store=store,
            evidence_records=_evidence_records(),
        )
        assert result.success
        assert result.decision is not None
        assert result.decision.decision == Decision.REQUIRES_MANUAL_APPROVAL

    @pytest.mark.asyncio
    async def test_tenant_in_decision_not_in_sample(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution=_resolution(),
            tenant_id="tampa_re",
            policy=_policy(),
            store=store,
        )
        assert result.decision is not None
        assert result.decision.tenant_id == "tampa_re"
        # Sample not emitted yet (pending approval), but if it were:
        # sample should never contain tenant_id
        if result.sample:
            assert "tenant_id" not in result.sample.model_dump()

    @pytest.mark.asyncio
    async def test_decision_persisted(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution=_resolution(),
            tenant_id="t1",
            policy=_policy(),
            store=store,
        )
        stored = await store.get_decision(result.decision.decision_id)
        assert stored is not None
        assert stored["tenant_id"] == "t1"


class TestDeniedPolicy:
    @pytest.mark.asyncio
    async def test_deny_all_produces_no_sample(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution=_resolution(),
            tenant_id="t1",
            policy=_policy(mode=PolicyMode.DENY_ALL),
            store=store,
        )
        assert result.success
        assert result.decision.decision == Decision.DENY
        assert result.sample is None

    @pytest.mark.asyncio
    async def test_blocked_tenant_produces_no_sample(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution=_resolution(),
            tenant_id="blocked_t",
            policy=_policy(blocked_tenants=["blocked_t"]),
            store=store,
        )
        assert result.decision.decision == Decision.DENY
        assert result.sample is None


class TestMalformedInput:
    @pytest.mark.asyncio
    async def test_missing_resolution_id_fails_closed(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution={"status": "resolved"},
            tenant_id="t1",
            policy=_policy(),
            store=store,
        )
        assert not result.success
        assert "Adapter failed" in result.error

    @pytest.mark.asyncio
    async def test_empty_resolution_fails_closed(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution={},
            tenant_id="t1",
            policy=_policy(),
            store=store,
        )
        assert not result.success


class TestManualApproval:
    @pytest.mark.asyncio
    async def test_pending_until_approved(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution=_resolution(),
            tenant_id="t1",
            policy=_policy(require_manual_approval=True),
            store=store,
        )
        assert result.decision.decision == Decision.REQUIRES_MANUAL_APPROVAL
        assert result.decision.manual_approval_status == ManualApprovalStatus.PENDING
        assert result.sample is None  # Not emitted yet

    @pytest.mark.asyncio
    async def test_approved_then_emit(self):
        store = _store()
        policy = _policy(require_manual_approval=True)

        # First pass: pending
        result = await create_public_sample_candidate_from_resolution(
            resolution=_resolution(),
            tenant_id="t1",
            policy=policy,
            store=store,
            evidence_records=_evidence_records(),
        )
        assert result.sample is None

        # Simulate approval
        await store.approve_decision(result.decision.decision_id)

        # Re-evaluate with approved decision
        # (In production, the /emit endpoint would be called after approval)
        from apps.api.src.public_metadata.adapter import adapt_engine_result
        from apps.api.src.public_metadata.policy_evaluator import evaluate
        from apps.api.src.public_metadata.emitter import emit_sample

        adapted = adapt_engine_result(_resolution(), "t1", evidence_records=_evidence_records())
        decision = evaluate(adapted.source, "t1", policy, adapted.anchors)
        decision.manual_approval_status = ManualApprovalStatus.APPROVED
        sample = emit_sample(adapted.source, "t1", policy, decision, adapted.anchors)

        assert sample is not None
        assert sample.headline
        assert "tampa_re" not in str(sample.model_dump())


class TestIntegrity:
    @pytest.mark.asyncio
    async def test_integrity_hash_deterministic(self):
        store1 = _store()
        store2 = _store()
        r1 = await create_public_sample_candidate_from_resolution(
            _resolution(), "t1", _policy(), store1,
        )
        r2 = await create_public_sample_candidate_from_resolution(
            _resolution(), "t1", _policy(), store2,
        )
        # Decisions use same input → same integrity hash
        assert r1.decision.integrity_hash == r2.decision.integrity_hash

    @pytest.mark.asyncio
    async def test_provenance_in_decision(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            _resolution(), "t1", _policy(), store,
            correlation_id="cmd_xyz",
        )
        assert result.decision.source_resolution_id == "r-gold-001"
        assert result.decision.created_at
        assert result.decision.integrity_hash
        assert len(result.decision.integrity_hash) == 64


class TestAnchorFiltering:
    @pytest.mark.asyncio
    async def test_only_allowed_anchors_survive(self):
        store = _store()
        policy = _policy(
            require_manual_approval=False,
            allow_real_sanitized_samples=True,
        )
        records = [
            {"data": {"step": "l1_rule_match"}},
            {"data": {"step": "pii_mask"}},
            {"data": {"spec_anchor": {"spec_id": "INV-010"}}},  # Not allowed
        ]
        result = await create_public_sample_candidate_from_resolution(
            _resolution(), "t1", policy, store,
            evidence_records=records,
        )
        assert result.sample is not None
        assert "INV-010" not in result.sample.public_spec_anchors
        assert "INV-002" in result.sample.public_spec_anchors
        assert "INV-006" in result.sample.public_spec_anchors
