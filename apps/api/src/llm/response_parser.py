"""Parse and validate LLM responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedResponse:
    """Parsed and validated LLM response."""
    resolution: str
    confidence: float
    valid: bool
    error: str = ""


def parse_llm_response(raw_response: str, confidence: float) -> ParsedResponse:
    """Parse and validate an LLM response.

    Args:
        raw_response: The text response from the LLM.
        confidence: Confidence score from the LLM.

    Returns:
        ParsedResponse with validation status.
    """
    if not raw_response or not raw_response.strip():
        return ParsedResponse(
            resolution="", confidence=0.0, valid=False, error="Empty response"
        )

    if confidence < 0.0 or confidence > 1.0:
        return ParsedResponse(
            resolution=raw_response,
            confidence=max(0.0, min(1.0, confidence)),
            valid=False,
            error=f"Confidence {confidence} out of range [0.0, 1.0]",
        )

    return ParsedResponse(
        resolution=raw_response.strip(),
        confidence=confidence,
        valid=True,
    )
