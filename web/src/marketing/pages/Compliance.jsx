import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Shield, FileCheck, Lock, Scale, Archive, Eye } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';
import CookieConsent from '../components/CookieConsent';
import { FadeIn } from '../components/AnimatedSection';

export default function Compliance() {
  useEffect(() => {
    document.title = 'Compliance & Governance | Intelligent Analyst';
  }, []);

  const frameworks = [
    {
      label: 'SOC 2',
      status: 'Aligned',
      detail: 'Audit trail integrity, access controls, cryptographic signing, and data retention are designed to support SOC 2 Trust Service Criteria for Processing Integrity and Confidentiality.',
    },
    {
      label: 'GDPR Article 28',
      status: 'Aligned',
      detail: 'Per-tenant isolation, data processing records, PII detection and masking, and explicit data retention controls support Article 28 processor obligations.',
    },
    {
      label: 'HIPAA',
      status: 'Aligned',
      detail: 'Encryption at rest and in transit, audit logging, access controls, and BAA-compatible architecture are designed for HIPAA-covered workflows. Formal customer use requires appropriate agreements and review.',
    },
    {
      label: 'EU AI Act',
      status: 'Pathway',
      detail: 'Deterministic replay, decision traceability, and human oversight (L4) support high-risk AI system requirements under the EU AI Act transparency obligations.',
    },
  ];

  const relianceTiers = [
    {
      tier: 'Advisory',
      description: 'IAVP attestation accompanies decisions but does not govern them. Human review is required for all outputs. Suitable for initial deployment and validation.',
      requirements: 'Attestation present. No automation dependency.',
    },
    {
      tier: 'Operational',
      description: 'IAVP-attested decisions are used in operational workflows with exception-based human review. L4 items are escalated; L1-L3 resolutions are accepted.',
      requirements: 'Attestation required. Replay verified. Audit trail retained.',
    },
    {
      tier: 'Autonomous',
      description: 'IAVP-attested decisions drive downstream systems without per-record human review. Full cryptographic chain required. Legal hold and WORM retention mandatory.',
      requirements: 'Full attestation chain. External anchoring. Legal hold capability. 7-year WORM.',
    },
  ];

  const evidencePackContents = [
    { file: 'results.csv', description: 'Complete resolution results with layer attribution and confidence scores' },
    { file: 'certificate.pdf', description: 'Forensic certificate with SHA-256 audit hash and ESG metrics' },
    { file: 'manifest.json', description: 'Cryptographic anchor — SHA-256 hashes of all files for integrity verification' },
    { file: 'audit_events.json', description: 'Full audit trail of processing events with timestamps' },
    { file: 'evidence_summary.json', description: 'Aggregated metadata including layer breakdown and verification status' },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* Trust Center Navigation */}
      <div className="pt-24 bg-slate-950 border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-6 text-sm">
            <Link to="/protocol" className="py-3 border-b-2 border-transparent text-slate-500 hover:text-slate-300 transition-colors">Protocol</Link>
            <Link to="/verify" className="py-3 border-b-2 border-transparent text-slate-500 hover:text-slate-300 transition-colors">Verify</Link>
            <span className="py-3 border-b-2 border-cyan-500 text-cyan-400 font-medium">Compliance</span>
          </div>
        </div>
      </div>

      {/* Hero */}
      <section className="pt-20 pb-16">
        <div className="max-w-4xl mx-auto px-6">
          <FadeIn direction="up">
            <div className="forensic-badge mb-6">Trust Center</div>
            <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
              Compliance
              <br />
              <span className="text-cyan-400">& Governance</span>
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed max-w-3xl">
              How Intelligent Analyst aligns with regulatory frameworks and supports
              governance requirements for autonomous decision systems.
            </p>
          </FadeIn>
        </div>
      </section>

      {/* Reliance Model */}
      <Section>
        <SectionHeader
          eyebrow="Reliance Model"
          title="Three tiers of operational reliance"
          subtitle="IAVP attestations support different levels of automation depending on your governance requirements."
        />
        <div className="grid md:grid-cols-3 gap-8">
          {relianceTiers.map((tier, index) => (
            <FadeIn key={tier.tier} delay={index * 100} direction="up">
              <div className="action-block bg-slate-900/80 p-8 h-full flex flex-col">
                <div className="flex items-center gap-3 mb-4">
                  <div className={`w-3 h-3 ${index === 0 ? 'bg-slate-400' : index === 1 ? 'bg-cyan-500' : 'bg-emerald-500'}`} />
                  <h3 className="text-lg font-semibold text-white">{tier.tier}</h3>
                </div>
                <p className="text-slate-400 text-sm leading-relaxed mb-4 flex-1">{tier.description}</p>
                <div className="text-xs font-mono text-slate-500 border-t border-slate-800 pt-3">
                  {tier.requirements}
                </div>
              </div>
            </FadeIn>
          ))}
        </div>
      </Section>

      {/* Framework Alignment */}
      <Section dark>
        <SectionHeader
          eyebrow="Framework Alignment"
          title="Regulatory readiness"
          subtitle='Intelligent Analyst is designed to support compliance. "Aligned" means architectural support is in place. "Certified" requires third-party attestation, which is a separate engagement.'
        />
        <div className="max-w-3xl mx-auto space-y-6">
          {frameworks.map((fw, index) => (
            <FadeIn key={fw.label} delay={index * 75} direction="up">
              <div className="action-block bg-slate-900/80 p-6">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-lg font-semibold text-white">{fw.label}</h3>
                  <span className="text-emerald-500 text-sm font-mono bg-emerald-950/30 px-2 py-0.5">
                    {fw.status}
                  </span>
                </div>
                <p className="text-slate-400 text-sm leading-relaxed">{fw.detail}</p>
              </div>
            </FadeIn>
          ))}
        </div>
      </Section>

      {/* Governance Enforcement */}
      <Section>
        <div className="max-w-4xl mx-auto">
          <FadeIn>
            <h2 className="text-2xl font-bold text-white mb-6">What IAVP Enforces</h2>
            <div className="grid md:grid-cols-2 gap-8 mb-8">
              <div>
                <h3 className="text-sm font-semibold text-cyan-400 uppercase tracking-wider mb-4">Protocol Controls</h3>
                <div className="space-y-3">
                  {[
                    'Deterministic replay (3 runs, 0 variance)',
                    'Cryptographic signature per batch',
                    'SHA-256 hash chain integrity',
                    'External anchor (write-only storage)',
                    'Per-tenant data isolation',
                    'PII detection and masking',
                    'Legal hold with WORM retention',
                  ].map((item) => (
                    <div key={item} className="flex items-start gap-3 text-slate-400 text-sm">
                      <div className="w-2 h-2 bg-emerald-500 mt-1.5 flex-shrink-0" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-4">Outside The Protocol</h3>
                <div className="space-y-3">
                  {[
                    'Decision correctness (L3 is probabilistic)',
                    'Canonical coverage completeness',
                    'Regulatory certification (requires third-party)',
                    'Legal advice or regulatory interpretation',
                    'Zero false positives in person screening',
                  ].map((item) => (
                    <div key={item} className="flex items-start gap-3 text-slate-500 text-sm">
                      <div className="w-2 h-2 bg-slate-700 mt-1.5 flex-shrink-0" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <p className="text-slate-500 text-sm leading-relaxed border-t border-slate-800 pt-6">
              IAVP proves that the process ran correctly and reproducibly. It does not guarantee
              that every individual decision is correct — L3 (LLM) decisions are probabilistic by
              nature and are flagged as such. L4 items are explicitly routed to human review.
              Quality assurance for L3 decisions is handled by the L3 Audit Process, which samples
              and reviews 10% of LLM decisions weekly.
            </p>
          </FadeIn>
        </div>
      </Section>

      {/* Evidence Pack */}
      <Section dark>
        <div className="max-w-4xl mx-auto">
          <FadeIn>
            <h2 className="text-2xl font-bold text-white mb-4">Evidence Pack</h2>
            <p className="text-slate-400 leading-relaxed mb-6">
              Every completed batch can produce an evidence pack — a self-contained ZIP archive
              that serves as the compliance deliverable. The manifest.json is the cryptographic
              anchor: verify all file hashes against it.
            </p>
            <div className="action-block bg-slate-900/80 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="text-left text-slate-500 font-mono py-3 px-4">File</th>
                    <th className="text-left text-slate-500 font-mono py-3 px-4">Contents</th>
                  </tr>
                </thead>
                <tbody>
                  {evidencePackContents.map((item) => (
                    <tr key={item.file} className="border-b border-slate-800/50 last:border-0">
                      <td className="text-cyan-400 font-mono py-3 px-4 whitespace-nowrap">{item.file}</td>
                      <td className="text-slate-400 py-3 px-4">{item.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* Legal Hold + WORM */}
      <Section>
        <div className="max-w-4xl mx-auto">
          <FadeIn>
            <div className="grid md:grid-cols-2 gap-12">
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <Archive size={22} className="text-cyan-500" />
                  <h2 className="text-xl font-bold text-white">Legal Hold</h2>
                </div>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Any batch can be placed on legal hold via API. Once held, the complete evidence
                  pack is vaulted to WORM storage with a 7-year retention lock. The hold can be
                  released by an admin, but the vaulted copy remains immutable for the full retention
                  period.
                </p>
              </div>
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <Eye size={22} className="text-cyan-500" />
                  <h2 className="text-xl font-bold text-white">Audit Access</h2>
                </div>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Auditors can access the full audit trail, evidence blobs, and verification
                  endpoint without write permissions. The auditor role provides read-only access
                  to all forensic data within the assigned tenant scope.
                </p>
              </div>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* CTA */}
      <Section dark>
        <FadeIn>
          <CTABox
            title="Ready for a governance audit?"
            description="Process your records through IAVP. Review the attestation. Decide your reliance tier."
            primaryText="Request a Governance Audit"
            primaryHref="/request-demo"
            secondaryText="View the Protocol"
            secondaryHref="/protocol"
          />
        </FadeIn>
      </Section>

      <Footer />
      <CookieConsent />
    </div>
  );
}
