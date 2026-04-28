#!/usr/bin/env python3
"""
Routing Benchmark — measures router accuracy against labeled datasets.

Usage:
    cd backend
    PYTHONPATH=. python3 benchmarks/run_routing_benchmark.py

Loads CSVs from benchmarks/routing/datasets/, runs inspect_dataset(),
compares against expected_results.json, outputs confusion matrix + JSON report.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from app.dataset_router import inspect_dataset

BENCHMARK_DIR = Path(__file__).parent / "routing"
DATASETS_DIR = BENCHMARK_DIR / "datasets"
EXPECTED_FILE = BENCHMARK_DIR / "expected_results.json"
RESULTS_DIR = BENCHMARK_DIR / "results"


def load_expected() -> Dict:
    with open(EXPECTED_FILE, "r") as f:
        return json.load(f)


def run_benchmark() -> Dict:
    expected = load_expected()
    results = []
    confusion = defaultdict(lambda: defaultdict(int))
    correct = 0
    total = 0
    errors = []

    for filename, expect in sorted(expected.items()):
        filepath = DATASETS_DIR / filename
        if not filepath.exists():
            errors.append({"file": filename, "error": "file_not_found"})
            continue

        content = filepath.read_bytes()
        t0 = time.monotonic()
        actual = inspect_dataset(content, filename)
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

        actual_mode = actual["effective_mode"]
        expected_mode = expect["effective_mode"]

        match = actual_mode == expected_mode
        if match:
            correct += 1
        total += 1

        confusion[expected_mode][actual_mode] += 1

        results.append({
            "file": filename,
            "category": expect.get("category", "unknown"),
            "expected_mode": expected_mode,
            "actual_mode": actual_mode,
            "match": match,
            "routing_decision": actual["routing_decision"],
            "classifier_label": actual.get("classifier_label"),
            "classifier_confidence": actual.get("classifier_confidence"),
            "fallback_used": actual.get("fallback_used"),
            "elapsed_ms": elapsed_ms,
        })

    accuracy = correct / max(total, 1)

    # Build confusion matrix as nested dict
    all_modes = sorted(set(
        list(confusion.keys()) +
        [m for row in confusion.values() for m in row.keys()]
    ))
    matrix = {}
    for expected_mode in all_modes:
        matrix[expected_mode] = {}
        for actual_mode in all_modes:
            matrix[expected_mode][actual_mode] = confusion[expected_mode][actual_mode]

    report = {
        "total_datasets": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "confusion_matrix": matrix,
        "results": results,
        "errors": errors,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    return report


def print_report(report: Dict) -> None:
    print("=" * 60)
    print("ROUTING BENCHMARK REPORT")
    print("=" * 60)
    print(f"  Datasets:  {report['total_datasets']}")
    print(f"  Correct:   {report['correct']}")
    print(f"  Accuracy:  {report['accuracy']:.1%}")
    print()

    # Confusion matrix
    matrix = report["confusion_matrix"]
    modes = sorted(matrix.keys())
    if modes:
        print("  Confusion Matrix (rows=expected, cols=actual):")
        header = "          " + "  ".join(f"{m:>8}" for m in modes)
        print(header)
        for row_mode in modes:
            cells = "  ".join(f"{matrix[row_mode].get(col, 0):>8}" for col in modes)
            print(f"  {row_mode:>8}  {cells}")
        print()

    # Per-file results
    print("  Per-file results:")
    for r in report["results"]:
        status = "PASS" if r["match"] else "FAIL"
        clf_info = ""
        if r.get("classifier_label"):
            clf_info = f" clf={r['classifier_label']}@{r['classifier_confidence']:.2f}"
        fb = " (fallback)" if r.get("fallback_used") else ""
        print(f"    [{status}] {r['file']:<40} expected={r['expected_mode']:<8} actual={r['actual_mode']:<8}{clf_info}{fb}")

    if report["errors"]:
        print(f"\n  Errors: {len(report['errors'])}")
        for e in report["errors"]:
            print(f"    {e['file']}: {e['error']}")

    print()
    print(f"  Overall: {'PASS' if report['accuracy'] >= 0.80 else 'FAIL'} ({report['accuracy']:.1%} accuracy)")
    print()


def main() -> int:
    report = run_benchmark()
    print_report(report)

    # Save JSON report
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = RESULTS_DIR / f"benchmark_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to: {report_file}")

    return 0 if report["accuracy"] >= 0.80 else 1


if __name__ == "__main__":
    sys.exit(main())
