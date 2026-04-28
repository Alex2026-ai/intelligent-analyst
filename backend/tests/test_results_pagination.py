"""
Results pagination tests — /batches/{trace_id}/results endpoint.

Proves:
  1. First page loads correctly with default params
  2. Offset/limit pagination returns correct slices without duplicates or skips
  3. Ordering remains stable across pages
  4. Small batches (< page size) return all rows in one page
  5. Response shape is deterministic (total, offset, limit, count, results)
  6. limit is clamped to max 1000
"""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


# --- Test data ---

def _make_results(n):
    """Generate n deterministic result records."""
    return [
        {
            "row_index": i,
            "original": f"Company_{i}",
            "resolved": f"Canonical_{i % 50}",
            "layer": f"L{i % 5}_TEST",
            "confidence": round(0.5 + (i % 50) / 100, 2),
        }
        for i in range(n)
    ]


_BATCH_DOC = {
    "trace_id": "BATCH-PAG-TEST",
    "status": "completed",
    "tenant_id": "tenant_pag",
    "total": 600,
}

_ALL_RESULTS = _make_results(600)

_AUTH = {"tenant_id": "tenant_pag", "role": "tenant_admin", "uid": "user1"}


@pytest.fixture(autouse=True)
def _setup():
    """Set up app with auth override and data mocks."""
    with patch.dict(os.environ, {"HMAC_SCOPE_KEY": "aa" * 32}):
        from app.server_enterprise_golden import app, verify_api_key
        app.dependency_overrides[verify_api_key] = lambda: _AUTH
        yield app, verify_api_key
        app.dependency_overrides.pop(verify_api_key, None)


def _client(app):
    return TestClient(app)


class TestResultsPagination:
    """Pagination contract for /batches/{trace_id}/results."""

    def _get(self, app, path):
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=_BATCH_DOC), \
             patch("app.server_enterprise_golden.fetch_results_from_firestore", return_value=_ALL_RESULTS):
            return _client(app).get(path)

    def test_first_page_default(self, _setup):
        app, _ = _setup
        resp = self._get(app, "/batches/BATCH-PAG-TEST/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 600
        assert data["offset"] == 0
        assert data["limit"] == 100
        assert data["count"] == 100
        assert len(data["results"]) == 100
        assert data["results"][0]["row_index"] == 0
        assert data["results"][99]["row_index"] == 99

    def test_first_page_250(self, _setup):
        app, _ = _setup
        resp = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=250&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 600
        assert data["offset"] == 0
        assert data["limit"] == 250
        assert data["count"] == 250
        assert data["results"][0]["row_index"] == 0
        assert data["results"][249]["row_index"] == 249

    def test_second_page_no_overlap(self, _setup):
        app, _ = _setup
        resp = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=250&offset=250")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 600
        assert data["offset"] == 250
        assert data["count"] == 250
        assert data["results"][0]["row_index"] == 250
        assert data["results"][249]["row_index"] == 499

    def test_last_page_partial(self, _setup):
        app, _ = _setup
        resp = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=250&offset=500")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 600
        assert data["offset"] == 500
        assert data["count"] == 100
        assert len(data["results"]) == 100
        assert data["results"][0]["row_index"] == 500
        assert data["results"][99]["row_index"] == 599

    def test_full_coverage_no_gaps(self, _setup):
        app, _ = _setup
        all_indices = []
        for offset in [0, 250, 500]:
            resp = self._get(app, f"/batches/BATCH-PAG-TEST/results?limit=250&offset={offset}")
            data = resp.json()
            indices = [r["row_index"] for r in data["results"]]
            all_indices.extend(indices)
        assert len(all_indices) == 600
        assert all_indices == list(range(600))

    def test_ordering_stable(self, _setup):
        app, _ = _setup
        resp1 = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=250&offset=0")
        resp2 = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=250&offset=0")
        assert resp1.json()["results"] == resp2.json()["results"]

    def test_small_batch_single_page(self, _setup):
        app, _ = _setup
        small_results = _make_results(50)
        small_batch = {**_BATCH_DOC, "total": 50}
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=small_batch), \
             patch("app.server_enterprise_golden.fetch_results_from_firestore", return_value=small_results):
            resp = _client(app).get("/batches/BATCH-PAG-TEST/results?limit=250&offset=0")
        data = resp.json()
        assert data["total"] == 50
        assert data["count"] == 50
        assert len(data["results"]) == 50

    def test_response_shape_deterministic(self, _setup):
        app, _ = _setup
        resp = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=10&offset=0")
        data = resp.json()
        assert set(data.keys()) == {"trace_id", "total", "offset", "limit", "count", "results"}

    def test_limit_clamped_to_1000(self, _setup):
        app, _ = _setup
        resp = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=5000&offset=0")
        data = resp.json()
        assert data["limit"] == 1000
        assert data["count"] == 600

    def test_offset_beyond_total_returns_empty(self, _setup):
        app, _ = _setup
        resp = self._get(app, "/batches/BATCH-PAG-TEST/results?limit=250&offset=9999")
        data = resp.json()
        assert data["total"] == 600
        assert data["count"] == 0
        assert data["results"] == []

    def test_batch_not_found_404(self, _setup):
        app, _ = _setup
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=None):
            resp = _client(app).get("/batches/BATCH-NONEXISTENT/results")
        assert resp.status_code == 404
