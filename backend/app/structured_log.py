"""
Structured JSON logging for Cloud Run stdout capture.
Zero dependencies beyond stdlib. Non-blocking. Microsecond overhead per call.

GCP Cloud Run auto-parses JSON stdout lines into structured Cloud Logging
entries with severity, trace_id, and custom fields.
"""

import json
import time
from typing import Any, Optional


def slog(
    *,
    trace_id: str,
    phase: str,
    event: str,
    elapsed_seconds: Optional[float] = None,
    batch_start_time: Optional[float] = None,
    **kwargs: Any
) -> None:
    """
    Emit a single-line JSON log to stdout.

    Args:
        trace_id: Batch trace ID (e.g. "BATCH-A1B2C3D4")
        phase: Pipeline phase (parse, phase1, phase2, hash_chain, replay,
               forensic, lifecycle, resolution)
        event: Event name (e.g. "phase1_complete", "l3_heartbeat")
        elapsed_seconds: Explicit elapsed time. If None, computed from batch_start_time.
        batch_start_time: time.time() value from batch start.
        **kwargs: Additional fields merged into the log entry.
    """
    entry = {
        "severity": "INFO",
        "trace_id": trace_id,
        "phase": phase,
        "event": event,
        "ts": time.time(),
    }

    if elapsed_seconds is not None:
        entry["elapsed_seconds"] = round(elapsed_seconds, 3)
    elif batch_start_time is not None:
        entry["elapsed_seconds"] = round(time.time() - batch_start_time, 3)

    # Allow kwargs to override severity (for slog_error)
    entry.update(kwargs)
    print(json.dumps(entry, default=str), flush=True)


def slog_error(
    *,
    trace_id: str,
    phase: str,
    event: str,
    error_type: str,
    error_message: str,
    batch_start_time: Optional[float] = None,
    **kwargs: Any
) -> None:
    """Emit a structured error log with severity=ERROR."""
    slog(
        trace_id=trace_id,
        phase=phase,
        event=event,
        batch_start_time=batch_start_time,
        severity="ERROR",
        error_type=error_type,
        error_message=error_message,
        **kwargs
    )
