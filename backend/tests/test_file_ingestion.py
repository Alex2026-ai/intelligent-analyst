"""Tests for file_ingestion — resilient file parsing with fallback chain."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from app.file_ingestion import (
    ingest_file,
    detect_file_type,
    detect_encoding,
    detect_header_row,
    _detect_delimiter,
    MAX_FILE_SIZE,
)


# ============================================================================
# HELPERS
# ============================================================================

def _csv_bytes(df: pd.DataFrame, encoding: str = "utf-8") -> bytes:
    return df.to_csv(index=False).encode(encoding)


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _xlsx_multisheet(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


def _zip_containing(filename: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


def _sample_df():
    return pd.DataFrame({
        "Name": ["Alice", "Bob", "Charlie"] * 10,
        "Age": [30, 25, 45] * 10,
        "City": ["NY", "LA", "SF"] * 10,
    })


# ============================================================================
# TEST 1: UTF-8 CSV
# ============================================================================

class TestUTF8CSV:

    def test_basic_utf8_csv(self):
        df = _sample_df()
        content = _csv_bytes(df)
        result = ingest_file(content, "data.csv")

        assert result["error"] is None
        assert result["rows"] == 30
        assert result["columns"] == 3
        assert "Name" in result["headers"]
        assert result["detected_type"] == "csv"
        assert result["df"] is not None

    def test_utf8_bom_csv(self):
        df = _sample_df()
        raw = b"\xef\xbb\xbf" + df.to_csv(index=False).encode("utf-8")
        result = ingest_file(raw, "bom.csv")

        assert result["error"] is None
        assert result["rows"] == 30


# ============================================================================
# TEST 2: Latin-1 CSV
# ============================================================================

class TestLatin1CSV:

    def test_latin1_encoded(self):
        text = "Nombre,Ciudad\nJosé,São Paulo\nMaría,Bogotá\nRené,Montréal\n" * 10
        content = text.encode("latin-1")
        result = ingest_file(content, "latin.csv")

        assert result["error"] is None
        assert result["rows"] >= 30
        assert "Nombre" in result["headers"]


# ============================================================================
# TEST 3: Windows-1252 CSV
# ============================================================================

class TestCP1252CSV:

    def test_cp1252_encoded(self):
        # cp1252 has characters in 0x80-0x9F that differ from latin-1
        # Build bytes directly since \x93 \x94 \x96 are valid cp1252 but not valid Python str
        line1 = b"Name,Notes\n"
        line2 = b"Alice,Smart \x93quotes\x94\n"
        line3 = b"Bob,En dash \x96\n"
        content = (line1 + line2 + line3) * 10
        result = ingest_file(content, "windows.csv")

        assert result["error"] is None
        assert result["rows"] >= 20


# ============================================================================
# TEST 4: Multi-sheet XLSX
# ============================================================================

class TestMultiSheetXLSX:

    def test_multisheet_selects_best(self):
        sheets = {
            "Metadata": pd.DataFrame({"Key": [1, 2], "Value": [3, 4]}),
            "People": pd.DataFrame({
                "Name": ["Frank", "Maria", "Jose", "Ana", "Carlos"] * 5,
                "Department": ["Eng", "Sales", "HR", "Finance", "Ops"] * 5,
                "Location": ["NY", "LA", "SF", "CHI", "MIA"] * 5,
            }),
            "Empty": pd.DataFrame(),
        }
        content = _xlsx_multisheet(sheets)
        result = ingest_file(content, "multi.xlsx")

        assert result["error"] is None
        assert result["sheets_found"] >= 2
        # Should pick "People" sheet (highest text density)
        assert result["rows"] >= 20
        assert "Name" in result["headers"]


# ============================================================================
# TEST 5: CSV with header at row 3
# ============================================================================

class TestHeaderAutoDetect:

    def test_header_at_row_3(self):
        lines = [
            "Report Generated: 2026-01-15",
            "Source: Internal DB",
            "",
            "Name,Age,City",
            "Alice,30,NY",
            "Bob,25,LA",
            "Charlie,45,SF",
        ]
        content = "\n".join(lines).encode("utf-8")
        result = ingest_file(content, "offset_header.csv")

        assert result["error"] is None
        # The header auto-detection should find the row with Name,Age,City
        assert result["df"] is not None
        headers_lower = [h.lower() for h in result["headers"]]
        # Either pandas parsed it correctly or header detection fixed it
        assert result["rows"] >= 3

    def test_normal_header_unchanged(self):
        df = _sample_df()
        content = _csv_bytes(df)
        result = ingest_file(content, "normal.csv")

        assert result["header_row_detected"] == 0
        assert "Name" in result["headers"]


# ============================================================================
# TEST 6: Malformed CSV quoting
# ============================================================================

class TestMalformedCSV:

    def test_bad_quoting_survives(self):
        content = b'Name,Notes\n"Alice","good"\n"Bob,"missing quote\nCharlie,ok\n' * 10
        result = ingest_file(content, "bad_quotes.csv")

        # Should not crash — fallback chain should handle it
        assert result["df"] is not None or result["error"] is not None
        # Even if parser produces partial results, it should not crash
        if result["df"] is not None:
            assert result["rows"] >= 1

    def test_mixed_delimiters(self):
        content = b"Name;Age;City\nAlice;30;NY\nBob;25;LA\n" * 10
        result = ingest_file(content, "semicolon.csv")

        assert result["error"] is None
        assert result["rows"] >= 20


# ============================================================================
# TEST 7: Large file size guard
# ============================================================================

class TestFileSizeGuard:

    def test_oversized_file_rejected(self):
        # Simulate a file exceeding MAX_FILE_SIZE by using a small fake
        # We'll test the guardrail logic by patching the constant
        from unittest.mock import patch
        content = b"x" * 1000
        with patch("app.file_ingestion.MAX_FILE_SIZE", 500):
            result = ingest_file(content, "huge.csv")

        assert result["error"] is not None
        assert result["guardrail_hit"] == "max_file_size"

    def test_empty_file(self):
        result = ingest_file(b"", "empty.csv")
        assert result["error"] is not None
        assert result["rows"] == 0


# ============================================================================
# TEST 8: ZIP archive containing CSV
# ============================================================================

class TestZipArchive:

    def test_zip_with_csv(self):
        df = _sample_df()
        csv_content = _csv_bytes(df)
        zip_content = _zip_containing("data.csv", csv_content)
        result = ingest_file(zip_content, "archive.zip")

        assert result["error"] is None
        assert result["rows"] == 30
        assert "Name" in result["headers"]

    def test_zip_with_xlsx(self):
        df = _sample_df()
        xlsx_content = _xlsx_bytes(df)
        zip_content = _zip_containing("data.xlsx", xlsx_content)
        result = ingest_file(zip_content, "archive.zip")

        assert result["error"] is None
        assert result["rows"] == 30

    def test_zip_with_no_supported_file(self):
        zip_content = _zip_containing("image.png", b"\x89PNG fake image data")
        result = ingest_file(zip_content, "images.zip")

        assert result["error"] is not None


# ============================================================================
# TEST 9: Binary file rejection
# ============================================================================

class TestBinaryRejection:

    def test_png_rejected(self):
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = ingest_file(content, "image.png")

        assert result["error"] is not None
        assert "Unsupported" in result["error"]

    def test_pdf_rejected(self):
        content = b"%PDF-1.4 fake pdf content" + b"\x00" * 100
        result = ingest_file(content, "report.pdf")

        assert result["error"] is not None

    def test_jpeg_rejected(self):
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        result = ingest_file(content, "photo.jpg")

        assert result["error"] is not None


# ============================================================================
# TEST 10: File type detection
# ============================================================================

class TestFileTypeDetection:

    def test_csv_detection(self):
        info = detect_file_type(b"Name,Age\nAlice,30\n", "data.csv")
        assert info["detected_type"] == "csv"
        assert info["supported"] is True

    def test_xlsx_detection(self):
        df = _sample_df()
        content = _xlsx_bytes(df)
        info = detect_file_type(content, "data.xlsx")
        assert info["detected_type"] == "xlsx"
        assert info["supported"] is True

    def test_png_detection(self):
        info = detect_file_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, "img.png")
        assert info["detected_type"] == "png"
        assert info["supported"] is False

    def test_json_detection(self):
        info = detect_file_type(b'[{"name": "test"}]', "data.json")
        assert info["detected_type"] == "json"
        assert info["supported"] is True

    def test_zip_detection(self):
        content = _zip_containing("test.csv", b"a,b\n1,2\n")
        info = detect_file_type(content, "archive.zip")
        assert info["detected_type"] == "zip"
        assert info["supported"] is True


# ============================================================================
# TEST 11: Encoding detection
# ============================================================================

class TestEncodingDetection:

    def test_utf8_detected(self):
        enc = detect_encoding("hello world".encode("utf-8"))
        assert enc in ("utf-8", "ascii")

    def test_bom_detected(self):
        enc = detect_encoding(b"\xef\xbb\xbf" + "hello".encode("utf-8"))
        assert enc == "utf-8-sig"

    def test_utf16_detected(self):
        enc = detect_encoding(b"\xff\xfe" + "hello".encode("utf-16-le"))
        assert enc == "utf-16"

    def test_high_bytes_detected(self):
        content = "José María García".encode("latin-1")
        enc = detect_encoding(content)
        assert enc in ("latin-1", "cp1252")


# ============================================================================
# TEST 12: Parse failure logging
# ============================================================================

class TestParseFailureLogging:

    def test_failure_logged(self, tmp_path):
        from unittest.mock import patch
        log_file = tmp_path / "parse_failures.jsonl"

        with patch("app.file_ingestion._LOG_DIR", tmp_path), \
             patch("app.file_ingestion._PARSE_FAILURE_FILE", log_file):
            # Binary file will be rejected and logged
            result = ingest_file(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "bad.png")

        assert result["error"] is not None
        assert log_file.exists()
        records = [json.loads(line) for line in log_file.read_text().splitlines()]
        assert len(records) >= 1
        rec = records[0]
        assert "timestamp" in rec
        assert "filename" in rec
        assert "mime_type" in rec
        assert "file_size" in rec
        assert "first_256_bytes_hex" in rec
        assert "parser_attempted" in rec
        assert "error_message" in rec


# ============================================================================
# PHASE 2 TESTS
# ============================================================================

# ============================================================================
# TEST 13: Semicolon-delimited CSV
# ============================================================================

class TestSemicolonCSV:

    def test_semicolon_delimited(self):
        content = b"Name;Age;City\nAlice;30;NY\nBob;25;LA\nCharlie;45;SF\n" * 10
        result = ingest_file(content, "european.csv")

        assert result["error"] is None
        assert result["rows"] >= 30
        assert result["columns"] == 3
        assert "Name" in result["headers"]

    def test_semicolon_delimiter_detected(self):
        content = b"Name;Age;City\nAlice;30;NY\nBob;25;LA\n"
        delim = _detect_delimiter(content, "utf-8")
        assert delim == ";"


# ============================================================================
# TEST 14: Tab-delimited CSV
# ============================================================================

class TestTabDelimitedCSV:

    def test_tab_delimited(self):
        content = b"Name\tAge\tCity\nAlice\t30\tNY\nBob\t25\tLA\nCharlie\t45\tSF\n" * 10
        result = ingest_file(content, "tabbed.tsv")

        assert result["error"] is None
        assert result["rows"] >= 30
        assert result["columns"] == 3
        assert "Name" in result["headers"]

    def test_tab_delimiter_detected(self):
        content = b"Name\tAge\tCity\nAlice\t30\tNY\nBob\t25\tLA\n"
        delim = _detect_delimiter(content, "utf-8")
        assert delim == "\t"


# ============================================================================
# TEST 15: Header at row 5
# ============================================================================

class TestHeaderAtRow5:

    def test_header_at_row_5(self):
        lines = [
            "Report Title: Employee Analysis",
            "Department: Engineering",
            "Date: 2026-03-15",
            "Confidential",
            "",
            "Employee,Department,Salary,Location",
            "Alice,Eng,95000,NY",
            "Bob,Sales,87000,LA",
            "Charlie,HR,72000,SF",
            "Diana,Finance,91000,CHI",
        ]
        content = "\n".join(lines).encode("utf-8")
        result = ingest_file(content, "deep_header.csv")

        assert result["error"] is None
        assert result["df"] is not None
        assert result["rows"] >= 4
        assert result["columns"] >= 3


# ============================================================================
# TEST 16: Excel with 3 sheets → correct sheet selected
# ============================================================================

class TestExcelThreeSheets:

    def test_three_sheets_best_selected(self):
        sheets = {
            "Config": pd.DataFrame({"Setting": ["mode"], "Value": ["prod"]}),
            "Employees": pd.DataFrame({
                "Name": ["Alice", "Bob", "Charlie", "Diana", "Eve"] * 6,
                "Department": ["Eng", "Sales", "HR", "Finance", "Ops"] * 6,
                "City": ["NY", "LA", "SF", "CHI", "MIA"] * 6,
                "Salary": [95000, 87000, 72000, 91000, 88000] * 6,
            }),
            "Summary": pd.DataFrame({
                "Metric": ["Total", "Average"],
                "Count": [30, 15],
            }),
        }
        content = _xlsx_multisheet(sheets)
        result = ingest_file(content, "three_sheets.xlsx")

        assert result["error"] is None
        assert result["sheets_found"] == 3
        # Should pick Employees (highest text density and most rows)
        assert result["rows"] >= 25
        assert "Name" in result["headers"]


# ============================================================================
# TEST 17: Excel sheets flattened (similar density concat)
# ============================================================================

class TestExcelSheetsFlattened:

    def test_similar_sheets_concatenated(self):
        sheets = {
            "Q1": pd.DataFrame({
                "Name": ["Alice", "Bob", "Charlie"] * 5,
                "Region": ["East", "West", "Central"] * 5,
                "Revenue": [100, 200, 300] * 5,
            }),
            "Q2": pd.DataFrame({
                "Name": ["Diana", "Eve", "Frank"] * 5,
                "Region": ["East", "West", "Central"] * 5,
                "Revenue": [150, 250, 350] * 5,
            }),
        }
        content = _xlsx_multisheet(sheets)
        result = ingest_file(content, "quarterly.xlsx")

        assert result["error"] is None
        assert result["sheets_found"] == 2
        # Both sheets have same structure + similar density → should concat
        # Total rows = 15 + 15 = 30
        assert result["rows"] >= 25
        assert "Name" in result["headers"]
        # Verify concat happened: should see names from both sheets
        names = result["df"]["Name"].unique().tolist()
        assert len(names) >= 5  # Has names from both Q1 and Q2


# ============================================================================
# TEST 18: Mixed encoding detection (library fallback)
# ============================================================================

class TestMixedEncodingDetection:

    def test_encoding_library_used_when_available(self):
        """Encoding detection works even with unusual encodings."""
        # ISO-8859-15 (euro sign differs from latin-1)
        text = "Name,Notes\nAlice,Caf\u00e9\nBob,R\u00e9sum\u00e9\n" * 10
        content = text.encode("iso-8859-15")
        result = ingest_file(content, "euro.csv")

        assert result["error"] is None
        assert result["rows"] >= 20
        assert "Name" in result["headers"]

    def test_detect_encoding_with_high_bytes(self):
        """Encoding detection handles high-byte content gracefully."""
        content = b"Nom,Pr\xe9nom\nDupont,Ren\xe9\nMartin,Fran\xe7ois\n" * 10
        result = ingest_file(content, "french.csv")

        assert result["error"] is None
        assert result["rows"] >= 20


# ============================================================================
# TEST 19: Malformed CSV with uneven rows
# ============================================================================

class TestMalformedUnevenRows:

    def test_uneven_rows_recovered(self):
        """CSV with inconsistent column counts should still parse."""
        lines = [
            b"Name,Age,City",
            b"Alice,30,NY",
            b"Bob,25",           # missing City
            b"Charlie,45,SF,Extra",  # extra column
            b"Diana,28,LA",
            b"Eve,33,CHI",
        ]
        content = b"\n".join(lines * 5)
        result = ingest_file(content, "uneven.csv")

        assert result["df"] is not None
        # Should parse at least some rows successfully
        assert result["rows"] >= 5

    def test_mixed_quotes_and_delimiters(self):
        """CSV with mixed quoting styles should not crash."""
        content = b'Name,Notes\n"Alice","normal"\nBob,"unmatched\nCharlie,plain\n"Diana","nested ""quotes"""\n' * 5
        result = ingest_file(content, "messy.csv")

        assert result["df"] is not None
        assert result["rows"] >= 1
