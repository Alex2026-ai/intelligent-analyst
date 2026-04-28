"""Tenant configuration repository — versioned config with history tracking.

Async-safe: all Firestore operations use _await_if_needed() and
_collect_stream() for dual sync/async backend support.
"""

from __future__ import annotations

from typing import Any, Optional

from apps.api.src.storage.firestore.base import BaseRepository

CONFIG_COLLECTION = "config"
HISTORY_COLLECTION = "config_history"


class ConfigRepository(BaseRepository):
    """Tenant configuration with version tracking."""

    async def get_config(self) -> Optional[dict[str, Any]]:
        """Get current tenant configuration."""
        doc = self._collection(CONFIG_COLLECTION).document("current").get()
        result = await self._await_if_needed(doc)
        if result is None:
            return None
        return result.to_dict() if hasattr(result, "to_dict") else result

    async def set_config(
        self,
        config_data: dict[str, Any],
        updated_by: str,
        change_reason: str,
    ) -> dict[str, Any]:
        """Update tenant configuration with version tracking.

        Increments config_version, stores history snapshot.
        """
        current = await self.get_config()
        version = (current.get("config_version", 0) if current else 0) + 1

        new_config = self._with_schema_version({
            "config_version": version,
            **config_data,
            "updated_at": self._now(),
        })
        await self._await_if_needed(
            self._collection(CONFIG_COLLECTION).document("current").set(new_config)
        )

        # Record in history
        history_entry = self._with_schema_version({
            "version": version,
            "updated_by": updated_by,
            "updated_at": self._now(),
            "change_reason": change_reason,
            "snapshot": config_data,
        })
        await self._await_if_needed(
            self._collection(HISTORY_COLLECTION).document(str(version)).set(history_entry)
        )

        return new_config

    async def get_history(self) -> list[dict[str, Any]]:
        """Get full config change history."""
        stream = self._collection(HISTORY_COLLECTION).stream()
        results = await self._collect_stream(stream)
        return [data for _, data in results]
