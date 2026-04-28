"""
Tests for receipt path builder, GCS bundle writer, and idempotency.

Phase 1B test coverage:
- receipt path builder correctness
- deterministic receipt_id
- idempotent retry (mock GCS)
- missing secret fail-closed
- partial write does not produce Firestore pointer
"""

import hashlib
import json
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

os.environ.setdefault("HMAC_SCOPE_KEY", "aa" * 32)

from app.attestation.receipt_paths import (
    build_receipt_prefix,
    manifest_path,
    signature_path,
    metadata_path,
    deterministic_receipt_id,
    get_receipt_bucket,
)
from app.attestation.receipt_writer import (
    write_receipt_bundle,
    build_firestore_receipt_pointer,
    _write_blob_idempotent,
)
from app.security.iavp import jcs_canonicalize


# ---------------------------------------------------------------------------
# Receipt path builder
# ---------------------------------------------------------------------------

class TestReceiptPaths:

    def test_build_receipt_prefix(self):
        prefix = build_receipt_prefix("a1b2c3d4e5f6a7b8", "abc-def-123")
        assert prefix == "receipts/a1b2c3d4e5f6a7b8/abc-def-123"

    def test_manifest_path(self):
        p = manifest_path("a1b2c3d4e5f6a7b8", "rid-001")
        assert p == "receipts/a1b2c3d4e5f6a7b8/rid-001/manifest.json"

    def test_signature_path(self):
        p = signature_path("a1b2c3d4e5f6a7b8", "rid-001")
        assert p == "receipts/a1b2c3d4e5f6a7b8/rid-001/signature.der"

    def test_metadata_path(self):
        p = metadata_path("a1b2c3d4e5f6a7b8", "rid-001")
        assert p == "receipts/a1b2c3d4e5f6a7b8/rid-001/receipt_metadata.json"

    def test_invalid_tenant_scope_length(self):
        with pytest.raises(ValueError, match="tenant_scope"):
            build_receipt_prefix("abc", "rid")

    def test_empty_receipt_id(self):
        with pytest.raises(ValueError, match="receipt_id"):
            build_receipt_prefix("a1b2c3d4e5f6a7b8", "")


class TestDeterministicReceiptId:

    def test_deterministic(self):
        """Same inputs → same receipt_id."""
        r1 = deterministic_receipt_id("BATCH-ABC", "f" * 64)
        r2 = deterministic_receipt_id("BATCH-ABC", "f" * 64)
        assert r1 == r2

    def test_different_batch_different_id(self):
        r1 = deterministic_receipt_id("BATCH-AAA", "f" * 64)
        r2 = deterministic_receipt_id("BATCH-BBB", "f" * 64)
        assert r1 != r2

    def test_different_hash_different_id(self):
        r1 = deterministic_receipt_id("BATCH-AAA", "a" * 64)
        r2 = deterministic_receipt_id("BATCH-AAA", "b" * 64)
        assert r1 != r2

    def test_uuid_format(self):
        r = deterministic_receipt_id("BATCH-X", "c" * 64)
        parts = r.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_missing_inputs(self):
        with pytest.raises(ValueError):
            deterministic_receipt_id("", "f" * 64)
        with pytest.raises(ValueError):
            deterministic_receipt_id("BATCH-X", "")


class TestGetReceiptBucket:

    def test_reads_env(self):
        os.environ["RECEIPT_BUCKET"] = "my-test-bucket"
        try:
            assert get_receipt_bucket() == "my-test-bucket"
        finally:
            del os.environ["RECEIPT_BUCKET"]

    def test_missing_raises(self):
        old = os.environ.pop("RECEIPT_BUCKET", None)
        try:
            with pytest.raises(ValueError, match="RECEIPT_BUCKET"):
                get_receipt_bucket()
        finally:
            if old is not None:
                os.environ["RECEIPT_BUCKET"] = old


# ---------------------------------------------------------------------------
# GCS blob write (mocked)
# ---------------------------------------------------------------------------

class TestWriteBlobIdempotent:

    @patch("app.attestation.receipt_writer._get_gcs_client")
    def test_first_write_succeeds(self, mock_client):
        """First write creates the object."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket
        mock_blob.upload_from_string.return_value = None  # success

        wrote, status = _write_blob_idempotent(
            "bucket", "path/obj.json", b"data", "application/json"
        )
        assert wrote is True
        assert status == "created"
        mock_blob.upload_from_string.assert_called_once()

    @patch("app.attestation.receipt_writer._get_gcs_client")
    def test_idempotent_skip_on_match(self, mock_client):
        """Existing object with matching hash → idempotent skip."""
        data = b"manifest content"
        expected_hash = hashlib.sha256(data).hexdigest().lower()

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        # First upload fails with 412 (precondition)
        from app.attestation.receipt_writer import gcs_exceptions
        if gcs_exceptions:
            mock_blob.upload_from_string.side_effect = gcs_exceptions.PreconditionFailed("412")
        else:
            mock_blob.upload_from_string.side_effect = Exception("412 conditionNotMet")

        mock_blob.download_as_bytes.return_value = data

        wrote, status = _write_blob_idempotent(
            "bucket", "path/obj.json", data, "application/json",
            expected_hash=expected_hash,
        )
        assert wrote is False
        assert status == "idempotent_skip"

    @patch("app.attestation.receipt_writer._get_gcs_client")
    def test_corruption_detected(self, mock_client):
        """Existing object with different hash → RuntimeError."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        mock_blob.upload_from_string.side_effect = Exception("412 conditionNotMet")
        mock_blob.download_as_bytes.return_value = b"DIFFERENT DATA"

        with pytest.raises(RuntimeError, match="corruption"):
            _write_blob_idempotent(
                "bucket", "path/obj.json", b"original", "application/json",
                expected_hash=hashlib.sha256(b"original").hexdigest(),
            )

    @patch("app.attestation.receipt_writer._get_gcs_client")
    def test_no_client_raises(self, mock_client):
        mock_client.return_value = None
        with pytest.raises(RuntimeError, match="GCS client"):
            _write_blob_idempotent("b", "p", b"d", "t")


# ---------------------------------------------------------------------------
# Receipt bundle writer (mocked GCS)
# ---------------------------------------------------------------------------

class TestWriteReceiptBundle:

    @patch("app.attestation.receipt_writer._get_gcs_client")
    @patch("app.attestation.receipt_writer.get_receipt_bucket")
    def test_writes_three_objects(self, mock_bucket, mock_client):
        """Bundle write creates manifest, signature, and metadata."""
        mock_bucket.return_value = "test-receipts"
        mock_gcs_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_gcs_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_gcs_bucket

        manifest = {
            "protocol_version": "ia-attestation/v1",
            "batch_id": "BATCH-TEST",
            "receipt_id": "r-001",
        }
        sig_bytes = b"\x00\x01\x02"

        result = write_receipt_bundle(
            manifest=manifest,
            signature_bytes=sig_bytes,
            tenant_scope="a1b2c3d4e5f6a7b8",
            receipt_id="r-001",
            batch_id="BATCH-TEST",
            environment="test",
        )

        assert result["receipt_id"] == "r-001"
        assert result["bucket"] == "test-receipts"
        assert "manifest_hash" in result
        assert len(result["manifest_hash"]) == 64

        # 3 blobs written
        assert mock_blob.upload_from_string.call_count == 3

    @patch("app.attestation.receipt_writer._get_gcs_client")
    @patch("app.attestation.receipt_writer.get_receipt_bucket")
    def test_manifest_is_jcs_bytes(self, mock_bucket, mock_client):
        """manifest.json is written as JCS canonical bytes, not pretty-printed."""
        mock_bucket.return_value = "test-receipts"
        mock_gcs_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_gcs_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_gcs_bucket

        written_data = []
        mock_blob.upload_from_string.side_effect = lambda data, **kw: written_data.append(data)

        manifest = {"z_field": "last", "a_field": "first"}

        write_receipt_bundle(
            manifest=manifest,
            signature_bytes=b"sig",
            tenant_scope="a1b2c3d4e5f6a7b8",
            receipt_id="r-002",
            batch_id="BATCH-T",
            environment="test",
        )

        # First write is manifest.json — must be JCS bytes
        manifest_written = written_data[0]
        expected_jcs = jcs_canonicalize(manifest)
        assert manifest_written == expected_jcs


# ---------------------------------------------------------------------------
# Firestore pointer
# ---------------------------------------------------------------------------

class TestFirestorePointer:

    def test_pointer_shape(self):
        ptr = build_firestore_receipt_pointer(
            receipt_id="r-001",
            gcs_prefix="gs://bucket/receipts/scope/r-001",
        )
        assert ptr["id"] == "r-001"
        assert ptr["gcs_path"] == "gs://bucket/receipts/scope/r-001"
        assert ptr["version"] == "ia-attestation/v1"
        assert "finalized_at" in ptr

    def test_no_pii_in_pointer(self):
        """Pointer must not contain raw tenant_id or company names."""
        ptr = build_firestore_receipt_pointer("r-001", "gs://b/p")
        ptr_json = json.dumps(ptr)
        assert "tenant_id" not in ptr_json.lower() or "tenant" not in ptr_json
        # Only allowed fields
        assert set(ptr.keys()) == {"id", "gcs_path", "version", "finalized_at"}


# ---------------------------------------------------------------------------
# Missing secret fail-closed
# ---------------------------------------------------------------------------

class TestMissingSecretFailsClosed:

    def test_hmac_scope_key_required(self):
        """compute_tenant_scope raises if no key."""
        from app.utils.hashing import compute_tenant_scope
        old = os.environ.pop("HMAC_SCOPE_KEY", None)
        try:
            with pytest.raises(ValueError, match="HMAC_SCOPE_KEY"):
                compute_tenant_scope("tenant_x", scope_key=None)
        finally:
            if old:
                os.environ["HMAC_SCOPE_KEY"] = old
            else:
                os.environ["HMAC_SCOPE_KEY"] = "aa" * 32


# ---------------------------------------------------------------------------
# Partial write safety
# ---------------------------------------------------------------------------

class TestPartialWriteSafety:

    @patch("app.attestation.receipt_writer._get_gcs_client")
    @patch("app.attestation.receipt_writer.get_receipt_bucket")
    def test_signature_failure_does_not_produce_pointer(self, mock_bucket, mock_client):
        """If signature write fails, no Firestore pointer should be built."""
        mock_bucket.return_value = "test-receipts"
        mock_gcs_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_gcs_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_gcs_bucket

        call_count = [0]
        def fail_on_second(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # signature write
                raise RuntimeError("GCS write failed")

        mock_blob.upload_from_string.side_effect = fail_on_second

        with pytest.raises(RuntimeError, match="GCS write failed"):
            write_receipt_bundle(
                manifest={"protocol_version": "ia-attestation/v1"},
                signature_bytes=b"sig",
                tenant_scope="a1b2c3d4e5f6a7b8",
                receipt_id="r-003",
                batch_id="BATCH-FAIL",
                environment="test",
            )

        # If write_receipt_bundle raises, the caller in server_enterprise_golden.py
        # will NOT build _receipt_pointer (it's in the except block).
        # This test verifies the exception propagates.
