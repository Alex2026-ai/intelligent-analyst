/**
 * TRUST SEAL COMPONENT (Days 21-30)
 *
 * "McAfee-style" verification badge that displays batch verification status.
 * Interactive - clicking opens a modal with real-time Certainty Report.
 *
 * Features:
 * - Visual verification badge (Verified/Unverified/Pending)
 * - ESG/Energy rating indicator
 * - Legal hold status indicator
 * - Click to view full verification details
 * - Embeddable via URL parameter
 *
 * Usage:
 *   <TrustSeal batchId="BATCH-ABC123" size="large" />
 *   <TrustSeal batchId="BATCH-ABC123" compact={true} />
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck, ShieldAlert, ShieldX, Shield,
  Leaf, Flame, Zap, Lock, ExternalLink, X,
  CheckCircle, XCircle, Clock, Hash, Key,
  Loader2, AlertTriangle, RefreshCw, Copy, Check
} from 'lucide-react';

// ============================================================================
// VERIFICATION STATUS TYPES
// ============================================================================

const VerificationStatus = {
  VERIFIED: 'VERIFIED',
  UNVERIFIED: 'UNVERIFIED',
  PENDING: 'PENDING',
  ERROR: 'ERROR',
  NOT_FOUND: 'NOT_FOUND',
  LOADING: 'LOADING',
};

const ESGRatings = {
  LOW_CARBON: { label: 'Low Carbon', color: 'emerald', icon: Leaf },
  MODERATE: { label: 'Moderate', color: 'amber', icon: Zap },
  HIGH_ENERGY: { label: 'High Energy', color: 'red', icon: Flame },
  UNKNOWN: { label: 'Unknown', color: 'slate', icon: Zap },
};

// ============================================================================
// API FUNCTIONS
// ============================================================================

const fetchVerification = async (batchId) => {
  try {
    // Use the public verification endpoint (no auth required)
    const apiBase = import.meta.env.VITE_API_BASE_URL || '';
    const url = `${apiBase}/verify/${encodeURIComponent(batchId)}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      if (response.status === 404) {
        return { status: VerificationStatus.NOT_FOUND };
      }
      if (response.status === 429) {
        return { status: VerificationStatus.ERROR, error: 'Rate limited. Please try again.' };
      }
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Verification fetch failed:', error);
    return {
      status: VerificationStatus.ERROR,
      error: error.message || 'Failed to fetch verification',
    };
  }
};

// ============================================================================
// TRUST SEAL BADGE COMPONENT
// ============================================================================

const TrustSealBadge = ({
  status,
  esgRating,
  legalHoldActive,
  size = 'medium',
  onClick,
  loading = false,
  customLabel = null,
}) => {
  const sizeStyles = {
    small: 'px-2 py-1 text-xs gap-1',
    medium: 'px-3 py-2 text-sm gap-2',
    large: 'px-4 py-3 text-base gap-3',
  };

  const iconSizes = {
    small: 'w-4 h-4',
    medium: 'w-5 h-5',
    large: 'w-6 h-6',
  };

  const statusStyles = {
    [VerificationStatus.VERIFIED]: {
      bg: 'bg-gradient-to-r from-emerald-500/20 to-cyan-500/20',
      border: 'border-emerald-500/50',
      text: 'text-emerald-400',
      icon: ShieldCheck,
      label: 'Verified by IA',
    },
    [VerificationStatus.UNVERIFIED]: {
      bg: 'bg-gradient-to-r from-red-500/20 to-orange-500/20',
      border: 'border-red-500/50',
      text: 'text-red-400',
      icon: ShieldX,
      label: 'Unverified',
    },
    [VerificationStatus.PENDING]: {
      bg: 'bg-gradient-to-r from-amber-500/20 to-yellow-500/20',
      border: 'border-amber-500/50',
      text: 'text-amber-400',
      icon: Clock,
      label: 'Processing',
    },
    [VerificationStatus.ERROR]: {
      bg: 'bg-gradient-to-r from-slate-500/20 to-slate-600/20',
      border: 'border-slate-500/50',
      text: 'text-slate-400',
      icon: ShieldAlert,
      label: 'Error',
    },
    [VerificationStatus.NOT_FOUND]: {
      bg: 'bg-gradient-to-r from-slate-500/20 to-slate-600/20',
      border: 'border-slate-500/50',
      text: 'text-slate-400',
      icon: ShieldAlert,
      label: 'Not Found',
    },
    [VerificationStatus.LOADING]: {
      bg: 'bg-gradient-to-r from-cyan-500/20 to-blue-500/20',
      border: 'border-cyan-500/50',
      text: 'text-cyan-400',
      icon: Shield,
      label: 'Checking...',
    },
  };

  const style = statusStyles[status] || statusStyles[VerificationStatus.ERROR];
  const Icon = style.icon;
  const EsgIcon = ESGRatings[esgRating]?.icon || Zap;

  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`
        flex items-center ${sizeStyles[size]}
        ${style.bg} ${style.border} border rounded-lg
        ${style.text} font-medium
        hover:opacity-90 transition-all cursor-pointer
        shadow-lg hover:shadow-xl
        disabled:cursor-not-allowed disabled:opacity-70
      `}
    >
      {loading ? (
        <Loader2 className={`${iconSizes[size]} animate-spin`} />
      ) : (
        <Icon className={iconSizes[size]} />
      )}

      <div className="flex flex-col items-start leading-tight">
        <span className="font-semibold">{customLabel || style.label}</span>
        {status === VerificationStatus.VERIFIED && esgRating && (
          <span className="text-[10px] opacity-75 flex items-center gap-1">
            <EsgIcon className="w-3 h-3" />
            {ESGRatings[esgRating]?.label || esgRating}
          </span>
        )}
      </div>

      {legalHoldActive && (
        <div className="ml-1 px-1.5 py-0.5 bg-amber-500/20 border border-amber-500/30 rounded text-[10px] text-amber-400 flex items-center gap-1">
          <Lock className="w-3 h-3" />
          Held
        </div>
      )}

      <ExternalLink className={`w-3 h-3 opacity-50 ml-1`} />
    </button>
  );
};

// ============================================================================
// VERIFICATION MODAL COMPONENT
// ============================================================================

const VerificationModal = ({
  isOpen,
  onClose,
  batchId,
  verificationData,
  loading,
  onRefresh,
}) => {
  const [copiedField, setCopiedField] = useState(null);

  if (!isOpen) return null;

  const status = verificationData?.status || VerificationStatus.LOADING;
  const verification = verificationData?.verification || {};
  const trustSummary = verificationData?.trust_summary || {};
  const legalHold = verificationData?.legal_hold;

  const copyToClipboard = (text, field) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const statusColors = {
    [VerificationStatus.VERIFIED]: 'text-emerald-400',
    [VerificationStatus.UNVERIFIED]: 'text-red-400',
    [VerificationStatus.PENDING]: 'text-amber-400',
    [VerificationStatus.ERROR]: 'text-slate-400',
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-gradient-to-r from-slate-800/80 to-slate-900/80">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${
              status === VerificationStatus.VERIFIED
                ? 'bg-emerald-500/20'
                : 'bg-slate-700/50'
            }`}>
              <ShieldCheck className={`w-6 h-6 ${statusColors[status] || 'text-slate-400'}`} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Certainty Report</h2>
              <p className="text-sm text-slate-400 font-mono">{batchId}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onRefresh}
              disabled={loading}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors text-slate-400 hover:text-white"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin mb-4" />
              <p className="text-slate-400">Verifying cryptographic signatures...</p>
            </div>
          ) : (
            <>
              {/* Verification Status */}
              <div className={`p-4 rounded-lg border ${
                status === VerificationStatus.VERIFIED
                  ? 'bg-emerald-500/10 border-emerald-500/30'
                  : status === VerificationStatus.UNVERIFIED
                  ? 'bg-red-500/10 border-red-500/30'
                  : 'bg-slate-800/50 border-slate-700'
              }`}>
                <div className="flex items-center gap-3">
                  {status === VerificationStatus.VERIFIED ? (
                    <CheckCircle className="w-6 h-6 text-emerald-400" />
                  ) : status === VerificationStatus.UNVERIFIED ? (
                    <XCircle className="w-6 h-6 text-red-400" />
                  ) : (
                    <AlertTriangle className="w-6 h-6 text-amber-400" />
                  )}
                  <div>
                    <div className={`text-lg font-semibold ${statusColors[status]}`}>
                      {status === VerificationStatus.VERIFIED
                        ? 'Cryptographically Verified'
                        : status === VerificationStatus.UNVERIFIED
                        ? 'Verification Failed'
                        : status}
                    </div>
                    <div className="text-sm text-slate-400">
                      {status === VerificationStatus.VERIFIED
                        ? 'Evidence integrity confirmed via KMS signature'
                        : verificationData?.error || 'Unable to verify'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Verification Details */}
              {verification && Object.keys(verification).length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-medium text-slate-300">Verification Details</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-slate-800/50 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <Key className="w-4 h-4 text-cyan-400" />
                        <span className="text-xs text-slate-500">Signature</span>
                      </div>
                      <div className={`text-sm font-medium ${
                        verification.signature_valid ? 'text-emerald-400' : 'text-red-400'
                      }`}>
                        {verification.signature_valid ? 'Valid' : 'Invalid'}
                      </div>
                    </div>
                    <div className="bg-slate-800/50 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <Hash className="w-4 h-4 text-violet-400" />
                        <span className="text-xs text-slate-500">Hash Chain</span>
                      </div>
                      <div className={`text-sm font-medium ${
                        verification.hash_chain_valid ? 'text-emerald-400' : 'text-red-400'
                      }`}>
                        {verification.hash_chain_valid
                          ? `Valid (${verification.hash_chain_length || 0} records)`
                          : 'Not Available'}
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-slate-500">
                    Algorithm: {verification.signature_algorithm || 'ECDSA_P256_SHA256'}
                  </div>
                </div>
              )}

              {/* Trust Summary */}
              {trustSummary && Object.keys(trustSummary).length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-medium text-slate-300">Trust Summary</h3>
                  <div className="bg-slate-800/50 rounded-lg p-4 space-y-3">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-xs text-slate-500 mb-1">Processed</div>
                        <div className="text-sm text-white">{trustSummary.processed_at || 'N/A'}</div>
                      </div>
                      <div>
                        <div className="text-xs text-slate-500 mb-1">Config Version</div>
                        <div className="text-sm text-white">{trustSummary.config_version || 'N/A'}</div>
                      </div>
                      <div>
                        <div className="text-xs text-slate-500 mb-1">Total Records</div>
                        <div className="text-sm text-white">{trustSummary.total_records?.toLocaleString() || 'N/A'}</div>
                      </div>
                      <div>
                        <div className="text-xs text-slate-500 mb-1">ESG Rating</div>
                        <div className={`text-sm font-medium ${
                          trustSummary.esg_rating === 'LOW_CARBON'
                            ? 'text-emerald-400'
                            : trustSummary.esg_rating === 'MODERATE'
                            ? 'text-amber-400'
                            : 'text-red-400'
                        }`}>
                          {ESGRatings[trustSummary.esg_rating]?.label || trustSummary.esg_rating}
                        </div>
                      </div>
                    </div>
                    {trustSummary.resolution_quality && (
                      <div className="pt-3 border-t border-slate-700">
                        <div className="text-xs text-slate-500 mb-2">Resolution Quality</div>
                        <div className="flex gap-4">
                          <div className="flex-1 bg-slate-900/50 rounded p-2 text-center">
                            <div className="text-lg font-semibold text-emerald-400">
                              {trustSummary.resolution_quality.auto_resolved_pct}%
                            </div>
                            <div className="text-xs text-slate-500">Auto-Resolved</div>
                          </div>
                          <div className="flex-1 bg-slate-900/50 rounded p-2 text-center">
                            <div className="text-lg font-semibold text-amber-400">
                              {trustSummary.resolution_quality.human_review_pct}%
                            </div>
                            <div className="text-xs text-slate-500">Human Review</div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Legal Hold Status */}
              {legalHold && (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <Lock className="w-5 h-5 text-amber-400" />
                    <div>
                      <div className="text-sm font-medium text-amber-400">Legal Hold Active</div>
                      <div className="text-xs text-slate-400">
                        Evidence is immutable until {legalHold.immutable_until || 'retention expires'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Batch ID */}
              <div className="flex items-center justify-between bg-slate-800/50 rounded-lg p-3">
                <div>
                  <div className="text-xs text-slate-500">Batch ID</div>
                  <div className="text-sm font-mono text-cyan-400">{batchId}</div>
                </div>
                <button
                  onClick={() => copyToClipboard(batchId, 'batchId')}
                  className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
                >
                  {copiedField === 'batchId' ? (
                    <Check className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <Copy className="w-4 h-4 text-slate-400" />
                  )}
                </button>
              </div>

              {/* Verification Timestamp */}
              <div className="text-center text-xs text-slate-500">
                Verified at: {verificationData?.timestamp_utc || new Date().toISOString()}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 bg-slate-800/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <span>Powered by Intelligent Analyst</span>
            </div>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-white transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// MAIN TRUST SEAL COMPONENT
// ============================================================================

const TrustSeal = ({
  batchId,
  size = 'medium',
  compact = false,
  autoFetch = true,
  onVerificationChange,
  href = null,        // If provided, opens URL in new tab instead of modal
  label = null,       // Custom label override
  variant = null,     // 'compact' | 'badge' | null
}) => {
  const [verificationData, setVerificationData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);

  const fetchData = useCallback(async () => {
    if (!batchId) return;

    setLoading(true);
    try {
      const data = await fetchVerification(batchId);
      setVerificationData(data);
      if (onVerificationChange) {
        onVerificationChange(data);
      }
    } catch (error) {
      console.error('Failed to fetch verification:', error);
      setVerificationData({
        status: VerificationStatus.ERROR,
        error: error.message,
      });
    } finally {
      setLoading(false);
    }
  }, [batchId, onVerificationChange]);

  useEffect(() => {
    if (autoFetch && batchId) {
      fetchData();
    }
  }, [autoFetch, batchId, fetchData]);

  // Handle click - either open URL in new tab or open modal
  const handleClick = () => {
    if (href) {
      // Open verification URL in new tab
      window.open(href, '_blank', 'noopener,noreferrer');
    } else {
      // Open modal
      setShowModal(true);
      if (!verificationData || verificationData.status === VerificationStatus.ERROR) {
        fetchData();
      }
    }
  };

  const status = loading
    ? VerificationStatus.LOADING
    : verificationData?.status || VerificationStatus.LOADING;

  const esgRating = verificationData?.trust_summary?.esg_rating;
  const legalHoldActive = verificationData?.legal_hold?.active;

  // Determine if compact mode (either via prop or variant)
  const isCompact = compact || variant === 'compact';

  if (isCompact) {
    // Compact mode - just the shield icon
    return (
      <>
        <button
          onClick={handleClick}
          className={`p-1.5 rounded-lg transition-all ${
            status === VerificationStatus.VERIFIED
              ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
              : status === VerificationStatus.LOADING
              ? 'bg-cyan-500/20 text-cyan-400'
              : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
          }`}
          title={label || `Verification: ${status}`}
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : status === VerificationStatus.VERIFIED ? (
            <ShieldCheck className="w-4 h-4" />
          ) : (
            <ShieldAlert className="w-4 h-4" />
          )}
        </button>

        {/* Only show modal if no href */}
        {!href && (
          <VerificationModal
            isOpen={showModal}
            onClose={() => setShowModal(false)}
            batchId={batchId}
            verificationData={verificationData}
            loading={loading}
            onRefresh={fetchData}
          />
        )}
      </>
    );
  }

  return (
    <>
      <TrustSealBadge
        status={status}
        esgRating={esgRating}
        legalHoldActive={legalHoldActive}
        size={size}
        loading={loading}
        onClick={handleClick}
        customLabel={label}
      />

      {/* Only show modal if no href */}
      {!href && (
        <VerificationModal
          isOpen={showModal}
          onClose={() => setShowModal(false)}
          batchId={batchId}
          verificationData={verificationData}
          loading={loading}
          onRefresh={fetchData}
        />
      )}
    </>
  );
};

export default TrustSeal;
export { TrustSealBadge, VerificationModal, VerificationStatus, ESGRatings };
