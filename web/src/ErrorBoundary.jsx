import React, { Component } from 'react';

/**
 * Global Error Boundary
 *
 * Catches unhandled JS errors in the component tree and renders
 * a simple fallback instead of a black/white screen.
 * Logs the error for debugging.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Log to console for debugging (production would send to telemetry)
    console.error('[ErrorBoundary] Uncaught error:', error);
    console.error('[ErrorBoundary] Component stack:', info?.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#020617',
            color: '#e2e8f0',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            padding: '2rem',
          }}
        >
          <div
            style={{
              maxWidth: '28rem',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              backgroundColor: 'rgba(239, 68, 68, 0.05)',
              padding: '2rem',
            }}
          >
            <h2 style={{ color: '#f87171', fontSize: '1.125rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              Page failed to load
            </h2>
            <p style={{ color: '#94a3b8', fontSize: '0.875rem', lineHeight: 1.6, marginBottom: '1.5rem' }}>
              An unexpected error occurred. This has been logged for investigation.
            </p>
            {this.state.error && (
              <pre
                style={{
                  fontSize: '0.75rem',
                  color: '#64748b',
                  backgroundColor: '#0f172a',
                  padding: '0.75rem',
                  marginBottom: '1.5rem',
                  overflow: 'auto',
                  maxHeight: '6rem',
                  border: '1px solid #1e293b',
                }}
              >
                {String(this.state.error.message || this.state.error).slice(0, 200)}
              </pre>
            )}
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                onClick={this.handleReload}
                style={{
                  height: '2.5rem',
                  padding: '0 1.25rem',
                  backgroundColor: '#0891b2',
                  color: '#fff',
                  border: 'none',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                }}
              >
                Refresh Page
              </button>
              <button
                onClick={this.handleGoHome}
                style={{
                  height: '2.5rem',
                  padding: '0 1.25rem',
                  backgroundColor: 'transparent',
                  color: '#94a3b8',
                  border: '1px solid #334155',
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                }}
              >
                Go to Home
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
