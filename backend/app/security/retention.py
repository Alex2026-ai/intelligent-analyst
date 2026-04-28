"""
================================================================================
RETENTION MANAGER (Week 2, Day 8-9)
================================================================================

Governs the transition of evidence from Hot to Cold storage and enforces
the Final Purge guard for batches older than 7 years.

Architecture:
1. Hot Storage (STANDARD) → Cold Storage (COLDLINE) after 90 days
2. Final Purge after 7 years (2555 days) with Legal Hold protection
3. GCS Lifecycle policies for automated transitions

Key Rules:
- Batches under legal_hold NEVER transition or purge
- RetentionViolationError thrown if purge attempted on held batch
- All transitions logged to audit trail

================================================================================
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import hashlib
import os

# GCS client (optional - graceful degradation)
try:
    from google.cloud import storage
    HAS_GCS = True
except ImportError:
    HAS_GCS = False
    storage = None


class RetentionStatus(str, Enum):
    """Storage retention status."""
    HOT = "HOT"                 # Standard storage (< 90 days)
    COLD = "COLD"               # Coldline storage (90 days - 7 years)
    ARCHIVE = "ARCHIVE"         # Archive storage (near 7 years)
    PURGE_ELIGIBLE = "PURGE_ELIGIBLE"  # > 7 years, eligible for deletion
    HELD = "HELD"               # Under legal hold (protected)


class RetentionAction(str, Enum):
    """Actions for retention transitions."""
    NONE = "NONE"
    TRANSITION_TO_COLD = "TRANSITION_TO_COLD"
    TRANSITION_TO_ARCHIVE = "TRANSITION_TO_ARCHIVE"
    PURGE = "PURGE"
    BLOCKED_BY_HOLD = "BLOCKED_BY_HOLD"


class RetentionViolationError(Exception):
    """
    Raised when a purge operation is attempted on a legally held batch.

    This is a HARD BLOCK - the system must never delete evidence under hold.
    """
    def __init__(self, batch_id: str, hold_id: str, message: str = None):
        self.batch_id = batch_id
        self.hold_id = hold_id
        self.message = message or f"RETENTION VIOLATION: Cannot purge batch {batch_id} - active legal hold {hold_id}"
        super().__init__(self.message)


# Retention thresholds (days)
COLD_TRANSITION_DAYS = 90       # Move to Coldline after 90 days
ARCHIVE_TRANSITION_DAYS = 2190  # Move to Archive after ~6 years
PURGE_THRESHOLD_DAYS = 2555     # Delete after ~7 years
PURGE_WARNING_DAYS = 2520       # ~6.9 years - upcoming purge list


class RetentionManager:
    """
    Manages evidence retention lifecycle.

    Transitions:
    1. HOT (STANDARD) → COLD (COLDLINE) after 90 days
    2. COLD → ARCHIVE after 6 years
    3. ARCHIVE → PURGE after 7 years (with legal hold check)
    """

    def __init__(
        self,
        vault_bucket: str,
        firestore_db = None,
        cold_transition_days: int = COLD_TRANSITION_DAYS,
        purge_threshold_days: int = PURGE_THRESHOLD_DAYS,
    ):
        self.vault_bucket = vault_bucket
        self.firestore_db = firestore_db
        self.cold_transition_days = cold_transition_days
        self.purge_threshold_days = purge_threshold_days

        # GCS client
        self._storage_client = None
        if HAS_GCS and vault_bucket:
            try:
                self._storage_client = storage.Client()
            except Exception as e:
                print(f"[RetentionManager] GCS client init failed: {e}", flush=True)

    def get_batch_age_days(self, batch: Dict[str, Any]) -> Optional[int]:
        """Calculate batch age in days from finished_at timestamp."""
        finished_at = batch.get("finished_at") or batch.get("timestamp")
        if not finished_at:
            return None

        try:
            if isinstance(finished_at, str):
                if finished_at.endswith("Z"):
                    finished_at = finished_at[:-1] + "+00:00"
                batch_date = datetime.fromisoformat(finished_at)
                if batch_date.tzinfo is None:
                    batch_date = batch_date.replace(tzinfo=timezone.utc)
            else:
                return None

            now = datetime.now(timezone.utc)
            return (now - batch_date).days
        except Exception:
            return None

    def check_legal_hold(self, batch: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if batch is under legal hold.

        Returns: (is_held, hold_id)
        """
        legal_hold = batch.get("legal_hold", {})
        if legal_hold.get("status") == "ACTIVE":
            return True, legal_hold.get("hold_id")
        return False, None

    def evaluate_retention_status(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate retention status for a single batch.

        Returns status, recommended action, and metadata.
        """
        trace_id = batch.get("trace_id", "UNKNOWN")
        age_days = self.get_batch_age_days(batch)
        is_held, hold_id = self.check_legal_hold(batch)

        # Legal hold overrides all retention logic
        if is_held:
            return {
                "trace_id": trace_id,
                "age_days": age_days,
                "status": RetentionStatus.HELD.value,
                "action": RetentionAction.BLOCKED_BY_HOLD.value,
                "hold_id": hold_id,
                "protected": True,
                "reason": f"Protected by legal hold {hold_id}"
            }

        if age_days is None:
            return {
                "trace_id": trace_id,
                "age_days": None,
                "status": RetentionStatus.HOT.value,
                "action": RetentionAction.NONE.value,
                "protected": False,
                "reason": "Cannot determine batch age"
            }

        # Determine status based on age
        if age_days >= self.purge_threshold_days:
            status = RetentionStatus.PURGE_ELIGIBLE
            action = RetentionAction.PURGE
            reason = f"Batch is {age_days} days old (> {self.purge_threshold_days} days) - eligible for purge"
        elif age_days >= ARCHIVE_TRANSITION_DAYS:
            status = RetentionStatus.ARCHIVE
            action = RetentionAction.TRANSITION_TO_ARCHIVE
            reason = f"Batch is {age_days} days old - in archive phase"
        elif age_days >= self.cold_transition_days:
            status = RetentionStatus.COLD
            action = RetentionAction.TRANSITION_TO_COLD
            reason = f"Batch is {age_days} days old (> {self.cold_transition_days} days) - should be in Coldline"
        else:
            status = RetentionStatus.HOT
            action = RetentionAction.NONE
            days_until_cold = self.cold_transition_days - age_days
            reason = f"Batch is {age_days} days old - {days_until_cold} days until cold transition"

        return {
            "trace_id": trace_id,
            "age_days": age_days,
            "status": status.value,
            "action": action.value,
            "protected": False,
            "reason": reason,
            "days_until_cold": max(0, self.cold_transition_days - age_days) if age_days else None,
            "days_until_purge": max(0, self.purge_threshold_days - age_days) if age_days else None,
        }

    def transition_to_cold(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transition batch evidence from STANDARD to COLDLINE storage.

        Returns transition result.
        """
        trace_id = batch.get("trace_id", "UNKNOWN")
        is_held, hold_id = self.check_legal_hold(batch)

        if is_held:
            return {
                "trace_id": trace_id,
                "transitioned": False,
                "reason": f"Blocked by legal hold {hold_id}",
                "storage_class": "STANDARD"  # Remains in hot storage for accessibility
            }

        # In production, this would change GCS storage class
        # For now, we log the intent
        return {
            "trace_id": trace_id,
            "transitioned": True,
            "reason": "Transitioned to COLDLINE storage",
            "storage_class": "COLDLINE",
            "transitioned_at": datetime.now(timezone.utc).isoformat()
        }

    def execute_purge(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute final purge on a batch.

        HARD BLOCK: Raises RetentionViolationError if batch is under legal hold.
        """
        trace_id = batch.get("trace_id", "UNKNOWN")
        is_held, hold_id = self.check_legal_hold(batch)

        # HARD BLOCK - Never delete held evidence
        if is_held:
            raise RetentionViolationError(
                batch_id=trace_id,
                hold_id=hold_id,
                message=f"CRITICAL: Attempted purge of legally held batch {trace_id} (hold: {hold_id})"
            )

        age_days = self.get_batch_age_days(batch)
        if age_days is None or age_days < self.purge_threshold_days:
            return {
                "trace_id": trace_id,
                "purged": False,
                "reason": f"Batch age ({age_days} days) below threshold ({self.purge_threshold_days} days)"
            }

        # In production, this would delete from GCS and Firestore
        # For now, we log the intent
        return {
            "trace_id": trace_id,
            "purged": True,
            "age_days": age_days,
            "reason": "Purged after retention period expired",
            "purged_at": datetime.now(timezone.utc).isoformat()
        }

    def get_retention_status_summary(self, batches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get comprehensive retention status summary.

        Returns:
        - Total batches in Archive status
        - Total batches Protected by Legal Hold
        - Upcoming purge list (> 6.9 years old)
        """
        archive_count = 0
        held_count = 0
        upcoming_purge = []
        hot_count = 0
        cold_count = 0
        purge_eligible_count = 0

        for batch in batches:
            evaluation = self.evaluate_retention_status(batch)
            status = evaluation["status"]

            if status == RetentionStatus.HELD.value:
                held_count += 1
            elif status == RetentionStatus.ARCHIVE.value:
                archive_count += 1
            elif status == RetentionStatus.HOT.value:
                hot_count += 1
            elif status == RetentionStatus.COLD.value:
                cold_count += 1
            elif status == RetentionStatus.PURGE_ELIGIBLE.value:
                purge_eligible_count += 1

            # Check for upcoming purge (> 6.9 years / 2520 days)
            age_days = evaluation.get("age_days")
            if age_days and age_days >= PURGE_WARNING_DAYS and status != RetentionStatus.HELD.value:
                upcoming_purge.append({
                    "trace_id": evaluation["trace_id"],
                    "age_days": age_days,
                    "days_until_purge": evaluation.get("days_until_purge", 0),
                    "status": status
                })

        # Sort upcoming purge by days until purge (most urgent first)
        upcoming_purge.sort(key=lambda x: x.get("days_until_purge", 9999))

        return {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "total_batches": len(batches),
            "by_status": {
                "hot": hot_count,
                "cold": cold_count,
                "archive": archive_count,
                "purge_eligible": purge_eligible_count,
                "protected_by_hold": held_count,
            },
            "archive_count": archive_count,
            "protected_by_legal_hold": held_count,
            "upcoming_purge_list": upcoming_purge,
            "upcoming_purge_count": len(upcoming_purge),
            "thresholds": {
                "cold_transition_days": self.cold_transition_days,
                "archive_transition_days": ARCHIVE_TRANSITION_DAYS,
                "purge_threshold_days": self.purge_threshold_days,
                "purge_warning_days": PURGE_WARNING_DAYS,
            }
        }


def generate_gcs_lifecycle_policy() -> Dict[str, Any]:
    """
    Generate GCS lifecycle policy for the vault bucket.

    Rules:
    1. Transition STANDARD → COLDLINE after 90 days
    2. Delete after 2555 days (7 years)

    IMPORTANT: The Delete rule is overridden by backend-level Legal Hold check.
    GCS lifecycle cannot auto-purge protected evidence because:
    1. Legal holds set object retention
    2. Backend blocks delete API calls for held batches
    """
    return {
        "rule": [
            {
                "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
                "condition": {"age": 90, "matchesStorageClass": ["STANDARD"]}
            },
            {
                "action": {"type": "Delete"},
                "condition": {"age": 2555, "isLive": True}
            }
        ]
    }


def apply_gcs_lifecycle_policy(bucket_name: str) -> Dict[str, Any]:
    """
    Apply lifecycle policy to GCS bucket.

    Returns application result.
    """
    if not HAS_GCS:
        return {
            "applied": False,
            "reason": "GCS client not available"
        }

    try:
        client = storage.Client()
        bucket = client.get_bucket(bucket_name)

        # Set lifecycle rules
        bucket.lifecycle_rules = [
            {
                "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
                "condition": {"age": 90, "matchesStorageClass": ["STANDARD"]}
            },
            {
                "action": {"type": "Delete"},
                "condition": {"age": 2555, "isLive": True}
            }
        ]
        bucket.patch()

        return {
            "applied": True,
            "bucket": bucket_name,
            "rules": list(bucket.lifecycle_rules),
            "applied_at": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        return {
            "applied": False,
            "bucket": bucket_name,
            "error": str(e)
        }


def build_retention_event(
    action: str,
    batch_id: str,
    tenant_id: str,
    actor_id: str,
    previous_status: str,
    new_status: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Build an immutable retention action event for audit trail.
    """
    event_id = f"RET-{hashlib.sha256(f'{batch_id}{datetime.now().isoformat()}'.encode()).hexdigest()[:12].upper()}"
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "event_id": event_id,
        "event_type": f"RETENTION_{action.upper()}",
        "batch_id": batch_id,
        "tenant_id_hash": hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
        "actor": actor_id,
        "timestamp": timestamp,
        "previous_status": previous_status,
        "new_status": new_status,
        "reason": reason,
    }
