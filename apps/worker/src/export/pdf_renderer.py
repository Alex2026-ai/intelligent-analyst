"""PDF export — text-based report of resolution + evidence.

Uses plain text format for now. In production, would use reportlab or weasyprint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def render_pdf(
    resolution: dict[str, Any],
    evidence_nodes: list[dict[str, Any]],
    include_evidence: bool = True,
) -> bytes:
    """Render resolution as a PDF-like text report.

    Every export includes evidence reference (INV-012).
    In production, this would generate actual PDF via reportlab.
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("INTELLIGENT ANALYST — RESOLUTION REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Resolution ID: {resolution.get('resolution_id', 'N/A')}")
    lines.append(f"Status: {resolution.get('status', 'N/A')}")
    lines.append(f"Confidence: {resolution.get('confidence', 'N/A')}")
    lines.append(f"Layer Used: {resolution.get('layer_used', 'N/A')}")
    lines.append("")

    if resolution.get("resolution"):
        lines.append("Resolution:")
        lines.append(f"  {resolution['resolution']}")
        lines.append("")

    if include_evidence and evidence_nodes:
        lines.append("-" * 40)
        lines.append("EVIDENCE CHAIN")
        lines.append("-" * 40)
        for node in evidence_nodes:
            lines.append(f"  [{node.get('sequence', '?')}] {node.get('node_type', '?')}")
            lines.append(f"      Time: {node.get('timestamp', '?')}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("END OF REPORT")

    return "\n".join(lines).encode("utf-8")
