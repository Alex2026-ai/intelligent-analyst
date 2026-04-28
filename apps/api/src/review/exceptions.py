"""Review-specific exceptions."""

from __future__ import annotations


class ReviewQueueError(Exception):
    """Base exception for review queue operations."""


class CaseNotFoundError(ReviewQueueError):
    def __init__(self, case_id: str) -> None:
        super().__init__(f"Review case not found: {case_id}")
        self.case_id = case_id


class CaseAlreadyDecidedError(ReviewQueueError):
    def __init__(self, case_id: str) -> None:
        super().__init__(f"Case already decided: {case_id}")
        self.case_id = case_id


class InvalidDecisionError(ReviewQueueError):
    def __init__(self, decision: str) -> None:
        super().__init__(f"Invalid decision: {decision}")
        self.decision = decision
