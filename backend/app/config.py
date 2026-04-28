"""
Centralized configuration — Environment-driven with secure defaults.

All environment variables are parsed once at import time.
Import `config` singleton from this module.
"""

import os
from typing import List


class Config:
    """Centralized configuration with secure defaults."""

    # Security
    API_KEY: str = os.getenv("BACKEND_API_KEY", "")
    PLATFORM_ADMIN_API_KEY: str = os.getenv("PLATFORM_ADMIN_API_KEY", "")
    _DEFAULT_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    ALLOWED_ORIGINS: List[str] = [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
    ] or _DEFAULT_ORIGINS

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Circuit Breaker
    CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
    CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = int(os.getenv("CIRCUIT_BREAKER_TIMEOUT_SECONDS", "30"))

    # Processing Limits
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "100000"))
    PARALLEL_LIMIT: int = int(os.getenv("PARALLEL_LIMIT", "20"))

    # L3 LLM Gating
    L3_MAX_COST_USD: float = float(os.getenv("L3_MAX_COST_USD", "10.0"))
    L3_COST_PER_CALL_USD: float = float(os.getenv("L3_COST_PER_CALL_USD", "0.005"))
    L3_MIN_SIMILARITY: float = float(os.getenv("L3_MIN_SIMILARITY", "0.30"))
    L3_MAX_CONCURRENCY: int = int(os.getenv("L3_MAX_CONCURRENCY", "20"))
    L3_CALL_TIMEOUT_SECONDS: int = int(os.getenv("L3_CALL_TIMEOUT_SECONDS", "30"))
    # L3 Semantic Cache
    L3_CACHE_ENABLED: bool = os.getenv("L3_CACHE_ENABLED", "true").lower() == "true"
    L3_CACHE_SIMILARITY: float = float(os.getenv("L3_CACHE_SIMILARITY", "0.85"))
    L3_CACHE_MAX_SIZE: int = int(os.getenv("L3_CACHE_MAX_SIZE", "50000"))

    # L3 Firestore Cache
    L3_FIRESTORE_CACHE_ENABLED: bool = os.getenv("L3_FIRESTORE_CACHE_ENABLED", "true").lower() == "true"
    L3_FIRESTORE_CACHE_TTL_DAYS: int = int(os.getenv("L3_FIRESTORE_CACHE_TTL_DAYS", "30"))
    L3_CACHE_PROMPT_VERSION: str = os.getenv("L3_CACHE_PROMPT_VERSION", "v2")
    L3_CACHE_ALIASING_ENABLED: bool = os.getenv("L3_CACHE_ALIASING_ENABLED", "true").lower() == "true"

    # L3 Volume Circuit Breaker
    L3_MAX_PERCENT: float = float(os.getenv("L3_MAX_PERCENT", "0.20"))
    L3_CIRCUIT_BREAKER_ENABLED: bool = os.getenv("L3_CIRCUIT_BREAKER_ENABLED", "true").lower() == "true"
    L3_MIN_ELIGIBLE_ROWS_FOR_ANOMALY: int = int(os.getenv("L3_MIN_ELIGIBLE_ROWS_FOR_ANOMALY", "3"))
    L3_MIN_BATCH_ROWS_FOR_ANOMALY: int = int(os.getenv("L3_MIN_BATCH_ROWS_FOR_ANOMALY", "10"))

    # Person Mode
    PERSON_L3_ENABLED: bool = os.getenv("PERSON_L3_ENABLED", "false").lower() == "true"

    # Invariants
    INVARIANTS_RESET_ENABLED: bool = os.getenv("INVARIANTS_RESET_ENABLED", "false").lower() == "true"

    # Margin Sentinel
    HUMAN_COST_PER_RECORD_USD: float = float(os.getenv("HUMAN_COST_PER_RECORD_USD", "0.50"))
    L4_WARNING_THRESHOLD_PCT: float = float(os.getenv("L4_WARNING_THRESHOLD_PCT", "6.0"))
    L4_RED_THRESHOLD_PCT: float = float(os.getenv("L4_RED_THRESHOLD_PCT", "8.0"))
    COST_PER_RECORD_RED_USD: float = float(os.getenv("COST_PER_RECORD_RED_USD", "0.05"))

    # Sanitization
    SANITIZATION_VERSION: str = os.getenv("SANITIZATION_VERSION", "SANITIZER_v1")
    WATCHLIST_VERSION_HASH: str = os.getenv("WATCHLIST_VERSION_HASH", "TEST_UNKNOWN")

    # Audit Storage
    AUDIT_STORAGE_PATH: str = os.getenv("AUDIT_STORAGE_PATH", "/tmp/ia_audit")

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    FIRESTORE_DATABASE: str = os.getenv("FIRESTORE_DATABASE", "(default)")

    # Demo Mode
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"

    # Congestion Hardening
    MAX_CONCURRENT_FINALIZE_GLOBAL: int = int(os.getenv("MAX_CONCURRENT_FINALIZE_GLOBAL", "3"))
    MAX_CONCURRENT_FINALIZE_PER_TENANT: int = int(os.getenv("MAX_CONCURRENT_FINALIZE_PER_TENANT", "1"))
    MAX_ACTIVE_SHARDS_GLOBAL: int = int(os.getenv("MAX_ACTIVE_SHARDS_GLOBAL", "50"))

    # Transaction Retry
    FINALIZE_TXN_MAX_ATTEMPTS: int = int(os.getenv("FINALIZE_TXN_MAX_ATTEMPTS", "5"))
    DEMO_TENANT_ID: str = "tenant_demo"
    AUDIT_MAX_ENTRIES: int = int(os.getenv("AUDIT_MAX_ENTRIES", "1000"))

    # PII
    PII_LOG_PATH: str = os.getenv("PII_LOG_PATH", "/tmp/ia_pii_log")

    # Input Validation
    INPUT_VALIDATION_ENABLED: bool = os.getenv("INPUT_VALIDATION_ENABLED", "true").lower() == "true"
    INPUT_MAX_LENGTH: int = int(os.getenv("INPUT_MAX_LENGTH", "500"))
    INPUT_MIN_LENGTH: int = int(os.getenv("INPUT_MIN_LENGTH", "1"))

    # KMS Signing
    KMS_SIGNING_KEY_ID: str = os.getenv("KMS_SIGNING_KEY_ID", "")
    SIGNING_ENABLED: bool = os.getenv("SIGNING_ENABLED", "true").lower() == "true"
    SIGNING_ALG: str = os.getenv("SIGNING_ALG", "EC_SIGN_P256_SHA256")

    # Evidence
    EVIDENCE_STORE_FULL_LLM_TEXT: bool = os.getenv("EVIDENCE_STORE_FULL_LLM_TEXT", "false").lower() == "true"

    # Hash Chain
    HASH_CHAIN_ENABLED: bool = os.getenv("HASH_CHAIN_ENABLED", "true").lower() == "true"

    # IAVP
    IAVP_ENABLED: bool = os.getenv("IAVP_ENABLED", "true").lower() == "true"
    IAVP_REPLAY_VERIFICATION: bool = os.getenv("IAVP_REPLAY_VERIFICATION", "true").lower() == "true"
    IAVP_FAIL_ON_VARIANCE: bool = os.getenv("IAVP_FAIL_ON_VARIANCE", "true").lower() == "true"
    IS_PRODUCTION: bool = (
        os.getenv("ENVIRONMENT", "").lower() in ("production", "prod") or
        "prod" in os.getenv("K_SERVICE", "").lower()
    )
    DEMO_KEY_FINGERPRINT: str = os.getenv("DEMO_KEY_FINGERPRINT", "")
    ENGINE_VERSION: str = os.getenv("ENGINE_VERSION", "3.0.0")

    # External Anchoring
    ANCHORING_ENABLED: bool = os.getenv("ANCHORING_ENABLED", "false").lower() == "true"
    ANCHOR_TARGET: str = os.getenv("ANCHOR_TARGET", "")

    # Tenant Isolation
    TENANT_ISOLATION_ENABLED: bool = os.getenv("TENANT_ISOLATION_ENABLED", "true").lower() == "true"
    TENANT_ENCRYPTION_ENABLED: bool = os.getenv("TENANT_ENCRYPTION_ENABLED", "false").lower() == "true"
    TENANT_ENCRYPTION_REQUIRED: bool = os.getenv("TENANT_ENCRYPTION_REQUIRED", "false").lower() == "true"
    TENANT_KMS_KEYRING: str = os.getenv("TENANT_KMS_KEYRING", "")
    TENANT_KEY_PREFIX: str = os.getenv("TENANT_KEY_PREFIX", "tenant-")

    # Legal Hold + WORM Vaulting
    LEGAL_HOLD_ENABLED: bool = os.getenv("LEGAL_HOLD_ENABLED", "false").lower() == "true"
    VAULT_BUCKET: str = os.getenv("VAULT_BUCKET", "")
    VAULT_RETENTION_DAYS: int = int(os.getenv("VAULT_RETENTION_DAYS", "2555"))
    VAULT_MODE: str = os.getenv("VAULT_MODE", "GCP_BUCKET_LOCK")

    # Retention Policy
    RETENTION_POLICY_ENABLED: bool = os.getenv("RETENTION_POLICY_ENABLED", "true").lower() == "true"
    RETENTION_COMPLETED_DAYS: int = int(os.getenv("RETENTION_COMPLETED_DAYS", "2555"))
    RETENTION_FAILED_DAYS: int = int(os.getenv("RETENTION_FAILED_DAYS", "90"))
    RETENTION_ABORTED_DAYS: int = int(os.getenv("RETENTION_ABORTED_DAYS", "30"))
    RETENTION_GRACE_PERIOD_DAYS: int = int(os.getenv("RETENTION_GRACE_PERIOD_DAYS", "30"))
    RETENTION_AUTO_DELETE: bool = os.getenv("RETENTION_AUTO_DELETE", "false").lower() == "true"

    # Transparency Log Spine (Phase 9.1)
    TRANSPARENCY_LOG_ENABLED: bool = os.getenv("TRANSPARENCY_LOG_ENABLED", "false").lower() == "true"
    TRANSPARENCY_BUCKET: str = os.getenv("TRANSPARENCY_BUCKET", "")
    TRANSPARENCY_KMS_KEY_ID: str = os.getenv("TRANSPARENCY_KMS_KEY_ID", "")
    TRANSPARENCY_ROOT_PUBLISH_ENTRIES: int = int(os.getenv("TRANSPARENCY_ROOT_PUBLISH_ENTRIES", "1024"))
    TRANSPARENCY_ROOT_PUBLISH_INTERVAL: int = int(os.getenv("TRANSPARENCY_ROOT_PUBLISH_INTERVAL", "300"))

    # Sustainability
    ENERGY_ESTIMATES_ENABLED: bool = os.getenv("ENERGY_ESTIMATES_ENABLED", "false").lower() == "true"
    PROCESSING_REGION: str = os.getenv("PROCESSING_REGION", "unknown")
    DEPLOY_REGION: str = os.getenv("DEPLOY_REGION", "us")


config = Config()
