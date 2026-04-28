"""
================================================================================
INTELLIGENT ANALYST - NOSTRUM-GRADE PDF ENGINE (Days 17-20)
================================================================================

Enterprise-grade PDF certificate generation with:
- Energy/ESG metrics integration (Low Carbon badge)
- KMS Digital Signature Footer (ECDSA P-256)
- Dynamic company/tenant context
- Full forensic evidence chain

This module extends certificate_service.py with enhanced enterprise features.

Usage:
    from reporting.pdf_engine import build_evidence_certificate

    pdf_bytes, metadata = build_evidence_certificate(
        batch_id="BATCH-ABC123",
        tenant_context={"name": "Nostrum Energy", "id": "nostrum-energy"},
        forensic_data={...},
        signature_info={...}
    )

================================================================================
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# ============================================================================
# CONSTANTS
# ============================================================================

SYSTEM_NAME = "Intelligent Analyst"
SYSTEM_VERSION = "8.2.2"

# Energy efficiency thresholds (must match ForensicPanel.jsx)
ENERGY_LOW_CARBON_THRESHOLD = 0.95
ENERGY_MODERATE_THRESHOLD = 0.80

# ESG badge labels
ESG_BADGES = {
    "low_carbon": {"label": "LOW CARBON", "color": colors.Color(0.2, 0.8, 0.4)},
    "moderate": {"label": "MODERATE", "color": colors.Color(0.9, 0.7, 0.2)},
    "high_energy": {"label": "HIGH ENERGY", "color": colors.Color(0.9, 0.3, 0.3)},
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hash and return hex string."""
    return hashlib.sha256(data).hexdigest()


def _calculate_energy_rating(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate energy efficiency rating from batch stats.

    Returns:
        {
            "rating": "low_carbon" | "moderate" | "high_energy",
            "ratio": float (0.0-1.0),
            "badge": str,
            "l1_count": int,
            "l2_count": int,
            "l3_count": int,
            "total": int
        }
    """
    if not stats:
        return {"rating": "unavailable", "ratio": 0.0, "badge": "N/A", "total": 0}

    total = stats.get("total", 0) or stats.get("total_records", 0)
    if total == 0:
        return {"rating": "unavailable", "ratio": 0.0, "badge": "N/A", "total": 0}

    # Count L1 resolutions
    l1_exact = stats.get("layer_1_exact", 0) or stats.get("l1_exact", 0)
    l1_norm = stats.get("layer_1_norm", 0) or stats.get("l1_norm", 0)
    l1_count = l1_exact + l1_norm

    # Count L2 resolutions
    l2_count = (
        stats.get("layer_2_vector", 0) or
        stats.get("layer_2_total", 0) or
        stats.get("l2_vector", 0)
    )

    # Count L3 LLM calls
    l3_count = (
        stats.get("layer_3_llm", 0) or
        stats.get("layer_3_llm_calls", 0) or
        stats.get("l3_llm", 0)
    )

    # Energy efficiency = (L1 + L2) / Total
    efficient_ratio = (l1_count + l2_count) / total

    if efficient_ratio >= ENERGY_LOW_CARBON_THRESHOLD:
        rating = "low_carbon"
    elif efficient_ratio >= ENERGY_MODERATE_THRESHOLD:
        rating = "moderate"
    else:
        rating = "high_energy"

    return {
        "rating": rating,
        "ratio": efficient_ratio,
        "badge": ESG_BADGES[rating]["label"],
        "l1_count": l1_count,
        "l2_count": l2_count,
        "l3_count": l3_count,
        "total": total,
    }


def _format_signature_id(key_id: str) -> str:
    """Format KMS key ID for display (show last segment)."""
    if not key_id:
        return "N/A"
    # KMS key format: projects/.../locations/.../keyRings/.../cryptoKeys/.../cryptoKeyVersions/...
    parts = key_id.split("/")
    if len(parts) >= 2:
        return f".../{parts[-2]}/{parts[-1]}"
    return key_id[-40:] if len(key_id) > 40 else key_id


def _truncate_hash(hash_str: str, length: int = 16) -> str:
    """Truncate hash for display with ellipsis."""
    if not hash_str or len(hash_str) <= length:
        return hash_str or "N/A"
    return hash_str[:length] + "..."


# ============================================================================
# PDF BUILDER
# ============================================================================

def build_evidence_certificate(
    batch_id: str,
    tenant_context: Dict[str, Any],
    forensic_data: Dict[str, Any],
    signature_info: Optional[Dict[str, Any]] = None,
    batch_stats: Optional[Dict[str, Any]] = None,
    config_snapshot: Optional[Dict[str, Any]] = None,
    events: Optional[List[Dict]] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Build a Nostrum-Grade evidence certificate PDF.

    Args:
        batch_id: Batch trace ID
        tenant_context: {"id": "...", "name": "Nostrum Energy", ...}
        forensic_data: Forensic verification data (signatures, hash chain, etc.)
        signature_info: KMS signature metadata
        batch_stats: Batch processing statistics
        config_snapshot: Configuration at time of processing
        events: Audit events or evidence records

    Returns:
        Tuple of (pdf_bytes, metadata_dict)

        metadata_dict includes:
        - certificate_hash: SHA-256 of normalized evidence
        - energy_rating: Calculated ESG rating
        - signature_verified: Whether KMS signature is valid
    """
    generated_at = datetime.now(timezone.utc)

    # Extract tenant info
    company_name = tenant_context.get("name", tenant_context.get("id", "Unknown"))
    tenant_id = tenant_context.get("id", "unknown")

    # Calculate energy metrics
    energy_metrics = _calculate_energy_rating(batch_stats or {})

    # Extract signature info
    kms_key_id = ""
    signature_hash = ""
    signature_verified = False
    signed_at = ""

    if signature_info:
        kms_key_id = signature_info.get("signing_key_id", "")
        signature_hash = signature_info.get("signature_hash", "") or signature_info.get("evidence_hash_sha256", "")
        signature_verified = signature_info.get("verified", False) or signature_info.get("signature_verified", False)
        signed_at = signature_info.get("signed_at_utc", "") or signature_info.get("signed_at", "")

    # Fallback to forensic_data
    if not kms_key_id and forensic_data:
        sig_data = forensic_data.get("signature", {})
        kms_key_id = sig_data.get("signing_key_id", "")
        signature_hash = sig_data.get("evidence_hash_sha256", "")
        signature_verified = forensic_data.get("signature_verified", False)
        signed_at = sig_data.get("signed_at_utc", "")

    # Build normalized evidence for certificate hash
    evidence_obj = {
        "batch_id": batch_id,
        "tenant_id": tenant_id,
        "company_name": company_name,
        "generated_at": generated_at.isoformat(),
        "system_name": SYSTEM_NAME,
        "system_version": SYSTEM_VERSION,
        "energy_metrics": energy_metrics,
        "signature": {
            "kms_key_id": kms_key_id,
            "signature_hash": signature_hash,
            "verified": signature_verified,
            "signed_at": signed_at,
        },
        "stats": batch_stats or {},
        "config_snapshot": config_snapshot or {},
        "events_count": len(events) if events else 0,
    }
    evidence_json = json.dumps(evidence_obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    cert_hash = _sha256_hex(evidence_json)

    # ========================================================================
    # BUILD PDF
    # ========================================================================

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        title=f"{company_name} - Evidence Certificate",
        author=f"{SYSTEM_NAME} {SYSTEM_VERSION}",
        subject=f"Forensic Evidence Certificate for {batch_id}",
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=1.0*inch,  # Extra space for digital signature footer
    )

    styles = getSampleStyleSheet()

    # Custom styles
    styles.add(ParagraphStyle(
        name='CompanyHeader',
        parent=styles['Title'],
        fontSize=24,
        spaceAfter=6,
        textColor=colors.Color(0.1, 0.1, 0.15),
    ))
    styles.add(ParagraphStyle(
        name='CertTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceBefore=0,
        spaceAfter=12,
        textColor=colors.Color(0.2, 0.6, 0.8),
    ))
    styles.add(ParagraphStyle(
        name='SectionTitle',
        parent=styles['Heading3'],
        fontSize=11,
        spaceBefore=14,
        spaceAfter=8,
        textColor=colors.Color(0.15, 0.15, 0.2),
        borderPadding=4,
    ))
    styles.add(ParagraphStyle(
        name='FooterText',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.Color(0.4, 0.4, 0.4),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='MonoSmall',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        textColor=colors.Color(0.2, 0.2, 0.25),
    ))

    story = []

    # ------------------------------------------------------------------------
    # HEADER: Company Name and Certificate Title
    # ------------------------------------------------------------------------

    story.append(Paragraph(company_name.upper(), styles['CompanyHeader']))
    story.append(Paragraph("Forensic Evidence Certificate", styles['CertTitle']))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.Color(0.2, 0.6, 0.8)))
    story.append(Spacer(1, 12))

    # ------------------------------------------------------------------------
    # CERTIFICATE METADATA
    # ------------------------------------------------------------------------

    meta_data = [
        ["Batch ID", batch_id],
        ["Tenant ID", tenant_id],
        ["Generated At (UTC)", generated_at.strftime("%Y-%m-%d %H:%M:%S")],
        ["System Version", f"{SYSTEM_NAME} v{SYSTEM_VERSION}"],
        ["Certificate Hash", _truncate_hash(cert_hash, 32) + "..."],
    ]

    meta_table = Table(meta_data, colWidths=[140, 400])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.95, 0.97)),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.Color(0.15, 0.15, 0.2)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.85, 0.88)),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    # ------------------------------------------------------------------------
    # ENERGY / ESG METRICS
    # ------------------------------------------------------------------------

    story.append(Paragraph("Energy Efficiency Metrics", styles['SectionTitle']))

    esg_badge_color = ESG_BADGES.get(energy_metrics["rating"], ESG_BADGES["high_energy"])["color"]

    energy_data = [
        ["ESG Rating", energy_metrics["badge"]],
        ["Efficiency Ratio", f"{energy_metrics['ratio']*100:.1f}%"],
        ["L1 Deterministic", str(energy_metrics.get("l1_count", 0))],
        ["L2 Vector/Fuzzy", str(energy_metrics.get("l2_count", 0))],
        ["L3 LLM Calls", str(energy_metrics.get("l3_count", 0))],
        ["Total Records", str(energy_metrics.get("total", 0))],
    ]

    energy_table = Table(energy_data, colWidths=[140, 140])
    energy_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.97, 0.95)),
        ("BACKGROUND", (1, 0), (1, 0), esg_badge_color),  # Badge row color
        ("TEXTCOLOR", (1, 0), (1, 0), colors.white),  # Badge text white
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.Color(0.15, 0.15, 0.2)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.88, 0.85)),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(energy_table)

    # ESG explanation
    story.append(Spacer(1, 8))
    if energy_metrics["rating"] == "low_carbon":
        esg_text = (
            "<font color='green'><b>LOW CARBON:</b></font> This batch achieved over 95% resolution "
            "through deterministic (L1) and vector-based (L2) methods, minimizing LLM compute usage."
        )
    elif energy_metrics["rating"] == "moderate":
        esg_text = (
            "<font color='orange'><b>MODERATE:</b></font> This batch achieved 80-95% resolution "
            "through efficient methods. Some LLM calls were required for ambiguous cases."
        )
    else:
        esg_text = (
            "<font color='red'><b>HIGH ENERGY:</b></font> This batch required significant LLM "
            "processing. Consider expanding canonical lists for better efficiency."
        )
    story.append(Paragraph(esg_text, styles['Normal']))
    story.append(Spacer(1, 16))

    # ------------------------------------------------------------------------
    # PROCESSING STATISTICS
    # ------------------------------------------------------------------------

    if batch_stats:
        story.append(Paragraph("Processing Statistics", styles['SectionTitle']))

        stats_rows = []

        # Layer breakdown
        l0 = batch_stats.get("layer_0_garbage", 0) or batch_stats.get("l0_garbage", 0)
        l1_exact = batch_stats.get("layer_1_exact", 0) or batch_stats.get("l1_exact", 0)
        l1_norm = batch_stats.get("layer_1_norm", 0) or batch_stats.get("l1_norm", 0)
        l2 = batch_stats.get("layer_2_vector", 0) or batch_stats.get("l2_vector", 0)
        l3 = batch_stats.get("layer_3_llm", 0) or batch_stats.get("l3_llm", 0)
        l4 = batch_stats.get("layer_4_human", 0) or batch_stats.get("l4_human", 0)

        stats_rows.append(["L0 Garbage (Quarantined)", str(l0)])
        stats_rows.append(["L1 Exact Match", str(l1_exact)])
        stats_rows.append(["L1 Normalized Match", str(l1_norm)])
        stats_rows.append(["L2 Vector/Fuzzy", str(l2)])
        stats_rows.append(["L3 LLM Resolved", str(l3)])
        stats_rows.append(["L4 Human Review", str(l4)])

        # Add duration if available
        duration = batch_stats.get("duration_seconds")
        if duration:
            stats_rows.append(["Processing Duration", f"{duration:.1f}s"])

        stats_table = Table(stats_rows, colWidths=[200, 100])
        stats_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.95, 0.97)),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.Color(0.15, 0.15, 0.2)),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.85, 0.88)),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
            ("FONTNAME", (1, 0), (1, -1), "Courier"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 16))

    # ------------------------------------------------------------------------
    # CRYPTOGRAPHIC VERIFICATION
    # ------------------------------------------------------------------------

    story.append(Paragraph("Cryptographic Verification", styles['SectionTitle']))

    sig_status = "VERIFIED" if signature_verified else "NOT VERIFIED"
    sig_color = colors.Color(0.2, 0.7, 0.3) if signature_verified else colors.Color(0.8, 0.3, 0.3)

    crypto_data = [
        ["Signature Status", sig_status],
        ["Algorithm", "ECDSA P-256 SHA-256"],
        ["KMS Key ID", _format_signature_id(kms_key_id)],
        ["Evidence Hash", _truncate_hash(signature_hash, 24)],
        ["Signed At (UTC)", signed_at.split("T")[0] if signed_at else "N/A"],
    ]

    crypto_table = Table(crypto_data, colWidths=[140, 300])
    crypto_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.95, 0.97)),
        ("BACKGROUND", (1, 0), (1, 0), sig_color),  # Status row
        ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.Color(0.15, 0.15, 0.2)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.85, 0.88)),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 1), (1, -1), "Courier"),
        ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(crypto_table)
    story.append(Spacer(1, 8))

    # Full hashes for copy-paste
    story.append(Paragraph("<b>Full Certificate Hash (SHA-256):</b>", styles['Normal']))
    story.append(Paragraph(f"<font face='Courier' size='7'>{cert_hash}</font>", styles['Normal']))
    story.append(Spacer(1, 6))

    if signature_hash:
        story.append(Paragraph("<b>Full Evidence Hash (SHA-256):</b>", styles['Normal']))
        story.append(Paragraph(f"<font face='Courier' size='7'>{signature_hash}</font>", styles['Normal']))

    story.append(Spacer(1, 20))

    # ------------------------------------------------------------------------
    # HASH CHAIN INFO (if available)
    # ------------------------------------------------------------------------

    hash_chain = forensic_data.get("hash_chain", {})
    if hash_chain.get("chain_enabled"):
        story.append(Paragraph("Hash Chain Integrity", styles['SectionTitle']))

        chain_verified = hash_chain.get("verified", False)
        chain_status = "VERIFIED" if chain_verified else "NOT VERIFIED"
        chain_color = colors.Color(0.2, 0.7, 0.3) if chain_verified else colors.Color(0.8, 0.3, 0.3)

        chain_data = [
            ["Chain Status", chain_status],
            ["Chain Length", str(hash_chain.get("chain_length", "N/A"))],
            ["Algorithm", hash_chain.get("chain_algo", "SHA-256")],
            ["Root Hash", _truncate_hash(hash_chain.get("batch_root_hash", ""), 24)],
        ]

        chain_table = Table(chain_data, colWidths=[140, 300])
        chain_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.93, 0.95, 0.97)),
            ("BACKGROUND", (1, 0), (1, 0), chain_color),
            ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.Color(0.15, 0.15, 0.2)),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.85, 0.88)),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 1), (1, -1), "Courier"),
            ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(chain_table)
        story.append(Spacer(1, 16))

    # ------------------------------------------------------------------------
    # DIGITAL SIGNATURE FOOTER
    # ------------------------------------------------------------------------

    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.Color(0.6, 0.6, 0.65)))
    story.append(Spacer(1, 8))

    # Digital signature block
    sig_block_data = [
        [
            Paragraph("<b>DIGITAL SIGNATURE</b>", styles['FooterText']),
            Paragraph(f"<b>KMS Key:</b> {_format_signature_id(kms_key_id)}", styles['FooterText']),
            Paragraph(f"<b>Signature Hash:</b> {_truncate_hash(signature_hash, 20)}", styles['FooterText']),
        ]
    ]

    sig_block = Table(sig_block_data, colWidths=[180, 180, 180])
    sig_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.97, 0.97, 0.98)),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.Color(0.3, 0.3, 0.35)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.75)),
    ]))
    story.append(sig_block)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"This certificate was cryptographically signed by {SYSTEM_NAME} v{SYSTEM_VERSION} "
        f"using Google Cloud KMS (ECDSA P-256). Verify signature at: "
        f"<font face='Courier' size='6'>api.intelligentanalyst.ai/verify/{batch_id}</font>",
        styles['FooterText']
    ))
    story.append(Paragraph(
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')} | "
        f"Tenant: {tenant_id}",
        styles['FooterText']
    ))

    # Build PDF
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    # Return metadata
    metadata = {
        "certificate_hash": cert_hash,
        "energy_rating": energy_metrics["rating"],
        "energy_badge": energy_metrics["badge"],
        "energy_ratio": energy_metrics["ratio"],
        "signature_verified": signature_verified,
        "kms_key_id": kms_key_id,
        "signature_hash": signature_hash,
        "generated_at": generated_at.isoformat(),
        "tenant_id": tenant_id,
        "company_name": company_name,
        "batch_id": batch_id,
        "pdf_size_bytes": len(pdf_bytes),
    }

    return pdf_bytes, metadata


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def build_certificate_from_batch(
    batch_doc: Dict[str, Any],
    verification_data: Optional[Dict[str, Any]] = None,
    tenant_name: Optional[str] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Convenience function to build certificate from a batch document.

    Args:
        batch_doc: Firestore batch document
        verification_data: Optional verification endpoint response
        tenant_name: Override tenant name (e.g., "Nostrum Energy")

    Returns:
        (pdf_bytes, metadata)
    """
    batch_id = batch_doc.get("trace_id", batch_doc.get("batch_id", "UNKNOWN"))
    tenant_id = batch_doc.get("tenant_id", "unknown")

    tenant_context = {
        "id": tenant_id,
        "name": tenant_name or tenant_id.replace("-", " ").title(),
    }

    # Extract stats
    stats = batch_doc.get("stats") or batch_doc.get("counts") or {}
    if not stats:
        # Try to build from individual fields
        stats = {
            "total": batch_doc.get("total_records") or batch_doc.get("total", 0),
            "layer_0_garbage": batch_doc.get("l0_garbage", 0),
            "layer_1_exact": batch_doc.get("l1_exact", 0),
            "layer_1_norm": batch_doc.get("l1_norm", 0),
            "layer_2_vector": batch_doc.get("l2_vector", 0),
            "layer_3_llm": batch_doc.get("l3_llm", 0),
            "layer_4_human": batch_doc.get("l4_human", 0),
            "duration_seconds": batch_doc.get("duration_seconds"),
        }

    # Extract signature info
    signature_info = batch_doc.get("signature") or {}
    if verification_data:
        signature_info = verification_data.get("signature", signature_info)
        signature_info["signature_verified"] = verification_data.get("signature_verified", False)

    # Config snapshot
    config_snapshot = batch_doc.get("config_snapshot") or batch_doc.get("config") or {}

    return build_evidence_certificate(
        batch_id=batch_id,
        tenant_context=tenant_context,
        forensic_data=verification_data or {},
        signature_info=signature_info,
        batch_stats=stats,
        config_snapshot=config_snapshot,
    )


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test data
    test_batch = {
        "trace_id": "BATCH-TEST123456",
        "tenant_id": "nostrum-energy",
        "total_records": 10000,
        "stats": {
            "total": 10000,
            "layer_0_garbage": 50,
            "layer_1_exact": 3500,
            "layer_1_norm": 2500,
            "layer_2_vector": 3200,
            "layer_3_llm": 200,
            "layer_4_human": 550,
            "duration_seconds": 45.7,
        },
        "signature": {
            "signing_key_id": "projects/example-project/locations/us-central1/keyRings/forensic/cryptoKeys/evidence-signing/cryptoKeyVersions/1",
            "evidence_hash_sha256": "abc123def456789012345678901234567890abcdef1234567890abcdef12345678",
            "signed_at_utc": "2026-02-15T10:30:00Z",
        },
    }

    test_verification = {
        "signature_verified": True,
        "hash_chain": {
            "chain_enabled": True,
            "verified": True,
            "chain_length": 10000,
            "chain_algo": "SHA-256",
            "batch_root_hash": "def456abc789012345678901234567890fedcba0987654321abcdef1234567890",
        },
    }

    pdf_bytes, metadata = build_certificate_from_batch(
        test_batch,
        verification_data=test_verification,
        tenant_name="Nostrum Energy",
    )

    print(f"PDF generated:")
    print(f"  Size: {len(pdf_bytes):,} bytes")
    print(f"  Certificate Hash: {metadata['certificate_hash'][:32]}...")
    print(f"  Energy Rating: {metadata['energy_badge']}")
    print(f"  Signature Verified: {metadata['signature_verified']}")

    # Save test PDF
    with open("/tmp/nostrum_evidence_cert.pdf", "wb") as f:
        f.write(pdf_bytes)
    print(f"  Saved to: /tmp/nostrum_evidence_cert.pdf")
