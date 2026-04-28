import React from 'react';

/**
 * TransparencyManifesto
 *
 * Core doctrine statement. No gradients, no animation.
 * Serious institutional tone.
 */
export default function TransparencyManifesto() {
  return (
    <section className="py-20 md:py-28 bg-slate-950">
      {/* Top divider */}
      <div className="max-w-7xl mx-auto px-6">
        <div className="border-t border-slate-800 mb-16" />
      </div>

      <div className="max-w-4xl mx-auto px-6">
        <h2 className="text-2xl md:text-3xl font-bold text-white mb-8">
          The End of the Black Box
        </h2>

        <div className="space-y-6 text-slate-400 leading-relaxed">
          <p>
            Most AI systems return answers but conceal the reasoning.
            Intelligent Analyst was founded on a different premise: transparency is non-negotiable.
          </p>

          <div className="space-y-2 font-mono text-sm text-slate-300 pl-4 border-l-2 border-slate-700">
            <p>Every resolution is traceable.</p>
            <p>Every layer is attributable.</p>
            <p>Every decision carries a cryptographic signature.</p>
          </div>

          <p>
            We do not ask enterprises to trust a model.
            <br />
            We provide evidence.
          </p>
        </div>
      </div>

      {/* Bottom divider */}
      <div className="max-w-7xl mx-auto px-6">
        <div className="border-t border-slate-800 mt-16" />
      </div>
    </section>
  );
}
