"""Confidence scoring and threshold evaluation.

All thresholds come from ResolverConfig — never hardcoded (INV-011).
"""

from __future__ import annotations

from apps.api.src.resolver.base import ResolverConfig


def l1_confidence() -> float:
    """L1 deterministic rules always produce confidence 1.0."""
    return 1.0


def l2_confidence(similarity_score: float) -> float:
    """Convert L2 match similarity to a confidence score.

    Args:
        similarity_score: Raw similarity from matching algorithm (0.0-1.0).

    Returns:
        Clamped confidence score in [0.0, 1.0].
    """
    return max(0.0, min(1.0, similarity_score))


def is_below_review_threshold(confidence: float, config: ResolverConfig) -> bool:
    """Check if confidence is below the review routing threshold.

    Args:
        confidence: Resolution confidence score.
        config: Resolver configuration with thresholds.

    Returns:
        True if the resolution should be routed to human review.
    """
    return confidence < config.review_threshold


def is_above_l2_match_threshold(similarity: float, config: ResolverConfig) -> bool:
    """Check if an L2 match similarity is above the acceptance threshold.

    Args:
        similarity: Raw match similarity score.
        config: Resolver configuration with thresholds.

    Returns:
        True if the match should be accepted.
    """
    return similarity >= config.l2_match_threshold
