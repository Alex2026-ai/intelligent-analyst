"""Tests for confidence-aware abstention policy in dataset_router."""
from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from app.dataset_router import inspect_dataset, reset_routing_metrics


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _person_df():
    return pd.DataFrame({
        "Nombre": ["Frank", "Maria", "Jose"] * 10,
        "Primer Apellido": ["Garcia", "Lopez", "Martinez"] * 10,
        "Edad": [35, 28, 42] * 10,
    })


def _company_df():
    return pd.DataFrame({
        "Company Name": ["Apple Inc", "Google LLC", "Microsoft Corp"] * 20,
        "Industry": ["Tech", "Tech", "Tech"] * 20,
        "Revenue": [394000, 283000, 198000] * 20,
    })


# ============================================================================
# TEST 1: confidence >= 0.80 → classifier allowed
# ============================================================================

class TestHighConfidence:

    def test_classifier_wins_at_high_confidence(self):
        """Classifier at 0.85 confidence must be allowed to route."""
        content = _csv_bytes(_person_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "person", "confidence": 0.85}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["fallback_used"] is False
        assert result["abstained"] is False
        assert result["routing_decision"] == "ml_classifier_person"
        assert result["effective_mode"] == "mixed"

    def test_high_confidence_org(self):
        """Org classifier at 0.90 must route to company."""
        content = _csv_bytes(_company_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "org", "confidence": 0.90}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["fallback_used"] is False
        assert result["abstained"] is False
        assert result["effective_mode"] == "company"


# ============================================================================
# TEST 2: confidence < 0.50 → deterministic fallback always
# ============================================================================

class TestLowConfidence:

    def test_low_confidence_uses_heuristic(self):
        """Classifier at 0.30 must always fall back to heuristics."""
        content = _csv_bytes(_person_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "garbage", "confidence": 0.30}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["fallback_used"] is True
        assert result["effective_mode"] == "mixed"
        assert result["routing_decision"] == "person_dataset"

    def test_low_confidence_even_if_correct_label(self):
        """Even if classifier label matches heuristic, low confidence → fallback."""
        content = _csv_bytes(_person_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "person", "confidence": 0.40}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["fallback_used"] is True
        assert result["routing_decision"] == "person_dataset"


# ============================================================================
# TEST 3: mid-confidence + agreement → classifier allowed
# ============================================================================

class TestMidConfidenceAgreement:

    def test_mid_confidence_agreement_allows_classifier(self):
        """Classifier at 0.65 agreeing with heuristic → classifier wins."""
        content = _csv_bytes(_company_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            # Heuristic will say "company" (Company Name header), classifier also says "org" → agreement
            mock_clf.return_value = {"label": "org", "confidence": 0.65}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["fallback_used"] is False
        assert result["abstained"] is False
        assert result["effective_mode"] == "company"
        assert result["routing_decision"] == "ml_classifier_org"

    def test_mid_confidence_person_agreement(self):
        """Classifier at 0.55 agreeing with person heuristic → classifier wins."""
        content = _csv_bytes(_person_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "person", "confidence": 0.55}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["fallback_used"] is False
        assert result["abstained"] is False
        assert result["effective_mode"] == "mixed"


# ============================================================================
# TEST 4: mid-confidence + disagreement → abstain + fallback
# ============================================================================

class TestMidConfidenceDisagreement:

    def test_mid_confidence_disagreement_abstains(self):
        """Classifier at 0.60 disagreeing with heuristic → abstain."""
        content = _csv_bytes(_person_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            # Heuristic will say "person", classifier says "org" → disagreement
            mock_clf.return_value = {"label": "org", "confidence": 0.60}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["fallback_used"] is True
        assert result["abstained"] is True
        assert "abstain_reason" in result
        assert "disagreement" in result["abstain_reason"].lower()
        assert result["effective_mode"] == "mixed"
        assert result["routing_decision"] == "person_dataset"
        assert result["heuristic_result"] == "person"

    def test_mid_confidence_garbage_on_person_abstains(self):
        """Classifier says garbage@0.55 on person data → abstain, use heuristic."""
        content = _csv_bytes(_person_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "garbage", "confidence": 0.55}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert result["abstained"] is True
        assert result["fallback_used"] is True
        assert result["effective_mode"] == "mixed"
        assert result["effective_mode"] != "reject"


# ============================================================================
# TEST 5: abstention log written
# ============================================================================

class TestAbstentionLogging:

    def test_abstention_log_written(self, tmp_path):
        """Abstention case must write to routing_abstentions.jsonl."""
        content = _csv_bytes(_person_df())
        abstention_file = tmp_path / "routing_abstentions.jsonl"

        with patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._ABSTENTION_FILE", abstention_file), \
             patch("app.dataset_router._LOGGING_ENABLED", True), \
             patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "org", "confidence": 0.60}
            reset_routing_metrics()
            inspect_dataset(content, "test.csv")

        assert abstention_file.exists(), "Abstention log not written"
        records = [json.loads(line) for line in abstention_file.read_text().splitlines()]
        assert len(records) >= 1
        rec = records[0]
        assert rec["classifier_label"] == "org"
        assert rec["classifier_confidence"] == 0.60
        assert rec["heuristic_result"] == "person"
        assert "abstain_reason" in rec
        assert "timestamp" in rec
        assert "dataset_headers" in rec

    def test_no_abstention_log_when_not_abstaining(self, tmp_path):
        """No abstention log when classifier is simply allowed."""
        content = _csv_bytes(_company_df())
        abstention_file = tmp_path / "routing_abstentions.jsonl"

        with patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._ABSTENTION_FILE", abstention_file), \
             patch("app.dataset_router._LOGGING_ENABLED", True), \
             patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "org", "confidence": 0.85}
            reset_routing_metrics()
            inspect_dataset(content, "test.csv")

        if abstention_file.exists():
            assert abstention_file.read_text().strip() == ""


# ============================================================================
# TEST 6: metadata fields present
# ============================================================================

class TestAbstentionMetadata:

    def test_metadata_has_abstention_fields(self):
        """All routing results must include abstained and heuristic_result."""
        content = _csv_bytes(_person_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "org", "confidence": 0.60}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert "abstained" in result
        assert "abstain_reason" in result
        assert "heuristic_result" in result
        assert "classifier_label" in result
        assert "classifier_confidence" in result
        assert "fallback_used" in result
        assert isinstance(result["abstained"], bool)

    def test_non_abstained_result_has_fields(self):
        """Even non-abstained results have the abstained field."""
        content = _csv_bytes(_company_df())

        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "org", "confidence": 0.85}
            reset_routing_metrics()
            result = inspect_dataset(content, "test.csv")

        assert "abstained" in result
        assert result["abstained"] is False
        assert "heuristic_result" in result
