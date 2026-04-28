"""
Company Resolver - Entity Resolution Pipeline

Dedicated resolution pipeline for company name matching against canonical list.
Separate from person resolution - different normalization, scoring, and semantics.

Match Types:
- EXACT_MATCH: L1 deterministic hit
- FUZZY_MATCH: L2 vector similarity >= 0.85
- POSSIBLE_MATCH: L3 LLM resolved
- NO_MATCH: Below threshold or garbage
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum


class MatchType(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    FUZZY_MATCH = "FUZZY_MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    NO_MATCH = "NO_MATCH"


def get_match_type_for_layer(layer: str, confidence: float) -> str:
    """
    Map resolution layer to match type for company mode.

    Layer mapping:
    - L1_KNOWN_PARENT, L1_EXACT → EXACT_MATCH
    - L2_VECTOR with confidence >= 0.85 → FUZZY_MATCH
    - L2_VECTOR with confidence < 0.85 → POSSIBLE_MATCH
    - L3_LLM → POSSIBLE_MATCH
    - L4_HUMAN → NO_MATCH (needs review)
    - L0_GARBAGE_* → NO_MATCH
    """
    if layer.startswith("L0_GARBAGE"):
        return MatchType.NO_MATCH.value

    if layer in ("L1_KNOWN_PARENT", "L1_EXACT"):
        return MatchType.EXACT_MATCH.value

    if layer == "L2_VECTOR":
        if confidence >= 0.85:
            return MatchType.FUZZY_MATCH.value
        else:
            return MatchType.POSSIBLE_MATCH.value

    if layer.startswith("L3_"):
        return MatchType.POSSIBLE_MATCH.value

    if layer == "L4_HUMAN":
        return MatchType.NO_MATCH.value

    # Default
    return MatchType.NO_MATCH.value


def enrich_company_result_with_match_type(result: Dict) -> Dict:
    """
    Add match_type field to company resolution result.

    Called after resolve_entity_sync() to add compliance categorization.
    """
    layer = result.get("layer", "")
    confidence = result.get("similarity", 0.0)

    result["match_type"] = get_match_type_for_layer(layer, confidence)

    return result


# =============================================================================
# NOTE: Company resolution logic remains in server_enterprise_golden.py
# This module provides:
# 1. MatchType enum for consistency
# 2. get_match_type_for_layer() to classify results
# 3. enrich_company_result_with_match_type() wrapper
#
# The actual resolve_entity_sync() function stays in the main server file
# because it's tightly integrated with:
# - CANONICAL_EMBEDDINGS
# - L3BudgetTracker
# - resolve_with_claude_sync()
# - Firestore audit logging
#
# Future refactoring may extract more, but this maintains stability.
# =============================================================================
