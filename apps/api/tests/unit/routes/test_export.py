"""Tests for export endpoints."""

from apps.api.tests.conftest import VALID_TOKEN, auth_header


class TestRequestExport:
    def test_valid_export_request(self, client):
        resp = client.post(
            "/v1/export",
            json={"resolution_id": "r1", "format": "pdf"},
            headers=auth_header(),
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert data["format"] == "pdf"
        assert "export_id" in data

    def test_invalid_format(self, client):
        resp = client.post(
            "/v1/export",
            json={"resolution_id": "r1", "format": "docx"},
            headers=auth_header(),
        )
        assert resp.status_code == 400

    def test_missing_resolution_id(self, client):
        resp = client.post(
            "/v1/export",
            json={"format": "pdf"},
            headers=auth_header(),
        )
        assert resp.status_code == 400

    def test_requires_auth(self, client):
        resp = client.post("/v1/export", json={"resolution_id": "r1", "format": "pdf"})
        assert resp.status_code == 401


class TestGetExportStatus:
    def test_not_found(self, client):
        resp = client.get("/v1/export/nonexistent", headers=auth_header())
        assert resp.status_code == 404
