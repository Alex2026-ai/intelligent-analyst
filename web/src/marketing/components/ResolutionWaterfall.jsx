import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle, Zap, Brain, Stamp } from 'lucide-react';

/**
 * ResolutionWaterfall
 *
 * Mechanical scroll-driven narrative showing entity transformation through L1→L2→L3→L4 gates.
 * Features scanning animations and stamp effect for notarization.
 */

const gates = [
  {
    id: 'l1',
    layer: 'L1',
    title: 'Deterministic',
    subtitle: 'Exact Match',
    icon: CheckCircle,
    color: '#22c55e',
    description: 'Normalize, deduplicate, and match against known canonical names.',
    transform: {
      before: 'JPMORGAN CHASE & CO.',
      after: 'JPMorgan Chase & Co.',
    },
    stats: { resolved: '~40%', latency: '<1ms' },
  },
  {
    id: 'l2',
    layer: 'L2',
    title: 'Vector',
    subtitle: 'Semantic Similarity',
    icon: Zap,
    color: '#3b82f6',
    description: 'TF-IDF and cosine similarity match fuzzy variations to canonicals.',
    transform: {
      before: 'JP Morgan Chase',
      after: 'JPMorgan Chase & Co.',
    },
    stats: { resolved: '~35%', latency: '~5ms' },
  },
  {
    id: 'l3',
    layer: 'L3',
    title: 'Adjudication',
    subtitle: 'AI Resolution',
    icon: Brain,
    color: '#f59e0b',
    description: 'Claude analyzes ambiguous cases with context and reasoning.',
    transform: {
      before: 'Chase Manhattan Bank',
      after: 'JPMorgan Chase & Co.',
    },
    stats: { resolved: '~20%', latency: '~500ms' },
  },
  {
    id: 'l4',
    layer: 'L4',
    title: 'Notarization',
    subtitle: 'Cryptographic Seal',
    icon: Stamp,
    color: '#0891b2',
    description: 'Hash-chain commitment and ECDSA signature for immutable audit.',
    transform: {
      before: 'Resolved Entity',
      after: 'BATCH-A1B2C3D4',
    },
    stats: { integrity: 'SHA-256', retention: '7 years' },
    isNotarization: true,
  },
];

function GateCard({ gate, isActive, isComplete, index }) {
  const Icon = gate.icon;
  const [showStamp, setShowStamp] = useState(false);

  useEffect(() => {
    if (gate.isNotarization && isActive && !isComplete) {
      const timer = setTimeout(() => setShowStamp(true), 500);
      return () => clearTimeout(timer);
    }
    // Reset stamp when gate becomes inactive
    if (!isActive) {
      setShowStamp(false);
    }
  }, [isActive, isComplete, gate.isNotarization]);

  return (
    <div
      className={`waterfall-gate transition-all duration-300 ${isActive ? 'active' : ''} ${isComplete ? 'opacity-50' : ''}`}
      style={{
        transform: isActive ? 'translateX(0)' : 'translateX(-8px)',
        background: isActive ? 'rgba(8, 145, 178, 0.05)' : 'transparent',
      }}
    >
      {/* Scanning laser animation for active gate (L1-L3 only) */}
      {isActive && !gate.isNotarization && (
        <div className="gate-scanner" />
      )}

      <div className="flex items-start gap-6">
        {/* Layer Badge */}
        <div
          className="w-16 h-16 flex items-center justify-center border flex-shrink-0 relative"
          style={{
            borderColor: isActive ? gate.color : 'var(--forensic-border)',
            background: isActive ? `${gate.color}15` : 'transparent',
          }}
        >
          <Icon
            size={28}
            style={{ color: isActive ? gate.color : 'var(--forensic-muted)' }}
          />

          {/* Stamp seal animation for L4 */}
          {gate.isNotarization && showStamp && (
            <div className="absolute inset-0 flex items-center justify-center stamp-seal">
              <div
                className="w-12 h-12 border-2 flex items-center justify-center"
                style={{ borderColor: gate.color }}
              >
                <span className="font-mono text-xs font-bold" style={{ color: gate.color }}>
                  SEALED
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <span
              className="font-mono text-sm font-semibold"
              style={{ color: gate.color }}
            >
              {gate.layer}
            </span>
            <span className="text-white font-semibold">{gate.title}</span>
            <span className="text-slate-500 text-sm font-mono">/ {gate.subtitle}</span>
          </div>

          <p className="text-slate-400 text-sm mb-4">{gate.description}</p>

          {/* Transformation Example */}
          {gate.transform && (
            <div className="bg-slate-900/80 border border-slate-800 p-4 mb-4">
              <div className="flex items-center gap-4 text-sm">
                <div className="flex-1">
                  <div className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-1">Input</div>
                  <div className="font-mono text-slate-300">{gate.transform.before}</div>
                </div>
                <div className="text-slate-600 font-mono">→</div>
                <div className="flex-1">
                  <div className="text-xs font-mono uppercase tracking-wider mb-1" style={{ color: gate.color }}>
                    Output
                  </div>
                  <div className="font-mono text-white">{gate.transform.after}</div>
                </div>
              </div>
            </div>
          )}

          {/* Stats */}
          <div className="flex gap-6 text-xs">
            {Object.entries(gate.stats).map(([key, value]) => (
              <div key={key} className="font-mono">
                <span className="text-slate-500 uppercase tracking-wider">{key}: </span>
                <span className="text-slate-300">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ResolutionWaterfall() {
  const containerRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const prefersReducedMotion = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    if (prefersReducedMotion) {
      setActiveIndex(gates.length - 1);
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const rect = container.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const scrollProgress = Math.max(0, Math.min(1,
        (viewportHeight - rect.top) / (viewportHeight + rect.height * 0.5)
      ));
      const newIndex = Math.min(
        gates.length - 1,
        Math.floor(scrollProgress * gates.length)
      );
      setActiveIndex(newIndex);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();

    return () => window.removeEventListener('scroll', handleScroll);
  }, [prefersReducedMotion]);

  return (
    <section className="py-24 md:py-32 bg-slate-950" ref={containerRef}>
      <div className="max-w-7xl mx-auto px-6">
        {/* Section Header */}
        <div className="max-w-3xl mb-16">
          <div className="forensic-badge mb-4">Resolution Pipeline</div>
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Four gates of attestation
          </h2>
          <p className="text-lg text-slate-400 leading-relaxed">
            Radical transparency through a deterministic waterfall.
            We replace AI guessing with traceable, governed resolution layers.
          </p>
        </div>

        {/* Waterfall Visualization */}
        <div className="grid lg:grid-cols-2 gap-12 items-start">
          {/* Left: Gate Cards */}
          <div className="space-y-0">
            {gates.map((gate, index) => (
              <GateCard
                key={gate.id}
                gate={gate}
                isActive={index === activeIndex}
                isComplete={index < activeIndex}
                index={index}
              />
            ))}
          </div>

          {/* Right: Live Entity Status */}
          <div className="lg:sticky lg:top-32">
            <div className="terminal-frame p-6">
              <div className="terminal-header mb-4">
                Entity Processing Status
              </div>

              {/* Current Gate Indicator */}
              <div className="mb-6">
                <div className="flex items-center gap-3 mb-2">
                  <div
                    className="w-2 h-2"
                    style={{
                      backgroundColor: gates[activeIndex].color,
                      boxShadow: `0 0 8px ${gates[activeIndex].color}`
                    }}
                  />
                  <span className="font-mono text-sm" style={{ color: gates[activeIndex].color }}>
                    {gates[activeIndex].layer}
                  </span>
                  <span className="text-white font-medium">
                    {gates[activeIndex].title}
                  </span>
                </div>
                <p className="text-slate-400 text-sm font-mono">
                  {gates[activeIndex].description}
                </p>
              </div>

              {/* Progress Bar */}
              <div className="mb-6">
                <div className="flex justify-between text-xs font-mono text-slate-500 mb-2">
                  <span>PROGRESS</span>
                  <span>{Math.round(((activeIndex + 1) / gates.length) * 100)}%</span>
                </div>
                <div className="h-1 bg-slate-800 relative overflow-hidden">
                  <div
                    className="h-full transition-all duration-500"
                    style={{
                      width: `${((activeIndex + 1) / gates.length) * 100}%`,
                      backgroundColor: gates[activeIndex].color,
                      boxShadow: `0 0 10px ${gates[activeIndex].color}`,
                    }}
                  />
                  {/* Scan line */}
                  <div className="scan-line" style={{ top: 0 }} />
                </div>
              </div>

              {/* Layer Distribution Preview */}
              <div className="grid grid-cols-4 gap-2">
                {gates.map((gate, index) => (
                  <div
                    key={gate.id}
                    className={`p-3 border text-center transition-all duration-300 ${
                      index <= activeIndex ? '' : 'opacity-30'
                    }`}
                    style={{
                      borderColor: index <= activeIndex ? gate.color : 'var(--forensic-border)',
                      background: index === activeIndex ? `${gate.color}10` : 'transparent',
                    }}
                  >
                    <div className="font-mono text-xs mb-1" style={{ color: gate.color }}>
                      {gate.layer}
                    </div>
                    <div className="text-slate-500 text-xs font-mono truncate">{gate.title}</div>
                  </div>
                ))}
              </div>

              {/* Hash Preview */}
              {activeIndex === gates.length - 1 && (
                <div className="mt-6 pt-4 border-t border-slate-800">
                  <div className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">
                    Batch Signature
                  </div>
                  <div className="hash-display hash-flicker">
                    sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
                  </div>
                </div>
              )}
            </div>

            {/* Reduced Motion Notice */}
            {prefersReducedMotion && (
              <div className="mt-4 p-3 border border-slate-800 text-xs font-mono text-slate-500">
                Animation disabled per accessibility preferences.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
