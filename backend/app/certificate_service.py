"""
================================================================================
INTELLIGENT ANALYST v8.2.2 - CERTIFICATE SERVICE
================================================================================

Generates PDF transparency certificates for audit trails.
Isolated module to keep the main server file clean.

Usage:
    from certificate_service import make_certificate_input, build_transparency_certificate_pdf
    
    ci = make_certificate_input(trace_id, tenant_id, ...)
    pdf_bytes, cert_hash = build_transparency_certificate_pdf(ci)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors


@dataclass(frozen=True)
class CertificateInput:
    """Immutable input for certificate generation."""
    trace_id: str
    tenant_id: str
    generated_at_iso: str
    system_name: str
    system_version: str

    # Evidence (keep generic for compatibility)
    # events can be a list (batch trace) OR a single dict (single decision trace)
    events: Any

    # Optional metadata snapshots
    config_snapshot: Optional[Dict[str, Any]] = None
    security_snapshot: Optional[Dict[str, Any]] = None


def _sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hash and return hex string."""
    return hashlib.sha256(data).hexdigest()


def build_transparency_certificate_pdf(payload: CertificateInput) -> Tuple[bytes, str]:
    """
    Build a PDF transparency certificate.
    
    Returns: (pdf_bytes, certificate_hash_sha256)
    
    The certificate_hash is SHA-256 of the normalized JSON evidence payload,
    not the PDF bytes. This ensures reproducibility.
    """
    # Normalize evidence payload for deterministic hashing
    evidence_obj = {
        "trace_id": payload.trace_id,
        "tenant_id": payload.tenant_id,
        "generated_at": payload.generated_at_iso,
        "system_name": payload.system_name,
        "system_version": payload.system_version,
        "events": payload.events,
        "config_snapshot": payload.config_snapshot or {},
        "security_snapshot": payload.security_snapshot or {},
    }
    evidence_json = json.dumps(evidence_obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    cert_hash = _sha256_hex(evidence_json)

    # Build PDF
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, 
        pagesize=LETTER, 
        title="Intelligent Analyst - Transparency Certificate",
        author="Intelligent Analyst v8.2.2",
        subject=f"Audit Certificate for {payload.trace_id}"
    )
    styles = getSampleStyleSheet()

    story = []
    
    # Header
    story.append(Paragraph("INTELLIGENT ANALYST", styles["Title"]))
    story.append(Paragraph("Data Transparency Certificate", styles["Heading2"]))
    story.append(Spacer(1, 12))

    # Metadata table
    meta_rows = [
        ["Trace ID", payload.trace_id],
        ["Tenant ID", payload.tenant_id],
        ["Generated At (UTC)", payload.generated_at_iso],
        ["System Version", payload.system_version],
        ["Certificate Hash (SHA-256)", cert_hash[:32] + "..."],  # Truncate for display
    ]
    meta = Table(meta_rows, colWidths=[160, 380])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.95, 0.95)),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta)
    story.append(Spacer(1, 14))

    # Full hash (separate for copy-paste)
    story.append(Paragraph("Full Certificate Hash", styles["Heading4"]))
    story.append(Paragraph(f"<font face='Courier' size='8'>{cert_hash}</font>", styles["Normal"]))
    story.append(Spacer(1, 14))

    # Evidence summary
    story.append(Paragraph("Evidence Summary", styles["Heading3"]))
    events = payload.events
    if isinstance(events, list):
        event_count = len(events)
        story.append(Paragraph(f"Total events captured: <b>{event_count}</b>", styles["Normal"]))
        
        # Layer breakdown if available
        layer_counts = {}
        flagged_count = 0
        for ev in events:
            if isinstance(ev, dict):
                layer = ev.get("layer_used", ev.get("layer", "unknown"))
                layer_counts[layer] = layer_counts.get(layer, 0) + 1
                if ev.get("flag"):
                    flagged_count += 1
        
        if layer_counts:
            story.append(Spacer(1, 6))
            layer_text = ", ".join(f"L{k}: {v}" for k, v in sorted(layer_counts.items()) if isinstance(k, int))
            if layer_text:
                story.append(Paragraph(f"Layer distribution: {layer_text}", styles["Normal"]))
            if flagged_count > 0:
                story.append(Paragraph(f"Flagged for review: <b>{flagged_count}</b>", styles["Normal"]))
                
    elif isinstance(events, dict):
        story.append(Paragraph("Evidence captured: single trace record", styles["Normal"]))
    else:
        story.append(Paragraph("Evidence captured: (unrecognized format)", styles["Normal"]))

    story.append(Spacer(1, 10))

    # Evidence excerpt (bounded to keep PDF small)
    story.append(Paragraph("Evidence Excerpt (JSON)", styles["Heading3"]))
    excerpt = json.dumps(evidence_obj, indent=2, ensure_ascii=False)
    if len(excerpt) > 3000:
        excerpt = excerpt[:3000] + "\n... [truncated]"
    
    # Escape HTML special chars and format for PDF
    excerpt_safe = (excerpt
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
        .replace("  ", "&nbsp;&nbsp;")
    )
    story.append(Paragraph(f"<font face='Courier' size='7'>{excerpt_safe}</font>", styles["Normal"]))
    story.append(Spacer(1, 10))

    # Security snapshot if provided
    if payload.security_snapshot:
        story.append(Paragraph("Security Snapshot", styles["Heading3"]))
        sec = json.dumps(payload.security_snapshot, indent=2, ensure_ascii=False)
        if len(sec) > 1500:
            sec = sec[:1500] + "\n... [truncated]"
        sec_safe = (sec
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
            .replace("  ", "&nbsp;&nbsp;")
        )
        story.append(Paragraph(f"<font face='Courier' size='7'>{sec_safe}</font>", styles["Normal"]))
        story.append(Spacer(1, 10))

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "<font size='8' color='grey'>This certificate was automatically generated by Intelligent Analyst. "
        "The SHA-256 hash can be used to verify the integrity of this audit record.</font>",
        styles["Normal"]
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes, cert_hash


def make_certificate_input(
    trace_id: str,
    tenant_id: str,
    system_name: str,
    system_version: str,
    events: Any,
    config_snapshot: Optional[Dict[str, Any]] = None,
    security_snapshot: Optional[Dict[str, Any]] = None,
) -> CertificateInput:
    """Factory function to create CertificateInput with current timestamp."""
    return CertificateInput(
        trace_id=trace_id,
        tenant_id=tenant_id,
        generated_at_iso=datetime.now(timezone.utc).isoformat(),
        system_name=system_name,
        system_version=system_version,
        events=events,
        config_snapshot=config_snapshot,
        security_snapshot=security_snapshot,
    )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Quick test
    test_events = [
        {"row_index": 0, "company_raw": "Microsoft", "layer_used": 1, "flag": None},
        {"row_index": 1, "company_raw": "Google", "layer_used": 1, "flag": None},
        {"row_index": 2, "company_raw": "Unknown Corp", "layer_used": 4, "flag": "REVIEW"},
    ]
    
    ci = make_certificate_input(
        trace_id="BATCH-TEST1234",
        tenant_id="demo-tenant",
        system_name="Intelligent Analyst",
        system_version="8.2.2",
        events=test_events,
        config_snapshot={"vector_threshold": 0.55},
        security_snapshot={"cors_enabled": True, "auth_required": True},
    )
    
    pdf_bytes, cert_hash = build_transparency_certificate_pdf(ci)
    
    print(f"✅ Certificate generated")
    print(f"   PDF size: {len(pdf_bytes):,} bytes")
    print(f"   SHA-256:  {cert_hash}")
    
    # Save test PDF
    with open("/tmp/test_certificate.pdf", "wb") as f:
        f.write(pdf_bytes)
    print(f"   Saved to: /tmp/test_certificate.pdf")
