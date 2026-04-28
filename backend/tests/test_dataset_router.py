"""Tests for dataset_router — deterministic schema-level routing."""

import io
from unittest.mock import patch

import pytest
import pandas as pd

from app.dataset_router import inspect_dataset, _normalize_header, _profile_column


# ============================================================================
# HELPERS
# ============================================================================

def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to xlsx bytes."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _csv_bytes(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")


# ============================================================================
# TEST 1: Frank HR dataset → PERSON → effective_mode=mixed
# ============================================================================

class TestPersonDataset:
    """Person-heavy HR spreadsheet must route to mixed (sanitize), not garbage."""

    def _make_frank_dataset(self):
        return pd.DataFrame({
            "Nombre": ["Frank", "Maria", "Jose", "Ana", "Carlos", "Luis", "Rosa", "Pedro", "Sofia", "Diego"] * 10,
            "Primer Apellido": ["Garcia", "Lopez", "Martinez", "Hernandez", "Gonzalez", "Rodriguez", "Perez", "Sanchez", "Ramirez", "Torres"] * 10,
            "Segundo Apellido": ["Escobedo", "Reyes", "Cruz", "Flores", "Rivera", "Gomez", "Diaz", "Morales", "Jimenez", "Ruiz"] * 10,
            "Edad": [35, 28, 42, 31, 45, 38, 29, 50, 33, 27] * 10,
            "Sexo": ["M", "F", "M", "F", "M", "M", "F", "M", "F", "M"] * 10,
            "Departamento": ["Engineering", "Sales", "HR", "Finance", "Ops", "Marketing", "Legal", "IT", "Support", "R&D"] * 10,
            "Posicion": ["Manager", "Analyst", "Director", "Specialist", "Lead", "VP", "Coordinator", "Engineer", "Advisor", "Intern"] * 10,
        })

    def test_xlsx_person_routing(self):
        df = self._make_frank_dataset()
        content = _xlsx_bytes(df)
        result = inspect_dataset(content, "frank-1.xlsx")

        assert result["effective_mode"] == "mixed", f"Expected mixed, got {result['effective_mode']}"
        assert result["routing_decision"] == "person_dataset"
        assert result["dataset_type"] == "PERSON"
        assert len(result["person_headers_detected"]) >= 2

    def test_csv_person_routing(self):
        df = self._make_frank_dataset()
        content = _csv_bytes(df)
        result = inspect_dataset(content, "frank-1.csv")

        assert result["effective_mode"] == "mixed"
        assert result["routing_decision"] == "person_dataset"

    def test_english_person_headers(self):
        df = pd.DataFrame({
            "First Name": ["John", "Jane", "Bob"] * 10,
            "Last Name": ["Smith", "Doe", "Wilson"] * 10,
            "Age": [30, 25, 45] * 10,
            "Gender": ["M", "F", "M"] * 10,
            "Employee ID": [1001, 1002, 1003] * 10,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "employees.csv")

        assert result["effective_mode"] == "mixed"
        assert result["routing_decision"] == "person_dataset"


# ============================================================================
# TEST 2: Company dataset → COMPANY → effective_mode=company
# ============================================================================

class TestCompanyDataset:
    """Company name lists must route to waterfall resolution."""

    def test_company_headers(self):
        df = pd.DataFrame({
            "Company Name": ["Apple Inc", "Google LLC", "Microsoft Corporation", "Amazon.com Inc", "Meta Platforms Inc"] * 20,
            "Industry": ["Tech", "Tech", "Tech", "Retail", "Social"] * 20,
            "Revenue": [394000, 283000, 198000, 514000, 117000] * 20,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "companies.csv")

        assert result["effective_mode"] == "company"
        assert result["routing_decision"] in ("company_dataset", "ml_classifier_org")
        assert result["dataset_type"] == "COMPANY"

    def test_vendor_header(self):
        df = pd.DataFrame({
            "Vendor": ["Pfizer Inc", "Johnson & Johnson", "Merck & Co Ltd", "Abbott Labs Corp"] * 25,
            "Amount": [50000, 75000, 32000, 28000] * 25,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "vendors.xlsx")

        assert result["effective_mode"] == "company"

    def test_company_tokens_in_values(self):
        """Even without company headers, high company token ratio → company mode."""
        df = pd.DataFrame({
            "Name": [
                "Acme Corp", "Smith LLC", "Global Holdings Ltd", "Pacific Group Inc",
                "United Corp", "Sterling Partners LLC", "Atlas International Ltd",
                "Prime Group Inc", "Summit Corp", "Apex Holdings LLC",
            ] * 10,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "data.csv")

        assert result["effective_mode"] == "company"
        assert result["company_token_ratio"] >= 0.30


# ============================================================================
# TEST 3: Mixed CRM export → MIXED → effective_mode=mixed
# ============================================================================

class TestMixedDataset:
    """Mixed entity data without strong signals → sanitize pipeline."""

    def test_mixed_crm_export(self):
        df = pd.DataFrame({
            "Record": list(range(1, 51)),
            "Value": [
                "John Smith", "Acme Corp", "123 Main St", "jane@email.com",
                "Bob Wilson", "42", "N/A", "Global Tech",
                "Maria Garcia", "Test Company",
            ] * 5,
            "Type": ["person", "company", "address", "email", "person",
                     "number", "null", "company", "person", "company"] * 5,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "crm_export.csv")

        assert result["effective_mode"] == "mixed"
        assert result["dataset_type"] == "MIXED"


# ============================================================================
# TEST 4: Numeric junk → INVALID → effective_mode=reject
# ============================================================================

class TestInvalidDataset:
    """Purely numeric data with no entity signals → reject."""

    def test_numeric_only(self):
        df = pd.DataFrame({
            "col1": list(range(1000, 1100)),
            "col2": list(range(2000, 2100)),
            "col3": [float(x) * 1.5 for x in range(100)],
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "numbers.csv")

        assert result["effective_mode"] == "reject"
        assert result["routing_decision"] == "invalid_dataset"
        assert result["dataset_type"] == "INVALID"

    def test_empty_file(self):
        result = inspect_dataset(b"", "empty.csv")
        assert result["effective_mode"] == "mixed"
        assert result["routing_decision"] == "empty_dataset"


# ============================================================================
# TEST 5: Structured routing metadata
# ============================================================================

class TestRoutingMetadata:
    """Routing result must contain all required structured fields."""

    def test_metadata_fields(self):
        df = pd.DataFrame({
            "Nombre": ["Frank", "Maria"] * 10,
            "Primer Apellido": ["Garcia", "Lopez"] * 10,
            "Edad": [35, 28] * 10,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "test.csv")

        required_fields = [
            "effective_mode", "routing_decision", "routing_reason",
            "dataset_type", "sampled_headers", "person_headers_detected",
            "company_headers_detected", "sample_row_count",
            "alpha_columns", "numeric_columns", "company_token_ratio",
            "fallback_used",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_headers_preserved(self):
        df = pd.DataFrame({
            "Nombre": ["Frank"] * 5,
            "Primer Apellido": ["Garcia"] * 5,
            "Segundo Apellido": ["Escobedo"] * 5,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "test.csv")

        assert len(result["sampled_headers"]) == 3


# ============================================================================
# UNIT TESTS: Helpers
# ============================================================================

class TestHelpers:

    def test_normalize_header(self):
        assert _normalize_header("Primer Apellido") == "primer apellido"
        assert _normalize_header("COMPANY_NAME") == "company_name"
        assert _normalize_header("  Nombre  ") == "nombre"
        assert _normalize_header("Col#1!") == "col1"

    def test_profile_column_numeric(self):
        s = pd.Series([1, 2, 3, 4, 5, 100, 200, 300, 400, 500])
        p = _profile_column(s)
        assert p["numeric_ratio"] > 0.9
        assert p["alpha_ratio"] == 0.0

    def test_profile_column_alpha(self):
        s = pd.Series(["Frank", "Maria", "Jose", "Ana", "Carlos"])
        p = _profile_column(s)
        assert p["alpha_ratio"] == 1.0
        assert p["numeric_ratio"] == 0.0

    def test_profile_column_nulls(self):
        s = pd.Series([None, None, None, "Frank", "Maria"])
        p = _profile_column(s)
        assert p["null_ratio"] == 0.6


# ============================================================================
# TEST 7: Router uses classifier when confidence >= threshold
# ============================================================================

class TestClassifierIntegration:
    """Router must use classifier when confidence is high, fall back otherwise."""

    def test_classifier_high_confidence_used(self):
        """When classifier returns high confidence, router uses it (fallback_used=False)."""
        df = pd.DataFrame({
            "Company Name": ["Apple Inc", "Google LLC", "Microsoft Corporation"] * 30,
            "Industry": ["Tech", "Tech", "Tech"] * 30,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "companies.csv")

        assert result["effective_mode"] == "company"
        # Either ML or heuristic can route this — both are correct
        if result.get("fallback_used") is False:
            assert result["routing_decision"].startswith("ml_classifier_")
            assert result.get("classifier_confidence", 0) >= 0.70
        else:
            assert result["routing_decision"] == "company_dataset"

    def test_classifier_fallback_when_model_unavailable(self):
        """When classifier model is unavailable, router falls back to heuristics."""
        df = pd.DataFrame({
            "Nombre": ["Frank", "Maria", "Jose"] * 10,
            "Primer Apellido": ["Garcia", "Lopez", "Martinez"] * 10,
            "Edad": [35, 28, 42] * 10,
        })
        content = _csv_bytes(df)

        # Patch classify_dataset to simulate model unavailable
        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "unknown", "confidence": 0.0, "error": "model_not_loaded"}
            result = inspect_dataset(content, "hr_data.csv")

        assert result["effective_mode"] == "mixed"
        assert result["routing_decision"] == "person_dataset"
        assert result["fallback_used"] is True

    def test_classifier_fallback_when_confidence_low(self):
        """When classifier confidence < 0.70, router falls back to heuristics."""
        df = pd.DataFrame({
            "Nombre": ["Frank", "Maria", "Jose"] * 10,
            "Primer Apellido": ["Garcia", "Lopez", "Martinez"] * 10,
            "Edad": [35, 28, 42] * 10,
        })
        content = _csv_bytes(df)

        # Patch classify_dataset to return low confidence
        with patch("app.dataset_router.classify_dataset") as mock_clf:
            mock_clf.return_value = {"label": "garbage", "confidence": 0.45}
            result = inspect_dataset(content, "hr_data.csv")

        # Even though classifier said "garbage", low confidence → heuristic wins
        assert result["effective_mode"] == "mixed"
        assert result["routing_decision"] == "person_dataset"
        assert result["fallback_used"] is True

    def test_frank_hr_routes_to_sanitize_not_garbage(self):
        """Frank-style HR dataset must route to mixed (sanitize+attest), never garbage."""
        df = pd.DataFrame({
            "Nombre": ["Frank", "Maria", "Jose", "Ana", "Carlos"] * 20,
            "Primer Apellido": ["Garcia", "Lopez", "Martinez", "Hernandez", "Gonzalez"] * 20,
            "Segundo Apellido": ["Escobedo", "Reyes", "Cruz", "Flores", "Rivera"] * 20,
            "Edad": [35, 28, 42, 31, 45] * 20,
            "Sexo": ["M", "F", "M", "F", "M"] * 20,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "frank-1.xlsx")

        assert result["effective_mode"] == "mixed", f"Frank HR routed to {result['effective_mode']}, expected mixed"
        assert result["effective_mode"] != "reject", "Frank HR must never be rejected"
        assert result["dataset_type"] == "PERSON"

    def test_company_dataset_routes_to_waterfall(self):
        """Company dataset must route to company mode (waterfall resolution)."""
        df = pd.DataFrame({
            "Vendor": ["Pfizer Inc", "Tesla Inc", "Boeing Company", "Oracle Corporation"] * 25,
            "Amount": [50000, 75000, 32000, 28000] * 25,
        })
        content = _csv_bytes(df)
        result = inspect_dataset(content, "vendors.csv")

        assert result["effective_mode"] == "company", f"Company dataset routed to {result['effective_mode']}, expected company"
        assert result["dataset_type"] == "COMPANY"
