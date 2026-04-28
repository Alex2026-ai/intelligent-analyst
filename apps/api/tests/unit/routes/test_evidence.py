"""Tests for evidence endpoints."""

from apps.api.tests.conftest import VALID_TOKEN, auth_header


class TestGetEvidence:
    def test_not_found(self, client):
        resp = client.get("/v1/evidence/nonexistent", headers=auth_header())
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/v1/evidence/some-id")
        assert resp.status_code == 401
