"""Tests for release attestation validation."""

import os
import tempfile

from apps.api.src.startup.attestation import compute_file_checksum, validate_attestation


class TestAttestation:
    def test_valid_manifest(self):
        result = validate_attestation(manifest={
            "git_commit_sha": "abc123",
            "sbom_hash": "sha256:xyz",
            "file_checksums": {},
        })
        assert result.valid is True

    def test_missing_manifest(self):
        result = validate_attestation(manifest=None)
        assert result.valid is False
        assert "manifest" in result.errors[0].lower()

    def test_missing_commit_sha(self):
        result = validate_attestation(manifest={
            "sbom_hash": "sha256:xyz",
            "file_checksums": {},
        })
        assert result.checks["build_metadata"] is False

    def test_missing_sbom(self):
        result = validate_attestation(manifest={
            "git_commit_sha": "abc",
            "file_checksums": {},
        })
        assert result.checks["sbom_present"] is False

    def test_checksum_match(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".py") as f:
            f.write(b"test content")
            filepath = f.name
        try:
            expected = compute_file_checksum(filepath)
            result = validate_attestation(
                manifest={
                    "git_commit_sha": "abc",
                    "sbom_hash": "xyz",
                    "file_checksums": {filepath: expected},
                },
                base_path="",
            )
            assert result.valid is True
        finally:
            os.unlink(filepath)

    def test_checksum_mismatch(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".py") as f:
            f.write(b"test content")
            filepath = f.name
        try:
            result = validate_attestation(
                manifest={
                    "git_commit_sha": "abc",
                    "sbom_hash": "xyz",
                    "file_checksums": {filepath: "wrong_hash"},
                },
                base_path="",
            )
            assert result.valid is False
        finally:
            os.unlink(filepath)

    def test_missing_critical_file(self):
        result = validate_attestation(
            manifest={
                "git_commit_sha": "abc",
                "sbom_hash": "xyz",
                "file_checksums": {"nonexistent.py": "hash"},
            },
        )
        assert result.valid is False
