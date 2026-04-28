import React from 'react';
import { X, MessageSquare, Sparkles } from 'lucide-react';
import { cx } from '../theme';

interface AssistedAnalysisDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  /** Selected batch trace_id, if any */
  batchId?: string | null;
}

/**
 * AssistedAnalysisDrawer — Read-only analysis panel
 *
 * Visual implementation only. No API calls.
 * Shows allowed prompt buttons and disabled input.
 */
export function AssistedAnalysisDrawer({
  isOpen,
  onClose,
  batchId,
}: AssistedAnalysisDrawerProps) {
  const hasBatch = Boolean(batchId);

  // Contract-specified allowed prompts (Section 5.3)
  const allowedPrompts = [
    'Explain why these records were flagged',
    'Summarize audit findings',
    'Generate a regulator-ready summary',
    'Explain this certificate',
  ];

  return (
    <aside className={cx('ia-shell__drawer', isOpen && 'ia-shell__drawer--open')}>
      {/* Header */}
      <div className="ia-drawer-header">
        <div>
          <div className="ia-drawer-header__title">
            <Sparkles size={12} style={{ display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />
            Assisted Analysis
          </div>
          <div className="ia-drawer-subtext">Read-only · Batch-scoped</div>
        </div>
        <button className="ia-drawer-header__close" onClick={onClose} title="Close">
          <X size={16} />
        </button>
      </div>

      {/* Content */}
      <div className="ia-drawer-content">
        {!hasBatch ? (
          /* Empty state */
          <div className="ia-drawer-empty">
            <MessageSquare size={32} className="ia-drawer-empty__icon" />
            <p className="ia-drawer-empty__text">
              Select a batch to analyze
            </p>
          </div>
        ) : (
          /* Batch selected - show prompts */
          <div className="ia-drawer-prompts">
            <div className="ia-drawer-batch-id">
              <span className="ia-drawer-batch-id__label">Batch:</span>
              <code className="ia-drawer-batch-id__value">{batchId}</code>
            </div>

            <div className="ia-drawer-section">
              <div className="ia-drawer-section__title">Suggested Prompts</div>
              {allowedPrompts.map((prompt, i) => (
                <button
                  key={i}
                  className="ia-prompt-btn"
                  disabled
                  title="Analysis is read-only"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer with disabled input */}
      <div className="ia-drawer-footer">
        <input
          type="text"
          className="ia-drawer-input"
          placeholder="Analysis is read-only and batch-scoped"
          disabled
        />
      </div>
    </aside>
  );
}

export default AssistedAnalysisDrawer;
