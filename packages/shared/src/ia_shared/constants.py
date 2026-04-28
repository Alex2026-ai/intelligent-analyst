"""Shared constants for Intelligent Analyst.

All behavioral thresholds are defined here — never hardcoded in application logic (INV-011).
"""

# --- Batch limits ---
MAX_BATCH_SIZE: int = 100
"""Maximum documents per batch request."""

MAX_BATCH_PARALLEL: int = 10
"""Maximum parallel resolution workers per batch."""

DEFAULT_BATCH_PARALLEL: int = 5
"""Default parallel resolution workers per batch."""

# --- Content limits ---
MAX_DOCUMENT_CONTENT_BYTES: int = 50 * 1024
"""Maximum document content size in bytes (50KB)."""

# --- Pagination ---
DEFAULT_PAGE_SIZE: int = 50
"""Default number of results per page."""

MAX_PAGE_SIZE: int = 200
"""Maximum number of results per page."""

# --- Confidence ---
MIN_CONFIDENCE: float = 0.0
"""Minimum confidence score."""

MAX_CONFIDENCE: float = 1.0
"""Maximum confidence score."""

# --- Review ---
MIN_REVIEW_NOTES_LENGTH: int = 10
"""Minimum character length for review decision notes."""

# --- Export ---
EXPORT_URL_TTL_SECONDS: int = 900
"""Signed download URL time-to-live (15 minutes)."""

# --- Schema ---
SCHEMA_VERSION: str = "1.0"
"""Current schema version for storable models."""

# --- Events ---
EVENT_VERSION: str = "1.0"
"""Current event schema version."""

# --- Resolution layers ---
LAYER_L1: int = 1
"""Layer 1 — deterministic matching."""

LAYER_L2: int = 2
"""Layer 2 — vector similarity."""

LAYER_L3: int = 3
"""Layer 3 — LLM reasoning."""

LAYER_L4: int = 4
"""Layer 4 — human review."""
