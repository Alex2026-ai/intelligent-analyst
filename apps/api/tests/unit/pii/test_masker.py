"""Tests for PII masker — all categories detected and masked."""

from apps.api.src.pii.masker import PIIMasker


SYNTHETIC_PII_DOC = (
    "Patient John Smith (SSN: 123-45-6789) was seen on 03/15/1990. "
    "Contact: john.smith@hospital.org or (555) 123-4567. "
    "Credit card: 4111 1111 1111 1111. IP: 192.168.1.100. "
    "MRN: MRN-00123456."
)


class TestPIIMasker:
    def test_masks_ssn(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask("SSN: 123-45-6789")
        assert "123-45-6789" not in masked
        assert "SSN" in cats

    def test_masks_email(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask("Email: john@example.com")
        assert "john@example.com" not in masked
        assert "EMAIL" in cats

    def test_masks_phone(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask("Phone: (555) 123-4567")
        assert "(555) 123-4567" not in masked
        assert "PHONE" in cats

    def test_masks_credit_card(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask("Card: 4111 1111 1111 1111")
        assert "4111" not in masked
        assert "CREDIT_CARD" in cats

    def test_masks_ip_address(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask("IP: 192.168.1.100")
        assert "192.168.1.100" not in masked
        assert "IP_ADDRESS" in cats

    def test_masks_dob(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask("DOB: 03/15/1990")
        assert "03/15/1990" not in masked
        assert "DOB" in cats

    def test_masks_mrn(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask("MRN: MRN-00123456")
        assert "MRN-00123456" not in masked
        assert "MRN" in cats

    def test_multiple_categories(self):
        masker = PIIMasker()
        masked, vault, cats = masker.mask(SYNTHETIC_PII_DOC)
        assert len(cats) >= 5  # SSN, EMAIL, PHONE, CC, IP, DOB, MRN

    def test_no_pii_passes_through(self):
        masker = PIIMasker()
        text = "This document has no PII content whatsoever."
        masked, vault, cats = masker.mask(text)
        assert masked == text
        assert len(cats) == 0

    def test_get_report(self):
        masker = PIIMasker()
        _, vault, cats = masker.mask("SSN: 123-45-6789, Email: a@b.com")
        report = masker.get_report(vault, cats)
        assert report.token_count >= 2
        assert report.masking_version == "1.0"
