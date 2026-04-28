"""Versioned prompt management — immutable prompt registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """An immutable prompt template."""
    version: str
    system: str
    user_template: str


# Prompt registry — versioned, immutable
PROMPTS: dict[str, dict[str, Prompt]] = {
    "resolution_analysis": {
        "1.0": Prompt(
            version="1.0",
            system="You are an expert compliance analyst. Analyze the document and provide a resolution.",
            user_template="Analyze this document and determine the compliance status:\n\n{content}",
        ),
    },
    "resolution_with_context": {
        "1.0": Prompt(
            version="1.0",
            system="You are an expert compliance analyst with access to prior resolutions.",
            user_template="Analyze this document with additional context:\n\nDocument: {content}\n\nContext: {context}",
        ),
    },
}


def get_prompt(prompt_name: str, version: str = "1.0") -> Prompt:
    """Get a prompt by name and version.

    Args:
        prompt_name: Name of the prompt template.
        version: Version string (default: "1.0").

    Returns:
        Prompt template.

    Raises:
        KeyError: If prompt or version not found.
    """
    versions = PROMPTS.get(prompt_name)
    if versions is None:
        raise KeyError(f"Prompt '{prompt_name}' not found")
    prompt = versions.get(version)
    if prompt is None:
        raise KeyError(f"Prompt '{prompt_name}' version '{version}' not found")
    return prompt
