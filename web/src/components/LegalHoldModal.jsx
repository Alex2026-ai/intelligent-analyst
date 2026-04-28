/**
 * LEGAL HOLD MODAL (Days 14-16)
 *
 * Transactional UI for placing legal holds on batches.
 * Legal holds are legal actions requiring audit trail and confirmation.
 *
 * SECURITY:
 * - Mandatory reason field (10-500 chars)
 * - UI locked until backend confirms vault_objects_written_count > 0
 * - Server enforces role-based access (tenant_admin, platform_admin)
 */

import React, { useState } from 'react';
import {
  Lock, AlertTriangle, Loader2, X, ShieldCheck, FileText,
  CheckCircle, XCircle, Info
} from 'lucide-react';
import { placeLegalHold, releaseLegalHold } from '../api/client';

// ============================================================================
// CONSTANTS
// ============================================================================

const MIN_REASON_LENGTH = 10;
const MAX_REASON_LENGTH = 500;

const REASON_TEMPLATES = [
  { label: 'Regulatory Examination', value: 'Regulatory examination - preserving records per SEC Rule 17a-4' },
  { label: 'Internal Investigation', value: 'Internal investigation - preserving evidence for compliance review' },
  { label: 'Litigation Hold', value: 'Litigation hold - preserving records pending legal proceedings' },
  { label: 'Audit Requirement', value: 'External audit requirement - preserving records for auditor access' },
  { label: 'Custom Reason', value: '' },
];

// ============================================================================
// LEGAL HOLD MODAL COMPONENT
// ============================================================================

const LegalHoldModal = ({
  isOpen,
  onClose,
  batchId,
  batchFilename,
  currentHoldStatus,
  onHoldPlaced,
  onHoldReleased,
  canRelease = false,
}) => {
  // Form state
  const [reason, setReason] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [expiresAt, setExpiresAt] = useState('');

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [step, setStep] = useState('input'); // 'input' | 'confirm' | 'vaulting' | 'complete'

  // Derived state
  const isPlacingHold = currentHoldStatus !== 'ACTIVE';
  const isReleasingHold = currentHoldStatus === 'ACTIVE';

  // Reset state when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setReason('');
      setSelectedTemplate('');
      setExpiresAt('');
      setError(null);
      setSuccess(null);
      setStep('input');
    }
  }, [isOpen]);

  // ============================================================================
  // HANDLERS
  // ============================================================================

  const handleTemplateChange = (template) => {
    setSelectedTemplate(template);
    if (template) {
      setReason(template);
    }
  };

  const validateReason = () => {
    if (!reason || reason.trim().length < MIN_REASON_LENGTH) {
      setError(`A valid legal reason is required (minimum ${MIN_REASON_LENGTH} characters).`);
      return false;
    }
    if (reason.length > MAX_REASON_LENGTH) {
      setError(`Reason must be less than ${MAX_REASON_LENGTH} characters.`);
      return false;
    }
    return true;
  };

  const handleConfirm = () => {
    setError(null);
    if (!validateReason()) return;
    setStep('confirm');
  };

  const handlePlaceHold = async () => {
    setError(null);
    setStep('vaulting');
    setLoading(true);

    try {
      const result = await placeLegalHold(
        batchId,
        reason.trim(),
        expiresAt || undefined
      );

      if (!result.ok) {
        throw new Error(result.error || 'Failed to place legal hold');
      }

      // Verify vault objects were written
      const data = result.data;
      if (!data.vault_objects_written_count || data.vault_objects_written_count === 0) {
        throw new Error('Legal hold placed but vault objects not written - please verify');
      }

      setSuccess({
        message: 'Legal hold placed successfully',
        holdId: data.hold_id,
        vaultCount: data.vault_objects_written_count,
      });
      setStep('complete');

      // Notify parent
      if (onHoldPlaced) {
        onHoldPlaced(data);
      }
    } catch (err) {
      setError(err.message || 'Failed to place legal hold');
      setStep('input');
    } finally {
      setLoading(false);
    }
  };

  const handleReleaseHold = async () => {
    if (!canRelease) {
      setError('Only Platform Admins can release legal holds');
      return;
    }

    setError(null);
    if (!validateReason()) return;

    setStep('vaulting');
    setLoading(true);

    try {
      const result = await releaseLegalHold(batchId, reason.trim());

      if (!result.ok) {
        throw new Error(result.error || 'Failed to release legal hold');
      }

      setSuccess({
        message: 'Legal hold released',
        note: 'Vaulted evidence remains in WORM storage until retention expires.',
      });
      setStep('complete');

      // Notify parent
      if (onHoldReleased) {
        onHoldReleased(result.data);
      }
    } catch (err) {
      setError(err.message || 'Failed to release legal hold');
      setStep('input');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={step === 'input' ? onClose : undefined}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/50">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isReleasingHold ? 'bg-amber-500/10' : 'bg-cyan-500/10'}`}>
              <Lock className={`w-5 h-5 ${isReleasingHold ? 'text-amber-400' : 'text-cyan-400'}`} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                {isReleasingHold ? 'Release Legal Hold' : 'Place Legal Hold'}
              </h2>
              <p className="text-sm text-slate-400">{batchFilename || batchId}</p>
            </div>
          </div>
          {step === 'input' && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-slate-400" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step: Input */}
          {step === 'input' && (
            <div className="space-y-6">
              {/* Warning Banner */}
              <div className={`flex items-start gap-3 p-4 rounded-lg border ${
                isReleasingHold
                  ? 'bg-amber-500/5 border-amber-500/20'
                  : 'bg-cyan-500/5 border-cyan-500/20'
              }`}>
                <AlertTriangle className={`w-5 h-5 mt-0.5 ${
                  isReleasingHold ? 'text-amber-400' : 'text-cyan-400'
                }`} />
                <div className="text-sm">
                  {isReleasingHold ? (
                    <>
                      <p className="text-amber-400 font-medium">Release Warning</p>
                      <p className="text-slate-400 mt-1">
                        Releasing a legal hold does not delete vaulted evidence.
                        Records remain in WORM storage until retention expires.
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-cyan-400 font-medium">WORM Vaulting</p>
                      <p className="text-slate-400 mt-1">
                        This action will copy all evidence to immutable WORM storage.
                        A legal reason is required for the audit trail.
                      </p>
                    </>
                  )}
                </div>
              </div>

              {/* Reason Templates */}
              {!isReleasingHold && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Select Reason Template
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {REASON_TEMPLATES.map((template) => (
                      <button
                        key={template.label}
                        onClick={() => handleTemplateChange(template.value)}
                        className={`p-2 text-xs text-left rounded-lg border transition-colors ${
                          selectedTemplate === template.value
                            ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-400'
                            : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-600'
                        }`}
                      >
                        {template.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Reason Input */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {isReleasingHold ? 'Release Reason' : 'Legal Hold Reason'}
                  <span className="text-red-400 ml-1">*</span>
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={isReleasingHold
                    ? 'Enter reason for releasing the legal hold...'
                    : 'Enter the legal basis for placing this hold...'
                  }
                  rows={4}
                  className="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 resize-none"
                />
                <div className="flex justify-between mt-2 text-xs">
                  <span className={reason.length < MIN_REASON_LENGTH ? 'text-red-400' : 'text-slate-500'}>
                    Minimum {MIN_REASON_LENGTH} characters
                  </span>
                  <span className={reason.length > MAX_REASON_LENGTH ? 'text-red-400' : 'text-slate-500'}>
                    {reason.length}/{MAX_REASON_LENGTH}
                  </span>
                </div>
              </div>

              {/* Optional: Expiration (for placing hold only) */}
              {!isReleasingHold && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Expiration Date (Optional)
                  </label>
                  <input
                    type="datetime-local"
                    value={expiresAt}
                    onChange={(e) => setExpiresAt(e.target.value)}
                    className="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50"
                  />
                  <p className="mt-1 text-xs text-slate-500">
                    Leave empty for indefinite hold
                  </p>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                  <XCircle className="w-4 h-4 text-red-400" />
                  <span className="text-sm text-red-400">{error}</span>
                </div>
              )}
            </div>
          )}

          {/* Step: Confirm */}
          {step === 'confirm' && (
            <div className="space-y-6">
              <div className="text-center py-4">
                <div className="inline-flex p-4 rounded-full bg-amber-500/10 mb-4">
                  <AlertTriangle className="w-8 h-8 text-amber-400" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">
                  Confirm {isReleasingHold ? 'Release' : 'Legal Hold'}
                </h3>
                <p className="text-slate-400 max-w-sm mx-auto">
                  {isReleasingHold
                    ? 'Are you sure you want to release this legal hold?'
                    : 'This action will vault evidence to immutable WORM storage.'}
                </p>
              </div>

              <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Batch ID</span>
                  <span className="font-mono text-cyan-400">{batchId}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Action</span>
                  <span className="text-white">{isReleasingHold ? 'Release Hold' : 'Place Hold'}</span>
                </div>
                <div className="pt-2 border-t border-slate-700">
                  <span className="text-slate-500 text-sm">Reason:</span>
                  <p className="text-slate-300 text-sm mt-1">{reason}</p>
                </div>
              </div>
            </div>
          )}

          {/* Step: Vaulting */}
          {step === 'vaulting' && (
            <div className="text-center py-12">
              <Loader2 className="w-12 h-12 text-cyan-400 animate-spin mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-white mb-2">
                {isReleasingHold ? 'Releasing Hold...' : 'Vaulting Evidence...'}
              </h3>
              <p className="text-slate-400">
                {isReleasingHold
                  ? 'Updating hold status and audit trail'
                  : 'Copying evidence to immutable WORM storage'}
              </p>
              <p className="text-xs text-slate-500 mt-4">
                Please do not close this window
              </p>
            </div>
          )}

          {/* Step: Complete */}
          {step === 'complete' && success && (
            <div className="text-center py-8">
              <div className="inline-flex p-4 rounded-full bg-emerald-500/10 mb-4">
                <CheckCircle className="w-8 h-8 text-emerald-400" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                {success.message}
              </h3>
              {success.holdId && (
                <p className="text-slate-400">
                  Hold ID: <span className="font-mono text-cyan-400">{success.holdId}</span>
                </p>
              )}
              {success.vaultCount && (
                <p className="text-slate-400 mt-1">
                  {success.vaultCount} vault objects written
                </p>
              )}
              {success.note && (
                <p className="text-slate-500 text-sm mt-4 max-w-sm mx-auto">
                  {success.note}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-700 bg-slate-800/30">
          {step === 'input' && (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                disabled={reason.length < MIN_REASON_LENGTH}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  reason.length < MIN_REASON_LENGTH
                    ? 'bg-slate-700 text-slate-500 cursor-not-allowed'
                    : isReleasingHold
                    ? 'bg-amber-500 hover:bg-amber-600 text-black'
                    : 'bg-cyan-500 hover:bg-cyan-600 text-black'
                }`}
              >
                <Lock className="w-4 h-4" />
                {isReleasingHold ? 'Release Hold' : 'Place Hold'}
              </button>
            </>
          )}

          {step === 'confirm' && (
            <>
              <button
                onClick={() => setStep('input')}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                Back
              </button>
              <button
                onClick={isReleasingHold ? handleReleaseHold : handlePlaceHold}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${
                  isReleasingHold
                    ? 'bg-amber-500 hover:bg-amber-600 text-black'
                    : 'bg-emerald-500 hover:bg-emerald-600 text-black'
                }`}
              >
                <ShieldCheck className="w-4 h-4" />
                Confirm {isReleasingHold ? 'Release' : 'Hold'}
              </button>
            </>
          )}

          {step === 'complete' && (
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-slate-700 hover:bg-slate-600 text-white transition-colors"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default LegalHoldModal;
