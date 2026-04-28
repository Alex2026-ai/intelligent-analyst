import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, AlertTriangle, Clock, FileWarning, Scale } from 'lucide-react';
import { FadeIn } from './AnimatedSection';

/**
 * SilentTax
 *
 * Heavy, blueprint-style section highlighting the hidden cost of un-notarized data.
 * LED/ledger aesthetic to emphasize financial burden.
 */

const painPoints = [
  {
    icon: Clock,
    stat: '40',
    unit: '%',
    label: 'of analyst time',
    description: 'spent on manual reconciliation and data validation that could be automated.',
    source: 'Industry average for mid-market financial institutions',
  },
  {
    icon: FileWarning,
    stat: '2.4',
    unit: 'M',
    prefix: '$',
    label: 'average audit cost',
    description: 'when regulators request evidence trails that don\'t exist or can\'t be verified.',
    source: 'Estimated remediation cost for data integrity findings',
  },
  {
    icon: Scale,
    stat: '18',
    unit: 'mo',
    label: 'regulatory lag',
    description: 'average delay in exam resolution due to missing or incomplete audit documentation.',
    source: 'Observed across banking examination cycles',
  },
  {
    icon: AlertTriangle,
    stat: '73',
    unit: '%',
    label: 'of data issues',
    description: 'discovered during audits, not during normal operations—when it\'s too late.',
    source: 'Post-mortem analysis of compliance findings',
  },
];

export default function SilentTax() {
  return (
    <section className="py-24 md:py-32 bg-slate-950 relative overflow-hidden">
      {/* Heavy blueprint grid background - darker and more prominent */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(30, 41, 59, 0.6) 1px, transparent 1px),
            linear-gradient(90deg, rgba(30, 41, 59, 0.6) 1px, transparent 1px),
            linear-gradient(rgba(30, 41, 59, 0.3) 1px, transparent 1px),
            linear-gradient(90deg, rgba(30, 41, 59, 0.3) 1px, transparent 1px)
          `,
          backgroundSize: '100px 100px, 100px 100px, 20px 20px, 20px 20px',
        }}
      />
      {/* Vignette effect for grounding */}
      <div className="absolute inset-0 bg-gradient-to-b from-slate-950/80 via-transparent to-slate-950/80 pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-r from-slate-950/50 via-transparent to-slate-950/50 pointer-events-none" />

      <div className="max-w-7xl mx-auto px-6 relative">
        {/* Header */}
        <FadeIn direction="up">
          <div className="max-w-3xl mb-16">
            <div className="forensic-badge mb-4">The Problem</div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-6 leading-tight">
              The silent tax on
              <br />
              <span className="text-amber-400">financial integrity</span>
            </h2>
            <p className="text-lg text-slate-400 leading-relaxed">
              Every day, institutions pay an invisible cost for un-notarized data:
              manual reconciliations, audit delays, regulatory risk, and decisions
              made on records that can't be proven.
            </p>
          </div>
        </FadeIn>

        {/* Pain Points Grid */}
        <div className="grid md:grid-cols-2 gap-6 mb-16">
          {painPoints.map((point, index) => (
            <FadeIn key={point.label} delay={index * 100} direction="up">
              <div className="bg-slate-900/80 border border-slate-800 p-6 hover:border-amber-900/50 transition-colors relative overflow-hidden">
                {/* Subtle grid overlay on card */}
                <div className="absolute inset-0 blueprint-grid opacity-30 pointer-events-none" />

                <div className="flex items-start gap-4 relative">
                  <div className="w-12 h-12 bg-amber-950/50 border border-amber-900/30 flex items-center justify-center flex-shrink-0">
                    <point.icon size={22} className="text-amber-500" />
                  </div>
                  <div className="flex-1">
                    {/* LED-style number display */}
                    <div className="flex items-baseline gap-1 mb-2">
                      {point.prefix && (
                        <span className="text-amber-400 font-mono text-xl ledger-number">{point.prefix}</span>
                      )}
                      <span className="text-4xl font-bold text-amber-400 font-mono ledger-number tracking-tight">
                        {point.stat}
                      </span>
                      <span className="text-amber-400/70 font-mono text-lg ledger-number">{point.unit}</span>
                      <span className="text-slate-400 text-sm font-mono ml-2">{point.label}</span>
                    </div>
                    <p className="text-slate-400 text-sm leading-relaxed mb-3">
                      {point.description}
                    </p>
                    <div className="text-slate-600 text-xs font-mono italic border-l-2 border-slate-800 pl-3">
                      {point.source}
                    </div>
                  </div>
                </div>
              </div>
            </FadeIn>
          ))}
        </div>

        {/* The Alternative */}
        <FadeIn direction="up" delay={400}>
          <div className="terminal-frame p-8 md:p-12">
            <div className="terminal-header mb-6">
              System Alternative
            </div>

            <div className="grid md:grid-cols-2 gap-8 items-center">
              <div>
                <h3 className="text-2xl font-bold text-white mb-4">
                  What if every record was provable?
                </h3>
                <p className="text-slate-400 leading-relaxed mb-6">
                  Intelligent Analyst eliminates the silent tax by making data
                  attestation automatic. Every entity resolved, every decision
                  signed, every audit trail immutable.
                </p>
                <ul className="space-y-3 text-sm font-mono">
                  {[
                    'Cryptographic proof at the record level',
                    'Instant audit response with pre-computed evidence',
                    'Zero manual reconciliation for resolved entities',
                    'Regulator-ready exports in one click',
                  ].map((item) => (
                    <li key={item} className="flex items-center gap-3 text-slate-300">
                      <div className="w-1.5 h-1.5 bg-cyan-500" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="text-center md:text-right">
                <div className="inline-block bg-slate-950 border border-slate-800 p-6">
                  <div className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">
                    Time to Audit Response
                  </div>
                  <div className="flex items-baseline justify-center md:justify-end gap-2 mb-4">
                    <span className="text-5xl font-bold text-cyan-400 font-mono ledger-number">&lt;1</span>
                    <span className="text-slate-400 font-mono">min</span>
                  </div>
                  <div className="text-slate-600 text-xs font-mono border-t border-slate-800 pt-3 mt-3">
                    vs. 18+ months industry average
                  </div>
                </div>
                <div className="mt-6">
                  <Link
                    to="/request-demo"
                    className="group inline-flex items-center gap-2 text-cyan-500 font-mono text-sm hover:text-cyan-400 transition-colors"
                  >
                    SEE THE DIFFERENCE
                    <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </FadeIn>
      </div>
    </section>
  );
}
