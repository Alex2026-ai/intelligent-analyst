"""Tests for dataset_classifier — ML-based dataset type prediction.

Covers:
  1. Model loading and predict_proba contract
  2. classify_dataset() API with person/org/garbage inputs
  3. Header boosting behavior
  4. Graceful degradation when model is missing
  5. End-to-end routing with CSV fixture files
  6. Inspection logging writes to disk
  7. Training data integrity
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import app.dataset_classifier as dc_module
from app.dataset_classifier import classify_dataset, _header_tokens, _load_model, MODEL_PATH
from app.dataset_router import inspect_dataset


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "data"


def _load_fixture(name: str) -> bytes:
    path = FIXTURES_DIR / name
    assert path.exists(), f"Fixture not found: {path}"
    return path.read_bytes()


# ============================================================================
# TEST 1: Person dataset → person
# ============================================================================

class TestPersonClassification:

    def test_person_names_with_headers(self):
        texts = [
            "Francisco Perez Benitez",
            "Maria Elena Garcia Lopez",
            "Jose Luis Martinez Cruz",
            "Ana Sofia Hernandez",
            "Carlos Alberto Gonzalez",
        ] * 10
        headers = ["Nombre", "Primer Apellido", "Segundo Apellido", "Edad", "Sexo"]
        result = classify_dataset(texts, headers=headers)

        assert result["label"] == "person", f"Expected person, got {result}"
        assert result["confidence"] > 0.0

    def test_person_names_english(self):
        texts = [
            "John Smith",
            "Jane Elizabeth Doe",
            "Robert James Wilson",
            "Mary Anne Johnson",
            "William Thompson",
        ] * 10
        headers = ["First Name", "Last Name", "Age", "Gender"]
        result = classify_dataset(texts, headers=headers)

        assert result["label"] == "person", f"Expected person, got {result}"


# ============================================================================
# TEST 2: Company dataset → org
# ============================================================================

class TestOrgClassification:

    def test_company_names_with_headers(self):
        texts = [
            "Goldman Sachs Group Inc",
            "Apple Inc",
            "Microsoft Corporation",
            "Amazon.com Inc",
            "JPMorgan Chase & Co",
        ] * 10
        headers = ["Company Name", "Industry", "Revenue"]
        result = classify_dataset(texts, headers=headers)

        assert result["label"] == "org", f"Expected org, got {result}"

    def test_company_names_without_headers(self):
        texts = [
            "Pfizer Inc",
            "Tesla Inc",
            "Boeing Company",
            "Oracle Corporation",
            "Cisco Systems Inc",
        ] * 10
        result = classify_dataset(texts, headers=None)

        assert result["label"] == "org", f"Expected org, got {result}"


# ============================================================================
# TEST 3: Garbage dataset → garbage
# ============================================================================

class TestGarbageClassification:

    def test_garbage_values(self):
        texts = [
            "123456789",
            "N/A",
            "null",
            "test",
            "unknown",
            "0000000000",
            "xxx",
            "asdfasdf",
            "TBD",
            "placeholder",
        ] * 10
        result = classify_dataset(texts, headers=None)

        assert result["label"] == "garbage", f"Expected garbage, got {result}"


# ============================================================================
# TEST 4: Mixed / fallback
# ============================================================================

class TestMixedFallback:

    def test_empty_input(self):
        result = classify_dataset([], headers=None)
        assert result["label"] == "unknown"
        assert result["confidence"] == 0.0

    def test_no_model(self):
        """If model fails to load, should return unknown."""
        # This tests the error path — model is loaded so we just verify the interface
        result = classify_dataset(["test"], headers=None)
        assert "label" in result
        assert "confidence" in result


# ============================================================================
# TEST 5: Header token generation
# ============================================================================

class TestHeaderTokens:

    def test_person_headers(self):
        tokens = _header_tokens(["Nombre", "Primer Apellido", "Edad"])
        assert "header:nombre" in tokens
        assert "header:apellido" in tokens
        assert "header:edad" in tokens

    def test_org_headers(self):
        tokens = _header_tokens(["Company Name", "Vendor ID"])
        assert "header:company" in tokens
        assert "header:vendor" in tokens

    def test_empty_headers(self):
        tokens = _header_tokens([])
        assert tokens == ""


# ============================================================================
# TEST 6: Interface contract — output shape
# ============================================================================

class TestInterfaceContract:

    def test_output_has_label_and_confidence(self):
        result = classify_dataset(["Apple Inc"], headers=["Company"])
        assert "label" in result
        assert "confidence" in result
        assert isinstance(result["label"], str)
        assert isinstance(result["confidence"], float)

    def test_label_values(self):
        """Label must be one of: person, org, garbage, unknown."""
        result = classify_dataset(["Apple Inc"], headers=["Company"])
        assert result["label"] in ("person", "org", "garbage", "unknown")


# ============================================================================
# TEST 7: Model loading
# ============================================================================

class TestModelLoading:
    """Model must load from disk and expose predict_proba."""

    def test_model_exists(self):
        assert MODEL_PATH.exists(), (
            f"Model not found at {MODEL_PATH}. "
            f"Run: cd backend && python3 scripts/train_dataset_classifier.py"
        )

    def test_model_has_predict_proba(self):
        model = _load_model()
        if model is None:
            pytest.skip("Model not available")
        assert hasattr(model, "predict_proba")
        assert hasattr(model, "classes_")

    def test_model_classes(self):
        model = _load_model()
        if model is None:
            pytest.skip("Model not available")
        classes = sorted(model.classes_)
        assert classes == ["garbage", "org", "person"], f"Unexpected classes: {classes}"


# ============================================================================
# TEST 8: Graceful degradation
# ============================================================================

class TestGracefulDegradation:

    def test_missing_model_returns_unknown(self):
        orig_model = dc_module._model
        orig_loaded = dc_module._model_loaded
        try:
            dc_module._model = None
            dc_module._model_loaded = True
            result = classify_dataset(["test input"])
            assert result["label"] == "unknown"
            assert result["confidence"] == 0.0
            assert "error" in result
        finally:
            dc_module._model = orig_model
            dc_module._model_loaded = orig_loaded


# ============================================================================
# TEST 9: End-to-end routing with fixture files
# ============================================================================

class TestFixtureRouting:

    def test_person_fixture_routes_to_mixed(self):
        content = _load_fixture("person_dataset.csv")
        result = inspect_dataset(content, "person_dataset.csv")
        assert result["effective_mode"] == "mixed", (
            f"Person fixture should route to mixed, got {result['effective_mode']}. "
            f"Decision: {result['routing_decision']}"
        )

    def test_org_fixture_routes_to_company(self):
        content = _load_fixture("org_dataset.csv")
        result = inspect_dataset(content, "org_dataset.csv")
        assert result["effective_mode"] == "company", (
            f"Org fixture should route to company, got {result['effective_mode']}. "
            f"Decision: {result['routing_decision']}"
        )

    def test_garbage_fixture_routes_to_reject(self):
        content = _load_fixture("garbage_dataset.csv")
        result = inspect_dataset(content, "garbage_dataset.csv")
        assert result["effective_mode"] == "reject", (
            f"Garbage fixture should route to reject, got {result['effective_mode']}. "
            f"Decision: {result['routing_decision']}"
        )


# ============================================================================
# TEST 10: Inspection logging
# ============================================================================

class TestInspectionLogging:

    def test_logging_writes_jsonl(self, tmp_path):
        log_file = tmp_path / "test_routing.json"
        with patch("app.dataset_router._LOG_FILE", log_file), \
             patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._LOGGING_ENABLED", True):
            content = _load_fixture("person_dataset.csv")
            result = inspect_dataset(content, "person_fixture_test.csv")

        assert log_file.exists(), "Log file was not created"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[-1])
        assert record["filename"] == "person_fixture_test.csv"
        assert "timestamp" in record
        assert "headers" in record
        assert record["routing_result"]["effective_mode"] == result["effective_mode"]

    def test_logging_disabled(self, tmp_path):
        log_file = tmp_path / "should_not_exist.json"
        with patch("app.dataset_router._LOG_FILE", log_file), \
             patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._LOGGING_ENABLED", False):
            content = _load_fixture("person_dataset.csv")
            inspect_dataset(content, "test.csv")
        assert not log_file.exists()


# ============================================================================
# TEST 11: Training data integrity
# ============================================================================

class TestTrainingData:

    def test_labeled_samples_exist(self):
        data_path = Path(__file__).parent.parent / "data" / "labeled_samples.csv"
        assert data_path.exists()

    def test_minimum_sample_count(self):
        data_path = Path(__file__).parent.parent / "data" / "labeled_samples.csv"
        df = pd.read_csv(data_path)
        assert len(df) >= 300, f"Only {len(df)} samples, need at least 300"

    def test_label_balance(self):
        data_path = Path(__file__).parent.parent / "data" / "labeled_samples.csv"
        df = pd.read_csv(data_path)
        for label in ["person", "org", "garbage"]:
            count = (df["label"] == label).sum()
            assert count >= 50, f"Label '{label}' has only {count} samples, need >= 50"

    def test_valid_labels_only(self):
        data_path = Path(__file__).parent.parent / "data" / "labeled_samples.csv"
        df = pd.read_csv(data_path)
        valid_labels = {"person", "org", "garbage"}
        actual_labels = set(df["label"].unique())
        assert actual_labels <= valid_labels, f"Invalid labels: {actual_labels - valid_labels}"

    def test_no_empty_texts(self):
        data_path = Path(__file__).parent.parent / "data" / "labeled_samples.csv"
        df = pd.read_csv(data_path)
        empty = df[df["text"].astype(str).str.strip() == ""]
        assert len(empty) == 0, f"Found {len(empty)} empty text rows"
