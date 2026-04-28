"""JSON export — structured resolution + evidence output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def render_json(
    resolution: dict[str, Any],
    evidence_nodes: list[dict[str, Any]],
    include_evidence: bool = True,
) -> bytes:
    """Render resolution as structured JSON.

    Every export includes evidence reference (INV-012).
    """
    output: dict[str, Any] = {
        "export_format": "json",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "resolution": {
            "resolution_id": resolution.get("resolution_id"),
            "status": resolution.get("status"),
            "confidence": resolution.get("confidence"),
            "layer_used": resolution.get("layer_used"),
            "resolution_text": resolution.get("resolution"),
        },
    }

    if include_evidence:
        output["evidence_chain"] = {
            "node_count": len(evidence_nodes),
            "nodes": [
                {
                    "node_id": n.get("node_id"),
                    "node_type": n.get("node_type"),
                    "sequence": n.get("sequence"),
                    "timestamp": n.get("timestamp"),
                }
                for n in evidence_nodes
            ],
        }
    else:
        output["evidence_chain"] = {"note": "Evidence excluded from export"}

    return json.dumps(output, indent=2, ensure_ascii=True).encode("utf-8")
