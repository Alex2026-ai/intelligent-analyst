"""PMC policy configuration — load from store with TTL cache.

Fail-closed: if config is absent, malformed, or Firestore fails,
returns cached policy (if warm) or safe default.
No background threads. No external cache. In-process only.

TTL cache contract:
- Default TTL: 60 seconds
- On cache hit within TTL: return cached policy, no Firestore read
- On cache miss/expiry: read Firestore, update cache
- On Firestore failure with warm cache: use cached policy
- On Firestore failure without cache: use safe default
- Malformed Firestore data never poisons the cache
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any

from apps.api.src.public_metadata.models import PolicyMode, PublicMetadataPolicy
from apps.api.src.storage.firestore.protocol import FirestoreClientProtocol

logger = logging.getLogger(__name__)
config_logger = logging.getLogger("ia.pmc.config")

PMC_CONFIG_PATH = "pmc_config"
PMC_CONFIG_DOC = "active_policy"
DEFAULT_CACHE_TTL_SECONDS: float = 60.0

_SAFE_DEFAULT = PublicMetadataPolicy(
    policy_id="pmc-safe-default",
    version="1.0",
    mode=PolicyMode.CURATED_HYBRID,
    allow_real_sanitized_samples=True,
    require_manual_approval=True,
    public_anchor_allowlist=["INV-002", "INV-005", "INV-006"],
    blocked_tenants=[],
)

# --- In-process TTL cache ---
_cached_policy: PublicMetadataPolicy | None = None
_cached_at: float = 0.0
_cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS


def _emit(event_type: str, policy_id: str = "", version: str = "") -> dict[str, Any]:
    event: dict[str, Any] = {"event": f"pmc_config_{event_type}"}
    if policy_id:
        event["policy_id"] = policy_id
    if version:
        event["version"] = version
    config_logger.info("%s", event)
    return event


def get_safe_default_policy() -> PublicMetadataPolicy:
    return _SAFE_DEFAULT


def reset_cache() -> None:
    """Clear the policy cache. For tests only."""
    global _cached_policy, _cached_at
    _cached_policy = None
    _cached_at = 0.0


def set_cache_ttl(ttl: float) -> None:
    """Override cache TTL. For tests only."""
    global _cache_ttl
    _cache_ttl = ttl


def _is_warm() -> bool:
    return _cached_policy is not None and (time.monotonic() - _cached_at) < _cache_ttl


def _parse(data: dict[str, Any]) -> PublicMetadataPolicy:
    return PublicMetadataPolicy(
        policy_id=data.get("policy_id", _SAFE_DEFAULT.policy_id),
        version=data.get("version", _SAFE_DEFAULT.version),
        mode=PolicyMode(data.get("mode", _SAFE_DEFAULT.mode.value)),
        allow_real_sanitized_samples=data.get(
            "allow_real_sanitized_samples", _SAFE_DEFAULT.allow_real_sanitized_samples),
        require_manual_approval=data.get(
            "require_manual_approval", _SAFE_DEFAULT.require_manual_approval),
        public_anchor_allowlist=data.get(
            "public_anchor_allowlist", list(_SAFE_DEFAULT.public_anchor_allowlist)),
        blocked_tenants=data.get("blocked_tenants", list(_SAFE_DEFAULT.blocked_tenants)),
    )


async def load_policy(db: FirestoreClientProtocol | None) -> PublicMetadataPolicy:
    """Load PMC policy with in-process TTL cache. Fail-closed."""
    global _cached_policy, _cached_at

    if db is None:
        return _cached_policy if _cached_policy is not None else _SAFE_DEFAULT

    if _is_warm():
        _emit("cache_hit", _cached_policy.policy_id, _cached_policy.version)
        return _cached_policy

    # Cache miss/expired — read Firestore
    _emit("cache_miss")
    try:
        result = db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).get()
        if inspect.isawaitable(result):
            result = await result

        if result is None:
            _emit("cache_fallback_safe_default")
            return _cached_policy if _cached_policy is not None else _SAFE_DEFAULT

        data = result.to_dict() if hasattr(result, "to_dict") else result
        if not data or not isinstance(data, dict):
            _emit("cache_fallback_safe_default")
            return _cached_policy if _cached_policy is not None else _SAFE_DEFAULT

        new_policy = _parse(data)
        _cached_policy = new_policy
        _cached_at = time.monotonic()
        _emit("cache_refresh", new_policy.policy_id, new_policy.version)
        return new_policy

    except Exception as e:
        logger.warning("PMC config load failed: %s", e)
        if _cached_policy is not None:
            _emit("cache_hit", _cached_policy.policy_id, _cached_policy.version)
            return _cached_policy
        _emit("cache_fallback_safe_default")
        return _SAFE_DEFAULT
