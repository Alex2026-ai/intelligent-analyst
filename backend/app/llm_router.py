"""
llm_router.py — Minimal L3 model abstraction + soft failover.

Drives model selection from environment variables. Provides a single
call_l3_with_failover() wrapper used by both company and person L3 resolvers.

Env vars:
    L3_PRIMARY_PROVIDER     "anthropic" (default)
    L3_PRIMARY_MODEL        "claude-3-haiku-20240307" (default)
    L3_SECONDARY_PROVIDER   "" = disabled (default)
    L3_SECONDARY_MODEL      ""
    L3_SECONDARY_API_KEY    ""
    L3_SECONDARY_BASE_URL   "" (e.g. "https://openrouter.ai/api/v1")
    L3_SECONDARY_COST_PER_CALL_USD  "0.005"
"""

import os
import time
import traceback
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------

L3_PRIMARY_PROVIDER = os.getenv("L3_PRIMARY_PROVIDER", "anthropic")
L3_PRIMARY_MODEL = os.getenv("L3_PRIMARY_MODEL", "claude-3-haiku-20240307")
L3_SECONDARY_PROVIDER = os.getenv("L3_SECONDARY_PROVIDER", "")
L3_SECONDARY_MODEL = os.getenv("L3_SECONDARY_MODEL", "")
L3_SECONDARY_API_KEY = os.getenv("L3_SECONDARY_API_KEY", "")
L3_SECONDARY_BASE_URL = os.getenv("L3_SECONDARY_BASE_URL", "")
L3_SECONDARY_COST_PER_CALL_USD = float(
    os.getenv("L3_SECONDARY_COST_PER_CALL_USD", "0.005")
)


@dataclass
class LLMProviderConfig:
    provider: str           # "anthropic" | "openrouter"
    model: str              # model ID string
    api_key: str
    base_url: Optional[str] = None
    cost_per_call_usd: float = 0.005


@dataclass
class LLMCallResult:
    text: str
    provider_used: str
    model_used: str
    failover_used: bool = False
    attempts: int = 1


def get_active_model_config() -> LLMProviderConfig:
    """Return current primary config from env vars."""
    return LLMProviderConfig(
        provider=L3_PRIMARY_PROVIDER,
        model=L3_PRIMARY_MODEL,
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        cost_per_call_usd=float(os.getenv("L3_COST_PER_CALL_USD", "0.005")),
    )


def get_secondary_config() -> Optional[LLMProviderConfig]:
    """Return secondary config, or None if not configured."""
    if not L3_SECONDARY_PROVIDER or not L3_SECONDARY_MODEL:
        return None
    return LLMProviderConfig(
        provider=L3_SECONDARY_PROVIDER,
        model=L3_SECONDARY_MODEL,
        api_key=L3_SECONDARY_API_KEY,
        base_url=L3_SECONDARY_BASE_URL or None,
        cost_per_call_usd=L3_SECONDARY_COST_PER_CALL_USD,
    )


# ---------------------------------------------------------------------------
# Raw provider call (single attempt, no retries)
# ---------------------------------------------------------------------------

def _call_provider(config: LLMProviderConfig, messages: list, max_tokens: int) -> str:
    """
    Single raw LLM call. No retries. Raises on error.

    Supported providers:
      - "anthropic": uses anthropic.Anthropic SDK
      - "openrouter": uses httpx POST (Messages API compatible)
    """
    if config.provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=config.api_key)
        message = client.messages.create(
            model=config.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return message.content[0].text

    elif config.provider == "openrouter":
        import httpx
        if not config.base_url:
            raise ValueError("openrouter requires L3_SECONDARY_BASE_URL")
        resp = httpx.post(
            f"{config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "max_tokens": max_tokens,
                "messages": messages,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    else:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")


# ---------------------------------------------------------------------------
# Failover logic
# ---------------------------------------------------------------------------

def should_failover(error: Exception) -> bool:
    """True only for 429 (rate limit) or 503 (service unavailable)."""
    error_str = str(error).lower()
    # Anthropic SDK raises specific exception types
    error_type = type(error).__name__.lower()

    if "429" in str(error) or "rate_limit" in error_str or "ratelimit" in error_type:
        return True
    if "503" in str(error) or "service_unavailable" in error_str or "serviceunavailable" in error_type:
        return True
    return False


def call_l3_with_failover(
    messages: list,
    max_tokens: int = 100,
) -> LLMCallResult:
    """
    Central L3 wrapper with retry + soft failover.

    1. Primary: up to 3 attempts (1 + 2 retries) with exponential backoff on 429/503
    2. If all primary attempts fail with 429/503 AND secondary is configured:
       → exactly 1 attempt on secondary
    3. If secondary also fails → raise original primary exception

    Returns LLMCallResult with response text + provider metadata.
    """
    primary = get_active_model_config()
    secondary = get_secondary_config()

    max_retries = 2
    base_delay = 0.5
    primary_error = None
    total_attempts = 0

    # --- Primary attempts ---
    for attempt in range(max_retries + 1):
        total_attempts += 1
        try:
            text = _call_provider(primary, messages, max_tokens)
            return LLMCallResult(
                text=text,
                provider_used=primary.provider,
                model_used=primary.model,
                failover_used=False,
                attempts=total_attempts,
            )
        except Exception as e:
            primary_error = e
            if should_failover(e) and attempt < max_retries:
                delay = base_delay * (2 ** attempt) + (time.time() % 0.5)
                print(
                    f"[llm_router] Primary {primary.provider} attempt {attempt + 1}/{max_retries + 1} "
                    f"failed ({type(e).__name__}), retry in {delay:.2f}s",
                    flush=True,
                )
                time.sleep(delay)
                continue
            elif not should_failover(e):
                # Non-retryable error — raise immediately
                raise

    # --- All primary retries exhausted with retryable error ---
    if secondary is None:
        print(
            f"[llm_router] Primary exhausted, no secondary configured. Raising.",
            flush=True,
        )
        raise primary_error

    # --- Single secondary attempt ---
    total_attempts += 1
    print(
        f"[llm_router] Primary exhausted. Failover → {secondary.provider}/{secondary.model}",
        flush=True,
    )
    try:
        text = _call_provider(secondary, messages, max_tokens)
        return LLMCallResult(
            text=text,
            provider_used=secondary.provider,
            model_used=secondary.model,
            failover_used=True,
            attempts=total_attempts,
        )
    except Exception as secondary_error:
        print(
            f"[llm_router] Secondary also failed: {secondary_error}",
            flush=True,
        )
        traceback.print_exc()
        # Raise the ORIGINAL primary error per spec
        raise primary_error
