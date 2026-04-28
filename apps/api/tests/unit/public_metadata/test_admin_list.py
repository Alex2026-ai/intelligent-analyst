import pytest
"""Tests for the PMC admin listing endpoint and full admin lifecycle."""

from apps.api.src.public_metadata.models import OutcomeClass, SampleStatus, PublicAuthoritySample
from apps.api.src.public_metadata.store import PublicMetadataStore
from apps.api.tests.conftest import ADMIN_TOKEN, VALID_TOKEN, auth_header


def _sample(sample_id: str, status: SampleStatus = SampleStatus.DRAFT, emitted_at: str = "2026-03-23T00:00:00Z"):
    return PublicAuthoritySample(
        public_sample_id=sample_id, status=status,
        headline=f"Sample {sample_id}", summary="Test summary",
        outcome_class=OutcomeClass.RESOLVED, integrity_hash="a" * 64,
        emitted_at=emitted_at,
    )


class TestAdminListEndpoint:
    @pytest.mark.asyncio
    async def test_requires_admin(self, client):
        resp = client.get("/v1/public-metadata/admin/samples", headers=auth_header(VALID_TOKEN))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_all_statuses(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-draft", SampleStatus.DRAFT))
        await store.save_sample(_sample("s-pub", SampleStatus.DRAFT))
        await store.approve_sample("s-pub")
        await store.publish_sample("s-pub")
        resp = client.get("/v1/public-metadata/admin/samples", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2
        ids = [s["public_sample_id"] for s in data["samples"]]
        assert "s-draft" in ids
        assert "s-pub" in ids

    @pytest.mark.asyncio
    async def test_filter_by_draft(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-d1", SampleStatus.DRAFT))
        await store.save_sample(_sample("s-d2", SampleStatus.DRAFT))
        await store.approve_sample("s-d2")
        resp = client.get("/v1/public-metadata/admin/samples?status=draft", headers=auth_header(ADMIN_TOKEN))
        data = resp.json()
        statuses = {s["status"] for s in data["samples"]}
        assert statuses == {"draft"}

    @pytest.mark.asyncio
    async def test_filter_by_approved(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-a1", SampleStatus.DRAFT))
        await store.approve_sample("s-a1")
        resp = client.get("/v1/public-metadata/admin/samples?status=approved", headers=auth_header(ADMIN_TOKEN))
        ids = [s["public_sample_id"] for s in resp.json()["samples"]]
        assert "s-a1" in ids

    @pytest.mark.asyncio
    async def test_filter_by_published(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-p1"))
        await store.approve_sample("s-p1")
        await store.publish_sample("s-p1")
        resp = client.get("/v1/public-metadata/admin/samples?status=published", headers=auth_header(ADMIN_TOKEN))
        ids = [s["public_sample_id"] for s in resp.json()["samples"]]
        assert "s-p1" in ids

    @pytest.mark.asyncio
    async def test_filter_by_revoked(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-r1"))
        await store.approve_sample("s-r1")
        await store.revoke_sample("s-r1")
        resp = client.get("/v1/public-metadata/admin/samples?status=revoked", headers=auth_header(ADMIN_TOKEN))
        ids = [s["public_sample_id"] for s in resp.json()["samples"]]
        assert "s-r1" in ids

    @pytest.mark.asyncio
    async def test_invalid_status_returns_400(self, client):
        resp = client.get("/v1/public-metadata/admin/samples?status=bogus", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_result(self, client):
        resp = client.get("/v1/public-metadata/admin/samples?status=draft", headers=auth_header(ADMIN_TOKEN))
        data = resp.json()
        assert data["count"] == 0
        assert data["samples"] == []

    @pytest.mark.asyncio
    async def test_no_private_payload_in_response(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-safe"))
        resp = client.get("/v1/public-metadata/admin/samples", headers=auth_header(ADMIN_TOKEN))
        for s in resp.json()["samples"]:
            assert "tenant_id" not in s
            assert "decision_id" not in s
            assert "source_resolution_id" not in s


class TestPublicFeedUnchanged:
    """Public /feed contract must not be affected by admin endpoint."""

    @pytest.mark.asyncio
    async def test_feed_still_published_only(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-feed-d", SampleStatus.DRAFT))
        await store.save_sample(_sample("s-feed-p", SampleStatus.DRAFT))
        await store.approve_sample("s-feed-p")
        await store.publish_sample("s-feed-p")
        resp = client.get("/v1/public-metadata/feed")
        data = resp.json()
        ids = [s["public_sample_id"] for s in data["samples"]]
        assert "s-feed-p" in ids
        assert "s-feed-d" not in ids


class TestFullLifecycleViaAdmin:
    @pytest.mark.asyncio
    async def test_draft_to_published_to_revoked(self, client, app):
        """Full operator workflow: see draft → approve → publish → verify in feed → revoke → gone."""
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("s-lc"))
        h = auth_header(ADMIN_TOKEN)

        # Draft visible in admin
        resp = client.get("/v1/public-metadata/admin/samples?status=draft", headers=h)
        assert any(s["public_sample_id"] == "s-lc" for s in resp.json()["samples"])

        # Approve
        assert client.post("/v1/public-metadata/approve/s-lc", headers=h).status_code == 200
        resp = client.get("/v1/public-metadata/admin/samples?status=approved", headers=h)
        assert any(s["public_sample_id"] == "s-lc" for s in resp.json()["samples"])

        # Not yet in public feed
        feed = client.get("/v1/public-metadata/feed").json()
        assert "s-lc" not in [s["public_sample_id"] for s in feed["samples"]]

        # Publish
        assert client.post("/v1/public-metadata/publish/s-lc", headers=h).status_code == 200

        # Now in public feed
        feed = client.get("/v1/public-metadata/feed").json()
        assert "s-lc" in [s["public_sample_id"] for s in feed["samples"]]

        # Revoke
        assert client.post("/v1/public-metadata/revoke/s-lc", headers=h).status_code == 200

        # Gone from public feed
        feed = client.get("/v1/public-metadata/feed").json()
        assert "s-lc" not in [s["public_sample_id"] for s in feed["samples"]]

        # Still visible in admin as revoked
        resp = client.get("/v1/public-metadata/admin/samples?status=revoked", headers=h)
        assert any(s["public_sample_id"] == "s-lc" for s in resp.json()["samples"])
