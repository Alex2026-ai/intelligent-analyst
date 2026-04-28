"""
Person Resolver - Sanctions Screening Pipeline

Dedicated resolution pipeline for person name matching against configured reference data.
Separate from company resolution - different normalization, scoring, and semantics.

Match Types:
- EXACT_MATCH: L1 deterministic hit
- FUZZY_MATCH: L2 score >= 0.92
- POSSIBLE_MATCH: L2 score 0.90-0.92 (eligible for L3 adjudication)
- NO_MATCH: Below threshold or garbage

L3 Adjudication:
- ONLY invoked for POSSIBLE_MATCH cases (score in [0.90, 0.92))
- Never invoked for EXACT_MATCH, FUZZY_MATCH, or NO_MATCH
- Bounded by PERSON_L3_MAX_CALLS per batch
"""

import os
import re
import json
import time
import unicodedata
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field

# Conditional jellyfish import
try:
    import jellyfish
    HAS_JELLYFISH = True
except ImportError:
    HAS_JELLYFISH = False
    print("[person_resolver] WARNING: jellyfish not installed, person L2 fuzzy matching disabled", flush=True)

# Conditional anthropic import
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("[person_resolver] WARNING: anthropic not installed, person L3 LLM disabled", flush=True)

from .person_canonical_loader import get_person_store, PersonCanonicalStore

# API Key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# =============================================================================
# MATCH TYPE ENUM
# =============================================================================

class MatchType(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    FUZZY_MATCH = "FUZZY_MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    NO_MATCH = "NO_MATCH"


# =============================================================================
# CONFIGURATION
# =============================================================================

# Person L2 thresholds (calibrated 2026-02-14)
PERSON_L2_ACCEPT_THRESHOLD = 0.92    # Auto-resolve as FUZZY_MATCH
PERSON_L2_POSSIBLE_THRESHOLD = 0.90  # Possible match, needs review (raised from 0.88)
PERSON_L2_MIN_SCORE = 0.70           # Below this = NO_MATCH

# Scoring weights (must sum to 1.0)
WEIGHT_JARO_WINKLER = 0.50  # Reduced to lower FP
WEIGHT_LAST_NAME = 0.40     # Increased for better last-name matching
WEIGHT_PHONETIC = 0.10

# L1 Initial Match controls (tightened 2026-02-14 to reduce FP)
L1_INITIAL_MIN_LAST_NAME_LENGTH = 6  # Require last name >= 6 chars (avoids Smith, Jones, Brown)
L1_INITIAL_MIN_FIRST_NAME_CHARS = 3  # Require at least 3 chars from first name

# L3 LLM Configuration (enabled for POSSIBLE_MATCH only)
PERSON_L3_ENABLED = os.getenv("PERSON_L3_ENABLED", "true").lower() == "true"
PERSON_L3_MAX_CALLS = int(os.getenv("PERSON_L3_MAX_CALLS", "200"))  # Max L3 calls per batch
PERSON_L3_COST_PER_CALL = float(os.getenv("PERSON_L3_COST_PER_CALL", "0.005"))  # ~$0.005 per call

# Person titles and suffixes to strip
PERSON_TITLES = {
    'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'professor',
    'sir', 'dame', 'lord', 'lady', 'rev', 'reverend',
    'hon', 'honorable', 'judge', 'justice', 'gen', 'general',
    'col', 'colonel', 'maj', 'major', 'capt', 'captain', 'lt', 'lieutenant',
    'sgt', 'sergeant', 'cpl', 'corporal', 'pvt', 'private',
    'adm', 'admiral', 'cmdr', 'commander'
}

PERSON_SUFFIXES = {
    'jr', 'sr', 'i', 'ii', 'iii', 'iv', 'v',
    'phd', 'md', 'dds', 'esq', 'cpa', 'jd', 'llm',
    'mba', 'msc', 'bsc', 'ba', 'ma'
}


# =============================================================================
# L3 BUDGET TRACKER
# =============================================================================

@dataclass
class PersonL3BudgetTracker:
    """
    Track L3 LLM calls for person mode with call cap.

    Separate from company mode budget to enable independent tracking.
    """
    max_calls: int = PERSON_L3_MAX_CALLS
    calls_attempted: int = 0
    calls_succeeded: int = 0  # LLM returned MATCH
    calls_rejected: int = 0   # LLM returned NO_MATCH
    calls_errored: int = 0    # LLM error or timeout
    cost_usd: float = 0.0

    def can_call(self) -> Tuple[bool, Optional[str]]:
        """Check if we can make another L3 call."""
        if not PERSON_L3_ENABLED:
            return False, "L3_DISABLED"
        if not HAS_ANTHROPIC:
            return False, "NO_ANTHROPIC"
        if not ANTHROPIC_API_KEY:
            return False, "NO_API_KEY"
        if self.calls_attempted >= self.max_calls:
            return False, "BUDGET_EXHAUSTED"
        return True, None

    def record_call(self, success: bool, error: bool = False):
        """Record an L3 call result."""
        self.calls_attempted += 1
        self.cost_usd += PERSON_L3_COST_PER_CALL
        if error:
            self.calls_errored += 1
        elif success:
            self.calls_succeeded += 1
        else:
            self.calls_rejected += 1

    def get_yield(self) -> float:
        """Calculate L3 yield (success rate)."""
        if self.calls_attempted == 0:
            return 0.0
        return (self.calls_succeeded / self.calls_attempted) * 100

    def to_dict(self) -> Dict:
        """Return metrics as dict."""
        return {
            "person_l3_max_calls": self.max_calls,
            "person_l3_attempted": self.calls_attempted,
            "person_l3_succeeded": self.calls_succeeded,
            "person_l3_rejected": self.calls_rejected,
            "person_l3_errored": self.calls_errored,
            "person_l3_cost_usd": round(self.cost_usd, 4),
            "person_l3_yield": round(self.get_yield(), 2)
        }


# =============================================================================
# NAME NORMALIZATION
# =============================================================================

def normalize_person_name(name: str) -> str:
    """
    Normalize a person name for matching.

    Steps:
    1. Lowercase, strip whitespace
    2. Remove titles (Mr., Dr., Prof.)
    3. Remove suffixes (Jr., III, PhD)
    4. Normalize accents/diacritics (NFKD)
    5. Handle LAST, FIRST format
    6. Collapse whitespace
    """
    if not name:
        return ""

    # Lowercase and strip
    name = str(name).lower().strip()

    # Remove accents (NFKD decomposition)
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')

    # Remove punctuation except apostrophe and comma
    name = re.sub(r"[^\w\s',]", ' ', name)

    # Split into tokens
    tokens = name.split()
    if not tokens:
        return ""

    # Remove titles from start
    while tokens and tokens[0].rstrip('.') in PERSON_TITLES:
        tokens.pop(0)

    # Remove suffixes from end
    while tokens and tokens[-1].rstrip('.') in PERSON_SUFFIXES:
        tokens.pop()

    if not tokens:
        return ""

    # Handle "LAST, FIRST" format - swap order
    name = ' '.join(tokens)
    if ',' in name:
        parts = name.split(',', 1)
        if len(parts) == 2:
            last = parts[0].strip()
            first = parts[1].strip()
            name = f"{first} {last}"

    # Final cleanup - collapse whitespace
    return ' '.join(name.split())


def extract_last_name(name: str) -> str:
    """
    Extract last name from a normalized name.

    Heuristics:
    - If comma present: before the comma
    - If all caps token: likely last name
    - Otherwise: last token
    """
    if not name:
        return ""

    name = str(name).strip()

    # Handle "LAST, FIRST" format
    if ',' in name:
        return name.split(',')[0].strip().lower()

    tokens = name.split()
    if not tokens:
        return ""

    # Look for all-caps token (common in formal lists)
    for token in tokens:
        if token.isupper() and len(token) > 1:
            return token.lower()

    # Default: last token
    return tokens[-1].lower()


def extract_first_initial(name: str) -> str:
    """Extract first initial from normalized name."""
    name = normalize_person_name(name)
    if not name:
        return ""
    tokens = name.split()
    if tokens:
        return tokens[0][0].lower() if tokens[0] else ""
    return ""


# =============================================================================
# L1 DETERMINISTIC MATCHING
# =============================================================================

def person_l1_match(name: str, store: PersonCanonicalStore) -> Optional[Tuple[Dict, str, MatchType]]:
    """
    L1 Deterministic person matching.

    Strategies (in order):
    1. Exact normalized match against canonical set
    2. Alias match
    3. Last name + first initial match

    Returns: (person_record, layer, match_type) or None
    """
    normalized = normalize_person_name(name)
    if not normalized:
        return None

    # Strategy 1: Exact match on canonical name
    exact = store.get_exact_match(normalized)
    if exact:
        return (exact, "L1_PERSON_EXACT", MatchType.EXACT_MATCH)

    # Strategy 2: Alias match
    alias = store.get_alias_match(normalized)
    if alias:
        return (alias, "L1_PERSON_ALIAS", MatchType.EXACT_MATCH)

    # Strategy 3: Last name + first name prefix (stricter than just initial)
    last_name = extract_last_name(name)
    normalized_tokens = normalized.split()

    # Only attempt initial match for:
    # - Last names >= 5 chars (avoid common short names)
    # - Multi-token inputs (avoid matching single names)
    if last_name and len(last_name) >= L1_INITIAL_MIN_LAST_NAME_LENGTH and len(normalized_tokens) >= 2:
        candidates = store.get_candidates_by_last_name(last_name)

        # Get first name from input (not just initial)
        input_first = normalized_tokens[0] if normalized_tokens else ""

        for candidate in candidates:
            cand_first = candidate.get("first_name", "").lower()
            cand_last = candidate.get("last_name", "").lower()

            # Require exact last name match (case-insensitive)
            if cand_last != last_name:
                continue

            # Require at least first 2 characters of first name match
            # This prevents "P. Johnson" matching "Prince Johnson" (P != Pr)
            if cand_first and input_first:
                match_len = min(L1_INITIAL_MIN_FIRST_NAME_CHARS, len(input_first), len(cand_first))
                if input_first[:match_len] == cand_first[:match_len]:
                    return (candidate, "L1_PERSON_INITIAL", MatchType.EXACT_MATCH)

    return None


# =============================================================================
# L2 FUZZY MATCHING
# =============================================================================

def compute_person_similarity(name1: str, name2: str, store: PersonCanonicalStore) -> Tuple[float, Dict]:
    """
    Compute weighted similarity score between two person names.

    Scoring formula:
    score = (jaro_winkler * 0.60) + (last_name_match * 0.30) + (phonetic_bonus * 0.10)

    Returns: (score, details_dict)
    """
    if not HAS_JELLYFISH:
        return 0.0, {"error": "jellyfish not installed"}

    norm1 = normalize_person_name(name1)
    norm2 = normalize_person_name(name2)

    if not norm1 or not norm2:
        return 0.0, {"error": "empty after normalization"}

    # Component 1: Jaro-Winkler similarity (0.0 - 1.0)
    jw_score = jellyfish.jaro_winkler_similarity(norm1, norm2)

    # Component 2: Last name match (0.0 - 1.0)
    last1 = extract_last_name(name1)
    last2 = extract_last_name(name2)
    if last1 and last2:
        last_name_score = jellyfish.jaro_winkler_similarity(last1, last2)
    else:
        last_name_score = 0.0

    # Component 3: Phonetic bonus (0.0 or 1.0)
    phonetic_score = 0.0
    try:
        soundex1 = jellyfish.soundex(norm1.replace(' ', ''))
        soundex2 = jellyfish.soundex(norm2.replace(' ', ''))
        if soundex1 == soundex2:
            phonetic_score = 1.0
        else:
            # Check metaphone as fallback
            meta1 = jellyfish.metaphone(norm1.replace(' ', ''))
            meta2 = jellyfish.metaphone(norm2.replace(' ', ''))
            if meta1 == meta2:
                phonetic_score = 0.5
    except Exception:
        phonetic_score = 0.0

    # Weighted score
    total_score = (
        (jw_score * WEIGHT_JARO_WINKLER) +
        (last_name_score * WEIGHT_LAST_NAME) +
        (phonetic_score * WEIGHT_PHONETIC)
    )

    details = {
        "jaro_winkler": round(jw_score, 4),
        "last_name_score": round(last_name_score, 4),
        "phonetic_score": round(phonetic_score, 4),
        "weighted_total": round(total_score, 4)
    }

    return total_score, details


def person_l2_fuzzy_match(name: str, store: PersonCanonicalStore, top_n: int = 5) -> List[Tuple[Dict, float, Dict]]:
    """
    L2 Fuzzy matching for person names.

    Scans all candidates with matching last name and computes weighted similarity.

    Returns: [(person_record, score, details), ...] sorted by score descending
    """
    if not HAS_JELLYFISH:
        return []

    last_name = extract_last_name(name)
    if not last_name:
        # Fall back to scanning all (expensive but thorough)
        candidates = store.get_all_persons()
    else:
        # Start with same-last-name candidates
        candidates = store.get_candidates_by_last_name(last_name)

        # If no matches, expand to all
        if not candidates:
            candidates = store.get_all_persons()

    results = []
    for candidate in candidates:
        canonical = candidate.get("canonical_name", "")
        if not canonical:
            continue

        score, details = compute_person_similarity(name, canonical, store)

        if score >= PERSON_L2_MIN_SCORE:
            results.append((candidate, score, details))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)

    return results[:top_n]


def person_l2_resolve(name: str, store: PersonCanonicalStore) -> Optional[Tuple[Dict, float, str, MatchType]]:
    """
    L2 resolution with threshold-based match type assignment.

    Returns: (person_record, score, layer, match_type) or None
    """
    matches = person_l2_fuzzy_match(name, store, top_n=5)

    if not matches:
        return None

    top_match, top_score, details = matches[0]

    if top_score >= PERSON_L2_ACCEPT_THRESHOLD:
        return (top_match, top_score, "L2_PERSON_FUZZY", MatchType.FUZZY_MATCH)
    elif top_score >= PERSON_L2_POSSIBLE_THRESHOLD:
        return (top_match, top_score, "L2_PERSON_FUZZY", MatchType.POSSIBLE_MATCH)
    else:
        # Below threshold - still return for audit but mark as NO_MATCH
        return (top_match, top_score, "L2_PERSON_FUZZY", MatchType.NO_MATCH)


# =============================================================================
# L3 LLM ADJUDICATION (POSSIBLE_MATCH ONLY)
# =============================================================================

def person_l3_adjudicate(
    input_name: str,
    candidates: List[Tuple[Dict, float, Dict]],
    budget_tracker: Optional[PersonL3BudgetTracker] = None
) -> Optional[Dict]:
    """
    L3 LLM adjudication for POSSIBLE_MATCH cases only.

    GATING RULES:
    - ONLY called when match_type == POSSIBLE_MATCH
    - NEVER called for EXACT_MATCH, FUZZY_MATCH, or NO_MATCH
    - Bounded by PERSON_L3_MAX_CALLS per batch

    Input:
    - input_name: The name being screened
    - candidates: Top N candidates from L2 [(record, score, details), ...]
    - budget_tracker: Optional tracker for L3 calls

    Output:
    - Dict with decision, selected_id, confidence, reason
    - None if L3 unavailable or budget exhausted

    LLM Contract:
    - Can ONLY pick from provided candidates
    - If unsure → NO_MATCH
    - Never invents new entities
    """
    # Check budget
    if budget_tracker:
        can_call, reason = budget_tracker.can_call()
        if not can_call:
            print(f"[PERSON_L3] Skipped: {reason}", flush=True)
            return None
    elif not PERSON_L3_ENABLED or not HAS_ANTHROPIC or not ANTHROPIC_API_KEY:
        return None

    if not candidates:
        return None

    # Build candidate list for prompt
    candidate_lines = []
    for i, (record, score, details) in enumerate(candidates[:5]):
        canonical = record.get("canonical_name", "")
        record_id = record.get("id", "")
        aliases = record.get("aliases", [])[:3]  # Max 3 aliases
        alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
        candidate_lines.append(f"  {i+1}. ID={record_id}: {canonical}{alias_str} [score={score:.2f}]")

    candidate_text = '\n'.join(candidate_lines)

    prompt = f"""You are a reference-data matching reviewer adjudicating an ambiguous name match.

INPUT NAME: "{input_name}"

CANDIDATE MATCHES (pick ONLY from this list):
{candidate_text}

TASK: Determine if the input name matches any of the candidates.

RULES:
1. You may ONLY select from the provided candidates
2. Consider name variations: spelling, transliteration, nicknames, aliases
3. If the input clearly matches a candidate → decision: "MATCH"
4. If unsure or no clear match → decision: "NO_MATCH"
5. NEVER invent or guess entities not in the list
6. Err on the side of caution when the match is ambiguous

RESPOND WITH EXACTLY THIS JSON FORMAT (no other text):
{{
  "decision": "MATCH" or "NO_MATCH",
  "selected_id": "the_candidate_id_or_null",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation"
}}"""

    # L3 call via llm_router (retry + soft failover handled inside)
    try:
        from app.llm_router import call_l3_with_failover

        llm_result = call_l3_with_failover(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )

        response_text = llm_result.text.strip()

        # Parse JSON response
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result = json.loads(response_text)

        decision = result.get("decision", "NO_MATCH").upper()
        selected_id = result.get("selected_id")
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "")

        # Validate decision
        if decision not in ["MATCH", "NO_MATCH"]:
            decision = "NO_MATCH"

        # If MATCH, verify selected_id is in candidates
        selected_record = None
        if decision == "MATCH" and selected_id:
            for record, score, details in candidates:
                if record.get("id") == selected_id:
                    selected_record = record
                    break

            if not selected_record:
                # LLM hallucinated an ID - reject
                print(f"[PERSON_L3] Rejected hallucinated ID: {selected_id}", flush=True)
                decision = "NO_MATCH"
                selected_id = None
                confidence = 0.0
                reason = "Invalid candidate ID"

        # Record call
        if budget_tracker:
            budget_tracker.record_call(success=(decision == "MATCH"))

        print(f"[PERSON_L3] '{input_name}' → {decision} (id={selected_id}, conf={confidence:.2f})", flush=True)

        return {
            "decision": decision,
            "selected_id": selected_id,
            "selected_record": selected_record,
            "confidence": confidence,
            "reason": reason,
            "layer": "L3_PERSON_LLM",
            "model_used": llm_result.model_used,
            "provider_used": llm_result.provider_used,
            "failover_used": llm_result.failover_used,
        }

    except json.JSONDecodeError as e:
        print(f"[PERSON_L3] JSON parse error: {e}", flush=True)
        if budget_tracker:
            budget_tracker.record_call(success=False, error=True)
        return None

    except Exception as e:
        print(f"[PERSON_L3] Error: {e}", flush=True)
        if budget_tracker:
            budget_tracker.record_call(success=False, error=True)
        return None


# =============================================================================
# MAIN RESOLUTION FUNCTION
# =============================================================================

def resolve_person_sync(
    name_raw: str,
    tenant_id: str,
    batch_trace_id: str,
    idx: int,
    store: Optional[PersonCanonicalStore] = None,
    budget_tracker: Optional[PersonL3BudgetTracker] = None,
    allow_l3: bool = True
) -> Dict:
    """
    Main person resolution pipeline.

    Pipeline: L0 Garbage → L1 Deterministic → L2 Fuzzy → L3 (POSSIBLE only) → L4 Human

    L3 GATING:
    - L3 is ONLY invoked when L2 returns POSSIBLE_MATCH (score in [0.90, 0.92))
    - L3 is NEVER invoked for EXACT_MATCH, FUZZY_MATCH, or NO_MATCH
    - L3 is bounded by PERSON_L3_MAX_CALLS per batch

    Returns:
    {
        "original": str,
        "normalized_input": str,
        "resolved": canonical_name or None,
        "match_id": "SDN-12345" or None,
        "match_type": "EXACT_MATCH" | "FUZZY_MATCH" | "POSSIBLE_MATCH" | "NO_MATCH",
        "confidence": float,
        "layer": "L0_GARBAGE" | "L1_PERSON_*" | "L2_PERSON_FUZZY" | "L3_PERSON_LLM" | "L4_HUMAN",
        "top_candidates": [...],
        "similarity_scores": {...},
        "source": str (watchlist source),
        "matched_sources": ["OFAC", "UN", "EU"],  # Multi-source evidence
        "matched_source_ids": ["SDN-123", "UN-456"],  # Source-specific IDs
        "l3_result": {...} (if L3 was invoked)
    }
    """
    if store is None:
        store = get_person_store()

    name_raw = str(name_raw).strip() if name_raw else ""
    normalized = normalize_person_name(name_raw)

    # Base result with multi-source evidence fields
    result = {
        "original": name_raw,
        "normalized_input": normalized,
        "resolved": None,
        "match_id": None,
        "match_type": MatchType.NO_MATCH.value,
        "confidence": 0.0,
        "layer": "L4_HUMAN",
        "top_candidates": [],
        "similarity_scores": {},
        "source": store.source,
        "matched_sources": [],  # List of sources where match found
        "matched_source_ids": [],  # List of source-specific IDs
        "watchlist_version": store.version_hash if hasattr(store, 'version_hash') else ""
    }

    # L0: Garbage detection
    if not name_raw or len(name_raw) < 2:
        result["layer"] = "L0_GARBAGE_SHORT"
        result["match_type"] = MatchType.NO_MATCH.value
        return result

    if name_raw.replace('.', '').replace('-', '').isdigit():
        result["layer"] = "L0_GARBAGE_NUMERIC"
        result["match_type"] = MatchType.NO_MATCH.value
        return result

    # Check if store has data
    if not store.is_loaded():
        result["layer"] = "L4_HUMAN"
        result["match_type"] = MatchType.NO_MATCH.value
        result["similarity_scores"] = {"error": "no watchlist loaded"}
        return result

    # L1: Deterministic matching (EXACT_MATCH - never send to L3)
    l1_result = person_l1_match(name_raw, store)
    if l1_result:
        person, layer, match_type = l1_result
        result["resolved"] = person.get("canonical_name")
        result["match_id"] = person.get("id")
        result["match_type"] = match_type.value
        result["confidence"] = 1.0
        result["layer"] = layer
        result["source"] = person.get("source", store.source)
        # Multi-source evidence
        sources_list = person.get("sources", [])
        if sources_list:
            result["matched_sources"] = list(set(s.get("source", "") for s in sources_list))
            result["matched_source_ids"] = [s.get("source_id", "") for s in sources_list]
        else:
            result["matched_sources"] = [person.get("source", "UNKNOWN")]
            result["matched_source_ids"] = [person.get("id", "")]
        # L1 hit = EXACT_MATCH → skip L3 entirely
        return result

    # L2: Fuzzy matching
    l2_matches = person_l2_fuzzy_match(name_raw, store, top_n=5)

    if l2_matches:
        # Store top candidates for audit
        result["top_candidates"] = [
            {
                "name": m[0].get("canonical_name"),
                "id": m[0].get("id"),
                "score": round(m[1], 4),
                "details": m[2]
            }
            for m in l2_matches
        ]

        top_match, top_score, top_details = l2_matches[0]
        result["similarity_scores"] = top_details

        if top_score >= PERSON_L2_ACCEPT_THRESHOLD:
            # High confidence fuzzy match (FUZZY_MATCH - never send to L3)
            result["resolved"] = top_match.get("canonical_name")
            result["match_id"] = top_match.get("id")
            result["match_type"] = MatchType.FUZZY_MATCH.value
            result["confidence"] = top_score
            result["layer"] = "L2_PERSON_FUZZY"
            result["source"] = top_match.get("source", store.source)
            # Multi-source evidence
            sources_list = top_match.get("sources", [])
            if sources_list:
                result["matched_sources"] = list(set(s.get("source", "") for s in sources_list))
                result["matched_source_ids"] = [s.get("source_id", "") for s in sources_list]
            else:
                result["matched_sources"] = [top_match.get("source", "UNKNOWN")]
                result["matched_source_ids"] = [top_match.get("id", "")]
            return result

        elif top_score >= PERSON_L2_POSSIBLE_THRESHOLD:
            # POSSIBLE_MATCH → eligible for L3 adjudication
            result["resolved"] = top_match.get("canonical_name")
            result["match_id"] = top_match.get("id")
            result["match_type"] = MatchType.POSSIBLE_MATCH.value
            result["confidence"] = top_score
            result["layer"] = "L4_HUMAN"  # Default to human review
            # Multi-source evidence (for possible match)
            sources_list = top_match.get("sources", [])
            if sources_list:
                result["matched_sources"] = list(set(s.get("source", "") for s in sources_list))
                result["matched_source_ids"] = [s.get("source_id", "") for s in sources_list]
            else:
                result["matched_sources"] = [top_match.get("source", "UNKNOWN")]
                result["matched_source_ids"] = [top_match.get("id", "")]

            # L3 ADJUDICATION: Only for POSSIBLE_MATCH
            if allow_l3 and PERSON_L3_ENABLED:
                l3_result = person_l3_adjudicate(name_raw, l2_matches, budget_tracker)

                if l3_result:
                    result["l3_result"] = l3_result

                    if l3_result.get("decision") == "MATCH":
                        # L3 confirmed match
                        selected_record = l3_result.get("selected_record")
                        if selected_record:
                            result["resolved"] = selected_record.get("canonical_name")
                            result["match_id"] = selected_record.get("id")
                            result["match_type"] = MatchType.FUZZY_MATCH.value  # Upgrade to FUZZY_MATCH
                            result["confidence"] = l3_result.get("confidence", 0.85)
                            result["layer"] = "L3_PERSON_LLM"
                            result["source"] = selected_record.get("source", store.source)
                            # Multi-source evidence for L3 match
                            sources_list = selected_record.get("sources", [])
                            if sources_list:
                                result["matched_sources"] = list(set(s.get("source", "") for s in sources_list))
                                result["matched_source_ids"] = [s.get("source_id", "") for s in sources_list]
                            else:
                                result["matched_sources"] = [selected_record.get("source", "UNKNOWN")]
                                result["matched_source_ids"] = [selected_record.get("id", "")]
                            print(f"[PERSON_L3] Resolved: '{name_raw}' → '{result['resolved']}'", flush=True)
                            return result
                    else:
                        # L3 rejected → downgrade to NO_MATCH
                        result["match_type"] = MatchType.NO_MATCH.value
                        result["layer"] = "L3_PERSON_LLM_REJECT"
                        result["confidence"] = 0.0
                        result["resolved"] = None
                        result["match_id"] = None
                        print(f"[PERSON_L3] Rejected: '{name_raw}' (reason: {l3_result.get('reason')})", flush=True)
                        return result

            # L3 not available or budget exhausted → route to L4
            return result

    # Below POSSIBLE threshold → NO_MATCH (never send to L3)
    result["layer"] = "L4_HUMAN"
    result["match_type"] = MatchType.NO_MATCH.value
    return result


# =============================================================================
# BATCH RESOLUTION
# =============================================================================

def resolve_person_batch(
    names: List[str],
    tenant_id: str,
    batch_trace_id: str,
    store: Optional[PersonCanonicalStore] = None,
    allow_l3: bool = True
) -> Tuple[List[Dict], PersonL3BudgetTracker]:
    """
    Resolve a batch of person names with L3 budget tracking.

    L3 is ONLY invoked for POSSIBLE_MATCH cases and bounded by PERSON_L3_MAX_CALLS.

    Returns:
    - List of resolution results
    - PersonL3BudgetTracker with call metrics
    """
    if store is None:
        store = get_person_store()

    # Initialize budget tracker for this batch
    budget_tracker = PersonL3BudgetTracker(max_calls=PERSON_L3_MAX_CALLS)

    results = []
    for idx, name in enumerate(names):
        result = resolve_person_sync(
            name, tenant_id, batch_trace_id, idx,
            store=store,
            budget_tracker=budget_tracker,
            allow_l3=allow_l3
        )
        results.append(result)

    # Log batch summary
    if budget_tracker.calls_attempted > 0:
        print(f"[PERSON_L3] Batch {batch_trace_id} summary: "
              f"attempted={budget_tracker.calls_attempted}, "
              f"succeeded={budget_tracker.calls_succeeded}, "
              f"rejected={budget_tracker.calls_rejected}, "
              f"yield={budget_tracker.get_yield():.1f}%", flush=True)

    return results, budget_tracker


def create_person_l3_budget_tracker() -> PersonL3BudgetTracker:
    """Create a new L3 budget tracker for external use."""
    return PersonL3BudgetTracker(max_calls=PERSON_L3_MAX_CALLS)
