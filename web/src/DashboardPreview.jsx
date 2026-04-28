'use client';

/**
 * DashboardPreview — Preview dashboard without auth
 * Analysis is the default landing page
 */
import React, { useMemo, useRef, useState } from 'react';
import JSZip from 'jszip';
import {
  BrainCircuit, Activity, History, Terminal, Upload,
  CheckCircle, ChevronRight, Copy, Check, FileText, Sparkles,
  Download, PlayCircle, ShieldCheck, RefreshCcw, Database, Lock
} from 'lucide-react';
import AuditLog from './views/AuditLog';
import AnalysisHome from './views/AnalysisHome';

// Mock batch data
const mockBatches = [
  {
    trace_id: 'BATCH-A1B2C3D4E5F6',
    filename: 'companies_q4.csv',
    total: 1250,
    auto_resolved_pct: 94.2,
    flagged_count: 12,
    timestamp: '2026-02-08T10:30:00Z',
    status: 'completed'
  },
  {
    trace_id: 'BATCH-F7E8D9C0B1A2',
    filename: 'vendors_list.csv',
    total: 450,
    auto_resolved_pct: 98.1,
    flagged_count: 2,
    timestamp: '2026-02-07T14:22:00Z',
    status: 'completed'
  },
  {
    trace_id: 'BATCH-123456789ABC',
    filename: 'suppliers_2026.xlsx',
    total: 2100,
    auto_resolved_pct: 87.5,
    flagged_count: 45,
    timestamp: '2026-02-06T09:15:00Z',
    status: 'completed'
  },
];

const sampleUploadBatch = {
  trace_id: 'DEMO-SAMPLE-20260427',
  filename: 'sample_suppliers_public_demo.csv',
  total: 25,
  auto_resolved_pct: 96,
  flagged_count: 1,
  timestamp: '2026-04-27T12:00:00Z',
  status: 'completed',
  stats: {
    layer_1_exact: 14,
    layer_1_norm: 6,
    layer_2_vector: 4,
    layer_3_llm: 0,
  },
  transparency_statement: {
    template_id: 'TLS_PUBLIC_PREVIEW_v1',
    hash: '8f4d2c91a7b0d62e4f5319ad0c661e44',
    timestamp: '2026-04-27T12:00:03Z',
  },
  decision_path_summary: {
    L1_DETERMINISTIC: 20,
    L2_VECTOR_FUZZY: 4,
    L3_LLM: 0,
    L4_HUMAN_REVIEW_REQUIRED: 1,
  },
  llm_budget_summary: {
    budget_usd: 100,
    spent_usd: 0,
    calls: 0,
    budget_exhausted: false,
  },
};

const sampleRecords = [
  { input: 'Apple Inc', resolved: 'Apple Inc.', layer: 'L1 deterministic', confidence: 1 },
  { input: 'Microsoft Corp.', resolved: 'Microsoft Corporation', layer: 'L1 deterministic', confidence: 1 },
  { input: 'Acme Industrial Supply LLC', resolved: 'Acme Industrial Supply, LLC', layer: 'L2 vector fuzzy', confidence: 0.94 },
  { input: 'Northstar Components', resolved: 'Northstar Components', layer: 'L2 vector fuzzy', confidence: 0.91 },
  { input: 'Unknown Vendor 4421', resolved: 'Human review required', layer: 'L4 review', confidence: 0.62 },
];

const buildEvidencePack = (batch) => ({
  manifest: {
    product: 'Intelligent Analyst Enterprise',
    pack_type: 'public_preview_sample',
    generated_at: '2026-04-27T12:00:05Z',
    trace_id: batch.trace_id,
    source_file: batch.filename,
    notice: 'This evidence pack is generated from bundled public preview data. It contains no customer data and makes no backend calls.',
  },
  summary: {
    status: batch.status,
    total_records: batch.total,
    auto_resolved_pct: batch.auto_resolved_pct,
    flagged_count: batch.flagged_count,
    decision_path_summary: batch.decision_path_summary || {
      L1_DETERMINISTIC: Math.round(batch.total * 0.82),
      L2_VECTOR_FUZZY: Math.round(batch.total * 0.12),
      L3_LLM: 0,
      L4_HUMAN_REVIEW_REQUIRED: batch.flagged_count,
    },
  },
  deterministic_replay: {
    replay_runs: 3,
    variance: 0,
    hash_algorithm: 'SHA-256',
    signature_profile: 'ECDSA P-256',
    sample_root_hash: `preview-${batch.trace_id.toLowerCase()}`,
  },
  audit_trail: [
    { timestamp: batch.timestamp, actor: 'public-preview', action: 'upload', target: batch.trace_id, result: 'success' },
    { timestamp: batch.timestamp, actor: 'service', action: 'layer_executed', target: batch.trace_id, result: 'success' },
    { timestamp: batch.timestamp, actor: 'service', action: 'evidence_generated', target: batch.trace_id, result: 'success' },
  ],
  sample_resolutions: sampleRecords,
});

// --- VISUAL COMPONENTS ---

const NavItem = ({ active, onClick, label, icon: Icon }) => (
  <button
    onClick={onClick}
    type="button"
    className={`flex items-center gap-2 px-4 py-2 text-[10px] font-mono uppercase tracking-widest transition-colors ${
      active ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-slate-400 hover:text-white border-b-2 border-transparent'
    }`}
  >
    <Icon size={14} />
    {label}
  </button>
);

const Badge = ({ children, color = "cyan" }) => {
  const colors = {
    cyan: "border-cyan-500/20 bg-cyan-950/30 text-cyan-400",
    violet: "border-violet-500/20 bg-violet-950/30 text-violet-400",
    amber: "border-amber-500/20 bg-amber-950/30 text-amber-400"
  };
  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-widest ${colors[color]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      {children}
    </span>
  );
};

export default function DashboardPreview() {
  const [activeTab, setActiveTab] = useState('analysis');
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [demoBatches, setDemoBatches] = useState(mockBatches);
  const [notice, setNotice] = useState('');
  const noticeTimeoutRef = useRef(null);

  const overview = useMemo(() => {
    const totals = demoBatches.reduce((acc, batch) => {
      acc.records += batch.total || 0;
      acc.flagged += batch.flagged_count || 0;
      acc.resolvedWeighted += ((batch.auto_resolved_pct || 0) / 100) * (batch.total || 0);
      return acc;
    }, { records: 0, flagged: 0, resolvedWeighted: 0 });

    const resolvedPct = totals.records > 0
      ? ((totals.resolvedWeighted / totals.records) * 100).toFixed(1)
      : '0.0';

    return {
      batches: demoBatches.length,
      records: totals.records,
      flagged: totals.flagged,
      resolvedPct,
    };
  }, [demoBatches]);

  const showNotice = (message) => {
    setNotice(message);
    window.clearTimeout(noticeTimeoutRef.current);
    noticeTimeoutRef.current = window.setTimeout(() => setNotice(''), 3000);
  };

  const copyToClipboard = (text) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
    }
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const runSampleUpload = () => {
    setDemoBatches((current) => [
      sampleUploadBatch,
      ...current.filter((batch) => batch.trace_id !== sampleUploadBatch.trace_id),
    ]);
    setSelectedBatch(sampleUploadBatch);
    setActiveTab('history');
    showNotice('Sample upload processed locally. No file was uploaded.');
  };

  const refreshSampleData = () => {
    showNotice('Sample data is already current.');
  };

  const downloadEvidencePack = async (batch) => {
    const pack = buildEvidencePack(batch);
    const zip = new JSZip();

    zip.file('manifest.json', JSON.stringify(pack.manifest, null, 2));
    zip.file('summary.json', JSON.stringify(pack.summary, null, 2));
    zip.file('deterministic-replay.json', JSON.stringify(pack.deterministic_replay, null, 2));
    zip.file('audit-trail.json', JSON.stringify(pack.audit_trail, null, 2));
    zip.file('sample-resolutions.json', JSON.stringify(pack.sample_resolutions, null, 2));
    zip.file('README.txt', [
      'Intelligent Analyst public preview evidence pack',
      '',
      'This ZIP is generated locally from bundled sample data.',
      'It is intended to show the shape of an audit artifact without exposing customer data.',
      '',
      `Trace ID: ${batch.trace_id}`,
      `Source file: ${batch.filename}`,
    ].join('\n'));

    const blob = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${batch.trace_id.toLowerCase()}-sample-evidence-pack.zip`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    showNotice('Sample evidence pack downloaded.');
  };

  return (
    <div style={{ backgroundColor: '#050814', color: '#e2e8f0', minHeight: '100vh' }} className="font-sans antialiased selection:bg-cyan-900 selection:text-white">

      {/* Navigation */}
      <nav className="sticky top-0 inset-x-0 z-50 border-b border-slate-700 bg-[#0B1220]/95 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 lg:min-h-20 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 bg-gradient-to-br from-cyan-950 to-slate-900 border border-slate-700 flex items-center justify-center">
              <BrainCircuit className="text-cyan-500" size={20} />
            </div>
            <div className="leading-tight text-left min-w-0">
              <div className="font-bold text-slate-100 tracking-tight text-lg uppercase">Intelligent Analyst</div>
              <div className="text-[10px] text-cyan-500/70 font-mono tracking-widest uppercase">Enterprise v8.2.2</div>
            </div>
          </div>
          <div className="w-full lg:w-auto overflow-x-auto">
            <div className="flex gap-1 min-w-max">
              <NavItem active={activeTab === 'analysis'} onClick={() => setActiveTab('analysis')} label="Analysis" icon={Sparkles} />
              <NavItem active={activeTab === 'upload'} onClick={() => setActiveTab('upload')} label="Upload" icon={Upload} />
              <NavItem active={activeTab === 'history'} onClick={() => setActiveTab('history')} label="History" icon={History} />
              <NavItem active={activeTab === 'auditlog'} onClick={() => setActiveTab('auditlog')} label="Audit Log" icon={FileText} />
              <NavItem active={activeTab === 'overview'} onClick={() => setActiveTab('overview')} label="Overview" icon={Activity} />
              <NavItem active={activeTab === 'config'} onClick={() => setActiveTab('config')} label="Config" icon={Terminal} />
              <a
                href="/request-demo"
                className="flex items-center gap-2 px-4 py-2 text-[10px] font-mono uppercase tracking-widest text-slate-300 hover:text-white transition-colors border border-slate-700 hover:border-cyan-500/50"
              >
                Request Demo
              </a>
            </div>
          </div>
        </div>
      </nav>

      {/* Preview Mode Banner */}
      <div className="bg-violet-500/20 border-b border-violet-500/40 py-3 px-6">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-center gap-2 text-center">
          <ShieldCheck className="text-violet-400" size={14} />
          <span className="text-violet-400 text-xs font-mono uppercase tracking-wider">
            Interactive Public Demo - sample data only, no backend calls
          </span>
        </div>
      </div>

      {notice && (
        <div role="status" className="max-w-7xl mx-auto px-6 pt-6">
          <div className="border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 px-4 py-3 text-sm">
            {notice}
          </div>
        </div>
      )}

      <main className="pb-20 max-w-7xl mx-auto px-6 pt-10">

        {/* ANALYSIS TAB - Default landing page */}
        {activeTab === 'analysis' && (
          <AnalysisHome
            batches={demoBatches}
            batchesLoading={false}
            selectedBatch={selectedBatch}
            onSelectBatch={(batch) => {
              setSelectedBatch(batch);
              setActiveTab('history');
            }}
            onNavigateToHistory={() => setActiveTab('history')}
            isDemoMode={true}
          />
        )}

        {/* AUDIT LOG TAB */}
        {activeTab === 'auditlog' && (
          <AuditLog
            batches={demoBatches}
            loading={false}
          />
        )}

        {/* UPLOAD TAB */}
        {activeTab === 'upload' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="mb-8">
              <Badge>Entity Resolution</Badge>
              <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">Upload & Process</h2>
              <p className="text-slate-400 max-w-3xl text-lg font-light leading-relaxed">
                The public preview uses a bundled sample file so anyone can test the flow without credentials or customer data.
              </p>
            </div>
            <div className="grid lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 border border-slate-800 bg-[#0B0F19] p-8">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 border border-cyan-500/30 bg-cyan-500/10 flex items-center justify-center shrink-0">
                    <Upload className="text-cyan-400" size={22} />
                  </div>
                  <div>
                    <h3 className="text-white text-xl font-semibold mb-2">Run the bundled sample dataset</h3>
                    <p className="text-slate-400 leading-relaxed mb-6">
                      This simulates a CSV upload, runs the sample through the demo waterfall, and opens the generated batch in History.
                    </p>
                    <button
                      type="button"
                      onClick={runSampleUpload}
                      className="inline-flex items-center gap-2 px-5 py-3 bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/20 transition-colors text-xs font-mono uppercase tracking-wider"
                    >
                      <PlayCircle size={16} />
                      Run Sample Upload
                    </button>
                  </div>
                </div>
              </div>
              <div className="border border-slate-800 bg-[#0B0F19] p-6">
                <h3 className="text-[10px] font-mono text-amber-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                  <Lock size={14} />
                  Public Preview Limits
                </h3>
                <ul className="space-y-3 text-sm text-slate-400">
                  <li>No local file picker is opened.</li>
                  <li>No files leave your browser.</li>
                  <li>Authenticated deployments enable CSV, Excel, JSON, and TXT uploads.</li>
                </ul>
              </div>
            </div>
            <div className="bg-[#0B0F19] border border-slate-800">
              <div className="p-4 border-b border-slate-800">
                <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Sample Rows</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-[10px] font-mono text-slate-500 uppercase tracking-wider border-b border-slate-800">
                      <th className="text-left p-4">Input</th>
                      <th className="text-left p-4">Result</th>
                      <th className="text-left p-4">Layer</th>
                      <th className="text-right p-4">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sampleRecords.map((record) => (
                      <tr key={`${record.input}-${record.layer}`} className="border-b border-slate-800/50">
                        <td className="p-4 text-slate-300 text-sm">{record.input}</td>
                        <td className="p-4 text-white text-sm">{record.resolved}</td>
                        <td className="p-4 text-cyan-400 text-xs font-mono uppercase">{record.layer}</td>
                        <td className="p-4 text-right text-slate-300 text-sm font-mono">{Math.round(record.confidence * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* HISTORY TAB */}
        {activeTab === 'history' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="mb-8">
              <Badge color="violet">Batch History</Badge>
              <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">Processing History</h2>
              <p className="text-slate-400 max-w-3xl text-lg font-light leading-relaxed">
                View past batches and download evidence packs. Select a row to enable analysis.
              </p>
            </div>

            <div className="grid lg:grid-cols-3 gap-8">
              {/* Batch Table */}
              <div className="lg:col-span-2">
                <div className="bg-[#0B0F19] border border-slate-800">
                  <div className="flex items-center justify-between p-4 border-b border-slate-800">
                    <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Recent Batches</h3>
                    <button
                      type="button"
                      onClick={refreshSampleData}
                      className="inline-flex items-center gap-1 text-[10px] font-mono text-slate-500 hover:text-cyan-400 transition-colors"
                    >
                      <RefreshCcw size={12} />
                      Refresh
                    </button>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="text-[10px] font-mono text-slate-500 uppercase tracking-wider border-b border-slate-800">
                          <th className="text-left p-4">Trace ID</th>
                          <th className="text-left p-4">Filename</th>
                          <th className="text-right p-4">Records</th>
                          <th className="text-right p-4">Resolved</th>
                          <th className="text-right p-4">Flagged</th>
                          <th className="w-8 p-4"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {demoBatches.map((batch) => (
                          <tr
                            key={batch.trace_id}
                            onClick={() => setSelectedBatch(batch)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                setSelectedBatch(batch);
                              }
                            }}
                            role="button"
                            tabIndex={0}
                            aria-label={`Select batch ${batch.trace_id} ${batch.filename}`}
                            className={`border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer group transition-colors ${
                              selectedBatch?.trace_id === batch.trace_id ? 'bg-cyan-500/5 border-l-2 border-l-cyan-500' : ''
                            }`}
                          >
                            <td className="p-4">
                              <div className="flex items-center gap-2">
                                <code className="text-cyan-400 text-xs font-mono">{batch.trace_id.slice(0, 14)}</code>
                                <button
                                  onClick={(e) => { e.stopPropagation(); copyToClipboard(batch.trace_id); }}
                                  type="button"
                                  aria-label={`Copy trace ID ${batch.trace_id}`}
                                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                  {copiedId === batch.trace_id ? (
                                    <Check size={12} className="text-emerald-400" />
                                  ) : (
                                    <Copy size={12} className="text-slate-500" />
                                  )}
                                </button>
                              </div>
                            </td>
                            <td className="p-4 text-slate-300 text-sm">{batch.filename}</td>
                            <td className="p-4 text-right font-mono text-sm text-white">{batch.total.toLocaleString()}</td>
                            <td className="p-4 text-right font-mono text-sm text-cyan-400">{batch.auto_resolved_pct}%</td>
                            <td className="p-4 text-right font-mono text-sm">
                              {batch.flagged_count > 0 ? (
                                <span className="text-amber-400">{batch.flagged_count}</span>
                              ) : (
                                <span className="text-slate-600">0</span>
                              )}
                            </td>
                            <td className="p-4">
                              <ChevronRight size={14} className="text-slate-600 group-hover:text-cyan-400 transition-colors" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Detail Panel */}
              <div className="lg:col-span-1">
                {selectedBatch ? (
                  <div className="bg-[#0B0F19] border border-slate-800 p-6 space-y-6">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                      <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Batch Details</h3>
                    </div>
                    <div>
                      <label className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Trace ID</label>
                      <code className="block text-cyan-400 text-sm font-mono mt-1">{selectedBatch.trace_id}</code>
                    </div>
                    <div>
                      <label className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Status</label>
                      <div className="mt-1">
                        <span className="inline-flex items-center gap-1 text-emerald-400">
                          <CheckCircle size={12} /> Completed
                        </span>
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Filename</label>
                      <p className="text-white mt-1">{selectedBatch.filename}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-800">
                      <div>
                        <label className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Records</label>
                        <p className="text-2xl text-white font-bold font-mono mt-1">{selectedBatch.total.toLocaleString()}</p>
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Resolved</label>
                        <p className="text-2xl text-cyan-400 font-bold font-mono mt-1">{selectedBatch.auto_resolved_pct}%</p>
                      </div>
                    </div>
                    <div className="pt-4 border-t border-slate-800">
                      <button
                        type="button"
                        onClick={() => downloadEvidencePack(selectedBatch)}
                        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20 transition-colors text-xs font-mono uppercase tracking-wider"
                      >
                        <Download size={14} />
                        Download Sample Evidence Pack
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="bg-[#0B0F19] border border-slate-800 border-dashed p-12 text-center">
                    <History className="mx-auto text-slate-600 mb-4" size={32} />
                    <p className="text-slate-500 text-sm">Select a batch to view details</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* OVERVIEW TAB */}
        {activeTab === 'overview' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="mb-8">
              <Badge color="cyan">Analytics</Badge>
              <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">Performance Overview</h2>
            </div>
            <div className="grid md:grid-cols-4 gap-4">
              {[
                ['Batches', overview.batches.toLocaleString()],
                ['Records', overview.records.toLocaleString()],
                ['Resolved', `${overview.resolvedPct}%`],
                ['Flagged', overview.flagged.toLocaleString()],
              ].map(([label, value]) => (
                <div key={label} className="bg-[#0B0F19] border border-slate-800 p-6">
                  <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">{label}</div>
                  <div className="text-3xl text-white font-bold font-mono mt-3">{value}</div>
                </div>
              ))}
            </div>
            <div className="bg-[#0B0F19] border border-slate-800 p-6">
              <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-3">Demo Readout</h3>
              <p className="text-slate-400 leading-relaxed">
                Metrics are calculated from the sample batches in this browser session. Run the bundled sample upload to add a new demo batch, then download its evidence pack from History.
              </p>
            </div>
          </div>
        )}

        {/* CONFIG TAB */}
        {activeTab === 'config' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="mb-8">
              <Badge color="amber">Admin</Badge>
              <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">Demo Configuration</h2>
            </div>
            <div className="grid md:grid-cols-2 gap-6">
              {[
                ['Data scope', 'Bundled sample data only'],
                ['Upload mode', 'Local simulation, no file transfer'],
                ['Evidence export', 'Client-side ZIP download'],
                ['Backend calls', 'Disabled in public preview'],
                ['Replay profile', '3 sample replay runs, zero variance'],
                ['Retention profile', 'Illustrative 7-year WORM policy'],
              ].map(([label, value]) => (
                <div key={label} className="bg-[#0B0F19] border border-slate-800 p-6 flex items-start gap-4">
                  <Database className="text-cyan-400 shrink-0 mt-1" size={18} />
                  <div>
                    <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">{label}</div>
                    <div className="text-white mt-2">{value}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-[#02040a] border-t border-slate-900 py-12 px-6 mt-20">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <p className="text-[10px] font-mono uppercase tracking-widest text-slate-600">Intelligent Analyst 2026</p>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-600">System Nominal</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
