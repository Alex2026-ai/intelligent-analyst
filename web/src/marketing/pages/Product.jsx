import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Upload, Layers, FileCheck, CheckCircle2, AlertCircle } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';
import ScreenshotWithCallouts, { CalloutLegend } from '../components/ScreenshotWithCallouts';

export default function Product() {
  useEffect(() => {
    document.title = 'Product Tour | Intelligent Analyst';
  }, []);

  const workflow = [
    {
      icon: Upload,
      step: '01',
      title: 'Ingest',
      description: 'Upload CSV or submit via API. Batch sizes up to 100K records.',
    },
    {
      icon: Layers,
      step: '02',
      title: 'Resolve',
      description: 'Deterministic waterfall (L0-L4) matches records to canonical entities.',
    },
    {
      icon: FileCheck,
      step: '03',
      title: 'Notarize',
      description: 'Signed receipt with hash chain, external anchor, and public verification.',
    },
  ];

  // Callout positions are percentage-based for responsiveness
  const batchOverviewCallouts = [
    {
      id: 'trace-id',
      label: 'Trace ID',
      description: 'Every resolution batch is uniquely identifiable.',
      x: 55,
      y: 22,
      align: 'right',
    },
    {
      id: 'layer-breakdown',
      label: 'Layer Breakdown',
      description: 'Deterministic waterfall attribution (L1–L4).',
      x: 45,
      y: 70,
      align: 'right',
    },
    {
      id: 'signature-status',
      label: 'Signature Status',
      description: 'Cryptographically signed at completion.',
      x: 88,
      y: 45,
      align: 'left',
    },
    {
      id: 'retention',
      label: 'Retention Policy',
      description: 'Locked retention under regulatory setting.',
      x: 70,
      y: 92,
      align: 'left',
    },
  ];

  const forensicReceiptCallouts = [
    {
      id: 'resolution-method',
      label: 'Resolution Method',
      description: 'Layer attribution preserved.',
      x: 22,
      y: 35,
      align: 'right',
    },
    {
      id: 'confidence',
      label: 'Confidence Score',
      description: 'Deterministic + similarity scoring.',
      x: 22,
      y: 52,
      align: 'right',
    },
    {
      id: 'signature',
      label: 'Signature Field',
      description: 'HSM-backed signing.',
      x: 70,
      y: 78,
      align: 'left',
    },
    {
      id: 'timestamp',
      label: 'Timestamp',
      description: 'Immutable record of processing.',
      x: 22,
      y: 25,
      align: 'right',
    },
  ];

  const publicVerifyCallouts = [
    {
      id: 'sig-valid',
      label: 'Signature Valid',
      description: 'Asymmetric key verification.',
      x: 50,
      y: 58,
      align: 'right',
    },
    {
      id: 'hash-valid',
      label: 'Hash Chain Valid',
      description: 'Batch integrity intact.',
      x: 50,
      y: 70,
      align: 'right',
    },
    {
      id: 'anchor',
      label: 'Anchor Confirmed',
      description: 'Stored under immutable policy.',
      x: 50,
      y: 82,
      align: 'right',
    },
    {
      id: 'no-pii',
      label: 'No PII Exposed',
      description: 'Integrity verified without data leakage.',
      x: 50,
      y: 35,
      align: 'right',
    },
  ];

  const platformScreens = [
    {
      image: '/img/dashboard-batch-overview',
      title: 'Batch Overview',
      callouts: batchOverviewCallouts,
      proves: 'Proves resolution path for every record',
    },
    {
      image: '/img/forensic-receipt',
      title: 'Forensic Receipt',
      callouts: forensicReceiptCallouts,
      proves: 'Proves decision integrity and timestamp',
    },
    {
      image: '/img/public-verify',
      title: 'Public Verification',
      callouts: publicVerifyCallouts,
      proves: 'Proves no tampering without exposing PII',
    },
  ];

  const doesDo = [
    'Validates and resolves entity identifiers',
    'Produces signed receipts with verifiable integrity proofs',
    'Supports retention and legal hold controls',
    'Exports regulator-ready evidence packages',
  ];

  const doesNotDo = [
    'Does not replace ERP, accounting, or loan systems',
    'Does not make financial decisions',
    'Does not provide legal or regulatory determinations',
    'Public verification exposes no PII',
  ];

  const onboarding = [
    { step: '1', title: 'Data Sample', desc: 'Submit representative dataset' },
    { step: '2', title: 'Pilot Run', desc: 'Process batch with your data' },
    { step: '3', title: 'Security Review', desc: 'Architecture walkthrough' },
    { step: '4', title: 'Production', desc: 'Deploy with your team' },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* Hero */}
      <section className="pt-40 pb-20 md:pt-48 md:pb-28">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-3xl">
            <div className="text-cyan-500 text-xs font-mono uppercase tracking-wider mb-4">
              Product Tour
            </div>
            <h1 className="text-4xl md:text-6xl font-bold leading-tight mb-6">
              See how entity resolution becomes a verifiable financial control
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed mb-8 max-w-2xl">
              Process records through a deterministic pipeline. Every decision is signed,
              chained, and independently verifiable.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <Link
                to="/request-demo"
                className="inline-flex items-center justify-center gap-2 h-14 px-8 bg-cyan-500 text-slate-950 font-semibold hover:bg-cyan-400 transition-colors"
              >
                Request Demo
                <ArrowRight size={18} />
              </Link>
              <Link
                to="/trust-architecture"
                className="inline-flex items-center justify-center gap-2 h-14 px-8 border border-slate-700 text-white font-medium hover:bg-slate-800/50 transition-colors"
              >
                View Trust Architecture
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Workflow */}
      <Section dark>
        <SectionHeader
          eyebrow="Workflow"
          title="Three steps to verifiable resolution"
        />
        <div className="grid md:grid-cols-3 gap-6">
          {workflow.map((item, index) => (
            <div
              key={item.title}
              className="relative bg-slate-950 border border-slate-800 p-6"
            >
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center flex-shrink-0">
                  <item.icon size={24} className="text-cyan-500" />
                </div>
                <div>
                  <div className="text-slate-600 font-mono text-xs mb-1">{item.step}</div>
                  <h3 className="text-xl font-semibold text-white mb-2">{item.title}</h3>
                  <p className="text-slate-400 text-sm">{item.description}</p>
                </div>
              </div>
              {index < 2 && (
                <div className="hidden md:block absolute top-1/2 -right-3 transform -translate-y-1/2 z-10">
                  <ArrowRight size={16} className="text-slate-600" />
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* Platform Screens with Callouts */}
      <Section>
        <SectionHeader
          eyebrow="Platform"
          title="What you see at each stage"
          description="Hover on markers to explore each element."
        />
        <div className="space-y-20">
          {platformScreens.map((screen, index) => (
            <div
              key={screen.title}
              className={`grid lg:grid-cols-5 gap-8 items-start ${
                index % 2 === 1 ? '' : ''
              }`}
            >
              {/* Screenshot with callouts - takes 3 columns */}
              <div className={`lg:col-span-3 ${index % 2 === 1 ? 'lg:order-2' : ''}`}>
                <ScreenshotWithCallouts
                  image={screen.image}
                  alt={screen.title}
                  callouts={screen.callouts}
                />
              </div>

              {/* Side panel - takes 2 columns */}
              <div className={`lg:col-span-2 ${index % 2 === 1 ? 'lg:order-1' : ''}`}>
                <h3 className="text-2xl font-bold text-white mb-6">{screen.title}</h3>

                {/* Callout legend for desktop */}
                <div className="hidden lg:block mb-6">
                  <CalloutLegend callouts={screen.callouts} />
                </div>

                {/* What it proves */}
                <div className="bg-slate-900 border border-cyan-900/30 p-4 rounded">
                  <div className="text-[10px] text-cyan-500 font-mono uppercase tracking-wider mb-1">
                    What it proves
                  </div>
                  <div className="text-slate-300 text-sm">{screen.proves}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Disclosures & Boundaries */}
      <Section dark>
        <SectionHeader
          eyebrow="Disclosures"
          title="Boundaries of the platform"
        />
        <div className="grid md:grid-cols-2 gap-8">
          {/* What it does */}
          <div className="bg-slate-950 border border-slate-800 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-emerald-950 border border-emerald-900 flex items-center justify-center">
                <CheckCircle2 size={20} className="text-emerald-500" />
              </div>
              <h3 className="text-lg font-semibold text-white">What Intelligent Analyst does</h3>
            </div>
            <ul className="space-y-3">
              {doesDo.map((item) => (
                <li key={item} className="flex items-start gap-3 text-slate-400 text-sm">
                  <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full mt-2 flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          {/* What it does not do */}
          <div className="bg-slate-950 border border-slate-800 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-slate-800 border border-slate-700 flex items-center justify-center">
                <AlertCircle size={20} className="text-slate-500" />
              </div>
              <h3 className="text-lg font-semibold text-white">What Intelligent Analyst does not do</h3>
            </div>
            <ul className="space-y-3">
              {doesNotDo.map((item) => (
                <li key={item} className="flex items-start gap-3 text-slate-500 text-sm">
                  <div className="w-1.5 h-1.5 bg-slate-600 rounded-full mt-2 flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      {/* Enterprise Onboarding */}
      <Section>
        <SectionHeader
          eyebrow="Onboarding"
          title="Enterprise deployment path"
        />
        <div className="bg-slate-900 border border-slate-800 p-8">
          <div className="grid md:grid-cols-4 gap-6">
            {onboarding.map((item, index) => (
              <div key={item.step} className="relative text-center">
                <div className="w-12 h-12 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center mx-auto mb-4">
                  <span className="text-cyan-400 font-mono font-bold">{item.step}</span>
                </div>
                <h3 className="text-lg font-semibold text-white mb-1">{item.title}</h3>
                <p className="text-slate-500 text-sm">{item.desc}</p>
                {index < 3 && (
                  <div className="hidden md:block absolute top-6 -right-3">
                    <ArrowRight size={16} className="text-slate-600" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* CTA */}
      <Section dark>
        <CTABox
          title="Schedule a technical demo"
          description="Walk through the platform with your own data sample."
          primaryText="Request Demo"
          primaryHref="/request-demo"
          secondaryText="Download Solution Brief"
          secondaryHref="/resources"
        />
      </Section>

      <Footer />
    </div>
  );
}
