"""Tests for the post-deploy probe harness logic.

Tests the probe functions against synthetic responses without real HTTP calls.
"""

import json
from unittest.mock import patch

import pytest

# Import probe internals
import scripts.post_deploy_probe as probe


def _mock_get(responses: dict[str, tuple[int, str]]):
    """Return a mock _get that returns preconfigured responses by URL suffix."""
    def _get(url, timeout=10):
        for suffix, resp in responses.items():
            if suffix in url:
                return resp
        return (404, "not found")
    return _get


class TestProbeHealth:
    def test_healthy(self):
        with patch.object(probe, "_get", return_value=(200, '{"status":"alive"}')):
            r = probe.probe_health()
            assert r.passed

    def test_unhealthy(self):
        with patch.object(probe, "_get", return_value=(200, '{"status":"degraded"}')):
            r = probe.probe_health()
            assert not r.passed

    def test_http_error(self):
        with patch.object(probe, "_get", return_value=(500, "error")):
            r = probe.probe_health()
            assert not r.passed

    def test_malformed_json(self):
        with patch.object(probe, "_get", return_value=(200, "not json")):
            r = probe.probe_health()
            assert not r.passed


class TestProbeFeed:
    def test_valid_feed(self):
        body = json.dumps({"samples": [], "count": 0, "total": 0, "limit": 20, "offset": 0})
        with patch.object(probe, "_get", return_value=(200, body)):
            r = probe.probe_feed()
            assert r.passed
            assert "count=0" in r.detail

    def test_non_200(self):
        with patch.object(probe, "_get", return_value=(401, "{}")):
            r = probe.probe_feed()
            assert not r.passed

    def test_malformed_json(self):
        with patch.object(probe, "_get", return_value=(200, "broken")):
            r = probe.probe_feed()
            assert not r.passed

    def test_missing_samples_key(self):
        with patch.object(probe, "_get", return_value=(200, '{"data":[]}')):
            r = probe.probe_feed()
            assert not r.passed


class TestProbeFeedContract:
    def test_clean_samples(self):
        body = json.dumps({"samples": [
            {"public_sample_id": "pub_1", "headline": "Test", "summary": "S",
             "status": "published", "outcome_class": "resolved", "integrity_hash": "a" * 64,
             "emitted_at": "2026-01-01", "sample_type": "resolution_authority",
             "workflow_stages": [], "public_spec_anchors": ["INV-002"],
             "proof_summary": "p", "redaction_profile_version": "1.0", "source_kind": "resolution"},
        ], "count": 1})
        with patch.object(probe, "_get", return_value=(200, body)):
            r = probe.probe_feed_contract()
            assert r.passed

    def test_forbidden_field_detected(self):
        body = json.dumps({"samples": [
            {"public_sample_id": "pub_1", "headline": "T", "tenant_id": "leaked!"},
        ], "count": 1})
        with patch.object(probe, "_get", return_value=(200, body)):
            r = probe.probe_feed_contract()
            assert not r.passed
            assert "forbidden" in r.detail

    def test_unexpected_field_detected(self):
        body = json.dumps({"samples": [
            {"public_sample_id": "pub_1", "headline": "T", "secret_internal": "x"},
        ], "count": 1})
        with patch.object(probe, "_get", return_value=(200, body)):
            r = probe.probe_feed_contract()
            assert not r.passed
            assert "unexpected" in r.detail

    def test_empty_feed_passes(self):
        body = json.dumps({"samples": [], "count": 0})
        with patch.object(probe, "_get", return_value=(200, body)):
            r = probe.probe_feed_contract()
            assert r.passed


class TestProbeMarketing:
    def test_page_loads(self):
        with patch.object(probe, "_get", return_value=(200, "<html>")):
            r = probe.probe_marketing_page()
            assert r.passed

    def test_page_fails(self):
        with patch.object(probe, "_get", return_value=(503, "down")):
            r = probe.probe_marketing_page()
            assert not r.passed


class TestProbeMarketingFeed:
    def test_consistent(self):
        body = json.dumps({"samples": [], "count": 0, "total": 0})
        with patch.object(probe, "_get", return_value=(200, body)):
            r = probe.probe_marketing_feed()
            assert r.passed

    def test_mismatch(self):
        call_count = [0]
        def _mock_get(url, timeout=10):
            call_count[0] += 1
            if call_count[0] == 1:
                return (200, json.dumps({"samples": [], "total": 5}))
            return (200, json.dumps({"samples": [], "total": 3}))
        with patch.object(probe, "_get", _mock_get):
            r = probe.probe_marketing_feed()
            assert not r.passed
            assert "mismatch" in r.detail


class TestURLOverrides:
    def test_defaults(self):
        assert "ia-api" in probe.BACKEND_URL
        assert "intelligentanalyst-marketing" in probe.MARKETING_URL

    def test_env_override(self):
        import os
        old_b = os.environ.get("PROBE_BACKEND_URL")
        old_m = os.environ.get("PROBE_MARKETING_URL")
        try:
            os.environ["PROBE_BACKEND_URL"] = "http://custom-backend"
            os.environ["PROBE_MARKETING_URL"] = "http://custom-marketing"
            # Module-level vars are set at import time, so we reload
            import importlib
            importlib.reload(probe)
            assert probe.BACKEND_URL == "http://custom-backend"
            assert probe.MARKETING_URL == "http://custom-marketing"
        finally:
            if old_b is None:
                os.environ.pop("PROBE_BACKEND_URL", None)
            else:
                os.environ["PROBE_BACKEND_URL"] = old_b
            if old_m is None:
                os.environ.pop("PROBE_MARKETING_URL", None)
            else:
                os.environ["PROBE_MARKETING_URL"] = old_m
            import importlib
            importlib.reload(probe)


class TestRunAll:
    def test_all_pass(self):
        body = json.dumps({"samples": [], "count": 0, "total": 0, "limit": 20, "offset": 0})
        health = '{"status":"alive"}'
        def _mock(url, timeout=10):
            if "health" in url:
                return (200, health)
            return (200, body)
        with patch.object(probe, "_get", _mock):
            results = probe.run_all()
            assert all(r.passed for r in results)

    def test_one_fail_means_overall_fail(self):
        body = json.dumps({"samples": [], "count": 0, "total": 0})
        def _mock(url, timeout=10):
            if "health" in url:
                return (500, "down")
            return (200, body)
        with patch.object(probe, "_get", _mock):
            results = probe.run_all()
            ok = probe.print_results(results)
            assert not ok
