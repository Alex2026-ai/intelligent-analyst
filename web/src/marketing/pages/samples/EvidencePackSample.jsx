import React from 'react';
import { Link } from 'react-router-dom';
import { FileDown, Package } from 'lucide-react';

export default function EvidencePackSample() {
  // Sample manifest data (sanitized, DEMO_SIMULATED mode)
  const manifest = {
    document_id: "IA-FRD-1.0",
    version: "1.0",
    publication_date_utc: "2026-02-19T00:00:00.000000Z",
    protocol_reference: "/protocol/iavp/v1",
    engine_version: "3.0.0",
    config_hash_sha256: "f636bc02c0eb2a7b3f34e4837a42507f70e400ec6e5bc0fc0b1c1f5a270feef0",
    batch_id: "[REDACTED]",
    record_count: 100,
    artifact_mode: "DEMO_SIMULATED",
    attested_scope: "FULL_BATCH_MANIFEST",
    total_records: 100,
    l1_pct: 65.0,
    l2_pct: 20.0,
    l3_pct: 10.0,
    l4_pct: 5.0,
    replay_runs: 3,
    replay_variance: 0,
    replay_method: "FULL_BATCH_REPROCESS_UNDER_IDENTICAL_CONFIG",
    hash_chain_method: "SHA256_CHAIN_V1",
    hash_chain_ordering: "STABLE_INPUT_ORDER_V1",
    root_hash_sha256: "7d132152fdbfad91f48491f0b20808ff27158c26ef5a12cd00db8a65ee34ef44",
    signature_algorithm: "ECDSA P-256",
    signature_encoding: "DER",
    signature_timestamp_utc: "2026-02-19T00:00:00.000000Z",
    pubkey_fingerprint_sha256: "8bf795f66fc7542681e2e94c710cfbb64ce1f614b1719f5da17bd024d1e7e464",
    signature_base64: "MEUCIQCx3tE9j...[truncated]"
  };

  return (
    <div className="min-h-screen bg-white text-gray-900 print:bg-white">
      {/* Document Header */}
      <header className="border-b border-gray-200 py-4 px-8 print:border-gray-400">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Link to="/" className="text-sm text-gray-500 hover:text-gray-700 print:text-gray-700">
            Intelligent Analyst, Inc.
          </Link>
          <span className="text-xs text-gray-400 font-mono">IA-FRD-1.0</span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-8 py-12">
        {/* Document Title Block */}
        <div className="border border-gray-300 mb-8">
          <div className="bg-gray-50 px-6 py-4 border-b border-gray-300">
            <h1 className="text-xl font-bold text-gray-900">
              Forensic Resolution Dossier
            </h1>
            <p className="text-sm text-gray-600 mt-1">Evidence Pack v1.0 — Sample</p>
          </div>
        </div>

        {/* Disclosures */}
        <div className="border border-gray-300 bg-gray-50 px-6 py-4 mb-8 text-xs text-gray-700 space-y-2">
          <p>1. This artifact demonstrates structural compliance with IAVP v1.0. Redacted fields do not affect verification semantics.</p>
          <p>2. This public sample is labeled DEMO_SIMULATED and does not represent production-retained WORM data.</p>
          <p>3. Demonstration keys are segregated from production keys.</p>
        </div>

        {/* Downloads */}
        <div className="flex gap-4 mb-10 print:hidden">
          <a
            href="/samples/evidence-pack/Evidence_Pack_v1.0_Sample_Dossier.pdf"
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

        {/* Section 1: Document Control */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            1. Document Control
          </h2>
          <table className="text-sm w-full">
            <tbody>
              <tr>
                <td className="text-gray-500 pr-4 py-1 w-56">Document ID</td>
                <td className="font-mono text-gray-900">{manifest.document_id}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">Version</td>
                <td className="font-mono text-gray-900">{manifest.version}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">Publication Date (UTC)</td>
                <td className="font-mono text-gray-900">{manifest.publication_date_utc}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">Protocol Reference</td>
                <td className="font-mono text-gray-900">
                  <Link to={manifest.protocol_reference} className="text-blue-600 hover:underline print:text-gray-900">
                    IAVP v1.0
                  </Link>
                </td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">Engine Version</td>
                <td className="font-mono text-gray-900">{manifest.engine_version}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">config_hash_sha256</td>
                <td className="font-mono text-gray-900 text-xs break-all">{manifest.config_hash_sha256}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">batch_id</td>
                <td className="font-mono text-gray-900">{manifest.batch_id}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">record_count</td>
                <td className="font-mono text-gray-900">{manifest.record_count}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">artifact_mode</td>
                <td className="font-mono text-gray-900">{manifest.artifact_mode}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">attested_scope</td>
                <td className="font-mono text-gray-900">{manifest.attested_scope}</td>
              </tr>
            </tbody>
          </table>
        </section>

        {/* Section 2: Batch Attestation Summary */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            2. Batch Attestation Summary
          </h2>
          <table className="text-sm w-full">
            <tbody>
              <tr>
                <td className="text-gray-500 pr-4 py-1 w-56">total_records</td>
                <td className="font-mono text-gray-900">{manifest.total_records}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">l1_pct</td>
                <td className="font-mono text-gray-900">{manifest.l1_pct}%</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">l2_pct</td>
                <td className="font-mono text-gray-900">{manifest.l2_pct}%</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">l3_pct</td>
                <td className="font-mono text-gray-900">{manifest.l3_pct}%</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">l4_pct</td>
                <td className="font-mono text-gray-900">{manifest.l4_pct}%</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">replay_runs</td>
                <td className="font-mono text-gray-900">{manifest.replay_runs}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">replay_variance</td>
                <td className="font-mono text-gray-900">{manifest.replay_variance}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">replay_method</td>
                <td className="font-mono text-gray-900 text-xs">{manifest.replay_method}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">hash_chain.method</td>
                <td className="font-mono text-gray-900">{manifest.hash_chain_method}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">hash_chain.ordering</td>
                <td className="font-mono text-gray-900">{manifest.hash_chain_ordering}</td>
              </tr>
            </tbody>
          </table>
        </section>

        {/* Section 3: Hash Chain Root */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            3. Hash Chain Root
          </h2>
          <table className="text-sm w-full mb-4">
            <tbody>
              <tr>
                <td className="text-gray-500 pr-4 py-1 w-56">root_hash_sha256</td>
                <td className="font-mono text-gray-900 text-xs break-all">{manifest.root_hash_sha256}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">record_count</td>
                <td className="font-mono text-gray-900">{manifest.record_count}</td>
              </tr>
            </tbody>
          </table>
          <p className="text-sm text-gray-700 mb-2">
            <strong>Genesis:</strong> H[0] = 32 zero bytes (64 hex zeros).
          </p>
          <p className="text-sm text-gray-700">
            The root hash is computed by iteratively hashing each record in STABLE_INPUT_ORDER_V1 sequence.
            Each step concatenates the previous hash with the current record hash before applying SHA-256.
          </p>
        </section>

        {/* Section 4: Signature Block */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            4. Signature Block
          </h2>
          <table className="text-sm w-full mb-6">
            <tbody>
              <tr>
                <td className="text-gray-500 pr-4 py-1 w-56">Signature Algorithm</td>
                <td className="font-mono text-gray-900">{manifest.signature_algorithm}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">Signature Encoding</td>
                <td className="font-mono text-gray-900">{manifest.signature_encoding}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">Signature Timestamp (UTC)</td>
                <td className="font-mono text-gray-900">{manifest.signature_timestamp_utc}</td>
              </tr>
              <tr>
                <td className="text-gray-500 pr-4 py-1">pubkey_fingerprint_sha256</td>
                <td className="font-mono text-gray-900 text-xs break-all">{manifest.pubkey_fingerprint_sha256}</td>
              </tr>
            </tbody>
          </table>

          <h3 className="text-sm font-bold text-gray-900 mb-2">Verification Command</h3>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto mb-4">
{`openssl dgst -sha256 -verify public_key.pem \\
  -signature attestation_signature.der \\
  attestation_manifest.jcs.json`}
          </pre>

          <h3 className="text-sm font-bold text-gray-900 mb-2">Fingerprint Verification (Optional)</h3>
          <pre className="bg-gray-100 border border-gray-200 p-4 text-xs font-mono overflow-x-auto">
{`openssl pkey -pubin -in public_key.pem -outform DER | openssl dgst -sha256`}
          </pre>
        </section>

        {/* Section 5: Replay Confirmation */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            5. Replay Confirmation
          </h2>
          <p className="text-sm text-gray-700">
            Reprocessing under identical configuration produced identical outcomes.
            Replay variance: <span className="font-mono font-bold">0</span>.
          </p>
        </section>

        {/* Section 6: Verification Instructions */}
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
            6. Verification Instructions
          </h2>
          <ol className="text-sm text-gray-700 list-decimal ml-6 space-y-2">
            <li>
              Download the verification bundle:{" "}
              <a href="/protocol/iavp/iavp_v1_example_bundle.zip" className="text-blue-600 hover:underline print:text-gray-900 font-mono text-xs">
                iavp_v1_example_bundle.zip
              </a>
            </li>
            <li>Extract the bundle to a local directory.</li>
            <li>
              Run the verification command:
              <pre className="bg-gray-100 border border-gray-200 p-3 text-xs font-mono overflow-x-auto mt-2">
{`openssl dgst -sha256 -verify public_key.pem \\
  -signature attestation_signature.der \\
  attestation_manifest.jcs.json`}
              </pre>
            </li>
            <li>
              Expected output: <code className="bg-gray-100 px-1 font-mono text-xs">Verified OK</code>
            </li>
          </ol>
        </section>

        {/* Footer */}
        <footer className="mt-16 pt-8 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            Document ID: {manifest.document_id} | Version: {manifest.version}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Generated: {manifest.publication_date_utc}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            &copy; {new Date().getFullYear()} Intelligent Analyst, Inc.
          </p>
        </footer>
      </main>
    </div>
  );
}
