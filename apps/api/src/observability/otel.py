"""OpenTelemetry production wiring — Cloud Trace exporter + FastAPI instrumentation.

Initialized once in create_app() when running on Cloud Run.
Skipped in testing (TESTING=true) to avoid exporter side effects.

Root cause of 10-hour "Unset" bug:
  GOOGLE_CLOUD_PROJECT was not set → CloudTraceSpanExporter never initialized →
  OTel SDK spans (with our status) never exported → Cloud Trace only showed
  Cloud Run's auto-generated spans which are always Unset.

Fix:
  1. Fallback to FIRESTORE_PROJECT for project ID.
  2. Raw ASGI middleware (SpanStatusASGIMiddleware) sets status at the lowest
     level — no BaseHTTPMiddleware contextvars breakage.
  3. inject_span_identity kept for auth.py / correlation.py callers.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False

# Key used to store the parent server span in the ASGI scope dict
SCOPE_SPAN_KEY = "ia_server_span"


# ---------------------------------------------------------------------------
# ASGI hooks — wired into FastAPIInstrumentor
# ---------------------------------------------------------------------------

def _server_request_hook(span, scope) -> None:
    """Store the parent server span in the ASGI scope for inner middleware."""
    if not span or not span.is_recording():
        return

    scope[SCOPE_SPAN_KEY] = span

    # Capture client-sent correlation ID from raw headers
    headers = dict(scope.get("headers", []))
    client_corr = headers.get(b"x-correlation-id", b"").decode("utf-8", errors="replace")
    if client_corr:
        span.set_attribute("ia.client_correlation_id", client_corr)


# ---------------------------------------------------------------------------
# Raw ASGI middleware — highest integrity for span status enforcement
# ---------------------------------------------------------------------------

class SpanStatusASGIMiddleware:
    """Set OTel span status at the ASGI transport level.

    Intercepts http.response.start to read status_code, then sets
    StatusCode.OK or StatusCode.ERROR on the parent server span stored
    in scope by server_request_hook. No BaseHTTPMiddleware, no contextvars.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                span = scope.get(SCOPE_SPAN_KEY)
                if span and span.is_recording():
                    try:
                        from opentelemetry.trace import StatusCode
                        if status_code >= 400:
                            span.set_status(StatusCode.ERROR, f"HTTP {status_code}")
                        else:
                            span.set_status(StatusCode.OK)
                        span.set_attribute("http.status_code", status_code)
                    except ImportError:
                        pass
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ---------------------------------------------------------------------------
# Identity injection — called from middleware (auth.py, correlation.py)
# ---------------------------------------------------------------------------

def inject_span_identity(scope_or_none: dict | None = None, correlation_id: str = "",
                         tenant_id: str = "", user_id: str = "") -> None:
    """Set identity attributes on the parent server span.

    Uses the span reference stored in ASGI scope (preferred) or falls back
    to trace.get_current_span() for backward compatibility.
    """
    span = None
    if scope_or_none is not None:
        span = scope_or_none.get(SCOPE_SPAN_KEY)

    if not span:
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
        except ImportError:
            return

    if not span or not getattr(span, "is_recording", lambda: False)():
        return

    if correlation_id:
        span.set_attribute("ia.correlation_id", correlation_id)
    if tenant_id:
        span.set_attribute("ia.tenant_id", tenant_id)
    if user_id:
        span.set_attribute("ia.user_id", user_id)


# Backward compat — correlation.py still imports this.
# Now a no-op because SpanStatusASGIMiddleware handles it.
def set_span_status(scope: dict, status_code: int) -> None:
    """No-op — span status is now set by SpanStatusASGIMiddleware."""
    pass


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_otel(service_name: str = "ia-api") -> None:
    """Initialize OpenTelemetry with Cloud Trace exporter.

    Idempotent — safe to call multiple times.
    Falls back to FIRESTORE_PROJECT if GOOGLE_CLOUD_PROJECT is unset.
    """
    global _initialized
    if _initialized:
        return

    # FALLBACK: Use FIRESTORE_PROJECT if GOOGLE_CLOUD_PROJECT is missing
    project_id = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("FIRESTORE_PROJECT")
        or ""
    )

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({
            "service.name": service_name,
            "service.namespace": "intelligent-analyst",
            "cloud.project_id": project_id,
            "deployment.environment": os.environ.get("ENVIRONMENT", "production"),
        })

        provider = TracerProvider(resource=resource)

        if project_id:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter(project_id=project_id)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            print(f"[OTel] Cloud Trace exporter configured for project {project_id}")
        else:
            print("[OTel] WARNING: No project ID — traces will not be exported")

        trace.set_tracer_provider(provider)
        _initialized = True
        print(f"[OTel] TracerProvider initialized for service '{service_name}'")

    except ImportError as e:
        print(f"[OTel] SDK not available — tracing disabled ({e})")


def instrument_fastapi(app) -> None:
    """Attach OpenTelemetry auto-instrumentation to a FastAPI app.

    Wires server_request_hook to store span in scope for the
    SpanStatusASGIMiddleware and identity injection.
    """
    if not _initialized:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            server_request_hook=_server_request_hook,
        )
        print("[OTel] FastAPI auto-instrumentation activated with server_request_hook")
    except ImportError as e:
        print(f"[OTel] FastAPI instrumentor not available ({e})")
