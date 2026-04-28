"""Tests for degraded mode management."""

from apps.api.src.resilience.degradation import DegradationManager, DegradedMode


class TestDegradationManager:
    def test_starts_healthy(self):
        dm = DegradationManager()
        assert dm.is_degraded is False
        assert dm.active_modes == set()

    def test_enter_mode(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "Provider A down")
        assert dm.is_degraded is True
        assert DegradedMode.LLM_DEGRADED in dm.active_modes

    def test_exit_mode(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "Down")
        dm.exit_mode(DegradedMode.LLM_DEGRADED)
        assert dm.is_degraded is False

    def test_multiple_modes(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "LLM down")
        dm.enter_mode(DegradedMode.STORAGE_DEGRADED, "GCS down")
        assert len(dm.active_modes) == 2

    def test_exit_one_keeps_other(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "LLM")
        dm.enter_mode(DegradedMode.READ_ONLY, "Firestore")
        dm.exit_mode(DegradedMode.LLM_DEGRADED)
        assert dm.is_degraded is True
        assert DegradedMode.READ_ONLY in dm.active_modes

    def test_is_mode_active(self):
        dm = DegradationManager()
        assert dm.is_mode_active(DegradedMode.LLM_DEGRADED) is False
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "Down")
        assert dm.is_mode_active(DegradedMode.LLM_DEGRADED) is True


class TestDegradedHeaders:
    def test_no_headers_when_healthy(self):
        dm = DegradationManager()
        assert dm.get_response_headers() == {}

    def test_header_when_degraded(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "Down")
        headers = dm.get_response_headers()
        assert "X-Degraded-Mode" in headers
        assert "llm_degraded" in headers["X-Degraded-Mode"]

    def test_multiple_modes_in_header(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.LLM_DEGRADED, "LLM")
        dm.enter_mode(DegradedMode.READ_ONLY, "FS")
        headers = dm.get_response_headers()
        assert "llm_degraded" in headers["X-Degraded-Mode"]
        assert "read_only" in headers["X-Degraded-Mode"]


class TestDegradationStatus:
    def test_status_when_healthy(self):
        dm = DegradationManager()
        status = dm.get_status()
        assert status["is_degraded"] is False
        assert status["active_modes"] == []

    def test_status_when_degraded(self):
        dm = DegradationManager()
        dm.enter_mode(DegradedMode.EXPORT_DEGRADED, "Paused")
        status = dm.get_status()
        assert status["is_degraded"] is True
        assert len(status["active_modes"]) == 1
