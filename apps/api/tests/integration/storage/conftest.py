"""Shared fixtures for storage integration tests."""

import pytest

from apps.api.src.storage.firestore.client import InMemoryFirestore
from apps.api.src.storage.gcs.client import InMemoryGCS


@pytest.fixture
def db():
    """Fresh in-memory Firestore for each test."""
    store = InMemoryFirestore()
    yield store
    store.clear()


@pytest.fixture
def gcs():
    """Fresh in-memory GCS for each test."""
    store = InMemoryGCS()
    yield store
    store.clear()
