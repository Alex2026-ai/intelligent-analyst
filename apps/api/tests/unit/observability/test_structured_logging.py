"""Tests for structured logging — required fields, PII scrubbing."""

from apps.api.src.observability.logging import (
    LOG_CLASS_PUBLIC,
    LOG_CLASS_RESTRICTED,
    StructuredLogger,
)


class TestStructuredLogger:
    def test_required_fields_present(self):
        logger = StructuredLogger()
        entry = logger.info("test event")
        assert "timestamp" in entry
        assert "service" in entry
        assert "level" in entry
        assert "event" in entry
        assert entry["service"] == "ia-api"
        assert entry["level"] == "INFO"

    def test_bind_adds_context(self):
        logger = StructuredLogger().bind(
            correlation_id="trace-1", tenant_id="t1"
        )
        entry = logger.info("test")
        assert entry["correlation_id"] == "trace-1"
        assert entry["tenant_id"] == "t1"

    def test_pii_scrubbed_in_event(self):
        logger = StructuredLogger()
        entry = logger.info("User john@example.com logged in")
        assert "john@example.com" not in entry["event"]
        assert "[EMAIL_REDACTED]" in entry["event"]

    def test_pii_scrubbed_in_kwargs(self):
        logger = StructuredLogger()
        entry = logger.info("login", email="user@test.com")
        assert "user@test.com" not in entry["email"]

    def test_restricted_classification_blocked(self):
        logger = StructuredLogger()
        entry = logger.info("secret data", classification=LOG_CLASS_RESTRICTED)
        assert entry["event"] == "[RESTRICTED_CONTENT_BLOCKED]"

    def test_log_levels(self):
        logger = StructuredLogger()
        assert logger.info("test")["level"] == "INFO"
        assert logger.warning("test")["level"] == "WARNING"
        assert logger.error("test")["level"] == "ERROR"
        assert logger.debug("test")["level"] == "DEBUG"

    def test_bind_immutability(self):
        base = StructuredLogger()
        bound = base.bind(tenant_id="t1")
        entry_base = base.info("test")
        entry_bound = bound.info("test")
        assert "tenant_id" not in entry_base
        assert entry_bound["tenant_id"] == "t1"
