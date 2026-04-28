"""Tests for routing observability — disagreement logging, metrics, benchmark."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from app.dataset_router import (
    inspect_dataset,
    get_routing_metrics,
    reset_routing_metrics,
    _flush_metrics,
    _DISAGREEMENT_FILE,
    _METRICS_FILE,
    _LOG_DIR,
)


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ============================================================================
# TEST 1: Disagreement log written when classifier != heuristic
# ============================================================================

class TestDisagreementLogging:

    def test_disagreement_logged_on_mismatch(self, tmp_path):
        """When classifier says 'garbage' but heuristic says 'person', log it."""
        df = pd.DataFrame({
            "Nombre": ["Frank", "Maria", "Jose"] * 10,
            "Primer Apellido": ["Garcia", "Lopez", "Martinez"] * 10,
            "Edad": [35, 28, 42] * 10,
        })
        content = _csv_bytes(df)

        disagreement_file = tmp_path / "routing_disagreements.jsonl"

        with patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._DISAGREEMENT_FILE", disagreement_file), \
             patch("app.dataset_router._LOGGING_ENABLED", True), \
             patch("app.dataset_router.classify_dataset") as mock_clf:
            # Classifier says garbage at 0.45 (below threshold) — heuristic says person
            mock_clf.return_value = {"label": "garbage", "confidence": 0.45}
            reset_routing_metrics()
            result = inspect_dataset(content, "hr.csv")

        assert result["effective_mode"] == "mixed"
        assert result["fallback_used"] is True
        assert disagreement_file.exists(), "Disagreement log was not written"

        records = [json.loads(line) for line in disagreement_file.read_text().splitlines()]
        assert len(records) >= 1
        rec = records[0]
        assert rec["classifier_label"] == "garbage"
        assert rec["heuristic_result"] == "person"
        assert "timestamp" in rec
        assert "dataset_headers" in rec

    def test_no_disagreement_when_agree(self, tmp_path):
        """When classifier and heuristic agree, no disagreement logged."""
        df = pd.DataFrame({
            "Nombre": ["Frank", "Maria"] * 10,
            "Primer Apellido": ["Garcia", "Lopez"] * 10,
            "Edad": [35, 28] * 10,
        })
        content = _csv_bytes(df)

        disagreement_file = tmp_path / "routing_disagreements.jsonl"

        with patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._DISAGREEMENT_FILE", disagreement_file), \
             patch("app.dataset_router._LOGGING_ENABLED", True), \
             patch("app.dataset_router.classify_dataset") as mock_clf:
            # Classifier says person at 0.50 (below threshold) — heuristic also person
            mock_clf.return_value = {"label": "person", "confidence": 0.50}
            reset_routing_metrics()
            result = inspect_dataset(content, "hr.csv")

        # No disagreement file should be created (or if it exists, empty)
        if disagreement_file.exists():
            content_str = disagreement_file.read_text().strip()
            assert content_str == "", "Disagreement logged when classifier and heuristic agree"


# ============================================================================
# TEST 2: Metrics file written
# ============================================================================

class TestMetricsTracking:

    def test_metrics_accumulate(self, tmp_path):
        """Metrics accumulate across multiple routing calls."""
        reset_routing_metrics()

        df = pd.DataFrame({
            "Nombre": ["Frank", "Maria"] * 10,
            "Primer Apellido": ["Garcia", "Lopez"] * 10,
            "Edad": [35, 28] * 10,
        })
        content = _csv_bytes(df)

        with patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._LOGGING_ENABLED", True):
            for _ in range(3):
                inspect_dataset(content, "test.csv")

        metrics = get_routing_metrics()
        assert metrics["total_runs"] == 3
        assert metrics["classifier_used"] + metrics["fallback_used"] == 3
        assert metrics["avg_confidence"] >= 0.0

    def test_metrics_flush_to_disk(self, tmp_path):
        """Metrics flush to JSON file at interval."""
        reset_routing_metrics()
        metrics_file = tmp_path / "routing_metrics.json"

        df = pd.DataFrame({
            "Nombre": ["Frank"] * 5,
            "Primer Apellido": ["Garcia"] * 5,
            "Edad": [35] * 5,
        })
        content = _csv_bytes(df)

        with patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._METRICS_FILE", metrics_file), \
             patch("app.dataset_router._LOGGING_ENABLED", True), \
             patch("app.dataset_router._METRICS_FLUSH_INTERVAL", 2):
            inspect_dataset(content, "a.csv")
            assert not metrics_file.exists(), "Should not flush after 1 run"
            inspect_dataset(content, "b.csv")
            assert metrics_file.exists(), "Should flush after 2 runs (interval=2)"

        data = json.loads(metrics_file.read_text())
        assert data["total_runs"] == 2
        assert "avg_confidence" in data
        assert "confidence_histogram" in data
        assert "flushed_at" in data

    def test_confidence_histogram_buckets(self, tmp_path):
        """Confidence histogram populates correct buckets."""
        reset_routing_metrics()

        df = pd.DataFrame({
            "Company Name": ["Apple Inc", "Google LLC"] * 20,
            "Revenue": [394000, 283000] * 20,
        })
        content = _csv_bytes(df)

        with patch("app.dataset_router._LOG_DIR", tmp_path), \
             patch("app.dataset_router._LOGGING_ENABLED", True):
            inspect_dataset(content, "co.csv")

        metrics = get_routing_metrics()
        histogram = metrics["confidence_histogram"]
        total_in_buckets = sum(histogram.values())
        assert total_in_buckets == 1

    def test_reset_clears_metrics(self):
        """reset_routing_metrics zeroes everything."""
        reset_routing_metrics()
        metrics = get_routing_metrics()
        assert metrics["total_runs"] == 0
        assert metrics["classifier_used"] == 0
        assert metrics["fallback_used"] == 0
        assert metrics["avg_confidence"] == 0.0


# ============================================================================
# TEST 3: Benchmark script runs
# ============================================================================

class TestBenchmarkHarness:

    def test_benchmark_script_exists(self):
        script = Path(__file__).parent.parent / "benchmarks" / "run_routing_benchmark.py"
        assert script.exists(), f"Benchmark script not found at {script}"

    def test_benchmark_imports_and_runs(self):
        """Benchmark harness can load and execute without error."""
        import importlib.util
        script = Path(__file__).parent.parent / "benchmarks" / "run_routing_benchmark.py"
        spec = importlib.util.spec_from_file_location("benchmark", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        report = mod.run_benchmark()
        assert "total_datasets" in report
        assert "correct" in report
        assert "accuracy" in report
        assert "confusion_matrix" in report
        assert "results" in report
        assert report["total_datasets"] > 0
        assert 0.0 <= report["accuracy"] <= 1.0

    def test_benchmark_confusion_matrix_structure(self):
        """Confusion matrix is a nested dict of ints."""
        import importlib.util
        script = Path(__file__).parent.parent / "benchmarks" / "run_routing_benchmark.py"
        spec = importlib.util.spec_from_file_location("benchmark", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        report = mod.run_benchmark()
        matrix = report["confusion_matrix"]
        assert isinstance(matrix, dict)
        for row_key, row_val in matrix.items():
            assert isinstance(row_val, dict)
            for cell in row_val.values():
                assert isinstance(cell, int)
