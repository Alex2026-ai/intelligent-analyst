"""Tests for PII scrubber — all categories, no false negatives."""

from apps.api.src.observability.pii_scrubber import scrub_value, scrub_dict, scrub_log_event


class TestSSN:
    def test_standard_format(self):
        assert "[SSN_REDACTED]" in scrub_value("SSN: 123-45-6789")

    def test_in_sentence(self):
        result = scrub_value("Patient SSN is 456-78-9012 on file")
        assert "456-78-9012" not in result
        assert "[SSN_REDACTED]" in result


class TestEmail:
    def test_standard_email(self):
        assert "[EMAIL_REDACTED]" in scrub_value("Contact: john@example.com")

    def test_complex_email(self):
        result = scrub_value("user.name+tag@sub.domain.co.uk")
        assert "user.name" not in result


class TestPhone:
    def test_parentheses_format(self):
        assert "[PHONE_US_REDACTED]" in scrub_value("Call (555) 123-4567")

    def test_dashes_format(self):
        assert "[PHONE_US_REDACTED]" in scrub_value("Phone: 555-123-4567")


class TestCreditCard:
    def test_spaces(self):
        assert "[CREDIT_CARD_REDACTED]" in scrub_value("Card: 4111 1111 1111 1111")

    def test_dashes(self):
        assert "[CREDIT_CARD_REDACTED]" in scrub_value("Card: 4111-1111-1111-1111")


class TestIPAddress:
    def test_ipv4(self):
        assert "[IP_ADDRESS_REDACTED]" in scrub_value("IP: 192.168.1.100")


class TestDOB:
    def test_standard_format(self):
        assert "[DOB_REDACTED]" in scrub_value("DOB: 01/15/1990")


class TestScrubDict:
    def test_scrubs_all_string_values(self):
        data = {"msg": "Email john@test.com", "ssn": "123-45-6789"}
        result = scrub_dict(data)
        assert "john@test.com" not in result["msg"]
        assert "123-45-6789" not in result["ssn"]

    def test_restricted_fields_redacted(self):
        data = {"password": "secret123", "api_key": "key-abc"}
        result = scrub_dict(data)
        assert result["password"] == "[RESTRICTED_REDACTED]"
        assert result["api_key"] == "[RESTRICTED_REDACTED]"

    def test_nested_dict_scrubbed(self):
        data = {"details": {"email": "user@test.com"}}
        result = scrub_dict(data)
        assert "user@test.com" not in str(result)

    def test_list_values_scrubbed(self):
        data = {"emails": ["a@b.com", "c@d.com"]}
        result = scrub_dict(data)
        assert all("[EMAIL_REDACTED]" in v for v in result["emails"])

    def test_non_string_values_preserved(self):
        data = {"count": 42, "active": True, "rate": 0.95}
        result = scrub_dict(data)
        assert result == data

    def test_phi_fields_blocked(self):
        data = {"medical_record": "MRN-12345", "diagnosis": "Type 2 DM"}
        result = scrub_dict(data)
        assert result["medical_record"] == "[RESTRICTED_REDACTED]"
        assert result["diagnosis"] == "[RESTRICTED_REDACTED]"


class TestScrubLogEvent:
    def test_full_event_scrubbed(self):
        event = {
            "event": "Resolution completed for john@test.com",
            "correlation_id": "trace-1",
            "ssn": "123-45-6789",
        }
        result = scrub_log_event(event)
        assert "john@test.com" not in result["event"]
        assert "123-45-6789" not in result["ssn"]
        assert result["correlation_id"] == "trace-1"
