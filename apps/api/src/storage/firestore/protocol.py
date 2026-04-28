"""Protocol for Firestore client abstraction.

Allows InMemoryFirestore (testing) and FirestoreClient (production) to be swapped.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FirestoreClientProtocol(Protocol):
    """Minimal interface that both InMemoryFirestore and real Firestore satisfy."""

    def collection(self, path: str) -> Any: ...
