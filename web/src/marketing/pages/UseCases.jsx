import React, { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowRight, Shield, FileCheck, Database, Truck, CheckCircle } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';

const USE_CASES = {
  'regulatory-compliance': {
    title: 'Regulatory Compliance',
    subtitle: 'Examination-ready audit trails',
    icon: Shield,
    description: 'Generate immutable evidence packages for regulatory examinations. Every entity resolution decision is signed, hash-chained, and retained in WORM storage for 7 years.',
    points: [
      'Cryptographic proof of every resolution decision',
      'Public verification without PII exposure',
      'WORM retention with legal hold support',
      'Deterministic replay for evidence reconstruction',
      'SOC 2-aligned control design',
    ],
  },
  'clinical-data-governance': {
    title: 'Clinical Data Governance',
    subtitle: 'HIPAA-aligned entity matching',
    icon: FileCheck,
    description: 'Resolve patient and provider entities across clinical systems with PII masking at ingestion. All resolution decisions are attributed and auditable.',
    points: [
      'PII detection and masking at ingestion',
      'Per-tenant data isolation',
      'Configurable matching thresholds',
      'Full decision lineage for compliance review',
      'HIPAA-aligned data handling design',
    ],
  },
  'master-data-management': {
    title: 'Master Data Management',
    subtitle: 'Unify records across systems',
    icon: Database,
    description: 'Consolidate entity records from disparate sources into a canonical reference. Deterministic matching ensures reproducible results.',
    points: [
      'Batch ingestion up to 100K records',
      '358 canonical entities across 27 sectors',
      'Layer attribution for every match decision',
      'Export to CSV with original-to-resolved mapping',
      'API integration for continuous resolution',
    ],
  },
  'supply-chain': {
    title: 'Supply Chain Verification',
    subtitle: 'Verify supplier identity',
    icon: Truck,
    description: 'Resolve supplier and counterparty names against approved canonical entity references. Resolution decisions are signed, reproducible, and auditable.',
    points: [
      'Supplier and counterparty entity resolution',
      'Canonical reference matching for approved supplier data',
      'Configurable risk thresholds',
      'Evidence packages for due diligence',
      'Cryptographic attestation of resolution results',
    ],
  },
};

const SLUG_ORDER = [
  'regulatory-compliance',
  'clinical-data-governance',
  'master-data-management',
  'supply-chain',
];

export default function UseCases() {
  const { slug } = useParams();
  const useCase = slug ? USE_CASES[slug] : null;

  useEffect(() => {
    document.title = useCase
      ? `${useCase.title} | Intelligent Analyst`
      : 'Use Cases | Intelligent Analyst';
  }, [useCase]);

  // If no slug or invalid slug, show index
  if (!useCase) {
    return (
      <div className="min-h-screen bg-slate-950 text-white">
        <Header />
        <section className="pt-32 pb-16 md:pt-40 md:pb-24">
          <div className="max-w-7xl mx-auto px-6">
            <div className="max-w-3xl mb-16">
              <div className="forensic-badge mb-6">Use Cases</div>
              <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
                Built for regulated industries
              </h1>
              <p className="text-xl text-slate-400 leading-relaxed">
                Entity resolution with cryptographic attestation for compliance-critical workflows.
              </p>
            </div>
            <div className="grid md:grid-cols-2 gap-6">
              {SLUG_ORDER.map((s) => {
                const uc = USE_CASES[s];
                return (
                  <Link
                    key={s}
                    to={`/use-cases/${s}`}
                    className="group block bg-slate-900 border border-slate-800 p-8 hover:border-cyan-900/50 transition-all"
                  >
                    <div className="w-12 h-12 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center mb-6">
                      <uc.icon size={24} className="text-cyan-500" />
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-2 group-hover:text-cyan-400 transition-colors">
                      {uc.title}
                    </h3>
                    <p className="text-slate-400 text-sm mb-4">{uc.subtitle}</p>
                    <span className="inline-flex items-center gap-1 text-cyan-500 text-sm font-medium group-hover:gap-2 transition-all">
                      Learn more <ArrowRight size={14} />
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        </section>
        <Section dark>
          <CTABox
            title="See it with your data"
            description="Schedule a demo with your own records."
            primaryText="Request Demo"
            primaryHref="/request-demo"
            secondaryText="Product Tour"
            secondaryHref="/product"
          />
        </Section>
        <Footer />
      </div>
    );
  }

  // Specific use case detail page
  const Icon = useCase.icon;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />
      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-3xl">
            <div className="forensic-badge mb-6">{useCase.title}</div>
            <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
              {useCase.subtitle}
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed mb-8">
              {useCase.description}
            </p>
            <Link
              to="/request-demo"
              className="inline-flex items-center gap-2 h-12 px-6 bg-cyan-600 text-white font-semibold hover:bg-cyan-500 transition-colors"
            >
              Request Demo
              <ArrowRight size={18} />
            </Link>
          </div>
        </div>
      </section>

      <Section dark>
        <SectionHeader eyebrow="Capabilities" title="What you get" />
        <ul className="max-w-2xl space-y-4">
          {useCase.points.map((point) => (
            <li key={point} className="flex items-start gap-3">
              <CheckCircle size={18} className="text-cyan-500 mt-0.5 flex-shrink-0" />
              <span className="text-slate-300">{point}</span>
            </li>
          ))}
        </ul>
      </Section>

      {/* Cross-links */}
      <Section>
        <SectionHeader eyebrow="Related" title="Other use cases" />
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {SLUG_ORDER.filter((s) => s !== slug).map((s) => {
            const uc = USE_CASES[s];
            return (
              <Link
                key={s}
                to={`/use-cases/${s}`}
                className="group block bg-slate-900 border border-slate-800 p-5 hover:border-cyan-900/50 transition-all"
              >
                <h3 className="text-sm font-semibold text-white mb-1 group-hover:text-cyan-400 transition-colors">
                  {uc.title}
                </h3>
                <p className="text-slate-500 text-xs">{uc.subtitle}</p>
              </Link>
            );
          })}
        </div>
      </Section>

      <Section dark>
        <CTABox
          title="See it with your data"
          description="Schedule a demo. Bring your own records."
          primaryText="Request Demo"
          primaryHref="/request-demo"
          secondaryText="Product Tour"
          secondaryHref="/product"
        />
      </Section>

      <Footer />
    </div>
  );
}
