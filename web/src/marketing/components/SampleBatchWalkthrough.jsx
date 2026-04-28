import React, { useState } from 'react';
import { Upload, Play, CheckCircle, FileText, Download } from 'lucide-react';
import sampleResults from '../fixtures/sample_batch_results.json';

/**
 * SampleBatchWalkthrough
 *
 * Golden Iteration proof widget: Upload → Results preview
 * No real uploads. Deterministic fixture data only.
 * Forensic design system: OLED, sharp corners, IBM Plex Mono.
 *
 * VERIFICATION: All results are verified against production resolution
 * engine on 2026-02-17. See backend/scripts/test_marketing_examples.py
 */
export default function SampleBatchWalkthrough() {
  const [hasRun, setHasRun] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleRunSample = () => {
    setIsProcessing(true);
    // Simulate processing delay (no network call)
    setTimeout(() => {
      setIsProcessing(false);
      setHasRun(true);
    }, 1500);
  };

  const { summary, results, forensic_receipt, batch_id } = sampleResults;

  return (
    <section className="py-20 md:py-28" style={{ backgroundColor: '#05070A' }}>
      <div className="max-w-6xl mx-auto px-6">
        {/* Section Header */}
        <div className="mb-12">
          <div className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-4">
            Verified Demo
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Sample Batch Walkthrough
          </h2>
          <p className="text-lg text-slate-400 max-w-2xl">
            Real inputs verified against production resolution engine.
            Run the sample batch below—results reflect actual system behavior.
          </p>
          <div className="mt-4 inline-flex items-center gap-2 px-3 py-1 border border-emerald-900 bg-emerald-950/30">
            <div className="w-2 h-2 bg-emerald-500 rounded-full" />
            <span className="font-mono text-xs text-emerald-400 uppercase tracking-wider">
              Verified 2026-02-17
            </span>
          </div>
        </div>

        {/* Sample Input Section */}
        <div className="grid lg:grid-cols-2 gap-8 mb-12">
          {/* Upload Box (visual only) */}
          <div className="border border-slate-800 bg-slate-950 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 border border-amber-900 bg-amber-950/30 flex items-center justify-center">
                <Upload size={18} className="text-amber-500" />
              </div>
              <div>
                <div className="font-mono text-sm text-white">Sample Input</div>
                <div className="text-xs text-slate-500">Deterministic fixture data</div>
              </div>
            </div>

            <div className="border border-dashed border-slate-700 p-6 mb-6 text-center">
              <FileText size={32} className="text-slate-600 mx-auto mb-3" />
              <div className="font-mono text-sm text-slate-300 mb-2">
                sample-acme-batch.csv
              </div>
              <div className="text-xs text-slate-500 mb-4">
                10 entity records • sample CSV
              </div>
              <a
                href="/samples/sample-acme-batch.csv"
                download
                className="inline-flex items-center gap-2 text-xs font-mono text-amber-500 hover:text-amber-400 transition-colors"
              >
                <Download size={14} />
                DOWNLOAD SAMPLE
              </a>
            </div>

            <button
              onClick={handleRunSample}
              disabled={isProcessing}
              className="w-full h-12 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-semibold flex items-center justify-center gap-2 transition-colors"
            >
              {isProcessing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  PROCESSING...
                </>
              ) : (
                <>
                  <Play size={16} />
                  RUN SAMPLE
                </>
              )}
            </button>
          </div>

          {/* Processing Summary */}
          <div className="border border-slate-800 bg-slate-950 p-6">
            <div className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-6">
              Processing Summary
            </div>

            {hasRun ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="border border-slate-800 p-4">
                    <div className="font-mono text-2xl text-white mb-1">10</div>
                    <div className="text-xs text-slate-500">Records Processed</div>
                  </div>
                  <div className="border border-slate-800 p-4">
                    <div className="font-mono text-2xl text-emerald-500 mb-1">{summary.auto_resolved_pct}%</div>
                    <div className="text-xs text-slate-500">Auto-Resolved</div>
                  </div>
                  <div className="border border-slate-800 p-4">
                    <div className="font-mono text-2xl text-amber-500 mb-1">{summary.llm_escalations_pct}%</div>
                    <div className="text-xs text-slate-500">LLM Escalations</div>
                  </div>
                  <div className="border border-slate-800 p-4">
                    <div className="font-mono text-2xl text-slate-300 mb-1">{summary.manual_review_pct}%</div>
                    <div className="text-xs text-slate-500">Manual Review</div>
                  </div>
                </div>

                <div className="border border-emerald-900 bg-emerald-950/20 p-4 flex items-center gap-3">
                  <CheckCircle size={20} className="text-emerald-500" />
                  <div>
                    <div className="font-mono text-sm text-emerald-400">Receipt: {summary.receipt_status}</div>
                    <div className="text-xs text-slate-500">{batch_id}</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-48 flex items-center justify-center border border-dashed border-slate-800">
                <div className="text-center">
                  <div className="text-slate-600 mb-2">No results yet</div>
                  <div className="text-xs text-slate-700">Run the sample to see processing summary</div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Results Preview Table */}
        {hasRun && (
          <div className="border border-slate-800 bg-slate-950 overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div className="font-mono text-xs text-slate-500 uppercase tracking-widest">
                Results Preview
              </div>
              <div className="font-mono text-xs text-emerald-500">
                All results verified against production engine
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/50">
                    <th className="text-left p-3 font-mono text-xs text-slate-500 uppercase tracking-wider">Input</th>
                    <th className="text-left p-3 font-mono text-xs text-slate-500 uppercase tracking-wider">Resolved</th>
                    <th className="text-left p-3 font-mono text-xs text-slate-500 uppercase tracking-wider">Path</th>
                    <th className="text-left p-3 font-mono text-xs text-slate-500 uppercase tracking-wider">Trace ID</th>
                    <th className="text-left p-3 font-mono text-xs text-slate-500 uppercase tracking-wider">Hash</th>
                    <th className="text-left p-3 font-mono text-xs text-slate-500 uppercase tracking-wider">Sig</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((row, index) => (
                    <tr
                      key={index}
                      className="border-b border-slate-800/50 hover:bg-slate-900/30 transition-colors"
                    >
                      <td className="p-3 text-slate-300">{row.input}</td>
                      <td className="p-3 text-white font-medium">
                        {row.resolved || (
                          <span className="text-amber-500 italic">Human Review</span>
                        )}
                      </td>
                      <td className="p-3">
                        <span
                          className="font-mono text-xs px-2 py-1 border"
                          style={{
                            borderColor: row.decision_path === 'L1' ? '#22c55e' :
                                        row.decision_path === 'L2' ? '#3b82f6' :
                                        row.decision_path === 'L3' ? '#f59e0b' : '#f59e0b',
                            color: row.decision_path === 'L1' ? '#22c55e' :
                                   row.decision_path === 'L2' ? '#3b82f6' :
                                   row.decision_path === 'L3' ? '#f59e0b' : '#f59e0b',
                          }}
                        >
                          {row.decision_path}
                        </span>
                      </td>
                      <td className="p-3 font-mono text-xs text-slate-500">{row.trace_id}</td>
                      <td className="p-3 font-mono text-xs text-slate-600">{row.hash}</td>
                      <td className="p-3">
                        {row.signature_verified && (
                          <CheckCircle size={16} className="text-emerald-500" />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Forensic Receipt Footer */}
            <div className="p-4 border-t border-slate-800 bg-slate-900/30">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                <div>
                  <div className="font-mono text-slate-600 uppercase tracking-wider mb-1">Batch Hash</div>
                  <div className="font-mono text-slate-400 truncate">{forensic_receipt.batch_hash.substring(0, 24)}...</div>
                </div>
                <div>
                  <div className="font-mono text-slate-600 uppercase tracking-wider mb-1">ECDSA</div>
                  <div className="font-mono text-emerald-500">{forensic_receipt.ecdsa_status}</div>
                </div>
                <div>
                  <div className="font-mono text-slate-600 uppercase tracking-wider mb-1">WORM</div>
                  <div className="font-mono text-amber-500">{forensic_receipt.worm_status}</div>
                </div>
                <div>
                  <div className="font-mono text-slate-600 uppercase tracking-wider mb-1">Retention</div>
                  <div className="font-mono text-slate-400">{forensic_receipt.retention_until}</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
