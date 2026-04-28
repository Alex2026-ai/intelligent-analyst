"""
Person Canonicals - Compatibility Shim

This module provides backward compatibility for imports.
All functionality has moved to:
- person_canonical_loader.py (loading from Firestore/CSV/JSON)
- person_resolver.py (resolution pipeline)

NO EMBEDDED SANCTIONS DATA - Watchlists must be loaded from external sources.
"""

from .person_canonical_loader import (
    PersonCanonicalStore,
    PersonCanonicalLoader,
    get_person_store,
    reload_person_store,
)

from .person_resolver import (
    MatchType,
    normalize_person_name,
    extract_last_name,
    extract_first_initial,
    person_l1_match,
    person_l2_fuzzy_match,
    person_l2_resolve,
    resolve_person_sync,
    resolve_person_batch,
)


# Backward compatibility - get store on first access
def get_person_by_id(person_id: str):
    """Get a person record by ID."""
    store = get_person_store()
    return store.get_by_id(person_id)


def get_exact_match(normalized_name: str):
    """Check for exact match in canonical set."""
    store = get_person_store()
    return store.get_exact_match(normalized_name)


def get_alias_match(normalized_name: str):
    """Check for alias match."""
    store = get_person_store()
    return store.get_alias_match(normalized_name)


def get_candidates_by_last_name(last_name: str):
    """Get all persons with a given last name."""
    store = get_person_store()
    return store.get_candidates_by_last_name(last_name)


def get_all_persons():
    """Get all person canonicals."""
    store = get_person_store()
    return store.get_all_persons()


# Deprecated - use get_person_store() instead
PERSON_CANONICALS = []
PERSON_CANONICAL_SET = set()
PERSON_NORMALIZED_LOOKUP = {}
PERSON_ALIAS_LOOKUP = {}
PERSON_LAST_NAME_INDEX = {}
PERSON_ID_LOOKUP = {}
