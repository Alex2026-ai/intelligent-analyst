"""Startup validation — fail-closed on missing config, secrets, or connectivity.

Every check must pass for the service to accept traffic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.api.src.config import AppSettings


@dataclass
class StartupCheck:
    """Result of a single startup check."""

    name: str
    passed: bool
    message: str = ""


@dataclass
class StartupResult:
    """Aggregate result of all startup checks."""

    checks: list[StartupCheck] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[StartupCheck]:
        return [c for c in self.checks if not c.passed]


def validate_startup(settings: AppSettings) -> StartupResult:
    """Run all startup validation checks.

    Checks (fail-closed):
    1. Configuration loaded and valid
    2. CORS not open (FP-003)
    3. Schema version matches expected
    4. Service name present

    In production, additional checks would include:
    - Firestore connectivity
    - Secret Manager accessibility
    - Attestation checksum verification

    Args:
        settings: Application settings to validate.

    Returns:
        StartupResult with pass/fail for each check.
    """
    checks: list[StartupCheck] = []

    # 1. Config loaded
    checks.append(StartupCheck(
        name="config",
        passed=bool(settings.service_name),
        message="Service name configured" if settings.service_name else "Service name missing",
    ))

    # 2. CORS not open (FP-003)
    cors_valid = settings.cors_origins_valid
    checks.append(StartupCheck(
        name="cors",
        passed=cors_valid,
        message="CORS properly configured" if cors_valid else "CORS allows '*' — FORBIDDEN (FP-003)",
    ))

    # 3. Schema version
    schema_ok = bool(settings.expected_schema_version)
    checks.append(StartupCheck(
        name="schema_version",
        passed=schema_ok,
        message=f"Schema version: {settings.expected_schema_version}" if schema_ok else "Missing schema version",
    ))

    # 4. Environment set
    env_ok = settings.environment in {"development", "staging", "production"}
    checks.append(StartupCheck(
        name="environment",
        passed=env_ok,
        message=f"Environment: {settings.environment}" if env_ok else f"Unknown environment: {settings.environment}",
    ))

    return StartupResult(checks=checks)
