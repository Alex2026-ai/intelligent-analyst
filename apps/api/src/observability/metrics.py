"""Application metrics — all SLI metrics from observability-slo-plan.md.

Uses a simple in-memory metrics collector for testing. In production,
this would use OpenTelemetry SDK exporting to Cloud Monitoring.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class MetricPoint:
    """A single metric observation."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """In-memory metrics collector.

    Collects counters, histograms, and gauges. Thread-safe.
    In production, replaced by OpenTelemetry MeterProvider.
    """

    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, float] = {}
        self._lock = Lock()

    def increment(self, name: str, value: float = 1.0, **labels: str) -> None:
        """Increment a counter metric."""
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def record(self, name: str, value: float, **labels: str) -> None:
        """Record a histogram observation."""
        key = self._key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        """Set a gauge value."""
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def get_counter(self, name: str, **labels: str) -> float:
        key = self._key(name, labels)
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_histogram(self, name: str, **labels: str) -> list[float]:
        key = self._key(name, labels)
        with self._lock:
            return list(self._histograms.get(key, []))

    def get_gauge(self, name: str, **labels: str) -> float | None:
        key = self._key(name, labels)
        with self._lock:
            return self._gauges.get(key)

    def clear(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._gauges.clear()

    @staticmethod
    def _key(name: str, labels: dict[str, str]) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Singleton metrics instance
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    return _metrics


# --- SLI metric names (from observability-slo-plan.md) ---

RESOLUTION_DURATION_MS = "resolution.duration_ms"
RESOLUTION_COUNT = "resolution.count"
RESOLUTION_LAYER_USED = "resolution.layer_used"
RESOLUTION_CONFIDENCE = "resolution.confidence"
RESOLUTION_ERROR_COUNT = "resolution.error_count"

REVIEW_QUEUE_DEPTH = "review.queue_depth"
REVIEW_SLA_BREACH_COUNT = "review.sla_breach_count"

CIRCUIT_BREAKER_STATE_CHANGE = "circuit_breaker.state_change"

EVIDENCE_INTEGRITY_CHECK = "evidence.integrity_check"

EXPORT_COUNT = "export.count"
EXPORT_ERROR_COUNT = "export.error_count"

LLM_LATENCY_MS = "llm.latency_ms"
LLM_ERROR_COUNT = "llm.error_count"

HTTP_REQUEST_COUNT = "http.request_count"
HTTP_REQUEST_DURATION_MS = "http.request_duration_ms"
HTTP_ERROR_COUNT = "http.error_count"

STARTUP_DURATION_MS = "startup.duration_ms"

SLO_ERROR_BUDGET_REMAINING = "slo.error_budget_remaining"
