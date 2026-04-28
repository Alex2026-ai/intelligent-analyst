"""
test_sharding.py — Unit tests for shard planner.

Tests compute_shard_ranges() boundary conditions per Day 2 spec:
  0, 1, 999, 1000, 1001, 1999, 2000, 10000 records.
"""

import pytest
from app.sharding import compute_shard_ranges


class TestComputeShardRanges:
    """Tests for the pure shard planner function."""

    def test_zero_records(self):
        result = compute_shard_ranges(0)
        assert result == []

    def test_negative_records(self):
        result = compute_shard_ranges(-5)
        assert result == []

    def test_one_record(self):
        result = compute_shard_ranges(1)
        assert len(result) == 1
        assert result[0] == {
            "shard_id": 0,
            "start_index": 0,
            "end_index": 1,
            "record_count": 1,
        }

    def test_999_records(self):
        """999 records → 1 shard (less than shard_size)."""
        result = compute_shard_ranges(999, shard_size=1000)
        assert len(result) == 1
        assert result[0]["start_index"] == 0
        assert result[0]["end_index"] == 999
        assert result[0]["record_count"] == 999

    def test_1000_records(self):
        """1000 records → exactly 1 shard."""
        result = compute_shard_ranges(1000, shard_size=1000)
        assert len(result) == 1
        assert result[0]["start_index"] == 0
        assert result[0]["end_index"] == 1000
        assert result[0]["record_count"] == 1000

    def test_1001_records(self):
        """1001 records → 2 shards (1000 + 1)."""
        result = compute_shard_ranges(1001, shard_size=1000)
        assert len(result) == 2

        assert result[0]["shard_id"] == 0
        assert result[0]["start_index"] == 0
        assert result[0]["end_index"] == 1000
        assert result[0]["record_count"] == 1000

        assert result[1]["shard_id"] == 1
        assert result[1]["start_index"] == 1000
        assert result[1]["end_index"] == 1001
        assert result[1]["record_count"] == 1

    def test_1999_records(self):
        """1999 records → 2 shards (1000 + 999)."""
        result = compute_shard_ranges(1999, shard_size=1000)
        assert len(result) == 2
        assert result[0]["record_count"] == 1000
        assert result[1]["record_count"] == 999
        assert result[1]["end_index"] == 1999

    def test_2000_records(self):
        """2000 records → 2 shards (1000 + 1000)."""
        result = compute_shard_ranges(2000, shard_size=1000)
        assert len(result) == 2
        assert result[0]["record_count"] == 1000
        assert result[1]["record_count"] == 1000

    def test_10000_records(self):
        """10000 records → 10 shards."""
        result = compute_shard_ranges(10000, shard_size=1000)
        assert len(result) == 10

        # All shards have shard_size records
        for i, shard in enumerate(result):
            assert shard["shard_id"] == i
            assert shard["start_index"] == i * 1000
            assert shard["end_index"] == (i + 1) * 1000
            assert shard["record_count"] == 1000

    def test_custom_shard_size(self):
        """Custom shard_size overrides default."""
        result = compute_shard_ranges(100, shard_size=30)
        assert len(result) == 4  # 30 + 30 + 30 + 10

        assert result[0]["record_count"] == 30
        assert result[1]["record_count"] == 30
        assert result[2]["record_count"] == 30
        assert result[3]["record_count"] == 10

    def test_shard_size_equals_total(self):
        """When shard_size == total, exactly 1 shard."""
        result = compute_shard_ranges(500, shard_size=500)
        assert len(result) == 1
        assert result[0]["record_count"] == 500

    def test_shard_size_larger_than_total(self):
        """When shard_size > total, exactly 1 shard."""
        result = compute_shard_ranges(50, shard_size=1000)
        assert len(result) == 1
        assert result[0]["record_count"] == 50

    def test_invalid_shard_size(self):
        """shard_size <= 0 raises ValueError."""
        with pytest.raises(ValueError):
            compute_shard_ranges(100, shard_size=0)
        with pytest.raises(ValueError):
            compute_shard_ranges(100, shard_size=-1)

    def test_contiguous_coverage(self):
        """All records are covered exactly once — no gaps, no overlaps."""
        total = 2501
        result = compute_shard_ranges(total, shard_size=1000)

        # Total record_count across all shards == total
        assert sum(s["record_count"] for s in result) == total

        # Shards are contiguous
        for i in range(1, len(result)):
            assert result[i]["start_index"] == result[i - 1]["end_index"]

        # First starts at 0, last ends at total
        assert result[0]["start_index"] == 0
        assert result[-1]["end_index"] == total

    def test_shard_ids_monotonic(self):
        """shard_ids are 0-indexed and monotonically increasing."""
        result = compute_shard_ranges(5000, shard_size=1000)
        ids = [s["shard_id"] for s in result]
        assert ids == list(range(5))

    def test_large_batch_100k(self):
        """100K records → 100 shards."""
        result = compute_shard_ranges(100000, shard_size=1000)
        assert len(result) == 100
        assert sum(s["record_count"] for s in result) == 100000
