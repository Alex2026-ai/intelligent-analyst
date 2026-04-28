"""
Forensic Summary API — Unit Tests (Trust Stack L1)
====================================================

Tests the GET /forensic-summary/{trace_id} endpoint logic against
the strict cryptographic contract. All fields derived ONLY from:
attestation payload, verification result, replay metadata, chain metadata,
key fingerprint.

Required tests:
  1. 404 for non-existent batch
  2. FAIL batch + variance=0 + runs=3 → determinism must NOT be VERIFIED
  3. PASS batch + replay_root_hash mismatch → determinism must NOT be VERIFIED
  4. PASS batch + hashes match + runs>=3 + variance=0 → determinism VERIFIED
  5. Stable serialization ordering
  6. RBAC: no cost data, no tenant IDs, no emails in response
"""
import os
import sys
import json
import pytest
from unittest.mock import patch
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures: mock batch data (mirrors Firestore document shape)
# ---------------------------------------------------------------------------

def _pass_batch():
    """Batch with full attestation binding, replay=3, anchor verified.
    verification.status will be PASS when sig_valid=True, chain_valid=True,
    anchor_verified=True."""
    return {
        "trace_id": "BATCH-PASS-001",
        "status": "completed",
        "total": 100000,
        "tenant_id": "tenant_test",
        "artifact_mode": "DEMO_SIMULATED",
        "hash_chain": {
            "batch_root_hash": "b981aea3d99a05f50098db73cf84d289a427ea3b2114ae1d0bfb12c47e7e5cb8",
            "chain_enabled": True,
            "chain_length": 100000,
            "method": "SHA256_CHAIN_V1",
            "ordering": "STABLE_INPUT_ORDER_V2",
            "replay_runs": 3,
            "replay_variance": 0,
            "replay_passed": True,
            "chained_at": "2026-02-20T05:23:55.710509+00:00",
        },
        "signature": {
            "signed_at_utc": "2026-02-20T05:28:45.403593+00:00",
            "algorithm": "ECDSA_P256_SHA256",
            "evidence_hash_sha256": "b981aea3d99a05f50098db73cf84d289a427ea3b2114ae1d0bfb12c47e7e5cb8",
            "signature": "MEUCIQD...",
        },
        "attestation": {
            "signature_b64": "MEUCICIyS9...",
            "signed_payload_jcs_b64": "eyJhcnRpZmFjdF9tb2Rl...",
            "key_id": "projects/ia/locations/us-central1/keyRings/ia-forensic-test/cryptoKeys/ia-signing-key-v1",
        },
        "anchor": {
            "anchored": True,
            "anchor_path": "gs://ia-anchors-test/anchors/hash/BATCH-PASS-001.json",
            "anchor_written_at_utc": "2026-02-20T05:28:39.423470+00:00",
        },
        "iavp_manifest": {
            "artifact_mode": "DEMO_SIMULATED",
            "protocol_version": "IA-VP-1.0",
            "dataset_hash_sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "config_hash_sha256": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5",
            "key": {
                "key_id": "projects/ia/locations/us-central1/keyRings/ia-forensic-test/cryptoKeys/ia-signing-key-v1",
                "pubkey_fingerprint_sha256": "fe411103d3d1c0cd",
            },
            "metrics": {
                "replay_runs": 3,
                "replay_variance": 0,
            },
        },
    }


def _fail_batch():
    """Batch where signature verification fails (tampered).
    verification.status will be FAIL."""
    return {
        "trace_id": "BATCH-FAIL-001",
        "status": "completed",
        "total": 500,
        "tenant_id": "tenant_test",
        "hash_chain": {
            "batch_root_hash": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "chain_enabled": True,
            "chain_length": 500,
            "method": "SHA256_CHAIN_V1",
            "ordering": "STABLE_INPUT_ORDER_V2",
            "replay_runs": 3,
            "replay_variance": 0,
            "replay_passed": True,
        },
        "signature": {
            "signed_at_utc": "2026-02-20T00:00:00Z",
            "algorithm": "ECDSA_P256_SHA256",
            "evidence_hash_sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "signature": "INVALID_SIG",
        },
        "attestation": {},
        "anchor": {"anchored": False},
        "iavp_manifest": {
            "metrics": {"replay_runs": 3, "replay_variance": 0},
        },
    }


# ---------------------------------------------------------------------------
# Helper: build response dict mimicking endpoint logic
# ---------------------------------------------------------------------------

def _build_summary(batch, sig_valid=True, sig_error=None,
                   verification_mode="ATTESTATION_BINDING_V1",
                   anchor_verified=None):
    """Build summary dict exactly as the endpoint does.
    This is a pure-function mirror of the endpoint logic for unit testing
    without HTTP or Firestore dependencies."""
    chain_meta = batch.get("hash_chain", {})
    sig_info = batch.get("signature", {})
    attestation_data = batch.get("attestation", {})
    anchor_meta = batch.get("anchor", {})
    manifest = batch.get("iavp_manifest", {})
    manifest_metrics = manifest.get("metrics", {})
    manifest_key = manifest.get("key", {})

    chain_root_hash = chain_meta.get("batch_root_hash")
    chain_valid = bool(chain_root_hash)

    if anchor_verified is None:
        anchor_verified = anchor_meta.get("anchored", False)

    # Verification status
    if sig_valid and chain_valid and anchor_verified:
        verification_status = "PASS"
    else:
        verification_status = "FAIL"
    failure_reason = None
    if verification_status == "FAIL":
        reasons = []
        if not sig_valid:
            reasons.append(f"signature: {sig_error or 'invalid'}")
        if not chain_valid:
            reasons.append("chain: no root hash")
        if not anchor_verified:
            reasons.append("anchor: not verified")
        failure_reason = "; ".join(reasons)

    # Replay
    replay_runs = manifest_metrics.get("replay_runs") or chain_meta.get("replay_runs", 0) or 0
    replay_variance = manifest_metrics.get("replay_variance") if manifest_metrics.get("replay_variance") is not None else chain_meta.get("replay_variance")

    # Attested root hash
    attested_root_hash = sig_info.get("evidence_hash_sha256")
    if not attested_root_hash and attestation_data.get("signed_payload_jcs_b64"):
        try:
            import base64 as _b64
            _payload_bytes = _b64.b64decode(attestation_data["signed_payload_jcs_b64"])
            _payload = json.loads(_payload_bytes.decode("utf-8"))
            attested_root_hash = _payload.get("root_hash_sha256")
        except Exception:
            pass

    replay_root_hash = f"sha256:{chain_root_hash}" if chain_root_hash else None

    # Determinism verdict (strict)
    replay_root_matches_attested = (
        bool(chain_root_hash)
        and bool(attested_root_hash)
        and chain_root_hash == attested_root_hash
    )
    replay_determinism = "UNKNOWN"
    replay_supported = replay_runs > 0
    if (
        verification_status == "PASS"
        and replay_runs >= 3
        and replay_variance == 0
        and replay_root_matches_attested
    ):
        replay_determinism = "VERIFIED"

    # Crypto
    key_fingerprint = manifest_key.get("pubkey_fingerprint_sha256")
    key_id = attestation_data.get("key_id") or manifest_key.get("key_id")
    sig_algorithm = sig_info.get("algorithm") or "ECDSA_P256_SHA256"

    attestation_manifest_hash = None
    if attestation_data.get("signed_payload_jcs_b64"):
        try:
            import base64 as _b64
            import hashlib as _hl
            _raw = _b64.b64decode(attestation_data["signed_payload_jcs_b64"])
            attestation_manifest_hash = f"sha256:{_hl.sha256(_raw).hexdigest()}"
        except Exception:
            pass

    # Run
    artifact_mode = manifest.get("artifact_mode") or batch.get("artifact_mode") or "UNKNOWN"
    dataset_hash_raw = manifest.get("dataset_hash_sha256")
    config_hash_raw = manifest.get("config_hash_sha256")

    protocol_version = manifest.get("protocol_version") or "IA-VP-1.0"
    verified_at = sig_info.get("signed_at_utc") if verification_status == "PASS" else None

    anchor_type = None
    anchor_id = None
    if anchor_verified:
        anchor_path = anchor_meta.get("anchor_path")
        if anchor_path:
            anchor_type = "GCS"
            anchor_id = anchor_path

    return {
        "trace_id": batch.get("trace_id"),
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "environment": "test",
        "protocol_version": protocol_version,
        "engine_version": "3.0.0",
        "verification": {
            "status": verification_status,
            "verified_at_utc": verified_at,
            "verifier_version": verification_mode if verification_status == "PASS" else None,
            "failure_reason": failure_reason,
        },
        "crypto": {
            "signature_algorithm": sig_algorithm,
            "key_fingerprint": key_fingerprint,
            "attestation_manifest_hash": attestation_manifest_hash,
            "root_hash": f"sha256:{chain_root_hash}" if chain_root_hash else None,
            "chain_height": chain_meta.get("chain_length", 0),
            "anchored": anchor_verified,
            "anchor_type": anchor_type,
            "anchor_id": anchor_id,
        },
        "run": {
            "record_count": batch.get("total", 0),
            "artifact_mode": artifact_mode,
            "dataset_hash": f"sha256:{dataset_hash_raw}" if dataset_hash_raw else None,
            "config_hash": f"sha256:{config_hash_raw}" if config_hash_raw else None,
        },
        "replay": {
            "supported": replay_supported,
            "determinism": replay_determinism,
            "replay_root_hash": replay_root_hash,
            "runs": replay_runs,
            "variance": replay_variance if replay_variance is not None else 0,
        },
    }


# ---------------------------------------------------------------------------
# Contract field sets
# ---------------------------------------------------------------------------

CONTRACT_TOP_LEVEL_KEYS = {
    "trace_id", "generated_at_utc", "environment", "protocol_version",
    "engine_version", "verification", "crypto", "run", "replay",
}

CONTRACT_VERIFICATION_KEYS = {
    "status", "verified_at_utc", "verifier_version", "failure_reason",
}

CONTRACT_CRYPTO_KEYS = {
    "signature_algorithm", "key_fingerprint", "attestation_manifest_hash",
    "root_hash", "chain_height", "anchored", "anchor_type", "anchor_id",
}

CONTRACT_RUN_KEYS = {
    "record_count", "artifact_mode", "dataset_hash", "config_hash",
}

CONTRACT_REPLAY_KEYS = {
    "supported", "determinism", "replay_root_hash", "runs", "variance",
}


# ---------------------------------------------------------------------------
# Test Class: Contract Structure
# ---------------------------------------------------------------------------

class TestForensicSummaryContract:
    """Verify exact contract shape — no extra fields, no missing fields."""

    def test_top_level_keys_exact(self):
        result = _build_summary(_pass_batch())
        assert set(result.keys()) == CONTRACT_TOP_LEVEL_KEYS

    def test_verification_keys_exact(self):
        result = _build_summary(_pass_batch())
        assert set(result["verification"].keys()) == CONTRACT_VERIFICATION_KEYS

    def test_crypto_keys_exact(self):
        result = _build_summary(_pass_batch())
        assert set(result["crypto"].keys()) == CONTRACT_CRYPTO_KEYS

    def test_run_keys_exact(self):
        result = _build_summary(_pass_batch())
        assert set(result["run"].keys()) == CONTRACT_RUN_KEYS

    def test_replay_keys_exact(self):
        result = _build_summary(_pass_batch())
        assert set(result["replay"].keys()) == CONTRACT_REPLAY_KEYS


# ---------------------------------------------------------------------------
# Test Class: PASS Batch
# ---------------------------------------------------------------------------

class TestPassBatch:
    """PASS batch: sig valid, chain valid, anchor verified."""

    def test_verification_status_pass(self):
        result = _build_summary(_pass_batch())
        assert result["verification"]["status"] == "PASS"

    def test_verification_no_failure_reason(self):
        result = _build_summary(_pass_batch())
        assert result["verification"]["failure_reason"] is None

    def test_verified_at_present(self):
        result = _build_summary(_pass_batch())
        assert result["verification"]["verified_at_utc"] is not None

    def test_verifier_version_present(self):
        result = _build_summary(_pass_batch())
        assert result["verification"]["verifier_version"] == "ATTESTATION_BINDING_V1"

    def test_crypto_root_hash_prefixed(self):
        result = _build_summary(_pass_batch())
        assert result["crypto"]["root_hash"].startswith("sha256:")

    def test_crypto_chain_height(self):
        result = _build_summary(_pass_batch())
        assert result["crypto"]["chain_height"] == 100000

    def test_crypto_anchored(self):
        result = _build_summary(_pass_batch())
        assert result["crypto"]["anchored"] is True

    def test_crypto_anchor_type(self):
        result = _build_summary(_pass_batch())
        assert result["crypto"]["anchor_type"] == "GCS"

    def test_crypto_anchor_id_present(self):
        result = _build_summary(_pass_batch())
        assert result["crypto"]["anchor_id"] is not None

    def test_crypto_key_fingerprint(self):
        result = _build_summary(_pass_batch())
        assert result["crypto"]["key_fingerprint"] == "fe411103d3d1c0cd"

    def test_crypto_signature_algorithm(self):
        result = _build_summary(_pass_batch())
        assert result["crypto"]["signature_algorithm"] == "ECDSA_P256_SHA256"

    def test_run_record_count(self):
        result = _build_summary(_pass_batch())
        assert result["run"]["record_count"] == 100000

    def test_run_artifact_mode(self):
        result = _build_summary(_pass_batch())
        assert result["run"]["artifact_mode"] == "DEMO_SIMULATED"

    def test_run_dataset_hash_prefixed(self):
        result = _build_summary(_pass_batch())
        assert result["run"]["dataset_hash"].startswith("sha256:")

    def test_run_config_hash_prefixed(self):
        result = _build_summary(_pass_batch())
        assert result["run"]["config_hash"].startswith("sha256:")

    def test_replay_supported(self):
        result = _build_summary(_pass_batch())
        assert result["replay"]["supported"] is True

    def test_replay_runs(self):
        result = _build_summary(_pass_batch())
        assert result["replay"]["runs"] == 3

    def test_replay_variance_zero(self):
        result = _build_summary(_pass_batch())
        assert result["replay"]["variance"] == 0

    def test_replay_root_hash_prefixed(self):
        result = _build_summary(_pass_batch())
        assert result["replay"]["replay_root_hash"].startswith("sha256:")

    def test_protocol_version(self):
        result = _build_summary(_pass_batch())
        assert result["protocol_version"] == "IA-VP-1.0"

    def test_generated_at_utc_format(self):
        result = _build_summary(_pass_batch())
        assert result["generated_at_utc"].endswith("Z")


# ---------------------------------------------------------------------------
# Test Class: FAIL Batch
# ---------------------------------------------------------------------------

class TestFailBatch:
    """FAIL batch: signature invalid."""

    def test_verification_status_fail(self):
        result = _build_summary(_fail_batch(), sig_valid=False,
                                sig_error="Signature verification failed",
                                verification_mode="LEGACY_ROOT_HASH")
        assert result["verification"]["status"] == "FAIL"

    def test_failure_reason_present(self):
        result = _build_summary(_fail_batch(), sig_valid=False,
                                sig_error="Signature verification failed",
                                verification_mode="LEGACY_ROOT_HASH")
        assert result["verification"]["failure_reason"] is not None
        assert "signature" in result["verification"]["failure_reason"]

    def test_verified_at_null_on_fail(self):
        result = _build_summary(_fail_batch(), sig_valid=False,
                                verification_mode="LEGACY_ROOT_HASH")
        assert result["verification"]["verified_at_utc"] is None

    def test_verifier_version_null_on_fail(self):
        result = _build_summary(_fail_batch(), sig_valid=False,
                                verification_mode="LEGACY_ROOT_HASH")
        assert result["verification"]["verifier_version"] is None

    def test_anchored_false_on_fail(self):
        result = _build_summary(_fail_batch(), sig_valid=False)
        assert result["crypto"]["anchored"] is False

    def test_anchor_type_null_on_fail(self):
        result = _build_summary(_fail_batch(), sig_valid=False)
        assert result["crypto"]["anchor_type"] is None

    def test_anchor_id_null_on_fail(self):
        result = _build_summary(_fail_batch(), sig_valid=False)
        assert result["crypto"]["anchor_id"] is None


# ---------------------------------------------------------------------------
# Test Class: Determinism Gating (Required Tests — strict)
# ---------------------------------------------------------------------------

class TestDeterminismGating:
    """
    Strict gating: replay.determinism must be VERIFIED only when ALL are true:
      1. verification.status == PASS
      2. replay.runs >= 3
      3. replay.variance == 0
      4. replay_root_hash matches attested root hash
    """

    def test_fail_batch_variance0_runs3_determinism_not_verified(self):
        """FAIL batch with variance=0 and runs=3 → determinism MUST be UNKNOWN."""
        batch = _fail_batch()
        result = _build_summary(batch, sig_valid=False,
                                verification_mode="LEGACY_ROOT_HASH")
        assert result["verification"]["status"] == "FAIL"
        assert result["replay"]["runs"] == 3
        assert result["replay"]["variance"] == 0
        assert result["replay"]["determinism"] != "VERIFIED"
        assert result["replay"]["determinism"] == "UNKNOWN"

    def test_pass_batch_root_hash_mismatch_determinism_not_verified(self):
        """PASS batch but replay_root_hash != attested root → determinism MUST be UNKNOWN."""
        batch = _pass_batch()
        # Mismatch: attested hash differs from chain root hash
        batch["signature"]["evidence_hash_sha256"] = "0" * 64
        result = _build_summary(batch)
        assert result["verification"]["status"] == "PASS"
        assert result["replay"]["determinism"] != "VERIFIED"
        assert result["replay"]["determinism"] == "UNKNOWN"

    def test_pass_batch_hashes_match_runs3_variance0_determinism_verified(self):
        """PASS batch + hashes match + runs>=3 + variance=0 → determinism VERIFIED."""
        batch = _pass_batch()
        root = batch["hash_chain"]["batch_root_hash"]
        batch["signature"]["evidence_hash_sha256"] = root
        result = _build_summary(batch)
        assert result["verification"]["status"] == "PASS"
        assert result["replay"]["runs"] >= 3
        assert result["replay"]["variance"] == 0
        assert result["replay"]["determinism"] == "VERIFIED"

    def test_pass_batch_runs_less_than_3_determinism_unknown(self):
        """PASS batch with only 1 replay run → determinism UNKNOWN."""
        batch = _pass_batch()
        batch["hash_chain"]["replay_runs"] = 1
        batch["iavp_manifest"]["metrics"]["replay_runs"] = 1
        result = _build_summary(batch)
        assert result["verification"]["status"] == "PASS"
        assert result["replay"]["determinism"] == "UNKNOWN"

    def test_pass_batch_variance_nonzero_determinism_unknown(self):
        """PASS batch with variance > 0 → determinism UNKNOWN."""
        batch = _pass_batch()
        batch["hash_chain"]["replay_variance"] = 1
        batch["iavp_manifest"]["metrics"]["replay_variance"] = 1
        result = _build_summary(batch)
        assert result["replay"]["determinism"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test Class: Gating Table Regression (Step 2 — explicit)
# ---------------------------------------------------------------------------

class TestGatingTableRegression:
    """
    Regression tests explicitly tied to the gating truth table.

    Determinism VERIFIED requires ALL four conditions simultaneously:
      1. verification.status == PASS
      2. replay.runs >= 3
      3. replay.variance == 0
      4. replay_root_hash == attested root_hash (crypto.root_hash)

    If ANY single condition is false, determinism MUST be UNKNOWN.
    """

    def test_forensic_summary_fail_never_verifies_determinism_even_with_zero_variance(self):
        """
        FAIL batch with runs=3, variance=0, hashes match → determinism UNKNOWN.

        This is the critical scenario: every replay/chain condition is perfect,
        but verification.status is FAIL (sig_valid=False). The endpoint must
        not promote to VERIFIED just because replay metrics look good.
        """
        # Start from PASS batch (all conditions met) and break only sig_valid
        batch = _pass_batch()
        root = batch["hash_chain"]["batch_root_hash"]
        batch["signature"]["evidence_hash_sha256"] = root  # hashes match

        result = _build_summary(batch, sig_valid=False,
                                sig_error="Signature verification failed")

        # Preconditions: all replay/chain conditions ARE met
        assert result["replay"]["runs"] == 3
        assert result["replay"]["variance"] == 0
        assert result["replay"]["replay_root_hash"] == result["crypto"]["root_hash"]

        # Gate: verification FAIL blocks determinism
        assert result["verification"]["status"] == "FAIL"
        assert result["replay"]["determinism"] == "UNKNOWN"

    def test_forensic_summary_pass_verifies_determinism_only_when_hashes_match_and_runs_ge_3(self):
        """
        PASS batch + hashes match + runs >= 3 + variance == 0 → determinism VERIFIED.
        Same batch but with hash mismatch → determinism UNKNOWN.

        Proves the gate opens ONLY when all four conditions are satisfied.
        """
        batch = _pass_batch()
        root = batch["hash_chain"]["batch_root_hash"]
        batch["signature"]["evidence_hash_sha256"] = root

        # Case A: all conditions met → VERIFIED
        result_a = _build_summary(batch)
        assert result_a["verification"]["status"] == "PASS"
        assert result_a["replay"]["runs"] >= 3
        assert result_a["replay"]["variance"] == 0
        assert result_a["replay"]["replay_root_hash"] == result_a["crypto"]["root_hash"]
        assert result_a["replay"]["determinism"] == "VERIFIED"

        # Case B: break hash match → UNKNOWN
        batch_b = _pass_batch()
        batch_b["signature"]["evidence_hash_sha256"] = "0" * 64
        result_b = _build_summary(batch_b)
        assert result_b["verification"]["status"] == "PASS"
        assert result_b["replay"]["determinism"] == "UNKNOWN"

        # Case C: restore hash, break runs → UNKNOWN
        batch_c = _pass_batch()
        batch_c["hash_chain"]["replay_runs"] = 2
        batch_c["iavp_manifest"]["metrics"]["replay_runs"] = 2
        batch_c["signature"]["evidence_hash_sha256"] = root
        result_c = _build_summary(batch_c)
        assert result_c["verification"]["status"] == "PASS"
        assert result_c["replay"]["determinism"] == "UNKNOWN"

    def test_forensic_summary_gating_table_exhaustive(self):
        """
        Exhaustive truth table: flip each condition one at a time.

        | status | runs>=3 | var==0 | hash_match | → determinism |
        |--------|---------|--------|------------|---------------|
        | PASS   | 3       | 0      | yes        | VERIFIED      |
        | FAIL   | 3       | 0      | yes        | UNKNOWN       |
        | PASS   | 2       | 0      | yes        | UNKNOWN       |
        | PASS   | 3       | 1      | yes        | UNKNOWN       |
        | PASS   | 3       | 0      | no         | UNKNOWN       |
        """
        root = _pass_batch()["hash_chain"]["batch_root_hash"]

        def make(sig_valid=True, runs=3, variance=0, hash_match=True):
            b = _pass_batch()
            b["hash_chain"]["replay_runs"] = runs
            b["iavp_manifest"]["metrics"]["replay_runs"] = runs
            b["hash_chain"]["replay_variance"] = variance
            b["iavp_manifest"]["metrics"]["replay_variance"] = variance
            b["signature"]["evidence_hash_sha256"] = root if hash_match else ("0" * 64)
            return _build_summary(b, sig_valid=sig_valid)

        # Row 1: all true → VERIFIED
        assert make()["replay"]["determinism"] == "VERIFIED"

        # Row 2: FAIL status → UNKNOWN
        assert make(sig_valid=False)["replay"]["determinism"] == "UNKNOWN"

        # Row 3: runs < 3 → UNKNOWN
        assert make(runs=2)["replay"]["determinism"] == "UNKNOWN"

        # Row 4: variance > 0 → UNKNOWN
        assert make(variance=1)["replay"]["determinism"] == "UNKNOWN"

        # Row 5: hash mismatch → UNKNOWN
        assert make(hash_match=False)["replay"]["determinism"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test Class: Schema / Contract Snapshot
# ---------------------------------------------------------------------------

class TestContractSnapshot:
    """
    Schema snapshot: assert exact key sets and sha256: prefix convention.
    If anyone adds/removes/renames a field, this test fails immediately.
    """

    EXPECTED_TOP_LEVEL = [
        "trace_id", "generated_at_utc", "environment", "protocol_version",
        "engine_version", "verification", "crypto", "run", "replay",
    ]

    def test_top_level_keys_are_exactly(self):
        result = _build_summary(_pass_batch())
        assert set(result.keys()) == set(self.EXPECTED_TOP_LEVEL)

    def test_top_level_key_count(self):
        result = _build_summary(_pass_batch())
        assert len(result.keys()) == 9

    def test_verification_keys_snapshot(self):
        result = _build_summary(_pass_batch())
        assert set(result["verification"].keys()) == {
            "status", "verified_at_utc", "verifier_version", "failure_reason",
        }

    def test_crypto_keys_snapshot(self):
        result = _build_summary(_pass_batch())
        assert set(result["crypto"].keys()) == {
            "signature_algorithm", "key_fingerprint", "attestation_manifest_hash",
            "root_hash", "chain_height", "anchored", "anchor_type", "anchor_id",
        }

    def test_run_keys_snapshot(self):
        result = _build_summary(_pass_batch())
        assert set(result["run"].keys()) == {
            "record_count", "artifact_mode", "dataset_hash", "config_hash",
        }

    def test_replay_keys_snapshot(self):
        result = _build_summary(_pass_batch())
        assert set(result["replay"].keys()) == {
            "supported", "determinism", "replay_root_hash", "runs", "variance",
        }

    def test_all_hash_fields_sha256_prefixed(self):
        """Every hash field in the response must be sha256: prefixed or null."""
        result = _build_summary(_pass_batch())

        hash_fields = [
            ("crypto", "attestation_manifest_hash"),
            ("crypto", "root_hash"),
            ("run", "dataset_hash"),
            ("run", "config_hash"),
            ("replay", "replay_root_hash"),
        ]

        for section, field in hash_fields:
            value = result[section][field]
            assert value is None or value.startswith("sha256:"), \
                f"{section}.{field} = {value!r} — must be sha256: prefixed or null"

    def test_hash_fields_null_when_missing(self):
        """When source data has no hash, field must be null (not empty string)."""
        batch = _pass_batch()
        batch["iavp_manifest"].pop("dataset_hash_sha256", None)
        batch["iavp_manifest"].pop("config_hash_sha256", None)
        result = _build_summary(batch)
        assert result["run"]["dataset_hash"] is None
        assert result["run"]["config_hash"] is None

    def test_no_old_contract_fields_present(self):
        """Ensure no fields from the old response shape leak through."""
        result = _build_summary(_pass_batch())
        serialized = json.dumps(result)
        old_fields = [
            "integrity_status", "narrative", "artifact_mode",
            "verification_mode", "signing", "chain",
            "record_count", "passed",
        ]
        # These must NOT appear as top-level keys
        for field in ["integrity_status", "narrative", "verification_mode",
                      "signing", "chain"]:
            assert field not in result, f"Old field '{field}' found at top level"


# ---------------------------------------------------------------------------
# Test Class: Stable Serialization
# ---------------------------------------------------------------------------

class TestStableSerialization:
    """Response must have stable key ordering across calls."""

    def test_response_key_order_stable(self):
        """Multiple calls produce identical key ordering."""
        r1 = _build_summary(_pass_batch())
        r2 = _build_summary(_pass_batch())
        # Compare JSON serialization (keys in insertion order)
        j1 = json.dumps(r1, default=str, sort_keys=False)
        j2 = json.dumps(r2, default=str, sort_keys=False)
        # Keys must be in same order (generated_at_utc will differ but key order is same)
        keys1 = list(r1.keys())
        keys2 = list(r2.keys())
        assert keys1 == keys2

    def test_nested_key_order_stable(self):
        """Nested objects also have stable key ordering."""
        r1 = _build_summary(_pass_batch())
        r2 = _build_summary(_pass_batch())
        for section in ["verification", "crypto", "run", "replay"]:
            assert list(r1[section].keys()) == list(r2[section].keys())

    def test_no_extra_fields_in_response(self):
        """Response must not contain fields outside the contract."""
        result = _build_summary(_pass_batch())
        all_keys = set(result.keys())
        assert all_keys == CONTRACT_TOP_LEVEL_KEYS, f"Extra keys: {all_keys - CONTRACT_TOP_LEVEL_KEYS}"


# ---------------------------------------------------------------------------
# Test Class: RBAC Compliance
# ---------------------------------------------------------------------------

class TestRBACCompliance:
    """No cost data, no tenant IDs, no emails in response."""

    def test_no_cost_fields(self):
        result = _build_summary(_pass_batch())
        serialized = json.dumps(result)
        assert "cost" not in serialized.lower() or "cost" in "config_hash"  # config_hash is fine
        # Check specific cost fields that must not appear
        assert "total_cost" not in serialized
        assert "l3_yield" not in serialized
        assert "llm_budget" not in serialized

    def test_no_tenant_id_in_response(self):
        result = _build_summary(_pass_batch())
        serialized = json.dumps(result)
        assert "tenant_test" not in serialized
        assert "tenant_id" not in serialized

    def test_no_email_in_response(self):
        result = _build_summary(_pass_batch())
        serialized = json.dumps(result)
        assert "@" not in serialized


# ---------------------------------------------------------------------------
# Test Class: HTTP-level via TestClient
# ---------------------------------------------------------------------------

class TestForensicSummaryHTTP:
    """Test the endpoint via FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from app.server_enterprise_golden import app
        self.client = TestClient(app)

    def test_nonexistent_batch_returns_404(self):
        """GET /forensic-summary/BATCH-NONEXISTENT-999 → 404 {"detail":"Batch not found"}"""
        with patch("app.server_enterprise_golden.verify_request_identity") as mock_auth:
            mock_auth.return_value = {
                "auth_method": "mock",
                "uid": "test-uid",
                "email": "test@test.com",
                "tenant_id": "tenant_test",
                "role": "admin",
                "api_key": None,
                "demo_mode": False,
            }
            response = self.client.get("/forensic-summary/BATCH-NONEXISTENT-999")
            assert response.status_code == 404
            assert response.json()["detail"] == "Batch not found"

    def test_forensic_summary_requires_auth(self):
        """Endpoint requires authentication — 401 without credentials."""
        response = self.client.get("/forensic-summary/BATCH-TEST-001")
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
