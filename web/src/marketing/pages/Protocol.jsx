import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Hash, Repeat, Shield, FileCheck, Lock, ExternalLink } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';
import CookieConsent from '../components/CookieConsent';
import { FadeIn } from '../components/AnimatedSection';

export default function Protocol() {
  useEffect(() => {
    document.title = 'IAVP v1.0 — The Verification Protocol | Intelligent Analyst';
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* Trust Center Navigation */}
      <div className="pt-24 bg-slate-950 border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-6 text-sm">
            <span className="py-3 border-b-2 border-cyan-500 text-cyan-400 font-medium">Protocol</span>
            <Link to="/verify" className="py-3 border-b-2 border-transparent text-slate-500 hover:text-slate-300 transition-colors">Verify</Link>
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
              IAVP v1.0
              <br />
              <span className="text-cyan-400">The Verification Protocol</span>
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed max-w-3xl">
              The Intelligent Analyst Verification Protocol is a deterministic attestation
              standard that proves AI decisions are reproducible, signed, and tamper-evident.
            </p>
          </FadeIn>
        </div>
      </section>

      {/* What IAVP Is */}
      <Section>
        <div className="max-w-4xl mx-auto">
          <FadeIn>
            <h2 className="text-2xl font-bold text-white mb-6">What IAVP Controls</h2>
            <div className="space-y-4 text-slate-400 leading-relaxed">
              <p>
                IAVP is not a feature. It is a protocol — a set of cryptographic and
                procedural controls that any resolution batch must satisfy before
                attestation is issued.
              </p>
              <p>
                Every IAVP-attested batch has been processed three independent times
                with zero variance, cryptographically signed with a KMS-managed key,
                hash-chained for tamper detection, and anchored to immutable external storage.
              </p>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* Core Mechanisms */}
      <Section dark>
        <SectionHeader
          eyebrow="Mechanisms"
          title="How IAVP works"
        />
        <div className="grid md:grid-cols-2 gap-8">
          <FadeIn direction="up">
            <div className="action-block bg-slate-900/80 p-8">
              <div className="flex items-center gap-3 mb-4">
                <Repeat size={22} className="text-cyan-500" />
                <h3 className="text-lg font-semibold text-white">Deterministic Replay</h3>
              </div>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                Every batch is processed three independent times. Records are sorted
                using STABLE_INPUT_ORDER_V1 — a canonical ordering by timestamp,
                source system ID, and record hash — ensuring identical sequencing
                across runs.
              </p>
              <div className="font-mono text-xs text-slate-500 bg-slate-950 p-3 border border-slate-800">
                replay_runs: 3<br />
                replay_variance: 0<br />
                ordering: STABLE_INPUT_ORDER_V1
              </div>
            </div>
          </FadeIn>

          <FadeIn direction="up" delay={100}>
            <div className="action-block bg-slate-900/80 p-8">
              <div className="flex items-center gap-3 mb-4">
                <Shield size={22} className="text-cyan-500" />
                <h3 className="text-lg font-semibold text-white">Attestation Binding</h3>
              </div>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                Each batch is signed with an ECDSA P-256 key managed by Google Cloud KMS.
                The signature covers the batch root hash, config snapshot, and IAVP manifest.
                Key separation enforced: test keys cannot sign production batches.
              </p>
              <div className="font-mono text-xs text-slate-500 bg-slate-950 p-3 border border-slate-800">
                algorithm: ECDSA P-256<br />
                key_management: Google Cloud KMS<br />
                key_separation: enforced
              </div>
            </div>
          </FadeIn>

          <FadeIn direction="up" delay={200}>
            <div className="action-block bg-slate-900/80 p-8">
              <div className="flex items-center gap-3 mb-4">
                <Hash size={22} className="text-cyan-500" />
                <h3 className="text-lg font-semibold text-white">Hash Chain</h3>
              </div>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                Every record in a batch is linked via a SHA-256 hash chain. Each record's
                hash includes the previous record's hash, creating a tamper-evident sequence.
                Any modification to any record breaks the chain and is immediately detectable.
              </p>
              <div className="font-mono text-xs text-slate-500 bg-slate-950 p-3 border border-slate-800">
                method: SHA256_CHAIN_V1<br />
                canonicalization: JCS (RFC 8785)<br />
                tamper_detection: immediate
              </div>
            </div>
          </FadeIn>

          <FadeIn direction="up" delay={300}>
            <div className="action-block bg-slate-900/80 p-8">
              <div className="flex items-center gap-3 mb-4">
                <Lock size={22} className="text-cyan-500" />
                <h3 className="text-lg font-semibold text-white">External Anchoring</h3>
              </div>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                The batch root hash is anchored to immutable external storage (GCS with
                write-only policy). This creates an independent record that cannot be
                modified by the system that produced it.
              </p>
              <div className="font-mono text-xs text-slate-500 bg-slate-950 p-3 border border-slate-800">
                storage: Google Cloud Storage<br />
                policy: write-only (append)<br />
                retention: 7-year WORM
              </div>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* Evidence Schema */}
      <Section>
        <div className="max-w-4xl mx-auto">
          <FadeIn>
            <h2 className="text-2xl font-bold text-white mb-6">Evidence Schema</h2>
            <p className="text-slate-400 leading-relaxed mb-6">
              IAVP v1.0 uses the <span className="text-slate-300 font-mono">chunk_v1</span> evidence
              schema. Each batch produces a single attestation artifact containing up to 500 records
              per chunk, with per-batch KMS signatures. The schema is frozen and versioned.
            </p>
            <div className="action-block bg-slate-900/80 p-6">
              <div className="font-mono text-xs text-slate-400 space-y-1">
                <div><span className="text-cyan-400">protocol_version:</span> 1.0</div>
                <div><span className="text-cyan-400">artifact_type:</span> BATCH_ATTESTATION</div>
                <div><span className="text-cyan-400">evidence_schema:</span> chunk_v1</div>
                <div><span className="text-cyan-400">hash_chain.method:</span> SHA256_CHAIN_V1</div>
                <div><span className="text-cyan-400">hash_chain.ordering:</span> STABLE_INPUT_ORDER_V1</div>
                <div><span className="text-cyan-400">metrics.replay_runs:</span> 3</div>
                <div><span className="text-cyan-400">metrics.replay_variance:</span> 0</div>
              </div>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* Version + Full Spec Link */}
      <Section dark>
        <div className="max-w-4xl mx-auto">
          <FadeIn>
            <h2 className="text-2xl font-bold text-white mb-6">Protocol Version</h2>
            <div className="space-y-4 text-slate-400 leading-relaxed">
              <p>
                IAVP v1.0 is frozen. The protocol specification, evidence schema, and
                verification procedure are locked and will not change within the v1.x series.
                Any breaking change requires a major version increment (v2.0).
              </p>
              <p>
                Non-breaking additions (new optional fields, new layer types) may be
                introduced in minor versions (v1.1, v1.2) without invalidating existing
                attestations.
              </p>
            </div>
            <div className="mt-8 flex flex-col sm:flex-row gap-4">
              <Link
                to="/protocol/iavp/v1"
                className="group inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400 transition-colors"
              >
                Read the full formal specification
                <ExternalLink size={16} className="group-hover:translate-x-0.5 transition-transform" />
              </Link>
              <Link
                to="/verify"
                className="group inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400 transition-colors"
              >
                Verify a batch yourself
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* CTA */}
      <Section>
        <FadeIn>
          <CTABox
            title="See deterministic resolution with your data"
            description="Schedule a governance audit. We'll process your records and show you the attestation."
            primaryText="Request a Governance Audit"
            primaryHref="/request-demo"
            secondaryText="Compliance Details"
            secondaryHref="/compliance"
          />
        </FadeIn>
      </Section>

      <Footer />
      <CookieConsent />
    </div>
  );
}
