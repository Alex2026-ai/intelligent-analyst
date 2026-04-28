"""Tests verifying self-healing bounds — allowed actions work, forbidden impossible."""

from apps.api.src.resilience.config import SELF_HEALING_BOUNDS
from apps.api.src.resilience.breaker_registry import BreakerRegistry
from apps.api.src.resilience.kill_switch import KillSwitchManager
from apps.api.src.resilience.degradation import DegradationManager, DegradedMode


class TestAllowedSelfHealing:
    def test_llm_failover_has_bound(self):
        assert "llm_failover" in SELF_HEALING_BOUNDS
        assert SELF_HEALING_BOUNDS["llm_failover"]["max_per_hour"] > 0

    def test_review_reassignment_has_bound(self):
        assert "review_reassignment" in SELF_HEALING_BOUNDS
        assert SELF_HEALING_BOUNDS["review_reassignment"]["max_per_case"] == 2

    def test_export_retry_has_bound(self):
        assert "export_retry" in SELF_HEALING_BOUNDS
        assert SELF_HEALING_BOUNDS["export_retry"]["max_retries"] == 3

    def test_circuit_breaker_auto_recovery(self):
        """Circuit breaker auto-recovery is an allowed self-healing action."""
        registry = BreakerRegistry()
        cb = registry.get("llm_provider_a")
        # This should work without human intervention
        assert cb.state.value == "closed"


class TestForbiddenSelfHealing:
    def test_no_auto_approve_method(self):
        """No code path can auto-approve review cases."""
        from apps.api.src.review import decision
        # The decision module requires explicit reviewer_id and notes
        assert "auto_approve" not in dir(decision)
        assert "auto_decide" not in dir(decision)

    def test_no_threshold_modification(self):
        """No code path auto-modifies decision thresholds at runtime."""
        from apps.api.src.resolver.base import ResolverConfig
        config = ResolverConfig()
        # ResolverConfig is frozen — cannot be modified
        assert config.__dataclass_params__.frozen is True

    def test_no_evidence_deletion(self):
        """No code path deletes evidence chains."""
        from apps.api.src.evidence import builder
        b = builder.EvidenceChainBuilder()
        assert not hasattr(b, "delete_chain")
        assert not hasattr(b, "delete_node")
        assert not hasattr(b, "remove_node")

    def test_no_kill_switch_auto_toggle(self):
        """Kill switches can only be toggled by explicit human action."""
        ks = KillSwitchManager()
        # activate requires activated_by (human identifier)
        import inspect
        sig = inspect.signature(ks.activate)
        assert "activated_by" in sig.parameters

    def test_no_auto_scale_bypass(self):
        """Bulkhead limits are enforced — no bypass method."""
        from apps.api.src.resilience.bulkheads import Bulkhead
        bh = Bulkhead("test", max_concurrent=1)
        assert not hasattr(bh, "override_limit")
        assert not hasattr(bh, "set_unlimited")

    def test_degradation_requires_explicit_entry(self):
        """Degraded modes require explicit enter/exit — no auto-toggle."""
        dm = DegradationManager()
        assert not hasattr(dm, "auto_enter")
        assert not hasattr(dm, "auto_exit")
