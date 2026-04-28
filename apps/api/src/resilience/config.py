"""Resilience configuration — thresholds from resilience.md and communication.md.

All thresholds are explicit (INV-011: no silent thresholds).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for a single circuit breaker."""
    failure_threshold: int
    failure_window_seconds: float
    open_duration_seconds: float
    half_open_probes: int
    success_to_close: int


# Per-dependency configurations from resilience.md
BREAKER_CONFIGS: dict[str, CircuitBreakerConfig] = {
    "llm_provider_a": CircuitBreakerConfig(
        failure_threshold=5, failure_window_seconds=60,
        open_duration_seconds=30, half_open_probes=1, success_to_close=3,
    ),
    "llm_provider_b": CircuitBreakerConfig(
        failure_threshold=5, failure_window_seconds=60,
        open_duration_seconds=30, half_open_probes=1, success_to_close=3,
    ),
    "firestore_writes": CircuitBreakerConfig(
        failure_threshold=3, failure_window_seconds=30,
        open_duration_seconds=15, half_open_probes=1, success_to_close=2,
    ),
    "firestore_reads": CircuitBreakerConfig(
        failure_threshold=5, failure_window_seconds=30,
        open_duration_seconds=15, half_open_probes=1, success_to_close=2,
    ),
    "gcs": CircuitBreakerConfig(
        failure_threshold=3, failure_window_seconds=30,
        open_duration_seconds=15, half_open_probes=1, success_to_close=2,
    ),
    "identity_provider": CircuitBreakerConfig(
        failure_threshold=3, failure_window_seconds=30,
        open_duration_seconds=60, half_open_probes=1, success_to_close=2,
    ),
}

# Allowed self-healing actions with bounds
SELF_HEALING_BOUNDS: dict[str, dict[str, int]] = {
    "llm_failover": {"max_per_hour": 3},
    "review_reassignment": {"max_per_case": 2},
    "export_retry": {"max_retries": 3},
    "pubsub_retry": {"max_retries": 10},
    "evidence_flag": {"max_per_batch": 100},
}

# All known kill switches
KILL_SWITCHES: list[str] = [
    "llm_provider_a",
    "llm_provider_b",
    "llm_all",
    "resolution",
    "batch_resolution",
    "exports",
    "review_assignment",
    "drift_detection",
]
