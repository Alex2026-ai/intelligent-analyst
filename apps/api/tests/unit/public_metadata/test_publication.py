import pytest
"""Tests for Phase 3A publication contract — lifecycle, public feed, admin actions."""

import logging

from apps.api.src.public_metadata.events import emit_publication_event
from apps.api.src.public_metadata.models import OutcomeClass, SampleStatus
from apps.api.src.public_metadata.store import PublicMetadataStore, SAMPLES_PATH, DECISIONS_PATH
from apps.api.src.storage.firestore.client import InMemoryFirestore
from apps.api.tests.conftest import ADMIN_TOKEN, VALID_TOKEN, auth_header


def _draft_sample(sample_id: str = "pub_test001") -> dict:
    from apps.api.src.public_metadata.models import PublicAuthoritySample
    s = PublicAuthoritySample(
        public_sample_id=sample_id, status=SampleStatus.DRAFT,
        headline="Test headline", summary="Test summary",
        outcome_class=OutcomeClass.RESOLVED, integrity_hash="a" * 64, emitted_at="2026-03-23T00:00:00Z",
    )
    return s


async def _store_with_draft(sample_id: str = "pub_test001"):
    db = InMemoryFirestore()
    store = PublicMetadataStore(db)
    await store.save_sample(_draft_sample(sample_id))
    return store


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

class TestLifecycleTransitions:
    @pytest.mark.asyncio
    async def test_draft_to_approved(self):
        store = await _store_with_draft()
        assert await store.approve_sample("pub_test001")
        s = await store.get_sample("pub_test001")
        assert s["status"] == "approved"

    @pytest.mark.asyncio
    async def test_approved_to_published(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        assert await store.publish_sample("pub_test001")
        s = await store.get_sample("pub_test001")
        assert s["status"] == "published"

    @pytest.mark.asyncio
    async def test_published_to_revoked(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        await store.publish_sample("pub_test001")
        assert await store.revoke_sample("pub_test001")
        s = await store.get_sample("pub_test001")
        assert s["status"] == "revoked"

    @pytest.mark.asyncio
    async def test_approved_to_revoked(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        assert await store.revoke_sample("pub_test001")

    @pytest.mark.asyncio
    async def test_cannot_publish_draft_directly(self):
        store = await _store_with_draft()
        assert await store.publish_sample("pub_test001") is False

    @pytest.mark.asyncio
    async def test_cannot_approve_published(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        await store.publish_sample("pub_test001")
        assert await store.approve_sample("pub_test001") is False

    @pytest.mark.asyncio
    async def test_revoked_is_terminal(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        await store.revoke_sample("pub_test001")
        assert await store.approve_sample("pub_test001") is False
        assert await store.publish_sample("pub_test001") is False

    @pytest.mark.asyncio
    async def test_nonexistent_sample_returns_false(self):
        store = PublicMetadataStore(InMemoryFirestore())
        assert await store.approve_sample("nope") is False
        assert await store.publish_sample("nope") is False
        assert await store.revoke_sample("nope") is False


# ---------------------------------------------------------------------------
# Public read contract
# ---------------------------------------------------------------------------

class TestPublicReadContract:
    @pytest.mark.asyncio
    async def test_list_published_excludes_draft(self):
        store = await _store_with_draft()
        assert await store.list_published() == []

    @pytest.mark.asyncio
    async def test_list_published_excludes_approved(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        assert await store.list_published() == []

    @pytest.mark.asyncio
    async def test_list_published_includes_published(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        await store.publish_sample("pub_test001")
        result = await store.list_published()
        assert len(result) == 1
        assert result[0]["status"] == "published"

    @pytest.mark.asyncio
    async def test_list_published_excludes_revoked(self):
        store = await _store_with_draft()
        await store.approve_sample("pub_test001")
        await store.publish_sample("pub_test001")
        await store.revoke_sample("pub_test001")
        assert await store.list_published() == []


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------

class TestFeedEndpoint:
    @pytest.mark.asyncio
    async def test_feed_returns_empty_initially(self, client):
        resp = client.get("/v1/public-metadata/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["samples"] == []

    @pytest.mark.asyncio
    async def test_sample_endpoint_rejects_draft(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_draft_sample("pub_draft"))
        resp = client.get("/v1/public-metadata/sample/pub_draft")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_sample_endpoint_rejects_approved(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_draft_sample("pub_appr"))
        await store.approve_sample("pub_appr")
        resp = client.get("/v1/public-metadata/sample/pub_appr")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_sample_endpoint_returns_published(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_draft_sample("pub_live"))
        await store.approve_sample("pub_live")
        await store.publish_sample("pub_live")
        resp = client.get("/v1/public-metadata/sample/pub_live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["headline"] == "Test headline"
        assert "tenant_id" not in data

    @pytest.mark.asyncio
    async def test_sample_endpoint_rejects_revoked(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_draft_sample("pub_revoked"))
        await store.approve_sample("pub_revoked")
        await store.publish_sample("pub_revoked")
        await store.revoke_sample("pub_revoked")
        resp = client.get("/v1/public-metadata/sample/pub_revoked")
        assert resp.status_code == 404


class TestAdminActions:
    @pytest.mark.asyncio
    async def test_approve_requires_admin(self, client):
        resp = client.post("/v1/public-metadata/approve/x", headers=auth_header(VALID_TOKEN))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_publish_requires_admin(self, client):
        resp = client.post("/v1/public-metadata/publish/x", headers=auth_header(VALID_TOKEN))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_revoke_requires_admin(self, client):
        resp = client.post("/v1/public-metadata/revoke/x", headers=auth_header(VALID_TOKEN))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_404(self, client):
        resp = client.post("/v1/public-metadata/approve/nope", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_publish_nonexistent_returns_404(self, client):
        resp = client.post("/v1/public-metadata/publish/nope", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_publish_draft_returns_409(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_draft_sample("pub_bad"))
        resp = client.post("/v1/public-metadata/publish/pub_bad", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_full_lifecycle_via_routes(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_draft_sample("pub_full"))
        h = auth_header(ADMIN_TOKEN)
        assert client.post("/v1/public-metadata/approve/pub_full", headers=h).status_code == 200
        assert client.post("/v1/public-metadata/publish/pub_full", headers=h).status_code == 200
        assert client.get("/v1/public-metadata/sample/pub_full").status_code == 200
        assert client.post("/v1/public-metadata/revoke/pub_full", headers=h).status_code == 200
        assert client.get("/v1/public-metadata/sample/pub_full").status_code == 404


class TestStorageSeparation:
    @pytest.mark.asyncio
    async def test_platform_paths_only(self):
        assert "tenants/" not in SAMPLES_PATH
        assert "tenants/" not in DECISIONS_PATH
        assert "tenants/" not in SAMPLES_PATH

    @pytest.mark.asyncio
    async def test_no_tenant_data_in_public_response(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_draft_sample("pub_clean"))
        await store.approve_sample("pub_clean")
        await store.publish_sample("pub_clean")
        resp = client.get("/v1/public-metadata/sample/pub_clean")
        data = resp.json()
        data_str = str(data)
        assert "tenant" not in data_str.lower()


class TestPublicationEvents:
    @pytest.mark.asyncio
    async def test_approve_emits_events(self, caplog):
        with caplog.at_level(logging.INFO, logger="ia.pmc.events"):
            emit_publication_event("approve", "attempted", "pub_1")
            emit_publication_event("approve", "succeeded", "pub_1")
        msgs = [r.getMessage() for r in caplog.records]
        assert any("approve_attempted" in m for m in msgs)
        assert any("approve_succeeded" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_failed_event_logged_as_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="ia.pmc.events"):
            emit_publication_event("publish", "failed", "pub_1", "not found")
        assert any("publish_failed" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_event_contains_no_private_data(self):
        event = emit_publication_event("revoke", "succeeded", "pub_123")
        assert "tenant" not in str(event)
        assert "content" not in event
