import React from 'react';
import { Lock, Shield, Database } from 'lucide-react';

/**
 * SignatureNotaryCard
 *
 * ECDSA + WORM card with CSS-only hover expand.
 * Reveals hash chain diagram and 3-bullet explanation.
 * No external animation libraries.
 */

// Inline SVG hash chain diagram
function HashChainDiagram({ color = '#0891b2' }) {
  return (
    <svg
      viewBox="0 0 200 60"
      className="w-full h-auto"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Hash blocks */}
      <rect x="0" y="20" width="40" height="20" stroke={color} strokeWidth="1" fill="none" />
      <rect x="55" y="20" width="40" height="20" stroke={color} strokeWidth="1" fill="none" />
      <rect x="110" y="20" width="40" height="20" stroke={color} strokeWidth="1" fill="none" />
      <rect x="165" y="20" width="35" height="20" stroke={color} strokeWidth="1" fill="none" />

      {/* Connecting arrows */}
      <line x1="40" y1="30" x2="55" y2="30" stroke={color} strokeWidth="1" />
      <polygon points="52,27 55,30 52,33" fill={color} />

      <line x1="95" y1="30" x2="110" y2="30" stroke={color} strokeWidth="1" />
      <polygon points="107,27 110,30 107,33" fill={color} />

      <line x1="150" y1="30" x2="165" y2="30" stroke={color} strokeWidth="1" />
      <polygon points="162,27 165,30 162,33" fill={color} />

      {/* Labels */}
      <text x="20" y="33" fill="#64748b" fontSize="6" textAnchor="middle" fontFamily="monospace">H₀</text>
      <text x="75" y="33" fill="#64748b" fontSize="6" textAnchor="middle" fontFamily="monospace">H₁</text>
      <text x="130" y="33" fill="#64748b" fontSize="6" textAnchor="middle" fontFamily="monospace">H₂</text>
      <text x="183" y="33" fill="#64748b" fontSize="6" textAnchor="middle" fontFamily="monospace">Hₙ</text>

      {/* Chain indicator */}
      <text x="100" y="55" fill="#64748b" fontSize="5" textAnchor="middle" fontFamily="monospace">
        SHA-256 LINKED
      </text>
    </svg>
  );
}

export function ECDSACard() {
  return (
    <div className="signature-notary-card group">
      <div className="p-6 border border-slate-800 bg-slate-900/80 transition-all duration-300 group-hover:border-amber-800">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          <div className="w-12 h-12 bg-amber-950/50 border border-amber-900/50 flex items-center justify-center flex-shrink-0">
            <Lock size={20} className="text-amber-500" />
          </div>
          <div>
            <h3 className="text-white font-semibold mb-1">ECDSA P-256 Signing</h3>
            <p className="text-slate-500 text-sm font-mono">Cloud KMS Managed</p>
          </div>
        </div>

        {/* Expandable content - CSS controlled */}
        <div className="overflow-hidden transition-all duration-300 max-h-0 group-hover:max-h-48 opacity-0 group-hover:opacity-100">
          <div className="pt-4 border-t border-slate-800">
            {/* Hash chain diagram */}
            <div className="mb-4 p-3 bg-slate-950 border border-slate-800">
              <HashChainDiagram color="#0891b2" />
            </div>

            {/* Bullet points */}
            <ul className="space-y-2 text-sm">
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-amber-500 mt-2 flex-shrink-0" />
                <span>Asymmetric key pairs stored in hardware security modules</span>
              </li>
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-amber-500 mt-2 flex-shrink-0" />
                <span>Signatures verifiable for 7+ years post-creation</span>
              </li>
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-amber-500 mt-2 flex-shrink-0" />
                <span>Public verification exposes zero underlying PII</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export function WORMCard() {
  return (
    <div className="signature-notary-card group">
      <div className="p-6 border border-slate-800 bg-slate-900/80 transition-all duration-300 group-hover:border-emerald-800">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          <div className="w-12 h-12 bg-emerald-950/50 border border-emerald-900/50 flex items-center justify-center flex-shrink-0">
            <Database size={20} className="text-emerald-500" />
          </div>
          <div>
            <h3 className="text-white font-semibold mb-1">WORM Retention</h3>
            <p className="text-slate-500 text-sm font-mono">7-Year Immutable</p>
          </div>
        </div>

        {/* Expandable content - CSS controlled */}
        <div className="overflow-hidden transition-all duration-300 max-h-0 group-hover:max-h-48 opacity-0 group-hover:opacity-100">
          <div className="pt-4 border-t border-slate-800">
            {/* WORM diagram */}
            <div className="mb-4 p-3 bg-slate-950 border border-slate-800">
              <div className="flex items-center justify-between text-xs font-mono">
                <div className="text-slate-600">WRITE</div>
                <div className="flex-1 mx-4 border-t border-dashed border-slate-700" />
                <div className="text-emerald-500">LOCKED</div>
                <div className="flex-1 mx-4 border-t border-slate-700" />
                <div className="text-slate-600">+7 YEARS</div>
              </div>
            </div>

            {/* Bullet points */}
            <ul className="space-y-2 text-sm">
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-emerald-500 mt-2 flex-shrink-0" />
                <span>Write-once storage prevents retroactive modification</span>
              </li>
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-emerald-500 mt-2 flex-shrink-0" />
                <span>Legal hold support for regulatory examinations</span>
              </li>
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-emerald-500 mt-2 flex-shrink-0" />
                <span>Administrators cannot delete retention-locked records</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export function HashChainCard() {
  return (
    <div className="signature-notary-card group">
      <div className="p-6 border border-slate-800 bg-slate-900/80 transition-all duration-300 group-hover:border-blue-800">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          <div className="w-12 h-12 bg-blue-950/50 border border-blue-900/50 flex items-center justify-center flex-shrink-0">
            <Shield size={20} className="text-blue-500" />
          </div>
          <div>
            <h3 className="text-white font-semibold mb-1">SHA-256 Hash Chain</h3>
            <p className="text-slate-500 text-sm font-mono">Per-Batch Linking</p>
          </div>
        </div>

        {/* Expandable content - CSS controlled */}
        <div className="overflow-hidden transition-all duration-300 max-h-0 group-hover:max-h-48 opacity-0 group-hover:opacity-100">
          <div className="pt-4 border-t border-slate-800">
            {/* Hash chain diagram */}
            <div className="mb-4 p-3 bg-slate-950 border border-slate-800">
              <HashChainDiagram color="#3b82f6" />
            </div>

            {/* Bullet points */}
            <ul className="space-y-2 text-sm">
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-blue-500 mt-2 flex-shrink-0" />
                <span>Each record hash includes previous record hash</span>
              </li>
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-blue-500 mt-2 flex-shrink-0" />
                <span>Single bit modification breaks entire chain</span>
              </li>
              <li className="flex items-start gap-2 text-slate-400">
                <span className="w-1 h-1 bg-blue-500 mt-2 flex-shrink-0" />
                <span>Chain root anchored to external immutable storage</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SignatureNotaryVisualizer() {
  return (
    <div className="grid md:grid-cols-3 gap-6">
      <ECDSACard />
      <HashChainCard />
      <WORMCard />
    </div>
  );
}
