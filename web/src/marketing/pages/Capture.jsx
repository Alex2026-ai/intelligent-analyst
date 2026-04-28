import React from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, Shield, Lock, FileCheck, Database, Clock } from 'lucide-react';

// Fixture imports
import batchData from '../fixtures/captureBatch.json';
import receiptData from '../fixtures/captureReceipt.json';
import verifyData from '../fixtures/captureVerify.json';

/**
 * Capture pages for marketing asset generation.
 * These render real UI components with fixture data.
 * Used by Playwright to generate WebP/PNG assets.
 *
 * Routes:
 *   /__capture/batch   → Batch Overview
 *   /__capture/receipt → Forensic Receipt
 *   /__capture/verify  → Public Verification
 */

function BatchOverviewCapture() {
  const data = batchData;

  return (
    <div id="capture-container" className="capture-mode bg-slate-950 p-6 w-[800px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="text-slate-400 text-xs font-mono mb-1">BATCH</div>
          <div className="text-white text-2xl font-bold">{data.trace_id}</div>
        </div>
        <div className="px-4 py-2 bg-emerald-950 border border-emerald-900 rounded">
          <span className="text-emerald-400 font-semibold text-sm">COMPLETED</span>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-slate-900 border border-slate-800 p-4 rounded">
          <div className="text-slate-500 text-xs font-mono mb-1">TOTAL ROWS</div>
          <div className="text-white text-2xl font-bold">{data.total_rows.toLocaleString()}</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded">
          <div className="text-slate-500 text-xs font-mono mb-1">RESOLVED</div>
          <div className="text-cyan-400 text-2xl font-bold">
            {(data.total_rows - data.counts.l4_human).toLocaleString()}
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded">
          <div className="text-slate-500 text-xs font-mono mb-1">L4 REVIEW</div>
          <div className="text-amber-400 text-2xl font-bold">{data.counts.l4_human.toLocaleString()}</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded">
          <div className="text-slate-500 text-xs font-mono mb-1">SIGNED</div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="text-emerald-500" size={24} />
            <span className="text-emerald-400 text-lg font-semibold">Valid</span>
          </div>
        </div>
      </div>

      {/* Layer distribution */}
      <div className="bg-slate-900 border border-slate-800 p-4 rounded mb-6">
        <div className="text-slate-400 text-xs font-mono mb-4">LAYER DISTRIBUTION</div>
        <div className="space-y-3">
          {[
            { layer: 'L1', name: 'Deterministic', pct: data.percentages.l1, color: 'bg-cyan-500' },
            { layer: 'L2', name: 'Vector Match', pct: data.percentages.l2, color: 'bg-cyan-600' },
            { layer: 'L3', name: 'LLM Adjudication', pct: data.percentages.l3, color: 'bg-cyan-700' },
            { layer: 'L4', name: 'Human Review', pct: data.percentages.l4, color: 'bg-amber-500' },
          ].map((item) => (
            <div key={item.layer} className="flex items-center gap-3">
              <div className="w-8 text-slate-500 font-mono text-xs">{item.layer}</div>
              <div className="flex-1 h-6 bg-slate-800 rounded overflow-hidden">
                <div
                  className={`h-full ${item.color} rounded`}
                  style={{ width: `${item.pct}%` }}
                />
              </div>
              <div className="w-16 text-right text-slate-400 font-mono text-sm">
                {item.pct.toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer metadata */}
      <div className="grid grid-cols-3 gap-4">
        <div className="flex items-center gap-2 text-slate-500 text-xs">
          <Shield size={14} className="text-cyan-500" />
          <span>Signature: {data.signature.algorithm}</span>
        </div>
        <div className="flex items-center gap-2 text-slate-500 text-xs">
          <Lock size={14} className="text-cyan-500" />
          <span>Hash Chain: {data.hash_chain.algorithm}</span>
        </div>
        <div className="flex items-center gap-2 text-slate-500 text-xs">
          <Database size={14} className="text-cyan-500" />
          <span>Retention: {data.retention.years}Y WORM</span>
        </div>
      </div>
    </div>
  );
}

function ForensicReceiptCapture() {
  const data = receiptData;

  return (
    <div id="capture-container" className="capture-mode bg-slate-950 p-6 w-[800px]">
      <div className="grid grid-cols-2 gap-6">
        {/* Left: JSON blob */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded">
          <div className="text-slate-500 text-xs font-mono mb-3">// Evidence Blob</div>
          <pre className="text-xs font-mono leading-relaxed overflow-hidden">
            <span className="text-purple-400">{'{'}</span>{'\n'}
            <span className="text-slate-400">  "trace_id": </span>
            <span className="text-amber-400">"{data.evidence_blob.trace_id}"</span>,{'\n'}
            <span className="text-slate-400">  "timestamp": </span>
            <span className="text-amber-400">"{data.evidence_blob.timestamp}"</span>,{'\n'}
            <span className="text-slate-400">  "resolution_layer": </span>
            <span className="text-amber-400">"{data.evidence_blob.resolution.layer}"</span>,{'\n'}
            <span className="text-slate-400">  "canonical_match": </span>
            <span className="text-amber-400">"{data.evidence_blob.resolution.canonical_name}"</span>,{'\n'}
            <span className="text-slate-400">  "confidence": </span>
            <span className="text-purple-300">{data.evidence_blob.resolution.confidence}</span>,{'\n'}
            <span className="text-slate-400">  "signature_valid": </span>
            <span className="text-emerald-400">true</span>,{'\n'}
            <span className="text-slate-400">  "hash_chain": </span>
            <span className="text-amber-400">"sha256:9f8e7d..."</span>,{'\n'}
            <span className="text-slate-400">  "anchor_status": </span>
            <span className="text-amber-400">"CONFIRMED"</span>{'\n'}
            <span className="text-purple-400">{'}'}</span>
          </pre>
        </div>

        {/* Right: PDF preview */}
        <div className="bg-white rounded overflow-hidden">
          {/* PDF Header */}
          <div className="bg-slate-900 p-4">
            <div className="text-white font-bold text-sm">FORENSIC EVIDENCE CERTIFICATE</div>
            <div className="text-slate-400 text-xs font-mono">Intelligent Analyst Enterprise</div>
          </div>

          {/* PDF Body */}
          <div className="p-4 text-slate-900">
            <div className="text-xs font-semibold mb-2">Batch Details</div>
            <div className="border-t border-slate-200 pt-2 space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">Trace ID</span>
                <span className="font-mono">{data.certificate.batch_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Records Processed</span>
                <span className="font-mono">{data.certificate.records_processed.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Processing Date</span>
                <span className="font-mono">{data.certificate.processing_date}</span>
              </div>
            </div>

            <div className="text-xs font-semibold mt-4 mb-2">Cryptographic Attestation</div>
            <div className="border-t border-slate-200 pt-2">
              <div className="bg-slate-100 p-3 rounded text-xs space-y-2">
                <div>
                  <div className="text-slate-500">Digital Signature</div>
                  <div className="font-mono text-slate-700">{data.certificate.attestation.signature_algorithm}</div>
                </div>
                <div>
                  <div className="text-slate-500">Hash Chain</div>
                  <div className="font-mono text-slate-700">{data.certificate.attestation.hash_chain}</div>
                </div>
              </div>
            </div>

            {/* Verified stamp */}
            <div className="mt-4 flex justify-end">
              <div className="w-16 h-16 rounded-full bg-emerald-100 border-2 border-emerald-500 flex items-center justify-center">
                <span className="text-emerald-600 text-xs font-bold">VERIFIED</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PublicVerifyCapture() {
  const data = verifyData;

  return (
    <div id="capture-container" className="capture-mode bg-slate-950 p-6 w-[600px]">
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="text-slate-400 text-sm mb-1">Public Verification</div>
          <div className="text-white font-mono text-lg">{data.trace_id}</div>
        </div>

        {/* Status badge */}
        <div className="flex justify-center mb-6">
          <div className="px-8 py-3 bg-emerald-950 border border-emerald-900 rounded">
            <span className="text-emerald-400 font-bold text-xl">VERIFIED</span>
          </div>
        </div>

        {/* Checks */}
        <div className="space-y-3">
          {data.checks.map((check, index) => (
            <div key={index} className="bg-slate-950 border border-slate-800 rounded p-4 flex items-start gap-3">
              <div className="w-6 h-6 bg-emerald-950 rounded-full flex items-center justify-center flex-shrink-0">
                <CheckCircle2 size={14} className="text-emerald-500" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-white font-medium text-sm">{check.name}</span>
                  <span className="text-emerald-400 font-mono text-xs">{check.status}</span>
                </div>
                <div className="text-slate-500 text-xs mt-1">
                  {check.detail} • {check.sub_detail}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Privacy note */}
        <div className="mt-6 pt-4 border-t border-slate-800 text-center">
          <p className="text-slate-500 text-xs">{data.privacy_note}</p>
        </div>
      </div>
    </div>
  );
}

export default function Capture() {
  const { type } = useParams();

  // Capture-mode styles: no animations, fixed dimensions
  const style = `
    .capture-mode * {
      animation: none !important;
      transition: none !important;
    }
  `;

  return (
    <>
      <style>{style}</style>
      {type === 'batch' && <BatchOverviewCapture />}
      {type === 'receipt' && <ForensicReceiptCapture />}
      {type === 'verify' && <PublicVerifyCapture />}
    </>
  );
}
