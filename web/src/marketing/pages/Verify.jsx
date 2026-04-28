import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section from '../components/Section';
import CTABox from '../components/CTABox';
import CookieConsent from '../components/CookieConsent';
import { FadeIn } from '../components/AnimatedSection';

export default function Verify() {
  useEffect(() => {
    document.title = 'Verification Walkthrough | Intelligent Analyst';
  }, []);

  const steps = [
    {
      step: '01',
      title: 'Retrieve the Batch Attestation',
      description: 'Every completed batch produces an IAVP manifest stored alongside the results. The manifest contains the protocol version, hash chain root, replay metrics, and signing key reference.',
      code: `GET /batches/{batch_id}/verify
Authorization: Bearer <token>

Response:
{
  "status": "PASS",
  "hash_chain": {
    "chain_length": 4979,
    "batch_root_hash": "a3f8c1...",
    "verified": true
  },
  "signature": {
    "verified": true,
    "key_id": "projects/.../cryptoKeys/golden-signing-prod"
  },
  "replay": {
    "runs": 3,
    "variance": 0
  }
}`,
    },
    {
      step: '02',
      title: 'Verify the Hash Chain',
      description: 'The hash chain links every record in the batch. Each record is canonicalized using JCS (RFC 8785), then hashed with SHA-256. Each hash incorporates the previous hash, creating a tamper-evident sequence.',
      code: `# For each record in STABLE_INPUT_ORDER_V1:
record_json = jcs_canonicalize(record)
record_hash = sha256(record_json)
chain_hash  = sha256(previous_chain_hash + record_hash)

# Final chain_hash must equal batch_root_hash
assert chain_hash == manifest.batch_root_hash`,
    },
    {
      step: '03',
      title: 'Verify the Signature',
      description: 'The batch root hash is signed with an ECDSA P-256 key managed by Google Cloud KMS. The public key fingerprint is included in the manifest. Verify the signature against the published public key.',
      code: `# Signature covers:
signed_payload = sha256(
  batch_root_hash +
  config_hash +
  dataset_hash +
  protocol_version
)

# Verify with KMS public key
ecdsa_verify(
  public_key=manifest.key.pubkey_fingerprint_sha256,
  signature=manifest.signature,
  payload=signed_payload
)`,
    },
    {
      step: '04',
      title: 'Verify Record Ordering',
      description: 'STABLE_INPUT_ORDER_V1 guarantees deterministic sequencing. Records are sorted by (source_timestamp, source_system_id, record_hash) using lexicographic comparison. Timestamps are canonicalized to RFC 3339 UTC with 6 fractional digits.',
      code: `# Canonical timestamp format:
# YYYY-MM-DDTHH:MM:SS.ffffffZ

# Sort key per record:
sort_key = (
  source_timestamp,        # RFC3339 UTC, 6 fractional digits
  source_system_id_bytes,  # Unicode NFC, UTF-8 encoded
  record_hash              # lowercase hex SHA-256
)

# Lexicographic sort, then chain`,
    },
    {
      step: '05',
      title: 'Check the External Anchor',
      description: 'The batch root hash is independently stored in a write-only GCS bucket. This anchor cannot be modified by the system that produced the attestation. Compare the stored anchor hash against your computed chain root.',
      code: `# Anchor record location:
gs://ia-anchor-{env}/{batch_id}/anchor.json

# Contains:
{
  "batch_id": "BATCH-...",
  "batch_root_hash": "a3f8c1...",
  "anchored_at": "2026-02-21T...",
  "signing_key_id": "projects/..."
}`,
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* Trust Center Navigation */}
      <div className="pt-24 bg-slate-950 border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-6 text-sm">
            <Link to="/protocol" className="py-3 border-b-2 border-transparent text-slate-500 hover:text-slate-300 transition-colors">Protocol</Link>
            <span className="py-3 border-b-2 border-cyan-500 text-cyan-400 font-medium">Verify</span>
            <Link to="/compliance" className="py-3 border-b-2 border-transparent text-slate-500 hover:text-slate-300 transition-colors">Compliance</Link>
          </div>
        </div>
      </div>

      {/* Hero */}
      <section className="pt-20 pb-16">
        <div className="max-w-4xl mx-auto px-6">
          <FadeIn direction="up">
            <div className="forensic-badge mb-6">Trust Center</div>
            <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
              Verification
              <br />
              <span className="text-cyan-400">Walkthrough</span>
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed max-w-3xl">
              How to independently verify an IAVP attestation. Every step is reproducible
              with standard cryptographic tools.
            </p>
          </FadeIn>
        </div>
      </section>

      {/* Steps */}
      {steps.map((step, index) => (
        <Section key={step.step} dark={index % 2 === 0}>
          <div className="max-w-4xl mx-auto">
            <FadeIn direction="up">
              <div className="flex items-start gap-6">
                <div className="flex-shrink-0 w-12 h-12 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center">
                  <span className="text-cyan-400 font-mono font-bold text-sm">{step.step}</span>
                </div>
                <div className="flex-1">
                  <h2 className="text-2xl font-bold text-white mb-4">{step.title}</h2>
                  <p className="text-slate-400 leading-relaxed mb-6">{step.description}</p>
                  <div className="action-block bg-slate-950 border border-slate-800 p-4 overflow-x-auto">
                    <pre className="font-mono text-xs text-slate-400 whitespace-pre">{step.code}</pre>
                  </div>
                </div>
              </div>
            </FadeIn>
          </div>
        </Section>
      ))}

      {/* Summary */}
      <Section>
        <div className="max-w-4xl mx-auto">
          <FadeIn>
            <h2 className="text-2xl font-bold text-white mb-6">Verification Summary</h2>
            <div className="space-y-4 text-slate-400 leading-relaxed">
              <p>
                A fully verified IAVP attestation confirms:
              </p>
              <div className="space-y-2 font-mono text-sm text-slate-300 pl-4 border-l-2 border-slate-700">
                <p>Hash chain intact — no record modified after processing.</p>
                <p>Signature valid — batch was signed by the claimed KMS key.</p>
                <p>Replay variance zero — three independent runs produced identical results.</p>
                <p>Anchor matches — external record confirms the root hash independently.</p>
              </div>
              <p>
                If any check fails, the attestation is invalid. There is no partial pass.
              </p>
            </div>
            <div className="mt-8 flex flex-col sm:flex-row gap-4">
              <Link
                to="/protocol"
                className="group inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400 transition-colors"
              >
                Back to protocol overview
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link
                to="/compliance"
                className="group inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400 transition-colors"
              >
                Compliance & governance
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* CTA */}
      <Section dark>
        <FadeIn>
          <CTABox
            title="Verify it with your own data"
            description="Process your records through IAVP and inspect the attestation yourself."
            primaryText="Request a Governance Audit"
            primaryHref="/request-demo"
          />
        </FadeIn>
      </Section>

      <Footer />
      <CookieConsent />
    </div>
  );
}
