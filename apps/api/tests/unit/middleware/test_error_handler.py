"""Tests for error handler — structured error format."""

from apps.api.src.middleware.error_handler import make_error_response
from ia_shared.models.errors import VALIDATION_ERROR


class TestMakeErrorResponse:
    def test_structure(self):
        resp = make_error_response(400, VALIDATION_ERROR, "Bad input", "trace-1")
        body = resp.body
        import json
        data = json.loads(body)
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["message"] == "Bad input"
        assert data["error"]["correlation_id"] == "trace-1"
        assert data["error"]["retry"] is False

    def test_retryable(self):
        import json
        resp = make_error_response(429, "RATE_LIMIT_EXCEEDED", "Too many", retry=True)
        data = json.loads(resp.body)
        assert data["error"]["retry"] is True

    def test_status_code(self):
        resp = make_error_response(404, "NOT_FOUND", "Missing")
        assert resp.status_code == 404
