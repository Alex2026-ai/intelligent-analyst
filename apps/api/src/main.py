"""FastAPI application factory — production wiring.

Wires real infrastructure (Firestore, GCS, Anthropic, JWT) when environment
variables are present. Falls back to in-memory implementations for testing.
Uses lifespan pattern for Firebase Admin SDK initialization.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.src.config import AppSettings
from apps.api.src.middleware.auth import AuthMiddleware, TokenValidator
from apps.api.src.middleware.correlation import CorrelationMiddleware
from apps.api.src.middleware.error_handler import generic_exception_handler, http_exception_handler
from apps.api.src.routes import admin, batches, command, command_stream, evidence, export, health, public_metadata, resolve, review
from apps.api.src.routes.health import mark_startup_complete
from apps.api.src.startup.validator import validate_startup

logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    """Initialize Firebase Admin SDK exactly once.

    Uses Application Default Credentials on Cloud Run.
    Explicit project detection via GOOGLE_CLOUD_PROJECT env var.
    """
    import firebase_admin

    if not firebase_admin._apps:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("FIRESTORE_PROJECT")
        if project_id:
            logger.info("Initializing Firebase Admin SDK for project: %s", project_id)
        else:
            logger.warning("No explicit project ID found — Firebase will use ADC default")
        firebase_admin.initialize_app()


def create_app(
    settings: AppSettings | None = None,
    token_validator: TokenValidator | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Application settings. Defaults to AppSettings().
        token_validator: Token validator. If None, wired from config or defaults.

    Returns:
        Configured FastAPI application.
    """
    settings = settings or AppSettings.from_env()

    is_testing = os.environ.get("TESTING", "").lower() in ("1", "true")

    # --- OpenTelemetry initialization (before app creation) ---
    if not is_testing:
        from apps.api.src.observability.otel import init_otel
        init_otel(service_name="ia-api")

    # --- Firebase initialization (lifespan-safe, idempotent) ---
    if not is_testing and settings.auth_provider == "firebase":
        _init_firebase()

    # --- Token validator ---
    if not is_testing and token_validator is None:
        if settings.auth_provider == "firebase":
            from apps.api.src.middleware.firebase_validator import FirebaseTokenValidator
            token_validator = TokenValidator(verify_func=FirebaseTokenValidator())
        elif settings.jwks_url:
            from apps.api.src.middleware.jwks_validator import JWKSTokenValidator
            jwks_validator = JWKSTokenValidator(
                jwks_url=settings.jwks_url,
                audience=settings.auth_audience,
                issuer=settings.auth_issuer,
                cache_ttl_seconds=settings.jwks_cache_ttl_seconds,
            )
            token_validator = TokenValidator(verify_func=jwks_validator)

    token_validator = token_validator or TokenValidator()

    app = FastAPI(
        title="Intelligent Analyst API",
        version=settings.version,
        docs_url=None,
        redoc_url=None,
    )

    # --- Infrastructure on app.state for dependency injection ---
    if not is_testing:
        # Firestore
        if settings.firestore_project:
            from apps.api.src.storage.firestore.real_client import FirestoreClient
            app.state.firestore_client = FirestoreClient(project=settings.firestore_project)
        else:
            from apps.api.src.storage.firestore.client import InMemoryFirestore
            app.state.firestore_client = InMemoryFirestore()

        # GCS
        gcs_bucket = os.environ.get("GCS_BUCKET", "")
        if gcs_bucket:
            from apps.api.src.storage.gcs.real_client import GCSClient
            app.state.gcs_client = GCSClient(bucket_name=gcs_bucket)
        else:
            from apps.api.src.storage.gcs.client import InMemoryGCS
            app.state.gcs_client = InMemoryGCS()

        # LLM
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            from apps.api.src.llm.anthropic_provider import AnthropicProvider
            from apps.api.src.llm.config import LLMConfig
            llm_config = LLMConfig.from_env()
            app.state.llm_primary = AnthropicProvider(
                model=llm_config.primary_model,
                max_tokens=llm_config.max_tokens,
                temperature=llm_config.temperature,
            )
        else:
            from apps.api.src.llm.provider import MockLLMProvider
            app.state.llm_primary = MockLLMProvider()
    else:
        # Test mode — always in-memory
        from apps.api.src.storage.firestore.client import InMemoryFirestore
        from apps.api.src.storage.gcs.client import InMemoryGCS
        from apps.api.src.llm.provider import MockLLMProvider
        app.state.firestore_client = InMemoryFirestore()
        app.state.gcs_client = InMemoryGCS()
        app.state.llm_primary = MockLLMProvider()

    # Middleware
    app.add_middleware(AuthMiddleware, token_validator=token_validator)
    app.add_middleware(CorrelationMiddleware)

    # Exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Routes
    app.include_router(health.router)
    app.include_router(resolve.router)
    app.include_router(evidence.router)
    app.include_router(review.router)
    app.include_router(export.router)
    app.include_router(admin.router)
    app.include_router(command.router)
    app.include_router(command_stream.router)
    app.include_router(public_metadata.router)
    app.include_router(batches.router)

    # --- OpenTelemetry FastAPI auto-instrumentation ---
    # instrument_fastapi wraps the app with OTel ASGI middleware.
    # SpanStatusASGIMiddleware sits inside to set OK/ERROR on the parent span.
    # server_request_hook stores the span ref in scope for both.
    if not is_testing:
        from apps.api.src.observability.otel import SpanStatusASGIMiddleware, instrument_fastapi
        app.add_middleware(SpanStatusASGIMiddleware)
        instrument_fastapi(app)

    # --- Startup validation (fail-closed) ---
    result = validate_startup(settings)
    if result.all_passed:
        mark_startup_complete(settings.version)
        logger.info("Startup validation passed: all %d checks ok", len(result.checks))
    else:
        failed = [f"{c.name}: {c.message}" for c in result.failed_checks]
        logger.error("Startup validation FAILED (fail-closed): %s", "; ".join(failed))

    return app
