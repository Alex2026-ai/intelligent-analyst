import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * AttestationFrameworkModal
 *
 * Sharp-edged disclosure modal for regulated industry cards.
 * Keyboard accessible, no external libraries.
 */
export default function AttestationFrameworkModal({ isOpen, onClose, industry }) {
  const modalRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previousFocusRef = useRef(null);

  // Store the element that triggered the modal
  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement;
      // Focus the close button when modal opens
      setTimeout(() => {
        closeButtonRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Handle escape key and trap focus
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }

      // Trap focus within modal
      if (e.key === 'Tab') {
        const focusableElements = modalRef.current?.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusableElements || focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey && document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        } else if (!e.shiftKey && document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    // Prevent body scroll when modal is open
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  // Return focus to trigger element on close
  useEffect(() => {
    if (!isOpen && previousFocusRef.current) {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const bullets = [
    'Immutable audit receipts suitable for examination and audit defense',
    'Deterministic lineage (reproducible pipeline behavior)',
    'Signature verification (integrity proof without implied trust)',
    'WORM retention anchoring (evidence persistence)',
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-slate-950/90"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        ref={modalRef}
        className="relative bg-slate-950 border border-slate-700 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto"
        style={{ borderRadius: '2px' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-800">
          <h2
            id="modal-title"
            className="font-mono text-sm uppercase tracking-wider text-amber-400"
          >
            [ ATTESTATION_FRAMEWORK ]
          </h2>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="w-10 h-10 flex items-center justify-center border border-slate-700 hover:border-slate-500 hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500/50"
            style={{ borderRadius: '2px' }}
            aria-label="Close modal"
          >
            <X size={18} className="text-slate-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Industry Header */}
          <div className="mb-6">
            <div className="font-mono text-xs text-slate-500 mb-2">
              {'>'} ATTESTATION_FRAMEWORK: <span className="text-white">{industry?.toUpperCase()}</span>
            </div>
          </div>

          {/* Bullets */}
          <ul className="space-y-4 mb-8">
            {bullets.map((bullet, index) => (
              <li key={index} className="flex items-start gap-3">
                <div className="w-1.5 h-1.5 bg-amber-500 mt-2 flex-shrink-0" />
                <span className="text-slate-300 text-sm leading-relaxed">{bullet}</span>
              </li>
            ))}
          </ul>

          {/* Footer microline */}
          <div className="pt-4 border-t border-slate-800">
            <div className="font-mono text-xs text-slate-500 tracking-wider">
              TRANSPARENCY: <span className="text-emerald-500">ENFORCED</span>
              {' • '}
              INTEGRITY: <span className="text-emerald-500">VERIFIED</span>
              {' • '}
              PII: <span className="text-amber-500">REDACTED</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
