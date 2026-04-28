import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, FileCheck, Hash, Shield, Database, CheckCircle } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';

/**
 * ForensicAudit
 *
 * Procedural page for forensic audit initialization.
 * Tone: Measured. Procedural. Not dramatic.
 */
export default function ForensicAudit() {
  useEffect(() => {
    document.title = 'Forensic Audit | Intelligent Analyst';
  }, []);

  const reconstructionSteps = [
    {
      step: '01',
      title: 'Batch Ingestion',
      description: 'Upload historical records via secure API or encrypted file transfer. Records are validated, sanitized, and prepared for deterministic replay.',
    },
    {
      step: '02',
      title: 'Deterministic Replay',
      description: 'Each record is processed through the identical resolution pipeline used in production. Layer attribution is preserved for every decision.',
    },
    {
      step: '03',
      title: 'Evidence Capture',
      description: 'Every resolution is signed, hash-chained, and anchored to immutable storage. The complete decision lineage is reconstructed with cryptographic proof.',
    },
  ];

  const deliverables = [
    {
      icon: FileCheck,
      title: 'Forensic Receipt',
      description: 'Per-record decision documentation with layer attribution, confidence scores, and timestamp. Suitable for examination review.',
    },
    {
      icon: Hash,
      title: 'Hash Chain',
      description: 'SHA-256 cryptographic chain linking all records in the batch. Any modification breaks the chain and is immediately detectable.',
    },
    {
      icon: Shield,
      title: 'Signature Verification',
      description: 'ECDSA P-256 signatures on every decision. Signatures are independently verifiable using the public key fingerprint.',
    },
    {
      icon: Database,
      title: 'WORM Retention',
      description: '7-year immutable retention with legal hold support. Records cannot be deleted or modified, even by administrators.',
    },
  ];

  const verificationPoints = [
    'Verification exposes no PII or sensitive data',
    'Signature validation uses public key cryptography',
    'Hash chain integrity is independently reproducible',
    'Anchor records are stored in write-once storage',
    'Third-party auditors can verify without platform access',
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* Hero */}
      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-3xl">
            <div
              className="inline-flex items-center gap-2 px-3 py-1 border mb-6"
              style={{
                borderColor: '#FFB800',
                backgroundColor: 'rgba(255, 184, 0, 0.08)',
              }}
            >
              <span
                className="font-mono text-xs uppercase"
                style={{ color: '#FFB800', letterSpacing: '0.08em' }}
              >
                Forensic Audit
              </span>
            </div>
            <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
              Evidence Reconstruction
              <br />
              <span className="text-slate-400">for Regulatory Review</span>
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed mb-8">
              Reconstruct decision lineage using deterministic replay.
              Generate examination-ready documentation with cryptographic verification.
            </p>
            <Link
              to="/request-demo"
              className="inline-flex items-center gap-2 px-6 py-3 border transition-colors"
              style={{
                borderColor: '#FFB800',
                borderRadius: '2px',
              }}
            >
              <span style={{ color: '#FFB800' }} className="font-semibold">
                Request Forensic Review
              </span>
              <ArrowRight size={18} style={{ color: '#FFB800' }} />
            </Link>
          </div>
        </div>
      </section>

      {/* Section 1: Rapid Evidence Reconstruction */}
      <Section dark>
        <SectionHeader
          eyebrow="Process"
          title="Rapid Evidence Reconstruction"
          description="Deterministic replay of historical decisions with full lineage preservation."
        />
        <div className="grid md:grid-cols-3 gap-6">
          {reconstructionSteps.map((item, index) => (
            <div
              key={item.step}
              className="relative bg-slate-950 border border-slate-800 p-6"
            >
              <div className="flex items-start gap-4">
                <div
                  className="w-12 h-12 border flex items-center justify-center flex-shrink-0"
                  style={{
                    borderColor: '#FFB800',
                    backgroundColor: 'rgba(255, 184, 0, 0.08)',
                  }}
                >
                  <span className="font-mono text-sm" style={{ color: '#FFB800' }}>
                    {item.step}
                  </span>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white mb-2">{item.title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed">{item.description}</p>
                </div>
              </div>
              {index < reconstructionSteps.length - 1 && (
                <div className="hidden md:block absolute top-1/2 -right-3 transform -translate-y-1/2 z-10">
                  <ArrowRight size={16} className="text-slate-600" />
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* Section 2: Examination Deliverables */}
      <Section>
        <SectionHeader
          eyebrow="Deliverables"
          title="Examination Documentation"
          description="Cryptographically verified evidence suitable for regulatory review."
        />
        <div className="grid md:grid-cols-2 gap-6">
          {deliverables.map((item) => (
            <div
              key={item.title}
              className="bg-slate-900 border border-slate-800 p-6"
            >
              <div className="w-12 h-12 bg-amber-950/50 border border-amber-900/50 flex items-center justify-center mb-4">
                <item.icon size={24} className="text-amber-500" />
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">{item.title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed">{item.description}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Section 3: Public Verification */}
      <Section dark>
        <SectionHeader
          eyebrow="Verification"
          title="Independent Verification"
          description="Zero-PII validation for third-party audit."
        />
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-lg text-slate-400 leading-relaxed mb-8">
              Verification endpoints expose cryptographic proofs without revealing
              underlying data. Third-party auditors can independently confirm
              integrity without requiring platform access or data exposure.
            </p>
            <ul className="space-y-4">
              {verificationPoints.map((point) => (
                <li key={point} className="flex items-start gap-3">
                  <CheckCircle size={18} className="text-emerald-500 mt-0.5 flex-shrink-0" />
                  <span className="text-slate-300 text-sm">{point}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-slate-950 border border-slate-800 p-6">
            <div className="font-mono text-xs text-slate-500 uppercase tracking-wider mb-4">
              Verification Response
            </div>
            <pre className="text-sm text-slate-400 overflow-x-auto">
{`{
  "batch_id": "BATCH-2026-Q1-DEMO",
  "signature_valid": true,
  "hash_chain_valid": true,
  "anchor_confirmed": true,
  "pii_exposed": false,
  "retention_status": "COMMITTED",
  "retention_until": "2033-02-17"
}`}
            </pre>
          </div>
        </div>
      </Section>

      {/* Doctrine Block */}
      <Section>
        <div className="max-w-2xl mx-auto text-center">
          <div className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-8">
            TRANSPARENCY HAS NO SIDE
          </div>
          <div className="space-y-6 text-lg text-slate-400 leading-relaxed">
            <p>
              Forensic reconstruction is not remediation. It is documentation.
            </p>
            <p>
              The platform does not alter historical decisions.
              It reconstructs and attests to what occurred.
            </p>
            <p className="text-slate-500">
              The outcome is verifiable record — not revisionist narrative.
            </p>
          </div>
        </div>
      </Section>

      {/* CTA */}
      <Section dark>
        <CTABox
          title="Initialize Forensic Review"
          description="Schedule a technical walkthrough of the evidence reconstruction process."
          primaryText="Request Demo"
          primaryHref="/request-demo"
          secondaryText="View Trust Architecture"
          secondaryHref="/trust-architecture"
        />
      </Section>

      <Footer />
    </div>
  );
}
