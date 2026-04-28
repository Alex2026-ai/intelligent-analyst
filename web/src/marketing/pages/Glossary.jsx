import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';

const glossaryTerms = [
  {
    term: 'Deterministic Replay',
    definition: 'The process of reprocessing a batch under identical configuration to verify that outcomes remain unchanged. A system exhibits deterministic replay when repeated executions produce bit-identical results.',
    reference: 'IAVP v1.0',
    relatedFields: ['replay_runs', 'replay_variance', 'replay_method'],
  },
  {
    term: 'Replay Variance',
    definition: 'The count of records whose resolution outcome differs between replay runs. A compliant batch must achieve replay_variance = 0.',
    reference: 'IAVP v1.0',
    relatedFields: ['replay_variance'],
  },
  {
    term: 'STABLE_INPUT_ORDER_V1',
    definition: 'The canonical ordering algorithm for records before hash chain construction. Records are sorted by: (1) source_timestamp (lexicographic), (2) source_system_id (UTF-8 bytes), (3) record_hash (lowercase hex). This ensures deterministic ordering regardless of input sequence.',
    reference: 'IAVP v1.0',
    relatedFields: ['hash_chain.ordering'],
  },
  {
    term: 'SHA256_CHAIN_V1',
    definition: 'The hash chain construction method where each link is computed as H[i] = SHA256(bytes(H[i-1]) || bytes(record_hash[i])). Genesis value H[0] is 32 zero bytes.',
    reference: 'IAVP v1.0',
    relatedFields: ['hash_chain.method'],
  },
  {
    term: 'Attested Scope',
    definition: 'The boundary of what the cryptographic attestation covers. Defines whether the signature applies to a full batch manifest, partial records, or specific fields.',
    reference: 'IAVP v1.0',
    relatedFields: ['attested_scope'],
  },
  {
    term: 'FULL_BATCH_MANIFEST',
    definition: 'An attested_scope value indicating that the cryptographic attestation covers the complete batch manifest including all records, configuration hash, and replay verification results.',
    reference: 'IAVP v1.0',
    relatedFields: ['attested_scope'],
  },
  {
    term: 'Artifact Mode',
    definition: 'Classification of an attestation artifact indicating whether it was produced in a production or demonstration environment. Determines whether the artifact is suitable for regulatory submission.',
    reference: 'IAVP v1.0',
    relatedFields: ['artifact_mode'],
  },
  {
    term: 'PRODUCTION_REAL',
    definition: 'An artifact_mode value indicating the attestation was produced in a production environment with production keys, WORM retention, and full forensic controls enabled.',
    reference: 'IAVP v1.0',
    relatedFields: ['artifact_mode'],
  },
  {
    term: 'DEMO_SIMULATED',
    definition: 'An artifact_mode value indicating the attestation was produced in a demonstration or test environment. Such artifacts are not suitable for regulatory submission and use segregated keys.',
    reference: 'IAVP v1.0',
    relatedFields: ['artifact_mode'],
  },
  {
    term: 'Cryptographic Attestation',
    definition: 'A digitally signed statement binding a hash chain root to a specific batch, configuration, and timestamp. Provides non-repudiation and tamper evidence for the attested scope.',
    reference: 'IAVP v1.0',
    relatedFields: ['signature_base64', 'signature_timestamp_utc'],
  },
  {
    term: 'ECDSA P-256',
    definition: 'The elliptic curve digital signature algorithm using the NIST P-256 curve (secp256r1). Required signature algorithm for IAVP v1.0 attestations.',
    reference: 'IAVP v1.0, FIPS 186-4',
    relatedFields: ['signature_algorithm'],
  },
  {
    term: 'DER Encoding',
    definition: 'Distinguished Encoding Rules. A binary encoding format for the ECDSA signature. The signature bytes are DER-encoded before base64 representation in the manifest.',
    reference: 'IAVP v1.0, ITU-T X.690',
    relatedFields: ['signature_encoding'],
  },
  {
    term: 'Hash Chain',
    definition: 'An ordered sequence of cryptographic hashes where each element depends on the previous element. Provides tamper-evident linking of all records in a batch. Modification of any record changes all subsequent hashes.',
    reference: 'IAVP v1.0',
    relatedFields: ['hash_chain.method', 'hash_chain.ordering'],
  },
  {
    term: 'Root Hash',
    definition: 'The final hash value of a completed hash chain. Serves as a cryptographic commitment to the entire ordered sequence of records. Published in the attestation manifest as root_hash_sha256.',
    reference: 'IAVP v1.0',
    relatedFields: ['root_hash_sha256'],
  },
  {
    term: 'RFC 8785 (JCS)',
    definition: 'JSON Canonicalization Scheme. Defines deterministic serialization of JSON objects for cryptographic operations. Ensures identical byte sequences regardless of original formatting or key ordering.',
    reference: 'RFC 8785',
    relatedFields: ['manifest serialization'],
  },
  {
    term: 'Canonicalization',
    definition: 'The process of converting data to a standard, deterministic form before cryptographic operations. Ensures that semantically equivalent inputs produce identical byte sequences for hashing or signing.',
    reference: 'IAVP v1.0, RFC 8785',
  },
  {
    term: 'Configuration Hash',
    definition: 'A SHA-256 hash of the resolution engine configuration at processing time. Enables verification that replay was performed under identical settings. Stored as config_hash_sha256.',
    reference: 'IAVP v1.0',
    relatedFields: ['config_hash_sha256'],
  },
  {
    term: 'WORM Retention',
    definition: 'Write Once Read Many. A storage policy where data cannot be modified or deleted after writing. Required for regulatory compliance in financial services. Attestation artifacts are committed to WORM storage with defined retention periods.',
    reference: 'IAVP v1.0',
  },
  {
    term: 'Fail-Closed Behavior',
    definition: 'A system design principle where failures result in denial of service rather than degraded security. If integrity verification fails, the system rejects the batch rather than proceeding with unverified data.',
    reference: 'IAVP v1.0',
  },
  {
    term: 'Key Separation Enforcement',
    definition: 'A control requiring distinct cryptographic keys for production and non-production environments. Production systems must reject demonstration keys at startup. Prevents accidental use of test credentials in regulated environments.',
    reference: 'IAVP v1.0',
  },
];

export default function Glossary() {
  useEffect(() => {
    document.title = 'Glossary of Institutional Data Integrity Terms | Intelligent Analyst';

    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      metaDesc.setAttribute('content', 'Definitions of deterministic replay, cryptographic attestation, hash chaining, and related governance terminology aligned to IAVP v1.0.');
    }
  }, []);

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-gray-200 py-4 px-8">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Link to="/" className="text-sm text-gray-500 hover:text-gray-700">
            Intelligent Analyst, Inc.
          </Link>
          <span className="text-xs text-gray-400 font-mono">Glossary</span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-8 py-12">
        {/* Title Block */}
        <div className="border border-gray-300 mb-10">
          <div className="bg-gray-50 px-6 py-4 border-b border-gray-300">
            <h1 className="text-xl font-bold text-gray-900">
              Glossary of Institutional Data Integrity Terms
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Version 1.0 — Aligned to{' '}
              <Link to="/protocol/iavp/v1" className="text-blue-600 hover:underline">
                IAVP v1.0
              </Link>
            </p>
          </div>
        </div>

        {/* Terms */}
        <div className="space-y-10">
          {glossaryTerms.map((item, idx) => (
            <section key={idx} id={item.term.toLowerCase().replace(/[\s()]/g, '-')} className="border-b border-gray-100 pb-8">
              <h2 className="text-lg font-bold text-gray-900 mb-3">
                {item.term}
              </h2>
              <p className="text-sm text-gray-700 leading-relaxed mb-4">
                {item.definition}
              </p>
              <div className="text-xs text-gray-500 space-y-1">
                {item.reference && (
                  <p>
                    <span className="font-semibold">Reference:</span>{' '}
                    {item.reference.includes('IAVP') ? (
                      <Link to="/protocol/iavp/v1" className="text-blue-600 hover:underline">
                        {item.reference}
                      </Link>
                    ) : (
                      item.reference
                    )}
                  </p>
                )}
                {item.relatedFields && item.relatedFields.length > 0 && (
                  <p>
                    <span className="font-semibold">Related Fields:</span>{' '}
                    <span className="font-mono">{item.relatedFields.join(', ')}</span>
                  </p>
                )}
              </div>
            </section>
          ))}
        </div>

        {/* Footer Note */}
        <div className="mt-12 pt-8 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            This glossary defines terminology as used within the Intelligent Analyst Verification Protocol (IAVP) v1.0 specification.
            Terms are not intended as general industry definitions and may differ from usage in other contexts.
          </p>
        </div>
      </main>

      {/* Page Footer */}
      <footer className="border-t border-gray-200 py-6 px-8 mt-16">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs text-gray-400">
            &copy; {new Date().getFullYear()} Intelligent Analyst, Inc.
          </p>
        </div>
      </footer>
    </div>
  );
}
