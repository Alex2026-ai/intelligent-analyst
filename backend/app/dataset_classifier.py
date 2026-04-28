"""
Dataset Classifier — Lightweight ML classifier for dataset type prediction.

ARCHITECTURE CONSTRAINTS:
  - This module is ISOLATED. It must NOT import or modify:
    resolver, waterfall, sanitize pipeline, attest pipeline, or storage.
  - Returns ONLY: { label: str, confidence: float }
  - The ROUTER decides pipeline behavior based on this output.
  - If classifier fails or confidence < threshold → router falls back to heuristics.

Model: TF-IDF (max_features=5000, ngram_range=(1,2)) + LogisticRegression (multinomial)
Labels: person, org, garbage
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np

# ============================================================================
# CONSTANTS
# ============================================================================

MODEL_PATH = Path(__file__).parent.parent / "models" / "entity_classifier.pkl"

PERSON_HEADER_TOKENS = {
    "nombre", "apellido", "first", "last", "edad", "age",
    "sexo", "gender", "id", "carne", "employee", "staff",
    "surname", "given", "dob", "nationality", "person",
}

ORG_HEADER_TOKENS = {
    "company", "corp", "inc", "empresa", "organization", "legal",
    "imo", "vessel", "vendor", "supplier", "entity", "account",
    "business", "firm", "subsidiary", "trading",
}


# ============================================================================
# MODEL LOADING
# ============================================================================

_model = None
_model_loaded = False


def _load_model():
    """Load the trained model from disk. Returns None if unavailable."""
    global _model, _model_loaded
    if _model_loaded:
        return _model
    _model_loaded = True
    try:
        if MODEL_PATH.exists():
            _model = joblib.load(MODEL_PATH)
            print(f"[dataset_classifier] Model loaded from {MODEL_PATH}", flush=True)
        else:
            print(f"[dataset_classifier] No model found at {MODEL_PATH}", flush=True)
    except Exception as e:
        print(f"[dataset_classifier] Failed to load model: {e}", flush=True)
        _model = None
    return _model


# ============================================================================
# HEADER FEATURE EXTRACTION
# ============================================================================

def _header_tokens(headers: List[str]) -> str:
    """Convert column headers into boost tokens for classification."""
    tokens = []
    for h in headers:
        h_lower = h.lower().strip()
        for token in PERSON_HEADER_TOKENS:
            if token in h_lower:
                tokens.append(f"header:{token}")
        for token in ORG_HEADER_TOKENS:
            if token in h_lower:
                tokens.append(f"header:{token}")
    return " ".join(tokens)


# ============================================================================
# PUBLIC API — Single entry point
# ============================================================================

def classify_dataset(
    sample_texts: List[str],
    headers: Optional[List[str]] = None,
) -> Dict:
    """
    Classify a dataset based on sample row texts and optional headers.

    Args:
        sample_texts: List of text values sampled from the dataset rows.
        headers: Optional list of column header names for feature boosting.

    Returns:
        { "label": "person" | "org" | "garbage", "confidence": float }

    If the model is unavailable or fails, returns:
        { "label": "unknown", "confidence": 0.0, "error": "..." }
    """
    model = _load_model()
    if model is None:
        return {"label": "unknown", "confidence": 0.0, "error": "model_not_loaded"}

    if not sample_texts:
        return {"label": "unknown", "confidence": 0.0, "error": "no_samples"}

    try:
        # Build header boost string
        header_boost = _header_tokens(headers) if headers else ""

        # Prepare texts: each sample gets header tokens prepended
        prepared = []
        for text in sample_texts:
            t = str(text).strip()
            if t and t.lower() not in ("nan", "none", ""):
                entry = f"{header_boost} {t}" if header_boost else t
                prepared.append(entry)

        if not prepared:
            return {"label": "unknown", "confidence": 0.0, "error": "no_valid_samples"}

        # Predict
        probabilities = model.predict_proba(prepared)
        classes = model.classes_

        # Aggregate: average probabilities across all samples
        avg_proba = np.mean(probabilities, axis=0)
        best_idx = np.argmax(avg_proba)
        label = classes[best_idx]
        confidence = float(avg_proba[best_idx])

        return {
            "label": label,
            "confidence": round(confidence, 4),
        }

    except Exception as e:
        return {"label": "unknown", "confidence": 0.0, "error": str(e)}
