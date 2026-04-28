import React from 'react';
import { Link } from 'react-router-dom';
import { FileDown, Package } from 'lucide-react';

export default function IAVPv1() {
  return (
    <div className="min-h-screen bg-white text-gray-900">
      {/* Document Header */}
      <header className="border-b border-gray-200 py-4 px-8">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Link to="/" className="text-sm text-gray-500 hover:text-gray-700">
            Intelligent Analyst, Inc.
          </Link>
          <span className="text-xs text-gray-400 font-mono">IA-VP-1.0</span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-8 py-12">
        {/* Document Control Block */}
        <div className="border border-gray-300 mb-12">
          <div className="bg-gray-50 px-6 py-4 border-b border-gray-300">
            <h1 className="text-xl font-bold text-gray-900">
              Intelligent Analyst Verification Protocol (IAVP)
            </h1>
            <p className="text-sm text-gray-600 mt-1">Public Verification Specification</p>
          </div>
          <div className="px-6 py-4">
            <table className="text-sm w-full">
              <tbody>
                <tr>
                  <td className="text-gray-500 pr-4 py-1 w-48">Document ID</td>
                  <td className="font-mono text-gray-900">IA-VP-1.0</td>
                </tr>
                <tr>
                  <td className="text-gray-500 pr-4 py-1">Version</td>
                  <td className="font-mono text-gray-900">1.0</td>
                </tr>
                <tr>
                  <td className="text-gray-500 pr-4 py-1">Publication Date</td>
                  <td className="font-mono text-gray-900">2026-02-18</td>
                </tr>
                <tr>
                  <td className="text-gray-500 pr-4 py-1">Status</td>
                  <td className="text-gray-900">Final</td>
                </tr>
                <tr>
                  <td className="text-gray-500 pr-4 py-1">Owner</td>
                  <td className="text-gray-900">Intelligent Analyst, Inc.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Downloads */}
        <div className="flex gap-4 mb-12">
          <a
            href="/protocol/iavp/IAVP_v1.0_Public_Verification_Specification.pdf"
            download
            className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-sm text-gray-700 hover:bg-gray-50"
          >
            <FileDown size={16} />
            Download PDF
          </a>
          <a
            href="/protocol/iavp/iavp_v1_example_bundle.zip"
            download
            className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-sm text-gray-700 hover:bg-gray-50"
          >
            <Package size={16} />
            Download Verification Bundle
          </a>
        </div>

        {/* Section 1: Scope */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            1. Scope
          </h2>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            This specification defines the Intelligent Analyst Verification Protocol (IAVP) version 1.0.
            IAVP provides a method for independent verification of attestation artifacts produced by
            Intelligent Analyst processing batches.
          </p>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            IAVP v1.0 defines batch-level attestation only. Record-level attestation is not within
            the scope of this version.
          </p>
          <p className="text-sm text-gray-700 leading-relaxed">
            This specification is intended for use by auditors, compliance officers, and technical
            personnel who require independent verification of processing results without access to
            the Intelligent Analyst platform.
          </p>
        </section>

        {/* Section 2: Definitions */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            2. Definitions
          </h2>
          <dl className="text-sm space-y-3">
            <div>
              <dt className="font-semibold text-gray-900">Attestation Manifest</dt>
              <dd className="text-gray-700 ml-4">
                A JSON document containing metadata, metrics, and cryptographic commitments for a processed batch.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-gray-900">Evidence Pack</dt>
              <dd className="text-gray-700 ml-4">
                An artifact bundle containing processing results and attestation materials.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-gray-900">Hash Chain</dt>
              <dd className="text-gray-700 ml-4">
                A cryptographic structure linking ordered records through iterative hashing.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-gray-900">Root Hash</dt>
              <dd className="text-gray-700 ml-4">
                The final hash value of a hash chain, serving as a commitment to the entire ordered sequence.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-gray-900">JCS</dt>
              <dd className="text-gray-700 ml-4">
                JSON Canonicalization Scheme as defined in RFC 8785.
              </dd>
            </div>
          </dl>
        </section>

        {/* Section 3: Canonical Serialization */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            3. Canonical Serialization
          </h2>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            All JSON documents subject to hashing or signing MUST be serialized according to RFC 8785
            (JSON Canonicalization Scheme). This ensures deterministic byte representation regardless
            of the original formatting.
          </p>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            JCS requirements:
          </p>
          <ul className="text-sm text-gray-700 list-disc ml-6 space-y-1 mb-4">
            <li>Object keys MUST be sorted lexicographically by UTF-16 code units</li>
            <li>No whitespace between tokens</li>
            <li>Numbers MUST use shortest representation without trailing zeros</li>
            <li>Strings MUST use minimal escape sequences</li>
          </ul>
          <p className="text-sm text-gray-700 leading-relaxed">
            Implementations MAY use any conformant RFC 8785 library. The canonical form is the
            byte sequence used for hashing and signature computation.
          </p>
        </section>

        {/* Section 4: Record Hashing */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            4. Record Hashing
          </h2>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            Each record MUST be hashed using SHA-256. The hash input is the JCS-canonical byte
            representation of the record JSON object.
          </p>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto mb-4">
{`record_bytes = JCS(record_json)
record_hash = SHA256(record_bytes)
record_hash_hex = lowercase_hex(record_hash)`}
          </pre>
          <p className="text-sm text-gray-700 leading-relaxed">
            The <code className="bg-gray-100 px-1 font-mono text-xs">record_hash</code> MUST be
            represented as a 64-character lowercase hexadecimal string.
          </p>
        </section>

        {/* Section 5: STABLE_INPUT_ORDER_V1 */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            5. STABLE_INPUT_ORDER_V1
          </h2>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            Before constructing the hash chain, records MUST be ordered according to
            STABLE_INPUT_ORDER_V1. This ensures deterministic ordering regardless of
            processing parallelism or system state.
          </p>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">5.1 Normalization</h3>
          <ol className="text-sm text-gray-700 list-decimal ml-6 space-y-2 mb-4">
            <li>
              <strong>Timestamps:</strong> Canonicalize to RFC 3339 UTC with exactly 6 fractional
              digits (e.g., <code className="bg-gray-100 px-1 font-mono text-xs">2026-02-18T23:59:59.000000Z</code>)
            </li>
            <li>
              <strong>Source System ID:</strong> Normalize to Unicode NFC form
            </li>
            <li>
              <strong>Record Hash:</strong> Lowercase hexadecimal SHA-256 (64 characters)
            </li>
          </ol>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">5.2 Sort Order</h3>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            Records SHALL be sorted ascending by the following keys, in order of precedence:
          </p>
          <ol className="text-sm text-gray-700 list-decimal ml-6 space-y-2">
            <li>
              <code className="bg-gray-100 px-1 font-mono text-xs">source_timestamp</code> (RFC 3339 string comparison)
            </li>
            <li>
              <code className="bg-gray-100 px-1 font-mono text-xs">source_system_id</code> (UTF-8 byte lexicographic order; no locale collation)
            </li>
            <li>
              <code className="bg-gray-100 px-1 font-mono text-xs">record_hash</code> (lowercase hex lexicographic order)
            </li>
          </ol>
        </section>

        {/* Section 6: Hash Chain Construction */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            6. Hash Chain Construction (SHA256_CHAIN_V1)
          </h2>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            The hash chain provides tamper-evident linking of all records in a batch.
          </p>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">6.1 Algorithm</h3>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto mb-4">
{`# Genesis hash: 32 bytes of zero
H[0] = 0x00 (repeated 32 times)
     = "0000000000000000000000000000000000000000000000000000000000000000"

# Chain construction
for i = 1 to N:
    H[i] = SHA256( bytes(H[i-1]) || bytes(record_hash[i]) )

# Root hash
root_hash = H[N]`}
          </pre>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            Where:
          </p>
          <ul className="text-sm text-gray-700 list-disc ml-6 space-y-1">
            <li>
              <code className="bg-gray-100 px-1 font-mono text-xs">bytes(x)</code> converts a 64-character
              hex string to its 32-byte binary representation
            </li>
            <li>
              <code className="bg-gray-100 px-1 font-mono text-xs">||</code> denotes byte concatenation
            </li>
            <li>
              <code className="bg-gray-100 px-1 font-mono text-xs">N</code> is the total number of records
            </li>
          </ul>
        </section>

        {/* Section 7: Attestation Manifest Schema */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            7. Attestation Manifest Schema
          </h2>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            The Attestation Manifest is a JSON document containing all metadata required for
            independent verification. The following fields are REQUIRED:
          </p>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto mb-4">
{`{
  "protocol_version": "IA-VP-1.0",
  "artifact_type": "EVIDENCE_PACK",
  "artifact_version": "1.0",
  "artifact_mode": "PRODUCTION_REAL",
  "generated_at_utc": "2026-02-18T12:00:00.000000Z",
  "engine_version": "3.0.0",
  "config_hash_sha256": "a1b2c3d4...",
  "batch_id": "BATCH-12345678",
  "dataset_hash_sha256": "e5f6a7b8...",
  "hash_chain": {
    "method": "SHA256_CHAIN_V1",
    "root_hash_sha256": "c9d0e1f2...",
    "record_count": 1000,
    "ordering": "STABLE_INPUT_ORDER_V1"
  },
  "metrics": {
    "l1_pct": 65.0,
    "l2_pct": 20.0,
    "l3_pct": 10.0,
    "l4_pct": 5.0,
    "replay_variance": 0
  },
  "key": {
    "key_id": "projects/.../cryptoKeyVersions/1",
    "pubkey_fingerprint_sha256": "f3a4b5c6..."
  }
}`}
          </pre>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">7.1 Field Definitions</h3>
          <table className="text-sm w-full border border-gray-200 mb-4">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-3 py-2 border-b border-gray-200">Field</th>
                <th className="text-left px-3 py-2 border-b border-gray-200">Type</th>
                <th className="text-left px-3 py-2 border-b border-gray-200">Description</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">protocol_version</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">MUST be "IA-VP-1.0"</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">artifact_type</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">"EVIDENCE_PACK" or "STRESS_TEST_CERT"</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">artifact_mode</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">"DEMO_SIMULATED" or "PRODUCTION_REAL"</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">generated_at_utc</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">RFC 3339 UTC timestamp</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">config_hash_sha256</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">64-char hex hash of engine config</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">dataset_hash_sha256</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">64-char hex hash of input dataset</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">hash_chain.method</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">MUST be "SHA256_CHAIN_V1"</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="px-3 py-2">hash_chain.ordering</td>
                <td className="px-3 py-2">string</td>
                <td className="px-3 py-2 font-sans">MUST be "STABLE_INPUT_ORDER_V1"</td>
              </tr>
              <tr>
                <td className="px-3 py-2">metrics.replay_variance</td>
                <td className="px-3 py-2">number</td>
                <td className="px-3 py-2 font-sans">MUST be 0 for deterministic processing</td>
              </tr>
            </tbody>
          </table>
        </section>

        {/* Section 8: Signature Specification */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            8. Signature Specification
          </h2>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">8.1 Algorithm</h3>
          <ul className="text-sm text-gray-700 list-disc ml-6 space-y-1 mb-4">
            <li><strong>Curve:</strong> ECDSA P-256 (prime256v1 / secp256r1)</li>
            <li><strong>Hash:</strong> SHA-256</li>
            <li><strong>Encoding:</strong> DER (Distinguished Encoding Rules)</li>
          </ul>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">8.2 Signature Procedure</h3>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto mb-4">
{`# Step 1: Canonicalize the manifest
manifest_bytes = JCS(manifest_json)

# Step 2: Compute manifest hash
manifest_hash = SHA256(manifest_bytes)

# Step 3: Sign with ECDSA P-256
signature_der = ECDSA_P256_SIGN(private_key, manifest_hash)`}
          </pre>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">8.3 Public Key Fingerprint</h3>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto">
{`# Compute fingerprint from SubjectPublicKeyInfo DER
pubkey_der = SubjectPublicKeyInfo(public_key)
pubkey_fingerprint_sha256 = SHA256(pubkey_der)`}
          </pre>
        </section>

        {/* Section 9: Public Verification Procedure */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            9. Public Verification Procedure
          </h2>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            The following procedure allows independent verification using standard OpenSSL tools.
          </p>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">9.1 Required Files</h3>
          <ul className="text-sm text-gray-700 list-disc ml-6 space-y-1 mb-4">
            <li><code className="bg-gray-100 px-1 font-mono text-xs">public_key.pem</code> - PEM-encoded public key</li>
            <li><code className="bg-gray-100 px-1 font-mono text-xs">attestation_manifest.jcs.json</code> - JCS-canonical manifest</li>
            <li><code className="bg-gray-100 px-1 font-mono text-xs">attestation_signature.der</code> - DER-encoded signature</li>
          </ul>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">9.2 Verification Command</h3>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto mb-4">
{`openssl dgst -sha256 -verify public_key.pem \\
  -signature attestation_signature.der \\
  attestation_manifest.jcs.json`}
          </pre>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            Expected output on success:
          </p>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto mb-4">
{`Verified OK`}
          </pre>
          <h3 className="text-sm font-bold text-gray-900 mt-6 mb-3">9.3 Optional: Fingerprint Verification</h3>
          <p className="text-sm text-gray-700 leading-relaxed mb-4">
            To verify the public key fingerprint matches the manifest:
          </p>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto">
{`openssl pkey -pubin -in public_key.pem -outform DER | openssl dgst -sha256`}
          </pre>
        </section>

        {/* Section 10: Versioning Policy */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            10. Versioning Policy
          </h2>
          <ul className="text-sm text-gray-700 list-disc ml-6 space-y-2">
            <li>
              <strong>v1.0</strong> is immutable. No silent edits SHALL be made to this specification.
            </li>
            <li>
              <strong>Clarifications</strong> that do not change behavior MAY be issued as v1.0.x
              (e.g., v1.0.1). These are non-breaking.
            </li>
            <li>
              <strong>Breaking changes</strong> require a new major version (e.g., v2.0).
            </li>
            <li>
              All historical versions SHALL remain accessible at their original URLs.
            </li>
          </ul>
        </section>

        {/* Footer */}
        <footer className="mt-16 pt-8 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            Last updated: 2026-02-18
          </p>
          <p className="text-xs text-gray-500 mt-2">
            &copy; {new Date().getFullYear()} Intelligent Analyst, Inc. All rights reserved.
          </p>
        </footer>
      </main>
    </div>
  );
}
