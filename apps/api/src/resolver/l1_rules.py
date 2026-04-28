"""L1 Rules Engine — deterministic rule-based resolution.

Rules are data-driven: loaded from a serializable rule set (JSON-compatible dicts),
not hardcoded if-else chains (FP-002, INV-011).

Pure function: same input → same output. Zero external dependencies.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from apps.api.src.resolver.base import EvidenceRecord, LayerResult
from apps.api.src.resolver.confidence import l1_confidence

# Layer identifier
L1_LAYER = 1


def _match_condition(condition: dict[str, Any], content: str, document_type: str) -> bool:
    """Evaluate a single rule condition against the document.

    Supported condition types:
    - document_type_equals: exact match on document type
    - content_contains: case-insensitive substring match on content
    - content_pattern: regex match on content
    - all_of: all sub-conditions must match
    - any_of: at least one sub-condition must match

    Args:
        condition: Rule condition dictionary.
        content: Document content text.
        document_type: Document type string.

    Returns:
        True if the condition matches.
    """
    if "all_of" in condition:
        return all(_match_condition(c, content, document_type) for c in condition["all_of"])
    if "any_of" in condition:
        return any(_match_condition(c, content, document_type) for c in condition["any_of"])
    if "document_type_equals" in condition:
        return document_type == condition["document_type_equals"]
    if "content_contains" in condition:
        return condition["content_contains"].lower() in content.lower()
    if "content_pattern" in condition:
        return bool(re.search(condition["content_pattern"], content, re.IGNORECASE))
    return False


def resolve_l1(
    content: str,
    document_type: str,
    metadata: dict[str, Any],
    rule_set: list[dict[str, Any]],
    rule_set_version: str,
) -> Optional[LayerResult]:
    """Apply L1 deterministic rules to resolve a document.

    Evaluates rules in order. First matching rule wins.

    Args:
        content: Document content text.
        document_type: Document type classification.
        metadata: Document metadata.
        rule_set: Ordered list of rules. Each rule has 'id', 'condition', 'resolution'.
        rule_set_version: Version identifier for the rule set.

    Returns:
        LayerResult with confidence 1.0 if a rule matches, None otherwise.
    """
    for rule in rule_set:
        condition = rule.get("condition", {})
        if _match_condition(condition, content, document_type):
            resolution_text = rule["resolution"]
            evidence = EvidenceRecord(
                node_type="transformation",
                data={
                    "step": "l1_rule_match",
                    "rule_id": rule.get("id", "unknown"),
                    "rule_set_version": rule_set_version,
                    "document_type": document_type,
                    "matched": True,
                },
            )
            return LayerResult(
                resolution=resolution_text,
                confidence=l1_confidence(),
                layer_used=L1_LAYER,
                evidence=[evidence],
            )

    # No rule matched — engine will proceed to L2
    return None
