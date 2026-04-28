"""Export artifact generator — dispatches to format-specific renderers."""

from __future__ import annotations

from typing import Any

from apps.worker.src.export.csv_exporter import render_csv
from apps.worker.src.export.json_exporter import render_json
from apps.worker.src.export.pdf_renderer import render_pdf


def generate_export(
    resolution: dict[str, Any],
    evidence_nodes: list[dict[str, Any]],
    format: str,
    include_evidence: bool = True,
    include_source_document: bool = False,
) -> bytes:
    """Generate an export artifact in the requested format.

    Args:
        resolution: Resolution data dict.
        evidence_nodes: List of evidence node dicts.
        format: Output format (pdf, json, csv).
        include_evidence: Whether to include evidence chain.
        include_source_document: Whether to include source document.

    Returns:
        Export artifact as bytes.

    Raises:
        ValueError: If format is unsupported.
    """
    if format == "json":
        return render_json(resolution, evidence_nodes, include_evidence)
    elif format == "csv":
        return render_csv(resolution, evidence_nodes, include_evidence)
    elif format == "pdf":
        return render_pdf(resolution, evidence_nodes, include_evidence)
    else:
        raise ValueError(f"Unsupported export format: {format}")
