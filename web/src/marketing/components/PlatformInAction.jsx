import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Shield, CheckCircle2, FileCheck, Lock } from 'lucide-react';

export function BatchOverviewSection() {
  return (
    <section className="py-20 md:py-28 bg-slate-950">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-cyan-500 text-xs font-mono uppercase tracking-wider mb-4">
          Platform in Action
        </div>
        <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
          See how identity attestation becomes a financial control
        </h2>
        <p className="text-slate-400 mb-12 max-w-2xl">
          Every batch produces cryptographic proof. Every decision is traceable.
        </p>

        <div className="grid lg:grid-cols-2 gap-8 items-start">
          {/* Screenshot */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <picture>
              <source srcSet="/img/dashboard-batch-overview.webp" type="image/webp" />
              <img
                src="/img/dashboard-batch-overview.png"
                alt="Batch Overview Dashboard"
                className="w-full"
                loading="lazy"
              />
            </picture>
          </div>

          {/* Details panel */}
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Layer Distribution</h3>
              <div className="space-y-3">
                {[
                  { layer: 'L1', name: 'Deterministic', pct: '67%', color: 'bg-cyan-500' },
                  { layer: 'L2', name: 'Vector Match', pct: '25%', color: 'bg-cyan-600' },
                  { layer: 'L3', name: 'LLM Adjudication', pct: '6%', color: 'bg-cyan-700' },
                  { layer: 'L4', name: 'Human Review', pct: '2%', color: 'bg-amber-500' },
                ].map((item) => (
                  <div key={item.layer} className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-mono text-slate-400">
                      {item.layer}
                    </div>
                    <div className="flex-1">
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-slate-300">{item.name}</span>
                        <span className="text-slate-500 font-mono">{item.pct}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-900 border border-slate-800 p-4">
                <div className="text-slate-500 text-xs mb-1">Trace ID</div>
                <div className="text-cyan-400 font-mono text-sm">BATCH-A7F2E9C1</div>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4">
                <div className="text-slate-500 text-xs mb-1">Signature</div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-emerald-500" />
                  <span className="text-emerald-400 text-sm">Valid</span>
                </div>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4">
                <div className="text-slate-500 text-xs mb-1">Hash Chain</div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-emerald-500" />
                  <span className="text-emerald-400 text-sm">Intact</span>
                </div>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4">
                <div className="text-slate-500 text-xs mb-1">Retention</div>
                <div className="text-slate-300 text-sm font-mono">7 Years WORM</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ForensicReceiptSection() {
  return (
    <section className="py-20 md:py-28 bg-slate-900">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-cyan-500 text-xs font-mono uppercase tracking-wider mb-4">
          Forensic Evidence
        </div>
        <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
          The Forensic Receipt
        </h2>
        <p className="text-slate-400 mb-12 max-w-2xl">
          Every resolution produces a cryptographically signed evidence blob.
          Exportable as JSON or PDF for regulatory examinations.
        </p>

        <div className="bg-slate-950 border border-slate-800 rounded-lg overflow-hidden">
          <picture>
            <source srcSet="/img/forensic-receipt.webp" type="image/webp" />
            <img
              src="/img/forensic-receipt.png"
              alt="Forensic Receipt - JSON and PDF"
              className="w-full"
              loading="lazy"
            />
          </picture>
        </div>

        <div className="grid md:grid-cols-3 gap-6 mt-8">
          {[
            {
              icon: Lock,
              title: 'Cryptographic Signature',
              desc: 'ECDSA P-256 via Cloud KMS',
            },
            {
              icon: Shield,
              title: 'Hash Chain Integrity',
              desc: 'SHA-256 linking all records',
            },
            {
              icon: FileCheck,
              title: 'External Anchor',
              desc: 'GCS immutable write confirmation',
            },
          ].map((item) => (
            <div key={item.title} className="flex items-start gap-3">
              <div className="w-10 h-10 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center flex-shrink-0">
                <item.icon size={18} className="text-cyan-500" />
              </div>
              <div>
                <div className="text-white font-medium">{item.title}</div>
                <div className="text-slate-500 text-sm">{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function PublicVerifySection() {
  return (
    <section className="py-20 md:py-28 bg-slate-950">
      <div className="max-w-7xl mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <div className="text-cyan-500 text-xs font-mono uppercase tracking-wider mb-4">
              Public Verification
            </div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Verify without exposing data
            </h2>
            <p className="text-slate-400 mb-6">
              Public verification confirms cryptographic integrity without revealing
              underlying records. Regulators and auditors can independently validate
              that evidence has not been tampered with.
            </p>

            <div className="space-y-3 mb-8">
              {[
                'Hash chain verification',
                'Signature validation',
                'External anchor confirmation',
                'Zero PII exposure',
              ].map((item) => (
                <div key={item} className="flex items-center gap-3 text-slate-300">
                  <CheckCircle2 size={16} className="text-emerald-500" />
                  {item}
                </div>
              ))}
            </div>

            <Link
              to="/trust-architecture"
              className="inline-flex items-center gap-2 text-cyan-500 font-medium hover:text-cyan-400"
            >
              Learn more about trust architecture
              <ArrowRight size={16} />
            </Link>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <picture>
              <source srcSet="/img/public-verify.webp" type="image/webp" />
              <img
                src="/img/public-verify.png"
                alt="Public Verification Interface"
                className="w-full"
                loading="lazy"
              />
            </picture>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function PlatformInAction() {
  return (
    <>
      <BatchOverviewSection />
      <ForensicReceiptSection />
      <PublicVerifySection />
    </>
  );
}
