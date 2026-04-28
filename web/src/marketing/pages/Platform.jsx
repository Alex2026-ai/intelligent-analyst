import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Database, Layers, Zap, Shield, CheckCircle } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import CTABox from '../components/CTABox';

export default function Platform() {
  useEffect(() => {
    document.title = 'Platform | Intelligent Analyst';
  }, []);

  const layers = [
    {
      id: 'L0',
      title: 'Garbage Detection',
      description: 'Regex-based filtering of empty, numeric-only, PII, and placeholder entries.',
      cost: '$0',
    },
    {
      id: 'L1',
      title: 'Deterministic Match',
      description: 'Exact match, normalized match after suffix stripping, and known parent/alias lookup.',
      cost: '$0',
    },
    {
      id: 'L2',
      title: 'Vector Similarity',
      description: 'TF-IDF character n-gram vectorization with cosine similarity against canonical embeddings.',
      cost: '$0',
    },
    {
      id: 'L3',
      title: 'LLM Reasoning',
      description: 'Semantic resolution via Claude API. Budget-gated with configurable cost caps per batch.',
      cost: '~$0.005/call',
    },
    {
      id: 'L4',
      title: 'Human Review',
      description: 'Unresolved items flagged for manual review with full decision context preserved.',
      cost: 'Manual',
    },
  ];

  const capabilities = [
    'Batch sizes up to 100,000 records',
    '358 canonical entities across 27 sectors',
    'Configurable similarity thresholds',
    'Per-record layer attribution',
    'PII detection and masking',
    'Cryptographic audit trail for every decision',
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* Hero */}
      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-3xl">
            <div className="forensic-badge mb-6">Entity Resolution</div>
            <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
              Match messy records
              <br />
              <span className="text-cyan-400">to canonical entities</span>
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed mb-8">
              A deterministic waterfall that resolves entity names through five layers
              of increasing sophistication. Every decision is attributed, signed, and auditable.
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

      {/* Waterfall Layers */}
      <Section dark>
        <SectionHeader
          eyebrow="Architecture"
          title="Five-layer resolution waterfall"
          description="Each record flows through layers sequentially. Once resolved, it stops."
        />
        <div className="space-y-4">
          {layers.map((layer) => (
            <div
              key={layer.id}
              className="bg-slate-950 border border-slate-800 p-6 flex flex-col md:flex-row md:items-center gap-4"
            >
              <div className="w-16 h-16 border border-cyan-900/50 bg-cyan-950/30 flex items-center justify-center flex-shrink-0">
                <span className="font-mono text-cyan-400 text-lg font-bold">{layer.id}</span>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-1">{layer.title}</h3>
                <p className="text-slate-400 text-sm">{layer.description}</p>
              </div>
              <div className="font-mono text-sm text-slate-500">{layer.cost}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* Capabilities */}
      <Section>
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div>
            <SectionHeader
              eyebrow="Capabilities"
              title="Enterprise-grade resolution"
            />
            <ul className="space-y-4">
              {capabilities.map((cap) => (
                <li key={cap} className="flex items-start gap-3">
                  <CheckCircle size={18} className="text-cyan-500 mt-0.5 flex-shrink-0" />
                  <span className="text-slate-300 text-sm">{cap}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-6">
            <div className="font-mono text-xs text-slate-500 uppercase tracking-wider mb-4">
              Typical Distribution
            </div>
            <div className="space-y-3">
              {[
                { label: 'L1 Deterministic', pct: 85 },
                { label: 'L2 Vector', pct: 8 },
                { label: 'L3 LLM', pct: 2 },
                { label: 'L4 Human', pct: 5 },
              ].map((item) => (
                <div key={item.label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-400">{item.label}</span>
                    <span className="text-slate-500 font-mono">~{item.pct}%</span>
                  </div>
                  <div className="h-2 bg-slate-800">
                    <div
                      className="h-full bg-cyan-600"
                      style={{ width: `${item.pct}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* CTA */}
      <Section dark>
        <CTABox
          title="See the waterfall in action"
          description="Upload your records. See how each layer resolves."
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
