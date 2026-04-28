"""Tests for orphan detector."""

from apps.worker.src.audit.orphan_detector import detect_orphans


class TestDetectOrphans:
    def test_no_orphans(self):
        chains = {"c1": "r1", "c2": "r2"}
        resolutions = {"r1", "r2"}
        report = detect_orphans(chains, resolutions)
        assert report.chains_without_resolutions == []
        assert report.resolutions_without_chains == []

    def test_chain_without_resolution(self):
        chains = {"c1": "r1", "c2": "r-missing"}
        resolutions = {"r1"}
        report = detect_orphans(chains, resolutions)
        assert "c2" in report.chains_without_resolutions
        assert report.resolutions_without_chains == []

    def test_resolution_without_chain(self):
        chains = {"c1": "r1"}
        resolutions = {"r1", "r2"}
        report = detect_orphans(chains, resolutions)
        assert report.chains_without_resolutions == []
        assert "r2" in report.resolutions_without_chains

    def test_both_orphan_types(self):
        chains = {"c1": "r1", "c-orphan": "r-missing"}
        resolutions = {"r1", "r-orphan"}
        report = detect_orphans(chains, resolutions)
        assert "c-orphan" in report.chains_without_resolutions
        assert "r-orphan" in report.resolutions_without_chains

    def test_empty_inputs(self):
        report = detect_orphans({}, set())
        assert report.chains_without_resolutions == []
        assert report.resolutions_without_chains == []

    def test_results_sorted(self):
        chains = {"c3": "r-z", "c1": "r-a", "c2": "r-m"}
        resolutions: set[str] = set()
        report = detect_orphans(chains, resolutions)
        assert report.chains_without_resolutions == sorted(report.chains_without_resolutions)
