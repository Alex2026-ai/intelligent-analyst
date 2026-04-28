"""Evidence-specific exceptions."""

from __future__ import annotations


class EvidenceIntegrityError(Exception):
    """Raised when evidence chain integrity verification fails.

    Contains chain_id, node_id (if applicable), expected and actual hashes.
    """

    def __init__(
        self,
        message: str,
        chain_id: str,
        node_id: str | None = None,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
    ) -> None:
        super().__init__(message)
        self.chain_id = chain_id
        self.node_id = node_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


class ChainNotFoundError(Exception):
    """Raised when a requested evidence chain does not exist."""

    def __init__(self, chain_id: str) -> None:
        super().__init__(f"Evidence chain not found: {chain_id}")
        self.chain_id = chain_id


class ChainClosedError(Exception):
    """Raised when attempting to modify a completed evidence chain."""

    def __init__(self, chain_id: str) -> None:
        super().__init__(f"Evidence chain is closed: {chain_id}")
        self.chain_id = chain_id
