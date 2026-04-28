"""Reversible PII tokenization — mask before external calls, unmask after.

Every character of content is scanned. This is NOT optional (INV-006).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from apps.api.src.pii.patterns import detect_pii
from apps.api.src.pii.vault import PIIVault


@dataclass(frozen=True)
class MaskingResult:
    """Result of PII tokenization."""
    masked_text: str
    vault: PIIVault
    categories_found: set[str] = field(default_factory=set)
    token_count: int = 0


def mask_pii(text: str, vault: PIIVault | None = None) -> MaskingResult:
    """Detect and replace all PII in text with tokens.

    Args:
        text: Document content to scan.
        vault: Optional existing vault (creates new if None).

    Returns:
        MaskingResult with masked text, vault, and metadata.
    """
    vault = vault or PIIVault()
    findings = detect_pii(text)

    if not findings:
        return MaskingResult(
            masked_text=text,
            vault=vault,
            categories_found=set(),
            token_count=0,
        )

    # Replace from end to start to preserve positions
    result = text
    categories: set[str] = set()
    replaced_ranges: list[tuple[int, int]] = []

    # Deduplicate overlapping ranges (keep longest)
    non_overlapping = _deduplicate_ranges(findings)

    for category, original, start, end in reversed(non_overlapping):
        token = vault.store(category, original)
        result = result[:start] + token + result[end:]
        categories.add(category)

    return MaskingResult(
        masked_text=result,
        vault=vault,
        categories_found=categories,
        token_count=vault.token_count,
    )


def unmask_pii(masked_text: str, vault: PIIVault) -> str:
    """Replace tokens in text with original PII values.

    Called after receiving LLM response to restore PII.

    Args:
        masked_text: Text containing tokens like [SSN_1].
        vault: The vault from the masking step.

    Returns:
        Text with tokens replaced by original PII values.
    """
    result = masked_text
    token_pattern = re.compile(r"\[[A-Z_]+_\d+\]")
    for match in token_pattern.finditer(masked_text):
        token = match.group()
        original = vault.restore(token)
        if original is not None:
            result = result.replace(token, original)
    return result


def _deduplicate_ranges(
    findings: list[tuple[str, str, int, int]],
) -> list[tuple[str, str, int, int]]:
    """Remove overlapping PII detections, keeping the longest match."""
    if not findings:
        return []
    result: list[tuple[str, str, int, int]] = []
    for finding in findings:
        _, _, start, end = finding
        overlaps = False
        for _, _, rs, re_ in result:
            if start < re_ and end > rs:
                overlaps = True
                break
        if not overlaps:
            result.append(finding)
    return result
