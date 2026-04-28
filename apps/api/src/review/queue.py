"""Review queue operations — list, assign, stats."""

from __future__ import annotations

from typing import Any


class ReviewQueue:
    """In-memory review queue for operations. In production, backed by Firestore."""

    def __init__(self) -> None:
        self._cases: dict[str, dict[str, Any]] = {}

    def add_case(self, case: dict[str, Any]) -> None:
        self._cases[case["case_id"]] = case

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return self._cases.get(case_id)

    def list_cases(
        self,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
    ) -> list[dict[str, Any]]:
        results = list(self._cases.values())
        if status:
            results = [c for c in results if c.get("status") == status]
        if priority:
            results = [c for c in results if c.get("priority") == priority]
        if assigned_to:
            results = [c for c in results if c.get("assigned_to") == assigned_to]
        return results

    def assign_case(self, case_id: str, reviewer_id: str) -> dict[str, Any] | None:
        case = self._cases.get(case_id)
        if case is None:
            return None
        case["assigned_to"] = reviewer_id
        case["status"] = "assigned"
        return case

    def update_status(self, case_id: str, status: str) -> dict[str, Any] | None:
        case = self._cases.get(case_id)
        if case is None:
            return None
        case["status"] = status
        return case

    def get_stats(self) -> dict[str, Any]:
        cases = list(self._cases.values())
        return {
            "total_pending": sum(1 for c in cases if c["status"] == "pending"),
            "total_assigned": sum(1 for c in cases if c["status"] == "assigned"),
            "total_decided": sum(1 for c in cases if c["status"] == "decided"),
            "total": len(cases),
        }
