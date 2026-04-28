"""PII vault — request-scoped token-to-original mapping.

The vault exists only for the duration of a single request.
It is never persisted, never sent externally, never logged.
"""

from __future__ import annotations


class PIIVault:
    """Request-scoped PII token vault.

    Maps tokens like [SSN_1] back to original PII values.
    Destroyed when the request completes.
    """

    def __init__(self) -> None:
        self._token_to_original: dict[str, str] = {}
        self._original_to_token: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def store(self, category: str, original: str) -> str:
        """Store a PII value and return its token.

        If the same original value was already stored, returns the same token.

        Args:
            category: PII category (e.g., "SSN", "EMAIL").
            original: The original PII value.

        Returns:
            Token string like "[SSN_1]".
        """
        if original in self._original_to_token:
            return self._original_to_token[original]

        count = self._counters.get(category, 0) + 1
        self._counters[category] = count
        token = f"[{category}_{count}]"

        self._token_to_original[token] = original
        self._original_to_token[original] = token
        return token

    def restore(self, token: str) -> str | None:
        """Look up the original PII value for a token.

        Returns None if token not found.
        """
        return self._token_to_original.get(token)

    @property
    def token_count(self) -> int:
        return len(self._token_to_original)

    @property
    def categories_used(self) -> set[str]:
        return set(self._counters.keys())

    def clear(self) -> None:
        """Destroy all mappings. Called at end of request."""
        self._token_to_original.clear()
        self._original_to_token.clear()
        self._counters.clear()
