import React, { useState } from 'react';
import { Shield, Clock, Lock, Hash, CheckCircle } from 'lucide-react';

/**
 * EvidencePackPreview
 *
 * Static forensic receipt preview with tooltip micro-explainers.
 * Uses CSS-only tooltips, no external libraries.
 */

// Tooltip wrapper component
function ExplainerTooltip({ children, explanation }) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-slate-950 border border-slate-700 shadow-xl">
          <div className="text-xs text-slate-300 leading-relaxed">
            {explanation}
          </div>
          {/* Arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-950 border-r border-b border-slate-700 transform rotate-45 -mt-1" />
        </div>
      )}
    </div>
  );
}

// Sample evidence data
const sampleEvidence = {
  trace_id: 'BATCH-A7F2E9C1',
  timestamp: '2026-02-17T10:30:00.000Z',
  hash_chain_root: 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  signature: {
    algorithm: 'ECDSA P-256',
    status: 'VALID',
    key_id: 'golden-signing-prod',
  },
  retention: {
    policy: 'WORM',
    until: '2033-02-17',
  },
  records: {
    total: 1000,
    resolved: 998,
    pending_review: 2,
  },
};

export default function EvidencePackPreview() {
  return (
    <div className="terminal-frame p-6">
      <div className="terminal-header mb-6">
        Evidence Pack Preview
      </div>

      {/* Receipt Content */}
      <div className="space-y-4">
        {/* Trace ID */}
        <div className="flex items-center justify-between p-3 bg-slate-900/50 border border-slate-800">
          <div className="flex items-center gap-3">
            <Shield size={14} className="text-amber-500" />
            <span className="text-slate-500 text-sm font-mono">TRACE_ID</span>
          </div>
          <span className="font-mono text-amber-400 text-sm">{sampleEvidence.trace_id}</span>
        </div>

        {/* Timestamp with tooltip */}
        <div className="flex items-center justify-between p-3 bg-slate-900/50 border border-slate-800">
          <div className="flex items-center gap-3">
            <Clock size={14} className="text-slate-500" />
            <ExplainerTooltip explanation="ISO 8601 timestamp recorded at batch completion. This timestamp is cryptographically bound to the signature and cannot be modified post-creation.">
              <span className="text-slate-500 text-sm font-mono border-b border-dashed border-slate-600 cursor-help">
                TIMESTAMP
              </span>
            </ExplainerTooltip>
          </div>
          <span className="font-mono text-slate-300 text-sm">
            {new Date(sampleEvidence.timestamp).toISOString()}
          </span>
        </div>

        {/* Hash with tooltip */}
        <div className="p-3 bg-slate-900/50 border border-slate-800">
          <div className="flex items-center gap-3 mb-2">
            <Hash size={14} className="text-blue-500" />
            <ExplainerTooltip explanation="SHA-256 hash chain root computed by linking all record hashes sequentially. Any modification to any record would change this root value, enabling instant tamper detection.">
              <span className="text-slate-500 text-sm font-mono border-b border-dashed border-slate-600 cursor-help">
                HASH_CHAIN_ROOT
              </span>
            </ExplainerTooltip>
          </div>
          <div className="font-mono text-xs text-slate-400 break-all bg-slate-950 p-2 border border-slate-800">
            {sampleEvidence.hash_chain_root}
          </div>
        </div>

        {/* Signature with tooltip */}
        <div className="flex items-center justify-between p-3 bg-slate-900/50 border border-slate-800">
          <div className="flex items-center gap-3">
            <Lock size={14} className="text-emerald-500" />
            <ExplainerTooltip explanation="ECDSA P-256 digital signature created using Cloud KMS hardware-backed keys. Verifiable for 7+ years. Proves the batch was created by an authorized system and has not been tampered with.">
              <span className="text-slate-500 text-sm font-mono border-b border-dashed border-slate-600 cursor-help">
                SIGNATURE
              </span>
            </ExplainerTooltip>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle size={14} className="text-emerald-500" />
            <span className="font-mono text-emerald-400 text-sm">{sampleEvidence.signature.status}</span>
          </div>
        </div>

        {/* Signature details */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-slate-900/50 border border-slate-800">
            <div className="text-slate-600 text-xs font-mono mb-1">ALGORITHM</div>
            <div className="font-mono text-sm text-slate-300">{sampleEvidence.signature.algorithm}</div>
          </div>
          <div className="p-3 bg-slate-900/50 border border-slate-800">
            <div className="text-slate-600 text-xs font-mono mb-1">KEY_ID</div>
            <div className="font-mono text-sm text-slate-300">{sampleEvidence.signature.key_id}</div>
          </div>
        </div>

        {/* Retention */}
        <div className="flex items-center justify-between p-3 border border-emerald-900/50 bg-emerald-950/20">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 bg-emerald-500" style={{ boxShadow: '0 0 8px #10b981' }} />
            <span className="text-slate-300 text-sm font-mono">WORM_RETENTION</span>
          </div>
          <span className="font-mono text-emerald-400 text-sm">Until {sampleEvidence.retention.until}</span>
        </div>

        {/* Record counts */}
        <div className="grid grid-cols-3 gap-3 pt-4 border-t border-slate-800">
          <div className="text-center">
            <div className="font-mono text-lg text-white">{sampleEvidence.records.total.toLocaleString()}</div>
            <div className="text-slate-600 text-xs font-mono">TOTAL</div>
          </div>
          <div className="text-center">
            <div className="font-mono text-lg text-emerald-400">{sampleEvidence.records.resolved.toLocaleString()}</div>
            <div className="text-slate-600 text-xs font-mono">RESOLVED</div>
          </div>
          <div className="text-center">
            <div className="font-mono text-lg text-amber-400">{sampleEvidence.records.pending_review}</div>
            <div className="text-slate-600 text-xs font-mono">REVIEW</div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-6 pt-4 border-t border-slate-800 text-center">
        <p className="text-xs font-mono text-slate-600">
          Hover underlined fields for detailed explanations
        </p>
      </div>
    </div>
  );
}
