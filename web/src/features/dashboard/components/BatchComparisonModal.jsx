import { FileDown, FileJson, Sliders, X } from 'lucide-react';

function getLayerCount(batch, prefix) {
  const s = batch.stats || {};
  const c = batch.counts || {};
  if (prefix === 'L0') return c.l0_quarantined || c.l0 || s.layer_0_garbage || 0;
  if (prefix === 'L1') return c.l1_resolved || c.l1 || ((s.layer_1_exact || 0) + (s.layer_1_norm || 0));
  if (prefix === 'L2') return c.l2_resolved || c.l2 || s.layer_2_vector || 0;
  if (prefix === 'L3') return c.l3_resolved || c.l3 || s.layer_3_llm || 0;
  if (prefix === 'L4') return c.l4_flagged || c.l4 || s.layer_4_human || 0;
  return 0;
}

function getDuration(batch) {
  return batch.duration_seconds || (batch.duration_ms ? batch.duration_ms / 1000 : 0);
}

function formatMetricValue(value, format) {
  if (format === 'sec') return `${value.toFixed(1)}s`;
  if (format.startsWith('pct')) return `${value.toFixed(1)}%`;
  return value;
}

function renderDelta(va, vb, format = 'num') {
  if (typeof va !== 'number' || typeof vb !== 'number' || !isFinite(va) || !isFinite(vb)) {
    return <span className="text-gray-500">—</span>;
  }
  const d = va - vb;
  if (d === 0) return <span className="text-gray-200">—</span>;
  const sign = d > 0 ? '+' : '';
  const color = format === 'pct_good' ? (d > 0 ? 'text-emerald-400' : 'text-red-400') :
                format === 'pct_bad' ? (d < 0 ? 'text-emerald-400' : 'text-red-400') :
                format === 'lower_better' ? (d < 0 ? 'text-emerald-400' : 'text-amber-400') :
                'text-[#cbd5e1]';
  const value = format.startsWith('pct') ? `${sign}${d.toFixed(1)}%` :
                format === 'sec' ? `${sign}${d.toFixed(1)}s` :
                `${sign}${d}`;
  return <span className={`font-mono ${color}`}>{value}</span>;
}

function buildRows(a, b, aAnomalies, bAnomalies) {
  return [
    { label: 'Records', va: a.total || a.total_records || 0, vb: b.total || b.total_records || 0, fmt: 'num' },
    { label: 'Auto-Resolved %', va: a.auto_resolved_pct || 0, vb: b.auto_resolved_pct || 0, fmt: 'pct_good' },
    { label: 'L0 Garbage', va: getLayerCount(a, 'L0'), vb: getLayerCount(b, 'L0'), fmt: 'lower_better' },
    { label: 'L1 Deterministic', va: getLayerCount(a, 'L1'), vb: getLayerCount(b, 'L1'), fmt: 'num' },
    { label: 'L2 Vector', va: getLayerCount(a, 'L2'), vb: getLayerCount(b, 'L2'), fmt: 'num' },
    { label: 'L3 LLM', va: getLayerCount(a, 'L3'), vb: getLayerCount(b, 'L3'), fmt: 'num' },
    { label: 'L4 Review', va: getLayerCount(a, 'L4'), vb: getLayerCount(b, 'L4'), fmt: 'lower_better' },
    { label: 'Duration', va: getDuration(a), vb: getDuration(b), fmt: 'sec' },
    { label: 'Anomalies', va: aAnomalies.anomalies.length, vb: bAnomalies.anomalies.length, fmt: 'lower_better' },
  ];
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function exportComparisonCsv(rows, a, b) {
  const csvRows = [['Metric', 'A (Primary)', 'B (Compare)', 'Delta']];
  rows.forEach(r => {
    csvRows.push([
      r.label,
      formatMetricValue(r.va, r.fmt),
      formatMetricValue(r.vb, r.fmt),
      String(r.va - r.vb),
    ]);
  });
  const csv = csvRows.map(r => r.join(',')).join('\n');
  downloadBlob(
    `comparison_${a.trace_id?.slice(0,12)}_vs_${b.trace_id?.slice(0,12)}.csv`,
    new Blob([csv], { type: 'text/csv' }),
  );
}

function exportComparisonJson(rows, a, b, batchLabels, aAnomalies, bAnomalies) {
  const payload = {
    exported_at: new Date().toISOString(),
    primary: { trace_id: a.trace_id, filename: a.filename, label: batchLabels[a.trace_id] || null },
    compare: { trace_id: b.trace_id, filename: b.filename, label: batchLabels[b.trace_id] || null },
    metrics: Object.fromEntries(rows.map(r => [r.label, { a: r.va, b: r.vb, delta: r.va - r.vb }])),
    anomalies: { a: aAnomalies.anomalies, b: bAnomalies.anomalies },
  };
  downloadBlob(
    `comparison_${a.trace_id?.slice(0,12)}_vs_${b.trace_id?.slice(0,12)}.json`,
    new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
  );
}

export default function BatchComparisonModal({
  selectedBatch,
  compareBatch,
  setCompareBatch,
  historyData,
  batchLabels,
  detectBatchAnomalies,
  onClose,
}) {
  if (!selectedBatch) return null;

  const batches = historyData?.batches || [];
  const completedBatches = batches.filter(b => b.trace_id !== selectedBatch.trace_id && b.status === 'completed');
  const currentIdx = batches.findIndex(b => b.trace_id === selectedBatch.trace_id);
  const previousBatch = currentIdx >= 0 ? batches.slice(currentIdx + 1).find(b => b.status === 'completed') : null;
  const latestClean = completedBatches.find(b => detectBatchAnomalies(b).level === 'clean');
  const baselineBatch = completedBatches.find(b => batchLabels[b.trace_id] === 'baseline');
  const shortcuts = [
    previousBatch && { label: 'vs Previous', batch: previousBatch },
    latestClean && { label: 'vs Latest Clean', batch: latestClean },
    baselineBatch && { label: 'vs Baseline', batch: baselineBatch },
  ].filter(Boolean);

  const comparison = compareBatch ? (() => {
    const aAnomalies = detectBatchAnomalies(selectedBatch);
    const bAnomalies = detectBatchAnomalies(compareBatch);
    const rows = buildRows(selectedBatch, compareBatch, aAnomalies, bAnomalies);
    return { aAnomalies, bAnomalies, rows };
  })() : null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[#0b1220] border border-[#1e293b] rounded-lg w-full max-w-2xl mx-4 max-h-[85vh] overflow-y-auto animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-[#0b1220] border-b border-[#1e293b] p-4 flex items-center justify-between z-10">
          <h3 className="text-[10px] font-mono text-amber-400 uppercase tracking-widest flex items-center gap-2">
            <Sliders size={12} /> Batch Comparison
          </h3>
          <button onClick={onClose} className="text-gray-200 hover:text-[#f1f5f9]">
            <X size={16} />
          </button>
        </div>
        <div className="p-4 space-y-4">
          <div className="bg-[#1e293b]/20 border border-[#1e293b] rounded p-3">
            <label className="text-[9px] font-mono text-cyan-400 uppercase tracking-widest">Primary (A)</label>
            <div className="flex items-center gap-2 mt-1">
              <code className="text-cyan-400 text-xs font-mono">{selectedBatch.trace_id?.slice(0, 16)}</code>
              <span className="text-[#cbd5e1] text-xs truncate">{selectedBatch.filename}</span>
            </div>
          </div>

          {shortcuts.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {shortcuts.map(s => (
                <button
                  key={s.label}
                  onClick={() => setCompareBatch(s.batch)}
                  className={`px-2.5 py-1 text-[10px] font-mono uppercase border rounded transition-colors ${compareBatch?.trace_id === s.batch.trace_id ? 'bg-amber-500/20 text-amber-400 border-amber-500/40' : 'bg-[#1e293b]/30 text-gray-200 border-[#1e293b] hover:border-amber-500/40 hover:text-amber-400'}`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}

          <div>
            <label className="text-[9px] font-mono text-amber-400 uppercase tracking-widest block mb-2">Compare With (B)</label>
            <select
              value={compareBatch?.trace_id || ''}
              onChange={(e) => {
                const batch = batches.find(b => b.trace_id === e.target.value);
                setCompareBatch(batch || null);
              }}
              className="w-full bg-[#0b1220] border border-[#1e293b] text-[#f1f5f9] px-2 py-2 text-xs font-mono rounded outline-none focus:border-amber-500"
            >
              <option value="">Select a batch...</option>
              {completedBatches.map(b => (
                <option key={b.trace_id} value={b.trace_id}>
                  {b.trace_id?.slice(0, 12)} — {b.filename}{batchLabels[b.trace_id] ? ` [${batchLabels[b.trace_id]}]` : ''} ({b.total || b.total_records || 0} rows)
                </option>
              ))}
            </select>
          </div>

          {compareBatch && comparison && (
            <>
              <div className="bg-[#1e293b]/20 border border-[#1e293b] rounded p-3">
                <label className="text-[9px] font-mono text-amber-400 uppercase tracking-widest">Compare (B)</label>
                <div className="flex items-center gap-2 mt-1">
                  <code className="text-amber-400 text-xs font-mono">{compareBatch.trace_id?.slice(0, 16)}</code>
                  <span className="text-[#cbd5e1] text-xs truncate">{compareBatch.filename}</span>
                </div>
              </div>

              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[9px] font-mono text-gray-200 uppercase tracking-widest border-b border-[#1e293b]">
                    <th className="text-left p-2">Metric</th>
                    <th className="text-right p-2">A (Primary)</th>
                    <th className="text-right p-2">B (Compare)</th>
                    <th className="text-right p-2">Delta</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e293b]/50">
                  {comparison.rows.map((r) => (
                    <tr key={r.label} className="hover:bg-[#1e293b]/20">
                      <td className="p-2 text-[#cbd5e1] font-mono">{r.label}</td>
                      <td className="p-2 text-right text-[#f1f5f9] font-mono">{formatMetricValue(r.va, r.fmt)}</td>
                      <td className="p-2 text-right text-[#f1f5f9] font-mono">{formatMetricValue(r.vb, r.fmt)}</td>
                      <td className="p-2 text-right text-xs">{renderDelta(r.va, r.vb, r.fmt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {(comparison.aAnomalies.anomalies.length > 0 || comparison.bAnomalies.anomalies.length > 0) && (
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div>
                    <label className="text-[9px] font-mono text-cyan-400 uppercase tracking-widest block mb-1">A Anomalies</label>
                    {comparison.aAnomalies.anomalies.length === 0 ? (
                      <span className="text-emerald-400 text-[10px]">None</span>
                    ) : (
                      <ul className="space-y-0.5">
                        {comparison.aAnomalies.anomalies.map((anomaly, i) => (
                          <li key={i} className="text-amber-400/80 text-[10px]">- {anomaly}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <label className="text-[9px] font-mono text-amber-400 uppercase tracking-widest block mb-1">B Anomalies</label>
                    {comparison.bAnomalies.anomalies.length === 0 ? (
                      <span className="text-emerald-400 text-[10px]">None</span>
                    ) : (
                      <ul className="space-y-0.5">
                        {comparison.bAnomalies.anomalies.map((anomaly, i) => (
                          <li key={i} className="text-amber-400/80 text-[10px]">- {anomaly}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}

              <div className="flex gap-2 pt-3 border-t border-[#1e293b]">
                <button
                  onClick={() => exportComparisonCsv(comparison.rows, selectedBatch, compareBatch)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase bg-[#1e293b]/30 hover:bg-[#1e293b]/60 border border-[#1e293b] rounded text-gray-200 hover:text-emerald-400 transition-colors"
                >
                  <FileDown size={12} /> Export CSV
                </button>
                <button
                  onClick={() => exportComparisonJson(comparison.rows, selectedBatch, compareBatch, batchLabels, comparison.aAnomalies, comparison.bAnomalies)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase bg-[#1e293b]/30 hover:bg-[#1e293b]/60 border border-[#1e293b] rounded text-gray-200 hover:text-violet-400 transition-colors"
                >
                  <FileJson size={12} /> Export JSON
                </button>
              </div>
            </>
          )}

          {!compareBatch && (
            <div className="text-center py-6 text-gray-200 text-xs">
              Select a completed batch above to compare against.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
