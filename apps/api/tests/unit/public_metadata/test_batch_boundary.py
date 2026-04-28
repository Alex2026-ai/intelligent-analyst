"""Regression test: batch resolve does NOT invoke PMC.

This is a locked architectural boundary per docs/architecture/public-metadata-controller.md.
"""

from unittest.mock import patch

from apps.api.src.public_metadata.store import SAMPLES_PATH, DECISIONS_PATH
from apps.api.src.public_metadata.store import PublicMetadataStore
from apps.api.tests.conftest import VALID_TOKEN, auth_header


class TestBatchDoesNotInvokePMC:
    def test_batch_resolve_no_pmc_call(self, client):
        """POST /v1/resolve/batch must not call _try_pmc_candidate."""
        with patch("apps.api.src.routes.resolve._try_pmc_candidate") as mock_pmc:
            resp = client.post(
                "/v1/resolve/batch",
                json={
                    "documents": [
                        {"document_id": "d1", "document_type": "regulatory", "content": "batch test 1"},
                        {"document_id": "d2", "document_type": "financial", "content": "batch test 2"},
                    ],
                },
                headers={**auth_header(), "Idempotency-Key": "batch-pmc-boundary"},
            )
            assert resp.status_code == 200
            mock_pmc.assert_not_called()

    def test_batch_creates_no_public_decisions(self, client, app):
        """Batch resolve must not create any PMC decisions in platform storage."""
        resp = client.post(
            "/v1/resolve/batch",
            json={
                "documents": [
                    {"document_id": "d1", "document_type": "regulatory", "content": "test"},
                ],
            },
            headers={**auth_header(), "Idempotency-Key": "batch-pmc-no-decisions"},
        )
        assert resp.status_code == 200
        db = app.state.firestore_client
        decisions = db.collection(DECISIONS_PATH).stream()
        # Filter to only decisions from this test (check source_resolution_id)
        batch_decisions = [d for _, d in decisions if d.get("source_resolution_id", "").startswith("d1")]
        assert len(batch_decisions) == 0

    def test_batch_creates_no_public_samples(self, client, app):
        """Batch resolve must not create any PMC samples in platform storage."""
        resp = client.post(
            "/v1/resolve/batch",
            json={
                "documents": [
                    {"document_id": "d1", "document_type": "financial", "content": "test"},
                ],
            },
            headers={**auth_header(), "Idempotency-Key": "batch-pmc-no-samples"},
        )
        assert resp.status_code == 200
        db = app.state.firestore_client
        samples = db.collection(SAMPLES_PATH).stream()
        assert len(samples) == 0
