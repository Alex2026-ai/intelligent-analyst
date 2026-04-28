"""CSV export — tabular summary of resolution + evidence."""

from __future__ import annotations

import csv
import io
from typing import Any


def render_csv(
    resolution: dict[str, Any],
    evidence_nodes: list[dict[str, Any]],
    include_evidence: bool = True,
) -> bytes:
    """Render resolution as CSV. One row per evidence node."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "resolution_id", "status", "confidence", "layer_used",
        "node_id", "node_type", "sequence", "timestamp",
    ])

    if include_evidence and evidence_nodes:
        for node in evidence_nodes:
            writer.writerow([
                resolution.get("resolution_id", ""),
                resolution.get("status", ""),
                resolution.get("confidence", ""),
                resolution.get("layer_used", ""),
                node.get("node_id", ""),
                node.get("node_type", ""),
                node.get("sequence", ""),
                node.get("timestamp", ""),
            ])
    else:
        writer.writerow([
            resolution.get("resolution_id", ""),
            resolution.get("status", ""),
            resolution.get("confidence", ""),
            resolution.get("layer_used", ""),
            "", "", "", "",
        ])

    return output.getvalue().encode("utf-8")
