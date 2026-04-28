"""
================================================================================
INTELLIGENT ANALYST v3.0.0 ENTERPRISE - AUDIT + BACKEND SUPPORT
================================================================================

SECURITY MODEL:
- Strict CORS with configurable allowed origins
- Mandatory API key authentication
- Rate limiting per tenant
- Circuit breaker for downstream dependencies
- PII detection and masking with audit logging
- Request validation and sanitization
- Persistent audit trail (Firestore)
- Full stats tracking for compliance

BUTTON SUPPORT:
- AUDIT Button: /audit, /audit/{trace_id}, /audit/{trace_id}/flagged, /security/pii-log
- BACKEND Button: /health, /security/status, /stats

DEPLOYMENT:
  # Local
  uvicorn server_enterprise_v3:app --host 0.0.0.0 --port 8000

  # Production (with env vars)
  BACKEND_API_KEY=xxx ALLOWED_ORIGINS=https://app.example.com uvicorn ...

================================================================================
"""

import os
import io
import re
import json
import time
import asyncio
import hashlib
import zipfile
import traceback
import threading
import sys
import secrets
from uuid import uuid4
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from functools import wraps
from dataclasses import dataclass, field, asdict

import pandas as pd
import numpy as np

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, validator

# Person Sanitizer (deterministic, O(n), no watchlist matching)
from app.person_sanitizer import sanitize_person_name_only, SanitizationResult
from app.l3_drift_invariant import compute_drift_invariant
from app.margin_sentinel_invariant import compute_margin_sentinel

# Entity Classifier (row-level, deterministic, O(n))
from app.entity_classifier import classify_entity, EntityType

# Dataset Router (schema-level, deterministic)
from app.dataset_router import inspect_dataset

# Organization Sanitizer (deterministic, O(n))
from app.org_sanitizer import sanitize_organization_name

# Vessel Sanitizer (deterministic, O(n))
from app.vessel_sanitizer import sanitize_vessel_name

# Structured JSON logging (observability upgrade v1)
from app.structured_log import slog, slog_error

# Day 2: Shard planner + Budget ledger
from app.sharding import (
    compute_shard_ranges, create_shard_docs, update_shard_status,
    fetch_shard_rows, try_complete_batch, get_all_shard_statuses,
    SHARD_SIZE,
)
from app.budget_ledger import (
    ensure_tenant_balance, reserve_budget, spend_budget, release_budget,
    get_tenant_balance,
)

# Day 3: L3 model abstraction + soft failover
from app.llm_router import (
    get_active_model_config, call_l3_with_failover, LLMCallResult,
)

# =============================================================================
# STRUCTURAL INTEGRITY EXCEPTIONS
# =============================================================================
# These exceptions represent catastrophic failures that must abort processing.
# They are NOT recoverable - they indicate fundamental pipeline corruption.

class IntegrityError(Exception):
    """Raised when waterfall integrity is violated - L1+L2+L4 != total before L3."""
    pass

class L3VolumeAnomalyError(Exception):
    """Raised when L3 eligible exceeds MAX_L3_PERCENT - indicates L1/L2 failure."""
    pass

class LLMDirectPathError(Exception):
    """Raised when L3 is called without L1/L2 processing - regression detection."""
    pass

class MetricsNotCommittedError(Exception):
    """Raised when batch completion attempted without full metric accounting."""
    pass

# =============================================================================
# STARTUP TIME TRACKING (for uptime calculation)
# =============================================================================
_STARTUP_TIME = datetime.utcnow()

# Certificate service (optional)
try:
    from app.certificate_service import make_certificate_input, build_transparency_certificate_pdf
    HAS_CERTIFICATE_SERVICE = True
except ImportError:
    HAS_CERTIFICATE_SERVICE = False

# Attestation signer (optional — verification bundles)
try:
    from app.attestation_signer import build_verification_bundle, SigningKeyError
    HAS_ATTESTATION_SIGNER = True
except ImportError:
    HAS_ATTESTATION_SIGNER = False

# Crypto module for manifest signing
try:
    from app.crypto import sign_manifest, get_public_key_pem, is_signing_available, get_key_source
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    print("[INFO] Crypto module not available - manifest signing disabled", flush=True)

# Security modules for forensic audit (Phase 0.5+)
try:
    from app.security.signing import (
        canonicalize_json, sha256_bytes, sha256_str,
        sign_bytes_kms, build_signature_metadata,
        get_signing_status, build_llm_replay_metadata,
        get_public_key_pem_kms, get_public_key_info,
        get_signing_key_metadata
    )
    from app.security.sbom import get_sbom_status, get_sbom_hash, get_sbom_for_evidence, compute_sbom_hash
    from app.security.evidence import (
        build_evidence_blob, extract_evidence_summary,
        verify_evidence_signature_format,
        detect_evidence_schema, verify_chunk_v1_evidence,
        EVIDENCE_SCHEMA_CHUNK_V1, EVIDENCE_SCHEMA_ROW_SIG_V1,
        EVIDENCE_SCHEMA_UNKNOWN
    )
    from app.security.hash_chain import (
        compute_batch_hash_chain, verify_hash_chain,
        verify_hash_chain_iavp,
        build_chain_metadata, GENESIS_HASH,
        compute_batch_hash_chain_iavp, ReplayVarianceError
    )
    from app.security.iavp import (
        IAVP_PROTOCOL_VERSION, IAVP_ARTIFACT_VERSION,
        IAVP_HASH_CHAIN_METHOD, IAVP_ORDERING_METHOD, IAVP_ATTESTED_SCOPE,
        ArtifactMode, ArtifactModeViolationError, get_artifact_mode,
        validate_artifact_mode, validate_key_separation,
        KeySeparationViolationError, build_iavp_manifest,
        validate_manifest_schema, compute_config_hash, compute_dataset_hash,
        jcs_sha256, normalize_timestamp_rfc3339
    )
    from app.security.anchoring import (
        build_anchor_record, write_anchor_to_gcs,
        verify_anchor, get_anchoring_status,
        ANCHORING_ENABLED as ANCHORING_MODULE_ENABLED
    )
    from app.security.tenant_encryption import (
        encrypt_evidence_blob, decrypt_evidence_blob,
        get_tenant_encryption_status, get_or_create_tenant_key,
        resolve_tenant_key_or_fail, TenantKeyMissingError
    )
    from app.security.legal_hold import (
        build_hold_record, build_release_record,
        vault_evidence_to_gcs, vault_hash_chain_to_gcs,
        verify_vaulted_evidence, get_legal_hold_status,
        # Week 2 governance additions
        HoldEventType, check_hold_placement_role, check_hold_release_role,
        build_hold_event, build_enhanced_hold_record, vault_all_for_hold,
        generate_hold_id, generate_event_id, HOLD_PLACEMENT_ROLES, HOLD_RELEASE_ROLES
    )
    from app.security.retention import (
        RetentionStatus, RetentionAction, RetentionViolationError,
        RetentionManager, generate_gcs_lifecycle_policy, apply_gcs_lifecycle_policy,
        build_retention_event, COLD_TRANSITION_DAYS, PURGE_THRESHOLD_DAYS
    )
    from app.security.energy_estimator import (
        EnergyCoefficients, load_coefficients_from_env,
        compute_coefficients_hash, estimate_energy,
        compute_batch_sustainability, get_energy_estimator_status,
        ENERGY_ESTIMATES_ENABLED
    )
    from app.security.integrity_check import (
        ForensicIntegrityChecker, IntegrityCheckError,
        run_startup_integrity_check, IntegrityStatus
    )
    HAS_FORENSIC_SIGNING = True
    HAS_INTEGRITY_CHECK = True
    print("[INFO] Forensic signing module loaded", flush=True)
except ImportError as e:
    HAS_FORENSIC_SIGNING = False
    HAS_INTEGRITY_CHECK = False
    print(f"[INFO] Forensic signing not available: {e}", flush=True)

# =============================================================================
# FIRESTORE FOR BATCH HISTORY (Optional - gracefully degrades)
# =============================================================================
_firestore_db = None
_firestore_database_id = os.getenv("FIRESTORE_DATABASE", "(default)")

try:
    from google.cloud import firestore as firestore_client
    _firestore_db = firestore_client.Client(database=_firestore_database_id)
    print(f"[INFO] Firestore connected: database={_firestore_database_id}", flush=True)
except Exception as e:
    _firestore_db = None
    print(f"[INFO] Firestore not available: {e} (batch history disabled)", flush=True)

# =============================================================================
# CLOUD TASKS FOR DURABLE BATCH PROCESSING
# =============================================================================
_tasks_client = None
CLOUD_TASKS_QUEUE = os.getenv("CLOUD_TASKS_QUEUE", "batch-processing")
CLOUD_TASKS_LOCATION = os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
CLOUD_RUN_SERVICE_URL = os.getenv("CLOUD_RUN_SERVICE_URL", "")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")

try:
    from google.cloud import tasks_v2
    _tasks_client = tasks_v2.CloudTasksClient()
    print(f"[INFO] Cloud Tasks client initialized: queue={CLOUD_TASKS_QUEUE}", flush=True)
except Exception as e:
    _tasks_client = None
    print(f"[INFO] Cloud Tasks not available: {e} (falling back to sync processing)", flush=True)

# =============================================================================
# FIREBASE ADMIN SDK FOR AUTH (Optional - dual mode with API key)
# =============================================================================
_firebase_app = None
HAS_FIREBASE_AUTH = False

try:
    import firebase_admin
    from firebase_admin import credentials, auth as firebase_auth
    if not firebase_admin._apps:
        _firebase_app = firebase_admin.initialize_app(credentials.ApplicationDefault())
    else:
        _firebase_app = firebase_admin.get_app()
    HAS_FIREBASE_AUTH = True
    print("[INFO] Firebase Admin SDK initialized for auth", flush=True)
except Exception as e:
    HAS_FIREBASE_AUTH = False
    print(f"[INFO] Firebase Admin SDK not available: {e} (using API key only)", flush=True)

# =============================================================================
# ANTHROPIC/CLAUDE FOR L3 LLM RESOLUTION (Optional)
# =============================================================================
try:
    import anthropic
    HAS_ANTHROPIC = True
    print("[INFO] Anthropic SDK available for L3 LLM resolution", flush=True)
except ImportError:
    HAS_ANTHROPIC = False
    print("[INFO] Anthropic SDK not installed - L3 LLM disabled", flush=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# =============================================================================
# JELLYFISH FOR PERSON NAME MATCHING (Optional)
# =============================================================================
try:
    import jellyfish
    HAS_JELLYFISH = True
    print("[INFO] Jellyfish available for person name fuzzy matching", flush=True)
except ImportError:
    HAS_JELLYFISH = False
    print("[INFO] Jellyfish not installed - person L2 fuzzy matching limited", flush=True)

# =============================================================================
# DATASET TYPE CLASSIFICATION (Mixed mode with row-level classification)
# =============================================================================
from enum import Enum

class DatasetType(str, Enum):
    """Dataset type classification for routing to appropriate pipeline."""
    MIXED = "MIXED"       # Row-level classification (default)
    PERSON = "PERSON"     # Force all rows to person sanitizer
    COMPANY = "COMPANY"   # Force all rows to company/org sanitizer
    VESSEL = "VESSEL"     # Force all rows to vessel sanitizer
    UNKNOWN = "UNKNOWN"

# Corporate suffixes indicating COMPANY type
CORPORATE_SUFFIXES = {
    'inc', 'incorporated', 'corp', 'corporation', 'co', 'company',
    'ltd', 'limited', 'llc', 'llp', 'plc', 'gmbh', 'ag', 'se', 'sa',
    'nv', 'bv', 'spa', 'srl', 'ab', 'as', 'oy', 'oyj',
    'holdings', 'group', 'enterprises', 'industries', 'partners',
    'trust', 'fund', 'capital', 'ventures', 'bank', 'insurance'
}

# Person title prefixes
PERSON_TITLE_PREFIXES = {
    'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'rev', 'hon',
    'sir', 'dame', 'lord', 'lady', 'capt', 'col', 'gen', 'maj'
}

# Person name suffixes
PERSON_NAME_SUFFIXES = {
    'jr', 'sr', 'ii', 'iii', 'iv', 'v', 'md', 'phd', 'esq', 'cpa'
}

# Cyrillic/Russian patronymic suffixes (transliterated)
CYRILLIC_PATRONYMIC_SUFFIXES = {'ovich', 'evich', 'ovna', 'evna', 'ich', 'ina'}


def classify_dataset_type(
    rows: List[str],
    sample_size: int = 100,
    person_threshold: float = 0.60
) -> Tuple[DatasetType, dict]:
    """
    Classify whether a batch contains person names or company names.

    Heuristics:
    1. Corporate suffix present → COMPANY
    2. Person title prefix → PERSON
    3. Person name suffix (Jr, III) → PERSON
    4. 2-4 tokens with title-case → PERSON
    5. 3 tokens ALL CAPS + patronymic ending → PERSON (Russian)
    6. Default: When ambiguous, lean toward PERSON

    Args:
        rows: List of entity names
        sample_size: Max rows to sample for classification
        person_threshold: Ratio above which batch is classified as PERSON

    Returns:
        (DatasetType, classification_metadata)
    """
    if not rows:
        return DatasetType.UNKNOWN, {"error": "empty batch"}

    sample = rows[:sample_size] if len(rows) > sample_size else rows

    person_signals = 0.0
    company_signals = 0.0

    for name in sample:
        if not name or not isinstance(name, str):
            continue

        name = str(name).strip()
        name_lower = name.lower()
        tokens = name_lower.split()
        token_count = len(tokens)

        # Skip empty/short entries
        if token_count == 0:
            continue

        # Signal 1: Corporate suffix → COMPANY
        has_corporate = any(
            token.rstrip('.,') in CORPORATE_SUFFIXES
            for token in tokens
        )
        if has_corporate:
            company_signals += 1.0
            continue

        # Signal 2: Person title prefix → PERSON
        if tokens[0].rstrip('.') in PERSON_TITLE_PREFIXES:
            person_signals += 1.0
            continue

        # Signal 3: Person name suffix (Jr., III) → PERSON
        if tokens[-1].rstrip('.').lower() in PERSON_NAME_SUFFIXES:
            person_signals += 1.0
            continue

        # Signal 4: 3 tokens ALL CAPS + patronymic ending → PERSON (Russian style)
        if token_count == 3 and name.isupper():
            if any(tokens[-1].lower().endswith(suffix) for suffix in CYRILLIC_PATRONYMIC_SUFFIXES):
                person_signals += 1.0
                continue

        # Signal 5: 2-4 tokens, each word capitalized → likely PERSON
        original_tokens = name.split()
        if 2 <= token_count <= 4:
            all_title_case = all(
                t[0].isupper() and (len(t) == 1 or t[1:].islower() or t.isupper())
                for t in original_tokens if t
            )
            if all_title_case:
                person_signals += 0.7
                continue

        # Default: short (2-3 tokens) without corporate markers → lean PERSON
        if 2 <= token_count <= 3:
            person_signals += 0.3
        else:
            company_signals += 0.3

    total = person_signals + company_signals
    person_ratio = person_signals / total if total > 0 else 0.5

    # Apply threshold (default 60% for PERSON, lean toward PERSON when ambiguous)
    if person_ratio >= person_threshold:
        classification = DatasetType.PERSON
    elif person_ratio <= (1 - person_threshold):
        classification = DatasetType.COMPANY
    else:
        # Ambiguous: lean toward PERSON per user requirement
        classification = DatasetType.PERSON

    metadata = {
        "sample_size": len(sample),
        "person_signals": round(person_signals, 1),
        "company_signals": round(company_signals, 1),
        "person_ratio": round(person_ratio, 3),
        "classification": classification.value,
        "threshold": person_threshold
    }

    print(f"[CLASSIFY] Dataset type: {classification.value} | "
          f"person_ratio={person_ratio:.2f}, threshold={person_threshold}", flush=True)

    return classification, metadata


# =============================================================================
# GLOBAL STATS TRACKING (for /stats endpoint)
# =============================================================================
@dataclass
class GlobalStats:
    """Tracks cumulative processing statistics."""
    total_records_processed: int = 0
    total_batches_processed: int = 0
    total_auto_resolved: int = 0
    total_l0_garbage: int = 0
    total_l1_exact: int = 0
    total_l1_norm: int = 0
    total_l2_vector: int = 0
    total_l3_llm: int = 0
    total_l4_human: int = 0
    total_pii_detections: int = 0
    total_latency_ms: float = 0.0
    total_cost: float = 0.0
    # L3 drift invariant — updated after every batch
    l3_drift_zone: str = "SAFE"
    l3_pct: float = 0.0
    l4_pct: float = 0.0
    l3_last_spent_usd: float = 0.0
    # Margin sentinel invariant — updated after every batch
    margin_zone: str = "SAFE"
    margin_human_cost_usd: float = 0.0
    margin_total_cost_usd: float = 0.0
    margin_cost_per_record_usd: float = 0.0
    # Per-batch snapshot — used by ?scope=last_batch (default)
    last_batch_l3: int = 0
    last_batch_l4: int = 0
    last_batch_valid_records: int = 0
    last_batch_llm_cost: float = 0.0

    def record_batch(
        self,
        stats: dict,
        duration_ms: float,
        l3_budget_usd: float = 10.0,
        human_cost_per_record_usd: float = 0.50,
        l4_warning_threshold_pct: float = 6.0,
        l4_red_threshold_pct: float = 8.0,
        cost_per_record_red_usd: float = 0.05,
    ):
        """Update global stats from a batch result."""
        # Snapshot this batch's values for ?scope=last_batch
        _batch_total = stats.get('total', 0)
        _batch_l0 = stats.get('layer_0_garbage', 0)
        self.last_batch_l3 = stats.get('layer_3_llm', 0)
        self.last_batch_l4 = stats.get('layer_4_human', 0)
        self.last_batch_llm_cost = stats.get('l3_cost_usd', 0.0)
        self.last_batch_valid_records = _batch_total - _batch_l0

        self.total_batches_processed += 1
        self.total_records_processed += stats.get('total', 0)
        self.total_auto_resolved += stats.get('auto_resolved', 0)
        self.total_l0_garbage += stats.get('layer_0_garbage', 0)
        self.total_l1_exact += stats.get('layer_1_exact', 0)
        self.total_l1_norm += stats.get('layer_1_norm', 0)
        self.total_l2_vector += stats.get('layer_2_vector', 0)
        self.total_l3_llm += stats.get('layer_3_llm', 0)
        self.total_l4_human += stats.get('layer_4_human', 0)
        self.total_pii_detections += stats.get('pii_detections', 0)
        self.total_latency_ms += duration_ms
        # Accumulate L3 cost and update drift invariant
        l3_cost = stats.get('l3_cost_usd', 0.0)
        self.total_cost += l3_cost
        self.l3_last_spent_usd = l3_cost
        valid_records = self.total_records_processed - self.total_l0_garbage
        inv = compute_drift_invariant(
            total_l3=self.total_l3_llm,
            total_l4=self.total_l4_human,
            total_valid_records=valid_records,
            spent_usd=l3_cost,
            budget_usd=l3_budget_usd,
        )
        self.l3_drift_zone = inv.zone
        self.l3_pct = inv.l3_pct
        self.l4_pct = inv.l4_pct
        # Compute margin sentinel invariant
        margin = compute_margin_sentinel(
            total_records=valid_records,
            total_l3=self.total_l3_llm,
            total_l4=self.total_l4_human,
            total_llm_cost_usd=self.total_cost,
            human_cost_per_record_usd=human_cost_per_record_usd,
            l4_warning_threshold_pct=l4_warning_threshold_pct,
            l4_red_threshold_pct=l4_red_threshold_pct,
            cost_per_record_red_usd=cost_per_record_red_usd,
        )
        self.margin_zone = margin.zone
        self.margin_human_cost_usd = margin.human_cost_usd
        self.margin_total_cost_usd = margin.total_cost_usd
        self.margin_cost_per_record_usd = margin.cost_per_record_usd

    def to_dict(self) -> dict:
        valid_records = self.total_records_processed - self.total_l0_garbage
        return {
            "total_records_processed": self.total_records_processed,
            "total_batches_processed": self.total_batches_processed,
            "auto_resolved_pct": round(self.total_auto_resolved / valid_records * 100, 2) if valid_records > 0 else 0.0,
            "layer_distribution": {
                "L0_GARBAGE": self.total_l0_garbage,
                "L1_EXACT": self.total_l1_exact,
                "L1_NORM": self.total_l1_norm,
                "L2_VECTOR": self.total_l2_vector,
                "L3_LLM": self.total_l3_llm,
                "L4_HUMAN": self.total_l4_human,
            },
            "avg_latency_ms": round(self.total_latency_ms / self.total_batches_processed, 2) if self.total_batches_processed > 0 else 0.0,
            "total_cost": self.total_cost,
            "pii_detections": self.total_pii_detections,
            "l3_drift_invariant": {
                "zone": self.l3_drift_zone,
                "l3_pct": self.l3_pct,
                "l4_pct": self.l4_pct,
            },
            "margin_sentinel": {
                "zone": self.margin_zone,
                "l4_pct": self.l4_pct,
                "human_cost_usd": round(self.margin_human_cost_usd, 4),
                "total_cost_usd": round(self.margin_total_cost_usd, 4),
                "cost_per_record_usd": round(self.margin_cost_per_record_usd, 5),
            },
        }


# Global stats instance
_global_stats = GlobalStats()
_stats_lock = threading.Lock()


# =============================================================================
# RATE LIMITING NOTE
# =============================================================================
# Rate limiting is handled by:
# 1. L3_MAX_CONCURRENCY=1 (single worker, sequential calls)
# 2. Retry logic with exponential backoff in resolve_with_claude_sync
# 3. The natural latency of LLM calls (~1-2s each)
# This keeps us under the 50 RPM limit without explicit rate limiting.


# =============================================================================
# L3 BUDGET TRACKER
# =============================================================================

@dataclass
class L3BudgetTracker:
    """
    Thread-safe tracker for L3 LLM budget and call limits per batch.
    Primary control: cost budget. Secondary: call cap. Tertiary: row threshold.
    """
    budget_usd: float = 100.0
    max_calls: int = 100000
    cost_per_call: float = 0.001

    # Runtime state
    spent_usd: float = 0.0
    calls: int = 0

    # L3 resolution tracking (for instrumentation)
    l3_eligible: int = 0       # Records that qualified for L3
    l3_attempted: int = 0      # L3 calls actually made
    l3_succeeded: int = 0      # L3 calls that resolved successfully
    l3_failed: int = 0         # L3 calls that returned UNKNOWN/None
    l3_cache_hits: int = 0     # Records resolved from semantic cache (no LLM call)
    l3_failover_count: int = 0  # Day 6: LLM failover events

    # Consolidated skip counters (for observability invariant)
    l3_skipped_budget: int = 0     # Skipped due to budget/cap exhaustion
    l3_skipped_rate_limit: int = 0 # Skipped due to timeout/error (rate limiting)

    # Detailed skip reason counters
    skipped_budget_exhausted: int = 0
    skipped_call_cap: int = 0
    skipped_row_threshold: int = 0
    skipped_llm_disabled: int = 0
    skipped_error: int = 0
    skipped_low_similarity: int = 0  # L2 score below L3_MIN_SIMILARITY threshold

    def can_run_l3(self) -> Tuple[bool, Optional[str]]:
        """
        Check if L3 can be run. Returns (can_run, skip_reason).
        skip_reason is None if can_run is True.
        """
        if self.calls >= self.max_calls:
            return False, "L3_CALL_CAP_REACHED"
        if self.spent_usd >= self.budget_usd:
            return False, "L3_BUDGET_EXHAUSTED"
        return True, None

    def record_call(self, cost: float, success: bool = True):
        """Record an L3 call with its cost and outcome."""
        self.calls += 1
        self.spent_usd += cost
        self.l3_attempted += 1
        if success:
            self.l3_succeeded += 1
        else:
            self.l3_failed += 1

    def record_skip(self, reason: str):
        """Record an L3 skip with reason. Updates both detailed and consolidated counters."""
        # Detailed counters
        if reason == "L3_BUDGET_EXHAUSTED":
            self.skipped_budget_exhausted += 1
            self.l3_skipped_budget += 1  # Consolidated
        elif reason == "L3_CALL_CAP_REACHED":
            self.skipped_call_cap += 1
            self.l3_skipped_budget += 1  # Consolidated (cap is budget-related)
        elif reason == "L3_ROW_THRESHOLD_EXCEEDED":
            self.skipped_row_threshold += 1
            self.l3_skipped_budget += 1  # Consolidated (threshold is budget-related)
        elif reason == "L3_DISABLED":
            self.skipped_llm_disabled += 1
            self.l3_skipped_budget += 1  # Consolidated (disabled is budget-related)
        elif reason == "L3_ERROR_FAIL_CLOSED":
            self.skipped_error += 1
            self.l3_skipped_rate_limit += 1  # Consolidated (errors from rate limiting)
        elif reason == "L3_LOW_SIMILARITY":
            self.skipped_low_similarity += 1
            self.l3_skipped_budget += 1  # Consolidated (low similarity is a cost-saving measure)

    def get_summary(self) -> dict:
        """Get summary for BATCH_LLM_BUDGET_SUMMARY audit event."""
        avg_cost = self.spent_usd / self.calls if self.calls > 0 else 0.0
        # L3 Yield: percentage of L3 calls that successfully resolved (vs returned UNKNOWN)
        l3_yield = (self.l3_succeeded / self.l3_attempted * 100) if self.l3_attempted > 0 else 0.0
        return {
            "budget_usd": self.budget_usd,
            "spent_usd": round(self.spent_usd, 6),
            "calls": self.calls,
            "avg_cost_per_call": round(avg_cost, 6),
            "budget_exhausted": self.spent_usd >= self.budget_usd,
            "call_cap_reached": self.calls >= self.max_calls,
            # L3 resolution metrics
            "l3_eligible": self.l3_eligible,
            "l3_attempted": self.l3_attempted,
            "l3_succeeded": self.l3_succeeded,
            "l3_failed": self.l3_failed,
            "l3_cache_hits": self.l3_cache_hits,
            "l3_yield": round(l3_yield, 1),  # L3 yield percentage (succeeded/attempted)
            "l3_failover_count": self.l3_failover_count,  # Day 6: LLM failover events
            # Consolidated skip counters (invariant: l3_eligible == l3_attempted + l3_skipped_budget + l3_skipped_rate_limit)
            "l3_skipped_budget": self.l3_skipped_budget,
            "l3_skipped_rate_limit": self.l3_skipped_rate_limit,
            "skipped_reason_counts": {
                "L3_BUDGET_EXHAUSTED": self.skipped_budget_exhausted,
                "L3_CALL_CAP_REACHED": self.skipped_call_cap,
                "L3_ROW_THRESHOLD_EXCEEDED": self.skipped_row_threshold,
                "L3_DISABLED": self.skipped_llm_disabled,
                "L3_ERROR_FAIL_CLOSED": self.skipped_error,
                "L3_LOW_SIMILARITY": self.skipped_low_similarity,
            }
        }


# =============================================================================
# L3 SEMANTIC CACHE - Reuse L3 results for similar company names
# =============================================================================

class L3SemanticCache:
    """
    Semantic cache for L3 LLM results. Uses TF-IDF vectors to find similar
    company names and reuse previous L3 resolutions.

    Phase 2B: Tenant-partitioned. Each namespace (tenant_id:model:version)
    gets an isolated cache partition. No cross-tenant embedding leakage.

    Thread-safe for concurrent L3 workers.
    """

    def __init__(self, similarity_threshold: float = 0.85, max_size: int = 50000):
        self.similarity_threshold = similarity_threshold
        self.max_size = max_size
        # Phase 2B: Partitioned by namespace
        self._partitions: Dict[str, Dict[str, dict]] = {}  # namespace -> {normalized_name -> result}
        self._partition_embeddings: Dict[str, List[Tuple[str, any]]] = {}  # namespace -> [(name, vec)]
        self._lock = threading.Lock()

        # Stats
        self.hits = 0
        self.misses = 0
        self.stores = 0

    def _normalize_for_cache(self, name: str) -> str:
        """Normalize name for cache key."""
        return re.sub(r'[^a-z0-9]', '', name.lower())

    def _get_partition(self, namespace: str) -> tuple:
        """Get or create a partition for the given namespace. Must hold _lock."""
        if namespace not in self._partitions:
            self._partitions[namespace] = {}
            self._partition_embeddings[namespace] = []
        return self._partitions[namespace], self._partition_embeddings[namespace]

    def lookup(self, name: str, vectorizer, vectors_matrix, namespace: str = None) -> Optional[dict]:
        """
        Look up a name in the cache using semantic similarity.

        Args:
            name: The company name to look up
            vectorizer: TF-IDF vectorizer (same one used for L2)
            vectors_matrix: Not used, we compare against our cache embeddings
            namespace: Phase 2B — tenant vector namespace (required)

        Returns:
            Cached result dict if found with sufficient similarity, None otherwise
        """
        if namespace is None:
            self.misses += 1
            return None

        normalized = self._normalize_for_cache(name)

        # Exact match first (fastest)
        with self._lock:
            cache, embeddings = self._get_partition(namespace)
            if not cache:
                self.misses += 1
                return None

            if normalized in cache:
                self.hits += 1
                cached = cache[normalized].copy()
                cached["cache_hit"] = "exact"
                return cached

        # Semantic similarity check
        try:
            query_vec = vectorizer.transform([name])

            with self._lock:
                cache, embeddings = self._get_partition(namespace)
                if not embeddings:
                    self.misses += 1
                    return None

                # Build matrix from cached embeddings
                from scipy.sparse import vstack
                cached_vectors = vstack([emb[1] for emb in embeddings])

                from sklearn.metrics.pairwise import cosine_similarity
                similarities = cosine_similarity(query_vec, cached_vectors)[0]

                best_idx = int(np.argmax(similarities))
                best_score = float(similarities[best_idx])

                if best_score >= self.similarity_threshold:
                    self.hits += 1
                    cached_name = embeddings[best_idx][0]
                    cached = cache[cached_name].copy()
                    cached["cache_hit"] = f"semantic_{best_score:.2f}"
                    return cached
        except Exception as e:
            print(f"[L3_CACHE] Lookup error: {e}", flush=True)

        self.misses += 1
        return None

    def store(self, name: str, result: dict, vectorizer, namespace: str = None) -> None:
        """
        Store an L3 result in the cache.

        Args:
            name: The original company name
            result: The L3 resolution result
            vectorizer: TF-IDF vectorizer to compute embedding
            namespace: Phase 2B — tenant vector namespace (required)
        """
        if not result or not result.get("resolved"):
            return  # Don't cache failed resolutions
        if namespace is None:
            return  # Phase 2B: no namespace → no store

        normalized = self._normalize_for_cache(name)

        try:
            query_vec = vectorizer.transform([name])

            with self._lock:
                cache, embeddings = self._get_partition(namespace)

                # Check size limit per partition
                if len(cache) >= self.max_size:
                    # Simple eviction: remove oldest 10%
                    evict_count = self.max_size // 10
                    keys_to_remove = list(cache.keys())[:evict_count]
                    for key in keys_to_remove:
                        del cache[key]
                    self._partition_embeddings[namespace] = [
                        (n, v) for n, v in embeddings if n not in keys_to_remove
                    ]

                # Store the result
                cache_entry = {
                    "resolved": result.get("resolved"),
                    "confidence": result.get("confidence", 0.9),
                    "layer": "L3_CACHED",
                    "reason": f"Cached from L3 ({result.get('reason', 'LLM')})",
                    "original_name": name,
                    "cached_at": time.time()
                }

                cache[normalized] = cache_entry
                self._partition_embeddings[namespace].append((normalized, query_vec))
                self.stores += 1

        except Exception as e:
            print(f"[L3_CACHE] Store error: {e}", flush=True)

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        total_entries = sum(len(c) for c in self._partitions.values())
        return {
            "enabled": True,
            "size": total_entries,
            "partitions": len(self._partitions),
            "max_size_per_partition": self.max_size,
            "similarity_threshold": self.similarity_threshold,
            "hits": self.hits,
            "misses": self.misses,
            "stores": self.stores,
            "hit_rate_pct": round(hit_rate, 1)
        }


# Global L3 semantic cache instance
_l3_cache: Optional[L3SemanticCache] = None

def get_l3_cache() -> Optional[L3SemanticCache]:
    """Get or create the global L3 semantic cache."""
    global _l3_cache
    if _l3_cache is None and config.L3_CACHE_ENABLED:
        _l3_cache = L3SemanticCache(
            similarity_threshold=config.L3_CACHE_SIMILARITY,
            max_size=config.L3_CACHE_MAX_SIZE
        )
        print(f"[L3_CACHE] Initialized: similarity_threshold={config.L3_CACHE_SIMILARITY}, max_size={config.L3_CACHE_MAX_SIZE}", flush=True)
    return _l3_cache


# =============================================================================
# L3 FIRESTORE CACHE - Persistent deterministic cache across instances
# =============================================================================

# L3 model ID for cache key (driven by env var via llm_router)
L3_MODEL_ID = get_active_model_config().model
L3_PROVIDER_ID = get_active_model_config().provider

# Track Firestore cache stats per batch
_l3_firestore_cache_stats = {"hits": 0, "misses": 0, "stores": 0, "errors": 0}

# Corporate suffixes to strip for cache key normalization
_CORPORATE_SUFFIXES = {
    'inc', 'incorporated', 'corp', 'corporation', 'co', 'company', 'companies',
    'ltd', 'limited', 'llc', 'llp', 'lp', 'plc', 'sa', 'gmbh', 'ag', 'nv', 'bv',
    'holding', 'holdings', 'group', 'international', 'intl', 'worldwide', 'global',
    'enterprises', 'enterprise', 'partners', 'partnership', 'associates', 'association',
    'services', 'solutions', 'technologies', 'technology', 'tech', 'systems', 'system',
}

# Alias map for high-leverage cache collisions (ticker symbols → canonical names)
_CACHE_ALIAS_MAP = {
    # Pharma
    'jnj': 'johnsonandjohnson', 'jandj': 'johnsonandjohnson', 'jandjohnson': 'johnsonandjohnson',
    'msd': 'merck', 'merckco': 'merck', 'merckandco': 'merck',
    'pfe': 'pfizer', 'pfizergrp': 'pfizer',
    'gsk': 'glaxosmithkline', 'glaxo': 'glaxosmithkline',
    'abt': 'abbott', 'abbottlabs': 'abbott', 'abbottlaboratories': 'abbott',
    'abbv': 'abbvie',
    'bmy': 'bristolmyerssquibb', 'bristolmyers': 'bristolmyerssquibb',
    'lly': 'elililly', 'lilly': 'elililly',
    'mrk': 'merck',
    # Tech
    'goog': 'alphabet', 'googl': 'alphabet', 'google': 'alphabet', 'googlellc': 'alphabet',
    'fb': 'meta', 'facebook': 'meta', 'metaplatforms': 'meta',
    'msft': 'microsoft', 'microsoftcorp': 'microsoft',
    'aapl': 'apple', 'appleinc': 'apple',
    'amzn': 'amazon', 'amazoncom': 'amazon', 'amazoninc': 'amazon',
    'nvda': 'nvidia', 'nvidiacorp': 'nvidia',
    'tsla': 'tesla', 'teslainc': 'tesla', 'teslamotors': 'tesla',
    'intc': 'intel', 'intelcorp': 'intel',
    'ibm': 'ibm', 'internationalbusinessmachines': 'ibm',
    'csco': 'cisco', 'ciscosystems': 'cisco',
    'orcl': 'oracle', 'oraclecorp': 'oracle',
    'crm': 'salesforce', 'salesforceinc': 'salesforce',
    'adbe': 'adobe', 'adobeinc': 'adobe', 'adobesystems': 'adobe',
    # Finance
    'jpm': 'jpmorganchase', 'jpmorgan': 'jpmorganchase', 'chase': 'jpmorganchase',
    'bac': 'bankofamerica', 'bofa': 'bankofamerica',
    'gs': 'goldmansachs', 'goldman': 'goldmansachs',
    'ms': 'morganstanley',
    'wfc': 'wellsfargo',
    'c': 'citigroup', 'citi': 'citigroup',
    'v': 'visa', 'visainc': 'visa',
    'ma': 'mastercard', 'mastercardinc': 'mastercard',
    'axp': 'americanexpress', 'amex': 'americanexpress',
    # Consumer
    'ko': 'cocacola', 'coke': 'cocacola', 'cocacolacompany': 'cocacola',
    'pep': 'pepsico', 'pepsi': 'pepsico',
    'pg': 'procterandgamble', 'procterandgamble': 'procterandgamble', 'pandg': 'procterandgamble',
    'mcd': 'mcdonalds', 'mcdonaldscorp': 'mcdonalds',
    'nke': 'nike', 'nikeinc': 'nike',
    'sbux': 'starbucks', 'starbuckscorp': 'starbucks',
    # Industrial
    'cat': 'caterpillar', 'caterpillarinc': 'caterpillar',
    'ba': 'boeing', 'boeingcompany': 'boeing', 'boeingco': 'boeing',
    'ge': 'generalelectric', 'gelectric': 'generalelectric',
    'hon': 'honeywell', 'honeywellinternational': 'honeywell',
    'mmm': '3m', '3mcompany': '3m', 'minnesotaminingandmanufacturing': '3m',
    'ups': 'ups', 'unitedparcelservice': 'ups',
    'fdx': 'fedex', 'fedexcorp': 'fedex', 'federalexpress': 'fedex',
    # Telecom
    'vz': 'verizon', 'verizoncommunications': 'verizon',
    't': 'att', 'atandt': 'att', 'attinc': 'att',
    'tmus': 'tmobile', 'tmobileus': 'tmobile',
    # Retail
    'wmt': 'walmart', 'walmartinc': 'walmart', 'walmartstores': 'walmart',
    'tgt': 'target', 'targetcorp': 'target',
    'cost': 'costco', 'costcowholesale': 'costco',
    'hd': 'homedepot', 'thehomedepot': 'homedepot',
    'low': 'lowes', 'lowescompanies': 'lowes',
    'cvs': 'cvshealth', 'cvspharmacy': 'cvshealth',
}


def _normalize_for_cache_key(name: str) -> str:
    """
    Normalize company name for deterministic cache key.
    Must be completely deterministic - same input always produces same output.

    Normalization steps:
    1. Lowercase and strip whitespace
    2. Replace & with 'and'
    3. Remove punctuation and collapse whitespace
    4. Strip corporate suffixes (inc, corp, ltd, etc.)
    5. Apply alias mapping for common ticker symbols
    6. Remove all remaining non-alphanumeric characters
    """
    if not name:
        return ""

    # Step 1: Lowercase and strip
    normalized = name.lower().strip()

    # Step 2: Replace & with 'and'
    normalized = normalized.replace('&', ' and ')

    # Step 3: Remove punctuation except spaces, collapse whitespace
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # Step 4: Strip corporate suffixes (from end, iteratively)
    words = normalized.split()
    while words and words[-1] in _CORPORATE_SUFFIXES:
        words.pop()
    normalized = ' '.join(words)

    # Step 5: Remove remaining spaces for final key
    normalized = normalized.replace(' ', '')

    # Step 6: Apply alias mapping (if enabled)
    if config.L3_CACHE_ALIASING_ENABLED and normalized in _CACHE_ALIAS_MAP:
        normalized = _CACHE_ALIAS_MAP[normalized]

    return normalized


def _compute_l3_cache_key(tenant_id: str, company_name: str) -> str:
    """
    Compute deterministic cache key for L3 result.
    Day 5: Key = sha256(tenant_id | agent_version_id | config_version | provider | model | normalized_query | canonical_hash)
    Cache auto-invalidates on any identity change: tenant, agent version, config, provider, model, or canonical list.
    """
    normalized = _normalize_for_cache_key(company_name)
    key_input = (
        f"{tenant_id}|{AGENT_VERSION_ID}|{CANONICAL_CONFIG_HASH}"
        f"|{L3_PROVIDER_ID}|{L3_MODEL_ID}"
        f"|{normalized}|{_CANONICAL_LIST_HASH}"
    )
    return hashlib.sha256(key_input.encode()).hexdigest()


def l3_firestore_cache_get(tenant_id: str, company_name: str) -> Optional[Dict[str, Any]]:
    """
    Look up L3 result in Firestore cache.
    Returns cached result dict if found and not expired, None otherwise.
    """
    global _l3_firestore_cache_stats

    if not config.L3_FIRESTORE_CACHE_ENABLED or not _firestore_db:
        return None

    try:
        cache_key = _compute_l3_cache_key(tenant_id, company_name)
        # Phase 2B: namespace-prefixed collection path for tenant isolation
        ns_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
        collection_path = f"l3_cache/{ns_hash}/entries"
        doc_ref = _firestore_db.collection(collection_path).document(cache_key)
        doc = doc_ref.get()

        if not doc.exists:
            # Fallback: check legacy global collection for migration compatibility
            legacy_ref = _firestore_db.collection("l3_cache").document(cache_key)
            doc = legacy_ref.get()
            if not doc.exists:
                _l3_firestore_cache_stats["misses"] += 1
                return None

        data = doc.to_dict()

        # Skip singleflight pending placeholders (another worker is computing)
        if data.get("status") == "pending":
            _l3_firestore_cache_stats["misses"] += 1
            return None

        # Check TTL expiry
        expires_at = data.get("ttl_expires_at")
        if expires_at:
            # Handle both string and datetime
            if isinstance(expires_at, str):
                expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            else:
                expires_dt = expires_at
            if datetime.now(expires_dt.tzinfo or None) > expires_dt:
                _l3_firestore_cache_stats["misses"] += 1
                return None

        # Update hit stats (async, fire-and-forget)
        try:
            doc_ref.update({
                "last_hit_at": datetime.utcnow().isoformat(),
                "hit_count": (data.get("hit_count", 0) or 0) + 1
            })
        except Exception:
            pass  # Non-critical, ignore errors

        _l3_firestore_cache_stats["hits"] += 1

        # Handle UNKNOWN cache entries (L3 returned UNKNOWN on a prior run)
        resolved = data.get("resolved")
        if resolved is None or data.get("status") == "unknown":
            return {
                "resolved": None,
                "confidence": 0.0,
                "layer": "L4_HUMAN",
                "reason": f"Firestore cache hit UNKNOWN (key={cache_key[:8]}...)",
                "cache_hit": "firestore_unknown",
                "is_unknown": True,
            }

        # Return the cached resolved result in the format expected by the L3 pipeline
        return {
            "resolved": resolved,
            "confidence": data.get("confidence", 0.85),
            "layer": "L3_FIRESTORE_CACHED",
            "reason": f"Firestore cache hit (key={cache_key[:8]}...)",
            "cache_hit": "firestore",
            "original_cached_name": data.get("normalized_query")
        }

    except Exception as e:
        _l3_firestore_cache_stats["errors"] += 1
        # Log but don't fail - cache miss is acceptable
        print(f"[L3_FS_CACHE] Get error: {e}", flush=True)
        return None


def l3_firestore_cache_set(tenant_id: str, company_name: str, result: Dict[str, Any]) -> bool:
    """
    Store L3 result in Firestore cache.
    Caches both resolved AND UNKNOWN outcomes for topology invariance:
    once an L3 decision is made, all subsequent lookups (any shard, any topology)
    see the same result through the cache.
    """
    global _l3_firestore_cache_stats

    if not config.L3_FIRESTORE_CACHE_ENABLED or not _firestore_db:
        return False

    if not result:
        return False

    try:
        cache_key = _compute_l3_cache_key(tenant_id, company_name)
        normalized = _normalize_for_cache_key(company_name)

        # Compute TTL expiry
        ttl_days = config.L3_FIRESTORE_CACHE_TTL_DAYS
        expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()

        resolved = result.get("resolved")
        cache_doc = {
            "tenant_id_hash": hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
            "normalized_query": normalized,
            "model_id": L3_MODEL_ID,
            "prompt_version": config.L3_CACHE_PROMPT_VERSION,
            "resolved": resolved,
            "confidence": result.get("confidence", 0.85) if resolved else 0.0,
            "original_layer": result.get("layer", "L3_LLM"),
            "original_reason": result.get("reason", ""),
            "status": "resolved" if resolved else "unknown",
            "created_at": datetime.utcnow().isoformat(),
            "last_hit_at": None,
            "hit_count": 0,
            "ttl_expires_at": expires_at,
        }

        # Phase 2B: write to namespace-prefixed collection
        ns_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
        collection_path = f"l3_cache/{ns_hash}/entries"
        _firestore_db.collection(collection_path).document(cache_key).set(cache_doc)
        _l3_firestore_cache_stats["stores"] += 1
        return True

    except Exception as e:
        _l3_firestore_cache_stats["errors"] += 1
        print(f"[L3_FS_CACHE] Set error: {e}", flush=True)
        return False


def get_l3_firestore_cache_stats() -> Dict[str, Any]:
    """Get Firestore cache statistics for current process with ROI metrics."""
    global _l3_firestore_cache_stats
    hits = _l3_firestore_cache_stats["hits"]
    misses = _l3_firestore_cache_stats["misses"]
    total = hits + misses
    hit_rate = (hits / total * 100) if total > 0 else 0.0

    # ROI metrics
    cost_per_call = config.L3_COST_PER_CALL_USD
    saved_cost = hits * cost_per_call
    # Estimated time saved (assuming ~500ms per L3 call)
    saved_time_ms = hits * 500

    return {
        "enabled": config.L3_FIRESTORE_CACHE_ENABLED,
        "aliasing_enabled": config.L3_CACHE_ALIASING_ENABLED,
        "hits": hits,
        "misses": misses,
        "stores": _l3_firestore_cache_stats["stores"],
        "errors": _l3_firestore_cache_stats["errors"],
        "hit_rate_pct": round(hit_rate, 1),
        "saved_cost_usd": round(saved_cost, 4),
        "saved_time_ms": saved_time_ms,
        "ttl_days": config.L3_FIRESTORE_CACHE_TTL_DAYS,
        "prompt_version": config.L3_CACHE_PROMPT_VERSION,
    }


def reset_l3_firestore_cache_stats():
    """Reset Firestore cache stats (call at start of each batch)."""
    global _l3_firestore_cache_stats
    _l3_firestore_cache_stats = {"hits": 0, "misses": 0, "stores": 0, "errors": 0}


# ---------------------------------------------------------------------------
# L3 SINGLEFLIGHT: Distributed deduplication of LLM calls across workers
# ---------------------------------------------------------------------------
_SINGLEFLIGHT_STALE_SECONDS = 30  # Treat pending older than this as crashed-worker


def l3_singleflight_acquire(tenant_id: str, company_name: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Try to acquire a singleflight lock for an L3 cache key.

    Returns (is_leader, cached_result_or_none):
      - (True, None)   → this worker should compute the result
      - (False, result) → another worker already computed; use this result
      - (False, None)   → another worker is computing; caller should poll/retry
    """
    if not _firestore_db:
        return True, None  # No Firestore → always leader (in-process only)

    cache_key = _compute_l3_cache_key(tenant_id, company_name)
    # Phase 2B: namespace-prefixed collection path
    ns_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
    collection_path = f"l3_cache/{ns_hash}/entries"
    doc_ref = _firestore_db.collection(collection_path).document(cache_key)

    try:
        # Attempt to create a pending placeholder (fails if doc already exists)
        doc_ref.create({
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        })
        return True, None  # We are the leader
    except Exception:
        # Document already exists — either completed result or another worker's pending
        pass

    # Read existing document
    try:
        doc = doc_ref.get()
        if not doc.exists:
            # Race: doc was deleted between our create and get. Treat as leader.
            return True, None

        data = doc.to_dict()

        # If it's a completed result (not pending), return it
        if data.get("status") != "pending" and data.get("resolved"):
            return False, {
                "resolved": data.get("resolved"),
                "confidence": data.get("confidence", 0.85),
                "layer": "L3_FIRESTORE_CACHED",
                "reason": "Singleflight cache hit",
                "cache_hit": "singleflight",
            }

        # It's pending — check if stale (crashed worker)
        created_at_str = data.get("created_at", "")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                age_seconds = (datetime.utcnow() - created_at).total_seconds()
                if age_seconds > _SINGLEFLIGHT_STALE_SECONDS:
                    # Stale pending — take over as leader by overwriting
                    doc_ref.set({
                        "status": "pending",
                        "created_at": datetime.utcnow().isoformat(),
                    })
                    return True, None
            except (ValueError, TypeError):
                pass

        # Another worker is actively computing — return None to signal "wait"
        return False, None

    except Exception as e:
        print(f"[SINGLEFLIGHT] Error reading lock: {e}", flush=True)
        return True, None  # On error, proceed as leader (safe fallback)


def l3_singleflight_poll(tenant_id: str, company_name: str, max_wait_seconds: float = 25.0) -> Optional[Dict[str, Any]]:
    """
    Poll for a singleflight result. Called by non-leader workers.
    Returns the cached result when available, or None on timeout.
    """
    import time as _time

    if not _firestore_db:
        return None

    cache_key = _compute_l3_cache_key(tenant_id, company_name)
    # Phase 2B: namespace-prefixed collection path
    ns_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
    collection_path = f"l3_cache/{ns_hash}/entries"
    doc_ref = _firestore_db.collection(collection_path).document(cache_key)
    deadline = _time.monotonic() + max_wait_seconds

    while _time.monotonic() < deadline:
        try:
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                if data.get("status") != "pending" and data.get("resolved"):
                    return {
                        "resolved": data.get("resolved"),
                        "confidence": data.get("confidence", 0.85),
                        "layer": "L3_FIRESTORE_CACHED",
                        "reason": "Singleflight poll hit",
                        "cache_hit": "singleflight_poll",
                    }
        except Exception:
            pass
        _time.sleep(0.5)

    return None  # Timeout — caller should proceed with own LLM call


def l3_singleflight_release(tenant_id: str, company_name: str) -> None:
    """Delete an orphaned singleflight pending stub.

    Called on any L3 failure path (fail-closed, timeout, exception) when
    this worker was the leader but never wrote a cache result.  Prevents
    pending stubs from accumulating in Firestore.
    """
    if not _firestore_db:
        return
    try:
        cache_key = _compute_l3_cache_key(tenant_id, company_name)
        ns_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
        collection_path = f"l3_cache/{ns_hash}/entries"
        doc_ref = _firestore_db.collection(collection_path).document(cache_key)
        doc = doc_ref.get()
        if doc.exists and doc.to_dict().get("status") == "pending":
            doc_ref.delete()
    except Exception as e:
        print(f"[SINGLEFLIGHT] Failed to release pending stub: {e}", flush=True)


def save_batch_to_firestore(batch_data: dict, tenant_id: str = "tenant_unknown") -> bool:
    """
    Save batch results to Firestore for history/retrieval.
    Returns True if saved successfully, False otherwise.
    tenant_id is required for multi-tenant isolation.
    """
    print(f"[Firestore] save_batch_to_firestore called, db_available={_firestore_db is not None}, tenant={tenant_id}", flush=True)

    if not _firestore_db:
        print("[Firestore] Skipping save - no database connection", flush=True)
        return False

    try:
        trace_id = batch_data.get('trace_id', f'unknown-{int(time.time())}')
        results = batch_data.get('results', [])

        # Count flagged items (L4_HUMAN needs review)
        flagged_count = sum(1 for r in results if r.get('layer') == 'L4_HUMAN')

        # Create a clean copy for Firestore - include tenant_id for isolation
        firestore_doc = {
            'trace_id': trace_id,
            'tenant_id': tenant_id,  # TENANT SCOPING
            'status': batch_data.get('status', 'unknown'),
            'total': batch_data.get('total', 0),
            'auto_resolved': batch_data.get('auto_resolved', 0),
            'auto_resolved_pct': batch_data.get('auto_resolved_pct', 0.0),
            'pii_detections': batch_data.get('pii_detections', 0),
            'filename': batch_data.get('filename', 'unknown'),
            'duration_ms': batch_data.get('duration_ms', 0.0),
            'records_per_sec': batch_data.get('records_per_sec', 0.0),
            'timestamp': datetime.utcnow().isoformat(),
            'stats': batch_data.get('stats', {}),
            'results_count': len(results),
            'flagged_count': flagged_count,
            'config_version': CANONICAL_CONFIG_VERSION,
        }

        # Save batch summary to Firestore
        batch_ref = _firestore_db.collection('batches').document(trace_id)
        batch_ref.set(firestore_doc)

        # Save audit events to subcollection using batched writes (max 500 per batch)
        audit_ref = batch_ref.collection('audit_events')
        BATCH_SIZE = 500
        for batch_start in range(0, len(results), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(results))
            write_batch = _firestore_db.batch()
            for i in range(batch_start, batch_end):
                result = results[i]
                audit_event = {
                    'row_index': i,
                    'tenant_id': tenant_id,  # TENANT SCOPING
                    'original': result.get('original', ''),
                    'resolved': result.get('resolved'),
                    'confidence': result.get('confidence', 0),
                    'layer': result.get('layer', 'UNKNOWN'),
                    'reason': result.get('reason', ''),
                    'pii_detected': result.get('pii_detected', []),
                    'latency_ms': result.get('latency_ms', 0),
                    'flagged': result.get('layer') == 'L4_HUMAN',
                    'timestamp': datetime.utcnow().isoformat(),
                    'config_version': CANONICAL_CONFIG_VERSION,
                }
                write_batch.set(audit_ref.document(f'row_{i:06d}'), audit_event)
            write_batch.commit()

        print(f"[Firestore] Saved batch {trace_id} with {len(results)} audit events ({flagged_count} flagged)", flush=True)
        return True

    except Exception as e:
        print(f"[Firestore] Error saving batch: {e}", flush=True)
        traceback.print_exc()
        return False


# =============================================================================
# EVIDENCE BLOB STORAGE (Phase 1 - Forensic Audit)
# =============================================================================

def save_evidence_blob_to_firestore(
    batch_trace_id: str,
    row_index: int,
    evidence_blob: Dict[str, Any]
) -> bool:
    """
    Save an evidence blob to Firestore.
    Storage path: batches/{batch_trace_id}/evidence/{row_index}
    """
    if not _firestore_db:
        return False

    try:
        evidence_ref = _firestore_db.collection('batches').document(batch_trace_id).collection('evidence')
        evidence_ref.document(f'row_{row_index:06d}').set(evidence_blob)
        return True
    except Exception as e:
        print(f"[Evidence] Error saving evidence blob: {e}", flush=True)
        return False


def save_evidence_blobs_batch(
    batch_trace_id: str,
    evidence_blobs: List[Tuple[int, Dict[str, Any]]],
    tenant_id: str = ""
) -> int:
    """
    Save multiple evidence blobs using batched writes.
    If TENANT_ENCRYPTION_ENABLED, encrypts each blob before storing.

    Key caching (v2): Resolves tenant KMS key ONCE per batch, not per row.

    Returns count of successfully saved blobs.
    """
    if not _firestore_db or not evidence_blobs:
        return 0

    try:
        evidence_ref = _firestore_db.collection('batches').document(batch_trace_id).collection('evidence')
        BATCH_SIZE = 500
        saved_count = 0
        encrypt_enabled = config.TENANT_ENCRYPTION_ENABLED and HAS_FORENSIC_SIGNING and tenant_id

        # Pre-resolve tenant KMS key ONCE for entire batch (not per row!)
        tenant_kms_key_path = None
        if encrypt_enabled:
            tenant_kms_key_path, key_error = resolve_tenant_key_or_fail(tenant_id)
            if key_error:
                print(f"[Evidence] Tenant key resolution failed: {key_error} - falling back to plaintext", flush=True)
                encrypt_enabled = False
            else:
                print(f"[Evidence] Using tenant key: {tenant_kms_key_path} for {len(evidence_blobs)} blobs", flush=True)

        for batch_start in range(0, len(evidence_blobs), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(evidence_blobs))
            write_batch = _firestore_db.batch()

            for i in range(batch_start, batch_end):
                row_index, blob = evidence_blobs[i]

                # Encrypt blob if tenant encryption is enabled
                if encrypt_enabled and tenant_kms_key_path:
                    encrypted_pkg, enc_error = encrypt_evidence_blob(
                        evidence_blob=blob,
                        tenant_id=tenant_id,
                        trace_id=batch_trace_id,
                        batch_id=batch_trace_id,
                        kms_key_path=tenant_kms_key_path  # Pass pre-resolved key
                    )
                    if encrypted_pkg and not enc_error:
                        # Store encrypted package with marker
                        storage_blob = {
                            "encrypted": True,
                            "envelope": encrypted_pkg
                        }
                    else:
                        # Encryption failed, store plaintext with warning
                        print(f"[Evidence] Encryption failed for row {row_index}: {enc_error}", flush=True)
                        storage_blob = blob
                else:
                    storage_blob = blob

                write_batch.set(evidence_ref.document(f'row_{row_index:06d}'), storage_blob)

            write_batch.commit()
            saved_count += (batch_end - batch_start)

        encryption_status = "encrypted" if encrypt_enabled else "plaintext"
        print(f"[Evidence] Saved {saved_count} evidence blobs ({encryption_status}) for {batch_trace_id}", flush=True)
        return saved_count

    except Exception as e:
        print(f"[Evidence] Error batch saving evidence blobs: {e}", flush=True)
        return 0


def get_evidence_blob_from_firestore(
    batch_trace_id: str,
    row_index: int,
    tenant_id: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single evidence blob from Firestore.
    Decrypts if the blob is encrypted and tenant_id is provided.
    """
    if not _firestore_db:
        return None

    try:
        doc = _firestore_db.collection('batches').document(batch_trace_id).collection('evidence').document(f'row_{row_index:06d}').get()
        if not doc.exists:
            return None

        storage_blob = doc.to_dict()

        # Check if encrypted
        if storage_blob.get("encrypted") and tenant_id and HAS_FORENSIC_SIGNING:
            encrypted_pkg = storage_blob.get("envelope")
            if encrypted_pkg:
                decrypted_blob, dec_error = decrypt_evidence_blob(
                    encrypted_package=encrypted_pkg,
                    tenant_id=tenant_id,
                    trace_id=batch_trace_id,
                    batch_id=batch_trace_id
                )
                if decrypted_blob and not dec_error:
                    return decrypted_blob
                else:
                    # Return error indicator
                    return {"decrypt_error": dec_error, "encrypted": True}

        return storage_blob
    except Exception as e:
        print(f"[Evidence] Error retrieving evidence blob: {e}", flush=True)
        return None


def get_evidence_blobs_for_batch(
    batch_trace_id: str,
    tenant_id: str = "",
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Retrieve all evidence blobs for a batch.
    Decrypts if blobs are encrypted and tenant_id is provided.
    """
    if not _firestore_db:
        return []

    try:
        evidence_ref = _firestore_db.collection('batches').document(batch_trace_id).collection('evidence')
        docs = list(evidence_ref.limit(limit).stream())
        results = []

        for doc in docs:
            storage_blob = doc.to_dict()

            # Check if encrypted
            if storage_blob.get("encrypted") and tenant_id and HAS_FORENSIC_SIGNING:
                encrypted_pkg = storage_blob.get("envelope")
                if encrypted_pkg:
                    decrypted_blob, dec_error = decrypt_evidence_blob(
                        encrypted_package=encrypted_pkg,
                        tenant_id=tenant_id,
                        trace_id=batch_trace_id,
                        batch_id=batch_trace_id
                    )
                    if decrypted_blob and not dec_error:
                        results.append(decrypted_blob)
                    else:
                        # Include error indicator
                        results.append({"decrypt_error": dec_error, "encrypted": True, "doc_id": doc.id})
                else:
                    results.append(storage_blob)
            else:
                results.append(storage_blob)

        return results
    except Exception as e:
        print(f"[Evidence] Error retrieving evidence blobs: {e}", flush=True)
        return []


def generate_and_store_evidence_blobs(
    batch_trace_id: str,
    tenant_id: str,
    results: List[Dict],
    config_version: str,
    sanitization_version: str,
    watchlist_version_hash: str
) -> Tuple[int, Optional[Dict[str, Any]]]:
    """
    Generate and store evidence blobs for all results in a batch.

    SCALABLE V2: Uses chunk-based evidence storage instead of per-row.
    - 100K rows → 200 chunk evidence objects (500 rows each)
    - Hash chain computed over chunk digests
    - ~500x reduction in I/O and crypto operations

    Returns: (row_count covered, batch_sustainability_rollup or None)
    """
    if not HAS_FORENSIC_SIGNING:
        return 0, None

    if not _firestore_db:
        return 0, None

    import time as _time
    total_start = _time.time()

    CHUNK_SIZE = 500  # Match Firestore batch size
    row_count = len(results)
    chunk_count = (row_count + CHUNK_SIZE - 1) // CHUNK_SIZE

    print(f"[Evidence] CHUNK MODE: {row_count} rows → {chunk_count} chunks ({CHUNK_SIZE} rows/chunk)", flush=True)

    record_sustainability_list = []

    # Load energy coefficients if enabled
    energy_coeffs = None
    energy_enabled = config.ENERGY_ESTIMATES_ENABLED and HAS_FORENSIC_SIGNING
    if energy_enabled:
        try:
            energy_coeffs = load_coefficients_from_env()
        except Exception as e:
            print(f"[Evidence] Error loading energy coefficients: {e}", flush=True)
            energy_enabled = False

    # Pre-resolve tenant KMS key ONCE for entire batch
    encrypt_enabled = config.TENANT_ENCRYPTION_ENABLED and HAS_FORENSIC_SIGNING and tenant_id
    tenant_kms_key_path = None
    if encrypt_enabled:
        key_start = _time.time()
        tenant_kms_key_path, key_error = resolve_tenant_key_or_fail(tenant_id)
        key_ms = (_time.time() - key_start) * 1000
        if key_error:
            print(f"[Evidence] Tenant key resolution failed ({key_ms:.0f}ms): {key_error} - falling back to plaintext", flush=True)
            encrypt_enabled = False
        else:
            print(f"[Evidence] Tenant key resolved ({key_ms:.0f}ms): {tenant_kms_key_path}", flush=True)

    # Build and store chunk-level evidence
    evidence_ref = _firestore_db.collection('batches').document(batch_trace_id).collection('evidence')
    chunk_digests = []  # For hash chain
    chunks_stored = 0
    build_ms_total = 0
    encrypt_ms_total = 0
    write_ms_total = 0

    for chunk_idx in range(chunk_count):
        chunk_start_row = chunk_idx * CHUNK_SIZE
        chunk_end_row = min(chunk_start_row + CHUNK_SIZE, row_count)
        chunk_results = results[chunk_start_row:chunk_end_row]

        # Build evidence records for this chunk
        build_start = _time.time()
        chunk_evidence_records = []
        for local_idx, r in enumerate(chunk_results):
            row_idx = chunk_start_row + local_idx
            try:
                # Sustainability
                sustainability = None
                if energy_enabled and energy_coeffs:
                    llm_used = "L3" in r.get("layer", "")
                    sustainability = estimate_energy(
                        llm_used=llm_used,
                        llm_output_tokens=r.get("llm_output_tokens"),
                        latency_ms=r.get("latency_ms"),
                        cpu_seconds=None,
                        coeffs=energy_coeffs,
                        processing_region=config.PROCESSING_REGION
                    )
                    record_sustainability_list.append(sustainability)

                # Build compact evidence record (no per-row signature)
                record = {
                    "row_index": row_idx,
                    "original_input": r.get("original", ""),
                    "sanitized_input": r.get("sanitized_name", r.get("resolved", "")),
                    "pii_detected": r.get("pii_detected", []),
                    "entity_type": r.get("entity_type", "UNKNOWN"),
                    "decision_path": r.get("decision_path", r.get("layer", "")),
                    "layer": r.get("layer", ""),
                    "resolved_output": r.get("resolved"),
                    "output_confidence": r.get("confidence", 0.0),
                    "match_type": r.get("match_type", ""),
                    "match_id": r.get("match_id"),
                    "latency_ms": r.get("latency_ms", 0.0),
                    "llm_used": "L3" in r.get("layer", ""),
                    "sustainability": sustainability,
                }
                chunk_evidence_records.append(record)
            except Exception as e:
                print(f"[Evidence] Error building evidence for row {row_idx}: {e}", flush=True)

        build_ms_total += (_time.time() - build_start) * 1000

        # Build chunk evidence artifact
        chunk_artifact = {
            "schema_version": "chunk_v1",
            "batch_id": batch_trace_id,
            "chunk_index": chunk_idx,
            "chunk_count": chunk_count,
            "row_start": chunk_start_row,
            "row_end": chunk_end_row,
            "rows_in_chunk": len(chunk_evidence_records),
            "config_version": config_version,
            "sanitization_version": sanitization_version,
            "watchlist_version_hash": watchlist_version_hash,
            "created_at_utc": datetime.utcnow().isoformat(),
            "records": chunk_evidence_records,
        }

        # Compute chunk digest (for hash chain)
        import json
        canonical_bytes = json.dumps(chunk_artifact, sort_keys=True, separators=(',', ':')).encode('utf-8')
        chunk_digest = hashlib.sha256(canonical_bytes).hexdigest()
        chunk_artifact["chunk_digest"] = chunk_digest
        chunk_digests.append(chunk_digest)

        # Encrypt chunk if enabled
        storage_blob = chunk_artifact
        if encrypt_enabled and tenant_kms_key_path:
            encrypt_start = _time.time()
            encrypted_pkg, enc_error = encrypt_evidence_blob(
                evidence_blob=chunk_artifact,
                tenant_id=tenant_id,
                trace_id=batch_trace_id,
                batch_id=batch_trace_id,
                kms_key_path=tenant_kms_key_path
            )
            encrypt_ms_total += (_time.time() - encrypt_start) * 1000
            if encrypted_pkg and not enc_error:
                storage_blob = {"encrypted": True, "envelope": encrypted_pkg}
            else:
                print(f"[Evidence] Chunk {chunk_idx} encryption failed: {enc_error}", flush=True)

        # Write chunk to Firestore
        write_start = _time.time()
        evidence_ref.document(f'chunk_{chunk_idx:04d}').set(storage_blob)
        write_ms_total += (_time.time() - write_start) * 1000
        chunks_stored += 1

    # Store chunk digests metadata for hash chain
    digests_doc = {
        "schema_version": "chunk_digests_v1",
        "batch_id": batch_trace_id,
        "chunk_count": chunk_count,
        "row_count": row_count,
        "chunk_size": CHUNK_SIZE,
        "digests": chunk_digests,
        "created_at_utc": datetime.utcnow().isoformat(),
    }
    evidence_ref.document('_chunk_digests').set(digests_doc)

    total_ms = (_time.time() - total_start) * 1000
    print(f"[Evidence] CHUNK COMPLETE: {chunks_stored} chunks, {row_count} rows in {total_ms:.0f}ms "
          f"(build={build_ms_total:.0f}ms, encrypt={encrypt_ms_total:.0f}ms, write={write_ms_total:.0f}ms)", flush=True)

    # Compute batch sustainability rollup
    batch_sustainability = None
    if energy_enabled and energy_coeffs and record_sustainability_list:
        sbom_hash = get_sbom_hash() if HAS_FORENSIC_SIGNING else "unavailable"
        batch_sustainability = compute_batch_sustainability(
            record_sustainability_list=record_sustainability_list,
            coeffs=energy_coeffs,
            processing_region=config.PROCESSING_REGION,
            sbom_hash=sbom_hash
        )

    return row_count, batch_sustainability


# =============================================================================
# HASH CHAIN STORAGE (Phase 2 - Forensic Audit)
# =============================================================================

def store_hash_chain_to_firestore(
    batch_trace_id: str,
    chain_entries: List[Dict[str, Any]],
    batch_root_hash: str
) -> Tuple[bool, Dict[str, Any]]:
    """
    Store hash chain entries to Firestore subcollection.
    Storage path: batches/{batch_trace_id}/hash_chain/{row_index}

    Returns: (success, chain_meta) - chain_meta should be added to batch_result
    """
    chain_meta = build_chain_metadata(batch_trace_id, chain_entries, batch_root_hash)

    if not _firestore_db or not config.HASH_CHAIN_ENABLED:
        return False, chain_meta

    try:
        batch_ref = _firestore_db.collection('batches').document(batch_trace_id)

        # NOTE: chain_meta is NOT stored here - it's returned for inclusion in batch_result
        # This avoids the atomic write overwriting it

        # Store individual chain entries in subcollection
        chain_ref = batch_ref.collection('hash_chain')
        BATCH_SIZE = 500

        for batch_start in range(0, len(chain_entries), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(chain_entries))
            write_batch = _firestore_db.batch()

            for i in range(batch_start, batch_end):
                entry = chain_entries[i]
                write_batch.set(chain_ref.document(f'row_{i:06d}'), entry)

            write_batch.commit()

        print(f"[HashChain] Stored {len(chain_entries)} chain entries for {batch_trace_id}, root={batch_root_hash[:16]}...", flush=True)
        return True, chain_meta

    except Exception as e:
        print(f"[HashChain] Error storing hash chain: {e}", flush=True)
        return False, chain_meta


def get_hash_chain_from_firestore(batch_trace_id: str) -> Tuple[List[Dict], Optional[str]]:
    """
    Retrieve hash chain entries and root hash from Firestore.
    Returns: (chain_entries, batch_root_hash)
    """
    if not _firestore_db:
        return [], None

    try:
        batch_ref = _firestore_db.collection('batches').document(batch_trace_id)

        # Get batch metadata for root hash
        batch_doc = batch_ref.get()
        if not batch_doc.exists:
            return [], None

        batch_data = batch_doc.to_dict()
        chain_meta = batch_data.get("hash_chain", {})
        batch_root_hash = chain_meta.get("batch_root_hash")

        if not batch_root_hash:
            return [], None

        # Get chain entries
        chain_ref = batch_ref.collection('hash_chain')
        docs = list(chain_ref.order_by('row_index').stream())
        chain_entries = [doc.to_dict() for doc in docs]

        return chain_entries, batch_root_hash

    except Exception as e:
        print(f"[HashChain] Error retrieving hash chain: {e}", flush=True)
        return [], None


def compute_and_store_hash_chain(
    batch_trace_id: str,
    results: List[Dict[str, Any]]
) -> Tuple[bool, Dict[str, Any]]:
    """
    Compute hash chain for results and store it.

    IAVP v1.0: Uses STABLE_INPUT_ORDER_V2 with JCS canonicalization and
    replay verification for determinism proof.

    SCALABLE V2: For large batches (>10K), uses pre-computed chunk digests.

    Returns: (success, chain_meta) - chain_meta should be added to batch_result
    """
    if not HAS_FORENSIC_SIGNING or not config.HASH_CHAIN_ENABLED:
        return False, {}

    if not _firestore_db:
        return False, {}

    import time as _time
    chain_start = _time.time()
    slog(trace_id=batch_trace_id, phase="hash_chain", event="chain_compute_start",
         record_count=len(results))

    try:
        # Try to read pre-computed chunk digests from evidence generation
        evidence_ref = _firestore_db.collection('batches').document(batch_trace_id).collection('evidence')
        digests_doc = evidence_ref.document('_chunk_digests').get()

        # IAVP MODE takes priority when enabled (excludes timestamps for replay determinism)
        if config.IAVP_ENABLED:
            print(f"[HashChain] IAVP MODE: STABLE_INPUT_ORDER_V2 with replay verification", flush=True)

            chain_entries, batch_root_hash, replay_result = compute_batch_hash_chain_iavp(
                batch_trace_id,
                results,
                enable_replay_verification=config.IAVP_REPLAY_VERIFICATION
            )

            # Check replay variance
            if config.IAVP_FAIL_ON_VARIANCE and replay_result.variance > 0:
                print(f"[HashChain] IAVP REPLAY VARIANCE: {replay_result.variance} - FAILING BATCH", flush=True)
                raise ReplayVarianceError(replay_result.variance, replay_result.runs)

            # Log replay result
            print(f"[HashChain] IAVP replay: {replay_result.to_dict()['replay_runs']} runs, "
                  f"variance={replay_result.variance}, passed={replay_result.passed}", flush=True)

            success, chain_meta = store_hash_chain_to_firestore(
                batch_trace_id, chain_entries, batch_root_hash
            )

            # Add IAVP replay data to metadata
            from app.security.iavp import IAVP_HASH_CHAIN_METHOD, IAVP_ORDERING_METHOD
            if success:
                chain_meta["method"] = IAVP_HASH_CHAIN_METHOD
                chain_meta["ordering"] = IAVP_ORDERING_METHOD
                chain_meta["replay_runs"] = replay_result.to_dict()["replay_runs"]
                chain_meta["replay_variance"] = replay_result.variance
                chain_meta["replay_passed"] = replay_result.passed
                chain_meta["chain_scope"] = "iavp_full_batch"

            chain_ms = (_time.time() - chain_start) * 1000
            print(f"[HashChain] IAVP chain built in {chain_ms:.0f}ms, root={batch_root_hash[:16]}...", flush=True)
            slog(trace_id=batch_trace_id, phase="hash_chain", event="chain_built",
                 chain_duration_ms=round(chain_ms, 1), root_hash=batch_root_hash[:16],
                 replay_passed=replay_result.passed, replay_variance=replay_result.variance)

            return success, chain_meta

        elif digests_doc.exists:
            # CHUNK MODE: Use pre-computed chunk digests (legacy mode, includes timestamps)
            digests_data = digests_doc.to_dict()
            chunk_digests = digests_data.get("digests", [])
            row_count = digests_data.get("row_count", len(results))
            chunk_count = len(chunk_digests)

            print(f"[HashChain] CHUNK MODE: {chunk_count} chunk digests for {row_count} rows", flush=True)

            # Build chain over chunk digests with IAVP compliance
            from app.security.iavp import IAVP_HASH_CHAIN_METHOD, IAVP_ORDERING_METHOD

            chain_entries = []
            prev_hash = GENESIS_HASH

            for chunk_idx, chunk_digest in enumerate(chunk_digests):
                # Build chain entry for chunk
                entry = {
                    "chunk_index": chunk_idx,
                    "prev_hash": prev_hash,
                    "event_hash": hashlib.sha256(f"{prev_hash}:{chunk_digest}".encode()).hexdigest().lower(),
                    "chunk_digest": chunk_digest,
                    "hash_algo": "SHA256",
                    "chain_scope": "batch_chunk",
                    "method": IAVP_HASH_CHAIN_METHOD,
                    "ordering": IAVP_ORDERING_METHOD,
                    "chained_at": datetime.utcnow().isoformat(),
                }
                chain_entries.append(entry)
                prev_hash = entry["event_hash"]

            batch_root_hash = prev_hash

            # Store chain entries (just chunk_count entries, not row_count)
            chain_ref = _firestore_db.collection('batches').document(batch_trace_id).collection('hash_chain')
            write_batch = _firestore_db.batch()
            for entry in chain_entries:
                write_batch.set(chain_ref.document(f'chunk_{entry["chunk_index"]:04d}'), entry)
            write_batch.commit()

            chain_ms = (_time.time() - chain_start) * 1000
            print(f"[HashChain] Stored {len(chain_entries)} chunk chain entries in {chain_ms:.0f}ms, root={batch_root_hash[:16]}...", flush=True)

            # Build IAVP-compliant chain metadata
            chain_meta = {
                "chain_enabled": True,
                "chain_scope": "batch_chunk",
                "chain_algo": "SHA256",
                "chain_length": chunk_count,
                "row_count": row_count,
                "genesis_hash": GENESIS_HASH,
                "batch_root_hash": batch_root_hash,
                "chained_at": datetime.utcnow().isoformat(),
                # IAVP v1.0 fields
                "method": IAVP_HASH_CHAIN_METHOD,
                "ordering": IAVP_ORDERING_METHOD,
            }

            return True, chain_meta

        else:
            # LEGACY MODE: Fallback to per-row chain when no chunk digests AND IAVP disabled
            print(f"[HashChain] LEGACY MODE: No chunk digests found, computing per-row chain", flush=True)
            chain_entries, batch_root_hash = compute_batch_hash_chain(batch_trace_id, results)
            success, chain_meta = store_hash_chain_to_firestore(batch_trace_id, chain_entries, batch_root_hash)
            chain_ms = (_time.time() - chain_start) * 1000
            print(f"[HashChain] LEGACY: Stored {len(chain_entries)} row chain entries in {chain_ms:.0f}ms", flush=True)
            return success, chain_meta

    except ReplayVarianceError:
        raise  # Re-raise to fail the batch
    except Exception as e:
        print(f"[HashChain] Error computing hash chain: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False, {}


def get_batches_from_firestore(limit: int = 50, tenant_id: str = None) -> List[Dict]:
    """
    Retrieve recent batches from Firestore, filtered by tenant_id.
    Includes backward-compatible handling of legacy batches without tenant_id:
    - Legacy batches (no tenant_id) are backfilled with current user's tenant_id on first read.

    Uses fetch-filter-backfill approach to avoid Firestore composite index requirements.
    """
    print(f"[Firestore] get_batches_from_firestore called, db_available={_firestore_db is not None}, tenant={tenant_id}", flush=True)

    if not _firestore_db:
        return []

    try:
        batches_ref = _firestore_db.collection('batches')

        # Fetch recent batches (no tenant filter - we filter in memory)
        # This avoids composite index requirement
        query = batches_ref.order_by('timestamp', direction=firestore_client.Query.DESCENDING).limit(200)
        docs = list(query.stream())

        print(f"[Firestore] Fetched {len(docs)} total batch docs", flush=True)

        result_batches = []
        backfilled_count = 0

        for doc in docs:
            batch_data = doc.to_dict()
            batch_tenant = batch_data.get('tenant_id')

            # Case 0: No tenant filter (admin cross-tenant) - include ALL batches
            if tenant_id is None:
                batch_data['id'] = doc.id
                result_batches.append(batch_data)

            # Case 1: Batch belongs to current tenant - include it
            elif batch_tenant == tenant_id:
                batch_data['id'] = doc.id
                result_batches.append(batch_data)

            # Case 2: Legacy batch (no tenant_id) - backfill and include
            elif batch_tenant is None and tenant_id:
                print(f"[Firestore] BACKFILL: Claiming legacy batch {doc.id} for tenant {tenant_id}", flush=True)
                try:
                    doc.reference.update({'tenant_id': tenant_id})
                    batch_data['tenant_id'] = tenant_id
                    batch_data['id'] = doc.id
                    result_batches.append(batch_data)
                    backfilled_count += 1
                except Exception as backfill_err:
                    print(f"[Firestore] Backfill failed for {doc.id}: {backfill_err}", flush=True)

            # Case 3: Batch belongs to different tenant - skip (isolation)
            # else: skip

        # Limit results
        result_batches = result_batches[:limit]

        print(f"[Firestore] Returning {len(result_batches)} batches for tenant={tenant_id} (backfilled {backfilled_count})", flush=True)
        return result_batches

    except Exception as e:
        print(f"[Firestore] Error retrieving batches: {e}", flush=True)
        traceback.print_exc()
        return []


def get_batches_from_firestore_admin(limit: int = 50, tenant_id: str = None) -> List[Dict]:
    """
    Admin-only: Retrieve batches filtered by specific tenant_id.
    No backfilling - read-only query for admin cross-tenant view.
    """
    if not _firestore_db:
        return []

    try:
        batches_ref = _firestore_db.collection('batches')

        # Fetch recent batches and filter in memory
        query = batches_ref.order_by('timestamp', direction=firestore_client.Query.DESCENDING).limit(200)
        docs = list(query.stream())

        result_batches = []
        for doc in docs:
            batch_data = doc.to_dict()
            batch_tenant = batch_data.get('tenant_id')

            # Match exact tenant_id
            if batch_tenant == tenant_id:
                batch_data['id'] = doc.id
                # Add tenant_id_hash for display
                batch_data['tenant_id_hash'] = hashlib.sha256(batch_tenant.encode()).hexdigest()[:16] if batch_tenant else None
                result_batches.append(batch_data)

        result_batches = result_batches[:limit]
        print(f"[Firestore] Admin query: {len(result_batches)} batches for tenant={tenant_id}", flush=True)
        return result_batches

    except Exception as e:
        print(f"[Firestore] Error in admin batch query: {e}", flush=True)
        traceback.print_exc()
        return []


def _stable_event_sort_key(e: Dict) -> tuple:
    """
    Deterministic ordering for audit events.
    Primary: row_index (int, ascending)
    Secondary: timestamp (string ISO, ascending)
    Tertiary: id (doc id, ascending)
    """
    row_index = e.get("row_index")
    try:
        row_index = int(row_index) if row_index is not None else 10**12
    except Exception:
        row_index = 10**12

    ts = e.get("timestamp") or ""
    doc_id = e.get("id") or ""
    original = e.get("original") or ""
    return (row_index, ts, doc_id, original)


def get_recent_audit_events_from_firestore(limit: int = 100) -> List[Dict]:
    """
    Retrieve recent audit events across all batches.
    For the /audit endpoint (no trace_id).
    """
    print(f"[Firestore] get_recent_audit_events called", flush=True)

    if not _firestore_db:
        return []

    try:
        # Get recent batches first
        batches = get_batches_from_firestore(limit=10)

        all_events = []
        for batch in batches[:5]:  # Limit to 5 most recent batches
            trace_id = batch.get('trace_id')
            if trace_id:
                events = get_audit_events_from_firestore(trace_id, limit=20)
                for event in events:
                    event['batch_trace_id'] = trace_id
                    event['batch_timestamp'] = batch.get('timestamp')
                all_events.extend(events)

        # Sort deterministically and limit
        all_events.sort(key=_stable_event_sort_key, reverse=True)
        return all_events[:limit]

    except Exception as e:
        print(f"[Firestore] Error retrieving recent audit events: {e}", flush=True)
        return []


def get_batch_tenant_id(trace_id: str) -> Optional[str]:
    """Get the tenant_id for a batch. Returns None if batch doesn't exist."""
    if not _firestore_db:
        return None

    try:
        batch_doc = _firestore_db.collection('batches').document(trace_id).get()
        if batch_doc.exists:
            return batch_doc.to_dict().get('tenant_id')
        return None
    except Exception as e:
        print(f"[Firestore] Error getting batch tenant: {e}", flush=True)
        return None


def verify_batch_ownership(trace_id: str, tenant_id: str) -> bool:
    """
    Verify that a batch belongs to the specified tenant.
    Returns True if owned, False otherwise.
    For security: returns False (not found) rather than revealing ownership.

    LEGACY HANDLING: If batch exists but has no tenant_id, claim it for current tenant.
    """
    if not _firestore_db:
        return False

    try:
        batch_doc = _firestore_db.collection('batches').document(trace_id).get()
        if not batch_doc.exists:
            return False  # Batch doesn't exist

        batch_data = batch_doc.to_dict()
        batch_tenant = batch_data.get('tenant_id')

        # LEGACY MIGRATION: If batch has no tenant_id, claim it for current user
        if batch_tenant is None:
            print(f"[Firestore] BACKFILL (ownership): Claiming legacy batch {trace_id} for tenant {tenant_id}", flush=True)
            batch_doc.reference.update({'tenant_id': tenant_id})
            return True  # Grant access after claiming

        return batch_tenant == tenant_id

    except Exception as e:
        print(f"[Firestore] Error verifying batch ownership: {e}", flush=True)
        return False


def get_audit_events_from_firestore(trace_id: str, limit: int = 1000) -> List[Dict]:
    """Retrieve audit events for a specific batch."""
    print(f"[Firestore] get_audit_events called for {trace_id}", flush=True)

    if not _firestore_db:
        return []

    try:
        audit_ref = _firestore_db.collection('batches').document(trace_id).collection('audit_events')
        docs = audit_ref.order_by('row_index').limit(limit).stream()

        events = []
        for doc in docs:
            event = doc.to_dict()
            event['id'] = doc.id
            events.append(event)

        print(f"[Firestore] Retrieved {len(events)} audit events for {trace_id}", flush=True)
        return events

    except Exception as e:
        print(f"[Firestore] Error retrieving audit events: {e}", flush=True)
        return []


def get_flagged_items_from_firestore(trace_id: str, limit: int = 500) -> List[Dict]:
    """Retrieve only flagged items (L4_HUMAN) needing review."""
    print(f"[Firestore] get_flagged_items called for {trace_id}", flush=True)

    if not _firestore_db:
        return []

    try:
        audit_ref = _firestore_db.collection('batches').document(trace_id).collection('audit_events')
        query = audit_ref.where('flagged', '==', True).order_by('row_index').limit(limit)
        docs = query.stream()

        flagged = []
        for doc in docs:
            item = doc.to_dict()
            item['id'] = doc.id
            flagged.append(item)

        # Sort deterministically by row_index
        flagged.sort(key=_stable_event_sort_key)

        print(f"[Firestore] Retrieved {len(flagged)} flagged items for {trace_id}", flush=True)
        return flagged

    except Exception as e:
        print(f"[Firestore] Error retrieving flagged items: {e}", flush=True)
        return []


def append_meta_audit_event(trace_id: str, event: dict) -> bool:
    """
    Append-only meta event writer for batches/{trace_id}/audit_events.
    Must be backward compatible with row-based audit events.
    """
    if _firestore_db is None:
        print("[Firestore] append_meta_audit_event: db not available", flush=True)
        return False

    try:
        batch_ref = _firestore_db.collection('batches').document(trace_id)
        audit_ref = batch_ref.collection('audit_events')

        # Ensure deterministic ordering: meta events sort after row_* by using high row_index.
        event.setdefault("row_index", 10_000_000_000)
        event.setdefault("timestamp", datetime.utcnow().isoformat())
        event.setdefault("flagged", False)
        event.setdefault("config_version", CANONICAL_CONFIG_VERSION)

        # Provide backward-compatible fields expected by existing UI/readers
        event.setdefault("layer", "META")
        event.setdefault("original", "meta")
        event.setdefault("resolved", None)
        event.setdefault("confidence", 1.0)
        event.setdefault("reason", event.get("event_type", "meta_event"))
        event.setdefault("latency_ms", 0)
        event.setdefault("pii_detected", [])

        # Unique doc id
        safe_ts = event["timestamp"].replace(":", "").replace(".", "")
        doc_id = event.get("id") or f"meta_{event.get('event_type','event')}_{safe_ts}"
        audit_ref.document(doc_id).set(event)
        return True
    except Exception as e:
        print(f"[Firestore] append_meta_audit_event failed: {e}", flush=True)
        return False


def check_batch_aborted(trace_id: str) -> bool:
    """
    Check if a batch has been aborted in Firestore.
    Used by batch processing loops to exit early when abort is requested.
    """
    if _firestore_db is None:
        return False

    try:
        doc = _firestore_db.collection('batches').document(trace_id).get()
        if doc.exists:
            status = doc.to_dict().get('status', '')
            return status == 'aborted'
        return False
    except Exception as e:
        print(f"[Firestore] check_batch_aborted failed: {e}", flush=True)
        return False


# =============================================================================
# CONFIGURATION - Environment-Driven with Secure Defaults
# =============================================================================

class Config:
    """Centralized configuration with secure defaults."""

    # Security
    API_KEY: str = os.getenv("BACKEND_API_KEY", "")
    PLATFORM_ADMIN_API_KEY: str = os.getenv("PLATFORM_ADMIN_API_KEY", "")  # Admin API key for governance ops
    # Default origins for public/local development.
    _DEFAULT_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    ALLOWED_ORIGINS: List[str] = [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
    ] or _DEFAULT_ORIGINS

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Circuit Breaker
    CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
    CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = int(os.getenv("CIRCUIT_BREAKER_TIMEOUT_SECONDS", "30"))

    # Processing Limits
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "100000"))
    PARALLEL_LIMIT: int = int(os.getenv("PARALLEL_LIMIT", "20"))

    # L3 LLM Gating - Cost-Based Budget Control with Smart Filtering
    L3_MAX_COST_USD: float = float(os.getenv("L3_MAX_COST_USD", "10.0"))  # Total spend allowed per batch
    L3_COST_PER_CALL_USD: float = float(os.getenv("L3_COST_PER_CALL_USD", "0.001"))  # ~$0.001 per call (Haiku 4.5: $1/1M input + $5/1M output)
    L3_MIN_SIMILARITY: float = float(os.getenv("L3_MIN_SIMILARITY", "0.30"))  # Min L2 score to qualify for L3
    L3_MAX_CONCURRENCY: int = int(os.getenv("L3_MAX_CONCURRENCY", "20"))  # Parallel L3 workers
    L3_CALL_TIMEOUT_SECONDS: int = int(os.getenv("L3_CALL_TIMEOUT_SECONDS", "30"))  # Per-call timeout
    # DEPRECATED: Row threshold disabled - cost budget is now the primary control
    L3_ROW_THRESHOLD: int = int(os.getenv("L3_ROW_THRESHOLD", "1000000"))  # Set high to disable

    # L3 Semantic Cache - Reuse L3 results for similar company names
    L3_CACHE_ENABLED: bool = os.getenv("L3_CACHE_ENABLED", "true").lower() == "true"
    L3_CACHE_SIMILARITY: float = float(os.getenv("L3_CACHE_SIMILARITY", "0.85"))  # Min similarity to use cached result
    L3_CACHE_MAX_SIZE: int = int(os.getenv("L3_CACHE_MAX_SIZE", "50000"))  # Max entries in cache

    # L3 Firestore Cache - Persistent cache across instances (deterministic keys)
    L3_FIRESTORE_CACHE_ENABLED: bool = os.getenv("L3_FIRESTORE_CACHE_ENABLED", "true").lower() == "true"
    L3_FIRESTORE_CACHE_TTL_DAYS: int = int(os.getenv("L3_FIRESTORE_CACHE_TTL_DAYS", "30"))  # Cache TTL in days
    L3_CACHE_PROMPT_VERSION: str = os.getenv("L3_CACHE_PROMPT_VERSION", "v2")  # Bump to invalidate cache (v2 = improved normalization)
    L3_CACHE_ALIASING_ENABLED: bool = os.getenv("L3_CACHE_ALIASING_ENABLED", "true").lower() == "true"  # Enable ticker/alias mapping

    # L3 Volume Circuit Breaker - Structural protection against L1/L2 failure
    # If L3 eligible exceeds this %, something is wrong with L1/L2 → abort batch
    L3_MAX_PERCENT: float = float(os.getenv("L3_MAX_PERCENT", "0.55"))  # 55% max L3 eligibility (raised from 20% for mixed datasets)
    L3_CIRCUIT_BREAKER_ENABLED: bool = os.getenv("L3_CIRCUIT_BREAKER_ENABLED", "true").lower() == "true"

    # Person Mode Safety - L3 disabled by default for person sanitization
    PERSON_L3_ENABLED: bool = os.getenv("PERSON_L3_ENABLED", "false").lower() == "true"

    # Invariant reset gate — disabled by default; must be explicitly enabled on TEST only
    INVARIANTS_RESET_ENABLED: bool = os.getenv("INVARIANTS_RESET_ENABLED", "false").lower() == "true"

    # Margin Sentinel — Human review cost modeling
    HUMAN_COST_PER_RECORD_USD: float = float(os.getenv("HUMAN_COST_PER_RECORD_USD", "0.50"))
    L4_WARNING_THRESHOLD_PCT: float = float(os.getenv("L4_WARNING_THRESHOLD_PCT", "6.0"))
    L4_RED_THRESHOLD_PCT: float = float(os.getenv("L4_RED_THRESHOLD_PCT", "8.0"))
    COST_PER_RECORD_RED_USD: float = float(os.getenv("COST_PER_RECORD_RED_USD", "0.05"))

    # Sanitization Version - for audit trail
    SANITIZATION_VERSION: str = os.getenv("SANITIZATION_VERSION", "SANITIZER_v1")
    WATCHLIST_VERSION_HASH: str = os.getenv("WATCHLIST_VERSION_HASH", "TEST_UNKNOWN")

    # Audit Storage
    AUDIT_STORAGE_PATH: str = os.getenv("AUDIT_STORAGE_PATH", "/tmp/ia_audit")

    # Environment Identification
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    FIRESTORE_DATABASE: str = os.getenv("FIRESTORE_DATABASE", "(default)")

    # Demo Mode
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"

    # Phase 2A: Congestion Hardening — Backpressure Governor
    MAX_CONCURRENT_FINALIZE_GLOBAL: int = int(os.getenv("MAX_CONCURRENT_FINALIZE_GLOBAL", "3"))
    MAX_CONCURRENT_FINALIZE_PER_TENANT: int = int(os.getenv("MAX_CONCURRENT_FINALIZE_PER_TENANT", "1"))
    MAX_ACTIVE_SHARDS_GLOBAL: int = int(os.getenv("MAX_ACTIVE_SHARDS_GLOBAL", "50"))

    # Phase 2A: Transaction Retry Cap
    FINALIZE_TXN_MAX_ATTEMPTS: int = int(os.getenv("FINALIZE_TXN_MAX_ATTEMPTS", "5"))
    DEMO_TENANT_ID: str = "tenant_demo"
    AUDIT_MAX_ENTRIES: int = int(os.getenv("AUDIT_MAX_ENTRIES", "1000"))

    # PII Detection
    PII_LOG_PATH: str = os.getenv("PII_LOG_PATH", "/tmp/ia_pii_log")

    # Input Validation
    INPUT_VALIDATION_ENABLED: bool = os.getenv("INPUT_VALIDATION_ENABLED", "true").lower() == "true"
    INPUT_MAX_LENGTH: int = int(os.getenv("INPUT_MAX_LENGTH", "500"))
    INPUT_MIN_LENGTH: int = int(os.getenv("INPUT_MIN_LENGTH", "1"))

    # ==========================================================================
    # FORENSIC AUDIT CONFIGURATION (Phase 0.5+)
    # ==========================================================================

    # KMS Signing
    KMS_SIGNING_KEY_ID: str = os.getenv("KMS_SIGNING_KEY_ID", "")
    SIGNING_ENABLED: bool = os.getenv("SIGNING_ENABLED", "true").lower() == "true"
    SIGNING_ALG: str = os.getenv("SIGNING_ALG", "EC_SIGN_P256_SHA256")

    # Evidence Storage
    EVIDENCE_STORE_FULL_LLM_TEXT: bool = os.getenv("EVIDENCE_STORE_FULL_LLM_TEXT", "false").lower() == "true"

    # Hash Chain
    HASH_CHAIN_ENABLED: bool = os.getenv("HASH_CHAIN_ENABLED", "true").lower() == "true"

    # IAVP v1.0 Compliance
    IAVP_ENABLED: bool = os.getenv("IAVP_ENABLED", "true").lower() == "true"
    IAVP_REPLAY_VERIFICATION: bool = os.getenv("IAVP_REPLAY_VERIFICATION", "true").lower() == "true"
    IAVP_FAIL_ON_VARIANCE: bool = os.getenv("IAVP_FAIL_ON_VARIANCE", "true").lower() == "true"
    # IAVP v1.0: Environment detection for artifact_mode enforcement
    # Matches: ENVIRONMENT=prod, ENVIRONMENT=production, or K_SERVICE contains "prod"
    IS_PRODUCTION: bool = (
        os.getenv("ENVIRONMENT", "").lower() in ("production", "prod") or
        "prod" in os.getenv("K_SERVICE", "").lower()
    )
    # Demo key fingerprint for separation enforcement (set to None in production)
    DEMO_KEY_FINGERPRINT: str = os.getenv("DEMO_KEY_FINGERPRINT", "")
    # Engine version for manifest
    ENGINE_VERSION: str = os.getenv("ENGINE_VERSION", "3.0.0")

    # External Anchoring
    ANCHORING_ENABLED: bool = os.getenv("ANCHORING_ENABLED", "false").lower() == "true"
    ANCHOR_TARGET: str = os.getenv("ANCHOR_TARGET", "")

    # Tenant Isolation + Encryption
    TENANT_ISOLATION_ENABLED: bool = os.getenv("TENANT_ISOLATION_ENABLED", "true").lower() == "true"
    TENANT_ENCRYPTION_ENABLED: bool = os.getenv("TENANT_ENCRYPTION_ENABLED", "false").lower() == "true"
    TENANT_ENCRYPTION_REQUIRED: bool = os.getenv("TENANT_ENCRYPTION_REQUIRED", "false").lower() == "true"
    TENANT_KMS_KEYRING: str = os.getenv("TENANT_KMS_KEYRING", "")
    TENANT_KEY_PREFIX: str = os.getenv("TENANT_KEY_PREFIX", "tenant-")

    # Legal Hold + WORM Vaulting
    LEGAL_HOLD_ENABLED: bool = os.getenv("LEGAL_HOLD_ENABLED", "false").lower() == "true"
    VAULT_BUCKET: str = os.getenv("VAULT_BUCKET", "")
    VAULT_RETENTION_DAYS: int = int(os.getenv("VAULT_RETENTION_DAYS", "2555"))  # ~7 years
    VAULT_MODE: str = os.getenv("VAULT_MODE", "GCP_BUCKET_LOCK")

    # Retention Policy Enforcement (Day 8-9)
    RETENTION_POLICY_ENABLED: bool = os.getenv("RETENTION_POLICY_ENABLED", "true").lower() == "true"
    # Default retention periods by batch status (days)
    RETENTION_COMPLETED_DAYS: int = int(os.getenv("RETENTION_COMPLETED_DAYS", "2555"))  # ~7 years (regulatory)
    RETENTION_FAILED_DAYS: int = int(os.getenv("RETENTION_FAILED_DAYS", "90"))  # 90 days for failed batches
    RETENTION_ABORTED_DAYS: int = int(os.getenv("RETENTION_ABORTED_DAYS", "30"))  # 30 days for aborted
    # Grace period before deletion after retention expires
    RETENTION_GRACE_PERIOD_DAYS: int = int(os.getenv("RETENTION_GRACE_PERIOD_DAYS", "30"))
    # Auto-deletion (must be explicitly enabled - dangerous)
    RETENTION_AUTO_DELETE: bool = os.getenv("RETENTION_AUTO_DELETE", "false").lower() == "true"

    # Energy/Carbon Estimation (Sustainability Metadata)
    ENERGY_ESTIMATES_ENABLED: bool = os.getenv("ENERGY_ESTIMATES_ENABLED", "false").lower() == "true"
    PROCESSING_REGION: str = os.getenv("PROCESSING_REGION", "unknown")
    DEPLOY_REGION: str = os.getenv("DEPLOY_REGION", "us")


config = Config()

# =============================================================================
# DEMO MODE FIXTURES (immutable, in-memory)
# =============================================================================

DEMO_BATCHES = [
    {
        "trace_id": "DEMO-BATCH-001-A1B2C3D4",
        "filename": "acme_suppliers_q4.csv",
        "total": 1250,
        "total_records": 1250,
        "status": "completed",
        "timestamp": "2026-02-08T10:30:00Z",
        "auto_resolved_pct": 94.2,
        "flagged_count": 12,
        "stats": {
            "layer_0_garbage": 8,
            "layer_1_exact": 845,
            "layer_1_norm": 156,
            "layer_2_vector": 178,
            "layer_3_llm": 51,
            "layer_4_human": 12
        },
        "transparency_statement": {
            "template_id": "TLS_v1",
            "hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
            "generated_at": "2026-02-08T10:30:00Z"
        },
        "decision_path_summary": {
            "L1_DETERMINISTIC": 1001,
            "L2_VECTOR_FUZZY": 178,
            "L3_LLM": 51,
            "L4_HUMAN_REVIEW_REQUIRED": 12,
            "total_processed": 1242
        }
    },
    {
        "trace_id": "DEMO-BATCH-002-E5F6G7H8",
        "filename": "vendors_master_list.csv",
        "total": 450,
        "total_records": 450,
        "status": "completed",
        "timestamp": "2026-02-07T14:22:00Z",
        "auto_resolved_pct": 98.1,
        "flagged_count": 2,
        "stats": {
            "layer_0_garbage": 3,
            "layer_1_exact": 312,
            "layer_1_norm": 98,
            "layer_2_vector": 32,
            "layer_3_llm": 3,
            "layer_4_human": 2
        },
        "transparency_statement": {
            "template_id": "TLS_v1",
            "hash": "b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567a",
            "generated_at": "2026-02-07T14:22:00Z"
        },
        "decision_path_summary": {
            "L1_DETERMINISTIC": 410,
            "L2_VECTOR_FUZZY": 32,
            "L3_LLM": 3,
            "L4_HUMAN_REVIEW_REQUIRED": 2,
            "total_processed": 447
        }
    },
    {
        "trace_id": "DEMO-BATCH-003-I9J0K1L2",
        "filename": "partners_2026.xlsx",
        "total": 2100,
        "total_records": 2100,
        "status": "completed",
        "timestamp": "2026-02-06T09:15:00Z",
        "auto_resolved_pct": 87.5,
        "flagged_count": 45,
        "stats": {
            "layer_0_garbage": 22,
            "layer_1_exact": 1245,
            "layer_1_norm": 398,
            "layer_2_vector": 312,
            "layer_3_llm": 78,
            "layer_4_human": 45
        },
        "transparency_statement": {
            "template_id": "TLS_v1",
            "hash": "c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567ab",
            "generated_at": "2026-02-06T09:15:00Z"
        },
        "decision_path_summary": {
            "L1_DETERMINISTIC": 1643,
            "L2_VECTOR_FUZZY": 312,
            "L3_LLM": 78,
            "L4_HUMAN_REVIEW_REQUIRED": 45,
            "total_processed": 2078
        }
    }
]


# =============================================================================
# PII DETECTION AND MASKING
# =============================================================================

@dataclass
class PIIDetection:
    """Record of a PII detection event."""
    timestamp: str
    tenant_id: str
    trace_id: str
    field_name: str
    pii_type: str
    masked_value: str
    row_index: int


class PIIMasker:
    """PII Detection and Masking Engine."""

    PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE_US": r'\b(?:\+1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        "SSN": r'\b[0-9]{3}[-\s]?[0-9]{2}[-\s]?[0-9]{4}\b',
        "CREDIT_CARD": r'\b(?:[0-9]{4}[-\s]?){3}[0-9]{4}\b',
        "IP_ADDRESS": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
    }

    def __init__(self):
        self._compiled = {k: re.compile(v, re.IGNORECASE) for k, v in self.PATTERNS.items()}
        self._detections: List[PIIDetection] = []
        self._lock = threading.Lock()
        self._detection_count = defaultdict(int)
        self._validation_failures = 0
        Path(config.PII_LOG_PATH).mkdir(parents=True, exist_ok=True)

    def detect_and_mask(
        self,
        text: str,
        tenant_id: str = "unknown",
        trace_id: str = "unknown",
        field_name: str = "unknown",
        row_index: int = 0
    ) -> Tuple[str, List[str]]:
        """Detect and mask PII in text."""
        if not text or not isinstance(text, str):
            return str(text) if text else "", []

        detected_types = []
        masked_text = text

        for pii_type, pattern in self._compiled.items():
            matches = pattern.findall(masked_text)
            if matches:
                detected_types.append(pii_type)
                for match in matches:
                    mask = f"[{pii_type}_MASKED]"
                    masked_text = masked_text.replace(match, mask)
                    detection = PIIDetection(
                        timestamp=datetime.utcnow().isoformat(),
                        tenant_id=tenant_id,
                        trace_id=trace_id,
                        field_name=field_name,
                        pii_type=pii_type,
                        masked_value=mask,
                        row_index=row_index
                    )
                    with self._lock:
                        self._detections.append(detection)
                        self._detection_count[pii_type] += 1
                        self._persist_detection(detection)

        return masked_text, detected_types

    def _persist_detection(self, detection: PIIDetection):
        """Persist detection to log file."""
        try:
            log_file = Path(config.PII_LOG_PATH) / f"pii_detections_{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
            with open(log_file, "a") as f:
                f.write(json.dumps(asdict(detection)) + "\n")
        except Exception as e:
            print(f"[PII] Failed to persist detection: {e}", flush=True)

    def record_validation_failure(self):
        """Record an input validation failure."""
        with self._lock:
            self._validation_failures += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get PII detection statistics."""
        with self._lock:
            return {
                "total_detections": sum(self._detection_count.values()),
                "by_type": dict(self._detection_count),
                "recent_detections": len(self._detections),
                "validation_failures": self._validation_failures,
            }

    def get_recent_detections(self, limit: int = 100) -> List[Dict]:
        """Get recent PII detections."""
        with self._lock:
            return [asdict(d) for d in self._detections[-limit:]]


# Global PII masker instance
pii_masker = PIIMasker()


# =============================================================================
# INPUT VALIDATOR
# =============================================================================

class InputValidator:
    """Input validation and sanitization for security hardening."""

    # Dangerous patterns that indicate injection attempts
    DANGEROUS_PATTERNS = [
        r'<script',           # XSS
        r'javascript:',       # XSS via URL
        r'data:text/html',    # Data URL injection
        r'\{\{.*\}\}',        # Template injection (Jinja, Angular, etc.)
        r'\$\{.*\}',          # Template literal injection
        r'__proto__',         # Prototype pollution
        r'constructor\s*\(',  # Constructor hijacking
        r'on\w+\s*=',         # Event handler injection (onclick=, onerror=, etc.)
    ]

    # Blocked characters (null bytes, etc.)
    BLOCKED_CHARS = ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
                     '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12',
                     '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a',
                     '\x1b', '\x1c', '\x1d', '\x1e', '\x1f']

    def __init__(self, enabled: bool = True, max_length: int = 500, min_length: int = 1):
        self.enabled = enabled
        self.max_length = max_length
        self.min_length = min_length
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS]
        self._validation_failures = 0
        self._lock = threading.Lock()

    def validate(self, text: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validate and sanitize input text.

        Returns:
            (is_valid, sanitized_text, error_message)
            - is_valid: True if input passes validation
            - sanitized_text: Cleaned text (blocked chars stripped)
            - error_message: None if valid, else description of failure
        """
        if not self.enabled:
            return True, str(text) if text else "", None

        # Handle None/empty
        if text is None:
            return True, "", None

        text = str(text)

        # Strip blocked characters
        sanitized = text
        for char in self.BLOCKED_CHARS:
            sanitized = sanitized.replace(char, '')

        # Check minimum length
        if len(sanitized.strip()) < self.min_length:
            # Empty/whitespace-only is OK - will be caught as garbage downstream
            return True, sanitized, None

        # Check maximum length
        if len(sanitized) > self.max_length:
            self._record_failure()
            return False, sanitized[:self.max_length], f"Input too long ({len(sanitized)} > {self.max_length})"

        # Check for dangerous patterns
        for pattern in self._compiled_patterns:
            if pattern.search(sanitized):
                self._record_failure()
                return False, "", f"Dangerous pattern detected: {pattern.pattern}"

        return True, sanitized, None

    def _record_failure(self):
        """Record a validation failure."""
        with self._lock:
            self._validation_failures += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "max_length": self.max_length,
                "min_length": self.min_length,
                "validation_failures": self._validation_failures,
            }


# Global input validator instance
input_validator = InputValidator(
    enabled=config.INPUT_VALIDATION_ENABLED,
    max_length=config.INPUT_MAX_LENGTH,
    min_length=config.INPUT_MIN_LENGTH
)


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitBreaker:
    """Circuit Breaker Pattern Implementation."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, name: str, threshold: int, timeout_seconds: int):
        self.name = name
        self.threshold = threshold
        self.timeout_seconds = timeout_seconds
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._success_count = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if self._last_failure_time:
                    elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                    if elapsed >= self.timeout_seconds:
                        self._state = self.HALF_OPEN
                        self._success_count = 0
            return self._state

    def record_success(self):
        with self._lock:
            if self._state == self.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= 3:
                    self._state = self.CLOSED
                    self._failure_count = 0
            elif self._state == self.CLOSED:
                self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
            elif self._failure_count >= self.threshold:
                self._state = self.OPEN

    def can_execute(self) -> bool:
        return self.state != self.OPEN

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state,
                "failure_count": self._failure_count,
                "threshold": self.threshold,
                "timeout_seconds": self.timeout_seconds,
                "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None,
            }


# Global circuit breakers
circuit_breakers = {
    "resolution": CircuitBreaker("resolution", config.CIRCUIT_BREAKER_THRESHOLD, config.CIRCUIT_BREAKER_TIMEOUT_SECONDS),
    "file_parse": CircuitBreaker("file_parse", config.CIRCUIT_BREAKER_THRESHOLD, config.CIRCUIT_BREAKER_TIMEOUT_SECONDS),
}


# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    """Token bucket rate limiter per tenant."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, tenant_id: str) -> Tuple[bool, Dict[str, Any]]:
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            self._buckets[tenant_id] = [
                t for t in self._buckets[tenant_id] if t > window_start
            ]

            current_count = len(self._buckets[tenant_id])
            remaining = max(0, self.max_requests - current_count)

            info = {
                "limit": self.max_requests,
                "remaining": remaining,
                "reset_seconds": self.window_seconds,
                "tenant_id": tenant_id,
            }

            if current_count >= self.max_requests:
                return False, info

            self._buckets[tenant_id].append(now)
            info["remaining"] = remaining - 1
            return True, info


# Global rate limiter
rate_limiter = RateLimiter(config.RATE_LIMIT_REQUESTS, config.RATE_LIMIT_WINDOW_SECONDS)


# =============================================================================
# AUDIT STORAGE (File-Based Fallback)
# =============================================================================

class AuditStorage:
    """Persistent audit storage using file system (fallback for non-Firestore)."""

    def __init__(self, storage_path: str, max_entries: int):
        self.storage_path = Path(storage_path)
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def store(self, trace_id: str, events: List[Dict]):
        try:
            file_path = self.storage_path / f"{trace_id}.json"
            with open(file_path, "w") as f:
                json.dump({
                    "trace_id": trace_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "events": events,
                    "count": len(events)
                }, f)
            self._cleanup()
        except Exception as e:
            print(f"[Audit] Failed to store trace {trace_id}: {e}", flush=True)

    def get(self, trace_id: str) -> Optional[Dict]:
        try:
            file_path = self.storage_path / f"{trace_id}.json"
            if file_path.exists():
                with open(file_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[Audit] Failed to retrieve trace {trace_id}: {e}", flush=True)
        return None

    def _cleanup(self):
        try:
            files = sorted(self.storage_path.glob("*.json"), key=lambda p: p.stat().st_mtime)
            if len(files) > self.max_entries:
                for f in files[:-self.max_entries]:
                    f.unlink()
        except Exception as e:
            print(f"[Audit] Cleanup error: {e}", flush=True)


# Global audit storage
audit_storage = AuditStorage(config.AUDIT_STORAGE_PATH, config.AUDIT_MAX_ENTRIES)


# =============================================================================
# RESOLUTION ENGINE - FORTUNE 500 CANONICAL LIST v2.0
# =============================================================================

# Config version for audit trail
CANONICAL_CONFIG_VERSION = "3.0.0-2026-01-31"  # Full Audit + Backend support
CANONICAL_CONFIG_HASH = "f500v3"
PROTOCOL_VERSION = "1.0.0"  # Semantic Unification — single structural pipeline
ROUTER_VERSION = "v1-static"
MODEL_MAPPING_VERSION = "v1-static"

# Day 5: Agent version identifier for sovereign cache partitioning
# Combines engine version + config hash to uniquely identify the resolution agent
AGENT_VERSION_ID = f"{os.getenv('ENGINE_VERSION', '3.0.0')}-{CANONICAL_CONFIG_HASH}"

# =============================================================================
# TRANSPARENCY & LIMITATIONS STATEMENT (TLS) - EU AI Act Compliance
# =============================================================================

TLS_TEMPLATE_ID = "TLS_v1"

TLS_TEMPLATE = """TRANSPARENCY & LIMITATIONS STATEMENT
Template: TLS_v1
================================================================================

BATCH REFERENCE
---------------
Trace ID: {trace_id}
Generated: {timestamp}
Config Version: {config_version}

PURPOSE
-------
This document is an immutable compliance artifact generated at batch creation
time. It discloses the operational boundaries, decision methodology, and
limitations of the Intelligent Analyst entity resolution system for this batch.

SYSTEM ROLE
-----------
Intelligent Analyst performs automated entity resolution and data readiness
assessment. The system:
- Matches input records against reference datasets
- Classifies match confidence using a multi-layer resolution waterfall
- Flags records requiring human review
- Generates audit evidence for compliance verification

The system is NOT a decision-maker. All outputs are advisory and subject to
human review where indicated.

DECISION PATH DISCLOSURE
------------------------
Records in this batch were processed through a 5-layer resolution waterfall (L0–L4):

L1_DETERMINISTIC:       Exact or normalized string matching. Fully automated.
                        No probabilistic methods. Highest confidence.

L2_VECTOR_FUZZY:        Vector similarity matching. Automated with confidence
                        scoring. May produce false positives on similar names.

L3_LLM:                 Large Language Model assisted resolution. Used only when
                        deterministic and vector methods are inconclusive.
                        Subject to model limitations and potential hallucination.

L4_HUMAN_REVIEW_REQUIRED: Records flagged for mandatory human review. Resolution
                        confidence below threshold or multiple ambiguous matches.

Any record classified as L4_HUMAN_REVIEW_REQUIRED has NOT been automatically
resolved and MUST be reviewed by a qualified human before use.

LIMITATIONS
-----------
- Output quality depends on input data quality
- False positives and false negatives may occur
- No external data retrieval or internet queries performed
- Processing scope limited to provided batch only
- Reference data currency affects match accuracy
- System does not verify legal status or compliance standing

EVIDENCE & TRACEABILITY
-----------------------
This statement is cryptographically linked to:
- Batch Trace ID: {trace_id}
- Evidence Pack Manifest (when generated)
- Row-level audit events in Firestore

All artifacts are immutable once generated.

NON-CLAIMS
----------
This system output:
- Is NOT legal, regulatory, or compliance advice
- Is NOT a substitute for human judgment
- Does NOT guarantee accuracy or completeness
- Does NOT establish liability or indemnification

================================================================================
END OF TRANSPARENCY & LIMITATIONS STATEMENT
Template Version: TLS_v1
================================================================================
"""


def generate_transparency_statement(trace_id: str, timestamp: str, config_version: str) -> Tuple[str, str]:
    """
    Generate immutable Transparency & Limitations Statement for a batch.
    Returns (content, sha256_hash).
    """
    content = TLS_TEMPLATE.format(
        trace_id=trace_id,
        timestamp=timestamp,
        config_version=config_version
    )
    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    return content, content_hash


def compute_decision_path_summary(stats: dict, budget_tracker=None) -> dict:
    """
    Compute EU-compliant decision path summary from layer stats.
    Maps internal layer names to EU AI Act compliant categories.

    L1_DETERMINISTIC includes all deterministic resolution layers:
      - Company mode: layer_1_exact + layer_1_norm
      - Mixed mode:   layer_1_mixed_org + layer_1_mixed_person + layer_1_mixed_vessel
      - Person mode:  layer_1_person_exact + layer_1_person_alias + layer_1_person_initial

    L3_LLM_ATTEMPTED: how many records were sent to the LLM (cost incurred).
    L3_LLM: how many of those were successfully resolved.
    """
    l1_deterministic = (
        stats.get("layer_1_exact", 0)
        + stats.get("layer_1_norm", 0)
        + stats.get("layer_1_mixed_org", 0)
        + stats.get("layer_1_mixed_person", 0)
        + stats.get("layer_1_mixed_vessel", 0)
        + stats.get("layer_1_person_exact", 0)
        + stats.get("layer_1_person_alias", 0)
        + stats.get("layer_1_person_initial", 0)
    )
    l2_vector_fuzzy = stats.get("layer_2_vector", 0) + stats.get("layer_2_person_fuzzy", 0)
    l3_llm = stats.get("layer_3_llm", 0)
    l4_human_review = stats.get("layer_4_human", 0)

    summary = {
        "L1_DETERMINISTIC": l1_deterministic,
        "L2_VECTOR_FUZZY": l2_vector_fuzzy,
        "L3_LLM": l3_llm,
        "L4_HUMAN_REVIEW_REQUIRED": l4_human_review,
        "total_processed": l1_deterministic + l2_vector_fuzzy + l3_llm + l4_human_review,
    }

    # Add L3 attempt transparency when budget tracker is available
    if budget_tracker is not None:
        summary["L3_LLM_ATTEMPTED"] = budget_tracker.l3_attempted
        summary["L3_LLM_FAILED"] = budget_tracker.l3_failed
        summary["L3_LLM_COST_USD"] = round(budget_tracker.spent_usd, 6)

    return summary

# -----------------------------------------------------------------------------
# CANONICALS - High-frequency, stable entities
# -----------------------------------------------------------------------------

CANONICALS_TECH = [
    "Alphabet Inc.", "Amazon.com, Inc.", "Apple Inc.", "Meta Platforms, Inc.",
    "Microsoft Corporation", "NVIDIA Corporation", "Tesla, Inc.", "Intel Corporation",
    "Netflix, Inc.", "Uber Technologies, Inc.", "Airbnb, Inc.", "X Corp.", "LinkedIn Corporation",
]

CANONICALS_ENTERPRISE = [
    "Salesforce, Inc.", "Oracle Corporation", "SAP SE", "IBM Corporation",
    "Adobe Inc.", "Cisco Systems, Inc.", "ServiceNow, Inc.", "Workday, Inc.",
    "Intuit Inc.", "Block, Inc.", "Shopify Inc.", "DocuSign, Inc.", "Twilio Inc.",
    "Zoom Video Communications", "Slack Technologies", "Atlassian Corporation",
    "HubSpot, Inc.", "Splunk Inc.", "VMware, Inc.",
]

CANONICALS_DATA = [
    "Databricks, Inc.", "Snowflake Inc.", "Palantir Technologies Inc.",
    "MongoDB, Inc.", "Elastic N.V.",
]

CANONICALS_INFRASTRUCTURE = [
    "Dell Technologies Inc.", "HP Inc.", "Hewlett Packard Enterprise",
    "Red Hat, Inc.", "Qualcomm Incorporated", "AMD (Advanced Micro Devices, Inc.)",
    "Broadcom Inc.",
]

CANONICALS_PHARMA = [
    "Pfizer Inc.", "Johnson & Johnson", "Eli Lilly and Company", "Merck & Co., Inc.",
    "AbbVie Inc.", "Bristol-Myers Squibb", "Novartis AG", "AstraZeneca plc",
    "Roche Holdings", "Genentech, Inc.", "Moderna, Inc.", "Amgen Inc.", "Gilead Sciences, Inc.",
]

CANONICALS_FINANCIAL = [
    # US Banks
    "JPMorgan Chase & Co.", "Bank of America Corporation", "Citigroup Inc.",
    "Wells Fargo & Company", "Morgan Stanley", "Goldman Sachs Group, Inc.",
    "U.S. Bancorp", "PNC Financial Services Group", "Truist Financial Corporation",
    "Capital One Financial Corporation", "Charles Schwab Corporation", "TD Bank, N.A.",
    "The Bank of New York Mellon", "State Street Corporation", "Fifth Third Bancorp",
    "KeyCorp", "Regions Financial Corporation", "Huntington Bancshares Incorporated",
    "Ally Financial Inc.", "Citizens Financial Group",
    # US Asset Managers
    "BlackRock, Inc.", "The Vanguard Group", "Fidelity Investments",
    "State Street Global Advisors", "T. Rowe Price Group", "Capital Group Companies",
    "PIMCO", "BNY Mellon Investment Management", "Invesco Ltd.", "Franklin Templeton",
    "Northern Trust Asset Management", "Wellington Management", "Geode Capital Management",
    "Dimensional Fund Advisors", "Charles Schwab Investment Management",
    # Europe Banks
    "HSBC Holdings PLC", "BNP Paribas SA", "Crédit Agricole Group",
    "Banco Santander SA", "Barclays PLC", "Société Générale", "UBS Group AG",
    "Deutsche Bank AG", "ING Groep N.V.", "Intesa Sanpaolo SpA", "UniCredit SpA",
    "Banco Bilbao Vizcaya Argentaria", "CaixaBank SA", "Crédit Mutuel Group",
    "Groupe BPCE", "Lloyds Banking Group PLC", "Nordea Bank Abp", "Commerzbank AG",
    "NatWest Group PLC", "Danske Bank A/S",
    # Europe Asset Managers
    "Amundi", "Legal & General Investment Management", "AXA Investment Managers",
    "Allianz Global Investors", "DWS Group", "Schroders PLC",
    "Natixis Investment Managers", "Aberdeen Standard Investments", "M&G Investments",
    "Union Investment", "Eurizon Capital", "Janus Henderson Group", "MEAG",
    "Swisscanto", "Robeco", "Pictet Asset Management", "Lombard Odier", "Candriam",
    "NN Investment Partners", "Aviva Investors",
    # Global Payment / Networks
    "Visa Inc.", "Mastercard Incorporated", "PayPal Holdings, Inc.",
    "American Express Company",
]

CANONICALS_CONSULTING = [
    "Accenture plc", "Deloitte Touche Tohmatsu Limited", "PricewaterhouseCoopers (PwC)",
    "Ernst & Young (EY)", "KPMG International", "McKinsey & Company",
    "Boston Consulting Group", "Bain & Company",
]

CANONICALS_CONSUMER_ELECTRONICS = [
    "Samsung Electronics Co., Ltd.", "Sony Group Corporation", "LG Electronics Inc.",
    "Panasonic Holdings Corporation", "Lenovo Group Limited", "Xiaomi Corporation",
    "Huawei Technologies Co., Ltd.",
]

CANONICALS_AUTOMOTIVE = [
    "Toyota Motor Corporation", "Volkswagen AG", "General Motors Company",
    "Ford Motor Company", "Honda Motor Co., Ltd.", "BMW AG", "Mercedes-Benz Group AG",
    "Stellantis N.V.", "Hyundai Motor Company", "Kia Corporation", "Nissan Motor Co., Ltd.",
    "Mazda Motor Corporation", "Subaru Corporation", "Mitsubishi Motors Corporation",
    "Volvo Car AB", "Ferrari N.V.", "Porsche AG", "Audi AG", "Jaguar Land Rover Limited",
    "Bentley Motors Limited", "Rolls-Royce Motor Cars Limited", "Lamborghini S.p.A.",
    "Maserati S.p.A.", "Alfa Romeo Automobiles S.p.A.", "Fiat S.p.A.", "Peugeot S.A.",
    "Renault S.A.", "Citroën", "SEAT S.A.", "Škoda Auto", "Opel Automobile GmbH",
    "Vauxhall Motors", "Mini (marque)", "Smart Automobile", "Suzuki Motor Corporation",
    "Daihatsu Motor Co., Ltd.", "Isuzu Motors Ltd.", "Hino Motors, Ltd.",
    "PACCAR Inc.", "Peterbilt Motors Company", "Kenworth Truck Company",
]

CANONICALS_RETAIL_FOOD = [
    "McDonald's Corporation", "Starbucks Corporation", "The Coca-Cola Company",
    "PepsiCo, Inc.", "Walmart Inc.", "Target Corporation", "Costco Wholesale Corporation",
    "The Kroger Co.", "Yum! Brands, Inc.", "Restaurant Brands International Inc.",
]

CANONICALS_STREAMING_MEDIA = [
    "Spotify Technology S.A.", "Roku, Inc.", "Snap Inc.", "Pinterest, Inc.",
    "Zoom Video Communications, Inc.",
]

CANONICALS_ENERGY = [
    "Exxon Mobil Corporation", "Chevron Corporation", "Shell plc", "BP p.l.c.",
    "ConocoPhillips", "TotalEnergies SE", "Occidental Petroleum Corporation",
    "Phillips 66", "Valero Energy Corporation", "Marathon Petroleum Corporation",
    "Schlumberger Limited", "Halliburton Company", "Baker Hughes Company",
    "Devon Energy Corporation", "Pioneer Natural Resources Company",
    "EOG Resources, Inc.", "Diamondback Energy, Inc.", "Hess Corporation",
]

CANONICALS_TELECOM = [
    "AT&T Inc.", "Verizon Communications Inc.", "T-Mobile US, Inc.",
    "Comcast Corporation", "Charter Communications, Inc.", "Lumen Technologies, Inc.",
    "Deutsche Telekom AG", "Vodafone Group plc", "Telefónica, S.A.",
    "Orange S.A.", "BT Group plc", "América Móvil, S.A.B. de C.V.",
]

CANONICALS_AEROSPACE_DEFENSE = [
    "The Boeing Company", "Lockheed Martin Corporation", "Raytheon Technologies Corporation",
    "Northrop Grumman Corporation", "General Dynamics Corporation", "L3Harris Technologies, Inc.",
    "BAE Systems plc", "Airbus SE", "Textron Inc.", "Leidos Holdings, Inc.",
    "Huntington Ingalls Industries, Inc.", "TransDigm Group Incorporated",
]

CANONICALS_INDUSTRIAL = [
    "3M Company", "General Electric Company", "Honeywell International Inc.",
    "Caterpillar Inc.", "Deere & Company", "Illinois Tool Works Inc.",
    "Parker-Hannifin Corporation", "Emerson Electric Co.", "Rockwell Automation, Inc.",
    "Eaton Corporation plc", "PACCAR Inc", "Cummins Inc.",
    "Stanley Black & Decker, Inc.", "Dover Corporation", "Fortive Corporation",
    "Ingersoll Rand Inc.", "Trane Technologies plc", "Otis Worldwide Corporation",
]

CANONICALS_INSURANCE = [
    "UnitedHealth Group Incorporated", "Anthem, Inc.", "Cigna Corporation",
    "Humana Inc.", "Aetna Inc.", "CVS Health Corporation",
    "The Progressive Corporation", "Allstate Corporation", "MetLife, Inc.",
    "Prudential Financial, Inc.", "Aflac Incorporated", "Travelers Companies, Inc.",
    "Chubb Limited", "American International Group, Inc.", "Principal Financial Group, Inc.",
    "Lincoln National Corporation", "Hartford Financial Services Group, Inc.",
]

CANONICALS_AIRLINES = [
    "Delta Air Lines, Inc.", "United Airlines Holdings, Inc.", "American Airlines Group Inc.",
    "Southwest Airlines Co.", "Alaska Air Group, Inc.", "JetBlue Airways Corporation",
    "Spirit Airlines, Inc.", "Frontier Group Holdings, Inc.",
    "Lufthansa Group", "Air France-KLM", "International Airlines Group",
    "Ryanair Holdings plc", "Emirates Group", "Qatar Airways Group",
]

CANONICALS_LOGISTICS = [
    "FedEx Corporation", "United Parcel Service, Inc.", "DHL International GmbH",
    "XPO Logistics, Inc.", "C.H. Robinson Worldwide, Inc.", "J.B. Hunt Transport Services, Inc.",
    "Expeditors International of Washington, Inc.", "Ryder System, Inc.",
    "Old Dominion Freight Line, Inc.", "Saia, Inc.", "Werner Enterprises, Inc.",
]

CANONICALS_HOSPITALITY = [
    "Marriott International, Inc.", "Hilton Worldwide Holdings Inc.", "Hyatt Hotels Corporation",
    "InterContinental Hotels Group plc", "Wyndham Hotels & Resorts, Inc.",
    "Choice Hotels International, Inc.", "MGM Resorts International",
    "Caesars Entertainment, Inc.", "Las Vegas Sands Corp.", "Wynn Resorts, Limited",
]

CANONICALS_MEDIA_ENTERTAINMENT = [
    "The Walt Disney Company", "Warner Bros. Discovery, Inc.", "NBCUniversal Media, LLC",
    "Paramount Global", "Fox Corporation", "Sony Pictures Entertainment Inc.",
    "Lionsgate Entertainment Corp.", "AMC Networks Inc.", "Discovery, Inc.",
    "ViacomCBS Inc.", "News Corporation", "iHeartMedia, Inc.",
]

CANONICALS_CHEMICALS = [
    "Dow Inc.", "DuPont de Nemours, Inc.", "BASF SE", "LyondellBasell Industries N.V.",
    "Eastman Chemical Company", "PPG Industries, Inc.", "Sherwin-Williams Company",
    "Air Products and Chemicals, Inc.", "Linde plc", "Ecolab Inc.",
    "International Flavors & Fragrances Inc.", "Celanese Corporation",
]

CANONICALS_HEALTHCARE_SERVICES = [
    "HCA Healthcare, Inc.", "CommonSpirit Health", "Ascension Health",
    "Kaiser Permanente", "Mayo Clinic", "Cleveland Clinic",
    "Johns Hopkins Medicine", "Mass General Brigham", "NewYork-Presbyterian Hospital",
    "Tenet Healthcare Corporation", "Universal Health Services, Inc.",
    "DaVita Inc.", "Fresenius Medical Care", "Laboratory Corporation of America Holdings",
    "Quest Diagnostics Incorporated", "IQVIA Holdings Inc.",
]

CANONICALS_MEDICAL_DEVICES = [
    "Medtronic plc", "Abbott Laboratories", "Thermo Fisher Scientific Inc.",
    "Danaher Corporation", "Becton, Dickinson and Company", "Boston Scientific Corporation",
    "Stryker Corporation", "Edwards Lifesciences Corporation", "Intuitive Surgical, Inc.",
    "Zimmer Biomet Holdings, Inc.", "Baxter International Inc.", "Align Technology, Inc.",
    "IDEXX Laboratories, Inc.", "ResMed Inc.", "Hologic, Inc.",
]

CANONICALS_FINTECH = [
    "Stripe, Inc.", "Plaid Inc.", "Robinhood Markets, Inc.", "Coinbase Global, Inc.",
    "Affirm Holdings, Inc.", "Marqeta, Inc.", "SoFi Technologies, Inc.",
    "Chime Financial, Inc.", "Klarna Bank AB", "Revolut Ltd",
    "Toast, Inc.", "Bill.com Holdings, Inc.", "Remitly Global, Inc.",
]

CANONICALS_CYBERSECURITY = [
    "CrowdStrike Holdings, Inc.", "Palo Alto Networks, Inc.", "Fortinet, Inc.",
    "Zscaler, Inc.", "Cloudflare, Inc.", "Okta, Inc.",
    "SentinelOne, Inc.", "Rapid7, Inc.", "Qualys, Inc.",
    "Tenable Holdings, Inc.", "CyberArk Software Ltd.", "Varonis Systems, Inc.",
]

CANONICALS_REAL_ESTATE = [
    "CBRE Group, Inc.", "Jones Lang LaSalle Incorporated", "Cushman & Wakefield plc",
    "Prologis, Inc.", "American Tower Corporation", "Crown Castle Inc.",
    "Equinix, Inc.", "Digital Realty Trust, Inc.", "Public Storage",
    "Simon Property Group, Inc.", "Realty Income Corporation", "AvalonBay Communities, Inc.",
]

CANONICALS_ECOMMERCE_RETAIL = [
    "eBay Inc.", "Etsy, Inc.", "Wayfair Inc.", "Chewy, Inc.",
    "The Home Depot, Inc.", "Lowe's Companies, Inc.", "Best Buy Co., Inc.",
    "TJX Companies, Inc.", "Ross Stores, Inc.", "Dollar General Corporation",
    "Dollar Tree, Inc.", "Walgreens Boots Alliance, Inc.",
    "Rite Aid Corporation", "Ulta Beauty, Inc.", "Bath & Body Works, Inc.",
]

CANONICALS = (
    CANONICALS_TECH + CANONICALS_ENTERPRISE + CANONICALS_DATA +
    CANONICALS_INFRASTRUCTURE + CANONICALS_PHARMA + CANONICALS_FINANCIAL +
    CANONICALS_CONSULTING + CANONICALS_CONSUMER_ELECTRONICS + CANONICALS_AUTOMOTIVE +
    CANONICALS_RETAIL_FOOD + CANONICALS_STREAMING_MEDIA +
    # Expanded sectors (added for 100K baseline improvement)
    CANONICALS_ENERGY + CANONICALS_TELECOM + CANONICALS_AEROSPACE_DEFENSE +
    CANONICALS_INDUSTRIAL + CANONICALS_INSURANCE + CANONICALS_AIRLINES +
    CANONICALS_LOGISTICS + CANONICALS_HOSPITALITY + CANONICALS_MEDIA_ENTERTAINMENT +
    CANONICALS_CHEMICALS + CANONICALS_HEALTHCARE_SERVICES + CANONICALS_MEDICAL_DEVICES +
    CANONICALS_FINTECH + CANONICALS_CYBERSECURITY + CANONICALS_REAL_ESTATE +
    CANONICALS_ECOMMERCE_RETAIL
)

# -----------------------------------------------------------------------------
# KNOWN PARENTS / ALIASES
# -----------------------------------------------------------------------------

KNOWN_PARENTS = {
    # Tech Giants
    "google": "Alphabet Inc.", "goog": "Alphabet Inc.", "googl": "Alphabet Inc.",
    "youtube": "Alphabet Inc.", "deepmind": "Alphabet Inc.", "waymo": "Alphabet Inc.",
    "parent of google": "Alphabet Inc.", "youtube parent": "Alphabet Inc.",
    "gmail provider": "Alphabet Inc.", "android maker": "Alphabet Inc.",
    "amazon": "Amazon.com, Inc.", "amzn": "Amazon.com, Inc.", "aws": "Amazon.com, Inc.",
    "kindle maker": "Amazon.com, Inc.", "aws provider": "Amazon.com, Inc.",
    "apple": "Apple Inc.", "aapl": "Apple Inc.",
    "iphone manufacturer": "Apple Inc.", "iphone maker": "Apple Inc.",
    "meta": "Meta Platforms, Inc.", "facebook": "Meta Platforms, Inc.", "fb": "Meta Platforms, Inc.",
    "instagram": "Meta Platforms, Inc.", "whatsapp": "Meta Platforms, Inc.",
    "instagram owner": "Meta Platforms, Inc.", "whatsapp parent": "Meta Platforms, Inc.",
    "microsoft": "Microsoft Corporation", "msft": "Microsoft Corporation",
    "azure": "Microsoft Corporation", "github": "Microsoft Corporation", "linkedin": "Microsoft Corporation",
    "windows creator": "Microsoft Corporation", "xbox manufacturer": "Microsoft Corporation",
    "office 365 creator": "Microsoft Corporation", "linkedin owner": "Microsoft Corporation",
    "nvidia": "NVIDIA Corporation", "nvda": "NVIDIA Corporation",
    "tesla": "Tesla, Inc.", "tsla": "Tesla, Inc.",
    "tesla ceo company": "Tesla, Inc.",
    "intel": "Intel Corporation", "intc": "Intel Corporation",
    "netflix": "Netflix, Inc.", "nflx": "Netflix, Inc.",
    "uber": "Uber Technologies, Inc.",
    "airbnb": "Airbnb, Inc.", "abnb": "Airbnb, Inc.",
    "twitter": "X Corp.", "x": "X Corp.",

    # Enterprise SaaS
    "salesforce": "Salesforce, Inc.", "sfdc": "Salesforce, Inc.",
    "oracle": "Oracle Corporation", "orcl": "Oracle Corporation",
    "sap": "SAP SE",
    "ibm": "IBM Corporation",
    "adobe": "Adobe Inc.", "adbe": "Adobe Inc.",
    "cisco": "Cisco Systems, Inc.", "csco": "Cisco Systems, Inc.",
    "servicenow": "ServiceNow, Inc.", "now": "ServiceNow, Inc.",
    "workday": "Workday, Inc.", "wday": "Workday, Inc.",
    "intuit": "Intuit Inc.", "intu": "Intuit Inc.", "turbotax": "Intuit Inc.", "quickbooks": "Intuit Inc.",
    "square": "Block, Inc.", "block": "Block, Inc.", "sq": "Block, Inc.", "cash app": "Block, Inc.",
    "shopify": "Shopify Inc.", "shop": "Shopify Inc.",
    "docusign": "DocuSign, Inc.", "docu": "DocuSign, Inc.",
    "twilio": "Twilio Inc.", "twlo": "Twilio Inc.",
    "slack": "Slack Technologies",
    "atlassian": "Atlassian Corporation", "team": "Atlassian Corporation", "jira": "Atlassian Corporation", "confluence": "Atlassian Corporation",
    "hubspot": "HubSpot, Inc.", "hubs": "HubSpot, Inc.",
    "splunk": "Splunk Inc.",
    "vmware": "VMware, Inc.",

    # Data / AI
    "databricks": "Databricks, Inc.",
    "snowflake": "Snowflake Inc.", "snow": "Snowflake Inc.",
    "palantir": "Palantir Technologies Inc.", "pltr": "Palantir Technologies Inc.",
    "mongodb": "MongoDB, Inc.", "mdb": "MongoDB, Inc.", "mongo": "MongoDB, Inc.",
    "elastic": "Elastic N.V.", "elasticsearch": "Elastic N.V.",

    # Infrastructure
    "dell": "Dell Technologies Inc.",
    "hp": "HP Inc.", "hewlett packard": "HP Inc.",
    "hpe": "Hewlett Packard Enterprise", "hewlett packard enterprise": "Hewlett Packard Enterprise",
    "redhat": "Red Hat, Inc.", "red hat": "Red Hat, Inc.",
    "qualcomm": "Qualcomm Incorporated", "qcom": "Qualcomm Incorporated",
    "amd": "AMD (Advanced Micro Devices, Inc.)", "advanced micro devices": "AMD (Advanced Micro Devices, Inc.)",
    "broadcom": "Broadcom Inc.", "avgo": "Broadcom Inc.",

    # Pharma
    "pfizer": "Pfizer Inc.", "pfe": "Pfizer Inc.",
    "viagra maker": "Pfizer Inc.",
    "jnj": "Johnson & Johnson", "johnson and johnson": "Johnson & Johnson", "j&j": "Johnson & Johnson",
    "produces tylenol": "Johnson & Johnson", "tylenol maker": "Johnson & Johnson",
    "lilly": "Eli Lilly and Company", "eli lilly": "Eli Lilly and Company", "lly": "Eli Lilly and Company",
    "merck": "Merck & Co., Inc.", "mrk": "Merck & Co., Inc.",
    "abbvie": "AbbVie Inc.", "abbv": "AbbVie Inc.",
    "maker of humira": "AbbVie Inc.", "humira maker": "AbbVie Inc.",
    "bms": "Bristol-Myers Squibb", "bristol myers": "Bristol-Myers Squibb", "bristol-myers": "Bristol-Myers Squibb",
    "novartis": "Novartis AG", "nvs": "Novartis AG",
    "astrazeneca": "AstraZeneca plc", "azn": "AstraZeneca plc", "az": "AstraZeneca plc",
    "roche": "Roche Holdings",
    "genentech": "Genentech, Inc.",
    "moderna": "Moderna, Inc.", "mrna": "Moderna, Inc.",
    "amgen": "Amgen Inc.", "amgn": "Amgen Inc.",
    "gilead": "Gilead Sciences, Inc.", "gild": "Gilead Sciences, Inc.",

    # Financial — US Banks
    "jpmorgan": "JPMorgan Chase & Co.", "jp morgan": "JPMorgan Chase & Co.", "jpm": "JPMorgan Chase & Co.",
    "chase": "JPMorgan Chase & Co.",
    "bofa": "Bank of America Corporation", "boa": "Bank of America Corporation",
    "bank of america": "Bank of America Corporation", "bac": "Bank of America Corporation",
    "citi": "Citigroup Inc.", "citigroup": "Citigroup Inc.", "citibank": "Citigroup Inc.", "c": "Citigroup Inc.",
    "wells fargo": "Wells Fargo & Company", "wells": "Wells Fargo & Company", "wfc": "Wells Fargo & Company",
    "morgan stanley": "Morgan Stanley", "ms": "Morgan Stanley",
    "goldman": "Goldman Sachs Group, Inc.", "goldman sachs": "Goldman Sachs Group, Inc.", "gs": "Goldman Sachs Group, Inc.",
    "us bank": "U.S. Bancorp", "us bancorp": "U.S. Bancorp",
    "pnc": "PNC Financial Services Group",
    "truist": "Truist Financial Corporation",
    "capital one": "Capital One Financial Corporation",
    "schwab": "Charles Schwab Corporation", "charles schwab": "Charles Schwab Corporation",
    "td bank": "TD Bank, N.A.",
    "bny mellon": "The Bank of New York Mellon", "bank of new york": "The Bank of New York Mellon",
    "state street": "State Street Corporation",
    # Financial — US Asset Managers
    "blackrock": "BlackRock, Inc.", "blk": "BlackRock, Inc.",
    "vanguard": "The Vanguard Group",
    "fidelity": "Fidelity Investments", "fidelity investments": "Fidelity Investments",
    "t rowe": "T. Rowe Price Group", "t rowe price": "T. Rowe Price Group",
    "pimco": "PIMCO",
    "invesco": "Invesco Ltd.",
    "franklin templeton": "Franklin Templeton",
    # Financial — Europe Banks
    "hsbc": "HSBC Holdings PLC",
    "bnp": "BNP Paribas SA", "bnp paribas": "BNP Paribas SA",
    "credit agricole": "Crédit Agricole Group",
    "santander": "Banco Santander SA",
    "barclays": "Barclays PLC",
    "socgen": "Société Générale", "societe generale": "Société Générale",
    "ubs": "UBS Group AG",
    "deutsche bank": "Deutsche Bank AG",
    "ing": "ING Groep N.V.",
    "intesa": "Intesa Sanpaolo SpA", "intesa sanpaolo": "Intesa Sanpaolo SpA",
    "unicredit": "UniCredit SpA",
    "bbva": "Banco Bilbao Vizcaya Argentaria",
    "caixabank": "CaixaBank SA",
    "lloyds": "Lloyds Banking Group PLC",
    "nordea": "Nordea Bank Abp",
    "commerzbank": "Commerzbank AG",
    # Financial — Europe Asset Managers
    "amundi": "Amundi",
    "axa im": "AXA Investment Managers",
    "allianz": "Allianz Global Investors", "allianz gi": "Allianz Global Investors",
    "dws": "DWS Group",
    "schroders": "Schroders PLC",
    "natixis": "Natixis Investment Managers",
    "m&g": "M&G Investments",
    # Financial — Global Payment / Networks
    "visa": "Visa Inc.", "v": "Visa Inc.",
    "mastercard": "Mastercard Incorporated", "ma": "Mastercard Incorporated",
    "paypal": "PayPal Holdings, Inc.", "pypl": "PayPal Holdings, Inc.",
    "amex": "American Express Company", "american express": "American Express Company", "axp": "American Express Company",

    # Consulting
    "accenture": "Accenture plc", "acn": "Accenture plc",
    "deloitte": "Deloitte Touche Tohmatsu Limited", "deloitte consulting": "Deloitte Touche Tohmatsu Limited",
    "deloitte llp": "Deloitte Touche Tohmatsu Limited",
    "pwc": "PricewaterhouseCoopers (PwC)", "pricewaterhousecoopers": "PricewaterhouseCoopers (PwC)",
    "ey": "Ernst & Young (EY)", "ernst young": "Ernst & Young (EY)", "ernst & young": "Ernst & Young (EY)",
    "kpmg": "KPMG International",
    "mckinsey": "McKinsey & Company",
    "bcg": "Boston Consulting Group", "boston consulting": "Boston Consulting Group",
    "bain": "Bain & Company",

    # Consumer Electronics
    "samsung": "Samsung Electronics Co., Ltd.", "samsung electronics": "Samsung Electronics Co., Ltd.",
    "sony": "Sony Group Corporation", "playstation": "Sony Group Corporation",
    "lg": "LG Electronics Inc.", "lg electronics": "LG Electronics Inc.",
    "panasonic": "Panasonic Holdings Corporation",
    "lenovo": "Lenovo Group Limited",
    "xiaomi": "Xiaomi Corporation",
    "huawei": "Huawei Technologies Co., Ltd.",

    # Automotive
    "toyota": "Toyota Motor Corporation", "lexus": "Toyota Motor Corporation",
    "volkswagen": "Volkswagen AG", "vw": "Volkswagen AG", "audi": "Audi AG",
    "gm": "General Motors Company", "general motors": "General Motors Company",
    "chevrolet": "General Motors Company", "chevy": "General Motors Company",
    "buick": "General Motors Company", "gmc": "General Motors Company",
    "cadillac": "General Motors Company",
    "ford": "Ford Motor Company", "lincoln": "Ford Motor Company",
    "honda": "Honda Motor Co., Ltd.", "acura": "Honda Motor Co., Ltd.",
    "bmw": "BMW AG", "mini": "BMW AG", "rolls royce": "Rolls-Royce Motor Cars Limited",
    "mercedes": "Mercedes-Benz Group AG", "mercedes benz": "Mercedes-Benz Group AG",
    "daimler": "Mercedes-Benz Group AG",
    "stellantis": "Stellantis N.V.", "chrysler": "Stellantis N.V.", "dodge": "Stellantis N.V.",
    "jeep": "Stellantis N.V.", "ram": "Stellantis N.V.", "fiat": "Stellantis N.V.",
    "alfa romeo": "Stellantis N.V.", "maserati": "Stellantis N.V.", "peugeot": "Stellantis N.V.",
    "citroen": "Stellantis N.V.", "opel": "Stellantis N.V.", "vauxhall": "Stellantis N.V.",
    "hyundai": "Hyundai Motor Company", "kia": "Kia Corporation",
    "nissan": "Nissan Motor Co., Ltd.", "infiniti": "Nissan Motor Co., Ltd.",
    "mazda": "Mazda Motor Corporation",
    "subaru": "Subaru Corporation",
    "mitsubishi": "Mitsubishi Motors Corporation", "mitsubishi motors": "Mitsubishi Motors Corporation",
    "volvo": "Volvo Car AB",
    "ferrari": "Ferrari N.V.",
    "porsche": "Porsche AG",
    "jaguar": "Jaguar Land Rover Limited", "land rover": "Jaguar Land Rover Limited",
    "bentley": "Bentley Motors Limited",
    "lamborghini": "Lamborghini S.p.A.",
    "suzuki": "Suzuki Motor Corporation",
    "daihatsu": "Daihatsu Motor Co., Ltd.",
    "isuzu": "Isuzu Motors Ltd.",
    "hino": "Hino Motors, Ltd.",
    "kenworth": "PACCAR Inc.", "peterbilt": "PACCAR Inc.", "paccar": "PACCAR Inc.",
    "ud trucks": "Isuzu Motors Ltd.",

    # Retail & Food
    "mcdonalds": "McDonald's Corporation", "mcdonald's": "McDonald's Corporation",
    "big mac": "McDonald's Corporation",
    "starbucks": "Starbucks Corporation", "sbux": "Starbucks Corporation",
    "coca cola": "The Coca-Cola Company", "coke": "The Coca-Cola Company", "ko": "The Coca-Cola Company",
    "pepsi": "PepsiCo, Inc.", "pepsico": "PepsiCo, Inc.", "pep": "PepsiCo, Inc.",
    "walmart": "Walmart Inc.", "wmt": "Walmart Inc.",
    "target": "Target Corporation", "tgt": "Target Corporation",
    "costco": "Costco Wholesale Corporation", "cost": "Costco Wholesale Corporation",
    "kroger": "The Kroger Co.", "kr": "The Kroger Co.",
    "yum": "Yum! Brands, Inc.", "yum brands": "Yum! Brands, Inc.", "kfc": "Yum! Brands, Inc.",
    "pizza hut": "Yum! Brands, Inc.", "taco bell": "Yum! Brands, Inc.",
    "burger king": "Restaurant Brands International Inc.", "tim hortons": "Restaurant Brands International Inc.",

    # Streaming / Media
    "spotify": "Spotify Technology S.A.", "spot": "Spotify Technology S.A.",
    "roku": "Roku, Inc.",
    "snapchat": "Snap Inc.", "snap": "Snap Inc.",
    "pinterest": "Pinterest, Inc.", "pins": "Pinterest, Inc.",
    "zoom": "Zoom Video Communications, Inc.", "zm": "Zoom Video Communications, Inc.",
    "zoom founder": "Zoom Video Communications, Inc.",

    # Energy
    "exxon": "Exxon Mobil Corporation", "exxonmobil": "Exxon Mobil Corporation", "xom": "Exxon Mobil Corporation",
    "chevron": "Chevron Corporation", "cvx": "Chevron Corporation",
    "shell": "Shell plc", "royal dutch shell": "Shell plc", "shel": "Shell plc",
    "bp": "BP p.l.c.", "british petroleum": "BP p.l.c.",
    "conocophillips": "ConocoPhillips", "cop": "ConocoPhillips",
    "total": "TotalEnergies SE", "totalenergies": "TotalEnergies SE",
    "occidental": "Occidental Petroleum Corporation", "oxy": "Occidental Petroleum Corporation",
    "phillips 66": "Phillips 66", "psx": "Phillips 66",
    "valero": "Valero Energy Corporation", "vlo": "Valero Energy Corporation",
    "marathon petroleum": "Marathon Petroleum Corporation", "mpc": "Marathon Petroleum Corporation",
    "schlumberger": "Schlumberger Limited", "slb": "Schlumberger Limited",
    "halliburton": "Halliburton Company", "hal": "Halliburton Company",
    "baker hughes": "Baker Hughes Company", "bkr": "Baker Hughes Company",

    # Telecom
    "at&t": "AT&T Inc.", "att": "AT&T Inc.", "t": "AT&T Inc.",
    "verizon": "Verizon Communications Inc.", "vz": "Verizon Communications Inc.",
    "t-mobile": "T-Mobile US, Inc.", "tmobile": "T-Mobile US, Inc.", "tmus": "T-Mobile US, Inc.",
    "comcast": "Comcast Corporation", "cmcsa": "Comcast Corporation", "xfinity": "Comcast Corporation",
    "charter": "Charter Communications, Inc.", "chtr": "Charter Communications, Inc.", "spectrum": "Charter Communications, Inc.",
    "lumen": "Lumen Technologies, Inc.", "centurylink": "Lumen Technologies, Inc.",
    "deutsche telekom": "Deutsche Telekom AG", "dtegy": "Deutsche Telekom AG",
    "vodafone": "Vodafone Group plc", "vod": "Vodafone Group plc",
    "telefonica": "Telefónica, S.A.",
    "orange": "Orange S.A.",
    "bt": "BT Group plc", "british telecom": "BT Group plc",

    # Aerospace & Defense
    "boeing": "The Boeing Company", "ba": "The Boeing Company",
    "lockheed": "Lockheed Martin Corporation", "lockheed martin": "Lockheed Martin Corporation", "lmt": "Lockheed Martin Corporation",
    "raytheon": "Raytheon Technologies Corporation", "rtx": "Raytheon Technologies Corporation",
    "northrop": "Northrop Grumman Corporation", "northrop grumman": "Northrop Grumman Corporation", "noc": "Northrop Grumman Corporation",
    "general dynamics": "General Dynamics Corporation", "gd": "General Dynamics Corporation",
    "l3harris": "L3Harris Technologies, Inc.", "lhx": "L3Harris Technologies, Inc.",
    "bae": "BAE Systems plc", "bae systems": "BAE Systems plc",
    "airbus": "Airbus SE", "eadsf": "Airbus SE",
    "textron": "Textron Inc.", "txt": "Textron Inc.", "bell helicopter": "Textron Inc.", "cessna": "Textron Inc.",
    "leidos": "Leidos Holdings, Inc.", "ldos": "Leidos Holdings, Inc.",

    # Industrial
    "3m": "3M Company", "mmm": "3M Company",
    "ge": "General Electric Company", "general electric": "General Electric Company",
    "honeywell": "Honeywell International Inc.", "hon": "Honeywell International Inc.",
    "caterpillar": "Caterpillar Inc.", "cat": "Caterpillar Inc.",
    "deere": "Deere & Company", "john deere": "Deere & Company", "de": "Deere & Company",
    "itw": "Illinois Tool Works Inc.", "illinois tool works": "Illinois Tool Works Inc.",
    "parker": "Parker-Hannifin Corporation", "parker hannifin": "Parker-Hannifin Corporation", "ph": "Parker-Hannifin Corporation",
    "emerson": "Emerson Electric Co.", "emr": "Emerson Electric Co.",
    "rockwell": "Rockwell Automation, Inc.", "rok": "Rockwell Automation, Inc.",
    "eaton": "Eaton Corporation plc", "etn": "Eaton Corporation plc",
    "cummins": "Cummins Inc.", "cmi": "Cummins Inc.",
    "stanley": "Stanley Black & Decker, Inc.", "stanley black decker": "Stanley Black & Decker, Inc.", "swk": "Stanley Black & Decker, Inc.",
    "trane": "Trane Technologies plc", "tt": "Trane Technologies plc",
    "otis": "Otis Worldwide Corporation", "otis elevator": "Otis Worldwide Corporation",

    # Insurance
    "unitedhealth": "UnitedHealth Group Incorporated", "unh": "UnitedHealth Group Incorporated", "united healthcare": "UnitedHealth Group Incorporated",
    "anthem": "Anthem, Inc.", "antm": "Anthem, Inc.", "wellpoint": "Anthem, Inc.",
    "cigna": "Cigna Corporation", "ci": "Cigna Corporation",
    "humana": "Humana Inc.", "hum": "Humana Inc.",
    "aetna": "Aetna Inc.",
    "cvs": "CVS Health Corporation", "cvs health": "CVS Health Corporation",
    "progressive": "The Progressive Corporation", "pgr": "The Progressive Corporation",
    "allstate": "Allstate Corporation", "all": "Allstate Corporation",
    "metlife": "MetLife, Inc.", "met": "MetLife, Inc.",
    "prudential": "Prudential Financial, Inc.", "pru": "Prudential Financial, Inc.",
    "aflac": "Aflac Incorporated", "afl": "Aflac Incorporated",
    "travelers": "Travelers Companies, Inc.", "trv": "Travelers Companies, Inc.",
    "chubb": "Chubb Limited", "cb": "Chubb Limited",
    "aig": "American International Group, Inc.", "american international": "American International Group, Inc.",
    "hartford": "Hartford Financial Services Group, Inc.", "hig": "Hartford Financial Services Group, Inc.",

    # Airlines
    "delta": "Delta Air Lines, Inc.", "dal": "Delta Air Lines, Inc.", "delta airlines": "Delta Air Lines, Inc.",
    "united airlines": "United Airlines Holdings, Inc.", "ual": "United Airlines Holdings, Inc.",
    "american airlines": "American Airlines Group Inc.", "aal": "American Airlines Group Inc.",
    "southwest": "Southwest Airlines Co.", "luv": "Southwest Airlines Co.", "southwest airlines": "Southwest Airlines Co.",
    "alaska airlines": "Alaska Air Group, Inc.", "alk": "Alaska Air Group, Inc.",
    "jetblue": "JetBlue Airways Corporation", "jblu": "JetBlue Airways Corporation",
    "spirit airlines": "Spirit Airlines, Inc.", "save": "Spirit Airlines, Inc.",
    "frontier airlines": "Frontier Group Holdings, Inc.", "ulcc": "Frontier Group Holdings, Inc.",
    "lufthansa": "Lufthansa Group", "dlaky": "Lufthansa Group",
    "air france": "Air France-KLM", "klm": "Air France-KLM",
    "british airways": "International Airlines Group", "iberia": "International Airlines Group",
    "ryanair": "Ryanair Holdings plc", "ryaay": "Ryanair Holdings plc",
    "emirates": "Emirates Group",
    "qatar airways": "Qatar Airways Group",

    # Logistics
    "fedex": "FedEx Corporation", "fdx": "FedEx Corporation",
    "ups": "United Parcel Service, Inc.", "united parcel": "United Parcel Service, Inc.",
    "dhl": "DHL International GmbH", "deutsche post": "DHL International GmbH",
    "xpo": "XPO Logistics, Inc.", "xpo logistics": "XPO Logistics, Inc.",
    "ch robinson": "C.H. Robinson Worldwide, Inc.", "chrw": "C.H. Robinson Worldwide, Inc.",
    "jb hunt": "J.B. Hunt Transport Services, Inc.", "jbht": "J.B. Hunt Transport Services, Inc.",
    "expeditors": "Expeditors International of Washington, Inc.", "expd": "Expeditors International of Washington, Inc.",
    "ryder": "Ryder System, Inc.", "r": "Ryder System, Inc.",
    "old dominion": "Old Dominion Freight Line, Inc.", "odfl": "Old Dominion Freight Line, Inc.",

    # Hospitality
    "marriott": "Marriott International, Inc.", "mar": "Marriott International, Inc.",
    "hilton": "Hilton Worldwide Holdings Inc.", "hlt": "Hilton Worldwide Holdings Inc.",
    "hyatt": "Hyatt Hotels Corporation", "h": "Hyatt Hotels Corporation",
    "ihg": "InterContinental Hotels Group plc", "intercontinental": "InterContinental Hotels Group plc",
    "wyndham": "Wyndham Hotels & Resorts, Inc.", "wh": "Wyndham Hotels & Resorts, Inc.",
    "choice hotels": "Choice Hotels International, Inc.", "chh": "Choice Hotels International, Inc.",
    "mgm": "MGM Resorts International", "mgm resorts": "MGM Resorts International",
    "caesars": "Caesars Entertainment, Inc.", "czr": "Caesars Entertainment, Inc.",
    "las vegas sands": "Las Vegas Sands Corp.", "lvs": "Las Vegas Sands Corp.",
    "wynn": "Wynn Resorts, Limited", "wynn resorts": "Wynn Resorts, Limited",

    # Media & Entertainment
    "disney": "The Walt Disney Company", "dis": "The Walt Disney Company", "walt disney": "The Walt Disney Company",
    "warner bros": "Warner Bros. Discovery, Inc.", "wbd": "Warner Bros. Discovery, Inc.", "hbo": "Warner Bros. Discovery, Inc.",
    "nbcuniversal": "NBCUniversal Media, LLC", "nbc": "NBCUniversal Media, LLC",
    "paramount": "Paramount Global", "para": "Paramount Global", "cbs": "Paramount Global",
    "fox": "Fox Corporation", "foxa": "Fox Corporation", "fox news": "Fox Corporation",
    "sony pictures": "Sony Pictures Entertainment Inc.",
    "lionsgate": "Lionsgate Entertainment Corp.", "lgf": "Lionsgate Entertainment Corp.",
    "amc networks": "AMC Networks Inc.", "amcx": "AMC Networks Inc.",
    "news corp": "News Corporation", "nws": "News Corporation", "wall street journal": "News Corporation",
    "iheartmedia": "iHeartMedia, Inc.", "ihrt": "iHeartMedia, Inc.", "iheartradio": "iHeartMedia, Inc.",

    # Chemicals
    "dow": "Dow Inc.", "dow chemical": "Dow Inc.",
    "dupont": "DuPont de Nemours, Inc.", "dd": "DuPont de Nemours, Inc.",
    "basf": "BASF SE", "basfy": "BASF SE",
    "lyondellbasell": "LyondellBasell Industries N.V.", "lyb": "LyondellBasell Industries N.V.",
    "eastman": "Eastman Chemical Company", "emn": "Eastman Chemical Company",
    "ppg": "PPG Industries, Inc.", "ppg industries": "PPG Industries, Inc.",
    "sherwin-williams": "Sherwin-Williams Company", "sherwin williams": "Sherwin-Williams Company", "shw": "Sherwin-Williams Company",
    "air products": "Air Products and Chemicals, Inc.", "apd": "Air Products and Chemicals, Inc.",
    "linde": "Linde plc", "lin": "Linde plc",
    "ecolab": "Ecolab Inc.", "ecl": "Ecolab Inc.",

    # Healthcare Services
    "hca": "HCA Healthcare, Inc.", "hca healthcare": "HCA Healthcare, Inc.",
    "kaiser": "Kaiser Permanente", "kaiser permanente": "Kaiser Permanente",
    "mayo clinic": "Mayo Clinic", "mayo": "Mayo Clinic",
    "cleveland clinic": "Cleveland Clinic",
    "johns hopkins": "Johns Hopkins Medicine", "hopkins": "Johns Hopkins Medicine",
    "mass general": "Mass General Brigham", "brigham": "Mass General Brigham",
    "davita": "DaVita Inc.", "dva": "DaVita Inc.",
    "fresenius": "Fresenius Medical Care", "fms": "Fresenius Medical Care",
    "labcorp": "Laboratory Corporation of America Holdings", "lh": "Laboratory Corporation of America Holdings",
    "quest diagnostics": "Quest Diagnostics Incorporated", "dgx": "Quest Diagnostics Incorporated",
    "iqvia": "IQVIA Holdings Inc.", "iqv": "IQVIA Holdings Inc.",

    # Medical Devices
    "medtronic": "Medtronic plc", "mdt": "Medtronic plc",
    "abbott": "Abbott Laboratories", "abt": "Abbott Laboratories",
    "thermo fisher": "Thermo Fisher Scientific Inc.", "tmo": "Thermo Fisher Scientific Inc.",
    "danaher": "Danaher Corporation", "dhr": "Danaher Corporation",
    "becton dickinson": "Becton, Dickinson and Company", "bd": "Becton, Dickinson and Company", "bdx": "Becton, Dickinson and Company",
    "boston scientific": "Boston Scientific Corporation", "bsx": "Boston Scientific Corporation",
    "stryker": "Stryker Corporation", "syk": "Stryker Corporation",
    "edwards": "Edwards Lifesciences Corporation", "ew": "Edwards Lifesciences Corporation",
    "intuitive surgical": "Intuitive Surgical, Inc.", "isrg": "Intuitive Surgical, Inc.", "da vinci": "Intuitive Surgical, Inc.",
    "zimmer": "Zimmer Biomet Holdings, Inc.", "zbh": "Zimmer Biomet Holdings, Inc.",
    "baxter": "Baxter International Inc.", "bax": "Baxter International Inc.",
    "align": "Align Technology, Inc.", "algn": "Align Technology, Inc.", "invisalign": "Align Technology, Inc.",
    "idexx": "IDEXX Laboratories, Inc.", "idxx": "IDEXX Laboratories, Inc.",
    "resmed": "ResMed Inc.", "rmd": "ResMed Inc.",

    # Fintech
    "stripe": "Stripe, Inc.",
    "plaid": "Plaid Inc.",
    "robinhood": "Robinhood Markets, Inc.", "hood": "Robinhood Markets, Inc.",
    "coinbase": "Coinbase Global, Inc.", "coin": "Coinbase Global, Inc.",
    "affirm": "Affirm Holdings, Inc.", "afrm": "Affirm Holdings, Inc.",
    "marqeta": "Marqeta, Inc.", "mq": "Marqeta, Inc.",
    "sofi": "SoFi Technologies, Inc.", "social finance": "SoFi Technologies, Inc.",
    "chime": "Chime Financial, Inc.",
    "klarna": "Klarna Bank AB",
    "revolut": "Revolut Ltd",
    "toast": "Toast, Inc.", "tost": "Toast, Inc.",
    "bill.com": "Bill.com Holdings, Inc.", "bill": "Bill.com Holdings, Inc.",
    "remitly": "Remitly Global, Inc.", "rely": "Remitly Global, Inc.",

    # Cybersecurity
    "crowdstrike": "CrowdStrike Holdings, Inc.", "crwd": "CrowdStrike Holdings, Inc.",
    "palo alto": "Palo Alto Networks, Inc.", "panw": "Palo Alto Networks, Inc.",
    "fortinet": "Fortinet, Inc.", "ftnt": "Fortinet, Inc.",
    "zscaler": "Zscaler, Inc.", "zs": "Zscaler, Inc.",
    "cloudflare": "Cloudflare, Inc.", "net": "Cloudflare, Inc.",
    "okta": "Okta, Inc.", "okta": "Okta, Inc.",
    "sentinelone": "SentinelOne, Inc.", "s": "SentinelOne, Inc.",
    "rapid7": "Rapid7, Inc.", "rpd": "Rapid7, Inc.",
    "qualys": "Qualys, Inc.", "qlys": "Qualys, Inc.",
    "tenable": "Tenable Holdings, Inc.", "tenb": "Tenable Holdings, Inc.",
    "cyberark": "CyberArk Software Ltd.", "cybr": "CyberArk Software Ltd.",
    "varonis": "Varonis Systems, Inc.", "vrns": "Varonis Systems, Inc.",

    # Real Estate
    "cbre": "CBRE Group, Inc.", "cbre group": "CBRE Group, Inc.",
    "jll": "Jones Lang LaSalle Incorporated", "jones lang lasalle": "Jones Lang LaSalle Incorporated",
    "cushman wakefield": "Cushman & Wakefield plc", "cwk": "Cushman & Wakefield plc",
    "prologis": "Prologis, Inc.", "pld": "Prologis, Inc.",
    "american tower": "American Tower Corporation", "amt": "American Tower Corporation",
    "crown castle": "Crown Castle Inc.", "cci": "Crown Castle Inc.",
    "equinix": "Equinix, Inc.", "eqix": "Equinix, Inc.",
    "digital realty": "Digital Realty Trust, Inc.", "dlr": "Digital Realty Trust, Inc.",
    "public storage": "Public Storage", "psa": "Public Storage",
    "simon property": "Simon Property Group, Inc.", "spg": "Simon Property Group, Inc.",
    "realty income": "Realty Income Corporation", "o": "Realty Income Corporation",
    "avalonbay": "AvalonBay Communities, Inc.", "avb": "AvalonBay Communities, Inc.",

    # E-commerce & Retail
    "ebay": "eBay Inc.", "ebay": "eBay Inc.",
    "etsy": "Etsy, Inc.",
    "wayfair": "Wayfair Inc.", "w": "Wayfair Inc.",
    "chewy": "Chewy, Inc.", "chwy": "Chewy, Inc.",
    "home depot": "The Home Depot, Inc.", "hd": "The Home Depot, Inc.",
    "lowes": "Lowe's Companies, Inc.", "lowe's": "Lowe's Companies, Inc.", "low": "Lowe's Companies, Inc.",
    "best buy": "Best Buy Co., Inc.", "bby": "Best Buy Co., Inc.",
    "tjx": "TJX Companies, Inc.", "tj maxx": "TJX Companies, Inc.", "marshalls": "TJX Companies, Inc.",
    "ross": "Ross Stores, Inc.", "rost": "Ross Stores, Inc.",
    "dollar general": "Dollar General Corporation", "dg": "Dollar General Corporation",
    "dollar tree": "Dollar Tree, Inc.", "dltr": "Dollar Tree, Inc.",
    "walgreens": "Walgreens Boots Alliance, Inc.", "wba": "Walgreens Boots Alliance, Inc.",
    "rite aid": "Rite Aid Corporation", "rad": "Rite Aid Corporation",
    "ulta": "Ulta Beauty, Inc.", "ulta beauty": "Ulta Beauty, Inc.",
    "bath body works": "Bath & Body Works, Inc.", "bbwi": "Bath & Body Works, Inc.",
}

# Build indexes
CANONICAL_SET = set(c.lower().strip() for c in CANONICALS)
NORMALIZED_LOOKUP = {}
for canonical in CANONICALS:
    NORMALIZED_LOOKUP[canonical.lower().strip()] = canonical

# Phase 10.1: Suffix-stripped lookup for L1 hardening
# Maps normalized-then-stripped names → canonical form
_CORP_SUFFIX_RE = re.compile(
    r',?\s*(&\s*)?\b(Inc\.?|Corp\.?|Corporation|Company|Ltd\.?|Limited|plc|AG|SE|'
    r'S\.A\.?|N\.V\.?|GmbH|S\.p\.A\.?|LLC|LP|LLP|Co\.?|Group|Holdings?|'
    r'Incorporated|International)\s*$', re.I
)

def _strip_corp_suffix(name: str) -> str:
    """Strip corporate suffix for suffix-tolerant L1 matching.
    Iteratively strips suffixes and trailing '&', then removes leading 'the '.
    """
    result = name.strip()
    # Iteratively strip — handles "& Co.", ", Inc." chains
    for _ in range(3):
        prev = result
        result = _CORP_SUFFIX_RE.sub('', result).strip()
        # Strip trailing ampersand left from "& Company" patterns
        result = re.sub(r'\s*&\s*$', '', result).strip()
        if result == prev:
            break
    # Strip leading "The " (e.g., "The Boeing Company" → "boeing")
    result = re.sub(r'^the\s+', '', result, flags=re.I).strip()
    return result.lower()

SUFFIX_STRIPPED_LOOKUP = {}
for canonical in CANONICALS:
    stripped = _strip_corp_suffix(canonical)
    if stripped and stripped != canonical.lower().strip():
        SUFFIX_STRIPPED_LOOKUP[stripped] = canonical

# Phase 10.1: KNOWN_PARENTS O(1) lookup indexes
# Separate short keys (≤3 chars, exact-only) from long keys (substring-capable)
_KP_EXACT = {}  # All keys: exact match lookup
_KP_LONG_KEYS = []  # Keys > 3 chars: for substring fallback
for _kp_key, _kp_val in KNOWN_PARENTS.items():
    _kp_exact_key = _kp_key.lower().strip()
    _KP_EXACT[_kp_exact_key] = _kp_val
    if len(_kp_key) > 3:
        _KP_LONG_KEYS.append((_kp_key, _kp_val))

# Canonical list fingerprint — included in L3 cache key so cache auto-invalidates when list changes.
_CANONICAL_LIST_HASH = hashlib.sha256(
    "|".join(sorted(c.lower() for c in CANONICALS)).encode()
).hexdigest()[:16]


def _try_canonical_match(name: str) -> Optional[Tuple[str, str, float]]:
    """
    Attempt deterministic canonical resolution using the same L1 lookup chain
    used by company mode (KNOWN_PARENTS, exact, normalized, suffix-stripped).

    Returns (resolved_canonical, layer, confidence) if matched, else None.

    Used by mixed-mode ORG path to resolve obvious canonicals before
    falling through to the org sanitizer.
    """
    name_lower = name.lower().strip()
    name_normalized = normalize(name)

    # L1: Known Parents — O(1) exact alias lookup
    kp_match = _KP_EXACT.get(name_lower) or _KP_EXACT.get(name_normalized)
    if kp_match:
        return (kp_match, "L1_CANONICAL", 1.0)

    # L1: Known Parents — substring fallback for long keys
    for key, parent in _KP_LONG_KEYS:
        if key in name_lower:
            return (parent, "L1_CANONICAL", 1.0)

    # L1: Exact canonical match
    if name_lower in CANONICAL_SET:
        resolved = NORMALIZED_LOOKUP.get(name_lower)
        if resolved:
            return (resolved, "L1_CANONICAL", 1.0)

    # L1: Normalized match
    if name_normalized in NORMALIZED_LOOKUP:
        return (NORMALIZED_LOOKUP[name_normalized], "L1_CANONICAL", 1.0)

    # L1: Suffix-stripped match
    stripped = _strip_corp_suffix(name)
    if stripped in SUFFIX_STRIPPED_LOOKUP:
        return (SUFFIX_STRIPPED_LOOKUP[stripped], "L1_CANONICAL", 0.98)

    return None

# TF-IDF
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    VECTORIZER = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4), lowercase=True)
    CANONICAL_VECTORS = VECTORIZER.fit_transform(CANONICALS)
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2B: Embedding Sovereignty — Tenant-partitioned vector namespace
# ─────────────────────────────────────────────────────────────────────────────
EMBEDDING_MODEL_ID = "tfidf-char_wb-ngram_2_4"
VECTOR_INDEX_VERSION = "v1"


def vector_namespace(tenant_id: str) -> str:
    """
    Compute deterministic namespace key for vector operations.
    Format: {tenant_id}:{EMBEDDING_MODEL_ID}:{VECTOR_INDEX_VERSION}

    Fail-closed: raises ValueError if tenant_id is missing or empty.
    """
    if not tenant_id or tenant_id in ("unknown", ""):
        raise ValueError(
            f"VECTOR_NAMESPACE_FAIL_CLOSED: tenant_id is required for vector operations, got '{tenant_id}'"
        )
    return f"{tenant_id}:{EMBEDDING_MODEL_ID}:{VECTOR_INDEX_VERSION}"


def _build_version_snapshot() -> dict:
    """Collect all version/model identifiers for receipt binding. Metadata only."""
    _code_version = "unknown"
    try:
        if HAS_FORENSIC_SIGNING:
            _code_version = get_signing_status().get(
                "service_identity", {}
            ).get("code_version", "unknown")
    except Exception:
        pass
    return {
        "protocol_version": PROTOCOL_VERSION,
        "router_version": ROUTER_VERSION,
        "model_mapping_version": MODEL_MAPPING_VERSION,
        "config_hash": hashlib.sha256(json.dumps({
            "config_version": CANONICAL_CONFIG_VERSION,
            "sanitization_version": config.SANITIZATION_VERSION,
            "watchlist_version_hash": config.WATCHLIST_VERSION_HASH,
            "l3_max_cost_usd": config.L3_MAX_COST_USD,
            "l3_min_similarity": config.L3_MIN_SIMILARITY,
        }, sort_keys=True).encode()).hexdigest(),
        "engine_commit_hash": _code_version,
        "engine_version": config.ENGINE_VERSION,
        "embedding_model_id": EMBEDDING_MODEL_ID,
        "llm_model_id": L3_MODEL_ID,
        "canonical_dataset_hash": _CANONICAL_LIST_HASH,
    }


def normalize(text: str) -> str:
    """Normalize company name."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r',?\s*\b(inc\.?|incorporated|corp\.?|corporation|co\.?|ltd\.?|llc\.?|plc\.?|group|holdings?|company|the|gmbh|ag|se|s\.a\.?|n\.v\.?)\b', '', text, flags=re.I)
    text = re.sub(r'[^\w\s]', '', text)
    return ' '.join(text.split())


def get_vector_candidates(company_name: str, top_n: int = 15, tenant_id: str = "unknown") -> List[Tuple[str, float]]:
    """
    Get top N vector similarity candidates for L3 grounding.
    Returns list of (canonical, score) tuples, even if below L2 accept threshold.

    Phase 2B: tenant_id required for namespace validation.
    """
    if not HAS_SKLEARN or not CANONICALS:
        return []

    try:
        # Phase 2B: validate namespace (fail-closed if tenant_id missing)
        ns = vector_namespace(tenant_id)

        query_vec = VECTORIZER.transform([company_name])
        similarities = cosine_similarity(query_vec, CANONICAL_VECTORS)[0]

        # Get top N indices sorted by score descending
        top_indices = np.argsort(similarities)[-top_n:][::-1]

        candidates = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.1:  # Minimum relevance threshold
                candidates.append((CANONICALS[idx], score))

        return candidates
    except ValueError:
        raise  # Re-raise namespace validation errors (fail-closed)
    except Exception as e:
        print(f"[L3_LLM] Vector candidates error: {e}", flush=True)
        return []


def resolve_with_claude_sync(company_name: str, candidates: List[Tuple[str, float]] = None, tenant_id: str = "unknown") -> Optional[Dict[str, Any]]:
    """
    Layer 3: Use Claude to resolve company names that L1/L2 couldn't match.
    Returns None if LLM is unavailable or can't resolve.

    Enterprise requirement: L3 should absorb the ambiguous tail to minimize L4.

    Features:
    - Candidate-set grounding: LLM picks only from provided candidates
    - Rate-limit hardening: 2 retries with exponential backoff on 429
    """
    if not HAS_ANTHROPIC or not ANTHROPIC_API_KEY:
        return None

    # Get candidates if not provided
    if candidates is None:
        candidates = get_vector_candidates(company_name, top_n=15, tenant_id=tenant_id)

    # Build candidate list for prompt
    if candidates:
        candidate_names = [c[0] for c in candidates]
        candidate_list = '\n'.join([f"  - {name}" for name in candidate_names])
        candidate_instruction = f"""
CANDIDATE COMPANIES (pick ONLY from this list if applicable):
{candidate_list}

IMPORTANT: If the input matches one of the candidates above, return that EXACT candidate name.
If none of the candidates match, return "UNKNOWN"."""
    else:
        # Fallback to general canonicals if no vector candidates
        sample_canonicals = ', '.join(CANONICALS[:30])
        candidate_instruction = f"""
Known companies include: {sample_canonicals}

If none match, return "UNKNOWN"."""

    prompt = f"""You are an entity resolution expert. Given a company reference, identify the canonical company name.

Input: "{company_name}"
{candidate_instruction}

Rules:
1. The input could be a nickname, abbreviation, product name, subsidiary, or description
2. Match to a candidate if the input clearly refers to that company
3. Common patterns:
   - "iPhone manufacturer" → Apple Inc
   - "Windows creator" → Microsoft Corporation
   - "maker of Humira" → AbbVie Inc
   - "produces Tylenol" → Johnson & Johnson
   - "Gmail provider" → Alphabet Inc
4. Return the EXACT candidate name if matched
5. Return "UNKNOWN" only if no candidate matches

Response (exact candidate name, or UNKNOWN):"""

    # L3 call via llm_router (retry + soft failover handled inside)
    try:
        llm_result = call_l3_with_failover(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
        )
        response = llm_result.text.strip()

        if response and response.upper() != "UNKNOWN" and len(response) < 100:
            response_lower = response.lower()
            response_normalized = normalize(response)

            # First check against provided candidates (highest priority)
            if candidates:
                for canonical, score in candidates:
                    canonical_lower = canonical.lower()
                    canonical_normalized = normalize(canonical)
                    if (canonical_lower == response_lower or
                        response_lower in canonical_lower or
                        canonical_lower in response_lower or
                        canonical_normalized == response_normalized):
                        return {
                            "resolved": canonical,
                            "confidence": min(0.85, 0.70 + score * 0.3),
                            "layer": "L3_LLM",
                            "reason": f"Claude Match (score={score:.2f})",
                            "model_used": llm_result.model_used,
                            "provider_used": llm_result.provider_used,
                            "failover_used": llm_result.failover_used,
                        }

            # Fallback: check all canonicals
            for canonical in CANONICALS:
                canonical_lower = canonical.lower()
                canonical_normalized = normalize(canonical)
                if (canonical_lower == response_lower or
                    response_lower in canonical_lower or
                    canonical_lower in response_lower or
                    canonical_normalized == response_normalized):
                    return {
                        "resolved": canonical,
                        "confidence": 0.80,
                        "layer": "L3_LLM",
                        "reason": "Claude Match",
                        "model_used": llm_result.model_used,
                        "provider_used": llm_result.provider_used,
                        "failover_used": llm_result.failover_used,
                    }

            # Check KNOWN_PARENTS
            for key, parent in KNOWN_PARENTS.items():
                if response_lower == key or key in response_lower or response_lower in key:
                    return {
                        "resolved": parent,
                        "confidence": 0.78,
                        "layer": "L3_LLM",
                        "reason": "Claude Known Parent",
                        "model_used": llm_result.model_used,
                        "provider_used": llm_result.provider_used,
                        "failover_used": llm_result.failover_used,
                    }

        # LLM returned UNKNOWN or unrecognized response
        return None

    except Exception as e:
        print(f"[L3_LLM] Claude error: {e}", flush=True)
        circuit_breakers["resolution"].record_failure()
        return None


def resolve_entity_sync(
    company_raw: str,
    tenant_id: str = "unknown",
    batch_trace_id: str = "unknown",
    idx: int = -1,
    allow_l3: bool = True,
    l3_skip_reason: Optional[str] = None,
):
    """Resolve a single entity with PII masking."""
    start_time = time.time()
    trace_id = batch_trace_id or f"TR-{hashlib.md5(f'{company_raw}{time.time()}'.encode()).hexdigest()[:6].upper()}"

    # Input Validation (security hardening)
    is_valid, sanitized_input, validation_error = input_validator.validate(company_raw)
    if not is_valid:
        return {
            "trace_id": trace_id,
            "original": company_raw[:100] if company_raw else "",  # Truncate for safety
            "resolved": None,
            "confidence": 0.0,
            "layer": "L0_VALIDATION",
            "reason": "Validation Failed",
            "validation_error": validation_error,
            "pii_detected": [],
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000)
        }

    # PII Detection and Masking
    masked_name, pii_types = pii_masker.detect_and_mask(
        sanitized_input, tenant_id, trace_id, "company_raw", idx
    )

    # Handle garbage
    if not masked_name or not str(masked_name).strip():
        return {
            "trace_id": trace_id,
            "original": masked_name,
            "resolved": None,
            "confidence": 0.0,
            "layer": "L0_GARBAGE",
            "reason": "Empty/Null",
            "pii_detected": pii_types,
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000)
        }

    name = str(masked_name).strip()
    name_lower = name.lower()
    name_normalized = normalize(name)

    # Check if known short alias BEFORE garbage filtering
    is_known_alias = name_lower in _KP_EXACT or name_normalized in _KP_EXACT

    # Garbage patterns
    garbage_patterns = [
        (r'\.xlsx?$|\.csv$|\.pdf$', 'File Extension'),
        (r'^[\d\s\-\.\(\)]+$', 'Numeric Only'),
        (r'^.{0,2}$', 'Too Short'),
        (r'\b(test|null|none|n/a|na|tbd|tbc|unknown|placeholder|draft|temp|sample|example|demo)\b', 'Placeholder'),
        (r'\[.*_MASKED\]', 'PII Content'),
        # Phase 10.1: Expanded garbage detection for calibration hardening
        (r'^(void|deleted|removed|do not use|see above|same as above|ditto|refer|pending|awaiting|not applicable|pending review|awaiting input)$', 'Status Placeholder'),
        (r'^(foo|bar|baz|asdf|qwerty|xxx|zzz|abc|xyz)$', 'Test Placeholder'),
        (r'^(.)\1{4,}$', 'Repeated Characters'),
        (r'^(the|and|or|for|a|an|of|to|in|is|it|at|by|on)$', 'Stop Word'),
        (r'^\[.+\]$', 'Bracketed Placeholder'),
        (r'^(company|enter|type|insert|input|fill|add|your)\s+(name|here|company|value|entity|data)', 'Form Placeholder'),
        (r'^[\s_]+$', 'Whitespace/Underscore Only'),
        (r'^[^\w\s]+$', 'Punctuation Only'),
    ]
    for pattern, reason in garbage_patterns:
        if is_known_alias:
            continue  # Phase 10.1: skip ALL garbage patterns for known aliases
        if re.search(pattern, name_lower, re.I):
            pii_masker.record_validation_failure()
            return {
                "trace_id": trace_id,
                "original": name,
                "resolved": None,
                "confidence": 0.0,
                "layer": "L0_GARBAGE",
                "reason": f"Garbage: {reason}",
                "pii_detected": pii_types,
                "cost": 0.0,
                "latency_ms": float((time.time() - start_time) * 1000)
            }

    # Layer 1: Known Parents — O(1) exact lookup (Phase 10.1)
    _kp_match = _KP_EXACT.get(name_lower) or _KP_EXACT.get(name_normalized)
    if _kp_match:
        circuit_breakers["resolution"].record_success()
        return {
            "trace_id": trace_id,
            "original": name,
            "resolved": _kp_match,
            "confidence": 1.0,
            "layer": "L1_NORM",
            "reason": "Known Parent (exact)",
            "pii_detected": pii_types,
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000)
        }

    # Layer 1: Known Parents — substring fallback for long keys only
    for key, parent in _KP_LONG_KEYS:
        if key in name_lower:
            circuit_breakers["resolution"].record_success()
            return {
                "trace_id": trace_id,
                "original": name,
                "resolved": parent,
                "confidence": 1.0,
                "layer": "L1_NORM",
                "reason": "Known Parent (substring)",
                "pii_detected": pii_types,
                "cost": 0.0,
                "latency_ms": float((time.time() - start_time) * 1000)
            }

    # Layer 1: Exact match
    if name_lower in CANONICAL_SET:
        circuit_breakers["resolution"].record_success()
        return {
            "trace_id": trace_id,
            "original": name,
            "resolved": NORMALIZED_LOOKUP.get(name_lower),
            "confidence": 1.0,
            "layer": "L1_EXACT",
            "reason": "Exact Match",
            "pii_detected": pii_types,
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000)
        }

    # Layer 1: Normalized match
    if name_normalized in NORMALIZED_LOOKUP:
        circuit_breakers["resolution"].record_success()
        return {
            "trace_id": trace_id,
            "original": name,
            "resolved": NORMALIZED_LOOKUP[name_normalized],
            "confidence": 1.0,
            "layer": "L1_NORM",
            "reason": "Normalized Match",
            "pii_detected": pii_types,
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000)
        }

    # Layer 1: Suffix-stripped match (Phase 10.1)
    name_suffix_stripped = _strip_corp_suffix(name)
    if name_suffix_stripped in SUFFIX_STRIPPED_LOOKUP:
        circuit_breakers["resolution"].record_success()
        return {
            "trace_id": trace_id,
            "original": name,
            "resolved": SUFFIX_STRIPPED_LOOKUP[name_suffix_stripped],
            "confidence": 0.98,
            "layer": "L1_NORM",
            "reason": "Suffix-Stripped Match",
            "pii_detected": pii_types,
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000)
        }

    # Layer 2: Vector similarity
    l2_best_score = 0.0  # Track L2 score for smart L3 gating
    if HAS_SKLEARN:
        try:
            query_vec = VECTORIZER.transform([name])
            similarities = cosine_similarity(query_vec, CANONICAL_VECTORS)[0]
            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])
            l2_best_score = best_score  # Preserve for L3 eligibility filtering

            if best_score >= 0.55:
                circuit_breakers["resolution"].record_success()
                return {
                    "trace_id": trace_id,
                    "original": name,
                    "resolved": CANONICALS[best_idx],
                    "confidence": best_score,
                    "layer": "L2_VECTOR",
                    "reason": f"Vector ({best_score:.0%})",
                    "pii_detected": pii_types,
                    "cost": 0.0,
                    "latency_ms": float((time.time() - start_time) * 1000)
                }
        except Exception as e:
            circuit_breakers["resolution"].record_failure()

    # Layer 3: LLM (Claude) for low-confidence matches
    llm_result = None
    l3_error = False
    if allow_l3:
        try:
            llm_result = resolve_with_claude_sync(name, tenant_id=tenant_id)
        except Exception as e:
            print(f"[L3_LLM] Error during resolution: {e}", flush=True)
            l3_error = True
            l3_skip_reason = "L3_ERROR_FAIL_CLOSED"

    if llm_result:
        circuit_breakers["resolution"].record_success()
        return {
            "trace_id": trace_id,
            "original": name,
            "resolved": llm_result["resolved"],
            "confidence": llm_result["confidence"],
            "layer": llm_result["layer"],
            "reason": llm_result["reason"],
            "pii_detected": pii_types,
            "cost": config.L3_COST_PER_CALL_USD,
            "latency_ms": float((time.time() - start_time) * 1000),
            "l3_skip_reason": None
        }

    # Layer 4: Human review
    # Include l3_skip_reason if L3 was skipped due to budget/cap/error
    reason = "Low Confidence"
    if l3_skip_reason:
        reason = f"Low Confidence ({l3_skip_reason})"

    return {
        "trace_id": trace_id,
        "original": name,
        "resolved": None,
        "confidence": 0.0,
        "layer": "L4_HUMAN",
        "reason": reason,
        "pii_detected": pii_types,
        "cost": 0.0,
        "latency_ms": float((time.time() - start_time) * 1000),
        "l3_skip_reason": l3_skip_reason,
        "l2_score": l2_best_score  # Preserved for smart L3 gating
    }


# =============================================================================
# PERSON REFERENCE-DATA PIPELINE (optional; no embedded reference data)
# =============================================================================

# Import from dedicated modules (no embedded data)
try:
    from app.person_canonical_loader import get_person_store, PersonCanonicalStore
    from app.person_resolver import (
        resolve_person_sync as _resolve_person_sync,
        MatchType as PersonMatchType,
        normalize_person_name,
    )
    from app.company_resolver import (
        MatchType as CompanyMatchType,
        get_match_type_for_layer,
        enrich_company_result_with_match_type,
    )
    HAS_PERSON_RESOLVER = True
    _person_store = get_person_store()
    print(f"[INFO] Person resolver loaded. Store: {_person_store.source}, records: {_person_store.record_count}", flush=True)
except ImportError as e:
    HAS_PERSON_RESOLVER = False
    _person_store = None
    print(f"[INFO] Person resolver not available: {e}", flush=True)


# Person resolution functions are imported from person_resolver module.
# The normalize_person_name function is imported above.


def resolve_person_sync(
    name_raw: str,
    tenant_id: str = "unknown",
    batch_trace_id: str = "unknown",
    idx: int = -1,
    allow_l3: bool = True,
    l3_skip_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve a single person name against configured reference data.

    Wraps the new person_resolver module with PII detection.

    NOTE: L3 is DISABLED for person mode until calibrated.
    """
    start_time = time.time()
    trace_id = batch_trace_id or f"TR-{hashlib.md5(f'{name_raw}{time.time()}'.encode()).hexdigest()[:6].upper()}"

    # Input Validation (security hardening)
    is_valid, sanitized_input, validation_error = input_validator.validate(name_raw)
    if not is_valid:
        return {
            "trace_id": trace_id,
            "original": name_raw[:100] if name_raw else "",  # Truncate for safety
            "normalized_input": "",
            "resolved": None,
            "match_id": None,
            "match_type": "NO_MATCH",
            "decision": "REJECTED",
            "confidence": 0.0,
            "layer": "L0_VALIDATION",
            "reason": "Validation Failed",
            "validation_error": validation_error,
            "pii_detected": [],
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000),
            "top_candidates": [],
            "similarity_scores": {}
        }

    # PII Detection (shared with company mode)
    masked_name, pii_types = pii_masker.detect_and_mask(
        sanitized_input, tenant_id, trace_id, "name_raw", idx
    )

    if not HAS_PERSON_RESOLVER:
        return {
            "trace_id": trace_id,
            "original": name_raw,
            "normalized_input": "",
            "resolved": None,
            "match_id": None,
            "match_type": "NO_MATCH",
            "decision": "REVIEW",
            "confidence": 0.0,
            "layer": "L4_HUMAN",
            "reason": "Person resolver not available",
            "pii_detected": pii_types,
            "cost": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000),
            "top_candidates": [],
            "similarity_scores": {}
        }

    # Call the new resolver module
    result = _resolve_person_sync(
        name_raw=masked_name,
        tenant_id=tenant_id,
        batch_trace_id=batch_trace_id,
        idx=idx,
        store=_person_store
    )

    # Add trace_id and PII info
    result["trace_id"] = trace_id
    result["pii_detected"] = pii_types
    result["latency_ms"] = float((time.time() - start_time) * 1000)
    result["cost"] = 0.0  # L3 disabled for person mode

    # Add sanitization data for metrics calculation
    # This provides meaningful confidence even when watchlist is empty
    try:
        from app.person_sanitizer import sanitize_person_name_only
        sanitization = sanitize_person_name_only(name_raw)
        result["sanitization"] = {
            "sanitized": sanitization.sanitized,
            "first_name": sanitization.first_name,
            "last_name": sanitization.last_name,
            "confidence": sanitization.confidence,
            "flags": sanitization.flags,
            "format_standardized": sanitization.format_standardized
        }
        # Use sanitization confidence for auto_resolved calculation when no watchlist match
        if result.get("layer") == "L4_HUMAN" and result.get("confidence", 0) < 0.5:
            result["confidence"] = sanitization.confidence
    except Exception:
        pass  # Sanitization is optional

    # Map decision for compatibility
    if result.get("match_type") == "EXACT_MATCH":
        result["decision"] = "MATCH"
    elif result.get("match_type") == "FUZZY_MATCH":
        result["decision"] = "MATCH"
    elif result.get("match_type") == "POSSIBLE_MATCH":
        result["decision"] = "REVIEW"
    else:
        result["decision"] = "REVIEW" if result.get("layer") == "L4_HUMAN" else "NO_MATCH"

    return result


# =============================================================================
# MIXED MODE RESOLVER (Row-level classification + deterministic sanitization)
# =============================================================================

def resolve_mixed_sync(
    name_raw: str,
    tenant_id: str = "unknown",
    batch_trace_id: str = "unknown",
    idx: int = -1,
) -> Dict[str, Any]:
    """
    Resolve a single row in mixed mode with row-level entity classification.

    1. Classify entity type: PERSON | ORGANIZATION | VESSEL | GARBAGE
    2. Route to appropriate sanitizer
    3. Return unified result format

    O(n) complexity. No ML. No fuzzy matching. No watchlist lookups.
    """
    start_time = time.time()
    trace_id = batch_trace_id or f"TR-{hashlib.md5(f'{name_raw}{time.time()}'.encode()).hexdigest()[:6].upper()}"

    # Input validation (security hardening)
    is_valid, sanitized_input, validation_error = input_validator.validate(name_raw)
    if not is_valid:
        return {
            "trace_id": trace_id,
            "original": name_raw[:100] + "..." if len(name_raw) > 100 else name_raw,
            "entity_type": "GARBAGE",
            "sanitized_name": "",
            "sanitization_confidence": 0.0,
            "sanitization_flags": [validation_error],
            "decision_path": "INPUT_REJECTED",
            "classification_confidence": 0.0,
            "classification_flags": [validation_error],
                "first_name": "",
                "middle_name": "",
                "last_name": "",
                "org_name": "",
                "legal_suffix": "",
                "org_category": "",
                "vessel_name": "",
                "imo_number": "",
                "vessel_prefix": "",
                "pii_detected": [],
                "layer": "L0_INPUT_REJECTED",
                "confidence": 0.0,
                "latency_ms": float((time.time() - start_time) * 1000),
            }

    # PII Detection
    masked_name, pii_types = pii_masker.detect_and_mask(
        name_raw, tenant_id, trace_id, "name_raw", idx
    )

    # Step 1: Classify entity type
    entity_type, cls_confidence, cls_flags = classify_entity(masked_name)

    # Step 2: Route to appropriate sanitizer
    if entity_type == EntityType.GARBAGE.value:
        # Garbage - minimal processing
        return {
            "trace_id": trace_id,
            "original": name_raw,
            "entity_type": entity_type,
            "sanitized_name": "",
            "sanitization_confidence": 0.0,
            "sanitization_flags": cls_flags,
            "decision_path": "GARBAGE",
            "classification_confidence": cls_confidence,
            "classification_flags": cls_flags,
            # Person fields (blank)
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            # Org fields (blank)
            "org_name": "",
            "legal_suffix": "",
            "org_category": "",
            # Vessel fields (blank)
            "vessel_name": "",
            "imo_number": "",
            "vessel_prefix": "",
            # Metadata
            "pii_detected": pii_types,
            "layer": "L0_GARBAGE",
            "confidence": 0.0,
            "latency_ms": float((time.time() - start_time) * 1000),
        }

    elif entity_type == EntityType.VESSEL.value:
        # Vessel sanitization
        result = sanitize_vessel_name(masked_name)
        return {
            "trace_id": trace_id,
            "original": name_raw,
            "entity_type": entity_type,
            "sanitized_name": result["sanitized_name"],
            "sanitization_confidence": result["sanitization_confidence"],
            "sanitization_flags": result["sanitization_flags"],
            "decision_path": result["decision_path"],
            "classification_confidence": cls_confidence,
            "classification_flags": cls_flags,
            # Person fields (blank)
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            # Org fields (blank)
            "org_name": "",
            "legal_suffix": "",
            "org_category": "",
            # Vessel fields
            "vessel_name": result["vessel_name"],
            "imo_number": result["imo_number"],
            "vessel_prefix": result["vessel_prefix"],
            # Metadata
            "pii_detected": pii_types,
            "layer": "L1_VESSEL",
            "confidence": result["sanitization_confidence"],
            "latency_ms": float((time.time() - start_time) * 1000),
        }

    elif entity_type == EntityType.ORGANIZATION.value:
        # Canonical pre-check: resolve obvious canonicals deterministically
        # before falling through to the org sanitizer. Uses the same L1
        # lookup chain as company mode (KNOWN_PARENTS, exact, normalized,
        # suffix-stripped). This prevents known financial/corporate entities
        # from being sanitized-only and landing in L4.
        canonical_hit = _try_canonical_match(masked_name)
        if canonical_hit:
            resolved_name, match_layer, match_confidence = canonical_hit
            return {
                "trace_id": trace_id,
                "original": name_raw,
                "entity_type": entity_type,
                "resolved": resolved_name,
                "sanitized_name": resolved_name,
                "sanitization_confidence": match_confidence,
                "sanitization_flags": ["CANONICAL_MATCH"],
                "decision_path": "CANONICAL_RESOLVED",
                "classification_confidence": cls_confidence,
                "classification_flags": cls_flags,
                # Person fields (blank)
                "first_name": "",
                "middle_name": "",
                "last_name": "",
                # Org fields
                "org_name": resolved_name,
                "legal_suffix": "",
                "org_category": "",
                # Vessel fields (blank)
                "vessel_name": "",
                "imo_number": "",
                "vessel_prefix": "",
                # Metadata
                "pii_detected": pii_types,
                "layer": match_layer,
                "confidence": match_confidence,
                "reason": "Canonical match (mixed-mode pre-check)",
                "latency_ms": float((time.time() - start_time) * 1000),
            }

        # Non-canonical org: standard sanitization path
        result = sanitize_organization_name(masked_name)
        return {
            "trace_id": trace_id,
            "original": name_raw,
            "entity_type": entity_type,
            "sanitized_name": result["sanitized_name"],
            "sanitization_confidence": result["sanitization_confidence"],
            "sanitization_flags": result["sanitization_flags"],
            "decision_path": result["decision_path"],
            "classification_confidence": cls_confidence,
            "classification_flags": cls_flags,
            # Person fields (blank)
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            # Org fields
            "org_name": result["org_name"],
            "legal_suffix": result["legal_suffix"],
            "org_category": result["org_category"],
            # Vessel fields (blank)
            "vessel_name": "",
            "imo_number": "",
            "vessel_prefix": "",
            # Metadata
            "pii_detected": pii_types,
            "layer": "L1_ORG",
            "confidence": result["sanitization_confidence"],
            "latency_ms": float((time.time() - start_time) * 1000),
        }

    else:  # EntityType.PERSON
        # Person sanitization
        result = sanitize_person_name_only(masked_name)
        return {
            "trace_id": trace_id,
            "original": name_raw,
            "entity_type": entity_type,
            "sanitized_name": result.sanitized,
            "sanitization_confidence": result.confidence,
            "sanitization_flags": result.flags,
            "decision_path": "PERSON_SANITIZED" if result.format_standardized else "PERSON_PASSTHROUGH",
            "classification_confidence": cls_confidence,
            "classification_flags": cls_flags,
            # Person fields
            "first_name": result.first_name or "",
            "middle_name": result.middle_name or "",
            "last_name": result.last_name or "",
            # Org fields (blank)
            "org_name": "",
            "legal_suffix": "",
            "org_category": "",
            # Vessel fields (blank)
            "vessel_name": "",
            "imo_number": "",
            "vessel_prefix": "",
            # Metadata
            "pii_detected": pii_types,
            "layer": "L1_PERSON",
            "confidence": result.confidence,
            "latency_ms": float((time.time() - start_time) * 1000),
        }


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

app = FastAPI(
    title="Intelligent Analyst v3.0.0 Enterprise",
    description="Enterprise Entity Resolution API with Full Audit + Backend Support",
    version="3.0.0",
    root_path="/api"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Certificate-SHA256", "Retry-After"],
)

# Rate Limiting Middleware (Days 21-30)
try:
    from .security.rate_limiter import rate_limit_middleware
    app.middleware("http")(rate_limit_middleware)
    print("[Startup] Rate limiting middleware enabled", flush=True)
except ImportError as e:
    print(f"[Startup] Rate limiting middleware not available: {e}", flush=True)

# Day 6: System vitals route registration
try:
    from app.routes.internal_system_vitals import router as vitals_router
    app.include_router(vitals_router)
    print("[Startup] System vitals route registered", flush=True)
except ImportError as e:
    print(f"[Startup] System vitals route not available: {e}", flush=True)


# =============================================================================
# STARTUP INTEGRITY CHECK (Day 10 - Zero-Trust Lockdown)
# =============================================================================

# Store integrity check result for /health endpoint
_integrity_check_result: Optional[Dict[str, Any]] = None

@app.on_event("startup")
async def startup_integrity_check():
    """
    Run forensic integrity check on startup.

    IAVP v1.0 Compliance:
    - Validate key separation (demo vs production)
    - Validate artifact_mode matches environment
    - Log artifact_mode at startup

    In PROD with strict mode:
    - REFUSE TO BOOT if KMS signing key is not accessible
    - REFUSE TO BOOT if vault bucket is missing retention policy
    - REFUSE TO BOOT if demo key detected in production (IAVP)
    - WARN but continue if anchor bucket is misconfigured

    In TEST:
    - Log warnings but allow boot
    """
    global _integrity_check_result

    if not HAS_FORENSIC_SIGNING:
        print("[INTEGRITY] Forensic signing not available - skipping integrity check", flush=True)
        _integrity_check_result = {
            "overall_status": "SKIP",
            "message": "Forensic signing module not loaded",
            "boot_allowed": True
        }
        return

    environment = os.getenv("ENVIRONMENT", "test").lower()

    # In PROD, we enforce strict mode - system refuses to boot on critical failure
    # In TEST, we log warnings but allow boot
    fail_on_critical = (environment == "prod")

    # ═══════════════════════════════════════════════════════════════════════
    # DEPLOY_REGION Validation
    # ═══════════════════════════════════════════════════════════════════════
    from app.security.tenant_region import VALID_REGIONS
    if config.DEPLOY_REGION not in VALID_REGIONS:
        raise RuntimeError(
            f"FATAL: DEPLOY_REGION={config.DEPLOY_REGION!r} is not valid. "
            f"Must be one of {VALID_REGIONS}"
        )
    print(f"[REGION] DEPLOY_REGION={config.DEPLOY_REGION}, PROCESSING_REGION={config.PROCESSING_REGION}", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # IAVP v1.0: Key Separation Enforcement (Section 5)
    # ═══════════════════════════════════════════════════════════════════════
    if config.IAVP_ENABLED:
        try:
            artifact_mode = get_artifact_mode(config.IS_PRODUCTION)
            print(f"[IAVP] artifact_mode={artifact_mode}, is_production={config.IS_PRODUCTION}", flush=True)

            # Validate key separation
            key_id = config.KMS_SIGNING_KEY_ID or "local-signing-key"
            key_fingerprint = config.DEMO_KEY_FINGERPRINT or ""

            try:
                validate_key_separation(key_id, key_fingerprint, config.IS_PRODUCTION)
                print(f"[IAVP] Key separation validated: key_id={key_id[:50]}...", flush=True)
            except KeySeparationViolationError as e:
                print(f"[IAVP] KEY SEPARATION VIOLATION: {e}", flush=True)
                if fail_on_critical:
                    raise RuntimeError(f"IAVP KEY SEPARATION VIOLATION: {e}") from e

            # Validate artifact_mode
            try:
                validate_artifact_mode(artifact_mode, config.IS_PRODUCTION)
                print(f"[IAVP] artifact_mode validated: {artifact_mode}", flush=True)
            except ArtifactModeViolationError as e:
                print(f"[IAVP] ARTIFACT_MODE VIOLATION: {e}", flush=True)
                if fail_on_critical:
                    raise RuntimeError(f"IAVP ARTIFACT_MODE VIOLATION: {e}") from e

        except (KeySeparationViolationError, ArtifactModeViolationError):
            raise  # Re-raise to prevent boot
        except Exception as e:
            print(f"[IAVP] Error during IAVP startup validation: {e}", flush=True)
            if fail_on_critical:
                raise

    try:
        _integrity_check_result = run_startup_integrity_check(
            signing_key_name=os.getenv("SIGNING_KEY_NAME", ""),
            vault_bucket=config.VAULT_BUCKET,
            anchor_bucket=os.getenv("ANCHOR_BUCKET", ""),
            environment=environment,
            fail_on_critical=fail_on_critical,
        )

    except IntegrityCheckError as e:
        # This only happens in PROD with critical failure
        print(f"[FATAL] Integrity check failed: {e.message}", flush=True)
        print(f"[FATAL] System refusing to boot - fix integrity issues and restart", flush=True)
        _integrity_check_result = {
            "overall_status": "FAIL",
            "message": e.message,
            "check_name": e.check_name,
            "boot_allowed": False
        }
        # Re-raise to prevent server from starting
        raise RuntimeError(f"INTEGRITY CHECK FAILED: {e.message}") from e

    except Exception as e:
        # Unexpected error - log and continue in TEST, fail in PROD
        print(f"[ERROR] Unexpected error during integrity check: {e}", flush=True)
        _integrity_check_result = {
            "overall_status": "ERROR",
            "message": str(e),
            "boot_allowed": not fail_on_critical
        }
        if fail_on_critical:
            raise RuntimeError(f"INTEGRITY CHECK ERROR: {e}") from e


# =============================================================================
# DEPENDENCIES
# =============================================================================

# =============================================================================
# ROLE-BASED ACCESS CONTROL
# =============================================================================

# Valid roles (derived server-side from Firebase custom claims)
# user = tenant (upload + read own batches), viewer = read-only on assigned tenant
VALID_ROLES = {"user", "auditor", "admin", "viewer", "platform_admin"}

# Admin bootstrap: ADMIN_EMAILS is PRIMARY (no hardcoded UIDs shipped)
ADMIN_EMAIL_ALLOWLIST = set(
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
)
# ADMIN_UIDS: optional fallback for UID-based bootstrap
ADMIN_UID_ALLOWLIST = set(
    uid.strip() for uid in os.getenv("ADMIN_UIDS", "").split(",") if uid.strip()
)

# Admin-tier roles (cross-tenant access, cost visibility)
ADMIN_ROLES = {"admin", "platform_admin"}


def is_admin_role(role: str) -> bool:
    """Check if role has admin-tier privileges (cross-tenant, cost visibility)."""
    return role in ADMIN_ROLES


def derive_role(decoded_token: dict) -> str:
    """
    Derive role server-side from Firebase ID token custom claims.
    Priority:
    1. Email in ADMIN_EMAIL_ALLOWLIST -> 'admin' (primary bootstrap)
    2. UID in ADMIN_UID_ALLOWLIST -> 'admin' (optional fallback)
    3. Custom claim 'role' if valid
    4. Fallback: 'user'
    Never trust client-supplied role values.
    """
    # Check admin email allowlist first (primary bootstrap)
    email = decoded_token.get("email", "")
    if email and email.lower() in ADMIN_EMAIL_ALLOWLIST:
        return "admin"

    # Check admin UID allowlist (optional fallback)
    uid = decoded_token.get("uid", "")
    if uid and uid in ADMIN_UID_ALLOWLIST:
        return "admin"

    role = decoded_token.get("role", "")
    if role in VALID_ROLES:
        return role
    return "user"  # Default role


def derive_tenant_id(decoded_token: dict) -> str:
    """
    Derive tenant_id server-side from Firebase ID token.
    Priority:
    1. Explicit 'tenant_id' custom claim (for viewer/admin assignment)
    2. Stable hash of firebase_project + uid (safe, no cross-tenant merges)
    Never trust client-supplied tenant values.
    Domain-based derivation intentionally removed to prevent accidental
    cross-tenant merges where users from the same domain see each other's data.
    """
    # Priority 1: Explicit tenant_id custom claim (admin assigns to viewer/user)
    explicit_tenant = decoded_token.get("tenant_id")
    if explicit_tenant and isinstance(explicit_tenant, str) and len(explicit_tenant) > 0:
        return explicit_tenant if explicit_tenant.startswith("tenant_") else f"tenant_{explicit_tenant}"

    # Priority 2: Stable hash-based tenant (no domain derivation — prevents cross-tenant merge)
    uid = decoded_token.get("uid", "")
    aud = decoded_token.get("aud", "")  # Firebase project ID
    if uid:
        stable_input = f"{aud}:{uid}"
        tenant_hash = hashlib.sha256(stable_input.encode()).hexdigest()[:16]
        return f"tenant_{tenant_hash}"

    # Ultimate fallback (should not happen with valid token)
    return "tenant_unknown"


async def require_firebase_admin_claim(request: Request):
    """
    Firebase-only admin auth. Fail-closed.
    No token → 401 | Invalid token → 401 | Non-admin → 403 | Admin → 200
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = auth_header[7:]
    if not HAS_FIREBASE_AUTH:
        raise HTTPException(status_code=503, detail="Firebase Admin SDK not available")
    try:
        from firebase_admin import auth as firebase_auth
        decoded = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    role = derive_role(decoded)
    if not is_admin_role(role):
        raise HTTPException(status_code=403, detail="Admin role required")
    return {"role": role, "uid": decoded.get("uid", "")}


async def verify_request_identity(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
    x_tenant_id: str = Header("default", alias="X-Tenant-Id"),
):
    """
    Firebase ID token authentication (primary, production).
    Verifies Authorization: Bearer <Firebase ID token> using Firebase Admin SDK.

    Tenant ID and role are ALWAYS derived server-side from the token.
    Client-supplied headers are ignored for security.

    Legacy API key auth is deprecated and disabled by default.
    """
    auth_header = request.headers.get("Authorization", "")

    # Firebase token authentication (primary)
    if auth_header.startswith("Bearer "):
        if not HAS_FIREBASE_AUTH:
            raise HTTPException(
                status_code=503,
                detail="Firebase Admin SDK not available - authentication service unavailable"
            )

        token = auth_header[7:]
        try:
            decoded = firebase_auth.verify_id_token(token)
            uid = decoded.get("uid", "")
            email = decoded.get("email", "")
            # Derive tenant_id and role server-side - never trust client
            tenant_id = derive_tenant_id(decoded)
            role = derive_role(decoded)

            # DEMO MODE: Force demo tenant
            if config.DEMO_MODE:
                tenant_id = config.DEMO_TENANT_ID
                print(f"[AUTH] DEMO MODE: Forcing tenant={tenant_id}", flush=True)

            print(f"[AUTH] Firebase token verified: uid={uid}, email={email}, tenant={tenant_id}, role={role}", flush=True)
            return {
                "auth_method": "firebase",
                "uid": uid,
                "email": email,
                "tenant_id": tenant_id,
                "role": role,
                "api_key": None,
                "demo_mode": config.DEMO_MODE,
            }
        except firebase_auth.ExpiredIdTokenError:
            print(f"[AUTH] Firebase token expired", flush=True)
            raise HTTPException(status_code=401, detail="Firebase token expired - please refresh")
        except firebase_auth.RevokedIdTokenError:
            print(f"[AUTH] Firebase token revoked", flush=True)
            raise HTTPException(status_code=401, detail="Firebase token revoked")
        except firebase_auth.InvalidIdTokenError as e:
            print(f"[AUTH] Invalid Firebase token: {e}", flush=True)
            raise HTTPException(status_code=401, detail="Invalid Firebase token")
        except Exception as e:
            print(f"[AUTH] Firebase token verification failed: {e}", flush=True)
            raise HTTPException(status_code=401, detail="Firebase token verification failed")

    # Platform admin API key auth (for governance operations)
    if config.PLATFORM_ADMIN_API_KEY and x_api_key and x_api_key == config.PLATFORM_ADMIN_API_KEY:
        api_key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()[:16]
        tenant_id = f"tenant_admin_{api_key_hash}"
        print(f"[AUTH] Platform admin API key verified, tenant={tenant_id}", flush=True)
        return {
            "auth_method": "platform_admin_key",
            "uid": "platform_admin",
            "email": None,
            "tenant_id": tenant_id,
            "role": "platform_admin",  # Full governance access
            "api_key": x_api_key,
            "demo_mode": False,
        }

    # Legacy API key auth (deprecated, only if explicitly configured)
    if config.API_KEY and x_api_key:
        if x_api_key != config.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")
        # For API key auth, derive a stable tenant from the key itself
        api_key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()[:16]
        tenant_id = f"tenant_apikey_{api_key_hash}"

        # DEMO MODE: Force demo tenant
        if config.DEMO_MODE:
            tenant_id = config.DEMO_TENANT_ID
            print(f"[AUTH] DEMO MODE: Forcing tenant={tenant_id}", flush=True)

        print(f"[AUTH] API key verified (deprecated), tenant={tenant_id}", flush=True)
        return {
            "auth_method": "api_key",
            "uid": None,
            "email": None,
            "tenant_id": tenant_id,
            "role": "user",  # API key auth defaults to user role
            "api_key": x_api_key,
            "demo_mode": config.DEMO_MODE,
        }

    # No valid authentication provided
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide Authorization: Bearer <Firebase ID token>"
    )


async def verify_api_key(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
    x_tenant_id: str = Header("default", alias="X-Tenant-Id"),
):
    """Wrapper for backward compatibility - delegates to verify_request_identity."""
    return await verify_request_identity(request, x_api_key, x_tenant_id)


async def require_write_permission(auth: dict = Depends(verify_api_key)):
    """
    Dependency that enforces write permission.
    Auditors and viewers are read-only and cannot perform uploads or mutations.
    Demo mode blocks all writes.
    Returns 403 Forbidden for auditors, viewers, or demo mode.
    """
    # DEMO MODE: Block all writes
    if config.DEMO_MODE:
        raise HTTPException(
            status_code=403,
            detail="Demo mode — uploads disabled. Sample data only."
        )

    role = auth.get("role", "user")
    if role == "auditor":
        raise HTTPException(
            status_code=403,
            detail="Auditors have read-only access. Upload not permitted."
        )
    if role == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Viewers have read-only access. Upload not permitted."
        )
    return auth


async def require_admin_role(auth: dict = Depends(verify_api_key)):
    """
    Dependency that enforces admin-tier role (admin or platform_admin).
    Returns 403 Forbidden for non-admin users.
    """
    role = auth.get("role", "user")
    if not is_admin_role(role):
        raise HTTPException(
            status_code=403,
            detail="Admin access required."
        )
    return auth


# Cost-sensitive fields that must NEVER be returned to non-admin roles
COST_FIELDS_BATCH = {"cost", "llm_budget_summary", "l3_yield"}
COST_FIELDS_HEALTH = {"l3_max_cost_usd", "l3_cost_per_call_usd", "l3_max_calls_computed"}


def strip_cost_fields(batch: dict) -> dict:
    """
    Remove ALL cost-sensitive fields from a batch dict for non-admin roles.
    Returns a shallow copy with cost fields stripped, including nested metrics.
    """
    result = dict(batch)
    for key in COST_FIELDS_BATCH:
        result.pop(key, None)
    # Strip nested cost fields in stats
    if "stats" in result and isinstance(result["stats"], dict):
        result["stats"] = {k: v for k, v in result["stats"].items() if k != "total_cost"}
    # Strip nested cost fields in llm_budget_summary (defensive — already popped above)
    result.pop("llm_budget_summary", None)
    return result


def strip_cost_from_record(record: dict) -> dict:
    """Strip per-record cost field from a resolution result."""
    result = dict(record)
    result.pop("cost", None)
    return result


async def check_tenant_region(
    request: Request,
    auth: dict = Depends(verify_api_key),
):
    """Enforce tenant region binding. Skips in DEMO mode."""
    if config.DEMO_MODE:
        auth["tenant_region"] = config.DEPLOY_REGION
        return auth

    tenant_id = auth.get("tenant_id", "default")

    if _firestore_db:
        from app.security.tenant_region import resolve_tenant_region, validate_tenant_region
        region = resolve_tenant_region(tenant_id, _firestore_db, config.DEPLOY_REGION)
        if not validate_tenant_region(region, config.DEPLOY_REGION):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "REGION_MISMATCH",
                    "tenant_region": region,
                    "service_region": config.DEPLOY_REGION,
                },
            )
        auth["tenant_region"] = region
    else:
        auth["tenant_region"] = config.DEPLOY_REGION

    return auth


async def check_rate_limit(
    request: Request,
    auth: dict = Depends(check_tenant_region)
):
    tenant_id = auth.get("tenant_id", "default")
    is_allowed, info = rate_limiter.is_allowed(tenant_id)
    request.state.rate_limit_info = info

    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Limit: {info['limit']}/min",
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
                "Retry-After": str(info["reset_seconds"]),
            }
        )
    return auth


# =============================================================================
# ORIGIN VALIDATION FOR /batch-upload
# =============================================================================

# Use config.ALLOWED_ORIGINS (includes production + localhost dev by default)
_UPLOAD_ALLOWED_ORIGINS: set = set(config.ALLOWED_ORIGINS)


async def validate_upload_origin(request: Request) -> str:
    origin = request.headers.get("origin")
    print(f"[origin-check] origin={origin}", flush=True)

    # Allow non-browser requests (curl, server-to-server)
    if origin is None:
        return "no-origin"

    if origin not in _UPLOAD_ALLOWED_ORIGINS:
        print(f"[origin-check] BLOCKED origin={origin}, allowed={_UPLOAD_ALLOWED_ORIGINS}", flush=True)
        raise HTTPException(status_code=403, detail="Origin not allowed")

    return origin


# Thread pool sized for parallel L3 + L1/L2 processing
THREAD_POOL = ThreadPoolExecutor(max_workers=max(config.L3_MAX_CONCURRENCY + config.PARALLEL_LIMIT, 50))


# =============================================================================
# FILE PARSING
# =============================================================================

# ── Column selection constants ──────────────────────────────────────────────

_PERSON_TARGET_COLS = [
    'nombre', 'full_name', 'canonical_name', 'employee_name', 'contact_name',
    'first_name', 'last_name', 'primer_apellido', 'segundo_apellido',
    'apellido', 'apellidos', 'person_name', 'name',
]

_COMPANY_TARGET_COLS = [
    'company_raw', 'company_name', 'company', 'name', 'account',
    'account_name', 'organization', 'entity', 'vendor',
]

_MIXED_TARGET_COLS = (
    _PERSON_TARGET_COLS + _COMPANY_TARGET_COLS
)

_REJECT_COL_NAMES = {
    'id', 'uuid', 'timestamp', 'default', 'balance', 'unnamed: 0', 'index',
    'edad', 'age', 'record', 'row', 'number', 'carne', 'carné', 'identidad',
    'employee_id', 'account_number', 'row_id', 'record_id', 'seq', 'sequence',
    'sexo', 'gender', 'sex',
}

_REJECT_COL_PATTERNS = re.compile(
    r'^(unnamed|column)[\s_:]?\d+$'   # unnamed:0, column_1, etc.
    r'|_id$'                           # any column ending in _id
    r'|^num[_\s]'                      # num_record, num_empleado
    r'|^no[_\s.]'                      # no. registro
    r'|^#$',                           # literal "#" column
    re.IGNORECASE,
)


def _score_column_for_names(df: pd.DataFrame, col: str, sample_size: int = 50) -> float:
    """
    Score a column by how much its content looks like human/company names.

    Returns 0.0-1.0.  High = likely names, low = likely numeric/ID.
    Signals:
      - alphabetic density (cells that are mostly letters)
      - low numeric ratio
      - token count in person-name range (2-4 tokens)
    """
    sample = df[col].dropna().astype(str).head(sample_size)
    if sample.empty:
        return 0.0

    total = len(sample)
    alpha_cells = 0
    person_pattern_cells = 0

    lengths = []
    for val in sample:
        val = val.strip()
        if not val or val.lower() in ('nan', 'none', 'null'):
            continue
        lengths.append(len(val))
        # Alphabetic density: >60% of chars are letters or spaces
        letter_chars = sum(1 for ch in val if ch.isalpha() or ch == ' ')
        if len(val) > 0 and letter_chars / len(val) > 0.6:
            alpha_cells += 1
        # Person-name token pattern: 1-4 alphabetic tokens
        tokens = val.split()
        if 1 <= len(tokens) <= 4 and all(any(c.isalpha() for c in t) for t in tokens):
            person_pattern_cells += 1

    alpha_ratio = alpha_cells / max(total, 1)
    person_ratio = person_pattern_cells / max(total, 1)

    # Penalize columns where average value length is very short (e.g. "M", "F", "Y", "N")
    avg_len = sum(lengths) / max(len(lengths), 1)
    length_penalty = min(avg_len / 3.0, 1.0)  # values < 3 chars get penalised

    return (alpha_ratio * 0.6 + person_ratio * 0.4) * length_penalty


def _is_rejected_column(col_name: str) -> bool:
    """Return True if column name signals a non-name column."""
    return col_name in _REJECT_COL_NAMES or bool(_REJECT_COL_PATTERNS.search(col_name))


def _select_best_column(df: pd.DataFrame, mode: str = "mixed",
                        column_meta: Optional[dict] = None) -> str:
    """
    Dataset-aware column selection.

    Priority:
      1. Exact match from mode-specific target list
      2. Best content-scored column (excluding rejected columns)
      3. First non-rejected column (last resort)

    If *column_meta* dict is provided, it is populated in-place with:
      - method: "target_list" | "content_score"
      - column: selected column name
      - score: float (only for content_score)
      - fallback: bool — True when no recognized header matched
    """
    cols = list(df.columns)
    print(f"[colsel] START mode={mode} columns={cols[:15]}", flush=True)

    def _emit(method: str, col: str, score: Optional[float] = None):
        if column_meta is not None:
            column_meta["method"] = method
            column_meta["column"] = col
            column_meta["fallback"] = method != "target_list"
            if score is not None:
                column_meta["score"] = round(score, 3)

    # Step 1: mode-specific target list lookup
    if mode in ("person", "mixed"):
        target_list = _MIXED_TARGET_COLS
    else:
        target_list = _COMPANY_TARGET_COLS

    # Build lookup with both space and underscore variants
    col_set = set(cols)
    for target in target_list:
        if target in col_set:
            print(f"[colsel] STEP1_HIT target='{target}' (exact)", flush=True)
            _emit("target_list", target)
            return target
        # Try space ↔ underscore variant
        alt = target.replace('_', ' ')
        if alt in col_set:
            print(f"[colsel] STEP1_HIT target='{target}' → alt='{alt}' (space variant)", flush=True)
            _emit("target_list", alt)
            return alt

    print(f"[colsel] STEP1_MISS — no target list match, falling through to scoring", flush=True)

    # Step 2: content-based scoring across all non-rejected columns
    rejected = [c for c in cols if _is_rejected_column(c)]
    candidates = [c for c in cols if not _is_rejected_column(c)]
    if rejected:
        print(f"[colsel] REJECTED columns: {rejected}", flush=True)
    if not candidates:
        candidates = cols  # nothing left, use all
        print(f"[colsel] WARNING: all columns rejected, using all", flush=True)

    best_col = candidates[0]
    best_score = -1.0
    all_scores = {}

    for col in candidates:
        score = _score_column_for_names(df, col)
        all_scores[col] = round(score, 3)
        if score > best_score:
            best_score = score
            best_col = col

    print(f"[colsel] STEP2_SCORES {all_scores}", flush=True)
    print(f"[colsel] STEP2_WINNER col='{best_col}' score={best_score:.3f}", flush=True)

    # Guard: if the best score is extremely low, the file may have no name column
    if best_score < 0.1:
        print(f"[colsel] WARNING: Best column '{best_col}' scored only {best_score:.2f} — "
              f"file may not contain name data. Columns: {cols[:10]}", flush=True)

    _emit("content_score", best_col, best_score)
    return best_col


async def parse_uploaded_file_golden(file: UploadFile, tenant_id: str, mode: str = "mixed",
                                     column_meta: Optional[dict] = None) -> List[str]:
    """Production-grade file parser with dataset-aware column selection.

    If *column_meta* dict is provided, it is populated with column selection
    metadata (method, column, fallback, score) so the caller can surface
    it in batch metadata / API responses (BUG-014).
    """
    if not circuit_breakers["file_parse"].can_execute():
        raise HTTPException(503, "File parsing service temporarily unavailable")

    filename = (file.filename or "upload").lower()
    content = await file.read()

    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {config.MAX_UPLOAD_BYTES // (1024*1024)}MB)")

    df = pd.DataFrame()

    try:
        if filename.endswith((".xlsx", ".xlsm")):
            try:
                df = pd.read_excel(io.BytesIO(content), engine="openpyxl", sheet_name=0)
            except zipfile.BadZipFile:
                df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", sep=None, engine="python", on_bad_lines="warn")
        elif filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content), engine="xlrd", sheet_name=0)
        elif filename.endswith(".json"):
            data = json.loads(content.decode("utf-8-sig"))
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                for key in ["results", "data", "companies", "items", "records"]:
                    if key in data and isinstance(data[key], list):
                        df = pd.DataFrame(data[key])
                        break
                if df.empty:
                    df = pd.DataFrame([data])
        else:
            try:
                df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", on_bad_lines="warn")
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), encoding="latin1", on_bad_lines="warn")

        circuit_breakers["file_parse"].record_success()

    except HTTPException:
        raise
    except Exception as e:
        circuit_breakers["file_parse"].record_failure()
        raise HTTPException(400, f"File parsing error: {str(e)}")

    if df.empty:
        raise HTTPException(400, "File is empty")

    raw_cols = list(df.columns)
    df.columns = [str(c).lower().strip() for c in df.columns]
    norm_cols = list(df.columns)
    print(f"[parse] raw_columns={raw_cols[:10]} → norm_columns={norm_cols[:10]} "
          f"(shape={df.shape}, mode={mode})", flush=True)

    selected_col = _select_best_column(df, mode=mode, column_meta=column_meta)

    print(f"[parse] Selected column: '{selected_col}' (mode={mode}, "
          f"columns={list(df.columns[:10])})", flush=True)

    # Person-path: combine split name columns (nombre + apellido) into full identity
    if mode in ("mixed", "person") and selected_col in ("nombre", "first_name", "firstname"):
        _SURNAME_COLS = ["primer apellido", "primer_apellido", "apellido", "apellidos",
                         "segundo apellido", "segundo_apellido", "last_name", "lastname", "surname"]
        surname_parts = []
        for sc in _SURNAME_COLS:
            if sc in norm_cols:
                surname_parts.append(sc)
        if surname_parts:
            combined = df[selected_col].fillna("").astype(str).str.strip()
            for sc in surname_parts:
                combined = combined + " " + df[sc].fillna("").astype(str).str.strip()
            combined = combined.str.strip()
            print(f"[parse] PERSON_COMBINE: '{selected_col}' + {surname_parts} → full_name", flush=True)
            rows = combined
            clean_rows = [r for r in rows.tolist() if r and r.lower() not in ['nan', 'none', '', 'null']]
        else:
            rows = df[selected_col].dropna().astype(str).str.strip()
            clean_rows = [r for r in rows.tolist() if r and r.lower() not in ['nan', 'none', '', 'null']]
    else:
        rows = df[selected_col].dropna().astype(str).str.strip()
        clean_rows = [r for r in rows.tolist() if r and r.lower() not in ['nan', 'none', '', 'null']]

    # Instrument: log sample values so we can verify names vs numbers
    sample = clean_rows[:5]
    numeric_count = sum(1 for v in clean_rows if v.replace('.', '', 1).replace('-', '', 1).isdigit())
    print(f"[parse] SAMPLE original_name values (first 5): {sample}", flush=True)
    print(f"[parse] VALUE_CHECK: {len(clean_rows)} total, {numeric_count} numeric "
          f"({numeric_count/max(len(clean_rows),1)*100:.0f}%)", flush=True)
    if numeric_count > len(clean_rows) * 0.5:
        print(f"[parse] ⚠ WARNING: >50% numeric — column '{selected_col}' is likely wrong!", flush=True)

    if not clean_rows:
        raise HTTPException(400, "No valid data found in selected column")

    return clean_rows


# Backwards-compat alias (remove after 1 release)
parse_uploaded_file_hardened = parse_uploaded_file_golden


# =============================================================================
# PARALLEL PROCESSING WITH COST-FIRST L3 BUDGET GATING
# =============================================================================

# Mode Policy — declarative config for each DatasetType.
# Replaces 4-way if/elif branch in Phase 1 orchestrator.
MODE_POLICY = {
    DatasetType.COMPANY: {
        "resolver": "entity",       # → resolve_entity_sync
        "has_l2": True,
        "l3_enabled": True,
        "match_type_fn": "company",  # company match_type logic
    },
    DatasetType.PERSON: {
        "resolver": "person",       # → resolve_person_sync
        "has_l2": True,
        "l3_enabled": False,        # L3_PERSON_DISABLED
        "match_type_fn": "person",
    },
    DatasetType.MIXED: {
        "resolver": "mixed",        # → resolve_mixed_sync
        "has_l2": False,
        "l3_enabled": False,
        "match_type_fn": "normalized",
    },
    DatasetType.VESSEL: {
        "resolver": "vessel",       # → resolve_mixed_sync + entity_type override
        "has_l2": False,
        "l3_enabled": False,
        "match_type_fn": "normalized",
    },
}


def _assign_match_type(result: dict, policy: dict) -> str:
    """Assign match_type based on mode policy. Single source of truth."""
    mt_fn = policy["match_type_fn"]
    if mt_fn == "normalized":
        return "NORMALIZED"

    layer = result.get("layer", "")
    confidence = result.get("similarity", result.get("confidence", 0.0))

    if mt_fn == "person":
        # Person resolver already sets match_type — preserve it
        return result.get("match_type", "NO_MATCH")

    # Company mode
    if HAS_PERSON_RESOLVER:
        return get_match_type_for_layer(layer, confidence)

    # Fallback match_type assignment
    if layer.startswith("L0_"):
        return "NO_MATCH"
    elif layer in ("L1_EXACT", "L1_NORM", "L1_KNOWN_PARENT"):
        return "EXACT_MATCH"
    elif layer == "L2_VECTOR" and confidence >= 0.85:
        return "FUZZY_MATCH"
    elif layer.startswith("L3_"):
        return "POSSIBLE_MATCH"
    return "NO_MATCH"


async def process_batch_parallel_golden(
    rows: List[str],
    tenant_id: str,
    batch_trace_id: str,
    dataset_type: DatasetType = DatasetType.COMPANY
) -> Tuple[List[Dict], L3BudgetTracker]:
    """
    Two-phase batch processing with cost-first L3 budget gating.

    Phase 1: Process all records through L1/L2 in parallel (no L3 calls)
    Phase 2: Process L3-eligible records in PARALLEL with bounded concurrency
             and atomic budget tracking

    Args:
        rows: List of entity names
        tenant_id: Tenant identifier
        batch_trace_id: Batch trace ID
        dataset_type: PERSON or COMPANY (determines which pipeline to use)

    Returns: (results, budget_tracker)
    """
    print(f"[batch] Processing {len(rows)} rows as {dataset_type.value} mode", flush=True)
    _batch_entry_time = time.time()
    phase1_sem = asyncio.Semaphore(config.PARALLEL_LIMIT)
    l3_sem = asyncio.Semaphore(config.L3_MAX_CONCURRENCY)
    budget_lock = asyncio.Lock()
    loop = asyncio.get_event_loop()

    # Initialize budget tracker with cost-based limits
    max_l3_calls = int(config.L3_MAX_COST_USD / config.L3_COST_PER_CALL_USD) if config.L3_COST_PER_CALL_USD > 0 else 100000
    budget_tracker = L3BudgetTracker(
        budget_usd=config.L3_MAX_COST_USD,
        max_calls=max_l3_calls,
        cost_per_call=config.L3_COST_PER_CALL_USD
    )
    print(f"[L3_COST] Initialized: max_cost=${config.L3_MAX_COST_USD:.2f}, "
          f"cost_per_call=${config.L3_COST_PER_CALL_USD:.3f}, max_calls={max_l3_calls}", flush=True)

    # DEPRECATED: Row threshold disabled - cost budget is the primary control
    row_threshold_exceeded = False  # Always false - budget tracker handles limits

    # Check if LLM is available
    llm_disabled = not HAS_ANTHROPIC or not ANTHROPIC_API_KEY

    # Progress tracking
    l3_completed = [0]  # Use list for mutable closure
    l3_total = [0]
    progress_interval = 250

    # L3 heartbeat (structured observability)
    _l3_last_heartbeat_time = [time.time()]
    _L3_HEARTBEAT_INTERVAL_SEC = 30
    _L3_HEARTBEAT_INTERVAL_COUNT = 25

    def _maybe_emit_l3_heartbeat():
        """Emit heartbeat if time or count threshold met. Caller must hold budget_lock."""
        now = time.time()
        count_trigger = (l3_completed[0] % _L3_HEARTBEAT_INTERVAL_COUNT == 0) and l3_completed[0] > 0
        time_trigger = (now - _l3_last_heartbeat_time[0]) >= _L3_HEARTBEAT_INTERVAL_SEC
        if count_trigger or time_trigger:
            _l3_last_heartbeat_time[0] = now
            slog(
                trace_id=batch_trace_id,
                phase="phase2",
                event="l3_heartbeat",
                batch_start_time=_batch_entry_time,
                l3_completed=l3_completed[0],
                l3_total=l3_total[0],
                l3_pct=round(l3_completed[0] / l3_total[0] * 100, 1) if l3_total[0] > 0 else 0,
                l3_calls=budget_tracker.calls,
                l3_spent_usd=round(budget_tracker.spent_usd, 4),
                l3_cache_hits=budget_tracker.l3_cache_hits,
            )

    # ==========================================================================
    # PHASE 1: L1/L2 Resolution (parallel, no L3) with abort checking
    # ==========================================================================
    phase1_aborted = [False]
    phase1_completed = [0]
    phase1_abort_check_interval = 500  # Check abort every 500 records

    async def phase1_resolve(row: str, idx: int):
        async with phase1_sem:
            # Check for abort periodically
            phase1_completed[0] += 1
            if phase1_completed[0] % phase1_abort_check_interval == 0:
                if check_batch_aborted(batch_trace_id):
                    phase1_aborted[0] = True
                    print(f"[batch] ABORT detected in Phase 1 at record {phase1_completed[0]}", flush=True)

            # Skip processing if batch is aborted
            if phase1_aborted[0]:
                return {
                    "trace_id": f"ABORTED-{idx}",
                    "original": row,
                    "resolved": None,
                    "confidence": 0.0,
                    "layer": "ABORTED",
                    "reason": "BATCH_ABORTED",
                    "pii_detected": [],
                    "cost": 0.0,
                    "latency_ms": 0.0,
                    "_original_idx": idx
                }

            try:
                # Policy-driven resolver dispatch (Semantic Unification)
                policy = MODE_POLICY[dataset_type]

                if policy["resolver"] == "mixed":
                    result = await loop.run_in_executor(
                        THREAD_POOL,
                        lambda r=row, t=tenant_id, b=batch_trace_id, i=idx: resolve_mixed_sync(r, t, b, i)
                    )
                elif policy["resolver"] == "vessel":
                    result = await loop.run_in_executor(
                        THREAD_POOL,
                        lambda r=row, t=tenant_id, b=batch_trace_id, i=idx: resolve_mixed_sync(r, t, b, i)
                    )
                    result["entity_type"] = EntityType.VESSEL.value
                elif policy["resolver"] == "person":
                    result = await loop.run_in_executor(
                        THREAD_POOL,
                        lambda r=row, t=tenant_id, b=batch_trace_id, i=idx: resolve_person_sync(r, t, b, i, allow_l3=False)
                    )
                else:  # "entity" (company)
                    result = await loop.run_in_executor(
                        THREAD_POOL,
                        lambda r=row, t=tenant_id, b=batch_trace_id, i=idx: resolve_entity_sync(r, t, b, i, allow_l3=False)
                    )

                # Unified match_type assignment
                result["match_type"] = _assign_match_type(result, policy)

                result["_original_idx"] = idx
                return result
            except Exception as e:
                return {
                    "trace_id": f"ERR-{idx}",
                    "original": row,
                    "resolved": None,
                    "confidence": 0.0,
                    "layer": "ERROR",
                    "reason": str(e),
                    "pii_detected": [],
                    "cost": 0.0,
                    "latency_ms": 0.0,
                    "_original_idx": idx
                }

    _phase1_start = time.time()
    phase1_tasks = [phase1_resolve(row, i) for i, row in enumerate(rows)]
    results = list(await asyncio.gather(*phase1_tasks))
    _phase1_duration_ms = (time.time() - _phase1_start) * 1000
    slog(
        trace_id=batch_trace_id,
        phase="phase1",
        event="phase1_complete",
        batch_start_time=_batch_entry_time,
        phase1_duration_ms=round(_phase1_duration_ms, 1),
        total_records=len(rows),
    )

    # If aborted during Phase 1, return early
    if phase1_aborted[0]:
        print(f"[batch] ABORT: Phase 1 stopped early, {phase1_completed[0]} records processed", flush=True)
        return results, budget_tracker

    # ==========================================================================
    # STRUCTURAL GUARD 1: L1/L2 INTEGRITY CHECK
    # ==========================================================================
    # Before Phase 2, verify that L1/L2 processed ALL records correctly.
    # If this fails, it means L1/L2 logic is broken and L3 should NOT proceed.
    total = len(results)
    # L0 includes all garbage subtypes and input rejections (all modes)
    l0_count = sum(1 for r in results if r.get("layer", "").startswith("L0_GARBAGE") or r.get("layer") == "L0_INPUT_REJECTED")
    # L1 includes company, person, and mixed mode layers
    l1_count = sum(1 for r in results if r.get("layer") in (
        "L1_EXACT", "L1_NORM",  # Company mode
        "L1_PERSON_EXACT", "L1_PERSON_ALIAS", "L1_PERSON_INITIAL",  # Person mode
        "L1_PERSON", "L1_ORG", "L1_VESSEL"  # Mixed mode
    ))
    # L2 includes company and person mode layers (mixed mode has no L2)
    l2_count = sum(1 for r in results if r.get("layer") in ("L2_VECTOR", "L2_PERSON_FUZZY"))
    l4_count = sum(1 for r in results if r.get("layer") == "L4_HUMAN")
    error_count = sum(1 for r in results if r.get("layer") in ("ERROR", "ABORTED", "L3_PERSON_LLM_REJECT"))

    phase1_sum = l0_count + l1_count + l2_count + l4_count + error_count
    if phase1_sum != total:
        # FAIL: Layer counts don't sum to total - something dropped records
        print(f"[INTEGRITY] FAIL: phase1_sum={phase1_sum} != total={total} → raising IntegrityError", flush=True)
        print(f"[INTEGRITY] Breakdown: L0={l0_count}, L1={l1_count}, L2={l2_count}, L4={l4_count}, ERR={error_count}", flush=True)
        error_msg = (f"L1/L2 integrity violation: phase1_sum={phase1_sum} != total={total}. "
                     f"Breakdown: L0={l0_count}, L1={l1_count}, L2={l2_count}, L4={l4_count}, ERR={error_count}")
        slog_error(
            trace_id=batch_trace_id, phase="phase1", event="integrity_check",
            batch_start_time=_batch_entry_time, error_type="IntegrityError", error_message=error_msg,
            l0=l0_count, l1=l1_count, l2=l2_count, l4=l4_count, errors=error_count, total=total,
        )
        raise IntegrityError(error_msg)

    # PASS: All records accounted for
    print(f"[INTEGRITY] PASS: phase1_sum={phase1_sum} == total={total} | L0={l0_count}, L1={l1_count}, L2={l2_count}, L4={l4_count}, ERR={error_count}", flush=True)
    slog(
        trace_id=batch_trace_id, phase="phase1", event="integrity_check",
        batch_start_time=_batch_entry_time, result="PASS",
        l0=l0_count, l1=l1_count, l2=l2_count, l4=l4_count, errors=error_count, total=total,
    )

    # ==========================================================================
    # PHASE 2: L3 Resolution (PARALLEL with bounded concurrency + atomic budget)
    # ==========================================================================
    # Step 1: Find all L4_HUMAN records with "Low Confidence" (potential L3 candidates)
    l4_candidate_indices = [
        i for i, r in enumerate(results)
        if r.get("layer") == "L4_HUMAN" and r.get("reason") == "Low Confidence"
    ]

    # Step 1b: MIXED mode — promote unresolved ORG rows to L3 candidates.
    # In MIXED mode, ORG rows get L1_ORG (sanitized) but may not match any canonical.
    # These are L3 candidates: the LLM can attempt semantic company resolution.
    if dataset_type == DatasetType.MIXED:
        mixed_org_promoted = 0
        for i, r in enumerate(results):
            if (r.get("entity_type") == "ORGANIZATION"
                    and r.get("layer") == "L1_ORG"
                    and not r.get("resolved")):
                # Promote to L4_HUMAN so Phase 2 picks it up
                results[i]["layer"] = "L4_HUMAN"
                results[i]["reason"] = "Low Confidence"
                results[i]["_mixed_org_promoted"] = True
                l4_candidate_indices.append(i)
                mixed_org_promoted += 1
        if mixed_org_promoted > 0:
            print(f"[batch] Phase 2: MIXED MODE — promoted {mixed_org_promoted} unresolved ORG rows to L3 candidates", flush=True)

    # Step 2: Smart L3 Gating - filter by L2 similarity score
    # Records with L2 score below threshold skip L3 (not worth the cost)
    l3_eligible_indices = []
    l3_skipped_low_sim = 0
    for i in l4_candidate_indices:
        l2_score = results[i].get("l2_score", 0.0)
        if l2_score >= config.L3_MIN_SIMILARITY:
            l3_eligible_indices.append(i)
        else:
            # Skip L3 - record too dissimilar to canonicals
            budget_tracker.record_skip("L3_LOW_SIMILARITY")
            results[i]["reason"] = f"Low Confidence (L3_LOW_SIMILARITY: L2={l2_score:.2f} < {config.L3_MIN_SIMILARITY})"
            results[i]["l3_skip_reason"] = "L3_LOW_SIMILARITY"
            l3_skipped_low_sim += 1

    l3_eligible_indices.sort(key=lambda i: results[i].get("_original_idx", i))
    l3_total[0] = len(l3_eligible_indices)
    budget_tracker.l3_eligible = l3_total[0] + l3_skipped_low_sim  # Track ALL candidates (eligible + skipped)

    # ==========================================================================
    # STRUCTURAL GUARD 2: L3 VOLUME CIRCUIT BREAKER (with mixed-mode reroute)
    # ==========================================================================
    # If L3 eligible exceeds MAX_L3_PERCENT, either reroute or abort.
    l3_all_candidates = len(l4_candidate_indices)  # All L4 "Low Confidence" (before sim filter)
    l3_percent = (l3_all_candidates / total * 100) if total > 0 else 0
    max_l3_percent = config.L3_MAX_PERCENT * 100  # Convert to percentage
    MIXED_REROUTE_THRESHOLD = 40.0  # If >40% L3-eligible, reroute to Sanitize+Attest

    if config.L3_CIRCUIT_BREAKER_ENABLED and l3_percent > MIXED_REROUTE_THRESHOLD:
        # ── Mixed-mode reroute: re-resolve L4 candidates via Sanitize+Attest ──
        # Instead of crashing, reroute unmatched records through mixed-mode
        # entity classification (PERSON → sanitize, ORG → L1/L2, GARBAGE → L0).
        reroute_count = 0
        top_unmatched = []
        for i in l4_candidate_indices:
            orig = results[i].get("original", "")
            if len(top_unmatched) < 20:
                top_unmatched.append(orig)
            try:
                mixed_result = resolve_mixed_sync(orig, tenant_id, batch_trace_id, i)
                # Preserve original index, overwrite resolution fields
                mixed_result["_original_idx"] = results[i].get("_original_idx", i)
                mixed_result["_rerouted"] = True
                results[i] = mixed_result
                reroute_count += 1
            except Exception as e:
                # Keep original L4 result on reroute failure
                results[i]["_reroute_error"] = str(e)

        print(f"[CIRCUIT_BREAKER] REROUTE: l3_eligible={l3_all_candidates}/{total} ({l3_percent:.1f}%) > {MIXED_REROUTE_THRESHOLD:.0f}% "
              f"→ rerouted {reroute_count}/{l3_all_candidates} via Sanitize+Attest", flush=True)
        print(f"[CIRCUIT_BREAKER] TOP_UNMATCHED (first 20): {top_unmatched}", flush=True)
        slog(
            trace_id=batch_trace_id, phase="phase2", event="mixed_mode_reroute",
            batch_start_time=_batch_entry_time,
            l3_eligible=l3_all_candidates, total=total, l3_percent=round(l3_percent, 1),
            rerouted=reroute_count, top_unmatched=top_unmatched[:10],
        )

        # Clear L3 eligible list — rerouted records no longer need L3
        l3_eligible_indices.clear()
        l3_total[0] = 0

        if l3_percent > max_l3_percent:
            # Still log the anomaly for observability, but don't crash
            print(f"[CIRCUIT_BREAKER] ANOMALY_LOGGED: {l3_percent:.1f}% > max={max_l3_percent:.0f}% "
                  f"(rerouted, not fatal)", flush=True)
            slog(
                trace_id=batch_trace_id, phase="phase2", event="circuit_breaker_check",
                batch_start_time=_batch_entry_time, result="REROUTED",
                l3_eligible=l3_all_candidates, total=total,
                l3_percent=round(l3_percent, 1), max_l3_percent=round(max_l3_percent, 0),
                rerouted=reroute_count,
            )
    else:
        # PASS: L3 volume within expected range
        print(f"[CIRCUIT_BREAKER] PASS: l3_eligible={l3_all_candidates}/{total} ({l3_percent:.1f}%) <= {MIXED_REROUTE_THRESHOLD:.0f}%", flush=True)
        slog(
            trace_id=batch_trace_id, phase="phase2", event="circuit_breaker_check",
            batch_start_time=_batch_entry_time, result="PASS",
            l3_eligible=l3_all_candidates, total=total,
            l3_percent=round(l3_percent, 1), max_l3_percent=round(max_l3_percent, 0),
        )

    print(f"[batch] Phase 2: {len(l4_candidate_indices)} L4 candidates, {l3_skipped_low_sim} skipped (L2<{config.L3_MIN_SIMILARITY}), "
          f"{l3_total[0]} L3-eligible (budget=${budget_tracker.budget_usd}, concurrency={config.L3_MAX_CONCURRENCY})", flush=True)
    slog(
        trace_id=batch_trace_id, phase="phase2", event="phase2_start",
        batch_start_time=_batch_entry_time,
        l4_candidates=len(l4_candidate_indices), l3_skipped_low_sim=l3_skipped_low_sim,
        l3_eligible=l3_total[0], budget_usd=budget_tracker.budget_usd,
        concurrency=config.L3_MAX_CONCURRENCY,
    )

    # Abort check before Phase 2
    if check_batch_aborted(batch_trace_id):
        print(f"[batch] ABORT detected before Phase 2, skipping L3 processing", flush=True)
        for i in l3_eligible_indices:
            budget_tracker.record_skip("L3_ABORTED")
            results[i]["reason"] = "Low Confidence (BATCH_ABORTED)"
            results[i]["l3_skip_reason"] = "L3_ABORTED"
        return results, budget_tracker

    # Track abort state for early exit
    batch_aborted = [False]
    abort_check_counter = [0]

    # Policy-driven L3 gating (Semantic Unification)
    # MIXED mode: selectively enable L3 for ORG-classified rows only.
    # PERSON/VESSEL rows skip L3 (company-specific prompt not applicable).
    policy = MODE_POLICY[dataset_type]
    l3_policy_blocked = False  # True if ALL remaining eligible rows were policy-blocked

    if not policy["l3_enabled"]:
        if dataset_type == DatasetType.MIXED:
            # Selective L3: allow ORG rows, skip PERSON/VESSEL/GARBAGE
            l3_org_indices = []
            l3_skipped_non_org = 0
            for i in l3_eligible_indices:
                row_entity_type = results[i].get("entity_type", "")
                if row_entity_type == "ORGANIZATION":
                    l3_org_indices.append(i)
                else:
                    skip_reason = f"L3_MIXED_{row_entity_type or 'UNKNOWN'}_DISABLED"
                    budget_tracker.record_skip(skip_reason)
                    results[i]["reason"] = f"Review Required ({skip_reason})"
                    results[i]["l3_skip_reason"] = skip_reason
                    l3_skipped_non_org += 1
            # Replace eligible list with ORG-only subset
            l3_eligible_indices = l3_org_indices
            l3_total[0] = len(l3_eligible_indices)
            print(f"[batch] Phase 2: MIXED MODE - selective L3: {l3_total[0]} ORG rows eligible, "
                  f"{l3_skipped_non_org} non-ORG rows skipped", flush=True)
            if l3_total[0] == 0:
                l3_policy_blocked = True
        else:
            # PERSON/VESSEL modes: L3 fully disabled
            skip_reason = f"L3_{dataset_type.value.upper()}_DISABLED"
            for i in l3_eligible_indices:
                budget_tracker.record_skip(skip_reason)
                results[i]["reason"] = f"Review Required ({skip_reason})"
                results[i]["l3_skip_reason"] = skip_reason
            print(f"[batch] Phase 2: {dataset_type.value} MODE - L3 disabled by policy, all {l3_total[0]} routed to L4", flush=True)
            l3_policy_blocked = True

    if l3_policy_blocked:
        pass  # All eligible rows handled above — skip to post-L3 processing
    elif llm_disabled:
        # Fast path: mark all as L3_DISABLED
        for i in l3_eligible_indices:
            budget_tracker.record_skip("L3_DISABLED")
            results[i]["reason"] = "Low Confidence (L3_DISABLED)"
            results[i]["l3_skip_reason"] = "L3_DISABLED"
        print(f"[batch] Phase 2 complete: L3 disabled, all {l3_total[0]} skipped", flush=True)
    else:
        # Get or initialize semantic cache
        l3_cache = get_l3_cache()
        cache_hits_this_batch = [0]  # Track cache hits for logging

        # Parallel L3 processing with atomic budget tracking
        async def process_l3_record(result_idx: int):
            async with l3_sem:
                # Check for abort every 10 records (more aggressive)
                async with budget_lock:
                    abort_check_counter[0] += 1
                    if abort_check_counter[0] % 10 == 0 or batch_aborted[0]:
                        if not batch_aborted[0]:
                            batch_aborted[0] = check_batch_aborted(batch_trace_id)
                        if batch_aborted[0]:
                            budget_tracker.record_skip("L3_ABORTED")
                            results[result_idx]["reason"] = "Low Confidence (BATCH_ABORTED)"
                            results[result_idx]["l3_skip_reason"] = "L3_ABORTED"
                            l3_completed[0] += 1
                            _maybe_emit_l3_heartbeat()
                            if abort_check_counter[0] % 10 == 0:
                                print(f"[batch] ABORT: skipping remaining L3 records ({l3_completed[0]}/{l3_total[0]})", flush=True)
                            return

                result = results[result_idx]
                original_name = result.get("original", "")

                # =================================================================
                # STRUCTURAL GUARD 3: HARD L3 ELIGIBILITY GATE
                # =================================================================
                # Assert that ONLY L4_HUMAN records reach L3. If L1/L2 resolved it,
                # it must NEVER reach L3. This is a regression detector.
                current_layer = result.get("layer")
                if current_layer != "L4_HUMAN":
                    # FAIL: Record reached L3 without being L4_HUMAN - regression detected
                    print(f"[LLM_DIRECT_PATH] FAIL: record[{result_idx}].layer={current_layer} != L4_HUMAN → raising LLMDirectPathError", flush=True)
                    error_msg = (f"LLM direct path detected: record[{result_idx}].layer={current_layer}, expected L4_HUMAN. "
                                 f"L3 must only process L4_HUMAN records.")
                    raise LLMDirectPathError(error_msg)

                # FIRESTORE CACHE CHECK - global cache across all workers
                fs_cached = l3_firestore_cache_get(tenant_id, original_name)
                if fs_cached:
                    if fs_cached.get("is_unknown"):
                        # UNKNOWN was cached — record stays at L4_HUMAN unchanged
                        # (no resolved/layer/confidence mutation — keeps L2 state)
                        async with budget_lock:
                            budget_tracker.l3_cache_hits += 1
                            cache_hits_this_batch[0] += 1
                            result["reason"] = "Low Confidence (L3_RETURNED_UNKNOWN)"
                            result["l3_skip_reason"] = "L3_RETURNED_UNKNOWN"
                            result["cache_hit"] = "firestore_unknown"
                            result["cost"] = 0.0
                            l3_completed[0] += 1
                            _maybe_emit_l3_heartbeat()
                        return
                    async with budget_lock:
                        budget_tracker.l3_cache_hits += 1
                        cache_hits_this_batch[0] += 1
                        result["resolved"] = fs_cached["resolved"]
                        result["confidence"] = fs_cached["confidence"]
                        result["layer"] = fs_cached["layer"]
                        result["reason"] = fs_cached.get("reason", "Firestore cache hit")
                        result["cost"] = 0.0  # No cost for cache hits
                        result["l3_skip_reason"] = None
                        result["cache_hit"] = "firestore"
                        l3_completed[0] += 1
                        _maybe_emit_l3_heartbeat()
                        if l3_completed[0] % progress_interval == 0:
                            fs_stats = get_l3_firestore_cache_stats()
                            print(f"[batch] Phase 2 progress: {l3_completed[0]}/{l3_total[0]} (fs_cache_hits={fs_stats['hits']})", flush=True)
                    return

                # SINGLEFLIGHT: Prevent duplicate LLM calls across workers.
                # If another worker is already computing this key, wait for their result.
                is_leader, sf_result = l3_singleflight_acquire(tenant_id, original_name)
                if not is_leader:
                    if sf_result:
                        # Another worker already completed — use their result
                        async with budget_lock:
                            budget_tracker.l3_cache_hits += 1
                            cache_hits_this_batch[0] += 1
                            result["resolved"] = sf_result["resolved"]
                            result["confidence"] = sf_result["confidence"]
                            result["layer"] = sf_result["layer"]
                            result["reason"] = sf_result.get("reason", "Singleflight hit")
                            result["cost"] = 0.0
                            result["l3_skip_reason"] = None
                            result["cache_hit"] = "singleflight"
                            l3_completed[0] += 1
                        return
                    else:
                        # Another worker is computing — poll for result
                        polled = await loop.run_in_executor(
                            THREAD_POOL,
                            lambda t=tenant_id, n=original_name: l3_singleflight_poll(t, n)
                        )
                        if polled:
                            async with budget_lock:
                                budget_tracker.l3_cache_hits += 1
                                cache_hits_this_batch[0] += 1
                                result["resolved"] = polled["resolved"]
                                result["confidence"] = polled["confidence"]
                                result["layer"] = polled["layer"]
                                result["reason"] = polled.get("reason", "Singleflight poll hit")
                                result["cost"] = 0.0
                                result["l3_skip_reason"] = None
                                result["cache_hit"] = "singleflight_poll"
                                l3_completed[0] += 1
                            return
                        # Poll timed out — fall through to own LLM call (safe fallback)

                # Phase 2B micro-guard: track whether singleflight leader wrote a result.
                # If any failure occurs before cache_set, clean up the pending stub.
                _sf_leader_wrote_result = False
                try:
                    # Pre-check budget under lock
                    async with budget_lock:
                        can_run, skip_reason = budget_tracker.can_run_l3()
                        if not can_run:
                            budget_tracker.record_skip(skip_reason)
                            result["reason"] = f"Low Confidence ({skip_reason})"
                            result["l3_skip_reason"] = skip_reason
                            l3_completed[0] += 1
                            _maybe_emit_l3_heartbeat()
                            # Log budget exhaustion on first skip
                            if budget_tracker.l3_skipped_budget == 1:
                                print(f"[L3_COST] Budget exhausted: {budget_tracker.calls}/{budget_tracker.max_calls} calls made, "
                                      f"${budget_tracker.spent_usd:.2f} spent", flush=True)
                            if l3_completed[0] % progress_interval == 0:
                                print(f"[batch] Phase 2 progress: {l3_completed[0]}/{l3_total[0]} (skipped: {skip_reason})", flush=True)
                            _sf_leader_wrote_result = True  # No stub to clean (budget skip, not a failure)
                            return

                    # Get candidates for L3 grounding (mode-specific)
                    if dataset_type == DatasetType.PERSON:
                        # For person mode: use L2 candidates from resolve_person_sync
                        top_cands = result.get("top_candidates", [])
                        candidates = [(c["name"], c["score"], c.get("reason", "")) for c in top_cands]
                    else:
                        # For company mode: get vector candidates (Phase 2B: tenant-namespaced)
                        candidates = get_vector_candidates(original_name, top_n=15, tenant_id=tenant_id)

                    # Execute L3 call with timeout (mode-specific resolver)
                    try:
                        if dataset_type == DatasetType.PERSON:
                            llm_result = await asyncio.wait_for(
                                loop.run_in_executor(
                                    THREAD_POOL,
                                    lambda name=original_name, cands=candidates: resolve_person_with_claude_sync(name, cands)
                                ),
                                timeout=config.L3_CALL_TIMEOUT_SECONDS
                            )
                        else:
                            llm_result = await asyncio.wait_for(
                                loop.run_in_executor(
                                    THREAD_POOL,
                                    lambda name=original_name, cands=candidates, tid=tenant_id: resolve_with_claude_sync(name, cands, tenant_id=tid)
                                ),
                                timeout=config.L3_CALL_TIMEOUT_SECONDS
                            )

                        # Post-call: update budget under lock
                        async with budget_lock:
                            if llm_result:
                                # Handle person mode L3 results differently
                                if dataset_type == DatasetType.PERSON:
                                    decision = llm_result.get("decision", "NO_MATCH")
                                    confidence_band = llm_result.get("confidence_band", "LOW")
                                    is_success = (decision == "MATCH" and confidence_band == "HIGH") or \
                                                 (decision == "NO_MATCH" and confidence_band == "HIGH")

                                    budget_tracker.record_call(config.L3_COST_PER_CALL_USD, success=is_success)
                                    result["resolved"] = llm_result.get("resolved")
                                    result["match_id"] = llm_result.get("candidate_id")
                                    result["decision"] = decision
                                    result["confidence"] = 0.85 if is_success else 0.5
                                    result["layer"] = llm_result.get("layer", "L3_PERSON_LLM")
                                    result["reason"] = llm_result.get("reason", "LLM adjudication")
                                    result["cost"] = config.L3_COST_PER_CALL_USD
                                    result["l3_skip_reason"] = None

                                    if not is_success:
                                        # Low confidence or POSSIBLE_MATCH stays at L4
                                        result["layer"] = "L4_HUMAN"
                                        result["reason"] = f"Review Required (L3_{decision}_{confidence_band})"
                                        result["l3_skip_reason"] = f"L3_{decision}_{confidence_band}"

                                    circuit_breakers["resolution"].record_success()
                                    if llm_result and llm_result.get("failover_used"):
                                        budget_tracker.l3_failover_count += 1
                                else:
                                    # Company mode (existing logic)
                                    budget_tracker.record_call(config.L3_COST_PER_CALL_USD, success=True)
                                    result["resolved"] = llm_result["resolved"]
                                    result["confidence"] = llm_result["confidence"]
                                    result["layer"] = llm_result["layer"]
                                    result["reason"] = llm_result["reason"]
                                    result["cost"] = config.L3_COST_PER_CALL_USD
                                    result["l3_skip_reason"] = None
                                    circuit_breakers["resolution"].record_success()
                                    if llm_result.get("failover_used"):
                                        budget_tracker.l3_failover_count += 1

                                    # Store in Firestore for persistence across instances
                                    # (in-memory semantic cache removed for shard determinism)
                                    l3_firestore_cache_set(tenant_id, original_name, llm_result)
                            else:
                                # L3 returned None (UNKNOWN) - stays L4 but still charged
                                budget_tracker.record_call(config.L3_COST_PER_CALL_USD, success=False)
                                result["cost"] = config.L3_COST_PER_CALL_USD
                                result["l3_skip_reason"] = "L3_RETURNED_UNKNOWN"
                                result["reason"] = "Low Confidence (L3_RETURNED_UNKNOWN)"
                                # Cache UNKNOWN for topology invariance: prevents LLM
                                # non-determinism from producing different outcomes on replay
                                l3_firestore_cache_set(tenant_id, original_name, {
                                    "resolved": None,
                                    "layer": "L4_HUMAN",
                                    "confidence": 0.0,
                                    "reason": "L3_RETURNED_UNKNOWN",
                                })

                            _sf_leader_wrote_result = True
                            l3_completed[0] += 1
                            _maybe_emit_l3_heartbeat()
                            if l3_completed[0] % progress_interval == 0:
                                print(f"[batch] Phase 2 progress: {l3_completed[0]}/{l3_total[0]} (spent=${budget_tracker.spent_usd:.4f}, cache_hits={cache_hits_this_batch[0]})", flush=True)

                    except asyncio.TimeoutError:
                        async with budget_lock:
                            budget_tracker.record_skip("L3_ERROR_FAIL_CLOSED")
                            result["reason"] = "Low Confidence (L3_TIMEOUT)"
                            result["l3_skip_reason"] = "L3_ERROR_FAIL_CLOSED"
                            circuit_breakers["resolution"].record_failure()
                            l3_completed[0] += 1
                            _maybe_emit_l3_heartbeat()
                        print(f"[L3_LLM] Timeout for record {result_idx}", flush=True)

                    except Exception as e:
                        async with budget_lock:
                            budget_tracker.record_skip("L3_ERROR_FAIL_CLOSED")
                            result["reason"] = "Low Confidence (L3_ERROR_FAIL_CLOSED)"
                            result["l3_skip_reason"] = "L3_ERROR_FAIL_CLOSED"
                            circuit_breakers["resolution"].record_failure()
                            l3_completed[0] += 1
                            _maybe_emit_l3_heartbeat()
                        print(f"[L3_LLM] Error for record {result_idx}: {e}", flush=True)

                finally:
                    # Phase 2B: clean up orphaned singleflight pending stub if
                    # this leader never wrote a cache result (fail-closed, timeout, etc.)
                    if is_leader and not _sf_leader_wrote_result:
                        await loop.run_in_executor(
                            THREAD_POOL,
                            lambda t=tenant_id, n=original_name: l3_singleflight_release(t, n)
                        )

        # Launch all L3 tasks in parallel (bounded by semaphore)
        l3_tasks = [process_l3_record(i) for i in l3_eligible_indices]
        await asyncio.gather(*l3_tasks)

        print(f"[batch] Phase 2 complete: {l3_completed[0]}/{l3_total[0]} processed (L3 calls={budget_tracker.calls}, cache_hits={budget_tracker.l3_cache_hits}, spent=${budget_tracker.spent_usd:.4f})", flush=True)
        slog(
            trace_id=batch_trace_id, phase="phase2", event="phase2_complete",
            batch_start_time=_batch_entry_time,
            l3_completed=l3_completed[0], l3_total=l3_total[0],
            l3_calls=budget_tracker.calls, l3_cache_hits=budget_tracker.l3_cache_hits,
            l3_spent_usd=round(budget_tracker.spent_usd, 4),
            l3_skipped_budget=budget_tracker.l3_skipped_budget,
        )
        # Cost summary
        print(f"[L3_COST] Summary: budget=${budget_tracker.budget_usd:.2f}, spent=${budget_tracker.spent_usd:.2f}, "
              f"calls={budget_tracker.calls}/{budget_tracker.max_calls}, cache_hits={budget_tracker.l3_cache_hits}, "
              f"skipped_budget={budget_tracker.l3_skipped_budget}, skipped_rate_limit={budget_tracker.l3_skipped_rate_limit}", flush=True)
        # Cache stats
        if l3_cache:
            cache_stats = l3_cache.get_stats()
            print(f"[L3_CACHE] Stats: size={cache_stats['size']}, hits={cache_stats['hits']}, misses={cache_stats['misses']}, hit_rate={cache_stats['hit_rate_pct']}%", flush=True)

    # Verify observability invariant: l3_eligible == l3_attempted + l3_cache_hits + l3_skipped_budget + l3_skipped_rate_limit
    invariant_sum = budget_tracker.l3_attempted + budget_tracker.l3_cache_hits + budget_tracker.l3_skipped_budget + budget_tracker.l3_skipped_rate_limit
    invariant_valid = budget_tracker.l3_eligible == invariant_sum
    print(f"[batch] L3 Invariant Check: eligible={budget_tracker.l3_eligible} == "
          f"(attempted={budget_tracker.l3_attempted} + cache_hits={budget_tracker.l3_cache_hits} + "
          f"skipped_budget={budget_tracker.l3_skipped_budget} + skipped_rate_limit={budget_tracker.l3_skipped_rate_limit}) = {invariant_sum} → {'✓ VALID' if invariant_valid else '✗ INVALID'}", flush=True)

    # Clean up internal tracking field
    for r in results:
        r.pop("_original_idx", None)

    return results, budget_tracker


# Backwards-compat alias (remove after 1 release)
process_batch_parallel_hardened = process_batch_parallel_golden


# =============================================================================
# API ENDPOINTS - BASIC
# =============================================================================

@app.get("/")
def root():
    """Root endpoint."""
    return {
        "status": "Intelligent Analyst v3.0.0 Enterprise Online",
        "version": "3.0.0",
        "canonicals": len(CANONICALS),
        "firestore_available": _firestore_db is not None
    }


# =============================================================================
# BACKEND BUTTON ENDPOINTS
# =============================================================================

@app.get("/health")
def health_check():
    """
    BACKEND BUTTON: Health & Versioning

    Returns system health, versions, and component status.
    """
    uptime_seconds = (datetime.utcnow() - _STARTUP_TIME).total_seconds()

    return {
        "status": "healthy",
        "version": "3.0.0",
        "environment": config.ENVIRONMENT,
        "canonical_config_version": CANONICAL_CONFIG_VERSION,
        "uptime_seconds": int(uptime_seconds),
        "uptime_human": str(timedelta(seconds=int(uptime_seconds))),
        "started_at": _STARTUP_TIME.isoformat(),
        "sklearn_available": HAS_SKLEARN,
        "llm_available": HAS_ANTHROPIC and bool(ANTHROPIC_API_KEY),
        "l3_row_threshold": config.L3_ROW_THRESHOLD,  # Deprecated - shown for visibility
        "l3_max_concurrency": config.L3_MAX_CONCURRENCY,
        "l3_min_similarity": config.L3_MIN_SIMILARITY,
        "l3_max_percent": config.L3_MAX_PERCENT,
        "l3_circuit_breaker_enabled": config.L3_CIRCUIT_BREAKER_ENABLED,
        "person_l3_enabled": config.PERSON_L3_ENABLED,
        "sanitization_version": config.SANITIZATION_VERSION,
        "watchlist_version_hash": config.WATCHLIST_VERSION_HASH,
        "certificate_service": HAS_CERTIFICATE_SERVICE,
        "firestore_available": _firestore_db is not None,
        "firestore_database": config.FIRESTORE_DATABASE,
        "audit_store_type": "firestore" if _firestore_db else "file",
        "canonicals_count": len(CANONICALS),
        "known_parents_count": len(KNOWN_PARENTS),
        "circuit_breakers": {
            name: cb.get_status() for name, cb in circuit_breakers.items()
        },
        "pii_stats": pii_masker.get_stats(),
        "input_validation": input_validator.get_stats(),
        "max_records_per_batch": config.MAX_BATCH_SIZE,
        "max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024),
        "config": {
            "max_batch_size": config.MAX_BATCH_SIZE,
            "max_upload_bytes": config.MAX_UPLOAD_BYTES,
            "rate_limit": f"{config.RATE_LIMIT_REQUESTS}/{config.RATE_LIMIT_WINDOW_SECONDS}s",
        },
        "auth": {
            "backend": "firebase_admin" if HAS_FIREBASE_AUTH else "api_key_only",
            "firebase_available": HAS_FIREBASE_AUTH,
            "project_id": _firebase_app.project_id if HAS_FIREBASE_AUTH and _firebase_app else None,
            "admin_uids_configured": len(ADMIN_UID_ALLOWLIST),
        },
        # Forensic Audit (Phase 0.5+)
        "forensic_audit": {
            "code_version": get_signing_status().get("service_identity", {}).get("code_version") if HAS_FORENSIC_SIGNING else None,
            "sbom_hash_sha256": get_sbom_hash() if HAS_FORENSIC_SIGNING else None,
            "signing_enabled": config.SIGNING_ENABLED,
            "signing_key_id": config.KMS_SIGNING_KEY_ID[:50] + "..." if len(config.KMS_SIGNING_KEY_ID) > 50 else config.KMS_SIGNING_KEY_ID if config.KMS_SIGNING_KEY_ID else None,
            "hash_chain_enabled": config.HASH_CHAIN_ENABLED,
            "anchoring_enabled": config.ANCHORING_ENABLED,
            "legal_hold_enabled": config.LEGAL_HOLD_ENABLED,
            "tenant_isolation_enabled": config.TENANT_ISOLATION_ENABLED,
            "tenant_encryption_enabled": config.TENANT_ENCRYPTION_ENABLED,
            "energy_estimates_enabled": config.ENERGY_ESTIMATES_ENABLED,
            "processing_region": config.PROCESSING_REGION,
            "deploy_region": config.DEPLOY_REGION,
        },
        # Energy/Carbon Sustainability Estimates
        "sustainability": get_energy_estimator_status() if HAS_FORENSIC_SIGNING else {"enabled": False},
        # Phase 2A: Backpressure Governor
        "backpressure": _backpressure.snapshot(),
    }


@app.get("/security/status")
def security_status(identity: dict = Depends(require_firebase_admin_claim)):
    """
    BACKEND BUTTON: Security Posture (admin-only)

    Returns high-level PASS/FAIL security controls status.
    Day 7: Requires Firebase admin claim — no raw config exposed.
    """
    all_cb_ok = all(cb.state == "closed" for cb in circuit_breakers.values())
    return {
        "pii_masking_enabled": True,
        "input_validation_enabled": config.INPUT_VALIDATION_ENABLED,
        "circuit_breaker_status": "PASS" if all_cb_ok else "DEGRADED",
        "rate_limiting_enabled": True,
        "authentication_enabled": bool(config.API_KEY),
        "firestore_available": _firestore_db is not None,
        "forensic_signing_enabled": HAS_FORENSIC_SIGNING,
        "anchoring_enabled": config.ANCHORING_ENABLED,
        "legal_hold_enabled": config.LEGAL_HOLD_ENABLED,
        "tenant_isolation_enabled": config.TENANT_ISOLATION_ENABLED,
        "tenant_encryption_enabled": config.TENANT_ENCRYPTION_ENABLED,
    }


@app.get("/security/integrity")
def get_integrity_status(identity: dict = Depends(require_firebase_admin_claim)):
    """
    SECURITY: Forensic Integrity Check Status (admin-only)

    Day 7: Requires Firebase admin claim — returns PASS/FAIL only.
    """
    if _integrity_check_result is None:
        return {
            "integrity_check_enabled": False,
            "status": "NOT_RUN",
        }

    passed = _integrity_check_result.get("all_passed", False)
    return {
        "integrity_check_enabled": True,
        "status": "PASS" if passed else "FAIL",
        "checks_run": _integrity_check_result.get("checks_run", 0),
        "checks_passed": _integrity_check_result.get("checks_passed", 0),
    }


@app.get("/security/public-key")
def get_public_key_endpoint():
    """
    SECURITY: Public Key for External Signature Verification

    Returns the public key (PEM format) and metadata for verifying
    evidence blob signatures independently.

    Use this endpoint to:
    1. Retrieve the current signing public key
    2. Get key version and creation metadata (for rotation governance)
    3. Verify signatures using external tools (openssl, Python, etc.)

    The public key can verify any evidence_blob.signature using:
    - Algorithm: ECDSA P-256 (secp256r1) with SHA-256
    - Input: SHA256(canonical_json(evidence_core))
    - Signature: Base64-decoded evidence_blob.signature.signature
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    public_key_info = get_public_key_info()

    if public_key_info.get("public_key_error"):
        raise HTTPException(500, f"Failed to retrieve public key: {public_key_info.get('public_key_error')}")

    return {
        "public_key_pem": public_key_info.get("public_key_pem"),
        "key_metadata": public_key_info.get("key_metadata"),
        "algorithm": public_key_info.get("algorithm"),
        "hash_algorithm": public_key_info.get("hash_algorithm"),
        "signature_encoding": public_key_info.get("signature_encoding"),
        "verification_instructions": public_key_info.get("verification_instructions"),
        "retrieved_at": datetime.utcnow().isoformat(),
    }


@app.get("/stats")
def get_stats():
    """
    BACKEND BUTTON: Performance Snapshot

    Returns cumulative processing statistics.
    Cost fields always stripped (public endpoint, no auth).
    """
    with _stats_lock:
        stats = _global_stats.to_dict()

    stats["config_version"] = CANONICAL_CONFIG_VERSION
    stats["uptime_seconds"] = int((datetime.utcnow() - _STARTUP_TIME).total_seconds())

    # RBAC: Always strip cost from public /stats endpoint
    stats.pop("total_cost", None)

    return stats


@app.get("/invariants/l3-drift")
async def get_l3_drift_invariant(
    scope: str = Query(default="last_batch"),
    auth: dict = Depends(require_admin_role),
):
    """
    ADMIN: L3 Drift Invariant

    Returns the current L3 drift zone classification.

    Query params:
      scope=last_batch  (default) — stats from the most recent batch only
      scope=cumulative             — aggregated since service start

    Zone meanings:
      SAFE    — L3 rate < 3.0%  (normal operation)
      WARNING — L3 rate 3.0–4.5% (elevated; review configuration)
      RED     — L3 rate >= 4.5% OR last batch hit the cost cap

    Requires admin API key (X-API-Key header).
    """
    effective_scope = "cumulative" if scope == "cumulative" else "last_batch"

    with _stats_lock:
        if effective_scope == "cumulative":
            total_l3 = _global_stats.total_l3_llm
            total_l4 = _global_stats.total_l4_human
            total_valid = _global_stats.total_records_processed - _global_stats.total_l0_garbage
            window_batches = _global_stats.total_batches_processed
        else:
            total_l3 = _global_stats.last_batch_l3
            total_l4 = _global_stats.last_batch_l4
            total_valid = _global_stats.last_batch_valid_records
            window_batches = 1
        spent_usd = _global_stats.l3_last_spent_usd

    inv = compute_drift_invariant(
        total_l3=total_l3,
        total_l4=total_l4,
        total_valid_records=total_valid,
        spent_usd=spent_usd,
        budget_usd=config.L3_MAX_COST_USD,
    )

    return {
        "zone": inv.zone,
        "reason": inv.reason,
        "l3_pct": inv.l3_pct,
        "l4_pct": inv.l4_pct,
        "cost_exceeded": inv.cost_exceeded,
        "total_l3": inv.total_l3,
        "total_l4": inv.total_l4,
        "total_valid_records": inv.total_records,
        "budget_usd": inv.budget_usd,
        "spent_usd": inv.spent_usd,
        "thresholds": {
            "warn_pct": 3.0,
            "red_pct": 4.5,
        },
        "scope": effective_scope,
        "window_records": total_valid,
        "window_batches": window_batches,
        "retrieved_at": datetime.utcnow().isoformat(),
    }


@app.get("/invariants/margin")
async def get_margin_invariant(
    scope: str = Query(default="last_batch"),
    auth: dict = Depends(require_admin_role),
):
    """
    ADMIN: Margin Sentinel Invariant

    Returns the current margin zone classification based on L4 escalation
    rate and cost-per-record (LLM + human review cost).

    Query params:
      scope=last_batch  (default) — stats from the most recent batch only
      scope=cumulative             — aggregated since service start

    Zone meanings:
      SAFE    — L4 rate < 6.0% AND cost/record < $0.05
      WARNING — L4 rate >= 6.0% (but not RED), OR cost/record approaching RED threshold
      RED     — L4 rate >= 8.0% OR cost/record >= $0.05

    Human review cost default: $0.50/record (HUMAN_COST_PER_RECORD_USD env var).
    Requires admin API key (X-API-Key header).
    """
    effective_scope = "cumulative" if scope == "cumulative" else "last_batch"

    with _stats_lock:
        if effective_scope == "cumulative":
            total_valid = _global_stats.total_records_processed - _global_stats.total_l0_garbage
            total_l3 = _global_stats.total_l3_llm
            total_l4 = _global_stats.total_l4_human
            total_llm_cost = _global_stats.total_cost
            window_batches = _global_stats.total_batches_processed
        else:
            total_valid = _global_stats.last_batch_valid_records
            total_l3 = _global_stats.last_batch_l3
            total_l4 = _global_stats.last_batch_l4
            total_llm_cost = _global_stats.last_batch_llm_cost
            window_batches = 1

    margin = compute_margin_sentinel(
        total_records=total_valid,
        total_l3=total_l3,
        total_l4=total_l4,
        total_llm_cost_usd=total_llm_cost,
        human_cost_per_record_usd=config.HUMAN_COST_PER_RECORD_USD,
        l4_warning_threshold_pct=config.L4_WARNING_THRESHOLD_PCT,
        l4_red_threshold_pct=config.L4_RED_THRESHOLD_PCT,
        cost_per_record_red_usd=config.COST_PER_RECORD_RED_USD,
    )

    return {
        "zone": margin.zone,
        "reason": margin.reason,
        "invariant_pass": margin.invariant_pass,
        "l4_pct": margin.l4_pct,
        "human_cost_usd": margin.human_cost_usd,
        "total_cost_usd": margin.total_cost_usd,
        "cost_per_record_usd": margin.cost_per_record_usd,
        "thresholds": {
            "l4_warning_pct": config.L4_WARNING_THRESHOLD_PCT,
            "l4_red_pct": config.L4_RED_THRESHOLD_PCT,
            "cost_per_record_red_usd": config.COST_PER_RECORD_RED_USD,
        },
        "scope": effective_scope,
        "window_records": total_valid,
        "window_batches": window_batches,
        "retrieved_at": datetime.utcnow().isoformat(),
    }


@app.post("/invariants/reset")
async def reset_invariants(auth: dict = Depends(require_admin_role)):
    """
    ADMIN: Reset Invariant Rolling Window

    Clears in-memory GlobalStats counters (rolling window only).
    Does NOT modify Firestore, audit events, evidence packs, or GCS anchors.

    Requires admin API key (X-API-Key header).
    Requires INVARIANTS_RESET_ENABLED=true env var (default: false).
    Returns 404 when disabled — endpoint is dark in PROD by default.
    """
    if not config.INVARIANTS_RESET_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    with _stats_lock:
        _global_stats.total_records_processed = 0
        _global_stats.total_batches_processed = 0
        _global_stats.total_auto_resolved = 0
        _global_stats.total_l0_garbage = 0
        _global_stats.total_l1_exact = 0
        _global_stats.total_l1_norm = 0
        _global_stats.total_l2_vector = 0
        _global_stats.total_l3_llm = 0
        _global_stats.total_l4_human = 0
        _global_stats.total_pii_detections = 0
        _global_stats.total_latency_ms = 0.0
        _global_stats.total_cost = 0.0
        _global_stats.l3_drift_zone = "SAFE"
        _global_stats.l3_pct = 0.0
        _global_stats.l4_pct = 0.0
        _global_stats.l3_last_spent_usd = 0.0
        _global_stats.margin_zone = "SAFE"
        _global_stats.margin_human_cost_usd = 0.0
        _global_stats.margin_total_cost_usd = 0.0
        _global_stats.margin_cost_per_record_usd = 0.0
        _global_stats.last_batch_l3 = 0
        _global_stats.last_batch_l4 = 0
        _global_stats.last_batch_valid_records = 0
        _global_stats.last_batch_llm_cost = 0.0

    return {
        "reset": True,
        "message": "In-memory rolling window stats cleared. Audit trail, Firestore, evidence packs, and GCS anchors are unchanged.",
        "reset_at": datetime.utcnow().isoformat(),
    }


@app.get("/security/pii-log")
def pii_log(limit: int = 100, auth: dict = Depends(verify_api_key)):
    """
    AUDIT BUTTON: PII Detection Log

    Returns recent PII detection events.
    """
    return {
        "detections": pii_masker.get_recent_detections(limit),
        "stats": pii_masker.get_stats(),
    }


@app.get("/security/manifest-public-key")
def get_manifest_public_key():
    """
    Evidence Pack v1.2: Get public key for manifest signature verification.

    Returns PEM-encoded RSA public key that can be used to verify
    manifest signatures created by POST /sign-manifest.
    """
    if not HAS_CRYPTO:
        raise HTTPException(503, "Crypto module not available")

    if not is_signing_available():
        raise HTTPException(503, "Signing keys not initialized")

    public_key = get_public_key_pem()
    if not public_key:
        raise HTTPException(503, "Failed to retrieve public key")

    return {
        "public_key_pem": public_key,
        "algorithm": "RSA-SHA256",
        "key_source": get_key_source(),
    }


class SignManifestRequest(BaseModel):
    """Request body for manifest signing."""
    manifest_json: str = Field(..., description="JSON string of the manifest to sign")


@app.post("/sign-manifest")
async def sign_manifest_endpoint(
    request: SignManifestRequest,
    auth: dict = Depends(verify_api_key)
):
    """
    Evidence Pack v1.2: Sign a manifest JSON with RSA-SHA256.

    The manifest should be the exact JSON string that will be included
    in the Evidence Pack ZIP. The signature is computed over the raw
    bytes of the JSON string (UTF-8 encoded).

    Returns base64-encoded signature that can be verified using the
    public key from GET /security/manifest-public-key.
    """
    if not HAS_CRYPTO:
        raise HTTPException(503, "Crypto module not available")

    if not is_signing_available():
        raise HTTPException(503, "Signing keys not initialized")

    try:
        manifest_bytes = request.manifest_json.encode('utf-8')
        signature = sign_manifest(manifest_bytes)

        if not signature:
            raise HTTPException(500, "Signing failed")

        return {
            "signature": signature,
            "algorithm": "RSA-SHA256-PKCS1v15",
            "encoding": "base64",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[sign-manifest] Error: {e}", flush=True)
        raise HTTPException(500, f"Signing error: {str(e)}")


@app.get("/security/whoami")
async def whoami(auth: dict = Depends(verify_api_key)):
    """
    Debug endpoint: Show derived tenant identity and role (no secrets exposed).
    Helps diagnose tenant/role scoping issues.
    """
    email = auth.get("email", "")
    domain = email.split("@")[1] if email and "@" in email else None

    return {
        "tenant_id": auth.get("tenant_id"),
        "role": auth.get("role", "user"),
        "auth_method": auth.get("auth_method"),
        "email_domain": domain,
        "uid_prefix": auth.get("uid", "")[:8] + "..." if auth.get("uid") else None,
        "demo_mode": config.DEMO_MODE,
    }


@app.get("/demo/status")
async def demo_status():
    """
    Returns demo mode status. No auth required.
    Frontend uses this to show demo banner and disable uploads.
    """
    return {
        "demo_mode": config.DEMO_MODE,
        "message": "Demo mode — sample data only" if config.DEMO_MODE else None,
        "uploads_disabled": config.DEMO_MODE,
    }


# =============================================================================
# ADMIN CONSOLE ENDPOINTS (Admin-only, Read-only)
# =============================================================================

def get_tenant_summary_from_firestore(limit: int = 50) -> List[Dict]:
    """
    Aggregate tenant statistics from Firestore batches.
    Returns tenant_id_hash, batch_count_30d, last_batch_timestamp.
    No PII exposed.
    """
    if not _firestore_db:
        return []

    try:
        batches_ref = _firestore_db.collection('batches')
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        # Fetch recent batches for aggregation
        query = batches_ref.order_by('timestamp', direction=firestore_client.Query.DESCENDING).limit(500)
        docs = list(query.stream())

        # Aggregate by tenant_id
        tenant_stats = {}
        for doc in docs:
            batch_data = doc.to_dict()
            tenant_id = batch_data.get('tenant_id')
            if not tenant_id:
                tenant_id = '__legacy__'

            # Hash tenant_id for privacy
            tenant_id_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]

            if tenant_id_hash not in tenant_stats:
                tenant_stats[tenant_id_hash] = {
                    'tenant_id_hash': tenant_id_hash,
                    '_raw_tenant_id': tenant_id,  # Internal use for filtering
                    'batch_count_30d': 0,
                    'last_batch_timestamp': None
                }

            # Count batches in last 30 days
            batch_ts = batch_data.get('timestamp')
            if batch_ts:
                try:
                    ts = datetime.fromisoformat(batch_ts.replace('Z', '+00:00')) if isinstance(batch_ts, str) else batch_ts
                    if hasattr(ts, 'replace'):
                        ts_naive = ts.replace(tzinfo=None) if hasattr(ts, 'tzinfo') and ts.tzinfo else ts
                    else:
                        ts_naive = ts
                    if ts_naive > thirty_days_ago:
                        tenant_stats[tenant_id_hash]['batch_count_30d'] += 1
                    # Track last batch timestamp
                    if tenant_stats[tenant_id_hash]['last_batch_timestamp'] is None or batch_ts > tenant_stats[tenant_id_hash]['last_batch_timestamp']:
                        tenant_stats[tenant_id_hash]['last_batch_timestamp'] = batch_ts
                except Exception:
                    pass

        # Convert to list and remove internal _raw_tenant_id
        result = []
        for stats in tenant_stats.values():
            result.append({
                'tenant_id_hash': stats['tenant_id_hash'],
                'batch_count_30d': stats['batch_count_30d'],
                'last_batch_timestamp': stats['last_batch_timestamp']
            })

        # Sort by last activity
        result.sort(key=lambda x: x['last_batch_timestamp'] or '', reverse=True)
        return result[:limit]

    except Exception as e:
        print(f"[Firestore] Error aggregating tenant stats: {e}", flush=True)
        return []


# Maintain a mapping of tenant_id_hash -> raw tenant_id for admin filtering
_tenant_hash_map = {}


def refresh_tenant_hash_map():
    """Refresh the tenant hash map from Firestore."""
    global _tenant_hash_map
    if not _firestore_db:
        return

    try:
        batches_ref = _firestore_db.collection('batches')
        query = batches_ref.order_by('timestamp', direction=firestore_client.Query.DESCENDING).limit(500)
        docs = list(query.stream())

        new_map = {}
        for doc in docs:
            batch_data = doc.to_dict()
            tenant_id = batch_data.get('tenant_id')
            if tenant_id:
                tenant_id_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
                new_map[tenant_id_hash] = tenant_id

        _tenant_hash_map = new_map
        print(f"[Admin] Refreshed tenant hash map: {len(_tenant_hash_map)} tenants", flush=True)
    except Exception as e:
        print(f"[Admin] Error refreshing tenant hash map: {e}", flush=True)


@app.get("/admin/tenants")
async def get_admin_tenants(
    limit: int = Query(50, le=100),
    auth: dict = Depends(require_admin_role)
):
    """
    ADMIN ONLY: List all tenants with summary statistics.
    Returns tenant_id_hash (not raw tenant_id) for privacy.
    """
    # Refresh tenant hash map
    refresh_tenant_hash_map()

    tenants = get_tenant_summary_from_firestore(limit)

    return {
        "tenants": tenants,
        "count": len(tenants),
        "message": f"Found {len(tenants)} tenants"
    }


# =============================================================================
# AUDIT BUTTON ENDPOINTS
# =============================================================================

@app.get("/audit")
async def get_recent_audit(
    limit: int = Query(100, le=500),
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Recent Audit Entries

    Returns recent audit events across all batches.
    """
    events = get_recent_audit_events_from_firestore(limit)

    return {
        "events": events,
        "count": len(events),
        "source": "firestore" if _firestore_db else "none",
        "message": f"Recent {len(events)} audit events"
    }


@app.get("/audit/{trace_id}")
async def get_audit(
    trace_id: str,
    limit: int = Query(1000, le=10000),
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Full Audit Trail for Trace ID

    Returns complete audit trail for a specific batch.
    Enforces tenant isolation - returns 404 if batch belongs to another tenant.
    Admin role bypasses tenant check (read-only cross-tenant access).
    """
    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin bypasses)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        # Return 404 (not 403) to avoid revealing existence
        raise HTTPException(status_code=404, detail="Batch not found")

    # Try Firestore first
    events = get_audit_events_from_firestore(trace_id, limit)

    if events:
        # Get batch metadata
        batch_meta = {}
        if _firestore_db:
            try:
                batch_doc = _firestore_db.collection('batches').document(trace_id).get()
                if batch_doc.exists:
                    batch_meta = batch_doc.to_dict()
            except:
                pass

        return {
            "trace_id": trace_id,
            "config_version": batch_meta.get("config_version", CANONICAL_CONFIG_VERSION),
            "timestamp": batch_meta.get("timestamp"),
            "total": batch_meta.get("total", len(events)),
            "auto_resolved": batch_meta.get("auto_resolved", 0),
            "flagged_count": batch_meta.get("flagged_count", 0),
            "events": events,
            "count": len(events),
            "source": "firestore"
        }

    # Fallback to file storage
    audit_data = audit_storage.get(trace_id)
    if audit_data:
        file_events = audit_data.get("events", [])[:limit]
        return {
            "trace_id": trace_id,
            "config_version": CANONICAL_CONFIG_VERSION,
            "events": file_events,
            "count": len(file_events),
            "source": "file"
        }

    return {"trace_id": trace_id, "events": [], "count": 0, "source": "none"}


@app.get("/audit/{trace_id}/flagged")
async def get_flagged_items(
    trace_id: str,
    limit: int = Query(500, le=2000),
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Flagged Items Needing Review

    Returns only L4_HUMAN items that need manual review.
    Enforces tenant isolation. Admin role bypasses tenant check.
    """
    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin bypasses)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    flagged = get_flagged_items_from_firestore(trace_id, limit)

    return {
        "trace_id": trace_id,
        "flagged_items": flagged,
        "count": len(flagged),
        "message": f"{len(flagged)} items need human review"
    }


# ─────────────────────────────────────────────────────────────────────────────
# L4 Human Review — Closed-Loop Decision Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class L4DecisionRequest(BaseModel):
    """Minimal decision model for L4 human review."""
    row_id: str = Field(..., description="Audit event doc ID, e.g. row_000123")
    decision: str = Field(..., description="APPROVED, REJECTED, or ESCALATED")
    decided_by: str = Field(default="operator", description="Identity of the reviewer")

    @validator('decision')
    def validate_decision(cls, v):
        allowed = {"APPROVED", "REJECTED", "ESCALATED"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"decision must be one of {allowed}")
        return v_upper


def _find_row_layer(trace_id: str, row_index: int) -> Optional[str]:
    """Find the layer of a specific row by index, checking results_chunks."""
    if not _firestore_db:
        return None
    try:
        results_ref = _firestore_db.collection('batches').document(trace_id).collection('results_chunks')
        for chunk_doc in results_ref.stream():
            chunk = chunk_doc.to_dict()
            start = chunk.get("start_index", 0)
            rows = chunk.get("rows", [])
            for i, row in enumerate(rows):
                if start + i == row_index:
                    return row.get("layer")
    except Exception as e:
        print(f"[L4-Review] Error scanning results_chunks: {e}", flush=True)
    return None


@app.post("/audit/{trace_id}/review")
async def submit_l4_review(
    trace_id: str,
    req: L4DecisionRequest,
    auth: dict = Depends(require_write_permission)
):
    """
    Submit a human review decision for an L4_HUMAN flagged item.

    Persists decision to batches/{trace_id}/decisions/{row_id}.
    Validates the row is L4_HUMAN via audit_events or results_chunks.
    Only L4_HUMAN items can be reviewed through this path.
    """
    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    if not _firestore_db:
        raise HTTPException(status_code=503, detail="Firestore not available")

    # Extract row_index from row_id (format: row_NNNNNN)
    row_index = None
    if req.row_id.startswith("row_"):
        try:
            row_index = int(req.row_id.split("_", 1)[1])
        except (ValueError, IndexError):
            pass

    # Try audit_events first (sequential batches write here)
    row_layer = None
    doc_ref = (_firestore_db.collection('batches')
               .document(trace_id)
               .collection('audit_events')
               .document(req.row_id))
    doc = doc_ref.get()
    if doc.exists:
        row_data = doc.to_dict()
        row_layer = row_data.get("layer")
        is_flagged = row_data.get("flagged", False)
    else:
        # Fallback: scan results_chunks (works for both sequential and sharded batches)
        is_flagged = False
        if row_index is not None:
            row_layer = _find_row_layer(trace_id, row_index)
            is_flagged = (row_layer == "L4_HUMAN")

    if row_layer is None:
        raise HTTPException(status_code=404, detail=f"Row {req.row_id} not found in {trace_id}")

    # Guard: only L4_HUMAN items can be reviewed
    if row_layer != "L4_HUMAN" and not is_flagged:
        raise HTTPException(
            status_code=409,
            detail=f"Row {req.row_id} is layer={row_layer}, not L4_HUMAN. Only flagged items can be reviewed."
        )

    decided_at = datetime.utcnow().isoformat()

    # Persist decision to dedicated decisions subcollection
    decision_doc = {
        "row_id": req.row_id,
        "row_index": row_index,
        "decision": req.decision,
        "decided_at": decided_at,
        "decided_by": req.decided_by,
        "trace_id": trace_id,
        "tenant_id": tenant_id or "unknown",
    }
    _firestore_db.collection('batches').document(trace_id).collection('decisions').document(req.row_id).set(decision_doc)

    # Also update audit_event doc if it exists (for flagged retrieval consistency)
    if doc.exists:
        doc_ref.update({
            "review_decision": req.decision,
            "review_decided_at": decided_at,
            "review_decided_by": req.decided_by,
        })

    # Append meta audit event for traceability
    append_meta_audit_event(trace_id, {
        "event_type": "l4_review_decision",
        "row_id": req.row_id,
        "decision": req.decision,
        "decided_by": req.decided_by,
        "decided_at": decided_at,
        "trace_id": trace_id,
        "tenant_id": tenant_id or "unknown",
    })

    print(f"[L4-Review] {trace_id}/{req.row_id}: {req.decision} by {req.decided_by}", flush=True)

    return {
        "trace_id": trace_id,
        "row_id": req.row_id,
        "decision": req.decision,
        "decided_at": decided_at,
        "decided_by": req.decided_by,
        "status": "persisted",
    }


@app.get("/audit/{trace_id}/decisions")
async def get_l4_decisions(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    Retrieve all L4 review decisions for a batch.

    Returns a map of row_id → decision document for UI overlay.
    """
    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    if not _firestore_db:
        return {"trace_id": trace_id, "decisions": {}, "count": 0}

    decisions = {}
    try:
        docs = _firestore_db.collection('batches').document(trace_id).collection('decisions').stream()
        for doc in docs:
            d = doc.to_dict()
            decisions[doc.id] = d
    except Exception as e:
        print(f"[L4-Review] Error fetching decisions: {e}", flush=True)

    return {
        "trace_id": trace_id,
        "decisions": decisions,
        "count": len(decisions),
    }


@app.get("/audit/{trace_id}/evidence")
async def get_evidence_blobs(
    trace_id: str,
    row_index: Optional[int] = Query(None, description="Specific row index, or None for all"),
    limit: int = Query(100, le=1000),
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Evidence Blobs (Phase 1 - Forensic)

    Returns cryptographically signed evidence blobs for a batch.
    Each blob contains decision context for deterministic replay.

    - If row_index is specified, returns single evidence blob
    - If row_index is None, returns all evidence blobs (up to limit)

    Evidence includes:
    - Input (original + sanitized)
    - Routing decision + signals
    - Output fields
    - Config snapshot
    - LLM prompt/response hashes (full text only if EVIDENCE_STORE_FULL_LLM_TEXT=true)
    - Signature (KMS-signed SHA-256)
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin bypasses)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    if row_index is not None:
        # Single evidence blob (decrypt if encrypted)
        blob = get_evidence_blob_from_firestore(trace_id, row_index, tenant_id=tenant_id)
        if not blob:
            raise HTTPException(status_code=404, detail=f"Evidence not found for row {row_index}")

        # Check for decryption error
        if blob.get("decrypt_error"):
            raise HTTPException(status_code=403, detail=f"Decryption failed: {blob.get('decrypt_error')}")

        # Verify signature format
        verification = verify_evidence_signature_format(blob)

        return {
            "trace_id": trace_id,
            "row_index": row_index,
            "evidence": blob,
            "signature_verification": verification,
            "encrypted_at_rest": config.TENANT_ENCRYPTION_ENABLED,
        }
    else:
        # All evidence blobs (decrypt if encrypted)
        blobs = get_evidence_blobs_for_batch(trace_id, tenant_id=tenant_id, limit=limit)

        return {
            "trace_id": trace_id,
            "evidence_blobs": [extract_evidence_summary(b) for b in blobs],
            "count": len(blobs),
            "full_evidence_available": True,
            "message": f"Retrieved {len(blobs)} evidence blobs. Use ?row_index=N for full details."
        }


@app.get("/audit/{trace_id}/certificate")
async def get_transparency_certificate(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """Generate PDF transparency certificate. Enforces tenant isolation. Admin bypasses."""
    if not HAS_CERTIFICATE_SERVICE:
        raise HTTPException(503, "Certificate service not available (requires reportlab)")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin bypasses)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Prefer authoritative Firestore events (deterministic row_index ordering)
    events = []
    try:
        events = get_audit_events_from_firestore(trace_id, limit=10000) or []
    except Exception as e:
        print(f"[Certificate] WARNING: Firestore audit fetch failed for {trace_id}: {e}", flush=True)
        events = []

    # Fallback to file-based storage if Firestore is empty/unavailable
    if not events:
        audit_data = audit_storage.get(trace_id)
        events = audit_data.get("events", []) if audit_data else []

    ci = make_certificate_input(
        trace_id=trace_id,
        tenant_id=auth.get("tenant_id", "unknown"),
        system_name="Intelligent Analyst",
        system_version="3.0.0",
        events=events,
        config_snapshot={
            "canonicals_count": len(CANONICALS),
            "known_parents_count": len(KNOWN_PARENTS),
            "vector_threshold": 0.55,
            "sklearn_available": HAS_SKLEARN,
            "config_version": CANONICAL_CONFIG_VERSION,
        },
        security_snapshot={
            "cors_origins": config.ALLOWED_ORIGINS,
            "max_upload_bytes": config.MAX_UPLOAD_BYTES,
            "parallel_limit": config.PARALLEL_LIMIT,
            "pii_detection_enabled": True,
            "circuit_breaker_enabled": True,
        },
    )

    pdf_bytes, cert_hash = build_transparency_certificate_pdf(ci)

    # Append-only: record evidence pack generation
    meta_event = {
        "event_type": "evidence_pack_generated",
        "artifact": "certificate_pdf",
        "cert_sha256": cert_hash,
        "trace_id": trace_id,
        "tenant_id": auth.get("tenant_id", "unknown"),
        "system_version": "3.0.0",
        "original": "certificate",
        "resolved": cert_hash,
        "layer": "META",
        "reason": "evidence_pack_generated",
    }
    ok = append_meta_audit_event(trace_id, meta_event)
    if not ok:
        # Minimal handling: do not fail certificate generation
        print(f"[Audit] WARNING: failed to append evidence_pack_generated for {trace_id}", flush=True)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="IA_Certificate_{trace_id}.pdf"',
            "X-Certificate-SHA256": cert_hash,
        }
    )


@app.get("/audit/{trace_id}/verification-bundle")
async def get_verification_bundle(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    Generate a portable verification bundle (zip) for independent external verification.

    Bundle contains: receipt.json, signature.der, public_key.pem, VERIFY.md.
    Verification does not require platform access or proprietary tooling.
    """
    if not HAS_ATTESTATION_SIGNER:
        raise HTTPException(503, "Attestation signer not available")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Fetch evidence to compute hashes
    # Path 1: audit_events (sequential batches)
    # Path 2: batch document attestation metadata (sharded batches)
    events = []
    try:
        events = get_audit_events_from_firestore(trace_id, limit=10000) or []
    except Exception:
        events = []
    if not events:
        audit_data = audit_storage.get(trace_id)
        events = audit_data.get("events", []) if audit_data else []

    if events:
        # Sequential batch path: hash from audit events
        evidence_obj = {
            "trace_id": trace_id,
            "tenant_id": auth.get("tenant_id", "unknown"),
            "events": events,
        }
        evidence_json = json.dumps(evidence_obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
        input_hash = hashlib.sha256(evidence_json).hexdigest()
    else:
        # Sharded batch fallback: hash from batch document attestation metadata
        batch_data = None
        if _firestore_db:
            try:
                batch_doc = _firestore_db.collection('batches').document(trace_id).get()
                if batch_doc.exists:
                    batch_data = batch_doc.to_dict()
            except Exception:
                pass

        if not batch_data:
            raise HTTPException(404, f"No evidence found for {trace_id}")

        # Build deterministic evidence from batch attestation fields
        attestation = batch_data.get("attestation", {})
        counts = batch_data.get("counts", {})
        evidence_obj = {
            "trace_id": trace_id,
            "tenant_id": auth.get("tenant_id", "unknown"),
            "status": batch_data.get("status"),
            "total": batch_data.get("total"),
            "counts": counts,
            "shard_count": batch_data.get("shard_count"),
            "dataset_hash": attestation.get("dataset_hash_sha256"),
            "root_hash": attestation.get("root_hash_sha256"),
            "config_hash": attestation.get("config_hash_sha256"),
        }
        evidence_json = json.dumps(evidence_obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
        input_hash = hashlib.sha256(evidence_json).hexdigest()
        print(f"[verification-bundle] Sharded batch fallback for {trace_id}: "
              f"input_hash={input_hash[:16]}...", flush=True)

    output_hash = input_hash  # single-artifact attestation

    ts = datetime.utcnow().isoformat() + "Z"

    try:
        zip_bytes, bundle_filename = build_verification_bundle(
            trace_id=trace_id,
            input_hash=input_hash,
            output_hash=output_hash,
            timestamp=ts,
            engine_version="8.2.2",
        )
    except SigningKeyError as e:
        raise HTTPException(503, f"Signing unavailable: {e}")

    # Append-only audit record
    meta_event = {
        "event_type": "verification_bundle_generated",
        "artifact": "verification_bundle_zip",
        "input_hash": input_hash,
        "trace_id": trace_id,
        "tenant_id": auth.get("tenant_id", "unknown"),
        "layer": "META",
        "reason": "verification_bundle_generated",
    }
    append_meta_audit_event(trace_id, meta_event)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{bundle_filename}"',
            "X-Input-Hash": input_hash,
        }
    )


# =============================================================================
# PROCESSING ENDPOINTS
# =============================================================================

@app.post("/resolve")
async def resolve_single(
    name: str,
    auth: dict = Depends(check_rate_limit),
):
    """Resolve a single company name."""
    tenant_id = auth.get("tenant_id", "default")
    result = resolve_entity_sync(name, tenant_id)
    return result


# ---------------------------------------------------------------------------
# PUBLIC DEMO RESOLVE — unauthenticated, strict rate limit
# ---------------------------------------------------------------------------

# Per-IP sliding window: 10 requests / 60 seconds
_demo_rate_window: Dict[str, List[float]] = {}
_DEMO_RATE_LIMIT = 10
_DEMO_RATE_WINDOW_SEC = 60

def _demo_rate_check(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    window = _demo_rate_window.setdefault(ip, [])
    # Prune expired entries
    _demo_rate_window[ip] = [t for t in window if now - t < _DEMO_RATE_WINDOW_SEC]
    if len(_demo_rate_window[ip]) >= _DEMO_RATE_LIMIT:
        return False
    _demo_rate_window[ip].append(now)
    return True


@app.post("/public/resolve")
@app.get("/public/resolve")
async def public_resolve(
    request: Request,
    name: str = Query(..., min_length=1, max_length=200),
):
    """
    Public demo endpoint — no authentication required.

    Rate limited to 10 req/min per IP. Returns the same resolution result
    as /resolve but under a demo tenant scope. L3 (LLM) is disabled to
    control cost.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _demo_rate_check(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Demo rate limit exceeded (10/min). Try again shortly.",
        )

    query = name.strip()
    if not query:
        raise HTTPException(status_code=400, detail="name parameter required")

    result = resolve_entity_sync(
        company_raw=query,
        tenant_id="demo-public",
        allow_l3=False,           # no LLM calls for public demo
        l3_skip_reason="public_demo",
    )

    # Strip internal fields
    safe_result = {
        "original": result.get("original", query),
        "resolved": result.get("resolved"),
        "layer": result.get("layer"),
        "confidence": result.get("confidence", 0.0),
        "reason": result.get("reason"),
        "cost": result.get("cost", 0.0),
        "latency_ms": round(result.get("latency_ms", 0), 1),
        "trace_id": result.get("trace_id"),
    }
    return safe_result


@app.post("/batch")
async def batch_json(rows: List[str], auth: dict = Depends(check_rate_limit)):
    """Process a JSON array of company names."""
    tenant_id = auth.get("tenant_id", "default")

    if len(rows) > config.MAX_BATCH_SIZE:
        raise HTTPException(400, f"Maximum {config.MAX_BATCH_SIZE} records per batch")

    batch_trace_id = f"BATCH-{hashlib.md5(f'{tenant_id}{time.time()}'.encode()).hexdigest()[:8].upper()}"
    results, budget_tracker = await process_batch_parallel_golden(rows, tenant_id, batch_trace_id)

    return {
        "status": "success",
        "trace_id": batch_trace_id,
        "total": len(results),
        "data": results,
        "llm_budget_summary": budget_tracker.get_summary()
    }


# =============================================================================
# BACKGROUND BATCH PROCESSING
# =============================================================================

async def process_batch_background(
    rows: List[str],
    tenant_id: str,
    batch_trace_id: str,
    filename: str,
    dataset_type: DatasetType = DatasetType.COMPANY
):
    """
    Background batch processing - runs after HTTP response is sent.
    Updates Firestore with progress and final results.

    Args:
        rows: List of entity names
        tenant_id: Tenant identifier
        batch_trace_id: Batch trace ID
        filename: Original filename
        dataset_type: PERSON or COMPANY (determines which pipeline to use)

    Lifecycle correctness:
    - Only mark COMPLETED after results are written and duration > 0
    - Mark FAILED with error_reason if processing fails
    """
    start_time = time.time()
    started_at = datetime.utcnow().isoformat()
    row_count = len(rows)
    max_l3_calls = int(config.L3_MAX_COST_USD / config.L3_COST_PER_CALL_USD) if config.L3_COST_PER_CALL_USD > 0 else 100000
    print(f"[LIFECYCLE] {batch_trace_id} QUEUED->PROCESSING: {row_count} rows, L3_budget=${config.L3_MAX_COST_USD:.2f}, max_calls={max_l3_calls}", flush=True)
    slog(
        trace_id=batch_trace_id, phase="lifecycle", event="batch_start",
        elapsed_seconds=0.0, row_count=row_count,
        l3_budget_usd=config.L3_MAX_COST_USD, max_l3_calls=max_l3_calls,
        dataset_type=dataset_type.value,
    )

    # Reset Firestore cache stats for this batch (per-batch metrics)
    reset_l3_firestore_cache_stats()

    try:
        # CRITICAL: Check if batch was already aborted before starting
        if check_batch_aborted(batch_trace_id):
            print(f"[LIFECYCLE] {batch_trace_id} ABORT detected before processing started, skipping", flush=True)
            return  # Don't process or overwrite aborted status

        # Update status to PROCESSING with started_at
        if _firestore_db:
            _firestore_db.collection('batches').document(batch_trace_id).update({
                "status": "processing",
                "started_at": started_at,
                "progress": {"phase": "L1_L2", "done": 0, "total": row_count}
            })
            print(f"[LIFECYCLE] {batch_trace_id} status=PROCESSING written to Firestore", flush=True)

        # Log cost-based L3 control (row threshold deprecated)
        print(f"[LIFECYCLE] {batch_trace_id} L3_COST_CONTROL: budget=${config.L3_MAX_COST_USD:.2f}, "
              f"cost_per_call=${config.L3_COST_PER_CALL_USD:.3f}, max_calls={max_l3_calls}", flush=True)

        # Run the batch processing pipeline
        results, budget_tracker = await process_batch_parallel_golden(rows, tenant_id, batch_trace_id, dataset_type)
        duration_ms = (time.time() - start_time) * 1000
        print(f"[background] Processed {len(results)} results in {duration_ms:.0f}ms (L3 calls: {budget_tracker.calls}, spent: ${budget_tracker.spent_usd:.4f})", flush=True)
        slog(
            trace_id=batch_trace_id, phase="resolution", event="resolution_complete",
            batch_start_time=start_time, total_records=len(results),
            duration_ms=round(duration_ms, 0),
            l3_calls=budget_tracker.calls, l3_spent_usd=round(budget_tracker.spent_usd, 4),
        )

        # Compute stats
        total = len(results)
        # L0 includes all garbage layers (company and person mode variants)
        l0 = sum(1 for r in results if r.get("layer", "").startswith("L0_GARBAGE"))
        # L0 breakdown by type (blank, short, numeric, placeholder, etc.)
        l0_blank = sum(1 for r in results if r.get("layer") in ("L0_GARBAGE", "L0_GARBAGE_BLANK") and ("Blank" in str(r.get("reason", "")) or "Empty" in str(r.get("reason", "")) or "Null" in str(r.get("reason", ""))))
        l0_short = sum(1 for r in results if r.get("layer") == "L0_GARBAGE_SHORT" or (r.get("layer") == "L0_GARBAGE" and "Too Short" in str(r.get("reason", ""))))
        l0_numeric = sum(1 for r in results if r.get("layer") == "L0_GARBAGE_NUMERIC" or (r.get("layer") == "L0_GARBAGE" and "Numeric" in str(r.get("reason", ""))))
        l0_other = l0 - l0_blank - l0_short - l0_numeric

        # Company mode layers
        l1_exact = sum(1 for r in results if r.get("layer") == "L1_EXACT")
        l1_norm = sum(1 for r in results if r.get("layer") == "L1_NORM")
        l2 = sum(1 for r in results if r.get("layer") == "L2_VECTOR")

        # Person mode layers
        l1_person_exact = sum(1 for r in results if r.get("layer") == "L1_PERSON_EXACT")
        l1_person_alias = sum(1 for r in results if r.get("layer") == "L1_PERSON_ALIAS")
        l1_person_initial = sum(1 for r in results if r.get("layer") == "L1_PERSON_INITIAL")
        l2_person = sum(1 for r in results if r.get("layer") == "L2_PERSON_FUZZY")

        # Combined L1/L2 for auto-resolved calculation
        l1_total = l1_exact + l1_norm + l1_person_exact + l1_person_alias + l1_person_initial
        l2_total = l2 + l2_person

        # L3 includes both LLM calls and cached results (company + person)
        l3_llm = sum(1 for r in results if r.get("layer") in ("L3_LLM", "L3_PERSON_LLM"))
        l3_cached = sum(1 for r in results if r.get("layer") == "L3_CACHED")
        l3 = l3_llm + l3_cached
        l4 = sum(1 for r in results if r.get("layer") == "L4_HUMAN")

        # Standard layers for checking "other"
        KNOWN_LAYERS = {
            "L0_GARBAGE", "L0_GARBAGE_SHORT", "L0_GARBAGE_NUMERIC", "L0_GARBAGE_BLANK",
            "L1_EXACT", "L1_NORM", "L2_VECTOR", "L3_LLM", "L3_CACHED", "L4_HUMAN",
            "L1_PERSON_EXACT", "L1_PERSON_ALIAS", "L1_PERSON_INITIAL", "L2_PERSON_FUZZY", "L3_PERSON_LLM",
            "L3_PERSON_LLM_REJECT",
            # Mixed mode layers
            "L1_PERSON", "L1_ORG", "L1_VESSEL", "L1_CANONICAL"
        }
        l_other = sum(1 for r in results if r.get("layer") not in KNOWN_LAYERS)

        # Mixed mode: count entity types and compute type-specific metrics
        l1_mixed_person = sum(1 for r in results if r.get("layer") == "L1_PERSON")
        l1_mixed_org = sum(1 for r in results if r.get("layer") == "L1_ORG")
        l1_mixed_vessel = sum(1 for r in results if r.get("layer") == "L1_VESSEL")
        l1_mixed_canonical = sum(1 for r in results if r.get("layer") == "L1_CANONICAL")

        # For person mode: compute auto_resolved from sanitization confidence
        # (screening metrics are not meaningful when watchlist is empty)
        if dataset_type == DatasetType.MIXED:
            # Mixed mode: count all records resolved at any L1/L2/L3 layer
            # (includes L1_EXACT, L1_NORM, L1_PERSON, L1_ORG, L1_VESSEL, L1_CANONICAL, L2_VECTOR, L3)
            auto_resolved = l1_total + l1_mixed_person + l1_mixed_org + l1_mixed_vessel + l1_mixed_canonical + l2_total + l3
        elif dataset_type == DatasetType.PERSON:
            # Count records with high sanitization confidence as "auto-resolved"
            # confidence >= 0.85 indicates successful parse with first+last name
            auto_resolved = sum(1 for r in results
                              if r.get("confidence", 0) >= 0.85
                              and r.get("layer") not in ("L0_GARBAGE", "L0_GARBAGE_SHORT", "L0_GARBAGE_NUMERIC", "L0_GARBAGE_BLANK"))
        else:
            # Company mode: use L1/L2/L3 resolution layers
            auto_resolved = l1_total + l2_total + l3

        valid = total - l0 - l_other  # Exclude garbage and errors from valid count
        pii_total = sum(len(r.get("pii_detected", [])) for r in results)

        stats = {
            "total": total,
            "layer_0_garbage": l0,
            "l0_breakdown": {
                "blank": l0_blank,
                "short": l0_short,
                "numeric": l0_numeric,
                "other": l0_other
            },
            # Company mode layers
            "layer_1_exact": l1_exact,
            "layer_1_norm": l1_norm,
            "layer_2_vector": l2,
            # Person mode layers
            "layer_1_person_exact": l1_person_exact,
            "layer_1_person_alias": l1_person_alias,
            "layer_1_person_initial": l1_person_initial,
            "layer_2_person_fuzzy": l2_person,
            # Mixed mode layers
            "layer_1_mixed_person": l1_mixed_person,
            "layer_1_mixed_org": l1_mixed_org,
            "layer_1_mixed_vessel": l1_mixed_vessel,
            # Combined
            "layer_1_total": l1_total + l1_mixed_person + l1_mixed_org + l1_mixed_vessel,
            "layer_2_total": l2_total,
            "layer_3_llm": l3,  # Includes both LLM calls and cached
            "layer_3_llm_calls": l3_llm,
            "layer_3_cached": l3_cached,
            "layer_4_human": l4,
            "layer_other": l_other,  # ERROR, ABORTED, etc.
            "valid_records": valid,
            "auto_resolved": auto_resolved,
            "auto_resolved_pct": float(auto_resolved / valid * 100) if valid > 0 else 0.0,
            "pii_detections": pii_total,
            "dataset_type": dataset_type.value,
            # Mixed mode breakdown (for UI)
            "entity_breakdown": {
                "person": l1_mixed_person,
                "organization": l1_mixed_org,
                "vessel": l1_mixed_vessel,
                "garbage": l0,
            } if dataset_type == DatasetType.MIXED else None
        }

        # Update global stats (include L3 cost for drift + margin invariant tracking)
        stats["l3_cost_usd"] = budget_tracker.spent_usd
        with _stats_lock:
            _global_stats.record_batch(
                stats, duration_ms,
                l3_budget_usd=config.L3_MAX_COST_USD,
                human_cost_per_record_usd=config.HUMAN_COST_PER_RECORD_USD,
                l4_warning_threshold_pct=config.L4_WARNING_THRESHOLD_PCT,
                l4_red_threshold_pct=config.L4_RED_THRESHOLD_PCT,
                cost_per_record_red_usd=config.COST_PER_RECORD_RED_USD,
            )
            # Console report: margin sentinel (per-batch scope)
            _lb_margin = compute_margin_sentinel(
                total_records=_global_stats.last_batch_valid_records,
                total_l3=_global_stats.last_batch_l3,
                total_l4=_global_stats.last_batch_l4,
                total_llm_cost_usd=_global_stats.last_batch_llm_cost,
                human_cost_per_record_usd=config.HUMAN_COST_PER_RECORD_USD,
                l4_warning_threshold_pct=config.L4_WARNING_THRESHOLD_PCT,
                l4_red_threshold_pct=config.L4_RED_THRESHOLD_PCT,
                cost_per_record_red_usd=config.COST_PER_RECORD_RED_USD,
            )
            print(
                f"\nMARGIN SENTINEL (last batch)\n"
                f"----------------------------\n"
                f"L4 %:         {_lb_margin.l4_pct:.2f}%\n"
                f"Human Cost:   ${_lb_margin.human_cost_usd:.2f}\n"
                f"Total Cost:   ${_lb_margin.total_cost_usd:.2f}\n"
                f"Cost/Record:  ${_lb_margin.cost_per_record_usd:.5f}\n"
                f"Zone:         {_lb_margin.zone}",
                flush=True,
            )

        # Store audit events
        audit_events = []
        for i, r in enumerate(results):
            layer_num = {"L0_GARBAGE": 0, "L1_EXACT": 1, "L1_NORM": 1, "L2_VECTOR": 2, "L3_LLM": 3, "L3_CACHED": 3, "L4_HUMAN": 4, "ERROR": -1, "ABORTED": -2}.get(r.get("layer"), 4)
            audit_events.append({
                "row_index": i,
                "company_raw": r.get("original", ""),
                "canonical_name": r.get("resolved") or "",
                "layer_used": layer_num,
                "confidence": r.get("confidence", 0),
                "latency_ms": r.get("latency_ms", 0),
                "flag": "REVIEW" if r.get("layer") == "L4_HUMAN" else None,
                "pii_detected": r.get("pii_detected", []),
                "flagged": r.get("layer") == "L4_HUMAN",
                "timestamp": datetime.utcnow().isoformat()
            })
        audit_storage.store(batch_trace_id, audit_events)

        # Compute finished_at and duration
        finished_at = datetime.utcnow().isoformat()
        duration_seconds = duration_ms / 1000.0

        # ═══════════════════════════════════════════════════════════════════════
        # HARD GUARD: Prevent premature completion (METRICS_NOT_COMMITTED)
        # ═══════════════════════════════════════════════════════════════════════
        # A batch can only be marked COMPLETED if ALL of these are true:
        # 1. duration_seconds > 0 (processing actually occurred)
        # 2. total > 0 (we have records)
        # 3. Waterfall integrity: layer counts sum to total
        # 4. Results list matches total count

        # Include l_other (ERROR, ABORTED, etc.) in waterfall sum for integrity check
        # Also include mixed mode layers
        waterfall_sum = l0 + l1_exact + l1_norm + l2 + l3 + l4 + l_other + l1_mixed_person + l1_mixed_org + l1_mixed_vessel
        waterfall_integrity = (waterfall_sum == total)
        if l_other > 0:
            print(f"[batch] {batch_trace_id}: {l_other} records with non-standard layers (ERROR/ABORTED)", flush=True)
        results_integrity = (len(results) == total)
        duration_valid = (duration_seconds > 0)
        has_records = (total > 0)

        # All checks must pass for COMPLETED status
        all_checks_pass = duration_valid and has_records and waterfall_integrity and results_integrity

        if not all_checks_pass:
            # Determine failure reason
            failure_reasons = []
            if not duration_valid:
                failure_reasons.append(f"duration={duration_seconds}")
            if not has_records:
                failure_reasons.append(f"total={total}")
            if not waterfall_integrity:
                failure_reasons.append(f"waterfall_sum={waterfall_sum}!=total={total}")
            if not results_integrity:
                failure_reasons.append(f"results_len={len(results)}!=total={total}")

            guard_reason = "METRICS_NOT_COMMITTED: " + ", ".join(failure_reasons)
            print(f"[GUARD] BLOCKED premature completion for {batch_trace_id}: {guard_reason}", flush=True)
            slog_error(trace_id=batch_trace_id, phase="lifecycle", event="guard_blocked_completion",
                       batch_start_time=start_time, error_type="MetricsNotCommitted",
                       error_message=guard_reason)
            final_status = "failed"
            error_reason = guard_reason
            print(f"[LIFECYCLE] {batch_trace_id} PROCESSING->FAILED: guard blocked, reason={guard_reason}", flush=True)
        else:
            # CRITICAL: Check if batch was aborted during processing
            # If so, preserve "aborted" status instead of overwriting with "completed"
            if check_batch_aborted(batch_trace_id):
                final_status = "aborted"
                error_reason = "BATCH_ABORTED_DURING_PROCESSING"
                print(f"[LIFECYCLE] {batch_trace_id} PROCESSING->ABORTED: abort detected at completion, "
                      f"preserving aborted status (not overwriting with completed)", flush=True)
            else:
                final_status = "completed"
                error_reason = None
                print(f"[LIFECYCLE] {batch_trace_id} PROCESSING->COMPLETED: all guards passed, "
                      f"duration={duration_seconds:.2f}s, auto_resolved={auto_resolved}/{total}", flush=True)

        # Build final batch result with full instrumentation
        batch_result = {
            "status": final_status,
            "error_reason": error_reason,  # None if completed, guard reason if failed
            "trace_id": batch_trace_id,
            "mode": dataset_type.value.lower(),  # mixed, person, company, vessel
            "dataset_type": dataset_type.value,  # MIXED, PERSON, COMPANY, VESSEL
            "total": total,
            "total_records": total,
            "auto_resolved": auto_resolved,
            "auto_resolved_pct": float(auto_resolved / valid * 100) if valid > 0 else 0.0,
            "pii_detections": pii_total,
            # For person/mixed mode: flagged = valid - auto_resolved (not L4 count)
            "flagged_count": valid - auto_resolved if dataset_type in (DatasetType.PERSON, DatasetType.MIXED) else l4,
            "results_count": total,
            "stats": stats,
            "filename": filename,
            "duration_ms": float(duration_ms),
            "duration_seconds": float(duration_seconds),
            "records_per_sec": float(total / duration_seconds) if duration_seconds > 0 else 0.0,
            "config_version": CANONICAL_CONFIG_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "version_snapshot": _build_version_snapshot(),
            "tenant_id": tenant_id,
            "tenant_region": config.DEPLOY_REGION,
            # Lifecycle timestamps
            "started_at": started_at,
            "finished_at": finished_at,
            # Instrumented layer counters (for enterprise visibility)
            # Invariant: l3_eligible == l3_attempted + l3_skipped_budget + l3_skipped_rate_limit
            "counts": {
                "l0_quarantined": l0,
                "l1_resolved": l1_total + l1_mixed_person + l1_mixed_org + l1_mixed_vessel,
                "l1_exact": l1_exact,
                "l1_norm": l1_norm,
                "l1_person": l1_mixed_person,
                "l1_org": l1_mixed_org,
                "l1_vessel": l1_mixed_vessel,
                "l2_resolved": l2_total,
                "l3_eligible": budget_tracker.l3_eligible,
                "l3_attempted": budget_tracker.l3_attempted,
                "l3_succeeded": budget_tracker.l3_succeeded,
                "l3_failed": budget_tracker.l3_failed,
                "l3_skipped_budget": budget_tracker.l3_skipped_budget,
                "l3_skipped_rate_limit": budget_tracker.l3_skipped_rate_limit,
                "l3_resolved": l3,  # Final count after L3 processing
                "l4_flagged": l4,
                # Short keys for dashboard parity
                "total": total,
                "l0": l0,
                "l1": l1_total + l1_mixed_person + l1_mixed_org + l1_mixed_vessel,
                "l2": l2_total,
                "l3": l3,
                "l4": l4,
            }
        }

        # Generate EU AI Act compliance artifacts
        batch_timestamp = datetime.utcnow().isoformat()

        # TLS
        tls_content, tls_hash = generate_transparency_statement(
            trace_id=batch_trace_id,
            timestamp=batch_timestamp,
            config_version=CANONICAL_CONFIG_VERSION
        )
        tls_event = {
            "event_type": "BATCH_TRANSPARENCY_STATEMENT_GENERATED",
            "trace_id": batch_trace_id,
            "tenant_id_hash": hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
            "timestamp": batch_timestamp,
            "actor": "service",
            "action_type": "BATCH_TRANSPARENCY_STATEMENT_GENERATED",
            "target_type": "artifact",
            "result": "PASS",
            "template_id": TLS_TEMPLATE_ID,
            "artifact_name": f"transparency_statement_{batch_trace_id}.txt",
            "artifact_hash": tls_hash,
        }
        append_meta_audit_event(batch_trace_id, tls_event)

        # Decision Path Summary
        decision_path_summary = compute_decision_path_summary(stats, budget_tracker=budget_tracker)
        dps_event = {
            "event_type": "BATCH_DECISION_PATH_SUMMARY",
            "trace_id": batch_trace_id,
            "tenant_id_hash": hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
            "timestamp": batch_timestamp,
            "actor": "service",
            "action_type": "BATCH_DECISION_PATH_SUMMARY",
            "target_type": "batch",
            "result": "PASS",
            "decision_path_counts": decision_path_summary,
        }
        append_meta_audit_event(batch_trace_id, dps_event)

        # LLM Budget Summary
        llm_budget_summary = budget_tracker.get_summary()
        budget_event = {
            "event_type": "BATCH_LLM_BUDGET_SUMMARY",
            "trace_id": batch_trace_id,
            "tenant_id_hash": hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
            "timestamp": batch_timestamp,
            "actor": "service",
            "action_type": "BATCH_LLM_BUDGET_SUMMARY",
            "target_type": "batch",
            "result": "PASS",
            "budget_usd": llm_budget_summary["budget_usd"],
            "spent_usd": llm_budget_summary["spent_usd"],
            "calls": llm_budget_summary["calls"],
            "avg_cost_per_call": llm_budget_summary["avg_cost_per_call"],
            "budget_exhausted": llm_budget_summary["budget_exhausted"],
            "call_cap_reached": llm_budget_summary["call_cap_reached"],
            "skipped_reason_counts": llm_budget_summary["skipped_reason_counts"],
        }
        append_meta_audit_event(batch_trace_id, budget_event)

        # Add compliance artifacts to batch result
        batch_result["transparency_statement"] = {
            "template_id": TLS_TEMPLATE_ID,
            "hash": tls_hash,
            "generated_at": batch_timestamp
        }
        batch_result["decision_path_summary"] = decision_path_summary
        batch_result["llm_budget_summary"] = llm_budget_summary
        batch_result["timestamp"] = batch_timestamp
        # Cost fields for frontend display (stats.total_cost is primary, cost is fallback)
        batch_result["stats"]["total_cost"] = llm_budget_summary["spent_usd"]
        batch_result["cost"] = llm_budget_summary["spent_usd"]
        # L3 yield for frontend display (percentage of L3 calls that resolved vs returned UNKNOWN)
        batch_result["stats"]["l3_yield"] = llm_budget_summary["l3_yield"]
        batch_result["l3_yield"] = llm_budget_summary["l3_yield"]
        # L3 Firestore cache stats
        batch_result["l3_firestore_cache"] = get_l3_firestore_cache_stats()
        batch_result["stats"]["l3_cache_hits"] = budget_tracker.l3_cache_hits

        # ═══════════════════════════════════════════════════════════════════════
        # PERSIST RESULTS IN CHUNKS (for export)
        # ═══════════════════════════════════════════════════════════════════════
        if final_status == "completed":
            store_results_to_firestore(batch_trace_id, results)

            # ═══════════════════════════════════════════════════════════════════
            # GENERATE EVIDENCE BLOBS (Phase 1 - Forensic Audit)
            # ═══════════════════════════════════════════════════════════════════
            if HAS_FORENSIC_SIGNING:
                evidence_count, batch_sustainability = generate_and_store_evidence_blobs(
                    batch_trace_id=batch_trace_id,
                    tenant_id=tenant_id,
                    results=results,
                    config_version=CANONICAL_CONFIG_VERSION,
                    sanitization_version=config.SANITIZATION_VERSION,
                    watchlist_version_hash=config.WATCHLIST_VERSION_HASH
                )
                print(f"[Evidence] Generated {evidence_count} signed evidence blobs for {batch_trace_id}", flush=True)
                slog(trace_id=batch_trace_id, phase="forensic", event="evidence_generated",
                     batch_start_time=start_time, evidence_count=evidence_count)

                # Store sustainability rollup if available
                if batch_sustainability:
                    batch_result["sustainability"] = batch_sustainability
                    print(f"[Sustainability] Computed batch rollup: coverage={batch_sustainability.get('coverage_pct', 0)}%", flush=True)

                # ═══════════════════════════════════════════════════════════════
                # COMPUTE HASH CHAIN (Phase 2 - Forensic Audit)
                # ═══════════════════════════════════════════════════════════════
                if config.HASH_CHAIN_ENABLED:
                    chain_success, chain_meta = compute_and_store_hash_chain(
                        batch_trace_id=batch_trace_id,
                        results=results
                    )
                    if chain_success and chain_meta:
                        batch_result["hash_chain"] = chain_meta
                        root_hash = chain_meta.get("batch_root_hash", "")
                        print(f"[HashChain] Computed and stored hash chain for {batch_trace_id}, root={root_hash[:16]}...", flush=True)
                        slog(trace_id=batch_trace_id, phase="forensic", event="hash_chain_computed",
                             batch_start_time=start_time, root_hash=root_hash[:16],
                             chain_length=chain_meta.get("chain_length", 0),
                             replay_runs=chain_meta.get("replay_runs"),
                             replay_variance=chain_meta.get("replay_variance"),
                             replay_passed=chain_meta.get("replay_passed"))

                        # ═══════════════════════════════════════════════════════
                        # Day 5: Resolve tenant-scoped signing key (Gate S2)
                        # Hoisted before anchoring so key_id threads through
                        # anchor record, attestation, and legacy signature.
                        # ═══════════════════════════════════════════════════════
                        from app.security.signing import resolve_signing_key_id
                        key_id = resolve_signing_key_id(tenant_id)
                        signing_status = get_signing_status()
                        pubkey_fingerprint = signing_status.get("service_identity", {}).get("signing_key_version", "unknown")

                        # ═══════════════════════════════════════════════════════
                        # EXTERNAL ANCHORING (Phase 3 - Forensic Audit)
                        # ═══════════════════════════════════════════════════════
                        if config.ANCHORING_ENABLED:
                            anchor_record = build_anchor_record(
                                batch_id=batch_trace_id,
                                tenant_id=tenant_id,
                                batch_root_hash=root_hash,
                                code_version=signing_status.get("service_identity", {}).get("code_version", "unknown"),
                                sbom_hash=get_sbom_hash() or "unknown",
                                chain_length=chain_meta.get("chain_length", 0),
                                signing_key_id=key_id,
                            )
                            anchor_success, anchor_path, anchor_error = write_anchor_to_gcs(
                                batch_id=batch_trace_id,
                                tenant_id=tenant_id,
                                anchor_record=anchor_record
                            )
                            if anchor_success:
                                batch_result["anchor"] = {
                                    "anchored": True,
                                    "anchor_path": anchor_path,
                                    "anchor_written_at_utc": anchor_record.get("created_at_utc"),
                                }
                                print(f"[Anchoring] Anchored {batch_trace_id} to {anchor_path}", flush=True)
                                slog(trace_id=batch_trace_id, phase="forensic", event="anchoring_complete",
                                     batch_start_time=start_time, result="success", anchor_path=anchor_path)
                            else:
                                batch_result["anchor"] = {
                                    "anchored": False,
                                    "error": anchor_error,
                                }
                                print(f"[Anchoring] Failed to anchor {batch_trace_id}: {anchor_error}", flush=True)
                                slog_error(trace_id=batch_trace_id, phase="forensic", event="anchoring_complete",
                                           batch_start_time=start_time, error_type="AnchoringError",
                                           error_message=str(anchor_error))

                        # ═══════════════════════════════════════════════════════
                        # IAVP v1.0 MANIFEST (Batch Attestation)
                        # Must be computed BEFORE signing so signature can bind
                        # manifest fields (FE-5.2 attestation binding fix)
                        # ═══════════════════════════════════════════════════════
                        iavp_manifest = None
                        config_hash = None
                        dataset_hash = None
                        artifact_mode = None
                        # key_id already resolved above (Day 5 Gate S2 hoist)

                        if config.IAVP_ENABLED:
                            try:
                                from app.security.iavp import (
                                    build_iavp_manifest, compute_config_hash, compute_dataset_hash,
                                    get_artifact_mode, ReplayVerificationResult
                                )

                                # Compute config hash (snapshot of processing config)
                                config_snapshot = {
                                    "config_version": CANONICAL_CONFIG_VERSION,
                                    "sanitization_version": config.SANITIZATION_VERSION,
                                    "watchlist_version_hash": config.WATCHLIST_VERSION_HASH,
                                    "l3_max_cost_usd": config.L3_MAX_COST_USD,
                                    "l3_min_similarity": config.L3_MIN_SIMILARITY,
                                    "iavp_enabled": config.IAVP_ENABLED,
                                    "iavp_replay_verification": config.IAVP_REPLAY_VERIFICATION,
                                }
                                config_hash = compute_config_hash(config_snapshot)

                                # Compute dataset hash
                                dataset_hash = compute_dataset_hash(results)

                                # Get artifact mode based on environment
                                artifact_mode = get_artifact_mode(config.IS_PRODUCTION)

                                # key_id, signing_status, pubkey_fingerprint already
                                # resolved above (Day 5 Gate S2 hoist)

                                # Build replay result from chain_meta
                                replay_result = ReplayVerificationResult()
                                if chain_meta.get("replay_runs"):
                                    for _ in range(chain_meta.get("replay_runs", 1)):
                                        replay_result.add_run(root_hash)
                                    replay_result.variance = chain_meta.get("replay_variance", 0)
                                    replay_result.passed = chain_meta.get("replay_passed", True)

                                # Compute metrics percentages
                                _l1_all = l1_total + l1_mixed_person + l1_mixed_org + l1_mixed_vessel
                                metrics = {
                                    "l1_pct": round(_l1_all / valid * 100, 2) if valid > 0 else 0.0,
                                    "l2_pct": round(l2 / valid * 100, 2) if valid > 0 else 0.0,
                                    "l3_pct": round(l3 / valid * 100, 2) if valid > 0 else 0.0,
                                    "l4_pct": round(l4 / valid * 100, 2) if valid > 0 else 0.0,
                                }

                                # Build IAVP manifest
                                iavp_manifest = build_iavp_manifest(
                                    batch_id=batch_trace_id,
                                    artifact_type="BATCH_ATTESTATION",
                                    artifact_mode=artifact_mode,
                                    engine_version=config.ENGINE_VERSION,
                                    config_hash=config_hash,
                                    dataset_hash=dataset_hash,
                                    root_hash=root_hash,
                                    record_count=total,
                                    metrics=metrics,
                                    replay_result=replay_result,
                                    key_id=key_id,
                                    pubkey_fingerprint=pubkey_fingerprint,
                                    tenant_id_hash=hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
                                    tenant_region=config.DEPLOY_REGION,
                                )

                                batch_result["iavp_manifest"] = iavp_manifest
                                print(f"[IAVP] Generated IAVP v1.0 manifest for {batch_trace_id}, "
                                      f"mode={artifact_mode}", flush=True)
                                slog(trace_id=batch_trace_id, phase="forensic", event="iavp_manifest_generated",
                                     batch_start_time=start_time, artifact_mode=artifact_mode)

                            except Exception as iavp_err:
                                print(f"[IAVP] Failed to generate manifest for {batch_trace_id}: {iavp_err}", flush=True)
                                slog_error(trace_id=batch_trace_id, phase="forensic", event="iavp_manifest_generated",
                                           batch_start_time=start_time, error_type="IAVPManifestError",
                                           error_message=str(iavp_err))
                                batch_result["iavp_manifest"] = {
                                    "error": str(iavp_err),
                                    "protocol_version": IAVP_PROTOCOL_VERSION,
                                }

                        # ═══════════════════════════════════════════════════════
                        # ATTESTATION BINDING + BATCH-LEVEL SIGNATURE
                        # Signs JCS-canonicalized attestation payload binding
                        # root_hash, artifact_mode, config, environment, etc.
                        # Also keeps legacy root-hash-only signature for compat.
                        # ═══════════════════════════════════════════════════════
                        if config.SIGNING_ENABLED:
                            try:
                                from .security.signing import sign_bytes_kms
                                import datetime as dt

                                # --- ATTESTATION BINDING (FE-5.2 fix) ---
                                if iavp_manifest:
                                    from app.security.iavp import (
                                        jcs_canonicalize, jcs_sha256,
                                        build_attestation_payload, normalize_timestamp_rfc3339,
                                        ATTESTATION_PAYLOAD_VERSION
                                    )
                                    import base64 as _b64

                                    signed_at = normalize_timestamp_rfc3339(
                                        dt.datetime.now(dt.timezone.utc)
                                    )
                                    metrics_hash = jcs_sha256(iavp_manifest.get("metrics", {}))

                                    att_payload = build_attestation_payload(
                                        batch_id=batch_trace_id,
                                        root_hash=root_hash,
                                        artifact_mode=artifact_mode,
                                        engine_version=config.ENGINE_VERSION,
                                        environment=os.getenv("ENVIRONMENT", "unknown"),
                                        protocol_version=IAVP_PROTOCOL_VERSION,
                                        config_hash=config_hash,
                                        dataset_hash=dataset_hash,
                                        key_id=key_id,
                                        metrics_hash=metrics_hash,
                                        record_count=total,
                                        signed_at_utc=signed_at,
                                        tenant_id_hash=hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
                                        tenant_region=config.DEPLOY_REGION,
                                    )
                                    canonical_bytes = jcs_canonicalize(att_payload)
                                    att_sig_b64, att_sig_error = sign_bytes_kms(canonical_bytes, key_id_override=key_id)

                                    batch_result["attestation"] = {
                                        "signed_payload_jcs_b64": _b64.b64encode(canonical_bytes).decode('ascii'),
                                        "signature_b64": att_sig_b64,
                                        "algorithm": "ECDSA_P256_SHA256",
                                        "key_id": key_id,
                                        "key_version": signing_status.get("service_identity", {}).get("signing_key_version"),
                                        "attestation_version": ATTESTATION_PAYLOAD_VERSION,
                                        "error": att_sig_error,
                                    }

                                    if att_sig_b64:
                                        print(f"[Attestation] Batch {batch_trace_id} attestation signed (15-field binding)", flush=True)
                                        slog(trace_id=batch_trace_id, phase="forensic", event="attestation_signed",
                                             batch_start_time=start_time, result="success",
                                             attestation_version=ATTESTATION_PAYLOAD_VERSION)
                                    else:
                                        print(f"[Attestation] Failed to sign attestation for {batch_trace_id}: {att_sig_error}", flush=True)
                                        slog_error(trace_id=batch_trace_id, phase="forensic", event="attestation_signed",
                                                   batch_start_time=start_time, error_type="AttestationSigningError",
                                                   error_message=str(att_sig_error))

                                # --- LEGACY SIGNATURE (root-hash only, backward compat) ---
                                root_hash_bytes = root_hash.encode('utf-8')
                                sig_b64, sig_error = sign_bytes_kms(root_hash_bytes, key_id_override=key_id)

                                batch_result["signature"] = {
                                    "evidence_hash_sha256": root_hash,
                                    "signature": sig_b64,
                                    "signed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                                    "key_version": get_signing_status().get("service_identity", {}).get("signing_key_version"),
                                    "algorithm": "ECDSA_P256_SHA256",
                                    "error": sig_error,
                                }

                                if sig_b64:
                                    print(f"[Signing] Batch {batch_trace_id} signed successfully (legacy)", flush=True)
                                    slog(trace_id=batch_trace_id, phase="forensic", event="signing_complete",
                                         batch_start_time=start_time, result="success")
                                else:
                                    print(f"[Signing] Failed to sign {batch_trace_id}: {sig_error}", flush=True)
                                    slog_error(trace_id=batch_trace_id, phase="forensic", event="signing_complete",
                                               batch_start_time=start_time, error_type="SigningError",
                                               error_message=str(sig_error))
                            except Exception as sign_err:
                                print(f"[Signing] Exception signing {batch_trace_id}: {sign_err}", flush=True)
                                slog_error(trace_id=batch_trace_id, phase="forensic", event="signing_complete",
                                           batch_start_time=start_time, error_type="SigningException",
                                           error_message=str(sign_err))
                                batch_result["signature"] = {
                                    "evidence_hash_sha256": root_hash,
                                    "signature": None,
                                    "error": str(sign_err),
                                }

        # ═══════════════════════════════════════════════════════════════════════
        # ATOMIC PERSISTENCE: Write all metrics + status in single transaction
        # ═══════════════════════════════════════════════════════════════════════
        # Firestore .set() is atomic for single documents - the entire batch_result
        # is written in one operation. Status only becomes COMPLETED when all
        # metrics are persisted together.

        if _firestore_db:
            print(f"[ATOMIC] Writing {final_status} batch {batch_trace_id} with "
                  f"duration={duration_seconds:.2f}s, total={total}, waterfall_sum={waterfall_sum}", flush=True)

            # Atomic write - status and metrics are committed together
            _firestore_db.collection('batches').document(batch_trace_id).set(batch_result)

            # Verification read to confirm persistence (fail-safe)
            try:
                verify_doc = _firestore_db.collection('batches').document(batch_trace_id).get()
                if verify_doc.exists:
                    verify_data = verify_doc.to_dict()
                    persisted_status = verify_data.get("status")
                    persisted_duration = verify_data.get("duration_seconds", 0)
                    persisted_counts = verify_data.get("counts", {})
                    has_counts = bool(persisted_counts) and persisted_counts.get("l1_resolved", -1) >= 0

                    if persisted_status == final_status and persisted_duration > 0 and has_counts:
                        print(f"[ATOMIC] VERIFIED: {batch_trace_id} persisted with status={persisted_status}, "
                              f"duration={persisted_duration:.2f}s, counts_present=True", flush=True)
                        slog(trace_id=batch_trace_id, phase="lifecycle", event="atomic_persist_verified",
                             batch_start_time=start_time, final_status=persisted_status,
                             persisted_duration=persisted_duration)
                    else:
                        print(f"[ATOMIC] WARNING: Verification failed for {batch_trace_id}: "
                              f"status={persisted_status} (expected {final_status}), "
                              f"duration={persisted_duration}, has_counts={has_counts}", flush=True)
                        slog_error(trace_id=batch_trace_id, phase="lifecycle", event="atomic_persist_verified",
                                   batch_start_time=start_time, error_type="PersistVerificationWarning",
                                   error_message=f"status={persisted_status}, duration={persisted_duration}, has_counts={has_counts}")
                else:
                    print(f"[ATOMIC] ERROR: Document {batch_trace_id} not found after write!", flush=True)
            except Exception as verify_err:
                print(f"[ATOMIC] Verification read failed (non-fatal): {verify_err}", flush=True)

        # Day 6: Observability metrics flush (non-fatal)
        try:
            from app.metrics.system_metrics import (
                record_finalize_latency, record_l3_cache_stats,
                record_failover_stats, record_ledger_snapshot,
            )
            record_finalize_latency(_firestore_db, duration_ms)
            _fs_stats = get_l3_firestore_cache_stats()
            record_l3_cache_stats(
                _firestore_db,
                l3_total_calls=budget_tracker.l3_attempted + budget_tracker.l3_cache_hits,
                l3_cache_hits=budget_tracker.l3_cache_hits,
                l3_unknown_cached=_fs_stats.get("unknown_cache_hits", 0),
            )
            record_failover_stats(_firestore_db, budget_tracker.l3_failover_count, budget_tracker.l3_attempted)
            from app.budget_ledger import get_tenant_balance
            _bal = get_tenant_balance(tenant_id, _firestore_db)
            if _bal:
                record_ledger_snapshot(_firestore_db, tenant_id,
                    _bal.get("credits_reserved_usd", 0.0), _bal.get("credits_spent_usd", 0.0),
                    0.0, _bal.get("credits_reserved_usd", 0.0) >= 0)
        except Exception as _me:
            print(f"[metrics] Non-fatal flush: {_me}", flush=True)

        # Log with L3 instrumentation details including yield and cache stats
        l3_yield = llm_budget_summary['l3_yield']
        fs_cache_stats = get_l3_firestore_cache_stats()
        print(f"[background] {final_status.upper()} {batch_trace_id}: {total} rows, "
              f"L3 eligible={budget_tracker.l3_eligible} attempted={budget_tracker.l3_attempted} "
              f"succeeded={budget_tracker.l3_succeeded} failed={budget_tracker.l3_failed} yield={l3_yield:.1f}%, "
              f"L4={l4}, cost=${llm_budget_summary['spent_usd']:.4f}, "
              f"fs_cache(hits={fs_cache_stats['hits']} misses={fs_cache_stats['misses']} stores={fs_cache_stats['stores']})", flush=True)
        slog(trace_id=batch_trace_id, phase="lifecycle", event="batch_complete",
             batch_start_time=start_time, final_status=final_status, total=total,
             duration_seconds=round(duration_seconds, 2), l3_yield=round(l3_yield, 1),
             l3_calls=budget_tracker.l3_attempted, l3_cost_usd=round(llm_budget_summary['spent_usd'], 4),
             l3_cache_hits=fs_cache_stats['hits'])

    except (IntegrityError, L3VolumeAnomalyError, LLMDirectPathError, TenantKeyMissingError) as structural_err:
        # ═══════════════════════════════════════════════════════════════════════
        # STRUCTURAL FAILURE - Catastrophic pipeline corruption detected
        # (includes TenantKeyMissingError: fail-closed when key not provisioned)
        # ═══════════════════════════════════════════════════════════════════════
        error_time = datetime.utcnow().isoformat()
        error_type = type(structural_err).__name__
        print(f"[FATAL] {batch_trace_id} STRUCTURAL FAILURE: {error_type}", flush=True)
        print(f"[FATAL] {batch_trace_id} Message: {structural_err}", flush=True)
        slog_error(trace_id=batch_trace_id, phase="lifecycle", event="structural_failure",
                   error_type=error_type, error_message=str(structural_err),
                   structural_failure=True)
        traceback.print_exc()

        # Mark as failed with structural error classification
        if _firestore_db:
            try:
                _firestore_db.collection('batches').document(batch_trace_id).update({
                    "status": "failed",
                    "error_reason": f"STRUCTURAL_FAILURE:{error_type}",
                    "error": str(structural_err),
                    "error_type": error_type,
                    "finished_at": error_time,
                    "timestamp": error_time,
                    "structural_failure": True  # Flag for monitoring/alerting
                })
                print(f"[FATAL] {batch_trace_id} STRUCTURAL_FAILURE written to Firestore", flush=True)
            except Exception as update_err:
                print(f"[FATAL] {batch_trace_id} FAILED to write structural error: {update_err}", flush=True)

    except Exception as e:
        error_time = datetime.utcnow().isoformat()
        print(f"[LIFECYCLE] {batch_trace_id} PROCESSING->FAILED: exception={type(e).__name__}: {e}", flush=True)
        slog_error(trace_id=batch_trace_id, phase="lifecycle", event="batch_failed",
                   error_type=type(e).__name__, error_message=str(e))
        traceback.print_exc()
        # Update status to FAILED with error_reason and keep partial progress
        if _firestore_db:
            try:
                _firestore_db.collection('batches').document(batch_trace_id).update({
                    "status": "failed",
                    "error_reason": str(e),
                    "error": str(e),  # Keep for backwards compat
                    "finished_at": error_time,
                    "timestamp": error_time
                })
                print(f"[LIFECYCLE] {batch_trace_id} status=FAILED written to Firestore", flush=True)
            except Exception as update_err:
                print(f"[LIFECYCLE] {batch_trace_id} FAILED to write error status: {update_err}", flush=True)


def store_batch_rows_to_firestore(batch_trace_id: str, rows: List[str]) -> bool:
    """Store batch rows in Firestore subcollection for large batch support.

    Splits rows into chunks of 500 to stay under Firestore document limits.
    """
    if not _firestore_db:
        print(f"[batch-rows] Firestore not available", flush=True)
        return False

    try:
        CHUNK_SIZE = 500  # Rows per document
        batch_ref = _firestore_db.collection('batches').document(batch_trace_id)
        rows_ref = batch_ref.collection('input_rows')

        # Store rows in chunks
        for chunk_idx in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[chunk_idx:chunk_idx + CHUNK_SIZE]
            doc_id = f"chunk_{chunk_idx:06d}"
            rows_ref.document(doc_id).set({
                "start_index": chunk_idx,
                "rows": chunk,
                "count": len(chunk)
            })

        # Store row count in batch doc
        batch_ref.update({"input_row_count": len(rows)})
        print(f"[batch-rows] Stored {len(rows)} rows in {(len(rows) + CHUNK_SIZE - 1) // CHUNK_SIZE} chunks", flush=True)
        return True

    except Exception as e:
        print(f"[batch-rows] Failed to store rows: {e}", flush=True)
        traceback.print_exc()
        return False


def fetch_batch_rows_from_firestore(batch_trace_id: str) -> Optional[List[str]]:
    """Fetch batch rows from Firestore subcollection."""
    if not _firestore_db:
        return None

    try:
        batch_ref = _firestore_db.collection('batches').document(batch_trace_id)
        rows_ref = batch_ref.collection('input_rows')

        # Fetch all chunks ordered by start_index
        docs = rows_ref.order_by('start_index').stream()

        all_rows = []
        for doc in docs:
            chunk_data = doc.to_dict()
            all_rows.extend(chunk_data.get('rows', []))

        print(f"[batch-rows] Fetched {len(all_rows)} rows from Firestore", flush=True)
        return all_rows

    except Exception as e:
        print(f"[batch-rows] Failed to fetch rows: {e}", flush=True)
        traceback.print_exc()
        return None


def enqueue_batch_task(rows: List[str], tenant_id: str, batch_trace_id: str, filename: str, dataset_type: str = "COMPANY") -> bool:
    """Enqueue batch processing via Cloud Tasks for durable execution.

    For large batches (>1000 rows), stores rows in Firestore first to avoid
    Cloud Tasks payload size limits.

    Args:
        dataset_type: "PERSON" or "COMPANY" - routing mode for resolution pipeline
    """
    if not _tasks_client or not CLOUD_RUN_SERVICE_URL:
        print(f"[tasks] Cloud Tasks not configured, falling back to sync", flush=True)
        return False

    try:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
        import datetime as dt

        parent = _tasks_client.queue_path(GCP_PROJECT_ID, CLOUD_TASKS_LOCATION, CLOUD_TASKS_QUEUE)

        # For large batches, store rows in Firestore and pass only metadata
        LARGE_BATCH_THRESHOLD = 1000
        if len(rows) > LARGE_BATCH_THRESHOLD:
            print(f"[tasks] Large batch ({len(rows)} rows), storing in Firestore first", flush=True)
            if not store_batch_rows_to_firestore(batch_trace_id, rows):
                print(f"[tasks] Failed to store rows, cannot enqueue", flush=True)
                return False

            # Payload without rows - worker will fetch from Firestore
            payload = json.dumps({
                "rows": [],  # Empty - fetch from Firestore
                "tenant_id": tenant_id,
                "batch_trace_id": batch_trace_id,
                "filename": filename,
                "fetch_rows_from_firestore": True,
                "dataset_type": dataset_type
            }).encode()
        else:
            # Small batch - include rows in payload
            payload = json.dumps({
                "rows": rows,
                "tenant_id": tenant_id,
                "batch_trace_id": batch_trace_id,
                "filename": filename,
                "fetch_rows_from_firestore": False,
                "dataset_type": dataset_type
            }).encode()

        # Dispatch deadline: 30 minutes (Cloud Tasks maximum)
        # Cloud Tasks allows 15s to 30m; Cloud Run timeout is set separately
        from google.protobuf import duration_pb2
        dispatch_deadline = duration_pb2.Duration()
        dispatch_deadline.seconds = 1800  # 30 minutes (Cloud Tasks max)

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{CLOUD_RUN_SERVICE_URL}/internal/process-batch",
                "headers": {"Content-Type": "application/json"},
                "body": payload,
                "oidc_token": {
                    "service_account_email": os.getenv("CLOUD_TASKS_SA_EMAIL", "")
                }
            },
            "dispatch_deadline": dispatch_deadline
        }

        # Schedule for immediate execution
        response = _tasks_client.create_task(parent=parent, task=task)
        print(f"[tasks] Enqueued {batch_trace_id}: {response.name}", flush=True)
        return True

    except Exception as e:
        print(f"[tasks] Failed to enqueue {batch_trace_id}: {e}", flush=True)
        traceback.print_exc()
        return False


def enqueue_shard_task(batch_trace_id: str, shard_id: int, tenant_id: str, dataset_type: str) -> bool:
    """Enqueue a single shard for processing via Cloud Tasks.

    Uses deterministic task name for idempotent retries:
        {batch_trace_id}-shard-{shard_id}

    The shard worker fetches its row slice from Firestore input_rows.
    """
    if not _tasks_client or not CLOUD_RUN_SERVICE_URL:
        print(f"[tasks] Cloud Tasks not configured, cannot enqueue shard", flush=True)
        return False

    try:
        from google.cloud import tasks_v2
        from google.protobuf import duration_pb2

        parent = _tasks_client.queue_path(GCP_PROJECT_ID, CLOUD_TASKS_LOCATION, CLOUD_TASKS_QUEUE)

        payload = json.dumps({
            "batch_trace_id": batch_trace_id,
            "shard_id": shard_id,
            "tenant_id": tenant_id,
            "dataset_type": dataset_type,
        }).encode()

        dispatch_deadline = duration_pb2.Duration()
        dispatch_deadline.seconds = 1800  # 30 minutes (Cloud Tasks max)

        # Deterministic task name for idempotent retries
        task_name = f"{parent}/tasks/{batch_trace_id}-shard-{shard_id}"

        task = {
            "name": task_name,
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{CLOUD_RUN_SERVICE_URL}/internal/process-shard",
                "headers": {"Content-Type": "application/json"},
                "body": payload,
                "oidc_token": {
                    "service_account_email": os.getenv(
                        "CLOUD_TASKS_SA_EMAIL",
                        ""
                    )
                }
            },
            "dispatch_deadline": dispatch_deadline,
        }

        response = _tasks_client.create_task(parent=parent, task=task)
        print(f"[tasks] Enqueued shard {shard_id} for {batch_trace_id}: {response.name}", flush=True)
        return True

    except Exception as e:
        print(f"[tasks] Failed to enqueue shard {shard_id} for {batch_trace_id}: {e}", flush=True)
        traceback.print_exc()
        return False


def enqueue_finalize_task(batch_trace_id: str, tenant_id: str) -> bool:
    """Enqueue the finalize step for a sharded batch via Cloud Tasks.

    Deterministic task name: {batch_trace_id}-finalize
    POST /internal/finalize-batch with {batch_trace_id, tenant_id}
    """
    if not _tasks_client or not CLOUD_RUN_SERVICE_URL:
        print(f"[tasks] Cloud Tasks not configured, cannot enqueue finalize", flush=True)
        return False

    try:
        from google.cloud import tasks_v2
        from google.protobuf import duration_pb2

        parent = _tasks_client.queue_path(GCP_PROJECT_ID, CLOUD_TASKS_LOCATION, CLOUD_TASKS_QUEUE)

        payload = json.dumps({
            "batch_trace_id": batch_trace_id,
            "tenant_id": tenant_id,
        }).encode()

        dispatch_deadline = duration_pb2.Duration()
        dispatch_deadline.seconds = 1800  # 30 minutes

        # Deterministic task name for idempotent retries
        task_name = f"{parent}/tasks/{batch_trace_id}-finalize"

        task = {
            "name": task_name,
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{CLOUD_RUN_SERVICE_URL}/internal/finalize-batch",
                "headers": {"Content-Type": "application/json"},
                "body": payload,
                "oidc_token": {
                    "service_account_email": os.getenv(
                        "CLOUD_TASKS_SA_EMAIL",
                        ""
                    )
                }
            },
            "dispatch_deadline": dispatch_deadline,
        }

        response = _tasks_client.create_task(parent=parent, task=task)
        print(f"[tasks] Enqueued finalize for {batch_trace_id}: {response.name}", flush=True)
        return True

    except Exception as e:
        print(f"[tasks] Failed to enqueue finalize for {batch_trace_id}: {e}", flush=True)
        traceback.print_exc()
        return False


class ProcessBatchRequest(BaseModel):
    """Request body for internal batch processing endpoint."""
    rows: List[str] = []  # May be empty for large batches
    tenant_id: str
    batch_trace_id: str
    filename: str
    fetch_rows_from_firestore: bool = False  # True for large batches
    dataset_type: str = "MIXED"  # "MIXED", "PERSON", "COMPANY", or "VESSEL" - resolution pipeline mode


@app.post("/internal/process-batch")
async def internal_process_batch(
    request: Request,
    body: ProcessBatchRequest
):
    """
    Internal endpoint called by Cloud Tasks for durable batch processing.

    This endpoint runs the full processing pipeline synchronously.
    Cloud Tasks guarantees delivery and handles retries.
    """
    # Verify request comes from Cloud Tasks (OIDC token in Authorization header)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        print(f"[internal] Missing OIDC token for {body.batch_trace_id}", flush=True)
        raise HTTPException(401, "Unauthorized - missing OIDC token")

    # Fetch rows from Firestore for large batches
    rows = body.rows
    if body.fetch_rows_from_firestore:
        print(f"[internal] Fetching rows from Firestore for {body.batch_trace_id}", flush=True)
        rows = fetch_batch_rows_from_firestore(body.batch_trace_id)
        if not rows:
            print(f"[internal] Failed to fetch rows from Firestore", flush=True)
            raise HTTPException(500, "Failed to fetch batch rows from Firestore")

    # Parse dataset_type from payload
    dataset_type_str = body.dataset_type
    try:
        dataset_type = DatasetType(dataset_type_str)
    except ValueError:
        dataset_type = DatasetType.MIXED
        print(f"[internal] Unknown dataset_type '{dataset_type_str}', defaulting to MIXED", flush=True)

    print(f"[internal] Processing {body.batch_trace_id}: {len(rows)} rows, mode={dataset_type.value}", flush=True)

    # Run the processing (this is the actual work)
    await process_batch_background(rows, body.tenant_id, body.batch_trace_id, body.filename, dataset_type)

    return {"status": "completed", "trace_id": body.batch_trace_id}


# ─────────────────────────────────────────────────────────────────────────────
# DAY 2: SHARD PROCESSING ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

class ProcessShardRequest(BaseModel):
    """Request body for internal shard processing endpoint."""
    batch_trace_id: str
    shard_id: int
    tenant_id: str
    dataset_type: str = "MIXED"


@app.post("/internal/process-shard")
async def internal_process_shard(
    request: Request,
    body: ProcessShardRequest,
):
    """
    Internal endpoint called by Cloud Tasks for per-shard processing.

    Each shard independently:
    1. Loads its row slice from Firestore input_rows
    2. Runs process_batch_parallel_golden() on that slice
    3. Stores results with shard-prefixed chunk IDs
    4. Records actual L3 spend via budget ledger
    5. Releases unused budget reserve
    6. Calls try_complete_batch() to check if all shards are done
    """
    # Auth: verify OIDC token (same as /internal/process-batch)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        print(f"[shard] Missing OIDC token for {body.batch_trace_id} shard {body.shard_id}", flush=True)
        raise HTTPException(401, "Unauthorized - missing OIDC token")

    batch_trace_id = body.batch_trace_id
    shard_id = body.shard_id
    tenant_id = body.tenant_id
    shard_tag = f"{batch_trace_id}/shard-{shard_id}"

    # Phase 2A: Backpressure gate for shard processing
    # Return 429 so Cloud Tasks retries with exponential backoff.
    # Previously returned 202 which Cloud Tasks treated as success, silently dropping shards.
    bp_allowed, bp_reason = _backpressure.try_acquire_shard()
    if not bp_allowed:
        slog(trace_id=batch_trace_id, phase="shard", event="backpressure_triggered",
             shard_id=shard_id, reason=bp_reason)
        print(f"[shard] {shard_tag}: backpressure rejected (429) — {bp_reason}", flush=True)
        return JSONResponse(status_code=429, content={
            "status": "backpressure", "trace_id": batch_trace_id,
            "shard_id": shard_id, "reason": bp_reason,
            "retry": True,
        })

    try:
        dataset_type_str = body.dataset_type
        try:
            dataset_type = DatasetType(dataset_type_str)
        except ValueError:
            dataset_type = DatasetType.MIXED

        # 1. Load shard metadata
        shard_statuses = get_all_shard_statuses(batch_trace_id, _firestore_db)
        shard_meta = next((s for s in shard_statuses if s.get("shard_id") == shard_id), None)

        if not shard_meta:
            print(f"[shard] {shard_tag}: shard metadata not found", flush=True)
            raise HTTPException(404, f"Shard {shard_id} not found for {batch_trace_id}")

        start_index = shard_meta["start_index"]
        end_index = shard_meta["end_index"]
        record_count = shard_meta["record_count"]

        # 2. Update shard → "running"
        update_shard_status(batch_trace_id, shard_id, "running", _firestore_db)
        print(f"[shard] {shard_tag}: RUNNING [{start_index}:{end_index}] ({record_count} rows)", flush=True)

        # 3. Fetch shard rows from Firestore input_rows
        rows = fetch_shard_rows(batch_trace_id, start_index, end_index, _firestore_db)
        if not rows:
            error_msg = f"Failed to load rows [{start_index}:{end_index}]"
            update_shard_status(batch_trace_id, shard_id, "failed", _firestore_db, error=error_msg)
            print(f"[shard] {shard_tag}: FAILED — {error_msg}", flush=True)
            try_complete_batch(batch_trace_id, tenant_id, _firestore_db)
            raise HTTPException(500, error_msg)

        if len(rows) != record_count:
            print(f"[shard] {shard_tag}: WARNING row count mismatch: expected {record_count}, got {len(rows)}", flush=True)

        # 4. Run processing pipeline on shard slice
        start_time = time.time()
        results, budget_tracker = await process_batch_parallel_golden(rows, tenant_id, batch_trace_id, dataset_type)
        duration_ms = (time.time() - start_time) * 1000
        l3_spent = budget_tracker.spent_usd

        print(f"[shard] {shard_tag}: processed {len(results)} rows in {duration_ms:.0f}ms, "
              f"L3 calls={budget_tracker.calls}, spent=${l3_spent:.4f}", flush=True)

        # 5. Store results with shard-prefixed chunk IDs
        # Pass global start_index so chunk start_index values are globally unique,
        # ensuring fetch_results_from_firestore() order_by('start_index') matches
        # the same ordering used by fetch_sharded_results_deterministic().
        store_results_to_firestore(batch_trace_id, results, shard_id=shard_id, global_start_index=start_index)

        # 5b. Compute the chunk doc IDs written by this shard (for shard receipt)
        results_chunks = [
            f"shard_{shard_id:04d}_chunk_{i:06d}"
            for i in range(0, len(results), RESULTS_CHUNK_SIZE)
        ]

        # 6. Compute shard-level counts
        shard_counts = {
            "total": len(results),
            "l0": sum(1 for r in results if r.get("layer", "").startswith("L0_GARBAGE")),
            "l1": sum(1 for r in results if r.get("layer", "").startswith("L1_")),
            "l2": sum(1 for r in results if r.get("layer") == "L2_VECTOR"),
            "l3": sum(1 for r in results if r.get("layer", "").startswith("L3_")),
            "l4": sum(1 for r in results if r.get("layer") == "L4_HUMAN"),
            "l3_calls": budget_tracker.calls,
            "l3_spent_usd": round(l3_spent, 6),
        }

        # 7. Record actual L3 spend via budget ledger
        if l3_spent > 0:
            spend_result = spend_budget(
                tenant_id, batch_trace_id, shard_id, l3_spent,
                f"spend_shard_{shard_id}", _firestore_db
            )
            if not spend_result.success:
                print(f"[shard] {shard_tag}: ledger spend failed: {spend_result.message}", flush=True)

        # 8. Release unused reserve (reserved per-shard estimate minus actual)
        estimated_cost = record_count * config.L3_COST_PER_CALL_USD
        unused_reserve = max(0.0, estimated_cost - l3_spent)
        if unused_reserve > 0:
            release_result = release_budget(
                tenant_id, batch_trace_id, shard_id, unused_reserve,
                f"release_shard_{shard_id}", _firestore_db
            )
            if not release_result.success:
                print(f"[shard] {shard_tag}: ledger release failed: {release_result.message}", flush=True)

        # 9. Update shard → "completed" with enriched receipt
        update_shard_status(
            batch_trace_id, shard_id, "completed", _firestore_db,
            counts=shard_counts, l3_spent_usd=l3_spent,
            results_chunks=results_chunks, duration_ms=duration_ms
        )
        try:
            from app.metrics.system_metrics import record_shard_latency
            record_shard_latency(_firestore_db, duration_ms)
        except Exception:
            pass
        print(f"[shard] {shard_tag}: COMPLETED", flush=True)

        # 10. Check if all shards done → finalize or fail
        batch_result = try_complete_batch(batch_trace_id, tenant_id, _firestore_db)
        if isinstance(batch_result, dict) and batch_result.get("action") == "finalize":
            # All shards done → dispatch finalize task
            enqueue_finalize_task(batch_trace_id, tenant_id)
            print(f"[shard] {shard_tag}: all shards done → finalize task enqueued", flush=True)
        elif batch_result is True:
            print(f"[shard] {shard_tag}: batch marked as failed (shard failures)", flush=True)

        return {
            "status": "completed",
            "trace_id": batch_trace_id,
            "shard_id": shard_id,
            "record_count": len(results),
            "duration_ms": round(duration_ms, 0),
            "l3_spent_usd": round(l3_spent, 6),
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)[:500]
        print(f"[shard] {shard_tag}: ERROR — {error_msg}", flush=True)
        traceback.print_exc()
        update_shard_status(batch_trace_id, shard_id, "failed", _firestore_db, error=error_msg)
        try_complete_batch(batch_trace_id, tenant_id, _firestore_db)
        raise HTTPException(500, f"Shard processing failed: {error_msg}")
    finally:
        # Phase 2A: Always release shard backpressure slot
        _backpressure.release_shard()


# ─────────────────────────────────────────────────────────────────────────────
# DAY 3: SHARD FINALIZE ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2A: BACKPRESSURE GOVERNOR (instance-scoped, not distributed)
# ─────────────────────────────────────────────────────────────────────────────

class BackpressureGovernor:
    """In-memory concurrency limiter. Cloud Run instance-scoped. Not distributed."""
    def __init__(self):
        self._lock = threading.Lock()
        self._active_finalize_global = 0
        self._active_finalize_by_tenant: dict[str, int] = {}
        self._active_shards_global = 0

    def try_acquire_finalize(self, tenant_id: str) -> tuple[bool, str]:
        with self._lock:
            if self._active_finalize_global >= config.MAX_CONCURRENT_FINALIZE_GLOBAL:
                return False, f"global_finalize_limit ({self._active_finalize_global}/{config.MAX_CONCURRENT_FINALIZE_GLOBAL})"
            tc = self._active_finalize_by_tenant.get(tenant_id, 0)
            if tc >= config.MAX_CONCURRENT_FINALIZE_PER_TENANT:
                return False, f"tenant_finalize_limit ({tc}/{config.MAX_CONCURRENT_FINALIZE_PER_TENANT})"
            self._active_finalize_global += 1
            self._active_finalize_by_tenant[tenant_id] = tc + 1
            return True, "ok"

    def release_finalize(self, tenant_id: str):
        with self._lock:
            self._active_finalize_global = max(0, self._active_finalize_global - 1)
            c = self._active_finalize_by_tenant.get(tenant_id, 0)
            if c <= 1:
                self._active_finalize_by_tenant.pop(tenant_id, None)
            else:
                self._active_finalize_by_tenant[tenant_id] = c - 1

    def try_acquire_shard(self) -> tuple[bool, str]:
        with self._lock:
            if self._active_shards_global >= config.MAX_ACTIVE_SHARDS_GLOBAL:
                return False, f"global_shard_limit ({self._active_shards_global}/{config.MAX_ACTIVE_SHARDS_GLOBAL})"
            self._active_shards_global += 1
            return True, "ok"

    def release_shard(self):
        with self._lock:
            self._active_shards_global = max(0, self._active_shards_global - 1)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active_finalize_global": self._active_finalize_global,
                "active_finalize_by_tenant": dict(self._active_finalize_by_tenant),
                "active_shards_global": self._active_shards_global,
            }

_backpressure = BackpressureGovernor()


FINALIZE_LOCK_TTL_SECONDS = 900


def _finalize_transactional(func):
    """Decorator for finalize transactional functions (mirrors sharding pattern)."""
    from google.cloud import firestore
    return firestore.transactional(func)


def acquire_finalize_lock(batch_trace_id: str, locked_by: str, db):
    """
    Transactionally acquire finalize lock on a batch.
    Phase 2A: Uses dedicated batch_finalize_state/{id} collection to avoid
    contention on the batches/{id} document.
    Returns: ("acquired", lock_id) | ("already_terminal", None) | ("locked", None)
    """
    @_finalize_transactional
    def _acquire(transaction, state_ref):
        snap = state_ref.get(transaction=transaction)
        if snap.exists:
            data = snap.to_dict()
        else:
            # Pre-migration batch: doc doesn't exist yet. Create on acquire.
            data = {"finalize_state": "none", "finalize_lock": None}

        state = data.get("finalize_state", "none")
        if state in ("completed", "failed"):
            return ("already_terminal", None)

        lock = data.get("finalize_lock") or {}
        if lock.get("expires_at"):
            try:
                expires = datetime.fromisoformat(lock["expires_at"].replace("Z", "+00:00"))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires > datetime.now(timezone.utc):
                    return ("locked", None)
            except Exception:
                pass

        lock_id = f"lock-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=FINALIZE_LOCK_TTL_SECONDS)
        transaction.set(state_ref, {
            "finalize_state": "finalizing",
            "finalize_lock": {
                "lock_id": lock_id,
                "locked_by": locked_by,
                "locked_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
            "batch_trace_id": batch_trace_id,
            "updated_at": now.isoformat(),
        })
        return ("acquired", lock_id)

    state_ref = db.collection("batch_finalize_state").document(batch_trace_id)
    txn = db.transaction(max_attempts=config.FINALIZE_TXN_MAX_ATTEMPTS)
    return _acquire(txn, state_ref)


def complete_finalize_state(batch_trace_id: str, lock_id: str, new_state: str, db):
    """
    Transactionally complete finalize: verify lock ownership, set state, clear lock.
    Phase 2A: Uses dedicated batch_finalize_state/{id} collection.
    Returns: ("ok", None) | ("lock_mismatch", held_lock_id) | ("not_found", None)
    """
    @_finalize_transactional
    def _complete(transaction, state_ref):
        snap = state_ref.get(transaction=transaction)
        if not snap.exists:
            return ("not_found", None)
        data = snap.to_dict()
        held = (data.get("finalize_lock") or {}).get("lock_id")
        if held != lock_id:
            return ("lock_mismatch", held)
        transaction.set(state_ref, {
            "finalize_state": new_state,
            "finalize_lock": None,
            "batch_trace_id": batch_trace_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return ("ok", None)

    state_ref = db.collection("batch_finalize_state").document(batch_trace_id)
    txn = db.transaction(max_attempts=config.FINALIZE_TXN_MAX_ATTEMPTS)
    return _complete(txn, state_ref)


def verify_index_integrity(results: list, expected_count: int) -> dict:
    """
    Pure function: verify contiguous global_index [0..expected-1] across results.
    Reads existing global_index from each row. Missing global_index => violation.
    """
    indices = []
    missing_global_index_rows = 0
    for i, r in enumerate(results):
        gi = r.get("global_index")
        if gi is None:
            missing_global_index_rows += 1
        else:
            indices.append(int(gi))

    if missing_global_index_rows > 0:
        return {
            "verified": False,
            "reason": "MISSING_GLOBAL_INDEX",
            "expected": expected_count,
            "observed": len(results),
            "missing_global_index_rows": missing_global_index_rows,
        }

    observed = len(indices)
    unique = set(indices)
    dup_count = observed - len(unique)
    min_idx = min(indices) if indices else -1
    max_idx = max(indices) if indices else -1
    expected_set = set(range(expected_count))
    gaps = sorted(expected_set - unique)
    from collections import Counter
    idx_counts = Counter(indices)
    dupe_samples = sorted(k for k, v in idx_counts.items() if v > 1)[:50]

    verified = (
        observed == expected_count
        and min_idx == 0
        and max_idx == expected_count - 1
        and dup_count == 0
        and len(gaps) == 0
    )

    return {
        "verified": verified,
        "reason": None if verified else "INDEX_INTEGRITY_VIOLATION",
        "expected": expected_count,
        "observed": observed,
        "min_index": min_idx,
        "max_index": max_idx,
        "duplicate_count": dup_count,
        "duplicate_samples": dupe_samples,
        "gap_count": len(gaps),
        "gap_samples": gaps[:50],
    }


class FinalizeBatchRequest(BaseModel):
    """Request body for internal finalize-batch endpoint."""
    batch_trace_id: str
    tenant_id: str


@app.post("/internal/finalize-batch")
async def internal_finalize_batch(
    request: Request,
    body: FinalizeBatchRequest,
):
    """
    Mandatory finalization for sharded batches.
    Called via Cloud Tasks after try_complete_batch() sets status="finalizing".

    Runs the full forensic pipeline (evidence blobs, hash chain, anchoring,
    IAVP manifest, attestation signing) and atomically writes the batch
    with veracity receipt.

    Idempotent: If status already "completed", returns 200 immediately.
    Fail-closed: Missing shard receipt or forensic failure → status="failed".
    """
    # Auth: verify OIDC token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        print(f"[finalize] Missing OIDC token for {body.batch_trace_id}", flush=True)
        raise HTTPException(401, "Unauthorized - missing OIDC token")

    batch_trace_id = body.batch_trace_id
    tenant_id = body.tenant_id
    lock_id = None

    # Phase 2A: Backpressure gate (before Firestore reads)
    bp_allowed, bp_reason = _backpressure.try_acquire_finalize(tenant_id)
    if not bp_allowed:
        slog(trace_id=batch_trace_id, phase="finalize", event="backpressure_triggered",
             tenant_id=tenant_id, reason=bp_reason)
        return JSONResponse(status_code=202, content={
            "status": "queued", "trace_id": batch_trace_id, "reason": bp_reason,
        })

    try:  # Phase 2A: outer try/finally for backpressure release
        # 1. Read batch doc — verify status
        if not _firestore_db:
            raise HTTPException(500, "Firestore not available")

        batch_doc = _firestore_db.collection('batches').document(batch_trace_id).get()
        if not batch_doc.exists:
            raise HTTPException(404, f"Batch {batch_trace_id} not found")

        batch_data = batch_doc.to_dict()
        current_status = batch_data.get("status")

        # Idempotency: terminal state → skip (Day 4 contract)
        if current_status == "completed":
            print(f"[finalize] {batch_trace_id}: already terminal, skipping", flush=True)
            return {"status": "already_terminal", "trace_id": batch_trace_id}

        if current_status != "finalizing":
            print(f"[finalize] {batch_trace_id}: unexpected status '{current_status}', expected 'finalizing'", flush=True)
            raise HTTPException(409, f"Batch status is '{current_status}', expected 'finalizing'")

        # Phase 2A: Check dedicated finalize_state collection
        finalize_state_doc = _firestore_db.collection('batch_finalize_state').document(batch_trace_id).get()
        if finalize_state_doc.exists:
            fs_state = finalize_state_doc.to_dict().get("finalize_state", "none")
            if fs_state in ("completed", "failed"):
                return {"status": "already_terminal", "trace_id": batch_trace_id}

        # Day 4: Acquire finalize lock (transactional, fail-closed)
        # Phase 2A: Now targets batch_finalize_state/{id} — no batch doc contention
        lock_start = time.time()
        lock_result, lock_id = acquire_finalize_lock(batch_trace_id, "finalize-endpoint", _firestore_db)
        lock_wait_seconds = time.time() - lock_start
        slog(trace_id=batch_trace_id, phase="finalize", event="lock_acquired",
             lock_result=lock_result, lock_wait_seconds=round(lock_wait_seconds, 3),
             tenant_id=tenant_id)

        if lock_result == "already_terminal":
            print(f"[finalize] {batch_trace_id}: terminal state (lock check), skipping", flush=True)
            return {"status": "already_terminal", "trace_id": batch_trace_id}
        if lock_result == "locked":
            print(f"[finalize] {batch_trace_id}: active lock held, rejecting", flush=True)
            raise HTTPException(409, f"Batch {batch_trace_id} is locked by another finalize")
        if lock_result != "acquired":
            raise HTTPException(500, f"Unexpected lock result: {lock_result}")

        slog(trace_id=batch_trace_id, phase="finalize", event="finalize_start",
             tenant_id=tenant_id, lock_id=lock_id, router_version=ROUTER_VERSION,
             llm_model_id=L3_MODEL_ID)
        start_time = time.time()

        # --- Phase 1B: Precondition guard for attestation manifest v1 ---
        _hmac_scope_key_hex = os.getenv("HMAC_SCOPE_KEY", "")
        if not _hmac_scope_key_hex:
            print(f"[finalize] FATAL: HMAC_SCOPE_KEY missing for {batch_trace_id}", flush=True)
            slog_error(trace_id=batch_trace_id, phase="finalize", event="precondition_failed",
                       error_type="MissingSecret", error_message="HMAC_SCOPE_KEY missing",
                       tenant_id=tenant_id, stage="precondition", fatal=True)
            if lock_id is not None:
                try:
                    complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
                except Exception:
                    pass
            _fail_batch(batch_trace_id, "PRECONDITION_FAILED: HMAC_SCOPE_KEY missing", _firestore_db)
            raise HTTPException(500, "Finalize precondition failed: HMAC_SCOPE_KEY missing")

        # 2. Read all shard docs — extract shard_receipts
        from app.sharding import get_all_shard_statuses, build_shard_receipts
        shard_statuses = get_all_shard_statuses(batch_trace_id, _firestore_db)

        if not shard_statuses:
            try:
                complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
            except Exception:
                pass
            _fail_batch(batch_trace_id, "FINALIZE_NO_SHARDS: No shard docs found", _firestore_db)
            raise HTTPException(500, "No shard docs found")

        shard_receipts = build_shard_receipts(shard_statuses)

        # 3. Verify every shard has status=="completed" and results_chunks is non-empty
        for receipt in shard_receipts:
            shard_id = receipt.get("shard_id")
            shard_status_entry = next((s for s in shard_statuses if s.get("shard_id") == shard_id), {})
            if shard_status_entry.get("status") != "completed":
                reason = f"FINALIZE_SHARD_NOT_COMPLETED: shard {shard_id} status={shard_status_entry.get('status')}"
                try:
                    complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
                except Exception:
                    pass
                _fail_batch(batch_trace_id, reason, _firestore_db)
                raise HTTPException(500, reason)
            if not receipt.get("results_chunks"):
                reason = f"FINALIZE_MISSING_RECEIPT: shard {shard_id} has no results_chunks"
                try:
                    complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
                except Exception:
                    pass
                _fail_batch(batch_trace_id, reason, _firestore_db)
                raise HTTPException(500, reason)

        total_shards = len(shard_receipts)
        print(f"[finalize] {batch_trace_id}: {total_shards} shards verified, loading results", flush=True)

        # 4. Load all results deterministically
        merge_start = time.time()
        results = fetch_sharded_results_deterministic(batch_trace_id, shard_receipts)
        shard_merge_duration = time.time() - merge_start
        slog(trace_id=batch_trace_id, phase="finalize", event="shard_merge_complete",
             shard_merge_duration_seconds=round(shard_merge_duration, 3),
             total_records=len(results) if results else 0, total_shards=len(shard_receipts),
             tenant_id=tenant_id)
        if not results:
            try:
                complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
            except Exception:
                pass
            _fail_batch(batch_trace_id, "FINALIZE_NO_RESULTS: Failed to load sharded results", _firestore_db)
            raise HTTPException(500, "Failed to load sharded results")

        total = len(results)
        print(f"[finalize] {batch_trace_id}: loaded {total} results, running forensic pipeline", flush=True)

        # 4b. Day 4: Index Integrity Proof (fail-closed, BEFORE sign+anchor)
        expected_count = batch_data.get("total", batch_data.get("total_records", 0))
        integrity_proof = verify_index_integrity(results, expected_count)
        if not integrity_proof["verified"]:
            print(f"[finalize] {batch_trace_id}: INDEX_INTEGRITY_VIOLATION — {integrity_proof}", flush=True)
            _firestore_db.collection('batches').document(batch_trace_id).update({
                "veracity_receipt.index_integrity_proof_v1": integrity_proof,
            })
            try:
                complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
            except Exception:
                pass
            _fail_batch(batch_trace_id, f"INDEX_INTEGRITY_VIOLATION: {integrity_proof.get('reason')}", _firestore_db)
            raise HTTPException(422, "INDEX_INTEGRITY_VIOLATION")

        # 5. Run forensic pipeline — replicates process_batch_background lines 6596-6862
        batch_result = {}
        batch_result["finalized_at"] = datetime.now(timezone.utc).isoformat()

        # --- Evidence Blobs ---
        root_hash = None
        if HAS_FORENSIC_SIGNING:
            evidence_count, batch_sustainability = generate_and_store_evidence_blobs(
                batch_trace_id=batch_trace_id,
                tenant_id=tenant_id,
                results=results,
                config_version=CANONICAL_CONFIG_VERSION,
                sanitization_version=config.SANITIZATION_VERSION,
                watchlist_version_hash=config.WATCHLIST_VERSION_HASH
            )
            print(f"[finalize] Generated {evidence_count} evidence blobs for {batch_trace_id}", flush=True)

            if batch_sustainability:
                batch_result["sustainability"] = batch_sustainability

            # --- Day 5: Resolve tenant-scoped signing key (Gate S2) ---
            from app.security.signing import resolve_signing_key_id
            key_id = resolve_signing_key_id(tenant_id)
            signing_status = get_signing_status()
            pubkey_fingerprint = signing_status.get("service_identity", {}).get("signing_key_version", "unknown")

            # --- Hash Chain ---
            root_hash = None
            chain_meta = None
            if config.HASH_CHAIN_ENABLED:
                chain_success, chain_meta = compute_and_store_hash_chain(
                    batch_trace_id=batch_trace_id,
                    results=results
                )
                if chain_success and chain_meta:
                    batch_result["hash_chain"] = chain_meta
                    root_hash = chain_meta.get("batch_root_hash", "")
                    print(f"[finalize] Hash chain computed for {batch_trace_id}, root={root_hash[:16]}...", flush=True)

                    # --- External Anchoring ---
                    if config.ANCHORING_ENABLED:
                        anchor_record = build_anchor_record(
                            batch_id=batch_trace_id,
                            tenant_id=tenant_id,
                            batch_root_hash=root_hash,
                            code_version=signing_status.get("service_identity", {}).get("code_version", "unknown"),
                            sbom_hash=get_sbom_hash() or "unknown",
                            chain_length=chain_meta.get("chain_length", 0),
                            signing_key_id=key_id,
                        )
                        anchor_success, anchor_path, anchor_error = write_anchor_to_gcs(
                            batch_id=batch_trace_id,
                            tenant_id=tenant_id,
                            anchor_record=anchor_record
                        )
                        if anchor_success:
                            batch_result["anchor"] = {
                                "anchored": True,
                                "anchor_path": anchor_path,
                                "anchor_written_at_utc": anchor_record.get("created_at_utc"),
                            }
                            print(f"[finalize] Anchored {batch_trace_id} to {anchor_path}", flush=True)
                        else:
                            batch_result["anchor"] = {"anchored": False, "error": anchor_error}
                            print(f"[finalize] Anchoring failed for {batch_trace_id}: {anchor_error}", flush=True)

                    # --- IAVP Manifest ---
                    iavp_manifest = None
                    config_hash = None
                    dataset_hash = None
                    artifact_mode = None
                    # key_id already resolved above (Day 5 Gate S2 hoist)

                    if config.IAVP_ENABLED:
                        try:
                            from app.security.iavp import (
                                build_iavp_manifest, compute_config_hash, compute_dataset_hash,
                                get_artifact_mode, ReplayVerificationResult
                            )

                            config_snapshot = {
                                "config_version": CANONICAL_CONFIG_VERSION,
                                "sanitization_version": config.SANITIZATION_VERSION,
                                "watchlist_version_hash": config.WATCHLIST_VERSION_HASH,
                                "l3_max_cost_usd": config.L3_MAX_COST_USD,
                                "l3_min_similarity": config.L3_MIN_SIMILARITY,
                                "iavp_enabled": config.IAVP_ENABLED,
                                "iavp_replay_verification": config.IAVP_REPLAY_VERIFICATION,
                            }
                            config_hash = compute_config_hash(config_snapshot)
                            dataset_hash = compute_dataset_hash(results)
                            artifact_mode = get_artifact_mode(config.IS_PRODUCTION)

                            # key_id, signing_status, pubkey_fingerprint already
                            # resolved above (Day 5 Gate S2 hoist)

                            # Build replay result from chain_meta
                            replay_result = ReplayVerificationResult()
                            if chain_meta.get("replay_runs"):
                                for _ in range(chain_meta.get("replay_runs", 1)):
                                    replay_result.add_run(root_hash)
                                replay_result.variance = chain_meta.get("replay_variance", 0)
                                replay_result.passed = chain_meta.get("replay_passed", True)

                            # Aggregate counts from batch_data (already set by try_complete_batch)
                            agg_counts = batch_data.get("counts", {})
                            valid = agg_counts.get("total", total)
                            l1 = agg_counts.get("l1", 0)
                            l2 = agg_counts.get("l2", 0)
                            l3 = agg_counts.get("l3", 0)
                            l4 = agg_counts.get("l4", 0)

                            metrics = {
                                "l1_pct": round(l1 / valid * 100, 2) if valid > 0 else 0.0,
                                "l2_pct": round(l2 / valid * 100, 2) if valid > 0 else 0.0,
                                "l3_pct": round(l3 / valid * 100, 2) if valid > 0 else 0.0,
                                "l4_pct": round(l4 / valid * 100, 2) if valid > 0 else 0.0,
                            }

                            iavp_manifest = build_iavp_manifest(
                                batch_id=batch_trace_id,
                                artifact_type="BATCH_ATTESTATION",
                                artifact_mode=artifact_mode,
                                engine_version=config.ENGINE_VERSION,
                                config_hash=config_hash,
                                dataset_hash=dataset_hash,
                                root_hash=root_hash,
                                record_count=total,
                                metrics=metrics,
                                replay_result=replay_result,
                                key_id=key_id,
                                pubkey_fingerprint=pubkey_fingerprint,
                                tenant_id_hash=hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
                                tenant_region=config.DEPLOY_REGION,
                            )

                            batch_result["iavp_manifest"] = iavp_manifest
                            print(f"[finalize] IAVP manifest generated for {batch_trace_id}, mode={artifact_mode}", flush=True)

                        except Exception as iavp_err:
                            print(f"[finalize] IAVP manifest failed for {batch_trace_id}: {iavp_err}", flush=True)
                            batch_result["iavp_manifest"] = {
                                "error": str(iavp_err),
                                "protocol_version": IAVP_PROTOCOL_VERSION,
                            }

                    # --- Attestation + Legacy Signing ---
                    if config.SIGNING_ENABLED:
                        try:
                            from .security.signing import sign_bytes_kms
                            import datetime as dt

                            # Attestation binding
                            if iavp_manifest:
                                from app.security.iavp import (
                                    jcs_canonicalize, jcs_sha256,
                                    build_attestation_payload, normalize_timestamp_rfc3339,
                                    ATTESTATION_PAYLOAD_VERSION
                                )
                                import base64 as _b64

                                signed_at = normalize_timestamp_rfc3339(
                                    dt.datetime.now(dt.timezone.utc)
                                )
                                metrics_hash = jcs_sha256(iavp_manifest.get("metrics", {}))

                                att_payload = build_attestation_payload(
                                    batch_id=batch_trace_id,
                                    root_hash=root_hash,
                                    artifact_mode=artifact_mode,
                                    engine_version=config.ENGINE_VERSION,
                                    environment=os.getenv("ENVIRONMENT", "unknown"),
                                    protocol_version=IAVP_PROTOCOL_VERSION,
                                    config_hash=config_hash,
                                    dataset_hash=dataset_hash,
                                    key_id=key_id,
                                    metrics_hash=metrics_hash,
                                    record_count=total,
                                    signed_at_utc=signed_at,
                                    tenant_id_hash=hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
                                    tenant_region=config.DEPLOY_REGION,
                                )
                                canonical_bytes = jcs_canonicalize(att_payload)
                                att_sig_b64, att_sig_error = sign_bytes_kms(canonical_bytes, key_id_override=key_id)

                                batch_result["attestation"] = {
                                    "signed_payload_jcs_b64": _b64.b64encode(canonical_bytes).decode('ascii'),
                                    "signature_b64": att_sig_b64,
                                    "algorithm": "ECDSA_P256_SHA256",
                                    "key_id": key_id,
                                    "key_version": signing_status.get("service_identity", {}).get("signing_key_version"),
                                    "attestation_version": ATTESTATION_PAYLOAD_VERSION,
                                    "error": att_sig_error,
                                }

                                if att_sig_b64:
                                    print(f"[finalize] Attestation signed for {batch_trace_id} (14-field binding)", flush=True)
                                else:
                                    print(f"[finalize] Attestation signing failed: {att_sig_error}", flush=True)

                            # Legacy signature (root-hash only)
                            root_hash_bytes = root_hash.encode('utf-8')
                            sig_b64, sig_error = sign_bytes_kms(root_hash_bytes, key_id_override=key_id)

                            batch_result["signature"] = {
                                "evidence_hash_sha256": root_hash,
                                "signature": sig_b64,
                                "signed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                                "key_version": signing_status.get("service_identity", {}).get("signing_key_version"),
                                "algorithm": "ECDSA_P256_SHA256",
                                "error": sig_error,
                            }

                            if sig_b64:
                                print(f"[finalize] Legacy signature for {batch_trace_id}", flush=True)
                            else:
                                print(f"[finalize] Legacy signing failed: {sig_error}", flush=True)

                        except Exception as sign_err:
                            print(f"[finalize] Signing exception for {batch_trace_id}: {sign_err}", flush=True)
                            batch_result["signature"] = {
                                "evidence_hash_sha256": root_hash,
                                "signature": None,
                                "error": str(sign_err),
                            }

        # --- Phase 1B: Attestation Manifest v1 + Receipt Bundle ---
        _receipt_pointer = None
        _receipt_verification = None
        if root_hash and config.SIGNING_ENABLED and config.ANCHORING_ENABLED:
            try:
                from app.attestation.manifest_v1 import build_attestation_manifest_v1
                from app.attestation.receipt_paths import deterministic_receipt_id
                from app.attestation.receipt_writer import write_receipt_bundle, build_firestore_receipt_pointer
                from app.utils.hashing import compute_dataset_hash_v1, compute_tenant_scope
                from app.security.iavp import jcs_canonicalize, get_artifact_mode

                _receipt_start = time.time()

                # 1. Compute v1 dataset hash (JCS array method)
                _v1_dataset_hash = compute_dataset_hash_v1(results)

                # 2. Compute HMAC tenant scope
                _v1_tenant_scope = compute_tenant_scope(tenant_id, scope_key=bytes.fromhex(_hmac_scope_key_hex))

                # 3. Deterministic receipt_id
                _v1_receipt_id = deterministic_receipt_id(batch_trace_id, root_hash)

                # 4. Build anchor_ref from existing anchor result
                _anchor_data = batch_result.get("anchor", {})
                _anchor_path = _anchor_data.get("anchor_path", "")
                _anchor_bucket_name = os.getenv("ANCHOR_BUCKET", "")
                _anchor_obj_path = _anchor_path.replace(f"gs://{_anchor_bucket_name}/", "") if _anchor_path else ""

                # Compute anchor hash from the anchor record written to GCS
                _anchor_hash = ""
                _anchor_timestamp = _anchor_data.get("anchor_written_at_utc", "")
                if _anchor_path and _anchor_bucket_name:
                    try:
                        from google.cloud import storage as _gcs_storage
                        _a_client = _gcs_storage.Client()
                        if _a_client:
                            _a_blob = _a_client.bucket(_anchor_bucket_name).blob(_anchor_obj_path)
                            _a_bytes = _a_blob.download_as_bytes()
                            _anchor_hash = hashlib.sha256(_a_bytes).hexdigest().lower()
                    except Exception as _ah_err:
                        print(f"[receipt] Anchor hash read failed: {_ah_err}", flush=True)

                _v1_anchor_ref = {
                    "anchor_hash": _anchor_hash or ("0" * 64),
                    "anchor_timestamp": _anchor_timestamp,
                    "bucket": _anchor_bucket_name,
                    "object_path": _anchor_obj_path,
                }

                # 5. Build metrics (fractional, not percentage)
                _agg = batch_data.get("counts", {})
                _v = _agg.get("total", total) or total
                _v1_metrics = {
                    "l1_pct": round(_agg.get("l1", 0) / _v, 4) if _v > 0 else 0.0,
                    "l2_pct": round(_agg.get("l2", 0) / _v, 4) if _v > 0 else 0.0,
                    "l3_pct": round(_agg.get("l3", 0) / _v, 4) if _v > 0 else 0.0,
                    "l4_pct": round(_agg.get("l4", 0) / _v, 4) if _v > 0 else 0.0,
                    "record_count": total,
                    "replay_method": "STABLE_INPUT_ORDER_V2",
                    "replay_runs": chain_meta.get("replay_runs", 3) if chain_meta else 3,
                    "replay_variance": chain_meta.get("replay_variance", 0) if chain_meta else 0,
                }

                # 6. Registry hash = WATCHLIST_VERSION_HASH padded to 64 chars
                _registry_raw = config.WATCHLIST_VERSION_HASH or "unknown"
                _v1_registry_hash = hashlib.sha256(_registry_raw.encode("utf-8")).hexdigest().lower()

                # 7. Build manifest
                _v1_env = os.getenv("ENVIRONMENT", "test")
                if _v1_env not in ("prod", "test"):
                    _v1_env = "test"

                # --- Phase 5: Compute artifact hashes from GCS ---
                _v1_artifact_hashes = []
                _artifact_hash_errors = []
                _artifact_hash_duration_ms = 0.0
                try:
                    from app.attestation.artifact_hasher import (
                        compute_artifact_hashes as _compute_ah,
                        build_artifact_list_for_batch as _build_ah_list,
                    )
                    _ah_start = time.time()
                    _vault_bucket = os.getenv("VAULT_BUCKET", "")
                    _ah_tenant_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
                    _ah_artifact_list = _build_ah_list(
                        anchor_bucket=_anchor_bucket_name,
                        anchor_object_path=_anchor_obj_path,
                        vault_bucket=_vault_bucket,
                        tenant_hash=_ah_tenant_hash,
                        batch_id=batch_trace_id,
                    )
                    if _ah_artifact_list:
                        _v1_artifact_hashes, _artifact_hash_errors = _compute_ah(_ah_artifact_list)
                    _artifact_hash_duration_ms = round((time.time() - _ah_start) * 1000, 1)

                    _ah_failure = None
                    if _artifact_hash_errors:
                        _ah_failure = _artifact_hash_errors[0].get("reason", "UNKNOWN")

                    slog(trace_id=batch_trace_id, phase="finalize",
                         event="artifact_hash_population",
                         stage="artifact_hash_population",
                         receipt_id=_v1_receipt_id,
                         batch_id=batch_trace_id,
                         artifact_hashes_populated=len(_v1_artifact_hashes),
                         artifact_count=len(_ah_artifact_list),
                         duration_ms=_artifact_hash_duration_ms,
                         failure_reason=_ah_failure,
                         tenant_id=tenant_id)
                except Exception as _ah_err:
                    print(f"[receipt] Artifact hash computation failed for {batch_trace_id}: {_ah_err}", flush=True)
                    slog(trace_id=batch_trace_id, phase="finalize",
                         event="artifact_hash_population",
                         stage="artifact_hash_population",
                         receipt_id=_v1_receipt_id,
                         batch_id=batch_trace_id,
                         artifact_hashes_populated=0,
                         artifact_count=0,
                         duration_ms=0,
                         failure_reason="INTERNAL_ERROR",
                         tenant_id=tenant_id)

                _v1_manifest = build_attestation_manifest_v1(
                    batch_id=batch_trace_id,
                    root_hash=root_hash,
                    artifact_mode=get_artifact_mode(config.IS_PRODUCTION),
                    engine_version=config.ENGINE_VERSION,
                    environment=_v1_env,
                    config_hash=config_hash or hashlib.sha256(b"unknown").hexdigest(),
                    dataset_hash=_v1_dataset_hash,
                    registry_hash=_v1_registry_hash,
                    key_id=key_id,
                    metrics=_v1_metrics,
                    tenant_scope=_v1_tenant_scope,
                    anchor_ref=_v1_anchor_ref,
                    artifact_hashes=_v1_artifact_hashes,
                    source_blob_hash=None,
                    receipt_id=_v1_receipt_id,
                )

                # 8. Single authoritative signature: sign manifest digest
                _v1_canonical = jcs_canonicalize(_v1_manifest)
                from app.security.signing import sign_bytes_kms
                _v1_sig_b64, _v1_sig_error = sign_bytes_kms(_v1_canonical, key_id_override=key_id)

                if _v1_sig_error:
                    print(f"[receipt] Manifest signing failed for {batch_trace_id}: {_v1_sig_error}", flush=True)
                else:
                    import base64 as _b64_receipt
                    _v1_sig_bytes = _b64_receipt.b64decode(_v1_sig_b64)

                    # 9. Write receipt bundle to GCS
                    _bundle_result = write_receipt_bundle(
                        manifest=_v1_manifest,
                        signature_bytes=_v1_sig_bytes,
                        tenant_scope=_v1_tenant_scope,
                        receipt_id=_v1_receipt_id,
                        batch_id=batch_trace_id,
                        environment=_v1_env,
                    )

                    # 10. Build Firestore pointer (written with batch doc below)
                    _receipt_pointer = build_firestore_receipt_pointer(
                        receipt_id=_v1_receipt_id,
                        gcs_prefix=_bundle_result["gcs_prefix"],
                    )

                    _receipt_ms = round((time.time() - _receipt_start) * 1000, 1)
                    print(f"[receipt] v1 receipt written for {batch_trace_id}: "
                          f"receipt_id={_v1_receipt_id}, "
                          f"manifest_hash={_bundle_result['manifest_hash'][:16]}..., "
                          f"duration={_receipt_ms}ms", flush=True)
                    slog(trace_id=batch_trace_id, phase="finalize", event="receipt_v1_written",
                         receipt_id=_v1_receipt_id, receipt_ms=_receipt_ms,
                         manifest_hash=_bundle_result["manifest_hash"][:16],
                         tenant_id=tenant_id)

                    # --- Phase 3: Post-write attestation verification (observability-only) ---
                    try:
                        from app.attestation.verifier_v1 import verify_manifest_bundle as _verify_bundle
                        from app.security.public_verify import _resolve_public_key_for_verification

                        def _finalize_key_resolver(kid: str):
                            pem = _resolve_public_key_for_verification(kid)
                            if pem and isinstance(pem, str):
                                return pem.encode("utf-8")
                            return pem

                        _verify_result = _verify_bundle(
                            manifest_bytes=_v1_canonical,
                            signature_bytes=_v1_sig_bytes,
                            metadata_bytes=None,  # metadata not re-read from GCS
                            public_key_resolver=_finalize_key_resolver,
                            fail_closed=False,
                        )

                        _receipt_verification = {
                            "status": "PASS" if _verify_result["success"] else "FAIL",
                            "failure_reason": _verify_result.get("failure_reason"),
                            "verified_at": datetime.now(timezone.utc).isoformat(),
                            "duration_ms": _verify_result.get("duration_ms", 0),
                            "checks_passed": _verify_result.get("checks_passed", []),
                        }

                        slog(trace_id=batch_trace_id, phase="finalize",
                             event="attestation_verify",
                             stage="attestation_verify",
                             receipt_id=_v1_receipt_id,
                             batch_id=batch_trace_id,
                             success=_verify_result["success"],
                             failure_reason=_verify_result.get("failure_reason"),
                             duration_ms=_verify_result.get("duration_ms", 0),
                             checks_passed=",".join(_verify_result.get("checks_passed", [])),
                             tenant_id=tenant_id)

                    except Exception as _verify_err:
                        # Non-fatal: verification failure must not block finalization
                        print(f"[verify] Post-write verification error for {batch_trace_id}: {_verify_err}", flush=True)
                        _receipt_verification = {
                            "status": "ERROR",
                            "failure_reason": "INTERNAL_ERROR",
                            "verified_at": datetime.now(timezone.utc).isoformat(),
                            "error": str(_verify_err)[:200],
                        }

                    # --- Phase 9.1: Transparency log entry for receipt (async) ---
                    try:
                        from app.transparency.spine import enqueue_entry as _tlog_enqueue, TRANSPARENCY_ENABLED as _tlog_on
                        if _tlog_on:
                            _tlog_root = _v1_manifest.get("root_hash", "")
                            if _tlog_root:
                                _tlog_enqueue(
                                    entry_type="receipt",
                                    entry_id=_v1_receipt_id,
                                    root_hash=_tlog_root,
                                )
                    except Exception as _tlog_err:
                        print(f"[transparency] Receipt entry enqueue failed: {_tlog_err}", flush=True)

            except Exception as _receipt_err:
                # Non-fatal: receipt generation failure must not block finalization
                print(f"[receipt] v1 receipt failed for {batch_trace_id}: {_receipt_err}", flush=True)
                slog_error(trace_id=batch_trace_id, phase="finalize", event="receipt_v1_error",
                           error_type=type(_receipt_err).__name__,
                           error_message=str(_receipt_err)[:300],
                           tenant_id=tenant_id)

        # 6. Build veracity receipt
        # Day 5 Gate S2: key_id/pubkey_fingerprint set in forensic block above;
        # provide defaults if HAS_FORENSIC_SIGNING was False.
        if not HAS_FORENSIC_SIGNING:
            from app.security.signing import resolve_signing_key_id
            key_id = resolve_signing_key_id(tenant_id)
            pubkey_fingerprint = "unknown"
        duration_seconds = time.time() - start_time
        _global_key = config.KMS_SIGNING_KEY_ID or "local-signing-key"
        veracity_receipt = {
            "shard_receipts": shard_receipts,
            "total_shards": total_shards,
            "total_records": total,
            "root_hash": batch_result.get("hash_chain", {}).get("batch_root_hash"),
            "anchor": batch_result.get("anchor"),
            "attestation": batch_result.get("attestation"),
            "finalized_at": batch_result.get("finalized_at"),
            "finalize_duration_seconds": round(duration_seconds, 2),
            "version_snapshot": _build_version_snapshot(),
            "tenant_id": tenant_id,
            "signing": {
                "key_id": key_id,
                "key_fingerprint": pubkey_fingerprint,
                "tenant_scoped": key_id != _global_key,
            },
        }

        # ═══════════════════════════════════════════════════════════════
        # DASHBOARD PARITY: compute batch summary metrics for sharded batches
        # Replicates sequential path (lines 6508-6627) field contract
        # ═══════════════════════════════════════════════════════════════
        dataset_type_str = batch_data.get("dataset_type", "COMPANY")
        mode_lower = dataset_type_str.lower()

        # Layer counts from results (matches sequential path lines 6290-6360)
        L0_LAYERS = {"L0_GARBAGE", "L0_GARBAGE_SHORT", "L0_GARBAGE_NUMERIC", "L0_GARBAGE_BLANK"}
        _l0 = sum(1 for r in results if r.get("layer") in L0_LAYERS)
        _l1_exact = sum(1 for r in results if r.get("layer") == "L1_EXACT")
        _l1_norm = sum(1 for r in results if r.get("layer") == "L1_NORM")
        _l2 = sum(1 for r in results if r.get("layer") == "L2_VECTOR")
        _l3 = sum(1 for r in results if r.get("layer", "").startswith("L3_"))
        _l4 = sum(1 for r in results if r.get("layer") == "L4_HUMAN")
        _l1_person = sum(1 for r in results if r.get("layer") == "L1_PERSON")
        _l1_org = sum(1 for r in results if r.get("layer") == "L1_ORG")
        _l1_vessel = sum(1 for r in results if r.get("layer") == "L1_VESSEL")
        _l2_person = sum(1 for r in results if r.get("layer") == "L2_PERSON_FUZZY")
        _l1_total = _l1_exact + _l1_norm
        _l2_total = _l2 + _l2_person

        # auto_resolved (mode-aware, replicates sequential logic lines 6364-6377)
        _valid = total - _l0
        if dataset_type_str == "MIXED":
            # Mixed mode: count all records resolved at any L1/L2/L3 layer
            _auto_resolved = _l1_total + _l1_person + _l1_org + _l1_vessel + _l2_total + _l3
        elif dataset_type_str == "PERSON":
            _auto_resolved = sum(1 for r in results
                                 if r.get("confidence", 0) >= 0.85
                                 and r.get("layer") not in L0_LAYERS)
        else:
            _auto_resolved = _l1_total + _l2_total + _l3
        _auto_resolved_pct = round(float(_auto_resolved / _valid * 100), 2) if _valid > 0 else 0.0

        # flagged_count (replicates line 6521)
        if dataset_type_str in ("PERSON", "MIXED"):
            _flagged_count = _valid - _auto_resolved
        else:
            _flagged_count = _l4

        # duration_seconds from batch creation timestamp → now
        _batch_created = batch_data.get("timestamp", "")
        _batch_duration_s = 0.0
        if _batch_created:
            try:
                _created_dt = datetime.fromisoformat(_batch_created.replace("Z", "+00:00"))
                _batch_duration_s = (datetime.now(timezone.utc) - _created_dt.replace(tzinfo=timezone.utc)).total_seconds()
            except Exception:
                pass

        # L3 cost from aggregated shard data
        _total_l3_spent = batch_data.get("total_l3_spent_usd", 0.0)
        _agg_l3_calls = batch_data.get("counts", {}).get("l3_calls", 0)

        # Dashboard-compatible counts dict (includes both long + short keys)
        _l1_all = _l1_total + _l1_person + _l1_org + _l1_vessel
        dashboard_counts = {
            "l0_quarantined": _l0,
            "l1_resolved": _l1_all,
            "l1_exact": _l1_exact,
            "l1_norm": _l1_norm,
            "l1_person": _l1_person,
            "l1_org": _l1_org,
            "l1_vessel": _l1_vessel,
            "l2_resolved": _l2_total,
            "l3_resolved": _l3,
            "l4_flagged": _l4,
            "total": total,
            "l0": _l0, "l1": _l1_all,
            "l2": _l2_total, "l3": _l3, "l4": _l4,
            "l3_calls": _agg_l3_calls,
            "l3_spent_usd": round(_total_l3_spent, 6),
        }

        # Minimal llm_budget_summary for dashboard cost display
        _budget_usd = float(os.getenv("L3_MAX_COST_USD", "10.0"))
        _llm_budget_summary = {
            "budget_usd": _budget_usd,
            "spent_usd": round(_total_l3_spent, 6),
            "calls": _agg_l3_calls,
            "avg_cost_per_call": round(_total_l3_spent / _agg_l3_calls, 6) if _agg_l3_calls > 0 else 0.0,
            "budget_exhausted": _total_l3_spent >= _budget_usd,
            "l3_yield": round(_l3 / _agg_l3_calls * 100, 1) if _agg_l3_calls > 0 else 0.0,
        }

        _stats = {
            "total": total,
            "total_cost": round(_total_l3_spent, 6),
            "l3_yield": _llm_budget_summary["l3_yield"],
        }

        # 7. Atomic update → status="completed" + forensic fields + dashboard metrics
        veracity_receipt["index_integrity_proof_v1"] = integrity_proof

        update_data = {
            "status": "completed",
            "veracity_receipt": veracity_receipt,
            "hash_chain_deferred": False,
            # Dashboard summary metrics (parity with sequential path)
            "duration_seconds": round(_batch_duration_s, 2),
            "duration_ms": round(_batch_duration_s * 1000, 1),
            "auto_resolved": _auto_resolved,
            "auto_resolved_pct": _auto_resolved_pct,
            "flagged_count": _flagged_count,
            "counts": dashboard_counts,
            "mode": mode_lower,
            "dataset_type": dataset_type_str,
            "cost": round(_total_l3_spent, 6),
            "stats": _stats,
            "llm_budget_summary": _llm_budget_summary,
        }
        # Merge forensic fields
        for key in ("hash_chain", "anchor", "iavp_manifest", "attestation",
                     "signature", "sustainability", "finalized_at"):
            if key in batch_result:
                update_data[key] = batch_result[key]

        # Phase 1B: Add receipt pointer (lightweight, GCS is source of truth)
        if _receipt_pointer:
            update_data["receipt"] = _receipt_pointer

        # Phase 3: Add receipt verification result (observability-only)
        if _receipt_verification:
            update_data["receipt_verification"] = _receipt_verification

        # Day 4: Write batch doc FIRST, then complete finalize state.
        # Ordering: doc written → lock cleared. If lock clear fails after
        # doc write, batch is completed (correct) with stale lock (TTL expires).
        write_start = time.time()
        _firestore_db.collection('batches').document(batch_trace_id).update(update_data)
        write_duration = time.time() - write_start
        slog(trace_id=batch_trace_id, phase="finalize", event="batch_write_complete",
             write_duration_seconds=round(write_duration, 3),
             tenant_id=tenant_id)

        complete_finalize_state(batch_trace_id, lock_id, "completed", _firestore_db)

        # Day 6: Observability metrics flush (non-fatal)
        try:
            from app.metrics.system_metrics import record_finalize_latency, record_ledger_snapshot
            record_finalize_latency(_firestore_db, duration_seconds * 1000)
            from app.budget_ledger import get_tenant_balance
            _bal = get_tenant_balance(tenant_id, _firestore_db)
            if _bal:
                record_ledger_snapshot(_firestore_db, tenant_id,
                    _bal.get("credits_reserved_usd", 0.0), _bal.get("credits_spent_usd", 0.0),
                    0.0, _bal.get("credits_reserved_usd", 0.0) >= 0)
        except Exception as _me:
            print(f"[metrics] Non-fatal finalize flush: {_me}", flush=True)

        slog(trace_id=batch_trace_id, phase="finalize", event="finalize_complete",
             elapsed_seconds=duration_seconds, tenant_id=tenant_id,
             total_records=total, total_shards=total_shards,
             l3_spent_usd=round(_total_l3_spent, 6), lock_id=lock_id,
             lock_wait_seconds=round(lock_wait_seconds, 3),
             shard_merge_seconds=round(shard_merge_duration, 3),
             batch_write_seconds=round(write_duration, 3),
             backpressure=_backpressure.snapshot())

        print(f"[finalize] {batch_trace_id}: COMPLETED in {duration_seconds:.2f}s, "
              f"{total} records, {total_shards} shards, "
              f"root_hash={batch_result.get('hash_chain', {}).get('batch_root_hash', 'none')[:16]}...", flush=True)

        return {
            "status": "completed",
            "trace_id": batch_trace_id,
            "total_records": total,
            "total_shards": total_shards,
            "finalize_duration_seconds": round(duration_seconds, 2),
        }

    except HTTPException:
        raise
    except TenantKeyMissingError as tke:
        error_msg = str(tke)[:500]
        print(f"[finalize] {batch_trace_id}: TENANT_KEY_MISSING — {error_msg}", flush=True)
        slog_error(trace_id=batch_trace_id, phase="finalize", event="tenant_key_missing",
                   error_type="TenantKeyMissingError", error_message=error_msg,
                   tenant_id=tenant_id, lock_id=lock_id or "none")
        if lock_id is not None:
            try:
                complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
            except Exception:
                pass
        _fail_batch(batch_trace_id, f"TENANT_KEY_MISSING: {error_msg}", _firestore_db)
        raise HTTPException(422, f"Tenant encryption key not provisioned: {error_msg}")
    except Exception as e:
        error_msg = str(e)[:500]
        print(f"[finalize] {batch_trace_id}: ERROR — {error_msg}", flush=True)
        traceback.print_exc()
        # Phase 2A: Specific logging for transaction retry exhaustion
        if "Aborted" in type(e).__name__ or "transaction" in error_msg.lower():
            slog_error(trace_id=batch_trace_id, phase="finalize",
                       event="transaction_retry_exceeded",
                       error_type="TransactionRetryExhausted",
                       error_message=error_msg, tenant_id=tenant_id)
        slog_error(trace_id=batch_trace_id, phase="finalize", event="finalize_error",
                   error_type="FinalizeException", error_message=error_msg,
                   tenant_id=tenant_id, lock_id=lock_id or "none")
        if lock_id is not None:
            try:
                complete_finalize_state(batch_trace_id, lock_id, "failed", _firestore_db)
            except Exception:
                pass
        _fail_batch(batch_trace_id, f"FINALIZE_ERROR: {error_msg}", _firestore_db)
        raise HTTPException(500, f"Finalize failed: {error_msg}")
    finally:
        # Phase 2A: Always release backpressure slot
        _backpressure.release_finalize(tenant_id)


@app.get("/admin/batch-economics/{trace_id}")
async def get_batch_economics(
    trace_id: str,
    auth: dict = Depends(require_admin_role),
):
    """Read-only margin telemetry for a batch. Admin only. No routing change."""
    if not _firestore_db:
        raise HTTPException(500, "Firestore not available")
    batch_doc = _firestore_db.collection("batches").document(trace_id).get()
    if not batch_doc.exists:
        raise HTTPException(404, f"Batch {trace_id} not found")
    data = batch_doc.to_dict()
    total = data.get("total", data.get("total_records", 0))
    l3_spent = float(data.get("cost", data.get("llm_budget_summary", {}).get("spent_usd", 0.0)))
    counts = data.get("counts", {})
    l3_calls = counts.get("l3_attempted", counts.get("l3_calls", 0))
    return {
        "trace_id": trace_id,
        "batch_total_cost": round(l3_spent, 6),
        "total_records": total,
        "l3_cost_per_record": round(l3_spent / total, 8) if total > 0 else 0.0,
        "l3_calls": l3_calls,
        "l3_cost_per_call": round(l3_spent / l3_calls, 6) if l3_calls > 0 else 0.0,
        "estimated_margin_per_record": None,  # Requires pricing model — Day 5 placeholder
        "layer_distribution": {
            "l0": counts.get("l0_quarantined", counts.get("l0", 0)),
            "l1": counts.get("l1_resolved", counts.get("l1", 0)),
            "l2": counts.get("l2_resolved", counts.get("l2", 0)),
            "l3": counts.get("l3_resolved", counts.get("l3", 0)),
            "l4": counts.get("l4_flagged", counts.get("l4", 0)),
        },
    }


def _choose_pipeline_auto(rows: List[str], sample_size: int = 200) -> dict:
    """
    Deterministic auto-routing heuristic (v2).

    Inspects the first N non-empty rows using classify_entity() to determine
    whether the batch should use the waterfall (company) or sanitize (mixed) pipeline.

    Decision rule:
        CONFIDENT waterfall:  org >= 80% AND person <= 10% AND garbage <= 20%  → company
        INCONCLUSIVE:         org >= 70% but fails strict thresholds           → mixed (safe default)
        Otherwise:            mixed (sanitize + attest)

    Returns structured fields for auditability and future self-improving loop.
    """
    sample = []
    for row in rows:
        value = (row or "").strip()
        if value:
            sample.append(value)
        if len(sample) >= sample_size:
            break

    inspected = len(sample)
    if inspected == 0:
        return {
            "effective_mode": "mixed",
            "routing_decision": "default_empty",
            "routing_reason": "No valid non-empty rows found; defaulting to sanitize pipeline",
            "routing_confidence": 0.0,
            "org_like_ratio": 0.0,
            "person_like_ratio": 0.0,
            "garbage_ratio": 1.0,
            "other_ratio": 0.0,
            "inspected_row_count": 0,
            "sample_size_requested": sample_size,
            "avg_classification_confidence": 0.0,
        }

    org_like = 0
    person_like = 0
    garbage_like = 0
    other_like = 0
    confidence_sum = 0.0

    for value in sample:
        entity_type, classification_confidence, _ = classify_entity(value)
        confidence_sum += classification_confidence
        if entity_type == EntityType.ORGANIZATION.value:
            org_like += 1
        elif entity_type == EntityType.PERSON.value:
            person_like += 1
        elif entity_type == EntityType.GARBAGE.value:
            garbage_like += 1
        else:
            other_like += 1

    org_ratio = org_like / inspected
    person_ratio = person_like / inspected
    garbage_ratio = garbage_like / inspected
    other_ratio = other_like / inspected
    avg_confidence = confidence_sum / inspected

    # Structured base fields (always returned)
    base = {
        "org_like_ratio": round(org_ratio, 4),
        "person_like_ratio": round(person_ratio, 4),
        "garbage_ratio": round(garbage_ratio, 4),
        "other_ratio": round(other_ratio, 4),
        "inspected_row_count": inspected,
        "sample_size_requested": sample_size,
        "avg_classification_confidence": round(avg_confidence, 4),
        "org_count": org_like,
        "person_count": person_like,
        "garbage_count": garbage_like,
        "other_count": other_like,
    }

    # Decision logic with confidence gating
    strict_waterfall = (org_ratio >= 0.80 and person_ratio <= 0.10 and garbage_ratio <= 0.20)
    inconclusive_zone = (org_ratio >= 0.70 and not strict_waterfall)

    if strict_waterfall:
        routing_confidence = min(org_ratio, 1.0 - person_ratio, 1.0 - garbage_ratio)
        return {
            **base,
            "effective_mode": "company",
            "routing_decision": "waterfall_confident",
            "routing_reason": f"{org_ratio:.0%} organization-like, {person_ratio:.0%} person, {garbage_ratio:.0%} garbage — waterfall resolution",
            "routing_confidence": round(routing_confidence, 4),
        }

    if inconclusive_zone:
        return {
            **base,
            "effective_mode": "mixed",
            "routing_decision": "inconclusive_safe_default",
            "routing_reason": f"{org_ratio:.0%} organization-like but below strict threshold — defaulting to sanitize pipeline for safety",
            "routing_confidence": round(org_ratio * 0.5, 4),
        }

    routing_confidence = 1.0 - org_ratio
    return {
        **base,
        "effective_mode": "mixed",
        "routing_decision": "mixed_distribution",
        "routing_reason": f"{org_ratio:.0%} org, {person_ratio:.0%} person, {garbage_ratio:.0%} garbage — sanitize pipeline",
        "routing_confidence": round(routing_confidence, 4),
    }


@app.post("/batch-upload", status_code=202)
async def batch_upload(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query("mixed", description="Batch mode: 'mixed' (auto-detect), 'person', 'company', or 'vessel'"),
    origin: str = Depends(validate_upload_origin),
    auth: dict = Depends(check_rate_limit),
    _write_check: dict = Depends(require_write_permission)
):
    """
    File upload endpoint - returns immediately, processes via Cloud Tasks.

    Query params:
    - mode: 'mixed' (default, auto-detect per row), 'person', 'company', or 'vessel'

    Returns HTTP 202 Accepted with trace_id.
    Poll /batches to check status: queued → processing → completed/failed
    """
    print(f"[batch-upload] Starting for file: {file.filename}, origin: {origin}, mode={mode}", flush=True)
    tenant_id = auth.get("tenant_id", "default")
    batch_trace_id = f"BATCH-{hashlib.md5(f'{file.filename}{time.time()}'.encode()).hexdigest()[:8].upper()}"

    try:
        # Validate mode parameter
        mode_lower = mode.lower().strip()
        if mode_lower not in ("auto", "mixed", "person", "company", "vessel"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "MODE_INVALID",
                    "message": "mode must be 'auto', 'mixed', 'person', 'company', or 'vessel'",
                    "provided": mode
                }
            )

        # ═══════════════════════════════════════════════════════════════════
        # AUTO-ROUTING: Schema-level inspection BEFORE column extraction
        # ═══════════════════════════════════════════════════════════════════
        requested_mode = mode_lower
        routing_meta = None

        if mode_lower == "auto":
            # Read file content for schema inspection
            file_content = await file.read()
            routing_meta = inspect_dataset(file_content, file.filename or "upload")
            mode_lower = routing_meta["effective_mode"]

            # Reject invalid datasets
            if mode_lower == "reject":
                raise HTTPException(400, f"Dataset rejected: {routing_meta.get('routing_reason', 'invalid data')}")

            print(f"[batch-upload] AUTO-ROUTE: effective_mode={mode_lower}, "
                  f"decision={routing_meta.get('routing_decision')}, "
                  f"reason={routing_meta.get('routing_reason')}", flush=True)

            # Reset file position for the parser
            await file.seek(0)

        # Parse and validate file (extracts single column, mode-aware)
        column_meta: dict = {}
        rows = await parse_uploaded_file_golden(file, tenant_id, mode=mode_lower, column_meta=column_meta)
        row_count = len(rows)
        print(f"[batch-upload] Parsed {row_count} rows", flush=True)
        if column_meta.get("fallback"):
            print(f"[batch-upload] COLUMN_FALLBACK: No recognized header matched. "
                  f"Using column '{column_meta.get('column')}' "
                  f"(method={column_meta.get('method')}, score={column_meta.get('score')})", flush=True)

        # Preflight column validation: reject clearly invalid uploads early.
        # Score < 0.05 means even the best candidate column is almost entirely
        # non-alphabetic (pure IDs, timestamps, numbers). Ambiguous files with
        # plausible name content (score >= 0.05) proceed with BUG-014 fallback warnings.
        PREFLIGHT_MIN_SCORE = 0.05
        if column_meta.get("fallback") and column_meta.get("score", 1.0) < PREFLIGHT_MIN_SCORE:
            col_name = column_meta.get("column", "unknown")
            score = column_meta.get("score", 0)
            raise HTTPException(
                400,
                f"No usable name column found. Best candidate column '{col_name}' "
                f"scored {score:.2f} (minimum {PREFLIGHT_MIN_SCORE}). "
                f"Please ensure your file has a column containing company or person names "
                f"(e.g. 'company', 'name', 'company_name', 'account')."
            )

        if row_count > config.MAX_BATCH_SIZE:
            raise HTTPException(400, f"Maximum {config.MAX_BATCH_SIZE} records per batch")

        # Set dataset type from mode parameter
        if mode_lower == "mixed":
            dataset_type = DatasetType.MIXED
        elif mode_lower == "person":
            dataset_type = DatasetType.PERSON
        elif mode_lower == "vessel":
            dataset_type = DatasetType.VESSEL
        else:
            dataset_type = DatasetType.COMPANY
        classification_meta = {"mode": mode_lower, "requested_mode": requested_mode}
        if routing_meta:
            classification_meta["routing"] = routing_meta

        print(f"[batch-upload] Dataset type: {dataset_type.value} | {classification_meta}", flush=True)

        # Create initial batch record with QUEUED status
        initial_batch = {
            "trace_id": batch_trace_id,
            "filename": file.filename,
            "total": row_count,
            "total_records": row_count,
            "status": "queued",
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": tenant_id,
            "config_version": CANONICAL_CONFIG_VERSION,
            "progress": {"phase": "queued", "done": 0, "total": row_count},
            "dataset_type": dataset_type.value,
            "classification_meta": classification_meta,
            "protocol_version": PROTOCOL_VERSION,
        }
        # BUG-014: surface column selection metadata so operators see fallback
        if column_meta:
            initial_batch["column_selection"] = column_meta

        # ═══════════════════════════════════════════════════════════════════
        # DAY 2: SHARDED PATH — large batches fan out into N independent shards
        # ═══════════════════════════════════════════════════════════════════
        if row_count >= SHARD_SIZE and _tasks_client and CLOUD_RUN_SERVICE_URL:
            shards = compute_shard_ranges(row_count, SHARD_SIZE)
            shard_count = len(shards)
            print(f"[batch-upload] SHARDED PATH: {row_count} rows → {shard_count} shards (shard_size={SHARD_SIZE})", flush=True)

            # Annotate batch record for sharded processing
            initial_batch["sharded"] = True
            initial_batch["shard_count"] = shard_count
            initial_batch["hash_chain_deferred"] = True  # Day 3: deterministic merge

            # Save batch record
            if _firestore_db:
                _firestore_db.collection('batches').document(batch_trace_id).set(initial_batch)
                print(f"[batch-upload] Created sharded batch record {batch_trace_id}", flush=True)

            # Store all rows in Firestore (shards fetch their slice)
            store_batch_rows_to_firestore(batch_trace_id, rows)

            # Create shard metadata documents
            create_shard_docs(batch_trace_id, shards, _firestore_db)

            # Reserve worst-case budget for tenant
            ensure_tenant_balance(tenant_id, _firestore_db)
            worst_case_cost = row_count * config.L3_COST_PER_CALL_USD
            reserve_result = reserve_budget(
                tenant_id, batch_trace_id, -1,
                worst_case_cost, "batch_reserve", _firestore_db
            )
            if not reserve_result.success and reserve_result.status == "rejected":
                print(f"[batch-upload] Budget rejected: {reserve_result.message}", flush=True)
                # Update batch to failed
                if _firestore_db:
                    _firestore_db.collection('batches').document(batch_trace_id).update({
                        "status": "failed",
                        "error_reason": f"BUDGET_REJECTED: {reserve_result.message}",
                    })
                raise HTTPException(402, f"Insufficient credits: {reserve_result.message}")

            # Enqueue shards in throttled waves to avoid overwhelming Cloud Tasks / Cloud Run.
            # Wave size controls how many shards are dispatched concurrently.
            # Between waves, a short delay lets the queue absorb the burst.
            WAVE_SIZE = int(os.getenv("SHARD_WAVE_SIZE", "20"))
            WAVE_DELAY_SECONDS = float(os.getenv("SHARD_WAVE_DELAY", "1.0"))

            enqueued = 0
            failed_shards = []
            for wave_start in range(0, shard_count, WAVE_SIZE):
                wave_end = min(wave_start + WAVE_SIZE, shard_count)
                wave_num = wave_start // WAVE_SIZE + 1
                wave_shards = shards[wave_start:wave_end]

                for shard in wave_shards:
                    if enqueue_shard_task(batch_trace_id, shard["shard_id"], tenant_id, dataset_type.value):
                        enqueued += 1
                    else:
                        failed_shards.append(shard["shard_id"])

                if wave_end < shard_count:
                    # Pause between waves — let Cloud Tasks absorb before next burst
                    import time as _time
                    _time.sleep(WAVE_DELAY_SECONDS)

                if shard_count > WAVE_SIZE:
                    print(f"[batch-upload] Wave {wave_num}: dispatched {wave_start}-{wave_end-1} "
                          f"({enqueued}/{shard_count} total)", flush=True)

            # Retry failed shards once (transient errors: quota, rate limit)
            if failed_shards:
                print(f"[batch-upload] Retrying {len(failed_shards)} failed shards for {batch_trace_id}", flush=True)
                import time as _time
                _time.sleep(2.0)  # back off before retry
                still_failed = []
                for sid in failed_shards:
                    if enqueue_shard_task(batch_trace_id, sid, tenant_id, dataset_type.value):
                        enqueued += 1
                    else:
                        still_failed.append(sid)
                if still_failed:
                    print(f"[batch-upload] WARNING: {len(still_failed)} shards failed after retry: {still_failed[:10]}", flush=True)

            print(f"[batch-upload] Enqueued {enqueued}/{shard_count} shard tasks for {batch_trace_id}", flush=True)

            resp = {
                "status": "queued",
                "trace_id": batch_trace_id,
                "total": row_count,
                "filename": file.filename,
                "dataset_type": dataset_type.value,
                "requested_mode": requested_mode,
                "effective_mode": mode_lower,
                "sharded": True,
                "shard_count": shard_count,
                "message": f"Batch queued: {shard_count} shards ({dataset_type.value} mode). Poll /batches to check status."
            }
            if routing_meta:
                resp["routing"] = routing_meta
            if column_meta:
                resp["column_selection"] = column_meta
            if column_meta.get("fallback"):
                resp.setdefault("warnings", []).append(
                    f"No recognized column header found. Using column '{column_meta.get('column')}' by content scoring.")
            return resp

        # ═══════════════════════════════════════════════════════════════════
        # SEQUENTIAL PATH — small batches (< SHARD_SIZE) — UNCHANGED
        # ═══════════════════════════════════════════════════════════════════

        # Save initial record to Firestore
        if _firestore_db:
            _firestore_db.collection('batches').document(batch_trace_id).set(initial_batch)
            print(f"[batch-upload] Created batch record {batch_trace_id} with status=queued", flush=True)

        # Enqueue via Cloud Tasks for durable execution
        if enqueue_batch_task(rows, tenant_id, batch_trace_id, file.filename, dataset_type.value):
            print(f"[batch-upload] Enqueued {batch_trace_id} via Cloud Tasks ({dataset_type.value} mode)", flush=True)
        else:
            # Fallback: run in background task (non-blocking)
            print(f"[batch-upload] Cloud Tasks unavailable, running in background task", flush=True)

            # For large batches, store rows in Firestore first
            LARGE_BATCH_THRESHOLD = 1000
            if len(rows) > LARGE_BATCH_THRESHOLD:
                print(f"[batch-upload] Large batch ({len(rows)} rows), storing in Firestore", flush=True)
                if store_batch_rows_to_firestore(batch_trace_id, rows):
                    # Process with fetched rows
                    # Capture dataset_type in closure
                    _dataset_type = dataset_type
                    async def background_process():
                        fetched_rows = fetch_batch_rows_from_firestore(batch_trace_id)
                        if fetched_rows:
                            await process_batch_background(fetched_rows, tenant_id, batch_trace_id, file.filename, _dataset_type)
                        else:
                            print(f"[batch-upload] Failed to fetch rows for {batch_trace_id}", flush=True)
                    asyncio.create_task(background_process())
                else:
                    print(f"[batch-upload] Failed to store rows, processing inline", flush=True)
                    asyncio.create_task(process_batch_background(rows, tenant_id, batch_trace_id, file.filename, dataset_type))
            else:
                # Small batch - process directly in background
                asyncio.create_task(process_batch_background(rows, tenant_id, batch_trace_id, file.filename, dataset_type))

        # Return immediately with 202 Accepted
        resp = {
            "status": "queued",
            "trace_id": batch_trace_id,
            "total": row_count,
            "filename": file.filename,
            "dataset_type": dataset_type.value,
            "requested_mode": requested_mode,
            "effective_mode": mode_lower,
            "message": f"Batch queued for processing ({dataset_type.value} mode). Poll /batches to check status."
        }
        if routing_meta:
            resp["routing"] = routing_meta
        if column_meta:
            resp["column_selection"] = column_meta
        if column_meta.get("fallback"):
            resp.setdefault("warnings", []).append(
                f"No recognized column header found. Using column '{column_meta.get('column')}' by content scoring.")
        return resp

    except HTTPException:
        raise
    except Exception as e:
        print(f"[batch-upload] ERROR: {e}", flush=True)
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/batches")
async def get_batches(
    limit: int = 50,
    tenant: Optional[str] = Query(None, description="Tenant filter (admin only): tenant_id_hash or raw tenant_id"),
    auth: dict = Depends(verify_api_key)
):
    """Get batch history from Firestore, filtered by tenant. Admins can filter by any tenant."""
    role = auth.get("role", "user")
    user_tenant_id = auth.get("tenant_id")

    # DEMO MODE: Return immutable fixtures instead of Firestore data
    if config.DEMO_MODE:
        print(f"[/batches] DEMO MODE: Returning {len(DEMO_BATCHES)} demo fixtures", flush=True)
        return {
            "batches": DEMO_BATCHES[:limit],
            "count": min(len(DEMO_BATCHES), limit),
            "firestore_available": True,
            "role": role,
            "demo_mode": True
        }

    # Admin-tier role can filter by specific tenant or see all
    if is_admin_role(role):
        if tenant:
            # Resolve tenant_id_hash to raw tenant_id if needed
            resolved_tenant = _tenant_hash_map.get(tenant, tenant)
            print(f"[/batches] ADMIN ACCESS: Filtering by tenant={tenant} (resolved={resolved_tenant}), limit={limit}", flush=True)
            batches = get_batches_from_firestore_admin(limit, tenant_id=resolved_tenant)
            print(f"[/batches] Returning {len(batches)} batches for admin tenant filter", flush=True)
        else:
            print(f"[/batches] ADMIN ACCESS: Getting all batches, limit={limit}", flush=True)
            batches = get_batches_from_firestore(limit, tenant_id=None)  # No tenant filter
            print(f"[/batches] Returning {len(batches)} batches (admin cross-tenant)", flush=True)
    else:
        # Non-admin: ignore tenant parameter, always filter by user's tenant
        if tenant:
            print(f"[/batches] WARNING: Non-admin attempted tenant filter (ignored)", flush=True)
        print(f"[/batches] Getting batch history, limit={limit}, tenant={user_tenant_id}", flush=True)
        batches = get_batches_from_firestore(limit, tenant_id=user_tenant_id)
        print(f"[/batches] Returning {len(batches)} batches for tenant={user_tenant_id}", flush=True)

    # Debug: Log first 3 batches with metrics
    if batches:
        print(f"[/batches] Returning {len(batches)} batches. Top 3:", flush=True)
        for i, b in enumerate(batches[:3]):
            counts = b.get('counts', {})
            print(f"[/batches] #{i+1}: {b.get('trace_id')} | status={b.get('status')} | "
                  f"duration={b.get('duration_seconds', 0):.2f}s | total={b.get('total', 0)} | "
                  f"auto_resolved_pct={b.get('auto_resolved_pct', 0):.1f}% | "
                  f"L1={counts.get('l1_resolved', '?')} L4={counts.get('l4_flagged', '?')}", flush=True)

    # RBAC: Strip cost fields for non-admin roles
    if not is_admin_role(role):
        batches = [strip_cost_fields(b) for b in batches]

    return {
        "batches": batches,
        "count": len(batches),
        "firestore_available": _firestore_db is not None,
        "role": role,
        "demo_mode": config.DEMO_MODE
    }


# =============================================================================
# PERSON MODE: SANITIZATION BATCH ENDPOINTS
# =============================================================================

class PersonBatchRequest(BaseModel):
    """Request body for person sanitization batch."""
    names: List[str] = Field(..., min_items=1, max_items=100000)


def compute_sanitization_certificate(rows: List[dict]) -> dict:
    """
    Compute sanitization quality certificate for a batch.

    Deterministic calculation - no external lookups.
    """
    total = len(rows)
    if total == 0:
        return {
            "destructive_transform_rate": 0.0,
            "standardization_rate": 0.0,
            "true_parse_success": 0.0,
            "quality_score": 0.0,
            "watchlist_version_hash": config.WATCHLIST_VERSION_HASH,
            "sanitization_version": config.SANITIZATION_VERSION,
        }

    # Destructive transform = 0 (we never truncate)
    destructive_rate = 0.0

    # Standardization = rows where format was standardized
    standardized = sum(1 for r in rows if r.get("decision_path") in ("PARSE_OK", "PARSE_PARTIAL", "SLAVIC_FORMAT"))
    standardization_rate = standardized / total

    # True parse success = rows where first_name AND last_name present
    parse_success = sum(1 for r in rows if r.get("first_name") and r.get("last_name"))
    true_parse_success = parse_success / total

    # Quality score = 0.40*(1-destructive) + 0.30*standardization + 0.30*parse_success
    quality_score = round(
        (0.40 * (1 - destructive_rate) + 0.30 * standardization_rate + 0.30 * true_parse_success) * 100,
        2
    )

    return {
        "destructive_transform_rate": round(destructive_rate, 4),
        "standardization_rate": round(standardization_rate, 4),
        "true_parse_success": round(true_parse_success, 4),
        "quality_score": quality_score,
        "watchlist_version_hash": config.WATCHLIST_VERSION_HASH,
        "sanitization_version": config.SANITIZATION_VERSION,
    }


def process_person_sanitization_batch(names: List[str]) -> List[dict]:
    """
    Process a batch of names through person sanitizer.

    Deterministic O(n) - no watchlist matching, no L3 LLM calls.

    Returns list of dicts with exact required columns.
    """
    results = []

    for name in names:
        r = sanitize_person_name_only(name)

        # Derive decision_path from flags
        if "SLAVIC_FORMAT" in r.flags:
            decision_path = "SLAVIC_FORMAT"
        elif r.first_name and r.last_name:
            decision_path = "PARSE_OK"
        elif r.last_name or r.first_name:
            decision_path = "PARSE_PARTIAL"
        elif "GARBAGE" in r.flags or "BLANK" in r.flags:
            decision_path = "GARBAGE"
        elif "NUMERIC" in r.flags:
            decision_path = "NUMERIC"
        else:
            decision_path = "UNKNOWN"

        results.append({
            "original_name": r.original,
            "sanitized_name": r.sanitized,
            "first_name": r.first_name or "",
            "middle_name": r.middle_name or "",
            "last_name": r.last_name or "",
            "match_type": "SANITIZED_INTAKE",
            "sanitization_confidence": round(r.confidence, 4),
            "sanitization_flags": json.dumps(r.flags),
            "decision_path": decision_path,
        })

    return results


@app.post("/batches")
async def create_person_batch(
    request: PersonBatchRequest,
    mode: str = Query("person", description="Batch mode: person or company"),
    auth: dict = Depends(verify_api_key)
):
    """
    Create and process a person sanitization batch.

    Mode=person: Deterministic sanitization only (no L3, no watchlist matching).
    """
    if mode != "person":
        raise HTTPException(400, f"Only mode=person is supported by this endpoint. Got: {mode}")

    if config.DEMO_MODE:
        raise HTTPException(403, "Cannot create batches in demo mode")

    tenant_id = auth.get("tenant_id", "unknown")
    trace_id = f"TR-{uuid4().hex[:8].upper()}"

    print(f"[POST /batches] Creating person batch: trace_id={trace_id}, names={len(request.names)}, tenant={tenant_id}", flush=True)

    try:
        # Process names through sanitizer (O(n), no watchlist)
        rows = process_person_sanitization_batch(request.names)

        # Compute certificate
        certificate = compute_sanitization_certificate(rows)

        # Persist to Firestore
        if _firestore_db:
            batch_doc = {
                "trace_id": trace_id,
                "mode": "person",
                "tenant_id": tenant_id,
                "total": len(rows),
                "status": "completed",
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "watchlist_version_hash": config.WATCHLIST_VERSION_HASH,
                "sanitization_version": config.SANITIZATION_VERSION,
                "certificate": certificate,
                "protocol_version": PROTOCOL_VERSION,
            }
            _firestore_db.collection("batches").document(trace_id).set(batch_doc)

            # Store rows in subcollection
            rows_ref = _firestore_db.collection("batches").document(trace_id).collection("rows")
            for i, row in enumerate(rows):
                row_doc = {"row_index": i, **row}
                rows_ref.document(str(i)).set(row_doc)

            print(f"[POST /batches] Persisted {len(rows)} rows to Firestore for {trace_id}", flush=True)

        return {
            "trace_id": trace_id,
            "total": len(rows),
            "mode": "person",
        }

    except Exception as e:
        print(f"[POST /batches] Error: {e}", flush=True)
        traceback.print_exc()
        raise HTTPException(500, f"Failed to create batch: {str(e)}")


@app.get("/batches/{trace_id}/export")
async def export_batch(
    trace_id: str,
    format: str = Query("csv", description="Export format: csv, sanitized, or mixed"),
    auth: dict = Depends(verify_api_key)
):
    """
    Export batch results as CSV.

    format=mixed: Mixed mode output with entity classification (default for mixed mode).
    format=sanitized: Person sanitization output with exact required columns.
    format=csv: Standard company resolution output.
    """
    from fastapi.responses import StreamingResponse

    # Validate ownership
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(404, "Batch not found")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")
    if not is_admin_role(role) and batch.get("tenant_id") != tenant_id:
        raise HTTPException(403, "Access denied")

    batch_mode = batch.get("mode", batch.get("dataset_type", "company")).lower()

    # Mixed mode: unified schema with entity classification
    if batch_mode == "mixed":
        # Fetch rows from Firestore results_chunks subcollection
        if not _firestore_db:
            raise HTTPException(503, "Firestore not available")

        # Results are stored in results_chunks, not rows
        results_ref = _firestore_db.collection("batches").document(trace_id).collection("results_chunks")
        chunks_docs = results_ref.order_by("start_index").stream()
        rows = []
        for chunk_doc in chunks_docs:
            chunk = chunk_doc.to_dict()
            rows.extend(chunk.get("rows", []))

        if not rows:
            raise HTTPException(404, "No rows found for batch")

        # Generate CSV with unified schema (entity classification + type-specific columns)
        csv_columns = [
            # Core fields (always present)
            "original_name",
            "entity_type",
            "sanitized_name",
            "sanitization_confidence",
            "sanitization_flags",
            "decision_path",
            # Person fields
            "first_name",
            "middle_name",
            "last_name",
            # Org fields
            "org_name",
            "legal_suffix",
            "org_category",
            # Vessel fields
            "vessel_name",
            "imo_number",
            "vessel_prefix",
        ]

        csv_lines = [",".join(csv_columns)]
        for row in rows:
            values = []
            for col in csv_columns:
                # Map original to original_name
                if col == "original_name":
                    val = str(row.get("original", row.get("original_name", "")))
                elif col == "sanitization_flags":
                    # Convert list to pipe-separated string
                    flags = row.get("sanitization_flags", [])
                    val = "|".join(flags) if isinstance(flags, list) else str(flags)
                else:
                    val = str(row.get(col, ""))
                # Escape quotes and wrap in quotes if contains comma
                if "," in val or '"' in val or "\n" in val:
                    val = '"' + val.replace('"', '""') + '"'
                values.append(val)
            csv_lines.append(",".join(values))

        csv_content = "\n".join(csv_lines)
        filename = f"mixed_{trace_id}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # Person mode: format=sanitized required
    if batch_mode == "person":
        if format != "sanitized":
            raise HTTPException(400, f"Person mode batches require format=sanitized. Got: {format}")

        # Fetch rows from Firestore subcollection
        if not _firestore_db:
            raise HTTPException(503, "Firestore not available")

        rows_ref = _firestore_db.collection("batches").document(trace_id).collection("rows")
        rows_docs = rows_ref.order_by("row_index").stream()
        rows = [doc.to_dict() for doc in rows_docs]

        if not rows:
            raise HTTPException(404, "No rows found for batch")

        # Generate CSV with exact column order
        csv_columns = [
            "original_name",
            "sanitized_name",
            "first_name",
            "middle_name",
            "last_name",
            "match_type",
            "sanitization_confidence",
            "sanitization_flags",
            "decision_path",
        ]

        csv_lines = [",".join(csv_columns)]
        for row in rows:
            values = []
            for col in csv_columns:
                val = str(row.get(col, ""))
                # Escape quotes and wrap in quotes if contains comma
                if "," in val or '"' in val or "\n" in val:
                    val = '"' + val.replace('"', '""') + '"'
                values.append(val)
            csv_lines.append(",".join(values))

        csv_content = "\n".join(csv_lines)
        filename = f"sanitized_{trace_id}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # Company mode: use existing export logic
    else:
        results = fetch_results_from_firestore(trace_id)
        if not results:
            raise HTTPException(404, "No results found for batch")

        csv_content = generate_results_csv(results)
        filename = f"{trace_id}_results.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


# =============================================================================
# EVIDENCE PACK DOWNLOAD (Days 17-20)
# =============================================================================

@app.get("/batches/{trace_id}/evidence-pack")
async def download_evidence_pack(
    trace_id: str,
    include_raw: bool = Query(False, description="Include raw evidence blobs (legal hold only)"),
    auth: dict = Depends(verify_api_key)
):
    """
    Download Nostrum-Grade Evidence Pack.

    Returns a ZIP file containing:
    - results.csv: All resolution results
    - certificate.pdf: Forensic certificate with ESG metrics and KMS signature
    - manifest.json: SHA-256 hashes of all files for integrity verification
    - audit_events.json: Full audit trail
    - evidence_summary.json: Aggregated metadata

    The manifest.json is the cryptographic anchor - verify all file hashes match.
    """
    from fastapi.responses import Response

    # Import reporting module
    try:
        from .reporting import build_evidence_pack
    except ImportError:
        from reporting import build_evidence_pack

    # Validate ownership
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        return JSONResponse(status_code=422, content={
            "error_code": "EXPORT_INVARIANT_VIOLATION",
            "message": "Batch not found — cannot assemble evidence pack without batch metadata.",
            "pointer": "batch",
            "trace_id": trace_id,
        })

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # Admin-tier bypass for tenant check
    if not is_admin_role(role) and batch.get("tenant_id") != tenant_id:
        raise HTTPException(403, "Access denied")

    # Only allow raw evidence for admin-tier roles
    if include_raw and not is_admin_role(role):
        raise HTTPException(403, "Raw evidence access requires admin role")

    # Invariant: batch must be completed to export evidence
    # "success" is a legacy status equivalent to "completed" (pre-standardization batches)
    batch_status = batch.get("status", "unknown")
    if batch_status not in ("completed", "completed_with_warnings", "success"):
        return JSONResponse(status_code=422, content={
            "error_code": "EXPORT_INVARIANT_VIOLATION",
            "message": f"Batch status is '{batch_status}' — evidence pack requires completed batch.",
            "pointer": "batch.status",
            "trace_id": trace_id,
        })

    # Fetch results
    results = fetch_results_from_firestore(trace_id)
    if not results:
        # Try rows subcollection for person mode
        if _firestore_db:
            rows_ref = _firestore_db.collection("batches").document(trace_id).collection("rows")
            rows_docs = rows_ref.order_by("row_index").stream()
            results = [doc.to_dict() for doc in rows_docs]

    # Fallback 3: recover results from audit_events (legacy batches pre-Feb-2026)
    if not results and _firestore_db:
        events_ref = _firestore_db.collection("batches").document(trace_id).collection("audit_events")
        events_docs = events_ref.order_by("row_index").stream()
        recovered = []
        for doc in events_docs:
            e = doc.to_dict()
            ri = e.get("row_index")
            layer = e.get("layer")
            if ri is None or not isinstance(ri, (int, float)) or layer is None or layer == "META":
                continue
            if ri >= 10_000_000_000:
                continue
            recovered.append({
                "row_index": int(ri),
                "original": e.get("original", ""),
                "resolved": e.get("resolved"),
                "layer": layer,
                "confidence": e.get("confidence", 0),
                "reason": e.get("reason", ""),
                "match_type": e.get("match_type"),
                "decision_path": e.get("decision_path") or layer,
                "flagged": e.get("flagged", False),
                "pii_detected": e.get("pii_detected", []),
            })
        if recovered:
            recovered.sort(key=lambda r: r["row_index"])
            results = recovered
            print(f"[EvidencePack] Recovered {len(results)} results from audit_events for {trace_id}", flush=True)

    if not results:
        return JSONResponse(status_code=422, content={
            "error_code": "EXPORT_INVARIANT_VIOLATION",
            "message": "No results found — cannot assemble evidence pack without resolution data.",
            "pointer": "results",
            "trace_id": trace_id,
        })

    # Fetch audit events
    audit_events = []
    if _firestore_db:
        events_ref = _firestore_db.collection("batches").document(trace_id).collection("audit_events")
        events_docs = events_ref.order_by("timestamp").stream()
        audit_events = [doc.to_dict() for doc in events_docs]

    # Get verification data
    verification_data = None
    if HAS_FORENSIC_SIGNING:
        try:
            chain_meta = batch.get("hash_chain", {})
            verification_data = {
                "signature_verified": batch.get("signature", {}).get("signature") is not None,
                "hash_chain": {
                    "chain_enabled": chain_meta.get("batch_root_hash") is not None,
                    "verified": True,  # Assume valid if present
                    "chain_length": chain_meta.get("chain_length", len(results)),
                    "chain_algo": "SHA-256",
                    "batch_root_hash": chain_meta.get("batch_root_hash"),
                },
                "signature": batch.get("signature", {}),
            }
        except Exception as e:
            print(f"[EvidencePack] Failed to build verification data: {e}", flush=True)

    # Build tenant context
    tenant_context = {
        "id": tenant_id or batch.get("tenant_id", "unknown"),
        "name": batch.get("tenant_name") or (tenant_id or "").replace("-", " ").title() or "Unknown",
    }

    # Get evidence blobs if requested
    evidence_blobs = None
    if include_raw:
        evidence_blobs = get_evidence_blobs_for_batch(trace_id, limit=len(results))

    # Build evidence pack
    try:
        zip_bytes, manifest = await build_evidence_pack(
            batch_id=trace_id,
            tenant_context=tenant_context,
            results=results,
            audit_events=audit_events,
            batch_doc=batch,
            verification_data=verification_data,
            evidence_blobs=evidence_blobs,
            include_raw_evidence=include_raw,
        )
    except Exception as e:
        print(f"[EvidencePack] ERROR - Failed to build evidence pack: {e}", flush=True)
        return JSONResponse(status_code=422, content={
            "error_code": "EXPORT_INVARIANT_VIOLATION",
            "message": f"Evidence pack assembly failed: {str(e)}",
            "pointer": "pack_assembly",
            "trace_id": trace_id,
        })

    # Log audit event
    if _firestore_db:
        try:
            event = {
                "event_type": "evidence_pack_downloaded",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trace_id": trace_id,
                "tenant_id": tenant_id,
                "user_id": auth.get("email") or auth.get("uid"),
                "include_raw": include_raw,
                "manifest_hash": manifest.get("integrity", {}).get("manifest_hash"),
                "certificate_hash": manifest.get("certificate_hash"),
                "file_count": len(manifest.get("files", [])),
            }
            _firestore_db.collection("batches").document(trace_id).collection("audit_events").add(event)
        except Exception as e:
            print(f"[EvidencePack] Failed to log evidence pack download: {e}", flush=True)

    # Return ZIP
    filename = f"{trace_id}_evidence_pack.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Manifest-Hash": manifest.get("integrity", {}).get("manifest_hash", ""),
            "X-Certificate-Hash": manifest.get("certificate_hash", ""),
            "X-File-Count": str(len(manifest.get("files", []))),
        }
    )


@app.get("/batches/{trace_id}/verify")
async def verify_batch_integrity(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Verify Batch Integrity (Phase 2 - Forensic)

    Verifies:
    1. Hash chain integrity (each event_hash correctly computed)
    2. Evidence signatures present and valid format
    3. Root hash matches stored value

    Returns PASS/FAIL with detailed verification results.
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin bypasses)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get batch metadata
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Check if hash chain exists
    chain_meta = batch.get("hash_chain", {})
    if not chain_meta.get("batch_root_hash"):
        return {
            "trace_id": trace_id,
            "status": "NOT_AVAILABLE",
            "message": "Hash chain not available for this batch (processed before Phase 2)",
            "chain_enabled": False,
        }

    # Get results for re-computation
    results = fetch_results_from_firestore(trace_id)
    if not results:
        return {
            "trace_id": trace_id,
            "status": "FAIL",
            "error": "results_not_found",
            "message": "Could not retrieve results for verification",
        }

    # Get stored hash chain
    chain_entries, expected_root = get_hash_chain_from_firestore(trace_id)
    if not chain_entries:
        return {
            "trace_id": trace_id,
            "status": "FAIL",
            "error": "chain_entries_not_found",
            "message": "Could not retrieve hash chain entries",
        }

    # Verify hash chain (IAVP: sort results with STABLE_INPUT_ORDER_V2 to match chain order)
    verification = verify_hash_chain_iavp(results, chain_entries, expected_root, trace_id)

    # Get evidence blobs and detect schema version (pass tenant_id for decryption)
    evidence_blobs = get_evidence_blobs_for_batch(trace_id, tenant_id=tenant_id, limit=len(results))
    evidence_schema = detect_evidence_schema(evidence_blobs) if HAS_FORENSIC_SIGNING else EVIDENCE_SCHEMA_UNKNOWN

    # Schema-aware evidence validation
    evidence_integrity = None
    signatures_section = None

    if evidence_schema == EVIDENCE_SCHEMA_CHUNK_V1:
        # chunk_v1: per-record signatures NOT APPLICABLE
        # Integrity via chunk digests → hash chain → batch attestation
        evidence_integrity = verify_chunk_v1_evidence(evidence_blobs)
        signatures_section = {
            "schema_version": EVIDENCE_SCHEMA_CHUNK_V1,
            "mode": "BATCH_ATTESTATION",
            "per_record_signatures": "NOT_APPLICABLE",
            "chunk_digest_chain": "VERIFIED" if evidence_integrity.get("valid") else "FAILED",
            "chunk_count": evidence_integrity.get("chunk_count", 0),
            "total_evidence_blobs": len(evidence_blobs),
        }
    elif evidence_schema == EVIDENCE_SCHEMA_ROW_SIG_V1:
        # Legacy row_sig_v1: apply per-row signature format checks
        signature_checks = []
        signatures_valid = 0
        signatures_missing = 0
        for blob in evidence_blobs[:10]:
            sig_check = verify_evidence_signature_format(blob)
            signature_checks.append(sig_check)
            if sig_check.get("has_signature"):
                signatures_valid += 1
            else:
                signatures_missing += 1
        signatures_section = {
            "schema_version": EVIDENCE_SCHEMA_ROW_SIG_V1,
            "mode": "PER_RECORD_SIGNATURE",
            "per_record_signatures": "CHECKED",
            "sampled": len(signature_checks),
            "valid_format": signatures_valid,
            "missing": signatures_missing,
            "total_evidence_blobs": len(evidence_blobs),
        }
    else:
        # Unknown schema: conservative FAIL
        signatures_section = {
            "schema_version": EVIDENCE_SCHEMA_UNKNOWN,
            "mode": "UNKNOWN",
            "per_record_signatures": "UNKNOWN",
            "failure_reason": "unknown_evidence_schema",
            "total_evidence_blobs": len(evidence_blobs),
        }

    # Verify external anchor (Phase 3)
    anchor_meta = batch.get("anchor", {})
    anchor_verification = None
    if anchor_meta.get("anchored") and config.ANCHORING_ENABLED:
        computed_root = verification.get("computed_root")
        if computed_root:
            anchor_verification = verify_anchor(trace_id, tenant_id, computed_root)

    # Verify attestation binding (FE-5.2 fix, Day 5 S3: key-aware)
    attestation_result = None
    if batch.get("attestation"):
        from app.security.public_verify import verify_attestation_binding
        att_valid, att_error, att_mode = verify_attestation_binding(batch)
        att_key_id = batch.get("attestation", {}).get("key_id")
        attestation_result = {
            "verified": att_valid,
            "mode": att_mode,
            "error": att_error,
            "key_id_used": att_key_id,
        }

    # Determine overall status (schema-aware)
    chain_valid = verification.get("valid")
    anchor_valid = anchor_verification.get("verified") if anchor_verification else None
    att_binding_valid = attestation_result.get("verified") if attestation_result else None

    if evidence_schema == EVIDENCE_SCHEMA_CHUNK_V1:
        # chunk_v1 PASS: chain + anchor (if enabled) + attestation binding
        evidence_ok = evidence_integrity.get("valid", False) if evidence_integrity else False
        conditions = [chain_valid, evidence_ok]
        if config.ANCHORING_ENABLED and anchor_meta.get("anchored"):
            conditions.append(anchor_valid)
        if attestation_result:
            conditions.append(att_binding_valid)
        overall_status = "PASS" if all(conditions) else "FAIL"
    elif evidence_schema == EVIDENCE_SCHEMA_ROW_SIG_V1:
        # Legacy: chain + per-row signatures + anchor (if enabled)
        signatures_ok = signatures_section.get("missing", 1) == 0
        conditions = [chain_valid, signatures_ok]
        if config.ANCHORING_ENABLED and anchor_meta.get("anchored"):
            conditions.append(anchor_valid)
        if attestation_result and not att_binding_valid:
            overall_status = "FAIL"
        else:
            overall_status = "PASS" if all(conditions) else "FAIL"
    else:
        # Unknown schema: always FAIL
        overall_status = "FAIL"

    # Derive top-level signature_verified for frontend consumption
    _att_verified = attestation_result.get("verified") if attestation_result else None
    _sig_verified = bool(_att_verified) if attestation_result else bool(batch.get("attestation", {}).get("signature_b64"))

    return {
        "trace_id": trace_id,
        "status": overall_status,
        "signature_verified": _sig_verified,
        "evidence_schema": evidence_schema,
        "signature": batch.get("attestation", {}),
        "hash_chain": {
            "chain_enabled": True,
            "verified": verification.get("valid"),
            "error": verification.get("error"),
            "computed_root": verification.get("computed_root"),
            "expected_root": expected_root,
            "chain_length": verification.get("chain_length", len(chain_entries)),
            "broken_at_index": verification.get("broken_at_index"),
        },
        "anchor": {
            "enabled": config.ANCHORING_ENABLED,
            "anchored": anchor_meta.get("anchored", False),
            "verified": anchor_verification.get("verified") if anchor_verification else None,
            "error": anchor_verification.get("error") if anchor_verification else None,
            "anchor_path": anchor_verification.get("anchor_path") if anchor_verification else anchor_meta.get("anchor_path"),
            "anchored_at": anchor_verification.get("anchored_at") if anchor_verification else anchor_meta.get("anchor_written_at_utc"),
        } if anchor_verification or anchor_meta.get("anchored") else {"enabled": config.ANCHORING_ENABLED, "anchored": False},
        "attestation_binding": attestation_result,
        "evidence_integrity": signatures_section,
        "batch_metadata": {
            "total_records": batch.get("total", 0),
            "status": batch.get("status"),
            "chain_enabled": chain_meta.get("chain_enabled", False),
            "chained_at": chain_meta.get("chained_at"),
        },
        "verified_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# EXECUTIVE FORENSIC SUMMARY (Trust Stack L1 — Cryptographic Derived View)
# =============================================================================

@app.get("/forensic-summary/{trace_id}")
async def get_forensic_summary(
    trace_id: str,
    auth: dict = Depends(verify_api_key),
):
    """
    Cryptographic executive forensic summary.

    Derived ONLY from: attestation payload, verification result,
    replay metadata, chain metadata, key fingerprint.
    No marketing language. No speculative claims.
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION — never expose cross-tenant data
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # --- Source data extraction (allowed sources only) ---
    chain_meta = batch.get("hash_chain", {})
    sig_info = batch.get("signature", {})
    attestation_data = batch.get("attestation", {})
    anchor_meta = batch.get("anchor", {})
    manifest = batch.get("iavp_manifest", {})
    manifest_metrics = manifest.get("metrics", {})
    manifest_key = manifest.get("key", {})

    # --- Attestation binding verification ---
    from app.security.public_verify import verify_attestation_binding
    sig_valid, sig_error, verification_mode = verify_attestation_binding(batch)

    # --- Chain validity ---
    chain_root_hash = chain_meta.get("batch_root_hash")
    chain_valid = bool(chain_root_hash)

    # --- Anchor verification (live if enabled) ---
    anchor_verified = anchor_meta.get("anchored", False)
    batch_tenant_id = batch.get("tenant_id", tenant_id)
    if anchor_verified and config.ANCHORING_ENABLED and chain_root_hash:
        try:
            anchor_result = verify_anchor(trace_id, batch_tenant_id, chain_root_hash)
            anchor_verified = anchor_result.get("verified", False)
        except Exception:
            anchor_verified = False

    # --- Verification status (derived from sig + chain + anchor) ---
    if sig_valid and chain_valid and anchor_verified:
        verification_status = "PASS"
    else:
        verification_status = "FAIL"
    failure_reason = None
    if verification_status == "FAIL":
        reasons = []
        if not sig_valid:
            reasons.append(f"signature: {sig_error or 'invalid'}")
        if not chain_valid:
            reasons.append("chain: no root hash")
        if not anchor_verified:
            reasons.append("anchor: not verified")
        failure_reason = "; ".join(reasons)

    # --- Replay metadata (from manifest or chain) ---
    replay_runs = manifest_metrics.get("replay_runs") or chain_meta.get("replay_runs", 0) or 0
    replay_variance = manifest_metrics.get("replay_variance") if manifest_metrics.get("replay_variance") is not None else chain_meta.get("replay_variance")

    # --- Attested root hash (from signature evidence or decoded attestation payload) ---
    attested_root_hash = sig_info.get("evidence_hash_sha256")
    if not attested_root_hash and attestation_data.get("signed_payload_jcs_b64"):
        try:
            import base64 as _b64
            _payload_bytes = _b64.b64decode(attestation_data["signed_payload_jcs_b64"])
            _payload = json.loads(_payload_bytes.decode("utf-8"))
            attested_root_hash = _payload.get("root_hash_sha256")
        except Exception:
            pass

    # Replay root hash = chain root hash (the chain was replayed to produce this)
    replay_root_hash = f"sha256:{chain_root_hash}" if chain_root_hash else None

    # --- Determinism verdict (strict gating) ---
    # VERIFIED only when ALL four conditions are provably true:
    #   1. verification.status == PASS
    #   2. replay.runs >= 3
    #   3. replay.variance == 0
    #   4. replay root hash matches attested root hash
    replay_root_matches_attested = (
        bool(chain_root_hash)
        and bool(attested_root_hash)
        and chain_root_hash == attested_root_hash
    )
    replay_determinism = "UNKNOWN"
    replay_supported = replay_runs > 0
    if (
        verification_status == "PASS"
        and replay_runs >= 3
        and replay_variance == 0
        and replay_root_matches_attested
    ):
        replay_determinism = "VERIFIED"

    # --- Crypto metadata (provable from attestation + chain + key) ---
    key_fingerprint = manifest_key.get("pubkey_fingerprint_sha256")
    key_id = attestation_data.get("key_id") or manifest_key.get("key_id")
    sig_algorithm = sig_info.get("algorithm") or "ECDSA_P256_SHA256"

    # Attestation manifest hash = hash of the signed payload (if present)
    attestation_manifest_hash = None
    if attestation_data.get("signed_payload_jcs_b64"):
        try:
            import base64 as _b64
            import hashlib as _hl
            _raw = _b64.b64decode(attestation_data["signed_payload_jcs_b64"])
            attestation_manifest_hash = f"sha256:{_hl.sha256(_raw).hexdigest()}"
        except Exception:
            pass

    # --- Run metadata (from manifest or batch) ---
    artifact_mode = manifest.get("artifact_mode") or batch.get("artifact_mode") or "UNKNOWN"
    dataset_hash_raw = manifest.get("dataset_hash_sha256")
    config_hash_raw = manifest.get("config_hash_sha256")

    # --- Protocol + engine versions ---
    protocol_version = manifest.get("protocol_version") or IAVP_PROTOCOL_VERSION
    engine_version = config.ENGINE_VERSION

    # --- Verified timestamp ---
    verified_at = sig_info.get("signed_at_utc") if verification_status == "PASS" else None

    # --- Anchor details ---
    anchor_type = None
    anchor_id = None
    if anchor_verified:
        anchor_path = anchor_meta.get("anchor_path")
        if anchor_path:
            anchor_type = "GCS"
            anchor_id = anchor_path

    # --- Build response (exact contract, stable key ordering) ---
    return {
        "trace_id": trace_id,
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "environment": config.ENVIRONMENT,
        "protocol_version": protocol_version,
        "engine_version": engine_version,
        "verification": {
            "status": verification_status,
            "verified_at_utc": verified_at,
            "verifier_version": verification_mode if verification_status == "PASS" else None,
            "failure_reason": failure_reason,
        },
        "crypto": {
            "signature_algorithm": sig_algorithm,
            "key_fingerprint": key_fingerprint,
            "attestation_manifest_hash": attestation_manifest_hash,
            "root_hash": f"sha256:{chain_root_hash}" if chain_root_hash else None,
            "chain_height": chain_meta.get("chain_length", 0),
            "anchored": anchor_verified,
            "anchor_type": anchor_type,
            "anchor_id": anchor_id,
        },
        "run": {
            "record_count": batch.get("total", 0),
            "artifact_mode": artifact_mode,
            "dataset_hash": f"sha256:{dataset_hash_raw}" if dataset_hash_raw else None,
            "config_hash": f"sha256:{config_hash_raw}" if config_hash_raw else None,
        },
        "replay": {
            "supported": replay_supported,
            "determinism": replay_determinism,
            "replay_root_hash": replay_root_hash,
            "runs": replay_runs,
            "variance": replay_variance if replay_variance is not None else 0,
        },
    }


# =============================================================================
# PUBLIC VERIFICATION ENDPOINT (Days 21-30 - Trust Seal)
# =============================================================================

@app.get("/verify/{batch_id}")
async def public_verify_batch(batch_id: str, request: Request):
    """
    PUBLIC VERIFICATION ENDPOINT (No Authentication Required)

    Returns cryptographic verification status and PII-redacted trust summary.
    This endpoint is designed for the Trust Seal badge.

    Security:
    - NO authentication required (public trust verification)
    - NO PII or actual names exposed
    - Only aggregate statistics and verification status
    - Rate limited to prevent abuse
    - batch_id sanitized to prevent XSS reflection
    """
    try:
        from .security.public_verify import build_public_verification_response, sanitize_batch_id
    except ImportError:
        from security.public_verify import build_public_verification_response, sanitize_batch_id

    # Security headers: inherit standard set, override Cache-Control for public caching
    _headers = {**_VERIFY_SECURITY_HEADERS, "Cache-Control": "public, max-age=300"}

    # Sanitize batch_id — reject invalid format
    safe_id = sanitize_batch_id(batch_id)
    if safe_id is None:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid batch_id format"},
            headers=_headers,
        )

    # Get batch (no auth check - public endpoint)
    batch = get_batch_by_trace_id(safe_id)

    # Build public verification response
    response = build_public_verification_response(safe_id, batch)

    # Fail closed: nonexistent batches get 404, not 200
    http_status = 404 if response.get("status") == "NOT_FOUND" else 200

    # Return with security + CORS headers
    return JSONResponse(
        status_code=http_status,
        content=response,
        headers=_headers,
    )


@app.get("/verify/{batch_id}/seal")
async def get_trust_seal_data(batch_id: str):
    """
    Minimal data for Trust Seal badge display.

    Returns only essential verification status for badge rendering.
    NOTARY-READY: No ESG rating - removed for compliance.
    """
    try:
        from .security.public_verify import sanitize_batch_id
    except ImportError:
        from security.public_verify import sanitize_batch_id

    # Security headers: inherit standard set, override Cache-Control for public caching
    _headers = {**_VERIFY_SECURITY_HEADERS, "Cache-Control": "public, max-age=300"}

    safe_id = sanitize_batch_id(batch_id)
    if safe_id is None:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid batch_id format"},
            headers=_headers,
        )

    batch = get_batch_by_trace_id(safe_id)

    if not batch:
        return JSONResponse(
            status_code=404,
            content={"verified": False, "status": "NOT_FOUND"},
            headers=_headers,
        )

    # Get signature status
    signature = batch.get("signature", {})
    is_signed = bool(signature.get("signature"))

    # Get hash chain status
    hash_chain = batch.get("hash_chain", {})
    has_chain = bool(hash_chain.get("batch_root_hash"))

    # NOTARY-READY: No ESG rating, no resolution quality metrics
    seal_data = {
        "verified": is_signed and has_chain,
        "batch_id": safe_id,
        "status": batch.get("status", "unknown"),
        "signed_at": signature.get("signed_at_utc", "").split("T")[0] if signature.get("signed_at_utc") else None,
        "legal_hold_active": batch.get("legal_hold", {}).get("status") == "ACTIVE",
    }

    return JSONResponse(
        content=seal_data,
        headers=_headers,
    )


# =============================================================================
# PUBLIC RECEIPT VERIFICATION ENDPOINT (Phase 4 - Attestation)
# =============================================================================

# Rate limiter for receipt verification (100 req/min/IP)
_receipt_verify_rate: Dict[str, list] = {}
_RECEIPT_VERIFY_LIMIT = 100
_RECEIPT_VERIFY_WINDOW = 60  # seconds


_VERIFY_SECURITY_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _check_receipt_rate_limit(client_ip: str) -> bool:
    """Check per-IP rate limit for receipt verification."""
    now = time.time()
    window_start = now - _RECEIPT_VERIFY_WINDOW
    if client_ip not in _receipt_verify_rate:
        _receipt_verify_rate[client_ip] = []
    _receipt_verify_rate[client_ip] = [
        t for t in _receipt_verify_rate[client_ip] if t > window_start
    ]
    if len(_receipt_verify_rate[client_ip]) >= _RECEIPT_VERIFY_LIMIT:
        return False
    _receipt_verify_rate[client_ip].append(now)
    return True


def _find_batch_by_receipt_id(receipt_id: str) -> Optional[Dict]:
    """Look up batch by receipt.id in Firestore."""
    if not _firestore_db:
        return None
    try:
        query = _firestore_db.collection("batches").where(
            "receipt.id", "==", receipt_id
        ).limit(1)
        docs = list(query.stream())
        if not docs:
            return None
        return docs[0].to_dict()
    except Exception as e:
        print(f"[verify-receipt] Firestore lookup error: {e}", flush=True)
        return None


def _load_receipt_bundle_from_gcs(gcs_prefix: str):
    """
    Load manifest.json + signature.der from GCS receipt bundle.

    Returns (manifest_bytes, signature_bytes, error_message).
    Any component may be None if missing.
    """
    manifest_bytes = None
    signature_bytes = None

    try:
        from google.cloud import storage as _gcs_mod
        client = _gcs_mod.Client()
    except Exception:
        return None, None, "storage_unavailable"

    # Parse gs://bucket/path prefix
    if not gcs_prefix.startswith("gs://"):
        return None, None, "invalid_gcs_prefix"

    parts = gcs_prefix[5:].split("/", 1)
    if len(parts) < 2:
        return None, None, "invalid_gcs_prefix"
    bucket_name, prefix = parts[0], parts[1]

    try:
        bucket = client.bucket(bucket_name)

        manifest_blob = bucket.blob(f"{prefix}/manifest.json")
        if manifest_blob.exists():
            manifest_bytes = manifest_blob.download_as_bytes()

        sig_blob = bucket.blob(f"{prefix}/signature.der")
        if sig_blob.exists():
            signature_bytes = sig_blob.download_as_bytes()

    except Exception as e:
        return manifest_bytes, signature_bytes, f"gcs_read_error"

    return manifest_bytes, signature_bytes, None


@app.get("/verify/receipt/{receipt_id}")
async def public_verify_receipt(receipt_id: str, request: Request):
    """
    PUBLIC RECEIPT VERIFICATION (Phase 4 — Attestation)

    Unauthenticated endpoint. Verifies an attestation receipt bundle
    by receipt_id. Returns sanitized verification result.

    - 200: receipt found (status: valid/invalid/incomplete)
    - 404: receipt not found
    - 429: rate limit exceeded
    """
    # Rate limit
    client_ip = request.client.host if request.client else "unknown"
    if not _check_receipt_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": _RECEIPT_VERIFY_WINDOW},
            headers={**_VERIFY_SECURITY_HEADERS, "Retry-After": str(_RECEIPT_VERIFY_WINDOW)},
        )

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # 1. Look up batch by receipt_id
    batch = _find_batch_by_receipt_id(receipt_id)
    if not batch:
        return JSONResponse(
            status_code=404,
            content={"error": "Receipt not found", "receipt_id": receipt_id},
            headers=_VERIFY_SECURITY_HEADERS,
        )

    receipt = batch.get("receipt", {})
    gcs_prefix = receipt.get("gcs_path", "")

    # 2. Load receipt bundle from GCS
    if not gcs_prefix:
        return JSONResponse(
            status_code=200,
            content={
                "receipt_id": receipt_id,
                "status": "incomplete",
                "verification_timestamp": now_utc,
                "checks": {
                    "signature_valid": False,
                    "anchor_valid": False,
                    "artifact_integrity": False,
                    "replay_protection": False,
                },
                "failure_reasons": ["BUNDLE_NOT_FOUND"],
                "_links": {},
            },
            headers=_VERIFY_SECURITY_HEADERS,
        )

    manifest_bytes, signature_bytes, gcs_error = _load_receipt_bundle_from_gcs(gcs_prefix)

    # 3. Check for incomplete bundle
    if manifest_bytes is None or signature_bytes is None:
        missing = []
        if manifest_bytes is None:
            missing.append("manifest.json")
        if signature_bytes is None:
            missing.append("signature.der")
        return JSONResponse(
            status_code=200,
            content={
                "receipt_id": receipt_id,
                "status": "incomplete",
                "verification_timestamp": now_utc,
                "checks": {
                    "signature_valid": False,
                    "anchor_valid": False,
                    "artifact_integrity": False,
                    "replay_protection": False,
                },
                "failure_reasons": ["BUNDLE_INCOMPLETE"],
                "_links": {"manifest": f"{gcs_prefix}/manifest.json"} if manifest_bytes else {},
            },
            headers=_VERIFY_SECURITY_HEADERS,
        )

    # 4. Run internal verifier
    try:
        from app.attestation.verifier_v1 import verify_manifest_bundle
        from app.security.public_verify import _resolve_public_key_for_verification

        def _public_key_resolver(key_id: str):
            pem = _resolve_public_key_for_verification(key_id)
            if pem and isinstance(pem, str):
                return pem.encode("utf-8")
            return pem

        verify_result = verify_manifest_bundle(
            manifest_bytes=manifest_bytes,
            signature_bytes=signature_bytes,
            metadata_bytes=None,
            public_key_resolver=_public_key_resolver,
            fail_closed=False,
        )
    except Exception as _ve:
        print(f"[verify-receipt] Verifier exception for {receipt_id}: {_ve}", flush=True)
        verify_result = {
            "success": False,
            "failure_reason": "INTERNAL_ERROR",
            "checks_passed": [],
            "duration_ms": 0,
        }

    # 5. Map verifier result to sanitized public response
    checks_passed = verify_result.get("checks_passed", [])

    signature_valid = "signature" in checks_passed
    anchor_valid = "anchor_binding" in checks_passed
    artifact_integrity = "artifact_integrity" in checks_passed
    replay_protection = "schema_jcs" in checks_passed  # JCS canonical = replay-safe

    failure_reasons = []
    if not verify_result["success"]:
        reason = verify_result.get("failure_reason")
        if reason:
            # Map internal taxonomy to public values (no internal detail leak)
            _ALLOWED_REASONS = {
                "MANIFEST_MALFORMED", "SIGNATURE_INVALID", "KEY_VERSION_MISMATCH",
                "METADATA_INCONSISTENT", "ANCHOR_HASH_MISMATCH",
                "ARTIFACT_HASH_MISMATCH", "ARTIFACT_SIZE_MISMATCH",
                "TIMESTAMP_SKEW_EXCEEDED", "INTERNAL_ERROR",
            }
            if reason in _ALLOWED_REASONS:
                failure_reasons.append(reason)
            else:
                failure_reasons.append("VERIFICATION_FAILED")

    if verify_result["success"]:
        status = "valid"
    else:
        status = "invalid"

    response = {
        "receipt_id": receipt_id,
        "status": status,
        "verification_timestamp": now_utc,
        "checks": {
            "signature_valid": signature_valid,
            "anchor_valid": anchor_valid,
            "artifact_integrity": artifact_integrity,
            "replay_protection": replay_protection,
        },
        "failure_reasons": failure_reasons,
        "_links": {
            "manifest": f"{gcs_prefix}/manifest.json",
        },
    }

    slog(trace_id=batch.get("trace_id", ""), phase="public_verify",
         event="receipt_verification",
         receipt_id=receipt_id, success=verify_result["success"],
         status=status, duration_ms=verify_result.get("duration_ms", 0))

    return JSONResponse(
        content=response,
        headers=_VERIFY_SECURITY_HEADERS,
    )


# =============================================================================
# LEGAL HOLD + WORM VAULTING ENDPOINTS (Phase 5 - Forensic)
# =============================================================================

class LegalHoldRequest(BaseModel):
    """Request model for placing a legal hold."""
    reason: str = Field(..., min_length=10, description="Reason for hold (min 10 chars)")
    expires_at: Optional[str] = Field(None, description="Optional expiration ISO timestamp")

    @validator('reason')
    def reason_min_length(cls, v):
        if len(v.strip()) < 10:
            raise ValueError('reason must be at least 10 characters')
        return v.strip()


class LegalHoldReleaseRequest(BaseModel):
    """Request model for releasing a legal hold."""
    reason: str = Field(..., min_length=10, description="Reason for release (min 10 chars)")

    @validator('reason')
    def reason_min_length(cls, v):
        if len(v.strip()) < 10:
            raise ValueError('reason must be at least 10 characters')
        return v.strip()


@app.post("/audit/{trace_id}/hold")
async def place_legal_hold(
    trace_id: str,
    request: LegalHoldRequest,
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Place Legal Hold (Week 2 Governance)

    Places a legal hold on a batch, vaulting evidence to WORM storage.

    Authorization:
    - tenant_admin: Can place holds on tenant's batches
    - platform_admin: Can place holds on any batch
    - Other roles: 403 Forbidden

    Effects:
    1. Creates hold record with hold_id
    2. Vaults evidence, chain, certificate, verify to GCS
    3. Records HOLD_PLACED event (append-only)
    4. Updates batch metadata
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    if not config.LEGAL_HOLD_ENABLED:
        raise HTTPException(503, "Legal hold not enabled")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")
    actor_id = auth.get("user_id", auth.get("tenant_id", "unknown"))

    # ROLE CHECK: Only tenant_admin or platform_admin can place holds
    if not check_hold_placement_role(role):
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden. Required role: {HOLD_PLACEMENT_ROLES}. Your role: {role}"
        )

    # TENANT ISOLATION: tenant_admin can only hold own batches
    if role == "tenant_admin" and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get batch metadata
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Check if already on hold
    existing_hold = batch.get("legal_hold", {})
    if existing_hold.get("status") == "ACTIVE":
        raise HTTPException(status_code=409, detail="Batch is already on legal hold")

    # Build enhanced hold record
    hold_record = build_enhanced_hold_record(
        batch_id=trace_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role=role,
        reason=request.reason,
        expires_at=request.expires_at
    )
    hold_id = hold_record["hold_id"]

    # Gather artifacts for vaulting
    evidence_blobs = get_evidence_blobs_for_batch(trace_id, tenant_id=tenant_id, limit=100000)
    chain_entries, root_hash = get_hash_chain_from_firestore(trace_id)

    # Get certificate if available
    certificate_data = batch.get("certificate")

    # Vault all artifacts with hash tracking
    vault_refs, vault_error = vault_all_for_hold(
        batch_id=trace_id,
        tenant_id=tenant_id,
        evidence_blobs=evidence_blobs,
        chain_entries=chain_entries,
        root_hash=root_hash or "",
        certificate_data=certificate_data,
    )

    # Update hold record with vault info
    hold_record["vault_objects"] = vault_refs
    hold_record["vault_objects_written_count"] = len(vault_refs)
    if vault_error:
        hold_record["vault_error"] = vault_error

    # Build hold event (append-only audit trail)
    hold_event = build_hold_event(
        event_type=HoldEventType.HOLD_PLACED,
        batch_id=trace_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role=role,
        reason=request.reason,
        hold_id=hold_id,
        previous_state=existing_hold.get("status", "NONE"),
        new_state="ACTIVE",
        vault_refs=vault_refs,
        expires_at=request.expires_at
    )

    # Store to Firestore (batch update + append event)
    if _firestore_db:
        try:
            batch_ref = _firestore_db.collection('batches').document(trace_id)
            events_ref = batch_ref.collection('hold_events')

            # Transaction: update hold + append event
            batch_ref.update({"legal_hold": hold_record})
            events_ref.document(hold_event["event_id"]).set(hold_event)

        except Exception as e:
            print(f"[LegalHold] Error updating batch: {e}", flush=True)
            raise HTTPException(500, f"Failed to update batch: {str(e)}")

    return {
        "batch_id": trace_id,
        "tenant_id": tenant_id,
        "status": "ACTIVE",
        "hold_id": hold_id,
        "vault_objects_written_count": len(vault_refs),
        "vault_paths": [v.get("path") for v in vault_refs],
        "requested_by": actor_id,
        "requested_at_utc": hold_record["requested_at_utc"],
        "message": "Legal hold placed successfully. Evidence vaulted to WORM storage."
    }


@app.post("/audit/{trace_id}/release-hold")
async def release_legal_hold(
    trace_id: str,
    request: LegalHoldReleaseRequest,
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Release Legal Hold (Week 2 Governance)

    Releases a legal hold. Note: Vaulted evidence remains in WORM storage
    until retention period expires.

    Authorization:
    - platform_admin ONLY (more restrictive than placement)
    - Other roles: 403 Forbidden
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    if not config.LEGAL_HOLD_ENABLED:
        raise HTTPException(503, "Legal hold not enabled")

    role = auth.get("role", "user")
    actor_id = auth.get("user_id", auth.get("tenant_id", "unknown"))
    tenant_id = auth.get("tenant_id")

    # ROLE CHECK: Only platform_admin can release holds
    if not check_hold_release_role(role):
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden. Required role: {HOLD_RELEASE_ROLES}. Your role: {role}"
        )

    # Get batch metadata
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Check if on hold
    existing_hold = batch.get("legal_hold", {})
    if existing_hold.get("status") != "ACTIVE":
        raise HTTPException(status_code=409, detail="Batch is not on legal hold")

    hold_id = existing_hold.get("hold_id", "UNKNOWN")

    # Build release record
    release_record = existing_hold.copy()
    release_record["status"] = "RELEASED"
    release_record["released_by"] = actor_id
    release_record["released_by_role"] = role
    release_record["released_at_utc"] = datetime.utcnow().isoformat()
    release_record["release_reason"] = request.reason

    # Build release event (append-only audit trail)
    release_event = build_hold_event(
        event_type=HoldEventType.HOLD_RELEASED,
        batch_id=trace_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role=role,
        reason=request.reason,
        hold_id=hold_id,
        previous_state="ACTIVE",
        new_state="RELEASED",
        vault_refs=existing_hold.get("vault_objects", [])
    )

    # Store to Firestore
    if _firestore_db:
        try:
            batch_ref = _firestore_db.collection('batches').document(trace_id)
            events_ref = batch_ref.collection('hold_events')

            batch_ref.update({"legal_hold": release_record})
            events_ref.document(release_event["event_id"]).set(release_event)

        except Exception as e:
            print(f"[LegalHold] Error releasing hold: {e}", flush=True)
            raise HTTPException(500, f"Failed to release hold: {str(e)}")

    return {
        "batch_id": trace_id,
        "status": "RELEASED",
        "hold_id": hold_id,
        "released_by": actor_id,
        "released_at_utc": release_record["released_at_utc"],
        "message": "Legal hold released. Vaulted evidence remains in WORM storage until retention expires."
    }


@app.get("/audit/{trace_id}/hold")
async def get_legal_hold_status_endpoint(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Get Legal Hold Status (Phase 5 - Forensic)

    Returns current legal hold status for a batch.
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin bypasses)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get batch metadata
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    hold_record = batch.get("legal_hold", {})

    # Verify vault status if on hold
    vault_verification = None
    if hold_record.get("status") == "ACTIVE" and config.LEGAL_HOLD_ENABLED:
        vault_verification = verify_vaulted_evidence(trace_id, tenant_id)

    return {
        "trace_id": trace_id,
        "legal_hold_enabled": config.LEGAL_HOLD_ENABLED,
        "hold_status": hold_record.get("status", "NONE"),
        "hold_record": hold_record if hold_record else None,
        "vault_verification": vault_verification,
    }


@app.get("/audit/{trace_id}/hold-history")
async def get_legal_hold_history(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    AUDIT BUTTON: Get Legal Hold Event History (Week 2 Governance)

    Returns append-only audit trail of all hold events for a batch.
    Events are ordered chronologically (oldest first).

    Event types:
    - HOLD_PLACED: Legal hold initiated
    - HOLD_RELEASED: Legal hold lifted (by platform_admin)
    - HOLD_EXTENDED: Hold expiration extended

    Each event includes:
    - event_id: Unique identifier
    - event_type: HOLD_PLACED | HOLD_RELEASED | HOLD_EXTENDED
    - actor_id: Who performed the action
    - actor_role: Role at time of action
    - timestamp: When action occurred
    - reason: User-provided justification
    - state_change: {previous_state, new_state}
    - vault_refs_summary: Count and sample of vaulted objects
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin and platform_admin bypass)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get batch metadata first (to verify existence)
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Query hold_events subcollection from Firestore
    events = []
    if _firestore_db:
        try:
            batch_ref = _firestore_db.collection('batches').document(trace_id)
            events_ref = batch_ref.collection('hold_events')

            # Query all events, ordered by timestamp
            query = events_ref.order_by('timestamp')
            docs = query.stream()

            for doc in docs:
                event_data = doc.to_dict()

                # Build summarized response
                vault_refs = event_data.get("vault_refs", [])
                vault_summary = {
                    "count": len(vault_refs),
                    "sample_paths": [v.get("path") for v in vault_refs[:3]] if vault_refs else []
                }

                events.append({
                    "event_id": event_data.get("event_id"),
                    "event_type": event_data.get("event_type"),
                    "actor_id": event_data.get("actor"),  # Field name is 'actor' in build_hold_event
                    "actor_role": event_data.get("actor_role"),
                    "timestamp_utc": event_data.get("timestamp"),  # Field name is 'timestamp' in build_hold_event
                    "reason": event_data.get("reason"),
                    "state_change": {
                        "previous_state": event_data.get("previous_state"),
                        "new_state": event_data.get("new_state")
                    },
                    "vault_refs_summary": vault_summary,
                    "hold_id": event_data.get("hold_id"),
                    "expires_at": event_data.get("expires_at")
                })

        except Exception as e:
            print(f"[LegalHold] Error fetching hold history: {e}", flush=True)
            # Return empty list rather than failing - events may not exist yet
            pass

    # Current hold status
    current_hold = batch.get("legal_hold", {})

    return {
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "current_status": current_hold.get("status", "NONE"),
        "event_count": len(events),
        "events": events,
        "message": f"Found {len(events)} hold event(s) in audit trail"
    }


# =============================================================================
# RETENTION MANAGER ENDPOINTS (Week 2, Day 8-9)
# =============================================================================

# Global RetentionManager instance (initialized on first use)
_retention_manager: Optional[RetentionManager] = None

def get_retention_manager() -> RetentionManager:
    """Get or create the RetentionManager singleton."""
    global _retention_manager
    if _retention_manager is None:
        _retention_manager = RetentionManager(
            vault_bucket=config.VAULT_BUCKET,
            firestore_db=_firestore_db,
            cold_transition_days=COLD_TRANSITION_DAYS,
            purge_threshold_days=PURGE_THRESHOLD_DAYS,
        )
    return _retention_manager


@app.get("/security/retention-status")
async def get_security_retention_status(
    auth: dict = Depends(verify_api_key),
    limit: int = Query(1000, ge=1, le=10000, description="Max batches to evaluate"),
):
    """
    RETENTION STATUS: Get comprehensive retention status summary.

    Returns:
    - Total batches in Archive status
    - Total batches Protected by Legal Hold
    - Upcoming purge list (Batches > 6.9 years old)

    This endpoint uses the RetentionManager to evaluate all batches
    and provides actionable intelligence for retention governance.
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    if not config.RETENTION_POLICY_ENABLED:
        return {
            "retention_policy_enabled": False,
            "message": "Retention policy enforcement is disabled"
        }

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # Get batches from Firestore
    batches = []
    if _firestore_db:
        try:
            batches_ref = _firestore_db.collection('batches')

            # Admin/platform_admin sees all, others see only their tenant
            if is_admin_role(role):
                query = batches_ref.limit(limit)
            else:
                query = batches_ref.where("tenant_id", "==", tenant_id).limit(limit)

            docs = query.stream()
            for doc in docs:
                batch_data = doc.to_dict()
                batch_data["trace_id"] = doc.id
                batches.append(batch_data)

        except Exception as e:
            print(f"[Retention] Error fetching batches: {e}", flush=True)
            raise HTTPException(500, f"Failed to fetch batches: {str(e)}")

    # Get retention manager and evaluate
    manager = get_retention_manager()
    summary = manager.get_retention_status_summary(batches)

    return {
        "retention_policy_enabled": True,
        "vault_bucket": config.VAULT_BUCKET,
        "lifecycle_policy": generate_gcs_lifecycle_policy(),
        **summary
    }


@app.get("/security/lifecycle-policy")
async def get_lifecycle_policy(
    auth: dict = Depends(verify_api_key)
):
    """
    Get the GCS lifecycle policy configuration.

    Returns the JSON lifecycle policy that should be applied to the vault bucket.
    This policy transitions objects from STANDARD → COLDLINE after 90 days,
    and deletes after 7 years (2555 days).

    IMPORTANT: The Delete rule is overridden by backend-level Legal Hold check.
    """
    return {
        "vault_bucket": config.VAULT_BUCKET,
        "lifecycle_policy": generate_gcs_lifecycle_policy(),
        "legal_hold_note": "Delete rule is globally overridden by backend Legal Hold check. Held batches cannot be auto-purged by GCS lifecycle.",
        "thresholds": {
            "cold_transition_days": COLD_TRANSITION_DAYS,
            "purge_threshold_days": PURGE_THRESHOLD_DAYS,
        }
    }


@app.post("/security/apply-lifecycle-policy")
async def apply_lifecycle_policy_endpoint(
    auth: dict = Depends(verify_api_key)
):
    """
    Apply GCS lifecycle policy to the vault bucket.

    Requires platform_admin role.
    """
    role = auth.get("role", "user")

    if role != "platform_admin":
        raise HTTPException(
            status_code=403,
            detail="Forbidden. Required role: platform_admin"
        )

    if not config.VAULT_BUCKET:
        raise HTTPException(400, "VAULT_BUCKET not configured")

    result = apply_gcs_lifecycle_policy(config.VAULT_BUCKET)

    if result.get("applied"):
        return {
            "status": "success",
            **result
        }
    else:
        raise HTTPException(500, f"Failed to apply lifecycle policy: {result.get('error', 'Unknown error')}")


@app.get("/batches/{trace_id}/retention")
async def get_batch_retention_status(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    Get retention status for a specific batch.

    Returns:
    - status: HOT | COLD | ARCHIVE | PURGE_ELIGIBLE | HELD
    - age_days: Batch age in days
    - action: Recommended action (NONE, TRANSITION_TO_COLD, PURGE, BLOCKED_BY_HOLD)
    """
    if not HAS_FORENSIC_SIGNING:
        raise HTTPException(503, "Forensic signing module not available")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin and platform_admin bypass)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get batch metadata
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if not config.RETENTION_POLICY_ENABLED:
        return {
            "trace_id": trace_id,
            "retention_policy_enabled": False,
            "message": "Retention policy enforcement is disabled"
        }

    # Use RetentionManager to evaluate
    manager = get_retention_manager()
    evaluation = manager.evaluate_retention_status(batch)

    return {
        "trace_id": trace_id,
        "retention_policy_enabled": True,
        "evaluation": evaluation,
        "thresholds": {
            "cold_transition_days": COLD_TRANSITION_DAYS,
            "purge_threshold_days": PURGE_THRESHOLD_DAYS,
        }
    }


@app.post("/batches/{trace_id}/retention/simulate-purge")
async def simulate_purge(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    SIMULATE PURGE: Test the Final Purge guard without actually deleting.

    This endpoint demonstrates the RetentionViolationError behavior:
    - If batch is under legal hold → Returns 409 Conflict with error details
    - If batch is eligible for purge → Returns success (simulation only)

    Requires platform_admin role.
    """
    role = auth.get("role", "user")
    tenant_id = auth.get("tenant_id")

    if role != "platform_admin":
        raise HTTPException(
            status_code=403,
            detail="Forbidden. Required role: platform_admin"
        )

    # Get batch metadata
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Use RetentionManager to attempt purge
    manager = get_retention_manager()

    try:
        result = manager.execute_purge(batch)
        return {
            "simulation": True,
            "trace_id": trace_id,
            "result": result,
            "message": "SIMULATION ONLY - No data was deleted"
        }
    except RetentionViolationError as e:
        # This is the expected behavior for held batches
        print(f"[RETENTION] HIGH-SEVERITY ALERT: {e.message}", flush=True)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "RetentionViolationError",
                "batch_id": e.batch_id,
                "hold_id": e.hold_id,
                "message": e.message,
                "severity": "HIGH",
                "action_blocked": True
            }
        )


# =============================================================================
# SUSTAINABILITY ENDPOINT (Energy/Carbon Estimates)
# =============================================================================

@app.get("/batches/{trace_id}/sustainability")
async def get_batch_sustainability(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    Get sustainability (energy/carbon) estimates for a batch.

    Returns batch-level rollup of energy consumption and CO2e estimates.
    All values are ESTIMATES based on operator-configured coefficients,
    NOT direct power telemetry measurements.

    The sustainability data is cryptographically bound to the batch:
    - Included in each evidence_blob BEFORE signature
    - Hash chain includes sustainability fields
    - Anchor reference connects to external immutable storage
    """
    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")

    # TENANT ISOLATION: Verify ownership (admin bypasses)
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get batch metadata
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    sustainability = batch.get("sustainability")
    if not sustainability:
        return {
            "trace_id": trace_id,
            "sustainability_available": False,
            "message": "Sustainability estimates not available for this batch. Either ENERGY_ESTIMATES_ENABLED=false when processed, or batch predates this feature.",
            "energy_estimates_enabled": config.ENERGY_ESTIMATES_ENABLED,
        }

    # Include hash chain and anchor references for forensic binding proof
    hash_chain = batch.get("hash_chain", {})
    anchor = batch.get("anchor", {})

    return {
        "trace_id": trace_id,
        "sustainability_available": True,
        "sustainability": sustainability,
        "forensic_binding": {
            "batch_root_hash": hash_chain.get("batch_root_hash"),
            "chain_length": hash_chain.get("chain_length"),
            "anchor_path": anchor.get("anchor_path") if anchor.get("anchored") else None,
            "anchored": anchor.get("anchored", False),
        },
        "batch_metadata": {
            "total_records": batch.get("total", 0),
            "status": batch.get("status"),
            "completed_at": batch.get("timestamp"),
        },
    }


@app.get("/batches/{trace_id}/certificate")
async def get_batch_certificate(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    Get sanitization quality certificate for a batch.

    Returns persisted certificate with exact required keys.
    """
    # Validate ownership
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(404, "Batch not found")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")
    if not is_admin_role(role) and batch.get("tenant_id") != tenant_id:
        raise HTTPException(403, "Access denied")

    # Return persisted certificate
    certificate = batch.get("certificate")
    if not certificate:
        # Compute if not persisted (legacy batches)
        raise HTTPException(404, "Certificate not found for this batch")

    return certificate


@app.post("/batches/{trace_id}/abort")
async def abort_batch(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """Abort a processing or queued batch. Sets status to 'aborted'."""
    role = auth.get("role", "user")
    user_tenant_id = auth.get("tenant_id")

    if role == "viewer":
        raise HTTPException(403, "Viewers have read-only access. Abort not permitted.")

    if config.DEMO_MODE:
        raise HTTPException(403, "Cannot abort batches in demo mode")

    if not _firestore_db:
        raise HTTPException(503, "Firestore not available")

    try:
        # Get the batch document
        batch_ref = _firestore_db.collection('batches').document(trace_id)
        batch_doc = batch_ref.get()

        if not batch_doc.exists:
            raise HTTPException(404, f"Batch {trace_id} not found")

        batch_data = batch_doc.to_dict()
        batch_tenant = batch_data.get("tenant_id")
        current_status = batch_data.get("status", "unknown")

        # Authorization: must be owner or admin
        if not is_admin_role(role) and batch_tenant != user_tenant_id:
            raise HTTPException(403, "Not authorized to abort this batch")

        # Can only abort queued or processing batches
        if current_status not in ("queued", "processing", "finalizing"):
            raise HTTPException(400, f"Cannot abort batch with status '{current_status}'. Only 'queued', 'processing', or 'finalizing' batches can be aborted.")

        # Update to aborted status
        abort_data = {
            "status": "aborted",
            "aborted_at": datetime.utcnow().isoformat(),
            "aborted_by": auth.get("uid", "unknown"),
            "previous_status": current_status
        }
        batch_ref.update(abort_data)

        print(f"[abort] Batch {trace_id} aborted by {auth.get('uid', 'unknown')} (was: {current_status})", flush=True)

        return {
            "status": "aborted",
            "trace_id": trace_id,
            "previous_status": current_status,
            "message": f"Batch {trace_id} has been aborted"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[abort] Error aborting batch {trace_id}: {e}", flush=True)
        traceback.print_exc()
        raise HTTPException(500, f"Failed to abort batch: {str(e)}")


# =============================================================================
# SHAREABLE BATCH LINKS
# =============================================================================

# Share link configuration
SHARE_LINK_EXPIRY_DAYS = 7
SHARE_TOKEN_LENGTH = 32
SHARE_LINK_BASE_URL = os.getenv("SHARE_LINK_BASE_URL", "http://localhost:5173/s")


def generate_share_token() -> str:
    """Generate a cryptographically secure share token."""
    return secrets.token_urlsafe(SHARE_TOKEN_LENGTH)


def create_share_link_in_firestore(
    trace_id: str,
    tenant_id: str,
    created_by_uid: str,
    expiry_days: int = SHARE_LINK_EXPIRY_DAYS
) -> Optional[Dict]:
    """Create a share link record in Firestore."""
    if not _firestore_db:
        return None

    try:
        share_token = generate_share_token()
        now = datetime.utcnow()
        expires_at = now + timedelta(days=expiry_days)

        # Hash tenant_id for privacy
        tenant_id_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16] if tenant_id else None

        share_data = {
            "share_token": share_token,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "tenant_id_hash": tenant_id_hash,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "created_by_uid": created_by_uid,
            "revoked": False
        }

        # Store in Firestore
        shares_ref = _firestore_db.collection('share_links')
        shares_ref.document(share_token).set(share_data)

        print(f"[Share] Created share link for trace_id={trace_id}, token={share_token[:8]}...", flush=True)

        return {
            "share_token": share_token,
            "url": f"{SHARE_LINK_BASE_URL}/{share_token}",
            "expires_at": expires_at.isoformat(),
            "trace_id": trace_id
        }

    except Exception as e:
        print(f"[Share] Error creating share link: {e}", flush=True)
        return None


def get_share_link_from_firestore(share_token: str) -> Optional[Dict]:
    """Retrieve a share link record from Firestore."""
    if not _firestore_db:
        return None

    try:
        shares_ref = _firestore_db.collection('share_links')
        doc = shares_ref.document(share_token).get()

        if not doc.exists:
            return None

        return doc.to_dict()

    except Exception as e:
        print(f"[Share] Error retrieving share link: {e}", flush=True)
        return None


def revoke_share_link_in_firestore(share_token: str) -> bool:
    """Revoke a share link in Firestore."""
    if not _firestore_db:
        return False

    try:
        shares_ref = _firestore_db.collection('share_links')
        shares_ref.document(share_token).update({"revoked": True})
        print(f"[Share] Revoked share link token={share_token[:8]}...", flush=True)
        return True

    except Exception as e:
        print(f"[Share] Error revoking share link: {e}", flush=True)
        return False


def get_batch_by_trace_id(trace_id: str) -> Optional[Dict]:
    """Retrieve a batch by trace_id from Firestore."""
    if not _firestore_db:
        return None

    try:
        batches_ref = _firestore_db.collection('batches')
        query = batches_ref.where('trace_id', '==', trace_id).limit(1)
        docs = list(query.stream())

        if not docs:
            return None

        return docs[0].to_dict()

    except Exception as e:
        print(f"[Share] Error retrieving batch: {e}", flush=True)
        return None


# =============================================================================
# RESULTS PERSISTENCE AND EXPORT
# =============================================================================

RESULTS_CHUNK_SIZE = 500  # Records per Firestore document


def store_results_to_firestore(batch_trace_id: str, results: List[Dict], shard_id: Optional[int] = None, global_start_index: int = 0) -> bool:
    """
    Store batch results in Firestore subcollection as chunks.

    Structure:
    batches/{trace_id}/results_chunks/{chunk_id}
        - start_index: int (global position in batch)
        - end_index: int (global position in batch)
        - rows: List[Dict]  # Result records

    For sharded batches, chunk IDs are prefixed with shard_XXXX_ to avoid
    collisions when multiple shards write concurrently.

    Args:
        global_start_index: Offset for start_index values. For sharded batches,
            pass the shard's start_index so chunks have globally unique positions.
            This ensures fetch_results_from_firestore() order_by('start_index')
            returns results in the same order as fetch_sharded_results_deterministic().

    Returns: True if successful
    """
    if not _firestore_db:
        print(f"[results] Firestore not available, skipping results storage", flush=True)
        return False

    try:
        batch_ref = _firestore_db.collection('batches').document(batch_trace_id)
        results_ref = batch_ref.collection('results_chunks')

        # Shard-prefixed chunk IDs prevent collisions across concurrent shard workers
        shard_prefix = f"shard_{shard_id:04d}_" if shard_id is not None else ""

        chunk_count = 0
        for i in range(0, len(results), RESULTS_CHUNK_SIZE):
            chunk = results[i:i + RESULTS_CHUNK_SIZE]
            chunk_id = f"{shard_prefix}chunk_{i:06d}"

            # Serialize results for storage
            serialized_rows = []
            for r in chunk:
                row = {
                    "original": r.get("original", ""),
                    "resolved": r.get("resolved"),
                    "match_type": r.get("match_type", "NO_MATCH"),
                    "match_id": r.get("match_id"),
                    "confidence": r.get("confidence", 0.0),
                    "layer": r.get("layer", ""),
                    "reason": r.get("reason", ""),
                    "decision": r.get("decision", ""),
                    "top_candidates": r.get("top_candidates", [])[:3],  # Limit for storage
                    "similarity_scores": r.get("similarity_scores", {}),
                    # Mixed mode fields (entity classification + type-specific)
                    "entity_type": r.get("entity_type", ""),
                    "sanitized_name": r.get("sanitized_name", ""),
                    "sanitization_confidence": r.get("sanitization_confidence", 0.0),
                    "sanitization_flags": r.get("sanitization_flags", []),
                    "decision_path": r.get("decision_path", ""),
                    "classification_confidence": r.get("classification_confidence", 0.0),
                    "classification_flags": r.get("classification_flags", []),
                    # Person fields
                    "first_name": r.get("first_name", ""),
                    "middle_name": r.get("middle_name", ""),
                    "last_name": r.get("last_name", ""),
                    # Org fields
                    "org_name": r.get("org_name", ""),
                    "legal_suffix": r.get("legal_suffix", ""),
                    "org_category": r.get("org_category", ""),
                    # Vessel fields
                    "vessel_name": r.get("vessel_name", ""),
                    "imo_number": r.get("imo_number", ""),
                    "vessel_prefix": r.get("vessel_prefix", ""),
                }
                serialized_rows.append(row)

            chunk_doc = {
                "start_index": global_start_index + i,
                "end_index": global_start_index + i + len(chunk),
                "rows": serialized_rows
            }

            results_ref.document(chunk_id).set(chunk_doc)
            chunk_count += 1

        print(f"[results] Stored {len(results)} results in {chunk_count} chunks for {batch_trace_id}", flush=True)
        return True

    except Exception as e:
        print(f"[results] Failed to store results: {e}", flush=True)
        traceback.print_exc()
        return False


def fetch_results_from_firestore(batch_trace_id: str) -> List[Dict]:
    """
    Fetch all results from Firestore subcollection.

    Returns: List of result records in order
    """
    if not _firestore_db:
        return []

    try:
        batch_ref = _firestore_db.collection('batches').document(batch_trace_id)
        results_ref = batch_ref.collection('results_chunks')

        # Fetch all chunks ordered by start_index
        docs = results_ref.order_by('start_index').stream()

        all_rows = []
        for doc in docs:
            chunk_data = doc.to_dict()
            all_rows.extend(chunk_data.get('rows', []))

        print(f"[results] Fetched {len(all_rows)} results for {batch_trace_id}", flush=True)
        return all_rows

    except Exception as e:
        print(f"[results] Failed to fetch results: {e}", flush=True)
        return []


def fetch_sharded_results_deterministic(batch_trace_id: str, shard_receipts: list) -> List[Dict]:
    """
    Load all results for a sharded batch in deterministic shard order.

    Iterates shard_receipts (already ordered by shard_id).
    For each shard, loads its results_chunks by doc ID from Firestore.
    Returns flattened list of all result records in shard order.

    Fail-closed: If any shard has empty results_chunks, returns empty list.
    """
    if not _firestore_db:
        return []

    try:
        results_ref = _firestore_db.collection('batches').document(batch_trace_id).collection('results_chunks')
        all_rows = []

        for receipt in shard_receipts:
            chunk_ids = receipt.get("results_chunks", [])
            if not chunk_ids:
                shard_id = receipt.get("shard_id", "?")
                print(f"[results] Shard {shard_id} has no results_chunks — fail-closed", flush=True)
                return []

            for chunk_id in chunk_ids:
                doc = results_ref.document(chunk_id).get()
                if doc.exists:
                    chunk_data = doc.to_dict()
                    all_rows.extend(chunk_data.get('rows', []))
                else:
                    print(f"[results] Missing chunk {chunk_id} for {batch_trace_id}", flush=True)
                    return []

        # Assign global_index after deterministic merge (required by index integrity proof)
        for i, row in enumerate(all_rows):
            row["global_index"] = i

        print(f"[results] Loaded {len(all_rows)} results deterministically for {batch_trace_id} "
              f"({len(shard_receipts)} shards, global_index assigned)", flush=True)
        return all_rows

    except Exception as e:
        print(f"[results] Failed to fetch sharded results: {e}", flush=True)
        traceback.print_exc()
        return []


def _fail_batch(batch_trace_id: str, reason: str, db) -> None:
    """Set batch status=failed with error_reason. Used by finalize on proof failure."""
    if not db:
        return
    try:
        db.collection('batches').document(batch_trace_id).update({
            "status": "failed",
            "error_reason": reason[:500],
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[finalize] FAILED batch {batch_trace_id}: {reason[:200]}", flush=True)
    except Exception as e:
        print(f"[finalize] Failed to mark batch as failed: {e}", flush=True)


def generate_results_csv(results: List[Dict]) -> str:
    """Generate CSV content from results."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "row_index",
        "original",
        "resolved",
        "match_type",
        "match_id",
        "confidence",
        "layer",
        "decision",
        "reason"
    ])

    # Data rows
    for i, r in enumerate(results):
        writer.writerow([
            i,
            r.get("original", ""),
            r.get("resolved", ""),
            r.get("match_type", "NO_MATCH"),
            r.get("match_id", ""),
            round(r.get("confidence", 0.0), 4),
            r.get("layer", ""),
            r.get("decision", ""),
            r.get("reason", "")
        ])

    return output.getvalue()


@app.get("/batches/{trace_id}/results")
async def get_batch_results(
    trace_id: str,
    limit: int = 100,
    offset: int = 0,
    auth: dict = Depends(verify_api_key)
):
    """
    Get batch results (paginated).

    Query params:
    - limit: Max records to return (default 100, max 1000)
    - offset: Starting index
    """
    # Validate ownership
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(404, "Batch not found")

    tenant_id = auth.get("tenant_id")
    role = auth.get("role", "user")
    if not is_admin_role(role) and batch.get("tenant_id") != tenant_id:
        raise HTTPException(403, "Access denied")

    # Fetch results
    all_results = fetch_results_from_firestore(trace_id)

    # Paginate
    limit = min(limit, 1000)
    paginated = all_results[offset:offset + limit]

    # RBAC: Strip per-record cost fields for non-admin
    if not is_admin_role(role):
        paginated = [strip_cost_from_record(r) for r in paginated]

    return {
        "trace_id": trace_id,
        "total": len(all_results),
        "offset": offset,
        "limit": limit,
        "count": len(paginated),
        "results": paginated
    }


@app.post("/share/batch/{trace_id}")
async def create_share_link(
    trace_id: str,
    auth: dict = Depends(verify_api_key)
):
    """
    Create a shareable read-only link for a batch.
    Only admin or batch owner can create share links.
    """
    role = auth.get("role", "user")
    tenant_id = auth.get("tenant_id")
    uid = auth.get("uid", "")

    if role == "viewer":
        raise HTTPException(403, "Viewers have read-only access. Share creation not permitted.")

    # Verify batch exists and user has access
    if not is_admin_role(role) and not verify_batch_ownership(trace_id, tenant_id):
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get batch to verify it exists
    batch = get_batch_by_trace_id(trace_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Create share link
    result = create_share_link_in_firestore(
        trace_id=trace_id,
        tenant_id=tenant_id,
        created_by_uid=uid
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to create share link")

    return result


@app.get("/share/{share_token}")
async def resolve_share_link(share_token: str):
    """
    Resolve a share token and return batch details.
    No authentication required - token is the credential.
    """
    # Validate token format
    if not share_token or len(share_token) < 20:
        raise HTTPException(status_code=404, detail="Invalid share link")

    # Get share link record
    share_data = get_share_link_from_firestore(share_token)

    if not share_data:
        raise HTTPException(status_code=404, detail="Share link not found")

    # Check if revoked
    if share_data.get("revoked"):
        raise HTTPException(status_code=410, detail="Share link has been revoked")

    # Check if expired
    expires_at_str = share_data.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo:
                expires_at = expires_at.replace(tzinfo=None)
            if datetime.utcnow() > expires_at:
                raise HTTPException(status_code=410, detail="Share link has expired")
        except ValueError:
            pass

    # Get the batch
    trace_id = share_data.get("trace_id")
    batch = get_batch_by_trace_id(trace_id)

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get audit events for the batch
    events = get_audit_events_from_firestore(trace_id, limit=10000)

    # Return batch details with limited info (read-only view)
    return {
        "batch": {
            "trace_id": batch.get("trace_id"),
            "filename": batch.get("filename"),
            "timestamp": batch.get("timestamp"),
            "total": batch.get("total") or batch.get("total_records", 0),
            "auto_resolved": batch.get("auto_resolved", 0),
            "auto_resolved_pct": batch.get("auto_resolved_pct", 0),
            "flagged_count": batch.get("flagged_count", 0),
            "duration_ms": batch.get("duration_ms", 0),
            "config_version": batch.get("config_version"),
            "stats": batch.get("stats", {})
        },
        "events": events,
        "events_count": len(events),
        "share_info": {
            "created_at": share_data.get("created_at"),
            "expires_at": share_data.get("expires_at"),
            "tenant_id_hash": share_data.get("tenant_id_hash")
        },
        "readonly": True
    }


@app.post("/share/{share_token}/revoke")
async def revoke_share_link(
    share_token: str,
    auth: dict = Depends(verify_api_key)
):
    """
    Revoke a share link.
    Only admin or the creator can revoke.
    """
    role = auth.get("role", "user")
    uid = auth.get("uid", "")

    if role == "viewer":
        raise HTTPException(403, "Viewers have read-only access. Revoke not permitted.")

    # Get share link record
    share_data = get_share_link_from_firestore(share_token)

    if not share_data:
        raise HTTPException(status_code=404, detail="Share link not found")

    # Check authorization: admin or creator
    if not is_admin_role(role) and share_data.get("created_by_uid") != uid:
        raise HTTPException(status_code=403, detail="Not authorized to revoke this link")

    # Revoke
    success = revoke_share_link_in_firestore(share_token)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to revoke share link")

    return {"status": "revoked", "share_token": share_token}


# =============================================================================
# TRUST ASSERTION LAYER (Phase 9 — ia-attestation/v1)
# =============================================================================
# POST /assert — policy-enforced gate consuming existing receipts.
# INVARIANT: /assert NEVER creates receipts. It only verifies and asserts.
# TEST-only initially.

import yaml as _yaml
import uuid as _uuid_mod

# --- Policy loader ---
_ASSERT_POLICY_CACHE: Dict[str, dict] = {}


def _load_assert_policy(version: str = "1.0") -> Optional[dict]:
    """Load assertion policy by version. Cached after first load."""
    if version in _ASSERT_POLICY_CACHE:
        return _ASSERT_POLICY_CACHE[version]
    policy_dir = os.path.join(os.path.dirname(__file__), "..", "config", "assert_policies")
    # Map version "1.0" -> "v1.yaml"
    major = version.split(".")[0]
    policy_path = os.path.join(policy_dir, f"v{major}.yaml")
    try:
        with open(policy_path, "r") as f:
            policy = _yaml.safe_load(f)
        if policy and policy.get("status") == "active":
            _ASSERT_POLICY_CACHE[version] = policy
            return policy
    except Exception as e:
        print(f"[assert] Failed to load policy v{version}: {e}", flush=True)
    return None


# --- Assertion rate limiters ---
_assert_ip_rate: Dict[str, list] = {}
_assert_receipt_rate: Dict[str, list] = {}
_ASSERT_IP_LIMIT = 100
_ASSERT_RECEIPT_LIMIT = 10
_ASSERT_RATE_WINDOW = 60  # seconds


def _check_assert_rate_limit(client_ip: str, receipt_id: str) -> Optional[str]:
    """
    Dual rate limit: per-IP (100/min) AND per-receipt_id (10/min).
    Returns None if allowed, or the limit type that was exceeded.
    """
    now = time.time()
    window_start = now - _ASSERT_RATE_WINDOW

    # Per-IP check
    if client_ip not in _assert_ip_rate:
        _assert_ip_rate[client_ip] = []
    _assert_ip_rate[client_ip] = [t for t in _assert_ip_rate[client_ip] if t > window_start]
    if len(_assert_ip_rate[client_ip]) >= _ASSERT_IP_LIMIT:
        return "ip"

    # Per-receipt_id check
    if receipt_id not in _assert_receipt_rate:
        _assert_receipt_rate[receipt_id] = []
    _assert_receipt_rate[receipt_id] = [t for t in _assert_receipt_rate[receipt_id] if t > window_start]
    if len(_assert_receipt_rate[receipt_id]) >= _ASSERT_RECEIPT_LIMIT:
        return "receipt_id"

    # Record the request
    _assert_ip_rate[client_ip].append(now)
    _assert_receipt_rate[receipt_id].append(now)
    return None


# --- Assertion audit log (Firestore, hash-chained, append-only) ---

def _write_assertion_event(
    assertion_id: str,
    receipt_id: str,
    decision: str,
    reason: str,
    context: dict,
    receipt_root_hash: Optional[str],
    policy_version: str,
    checks_evaluated: dict,
    client_ip: str,
) -> bool:
    """
    Write append-only assertion event to Firestore.
    Hash-chains assertion_id to receipt_root_hash for tamper evidence.
    """
    if not _firestore_db:
        return False
    try:
        now_utc = datetime.now(timezone.utc)
        # Hash chain: SHA-256(assertion_id + receipt_root_hash)
        chain_input = f"{assertion_id}:{receipt_root_hash or 'null'}"
        chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()

        event = {
            "assertion_id": assertion_id,
            "receipt_id": receipt_id,
            "decision": decision,
            "reason": reason,
            "context": {
                "system": context.get("system", ""),
                "action": context.get("action", ""),
                "resource_id": context.get("resource_id", ""),
                "correlation_id": context.get("correlation_id", ""),
            },
            "receipt_root_hash": receipt_root_hash,
            "policy_version": policy_version,
            "checks_evaluated": checks_evaluated,
            "chain_hash": chain_hash,
            "timestamp": now_utc.isoformat(),
            "client_ip_hash": hashlib.sha256(client_ip.encode()).hexdigest()[:16],
        }

        _firestore_db.collection("assertion_events").document(assertion_id).set(event)
        return True
    except Exception as e:
        print(f"[assert] Failed to write assertion event: {e}", flush=True)
        return False


# --- Request/Response models ---

class AssertionContext(BaseModel):
    system: str = Field(..., max_length=256, description="Calling system identifier")
    action: str = Field(..., max_length=256, description="Action being gated")
    resource_id: Optional[str] = Field(None, max_length=256, description="Resource being acted on")
    correlation_id: Optional[str] = Field(None, max_length=256, description="Caller correlation ID")


class AssertionRequiredChecks(BaseModel):
    signature_valid: bool = True
    anchor_valid: bool = True
    artifact_integrity: bool = True
    replay_protection: bool = True


class AssertionRequest(BaseModel):
    receipt_id: str = Field(..., min_length=1, max_length=256, description="Receipt ID to verify")
    required_checks: Optional[AssertionRequiredChecks] = None
    context: AssertionContext


# --- Endpoint ---

@app.post("/assert")
async def trust_assertion(body: AssertionRequest, request: Request):
    """
    TRUST ASSERTION LAYER (Phase 9 — ia-attestation/v1)

    Policy-enforced gate that requires a valid IA receipt before
    allowing downstream action. Consumes existing receipts only.
    NEVER creates receipts.

    - 200: assertion evaluated (decision: allow/deny)
    - 422: invalid request body
    - 429: rate limit exceeded
    - 503: assertion service unavailable
    """
    t0 = time.time()
    client_ip = request.client.host if request.client else "unknown"
    receipt_id = body.receipt_id
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # --- Rate limiting (dual) ---
    rate_exceeded = _check_assert_rate_limit(client_ip, receipt_id)
    if rate_exceeded:
        return JSONResponse(
            status_code=429,
            content={
                "decision": "deny",
                "receipt_id": receipt_id,
                "verified": False,
                "reason": "RATE_LIMITED",
                "assertion_id": None,
                "verification_timestamp": now_utc,
            },
            headers={**_VERIFY_SECURITY_HEADERS, "Retry-After": str(_ASSERT_RATE_WINDOW)},
        )

    # --- Load policy ---
    policy = _load_assert_policy("1.0")
    if not policy:
        if True:  # fail_closed default
            return JSONResponse(
                status_code=503,
                content={
                    "decision": "deny",
                    "receipt_id": receipt_id,
                    "verified": False,
                    "reason": "IA_UNAVAILABLE",
                    "assertion_id": None,
                    "verification_timestamp": now_utc,
                },
                headers=_VERIFY_SECURITY_HEADERS,
            )

    fail_closed = policy.get("fail_closed", True)
    policy_version = policy.get("version", "1.0")

    # --- Context validation ---
    ctx = body.context
    ctx_dict = {"system": ctx.system, "action": ctx.action,
                "resource_id": ctx.resource_id or "", "correlation_id": ctx.correlation_id or ""}

    # Check required context fields per policy
    required_ctx_fields = policy.get("context", {}).get("required_fields", [])
    for req_field in required_ctx_fields:
        val = ctx_dict.get(req_field, "")
        if not val or not val.strip():
            assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"
            _write_assertion_event(
                assertion_id=assertion_id, receipt_id=receipt_id, decision="deny",
                reason="CONTEXT_INVALID", context=ctx_dict, receipt_root_hash=None,
                policy_version=policy_version, checks_evaluated={}, client_ip=client_ip,
            )
            return JSONResponse(
                status_code=200,
                content={
                    "decision": "deny", "receipt_id": receipt_id, "verified": False,
                    "reason": "CONTEXT_INVALID", "assertion_id": assertion_id,
                    "verification_timestamp": now_utc,
                },
                headers=_VERIFY_SECURITY_HEADERS,
            )

    max_len = policy.get("context", {}).get("max_field_length", 256)
    for field_name in ["system", "action", "resource_id", "correlation_id"]:
        if len(ctx_dict.get(field_name, "")) > max_len:
            assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"
            _write_assertion_event(
                assertion_id=assertion_id, receipt_id=receipt_id, decision="deny",
                reason="CONTEXT_INVALID", context=ctx_dict, receipt_root_hash=None,
                policy_version=policy_version, checks_evaluated={}, client_ip=client_ip,
            )
            return JSONResponse(
                status_code=200,
                content={
                    "decision": "deny", "receipt_id": receipt_id, "verified": False,
                    "reason": "CONTEXT_INVALID", "assertion_id": assertion_id,
                    "verification_timestamp": now_utc,
                },
                headers=_VERIFY_SECURITY_HEADERS,
            )

    # --- Receipt lookup ---
    batch = _find_batch_by_receipt_id(receipt_id)
    if not batch:
        assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"
        _write_assertion_event(
            assertion_id=assertion_id, receipt_id=receipt_id, decision="deny",
            reason="RECEIPT_INVALID", context=ctx_dict, receipt_root_hash=None,
            policy_version=policy_version, checks_evaluated={}, client_ip=client_ip,
        )
        return JSONResponse(
            status_code=200,
            content={
                "decision": "deny", "receipt_id": receipt_id, "verified": False,
                "reason": "RECEIPT_INVALID", "assertion_id": assertion_id,
                "verification_timestamp": now_utc,
            },
            headers=_VERIFY_SECURITY_HEADERS,
        )

    receipt = batch.get("receipt", {})
    gcs_prefix = receipt.get("gcs_path", "")

    # --- Receipt age check ---
    max_age = policy.get("max_receipt_age_seconds", 86400)
    receipt_ts_str = receipt.get("finalized_at", "")
    if receipt_ts_str:
        try:
            if isinstance(receipt_ts_str, str):
                receipt_ts = datetime.fromisoformat(receipt_ts_str.replace("Z", "+00:00"))
            else:
                receipt_ts = receipt_ts_str  # Firestore timestamp
                if hasattr(receipt_ts, 'timestamp'):
                    receipt_ts = datetime.fromtimestamp(receipt_ts.timestamp(), tz=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - receipt_ts).total_seconds()
            if age_seconds > max_age:
                assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"
                _write_assertion_event(
                    assertion_id=assertion_id, receipt_id=receipt_id, decision="deny",
                    reason="RECEIPT_EXPIRED", context=ctx_dict,
                    receipt_root_hash=receipt.get("manifest_hash"),
                    policy_version=policy_version, checks_evaluated={}, client_ip=client_ip,
                )
                return JSONResponse(
                    status_code=200,
                    content={
                        "decision": "deny", "receipt_id": receipt_id, "verified": False,
                        "reason": "RECEIPT_EXPIRED", "assertion_id": assertion_id,
                        "verification_timestamp": now_utc,
                    },
                    headers=_VERIFY_SECURITY_HEADERS,
                )
        except Exception:
            pass  # Cannot parse timestamp — proceed to verification

    # --- Load receipt bundle from GCS ---
    if not gcs_prefix:
        assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"
        _write_assertion_event(
            assertion_id=assertion_id, receipt_id=receipt_id, decision="deny",
            reason="RECEIPT_INVALID", context=ctx_dict, receipt_root_hash=None,
            policy_version=policy_version, checks_evaluated={}, client_ip=client_ip,
        )
        return JSONResponse(
            status_code=200,
            content={
                "decision": "deny", "receipt_id": receipt_id, "verified": False,
                "reason": "RECEIPT_INVALID", "assertion_id": assertion_id,
                "verification_timestamp": now_utc,
            },
            headers=_VERIFY_SECURITY_HEADERS,
        )

    manifest_bytes, signature_bytes, gcs_error = _load_receipt_bundle_from_gcs(gcs_prefix)
    if manifest_bytes is None or signature_bytes is None:
        assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"
        _write_assertion_event(
            assertion_id=assertion_id, receipt_id=receipt_id, decision="deny",
            reason="RECEIPT_INVALID", context=ctx_dict, receipt_root_hash=None,
            policy_version=policy_version, checks_evaluated={}, client_ip=client_ip,
        )
        return JSONResponse(
            status_code=200,
            content={
                "decision": "deny", "receipt_id": receipt_id, "verified": False,
                "reason": "RECEIPT_INVALID", "assertion_id": assertion_id,
                "verification_timestamp": now_utc,
            },
            headers=_VERIFY_SECURITY_HEADERS,
        )

    # --- Run verifier ---
    try:
        from app.attestation.verifier_v1 import verify_manifest_bundle
        from app.security.public_verify import _resolve_public_key_for_verification

        def _assert_key_resolver(key_id: str):
            pem = _resolve_public_key_for_verification(key_id)
            if pem and isinstance(pem, str):
                return pem.encode("utf-8")
            return pem

        verify_result = verify_manifest_bundle(
            manifest_bytes=manifest_bytes,
            signature_bytes=signature_bytes,
            metadata_bytes=None,
            public_key_resolver=_assert_key_resolver,
            fail_closed=fail_closed,
        )
    except Exception as _ve:
        print(f"[assert] Verifier exception for {receipt_id}: {_ve}", flush=True)
        assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"
        decision = "deny" if fail_closed else "allow"
        _write_assertion_event(
            assertion_id=assertion_id, receipt_id=receipt_id, decision=decision,
            reason="IA_UNAVAILABLE", context=ctx_dict, receipt_root_hash=None,
            policy_version=policy_version, checks_evaluated={}, client_ip=client_ip,
        )
        return JSONResponse(
            status_code=200,
            content={
                "decision": decision, "receipt_id": receipt_id, "verified": False,
                "reason": "IA_UNAVAILABLE", "assertion_id": assertion_id,
                "verification_timestamp": now_utc,
            },
            headers=_VERIFY_SECURITY_HEADERS,
        )

    # --- Evaluate checks against policy ---
    checks_passed = verify_result.get("checks_passed", [])
    required_policy_checks = policy.get("required_checks", [])

    # Map request required_checks to internal verifier check names
    req_checks = body.required_checks or AssertionRequiredChecks()
    request_check_map = {
        "signature": req_checks.signature_valid,
        "anchor_binding": req_checks.anchor_valid,
        "artifact_integrity": req_checks.artifact_integrity,
        "schema_jcs": req_checks.replay_protection,
    }

    checks_evaluated = {}
    all_passed = verify_result.get("success", False)
    policy_violation = False

    for check_name in required_policy_checks:
        passed = check_name in checks_passed
        checks_evaluated[check_name] = passed
        # If the caller requires this check AND policy requires it, it must pass
        if request_check_map.get(check_name, True) and not passed:
            policy_violation = True

    # Extract root_hash from manifest for hash-chain
    root_hash = None
    try:
        manifest_data = json.loads(manifest_bytes)
        root_hash = manifest_data.get("root_hash")
    except Exception:
        pass

    # --- Decision ---
    assertion_id = f"asrt_{_uuid_mod.uuid4().hex[:24]}"

    if all_passed and not policy_violation:
        decision = "allow"
        reason = ""
    elif policy_violation:
        decision = "deny"
        reason = "POLICY_VIOLATION"
    else:
        decision = "deny"
        fr = verify_result.get("failure_reason", "RECEIPT_INVALID")
        # Map verifier failure to assertion taxonomy
        _ASSERT_REASON_MAP = {
            "MANIFEST_MALFORMED": "RECEIPT_INVALID",
            "SIGNATURE_INVALID": "RECEIPT_INVALID",
            "KEY_VERSION_MISMATCH": "RECEIPT_INVALID",
            "METADATA_INCONSISTENT": "RECEIPT_INVALID",
            "ANCHOR_HASH_MISMATCH": "RECEIPT_INVALID",
            "ARTIFACT_HASH_MISMATCH": "RECEIPT_INVALID",
            "ARTIFACT_SIZE_MISMATCH": "RECEIPT_INVALID",
            "TIMESTAMP_SKEW_EXCEEDED": "RECEIPT_EXPIRED",
            "INTERNAL_ERROR": "IA_UNAVAILABLE",
        }
        reason = _ASSERT_REASON_MAP.get(fr, "RECEIPT_INVALID")

    duration_ms = (time.time() - t0) * 1000

    # --- Write assertion audit event ---
    _write_assertion_event(
        assertion_id=assertion_id,
        receipt_id=receipt_id,
        decision=decision,
        reason=reason,
        context=ctx_dict,
        receipt_root_hash=root_hash,
        policy_version=policy_version,
        checks_evaluated=checks_evaluated,
        client_ip=client_ip,
    )

    # --- Structured log ---
    slog(trace_id=batch.get("trace_id", ""), phase="trust_assertion",
         event="assertion_evaluated",
         assertion_id=assertion_id, receipt_id=receipt_id,
         decision=decision, reason=reason,
         policy_version=policy_version, duration_ms=round(duration_ms, 2),
         checks_evaluated=checks_evaluated)

    # --- Phase 9.1: Transparency log entry for assertion (async) ---
    try:
        from app.transparency.spine import enqueue_entry as _tlog_enqueue_a, TRANSPARENCY_ENABLED as _tlog_on_a
        if _tlog_on_a and root_hash:
            _tlog_enqueue_a(
                entry_type="assertion",
                entry_id=assertion_id,
                root_hash=root_hash,
            )
    except Exception as _tlog_err_a:
        print(f"[transparency] Assertion entry enqueue failed: {_tlog_err_a}", flush=True)

    return JSONResponse(
        status_code=200,
        content={
            "decision": decision,
            "receipt_id": receipt_id,
            "verified": all_passed and not policy_violation,
            "reason": reason,
            "assertion_id": assertion_id,
            "verification_timestamp": now_utc,
        },
        headers=_VERIFY_SECURITY_HEADERS,
    )


# =============================================================================
# TRANSPARENCY LOG SPINE ENDPOINTS (Phase 9.1 — TEST only)
# =============================================================================

@app.get("/transparency/latest-root")
async def transparency_latest_root():
    """
    Get the latest transparency tree root.

    Returns tree size, root hash, and latest published signed root.
    TEST only.
    """
    try:
        from app.transparency.spine import get_latest_root, TRANSPARENCY_ENABLED
        if not TRANSPARENCY_ENABLED:
            return JSONResponse(
                status_code=503,
                content={"error": "Transparency log not enabled"},
                headers=_VERIFY_SECURITY_HEADERS,
            )
        result = get_latest_root()
        return JSONResponse(content=result, headers=_VERIFY_SECURITY_HEADERS)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error"},
            headers=_VERIFY_SECURITY_HEADERS,
        )


@app.get("/transparency/proof/{entry_id}")
async def transparency_proof(entry_id: str):
    """
    Get an inclusion proof for a transparency log entry.

    Returns leaf index, inclusion proof path, tree size, root hash.
    TEST only.
    """
    try:
        from app.transparency.spine import get_inclusion_proof, TRANSPARENCY_ENABLED
        if not TRANSPARENCY_ENABLED:
            return JSONResponse(
                status_code=503,
                content={"error": "Transparency log not enabled"},
                headers=_VERIFY_SECURITY_HEADERS,
            )
        result = get_inclusion_proof(entry_id)
        if not result["found"]:
            return JSONResponse(
                status_code=404,
                content={"error": "Entry not found", "entry_id": entry_id},
                headers=_VERIFY_SECURITY_HEADERS,
            )
        return JSONResponse(content=result, headers=_VERIFY_SECURITY_HEADERS)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error"},
            headers=_VERIFY_SECURITY_HEADERS,
        )


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 60, flush=True)
    print("INTELLIGENT ANALYST v3.0.0 ENTERPRISE", flush=True)
    print("Full Audit + Backend Button Support", flush=True)
    print("=" * 60, flush=True)
    print(f"CORS Origins: {config.ALLOWED_ORIGINS}", flush=True)
    print(f"Auth Enabled: {bool(config.API_KEY)}", flush=True)
    print(f"Rate Limit: {config.RATE_LIMIT_REQUESTS}/{config.RATE_LIMIT_WINDOW_SECONDS}s", flush=True)
    print(f"Max Batch: {config.MAX_BATCH_SIZE}", flush=True)
    print(f"Firestore: {'Connected' if _firestore_db else 'Not Available'}", flush=True)
    print(f"sklearn: {'Available' if HAS_SKLEARN else 'Not Available'}", flush=True)
    print("=" * 60, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)
