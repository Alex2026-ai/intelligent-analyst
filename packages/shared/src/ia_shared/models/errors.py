"""Error response model and error code constants.

All error codes are string constants — never magic strings in application code (FP-002).
Error format matches contracts.md exactly.
"""

from pydantic import BaseModel, ConfigDict

# --- Error code constants ---
# 400 Bad Request
VALIDATION_ERROR: str = "VALIDATION_ERROR"
DOCUMENT_TOO_LARGE: str = "DOCUMENT_TOO_LARGE"
BATCH_TOO_LARGE: str = "BATCH_TOO_LARGE"
INVALID_DOCUMENT_TYPE: str = "INVALID_DOCUMENT_TYPE"
NOTES_TOO_SHORT: str = "NOTES_TOO_SHORT"
EXPORT_PRECONDITION_FAILED: str = "EXPORT_PRECONDITION_FAILED"

# 401 Unauthorized
AUTHENTICATION_REQUIRED: str = "AUTHENTICATION_REQUIRED"
TOKEN_EXPIRED: str = "TOKEN_EXPIRED"

# 403 Forbidden
INSUFFICIENT_ROLE: str = "INSUFFICIENT_ROLE"
TENANT_MISMATCH: str = "TENANT_MISMATCH"

# 404 Not Found
RESOURCE_NOT_FOUND: str = "RESOURCE_NOT_FOUND"

# 409 Conflict
DUPLICATE_REQUEST: str = "DUPLICATE_REQUEST"
CASE_ALREADY_DECIDED: str = "CASE_ALREADY_DECIDED"

# 429 Too Many Requests
RATE_LIMIT_EXCEEDED: str = "RATE_LIMIT_EXCEEDED"

# 500 Internal Server Error
RESOLUTION_AMBIGUOUS: str = "RESOLUTION_AMBIGUOUS"

# 503 Service Unavailable
SERVICE_DEGRADED: str = "SERVICE_DEGRADED"

ALL_ERROR_CODES: frozenset[str] = frozenset({
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
})


class ErrorDetail(BaseModel):
    """Inner error object matching the contracts.md error response format."""

    model_config = ConfigDict(strict=True)

    code: str
    """Machine-readable error code (one of the constants above)."""

    message: str
    """Human-readable error description."""

    correlation_id: str
    """Trace ID for support and debugging."""

    retry: bool
    """Whether the client should retry this request."""


class ErrorResponse(BaseModel):
    """Top-level error response envelope.

    All API error responses use this format.
    """

    model_config = ConfigDict(strict=True)

    error: ErrorDetail
