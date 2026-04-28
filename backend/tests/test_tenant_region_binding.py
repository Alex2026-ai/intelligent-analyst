"""
Tenant Region Binding Tests (Phase 1)

Tests for:
- Region resolution with Firestore mocking
- Cache behavior (TTL, hit/miss)
- Region validation (match/mismatch)
- Attestation payload and manifest region fields
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.security.tenant_region import (
    resolve_tenant_region,
    validate_tenant_region,
    get_tenant_region_metrics,
    clear_region_cache,
    TENANT_REGION_CACHE_TTL_SECONDS,
)
from app.security.iavp import (
    build_attestation_payload,
    build_iavp_manifest,
    IAVP_PROTOCOL_VERSION,
    ReplayVerificationResult,
)


# ============================================================================
# HELPERS
# ============================================================================

def _mock_firestore_db(doc_exists: bool, doc_data: dict = None):
    """Build a mock Firestore DB that returns a single document."""
    mock_db = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()

    mock_doc_snapshot.exists = doc_exists
    mock_doc_snapshot.to_dict.return_value = doc_data if doc_exists else None

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_doc_ref.set = MagicMock()

    mock_db.collection.return_value.document.return_value = mock_doc_ref

    return mock_db, mock_doc_ref


# ============================================================================
# TEST 1: Missing region defaults to "us"
# ============================================================================

class TestRegionResolution:

    def setup_method(self):
        clear_region_cache()

    def test_missing_region_defaults_to_us(self):
        """Firestore doc exists but has no region field -> returns 'us'."""
        mock_db, mock_doc_ref = _mock_firestore_db(
            doc_exists=True, doc_data={"some_field": "value"}
        )

        region = resolve_tenant_region("tenant-legacy", mock_db, "eu")

        assert region == "us"
        # Should have backfilled the region
        mock_doc_ref.set.assert_called_once()
        call_args = mock_doc_ref.set.call_args
        assert call_args[0][0]["region"] == "us"
        assert call_args[1]["merge"] is True

    # ========================================================================
    # TEST 2: No doc auto-assigns deploy_region
    # ========================================================================

    def test_no_doc_auto_assigns_deploy_region(self):
        """No Firestore doc -> auto-assigns deploy_region, writes doc."""
        mock_db, mock_doc_ref = _mock_firestore_db(doc_exists=False)

        region = resolve_tenant_region("tenant-new", mock_db, "eu")

        assert region == "eu"
        mock_doc_ref.set.assert_called_once()
        call_args = mock_doc_ref.set.call_args
        assert call_args[0][0]["region"] == "eu"
        assert call_args[0][0]["region_auto_assigned"] is True
        assert call_args[1]["merge"] is True


# ============================================================================
# TEST 3-5: Region validation
# ============================================================================

class TestRegionValidation:

    def test_region_eu_on_us_service_rejects(self):
        assert validate_tenant_region("eu", "us") is False

    def test_region_us_on_eu_service_rejects(self):
        assert validate_tenant_region("us", "eu") is False

    def test_matching_region_passes(self):
        assert validate_tenant_region("eu", "eu") is True
        assert validate_tenant_region("us", "us") is True


# ============================================================================
# TEST 6: Cache prevents repeat reads
# ============================================================================

class TestRegionCache:

    def setup_method(self):
        clear_region_cache()

    def test_cache_prevents_repeat_reads(self):
        """Two calls for the same tenant should only hit Firestore once."""
        mock_db, mock_doc_ref = _mock_firestore_db(
            doc_exists=True, doc_data={"region": "eu"}
        )

        region1 = resolve_tenant_region("tenant-cached", mock_db, "us")
        region2 = resolve_tenant_region("tenant-cached", mock_db, "us")

        assert region1 == "eu"
        assert region2 == "eu"
        # Firestore .get() should have been called exactly once
        mock_doc_ref.get.assert_called_once()


# ============================================================================
# TEST 7: Attestation payload has 15 fields
# ============================================================================

class TestAttestationRegionBinding:

    def test_attestation_payload_has_15_fields(self):
        """Build with tenant_region='eu', assert 15 fields."""
        payload = build_attestation_payload(
            batch_id="BATCH-TEST-REGION",
            root_hash="a" * 64,
            artifact_mode="PRODUCTION_REAL",
            engine_version="3.0.0",
            environment="prod",
            protocol_version=IAVP_PROTOCOL_VERSION,
            config_hash="b" * 64,
            dataset_hash="c" * 64,
            key_id="projects/test/locations/us/keyRings/test/cryptoKeys/test",
            metrics_hash="d" * 64,
            record_count=1000,
            signed_at_utc="2026-02-20T12:00:00.000000Z",
            tenant_id_hash="abcd1234",
            tenant_region="eu",
        )

        assert len(payload) == 15
        assert payload["tenant_region"] == "eu"
        assert "tenant_id_hash_sha256" in payload
        assert "attestation_version" in payload


# ============================================================================
# TEST 8: Manifest includes tenant_region
# ============================================================================

class TestManifestRegionBinding:

    def test_manifest_includes_tenant_region(self):
        """Build manifest, assert manifest['tenant_region'] == 'eu'."""
        replay_result = ReplayVerificationResult()
        replay_result.add_run("a" * 64)
        replay_result.add_run("a" * 64)
        replay_result.add_run("a" * 64)

        manifest = build_iavp_manifest(
            batch_id="BATCH-TEST-MANIFEST",
            artifact_type="BATCH_ATTESTATION",
            artifact_mode="PRODUCTION_REAL",
            engine_version="3.0.0",
            config_hash="b" * 64,
            dataset_hash="c" * 64,
            root_hash="a" * 64,
            record_count=500,
            metrics={"l1_pct": 80.0, "l2_pct": 10.0, "l3_pct": 5.0, "l4_pct": 5.0},
            replay_result=replay_result,
            key_id="projects/test/locations/us/keyRings/test/cryptoKeys/test",
            pubkey_fingerprint="fp-test",
            tenant_id_hash="abcd1234",
            tenant_region="eu",
        )

        assert manifest["tenant_region"] == "eu"
        assert manifest["tenant_id_hash_sha256"] == "abcd1234"
