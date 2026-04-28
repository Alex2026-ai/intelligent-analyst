"""Tests for PII pattern detection accuracy."""

from apps.api.src.pii.patterns import detect_pii


class TestPatternDetection:
    def test_ssn(self):
        findings = detect_pii("SSN: 123-45-6789")
        assert any(f[0] == "SSN" for f in findings)

    def test_email(self):
        findings = detect_pii("user@example.com")
        assert any(f[0] == "EMAIL" for f in findings)

    def test_phone_parens(self):
        findings = detect_pii("(555) 123-4567")
        assert any(f[0] == "PHONE" for f in findings)

    def test_phone_dashes(self):
        findings = detect_pii("555-123-4567")
        assert any(f[0] == "PHONE" for f in findings)

    def test_credit_card(self):
        findings = detect_pii("4111 1111 1111 1111")
        assert any(f[0] == "CREDIT_CARD" for f in findings)

    def test_ip_address(self):
        findings = detect_pii("10.0.0.1")
        assert any(f[0] == "IP_ADDRESS" for f in findings)

    def test_dob(self):
        findings = detect_pii("03/15/1990")
        assert any(f[0] == "DOB" for f in findings)

    def test_mrn(self):
        findings = detect_pii("MRN-00123456")
        assert any(f[0] == "MRN" for f in findings)

    def test_no_pii(self):
        findings = detect_pii("This text has no PII")
        assert len(findings) == 0

    def test_multiple_findings(self):
        findings = detect_pii("SSN: 123-45-6789, Email: a@b.com")
        assert len(findings) >= 2

    def test_findings_have_positions(self):
        findings = detect_pii("SSN: 123-45-6789")
        ssn = [f for f in findings if f[0] == "SSN"][0]
        assert ssn[2] >= 0  # start
        assert ssn[3] > ssn[2]  # end > start
