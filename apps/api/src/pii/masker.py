"""PII masker — high-level API for masking document content before external calls.

Combines detection, tokenization, and vault management (INV-006).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.api.src.pii.tokenizer import MaskingResult, mask_pii, unmask_pii
from apps.api.src.pii.vault import PIIVault


@dataclass(frozen=True)
class MaskingReport:
    """Report of PII masking for evidence chain."""
    categories_found: list[str]
    token_count: int
    masking_version: str = "1.0"


class PIIMasker:
    """High-level PII masker for document content.

    Usage:
        masker = PIIMasker()
        masked, vault = masker.mask(content)
        # Send masked content to LLM
        llm_response = await llm.call(masked)
        # Restore PII in response
        restored = masker.unmask(llm_response, vault)
        # Get report for evidence chain
        report = masker.get_report(vault, categories)
    """

    def mask(self, content: str) -> tuple[str, PIIVault, set[str]]:
        """Mask all PII in content.

        Returns:
            (masked_content, vault, categories_found)
        """
        result = mask_pii(content)
        return result.masked_text, result.vault, result.categories_found

    def unmask(self, text: str, vault: PIIVault) -> str:
        """Restore PII tokens in text using the vault."""
        return unmask_pii(text, vault)

    @staticmethod
    def get_report(vault: PIIVault, categories: set[str]) -> MaskingReport:
        """Generate a masking report for the evidence chain."""
        return MaskingReport(
            categories_found=sorted(categories),
            token_count=vault.token_count,
        )
