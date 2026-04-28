"""Tests for app factory wiring."""

import os
from unittest.mock import patch

from apps.api.src.config import AppSettings
from apps.api.src.main import create_app
from apps.api.src.middleware.auth import TokenValidator


class TestAppFactory:
    def test_creates_app_with_defaults(self):
        with patch.dict(os.environ, {"TESTING": "true"}):
            app = create_app()
            assert app is not None
            assert hasattr(app.state, "firestore_client")
            assert hasattr(app.state, "gcs_client")
            assert hasattr(app.state, "llm_primary")

    def test_testing_mode_uses_in_memory(self):
        with patch.dict(os.environ, {"TESTING": "true"}):
            app = create_app()
            # Verify in-memory types
            from apps.api.src.storage.firestore.client import InMemoryFirestore
            from apps.api.src.storage.gcs.client import InMemoryGCS
            assert isinstance(app.state.firestore_client, InMemoryFirestore)
            assert isinstance(app.state.gcs_client, InMemoryGCS)

    def test_custom_token_validator_respected(self):
        with patch.dict(os.environ, {"TESTING": "true"}):
            custom_validator = TokenValidator(verify_func=lambda t: {"sub": "test"})
            app = create_app(token_validator=custom_validator)
            assert app is not None

    def test_no_env_uses_in_memory(self):
        """Without Firestore project or GCS bucket, falls back to in-memory."""
        with patch.dict(os.environ, {"TESTING": "false"}, clear=False):
            settings = AppSettings()  # No firestore_project set
            app = create_app(settings=settings)
            from apps.api.src.storage.firestore.client import InMemoryFirestore
            assert isinstance(app.state.firestore_client, InMemoryFirestore)


class TestAppSettingsFromEnv:
    def test_from_env(self):
        with patch.dict(os.environ, {
            "ENVIRONMENT": "staging",
            "AUTH_PROVIDER": "firebase",
            "FIRESTORE_PROJECT": "test-project",
        }):
            settings = AppSettings.from_env()
            assert settings.environment == "staging"
            assert settings.auth_provider == "firebase"
            assert settings.firestore_project == "test-project"

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = AppSettings.from_env()
            assert settings.environment == "development"
            assert settings.auth_provider == "jwks"
