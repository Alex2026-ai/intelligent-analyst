"""Kill switch evaluation — platform and tenant scoped.

Every activation/deactivation writes to audit log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.api.src.resilience.config import KILL_SWITCHES


class KillSwitchManager:
    """Manages kill switch state.

    In production, backed by Firestore with 30s cache refresh.
    This implementation uses in-memory state for testing.
    """

    def __init__(self) -> None:
        self._platform_switches: dict[str, bool] = {}
        self._tenant_switches: dict[str, dict[str, bool]] = {}
        self._audit_log: list[dict[str, Any]] = []

    def is_killed(self, switch_name: str, tenant_id: str | None = None) -> bool:
        """Check if a capability is disabled.

        Checks platform-level first, then tenant-level.
        """
        # Platform-level
        if self._platform_switches.get(switch_name, False):
            return True

        # Tenant-level
        if tenant_id:
            tenant_switches = self._tenant_switches.get(tenant_id, {})
            if tenant_switches.get(switch_name, False):
                return True

        return False

    def activate(
        self,
        switch_name: str,
        activated_by: str,
        reason: str,
        tenant_id: str | None = None,
    ) -> None:
        """Activate a kill switch. Writes to audit log."""
        if tenant_id:
            if tenant_id not in self._tenant_switches:
                self._tenant_switches[tenant_id] = {}
            self._tenant_switches[tenant_id][switch_name] = True
        else:
            self._platform_switches[switch_name] = True

        self._audit_log.append({
            "action": "activate",
            "switch_name": switch_name,
            "tenant_id": tenant_id,
            "activated_by": activated_by,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def deactivate(
        self,
        switch_name: str,
        deactivated_by: str,
        reason: str,
        tenant_id: str | None = None,
    ) -> None:
        """Deactivate a kill switch. Writes to audit log."""
        if tenant_id:
            tenant_switches = self._tenant_switches.get(tenant_id, {})
            tenant_switches[switch_name] = False
        else:
            self._platform_switches[switch_name] = False

        self._audit_log.append({
            "action": "deactivate",
            "switch_name": switch_name,
            "tenant_id": tenant_id,
            "deactivated_by": deactivated_by,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Get all kill switch audit entries."""
        return list(self._audit_log)

    def get_active_switches(self) -> dict[str, bool]:
        """Get all platform-level switch states."""
        return dict(self._platform_switches)
