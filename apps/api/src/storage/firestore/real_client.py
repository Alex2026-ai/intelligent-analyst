"""Real Firestore client wrapping google-cloud-firestore.

Uses Application Default Credentials (ADC) — no secrets in code (FP-004).
Pass project= for explicit project binding.
"""

from __future__ import annotations

from typing import Any

from google.cloud import firestore


class FirestoreClient:
    """Production Firestore client.

    Satisfies FirestoreClientProtocol.
    """

    def __init__(self, project: str | None = None) -> None:
        self._client = firestore.AsyncClient(project=project)

    @property
    def native_client(self) -> firestore.AsyncClient:
        return self._client

    def collection(self, path: str) -> Any:
        """Returns an AsyncCollectionReference scoped to the given path."""
        return self._client.collection(path)

    async def close(self) -> None:
        """Close the underlying gRPC channel."""
        self._client.close()
