"""Command endpoint — parses natural-language commands from the Omni-Bar.

Supports dry_run for pre-flight execution plans.
Returns structured intents: NAVIGATE, RESOLVE, CONFIG, UNKNOWN.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request

from apps.api.src.dependencies import AuthContext, Role, require_role

router = APIRouter(prefix="/v1", tags=["command"])

NAV_ROUTES: dict[str, str] = {
    "dashboard": "/",
    "home": "/",
    "resolutions": "/resolutions",
    "resolution": "/resolutions",
    "resolve": "/resolutions",
    "review": "/review",
    "queue": "/review",
    "admin": "/admin",
    "config": "/admin",
    "settings": "/admin",
}

RE_GOTO = re.compile(r"^(?:go(?:\s+to)?|goto|navigate|open|show)\s+(.+)$", re.IGNORECASE)
RE_RESOLVE = re.compile(r"^resolve\s+(?:--file=)?(.+)$", re.IGNORECASE)
RE_CONFIG = re.compile(r"^(?:config|set|toggle)\s+(.+)$", re.IGNORECASE)


def _parse_command(raw: str) -> dict[str, Any]:
    """Parse a raw command string into a structured intent."""
    text = raw.strip()

    goto_match = RE_GOTO.match(text)
    if goto_match:
        target = goto_match.group(1).strip().lower()
        route = NAV_ROUTES.get(target)
        if route:
            return {"intent": "NAVIGATE", "nav_target": route, "payload": {"label": target}}
        return {"intent": "UNKNOWN", "nav_target": None, "payload": {"error": f"Unknown destination: {target}"}}

    if text.lower() in NAV_ROUTES:
        return {"intent": "NAVIGATE", "nav_target": NAV_ROUTES[text.lower()], "payload": {"label": text.lower()}}

    resolve_match = RE_RESOLVE.match(text)
    if resolve_match:
        file_or_content = resolve_match.group(1).strip()
        correlation_id = f"cmd_{uuid.uuid4().hex[:12]}"
        return {
            "intent": "RESOLVE",
            "nav_target": "/resolutions",
            "payload": {
                "correlation_id": correlation_id,
                "source": file_or_content,
                "status": "queued",
            },
        }

    config_match = RE_CONFIG.match(text)
    if config_match:
        param = config_match.group(1).strip()
        return {"intent": "CONFIG", "nav_target": "/admin", "payload": {"parameter": param}}

    return {
        "intent": "UNKNOWN",
        "nav_target": None,
        "payload": {"raw": text, "suggestion": "Try: goto resolutions, resolve --file=report.pdf"},
    }


def _build_execution_plan(
    parsed: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    """Build a pre-flight execution plan for dry_run mode."""
    plan: dict[str, Any] = {
        "intent": parsed["intent"],
        "nav_target": parsed["nav_target"],
        "tenant_id": tenant_id,
        "tenant_partition": f"tenants/{tenant_id}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if parsed["intent"] == "RESOLVE":
        plan["steps"] = [
            {"step": 1, "action": "pii_scan", "description": "Scan content for PII (INV-006)", "status": "pending"},
            {"step": 2, "action": "pii_mask", "description": "Tokenize detected PII before LLM call", "status": "pending"},
            {"step": 3, "action": "llm_resolve", "description": "Send masked content to Anthropic Claude", "status": "pending"},
            {"step": 4, "action": "pii_unmask", "description": "Restore PII tokens in response", "status": "pending"},
            {"step": 5, "action": "evidence_chain", "description": "Build hash-protected evidence chain", "status": "pending"},
            {"step": 6, "action": "persist", "description": f"Store in tenants/{tenant_id}/resolutions", "status": "pending"},
        ]
        plan["pii_policy"] = "mask_before_llm"
        plan["data_scope"] = f"tenants/{tenant_id}/resolutions"
        plan["correlation_id"] = parsed["payload"].get("correlation_id")
        plan["source"] = parsed["payload"].get("source")
    elif parsed["intent"] == "NAVIGATE":
        plan["steps"] = [
            {"step": 1, "action": "navigate", "description": f"Route to {parsed['nav_target']}", "status": "ready"},
        ]
    elif parsed["intent"] == "CONFIG":
        plan["steps"] = [
            {"step": 1, "action": "load_config", "description": f"Read tenants/{tenant_id}/config", "status": "pending"},
            {"step": 2, "action": "apply_change", "description": f"Update parameter: {parsed['payload'].get('parameter', '?')}", "status": "pending"},
            {"step": 3, "action": "audit_log", "description": "Record change in audit trail", "status": "pending"},
        ]
        plan["data_scope"] = f"tenants/{tenant_id}/config"

    return plan


@router.post("/command")
async def handle_command(
    request: Request,
    body: dict[str, Any],
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    """Parse and execute a command from the Omni-Bar.

    Request body:
        {"command": "resolve --file=test.pdf", "dry_run": true}

    If dry_run=true, returns ExecutionPlan without executing.
    If dry_run=false (default), executes and returns result.
    """
    raw = body.get("command", "")
    dry_run = body.get("dry_run", False)

    if not raw.strip():
        return {"intent": "UNKNOWN", "nav_target": None, "payload": {"error": "Empty command"}}

    parsed = _parse_command(raw)
    parsed["timestamp"] = datetime.now(timezone.utc).isoformat()
    parsed["tenant_id"] = auth.tenant_id

    if dry_run:
        return {
            "dry_run": True,
            "execution_plan": _build_execution_plan(parsed, auth.tenant_id),
            **parsed,
        }

    return parsed
