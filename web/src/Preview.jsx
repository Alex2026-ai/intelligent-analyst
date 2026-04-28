/**
 * Preview component - Shows dashboard layout without auth
 * For visual development only - remove before production
 */
import React, { useState } from 'react';
import {
  Upload, History, Activity, Terminal, LogOut, BrainCircuit,
  FileText, CheckCircle, AlertTriangle, ChevronRight
} from 'lucide-react';
import {
  IntelligenceConsole,
  ConsoleNavItem,
  AnalysisConsole,
  AnalysisMessage,
  DataCard,
} from './ui';

// Mock data
const mockBatches = [
  { trace_id: 'BATCH-A1B2C3D4E5F6', filename: 'companies_q4.csv', total: 1250, auto_resolved_pct: 94.2, flagged_count: 12, timestamp: '2026-02-08T10:30:00Z', stats: { l0_count: 5, l1_count: 890, l2_count: 280, l3_count: 63, l4_count: 12 } },
  { trace_id: 'BATCH-F7E8D9C0B1A2', filename: 'vendors_list.csv', total: 450, auto_resolved_pct: 98.1, flagged_count: 2, timestamp: '2026-02-07T14:22:00Z', stats: { l0_count: 1, l1_count: 380, l2_count: 60, l3_count: 7, l4_count: 2 } },
  { trace_id: 'BATCH-123456789ABC', filename: 'suppliers_2026.xlsx', total: 2100, auto_resolved_pct: 87.5, flagged_count: 45, timestamp: '2026-02-06T09:15:00Z', stats: { l0_count: 12, l1_count: 1500, l2_count: 450, l3_count: 93, l4_count: 45 } },
];

const analysisPrompts = [
  'Explain flagged records',
  'Summarize audit findings',
  'Generate compliance summary',
  'Explain this certificate',
];

export default function Preview() {
  const [activeTab, setActiveTab] = useState('history');
  const [selectedBatch, setSelectedBatch] = useState(mockBatches[0]);

  return (
    <IntelligenceConsole
      headerLeft={
        <div className="console-brand">
          <div className="console-brand__mark">IA</div>
          <span className="console-brand__name">Intelligent Analyst</span>
        </div>
      }
      headerCenter={
        selectedBatch ? (
          <div className="console-batch-pill">
            <span className="console-batch-pill__label">Batch:</span>
            <span className="console-batch-pill__value">{selectedBatch.trace_id?.slice(0, 12)}</span>
          </div>
        ) : null
      }
      headerRight={
        <div className="flex items-center gap-3">
          <div className="console-status">
            <span className="console-status__dot" />
            Online
          </div>
          <button className="console-btn console-btn--ghost console-btn--sm">
            <LogOut size={14} />
          </button>
        </div>
      }
      contextRail={
        <div className="console-nav">
          <div className="console-nav-section">Workspace</div>
          <ConsoleNavItem icon={Upload} label="Upload" active={activeTab === 'upload'} onClick={() => setActiveTab('upload')} />
          <ConsoleNavItem icon={History} label="Batches" active={activeTab === 'history'} onClick={() => setActiveTab('history')} count={mockBatches.length} />
          <ConsoleNavItem icon={Activity} label="Overview" active={activeTab === 'overview'} onClick={() => setActiveTab('overview')} />
          <div className="console-nav-section">Admin</div>
          <ConsoleNavItem icon={Terminal} label="Config" active={activeTab === 'config'} onClick={() => setActiveTab('config')} />
        </div>
      }
      dataPanel={
        <div className="data-panel">
          <div className="data-panel__header">Data Context</div>
          <div className="data-panel__content">
            {selectedBatch && (
              <DataCard title="Batch Stats">
                <div className="console-metrics">
                  <div className="console-metric">
                    <div className="console-metric__value">{selectedBatch.total}</div>
                    <div className="console-metric__label">Records</div>
                  </div>
                  <div className="console-metric">
                    <div className="console-metric__value console-metric__value--positive">{selectedBatch.auto_resolved_pct?.toFixed(0)}%</div>
                    <div className="console-metric__label">Resolved</div>
                  </div>
                  <div className="console-metric">
                    <div className="console-metric__value console-metric__value--warning">{selectedBatch.flagged_count}</div>
                    <div className="console-metric__label">Flagged</div>
                  </div>
                  <div className="console-metric">
                    <div className="console-metric__value">{selectedBatch.stats?.l3_count || 0}</div>
                    <div className="console-metric__label">LLM Calls</div>
                  </div>
                </div>
              </DataCard>
            )}

            <DataCard title="Recent Batches">
              <table className="console-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th className="console-table th--right">Records</th>
                  </tr>
                </thead>
                <tbody>
                  {mockBatches.map((batch) => (
                    <tr
                      key={batch.trace_id}
                      className={`console-table tr--clickable ${selectedBatch?.trace_id === batch.trace_id ? 'bg-blue-500/10' : ''}`}
                      onClick={() => setSelectedBatch(batch)}
                    >
                      <td className="console-table td--mono">{batch.trace_id?.slice(0, 8)}</td>
                      <td className="console-table td--right">{batch.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </DataCard>

            {selectedBatch?.stats && (
              <DataCard title="Layer Distribution">
                <table className="console-table">
                  <tbody>
                    <tr>
                      <td>L0 (Invalid)</td>
                      <td className="console-table td--right">{selectedBatch.stats.l0_count}</td>
                    </tr>
                    <tr>
                      <td>L1 (Exact)</td>
                      <td className="console-table td--right console-table td--positive">{selectedBatch.stats.l1_count}</td>
                    </tr>
                    <tr>
                      <td>L2 (Fuzzy)</td>
                      <td className="console-table td--right">{selectedBatch.stats.l2_count}</td>
                    </tr>
                    <tr>
                      <td>L3 (LLM)</td>
                      <td className="console-table td--right console-table td--warning">{selectedBatch.stats.l3_count}</td>
                    </tr>
                    <tr>
                      <td>L4 (Manual)</td>
                      <td className="console-table td--right console-table td--negative">{selectedBatch.stats.l4_count}</td>
                    </tr>
                  </tbody>
                </table>
              </DataCard>
            )}
          </div>
        </div>
      }
      dataPanelOpen={true}
    >
      <AnalysisConsole
        inputPlaceholder="Ask about this batch..."
        inputDisabled={!selectedBatch}
        presetPrompts={selectedBatch ? analysisPrompts : undefined}
      >
        {!selectedBatch ? (
          <div className="analysis-console__empty">
            <BrainCircuit size={48} className="analysis-console__empty-icon" />
            <h2 className="analysis-console__empty-title">Intelligent Analyst</h2>
            <p className="analysis-console__empty-text">
              Select a batch from the sidebar to begin analysis.
            </p>
          </div>
        ) : (
          <>
            <AnalysisMessage type="system">
              <p><strong>Batch loaded:</strong> <code>{selectedBatch.trace_id}</code></p>
              <p>File: {selectedBatch.filename} • {selectedBatch.total} records</p>
            </AnalysisMessage>

            <AnalysisMessage type="assistant">
              <p><strong>Analysis Summary</strong></p>
              <p>This batch contains {selectedBatch.total} records with a {selectedBatch.auto_resolved_pct}% automatic resolution rate.</p>
              <p>{selectedBatch.flagged_count} records have been flagged for manual review.</p>
            </AnalysisMessage>

            {selectedBatch.flagged_count > 0 && (
              <AnalysisMessage type="assistant">
                <p><strong>Flagged Records Breakdown:</strong></p>
                <p>• {selectedBatch.stats.l4_count} records require manual verification</p>
                <p>• Primary reasons: Low confidence matches, ambiguous entity names</p>
                <p>• Recommended action: Review flagged records in the audit view</p>
              </AnalysisMessage>
            )}
          </>
        )}
      </AnalysisConsole>
    </IntelligenceConsole>
  );
}
