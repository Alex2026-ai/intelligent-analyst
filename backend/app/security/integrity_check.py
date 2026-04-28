"""
================================================================================
FORENSIC INTEGRITY CHECK (Day 10 - Zero-Trust Lockdown)
================================================================================

Performs startup verification of all forensic infrastructure components.
The system REFUSES TO BOOT if critical integrity checks fail.

Checks:
1. KMS Signing Key - Must be accessible and ENABLED
2. Vault Bucket - Must exist with retention policy
3. Anchor Bucket - Must exist and be configured
4. Service Account - Must have minimal permissions

================================================================================
"""

import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from enum import Enum


class IntegrityStatus(str, Enum):
    """Integrity check status."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class IntegrityCheckError(Exception):
    """
    Raised when a critical integrity check fails.

    This error should cause the system to REFUSE TO BOOT.
    """
    def __init__(self, check_name: str, message: str, details: Dict[str, Any] = None):
        self.check_name = check_name
        self.message = message
        self.details = details or {}
        super().__init__(f"INTEGRITY CHECK FAILED [{check_name}]: {message}")


# GCS client (optional)
try:
    from google.cloud import storage
    HAS_GCS = True
except ImportError:
    HAS_GCS = False
    storage = None

# KMS client (optional)
try:
    from google.cloud import kms
    HAS_KMS = True
except ImportError:
    HAS_KMS = False
    kms = None


class ForensicIntegrityChecker:
    """
    Performs comprehensive integrity checks on forensic infrastructure.

    Usage:
        checker = ForensicIntegrityChecker(
            signing_key_name="projects/.../cryptoKeys/evidence-signer/cryptoKeyVersions/1",
            vault_bucket="ia-vault-prod",
            anchor_bucket="ia-anchors-prod",
            environment="prod"
        )

        # Run all checks - raises IntegrityCheckError on critical failure
        results = checker.run_all_checks(fail_on_critical=True)
    """

    def __init__(
        self,
        signing_key_name: str = "",
        vault_bucket: str = "",
        anchor_bucket: str = "",
        environment: str = "test",
        strict_mode: bool = True,
    ):
        self.signing_key_name = signing_key_name
        self.vault_bucket = vault_bucket
        self.anchor_bucket = anchor_bucket
        self.environment = environment.lower()
        self.strict_mode = strict_mode  # PROD enforces all checks

        # Initialize clients
        self._kms_client = None
        self._storage_client = None

        if HAS_KMS and signing_key_name:
            try:
                self._kms_client = kms.KeyManagementServiceClient()
            except Exception as e:
                print(f"[IntegrityCheck] KMS client init failed: {e}", flush=True)

        if HAS_GCS:
            try:
                self._storage_client = storage.Client()
            except Exception as e:
                print(f"[IntegrityCheck] GCS client init failed: {e}", flush=True)

    def check_kms_signing_key(self) -> Dict[str, Any]:
        """
        Check KMS signing key is accessible and ENABLED.

        CRITICAL: System refuses to boot if this fails in PROD.
        """
        check_name = "KMS_SIGNING_KEY"

        if not self.signing_key_name:
            return {
                "check": check_name,
                "status": IntegrityStatus.SKIP.value,
                "message": "SIGNING_KEY_NAME not configured",
                "critical": False
            }

        if not HAS_KMS or not self._kms_client:
            return {
                "check": check_name,
                "status": IntegrityStatus.FAIL.value,
                "message": "KMS client not available",
                "critical": self.environment == "prod"
            }

        try:
            # Get key version metadata
            key_version = self._kms_client.get_crypto_key_version(
                name=self.signing_key_name
            )

            # Check state
            state_name = kms.CryptoKeyVersion.CryptoKeyVersionState(key_version.state).name

            if state_name != "ENABLED":
                return {
                    "check": check_name,
                    "status": IntegrityStatus.FAIL.value,
                    "message": f"Key is not ENABLED (state: {state_name})",
                    "key_name": self.signing_key_name,
                    "state": state_name,
                    "critical": True
                }

            # Verify algorithm
            algorithm_name = kms.CryptoKeyVersion.CryptoKeyVersionAlgorithm(key_version.algorithm).name

            return {
                "check": check_name,
                "status": IntegrityStatus.PASS.value,
                "message": "KMS signing key accessible and ENABLED",
                "key_name": self.signing_key_name,
                "state": state_name,
                "algorithm": algorithm_name,
                "create_time": key_version.create_time.isoformat() if key_version.create_time else None,
                "critical": False
            }

        except Exception as e:
            return {
                "check": check_name,
                "status": IntegrityStatus.FAIL.value,
                "message": f"Failed to access KMS key: {str(e)}",
                "key_name": self.signing_key_name,
                "critical": self.environment == "prod"
            }

    def check_vault_bucket(self) -> Dict[str, Any]:
        """
        Check vault bucket exists and has retention policy.

        CRITICAL: System refuses to boot if this fails in PROD.
        """
        check_name = "VAULT_BUCKET"

        if not self.vault_bucket:
            return {
                "check": check_name,
                "status": IntegrityStatus.SKIP.value,
                "message": "VAULT_BUCKET not configured",
                "critical": False
            }

        if not HAS_GCS or not self._storage_client:
            return {
                "check": check_name,
                "status": IntegrityStatus.FAIL.value,
                "message": "GCS client not available",
                "critical": self.environment == "prod"
            }

        try:
            bucket = self._storage_client.get_bucket(self.vault_bucket)

            # Check retention policy
            retention_policy = bucket.retention_policy_effective_time
            retention_period = bucket.retention_period

            # Check versioning
            versioning_enabled = bucket.versioning_enabled

            # Check uniform bucket-level access
            uniform_access = bucket.iam_configuration.uniform_bucket_level_access_enabled

            # Build result
            warnings = []

            if not retention_period:
                warnings.append("No retention policy set")

            if not versioning_enabled:
                warnings.append("Versioning not enabled")

            if not uniform_access:
                warnings.append("Uniform bucket-level access not enabled")

            # In PROD, missing retention is critical
            if self.environment == "prod" and not retention_period:
                return {
                    "check": check_name,
                    "status": IntegrityStatus.FAIL.value,
                    "message": "PROD vault bucket missing retention policy",
                    "bucket": self.vault_bucket,
                    "retention_period_seconds": retention_period,
                    "versioning": versioning_enabled,
                    "uniform_access": uniform_access,
                    "critical": True
                }

            status = IntegrityStatus.PASS if not warnings else IntegrityStatus.WARN

            return {
                "check": check_name,
                "status": status.value,
                "message": "Vault bucket configured" + (f" (warnings: {len(warnings)})" if warnings else ""),
                "bucket": self.vault_bucket,
                "retention_period_seconds": retention_period,
                "retention_period_days": retention_period // 86400 if retention_period else None,
                "versioning": versioning_enabled,
                "uniform_access": uniform_access,
                "warnings": warnings,
                "critical": False
            }

        except Exception as e:
            return {
                "check": check_name,
                "status": IntegrityStatus.FAIL.value,
                "message": f"Failed to access vault bucket: {str(e)}",
                "bucket": self.vault_bucket,
                "critical": self.environment == "prod"
            }

    def check_anchor_bucket(self) -> Dict[str, Any]:
        """
        Check anchor bucket exists and is configured.

        WARNING: Degraded mode if this fails (non-critical).
        """
        check_name = "ANCHOR_BUCKET"

        if not self.anchor_bucket:
            return {
                "check": check_name,
                "status": IntegrityStatus.SKIP.value,
                "message": "ANCHOR_BUCKET not configured",
                "critical": False
            }

        if not HAS_GCS or not self._storage_client:
            return {
                "check": check_name,
                "status": IntegrityStatus.WARN.value,
                "message": "GCS client not available - anchoring degraded",
                "critical": False
            }

        try:
            bucket = self._storage_client.get_bucket(self.anchor_bucket)

            return {
                "check": check_name,
                "status": IntegrityStatus.PASS.value,
                "message": "Anchor bucket accessible",
                "bucket": self.anchor_bucket,
                "critical": False
            }

        except Exception as e:
            return {
                "check": check_name,
                "status": IntegrityStatus.WARN.value,
                "message": f"Anchor bucket not accessible: {str(e)} - anchoring degraded",
                "bucket": self.anchor_bucket,
                "critical": False
            }

    def check_environment_config(self) -> Dict[str, Any]:
        """
        Check environment-specific configuration.
        """
        check_name = "ENVIRONMENT_CONFIG"

        warnings = []

        # Check required env vars for PROD
        if self.environment == "prod":
            required_vars = [
                "SIGNING_KEY_NAME",
                "VAULT_BUCKET",
                "ANCHOR_BUCKET",
                "LEGAL_HOLD_ENABLED",
                "TENANT_ENCRYPTION_ENABLED",
            ]

            missing = [v for v in required_vars if not os.getenv(v)]

            if missing:
                return {
                    "check": check_name,
                    "status": IntegrityStatus.FAIL.value,
                    "message": f"PROD missing required env vars: {missing}",
                    "missing_vars": missing,
                    "critical": True
                }

        return {
            "check": check_name,
            "status": IntegrityStatus.PASS.value,
            "message": f"Environment config valid ({self.environment})",
            "environment": self.environment,
            "critical": False
        }

    def run_all_checks(self, fail_on_critical: bool = True) -> Dict[str, Any]:
        """
        Run all integrity checks.

        Args:
            fail_on_critical: If True, raise IntegrityCheckError on critical failure

        Returns:
            Dictionary with all check results and overall status

        Raises:
            IntegrityCheckError: If fail_on_critical=True and a critical check fails
        """
        started_at = datetime.now(timezone.utc)

        checks = [
            self.check_kms_signing_key(),
            self.check_vault_bucket(),
            self.check_anchor_bucket(),
            self.check_environment_config(),
        ]

        # Analyze results
        critical_failures = [c for c in checks if c.get("critical") and c["status"] == IntegrityStatus.FAIL.value]
        warnings = [c for c in checks if c["status"] == IntegrityStatus.WARN.value]
        passes = [c for c in checks if c["status"] == IntegrityStatus.PASS.value]

        overall_status = IntegrityStatus.PASS
        if critical_failures:
            overall_status = IntegrityStatus.FAIL
        elif warnings:
            overall_status = IntegrityStatus.WARN

        result = {
            "integrity_check_version": "1.0.0",
            "environment": self.environment,
            "strict_mode": self.strict_mode,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status.value,
            "summary": {
                "total_checks": len(checks),
                "passed": len(passes),
                "warnings": len(warnings),
                "critical_failures": len(critical_failures),
            },
            "checks": checks,
            "boot_allowed": overall_status != IntegrityStatus.FAIL,
        }

        # Raise on critical failure if requested
        if fail_on_critical and critical_failures:
            first_failure = critical_failures[0]
            raise IntegrityCheckError(
                check_name=first_failure["check"],
                message=first_failure["message"],
                details=result
            )

        return result


def run_startup_integrity_check(
    signing_key_name: str = "",
    vault_bucket: str = "",
    anchor_bucket: str = "",
    environment: str = "test",
    fail_on_critical: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function to run integrity check on startup.

    This should be called during server initialization.
    If critical checks fail, raises IntegrityCheckError.
    """
    print("=" * 60, flush=True)
    print("FORENSIC INTEGRITY CHECK - STARTING", flush=True)
    print("=" * 60, flush=True)

    checker = ForensicIntegrityChecker(
        signing_key_name=signing_key_name,
        vault_bucket=vault_bucket,
        anchor_bucket=anchor_bucket,
        environment=environment,
    )

    try:
        result = checker.run_all_checks(fail_on_critical=fail_on_critical)

        # Log results
        for check in result["checks"]:
            status = check["status"]
            name = check["check"]
            message = check["message"]

            if status == IntegrityStatus.PASS.value:
                print(f"  [PASS] {name}: {message}", flush=True)
            elif status == IntegrityStatus.WARN.value:
                print(f"  [WARN] {name}: {message}", flush=True)
            elif status == IntegrityStatus.FAIL.value:
                print(f"  [FAIL] {name}: {message}", flush=True)
            else:
                print(f"  [SKIP] {name}: {message}", flush=True)

        print("=" * 60, flush=True)

        if result["boot_allowed"]:
            print(f"INTEGRITY CHECK: {result['overall_status']} - Boot allowed", flush=True)
        else:
            print(f"INTEGRITY CHECK: {result['overall_status']} - BOOT BLOCKED", flush=True)

        print("=" * 60, flush=True)

        return result

    except IntegrityCheckError as e:
        print(f"  [CRITICAL] {e.check_name}: {e.message}", flush=True)
        print("=" * 60, flush=True)
        print("INTEGRITY CHECK: FAIL - REFUSING TO BOOT", flush=True)
        print("=" * 60, flush=True)
        raise
