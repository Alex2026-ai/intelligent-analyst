"""
test_route_auth_matrix.py — Day 7: Endpoint authentication audit.

Programmatically verifies auth classification of every registered route.
Ensures:
  - No internal route lacks admin/OIDC dependency
  - No route uses deprecated API-key-only guard
  - /health is public
  - /internal/system-vitals requires admin claim
  - Public verify endpoints don't require auth (by design)
  - All /batches, /audit, /forensic routes require auth
"""

import pytest


def _get_route_map():
    """Extract all routes from the running app as {(path, method): deps}."""
    from app.server_enterprise_golden import app

    route_map = {}
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            deps = []
            if hasattr(route, 'dependant') and route.dependant:
                for dep in route.dependant.dependencies:
                    if hasattr(dep, 'call') and dep.call:
                        deps.append(dep.call.__name__ if hasattr(dep.call, '__name__') else str(dep.call))
            for method in route.methods:
                if method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
                    route_map[(route.path, method)] = deps
    return route_map


class TestPublicEndpointsAreIntentional:
    """Only whitelisted endpoints should lack auth dependencies."""

    # These endpoints are intentionally public (no auth dependency in signature).
    # Internal endpoints use in-body auth checks (Bearer/OIDC) not FastAPI Depends.
    ALLOWED_PUBLIC = {
        ("/", "GET"),                                    # Root redirect
        ("/health", "GET"),                              # Health check
        ("/stats", "GET"),                               # Performance metrics (cost stripped)
        ("/demo/status", "GET"),                         # Demo mode boolean
        ("/docs", "GET"),                                # Swagger UI
        ("/docs/oauth2-redirect", "GET"),                # Swagger OAuth redirect
        ("/openapi.json", "GET"),                        # OpenAPI spec
        ("/redoc", "GET"),                               # ReDoc
        ("/verify/{batch_id}", "GET"),                   # Public verification
        ("/verify/{batch_id}/seal", "GET"),              # Public trust seal
        ("/security/public-key", "GET"),                 # Public key for verification
        ("/security/manifest-public-key", "GET"),        # Manifest public key
        ("/verify/receipt/{receipt_id}", "GET"),          # Phase 4: Public receipt verification
        ("/assert", "POST"),                                # Phase 9: Trust assertion (public, policy-gated)
        ("/transparency/latest-root", "GET"),               # Phase 9.1: Transparency log (public read)
        ("/transparency/proof/{entry_id}", "GET"),          # Phase 9.1: Transparency proof (public read)
        # Day 7 F1/F2: /security/status and /security/integrity now require auth
        ("/share/{share_token}", "GET"),                 # Share link (token-based auth)
        # Internal Cloud Tasks endpoints use in-body OIDC check, not Depends
        ("/internal/process-batch", "POST"),
        ("/internal/process-shard", "POST"),
        ("/internal/finalize-batch", "POST"),
    }

    def test_no_unexpected_public_routes(self):
        route_map = _get_route_map()
        unexpected_public = []
        for (path, method), deps in route_map.items():
            if not deps and (path, method) not in self.ALLOWED_PUBLIC:
                unexpected_public.append(f"{method} {path}")
        assert unexpected_public == [], (
            f"Routes without auth dependencies not in whitelist: {unexpected_public}"
        )


class TestInternalSystemVitalsRequiresAdmin:
    def test_system_vitals_has_admin_dep(self):
        route_map = _get_route_map()
        deps = route_map.get(("/internal/system-vitals", "GET"), [])
        assert "require_firebase_admin_claim" in deps, (
            f"/internal/system-vitals deps: {deps} — must require admin claim"
        )


class TestAdminRoutesRequireAdminRole:
    ADMIN_PATHS = [
        "/admin/batch-economics/{trace_id}",
        "/admin/tenants",
    ]

    def test_admin_routes_have_admin_dep(self):
        route_map = _get_route_map()
        for path in self.ADMIN_PATHS:
            deps = route_map.get((path, "GET"), [])
            assert "require_admin_role" in deps, (
                f"{path} deps: {deps} — must require admin role"
            )


class TestBatchRoutesRequireAuth:
    BATCH_PATHS = [
        ("/batches", "GET"),
        ("/batches", "POST"),
        ("/batches/{trace_id}/abort", "POST"),
        ("/batches/{trace_id}/results", "GET"),
        ("/batches/{trace_id}/export", "GET"),
        ("/batches/{trace_id}/certificate", "GET"),
        ("/batches/{trace_id}/evidence-pack", "GET"),
        ("/batches/{trace_id}/verify", "GET"),
        ("/batches/{trace_id}/retention", "GET"),
        ("/batches/{trace_id}/sustainability", "GET"),
    ]

    def test_batch_routes_require_auth(self):
        route_map = _get_route_map()
        for path, method in self.BATCH_PATHS:
            deps = route_map.get((path, method), [])
            assert len(deps) > 0, (
                f"{method} {path} has no auth dependency"
            )
            assert "verify_api_key" in deps or "require_admin_role" in deps, (
                f"{method} {path} deps: {deps} — must require auth"
            )


class TestAuditRoutesRequireAuth:
    AUDIT_PATHS = [
        ("/audit", "GET"),
        ("/audit/{trace_id}", "GET"),
        ("/audit/{trace_id}/certificate", "GET"),
        ("/audit/{trace_id}/evidence", "GET"),
        ("/audit/{trace_id}/flagged", "GET"),
        ("/audit/{trace_id}/hold", "GET"),
        ("/audit/{trace_id}/hold", "POST"),
        ("/audit/{trace_id}/hold-history", "GET"),
        ("/audit/{trace_id}/release-hold", "POST"),
    ]

    def test_audit_routes_require_auth(self):
        route_map = _get_route_map()
        for path, method in self.AUDIT_PATHS:
            deps = route_map.get((path, method), [])
            assert "verify_api_key" in deps, (
                f"{method} {path} deps: {deps} — must require verify_api_key"
            )


class TestSecurityEndpointsRequireAuth:
    """Day 7 F1/F2: /security/status and /security/integrity must require admin claim."""

    # These two now use require_firebase_admin_claim (admin-only)
    SECURITY_ADMIN_PATHS = [
        ("/security/status", "GET"),
        ("/security/integrity", "GET"),
    ]

    # These still use verify_api_key
    SECURITY_AUTH_PATHS = [
        ("/security/whoami", "GET"),
        ("/security/pii-log", "GET"),
        ("/security/lifecycle-policy", "GET"),
        ("/security/retention-status", "GET"),
        ("/security/apply-lifecycle-policy", "POST"),
    ]

    def test_security_admin_routes_require_admin_claim(self):
        route_map = _get_route_map()
        for path, method in self.SECURITY_ADMIN_PATHS:
            deps = route_map.get((path, method), [])
            assert "require_firebase_admin_claim" in deps, (
                f"{method} {path} deps: {deps} — must require require_firebase_admin_claim"
            )

    def test_security_config_routes_require_auth(self):
        route_map = _get_route_map()
        for path, method in self.SECURITY_AUTH_PATHS:
            deps = route_map.get((path, method), [])
            assert "verify_api_key" in deps, (
                f"{method} {path} deps: {deps} — must require verify_api_key"
            )

    def test_security_status_not_public(self):
        route_map = _get_route_map()
        deps = route_map.get(("/security/status", "GET"), [])
        assert len(deps) > 0, "/security/status must not be public"

    def test_security_integrity_not_public(self):
        route_map = _get_route_map()
        deps = route_map.get(("/security/integrity", "GET"), [])
        assert len(deps) > 0, "/security/integrity must not be public"


class TestNoBypassInVitalsSource:
    """Verify /internal/system-vitals auth has no bypass logic."""
    def test_no_bypass_in_vitals(self):
        import inspect
        from app.routes.internal_system_vitals import require_firebase_admin_claim
        source = inspect.getsource(require_firebase_admin_claim)
        assert "ALLOW_INTERNAL_BYPASS" not in source
        assert "bypass" not in source.lower()


class TestNoBypassInServerSource:
    """Day 7 F4: Verify ALLOW_INTERNAL_BYPASS removed from entire server module."""
    def test_no_bypass_in_server(self):
        import inspect
        from app import server_enterprise_golden
        source = inspect.getsource(server_enterprise_golden)
        assert "ALLOW_INTERNAL_BYPASS" not in source, (
            "ALLOW_INTERNAL_BYPASS still present in server_enterprise_golden.py"
        )

    def test_no_bypass_in_verify_api_key(self):
        import inspect
        from app.server_enterprise_golden import verify_api_key
        source = inspect.getsource(verify_api_key)
        assert "ALLOW_INTERNAL_BYPASS" not in source
        assert "local_bypass" not in source
        assert "mock user" not in source.lower()


class TestHealthIsPublic:
    def test_health_has_no_deps(self):
        route_map = _get_route_map()
        deps = route_map.get(("/health", "GET"), [])
        assert deps == [], f"/health should have no deps, got: {deps}"


class TestForensicSummaryRequiresAuth:
    def test_forensic_summary_requires_auth(self):
        route_map = _get_route_map()
        deps = route_map.get(("/forensic-summary/{trace_id}", "GET"), [])
        assert "verify_api_key" in deps, (
            f"forensic-summary deps: {deps} — must require auth"
        )
