"""Security test: submit PII, verify it appears nowhere in logs.

This test verifies that the PII scrubber catches all PII categories
and that PHI never appears in any log output (HIPAA requirement).
"""

from apps.api.src.observability.logging import StructuredLogger
from apps.api.src.observability.pii_scrubber import scrub_value

# Synthetic PII test data
SYNTHETIC_PII = {
    "ssn": "123-45-6789",
    "email": "patient@hospital.org",
    "phone": "(555) 123-4567",
    "credit_card": "4111 1111 1111 1111",
    "ip_address": "10.0.0.42",
    "dob": "03/15/1985",
}

# PHI data that must NEVER appear
SYNTHETIC_PHI = {
    "diagnosis": "Type 2 Diabetes Mellitus",
    "medication": "Metformin 500mg",
    "lab_result": "A1C 7.2%",
    "medical_record": "MRN-00123456",
}


class TestNoPIILeaks:
    def test_all_pii_categories_scrubbed(self):
        """Every PII category must be detected and scrubbed."""
        for category, value in SYNTHETIC_PII.items():
            result = scrub_value(f"Data: {value}")
            assert value not in result, f"PII category '{category}' was not scrubbed: {value}"
            assert "_REDACTED]" in result

    def test_pii_not_in_log_output(self):
        """PII must not appear in structured log output."""
        logger = StructuredLogger()
        for category, value in SYNTHETIC_PII.items():
            entry = logger.info(f"Processing: {value}", detail=value)
            entry_str = str(entry)
            assert value not in entry_str, f"PII '{category}' leaked into log output"

    def test_phi_blocked_by_restricted_fields(self):
        """PHI fields must be completely blocked."""
        logger = StructuredLogger()
        entry = logger.info(
            "Patient record",
            medical_record="MRN-00123456",
            diagnosis="Type 2 DM",
        )
        assert entry["medical_record"] == "[RESTRICTED_REDACTED]"
        assert entry["diagnosis"] == "[RESTRICTED_REDACTED]"

    def test_combined_pii_in_single_string(self):
        """Multiple PII types in one string should all be caught."""
        combined = "Name: John, SSN: 123-45-6789, Email: john@test.com, Phone: (555) 123-4567"
        result = scrub_value(combined)
        assert "123-45-6789" not in result
        assert "john@test.com" not in result
        assert "(555) 123-4567" not in result

    def test_pii_in_nested_structures(self):
        """PII in nested dicts and lists must be caught."""
        from apps.api.src.observability.pii_scrubber import scrub_dict
        data = {
            "user": {"email": "test@example.com"},
            "contacts": ["admin@company.com"],
        }
        result = scrub_dict(data)
        result_str = str(result)
        assert "test@example.com" not in result_str
        assert "admin@company.com" not in result_str
