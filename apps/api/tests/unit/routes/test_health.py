"""Tests for health probe endpoints."""

from apps.api.src.routes.health import mark_startup_complete, reset_startup_state


class TestLivenessProbe:
    def test_always_responds(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"
        assert "timestamp" in resp.json()


class TestStartupProbe:
    def test_healthy_after_startup(self, client):
        resp = client.get("/health/startup")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert resp.json()["checks"]["config"] == "ok"

    def test_unhealthy_before_startup(self, app):
        from fastapi.testclient import TestClient
        reset_startup_state()
        c = TestClient(app)
        resp = c.get("/health/startup")
        assert resp.json()["status"] == "unhealthy"
        mark_startup_complete()  # Restore


class TestReadinessProbe:
    def test_ready_after_startup(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
        assert "circuit_breakers" in resp.json()
