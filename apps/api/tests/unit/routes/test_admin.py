"""Tests for admin endpoints — RBAC enforcement (FP-011)."""

from apps.api.tests.conftest import (
    ADMIN_TOKEN, REVIEWER_TOKEN, VALID_TOKEN, auth_header,
)


class TestAdminRBAC:
    def test_analyst_cannot_access_config(self, client):
        resp = client.get("/v1/admin/config", headers=auth_header(VALID_TOKEN))
        assert resp.status_code == 403

    def test_reviewer_cannot_access_config(self, client):
        resp = client.get("/v1/admin/config", headers=auth_header(REVIEWER_TOKEN))
        assert resp.status_code == 403

    def test_admin_can_access_config(self, client):
        resp = client.get("/v1/admin/config", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 200
        assert "config" in resp.json()

    def test_analyst_cannot_list_users(self, client):
        resp = client.get("/v1/admin/users", headers=auth_header(VALID_TOKEN))
        assert resp.status_code == 403

    def test_admin_can_list_users(self, client):
        resp = client.get("/v1/admin/users", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 200
