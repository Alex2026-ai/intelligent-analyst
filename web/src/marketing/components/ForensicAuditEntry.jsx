import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

/**
 * ForensicAuditEntry
 *
 * Permanent institutional action module for forensic audit initialization.
 * Not a panic banner. An infrastructure entry point.
 *
 * Design: OLED black, blueprint grid, amber accent, sharp corners.
 */
export default function ForensicAuditEntry() {
  return (
    <section className="py-16 md:py-20 relative" style={{ backgroundColor: '#05070A' }}>
      {/* Blueprint grid overlay */}
      <div
        className="absolute inset-0 pointer-events-none opacity-20"
        style={{
          backgroundImage: `
            linear-gradient(rgba(30, 41, 59, 0.5) 1px, transparent 1px),
            linear-gradient(90deg, rgba(30, 41, 59, 0.5) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }}
      />

      <div className="max-w-6xl mx-auto px-6 relative z-10">
        <div
          className="border p-8 md:p-12"
          style={{
            borderColor: '#FFB800',
            borderWidth: '1px',
            borderRadius: '2px',
            backgroundColor: 'rgba(5, 7, 10, 0.95)',
          }}
        >
          {/* Header */}
          <div className="mb-8">
            <div
              className="inline-block px-3 py-1 border mb-6"
              style={{
                borderColor: '#FFB800',
                backgroundColor: 'rgba(255, 184, 0, 0.08)',
              }}
            >
              <span
                className="font-mono text-xs uppercase"
                style={{
                  color: '#FFB800',
                  letterSpacing: '0.1em',
                }}
              >
                [ ACTION_REQUIRED: FORENSIC_AUDIT_INITIALIZATION ]
              </span>
            </div>
          </div>

          {/* Body */}
          <div className="max-w-3xl mb-10">
            <p className="text-lg md:text-xl text-slate-300 leading-relaxed mb-6">
              Facing a regulatory look-back, internal investigation, or compressed reporting deadline?
            </p>
            <p className="text-base text-slate-400 leading-relaxed mb-6">
              Intelligent Analyst reconstructs decision lineage using deterministic processing,
              cryptographic attestation, and immutable retention.
            </p>
            <p className="text-base text-slate-400 leading-relaxed">
              Generate verifiable evidence in hours — not narrative explanations in weeks.
            </p>
          </div>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <Link
              to="/security"
              className="group inline-flex items-center gap-3 px-6 py-3 border transition-colors"
              style={{
                borderColor: '#FFB800',
                borderRadius: '2px',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(255, 184, 0, 0.1)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              <span
                className="font-semibold"
                style={{ color: '#FFB800' }}
              >
                INITIALIZE FORENSIC AUDIT
              </span>
              <ArrowRight size={18} style={{ color: '#FFB800' }} className="group-hover:translate-x-1 transition-transform" />
            </Link>
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">
              Examination-ready evidence generation
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
