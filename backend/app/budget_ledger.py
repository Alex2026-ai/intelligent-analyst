"""
budget_ledger.py — Atomic Budget Ledger for tenant-level L3 cost control.

Provides transactional reserve/spend/release operations backed by Firestore.
All operations are idempotent via deterministic event_id hashing.

Firestore paths:
  /tenants/{tenant_id}/billing/balance     — tenant credit balance (source of truth)
  /tenants/{tenant_id}/ledger_events/{id}  — journal of all budget events (audit trail)

Fail-closed: if Firestore unavailable or transaction fails, L3 calls are NOT made.
"""

import hashlib
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LedgerResult:
    """Result of a ledger operation."""
    success: bool
    status: str          # "applied" | "duplicate" | "rejected" | "error"
    credits_remaining: float = 0.0
    message: str = ""


def _compute_event_id(batch_id: str, shard_id: int, fingerprint: str) -> str:
    """Deterministic event ID for idempotency."""
    raw = f"{batch_id}:{shard_id}:{fingerprint}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap: ensure tenant balance doc exists
# ──────────────────────────────────────────────────────────────────────────────

def ensure_tenant_balance(tenant_id: str, db, default_credits: float = 100.0) -> bool:
    """
    Create the tenant balance document if it doesn't exist.
    Does NOT overwrite existing balance. Safe to call multiple times.

    Args:
        default_credits: Initial credit allocation for new tenants (USD)

    Returns True if balance doc exists (created or already present).
    """
    if not db:
        print("[ledger] No Firestore client, cannot ensure balance", flush=True)
        return False

    try:
        balance_ref = (db.collection("tenants").document(tenant_id)
                       .collection("billing").document("balance"))

        doc = balance_ref.get()
        if doc.exists:
            return True

        # Create initial balance
        balance_ref.set({
            "credits_total_usd": default_credits,
            "credits_spent_usd": 0.0,
            "credits_reserved_usd": 0.0,
            "updated_at_utc": datetime.utcnow().isoformat(),
            "version": 1,
            "tenant_id": tenant_id,
            "created_at_utc": datetime.utcnow().isoformat(),
        })

        print(f"[ledger] Created balance for tenant {tenant_id}: ${default_credits:.2f}", flush=True)
        return True

    except Exception as e:
        print(f"[ledger] Failed to ensure balance for {tenant_id}: {e}", flush=True)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Reserve: pre-flight budget check before L3
# ──────────────────────────────────────────────────────────────────────────────

def reserve_budget(
    tenant_id: str,
    batch_id: str,
    shard_id: int,
    amount_usd: float,
    fingerprint: str,
    db,
) -> LedgerResult:
    """
    Atomically reserve budget for a shard's estimated L3 costs.

    Uses Firestore transaction:
    1. Check if event already exists (idempotent — returns "duplicate")
    2. Read balance doc
    3. Check credits_remaining >= amount_usd
    4. Increment credits_reserved_usd
    5. Write reserve event

    Fail-closed: if balance doc missing or insufficient credits → "rejected".
    """
    if not db:
        return LedgerResult(success=False, status="error", message="no_firestore")

    if amount_usd <= 0:
        return LedgerResult(success=True, status="applied", credits_remaining=0.0,
                            message="zero_amount")

    event_id = _compute_event_id(batch_id, shard_id, fingerprint)

    try:
        from google.cloud import firestore

        @firestore.transactional
        def _txn(transaction):
            # 1. Idempotency check
            event_ref = (db.collection("tenants").document(tenant_id)
                         .collection("ledger_events").document(event_id))
            event_doc = event_ref.get(transaction=transaction)

            if event_doc.exists:
                existing = event_doc.to_dict()
                return LedgerResult(
                    success=True,
                    status="duplicate",
                    credits_remaining=existing.get("credits_remaining_after", 0.0),
                    message=f"event {event_id[:12]} already exists"
                )

            # 2. Read balance
            balance_ref = (db.collection("tenants").document(tenant_id)
                           .collection("billing").document("balance"))
            balance_doc = balance_ref.get(transaction=transaction)

            if not balance_doc.exists:
                return LedgerResult(
                    success=False,
                    status="rejected",
                    message="no_balance_doc"
                )

            balance = balance_doc.to_dict()
            total = balance.get("credits_total_usd", 0.0)
            spent = balance.get("credits_spent_usd", 0.0)
            reserved = balance.get("credits_reserved_usd", 0.0)
            remaining = total - spent - reserved

            # 3. Check
            if remaining < amount_usd:
                # Write skip event for audit trail
                transaction.set(event_ref, {
                    "batch_id": batch_id,
                    "shard_id": shard_id,
                    "amount_usd": amount_usd,
                    "kind": "skip",
                    "status": "rejected",
                    "reason": "insufficient_credits",
                    "credits_remaining_after": remaining,
                    "created_at_utc": datetime.utcnow().isoformat(),
                })
                return LedgerResult(
                    success=False,
                    status="rejected",
                    credits_remaining=remaining,
                    message=f"insufficient: need ${amount_usd:.4f}, have ${remaining:.4f}"
                )

            # 4. Reserve
            new_remaining = remaining - amount_usd
            transaction.update(balance_ref, {
                "credits_reserved_usd": reserved + amount_usd,
                "updated_at_utc": datetime.utcnow().isoformat(),
                "version": balance.get("version", 0) + 1,
            })

            # 5. Write event
            transaction.set(event_ref, {
                "batch_id": batch_id,
                "shard_id": shard_id,
                "amount_usd": amount_usd,
                "kind": "reserve",
                "status": "applied",
                "credits_remaining_after": new_remaining,
                "created_at_utc": datetime.utcnow().isoformat(),
            })

            return LedgerResult(
                success=True,
                status="applied",
                credits_remaining=new_remaining,
            )

        return _txn(db.transaction())

    except Exception as e:
        print(f"[ledger] reserve_budget error: {e}", flush=True)
        traceback.print_exc()
        return LedgerResult(success=False, status="error", message=str(e)[:200])


# ──────────────────────────────────────────────────────────────────────────────
# Spend: record actual L3 cost
# ──────────────────────────────────────────────────────────────────────────────

def spend_budget(
    tenant_id: str,
    batch_id: str,
    shard_id: int,
    amount_usd: float,
    fingerprint: str,
    db,
) -> LedgerResult:
    """
    Atomically move amount from reserved to spent.

    Firestore transaction:
    1. Idempotency check (event_id)
    2. Decrement credits_reserved_usd
    3. Increment credits_spent_usd
    4. Write spend event
    """
    if not db:
        return LedgerResult(success=False, status="error", message="no_firestore")

    if amount_usd <= 0:
        return LedgerResult(success=True, status="applied", message="zero_amount")

    event_id = _compute_event_id(batch_id, shard_id, fingerprint)

    try:
        from google.cloud import firestore

        @firestore.transactional
        def _txn(transaction):
            # 1. Idempotency
            event_ref = (db.collection("tenants").document(tenant_id)
                         .collection("ledger_events").document(event_id))
            event_doc = event_ref.get(transaction=transaction)

            if event_doc.exists:
                existing = event_doc.to_dict()
                return LedgerResult(
                    success=True,
                    status="duplicate",
                    credits_remaining=existing.get("credits_remaining_after", 0.0),
                )

            # 2. Read balance
            balance_ref = (db.collection("tenants").document(tenant_id)
                           .collection("billing").document("balance"))
            balance_doc = balance_ref.get(transaction=transaction)

            if not balance_doc.exists:
                return LedgerResult(success=False, status="error", message="no_balance_doc")

            balance = balance_doc.to_dict()
            reserved = balance.get("credits_reserved_usd", 0.0)
            spent = balance.get("credits_spent_usd", 0.0)
            total = balance.get("credits_total_usd", 0.0)

            # 3. Move from reserved to spent
            new_reserved = max(0.0, reserved - amount_usd)
            new_spent = spent + amount_usd
            new_remaining = total - new_spent - new_reserved

            transaction.update(balance_ref, {
                "credits_reserved_usd": new_reserved,
                "credits_spent_usd": new_spent,
                "updated_at_utc": datetime.utcnow().isoformat(),
                "version": balance.get("version", 0) + 1,
            })

            # 4. Write event
            transaction.set(event_ref, {
                "batch_id": batch_id,
                "shard_id": shard_id,
                "amount_usd": amount_usd,
                "kind": "spend",
                "status": "applied",
                "credits_remaining_after": new_remaining,
                "created_at_utc": datetime.utcnow().isoformat(),
            })

            return LedgerResult(
                success=True,
                status="applied",
                credits_remaining=new_remaining,
            )

        return _txn(db.transaction())

    except Exception as e:
        print(f"[ledger] spend_budget error: {e}", flush=True)
        traceback.print_exc()
        return LedgerResult(success=False, status="error", message=str(e)[:200])


# ──────────────────────────────────────────────────────────────────────────────
# Release: return unused reserved budget
# ──────────────────────────────────────────────────────────────────────────────

def release_budget(
    tenant_id: str,
    batch_id: str,
    shard_id: int,
    amount_usd: float,
    fingerprint: str,
    db,
) -> LedgerResult:
    """
    Release unused reserved budget back to available credits.
    Called when a shard completes and didn't use its full L3 reserve.

    Firestore transaction:
    1. Idempotency check
    2. Decrement credits_reserved_usd by amount_usd
    3. Write release event
    """
    if not db:
        return LedgerResult(success=False, status="error", message="no_firestore")

    if amount_usd <= 0:
        return LedgerResult(success=True, status="applied", message="zero_amount")

    event_id = _compute_event_id(batch_id, shard_id, fingerprint)

    try:
        from google.cloud import firestore

        @firestore.transactional
        def _txn(transaction):
            # 1. Idempotency
            event_ref = (db.collection("tenants").document(tenant_id)
                         .collection("ledger_events").document(event_id))
            event_doc = event_ref.get(transaction=transaction)

            if event_doc.exists:
                existing = event_doc.to_dict()
                return LedgerResult(
                    success=True,
                    status="duplicate",
                    credits_remaining=existing.get("credits_remaining_after", 0.0),
                )

            # 2. Read balance
            balance_ref = (db.collection("tenants").document(tenant_id)
                           .collection("billing").document("balance"))
            balance_doc = balance_ref.get(transaction=transaction)

            if not balance_doc.exists:
                return LedgerResult(success=False, status="error", message="no_balance_doc")

            balance = balance_doc.to_dict()
            reserved = balance.get("credits_reserved_usd", 0.0)
            total = balance.get("credits_total_usd", 0.0)
            spent = balance.get("credits_spent_usd", 0.0)

            # 3. Release
            new_reserved = max(0.0, reserved - amount_usd)
            new_remaining = total - spent - new_reserved

            transaction.update(balance_ref, {
                "credits_reserved_usd": new_reserved,
                "updated_at_utc": datetime.utcnow().isoformat(),
                "version": balance.get("version", 0) + 1,
            })

            # 4. Write event
            transaction.set(event_ref, {
                "batch_id": batch_id,
                "shard_id": shard_id,
                "amount_usd": amount_usd,
                "kind": "release",
                "status": "applied",
                "credits_remaining_after": new_remaining,
                "created_at_utc": datetime.utcnow().isoformat(),
            })

            return LedgerResult(
                success=True,
                status="applied",
                credits_remaining=new_remaining,
            )

        return _txn(db.transaction())

    except Exception as e:
        print(f"[ledger] release_budget error: {e}", flush=True)
        traceback.print_exc()
        return LedgerResult(success=False, status="error", message=str(e)[:200])


# ──────────────────────────────────────────────────────────────────────────────
# Query: get tenant balance
# ──────────────────────────────────────────────────────────────────────────────

def get_tenant_balance(tenant_id: str, db) -> Optional[dict]:
    """Read current tenant balance. Returns None if not found."""
    if not db:
        return None

    try:
        balance_ref = (db.collection("tenants").document(tenant_id)
                       .collection("billing").document("balance"))
        doc = balance_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        print(f"[ledger] get_tenant_balance error: {e}", flush=True)
        return None
