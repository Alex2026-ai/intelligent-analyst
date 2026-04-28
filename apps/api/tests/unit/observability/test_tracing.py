"""Tests for distributed tracing."""

from apps.api.src.observability.tracing import (
    InMemoryTracer,
    extract_trace_context,
    inject_trace_context,
)


class TestInMemoryTracer:
    def test_start_and_end_span(self):
        tracer = InMemoryTracer()
        span = tracer.start_span("test-op", attributes={"key": "value"})
        assert span.name == "test-op"
        assert span.attributes["key"] == "value"
        assert span.end_time is None
        tracer.end_span(span)
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_span_collects(self):
        tracer = InMemoryTracer()
        tracer.start_span("op1")
        tracer.start_span("op2")
        assert len(tracer.get_spans()) == 2

    def test_trace_id_propagates(self):
        tracer = InMemoryTracer()
        s1 = tracer.start_span("parent")
        s2 = tracer.start_span("child", parent_span_id=s1.span_id)
        assert s2.trace_id == s1.trace_id
        assert s2.parent_span_id == s1.span_id

    def test_clear(self):
        tracer = InMemoryTracer()
        tracer.start_span("op")
        tracer.clear()
        assert len(tracer.get_spans()) == 0


class TestTraceContextPropagation:
    def test_inject_and_extract(self):
        tracer = InMemoryTracer()
        span = tracer.start_span("producer")
        headers = inject_trace_context(span)
        assert "traceparent" in headers

        context = extract_trace_context(headers)
        assert context["trace_id"] == span.trace_id
        assert context["parent_span_id"] == span.span_id

    def test_extract_empty_headers(self):
        context = extract_trace_context({})
        assert context == {}

    def test_extract_malformed_traceparent(self):
        context = extract_trace_context({"traceparent": "invalid"})
        assert context == {}
