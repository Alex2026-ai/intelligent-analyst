"""Security test: verify LLM receives ZERO PII — only tokens."""

from apps.api.src.pii.masker import PIIMasker


SYNTHETIC_PII_DOC = (
    "Patient John Smith (SSN: 123-45-6789) visited on 03/15/1990. "
    "Email: john.smith@hospital.org. Phone: (555) 123-4567. "
    "Credit card: 4111 1111 1111 1111. MRN: MRN-00123456."
)

PII_VALUES = [
    "123-45-6789",
    "john.smith@hospital.org",
    "(555) 123-4567",
    "4111 1111 1111 1111",
    "MRN-00123456",
    "03/15/1990",
]


class TestPIINotInLLMCalls:
    def test_masked_content_has_zero_pii(self):
        """The masked content sent to LLM must contain NO PII values."""
        masker = PIIMasker()
        masked, vault, categories = masker.mask(SYNTHETIC_PII_DOC)

        for pii_value in PII_VALUES:
            assert pii_value not in masked, (
                f"PII value '{pii_value}' found in masked content that would be sent to LLM"
            )

    def test_masked_content_contains_tokens(self):
        """Masked content should have tokens like [SSN_1], [EMAIL_1]."""
        masker = PIIMasker()
        masked, _, _ = masker.mask(SYNTHETIC_PII_DOC)
        assert "[" in masked and "]" in masked

    def test_round_trip_preserves_content(self):
        """After unmasking LLM response, all PII should be restored."""
        masker = PIIMasker()
        masked, vault, _ = masker.mask(SYNTHETIC_PII_DOC)

        # Simulate LLM returning masked content
        llm_response = f"Analysis of document: {masked}"
        restored = masker.unmask(llm_response, vault)

        for pii_value in PII_VALUES:
            assert pii_value in restored, (
                f"PII value '{pii_value}' not restored after round-trip"
            )
