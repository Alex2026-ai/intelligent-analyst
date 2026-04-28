"""
================================================================================
INTELLIGENT ANALYST - TENANT REGION BINDING (Phase 1)
================================================================================

Immutable tenant-to-region binding with in-memory caching.

Each tenant is bound to a region ("us" or "eu") at first contact.
Once assigned, the region is immutable. Every authenticated request
validates that the tenant's region matches the service's DEPLOY_REGION;
mismatches are rejected with 403.

Caching follows the same pattern as tenant_encryption.py:
- In-memory dict with 15-minute TTL
- Thread-safe via locks
- Metrics for observability

================================================================================
"""

import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

# Valid deployment regions
VALID_REGIONS = {"us", "eu"}

# Cache TTL (15 minutes)
TENANT_REGION_CACHE_TTL_SECONDS = 900

# In-memory cache: tenant_id -> (region, expiry_timestamp)
_region_cache: Dict[str, Tuple[str, float]] = {}
_region_cache_lock = threading.Lock()

# Metrics
_region_metrics = {
    "cache_hits": 0,
    "cache_misses": 0,
    "firestore_reads": 0,
    "auto_assignments": 0,
    "mismatches": 0,
}
_metrics_lock = threading.Lock()


def _increment_metric(metric: str) -> None:
    """Thread-safe metric increment."""
    with _metrics_lock:
        _region_metrics[metric] = _region_metrics.get(metric, 0) + 1


def get_tenant_region_metrics() -> Dict[str, int]:
    """Get tenant region caching metrics."""
    with _metrics_lock:
        return dict(_region_metrics)


def clear_region_cache() -> None:
    """Clear the region cache. For testing only."""
    with _region_cache_lock:
        _region_cache.clear()


def resolve_tenant_region(
    tenant_id: str,
    firestore_db,
    deploy_region: str,
) -> str:
    """
    Resolve the region for a tenant, with in-memory caching.

    Logic:
    1. Check cache (fast path, 15-min TTL)
    2. Read Firestore /tenants/{tenant_id}
    3a. Doc exists with region field -> return it
    3b. Doc exists without region field -> backfill to "us" (legacy safety)
    3c. No doc -> auto-assign deploy_region, create doc

    Uses set(merge=True) for race-safe creation.

    Args:
        tenant_id: Tenant identifier
        firestore_db: Firestore client instance
        deploy_region: This service's DEPLOY_REGION value

    Returns:
        The tenant's region string ("us" or "eu")
    """
    current_time = time.time()

    # Fast path: check cache
    with _region_cache_lock:
        if tenant_id in _region_cache:
            region, expiry = _region_cache[tenant_id]
            if current_time < expiry:
                _increment_metric("cache_hits")
                return region
            del _region_cache[tenant_id]

    _increment_metric("cache_misses")

    # Slow path: Firestore read
    _increment_metric("firestore_reads")
    doc_ref = firestore_db.collection("tenants").document(tenant_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict() or {}
        region = data.get("region")
        if region:
            # Doc exists with region — cache and return
            with _region_cache_lock:
                _region_cache[tenant_id] = (region, current_time + TENANT_REGION_CACHE_TTL_SECONDS)
            return region
        else:
            # Doc exists but no region field — legacy tenant, backfill to "us"
            region = "us"
            doc_ref.set({"region": region, "region_backfilled_at": datetime.now(timezone.utc).isoformat()}, merge=True)
            print(f"[REGION] Backfilled tenant {tenant_id} to region=us (legacy)", flush=True)
    else:
        # No doc — auto-assign deploy_region
        region = deploy_region
        doc_ref.set({
            "region": region,
            "region_assigned_at": datetime.now(timezone.utc).isoformat(),
            "region_auto_assigned": True,
        }, merge=True)
        _increment_metric("auto_assignments")
        print(f"[REGION] Auto-assigned tenant {tenant_id} to region={region}", flush=True)

    # Cache result
    with _region_cache_lock:
        _region_cache[tenant_id] = (region, current_time + TENANT_REGION_CACHE_TTL_SECONDS)

    return region


def validate_tenant_region(tenant_region: str, deploy_region: str) -> bool:
    """
    Check whether the tenant's region matches the service's deploy region.

    Args:
        tenant_region: The tenant's assigned region
        deploy_region: This service's DEPLOY_REGION

    Returns:
        True if regions match, False otherwise
    """
    match = tenant_region == deploy_region
    if not match:
        _increment_metric("mismatches")
    return match
