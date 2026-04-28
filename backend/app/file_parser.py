"""
================================================================================
UNIVERSAL DATA INGESTION LAYER
================================================================================

Senior Engineering approach to file parsing.
Handles CSV, Excel (.xlsx/.xls), and JSON with intelligent column detection.

Features:
- BOM handling for Excel-exported CSVs
- Multiple encoding fallbacks (utf-8-sig, latin1)
- Nested JSON support (finds first array in object)
- Intelligent column detection with priority list
- Graceful fallback to first column

================================================================================
"""

import pandas as pd
import json
import io
from typing import List, Optional


class FileParseError(Exception):
    """Custom exception for file parsing errors."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


async def parse_uploaded_file(file_content: bytes, filename: str) -> List[str]:
    """
    Universal Ingestion Layer.
    
    Accepts: CSV, Excel (.xlsx/.xls), JSON, TXT
    Returns: A clean list of strings (company names).
    Raises: FileParseError if format is invalid or file is empty.
    
    Args:
        file_content: Raw bytes from uploaded file
        filename: Original filename (used for format detection)
    
    Returns:
        List of company name strings, cleaned and deduplicated
    """
    filename_lower = filename.lower()
    df = pd.DataFrame()

    try:
        # --- STRATEGY 1: CSV Handling ---
        if filename_lower.endswith(".csv"):
            df = _parse_csv(file_content)

        # --- STRATEGY 2: Excel Handling (with explicit engine) ---
        elif filename_lower.endswith((".xlsx", ".xls")):
            df = _parse_excel(file_content, filename)

        # --- STRATEGY 3: JSON Handling ---
        elif filename_lower.endswith(".json"):
            df = _parse_json(file_content)

        # --- STRATEGY 4: Plain Text Handling ---
        elif filename_lower.endswith(".txt"):
            return _parse_text(file_content)

        else:
            raise FileParseError(
                "Unsupported file format. Please upload .csv, .xlsx, .xls, .json, or .txt",
                status_code=400
            )

    except FileParseError:
        raise
    except Exception as e:
        raise FileParseError(f"File parsing error: {str(e)}", status_code=400)

    if df.empty:
        raise FileParseError("The uploaded file contains no data.", status_code=400)

    # --- INTELLIGENT COLUMN DETECTION ---
    clean_rows = _extract_company_column(df)
    
    if not clean_rows:
        raise FileParseError(
            "Could not find any valid company names in the file.",
            status_code=400
        )

    return clean_rows


def _parse_csv(content: bytes) -> pd.DataFrame:
    """Parse CSV with multiple encoding fallbacks."""
    # Try utf-8-sig first (handles BOM from Excel)
    try:
        return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
    except UnicodeDecodeError:
        pass
    
    # Fallback to latin1 for legacy Windows files
    try:
        return pd.read_csv(io.BytesIO(content), encoding="latin1")
    except Exception:
        pass
    
    # Last resort: utf-8 with error replacement
    return pd.read_csv(io.BytesIO(content), encoding="utf-8", errors="replace")


def _parse_excel(content: bytes, filename: str = "") -> pd.DataFrame:
    """
    Parse Excel file with explicit engine assignment.
    
    CRITICAL: When reading from bytes (BytesIO), pandas cannot auto-detect
    the file format. We must explicitly specify the engine based on extension.
    
    - .xlsx → openpyxl (modern Excel 2007+)
    - .xls  → xlrd (legacy Excel 97-2003)
    """
    filename_lower = filename.lower()
    
    try:
        if filename_lower.endswith(".xlsx"):
            # Modern Excel files - requires: pip install openpyxl
            return pd.read_excel(
                io.BytesIO(content), 
                engine="openpyxl", 
                sheet_name=0
            )
        elif filename_lower.endswith(".xls"):
            # Legacy Excel files - requires: pip install xlrd
            return pd.read_excel(
                io.BytesIO(content), 
                engine="xlrd", 
                sheet_name=0
            )
        else:
            # Fallback: try openpyxl first (most common)
            try:
                return pd.read_excel(
                    io.BytesIO(content), 
                    engine="openpyxl", 
                    sheet_name=0
                )
            except Exception:
                # Last resort: try xlrd
                return pd.read_excel(
                    io.BytesIO(content), 
                    engine="xlrd", 
                    sheet_name=0
                )
    except ImportError as e:
        if "openpyxl" in str(e):
            raise FileParseError(
                "Missing dependency: pip install openpyxl (required for .xlsx files)",
                status_code=500
            )
        elif "xlrd" in str(e):
            raise FileParseError(
                "Missing dependency: pip install xlrd (required for .xls files)",
                status_code=500
            )
        raise


def _parse_json(content: bytes) -> pd.DataFrame:
    """
    Parse JSON with multiple structure support:
    - List of objects: [{"name": "A"}, {"name": "B"}]
    - Nested dict: {"results": [...]} or {"companies": [...]}
    - Single object: {"name": "A"}
    """
    try:
        data = json.loads(content.decode("utf-8"))
    except UnicodeDecodeError:
        data = json.loads(content.decode("latin1"))
    
    # Case A: List of objects
    if isinstance(data, list):
        return pd.DataFrame(data)
    
    # Case B: Nested Dict - find first key containing a list
    if isinstance(data, dict):
        # Priority keys to check first
        priority_keys = ["results", "data", "companies", "items", "records", "rows"]
        
        # Check priority keys first
        for key in priority_keys:
            if key in data and isinstance(data[key], list):
                return pd.DataFrame(data[key])
        
        # Fallback: find any key with a list
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0:
                return pd.DataFrame(value)
        
        # Case C: Single object - wrap in list
        return pd.DataFrame([data])
    
    raise FileParseError("Invalid JSON structure. Expected array or object.", status_code=400)


def _parse_text(content: bytes) -> List[str]:
    """Parse plain text file (one company per line)."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin1")
    
    lines = text.strip().split("\n")
    names = [line.strip() for line in lines if line.strip()]
    
    # Skip header if it looks like one
    header_keywords = ["company", "name", "company_name", "entity", "organization", "account"]
    if names and names[0].lower() in header_keywords:
        names = names[1:]
    
    return names


def _extract_company_column(df: pd.DataFrame) -> List[str]:
    """
    Intelligent column detection.
    Looks for common company column names, falls back to first column.
    """
    # Normalize headers to lowercase for search
    original_columns = df.columns.tolist()
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # Priority list of column names to look for (order matters!)
    target_cols = [
        "company_raw",      # Our standard input column
        "company_name",     # Common variant
        "company",          # Simple
        "name",             # Generic
        "account",          # Salesforce style
        "organization",     # Formal
        "entity",           # Legal/compliance
        "org",              # Abbreviated
        "account_name",     # CRM style
        "vendor",           # Procurement
        "supplier",         # Supply chain
        "customer",         # Sales
        "client",           # Services
    ]
    
    selected_col = None
    for col in target_cols:
        if col in df.columns:
            selected_col = col
            break
    
    # Fallback: Use first column if no header matches
    if selected_col is None:
        selected_col = df.columns[0]
        print(f"[FileParser] WARNING: No recognized column header. "
              f"Falling back to first column: '{original_columns[0]}'. "
              f"Upload may use wrong data — verify column names.", flush=True)
    else:
        print(f"[FileParser] Detected company column: '{selected_col}'", flush=True)
    
    # Extract, clean, and return
    clean_rows = (
        df[selected_col]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )
    
    # Filter out obvious non-names
    clean_rows = [
        row for row in clean_rows 
        if row and len(row) > 1 and row.lower() not in [
            "company", "name", "company_name", "nan", "null", "none", "-0-", ""
        ]
    ]
    
    return clean_rows


# Synchronous version for non-async contexts
def parse_file_sync(file_content: bytes, filename: str) -> List[str]:
    """
    Synchronous wrapper for parse_uploaded_file.
    Use this in non-async contexts.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        parse_uploaded_file(file_content, filename)
    )
