"""Tests for SLA tracking — deadline computation, breach detection."""

from datetime import datetime, timedelta, timezone

from apps.api.src.review.sla import compute_sla_deadline, find_breached_cases, is_breached


class TestSLADeadline:
    def test_standard_24h(self):
        now = "2026-03-21T10:00:00+00:00"
        deadline = compute_sla_deadline("standard", now)
        expected = "2026-03-22T10:00:00+00:00"
        assert deadline == expected

    def test_high_4h(self):
        now = "2026-03-21T10:00:00+00:00"
        deadline = compute_sla_deadline("high", now)
        expected = "2026-03-21T14:00:00+00:00"
        assert deadline == expected

    def test_urgent_1h(self):
        now = "2026-03-21T10:00:00+00:00"
        deadline = compute_sla_deadline("urgent", now)
        expected = "2026-03-21T11:00:00+00:00"
        assert deadline == expected

    def test_custom_sla_hours(self):
        now = "2026-03-21T10:00:00+00:00"
        custom = {"standard": 48, "high": 8, "urgent": 2}
        deadline = compute_sla_deadline("high", now, custom)
        expected = "2026-03-21T18:00:00+00:00"
        assert deadline == expected


class TestBreachDetection:
    def test_not_breached(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        assert is_breached(future) is False

    def test_breached(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert is_breached(past) is True

    def test_find_breached_cases(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        cases = [
            {"case_id": "c1", "status": "pending", "sla_deadline": past},
            {"case_id": "c2", "status": "pending", "sla_deadline": future},
            {"case_id": "c3", "status": "decided", "sla_deadline": past},  # Decided, skip
        ]
        breached = find_breached_cases(cases)
        assert len(breached) == 1
        assert breached[0]["case_id"] == "c1"
