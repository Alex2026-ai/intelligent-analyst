"""Anthropic Claude provider implementation.

API key sourced from ANTHROPIC_API_KEY environment variable (FP-004).
Content is already PII-masked when it reaches this provider (INV-006).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import anthropic

from apps.api.src.llm.provider import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """Real Anthropic Claude provider.

    API key from environment only — no hardcoded secrets (FP-004).
    Expects PII-masked content — masking happens upstream (INV-006).
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set (FP-004: no hardcoded secrets)")
        self._client = anthropic.AsyncAnthropic(api_key=key)

    @property
    def name(self) -> str:
        return "anthropic"

    async def resolve(
        self,
        masked_content: str,
        context: dict[str, Any],
        prompt_version: str,
    ) -> LLMResponse:
        """Send PII-masked content to Claude for resolution analysis."""
        start_ms = int(time.time() * 1000)

        system_prompt = self._build_system_prompt(context, prompt_version)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": masked_content}],
        )

        elapsed_ms = int(time.time() * 1000) - start_ms
        raw_text = response.content[0].text if response.content else ""

        parsed = self._parse_response(raw_text)

        return LLMResponse(
            resolution=parsed.get("resolution", raw_text),
            confidence=parsed.get("confidence", 0.0),
            provider=self.name,
            model=self._model,
            prompt_version=prompt_version,
            latency_ms=elapsed_ms,
            raw_response=raw_text,
        )

    def _build_system_prompt(self, context: dict[str, Any], prompt_version: str) -> str:
        """Build the system prompt for resolution analysis.

        Uses structured JSON output format for reliable parsing.
        """
        doc_type = context.get("document_type", "unknown")
        return (
            "You are Intelligent Analyst, a document resolution engine. "
            f"Document type: {doc_type}. Prompt version: {prompt_version}.\n\n"
            "Analyze the provided document content and produce a resolution.\n"
            "IMPORTANT: The content has been PII-masked. Work with masked tokens as-is.\n\n"
            "Respond in this exact JSON format:\n"
            "{\n"
            '  "resolution": "<your resolution text>",\n'
            '  "confidence": <float 0.0-1.0>,\n'
            '  "reasoning": "<brief reasoning>"\n'
            "}\n\n"
            "If you cannot resolve with confidence >= 0.7, set confidence to your actual "
            "estimate. The system will route low-confidence results to human review."
        )

    @staticmethod
    def _parse_response(raw_text: str) -> dict[str, Any]:
        """Parse structured JSON from LLM response.

        Falls back to raw text as resolution if JSON parsing fails.
        """
        try:
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw_text[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {"resolution": raw_text, "confidence": 0.0}
