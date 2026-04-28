"""Tenant configuration and user models.

These are internal/storage models — tenant_id appears here because these
represent stored records, not request bodies (INV-005).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ia_shared.constants import SCHEMA_VERSION


class Role(str, Enum):
    """User roles for RBAC enforcement.

    Role hierarchy: viewer < analyst < reviewer < tenant_admin < platform_admin.
    Each role includes all permissions of lower roles.
    """

    VIEWER = "viewer"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    TENANT_ADMIN = "tenant_admin"
    PLATFORM_ADMIN = "platform_admin"


class UserRecord(BaseModel):
    """A user within a tenant.

    Storable model — user_id and role are extracted from JWT tokens at runtime.
    This model represents the persisted user record.
    """

    model_config = ConfigDict(strict=True)

    _schema_version: str = SCHEMA_VERSION

    user_id: str = Field(..., description="UUID of the user")
    tenant_id: str = Field(..., description="Tenant this user belongs to")
    role: Role
    email: str
    display_name: str
    active: bool = True
    created_at: str = Field(..., description="ISO 8601 timestamp")
    updated_at: str = Field(..., description="ISO 8601 timestamp")


class TenantConfig(BaseModel):
    """Per-tenant configuration.

    All behavioral thresholds live here — never hardcoded (INV-011, FP-002).
    Changes to tenant config are versioned and audited (FP-009).
    """

    model_config = ConfigDict(strict=True)

    _schema_version: str = SCHEMA_VERSION

    tenant_id: str = Field(..., description="UUID of the tenant")
    tenant_name: str
    region: str = Field(..., description="GCP region (us-central1 or europe-west1)")
    active: bool = True

    # Resolution thresholds (INV-011: no silent thresholds)
    confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for auto-resolution",
    )
    high_impact_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence above which resolution is classified as high-impact",
    )

    # Rate limiting
    rate_limit_per_minute: int = Field(
        default=100, ge=1, description="Max requests per minute per tenant"
    )

    # SLA
    review_sla_hours: int = Field(
        default=24, ge=1, description="Hours before a review case breaches SLA"
    )

    # LLM budget
    l3_max_cost_usd: float = Field(
        default=10.0, ge=0.0, description="Maximum L3 LLM spend per batch"
    )

    created_at: str = Field(..., description="ISO 8601 timestamp")
    updated_at: str = Field(..., description="ISO 8601 timestamp")
