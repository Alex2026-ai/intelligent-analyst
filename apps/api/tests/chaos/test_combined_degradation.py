"""Chaos test: multiple simultaneous failures."""

from apps.api.src.resilience.breaker_registry import BreakerRegistry
from apps.api.src.resilience.degradation import DegradationManager, DegradedMode
from apps.api.src.resilience.kill_switch import KillSwitchManager


class TestCombinedDegradation:
    def test_multiple_breakers_open(self):
        registry = BreakerRegistry()
        # Trip LLM and Firestore breakers
        for _ in range(5):
            registry.get("llm_provider_a").record_failure()
        for _ in range(5):
            registry.get("llm_provider_b").record_failure()
        for _ in range(3):
            registry.get("firestore_writes").record_failure()

        assert registry.any_open() is True
        assert not registry.all_closed()
        states = registry.get_all_states()
        assert states["llm_provider_a"] == "open"
        assert states["llm_provider_b"] == "open"
        assert states["firestore_writes"] == "open"
        # Others still closed
        assert states["firestore_reads"] == "closed"
        assert states["gcs"] == "closed"

    def test_multiple_degraded_modes(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "Both providers down")
        dm.enter_mode(DegradedMode.READ_ONLY, "Firestore writes failing")
        dm.enter_mode(DegradedMode.STORAGE_DEGRADED, "GCS unavailable")

        assert len(dm.active_modes) == 3
        headers = dm.get_response_headers()
        assert "llm_degraded" in headers["X-Degraded-Mode"]
        assert "read_only" in headers["X-Degraded-Mode"]
        assert "storage_degraded" in headers["X-Degraded-Mode"]

    def test_kill_switch_plus_breaker(self):
        ks = KillSwitchManager()
        registry = BreakerRegistry()

        ks.activate("resolution", "admin", "Emergency")
        for _ in range(5):
            registry.get("llm_provider_a").record_failure()

        assert ks.is_killed("resolution") is True
        assert registry.any_open() is True

    def test_recovery_from_combined(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "Down")
        dm.enter_mode(DegradedMode.READ_ONLY, "FS down")

        # Partial recovery
        dm.exit_mode(DegradedMode.LLM_DEGRADED)
        assert dm.is_degraded is True  # Still read-only

        # Full recovery
        dm.exit_mode(DegradedMode.READ_ONLY)
        assert dm.is_degraded is False
        assert dm.get_response_headers() == {}
