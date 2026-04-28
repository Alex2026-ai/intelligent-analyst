"""Tests for startup validator — fail-closed behavior."""

from apps.api.src.config import AppSettings, CORSConfig
from apps.api.src.startup.validator import validate_startup


class TestStartupValidator:
    def test_valid_config_passes(self):
        settings = AppSettings()
        result = validate_startup(settings)
        assert result.all_passed is True

    def test_open_cors_fails(self):
        settings = AppSettings(cors=CORSConfig(allowed_origins=["*"]))
        result = validate_startup(settings)
        assert result.all_passed is False
        failed = [c.name for c in result.failed_checks]
        assert "cors" in failed

    def test_empty_service_name_fails(self):
        settings = AppSettings(service_name="")
        result = validate_startup(settings)
        assert result.all_passed is False

    def test_invalid_environment_fails(self):
        settings = AppSettings(environment="unknown_env")
        result = validate_startup(settings)
        assert result.all_passed is False
        failed = [c.name for c in result.failed_checks]
        assert "environment" in failed

    def test_reports_all_failures(self):
        settings = AppSettings(
            service_name="",
            cors=CORSConfig(allowed_origins=["*"]),
            environment="bad",
        )
        result = validate_startup(settings)
        assert len(result.failed_checks) == 3
