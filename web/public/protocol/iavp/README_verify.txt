================================================================================
INTELLIGENT ANALYST VERIFICATION PROTOCOL (IAVP) v1.0
Example Verification Bundle
================================================================================

This bundle contains example attestation materials for testing the IAVP v1.0
verification procedure. These are DEMO_SIMULATED artifacts, not production data.

CONTENTS
--------
- public_key.pem              ECDSA P-256 public key (PEM format)
- attestation_manifest.jcs.json   JCS-canonical attestation manifest
- attestation_signature.der       ECDSA-SHA256 signature (DER format)
- README_verify.txt               This file

VERIFICATION PROCEDURE
----------------------

Step 1: Verify the signature

    openssl dgst -sha256 -verify public_key.pem \
      -signature attestation_signature.der \
      attestation_manifest.jcs.json

    Expected output: Verified OK

Step 2: (Optional) Verify public key fingerprint

    openssl pkey -pubin -in public_key.pem -outform DER | openssl dgst -sha256

    Compare the output hash with the "pubkey_fingerprint_sha256" field in the
    attestation manifest.

Step 3: Inspect the manifest

    cat attestation_manifest.jcs.json | python3 -m json.tool

    Verify that:
    - protocol_version is "IA-VP-1.0"
    - artifact_mode is "DEMO_SIMULATED" (this is a demo bundle)
    - hash_chain.method is "SHA256_CHAIN_V1"
    - hash_chain.ordering is "STABLE_INPUT_ORDER_V1"
    - metrics.replay_variance is 0

IMPORTANT NOTICE
----------------
This example bundle uses DEMO_SIMULATED mode and a demo keypair. Production
attestations use PRODUCTION_REAL mode and are signed with keys managed by
Google Cloud KMS with hardware security modules.

For the full IAVP v1.0 specification, see:
https://intelligentanalyst.com/protocol/iavp/v1

================================================================================
Document: IA-VP-1.0
Version: 1.0
Publication Date: 2026-02-18
(c) Intelligent Analyst, Inc. All rights reserved.
================================================================================
