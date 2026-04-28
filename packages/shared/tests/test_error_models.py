"""Tests for error response models and error code constants."""

import pytest
from pydantic import ValidationError

from ia_shared.models.errors import (
    ALL_ERROR_CODES,
    AUTHENTICATION_REQUIRED,
    BATCH_TOO_LARGE,
    CASE_ALREADY_DECIDED,
    DOCUMENT_TOO_LARGE,
    DUPLICATE_REQUEST,
    EXPORT_PRECONDITION_FAILED,
    ErrorDetail,
    ErrorResponse,
    INSUFFICIENT_ROLE,
    INVALID_DOCUMENT_TYPE,
    NOTES_TOO_SHORT,
    RATE_LIMIT_EXCEEDED,
    RESOLUTION_AMBIGUOUS,
    RESOURCE_NOT_FOUND,
    SERVICE_DEGRADED,
    TENANT_MISMATCH,
    TOKEN_EXPIRED,
    VALIDATION_ERROR,
)


class TestErrorCodes:
    def test_all_codes_are_strings(self):
        for code in ALL_ERROR_CODES:
            assert isinstance(code, str)

    def test_all_codes_uppercase(self):
        for code in ALL_ERROR_CODES:
            assert code == code.upper()

    def test_expected_count(self):
        """All 16 error codes from contracts.md are defined."""
        assert len(ALL_ERROR_CODES) == 16

    def test_specific_codes_exist(self):
        expected = {
            VALIDATION_ERROR,
            DOCUMENT_TOO_LARGE,
            BATCH_TOO_LARGE,
            INVALID_DOCUMENT_TYPE,
            NOTES_TOO_SHORT,
            EXPORT_PRECONDITION_FAILED,
            AUTHENTICATION_REQUIRED,
            TOKEN_EXPIRED,
            INSUFFICIENT_ROLE,
            TENANT_MISMATCH,
            RESOURCE_NOT_FOUND,
            DUPLICATE_REQUEST,
            CASE_ALREADY_DECIDED,
            RATE_LIMIT_EXCEEDED,
            RESOLUTION_AMBIGUOUS,
            SERVICE_DEGRADED,
        }
        assert expected == ALL_ERROR_CODES


class TestErrorResponse:
    def test_valid(self):
        resp = ErrorResponse(
            error=ErrorDetail(
                code=VALIDATION_ERROR,
                message="Field 'document_type' is required",
                correlation_id="trace-123",
                retry=False,
            )
        )
        assert resp.error.code == "VALIDATION_ERROR"
        assert resp.error.retry is False

    def test_retryable_error(self):
        resp = ErrorResponse(
            error=ErrorDetail(
                code=RATE_LIMIT_EXCEEDED,
                message="Rate limit exceeded for tenant",
                correlation_id="trace-456",
                retry=True,
            )
        )
        assert resp.error.retry is True

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            ErrorDetail(
                code=VALIDATION_ERROR,
                message="test",
                # missing correlation_id and retry
            )

    def test_missing_error_field(self):
        with pytest.raises(ValidationError):
            ErrorResponse()
