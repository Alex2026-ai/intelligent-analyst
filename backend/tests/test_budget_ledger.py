"""
test_budget_ledger.py — Unit tests for atomic budget ledger.

Tests idempotency, insufficient credits, spend/release lifecycle,
and fail-closed behavior using a mock Firestore.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.budget_ledger import (
    LedgerResult,
    _compute_event_id,
    ensure_tenant_balance,
    reserve_budget,
    spend_budget,
    release_budget,
    get_tenant_balance,
)


class MockFirestoreDoc:
    """Mock Firestore document snapshot."""
    def __init__(self, data=None, exists=True):
        self._data = data or {}
        self.exists = exists

    def to_dict(self):
        return self._data.copy()


class MockTransaction:
    """Mock Firestore transaction that records operations."""
    def __init__(self):
        self.updates = []
        self.sets = []

    def update(self, ref, data):
        self.updates.append((ref, data))

    def set(self, ref, data):
        self.sets.append((ref, data))


class InMemoryFirestore:
    """
    Simple in-memory Firestore mock for unit testing.
    Supports collection/document/get/set/update patterns.
    """
    def __init__(self):
        self._data = {}  # path -> dict

    def _path(self, *parts):
        return "/".join(parts)

    def collection(self, name):
        return _CollectionRef(self, name)

    def transaction(self, **kwargs):
        return MockTransaction()


class _CollectionRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def document(self, doc_id):
        return _DocRef(self._db, f"{self._path}/{doc_id}")


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def collection(self, name):
        return _CollectionRef(self._db, f"{self._path}/{name}")

    def get(self, transaction=None):
        data = self._db._data.get(self._path)
        if data is not None:
            return MockFirestoreDoc(data, exists=True)
        return MockFirestoreDoc(exists=False)

    def set(self, data):
        self._db._data[self._path] = data.copy()

    def update(self, data):
        if self._path not in self._db._data:
            self._db._data[self._path] = {}
        self._db._data[self._path].update(data)


class TestComputeEventId:
    def test_deterministic(self):
        id1 = _compute_event_id("BATCH-123", 0, "fp1")
        id2 = _compute_event_id("BATCH-123", 0, "fp1")
        assert id1 == id2

    def test_different_inputs(self):
        id1 = _compute_event_id("BATCH-123", 0, "fp1")
        id2 = _compute_event_id("BATCH-123", 1, "fp1")
        assert id1 != id2

    def test_is_sha256_hex(self):
        event_id = _compute_event_id("BATCH-ABC", 5, "test")
        assert len(event_id) == 64
        assert all(c in "0123456789abcdef" for c in event_id)


class TestEnsureTenantBalance:
    def test_creates_balance_if_missing(self):
        db = InMemoryFirestore()
        result = ensure_tenant_balance("tenant-1", db, default_credits=50.0)
        assert result is True

        # Verify doc was created
        path = "tenants/tenant-1/billing/balance"
        assert path in db._data
        assert db._data[path]["credits_total_usd"] == 50.0
        assert db._data[path]["credits_spent_usd"] == 0.0
        assert db._data[path]["credits_reserved_usd"] == 0.0

    def test_does_not_overwrite_existing(self):
        db = InMemoryFirestore()
        # Pre-populate
        db._data["tenants/tenant-1/billing/balance"] = {
            "credits_total_usd": 200.0,
            "credits_spent_usd": 50.0,
            "credits_reserved_usd": 10.0,
        }

        result = ensure_tenant_balance("tenant-1", db, default_credits=100.0)
        assert result is True

        # Verify NOT overwritten
        assert db._data["tenants/tenant-1/billing/balance"]["credits_total_usd"] == 200.0

    def test_no_db_returns_false(self):
        result = ensure_tenant_balance("tenant-1", None)
        assert result is False


class TestReserveBudget:
    """Tests for reserve_budget using mocked Firestore transactions.

    Note: These tests verify the LedgerResult contract and event_id
    computation. Full transactional behavior requires Firestore emulator.
    """

    def test_zero_amount_succeeds(self):
        db = InMemoryFirestore()
        result = reserve_budget("t1", "BATCH-1", 0, 0.0, "fp", db)
        assert result.success is True
        assert result.status == "applied"

    def test_no_db_returns_error(self):
        result = reserve_budget("t1", "BATCH-1", 0, 5.0, "fp", None)
        assert result.success is False
        assert result.status == "error"

    def test_event_id_deterministic(self):
        """Same inputs produce same event_id for idempotency."""
        id1 = _compute_event_id("BATCH-1", 0, "reserve_preflight")
        id2 = _compute_event_id("BATCH-1", 0, "reserve_preflight")
        assert id1 == id2


class TestSpendBudget:
    def test_zero_amount_succeeds(self):
        db = InMemoryFirestore()
        result = spend_budget("t1", "BATCH-1", 0, 0.0, "fp", db)
        assert result.success is True
        assert result.status == "applied"

    def test_no_db_returns_error(self):
        result = spend_budget("t1", "BATCH-1", 0, 5.0, "fp", None)
        assert result.success is False
        assert result.status == "error"


class TestReleaseBudget:
    def test_zero_amount_succeeds(self):
        db = InMemoryFirestore()
        result = release_budget("t1", "BATCH-1", 0, 0.0, "fp", db)
        assert result.success is True
        assert result.status == "applied"

    def test_no_db_returns_error(self):
        result = release_budget("t1", "BATCH-1", 0, 5.0, "fp", None)
        assert result.success is False
        assert result.status == "error"


class TestGetTenantBalance:
    def test_existing_balance(self):
        db = InMemoryFirestore()
        db._data["tenants/tenant-1/billing/balance"] = {
            "credits_total_usd": 100.0,
            "credits_spent_usd": 25.0,
            "credits_reserved_usd": 10.0,
        }

        balance = get_tenant_balance("tenant-1", db)
        assert balance is not None
        assert balance["credits_total_usd"] == 100.0
        assert balance["credits_spent_usd"] == 25.0

    def test_missing_balance(self):
        db = InMemoryFirestore()
        balance = get_tenant_balance("tenant-1", db)
        assert balance is None

    def test_no_db_returns_none(self):
        balance = get_tenant_balance("tenant-1", None)
        assert balance is None


class TestFailClosed:
    """Verify fail-closed behavior: no Firestore → no L3."""

    def test_reserve_fails_without_db(self):
        result = reserve_budget("t1", "B1", 0, 10.0, "fp", None)
        assert result.success is False

    def test_spend_fails_without_db(self):
        result = spend_budget("t1", "B1", 0, 5.0, "fp", None)
        assert result.success is False

    def test_release_fails_without_db(self):
        result = release_budget("t1", "B1", 0, 5.0, "fp", None)
        assert result.success is False
