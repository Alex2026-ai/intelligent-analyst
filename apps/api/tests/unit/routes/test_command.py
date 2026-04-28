"""Tests for /v1/command endpoint."""

from apps.api.tests.conftest import VALID_TOKEN, REVIEWER_TOKEN, auth_header


class TestCommandNavigation:
    def test_goto_resolutions(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "goto resolutions"},
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "NAVIGATE"
        assert data["nav_target"] == "/resolutions"

    def test_goto_dashboard(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "go dashboard"},
            headers=auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["nav_target"] == "/"

    def test_goto_review(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "open review"},
            headers=auth_header(),
        )
        assert resp.json()["intent"] == "NAVIGATE"
        assert resp.json()["nav_target"] == "/review"

    def test_shorthand_nav(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "admin"},
            headers=auth_header(),
        )
        assert resp.json()["intent"] == "NAVIGATE"
        assert resp.json()["nav_target"] == "/admin"

    def test_unknown_destination(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "goto nonexistent"},
            headers=auth_header(),
        )
        assert resp.json()["intent"] == "UNKNOWN"


class TestCommandResolve:
    def test_resolve_file(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "resolve --file=report.pdf"},
            headers=auth_header(),
        )
        data = resp.json()
        assert data["intent"] == "RESOLVE"
        assert data["nav_target"] == "/resolutions"
        assert data["payload"]["correlation_id"]
        assert data["payload"]["source"] == "report.pdf"

    def test_resolve_inline(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "resolve quarterly earnings report"},
            headers=auth_header(),
        )
        assert resp.json()["intent"] == "RESOLVE"


class TestCommandConfig:
    def test_config_command(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "config confidence_threshold"},
            headers=auth_header(),
        )
        assert resp.json()["intent"] == "CONFIG"
        assert resp.json()["nav_target"] == "/admin"

    def test_set_command(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "set review_sla_hours 48"},
            headers=auth_header(),
        )
        assert resp.json()["intent"] == "CONFIG"


class TestCommandEdgeCases:
    def test_empty_command(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": ""},
            headers=auth_header(),
        )
        assert resp.json()["intent"] == "UNKNOWN"

    def test_requires_auth(self, client):
        resp = client.post("/v1/command", json={"command": "goto resolutions"})
        assert resp.status_code == 401

    def test_response_includes_tenant(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "goto resolutions"},
            headers=auth_header(),
        )
        assert resp.json()["tenant_id"] == "tenant-1"


class TestDryRun:
    def test_dry_run_resolve_returns_plan(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "resolve --file=test.pdf", "dry_run": True},
            headers=auth_header(),
        )
        data = resp.json()
        assert data["dry_run"] is True
        assert "execution_plan" in data
        plan = data["execution_plan"]
        assert plan["intent"] == "RESOLVE"
        assert plan["tenant_partition"] == "tenants/tenant-1"
        assert plan["pii_policy"] == "mask_before_llm"
        assert len(plan["steps"]) == 6
        assert plan["steps"][0]["action"] == "pii_scan"

    def test_dry_run_navigate_returns_plan(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "goto resolutions", "dry_run": True},
            headers=auth_header(),
        )
        data = resp.json()
        assert data["dry_run"] is True
        plan = data["execution_plan"]
        assert plan["steps"][0]["action"] == "navigate"

    def test_dry_run_config_returns_plan(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "config confidence_threshold", "dry_run": True},
            headers=auth_header(),
        )
        plan = resp.json()["execution_plan"]
        assert plan["data_scope"] == "tenants/tenant-1/config"
        assert len(plan["steps"]) == 3

    def test_non_dry_run_no_plan(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "resolve --file=test.pdf", "dry_run": False},
            headers=auth_header(),
        )
        data = resp.json()
        assert "execution_plan" not in data
        assert data["intent"] == "RESOLVE"

    def test_correlation_id_format(self, client):
        resp = client.post(
            "/v1/command",
            json={"command": "resolve --file=test.pdf"},
            headers=auth_header(),
        )
        cid = resp.json()["payload"]["correlation_id"]
        assert cid.startswith("cmd_")
        assert len(cid) == 16  # cmd_ + 12 hex chars


class TestTenantPartition:
    def test_partition_scopes_collections(self):
        from apps.api.src.storage.firestore.client import InMemoryFirestore
        from apps.api.src.lib.db import get_tenant_partition

        db = InMemoryFirestore()
        p = get_tenant_partition(db, "tampa_re")
        assert p.partition_path == "tenants/tampa_re"

        # Write via partition
        p.resolutions().add({"resolution_id": "r1", "status": "resolved"}, "r1")

        # Read back — should be scoped
        results = p.resolutions().stream()
        assert len(results) == 1
        assert results[0][1]["resolution_id"] == "r1"

        # Different tenant partition should see nothing
        p2 = get_tenant_partition(db, "madrid_re")
        results2 = p2.resolutions().stream()
        assert len(results2) == 0
