"""
Dataset Router — Deterministic auto-routing based on schema + column profiling.

Inspects headers and sample rows to classify the dataset type before
the file parser extracts a single column. This prevents person-heavy
spreadsheets from being misclassified as GARBAGE.

Decision order:
  1. Header signal detection (person, company keywords)
  2. Column profiling (numeric, alpha, null, unique ratios)
  3. Routing decision with structured metadata

Returns routing metadata dict persisted to batch classification_meta.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.dataset_classifier import classify_dataset


# ============================================================================
# INSPECTION LOGGING
# ============================================================================

_LOG_DIR = Path(os.environ.get("IA_ROUTING_LOG_DIR", Path(__file__).parent.parent / "logs"))
_LOG_FILE = _LOG_DIR / "dataset_routing_debug.json"
_DISAGREEMENT_FILE = _LOG_DIR / "routing_disagreements.jsonl"
_ABSTENTION_FILE = _LOG_DIR / "routing_abstentions.jsonl"
_METRICS_FILE = _LOG_DIR / "routing_metrics.json"
_LOGGING_ENABLED = os.environ.get("IA_ROUTING_LOGGING", "1") == "1"
_METRICS_FLUSH_INTERVAL = int(os.environ.get("IA_METRICS_FLUSH_INTERVAL", "1000"))

# In-memory metrics accumulator (flushed every _METRICS_FLUSH_INTERVAL runs)
_metrics = {
    "total_runs": 0,
    "classifier_used": 0,
    "fallback_used": 0,
    "confidence_sum": 0.0,
    "confidence_buckets": {
        "0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0,
        "0.6-0.8": 0, "0.8-1.0": 0,
    },
}


def _confidence_bucket(c: float) -> str:
    if c < 0.2:
        return "0.0-0.2"
    elif c < 0.4:
        return "0.2-0.4"
    elif c < 0.6:
        return "0.4-0.6"
    elif c < 0.8:
        return "0.6-0.8"
    return "0.8-1.0"


def _update_metrics(classifier_confidence: float, fallback_used: bool) -> None:
    """Accumulate routing metrics and flush to disk at interval."""
    _metrics["total_runs"] += 1
    _metrics["confidence_sum"] += classifier_confidence
    if fallback_used:
        _metrics["fallback_used"] += 1
    else:
        _metrics["classifier_used"] += 1
    bucket = _confidence_bucket(classifier_confidence)
    _metrics["confidence_buckets"][bucket] = _metrics["confidence_buckets"].get(bucket, 0) + 1

    if _metrics["total_runs"] % _METRICS_FLUSH_INTERVAL == 0:
        _flush_metrics()


def _flush_metrics() -> None:
    """Write current metrics snapshot to disk."""
    if not _LOGGING_ENABLED:
        return
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        total = _metrics["total_runs"]
        snapshot = {
            "total_runs": total,
            "classifier_used": _metrics["classifier_used"],
            "fallback_used": _metrics["fallback_used"],
            "avg_confidence": round(_metrics["confidence_sum"] / max(total, 1), 4),
            "confidence_histogram": dict(_metrics["confidence_buckets"]),
            "flushed_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        with open(_METRICS_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)
    except Exception as e:
        print(f"[dataset_router] Metrics flush failed: {e}", flush=True)


def get_routing_metrics() -> Dict:
    """Return current in-memory metrics snapshot (for testing / inspection)."""
    total = _metrics["total_runs"]
    return {
        "total_runs": total,
        "classifier_used": _metrics["classifier_used"],
        "fallback_used": _metrics["fallback_used"],
        "avg_confidence": round(_metrics["confidence_sum"] / max(total, 1), 4),
        "confidence_histogram": dict(_metrics["confidence_buckets"]),
    }


def reset_routing_metrics() -> None:
    """Reset in-memory metrics (for testing only)."""
    _metrics["total_runs"] = 0
    _metrics["classifier_used"] = 0
    _metrics["fallback_used"] = 0
    _metrics["confidence_sum"] = 0.0
    for k in _metrics["confidence_buckets"]:
        _metrics["confidence_buckets"][k] = 0


def _log_disagreement(headers: List[str], classifier_label: str,
                      classifier_confidence: float, heuristic_result: str,
                      effective_mode: str) -> None:
    """Log when classifier and heuristic disagree on routing."""
    if not _LOGGING_ENABLED:
        return
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "dataset_headers": headers[:20],
            "classifier_label": classifier_label,
            "classifier_confidence": classifier_confidence,
            "heuristic_result": heuristic_result,
            "effective_mode": effective_mode,
        }
        with open(_DISAGREEMENT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[dataset_router] Disagreement logging failed: {e}", flush=True)


def _log_abstention(headers: List[str], classifier_label: str,
                    classifier_confidence: float, heuristic_result: str,
                    abstain_reason: str, effective_mode: str) -> None:
    """Log when the router abstains from using the classifier."""
    if not _LOGGING_ENABLED:
        return
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "dataset_headers": headers[:20],
            "classifier_label": classifier_label,
            "classifier_confidence": classifier_confidence,
            "heuristic_result": heuristic_result,
            "abstain_reason": abstain_reason,
            "effective_mode": effective_mode,
        }
        with open(_ABSTENTION_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[dataset_router] Abstention logging failed: {e}", flush=True)


def _log_routing_decision(filename: str, result: Dict, raw_headers: List[str],
                          sample_rows: Optional[List[Dict]] = None) -> None:
    """Append a routing decision record to the debug log (JSONL format)."""
    if not _LOGGING_ENABLED:
        return
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "filename": filename,
            "headers": raw_headers[:20],
            "sample_rows": (sample_rows or [])[:5],
            "routing_result": {
                "effective_mode": result.get("effective_mode"),
                "routing_decision": result.get("routing_decision"),
                "routing_reason": result.get("routing_reason"),
                "dataset_type": result.get("dataset_type"),
                "alpha_columns": result.get("alpha_columns"),
                "numeric_columns": result.get("numeric_columns"),
                "company_token_ratio": result.get("company_token_ratio"),
                "classifier_label": result.get("classifier_label"),
                "classifier_confidence": result.get("classifier_confidence"),
                "fallback_used": result.get("fallback_used"),
            },
        }
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[dataset_router] Logging failed: {e}", flush=True)


# ============================================================================
# HEADER SIGNALS
# ============================================================================

PERSON_HEADER_SIGNALS = {
    "nombre", "primer apellido", "segundo apellido", "apellido",
    "edad", "sexo", "carne", "identidad", "departamento",
    "unidad organizativa", "posicion", "area",
    # English equivalents
    "first_name", "first name", "firstname", "last_name", "last name",
    "lastname", "middle_name", "middle name", "full_name", "full name",
    "given_name", "surname", "gender", "age", "date_of_birth", "dob",
    "employee", "employee_name", "employee_id", "person", "person_name",
    "staff", "worker", "title", "salutation", "nationality",
}

COMPANY_HEADER_SIGNALS = {
    "company", "company_name", "company_raw", "organization",
    "org_name", "entity", "vendor", "supplier", "customer",
    "account", "account_name", "corp", "corporation", "firm",
    "business", "business_name", "employer", "parent_company",
    "subsidiary", "legal_entity", "trading_name",
}

COMPANY_VALUE_TOKENS = {
    "company", "corp", "inc", "ltd", "group", "llc",
    "gmbh", "plc", "limited", "corporation", "holdings",
    "partners", "associates", "enterprises", "international",
    "sa", "srl", "bv", "nv", "ag", "pty",
}


# ============================================================================
# COLUMN PROFILING
# ============================================================================

def _normalize_header(h: str) -> str:
    """Lowercase, strip punctuation and whitespace."""
    return re.sub(r"[^a-z0-9\s_]", "", str(h).lower().strip())


def _profile_column(series: pd.Series, sample_size: int = 100) -> Dict:
    """Compute numeric/alpha/null/unique ratios for a column."""
    sample = series.head(sample_size)
    total = len(sample)
    if total == 0:
        return {"numeric_ratio": 0.0, "alpha_ratio": 0.0, "null_ratio": 1.0, "unique_ratio": 0.0}

    non_null = sample.dropna().astype(str).str.strip()
    null_count = total - len(non_null)
    non_empty = non_null[non_null != ""]

    if len(non_empty) == 0:
        return {"numeric_ratio": 0.0, "alpha_ratio": 0.0, "null_ratio": 1.0, "unique_ratio": 0.0}

    numeric_count = non_empty.str.match(r"^\d+\.?\d*$").sum()
    alpha_count = non_empty.str.contains(r"[a-zA-ZáéíóúñÁÉÍÓÚÑüÜ]", regex=True).sum()

    return {
        "numeric_ratio": round(numeric_count / len(non_empty), 4),
        "alpha_ratio": round(alpha_count / len(non_empty), 4),
        "null_ratio": round(null_count / total, 4),
        "unique_ratio": round(non_empty.nunique() / len(non_empty), 4) if len(non_empty) > 0 else 0.0,
    }


# ============================================================================
# DATASET INSPECTION
# ============================================================================

def inspect_dataset(content: bytes, filename: str) -> Dict:
    """
    Inspect raw file content and return a routing decision.

    Args:
        content: Raw file bytes
        filename: Original filename (for format detection)

    Returns:
        Routing metadata dict with effective_mode, routing_reason, etc.
    """
    filename_lower = (filename or "upload").lower()

    # Parse into DataFrame
    df = _parse_to_dataframe(content, filename_lower)
    if df is None or df.empty:
        result = _make_result(
            effective_mode="mixed",
            routing_decision="empty_dataset",
            routing_reason="File is empty or unparseable; defaulting to sanitize pipeline",
        )
        _log_routing_decision(filename, result, [])
        return result

    # Normalize headers
    raw_headers = [str(c) for c in df.columns]
    normalized_headers = [_normalize_header(h) for h in raw_headers]

    # 1. Header signal detection
    person_headers_found = [h for h in normalized_headers if h in PERSON_HEADER_SIGNALS]
    company_headers_found = [h for h in normalized_headers if h in COMPANY_HEADER_SIGNALS]
    person_header_signal = len(person_headers_found) >= 2
    company_header_signal = len(company_headers_found) >= 1

    # 2. Column profiling
    sample_size = min(100, len(df))
    profiles = {}
    alpha_columns = 0
    numeric_columns = 0

    for col in df.columns:
        profile = _profile_column(df[col], sample_size)
        col_name = _normalize_header(str(col))
        profiles[col_name] = profile

        if profile["numeric_ratio"] > 0.9:
            numeric_columns += 1
        if profile["alpha_ratio"] > 0.3:
            alpha_columns += 1

    # 3. Value-level company token scan (check first 100 non-null values across text columns)
    company_token_hits = 0
    text_values_checked = 0
    for col in df.columns:
        col_profile = profiles.get(_normalize_header(str(col)), {})
        if col_profile.get("alpha_ratio", 0) < 0.3:
            continue
        sample_vals = df[col].dropna().astype(str).head(sample_size)
        for val in sample_vals:
            text_values_checked += 1
            val_lower = val.lower()
            if any(token in val_lower for token in COMPANY_VALUE_TOKENS):
                company_token_hits += 1

    company_token_ratio = company_token_hits / max(text_values_checked, 1)

    # ================================================================
    # 4. ML CLASSIFIER — attempt prediction before heuristic fallback
    # ================================================================
    classifier_result = None
    sample_texts = []
    for col in df.columns:
        col_profile = profiles.get(_normalize_header(str(col)), {})
        if col_profile.get("alpha_ratio", 0) >= 0.3:
            sample_texts.extend(df[col].dropna().astype(str).head(sample_size).tolist())
    if not sample_texts:
        # Fall back to all columns if no alpha columns found
        for col in df.columns:
            sample_texts.extend(df[col].dropna().astype(str).head(sample_size).tolist())

    try:
        classifier_result = classify_dataset(sample_texts[:200], headers=raw_headers)
    except Exception as e:
        print(f"[dataset_router] Classifier failed, using heuristic fallback: {e}", flush=True)
        classifier_result = {"label": "unknown", "confidence": 0.0, "error": str(e)}

    # ================================================================
    # CONFIDENCE-AWARE ABSTENTION POLICY
    # ================================================================
    #   >= 0.80  → classifier wins (high confidence)
    #   0.50–0.79 → classifier wins ONLY if it agrees with heuristic;
    #               otherwise abstain and use heuristic
    #   < 0.50   → always use deterministic heuristic
    # ================================================================
    CONFIDENCE_HIGH = 0.80
    CONFIDENCE_MID = 0.50

    classifier_label = classifier_result.get("label", "unknown")
    classifier_confidence = classifier_result.get("confidence", 0.0)

    # Extract sample rows for logging (before any return)
    _sample_rows_for_log = []
    try:
        for _, row in df.head(5).iterrows():
            _sample_rows_for_log.append({str(k): str(v)[:100] for k, v in row.items()})
    except Exception:
        pass

    # Pre-compute heuristic result (deterministic, always computed)
    total_cols = len(df.columns)
    _heuristic_label = "mixed"  # default
    if person_header_signal and alpha_columns >= 2:
        _heuristic_label = "person"
    elif company_header_signal or company_token_ratio >= 0.30:
        _heuristic_label = "company"
    elif numeric_columns == total_cols and alpha_columns == 0 and not person_header_signal and not company_header_signal:
        _heuristic_label = "garbage"

    # Map classifier labels to heuristic-comparable labels
    _clf_as_heuristic = {"person": "person", "org": "company", "garbage": "garbage"}.get(classifier_label, "mixed")

    # Decide: should classifier be allowed to route?
    _use_classifier = False
    _abstained = False
    _abstain_reason = None

    if classifier_label == "unknown":
        # Classifier unavailable — pure fallback
        _abstain_reason = None  # not an abstention, just no classifier
    elif classifier_confidence >= CONFIDENCE_HIGH:
        # Zone 1: high confidence → classifier allowed
        _use_classifier = True
    elif classifier_confidence >= CONFIDENCE_MID:
        # Zone 2: mid confidence → only if classifier agrees with heuristic
        if _clf_as_heuristic == _heuristic_label:
            _use_classifier = True
        else:
            _abstained = True
            _abstain_reason = (
                f"Mid-confidence disagreement: classifier={classifier_label}@"
                f"{classifier_confidence:.2f} vs heuristic={_heuristic_label}"
            )
            _log_abstention(raw_headers, classifier_label, classifier_confidence,
                            _heuristic_label, _abstain_reason, _heuristic_label)
    else:
        # Zone 3: low confidence → always heuristic
        pass

    # Disagreement logging (observability — independent of abstention)
    if classifier_label != "unknown" and _clf_as_heuristic != _heuristic_label:
        _log_disagreement(raw_headers, classifier_label, classifier_confidence,
                          _heuristic_label,
                          _clf_as_heuristic if _use_classifier else _heuristic_label)

    if _use_classifier:
        label_to_mode = {"person": "mixed", "org": "company", "garbage": "reject"}
        label_to_type = {"person": "PERSON", "org": "COMPANY", "garbage": "INVALID"}
        eff_mode = label_to_mode.get(classifier_label, "mixed")
        ds_type = label_to_type.get(classifier_label, "MIXED")

        _update_metrics(classifier_confidence, fallback_used=False)

        _ml_result = _make_result(
            effective_mode=eff_mode,
            routing_decision=f"ml_classifier_{classifier_label}",
            routing_reason=f"ML classifier: {classifier_label} ({classifier_confidence:.0%} confidence)",
            dataset_type=ds_type,
            person_headers=person_headers_found,
            company_headers=company_headers_found,
            profiles=profiles,
            raw_headers=raw_headers,
            sample_row_count=sample_size,
            alpha_columns=alpha_columns,
            numeric_columns=numeric_columns,
            company_token_ratio=round(company_token_ratio, 4),
            classifier_label=classifier_label,
            classifier_confidence=classifier_confidence,
            fallback_used=False,
            abstained=False,
            heuristic_result=_heuristic_label,
        )
        _log_routing_decision(filename, _ml_result, raw_headers, _sample_rows_for_log)
        return _ml_result

    # ================================================================
    # 5. HEURISTIC FALLBACK — deterministic rules
    # ================================================================
    _update_metrics(classifier_confidence, fallback_used=True)

    # Helper to log + return in one step
    def _return_logged(result: Dict) -> Dict:
        _log_routing_decision(filename, result, raw_headers, _sample_rows_for_log)
        return result

    # Common kwargs for heuristic fallback results (include classifier + abstention info)
    _fallback_kwargs = dict(
        person_headers=person_headers_found,
        company_headers=company_headers_found,
        profiles=profiles,
        raw_headers=raw_headers,
        sample_row_count=sample_size,
        alpha_columns=alpha_columns,
        numeric_columns=numeric_columns,
        company_token_ratio=round(company_token_ratio, 4),
        classifier_label=classifier_label if classifier_label != "unknown" else None,
        classifier_confidence=classifier_confidence if classifier_label != "unknown" else None,
        fallback_used=True,
        abstained=_abstained,
        abstain_reason=_abstain_reason,
        heuristic_result=_heuristic_label,
    )

    # PERSON: strong header signal + alphabetic columns
    if person_header_signal and alpha_columns >= 2:
        return _return_logged(_make_result(
            effective_mode="mixed",
            routing_decision="person_dataset",
            routing_reason=f"Person dataset detected: {len(person_headers_found)} person headers ({', '.join(person_headers_found[:5])}), {alpha_columns} text columns",
            dataset_type="PERSON",
            **_fallback_kwargs,
        ))

    # COMPANY: header signal or high company token ratio
    if company_header_signal or company_token_ratio >= 0.30:
        return _return_logged(_make_result(
            effective_mode="company",
            routing_decision="company_dataset",
            routing_reason=f"Company dataset detected: {len(company_headers_found)} company headers, {company_token_ratio:.0%} company tokens in values",
            dataset_type="COMPANY",
            **_fallback_kwargs,
        ))

    # INVALID / GARBAGE: >90% numeric, no alpha, no header signals
    if numeric_columns == total_cols and alpha_columns == 0 and not person_header_signal and not company_header_signal:
        return _return_logged(_make_result(
            effective_mode="reject",
            routing_decision="invalid_dataset",
            routing_reason=f"All {total_cols} columns are numeric-only with no entity signals",
            dataset_type="INVALID",
            **_fallback_kwargs,
        ))

    # MIXED: alphabetic tokens exist but no strong signal
    return _return_logged(_make_result(
        effective_mode="mixed",
        routing_decision="mixed_dataset",
        routing_reason=f"Mixed dataset: {alpha_columns} text columns, {numeric_columns} numeric columns, no dominant entity signal",
        dataset_type="MIXED",
        **_fallback_kwargs,
    ))


# ============================================================================
# HELPERS
# ============================================================================

def _parse_to_dataframe(content: bytes, filename: str) -> Optional[pd.DataFrame]:
    """Parse file bytes into a DataFrame for inspection only."""
    try:
        if filename.endswith((".xlsx", ".xlsm")):
            try:
                return pd.read_excel(io.BytesIO(content), engine="openpyxl", sheet_name=0, nrows=200)
            except zipfile.BadZipFile:
                return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", sep=None, engine="python", on_bad_lines="warn", nrows=200)
        elif filename.endswith(".xls"):
            return pd.read_excel(io.BytesIO(content), engine="xlrd", sheet_name=0, nrows=200)
        elif filename.endswith(".json"):
            import json
            data = json.loads(content.decode("utf-8-sig"))
            if isinstance(data, list):
                return pd.DataFrame(data[:200])
            elif isinstance(data, dict):
                for key in ["results", "data", "companies", "items", "records"]:
                    if key in data and isinstance(data[key], list):
                        return pd.DataFrame(data[key][:200])
                return pd.DataFrame([data])
            return None
        else:
            try:
                return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", on_bad_lines="warn", nrows=200)
            except UnicodeDecodeError:
                return pd.read_csv(io.BytesIO(content), encoding="latin1", on_bad_lines="warn", nrows=200)
    except Exception:
        return None


def _make_result(
    effective_mode: str,
    routing_decision: str,
    routing_reason: str,
    dataset_type: str = "UNKNOWN",
    person_headers: Optional[List[str]] = None,
    company_headers: Optional[List[str]] = None,
    profiles: Optional[Dict] = None,
    raw_headers: Optional[List[str]] = None,
    sample_row_count: int = 0,
    alpha_columns: int = 0,
    numeric_columns: int = 0,
    company_token_ratio: float = 0.0,
    classifier_label: Optional[str] = None,
    classifier_confidence: Optional[float] = None,
    fallback_used: bool = True,
    abstained: bool = False,
    abstain_reason: Optional[str] = None,
    heuristic_result: Optional[str] = None,
) -> Dict:
    """Build structured routing result."""
    result = {
        "effective_mode": effective_mode,
        "routing_decision": routing_decision,
        "routing_reason": routing_reason,
        "dataset_type": dataset_type,
        "sampled_headers": raw_headers or [],
        "person_headers_detected": person_headers or [],
        "company_headers_detected": company_headers or [],
        "sampled_profiles": {k: v for k, v in (profiles or {}).items() if k in (raw_headers or [])[:10]} if profiles else {},
        "sample_row_count": sample_row_count,
        "alpha_columns": alpha_columns,
        "numeric_columns": numeric_columns,
        "company_token_ratio": company_token_ratio,
        "fallback_used": fallback_used,
        "abstained": abstained,
    }
    if abstain_reason is not None:
        result["abstain_reason"] = abstain_reason
    if heuristic_result is not None:
        result["heuristic_result"] = heuristic_result
    if classifier_label is not None:
        result["classifier_label"] = classifier_label
        result["classifier_confidence"] = classifier_confidence
    return result
