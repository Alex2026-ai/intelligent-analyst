import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle,
  Database,
  FileCheck,
  Fingerprint,
  GitBranch,
  Lock,
  ShieldCheck,
} from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';

export default function TrustArchitecture() {
  useEffect(() => {
    document.title = 'Trust Architecture | Intelligent Analyst';
  }, []);

  const layers = [
    {
      icon: Database,
      title: 'Tenant Boundary',
      detail:
        'Customer data is isolated by tenant before resolution work begins. Public verification exposes evidence metadata, not customer records.',
    },
    {
      icon: GitBranch,
      title: 'Deterministic Pipeline',
      detail:
        'Records follow a stable ordering and resolution path so the same input, policy, and model configuration can be replayed.',
    },
    {
      icon: Fingerprint,
      title: 'Attestation Layer',
      detail:
        'Batch roots, config snapshots, and manifest fields are bound to signatures and hash-chain evidence.',
    },
    {
      icon: Lock,
      title: 'Retention Boundary',
      detail:
        'Evidence artifacts are retained under policy controls designed for legal hold, audit review, and tamper detection.',
    },
  ];

  const controls = [
    'Least-privilege service access',
    'Per-batch evidence manifests',
    'PII-masked public verification',
    'Stable input ordering',
    'Hash-chain tamper detection',
    'Replay variance checks',
  ];

  const verificationFlow = [
    {
      step: '01',
      title: 'Canonicalize',
      body: 'Normalize batch records into a stable, reproducible representation.',
    },
    {
      step: '02',
      title: 'Resolve',
      body: 'Run the deterministic waterfall and preserve layer attribution.',
    },
    {
      step: '03',
      title: 'Bind',
      body: 'Hash the evidence chain and bind it to the manifest and signature.',
    },
    {
      step: '04',
      title: 'Verify',
      body: 'Expose a zero-PII proof surface for auditors and downstream systems.',
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-4xl">
            <div className="forensic-badge mb-6">Trust Architecture</div>
            <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
              Trust is designed
              <br />
              <span className="text-cyan-400">before the decision.</span>
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed max-w-3xl mb-8">
              Intelligent Analyst separates customer data, resolution logic, evidence
              generation, and public verification so each decision can be defended
              without exposing sensitive records.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <Link
                to="/protocol"
                className="inline-flex items-center justify-center gap-2 h-12 px-6 bg-cyan-500 text-slate-950 font-semibold hover:bg-cyan-400 transition-colors"
              >
                View Protocol
                <ArrowRight size={18} />
              </Link>
              <Link
                to="/verify"
                className="inline-flex items-center justify-center gap-2 h-12 px-6 border border-slate-700 text-slate-200 font-medium hover:bg-slate-900 transition-colors"
              >
                Verification Walkthrough
              </Link>
            </div>
          </div>
        </div>
      </section>

      <Section dark>
        <SectionHeader
          eyebrow="Boundary Model"
          title="Four trust layers"
          subtitle="Each layer has a narrow responsibility, so governance evidence is easier to reason about and verify."
        />
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {layers.map((layer) => (
            <div key={layer.title} className="bg-slate-950 border border-slate-800 p-6">
              <div className="w-12 h-12 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center mb-5">
                <layer.icon size={22} className="text-cyan-400" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-3">{layer.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{layer.detail}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <div className="grid lg:grid-cols-[0.9fr_1.1fr] gap-12 items-start">
          <div>
            <div className="forensic-badge mb-5">Control Surface</div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
              Evidence without unnecessary exposure
            </h2>
            <p className="text-slate-400 leading-relaxed mb-8">
              The trust architecture is built around one operating rule: prove the
              decision, not the private data behind it. Auditors can inspect signatures,
              ordering, replay status, and retention metadata while sensitive inputs stay
              inside the customer boundary.
            </p>
            <Link
              to="/samples/evidence-pack"
              className="inline-flex items-center gap-2 text-cyan-400 hover:text-cyan-300 font-medium"
            >
              Review sample evidence pack
              <ArrowRight size={16} />
            </Link>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            {controls.map((control) => (
              <div key={control} className="flex items-start gap-3 bg-slate-900/80 border border-slate-800 p-4">
                <CheckCircle size={18} className="text-emerald-400 mt-0.5 flex-shrink-0" />
                <span className="text-sm text-slate-300">{control}</span>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section dark>
        <SectionHeader
          eyebrow="Verification Path"
          title="From record to public proof"
          subtitle="The verification surface is narrow by design: enough proof for governance, without becoming a data leak."
        />
        <div className="grid md:grid-cols-4 gap-6">
          {verificationFlow.map((item) => (
            <div key={item.step} className="relative bg-slate-950 border border-slate-800 p-6">
              <div className="font-mono text-xs text-cyan-400 mb-4">{item.step}</div>
              <h3 className="text-lg font-semibold text-white mb-3">{item.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{item.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="bg-slate-900/80 border border-slate-800 p-6">
            <ShieldCheck size={24} className="text-cyan-400 mb-4" />
            <h3 className="text-lg font-semibold mb-2">For operators</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              A stable evidence contract for batch processing, exception review, and
              downstream system handoff.
            </p>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 p-6">
            <FileCheck size={24} className="text-cyan-400 mb-4" />
            <h3 className="text-lg font-semibold mb-2">For auditors</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              A repeatable path to inspect replay status, signatures, hash-chain roots,
              and retention metadata.
            </p>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 p-6">
            <Lock size={24} className="text-cyan-400 mb-4" />
            <h3 className="text-lg font-semibold mb-2">For security teams</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              A zero-PII public verification model that limits what leaves the tenant
              boundary.
            </p>
          </div>
        </div>
      </Section>

      <Section dark>
        <CTABox
          title="Review the trust model"
          description="Walk through tenant boundaries, verification surfaces, and evidence retention with your technical stakeholders."
          primaryText="Request a Governance Audit"
          primaryHref="/request-demo"
          secondaryText="Read IAVP v1.0"
          secondaryHref="/protocol/iavp/v1"
        />
      </Section>

      <Footer />
    </div>
  );
}
