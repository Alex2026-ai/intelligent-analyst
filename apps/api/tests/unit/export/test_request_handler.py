"""Tests for export request handler."""

from apps.api.src.export.request_handler import ExportRequestHandler


class MockPublisher:
    def __init__(self):
        self.messages = []
    def publish(self, msg):
        self.messages.append(msg)


class TestExportRequestHandler:
    def test_create_export(self):
        handler = ExportRequestHandler()
        result = handler.request_export("r1", "pdf", requested_by="u1", tenant_id="t1")
        assert result["status"] == "queued"
        assert result["format"] == "pdf"
        assert result["export_id"]

    def test_publishes_event(self):
        pub = MockPublisher()
        handler = ExportRequestHandler(event_publisher=pub)
        handler.request_export("r1", "json", tenant_id="t1")
        assert len(pub.messages) == 1
        assert pub.messages[0]["event_type"] == "export.requested"

    def test_get_status(self):
        handler = ExportRequestHandler()
        result = handler.request_export("r1", "csv")
        status = handler.get_status(result["export_id"])
        assert status is not None
        assert status["status"] == "queued"

    def test_update_status_complete(self):
        handler = ExportRequestHandler()
        result = handler.request_export("r1", "pdf")
        handler.update_status(result["export_id"], "complete", download_url="https://example.com/file")
        status = handler.get_status(result["export_id"])
        assert status["status"] == "complete"
        assert status["download_url"] == "https://example.com/file"
        assert status["completed_at"] is not None

    def test_idempotent_status_check(self):
        handler = ExportRequestHandler()
        assert handler.get_status("nonexistent") is None
