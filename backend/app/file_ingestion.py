"""
File Ingestion — resilient file parsing with fallback chain.

ARCHITECTURE CONSTRAINTS:
  - This module is ISOLATED. It handles raw bytes → DataFrame only.
  - Does NOT import or modify: router, classifier, waterfall, sanitize,
    attest, receipt, transparency, or evidence pack logic.
  - Fail-safe: if all parsers fail, returns raw text rows. Never crashes.

Fallback chain:
  1. pandas (csv/excel with detected format)
  2. pandas with encoding retries (latin-1, cp1252, utf-16)
  3. csv.Sniffer + csv module
  4. openpyxl / xlrd for Excel
  5. chardet/charset-normalizer decode → pandas retry
  6. raw line reader (last resort)

Phase 2 additions:
  - Robust delimiter detection (comma, semicolon, tab, pipe)
  - Header auto-detection with multi-signal scoring
  - Excel multi-sheet: text-density selection + concat when similar
  - charset-normalizer / chardet encoding fallback
  - Messy CSV recovery with skipped-row logging
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import os
import struct
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ============================================================================
# CONSTANTS
# ============================================================================

MAX_FILE_SIZE = int(os.environ.get("IA_MAX_FILE_SIZE", 100 * 1024 * 1024))  # 100MB
MAX_ROWS_MEMORY = int(os.environ.get("IA_MAX_ROWS_MEMORY", 500_000))
PARSER_TIMEOUT_SEC = int(os.environ.get("IA_PARSER_TIMEOUT", 30))
MAX_ZIP_DECOMPRESSED = 200 * 1024 * 1024  # 200MB decompression limit

_LOG_DIR = Path(os.environ.get("IA_ROUTING_LOG_DIR", Path(__file__).parent.parent / "logs"))
_PARSE_FAILURE_FILE = _LOG_DIR / "parse_failures.jsonl"

ENCODING_ATTEMPTS = ["utf-8-sig", "utf-8", "latin-1", "cp1252", "utf-16"]

# Magic bytes for file type detection
_MAGIC_SIGNATURES = {
    b"PK\x03\x04": "zip",           # ZIP / XLSX / XLSM / DOCX
    b"\xd0\xcf\x11\xe0": "xls",     # OLE2 compound (legacy .xls)
    b"\x89PNG": "png",
    b"\xff\xd8\xff": "jpeg",
    b"%PDF": "pdf",
    b"GIF8": "gif",
    b"\x1f\x8b": "gzip",
    b"BM": "bmp",
    b"\x7fELF": "elf",
}

_TEXT_EXTENSIONS = {".csv", ".tsv", ".txt", ".json", ".jsonl"}
_EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
_SUPPORTED_EXTENSIONS = _TEXT_EXTENSIONS | _EXCEL_EXTENSIONS | {".zip"}

_BINARY_REJECT = {"png", "jpeg", "pdf", "gif", "bmp", "elf", "gzip"}


# ============================================================================
# MAGIC-BYTE DETECTION
# ============================================================================

def detect_file_type(content: bytes, filename: str) -> Dict:
    """
    Detect file type via magic bytes + extension.

    Returns:
        {"mime_hint": str, "detected_type": str, "extension": str, "supported": bool}
    """
    ext = Path(filename).suffix.lower() if filename else ""

    # Check magic bytes
    detected = None
    for sig, ftype in _MAGIC_SIGNATURES.items():
        if content[:len(sig)] == sig:
            detected = ftype
            break

    # ZIP could be xlsx/xlsm — check extension
    if detected == "zip" and ext in _EXCEL_EXTENSIONS:
        detected = "xlsx"

    # If no magic match, infer from extension
    if detected is None:
        if ext in {".csv", ".tsv", ".txt"}:
            detected = "csv"
        elif ext == ".json" or ext == ".jsonl":
            detected = "json"
        elif ext in _EXCEL_EXTENSIONS:
            detected = ext.lstrip(".")
        elif ext == ".zip":
            detected = "zip"
        else:
            # Heuristic: if content looks like text, treat as csv
            try:
                sample = content[:4096]
                sample.decode("utf-8")
                detected = "csv"
            except (UnicodeDecodeError, ValueError):
                detected = "binary"

    supported = detected not in _BINARY_REJECT and detected != "binary"

    return {
        "detected_type": detected,
        "extension": ext,
        "supported": supported,
    }


# ============================================================================
# ENCODING DETECTION (with charset-normalizer / chardet fallback)
# ============================================================================

def _detect_encoding_library(content: bytes) -> Optional[str]:
    """Try charset-normalizer or chardet for encoding detection."""
    sample = content[:32768]
    # Try charset-normalizer first (preferred, pure-python)
    try:
        from charset_normalizer import from_bytes
        result = from_bytes(sample).best()
        if result is not None:
            return str(result.encoding)
    except ImportError:
        pass
    # Fallback to chardet
    try:
        import chardet
        result = chardet.detect(sample)
        if result and result.get("encoding"):
            return result["encoding"].lower()
    except ImportError:
        pass
    return None


def detect_encoding(content: bytes) -> str:
    """Detect encoding by attempting decodes, with library fallback."""
    # BOM checks
    if content[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"

    # Try each encoding on a sample
    sample = content[:8192]
    for enc in ["utf-8", "ascii"]:
        try:
            sample.decode(enc)
            return enc
        except (UnicodeDecodeError, ValueError):
            continue

    # Check for high-byte patterns common in latin-1/cp1252
    high_bytes = sum(1 for b in sample if b > 127)
    if high_bytes > 0:
        # Try cp1252 first (superset of latin-1 with printable chars in 0x80-0x9F)
        try:
            sample.decode("cp1252")
            return "cp1252"
        except (UnicodeDecodeError, ValueError):
            pass

        # Library-based detection before falling back to latin-1
        lib_enc = _detect_encoding_library(content)
        if lib_enc:
            return lib_enc

        return "latin-1"  # latin-1 never fails on any byte

    return "utf-8"


# ============================================================================
# HEADER AUTO-DETECTION
# ============================================================================

def _score_header_candidate(values: List[str], num_columns: int) -> float:
    """
    Score a row as a potential header using multiple signals:
      - alphabetic token density (0-1)
      - unique token ratio (0-1)
      - non-numeric ratio (0-1)
    Returns composite score 0-3.
    """
    if not values:
        return 0.0

    alpha_count = sum(1 for v in values if any(ch.isalpha() for ch in v))
    alpha_density = alpha_count / max(len(values), 1)

    unique_ratio = len(set(values)) / max(len(values), 1)

    non_numeric = sum(1 for v in values if not v.replace(".", "").replace("-", "").strip().isdigit())
    non_numeric_ratio = non_numeric / max(len(values), 1)

    return alpha_density + unique_ratio + non_numeric_ratio


def detect_header_row(df: pd.DataFrame, max_scan: int = 15) -> int:
    """
    Detect which row is the actual header using multi-signal scoring.

    Scans first `max_scan` rows, scoring each by:
      - alphabetic token density
      - unique token count
      - non-numeric ratio

    Returns 0 if the current header (row 0) looks correct.
    """
    if df.empty or len(df) < 2:
        return 0

    # Check if current column names look like headers (alphabetic)
    current_headers = [str(c) for c in df.columns]
    current_score = _score_header_candidate(current_headers, len(df.columns))
    if current_score >= 2.0:
        return 0

    # Scan data rows for better header candidate
    best_row = 0
    best_score = current_score
    scan_limit = min(max_scan, len(df))

    for i in range(scan_limit):
        row_vals = [str(v) for v in df.iloc[i]]
        score = _score_header_candidate(row_vals, len(df.columns))
        if score > best_score:
            best_score = score
            best_row = i

    # Only promote if data row scored meaningfully better
    if best_row > 0 and best_score > current_score + 0.5:
        return best_row

    return 0


def _reheader_df(df: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """Promote a data row to be the header and drop rows above it."""
    if header_row == 0:
        return df
    new_headers = [str(v) for v in df.iloc[header_row]]
    new_df = df.iloc[header_row + 1:].copy()
    new_df.columns = new_headers
    new_df.reset_index(drop=True, inplace=True)
    return new_df


# ============================================================================
# MULTI-SHEET EXCEL
# ============================================================================

def _sheet_text_density(sheet_df: pd.DataFrame) -> float:
    """
    Score a sheet by text density weighted by data volume.
    Score = text_ratio * log2(total_cells + 1) so larger sheets win ties.
    """
    if sheet_df.empty:
        return 0.0
    total_cells = sheet_df.shape[0] * sheet_df.shape[1]
    if total_cells == 0:
        return 0.0
    text_cells = 0
    for col in sheet_df.columns:
        sample = sheet_df[col].dropna().astype(str).head(50)
        text_cells += sum(1 for v in sample if any(ch.isalpha() for ch in v))
    text_ratio = text_cells / max(total_cells, 1)
    import math
    return text_ratio * math.log2(total_cells + 1)


def _parse_excel_multisheet(content: bytes, engine: str = "openpyxl") -> Tuple[Optional[pd.DataFrame], str]:
    """
    Parse Excel file with multi-sheet policy.

    Strategy:
      - Score each sheet by text density
      - If top sheets have similar density (within 20%), concat vertically
      - Otherwise pick the highest-density sheet

    Returns: (df, strategy_used)
    """
    try:
        all_sheets = pd.read_excel(
            io.BytesIO(content), engine=engine, sheet_name=None, nrows=MAX_ROWS_MEMORY
        )
    except Exception:
        return None, "error"

    if not all_sheets:
        return None, "empty"

    if len(all_sheets) == 1:
        return list(all_sheets.values())[0], "single_sheet"

    # Score each non-empty sheet by text density
    scored = []
    for name, sheet_df in all_sheets.items():
        if sheet_df.empty:
            continue
        density = _sheet_text_density(sheet_df)
        scored.append((name, sheet_df, density))

    if not scored:
        return None, "all_empty"

    scored.sort(key=lambda x: x[2], reverse=True)
    best_name, best_df, best_density = scored[0]

    # Check if top sheets have similar density → concat
    similar = [best_df]
    for name, sheet_df, density in scored[1:]:
        if best_density > 0 and density >= best_density * 0.8:
            similar.append(sheet_df)

    if len(similar) > 1:
        # Concat vertically, keeping columns from the first sheet
        # Only concat sheets that share at least 50% of columns
        base_cols = set(str(c) for c in similar[0].columns)
        to_concat = [similar[0]]
        for extra_df in similar[1:]:
            extra_cols = set(str(c) for c in extra_df.columns)
            overlap = len(base_cols & extra_cols) / max(len(base_cols), 1)
            if overlap >= 0.5:
                to_concat.append(extra_df)
        if len(to_concat) > 1:
            combined = pd.concat(to_concat, ignore_index=True)
            return combined, "concat"

    return best_df, "best_density"


# ============================================================================
# ZIP HANDLING
# ============================================================================

def _extract_from_zip(content: bytes) -> Optional[Tuple[bytes, str]]:
    """Extract the first supported dataset from a ZIP file. Returns (content, filename)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Zip bomb protection
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_ZIP_DECOMPRESSED:
                return None

            # Find first supported file
            for info in zf.infolist():
                if info.is_dir():
                    continue
                ext = Path(info.filename).suffix.lower()
                if ext in _TEXT_EXTENSIONS | _EXCEL_EXTENSIONS:
                    extracted = zf.read(info.filename)
                    return (extracted, info.filename)
    except (zipfile.BadZipFile, Exception):
        return None
    return None


# ============================================================================
# PARSE FAILURE LOGGING
# ============================================================================

def _log_parse_failure(filename: str, mime_type: str, file_size: int,
                       content: bytes, parser: str, error: str) -> None:
    """Write parse failure record to JSONL log."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "filename": filename,
            "mime_type": mime_type,
            "file_size": file_size,
            "first_256_bytes_hex": content[:256].hex(),
            "parser_attempted": parser,
            "error_message": str(error)[:500],
        }
        with open(_PARSE_FAILURE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def ingest_file(content: bytes, filename: str) -> Dict:
    """
    Parse raw file bytes into a DataFrame with full fallback chain.

    Args:
        content: Raw file bytes
        filename: Original filename

    Returns:
        {
            "df": pd.DataFrame or None,
            "rows": int,
            "columns": int,
            "headers": List[str],
            "detected_type": str,
            "encoding_used": str,
            "parser_used": str,
            "header_row_detected": int,
            "sheets_found": int,
            "error": str or None,
            "guardrail_hit": str or None,
        }
    """
    filename = filename or "upload"
    file_size = len(content)

    # ── Guardrail: file size ──
    if file_size > MAX_FILE_SIZE:
        return _result(error=f"File exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit",
                       guardrail_hit="max_file_size",
                       detected_type="unknown", filename=filename)

    if file_size == 0:
        return _result(error="Empty file", detected_type="empty", filename=filename)

    # ── Step 1: Magic-byte detection ──
    type_info = detect_file_type(content, filename)
    detected_type = type_info["detected_type"]

    if not type_info["supported"]:
        _log_parse_failure(filename, detected_type, file_size, content,
                           "magic_detect", f"Unsupported binary format: {detected_type}")
        return _result(error=f"Unsupported file format: {detected_type}",
                       detected_type=detected_type, filename=filename)

    # ── Step 2: ZIP extraction ──
    if detected_type == "zip":
        extracted = _extract_from_zip(content)
        if extracted is None:
            _log_parse_failure(filename, "zip", file_size, content,
                               "zip_extract", "No supported dataset found in ZIP")
            return _result(error="No supported dataset found in ZIP archive",
                           detected_type="zip", filename=filename)
        content, filename = extracted
        file_size = len(content)
        type_info = detect_file_type(content, filename)
        detected_type = type_info["detected_type"]

    # ── Step 3: Parse via fallback chain ──
    df = None
    parser_used = None
    encoding_used = None
    sheets_found = 1
    errors_collected = []

    if detected_type in ("xlsx", "xlsm"):
        # Excel path
        df, parser_used, sheets_found, err = _parse_excel(content, filename)
        if err:
            errors_collected.append(err)
    elif detected_type == "xls":
        df, parser_used, sheets_found, err = _parse_xls(content, filename)
        if err:
            errors_collected.append(err)
    elif detected_type == "json":
        df, parser_used, err = _parse_json(content, filename)
        if err:
            errors_collected.append(err)
    else:
        # CSV / TSV / TXT — text-based fallback chain
        df, parser_used, encoding_used, err = _parse_text(content, filename)
        if err:
            errors_collected.append(err)

    # ── Guardrail: max rows ──
    if df is not None and len(df) > MAX_ROWS_MEMORY:
        df = df.head(MAX_ROWS_MEMORY)

    # ── Step 4: Header auto-detection ──
    header_row = 0
    if df is not None and not df.empty:
        header_row = detect_header_row(df)
        if header_row > 0:
            df = _reheader_df(df, header_row)

    # ── Build result ──
    if df is not None and not df.empty:
        headers = [str(c) for c in df.columns]
        return _result(
            df=df, rows=len(df), columns=len(df.columns), headers=headers,
            detected_type=detected_type, encoding_used=encoding_used or "n/a",
            parser_used=parser_used or "unknown",
            header_row_detected=header_row, sheets_found=sheets_found,
            filename=filename,
        )

    # All parsers failed — log it
    combined_errors = "; ".join(errors_collected) if errors_collected else "All parsers failed"
    _log_parse_failure(filename, detected_type, file_size, content,
                       "all_parsers", combined_errors)

    return _result(error=combined_errors, detected_type=detected_type, filename=filename)


# ============================================================================
# PARSER IMPLEMENTATIONS
# ============================================================================

def _parse_excel(content: bytes, filename: str) -> Tuple[Optional[pd.DataFrame], Optional[str], int, Optional[str]]:
    """Parse XLSX/XLSM with multi-sheet support."""
    # Try openpyxl multi-sheet
    try:
        all_sheets = pd.read_excel(io.BytesIO(content), engine="openpyxl",
                                   sheet_name=None, nrows=MAX_ROWS_MEMORY)
        sheets_found = len(all_sheets)
        if sheets_found == 1:
            df = list(all_sheets.values())[0]
            strategy = "single_sheet"
        else:
            df, strategy = _parse_excel_multisheet(content, engine="openpyxl")
        if df is not None and not df.empty:
            return df, f"openpyxl_{strategy}", sheets_found, None
    except zipfile.BadZipFile:
        # Corrupted xlsx — try as CSV
        df, parser, enc, err = _parse_text(content, filename)
        return df, parser, 1, err
    except Exception:
        pass

    return None, None, 1, f"Excel parse failed for {filename}"


def _parse_xls(content: bytes, filename: str) -> Tuple[Optional[pd.DataFrame], Optional[str], int, Optional[str]]:
    """Parse legacy XLS."""
    try:
        all_sheets = pd.read_excel(io.BytesIO(content), engine="xlrd",
                                   sheet_name=None, nrows=MAX_ROWS_MEMORY)
        sheets_found = len(all_sheets)
        if sheets_found == 1:
            df = list(all_sheets.values())[0]
        else:
            # Pick sheet with most rows
            df = max(all_sheets.values(), key=lambda d: len(d))
        if df is not None and not df.empty:
            return df, "xlrd", sheets_found, None
    except Exception as e:
        return None, None, 1, f"XLS parse failed: {e}"
    return None, None, 1, "XLS file is empty"


def _parse_json(content: bytes, filename: str) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[str]]:
    """Parse JSON file."""
    # Try utf-8-sig first (BOM), then utf-8, then latin-1
    text = None
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = content.decode(enc)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    if text is None:
        return None, None, "JSON decode failed"

    try:
        data = json.loads(text)
        if isinstance(data, list):
            df = pd.DataFrame(data[:MAX_ROWS_MEMORY])
        elif isinstance(data, dict):
            for key in ["results", "data", "companies", "items", "records", "rows"]:
                if key in data and isinstance(data[key], list):
                    df = pd.DataFrame(data[key][:MAX_ROWS_MEMORY])
                    break
            else:
                df = pd.DataFrame([data])
        else:
            return None, None, "JSON root is not list or dict"
        if df is not None and not df.empty:
            return df, "json", None
    except json.JSONDecodeError as e:
        return None, None, f"JSON parse error: {e}"
    return None, None, "JSON file is empty"


def _detect_delimiter(content: bytes, encoding: str = "utf-8") -> Optional[str]:
    """
    Detect CSV delimiter using csv.Sniffer, then heuristic column-count scoring.
    Supports: comma, semicolon, tab, pipe.
    """
    try:
        text = content.decode(encoding, errors="replace")
    except Exception:
        text = content.decode("latin-1", errors="replace")

    sample = text[:16384]

    # Try csv.Sniffer first
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        pass

    # Heuristic: count each delimiter across first 20 lines,
    # pick the one that gives the most consistent column count
    lines = [line for line in sample.splitlines() if line.strip()][:20]
    if not lines:
        return None

    best_delim = ","
    best_consistency = -1

    for delim in [",", ";", "\t", "|"]:
        counts = [line.count(delim) for line in lines]
        if not counts or max(counts) == 0:
            continue
        # Consistency = how many lines have the same count as the mode
        from collections import Counter
        mode_count = Counter(counts).most_common(1)[0][1]
        avg_cols = sum(counts) / len(counts)
        # Score: consistency ratio * average columns (prefer more columns)
        consistency = (mode_count / len(counts)) * avg_cols
        if consistency > best_consistency:
            best_consistency = consistency
            best_delim = delim

    return best_delim if best_consistency > 0 else None


def _retry_with_header_scan(content: bytes, encoding: str, max_scan: int = 15) -> Optional[pd.DataFrame]:
    """
    When initial parse yields a single column, scan the first lines
    for the one that looks like a real CSV header (has delimiters)
    and re-parse with skiprows + detected delimiter.
    """
    try:
        text = content.decode(encoding, errors="replace")
        lines = text.splitlines()[:max_scan]
        for i, line in enumerate(lines):
            # A real CSV header has multiple delimited fields
            for delim in [",", ";", "\t", "|"]:
                if line.count(delim) >= 2:
                    df = pd.read_csv(io.BytesIO(content), encoding=encoding,
                                     skiprows=i, sep=delim,
                                     on_bad_lines="warn",
                                     nrows=MAX_ROWS_MEMORY)
                    if df is not None and len(df.columns) >= 2 and not df.empty:
                        return df
                    break
    except Exception:
        pass
    return None


def _parse_text(content: bytes, filename: str) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[str], Optional[str]]:
    """
    Parse text-based file (CSV/TSV/TXT) with full fallback chain.
    Returns: (df, parser_used, encoding_used, error)
    """
    # ── Attempt 1: pandas with detected delimiter + encoding attempts ──
    for enc in ENCODING_ATTEMPTS:
        try:
            delim = _detect_delimiter(content, enc)
            kwargs = {"encoding": enc, "on_bad_lines": "warn", "nrows": MAX_ROWS_MEMORY}
            if delim and delim != ",":
                kwargs["sep"] = delim
            df = pd.read_csv(io.BytesIO(content), **kwargs)
            if df is not None and not df.empty:
                # If we got a single-column result but the file has multi-column
                # rows further down, retry with skiprows to find the real header.
                if len(df.columns) == 1:
                    df2 = _retry_with_header_scan(content, enc)
                    if df2 is not None:
                        return df2, f"pandas_csv_{enc}_headerfix", enc, None
                return df, f"pandas_csv_{enc}", enc, None
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except Exception:
            continue

    # ── Attempt 2: pandas with sep detection (python engine) ──
    for enc in ["utf-8-sig", "latin-1"]:
        try:
            df = pd.read_csv(io.BytesIO(content), encoding=enc, sep=None,
                             engine="python", on_bad_lines="warn",
                             nrows=MAX_ROWS_MEMORY)
            if df is not None and not df.empty:
                return df, f"pandas_sniffer_{enc}", enc, None
        except Exception:
            continue

    # ── Attempt 3: csv.Sniffer + csv module ──
    detected_enc = detect_encoding(content)
    try:
        text = content.decode(detected_enc, errors="replace")
        sniffer = csv.Sniffer()
        sample = text[:8192]
        dialect = sniffer.sniff(sample, delimiters=",;\t|")
        reader = csv.reader(io.StringIO(text), dialect)
        rows = []
        for i, row in enumerate(reader):
            if i >= MAX_ROWS_MEMORY:
                break
            rows.append(row)
        if rows:
            header = rows[0]
            data = rows[1:]
            df = pd.DataFrame(data, columns=header)
            if not df.empty:
                return df, "csv_sniffer", detected_enc, None
    except Exception:
        pass

    # ── Attempt 4: messy CSV recovery (skip bad lines) ──
    for enc in ["utf-8-sig", "latin-1", "cp1252"]:
        try:
            delim = _detect_delimiter(content, enc)
            kwargs = {"encoding": enc, "on_bad_lines": "skip",
                      "engine": "python", "nrows": MAX_ROWS_MEMORY}
            if delim and delim != ",":
                kwargs["sep"] = delim
            df = pd.read_csv(io.BytesIO(content), **kwargs)
            if df is not None and not df.empty:
                # Count skipped rows for logging
                try:
                    full_lines = content.decode(enc, errors="replace").splitlines()
                    data_lines = len([l for l in full_lines if l.strip()]) - 1  # minus header
                    skipped = max(0, data_lines - len(df))
                    if skipped > 0:
                        import logging
                        logging.getLogger("file_ingestion").warning(
                            "Messy CSV recovery: %d rows skipped in %s", skipped, filename)
                except Exception:
                    pass
                return df, f"messy_recovery_{enc}", enc, None
        except Exception:
            continue

    # ── Attempt 5: detected encoding → pandas retry ──
    if detected_enc not in ENCODING_ATTEMPTS:
        try:
            df = pd.read_csv(io.BytesIO(content), encoding=detected_enc,
                             on_bad_lines="warn", nrows=MAX_ROWS_MEMORY)
            if df is not None and not df.empty:
                return df, f"pandas_detected_{detected_enc}", detected_enc, None
        except Exception:
            pass

    # ── Attempt 6: library-detected encoding → pandas retry ──
    lib_enc = _detect_encoding_library(content)
    if lib_enc and lib_enc not in ENCODING_ATTEMPTS and lib_enc != detected_enc:
        try:
            df = pd.read_csv(io.BytesIO(content), encoding=lib_enc,
                             on_bad_lines="warn", nrows=MAX_ROWS_MEMORY)
            if df is not None and not df.empty:
                return df, f"pandas_lib_{lib_enc}", lib_enc, None
        except Exception:
            pass

    # ── Attempt 7: raw line reader (last resort) ──
    try:
        text = content.decode(detected_enc, errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            df = pd.DataFrame({"raw_text": lines[:MAX_ROWS_MEMORY]})
            return df, "raw_line_reader", detected_enc, None
    except Exception:
        pass

    return None, None, None, "All text parsers failed"


# ============================================================================
# RESULT BUILDER
# ============================================================================

def _result(
    df: Optional[pd.DataFrame] = None,
    rows: int = 0,
    columns: int = 0,
    headers: Optional[List[str]] = None,
    detected_type: str = "unknown",
    encoding_used: str = "n/a",
    parser_used: str = "none",
    header_row_detected: int = 0,
    sheets_found: int = 1,
    error: Optional[str] = None,
    guardrail_hit: Optional[str] = None,
    filename: str = "upload",
) -> Dict:
    return {
        "df": df,
        "rows": rows,
        "columns": columns,
        "headers": headers or [],
        "detected_type": detected_type,
        "encoding_used": encoding_used,
        "parser_used": parser_used,
        "header_row_detected": header_row_detected,
        "sheets_found": sheets_found,
        "error": error,
        "guardrail_hit": guardrail_hit,
    }
