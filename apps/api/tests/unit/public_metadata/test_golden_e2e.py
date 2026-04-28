import pytest
"""Golden end-to-end PMC test + invariant hardening.

Uses typed EngineResult from the real resolver, not dicts.
Asserts exact deterministic output, anchor filtering, and tenant isolation.
"""

from dataclasses import dataclass

from apps.api.src.public_metadata.adapter import adapt_engine_result
from apps.api.src.public_metadata.models import (
    Decision,
    ManualApprovalStatus,
    PolicyMode,
    PublicMetadataPolicy,
)
from apps.api.src.public_metadata.orchestrator import create_public_sample_candidate_from_resolution
from apps.api.src.public_metadata.store import PublicMetadataStore, SAMPLES_PATH
from apps.api.src.resolver.base import EvidenceRecord
from apps.api.src.resolver.engine import EngineResult
from apps.api.src.storage.firestore.client import InMemoryFirestore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _golden_engine_result() -> EngineResult:
    """Production-like finalized resolution — the James Benson Gold Prime."""
    return EngineResult(
        resolution="APPROVED — Commercial lease application recommended for approval.",
        confidence=0.95,
        layer_used=3,
        status="resolved",
        review_reason=None,
        evidence=[
            EvidenceRecord(node_type="source_artifact", data={
                "document_type": "financial",
                "content_length": 412,
                "has_force_review": False,
            }),
            EvidenceRecord(node_type="transformation", data={
                "step": "pii_mask",
                "categories": ["SSN", "EMAIL"],
                "token_count": 2,
            }),
            EvidenceRecord(node_type="transformation", data={
                "step": "l1_rule_match",
                "rule_id": "R-001",
                "matched": True,
            }),
            EvidenceRecord(node_type="transformation", data={
                "step": "routing_decision",
                "route_to_review": False,
                "confidence": 0.95,
            }),
        ],
    )


def _golden_engine_result_as_dict() -> dict:
    """Same resolution as dict — for backward compatibility path."""
    return {
        "resolution_id": "r-gold-001",
        "status": "resolved",
        "confidence": 0.95,
        "layer_used": 3,
        "document_type": "financial",
        "evidence_chain_id": "ec-gold-001",
    }


def _policy(**overrides) -> PublicMetadataPolicy:
    defaults = {
        "policy_id": "golden-test",
        "version": "1.0",
        "mode": PolicyMode.CURATED_HYBRID,
        "allow_real_sanitized_samples": True,
        "require_manual_approval": False,  # Auto for golden tests
        "public_anchor_allowlist": ["INV-002", "INV-005", "INV-006"],
        "blocked_tenants": [],
    }
    defaults.update(overrides)
    return PublicMetadataPolicy(**defaults)


def _store() -> PublicMetadataStore:
    return PublicMetadataStore(InMemoryFirestore())


# ---------------------------------------------------------------------------
# 3. Golden End-to-End Fixture
# ---------------------------------------------------------------------------

class TestGoldenE2E:
    @pytest.mark.asyncio
    async def test_typed_engine_result_produces_candidate(self):
        """Full typed path: EngineResult → adapter → orchestrator → sample."""
        # EngineResult has no resolution_id — we provide it via dict overlay
        er = _golden_engine_result()
        # Orchestrator needs resolution_id in the input.
        # In production, this comes from the API response that wraps EngineResult.
        resolution_dict = _golden_engine_result_as_dict()

        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            resolution=resolution_dict,
            tenant_id="tampa_re",
            policy=_policy(),
            store=store,
            evidence_records=list(er.evidence),
        )

        assert result.success
        assert result.sample is not None
        sample = result.sample

        # Exact deterministic content
        assert sample.headline == "Automated resolution completed with verified confidence"
        assert "multi-layer" in sample.summary or "automated" in sample.summary.lower()
        assert sample.outcome_class.value == "resolved"

        # Only allowed anchors
        for a in sample.public_spec_anchors:
            assert a in {"INV-002", "INV-005", "INV-006"}

        # Anchors from evidence: pii_mask → INV-006, l1_rule_match → INV-002
        assert "INV-002" in sample.public_spec_anchors
        assert "INV-006" in sample.public_spec_anchors

        # No tenant or identifying data
        dump = str(sample.model_dump())
        assert "tampa_re" not in dump
        assert "James Benson" not in dump
        assert "999-55-4444" not in dump
        assert "r-gold-001" not in dump
        assert "ec-gold-001" not in dump
        assert "cmd_" not in dump

        # Integrity present
        assert len(sample.integrity_hash) == 64

    @pytest.mark.asyncio
    async def test_typed_evidence_records_extracted(self):
        """Typed EvidenceRecord objects yield correct anchors."""
        er = _golden_engine_result()
        adapted = adapt_engine_result(
            _golden_engine_result_as_dict(),
            "t1",
            evidence_records=list(er.evidence),
        )
        assert adapted.valid
        assert "INV-002" in adapted.anchors
        assert "INV-006" in adapted.anchors


# ---------------------------------------------------------------------------
# 4. Invariant Hardening
# ---------------------------------------------------------------------------

class TestTenantIsolationInvariant:
    @pytest.mark.asyncio
    async def test_tenant_path_never_in_public_storage(self):
        """Public samples must never be under tenants/."""
        assert not SAMPLES_PATH.startswith("tenants/")

    @pytest.mark.asyncio
    async def test_tenant_data_never_mirrors_to_public(self):
        """Writing to tenants/{tid}/ does NOT create anything in platform/."""
        db = InMemoryFirestore()
        # Write tenant data
        db.collection("tenants/tampa_re/resolutions").add(
            {"resolution_id": "r1", "status": "resolved"}, "r1"
        )
        # Public store sees nothing
        store = PublicMetadataStore(db)
        assert await store.get_sample("r1") is None
        results = await store.list_published()
        assert len(results) == 0


class TestAnchorFilteringE2E:
    @pytest.mark.asyncio
    async def test_disallowed_anchors_stripped_end_to_end(self):
        evidence = [
            EvidenceRecord(node_type="transformation", data={"step": "pii_mask"}),
            EvidenceRecord(node_type="transformation", data={
                "spec_anchor": {"spec_id": "INV-010"},  # Not on allowlist
            }),
            EvidenceRecord(node_type="transformation", data={
                "spec_anchor": {"spec_id": "PHASE-8"},  # Not on allowlist
            }),
        ]
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            _golden_engine_result_as_dict(), "t1", _policy(), store,
            evidence_records=list(evidence),
        )
        assert result.sample is not None
        assert "INV-010" not in result.sample.public_spec_anchors
        assert "PHASE-8" not in result.sample.public_spec_anchors
        assert "INV-006" in result.sample.public_spec_anchors


class TestDeterministicIntegrity:
    @pytest.mark.asyncio
    async def test_same_input_same_hash(self):
        """Identical finalized artifacts yield identical integrity hashes."""
        s1 = _store()
        s2 = _store()
        r1 = await create_public_sample_candidate_from_resolution(
            _golden_engine_result_as_dict(), "t1", _policy(), s1,
        )
        r2 = await create_public_sample_candidate_from_resolution(
            _golden_engine_result_as_dict(), "t1", _policy(), s2,
        )
        assert r1.sample is not None
        assert r2.sample is not None
        assert r1.sample.integrity_hash == r2.sample.integrity_hash

    @pytest.mark.asyncio
    async def test_changing_private_field_no_effect_on_sample(self):
        """Changing a dropped field (e.g. resolution text) does not change public output."""
        base = _golden_engine_result_as_dict()
        modified = {**base, "resolution": "TOTALLY DIFFERENT TEXT", "raw_response": "secret"}

        s1 = _store()
        s2 = _store()
        r1 = await create_public_sample_candidate_from_resolution(base, "t1", _policy(), s1)
        r2 = await create_public_sample_candidate_from_resolution(modified, "t1", _policy(), s2)

        assert r1.sample is not None
        assert r2.sample is not None
        # Headline, summary, outcome_class should be identical
        assert r1.sample.headline == r2.sample.headline
        assert r1.sample.summary == r2.sample.summary
        assert r1.sample.outcome_class == r2.sample.outcome_class
        assert r1.sample.integrity_hash == r2.sample.integrity_hash

    @pytest.mark.asyncio
    async def test_changing_public_field_changes_sample(self):
        """Changing an allowed field (status) deterministically changes public output."""
        resolved = {**_golden_engine_result_as_dict(), "status": "resolved"}
        review = {**_golden_engine_result_as_dict(), "status": "routed_to_review"}

        s1 = _store()
        s2 = _store()
        r1 = await create_public_sample_candidate_from_resolution(resolved, "t1", _policy(), s1)
        r2 = await create_public_sample_candidate_from_resolution(review, "t1", _policy(), s2)

        assert r1.sample is not None
        assert r2.sample is not None
        # Different status → different outcome_class → different headline
        assert r1.sample.outcome_class.value == "resolved"
        assert r2.sample.outcome_class.value == "human_review_required"
        assert r1.sample.headline != r2.sample.headline
        assert r1.sample.integrity_hash != r2.sample.integrity_hash


class TestManualApprovalInvariant:
    @pytest.mark.asyncio
    async def test_manual_approval_blocks_even_with_valid_input(self):
        store = _store()
        result = await create_public_sample_candidate_from_resolution(
            _golden_engine_result_as_dict(), "t1",
            _policy(require_manual_approval=True), store,
        )
        assert result.decision.decision == Decision.REQUIRES_MANUAL_APPROVAL
        assert result.sample is None  # Blocked until approved
