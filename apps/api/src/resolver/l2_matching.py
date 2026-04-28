"""L2 Matching Engine — precedent-based resolution.

Searches for matching precedents using exact and fuzzy string matching.
Pure function: same input → same output. Zero external dependencies.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from apps.api.src.resolver.base import EvidenceRecord, LayerResult, ResolverConfig
from apps.api.src.resolver.confidence import is_above_l2_match_threshold, l2_confidence

# Layer identifier
L2_LAYER = 2


def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, collapse whitespace, strip punctuation."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _exact_match(
    content_normalized: str, precedents: list[dict[str, Any]]
) -> Optional[tuple[dict[str, Any], float]]:
    """Find an exact match in precedents.

    Returns:
        (precedent, 1.0) if exact match found, None otherwise.
    """
    for precedent in precedents:
        precedent_normalized = _normalize(precedent["content"])
        if content_normalized == precedent_normalized:
            return precedent, 1.0
    return None


def _bigram_set(text: str) -> set[str]:
    """Generate character bigrams for fuzzy matching."""
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _dice_coefficient(a: str, b: str) -> float:
    """Calculate Dice coefficient between two strings.

    Dice = 2 * |intersection| / (|A| + |B|)
    Returns value in [0.0, 1.0].
    """
    bigrams_a = _bigram_set(a)
    bigrams_b = _bigram_set(b)
    if not bigrams_a and not bigrams_b:
        return 1.0
    if not bigrams_a or not bigrams_b:
        return 0.0
    intersection = bigrams_a & bigrams_b
    return 2.0 * len(intersection) / (len(bigrams_a) + len(bigrams_b))


def _fuzzy_match(
    content_normalized: str,
    precedents: list[dict[str, Any]],
    threshold: float,
) -> Optional[tuple[dict[str, Any], float]]:
    """Find the best fuzzy match above threshold.

    Uses Dice coefficient on character bigrams.

    Returns:
        (best_precedent, similarity) if above threshold, None otherwise.
    """
    best_match: Optional[tuple[dict[str, Any], float]] = None
    best_score = 0.0

    for precedent in precedents:
        precedent_normalized = _normalize(precedent["content"])
        score = _dice_coefficient(content_normalized, precedent_normalized)
        if score > best_score:
            best_score = score
            best_match = (precedent, score)

    if best_match and best_score >= threshold:
        return best_match
    return None


def resolve_l2(
    content: str,
    document_type: str,
    metadata: dict[str, Any],
    precedents: list[dict[str, Any]],
    config: ResolverConfig,
) -> Optional[LayerResult]:
    """Apply L2 matching to resolve a document against known precedents.

    Strategy: try exact match first, then fuzzy match. Best match above
    threshold wins.

    Args:
        content: Document content text.
        document_type: Document type classification.
        metadata: Document metadata.
        precedents: List of precedent dicts with 'content' and 'resolution' keys.
        config: Resolver configuration with match threshold.

    Returns:
        LayerResult with confidence based on match quality, None if no match.
    """
    content_normalized = _normalize(content)

    # Try exact match first
    exact = _exact_match(content_normalized, precedents)
    if exact:
        precedent, similarity = exact
        confidence = l2_confidence(similarity)
        evidence = EvidenceRecord(
            node_type="retrieval_result",
            data={
                "step": "l2_exact_match",
                "precedent_id": precedent.get("id", "unknown"),
                "similarity": similarity,
                "match_type": "exact",
            },
        )
        return LayerResult(
            resolution=precedent["resolution"],
            confidence=confidence,
            layer_used=L2_LAYER,
            evidence=[evidence],
        )

    # Try fuzzy match
    fuzzy = _fuzzy_match(content_normalized, precedents, config.l2_match_threshold)
    if fuzzy:
        precedent, similarity = fuzzy
        confidence = l2_confidence(similarity)
        if is_above_l2_match_threshold(similarity, config):
            evidence = EvidenceRecord(
                node_type="retrieval_result",
                data={
                    "step": "l2_fuzzy_match",
                    "precedent_id": precedent.get("id", "unknown"),
                    "similarity": similarity,
                    "match_type": "fuzzy",
                    "threshold": config.l2_match_threshold,
                },
            )
            return LayerResult(
                resolution=precedent["resolution"],
                confidence=confidence,
                layer_used=L2_LAYER,
                evidence=[evidence],
            )

    # No match above threshold
    return None
