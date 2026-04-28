"""Tests for PMC pagination — feed and admin endpoints."""

import pytest
from apps.api.src.public_metadata.models import OutcomeClass, SampleStatus, PublicAuthoritySample
from apps.api.src.public_metadata.store import PublicMetadataStore
from apps.api.tests.conftest import ADMIN_TOKEN, VALID_TOKEN, auth_header


def _sample(sid: str, emitted_at: str = "2026-03-24T00:00:00Z"):
    return PublicAuthoritySample(
        public_sample_id=sid, status=SampleStatus.DRAFT,
        headline=f"Sample {sid}", summary="Summary",
        outcome_class=OutcomeClass.RESOLVED, integrity_hash="a" * 64,
        emitted_at=emitted_at,
    )


async def _seed_published(app, count: int):
    store = PublicMetadataStore(app.state.firestore_client)
    for i in range(count):
        s = _sample(f"pag_{i:03d}", f"2026-03-24T{i:02d}:00:00Z")
        await store.save_sample(s)
        await store.approve_sample(f"pag_{i:03d}")
        await store.publish_sample(f"pag_{i:03d}")


class TestFeedPaginationDefaults:
    @pytest.mark.asyncio
    async def test_default_limit_and_offset(self, client, app):
        await _seed_published(app, 3)
        resp = client.get("/v1/public-metadata/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert data["total"] == 3
        assert data["count"] == 3

    @pytest.mark.asyncio
    async def test_empty_feed_with_pagination(self, client):
        resp = client.get("/v1/public-metadata/feed?limit=10&offset=0")
        data = resp.json()
        assert data["total"] == 0
        assert data["count"] == 0
        assert data["samples"] == []


class TestFeedPaginationExplicit:
    @pytest.mark.asyncio
    async def test_limit_restricts_count(self, client, app):
        await _seed_published(app, 5)
        resp = client.get("/v1/public-metadata/feed?limit=2&offset=0")
        data = resp.json()
        assert data["count"] == 2
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_offset_skips(self, client, app):
        await _seed_published(app, 5)
        resp = client.get("/v1/public-metadata/feed?limit=2&offset=2")
        data = resp.json()
        assert data["count"] == 2
        assert data["offset"] == 2

    @pytest.mark.asyncio
    async def test_offset_past_end(self, client, app):
        await _seed_published(app, 3)
        resp = client.get("/v1/public-metadata/feed?limit=10&offset=100")
        data = resp.json()
        assert data["count"] == 0
        assert data["total"] == 3


class TestFeedPaginationMaxLimit:
    @pytest.mark.asyncio
    async def test_limit_clamped_to_max(self, client, app):
        await _seed_published(app, 3)
        resp = client.get("/v1/public-metadata/feed?limit=999")
        data = resp.json()
        assert data["limit"] == 100  # MAX_LIMIT


class TestFeedPaginationInvalid:
    def test_limit_zero_returns_400(self, client):
        resp = client.get("/v1/public-metadata/feed?limit=0")
        assert resp.status_code == 422 or resp.status_code == 400

    def test_limit_negative_returns_400(self, client):
        resp = client.get("/v1/public-metadata/feed?limit=-1")
        assert resp.status_code == 422 or resp.status_code == 400

    def test_offset_negative_returns_400(self, client):
        resp = client.get("/v1/public-metadata/feed?offset=-1")
        assert resp.status_code == 422 or resp.status_code == 400

    def test_non_integer_limit_returns_422(self, client):
        resp = client.get("/v1/public-metadata/feed?limit=abc")
        assert resp.status_code == 422


class TestFeedPaginationPrivacy:
    @pytest.mark.asyncio
    async def test_paginated_feed_still_strips_forbidden(self, client, app):
        await _seed_published(app, 1)
        resp = client.get("/v1/public-metadata/feed?limit=1")
        forbidden = {"tenant_id", "decision_id", "source_resolution_id", "correlation_id"}
        for s in resp.json()["samples"]:
            for f in forbidden:
                assert f not in s

    @pytest.mark.asyncio
    async def test_paginated_feed_published_only(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        await store.save_sample(_sample("pag_draft"))  # draft, not published
        await _seed_published(app, 2)
        resp = client.get("/v1/public-metadata/feed?limit=100")
        data = resp.json()
        for s in data["samples"]:
            assert s["status"] == "published"
        ids = [s["public_sample_id"] for s in data["samples"]]
        assert "pag_draft" not in ids


class TestAdminPaginationDefaults:
    @pytest.mark.asyncio
    async def test_admin_default_pagination(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        for i in range(3):
            await store.save_sample(_sample(f"adm_{i}"))
        resp = client.get("/v1/public-metadata/admin/samples", headers=auth_header(ADMIN_TOKEN))
        data = resp.json()
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_admin_filter_plus_pagination(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        for i in range(5):
            await store.save_sample(_sample(f"afp_{i}"))
        await store.approve_sample("afp_0")
        resp = client.get("/v1/public-metadata/admin/samples?status=approved&limit=10", headers=auth_header(ADMIN_TOKEN))
        data = resp.json()
        assert all(s["status"] == "approved" for s in data["samples"])
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_admin_limit_and_offset(self, client, app):
        store = PublicMetadataStore(app.state.firestore_client)
        for i in range(5):
            await store.save_sample(_sample(f"alo_{i}"))
        resp = client.get("/v1/public-metadata/admin/samples?limit=2&offset=1", headers=auth_header(ADMIN_TOKEN))
        data = resp.json()
        assert data["count"] == 2
        assert data["offset"] == 1
