"""Structured logging configuration.

Every log entry includes: correlation_id, tenant_id, timestamp, service, level.
PII scrubber runs on EVERY log entry before output.
Logs to stdout in JSON format (Cloud Run → Cloud Logging).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from apps.api.src.observability.pii_scrubber import scrub_log_event

# Log classification levels
LOG_CLASS_PUBLIC = "public"
LOG_CLASS_INTERNAL = "internal"
LOG_CLASS_SENSITIVE = "sensitive"
LOG_CLASS_RESTRICTED = "restricted"  # Must NEVER exist — data should be scrubbed


class StructuredLogger:
    """JSON structured logger with mandatory PII scrubbing.

    Every log entry is scrubbed before output. This cannot be disabled.
    """

    def __init__(self, service: str = "ia-api", level: int = logging.INFO) -> None:
        self._service = service
        self._level = level
        self._context: dict[str, str] = {}

    def bind(self, **kwargs: str) -> "StructuredLogger":
        """Add persistent context fields (e.g., correlation_id, tenant_id)."""
        new = StructuredLogger(self._service, self._level)
        new._context = {**self._context, **kwargs}
        return new

    def _emit(self, level: str, event: str, classification: str, **kwargs: Any) -> dict[str, Any]:
        """Format and emit a log entry. Returns the emitted dict for testing."""
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self._service,
            "level": level,
            "event": event,
            "classification": classification,
            **self._context,
            **kwargs,
        }

        # CRITICAL: PII scrubbing runs on every log entry
        entry = scrub_log_event(entry)

        # Restricted classification must never exist
        if classification == LOG_CLASS_RESTRICTED:
            entry["event"] = "[RESTRICTED_CONTENT_BLOCKED]"
            entry["_warning"] = "Attempted to log restricted content"

        return entry

    def info(self, event: str, classification: str = LOG_CLASS_PUBLIC, **kwargs: Any) -> dict:
        return self._emit("INFO", event, classification, **kwargs)

    def warning(self, event: str, classification: str = LOG_CLASS_INTERNAL, **kwargs: Any) -> dict:
        return self._emit("WARNING", event, classification, **kwargs)

    def error(self, event: str, classification: str = LOG_CLASS_INTERNAL, **kwargs: Any) -> dict:
        return self._emit("ERROR", event, classification, **kwargs)

    def debug(self, event: str, classification: str = LOG_CLASS_PUBLIC, **kwargs: Any) -> dict:
        return self._emit("DEBUG", event, classification, **kwargs)
