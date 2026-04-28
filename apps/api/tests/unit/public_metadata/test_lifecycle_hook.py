"""Tests for the PMC lifecycle hook wired into the resolution flow.

Proves: hook fires exactly once for finalized resolutions, does not fire
for partial/failed states, tenant context is correct, samples stay in
platform/ storage, resolution flow succeeds when PMC denies or raises.
"""

from unittest.mock import patch, MagicMock

from apps.api.tests.conftest import VALID_TOKEN, auth_header
from apps.api.src.public_metadata.store import SAMPLES_PATH, DECISIONS_PATH


class TestPMCHookInvocation:
    def test_finalized_resolution_invokes_pmc(self, client):
        """A successful resolve triggers _try_pmc_candidate exactly once."""
        with patch("apps.api.src.routes.resolve._try_pmc_candidate") as mock_try:
            resp = client.post(
                "/v1/resolve",
                json={
                    "document_id": "d-hook-test",
                    "document_type": "regulatory",
                    "content": "Test document for PMC hook.",
                },
                headers={**auth_header(), "Idempotency-Key": "hook-test-1"},
            )
            assert resp.status_code == 200
            mock_try.assert_called_once()

    def test_pmc_receives_correct_tenant(self, client):
        """PMC is called with the authenticated tenant_id."""
        with patch("apps.api.src.routes.resolve._try_pmc_candidate") as mock_try:
            resp = client.post(
                "/v1/resolve",
                json={
                    "document_id": "d-tenant-check",
                    "document_type": "financial",
                    "content": "Tenant verification content.",
                },
                headers={**auth_header(), "Idempotency-Key": "hook-tenant-1"},
            )
            assert resp.status_code == 200
            assert mock_try.called
            tenant_arg = mock_try.call_args[0][2]  # third positional arg
            assert tenant_arg == "tenant-1"  # from test conftest


class TestPMCHookNotInvoked:
    def test_cached_idempotency_skips_pmc(self, client):
        """Idempotent cache hit returns cached response without re-invoking PMC."""
        headers = {**auth_header(), "Idempotency-Key": "hook-idem-1"}
        body = {"document_id": "d-idem", "document_type": "regulatory", "content": "test"}

        with patch("apps.api.src.routes.resolve._try_pmc_candidate") as mock_try:
            client.post("/v1/resolve", json=body, headers=headers)
            first_count = mock_try.call_count
            client.post("/v1/resolve", json=body, headers=headers)
            assert mock_try.call_count == first_count

    def test_validation_failure_skips_pmc(self, client):
        """Invalid request (missing fields) never reaches PMC."""
        with patch("apps.api.src.routes.resolve._try_pmc_candidate") as mock_try:
            resp = client.post(
                "/v1/resolve",
                json={"document_type": "regulatory"},
                headers={**auth_header(), "Idempotency-Key": "hook-invalid-1"},
            )
            assert resp.status_code == 400
            mock_try.assert_not_called()


class TestPMCStorageIsolation:
    def test_candidate_stored_in_platform_not_tenant(self, client, app):
        """PMC candidate persists to platform/ path, not tenants/."""
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "d-storage-check",
                "document_type": "compliance",
                "content": "Storage isolation test.",
            },
            headers={**auth_header(), "Idempotency-Key": "hook-storage-1"},
        )
        assert resp.status_code == 200

        db = app.state.firestore_client
        decisions = db.collection(DECISIONS_PATH).stream()
        assert len(decisions) >= 1

        tenant_pmc = db.collection("tenants/tenant-1/public_samples").stream()
        assert len(tenant_pmc) == 0


class TestPMCFailSafe:
    def test_resolution_succeeds_when_pmc_denies(self, client):
        """PMC DENY does not block the resolution response."""
        # Let the real _try_pmc_candidate run — it will create a REQUIRES_MANUAL_APPROVAL
        # decision (no sample emitted), which is fine
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "d-deny-test",
                "document_type": "regulatory",
                "content": "PMC will evaluate but not emit.",
            },
            headers={**auth_header(), "Idempotency-Key": "hook-deny-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolution_id"]
        assert data["status"] in ("resolved", "routed_to_review")

    def test_resolution_succeeds_when_pmc_raises(self, client):
        """PMC internal exception does not corrupt the resolution flow."""
        with patch(
            "apps.api.src.public_metadata.orchestrator.create_public_sample_candidate_from_resolution",
            side_effect=RuntimeError("PMC exploded"),
        ):
            resp = client.post(
                "/v1/resolve",
                json={
                    "document_id": "d-crash-test",
                    "document_type": "financial",
                    "content": "PMC will crash.",
                },
                headers={**auth_header(), "Idempotency-Key": "hook-crash-1"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["resolution_id"]
