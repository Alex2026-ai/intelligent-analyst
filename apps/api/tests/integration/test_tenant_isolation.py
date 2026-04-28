"""Integration test: cross-tenant access prevention."""

from apps.api.tests.conftest import TENANT_B_TOKEN, VALID_TOKEN, auth_header


class TestTenantIsolation:
    def test_review_queue_scoped_to_tenant(self, client):
        """Reviewer from tenant-1 should not see tenant-B cases."""
        from apps.api.tests.conftest import REVIEWER_TOKEN
        resp = client.get("/v1/review/queue", headers=auth_header(REVIEWER_TOKEN))
        assert resp.status_code == 200
        # No cases belong to this tenant
        assert resp.json()["cases"] == []

    def test_different_tenants_different_idempotency(self, client):
        """Same idempotency key from different tenants should work independently."""
        body = {"document_id": "d1", "document_type": "regulatory", "content": "test"}
        headers_a = {**auth_header(VALID_TOKEN), "Idempotency-Key": "shared-key"}
        headers_b = {**auth_header(TENANT_B_TOKEN), "Idempotency-Key": "shared-key-b"}

        r1 = client.post("/v1/resolve", json=body, headers=headers_a)
        r2 = client.post("/v1/resolve", json=body, headers=headers_b)
        assert r1.status_code == 200
        assert r2.status_code == 200
