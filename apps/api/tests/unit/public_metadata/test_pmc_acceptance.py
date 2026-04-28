import pytest
"""PMC Operator Acceptance Test — canonical lifecycle proof artifact.

This is the single deterministic test that proves the full intended operator
path works end-to-end. If this test passes, PMC is operationally complete.
"""

from apps.api.src.public_metadata.models import OutcomeClass, SampleStatus, PublicAuthoritySample
from apps.api.src.public_metadata.store import PublicMetadataStore
from apps.api.tests.conftest import ADMIN_TOKEN, auth_header

# Exhaustive allowlist — must match _ADMIN_SAFE_FIELDS and _PUBLIC_SAFE_FIELDS in routes
ALLOWED_RESPONSE_FIELDS = frozenset({
    "public_sample_id", "sample_type", "status", "headline", "summary",
    "outcome_class", "workflow_stages", "public_spec_anchors",
    "proof_summary", "redaction_profile_version", "source_kind",
    "integrity_hash", "emitted_at",
})

# Fields that must NEVER appear in any admin or public response
FORBIDDEN_FIELDS = frozenset({
    "tenant_id", "decision_id", "source_resolution_id", "correlation_id",
    "document_id", "content", "raw_content", "masked_content",
    "raw_response", "raw_prompt", "chain_hash", "node_hash",
    "bucket_path", "gcs_path", "storage_path", "db_path",
    "email", "phone", "ssn", "name", "password", "api_key",
})


def _acceptance_sample() -> PublicAuthoritySample:
    return PublicAuthoritySample(
        public_sample_id="acceptance-001",
        status=SampleStatus.DRAFT,
        headline="Automated resolution completed with verified confidence",
        summary="The system completed automated resolution with verified confidence.",
        outcome_class=OutcomeClass.RESOLVED,
        workflow_stages=["Document Intake", "PII Protection", "Deterministic Analysis",
                         "Confidence Scoring", "Evidence Chain Construction", "Integrity Verification"],
        public_spec_anchors=["INV-002", "INV-006"],
        proof_summary="Resolution verified through: hash-protected evidence lineage, PII-masked external processing.",
        integrity_hash="a1b2c3d4e5f6" * 5 + "a1b2",  # 64 chars
        emitted_at="2026-03-23T12:00:00Z",
    )


class TestAdminResponseBoundary:
    """Regression: forbidden fields must never appear in admin responses."""

    @pytest.mark.asyncio
    async def test_no_forbidden_fields_in_admin_response(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_acceptance_sample())
        resp = client.get("/v1/public-metadata/admin/samples", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 200
        for sample in resp.json()["samples"]:
            for field in FORBIDDEN_FIELDS:
                assert field not in sample, f"Forbidden field '{field}' found in admin response"

    @pytest.mark.asyncio
    async def test_only_allowed_fields_in_admin_response(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_acceptance_sample())
        resp = client.get("/v1/public-metadata/admin/samples", headers=auth_header(ADMIN_TOKEN))
        for sample in resp.json()["samples"]:
            for key in sample:
                assert key in ALLOWED_RESPONSE_FIELDS, f"Unexpected field '{key}' in admin response"

    @pytest.mark.asyncio
    async def test_no_forbidden_fields_in_public_feed(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_acceptance_sample())
        await store.approve_sample("acceptance-001")
        await store.publish_sample("acceptance-001")
        resp = client.get("/v1/public-metadata/feed")
        for sample in resp.json()["samples"]:
            for field in FORBIDDEN_FIELDS:
                assert field not in sample, f"Forbidden field '{field}' found in public feed"

    @pytest.mark.asyncio
    async def test_no_forbidden_fields_in_public_sample(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_acceptance_sample())
        await store.approve_sample("acceptance-001")
        await store.publish_sample("acceptance-001")
        resp = client.get("/v1/public-metadata/sample/acceptance-001")
        for field in FORBIDDEN_FIELDS:
            assert field not in resp.json(), f"Forbidden field '{field}' found in public sample"


class TestCanonicalOperatorAcceptance:
    """The single deterministic proof of the full PMC operator lifecycle.

    Flow: draft → admin visible → approve → publish → public feed → revoke → gone.
    This is the acceptance artifact for PMC operational readiness.
    """

    @pytest.mark.asyncio
    async def test_full_operator_lifecycle(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_acceptance_sample())
        h = auth_header(ADMIN_TOKEN)
        sid = "acceptance-001"

        # 1. Draft visible in admin list
        resp = client.get("/v1/public-metadata/admin/samples?status=draft", headers=h)
        assert resp.status_code == 200
        draft_ids = [s["public_sample_id"] for s in resp.json()["samples"]]
        assert sid in draft_ids

        # 2. Draft NOT in public feed
        feed = client.get("/v1/public-metadata/feed").json()
        assert sid not in [s["public_sample_id"] for s in feed["samples"]]

        # 3. Approve
        resp = client.post(f"/v1/public-metadata/approve/{sid}", headers=h)
        assert resp.status_code == 200

        # 4. Approved visible in admin list
        resp = client.get("/v1/public-metadata/admin/samples?status=approved", headers=h)
        approved_ids = [s["public_sample_id"] for s in resp.json()["samples"]]
        assert sid in approved_ids

        # 5. Approved NOT in public feed
        feed = client.get("/v1/public-metadata/feed").json()
        assert sid not in [s["public_sample_id"] for s in feed["samples"]]

        # 6. Publish
        resp = client.post(f"/v1/public-metadata/publish/{sid}", headers=h)
        assert resp.status_code == 200

        # 7. Published in public feed
        feed = client.get("/v1/public-metadata/feed").json()
        pub_ids = [s["public_sample_id"] for s in feed["samples"]]
        assert sid in pub_ids

        # 8. Published sample accessible via single-sample endpoint
        resp = client.get(f"/v1/public-metadata/sample/{sid}")
        assert resp.status_code == 200
        assert resp.json()["headline"] == "Automated resolution completed with verified confidence"

        # 9. Verify public response has only allowed fields
        for key in resp.json():
            assert key in ALLOWED_RESPONSE_FIELDS

        # 10. Revoke
        resp = client.post(f"/v1/public-metadata/revoke/{sid}", headers=h)
        assert resp.status_code == 200

        # 11. Revoked NOT in public feed
        feed = client.get("/v1/public-metadata/feed").json()
        assert sid not in [s["public_sample_id"] for s in feed["samples"]]

        # 12. Revoked NOT accessible via single-sample endpoint
        resp = client.get(f"/v1/public-metadata/sample/{sid}")
        assert resp.status_code == 404

        # 13. Revoked still visible in admin list
        resp = client.get("/v1/public-metadata/admin/samples?status=revoked", headers=h)
        revoked_ids = [s["public_sample_id"] for s in resp.json()["samples"]]
        assert sid in revoked_ids

        # 14. Revoked is terminal — cannot re-approve or re-publish
        assert client.post(f"/v1/public-metadata/approve/{sid}", headers=h).status_code == 409
        assert client.post(f"/v1/public-metadata/publish/{sid}", headers=h).status_code == 409
