'use client';

import React from 'react';
import { FileText, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

/**
 * AuditLog — Read-only audit log viewer
 *
 * Props:
 * - batches: array of batch objects from existing data source
 * - loading: boolean indicating if data is loading
 */
export default function AuditLog({ batches = [], loading = false }) {
  // Ensure batches is always a safe array
  const safeBatches = Array.isArray(batches) ? batches : [];

  // Transform batch data into audit log entries
  // Maps existing batch records to the required audit log format
  const auditEntries = React.useMemo(() => {
    if (safeBatches.length === 0) return [];

    const entries = [];

    safeBatches.forEach((batch) => {
      // Generate audit entries from batch lifecycle
      const timestamp = batch.timestamp || batch.created_at || new Date().toISOString();
      const traceId = batch.trace_id || 'unknown';
      const actor = batch.user_email || batch.actor || 'system';

      // Entry: batch_started
      entries.push({
        id: `${traceId}-started`,
        timestamp,
        actor,
        action: 'batch_started',
        target: traceId,
        context: batch.config_version || 'v1.0',
        result: 'success'
      });

      // Entry: layer_executed (if stats available)
      if (batch.stats) {
        const layerCount = (batch.stats.layer_1_exact || 0) +
                          (batch.stats.layer_1_norm || 0) +
                          (batch.stats.layer_2_vector || 0) +
                          (batch.stats.layer_3_llm || 0);
        if (layerCount > 0) {
          entries.push({
            id: `${traceId}-layers`,
            timestamp,
            actor: 'system',
            action: 'layer_executed',
            target: traceId,
            context: `L1:${(batch.stats.layer_1_exact||0)+(batch.stats.layer_1_norm||0)} L2:${batch.stats.layer_2_vector||0} L3:${batch.stats.layer_3_llm||0}`,
            result: 'success'
          });
        }
      }

      // Entry: evidence_generated (if batch completed)
      if (batch.status === 'completed') {
        entries.push({
          id: `${traceId}-evidence`,
          timestamp,
          actor: 'system',
          action: 'evidence_generated',
          target: traceId,
          context: `${batch.total || batch.total_records || 0} records`,
          result: 'success'
        });
      }

      // Entry: tls_generated (EU AI Act compliance - Transparency & Limitations Statement)
      if (batch.transparency_statement) {
        entries.push({
          id: `${traceId}-tls`,
          timestamp: batch.transparency_statement.timestamp || timestamp,
          actor: 'service',
          action: 'tls_generated',
          target: traceId,
          context: `${batch.transparency_statement.template_id || 'TLS_v1'} · SHA256:${(batch.transparency_statement.hash || '').slice(0, 12)}`,
          result: 'success'
        });
      }

      // Entry: decision_path_summary (EU AI Act compliance - Decision Path Classification)
      if (batch.decision_path_summary) {
        const dps = batch.decision_path_summary;
        entries.push({
          id: `${traceId}-dps`,
          timestamp,
          actor: 'service',
          action: 'decision_path_summary',
          target: traceId,
          context: `L1:${dps.L1_DETERMINISTIC||0} L2:${dps.L2_VECTOR_FUZZY||0} L3:${dps.L3_LLM||0} L4:${dps.L4_HUMAN_REVIEW_REQUIRED||0}`,
          result: 'success'
        });
      }

      // Entry: llm_budget_summary (Cost-first L3 budget gating)
      if (batch.llm_budget_summary) {
        const lbs = batch.llm_budget_summary;
        const exhaustedFlag = lbs.budget_exhausted ? ' EXHAUSTED' : '';
        entries.push({
          id: `${traceId}-lbs`,
          timestamp,
          actor: 'service',
          action: 'llm_budget_summary',
          target: traceId,
          context: `Budget: $${lbs.budget_usd} | Spent: $${lbs.spent_usd?.toFixed(4)||0} | Calls: ${lbs.calls||0}${exhaustedFlag}`,
          result: lbs.budget_exhausted ? 'warning' : 'success'
        });
      }

      // Entry: upload (original file)
      if (batch.filename) {
        entries.push({
          id: `${traceId}-upload`,
          timestamp,
          actor,
          action: 'upload',
          target: traceId,
          context: batch.filename,
          result: batch.status === 'failed' ? 'failure' : 'success'
        });
      }
    });

    // Sort by timestamp descending
    return entries.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }, [safeBatches]);

  const formatTimestamp = (ts) => {
    try {
      return new Date(ts).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
    } catch {
      return ts;
    }
  };

  const getActionBadge = (action) => {
    const styles = {
      upload: 'bg-violet-500/10 text-violet-400 border-violet-500/30',
      batch_started: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
      layer_executed: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
      evidence_generated: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      analysis_viewed: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
      // EU AI Act compliance events
      tls_generated: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
      decision_path_summary: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
      // LLM budget tracking
      llm_budget_summary: 'bg-amber-500/10 text-amber-400 border-amber-500/30'
    };
    return styles[action] || styles.analysis_viewed;
  };

  const getResultIcon = (result) => {
    if (result === 'success') {
      return <CheckCircle size={14} className="text-emerald-400" />;
    } else if (result === 'failure') {
      return <XCircle size={14} className="text-red-400" />;
    }
    return <AlertTriangle size={14} className="text-amber-400" />;
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Section Header */}
      <div className="mb-8">
        <span className="inline-flex items-center gap-2 px-3 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-widest border-amber-500/20 bg-amber-950/30 text-amber-400">
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
          Compliance
        </span>
        <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">Audit Log</h2>
        <p className="text-slate-500 text-sm font-mono uppercase tracking-widest">
          Read-only · Immutable · Tenant-scoped
        </p>
      </div>

      {/* Audit Table Panel */}
      <div className="bg-[#0B0F19] border border-slate-800">
        <div className="flex items-center justify-between p-4 border-b border-slate-800">
          <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest flex items-center gap-2">
            <FileText size={14} />
            Event Log
          </h3>
          <span className="text-[10px] font-mono text-slate-500">
            {auditEntries.length} entries
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-[10px] font-mono text-slate-500 uppercase tracking-wider border-b border-slate-800">
                <th className="text-left p-4">Timestamp (UTC)</th>
                <th className="text-left p-4">Actor</th>
                <th className="text-left p-4">Action</th>
                <th className="text-left p-4">Target</th>
                <th className="text-left p-4">Context</th>
                <th className="text-center p-4">Result</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500">
                    <div className="flex items-center justify-center gap-2">
                      <div className="w-4 h-4 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
                      Loading audit log...
                    </div>
                  </td>
                </tr>
              ) : auditEntries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500">
                    <FileText className="mx-auto mb-2 text-slate-600" size={24} />
                    No audit entries available
                  </td>
                </tr>
              ) : (
                auditEntries.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors"
                  >
                    <td className="p-4 text-slate-400 text-xs font-mono whitespace-nowrap">
                      {formatTimestamp(entry.timestamp)}
                    </td>
                    <td className="p-4 text-slate-300 text-sm truncate max-w-[150px]" title={entry.actor}>
                      {entry.actor}
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex px-2 py-0.5 text-[10px] font-mono uppercase border ${getActionBadge(entry.action)}`}>
                        {entry.action.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="p-4">
                      <code className="text-cyan-400 text-xs font-mono">
                        {entry.target?.slice(0, 16)}
                      </code>
                    </td>
                    <td className="p-4 text-slate-400 text-xs truncate max-w-[200px]" title={entry.context}>
                      {entry.context}
                    </td>
                    <td className="p-4 text-center">
                      {getResultIcon(entry.result)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
