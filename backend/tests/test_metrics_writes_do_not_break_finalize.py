"""
test_metrics_writes_do_not_break_finalize.py — Day 6: Fail-closed safety tests.

Verifies that metrics write failures never break the finalize pipeline.
"""

import pytest
from unittest.mock import MagicMock
from app.metrics.system_metrics import (
    record_finalize_latency,
    record_shard_latency,
    record_l3_cache_stats,
    record_failover_stats,
    record_ledger_snapshot,
)


class TestAllWritersFailGracefully:
    def test_all_writers_fail_gracefully(self):
        """db.collection() throws → all 5 writers return False."""
        db = MagicMock()
        db.collection.side_effect = RuntimeError("Firestore unavailable")

        assert record_finalize_latency(db, 100.0) is False
        assert record_shard_latency(db, 100.0) is False
        assert record_l3_cache_stats(db, 10, 3, 1) is False
        assert record_failover_stats(db, 1, 10) is False
        assert record_ledger_snapshot(db, "t1", 10.0, 5.0, 0.0, True) is False


class TestBudgetTrackerFailoverField:
    def test_budget_tracker_failover_field(self):
        """L3BudgetTracker has l3_failover_count field."""
        from app.server_enterprise_golden import L3BudgetTracker
        tracker = L3BudgetTracker()
        assert hasattr(tracker, "l3_failover_count")
        assert tracker.l3_failover_count == 0


class TestBudgetTrackerSummaryIncludesFailover:
    def test_budget_tracker_summary_includes_failover(self):
        """get_summary() dict contains l3_failover_count key."""
        from app.server_enterprise_golden import L3BudgetTracker
        tracker = L3BudgetTracker()
        tracker.l3_failover_count = 3
        summary = tracker.get_summary()
        assert "l3_failover_count" in summary
        assert summary["l3_failover_count"] == 3
