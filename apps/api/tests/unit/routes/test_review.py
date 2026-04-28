"""Tests for review endpoints — RBAC enforcement."""

from apps.api.tests.conftest import (
    REVIEWER_TOKEN, VALID_TOKEN, auth_header,
)


class TestReviewQueue:
    def test_analyst_cannot_access_queue(self, client):
        resp = client.get("/v1/review/queue", headers=auth_header(VALID_TOKEN))
        assert resp.status_code == 403

    def test_reviewer_can_access_queue(self, client):
        resp = client.get("/v1/review/queue", headers=auth_header(REVIEWER_TOKEN))
        assert resp.status_code == 200
        data = resp.json()
        assert "cases" in data
        assert "queue_stats" in data


class TestReviewDecision:
    def test_analyst_cannot_decide(self, client):
        resp = client.post(
            "/v1/review/case-1/decide",
            json={"decision": "approve", "notes": "Confirmed correct match."},
            headers=auth_header(VALID_TOKEN),
        )
        assert resp.status_code == 403

    def test_reviewer_can_decide(self, client):
        resp = client.post(
            "/v1/review/case-1/decide",
            json={"decision": "approve", "notes": "Confirmed correct match."},
            headers=auth_header(REVIEWER_TOKEN),
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approve"

    def test_invalid_decision(self, client):
        resp = client.post(
            "/v1/review/case-1/decide",
            json={"decision": "invalid", "notes": "Some reason here."},
            headers=auth_header(REVIEWER_TOKEN),
        )
        assert resp.status_code == 400

    def test_notes_too_short(self, client):
        resp = client.post(
            "/v1/review/case-1/decide",
            json={"decision": "approve", "notes": "short"},
            headers=auth_header(REVIEWER_TOKEN),
        )
        assert resp.status_code == 400
