import pytest
"""Tests for the Public Trust Feed contract — the canonical public-read surface.

Proves: empty feed returns 200, only published visible, drafts/approved/revoked hidden,
no tenant data leaked, no private fields in response.
"""

from apps.api.src.public_metadata.models import OutcomeClass, SampleStatus, PublicAuthoritySample
from apps.api.src.public_metadata.store import PublicMetadataStore
from apps.api.tests.conftest import ADMIN_TOKEN, VALID_TOKEN, auth_header


def _sample(sample_id: str, status: SampleStatus = SampleStatus.DRAFT) -> PublicAuthoritySample:
    return PublicAuthoritySample(
        public_sample_id=sample_id, status=status,
        headline="Verified resolution", summary="Deterministic summary",
        outcome_class=OutcomeClass.RESOLVED,
        workflow_stages=["Intake", "Analysis"],
        public_spec_anchors=["INV-002", "INV-006"],
        proof_summary="Verified through evidence lineage",
        integrity_hash="a" * 64, emitted_at="2026-03-23T00:00:00Z",
    )


class TestEmptyFeedContract:
    @pytest.mark.asyncio
    async def test_empty_feed_returns_200(self, client):
        resp = client.get("/v1/public-metadata/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["samples"] == []

    @pytest.mark.asyncio
    async def test_empty_feed_no_auth_required(self, client):
        """Feed is public — no Authorization header needed."""
        resp = client.get("/v1/public-metadata/feed")
        assert resp.status_code == 200


class TestFeedPublishedOnly:
    @pytest.mark.asyncio
    async def test_published_appears_in_feed(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_feed_1"))
        await store.approve_sample("pub_feed_1")
        await store.publish_sample("pub_feed_1")
        resp = client.get("/v1/public-metadata/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["samples"][0]["headline"] == "Verified resolution"

    @pytest.mark.asyncio
    async def test_draft_hidden_from_feed(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_draft"))
        resp = client.get("/v1/public-metadata/feed")
        drafts = [s for s in resp.json()["samples"] if s.get("public_sample_id") == "pub_draft"]
        assert len(drafts) == 0

    @pytest.mark.asyncio
    async def test_approved_hidden_from_feed(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_appr"))
        await store.approve_sample("pub_appr")
        resp = client.get("/v1/public-metadata/feed")
        approved = [s for s in resp.json()["samples"] if s.get("public_sample_id") == "pub_appr"]
        assert len(approved) == 0

    @pytest.mark.asyncio
    async def test_revoked_hidden_from_feed(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_rev"))
        await store.approve_sample("pub_rev")
        await store.publish_sample("pub_rev")
        await store.revoke_sample("pub_rev")
        resp = client.get("/v1/public-metadata/feed")
        revoked = [s for s in resp.json()["samples"] if s.get("public_sample_id") == "pub_rev"]
        assert len(revoked) == 0


class TestFeedSecurity:
    @pytest.mark.asyncio
    async def test_no_tenant_data_in_feed(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_sec"))
        await store.approve_sample("pub_sec")
        await store.publish_sample("pub_sec")
        resp = client.get("/v1/public-metadata/feed")
        feed_str = str(resp.json())
        assert "tenant" not in feed_str.lower()

    @pytest.mark.asyncio
    async def test_no_private_fields_in_feed(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_priv"))
        await store.approve_sample("pub_priv")
        await store.publish_sample("pub_priv")
        resp = client.get("/v1/public-metadata/feed")
        for sample in resp.json()["samples"]:
            assert "decision_id" not in sample
            assert "source_resolution_id" not in sample
            assert "tenant_id" not in sample
            assert "correlation_id" not in sample

    @pytest.mark.asyncio
    async def test_feed_response_deterministic(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_det"))
        await store.approve_sample("pub_det")
        await store.publish_sample("pub_det")
        r1 = client.get("/v1/public-metadata/feed").json()
        r2 = client.get("/v1/public-metadata/feed").json()
        assert r1 == r2


class TestSingleSampleEndpoint:
    @pytest.mark.asyncio
    async def test_published_sample_accessible(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_single"))
        await store.approve_sample("pub_single")
        await store.publish_sample("pub_single")
        resp = client.get("/v1/public-metadata/sample/pub_single")
        assert resp.status_code == 200
        assert resp.json()["headline"] == "Verified resolution"

    @pytest.mark.asyncio
    async def test_unpublished_sample_returns_404(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_hidden"))
        resp = client.get("/v1/public-metadata/sample/pub_hidden")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_sample_returns_404(self, client):
        resp = client.get("/v1/public-metadata/sample/does_not_exist")
        assert resp.status_code == 404


class TestAdminTransitionsViaRoutes:
    @pytest.mark.asyncio
    async def test_full_lifecycle_admin_to_feed(self, client, app):
        """draft → approve → publish → visible in feed → revoke → hidden."""
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pub_lifecycle"))
        h = auth_header(ADMIN_TOKEN)

        # Approve
        assert client.post("/v1/public-metadata/approve/pub_lifecycle", headers=h).status_code == 200
        assert client.get("/v1/public-metadata/sample/pub_lifecycle").status_code == 404  # not yet published

        # Publish
        assert client.post("/v1/public-metadata/publish/pub_lifecycle", headers=h).status_code == 200
        assert client.get("/v1/public-metadata/sample/pub_lifecycle").status_code == 200  # visible

        # Verify in feed
        feed = client.get("/v1/public-metadata/feed").json()
        ids = [s["public_sample_id"] for s in feed["samples"]]
        assert "pub_lifecycle" in ids

        # Revoke
        assert client.post("/v1/public-metadata/revoke/pub_lifecycle", headers=h).status_code == 200
        assert client.get("/v1/public-metadata/sample/pub_lifecycle").status_code == 404  # hidden again
