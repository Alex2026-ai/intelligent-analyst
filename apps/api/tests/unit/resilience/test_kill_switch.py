"""Tests for kill switch — platform + tenant scoping, audit trail."""

from apps.api.src.resilience.kill_switch import KillSwitchManager


class TestKillSwitch:
    def test_not_killed_by_default(self):
        ks = KillSwitchManager()
        assert ks.is_killed("resolution") is False

    def test_platform_kill(self):
        ks = KillSwitchManager()
        ks.activate("resolution", "admin-1", "Emergency shutdown")
        assert ks.is_killed("resolution") is True

    def test_deactivate(self):
        ks = KillSwitchManager()
        ks.activate("resolution", "admin-1", "Emergency")
        ks.deactivate("resolution", "admin-1", "Resolved")
        assert ks.is_killed("resolution") is False

    def test_tenant_scoped_kill(self):
        ks = KillSwitchManager()
        ks.activate("resolution", "admin-1", "Tenant issue", tenant_id="t1")
        assert ks.is_killed("resolution", tenant_id="t1") is True
        assert ks.is_killed("resolution", tenant_id="t2") is False

    def test_platform_overrides_tenant(self):
        ks = KillSwitchManager()
        ks.activate("resolution", "admin-1", "Global shutdown")
        # Platform kill applies to all tenants
        assert ks.is_killed("resolution", tenant_id="t1") is True

    def test_different_switches_independent(self):
        ks = KillSwitchManager()
        ks.activate("exports", "admin-1", "Pause exports")
        assert ks.is_killed("exports") is True
        assert ks.is_killed("resolution") is False


class TestKillSwitchAudit:
    def test_activation_logged(self):
        ks = KillSwitchManager()
        ks.activate("resolution", "admin-1", "Emergency")
        log = ks.get_audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "activate"
        assert log[0]["activated_by"] == "admin-1"
        assert log[0]["reason"] == "Emergency"

    def test_deactivation_logged(self):
        ks = KillSwitchManager()
        ks.activate("resolution", "admin-1", "Start")
        ks.deactivate("resolution", "admin-1", "End")
        log = ks.get_audit_log()
        assert len(log) == 2
        assert log[1]["action"] == "deactivate"

    def test_audit_includes_timestamp(self):
        ks = KillSwitchManager()
        ks.activate("exports", "admin-1", "Test")
        log = ks.get_audit_log()
        assert "timestamp" in log[0]
