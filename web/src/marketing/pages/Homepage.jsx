import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Shield, Lock, Database, Repeat, FileCheck, Scale } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import TrustStrip from '../components/TrustStrip';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';
import CookieConsent from '../components/CookieConsent';
import { FadeIn } from '../components/AnimatedSection';
import TransparencyManifesto from '../components/TransparencyManifesto';
import PublicTrustFeed from '../components/PublicTrustFeed';

export default function Homepage() {
  useEffect(() => {
    document.title = 'Deterministic AI Governance | Intelligent Analyst';
  }, []);

  const proofCards = [
    { label: 'Deterministic Replay', detail: '3 Runs, 0 Variance' },
    { label: 'Cryptographic Attestation', detail: 'ECDSA P-256 + SHA-256' },
    { label: 'Immutable Retention', detail: '7-Year WORM' },
  ];

  const pillars = [
    {
      icon: Repeat,
      title: 'Determinism',
      subtitle: 'Replay-Verified Outputs',
      description: 'Same input and configuration should produce the same decision. Evidence artifacts show the replay checks used to detect variance before downstream reliance.',
    },
    {
      icon: FileCheck,
      title: 'Attestation',
      subtitle: 'Proof of Every Decision',
      description: 'Every resolution is cryptographically signed, hash-chained, and externally anchored. Decisions are version-controlled and tamper-evident.',
    },
    {
      icon: Scale,
      title: 'Audit Evidence',
      subtitle: 'Built for Regulated Automation',
      description: 'Designed to give regulated teams a defensible evidence trail: signed artifacts, retention controls, and decision lineage for review.',
    },
  ];

  const integrations = [
    {
      title: 'Lakehouse / Batch Compute',
      description: 'Embed IAVP attestation directly inside distributed data jobs. Each execution produces a verifiable receipt without leaving your data plane.',
    },
    {
      title: 'Integration Boundary (CRM / ERP)',
      description: 'Attach proof of origin at system handoff. Records carry integrity metadata across environments — not just resolved values.',
    },
    {
      title: 'Internal API / Sidecar',
      description: 'Deploy alongside existing services as an API or sidecar. Deterministic governance without architectural disruption.',
    },
  ];

  const useCases = [
    {
      title: 'Regulatory Compliance',
      description: 'Audit trails for examinations.',
      href: '/use-cases/regulatory-compliance',
    },
    {
      title: 'Clinical Data',
      description: 'HIPAA-aligned entity matching.',
      href: '/use-cases/clinical-data-governance',
    },
    {
      title: 'Master Data',
      description: 'Unify records across systems.',
      href: '/use-cases/master-data-management',
    },
    {
      title: 'Supply Chain',
      description: 'Verify supplier identity.',
      href: '/use-cases/supply-chain',
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* ================================================================
          HERO — Autonomous Decisions You Can Defend
          ================================================================ */}
      <section className="pt-48 pb-32 md:pt-56 md:pb-40 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-cyan-950/10 via-transparent to-transparent pointer-events-none" />

        <div className="max-w-7xl mx-auto px-6 relative">
          <FadeIn direction="up" duration={800}>
            <div className="max-w-4xl">
              <div className="forensic-badge mb-8">Deterministic AI Governance</div>

              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-[1.1] mb-8 tracking-tight">
                Autonomous Decisions
                <br />
                <span className="text-cyan-400">You Can Defend.</span>
              </h1>

              <p className="text-xl md:text-2xl text-slate-400 leading-relaxed mb-12 max-w-3xl font-light">
                Eliminate non-defensible AI decisions.
                <br />
                Built for regulated environments where every output must be reproducible, provable, and audit-ready.
              </p>

              <div className="flex flex-col sm:flex-row gap-4 mb-20">
                <Link
                  to="/request-demo"
                  className="action-block group inline-flex items-center justify-center gap-2 h-14 px-8 bg-cyan-600 text-white font-semibold hover:bg-cyan-500 transition-all duration-200"
                >
                  Request a Governance Audit
                  <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                </Link>
                <Link
                  to="/protocol"
                  className="action-block inline-flex items-center justify-center gap-2 h-14 px-8 border border-slate-700 text-white font-medium hover:bg-slate-800/50 hover:border-slate-600 transition-all duration-200"
                >
                  View the Protocol
                </Link>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {proofCards.map((card, index) => (
                  <FadeIn key={card.label} delay={index * 100} direction="up">
                    <div className="action-block bg-slate-900/60 backdrop-blur-sm p-5">
                      <div className="text-cyan-400 font-mono text-base mb-1">{card.detail}</div>
                      <div className="text-slate-500 text-sm">{card.label}</div>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </FadeIn>
        </div>
      </section>

      <TrustStrip />

      {/* ================================================================
          THREE PILLARS — Why Intelligent Analyst Exists
          ================================================================ */}
      <Section>
        <SectionHeader
          eyebrow="Core Guarantees"
          title="Why Intelligent Analyst Exists"
        />
        <div className="grid md:grid-cols-3 gap-8">
          {pillars.map((pillar, index) => (
            <FadeIn key={pillar.title} delay={index * 100} direction="up">
              <div className="action-block bg-slate-900/80 p-8">
                <div className="w-14 h-14 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center mb-6">
                  <pillar.icon size={26} className="text-cyan-500" />
                </div>
                <h3 className="text-xl font-semibold text-white mb-1">
                  {pillar.title}
                </h3>
                <p className="text-cyan-400 text-sm font-mono mb-4">{pillar.subtitle}</p>
                <p className="text-slate-400 text-sm leading-relaxed">{pillar.description}</p>
              </div>
            </FadeIn>
          ))}
        </div>
      </Section>

      {/* ================================================================
          INDUSTRY-AGNOSTIC PROOF
          ================================================================ */}
      <Section dark>
        <div className="max-w-3xl mx-auto">
          <FadeIn direction="up">
            <div className="forensic-badge mb-5">Proof</div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-6 leading-tight">
              Zero-Variance Resolution in Unseen Domains
            </h2>
            <div className="space-y-4 text-slate-400 leading-relaxed">
              <p>
                During the Solar Discovery test, Intelligent Analyst processed companies
                that had never appeared in the canonical list. Entities from energy,
                industrial, and specialty sectors — none pre-trained, none pre-configured.
              </p>
              <p>
                The result: three independent replay runs. Zero variance. Every decision
                cryptographically attested.
              </p>
              <p className="text-slate-300">
                IAVP does not require training on your data. It proves decisions regardless
                of domain.
              </p>
            </div>
            <div className="mt-8">
              <Link
                to="/protocol"
                className="group inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400 transition-colors"
              >
                Read the protocol specification
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* Transparency Manifesto — Core Doctrine */}
      <TransparencyManifesto />

      {/* ================================================================
          LIVE TRUST FEED — Published Authority Samples
          ================================================================ */}
      <Section dark>
        <SectionHeader
          eyebrow="Live Proof"
          title="Public Trust Feed"
          subtitle="Verified resolutions — deterministic, auditable, published through policy-controlled derivation."
        />
        <PublicTrustFeed limit={3} />
        <div className="text-center mt-6">
          <Link
            to="/trust-feed"
            className="inline-flex items-center gap-2 text-sm text-cyan-500 hover:text-cyan-400 transition-colors"
          >
            View all published samples <ArrowRight size={14} />
          </Link>
        </div>
      </Section>

      {/* ================================================================
          PROTOCOL VS APP — Not an App. A Standard.
          ================================================================ */}
      <Section>
        <SectionHeader
          eyebrow="Architecture"
          title="Not an App. A Standard."
          subtitle="IAVP is embeddable infrastructure. You don't switch platforms — you add attestation to the ones you already use."
        />
        <div className="grid md:grid-cols-3 gap-8">
          {integrations.map((item, index) => (
            <FadeIn key={item.title} delay={index * 100} direction="up">
              <div className="action-block bg-slate-900/80 p-8 h-full">
                <h3 className="text-lg font-semibold text-white mb-3">
                  {item.title}
                </h3>
                <p className="text-slate-400 text-sm leading-relaxed">{item.description}</p>
              </div>
            </FadeIn>
          ))}
        </div>
        <div className="text-center mt-8">
          <Link
            to="/protocol"
            className="group inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400 transition-colors"
          >
            View integration patterns
            <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
          </Link>
        </div>
      </Section>

      {/* ================================================================
          USE CASES — Regulated Industries
          ================================================================ */}
      <Section dark>
        <SectionHeader
          eyebrow="Use Cases"
          title="Built for regulated industries"
        />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {useCases.map((useCase, index) => (
            <FadeIn key={useCase.title} delay={index * 75} direction="up">
              <Link
                to={useCase.href}
                className="group block relative bg-slate-900 border border-slate-700 p-5 hover:border-cyan-700 transition-all duration-200 overflow-hidden"
              >
                <div className="absolute inset-0 blueprint-grid opacity-20 pointer-events-none" />
                <div className="relative z-10">
                  <h3 className="text-sm font-semibold text-white mb-2 group-hover:text-cyan-400 transition-colors">
                    {useCase.title}
                  </h3>
                  <p className="text-slate-400 text-xs leading-relaxed">{useCase.description}</p>
                </div>
              </Link>
            </FadeIn>
          ))}
        </div>
      </Section>

      {/* ================================================================
          SECURITY — Framework Alignment
          ================================================================ */}
      <Section>
        <div className="grid md:grid-cols-2 gap-16 items-center">
          <FadeIn direction="right">
            <div>
              <div className="forensic-badge mb-5">Security</div>
              <h2 className="text-3xl md:text-4xl font-bold text-white mb-6 leading-tight">
                Zero-trust by design
              </h2>
              <p className="text-slate-400 text-lg leading-relaxed mb-4">
                Per-tenant encryption, cryptographic signatures, and WORM retention.
                Public verification exposes no PII.
              </p>
              <p className="text-slate-400 leading-relaxed mb-8">
                Security is not only about protection. It is about transparency.
                Our public verification endpoint enables third-party audit without exposing PII.
                Governance is verifiable.
              </p>
              <div className="grid grid-cols-2 gap-4 mb-8">
                {[
                  'PII Masking',
                  'Circuit Breaker',
                  'Persistent Audit',
                  'ECDSA Signatures',
                  'SHA-256 Hash Chains',
                  '7-year WORM Retention',
                ].map((item) => (
                  <div key={item} className="flex items-center gap-3 text-slate-400">
                    <div className="w-2 h-2 bg-cyan-500 flex-shrink-0" />
                    <span className="text-sm font-mono">{item}</span>
                  </div>
                ))}
              </div>
              <Link
                to="/compliance"
                className="group inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400 transition-colors"
              >
                Compliance details
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </FadeIn>
          <FadeIn direction="left" delay={150}>
            <div className="action-block bg-slate-900/80 p-8">
              <div className="space-y-4">
                {[
                  { label: 'SOC 2', status: 'Aligned' },
                  { label: 'GDPR Article 28', status: 'Aligned' },
                  { label: 'HIPAA', status: 'Aligned' },
                  { label: 'EU AI Act', status: 'Pathway' },
                ].map((fw) => (
                  <div key={fw.label} className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0">
                    <span className="text-slate-300">{fw.label}</span>
                    <span className="text-emerald-500 text-sm font-mono bg-emerald-950/30 px-2 py-0.5">
                      {fw.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </FadeIn>
        </div>
      </Section>

      {/* ================================================================
          CTA
          ================================================================ */}
      <Section dark>
        <FadeIn>
          <CTABox
            title="See it with your data"
            description="Schedule a governance audit. Bring your own records."
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
