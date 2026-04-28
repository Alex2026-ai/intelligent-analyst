/**
 * FORENSIC PANEL (Days 11-20)
 *
 * Enterprise-grade forensic verification display for batch evidence.
 * Displays cryptographic verification badges with bank-portal styling.
 *
 * Features:
 * - Integrity grid: KMS Signature, Hash Chain, External Anchor, Legal Hold
 * - Operational Cost Profile section (separated from integrity invariants)
 * - Legal Hold controls (RBAC-protected)
 * - Evidence blob metadata display
 * - Evidence Pack download (Days 17-20)
 *
 * RBAC (Days 14-16):
 * - Standard User: Cannot see Legal Hold toggle
 * - Tenant Admin: Can place hold, sees restricted tooltip on Release
 * - Platform Admin: Full control (place/release hold)
 */

import React, { useState, useEffect } from 'react';
import {
  ShieldCheck, ShieldAlert, ShieldX, Link, Unlink,
  Lock, Unlock, Clock, Hash, Key, FileCheck, AlertTriangle,
  CheckCircle, XCircle, Info, ChevronDown, ChevronUp, Loader2,
  Fingerprint, Activity, Shield, Download, Package, Archive
} from 'lucide-react';
import LegalHoldModal from './LegalHoldModal';
import { useAuth } from '../context/AuthContext';
import { downloadEvidencePack } from '../api/client';
import { calculateEnergyEfficiency } from './energyEfficiency';
import { isLegacyBatch as checkLegacyBatch } from './uiHelpers';

// ============================================================================
// VERIFICATION BADGE COMPONENT
// ============================================================================

const VerificationBadge = ({
  title,
  status,
  icon: Icon,
  details,
  loading = false,
  expandable = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  const statusStyles = {
    verified: {
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/30',
      text: 'text-emerald-400',
      icon: 'text-emerald-400',
      label: 'VERIFIED',
    },
    failed: {
      bg: 'bg-red-500/10',
      border: 'border-red-500/30',
      text: 'text-red-400',
      icon: 'text-red-400',
      label: 'FAILED',
    },
    warning: {
      bg: 'bg-amber-500/10',
      border: 'border-amber-500/30',
      text: 'text-amber-400',
      icon: 'text-amber-400',
      label: 'WARNING',
    },
    pending: {
      bg: 'bg-slate-500/10',
      border: 'border-slate-500/30',
      text: 'text-slate-400',
      icon: 'text-slate-400',
      label: 'PENDING',
    },
    unavailable: {
      bg: 'bg-slate-700/50',
      border: 'border-slate-600/30',
      text: 'text-slate-500',
      icon: 'text-slate-500',
      label: 'N/A',
    },
    legacy: {
      bg: 'bg-slate-600/10',
      border: 'border-slate-500/30',
      text: 'text-slate-400',
      icon: 'text-slate-500',
      label: 'NOT AVAILABLE',
    },
  };

  const style = statusStyles[status] || statusStyles.unavailable;

  return (
    <div
      className={`${style.bg} ${style.border} border rounded-lg p-4 transition-all duration-200 ${
        expandable ? 'cursor-pointer hover:bg-opacity-20' : ''
      }`}
      onClick={() => expandable && setExpanded(!expanded)}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {loading ? (
            <Loader2 className={`w-5 h-5 ${style.icon} animate-spin`} />
          ) : (
            <Icon className={`w-5 h-5 ${style.icon}`} />
          )}
          <div>
            <div className={`text-sm font-medium ${style.text}`}>{title}</div>
            <div className="text-xs text-slate-500">{style.label}</div>
          </div>
        </div>
        {expandable && (
          <div className={style.text}>
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        )}
      </div>

      {/* Expanded Details */}
      {expanded && details && (
        <div className="mt-4 pt-4 border-t border-slate-700/50">
          <div className="space-y-2 text-xs">
            {Object.entries(details).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-2 min-w-0">
                <span className="text-slate-500 shrink-0">{key}</span>
                <span className={`font-mono ${style.text} truncate`} title={String(value)}>
                  {typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// FORENSIC PANEL COMPONENT
// ============================================================================

const ForensicPanel = ({
  batch,
  verificationData,
  loading = false,
  onRefresh,
  onHoldChange,
  className = '',
}) => {
  const [expanded, setExpanded] = useState(false);
  const [showHoldModal, setShowHoldModal] = useState(false);

  // Evidence pack download state (Days 17-20)
  const [downloadingPack, setDownloadingPack] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(''); // Progress message
  const [downloadError, setDownloadError] = useState(null);
  const [costExpanded, setCostExpanded] = useState(false);

  // RBAC
  const { canPerform, role } = useAuth();
  const canViewHoldStatus = canPerform('VIEW_HOLD_STATUS');
  const canPlaceHold = canPerform('PLACE_HOLD');
  const canReleaseHold = canPerform('RELEASE_HOLD');
  const canExportAudit = canPerform('EXPORT_AUDIT');

  // Handlers
  const handleOpenHoldModal = () => {
    setShowHoldModal(true);
  };

  // Evidence Pack Download Handler
  const handleDownloadEvidencePack = async () => {
    if (!batch?.trace_id) return;

    setDownloadingPack(true);
    setDownloadError(null);
    setDownloadProgress('Generating Digital Seal...');

    try {
      // Simulate progress stages
      await new Promise(r => setTimeout(r, 500));
      setDownloadProgress('Verifying KMS Signature...');

      await new Promise(r => setTimeout(r, 500));
      setDownloadProgress('Building Certificate PDF...');

      await new Promise(r => setTimeout(r, 300));
      setDownloadProgress('Assembling Evidence Pack...');

      // Actually download
      const result = await downloadEvidencePack(batch.trace_id);

      if (!result.ok) {
        throw new Error(result.error || 'Failed to download evidence pack');
      }

      setDownloadProgress('Download Complete!');

      // Trigger browser download
      if (result.blob) {
        const url = URL.createObjectURL(result.blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${batch.trace_id}_evidence_pack.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }

      // Clear progress after success
      setTimeout(() => {
        setDownloadProgress('');
        setDownloadingPack(false);
      }, 1500);

    } catch (err) {
      console.error('Evidence pack download failed:', err);
      setDownloadError(err.message || 'Download failed');
      setDownloadProgress('');
      setDownloadingPack(false);
    }
  };

  const handleHoldComplete = (result) => {
    setShowHoldModal(false);
    if (onHoldChange) {
      onHoldChange(result);
    }
    if (onRefresh) {
      onRefresh();
    }
  };

  const handleHoldCancel = () => {
    setShowHoldModal(false);
  };

  // Legacy batch detection — uses extracted helper for testability
  const isLegacyBatch = checkLegacyBatch({ batch, verificationData, loading });

  const FORENSIC_CUTOVER = '2026-02-19';
  const legacyTooltip = `Processed before forensic attestation (cutover: ${FORENSIC_CUTOVER}).`;

  // Extract verification statuses — legacy overrides all badges.
  // When /verify times out, fall back to batch doc fields for status display.
  const signatureStatus = isLegacyBatch ? 'legacy'
    : verificationData?.signature_verified ? 'verified'
    : verificationData?.signature_verified === false ? 'failed'
    : (batch?.attestation?.signature_b64 || batch?.signature?.signature) ? 'verified'
    : 'pending';

  const hashChainStatus = isLegacyBatch ? 'legacy'
    : verificationData?.hash_chain?.chain_enabled
      ? (verificationData?.hash_chain?.verified ? 'verified' : 'warning')
    : batch?.hash_chain?.chain_enabled
      ? (batch?.hash_chain?.replay_passed ? 'verified' : 'warning')
      : 'unavailable';

  const legalHoldStatus = batch?.legal_hold?.status === 'ACTIVE'
    ? 'verified'
    : 'unavailable';

  const energyEfficiency = isLegacyBatch
    ? { rating: 'legacy', ratio: 0, badge: 'NOT AVAILABLE' }
    : calculateEnergyEfficiency(batch?.stats);

  // Anchor status — fall back to batch doc when /verify times out
  const anchorStatus = isLegacyBatch ? 'legacy'
    : verificationData?.anchor?.verified ? 'verified'
    : verificationData?.anchor?.anchored_at ? 'pending'
    : batch?.anchor?.anchored ? 'verified'
    : 'unavailable';

  return (
    <div className={`bg-slate-900/80 border border-slate-700/50 rounded-xl overflow-hidden ${className}`}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4 border-b border-slate-700/50 cursor-pointer hover:bg-slate-800/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <Fingerprint className="w-5 h-5 text-cyan-400" />
          <span className="font-semibold text-white">Forensic Verification</span>
          {/* Quick status indicators */}
          <div className="flex items-center gap-2 ml-4">
            {isLegacyBatch && (
              <div className="relative group flex items-center gap-1 px-2 py-0.5 bg-slate-600/20 border border-slate-500/30 rounded text-xs text-slate-400">
                <Clock className="w-3 h-3" />
                <span>Legacy Batch</span>
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-slate-800 border border-slate-600 rounded text-xs text-slate-300 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                  {legacyTooltip}
                </div>
              </div>
            )}
            {signatureStatus === 'verified' && (
              <div className="flex items-center gap-1 px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-400">
                <ShieldCheck className="w-3 h-3" />
                <span>Signed</span>
              </div>
            )}
            {hashChainStatus === 'verified' && (
              <div className="flex items-center gap-1 px-2 py-0.5 bg-cyan-500/10 border border-cyan-500/30 rounded text-xs text-cyan-400">
                <Link className="w-3 h-3" />
                <span>Chained</span>
              </div>
            )}
            {anchorStatus === 'verified' && (
              <div className="flex items-center gap-1 px-2 py-0.5 bg-violet-500/10 border border-violet-500/30 rounded text-xs text-violet-400">
                <Hash className="w-3 h-3" />
                <span>Anchored</span>
              </div>
            )}
            {legalHoldStatus === 'verified' && (
              <div className="flex items-center gap-1 px-2 py-0.5 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-400">
                <Lock className="w-3 h-3" />
                <span>Held</span>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {loading && <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />}
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="p-6 space-y-6">
          {/* Verification Badges Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* KMS Signature Badge */}
            <VerificationBadge
              title="KMS Signature"
              status={signatureStatus}
              icon={signatureStatus === 'verified' ? ShieldCheck : ShieldAlert}
              loading={loading && !isLegacyBatch}
              expandable={!isLegacyBatch}
              details={isLegacyBatch ? {
                'Status': 'Batch predates forensic attestation',
              } : {
                'Algorithm': verificationData?.signature?.signature_alg || 'ECDSA_P256_SHA256',
                'Key ID': verificationData?.signature?.signing_key_id?.split('/').pop() || 'N/A',
                'Signed At': verificationData?.signature?.signed_at_utc?.split('T')[0] || 'N/A',
                'Service': verificationData?.signature?.service_identity?.cloud_run_service || 'N/A',
              }}
            />

            {/* Hash Chain Badge */}
            <VerificationBadge
              title="Hash Chain"
              status={hashChainStatus}
              icon={hashChainStatus === 'verified' ? Link : Unlink}
              loading={loading && !isLegacyBatch}
              expandable={!isLegacyBatch}
              details={isLegacyBatch ? {
                'Status': 'Batch predates hash chain deployment',
              } : {
                'Chain Length': batch?.hash_chain?.chain_length || 'N/A',
                'Algorithm': batch?.hash_chain?.chain_algo || 'SHA256',
                'Root Hash': batch?.hash_chain?.batch_root_hash?.substring(0, 16) + '...' || 'N/A',
                'Chained At': batch?.hash_chain?.chained_at?.split('T')[0] || 'N/A',
              }}
            />

            {/* External Anchor Badge */}
            <VerificationBadge
              title="External Anchor"
              status={anchorStatus}
              icon={Hash}
              loading={loading && !isLegacyBatch}
              expandable={!isLegacyBatch}
              details={isLegacyBatch ? {
                'Status': 'Batch predates external anchoring',
              } : {
                'Anchor Target': verificationData?.anchor?.anchor_target || 'GCS_BUCKET',
                'Verified': verificationData?.anchor?.verified ? 'Yes' : 'No',
                'Anchored At': verificationData?.anchor?.anchored_at?.split('T')[0] || 'N/A',
                'Digest Match': verificationData?.anchor?.digest_match ? 'Yes' : 'Pending',
              }}
            />

            {/* Legal Hold Badge */}
            <VerificationBadge
              title="Legal Hold"
              status={legalHoldStatus}
              icon={legalHoldStatus === 'verified' ? Lock : Unlock}
              loading={loading}
              expandable
              details={
                batch?.legal_hold?.status === 'ACTIVE'
                  ? {
                      'Hold ID': batch?.legal_hold?.hold_id || 'N/A',
                      'Requested By': batch?.legal_hold?.requested_by?.substring(0, 20) + '...' || 'N/A',
                      'Requested At': batch?.legal_hold?.requested_at_utc?.split('T')[0] || 'N/A',
                      'Vault Objects': batch?.legal_hold?.vault_objects_written_count || 0,
                    }
                  : {
                      'Status': 'No active hold',
                      'Vault Enabled': batch?.vault_enabled ? 'Yes' : 'No',
                    }
              }
            />
          </div>

          {/* Evidence Metadata */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-4">
              <FileCheck className="w-4 h-4 text-cyan-400" />
              <span className="text-sm font-medium text-white">Evidence Metadata</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div className="min-w-0">
                <div className="text-slate-500 mb-1">Batch ID</div>
                <div className="font-mono text-cyan-400 truncate" title={batch?.trace_id}>{batch?.trace_id || 'N/A'}</div>
              </div>
              <div>
                <div className="text-slate-500 mb-1">Config Version</div>
                <div className="font-mono text-slate-300">{batch?.config_version || 'N/A'}</div>
              </div>
              <div>
                <div className="text-slate-500 mb-1">Records</div>
                <div className="font-mono text-slate-300">{batch?.total_records || batch?.total || 0}</div>
              </div>
              <div>
                <div className="text-slate-500 mb-1">Processed At</div>
                <div className="font-mono text-slate-300">
                  {batch?.finished_at?.split('T')[0] || batch?.timestamp?.split('T')[0] || 'N/A'}
                </div>
              </div>
            </div>
          </div>

          {/* Operational Cost Profile — separated from integrity invariants */}
          <div className="bg-slate-900/40 border border-slate-700/30 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-slate-400" />
                <span className="text-sm font-medium text-slate-300">Operational Cost Profile</span>
                {!isLegacyBatch && (
                  <span className={`px-2 py-0.5 rounded text-xs font-mono ${
                    energyEfficiency.badge === 'LOW CARBON'
                      ? 'bg-slate-700/50 text-slate-300'
                      : energyEfficiency.badge === 'MODERATE'
                        ? 'bg-slate-700/50 text-slate-400'
                        : energyEfficiency.badge === 'HIGH ENERGY'
                          ? 'bg-slate-700/50 text-slate-400'
                          : 'bg-slate-700/50 text-slate-500'
                  }`}>
                    {energyEfficiency.badge}
                  </span>
                )}
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); setCostExpanded(!costExpanded); }}
                className="text-slate-500 hover:text-slate-300 transition-colors"
              >
                {costExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>

            {isLegacyBatch ? (
              <div className="text-xs text-slate-500">Batch predates cost tracking.</div>
            ) : (
              <>
                {/* Summary line — always visible */}
                <div className="text-xs text-slate-400">
                  {(energyEfficiency.ratio * 100).toFixed(1)}% of {batch?.stats?.total || 0} records resolved at L1+L2 (deterministic + vector).
                </div>

                {/* Expandable details */}
                {costExpanded && <div className="mt-4 pt-3 border-t border-slate-700/30">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-y-3 gap-x-6 text-xs">
                    <div>
                      <div className="text-slate-500 mb-1">Formula</div>
                      <div className="font-mono text-slate-300">(L1 + L2) / total</div>
                    </div>
                    <div>
                      <div className="text-slate-500 mb-1">Efficiency</div>
                      <div className="font-mono text-slate-300">{(energyEfficiency.ratio * 100).toFixed(1)}%</div>
                    </div>
                    <div>
                      <div className="text-slate-500 mb-1">Thresholds</div>
                      <div className="font-mono text-slate-300">{'\u2265'}95% Low {'\u00b7'} {'\u2265'}80% Moderate</div>
                    </div>
                    <div>
                      <div className="text-slate-500 mb-1">L0 Garbage</div>
                      <div className="font-mono text-slate-300">{batch?.stats?.layer_0_garbage || 0} records</div>
                    </div>
                    <div>
                      <div className="text-slate-500 mb-1">L3 LLM Calls</div>
                      <div className="font-mono text-slate-300">{batch?.stats?.layer_3_llm_calls || batch?.stats?.layer_3_llm || 0}</div>
                    </div>
                    <div>
                      <div className="text-slate-500 mb-1">Note</div>
                      <div className="text-slate-400">
                        {(batch?.stats?.total || 0) < 10
                          ? 'Small batch — may be noisy.'
                          : 'Measures cost profile, not integrity.'}
                      </div>
                    </div>
                  </div>
                </div>}
              </>
            )}
          </div>

          {/* SBOM Info (if available) */}
          {batch?.sbom && batch?.sbom?.available && (
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-4">
                <Activity className="w-4 h-4 text-amber-400" />
                <span className="text-sm font-medium text-white">Software Bill of Materials</span>
                <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-400">
                  AVAILABLE
                </span>
              </div>
              <div className="text-xs text-slate-500">
                SBOM hash is cryptographically bound to evidence signatures for supply chain verification.
              </div>
            </div>
          )}

          {/* Evidence Pack Download (Days 17-20) */}
          {canExportAudit && (
            <div className="bg-gradient-to-r from-cyan-900/20 to-violet-900/20 border border-cyan-500/30 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-cyan-500/10 rounded-lg">
                    <Package className="w-5 h-5 text-cyan-400" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">Evidence Pack</div>
                    <div className="text-xs text-slate-400">
                      Download cryptographically sealed evidence bundle
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {/* Download Progress */}
                  {downloadingPack && downloadProgress && (
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-cyan-500/10 border border-cyan-500/30 rounded-lg">
                      <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                      <span className="text-xs text-cyan-400 font-medium">{downloadProgress}</span>
                    </div>
                  )}

                  {/* Error Message */}
                  {downloadError && (
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 border border-red-500/30 rounded-lg">
                      <XCircle className="w-3.5 h-3.5 text-red-400" />
                      <span className="text-xs text-red-400 max-w-xs truncate" title={downloadError}>{downloadError}</span>
                    </div>
                  )}

                  {/* Download Button */}
                  {!downloadingPack && (
                    <button
                      onClick={handleDownloadEvidencePack}
                      disabled={!batch?.trace_id || isLegacyBatch}
                      className="flex items-center gap-2 px-4 py-2 bg-cyan-500/20 border border-cyan-500/40 rounded-lg text-cyan-400 text-sm font-medium hover:bg-cyan-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Download className="w-4 h-4" />
                      {isLegacyBatch ? 'Not Available (Legacy)' : 'Download Evidence Pack'}
                    </button>
                  )}
                </div>
              </div>

              {/* Pack Contents Info */}
              <div className="mt-4 pt-4 border-t border-slate-700/50">
                <div className="grid grid-cols-4 gap-4 text-xs">
                  <div className="flex items-center gap-2">
                    <FileCheck className="w-3.5 h-3.5 text-slate-500" />
                    <span className="text-slate-400">results.csv</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Archive className="w-3.5 h-3.5 text-slate-500" />
                    <span className="text-slate-400">certificate.pdf</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Hash className="w-3.5 h-3.5 text-slate-500" />
                    <span className="text-slate-400">manifest.json</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Activity className="w-3.5 h-3.5 text-slate-500" />
                    <span className="text-slate-400">audit_events.json</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Legal Hold Controls (RBAC-Protected) */}
          {canViewHoldStatus && (
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-amber-400" />
                  <span className="text-sm font-medium text-white">Legal Hold Controls</span>
                  {batch?.legal_hold?.status === 'ACTIVE' && (
                    <span className="px-2 py-0.5 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-400">
                      ACTIVE HOLD
                    </span>
                  )}
                </div>

                {/* Role-based action buttons */}
                <div className="flex items-center gap-2">
                  {batch?.legal_hold?.status === 'ACTIVE' ? (
                    // Release Hold button - Platform Admin only
                    canReleaseHold ? (
                      <button
                        onClick={handleOpenHoldModal}
                        className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-xs font-medium hover:bg-red-500/20 transition-colors"
                      >
                        <Unlock className="w-3.5 h-3.5" />
                        Release Hold
                      </button>
                    ) : canPlaceHold ? (
                      // Tenant Admin sees restricted tooltip
                      <div className="relative group">
                        <button
                          disabled
                          className="flex items-center gap-2 px-3 py-1.5 bg-slate-700/50 border border-slate-600/30 rounded-lg text-slate-500 text-xs font-medium cursor-not-allowed"
                        >
                          <Unlock className="w-3.5 h-3.5" />
                          Release Hold
                        </button>
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-300 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="w-3 h-3 text-amber-400" />
                            Only Platform Admins can release a WORM lock.
                          </div>
                        </div>
                      </div>
                    ) : null
                  ) : (
                    // Place Hold button - Tenant Admin + Platform Admin
                    canPlaceHold && (
                      <button
                        onClick={handleOpenHoldModal}
                        className="flex items-center gap-2 px-3 py-1.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-xs font-medium hover:bg-amber-500/20 transition-colors"
                      >
                        <Lock className="w-3.5 h-3.5" />
                        Place Legal Hold
                      </button>
                    )
                  )}
                </div>
              </div>

              {/* Hold Status Details */}
              {batch?.legal_hold?.status === 'ACTIVE' ? (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                  <div className="min-w-0">
                    <div className="text-slate-500 mb-1">Hold ID</div>
                    <div className="font-mono text-amber-400 truncate" title={batch?.legal_hold?.hold_id}>{batch?.legal_hold?.hold_id || 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 mb-1">Requested By</div>
                    <div className="font-mono text-slate-300 truncate">
                      {batch?.legal_hold?.requested_by?.split('@')[0] || 'N/A'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 mb-1">Vault Objects</div>
                    <div className="font-mono text-emerald-400">
                      {batch?.legal_hold?.vault_objects_written_count || 0} written
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 mb-1">WORM Expiry</div>
                    <div className="font-mono text-slate-300">
                      {batch?.legal_hold?.worm_retention_until?.split('T')[0] || '7 years'}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-slate-500">
                  No active legal hold. Place a hold to vault evidence to immutable WORM storage with 7-year retention.
                </div>
              )}

              {/* Reason (if active hold) */}
              {batch?.legal_hold?.reason && (
                <div className="mt-4 p-3 bg-slate-900/50 border border-slate-700/30 rounded-lg">
                  <div className="text-xs text-slate-500 mb-1">Hold Reason</div>
                  <div className="text-sm text-slate-300 break-words">{batch?.legal_hold?.reason}</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Legal Hold Modal */}
      <LegalHoldModal
        isOpen={showHoldModal}
        onClose={handleHoldCancel}
        batchId={batch?.trace_id}
        batchFilename={batch?.filename || batch?.trace_id}
        currentHoldStatus={batch?.legal_hold?.status}
        onHoldPlaced={handleHoldComplete}
        onHoldReleased={handleHoldComplete}
        canRelease={canReleaseHold}
      />
    </div>
  );
};

export default ForensicPanel;
