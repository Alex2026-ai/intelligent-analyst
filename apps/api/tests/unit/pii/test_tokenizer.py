"""Tests for reversible tokenization — round-trip PII masking."""

from apps.api.src.pii.tokenizer import mask_pii, unmask_pii
from apps.api.src.pii.vault import PIIVault


class TestTokenizerRoundTrip:
    def test_mask_and_unmask_ssn(self):
        text = "SSN is 123-45-6789"
        result = mask_pii(text)
        assert "123-45-6789" not in result.masked_text
        restored = unmask_pii(result.masked_text, result.vault)
        assert "123-45-6789" in restored

    def test_mask_and_unmask_email(self):
        text = "Contact: user@example.com"
        result = mask_pii(text)
        assert "user@example.com" not in result.masked_text
        restored = unmask_pii(result.masked_text, result.vault)
        assert "user@example.com" in restored

    def test_multiple_pii_round_trip(self):
        text = "SSN: 123-45-6789, Email: a@b.com, Phone: 555-123-4567"
        result = mask_pii(text)
        assert "123-45-6789" not in result.masked_text
        assert "a@b.com" not in result.masked_text
        restored = unmask_pii(result.masked_text, result.vault)
        assert "123-45-6789" in restored
        assert "a@b.com" in restored

    def test_duplicate_pii_same_token(self):
        text = "SSN 123-45-6789 repeated: 123-45-6789"
        result = mask_pii(text)
        assert result.token_count == 1  # Same value → same token

    def test_no_pii_unchanged(self):
        text = "No PII here"
        result = mask_pii(text)
        assert result.masked_text == text
        assert result.token_count == 0

    def test_llm_response_with_tokens_restored(self):
        """Simulate LLM returning tokens — they get restored."""
        text = "Patient SSN: 123-45-6789"
        result = mask_pii(text)
        # Simulate LLM echoing the token
        llm_response = f"The patient with {result.masked_text.split('SSN: ')[1].split()[0]} needs review"
        restored = unmask_pii(llm_response, result.vault)
        assert "123-45-6789" in restored
