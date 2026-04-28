'use client';

import React, { useState, useEffect } from 'react';
import {
  BrainCircuit, CheckCircle, XCircle, AlertTriangle, Loader2,
  FileText, Hash, Shield, Clock, Users, Zap, Cpu
} from "lucide-react";
import { resolveShareLink } from './api/client';

/**
 * SharedBatchView - Read-only view for shared batch links
 * Accessed via /s/{share_token}
 */

const COLORS = {
  cyan: '#22d3ee',
  violet: '#a78bfa',
  amber: '#fbbf24',
  red: '#f87171',
  emerald: '#34d399',
  slate: '#64748b'
};

export default function SharedBatchView({ shareToken }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [batchData, setBatchData] = useState(null);

  useEffect(() => {
    const loadSharedBatch = async () => {
      setLoading(true);
      setError(null);

      try {
        const result = await resolveShareLink(shareToken);

        if (!result.ok) {
          // Handle specific error cases
          if (result.error?.includes('410') || result.error?.includes('expired') || result.error?.includes('revoked')) {
            setError('This share link has expired or been revoked.');
          } else if (result.error?.includes('404')) {
            setError('Share link not found.');
          } else {
            setError(result.error || 'Failed to load shared batch');
          }
          return;
        }

        setBatchData(result.data);
      } catch (err) {
        setError(err.message || 'Failed to load shared batch');
      } finally {
        setLoading(false);
      }
    };

    if (shareToken) {
      loadSharedBatch();
    }
  }, [shareToken]);

  if (loading) {
    return (
      <div style={{ backgroundColor: '#0b1220', color: '#e2e8f0', minHeight: '100vh' }} className="font-sans antialiased">
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center">
            <Loader2 className="mx-auto text-cyan-500 animate-spin mb-4" size={48} />
            <p className="text-gray-200">Loading shared batch...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ backgroundColor: '#0b1220', color: '#e2e8f0', minHeight: '100vh' }} className="font-sans antialiased">
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center max-w-md px-6">
            <AlertTriangle className="mx-auto text-amber-500 mb-4" size={48} />
            <h2 className="text-xl font-semibold text-[#f1f5f9] mb-2">Link Expired or Revoked</h2>
            <p className="text-gray-200 mb-6">{error}</p>
            <a
              href="/"
              className="inline-flex items-center gap-2 px-4 py-2 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded hover:bg-cyan-500/20 transition-colors text-sm font-mono uppercase"
            >
              Go to Dashboard
            </a>
          </div>
        </div>
      </div>
    );
  }

  const batch = batchData?.batch;
  const events = batchData?.events || [];
  const shareInfo = batchData?.share_info;
  const stats = batch?.stats || {};
  const counts = batch?.counts || {};
  const hasNewCounts = Object.keys(counts).length > 0;

  // Calculate layer breakdown (counts-aware: supports both new counts and legacy stats)
  const layerData = [
    { name: 'L0: Garbage', count: hasNewCounts ? (counts.l0_quarantined || counts.l0 || 0) : (stats.layer_0_garbage || 0), color: COLORS.slate, icon: Shield },
    { name: 'L1: Deterministic', count: hasNewCounts ? (counts.l1_resolved || counts.l1 || 0) : ((stats.layer_1_exact || 0) + (stats.layer_1_norm || 0)), color: COLORS.cyan, icon: Zap },
    { name: 'L2: Vector', count: hasNewCounts ? (counts.l2_resolved || counts.l2 || 0) : (stats.layer_2_vector || 0), color: COLORS.violet, icon: Cpu },
    { name: 'L3: LLM', count: hasNewCounts ? (counts.l3_resolved || counts.l3 || 0) : (stats.layer_3_llm || 0), color: COLORS.amber, icon: BrainCircuit },
    { name: 'L4: Human Review', count: hasNewCounts ? (counts.l4_flagged || counts.l4 || 0) : (stats.layer_4_human || 0), color: COLORS.red, icon: Users },
  ];

  return (
    <div style={{ backgroundColor: '#0b1220', color: '#e2e8f0', minHeight: '100vh' }} className="font-sans antialiased">
      {/* Header */}
      <nav className="border-b border-[#1e293b] bg-[#0B1220]/95">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-cyan-950 to-slate-900 border border-[#1e293b] flex items-center justify-center">
              <BrainCircuit className="text-cyan-500" size={16} />
            </div>
            <div className="leading-tight text-left">
              <div className="font-semibold text-slate-100 tracking-tight text-sm uppercase">Intelligent Analyst</div>
              <div className="text-[9px] text-cyan-500/70 font-mono tracking-widest uppercase">Shared View</div>
            </div>
          </div>
        </div>
      </nav>

      {/* Read-only Banner */}
      <div className="bg-violet-500/10 border-b border-violet-500/30 py-2 px-6">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
          <Shield size={14} className="text-violet-400" />
          <span className="text-violet-400 text-xs font-mono uppercase tracking-wider">
            Read-only shared view
          </span>
          {shareInfo?.expires_at && (
            <span className="text-gray-300 text-xs font-mono ml-auto flex items-center gap-1">
              <Clock size={12} />
              Expires: {new Date(shareInfo.expires_at).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>

      <main className="py-8 max-w-5xl mx-auto px-6">
        {/* Batch Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-widest border-cyan-500/20 bg-cyan-950/30 text-cyan-400">
              <span className="w-1.5 h-1.5 rounded-full bg-current" />
              Batch Results
            </span>
          </div>
          <h1 className="text-2xl font-semibold text-[#f1f5f9] uppercase tracking-tight mb-2">
            {batch?.filename || 'Batch Details'}
          </h1>
          <div className="flex items-center gap-4 text-sm text-gray-200">
            <span className="flex items-center gap-1">
              <FileText size={14} />
              {batch?.trace_id}
            </span>
            <span>
              {batch?.timestamp ? new Date(batch.timestamp).toLocaleString() : ''}
            </span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-[#0f172a] border border-slate-700/50 p-4">
            <div className="text-2xl text-[#f1f5f9] font-semibold font-mono">{batch?.total || 0}</div>
            <div className="text-[10px] font-mono text-gray-300 uppercase tracking-widest">Total Records</div>
          </div>
          <div className="bg-[#0f172a] border border-slate-700/50 p-4">
            <div className="text-2xl text-cyan-400 font-semibold font-mono">{batch?.auto_resolved_pct?.toFixed(1) || 0}%</div>
            <div className="text-[10px] font-mono text-gray-300 uppercase tracking-widest">Auto-Resolved</div>
          </div>
          <div className="bg-[#0f172a] border border-slate-700/50 p-4">
            <div className="text-2xl text-amber-400 font-semibold font-mono">{batch?.flagged_count || 0}</div>
            <div className="text-[10px] font-mono text-gray-300 uppercase tracking-widest">Flagged</div>
          </div>
          <div className="bg-[#0f172a] border border-slate-700/50 p-4">
            <div className="text-2xl text-[#cbd5e1] font-semibold font-mono">{((batch?.duration_ms || 0) / 1000).toFixed(1)}s</div>
            <div className="text-[10px] font-mono text-gray-300 uppercase tracking-widest">Duration</div>
          </div>
        </div>

        {/* Layer Breakdown */}
        <div className="bg-[#0f172a] border border-slate-700/50 p-6 mb-8">
          <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-4 flex items-center gap-2">
            <Hash size={12} /> Layer Breakdown
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {layerData.map((layer) => (
              <div key={layer.name} className="text-center">
                <layer.icon size={20} className="mx-auto mb-2" style={{ color: layer.color }} />
                <div className="text-xl font-semibold font-mono" style={{ color: layer.color }}>{layer.count}</div>
                <div className="text-[9px] font-mono text-gray-300 uppercase tracking-widest">{layer.name}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Results Table */}
        <div className="bg-[#0f172a] border border-slate-700/50">
          <div className="p-4 border-b border-slate-700/50">
            <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">
              Resolution Results ({events.length} records)
            </h3>
          </div>
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
            <table className="w-full text-left font-mono text-[11px]">
              <thead className="sticky top-0 bg-[#0b1220]">
                <tr className="text-gray-300 border-b border-slate-700/50">
                  <th className="p-3">#</th>
                  <th className="p-3">Original</th>
                  <th className="p-3">Resolved</th>
                  <th className="p-3">Layer</th>
                  <th className="p-3 text-right">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e293b]">
                {events.slice(0, 100).map((event, i) => (
                  <tr key={i} className="hover:bg-[#0f1a33]">
                    <td className="p-3 text-gray-300">{event.row_index ?? i}</td>
                    <td className="p-3 text-[#f1f5f9] max-w-[200px] truncate" title={event.original || event.company_raw}>
                      {event.original || event.company_raw || '-'}
                    </td>
                    <td className="p-3 text-cyan-400 max-w-[200px] truncate" title={event.resolved || event.canonical_name}>
                      {event.resolved || event.canonical_name || '-'}
                    </td>
                    <td className="p-3">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] ${
                        event.layer === 'L4_HUMAN' ? 'bg-red-500/20 text-red-400' :
                        event.layer === 'L3_LLM' ? 'bg-amber-500/20 text-amber-400' :
                        event.layer === 'L2_VECTOR' ? 'bg-violet-500/20 text-violet-400' :
                        event.layer?.startsWith('L1') ? 'bg-cyan-500/20 text-cyan-400' :
                        'bg-slate-500/20 text-gray-200'
                      }`}>
                        {event.layer || `L${event.layer_used}`}
                      </span>
                    </td>
                    <td className="p-3 text-right text-gray-200">
                      {((event.confidence ?? 0) * 100).toFixed(0)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {events.length > 100 && (
              <div className="p-3 text-center text-gray-300 text-xs border-t border-slate-700/50">
                Showing first 100 of {events.length} records
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-[#060c18] border-t border-slate-700/50 py-8 px-6 mt-12">
        <div className="max-w-5xl mx-auto flex justify-between items-center">
          <p className="text-[10px] font-mono uppercase tracking-widest text-gray-300">
            Intelligent Analyst — Shared View
          </p>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-violet-500 rounded-full" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-gray-300">Read-only</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
