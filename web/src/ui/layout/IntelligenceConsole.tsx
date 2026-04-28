import React from 'react';

/**
 * IntelligenceConsole — Palantir/Bloomberg-inspired layout
 *
 * Three-column layout with conversation as the hero:
 * - Left: Context rail (nav + batch context)
 * - Center: Main analysis console (ChatGPT-like)
 * - Right: Data panel (tables, metrics)
 */

interface NavItemProps {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  active?: boolean;
  count?: number;
  onClick?: () => void;
}

export function ConsoleNavItem({ icon: Icon, label, active, count, onClick }: NavItemProps) {
  return (
    <button
      onClick={onClick}
      className={`console-nav-item ${active ? 'console-nav-item--active' : ''}`}
    >
      <Icon size={16} className="console-nav-item__icon" />
      <span className="console-nav-item__label">{label}</span>
      {count !== undefined && count > 0 && (
        <span className="console-nav-item__count">{count}</span>
      )}
    </button>
  );
}

interface IntelligenceConsoleProps {
  /** Left context rail content */
  contextRail?: React.ReactNode;
  /** Center main content */
  children: React.ReactNode;
  /** Right data panel content */
  dataPanel?: React.ReactNode;
  /** Whether data panel is visible */
  dataPanelOpen?: boolean;
  /** Header left content (logo/title) */
  headerLeft?: React.ReactNode;
  /** Header center content (batch context) */
  headerCenter?: React.ReactNode;
  /** Header right content (status indicators) */
  headerRight?: React.ReactNode;
}

export function IntelligenceConsole({
  contextRail,
  children,
  dataPanel,
  dataPanelOpen = true,
  headerLeft,
  headerCenter,
  headerRight,
}: IntelligenceConsoleProps) {
  return (
    <div className="intel-console">
      {/* Top Bar */}
      <header className="intel-console__header">
        <div className="intel-console__header-left">
          {headerLeft}
        </div>
        <div className="intel-console__header-center">
          {headerCenter}
        </div>
        <div className="intel-console__header-right">
          {headerRight}
        </div>
      </header>

      {/* Main Layout */}
      <div className="intel-console__body">
        {/* Left Context Rail */}
        <aside className="intel-console__context">
          {contextRail}
        </aside>

        {/* Center Main Console */}
        <main className="intel-console__main">
          {children}
        </main>

        {/* Right Data Panel */}
        {dataPanelOpen && dataPanel && (
          <aside className="intel-console__data">
            {dataPanel}
          </aside>
        )}
      </div>
    </div>
  );
}

/**
 * AnalysisConsole — ChatGPT-like centered conversation UI
 */
interface AnalysisConsoleProps {
  children: React.ReactNode;
  inputPlaceholder?: string;
  inputDisabled?: boolean;
  onSubmit?: (message: string) => void;
  presetPrompts?: string[];
}

export function AnalysisConsole({
  children,
  inputPlaceholder = "Ask about this batch...",
  inputDisabled = true,
  presetPrompts,
}: AnalysisConsoleProps) {
  return (
    <div className="analysis-console">
      {/* Messages Area */}
      <div className="analysis-console__messages">
        {children}
      </div>

      {/* Preset Prompts */}
      {presetPrompts && presetPrompts.length > 0 && (
        <div className="analysis-console__presets">
          {presetPrompts.map((prompt, i) => (
            <button key={i} className="analysis-console__preset" disabled={inputDisabled}>
              {prompt}
            </button>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className="analysis-console__input-area">
        <div className="analysis-console__input-container">
          <input
            type="text"
            className="analysis-console__input"
            placeholder={inputPlaceholder}
            disabled={inputDisabled}
          />
          <button className="analysis-console__send" disabled={inputDisabled}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </div>
        {inputDisabled && (
          <div className="analysis-console__input-hint">
            Read-only · Select a batch to enable analysis
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * AnalysisMessage — Single message in the conversation
 */
interface AnalysisMessageProps {
  type: 'system' | 'user' | 'assistant';
  children: React.ReactNode;
  timestamp?: string;
}

export function AnalysisMessage({ type, children, timestamp }: AnalysisMessageProps) {
  return (
    <div className={`analysis-message analysis-message--${type}`}>
      <div className="analysis-message__content">
        {children}
      </div>
      {timestamp && (
        <div className="analysis-message__timestamp">{timestamp}</div>
      )}
    </div>
  );
}

/**
 * DataCard — Compact data display for the data panel
 */
interface DataCardProps {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export function DataCard({ title, children, actions }: DataCardProps) {
  return (
    <div className="data-card">
      <div className="data-card__header">
        <span className="data-card__title">{title}</span>
        {actions && <div className="data-card__actions">{actions}</div>}
      </div>
      <div className="data-card__content">
        {children}
      </div>
    </div>
  );
}

export default IntelligenceConsole;
