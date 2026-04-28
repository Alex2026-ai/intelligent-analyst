"""Stale case checker — finds cases past SLA deadline and reassigns.

Max 2 reassignments per case, then escalate.
"""

from __future__ import annotations

from typing import Any

from apps.api.src.review.sla import find_breached_cases

MAX_REASSIGNMENTS = 2


def check_and_reassign(
    cases: list[dict[str, Any]],
    available_reviewers: list[str],
) -> list[dict[str, Any]]:
    """Find SLA-breached cases and reassign or escalate them.

    Args:
        cases: All active review cases.
        available_reviewers: List of reviewer IDs available for reassignment.

    Returns:
        List of actions taken (reassign or escalate).
    """
    breached = find_breached_cases(cases)
    actions: list[dict[str, Any]] = []

    for case in breached:
        reassign_count = case.get("reassignment_count", 0)

        if reassign_count >= MAX_REASSIGNMENTS:
            case["status"] = "escalated"
            actions.append({
                "action": "escalate",
                "case_id": case["case_id"],
                "reason": f"SLA breached {reassign_count} times",
            })
        elif available_reviewers:
            # Assign to next available reviewer (not the current one)
            current = case.get("assigned_to")
            candidates = [r for r in available_reviewers if r != current]
            if candidates:
                case["assigned_to"] = candidates[0]
                case["status"] = "assigned"
                case["reassignment_count"] = reassign_count + 1
                actions.append({
                    "action": "reassign",
                    "case_id": case["case_id"],
                    "new_reviewer": candidates[0],
                })
            else:
                case["status"] = "escalated"
                actions.append({
                    "action": "escalate",
                    "case_id": case["case_id"],
                    "reason": "No alternative reviewer available",
                })
        else:
            case["status"] = "escalated"
            actions.append({
                "action": "escalate",
                "case_id": case["case_id"],
                "reason": "No reviewers available",
            })

    return actions
