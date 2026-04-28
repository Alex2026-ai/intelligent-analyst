"""Tests for metrics collection."""

from apps.api.src.observability.metrics import (
    RESOLUTION_COUNT,
    RESOLUTION_DURATION_MS,
    MetricsCollector,
)


class TestMetricsCollector:
    def test_counter_increment(self):
        m = MetricsCollector()
        m.increment(RESOLUTION_COUNT)
        m.increment(RESOLUTION_COUNT)
        assert m.get_counter(RESOLUTION_COUNT) == 2.0

    def test_counter_with_labels(self):
        m = MetricsCollector()
        m.increment(RESOLUTION_COUNT, layer="L1")
        m.increment(RESOLUTION_COUNT, layer="L2")
        m.increment(RESOLUTION_COUNT, layer="L1")
        assert m.get_counter(RESOLUTION_COUNT, layer="L1") == 2.0
        assert m.get_counter(RESOLUTION_COUNT, layer="L2") == 1.0

    def test_histogram_record(self):
        m = MetricsCollector()
        m.record(RESOLUTION_DURATION_MS, 150.0)
        m.record(RESOLUTION_DURATION_MS, 200.0)
        values = m.get_histogram(RESOLUTION_DURATION_MS)
        assert values == [150.0, 200.0]

    def test_gauge_set(self):
        m = MetricsCollector()
        m.set_gauge("review.queue_depth", 42)
        assert m.get_gauge("review.queue_depth") == 42
        m.set_gauge("review.queue_depth", 10)
        assert m.get_gauge("review.queue_depth") == 10

    def test_clear(self):
        m = MetricsCollector()
        m.increment("a")
        m.record("b", 1.0)
        m.set_gauge("c", 1)
        m.clear()
        assert m.get_counter("a") == 0.0
        assert m.get_histogram("b") == []
        assert m.get_gauge("c") is None

    def test_missing_counter_returns_zero(self):
        m = MetricsCollector()
        assert m.get_counter("nonexistent") == 0.0
