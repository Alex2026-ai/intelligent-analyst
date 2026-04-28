"""
================================================================================
INTELLIGENT ANALYST - ENERGY/CARBON ESTIMATOR MODULE
================================================================================

Provides ESTIMATES (not measurements) of energy consumption and carbon emissions
for forensic evidence blobs.

CRITICAL: These are model-based estimates using operator-configured coefficients.
Not direct power telemetry. All estimates are clearly marked as such.

Usage:
1. Load coefficients from environment at startup
2. For each record, call estimate_energy() with available metrics
3. Include sustainability dict in evidence_blob BEFORE signing

================================================================================
"""

import os
import json
import hashlib
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

from .signing import canonicalize_json


@dataclass
class EnergyCoefficients:
    """
    Energy estimation coefficients loaded from operator configuration.

    All coefficients are optional - if unset, estimates that depend on them
    will be null (not fabricated).
    """
    version: str
    llm_wh_per_1k_output_tokens: Optional[float]
    cpu_wh_per_second: Optional[float]
    base_wh_per_record: float
    co2e_g_per_kwh: Optional[float]
    source: str = "operator_config"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "llm_wh_per_1k_output_tokens": self.llm_wh_per_1k_output_tokens,
            "cpu_wh_per_second": self.cpu_wh_per_second,
            "base_wh_per_record": self.base_wh_per_record,
            "co2e_g_per_kwh": self.co2e_g_per_kwh,
            "source": self.source,
        }


def load_coefficients_from_env() -> EnergyCoefficients:
    """
    Load energy coefficients from environment variables.

    If a coefficient env var is unset or empty, the value will be None.
    This ensures we never fabricate estimates without explicit configuration.
    """
    def parse_float_or_none(env_var: str) -> Optional[float]:
        val = os.getenv(env_var, "").strip()
        if not val:
            return None
        try:
            return float(val)
        except ValueError:
            return None

    return EnergyCoefficients(
        version=os.getenv("ENERGY_COEFF_VERSION", "ENERGY_COEFF_v1"),
        llm_wh_per_1k_output_tokens=parse_float_or_none("ENERGY_LLM_WH_PER_1K_TOKENS"),
        cpu_wh_per_second=parse_float_or_none("ENERGY_CPU_WH_PER_SECOND"),
        base_wh_per_record=float(os.getenv("ENERGY_BASE_WH_PER_RECORD", "0.0")),
        co2e_g_per_kwh=parse_float_or_none("ENERGY_CO2E_G_PER_KWH"),
        source="operator_config",
    )


def compute_coefficients_hash(coeffs: EnergyCoefficients) -> str:
    """
    Compute SHA256 hash of coefficients for forensic binding.
    """
    coeffs_dict = coeffs.to_dict()
    canonical = canonicalize_json(coeffs_dict)
    return hashlib.sha256(canonical).hexdigest()


def estimate_energy(
    llm_used: bool,
    llm_output_tokens: Optional[int],
    latency_ms: Optional[float],
    cpu_seconds: Optional[float],
    coeffs: EnergyCoefficients,
    processing_region: str
) -> Dict[str, Any]:
    """
    Estimate energy consumption and CO2e emissions for a single record.

    CRITICAL RULES:
    1. If llm_used=True but llm_output_tokens is None -> estimates are null
    2. If coefficients are None -> estimates that depend on them are null
    3. Never fabricate numbers - return null if inputs unavailable

    Returns a sustainability dict suitable for inclusion in evidence_blob.
    """
    coefficients_hash = compute_coefficients_hash(coeffs)

    # Track what inputs are available
    token_count_available = llm_output_tokens is not None
    cpu_seconds_available = cpu_seconds is not None

    # Initialize estimates as null
    energy_wh_estimate: Optional[float] = None
    co2e_g_estimate: Optional[float] = None

    # Only compute LLM energy if we have BOTH token count AND coefficient
    llm_wh: Optional[float] = None
    if llm_used and token_count_available and coeffs.llm_wh_per_1k_output_tokens is not None:
        llm_wh = (llm_output_tokens / 1000.0) * coeffs.llm_wh_per_1k_output_tokens

    # Total energy = base + LLM (if available)
    if llm_wh is not None:
        energy_wh_estimate = coeffs.base_wh_per_record + llm_wh
    elif not llm_used:
        # Non-LLM record: only base energy if configured > 0
        if coeffs.base_wh_per_record > 0:
            energy_wh_estimate = coeffs.base_wh_per_record
        # If base is 0 and no LLM, energy stays null (we have no estimate basis)
    # else: LLM was used but token count unavailable -> energy stays null

    # CO2e only if we have energy estimate AND co2e coefficient
    if energy_wh_estimate is not None and coeffs.co2e_g_per_kwh is not None:
        co2e_g_estimate = (energy_wh_estimate / 1000.0) * coeffs.co2e_g_per_kwh

    return {
        "estimated": True,
        "measurement_source": "model_estimate",
        "methodology_version": coeffs.version,
        "coefficients_snapshot": coeffs.to_dict(),
        "coefficients_hash_sha256": coefficients_hash,
        "processing_region": processing_region,
        "energy_wh_estimate": energy_wh_estimate,
        "co2e_g_estimate": co2e_g_estimate,
        "inputs_used": {
            "token_count_available": token_count_available,
            "llm_output_tokens": llm_output_tokens,
            "latency_ms": latency_ms,
            "cpu_seconds_available": cpu_seconds_available,
            "cpu_seconds": cpu_seconds,
        },
        "disclaimer": "Estimates only. Not direct power telemetry. See coefficients_version and coverage.",
    }


def compute_batch_sustainability(
    record_sustainability_list: list,
    coeffs: EnergyCoefficients,
    processing_region: str,
    sbom_hash: str
) -> Dict[str, Any]:
    """
    Compute batch-level sustainability rollup from individual record estimates.

    Returns aggregated sustainability metrics with coverage information.
    """
    total_records = len(record_sustainability_list)

    if total_records == 0:
        return {
            "estimated": True,
            "measurement_source": "model_estimate",
            "methodology_version": coeffs.version,
            "coefficients_hash_sha256": compute_coefficients_hash(coeffs),
            "processing_region": processing_region,
            "sbom_hash_sha256": sbom_hash,
            "batch_energy_wh_estimate": None,
            "batch_co2e_g_estimate": None,
            "coverage_pct": 0.0,
            "total_records": 0,
            "records_with_estimates": 0,
            "disclaimer": "Estimates only. Not direct power telemetry. Coverage indicates percent of records with sufficient inputs.",
        }

    # Sum estimates where not null
    batch_energy_wh: Optional[float] = None
    batch_co2e_g: Optional[float] = None
    records_with_energy = 0

    for sus in record_sustainability_list:
        energy = sus.get("energy_wh_estimate")
        co2e = sus.get("co2e_g_estimate")

        if energy is not None:
            if batch_energy_wh is None:
                batch_energy_wh = 0.0
            batch_energy_wh += energy
            records_with_energy += 1

        if co2e is not None:
            if batch_co2e_g is None:
                batch_co2e_g = 0.0
            batch_co2e_g += co2e

    coverage_pct = (records_with_energy / total_records) * 100.0

    return {
        "estimated": True,
        "measurement_source": "model_estimate",
        "methodology_version": coeffs.version,
        "coefficients_hash_sha256": compute_coefficients_hash(coeffs),
        "processing_region": processing_region,
        "sbom_hash_sha256": sbom_hash,
        "batch_energy_wh_estimate": batch_energy_wh,
        "batch_co2e_g_estimate": batch_co2e_g,
        "coverage_pct": round(coverage_pct, 2),
        "total_records": total_records,
        "records_with_estimates": records_with_energy,
        "disclaimer": "Estimates only. Not direct power telemetry. Coverage indicates percent of records with sufficient inputs.",
    }


# Configuration
ENERGY_ESTIMATES_ENABLED = os.getenv("ENERGY_ESTIMATES_ENABLED", "false").lower() == "true"


def get_energy_estimator_status() -> Dict[str, Any]:
    """Get energy estimator status for /health endpoint."""
    if not ENERGY_ESTIMATES_ENABLED:
        return {
            "enabled": False,
            "coefficients_configured": False,
        }

    coeffs = load_coefficients_from_env()
    return {
        "enabled": True,
        "coefficients_configured": True,
        "methodology_version": coeffs.version,
        "coefficients_hash_sha256": compute_coefficients_hash(coeffs),
        "llm_coefficient_set": coeffs.llm_wh_per_1k_output_tokens is not None,
        "co2e_coefficient_set": coeffs.co2e_g_per_kwh is not None,
    }
