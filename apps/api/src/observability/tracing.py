"""Distributed tracing — span creation and trace context propagation.

In production, uses OpenTelemetry SDK exporting to Cloud Trace.
This module provides a lightweight in-memory tracer for testing.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Span:
    """A trace span representing a unit of work."""

    span_id: str
    trace_id: str
    name: str
    start_time: float
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    parent_span_id: str | None = None
    status: str = "OK"

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000


class InMemoryTracer:
    """In-memory tracer for testing. Collects spans without exporting."""

    def __init__(self, service_name: str = "ia-api") -> None:
        self._service_name = service_name
        self._spans: list[Span] = []
        self._current_trace_id: str | None = None

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> Span:
        """Start a new span."""
        tid = trace_id or self._current_trace_id or str(uuid.uuid4())
        self._current_trace_id = tid
        span = Span(
            span_id=str(uuid.uuid4()),
            trace_id=tid,
            name=name,
            start_time=time.monotonic(),
            attributes={"service": self._service_name, **(attributes or {})},
            parent_span_id=parent_span_id,
        )
        self._spans.append(span)
        return span

    def end_span(self, span: Span, status: str = "OK") -> None:
        """End a span, recording its completion time."""
        span.end_time = time.monotonic()
        span.status = status

    def get_spans(self) -> list[Span]:
        return list(self._spans)

    def clear(self) -> None:
        self._spans.clear()
        self._current_trace_id = None


def extract_trace_context(headers: dict[str, str]) -> dict[str, str]:
    """Extract trace context from HTTP/Pub/Sub headers.

    Format: "00/{trace_id}/{parent_span_id}/01"
    Uses '/' separator to avoid conflict with UUID dashes.
    """
    context: dict[str, str] = {}
    traceparent = headers.get("traceparent", "")
    if traceparent:
        parts = traceparent.split("/")
        if len(parts) >= 3:
            context["trace_id"] = parts[1]
            context["parent_span_id"] = parts[2]
    return context


def inject_trace_context(span: Span) -> dict[str, str]:
    """Inject trace context into headers for propagation (e.g., to Pub/Sub).

    Format: "00/{trace_id}/{span_id}/01"
    """
    return {
        "traceparent": f"00/{span.trace_id}/{span.span_id}/01",
    }
