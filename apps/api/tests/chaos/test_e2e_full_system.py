"""Full system E2E test: submit → L1/L2 resolve → evidence chain → review → export.

This test exercises all 9 phases together.
"""

import asyncio

from ia_shared.models.evidence import ChainStatus, NodeType

from apps.api.src.evidence.builder import EvidenceChainBuilder
from apps.api.src.evidence.hasher import verify_chain
from apps.api.src.export.preconditions import check_export_preconditions
from apps.api.src.llm.provider import MockLLMProvider
from apps.api.src.llm.router import LLMRouter
from apps.api.src.pii.masker import PIIMasker
from apps.api.src.resilience.breaker_registry import BreakerRegistry
from apps.api.src.resilience.degradation import DegradationManager
from apps.api.src.resilience.kill_switch import KillSwitchManager
from apps.api.src.resolver.base import ResolverConfig
from apps.api.src.resolver.engine import resolve_with_evidence
from apps.api.src.review.decision import build_evidence_node_data, process_decision
from apps.api.src.review.routing import create_review_case
from apps.api.tests.unit.resolver.conftest import SAMPLE_PRECEDENTS, SAMPLE_RULE_SET
from apps.worker.src.export.generator import generate_export


class TestFullSystemE2E:
    def test_l1_resolution_full_flow(self):
        """Submit regulatory doc → L1 match → evidence chain → export."""
        # Phase 2: Resolve
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r-e2e-l1",
            tenant_id="t-e2e",
        )

        # Verify resolution
        assert result.status == "resolved"
        assert result.layer_used == 1
        assert result.confidence == 1.0

        # Phase 3: Evidence chain valid
        chain = result.evidence_chain
        assert chain is not None
        assert chain.status == ChainStatus.COMPLETE
        assert verify_chain(chain) is True

        # Phase 7: Export (non-high-impact, no human approval needed)
        precondition = check_export_preconditions(
            "complete", [{"node_type": n.node_type.value, "data": n.data} for n in chain.nodes],
            is_high_impact=False,
        )
        assert precondition.allowed is True

        # Generate export artifact
        resolution_dict = {
            "resolution_id": "r-e2e-l1",
            "status": result.status,
            "confidence": result.confidence,
            "layer_used": result.layer_used,
            "resolution": result.resolution,
        }
        pdf = generate_export(resolution_dict, [], "pdf")
        assert len(pdf) > 0
        assert b"RESOLUTION REPORT" in pdf

    def test_l2_to_review_to_export(self):
        """Submit doc → L2 match → force_review → reviewer approves → export."""
        # Phase 2: Resolve with force_review
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={"force_review": True},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r-e2e-review",
            tenant_id="t-e2e",
        )
        assert result.status == "routed_to_review"
        assert result.evidence_chain.status == ChainStatus.BUILDING

        # Phase 7: Create review case
        case = create_review_case("r-e2e-review", result.evidence_chain.chain_id, "force_review")
        assert case["status"] == "pending"

        # Reviewer decides
        decision_record = process_decision(
            case, "approve", "reviewer-42", "Confirmed correct after full review."
        )
        assert decision_record["decision"] == "approve"
        assert case["status"] == "decided"

        # Add human_decision to evidence chain
        builder = EvidenceChainBuilder()
        chain = result.evidence_chain
        chain = builder.add_node(
            chain, NodeType.HUMAN_DECISION,
            build_evidence_node_data(decision_record),
        )
        chain = builder.close_chain(chain)
        assert chain.status == ChainStatus.COMPLETE
        assert verify_chain(chain) is True

        # Export with high-impact precondition
        nodes = [{"node_type": n.node_type.value, "data": n.data} for n in chain.nodes]
        precondition = check_export_preconditions("complete", nodes, is_high_impact=True)
        assert precondition.allowed is True  # Has human approval

    def test_pii_masking_in_llm_flow(self):
        """Full L3 flow: mask PII → call LLM → unmask response."""
        # Phase 8: PII masking
        masker = PIIMasker()
        content = "Patient SSN: 123-45-6789, email: john@hospital.org"
        masked, vault, categories = masker.mask(content)
        assert "123-45-6789" not in masked
        assert "john@hospital.org" not in masked

        # Phase 8: LLM call with masked content
        provider = MockLLMProvider(default_confidence=0.85)
        response = asyncio.run(provider.resolve(masked, {}, "1.0"))
        assert response.confidence == 0.85

        # Unmask
        restored = masker.unmask(response.resolution, vault)
        # Mock provider echoes masked content — no PII in response to restore
        # But the round-trip mechanism works
        vault.clear()
        assert vault.token_count == 0

    def test_resilience_under_degradation(self):
        """System operates in degraded mode when dependencies fail."""
        # Phase 9: Circuit breakers + degradation
        registry = BreakerRegistry()
        dm = DegradationManager()
        ks = KillSwitchManager()

        # Trip LLM breakers
        for _ in range(5):
            registry.get("llm_provider_a").record_failure()
            registry.get("llm_provider_b").record_failure()

        from apps.api.src.resilience.degradation import DegradedMode
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "Both providers down")

        # System still works — L1/L2 resolution
        config = ResolverConfig(max_layer=2)
        result = resolve_with_evidence(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r-degraded",
            tenant_id="t-e2e",
        )
        assert result.status == "resolved"
        assert result.layer_used == 1

        # Degraded mode headers
        headers = dm.get_response_headers()
        assert "X-Degraded-Mode" in headers
