"""Regression tests for CSV export (generate_results_csv).

Covers the NameError: 'csv' not defined bug that caused HTTP 500
on /batches/{id}/export.
"""
import csv
import io

import pytest

from app.server_enterprise_golden import generate_results_csv


FIXTURE = [
    {
        "original": "Appple Inc",
        "resolved": "Apple Inc.",
        "match_type": "FUZZY_MATCH",
        "match_id": "apple-inc",
        "confidence": 0.92,
        "layer": "L2_VECTOR",
        "decision": "RESOLVED",
        "reason": "L2 cosine similarity 0.92",
    },
    {
        "original": "google",
        "resolved": "Alphabet Inc.",
        "match_type": "PARENT_MATCH",
        "match_id": "alphabet-inc",
        "confidence": 1.0,
        "layer": "L1_PARENT",
        "decision": "RESOLVED",
        "reason": "Known alias",
    },
    {
        "original": "xyzzy corp",
        "resolved": None,
        "match_type": "NO_MATCH",
        "match_id": "",
        "confidence": 0.0,
        "layer": "L4_HUMAN",
        "decision": "UNRESOLVED",
        "reason": "No match found",
    },
]


def test_csv_export_returns_nonempty_string():
    result = generate_results_csv(FIXTURE)
    assert isinstance(result, str)
    assert len(result) > 0


def test_csv_export_header_row():
    result = generate_results_csv(FIXTURE)
    reader = csv.reader(io.StringIO(result))
    header = next(reader)
    assert header == [
        "row_index", "original", "resolved", "match_type",
        "match_id", "confidence", "layer", "decision", "reason",
    ]


def test_csv_export_row_count():
    result = generate_results_csv(FIXTURE)
    reader = csv.reader(io.StringIO(result))
    rows = list(reader)
    # 1 header + 3 data rows
    assert len(rows) == 4


def test_csv_export_data_content():
    result = generate_results_csv(FIXTURE)
    reader = csv.reader(io.StringIO(result))
    next(reader)  # skip header
    first_row = next(reader)
    assert first_row[1] == "Appple Inc"
    assert first_row[2] == "Apple Inc."
    assert first_row[6] == "L2_VECTOR"


def test_csv_export_empty_results():
    result = generate_results_csv([])
    reader = csv.reader(io.StringIO(result))
    rows = list(reader)
    # Header only, no data rows
    assert len(rows) == 1
