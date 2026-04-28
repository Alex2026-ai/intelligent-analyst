'use client';

import React from 'react';
import { CheckCircle, AlertTriangle, Loader2, Clock, FileText, ChevronRight, History, StopCircle } from 'lucide-react';

/**
 * AnalysisHome — Minimal landing page for Analysis tab
 * Shows system status, recent batches preview, and getting started guidance
 * No chat UI, no command router — just read-only status cards
 */
export default function AnalysisHome({
  batches = [],
  batchesLoading = false,
  selectedBatch = null,
  onSelectBatch,
  onNavigateToHistory,
  isDemoMode = false
}) {
  // Get top 5 most recent batches
  const recentBatches = Array.isArray(batches) ? batches.slice(0, 5) : [];

  const formatTimestamp = (ts) => {
    if (!ts) return '—';
    try {
      const date = new Date(ts);
      return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return ts;
    }
  };

  const getStatusBadge = (status) => {
    if (status === 'completed') {
      return (
        <span className="inline-flex items-center gap-1 text-emerald-400 text-xs">
          <CheckCircle size={12} />
          Completed
        </span>
      );
    }
    if (status === 'failed') {
      return (
        <span className="inline-flex items-center gap-1 text-red-400 text-xs">
          <AlertTriangle size={12} />
          Failed
        </span>
      );
    }
    if (status === 'aborted') {
      return (
        <span className="inline-flex items-center gap-1 text-orange-400 text-xs">
          <StopCircle size={12} />
          Aborted
        </span>
      );
    }
    if (status === 'queued') {
      return (
        <span className="inline-flex items-center gap-1 text-blue-400 text-xs">
          <Clock size={12} />
          Queued
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-amber-400 text-xs">
        <Loader2 size={12} className="animate-spin" />
        Processing
      </span>
    );
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Page Header */}
      <div className="mb-8">
        <span className="inline-flex items-center gap-2 px-3 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-widest border-cyan-500/20 bg-cyan-950/30 text-cyan-400">
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
          Analysis
        </span>
        <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">
          Intelligent Analyst
        </h2>
        <p className="text-slate-400 max-w-3xl text-lg font-light leading-relaxed">
          Entity resolution and compliance analysis dashboard.
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* System Status Card */}
        <div className="bg-[#0B0F19] border border-slate-800 p-6">
          <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-4 flex items-center gap-2">
            <CheckCircle size={14} />
            System Status
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-sm">Service</span>
              <span className="text-emerald-400 text-sm flex items-center gap-1">
                <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
                {isDemoMode ? 'Demo Mode' : 'Online'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-sm">Frontend</span>
              <span className="text-slate-300 text-sm font-mono">v8.2.2</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 text-sm">API</span>
              <span className={isDemoMode ? 'text-amber-400 text-sm' : 'text-emerald-400 text-sm'}>
                {isDemoMode ? 'Not connected' : 'Operational'}
              </span>
            </div>
            {isDemoMode && (
              <div className="mt-4 pt-4 border-t border-slate-800">
                <p className="text-amber-400 text-xs flex items-center gap-2">
                  <AlertTriangle size={12} />
                  Sample data only. No backend calls.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Recent Batches Card */}
        <div className="lg:col-span-2 bg-[#0B0F19] border border-slate-800">
          <div className="flex items-center justify-between p-4 border-b border-slate-800">
            <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest flex items-center gap-2">
              <Clock size={14} />
              Recent Batches
            </h3>
            {recentBatches.length > 0 && (
              <button
                onClick={onNavigateToHistory}
                className="text-[10px] font-mono text-slate-500 hover:text-cyan-400 transition-colors flex items-center gap-1"
              >
                View all in History
                <ChevronRight size={12} />
              </button>
            )}
          </div>

          {batchesLoading ? (
            <div className="p-8 text-center">
              <Loader2 className="mx-auto text-cyan-400 animate-spin mb-2" size={24} />
              <p className="text-slate-500 text-sm">Loading batches...</p>
            </div>
          ) : recentBatches.length === 0 ? (
            <div className="p-8 text-center">
              <FileText className="mx-auto text-slate-600 mb-2" size={24} />
              <p className="text-slate-500 text-sm">No batches yet</p>
              <p className="text-slate-600 text-xs mt-1">Upload a file to get started</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-800/50">
              {recentBatches.map((batch) => (
                <button
                  key={batch.trace_id}
                  onClick={() => onSelectBatch && onSelectBatch(batch)}
                  className="w-full flex items-center justify-between p-4 hover:bg-slate-800/30 transition-colors text-left group"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <code className="text-cyan-400 text-xs font-mono">
                        {(batch.trace_id || '').slice(0, 12)}
                      </code>
                      <span className="text-slate-300 text-sm truncate">
                        {batch.filename || 'Untitled'}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 mt-1">
                      <span className="text-slate-500 text-xs">
                        {formatTimestamp(batch.timestamp)}
                      </span>
                      <span className="text-slate-500 text-xs">
                        {batch.total || batch.total_records || 0} records
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {getStatusBadge(batch.status)}
                    <ChevronRight size={14} className="text-slate-600 group-hover:text-cyan-400 transition-colors" />
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Getting Started Card */}
      <div className="bg-[#0B0F19] border border-slate-800 p-6">
        <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-4 flex items-center gap-2">
          <History size={14} />
          Getting Started
        </h3>
        <p className="text-slate-400 text-sm leading-relaxed">
          {selectedBatch ? (
            <>
              Currently viewing batch: <code className="text-cyan-400 font-mono">{selectedBatch.trace_id?.slice(0, 12)}</code>
              {' — '}
              <button onClick={onNavigateToHistory} className="text-cyan-400 hover:underline">
                View in History
              </button>
            </>
          ) : (
            <>
              No batch selected. Select a batch in{' '}
              <button onClick={onNavigateToHistory} className="text-cyan-400 hover:underline">
                History
              </button>
              {' '}to view analysis details and download evidence packs.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
