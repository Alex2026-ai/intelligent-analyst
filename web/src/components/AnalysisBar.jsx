import React, { useState } from 'react';
import { Send, Sparkles } from 'lucide-react';

/**
 * AnalysisBar — ChatGPT-style input bar for Assisted Analysis
 *
 * Sits at the bottom center of the dashboard.
 * Read-only for now (no API calls).
 */
export default function AnalysisBar({ batchId, disabled = false }) {
  const [query, setQuery] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);

  const presetPrompts = [
    'Explain flagged records',
    'Summarize audit findings',
    'Generate compliance summary',
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    // Read-only for now - no actual submission
  };

  return (
    <div className="analysis-bar-container">
      {/* Preset prompts - show when expanded */}
      {isExpanded && (
        <div className="analysis-bar-presets">
          {presetPrompts.map((prompt, i) => (
            <button
              key={i}
              className="analysis-bar-preset"
              onClick={() => setQuery(prompt)}
              disabled={disabled}
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      {/* Main input bar */}
      <form onSubmit={handleSubmit} className="analysis-bar">
        <button
          type="button"
          className="analysis-bar-toggle"
          onClick={() => setIsExpanded(!isExpanded)}
          title="Assisted Analysis"
        >
          <Sparkles size={18} />
        </button>

        <input
          type="text"
          className="analysis-bar-input"
          placeholder={
            batchId
              ? `Ask about batch ${batchId.slice(0, 8)}...`
              : "Ask about your data..."
          }
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
          onFocus={() => setIsExpanded(true)}
        />

        <button
          type="submit"
          className="analysis-bar-send"
          disabled={disabled || !query.trim()}
        >
          <Send size={18} />
        </button>
      </form>

    </div>
  );
}
