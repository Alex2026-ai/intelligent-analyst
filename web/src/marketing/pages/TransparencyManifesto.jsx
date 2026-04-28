import React, { useEffect } from 'react';
import Header from '../components/Header';
import Footer from '../components/Footer';

/**
 * TransparencyManifesto
 *
 * Full page philosophical elevation.
 * OLED black. Blueprint grid. No gradients. No motion.
 * Whitepaper institutional tone.
 */

const pillars = [
  {
    number: '01',
    title: 'Determinism over Probability',
    description: 'We prioritize governed resolution layers over opaque statistical guesses. Every decision follows a traceable path through deterministic gates before any probabilistic inference is permitted.',
  },
  {
    number: '02',
    title: 'Attestation over Assertion',
    description: 'Every decision is signed. Nothing relies on implied trust. Cryptographic signatures bind each resolution to an immutable record that can be independently verified without platform dependency.',
  },
  {
    number: '03',
    title: 'Permanence over Drift',
    description: 'WORM retention prevents silent mutation of historical data. What was decided remains decided. Audit trails cannot be revised, overwritten, or selectively purged.',
  },
];

export default function TransparencyManifesto() {
  useEffect(() => {
    document.title = 'Transparency Manifesto | Intelligent Analyst';
  }, []);

  return (
    <div className="min-h-screen text-white" style={{ backgroundColor: '#05070A' }}>
      <Header />

      {/* Blueprint grid overlay - CSS only */}
      <div
        className="fixed inset-0 pointer-events-none opacity-30"
        style={{
          backgroundImage: `
            linear-gradient(rgba(30, 41, 59, 0.4) 1px, transparent 1px),
            linear-gradient(90deg, rgba(30, 41, 59, 0.4) 1px, transparent 1px),
            linear-gradient(rgba(30, 41, 59, 0.15) 1px, transparent 1px),
            linear-gradient(90deg, rgba(30, 41, 59, 0.15) 1px, transparent 1px)
          `,
          backgroundSize: '100px 100px, 100px 100px, 20px 20px, 20px 20px',
        }}
      />

      {/* Main Content */}
      <main className="relative z-10">
        {/* Opening Declaration */}
        <section className="pt-40 pb-16 md:pt-48 md:pb-20">
          <div className="max-w-3xl mx-auto px-6 text-center">
            <p
              className="text-3xl md:text-4xl lg:text-5xl font-light text-white leading-tight"
              style={{ letterSpacing: '0.02em' }}
            >
              Transparency has no side.
            </p>
          </div>
        </section>

        {/* Thin divider */}
        <div className="max-w-xl mx-auto px-6">
          <div className="border-t border-slate-800" />
        </div>

        {/* Hero Section */}
        <section className="pt-16 pb-24 md:pt-20 md:pb-32">
          <div className="max-w-4xl mx-auto px-6">
            <div className="mb-8">
              <span className="font-mono text-xs text-slate-500 uppercase tracking-widest">
                Doctrine
              </span>
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight mb-12">
              The End of the Black Box
            </h1>

            <div className="border-l-2 border-slate-700 pl-8 space-y-6 text-lg md:text-xl text-slate-400 leading-relaxed max-w-3xl">
              <p>
                Most AI systems return answers but conceal the reasoning.
              </p>
              <p>
                Intelligent Analyst was founded on a different premise:
                <span className="text-white font-medium"> transparency is non-negotiable.</span>
              </p>
            </div>
          </div>
        </section>

        {/* Divider */}
        <div className="max-w-4xl mx-auto px-6">
          <div className="border-t border-slate-800" />
        </div>

        {/* Pillars */}
        <section className="py-24 md:py-32">
          <div className="max-w-4xl mx-auto px-6">
            <div className="space-y-24">
              {pillars.map((pillar) => (
                <article key={pillar.number} className="group">
                  <div className="flex items-start gap-8">
                    {/* Number */}
                    <div className="flex-shrink-0 w-16">
                      <span className="font-mono text-2xl text-slate-600 font-light">
                        {pillar.number}
                      </span>
                    </div>

                    {/* Content */}
                    <div className="flex-1">
                      <h2 className="text-2xl md:text-3xl font-bold text-white mb-6">
                        {pillar.title}
                      </h2>
                      <p className="text-lg text-slate-400 leading-relaxed">
                        {pillar.description}
                      </p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Divider */}
        <div className="max-w-4xl mx-auto px-6">
          <div className="border-t border-slate-800" />
        </div>

        {/* Closing Statement */}
        <section className="py-24 md:py-32">
          <div className="max-w-4xl mx-auto px-6">
            <div className="text-center">
              <p className="font-mono text-lg md:text-xl text-slate-300 tracking-wide">
                Intelligent Analyst exists to make AI accountable.
              </p>
            </div>
          </div>
        </section>

        {/* Technical Specification Footer */}
        <section className="py-16 border-t border-slate-800">
          <div className="max-w-4xl mx-auto px-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
              <div>
                <div className="font-mono text-xs text-slate-600 uppercase tracking-widest mb-2">
                  Signing Algorithm
                </div>
                <div className="font-mono text-sm text-slate-400">
                  ECDSA P-256 / Cloud KMS
                </div>
              </div>
              <div>
                <div className="font-mono text-xs text-slate-600 uppercase tracking-widest mb-2">
                  Hash Chain
                </div>
                <div className="font-mono text-sm text-slate-400">
                  SHA-256 Cryptographic Linking
                </div>
              </div>
              <div>
                <div className="font-mono text-xs text-slate-600 uppercase tracking-widest mb-2">
                  Retention
                </div>
                <div className="font-mono text-sm text-slate-400">
                  7-Year WORM Immutable
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
