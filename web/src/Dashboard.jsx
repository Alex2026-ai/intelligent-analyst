'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, PieChart, Pie
} from 'recharts';
import {
  Zap, BrainCircuit, History, ShieldAlert, Terminal, Cpu, Users,
  DollarSign, Shield, Fingerprint, Upload, FileText, CheckCircle, XCircle,
  AlertTriangle, Loader2, Download, Lock, Sliders, Copy, Check, X, ChevronRight, Clock,
  FileDown, FileJson, Award, Hash, Package, ShieldCheck, LogOut, Share2, StopCircle
} from "lucide-react";
import Papa from 'papaparse';
import JSZip from 'jszip';
import { getAuth, signOut } from 'firebase/auth';
import { uploadBatch, fetchBatches, fetchAudit, fetchBatchResults, fetchBatchExportCSV, downloadCertificate, fetchManifestPublicKey, signManifest, fetchAdminTenants, createShareLink, fetchDemoStatus, checkHealth, abortBatch, fetchBatchVerification, fetchLegalHold, placeLegalHold, shadowPreHealth, shadowPreBatch, shadowPreBatchList, shadowPreBatchResults, shadowPreForensic, shadowPreAudit } from './api/client';
import AuditLog from './views/AuditLog';
import ForensicPanel from './components/ForensicPanel';
import TenantSwitcher from './components/TenantSwitcher';
import TrustSeal from './components/TrustSeal';
import { useAuth } from './context/AuthContext';
import { formatTimestamp, formatTimestampShort } from './utils/formatTimestamp';
import { UPLOAD_LIMITS } from './features/dashboard/constants';
import AdminPanel from './features/dashboard/components/AdminPanel';
import BatchHashDisplay from './features/dashboard/components/BatchHashDisplay';
import BatchComparisonModal from './features/dashboard/components/BatchComparisonModal';
import CommandPalette from './features/dashboard/components/CommandPalette';
import FileUploadZone from './features/dashboard/components/FileUploadZone';
import { Badge, NavItem } from './features/dashboard/components/VisualPrimitives';

/**
 * INTELLIGENT ANALYST — ENTERPRISE DASHBOARD v8.2.2
 * Status: ENTERPRISE SAFE (Proxy Mode)
 * - Design: Preserved
 * - Security: Uses /api/batch (No exposed keys)
 * - Admin: Demo Configuration Panel included
 * - Formats: CSV, Excel (XLSX/XLS), JSON, TXT
 */

// ═══════════════════════════════════════════════════════════════════════════
// ENVIRONMENT DETECTION (Build-time, read-only)
// ═══════════════════════════════════════════════════════════════════════════
// Environment is determined at BUILD TIME from VITE_ENVIRONMENT only.
// No runtime inference. No fallback. Unknown value → 'UNKNOWN'.
// Valid values: US-PROD | US-TEST | EU-PROD | EU-TEST | DEMO
const ENV_MAP = {
  'US-PROD': 'US-PROD',
  'US-TEST': 'US-TEST',
  'EU-PROD': 'EU-PROD',
  'EU-TEST': 'EU-TEST',
  'DEMO':    'DEMO',
};

const detectEnvironment = () => {
  const raw = import.meta.env.VITE_ENVIRONMENT;
  return ENV_MAP[raw] ?? 'UNKNOWN';
};

const CURRENT_ENVIRONMENT = detectEnvironment();

// Environment badge styles (read-only indicator)
const ENV_BADGE_STYLES = {
  'US-PROD': { bg: 'bg-emerald-500/20', border: 'border-emerald-500/40', text: 'text-emerald-400', label: 'US-PROD' },
  'US-TEST': { bg: 'bg-violet-500/20',  border: 'border-violet-500/40',  text: 'text-violet-400',  label: 'US-TEST' },
  'EU-PROD': { bg: 'bg-emerald-500/20', border: 'border-emerald-500/40', text: 'text-emerald-400', label: 'EU-PROD' },
  'EU-TEST': { bg: 'bg-violet-500/20',  border: 'border-violet-500/40',  text: 'text-violet-400',  label: 'EU-TEST' },
  'DEMO':    { bg: 'bg-amber-500/20',   border: 'border-amber-500/40',   text: 'text-amber-400',   label: 'DEMO'    },
  'UNKNOWN': { bg: 'bg-red-500/20',     border: 'border-red-500/40',     text: 'text-red-400',     label: 'UNKNOWN' },
};

const REGION_BADGE_STYLES = {
  us: { bg: 'bg-blue-500/20', border: 'border-blue-500/40', text: 'text-blue-400', label: 'US' },
  eu: { bg: 'bg-indigo-500/20', border: 'border-indigo-500/40', text: 'text-indigo-400', label: 'EU' },
};

const COLORS = {
  cyan: '#22d3ee',
  violet: '#a78bfa',
  amber: '#fbbf24',
  red: '#f87171',
  emerald: '#34d399',
  slate: '#64748b'  // For L0 Garbage
};

// --- EU AI ACT: DECISION PATH CLASSIFICATION ---
// Maps raw layer values to compliant decision path labels
const mapLayerToDecisionPath = (layer) => {
  if (!layer) return '—';
  const l = layer.toUpperCase();
  if (l === 'L1_EXACT' || l === 'L1_NORM' || l.startsWith('L1')) return 'L1_DETERMINISTIC';
  if (l === 'L2_VECTOR' || l.startsWith('L2')) return 'L2_VECTOR_FUZZY';
  if (l === 'L3_LLM' || l.startsWith('L3')) return 'L3_LLM';
  if (l === 'L4_HUMAN' || l.startsWith('L4')) return 'L4_HUMAN_REVIEW_REQUIRED';
  if (l === 'L0_GARBAGE' || l.startsWith('L0')) return 'L0_QUARANTINED';
  return layer; // fallback to raw value
};

// --- IDLE TIMEOUT ---
function getIdleTimeoutMs() {
  // Hard-pin production default to 5 minutes until env parsing is proven stable.
  return 5 * 60 * 1000;
}

const IDLE_TIMEOUT_MS = getIdleTimeoutMs();

// --- PUBLIC VERIFICATION URL BUILDER ---
// Constructs the public verification URL for TrustSeal links
const getPublicVerifyUrl = (batchId) => {
  if (!batchId) return null;
  // Prefer dedicated public base URL, fall back to API base
  const publicBase = import.meta.env.VITE_PUBLIC_VERIFY_BASE_URL
    || import.meta.env.VITE_API_BASE_URL
    || '';
  return `${publicBase}/verify/${encodeURIComponent(batchId)}`;
};

// --- MAIN DASHBOARD ---

export default function EnterpriseAnalystDashboard() {
  const [activeTab, setActiveTab] = useState('history');
  const [isClient, setIsClient] = useState(false);

  // RBAC from AuthContext (Days 14-16)
  const { canPerform, isPlatformAdmin, getEffectiveTenantId, activeTenantId, tenantRegion } = useAuth();

  // Role state (derived from backend)
  const [userRole, setUserRole] = useState('user'); // user | auditor | admin

  // Command Palette state
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);
  const [cmdQuery, setCmdQuery] = useState('');

  // Upload state
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [processingResults, setProcessingResults] = useState(null);
  const [processingError, setProcessingError] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState('idle'); // idle, uploading, processing, done, error
  // Pipeline mode is always 'auto' — backend inspects sample rows and chooses the pipeline

  // Preflight validation state
  const [preflightError, setPreflightError] = useState(null);
  const [preflightFileInfo, setPreflightFileInfo] = useState(null);

  // Dynamic Chart State
  const [waterfallData, setWaterfallData] = useState([]);

  // History state
  const [historyData, setHistoryData] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  // Evidence Pack state
  const [exportingCSV, setExportingCSV] = useState(false);
  const [downloadingCert, setDownloadingCert] = useState(false);
  const [showAuditSummary, setShowAuditSummary] = useState(false);
  const [evidenceError, setEvidenceError] = useState(null);
  const [buildingZip, setBuildingZip] = useState(false);
  const [buildingComplianceZip, setBuildingComplianceZip] = useState(false);

  // Share link state
  const [creatingShareLink, setCreatingShareLink] = useState(false);
  const [shareSuccess, setShareSuccess] = useState(null);
  const [verifyLinkCopied, setVerifyLinkCopied] = useState(false);

  // Abort batch state
  const [abortingBatchId, setAbortingBatchId] = useState(null);

  // Results preview state
  const [resultsPreview, setResultsPreview] = useState(null);
  const [resultsTotal, setResultsTotal] = useState(0);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState(null);

  // Results explorer filters (batch-scoped)
  const [resultsLayerFilter, setResultsLayerFilter] = useState('');
  const [resultsConfFilter, setResultsConfFilter] = useState('');
  const [resultsTextSearch, setResultsTextSearch] = useState('');
  const [resultsAnomalyFilter, setResultsAnomalyFilter] = useState('');

  // Row forensic drilldown
  const [selectedRow, setSelectedRow] = useState(null);

  // Batch comparison
  const [compareBatch, setCompareBatch] = useState(null);
  const [compareMode, setCompareMode] = useState(false);

  // Batch labels (persisted in localStorage)
  const [batchLabels, setBatchLabels] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ia_batch_labels') || '{}'); } catch { return {}; }
  });
  const BATCH_LABEL_OPTIONS = ['baseline', 'calibration', 'regression', 'demo', 'production sample'];
  const BATCH_LABEL_COLORS = {
    baseline: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    calibration: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
    regression: 'bg-red-500/20 text-red-400 border-red-500/30',
    demo: 'bg-violet-500/20 text-violet-400 border-violet-500/30',
    'production sample': 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  };
  const setBatchLabel = (traceId, label) => {
    setBatchLabels(prev => {
      const next = { ...prev };
      if (label) { next[traceId] = label; } else { delete next[traceId]; }
      localStorage.setItem('ia_batch_labels', JSON.stringify(next));
      return next;
    });
  };

  // Reproducibility hashes state - keyed by trace_id
  const [artifactHashes, setArtifactHashes] = useState({});

  // Forensic verification state (Days 11-13)
  const [forensicData, setForensicData] = useState(null);
  const [forensicLoading, setForensicLoading] = useState(false);

  // Admin console state
  const [adminTenants, setAdminTenants] = useState([]);
  const [adminTenantsLoading, setAdminTenantsLoading] = useState(false);
  const [selectedTenantFilter, setSelectedTenantFilter] = useState(''); // '' = all tenants

  // Demo mode state
  const [isDemoMode, setIsDemoMode] = useState(false);

  // Backend limits (fetched from /health)
  const [backendLimits, setBackendLimits] = useState({
    maxRecordsPerBatch: UPLOAD_LIMITS.MAX_ROWS,
    maxUploadMb: UPLOAD_LIMITS.MAX_FILE_SIZE_MB
  });

  // Computed: is user read-only (auditor)?
  const isReadOnly = userRole === 'auditor';
  // Computed: is user admin?
  const isAdmin = userRole === 'admin';
  // Computed: should upload be disabled?
  const isUploadDisabled = isReadOnly || isDemoMode;

  // Idle timer ref
  const idleTimerRef = useRef(null);

  // History fetch abort controller ref (prevents race conditions)
  const historyAbortRef = useRef(null);
  const preBatchListFired = useRef(false);

  // --- LOGOUT HANDLER ---
  async function handleLogout() {
    try {
      sessionStorage.setItem("logout_reason", "manual");
      const auth = getAuth();
      await signOut(auth);
    } finally {
      window.location.href = "/";
    }
  }

  // --- IDLE TIMER ---
  useEffect(() => {
    const handleIdleLogout = async () => {
      try {
        sessionStorage.setItem("logout_reason", "inactivity");
        const auth = getAuth();
        await signOut(auth);
      } finally {
        window.location.href = "/";
      }
    };

    const resetTimer = () => {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
      }
      idleTimerRef.current = setTimeout(() => {
        handleIdleLogout();
      }, IDLE_TIMEOUT_MS);
    };

    // Activity events to track
    const events = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'];

    // Start timer and add listeners
    resetTimer();
    events.forEach(event => window.addEventListener(event, resetTimer, { passive: true }));

    // Cleanup on unmount
    return () => {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
      }
      events.forEach(event => window.removeEventListener(event, resetTimer));
    };
  }, []);

  useEffect(() => setIsClient(true), []);

  // Command Palette keyboard shortcut (Cmd/Ctrl+K)
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCmdPaletteOpen(prev => !prev);
        setCmdQuery('');
      }
      if (e.key === 'Escape' && cmdPaletteOpen) {
        setCmdPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [cmdPaletteOpen]);

  // Fetch backend limits on mount + shadow PRE health check
  useEffect(() => {
    const fetchLimits = async () => {
      try {
        const result = await checkHealth();
        if (result.ok && result.data) {
          setBackendLimits({
            maxRecordsPerBatch: result.data.max_records_per_batch || UPLOAD_LIMITS.MAX_ROWS,
            maxUploadMb: result.data.max_upload_mb || UPLOAD_LIMITS.MAX_FILE_SIZE_MB
          });
        }
      } catch (err) {
        console.warn('Failed to fetch backend limits, using defaults:', err);
      }
    };
    fetchLimits();
    // Shadow: exercise PRE health path (fire-and-forget, no dashboard dependency)
    shadowPreHealth();
  }, []);

  // Clear results preview, filters, and row selection when selected batch changes
  useEffect(() => {
    setResultsPreview(null);
    setResultsTotal(0);
    setResultsError(null);
    setResultsLayerFilter('');
    setResultsConfFilter('');
    setResultsTextSearch('');
    setResultsAnomalyFilter('');
    setSelectedRow(null);
  }, [selectedBatch?.trace_id]);

  // Fetch forensic verification data when batch is selected (Days 11-13)
  useEffect(() => {
    if (!selectedBatch?.trace_id) {
      setForensicData(null);
      return;
    }

    const loadForensicData = async () => {
      setForensicLoading(true);
      try {
        const result = await fetchBatchVerification(selectedBatch.trace_id);
        if (result.ok && result.data) {
          setForensicData(result.data);
        }
      } catch (err) {
        console.warn('Failed to fetch forensic data:', err);
      } finally {
        setForensicLoading(false);
      }
    };

    loadForensicData();
    // Shadow: exercise PRE batch read + forensic metadata paths (fire-and-forget)
    shadowPreBatch(selectedBatch.trace_id);
    shadowPreForensic(selectedBatch.trace_id);
  }, [selectedBatch?.trace_id]);

  // --- PREFLIGHT VALIDATION ---
  const validateFilePreflight = async (file) => {
    const errors = [];
    const fileInfo = {
      name: file.name,
      size: file.size,
      estimatedRows: null
    };

    // Check file extension
    const ext = ('.' + file.name.split('.').pop()).toLowerCase();
    if (!UPLOAD_LIMITS.ALLOWED_EXTENSIONS.includes(ext)) {
      errors.push(`Invalid file type "${ext}". Allowed: ${UPLOAD_LIMITS.ALLOWED_EXTENSIONS.join(', ')}`);
    }

    // Check file size
    if (file.size > UPLOAD_LIMITS.MAX_FILE_SIZE_BYTES) {
      errors.push(`File too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum: ${UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB`);
    }

    // Estimate rows for text-based files (CSV, TXT, JSON)
    if (['.csv', '.txt', '.json'].includes(ext) && file.size < 10 * 1024 * 1024) {
      try {
        const text = await file.text();
        if (ext === '.json') {
          const parsed = JSON.parse(text);
          if (Array.isArray(parsed)) {
            fileInfo.estimatedRows = parsed.length;
          } else if (parsed.data && Array.isArray(parsed.data)) {
            fileInfo.estimatedRows = parsed.data.length;
          }
        } else {
          // CSV/TXT: count lines (subtract 1 for header)
          const lines = text.split(/\r?\n/).filter(line => line.trim());
          fileInfo.estimatedRows = Math.max(0, lines.length - 1);
        }

        if (fileInfo.estimatedRows !== null && fileInfo.estimatedRows > backendLimits.maxRecordsPerBatch) {
          errors.push(`Too many rows (~${fileInfo.estimatedRows.toLocaleString()}). Maximum: ${backendLimits.maxRecordsPerBatch.toLocaleString()}`);
        }
      } catch (e) {
        // Can't estimate, will be validated server-side
        console.warn('Could not estimate rows:', e);
      }
    }

    return { valid: errors.length === 0, errors, fileInfo };
  };

  // --- UPLOAD LOGIC (Same-origin proxy with Firebase token) ---
  const handleFileSelect = async (file) => {
    // Prevent duplicate submissions
    if (isProcessing) return;

    // Clear previous preflight state
    setPreflightError(null);
    setPreflightFileInfo(null);

    // Run preflight validation
    const preflight = await validateFilePreflight(file);
    setPreflightFileInfo(preflight.fileInfo);

    if (!preflight.valid) {
      setPreflightError(preflight.errors.join(' • '));
      return; // Block upload
    }

    setUploadedFile(file);
    setProcessingError(null);
    setProcessingResults(null);
    setIsProcessing(true);
    setUploadProgress(0);
    setUploadPhase('uploading');

    try {
      // Use the API client which calls /api/batch-upload (same-origin)
      const { promise } = uploadBatch(
        file,
        file.name,
        'auto', // Backend auto-routes based on sample row inspection
        // onProgress callback
        (progress) => {
          setUploadProgress(progress.percent);
        },
        // onProcessing callback (upload complete, server processing)
        () => {
          setUploadPhase('processing');
          setUploadProgress(100);
        }
      );

      const result = await promise;
      console.log('[UPLOAD] Result:', result);

      if (!result.ok) {
        console.error('[UPLOAD] Upload failed:', result.error);
        throw new Error(result.error || `Processing failed (${result.status})`);
      }

      const data = result.data;
      console.log('[UPLOAD] Data:', data);

      // Handle async 202 queued response - open batch inspector
      if (data?.status === 'queued') {
        console.log('[UPLOAD] Batch queued, opening inspector');
        setUploadPhase('done');
        setProcessingResults({
          queued: true,
          trace_id: data.trace_id,
          total: data.total,
          message: data.message || 'Batch queued for processing.',
          requested_mode: data.requested_mode,
          effective_mode: data.effective_mode,
          routing: data.routing,
        });
        await loadHistory();
        setActiveTab('history');
        // Auto-open the batch inspector for the newly created batch
        const newBatch = {
          trace_id: data.trace_id, status: 'queued', total: data.total,
          filename: uploadedFile?.name, timestamp: new Date().toISOString(),
          dataset_type: data.dataset_type, effective_mode: data.effective_mode,
          classification_meta: { mode: data.effective_mode, requested_mode: data.requested_mode, routing: data.routing },
        };
        setSelectedBatch(newBatch);
        return;
      }

      // Handle synchronous response (legacy flow) - open batch inspector
      console.log('[UPLOAD] Synchronous response, opening inspector');
      setProcessingResults(data);
      updateWaterfall(data?.stats, data?.counts);
      setUploadPhase('done');
      await loadHistory();
      setActiveTab('history');
      // Auto-open inspector for the completed batch
      const completedBatch = (historyData?.batches || []).find(b => b.trace_id === data.trace_id) || {
        trace_id: data.trace_id, status: 'completed', total: data.total, filename: uploadedFile?.name,
        auto_resolved_pct: data.auto_resolved_pct, stats: data.stats, counts: data.counts, timestamp: new Date().toISOString()
      };
      setSelectedBatch(completedBatch);

    } catch (error) {
      console.error('[UPLOAD] Error:', error);
      setProcessingError(error.message || 'Processing failed');
      setUploadPhase('error');
    } finally {
      setIsProcessing(false);
    }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // VISUAL LOCK: Waterfall uses counts object directly (no client-side computation)
  // ═══════════════════════════════════════════════════════════════════════════
  const updateWaterfall = (stats, counts = null) => {
    if (!stats && !counts) return;

    // VISUAL LOCK: Prefer counts object if available
    if (counts && Object.keys(counts).length > 0) {
      const total = (counts.l0_quarantined || 0) + (counts.l1_resolved || 0) +
                    (counts.l2_resolved || 0) + (counts.l3_resolved || 0) + (counts.l4_flagged || 0);
      const validRecords = total - (counts.l0_quarantined || 0);
      const l0 = counts.l0_quarantined || 0;
      const l1 = counts.l1_resolved || 0;
      const l2 = counts.l2_resolved || 0;
      const l3 = counts.l3_resolved || 0;
      const l4 = counts.l4_flagged || 0;

      setWaterfallData([
        { name: 'L0: Quarantined', records: l0, pct: total > 0 ? (l0/total * 100).toFixed(1) : '0.0', color: COLORS.slate, icon: ShieldAlert, isGarbage: true },
        { name: 'L1: Deterministic', records: l1, pct: validRecords > 0 ? (l1/validRecords * 100).toFixed(1) : '0.0', color: COLORS.cyan, icon: Shield },
        { name: 'L2: Vector', records: l2, pct: validRecords > 0 ? (l2/validRecords * 100).toFixed(1) : '0.0', color: COLORS.violet, icon: Cpu },
        { name: 'L3: LLM', records: l3, pct: validRecords > 0 ? (l3/validRecords * 100).toFixed(1) : '0.0', color: COLORS.amber, icon: BrainCircuit },
        { name: 'L4: Flagged', records: l4, pct: validRecords > 0 ? (l4/validRecords * 100).toFixed(1) : '0.0', color: COLORS.red, icon: Users },
      ]);
      return;
    }

    // Fallback to legacy stats object
    const l0 = stats.layer_0_garbage || 0;
    const l1 = (stats.layer_1_total || 0) || ((stats.layer_1_exact || 0) + (stats.layer_1_norm || 0) + (stats.layer_1_mixed_person || 0) + (stats.layer_1_mixed_org || 0) + (stats.layer_1_mixed_vessel || 0));
    const l2 = (stats.layer_2_total || 0) || (stats.layer_2_vector || 0);
    const l3 = stats.layer_3_llm || 0;
    const l4 = stats.layer_4_human || 0;
    const total = stats.total || (l0 + l1 + l2 + l3 + l4) || 1;
    const validRecords = stats.valid_records || (total - l0);

    setWaterfallData([
      { name: 'L0: Quarantined', records: l0, pct: (l0/total * 100).toFixed(1), color: COLORS.slate, icon: ShieldAlert, isGarbage: true },
      { name: 'L1: Deterministic', records: l1, pct: validRecords > 0 ? (l1/validRecords * 100).toFixed(1) : '0.0', color: COLORS.cyan, icon: Shield },
      { name: 'L2: Vector', records: l2, pct: validRecords > 0 ? (l2/validRecords * 100).toFixed(1) : '0.0', color: COLORS.violet, icon: Cpu },
      { name: 'L3: LLM', records: l3, pct: validRecords > 0 ? (l3/validRecords * 100).toFixed(1) : '0.0', color: COLORS.amber, icon: BrainCircuit },
      { name: 'L4: Flagged', records: l4, pct: validRecords > 0 ? (l4/validRecords * 100).toFixed(1) : '0.0', color: COLORS.red, icon: Users },
    ]);
  };

  const loadHistory = async (tenantFilter = '') => {
    // Cancel any in-flight request to prevent race conditions
    if (historyAbortRef.current) {
      historyAbortRef.current.abort();
    }
    historyAbortRef.current = new AbortController();
    const signal = historyAbortRef.current.signal;

    setHistoryLoading(true);
    setHistoryError(null);
    try {
      // Use the API client which calls /api/batches (same-origin)
      // Pass tenant filter for admin users and abort signal
      const result = await fetchBatches(signal, tenantFilter || undefined);

      // Handle authentication errors
      if (result.status === 401) {
        console.error('[HISTORY] Authentication failed (401). Please log out and log back in.');
        setHistoryError('Session expired. Please log out and log back in to refresh your authentication.');
        return;
      }

      if (result.ok && result.data) {
        // Debug: Log batches to verify data structure
        const batches = result.data.batches || [];
        console.log(`[HISTORY] Received ${batches.length} batches`);
        // Log first 5 batches with key metrics
        batches.slice(0, 5).forEach((b, i) => {
          console.log(`[HISTORY] #${i+1}: ${b.trace_id} | status=${b.status} | ` +
            `duration=${b.duration_seconds || 0}s | total=${b.total || b.total_records || 0} | ` +
            `auto_resolved=${b.auto_resolved_pct || 0}% | has_counts=${!!b.counts}`);
        });
        setHistoryData(result.data);
        setHistoryError(null);
        // Shadow: PRE batch list parity check (fire once, not on every poll)
        if (!preBatchListFired.current) {
          preBatchListFired.current = true;
          shadowPreBatchList(batches.length);
        }
        // Capture role from backend response
        if (result.role) {
          setUserRole(result.role);
        }
        // Capture demo mode from backend response
        setIsDemoMode(result.demoMode === true);
      } else if (!result.ok) {
        // Ignore intentional aborts (happens when we cancel a stale request)
        if (result.error === 'Request aborted') {
          console.log('[HISTORY] Previous request cancelled (expected during navigation)');
          return; // Don't update state for cancelled requests
        }
        console.error(`[HISTORY] API error: ${result.status} - ${result.error}`);
        setHistoryError(result.error || `Failed to load batches (${result.status})`);
      }
    } catch (error) {
      // Ignore AbortError (intentional cancellation)
      if (error?.name === 'AbortError') {
        console.log('[HISTORY] Fetch aborted (expected)');
        return;
      }
      console.error('Failed to fetch history:', error);
      setHistoryError('Network error. Please check your connection and try again.');
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadAdminTenants = async () => {
    setAdminTenantsLoading(true);
    try {
      const result = await fetchAdminTenants();
      if (result.ok && result.data) {
        setAdminTenants(result.data);
      }
    } catch (error) {
      console.error('Failed to fetch admin tenants:', error);
    } finally {
      setAdminTenantsLoading(false);
    }
  };

  const handleDownload = () => {
    if (!processingResults?.results) return;
    const csv = Papa.unparse(processingResults.results);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'intelligent_analyst_results.csv');
    document.body.appendChild(link);
    link.click();
  };

  // Consolidated history loading effect
  // Triggers: initial mount, tab switch to history, tenant filter change
  useEffect(() => {
    // Always load on mount to get role, or when on history tab
    const shouldLoad = activeTab === 'history' || activeTab === 'analysis';
    if (shouldLoad) {
      loadHistory(selectedTenantFilter);
      // Load admin tenants if admin and on history tab
      if (isAdmin && activeTab === 'history') {
        loadAdminTenants();
      }
    }

    // Cleanup: cancel in-flight request when dependencies change or unmount
    return () => {
      if (historyAbortRef.current) {
        historyAbortRef.current.abort();
      }
    };
  }, [activeTab, selectedTenantFilter, isAdmin]);

  // Initial mount: fetch role (only once)
  useEffect(() => {
    loadHistory();
    return () => {
      if (historyAbortRef.current) {
        historyAbortRef.current.abort();
      }
    };
  }, []);

  // Persistent polling: poll every 3s while on History tab until all batches are terminal
  useEffect(() => {
    // Only poll when on History tab
    if (activeTab !== 'history') {
      return;
    }

    // Check if any batches are still pending/processing
    const hasPendingBatches = historyData?.batches?.some(
      b => b.status === 'queued' || b.status === 'processing' || b.status === 'pending'
    );

    // Start polling immediately when entering History tab
    // Continue polling while there are pending batches
    const pollInterval = setInterval(() => {
      if (hasPendingBatches) {
        console.log('[POLL] Refreshing batches (pending batches detected)...');
      } else {
        console.log('[POLL] Polling for updates...');
      }
      loadHistory(selectedTenantFilter);
    }, 3000); // Poll every 3 seconds

    // Log polling status
    console.log(`[POLL] Started polling on History tab. Pending batches: ${hasPendingBatches}`);

    return () => {
      console.log('[POLL] Stopped polling (leaving History tab)');
      clearInterval(pollInterval);
    };
  }, [activeTab, selectedTenantFilter]);

  // Additional effect: refresh immediately when pending batches finish
  useEffect(() => {
    const hasPendingBatches = historyData?.batches?.some(
      b => b.status === 'queued' || b.status === 'processing' || b.status === 'pending'
    );

    // Log state for debugging
    if (historyData?.batches?.length > 0) {
      const firstBatch = historyData.batches[0];
      console.log(`[STATE] First batch: ${firstBatch.trace_id} | status=${firstBatch.status} | duration=${firstBatch.duration_seconds || 0}s`);
    }

    // Live refresh: sync selectedBatch from polled history data
    if (selectedBatch?.trace_id && historyData?.batches) {
      const fresh = historyData.batches.find(b => b.trace_id === selectedBatch.trace_id);
      if (fresh && fresh.status !== selectedBatch.status) {
        console.log(`[MODAL_REFRESH] ${selectedBatch.trace_id}: ${selectedBatch.status} → ${fresh.status}`);
        setSelectedBatch(fresh);
      } else if (fresh && fresh.auto_resolved_pct !== selectedBatch.auto_resolved_pct) {
        // Also refresh if metrics changed (e.g. counts populated)
        setSelectedBatch(fresh);
      }
    }
  }, [historyData]);

  const copyToClipboard = useCallback((text) => {
    if (!text) return;

    const showSuccess = () => {
      setCopiedId(text);
      setTimeout(() => setCopiedId(null), 2000);
    };

    const showError = () => {
      alert('Failed to copy to clipboard');
    };

    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text)
        .then(showSuccess)
        .catch(() => {
          // Fallback to execCommand
          fallbackCopy(text, showSuccess, showError);
        });
    } else {
      // Fallback for older browsers
      fallbackCopy(text, showSuccess, showError);
    }
  }, []);

  const fallbackCopy = (text, onSuccess, onError) => {
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      textarea.style.top = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const success = document.execCommand('copy');
      document.body.removeChild(textarea);
      if (success) {
        onSuccess();
      } else {
        onError();
      }
    } catch {
      onError();
    }
  };

  // --- REPRODUCIBILITY HASH FUNCTIONS ---
  const computeSHA256 = async (data) => {
    try {
      let bytes;
      if (typeof data === 'string') {
        bytes = new TextEncoder().encode(data);
      } else if (data instanceof Blob) {
        bytes = new Uint8Array(await data.arrayBuffer());
      } else if (data instanceof ArrayBuffer) {
        bytes = new Uint8Array(data);
      } else {
        bytes = new Uint8Array(data);
      }
      const hashBuffer = await crypto.subtle.digest('SHA-256', bytes);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    } catch (err) {
      console.error('SHA-256 computation failed:', err);
      return null;
    }
  };

  const computeBatchHash = useCallback((batch) => {
    if (!batch) return null;
    const stats = batch.stats || {};
    const counts = batch.counts || {};
    // Canonical JSON with stable key ordering (no timestamp to ensure determinism)
    const canonical = {
      trace_id: batch.trace_id || '',
      config_version: batch.config_version || 'unknown',
      total: batch.total || batch.total_records || 0,
      layer_counts: {
        L0: counts.l0_quarantined || counts.l0 || stats.layer_0_garbage || 0,
        L1: counts.l1_resolved || counts.l1 || ((stats.layer_1_exact || 0) + (stats.layer_1_norm || 0) + (stats.layer_1_mixed_person || 0) + (stats.layer_1_mixed_org || 0) + (stats.layer_1_mixed_vessel || 0)),
        L2: counts.l2_resolved || counts.l2 || stats.layer_2_vector || 0,
        L3: counts.l3_resolved || counts.l3 || stats.layer_3_llm || 0,
        L4: counts.l4_flagged || counts.l4 || stats.layer_4_human || 0
      }
    };
    const jsonStr = JSON.stringify(canonical, Object.keys(canonical).sort());
    return computeSHA256(jsonStr);
  }, []);

  const storeArtifactHash = useCallback((traceId, artifactType, hash) => {
    setArtifactHashes(prev => ({
      ...prev,
      [traceId]: {
        ...(prev[traceId] || {}),
        [artifactType]: hash
      }
    }));
  }, []);

  // --- ANOMALY DETECTION ---
  const detectBatchAnomalies = (batch) => {
    const anomalies = [];
    const status = batch.status || 'completed';
    const autoResolved = batch.auto_resolved_pct ?? null;
    const total = batch.total || batch.total_records || 0;
    const stats = batch.stats || {};
    const counts = batch.counts || {};

    if (status === 'failed' || status === 'error') return { level: 'failed', anomalies: ['Batch failed'] };
    if (status === 'aborted') return { level: 'failed', anomalies: ['Batch aborted'] };
    if (status !== 'completed') return { level: 'in_progress', anomalies: [] };

    // 0% auto-resolved
    if (autoResolved != null && autoResolved === 0 && total > 0) {
      anomalies.push('0% auto-resolved — all rows unresolved or garbage');
    } else if (autoResolved != null && autoResolved < 20 && total > 0) {
      anomalies.push(`Very low resolution rate: ${autoResolved.toFixed(1)}%`);
    }

    // All-garbage routing
    const garbageCount = counts.l0_quarantined || counts.l0 || stats.layer_0_garbage || 0;
    if (garbageCount > 0 && garbageCount >= total * 0.9) {
      anomalies.push(`${((garbageCount / total) * 100).toFixed(0)}% routed to garbage (L0)`);
    }

    // No metrics on completed batch
    const hasMetrics = batch.duration_seconds > 0 || batch.duration_ms > 0 || (batch.counts && Object.keys(batch.counts).length > 0);
    if (!hasMetrics) {
      anomalies.push('Missing completion metrics');
    }

    // Suspicious duration (>5min for <1K rows, or >30min for any batch)
    const durationSec = batch.duration_seconds || (batch.duration_ms ? batch.duration_ms / 1000 : 0);
    if (durationSec > 1800) {
      anomalies.push(`Unusually long duration: ${(durationSec / 60).toFixed(0)}min`);
    } else if (total < 1000 && durationSec > 300) {
      anomalies.push(`Slow for ${total} rows: ${(durationSec / 60).toFixed(1)}min`);
    }

    // High L4 flagging (>30% of total)
    const l4Count = counts.l4_flagged || counts.l4 || stats.layer_4_human || 0;
    if (l4Count > 0 && total > 0 && (l4Count / total) > 0.3) {
      anomalies.push(`High flagging rate: ${((l4Count / total) * 100).toFixed(0)}% sent to L4 review`);
    }

    return {
      level: anomalies.length > 0 ? 'anomaly' : 'clean',
      anomalies
    };
  };

  const getStatusBadge = (batch) => {
    const VALID_STATUSES = new Set(['uploading', 'queued', 'processing', 'finalizing', 'completed', 'failed', 'aborted']);
    const rawStatus = batch.status || 'completed';
    const status = VALID_STATUSES.has(rawStatus) ? rawStatus : 'completed';
    if (!VALID_STATUSES.has(rawStatus) && rawStatus) {
        console.warn(`[IA] Unknown batch status: "${rawStatus}" for ${batch.trace_id}`);
    }
    if (status === 'failed' || status === 'error') {
      return <span className="inline-flex items-center gap-1 text-red-400"><XCircle size={12} /> Failed</span>;
    }
    if (status === 'aborted') {
      return <span className="inline-flex items-center gap-1 text-red-400"><StopCircle size={12} /> Failed (Aborted)</span>;
    }
    if (status === 'uploading') {
      return <span className="inline-flex items-center gap-1 text-blue-400"><Loader2 size={12} className="animate-spin" /> Uploading</span>;
    }
    if (status === 'finalizing') {
      return <span className="inline-flex items-center gap-1 text-violet-400"><Loader2 size={12} className="animate-spin" /> Finalizing</span>;
    }
    if (status === 'processing') {
      return <span className="inline-flex items-center gap-1 text-amber-400"><Loader2 size={12} className="animate-spin" /> Processing</span>;
    }
    if (status === 'queued') {
      return <span className="inline-flex items-center gap-1 text-blue-400"><Clock size={12} /> Queued</span>;
    }
    // Completed — check for anomalies
    const { level } = detectBatchAnomalies(batch);
    if (level === 'anomaly') {
      return <span className="inline-flex items-center gap-1 text-amber-400"><AlertTriangle size={12} /> Completed with anomaly</span>;
    }
    return <span className="inline-flex items-center gap-1 text-emerald-400"><CheckCircle size={12} /> Completed</span>;
  };

  // --- COMMAND PALETTE COMMANDS ---
  const cmdPaletteCommands = () => {
    const batches = historyData?.batches || [];
    const latestBatch = batches[0];
    const anomalousBatches = batches.filter(b => detectBatchAnomalies(b).level === 'anomaly');

    return [
      // Navigation
      { group: 'Navigate', label: 'Upload New Batch', desc: 'Upload a file for resolution', keys: ['upload', 'new', 'run'], action: () => setActiveTab('upload') },
      { group: 'Navigate', label: 'Operations Console', desc: 'View batch history', keys: ['history', 'batches', 'ops', 'operations'], action: () => setActiveTab('history') },
      { group: 'Navigate', label: 'Audit Log', desc: 'Compliance event log', keys: ['audit', 'log', 'compliance'], action: () => setActiveTab('auditlog') },
      { group: 'Navigate', label: 'Configuration', desc: 'Admin settings', keys: ['config', 'settings', 'admin'], action: () => setActiveTab('config') },
      // Batch operations
      ...(latestBatch ? [
        { group: 'Batch', label: 'Open Latest Batch', desc: latestBatch.trace_id?.slice(0, 12), keys: ['latest', 'last', 'recent'], action: () => { setActiveTab('history'); setSelectedBatch(latestBatch); } },
      ] : []),
      ...(anomalousBatches.length > 0 ? [
        { group: 'Batch', label: `Open Anomalous Batches (${anomalousBatches.length})`, desc: 'Batches with issues', keys: ['anomal', 'issue', 'problem', 'warning'], action: () => { setActiveTab('history'); setSelectedBatch(anomalousBatches[0]); } },
      ] : []),
      ...(selectedBatch ? [
        { group: 'Batch', label: 'Show Waterfall', desc: 'Layer distribution for selected batch', keys: ['waterfall', 'layers', 'distribution'], action: () => { /* already in inspector */ setActiveTab('history'); } },
        { group: 'Batch', label: 'Download Evidence Pack', desc: 'ZIP with CSV + audit + cert', keys: ['evidence', 'download', 'zip', 'pack'], action: () => handleDownloadEvidencePack(selectedBatch) },
        { group: 'Batch', label: 'Open Audit for Batch', desc: 'Audit summary modal', keys: ['audit batch', 'summary'], action: () => setShowAuditSummary(true) },
        { group: 'Batch', label: 'View Results', desc: 'Load result rows', keys: ['results', 'rows', 'preview'], action: () => handleLoadResults(selectedBatch) },
        { group: 'Batch', label: 'Compare Batches', desc: 'Side-by-side comparison', keys: ['compare', 'diff', 'delta', 'calibrat'], action: () => setCompareMode(true) },
      ] : []),
      // System
      { group: 'System', label: 'Refresh Data', desc: 'Reload batch history', keys: ['refresh', 'reload'], action: () => loadHistory() },
    ];
  };

  // --- EVIDENCE PACK HANDLERS ---
  const handleExportCSV = async (batch) => {
    if (!batch?.trace_id) return;
    setExportingCSV(true);
    setEvidenceError(null);

    try {
      // Determine export format based on batch mode
      const batchMode = (batch.mode || batch.dataset_type || 'company').toLowerCase();
      const format = batchMode === 'person' ? 'sanitized' : 'csv';

      const result = await fetchBatchExportCSV(batch.trace_id, format);
      if (!result.ok || !result.blob) {
        const errMsg = result.error || 'Failed to export CSV';
        console.error(`[ExportCSV] ${batch.trace_id}: ${errMsg}`);
        if (errMsg.includes('403')) {
          throw new Error('Access denied — you may not have permission to export this batch.');
        }
        if (errMsg.includes('401') || errMsg.includes('token')) {
          throw new Error('Authentication required — please sign in again.');
        }
        throw new Error(errMsg);
      }

      // Compute hash for reproducibility
      const csvContent = await result.blob.text();
      const csvHash = await computeSHA256(csvContent);
      if (csvHash) {
        storeArtifactHash(batch.trace_id, 'csv', csvHash);
      }

      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${batch.trace_id}_results.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setEvidenceError(err.message || 'Export failed');
    } finally {
      setExportingCSV(false);
    }
  };

  // --- PERSON MODE: Download Sanitized Output (CSV) ---
  const [downloadingSanitized, setDownloadingSanitized] = useState(false);

  const handleDownloadSanitizedOutput = async (batch) => {
    if (!batch?.trace_id) return;
    setDownloadingSanitized(true);
    setEvidenceError(null);

    try {
      const result = await fetchBatchExportCSV(batch.trace_id, 'sanitized');
      if (!result.ok || !result.blob) {
        const errMsg = result.error || 'Export failed';
        console.error(`[SanitizedExport] ${batch.trace_id}: ${errMsg}`);
        if (errMsg.includes('403')) {
          throw new Error('Access denied — you may not have permission to export this batch.');
        }
        if (errMsg.includes('401') || errMsg.includes('token')) {
          throw new Error('Authentication required — please sign in again.');
        }
        throw new Error(errMsg);
      }

      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `sanitized_${batch.trace_id}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setEvidenceError(err.message || 'Download failed');
    } finally {
      setDownloadingSanitized(false);
    }
  };

  const handleDownloadCertificate = async (batch) => {
    if (!batch?.trace_id) return;
    setDownloadingCert(true);
    setEvidenceError(null);

    try {
      const result = await downloadCertificate(batch.trace_id);
      if (!result.ok || !result.blob) {
        throw new Error(result.error || 'Certificate not available');
      }

      // Compute hash for reproducibility
      const certHash = await computeSHA256(result.blob);
      if (certHash) {
        storeArtifactHash(batch.trace_id, 'cert', certHash);
      }

      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `IA_Certificate_${batch.trace_id}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setEvidenceError(err.message || 'Certificate download failed');
    } finally {
      setDownloadingCert(false);
    }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // VISUAL LOCK: Bind UI directly to batch_result.counts (no client-side recomputation)
  // ═══════════════════════════════════════════════════════════════════════════
  const getAuditSummary = (batch) => {
    if (!batch) return null;
    // VISUAL LOCK: Read directly from backend counts object (no client-side computation)
    const counts = batch.counts || {};
    const stats = batch.stats || {};  // Fallback for legacy batches
    const lbs = batch.llm_budget_summary || {};

    // Use counts object if available, otherwise fallback to legacy stats
    const hasNewCounts = Object.keys(counts).length > 0;

    return {
      trace_id: batch.trace_id,
      timestamp: batch.timestamp,
      filename: batch.filename,
      total_records: batch.total || batch.total_records || 0,
      auto_resolved: batch.auto_resolved || 0,
      auto_resolved_pct: batch.auto_resolved_pct || 0,
      flagged_count: batch.flagged_count || 0,

      // VISUAL LOCK: Layer counts bound directly to backend
      counts: hasNewCounts ? {
        l0_quarantined: counts.l0_quarantined || counts.l0 || 0,
        l1_resolved: counts.l1_resolved || counts.l1 || 0,
        l1_exact: counts.l1_exact || 0,
        l1_norm: counts.l1_norm || 0,
        l1_person: counts.l1_person || 0,
        l1_org: counts.l1_org || 0,
        l1_vessel: counts.l1_vessel || 0,
        l2_resolved: counts.l2_resolved || counts.l2 || 0,
        l3_eligible: counts.l3_eligible || 0,
        l3_attempted: counts.l3_attempted || 0,
        l3_succeeded: counts.l3_succeeded || 0,
        l3_failed: counts.l3_failed || 0,
        l3_skipped_budget: counts.l3_skipped_budget || 0,
        l3_skipped_rate_limit: counts.l3_skipped_rate_limit || 0,
        l3_resolved: counts.l3_resolved || counts.l3 || 0,
        l4_flagged: counts.l4_flagged || counts.l4 || 0
      } : null,

      // Legacy layer_counts for backward compatibility
      layer_counts: {
        L0_garbage: hasNewCounts ? (counts.l0_quarantined || counts.l0 || 0) : (stats.layer_0_garbage || 0),
        L1_exact: hasNewCounts ? (counts.l1_exact || 0) : (stats.layer_1_exact || 0),
        L1_normalized: hasNewCounts ? (counts.l1_norm || 0) : (stats.layer_1_norm || 0),
        L1_person: hasNewCounts ? (counts.l1_person || 0) : (stats.layer_1_mixed_person || 0),
        L1_org: hasNewCounts ? (counts.l1_org || 0) : (stats.layer_1_mixed_org || 0),
        L1_vessel: hasNewCounts ? (counts.l1_vessel || 0) : (stats.layer_1_mixed_vessel || 0),
        L1_total: hasNewCounts ? (counts.l1_resolved || counts.l1 || 0) : ((stats.layer_1_exact || 0) + (stats.layer_1_norm || 0) + (stats.layer_1_mixed_person || 0) + (stats.layer_1_mixed_org || 0) + (stats.layer_1_mixed_vessel || 0)),
        L2_vector: hasNewCounts ? (counts.l2_resolved || counts.l2 || 0) : (stats.layer_2_vector || 0),
        L3_llm: hasNewCounts ? (counts.l3_resolved || counts.l3 || 0) : (stats.layer_3_llm || 0),
        L4_human: hasNewCounts ? (counts.l4_flagged || counts.l4 || 0) : (stats.layer_4_human || 0)
      },

      // VISUAL LOCK: L3 instrumentation (attempted vs skipped)
      l3_metrics: hasNewCounts ? {
        eligible: counts.l3_eligible || 0,
        attempted: counts.l3_attempted || 0,
        succeeded: counts.l3_succeeded || 0,
        failed: counts.l3_failed || 0,
        skipped_budget: counts.l3_skipped_budget || 0,
        skipped_rate_limit: counts.l3_skipped_rate_limit || 0,
        // Observability invariant: eligible == attempted + skipped_budget + skipped_rate_limit
        invariant_valid: (counts.l3_eligible || 0) ===
          ((counts.l3_attempted || 0) + (counts.l3_skipped_budget || 0) + (counts.l3_skipped_rate_limit || 0))
      } : null,

      // VISUAL LOCK: Lifecycle timestamps
      lifecycle: {
        started_at: batch.started_at || null,
        finished_at: batch.finished_at || null,
        duration_ms: batch.duration_ms || 0,
        duration_seconds: batch.duration_seconds || (batch.duration_ms ? batch.duration_ms / 1000 : 0)
      },

      // LLM budget summary (direct from backend)
      llm_budget: {
        budget_usd: lbs.budget_usd || 0,
        spent_usd: lbs.spent_usd || 0,
        calls: lbs.calls || 0,
        avg_cost_per_call: lbs.avg_cost_per_call || 0,
        budget_exhausted: lbs.budget_exhausted || false,
        call_cap_reached: lbs.call_cap_reached || false,
        skipped_reason_counts: lbs.skipped_reason_counts || {}
      },

      duration_ms: batch.duration_ms || 0,
      total_cost: lbs.spent_usd || stats.total_cost || batch.cost || 0,
      config_version: batch.config_version || 'unknown'
    };
  };

  const handleDownloadAuditJSON = async (batch) => {
    const summary = getAuditSummary(batch);
    if (!summary) return;

    // Use stable JSON serialization (sorted keys)
    const jsonContent = JSON.stringify(summary, Object.keys(summary).sort(), 2);

    // Compute hash for reproducibility
    const auditHash = await computeSHA256(jsonContent);
    if (auditHash) {
      storeArtifactHash(batch.trace_id, 'audit', auditHash);
    }

    const blob = new Blob([jsonContent], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${batch.trace_id}_audit_summary.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // --- DOWNLOAD EVIDENCE PACK (ZIP) v1.2 with Cryptographic Signature ---
  const handleDownloadEvidencePack = async (batch) => {
    if (!batch?.trace_id) return;
    setBuildingZip(true);
    setEvidenceError(null);

    try {
      const zip = new JSZip();
      const generatedAt = new Date();
      const dateStr = generatedAt.toISOString().split('T')[0]; // YYYY-MM-DD
      const configVersion = batch.config_version || 'unknown';

      const manifest = {
        manifest_version: '1.2',
        app_version: '8.2.2',
        trace_id: batch.trace_id,
        config_version: configVersion,
        generated_at: generatedAt.toISOString(),
        files: [],
        hashes: {},
        batch_hash: null,
        signature: null,
        signature_algorithm: null
      };

      // 1. Generate results.csv
      const auditResult = await fetchAudit(batch.trace_id, 10000);
      if (!auditResult.ok || !auditResult.data?.events) {
        throw new Error(auditResult.error || 'Failed to fetch audit data for CSV');
      }

      const events = auditResult.data.events;
      const sortedEvents = [...events].sort((a, b) => (a.row_index || 0) - (b.row_index || 0));

      const csvRows = [
        ['row_index', 'original', 'resolved', 'layer', 'decision_path', 'confidence', 'reason'].join(',')
      ];
      for (const e of sortedEvents) {
        const row = [
          e.row_index ?? '',
          `"${(e.original || '').replace(/"/g, '""')}"`,
          `"${(e.resolved || '').replace(/"/g, '""')}"`,
          e.layer || '',
          mapLayerToDecisionPath(e.layer),
          e.confidence ?? '',
          `"${(e.reason || '').replace(/"/g, '""')}"`
        ];
        csvRows.push(row.join(','));
      }
      const csvContent = csvRows.join('\n');
      const csvHash = await computeSHA256(csvContent);

      zip.file('results.csv', csvContent);
      manifest.files.push('results.csv');
      manifest.hashes['results.csv'] = csvHash;

      // 2. Generate audit.json
      const summary = getAuditSummary(batch);
      const auditJson = JSON.stringify(summary, Object.keys(summary).sort(), 2);
      const auditHash = await computeSHA256(auditJson);

      zip.file('audit.json', auditJson);
      manifest.files.push('audit.json');
      manifest.hashes['audit.json'] = auditHash;

      // 3. Try to get certificate.pdf
      let certIncluded = false;
      try {
        const certResult = await downloadCertificate(batch.trace_id);
        if (certResult.ok && certResult.blob) {
          const certBytes = await certResult.blob.arrayBuffer();
          const certHash = await computeSHA256(certBytes);

          zip.file('certificate.pdf', certBytes);
          manifest.files.push('certificate.pdf');
          manifest.hashes['certificate.pdf'] = certHash;
          certIncluded = true;
        }
      } catch (certErr) {
        console.warn('Certificate not available:', certErr.message);
      }

      if (!certIncluded) {
        manifest.certificate_note = 'Certificate not available at time of generation';
      }

      // 3b. Add Transparency & Limitations Statement (TLS) if available
      let tlsIncluded = false;
      if (batch.transparency_statement?.content) {
        const tlsContent = batch.transparency_statement.content;
        const tlsHash = batch.transparency_statement.hash || await computeSHA256(tlsContent);

        zip.file('transparency_statement.txt', tlsContent);
        manifest.files.push('transparency_statement.txt');
        manifest.hashes['transparency_statement.txt'] = tlsHash;
        manifest.tls_template_id = batch.transparency_statement.template_id || 'TLS_v1';
        tlsIncluded = true;
      }

      if (!tlsIncluded) {
        manifest.tls_note = 'Transparency statement not available (batch created before TLS support)';
      }

      // 4. Compute batch hash
      const batchHash = await computeBatchHash(batch);
      manifest.batch_hash = batchHash;

      // 5. Sign manifest and get public key (v1.2)
      let signatureIncluded = false;
      try {
        // Create manifest JSON without signature fields for signing
        const manifestForSigning = { ...manifest };
        delete manifestForSigning.signature;
        delete manifestForSigning.signature_algorithm;
        const manifestJsonForSigning = JSON.stringify(manifestForSigning, null, 2);

        // Sign the manifest
        const signResult = await signManifest(manifestJsonForSigning);
        if (signResult.ok && signResult.data?.signature) {
          manifest.signature = signResult.data.signature;
          manifest.signature_algorithm = signResult.data.algorithm;

          // Add signature file
          zip.file('manifest.sig', signResult.data.signature);
          manifest.files.push('manifest.sig');
          signatureIncluded = true;

          // Get public key
          const pkResult = await fetchManifestPublicKey();
          if (pkResult.ok && pkResult.data?.public_key_pem) {
            zip.file('public_key.pem', pkResult.data.public_key_pem);
            manifest.files.push('public_key.pem');
          }
        }
      } catch (signErr) {
        console.warn('Manifest signing not available:', signErr.message);
        manifest.signature_note = 'Signature not available - signing service unavailable';
      }

      if (!signatureIncluded) {
        manifest.signature_note = manifest.signature_note || 'Signature not available at time of generation';
      }

      // 6. Add manifest.json to ZIP (with signature info embedded)
      const manifestJson = JSON.stringify(manifest, null, 2);
      zip.file('manifest.json', manifestJson);

      // 7. Generate and download ZIP
      const zipBlob = await zip.generateAsync({ type: 'blob' });
      const url = URL.createObjectURL(zipBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `IA_EvidencePack_${batch.trace_id}_${configVersion}_${dateStr}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      // Store hashes for display
      storeArtifactHash(batch.trace_id, 'csv', csvHash);
      storeArtifactHash(batch.trace_id, 'audit', auditHash);
      if (manifest.hashes['certificate.pdf']) {
        storeArtifactHash(batch.trace_id, 'cert', manifest.hashes['certificate.pdf']);
      }
      if (signatureIncluded) {
        storeArtifactHash(batch.trace_id, 'signed', 'true');
      }

    } catch (err) {
      setEvidenceError(err.message || 'Failed to build evidence pack');
    } finally {
      setBuildingZip(false);
    }
  };

  // --- DOWNLOAD COMPLIANCE PACKAGE (ZIP) v1.0 ---
  const handleDownloadCompliancePackage = async (batch) => {
    if (!batch?.trace_id) return;
    setBuildingComplianceZip(true);
    setEvidenceError(null);

    try {
      const complianceZip = new JSZip();
      const generatedAt = new Date();
      const dateStr = generatedAt.toISOString().split('T')[0];
      const configVersion = batch.config_version || 'unknown';
      const stats = batch.stats || {};
      const counts = batch.counts || {};
      const hasNewCounts = Object.keys(counts).length > 0;

      // Hash tenant_id for privacy
      const tenantIdHash = batch.tenant_id
        ? await computeSHA256(batch.tenant_id)
        : null;

      // 1. Generate SOC2_Evidence.json
      const soc2Evidence = {
        framework: 'SOC2 Type II',
        generated_at: generatedAt.toISOString(),
        trace_id: batch.trace_id,
        controls: {
          access_control: {
            control_id: 'CC6.1',
            description: 'Logical access to data is restricted',
            evidence: {
              tenant_isolation: true,
              tenant_id_hash: tenantIdHash ? tenantIdHash.slice(0, 16) + '...' : 'N/A',
              rbac_enabled: true,
              roles: ['user', 'auditor', 'admin'],
              authentication: 'Firebase ID Token (Google OAuth)'
            }
          },
          audit_trail: {
            control_id: 'CC7.2',
            description: 'System activities are logged and monitored',
            evidence: {
              batch_trace_id: batch.trace_id,
              events_logged: true,
              timestamp_recorded: batch.timestamp,
              deterministic_ordering: 'row_index',
              immutable_storage: 'Firestore'
            }
          },
          data_integrity: {
            control_id: 'CC6.6',
            description: 'Data integrity is maintained',
            evidence: {
              sha256_hashing: true,
              manifest_signing: 'RSA-SHA256',
              deterministic_outputs: true,
              config_version: configVersion
            }
          }
        },
        summary: {
          total_records: batch.total || batch.total_records || 0,
          auto_resolved_pct: batch.auto_resolved_pct || 0,
          flagged_for_review: batch.flagged_count || 0
        }
      };
      const soc2Json = JSON.stringify(soc2Evidence, null, 2);
      const soc2Hash = await computeSHA256(soc2Json);
      complianceZip.file('SOC2_Evidence.json', soc2Json);

      // 2. Generate EU_AI_Act_Transparency.json
      const euAiActTransparency = {
        regulation: 'EU AI Act (Article 13 - Transparency)',
        generated_at: generatedAt.toISOString(),
        trace_id: batch.trace_id,
        system_purpose: {
          description: 'Automated entity resolution for company name standardization',
          use_case: 'Data quality improvement and deduplication',
          risk_classification: 'Limited Risk (transparency requirements apply)'
        },
        data_source: {
          input_type: 'User-uploaded batch files (CSV, Excel, JSON)',
          total_records: batch.total || batch.total_records || 0,
          processing_timestamp: batch.timestamp
        },
        human_oversight: {
          human_in_the_loop: true,
          layer_4_flagged: hasNewCounts ? (counts.l4_flagged || counts.l4 || 0) : (stats.layer_4_human || 0),
          flagged_for_manual_review: batch.flagged_count || 0,
          automated_resolution_rate: (batch.auto_resolved_pct || 0) + '%'
        },
        risk_controls: {
          validation: {
            enabled: true,
            description: 'Multi-layer validation with confidence thresholds'
          },
          logging: {
            enabled: true,
            description: 'Complete audit trail with row-level traceability'
          },
          explainability: {
            enabled: true,
            description: 'Resolution layer and confidence score recorded per record'
          }
        },
        layer_breakdown: {
          L0_garbage: hasNewCounts ? (counts.l0_quarantined || counts.l0 || 0) : (stats.layer_0_garbage || 0),
          L1_deterministic: hasNewCounts ? (counts.l1_resolved || counts.l1 || 0) : ((stats.layer_1_exact || 0) + (stats.layer_1_norm || 0)),
          L2_vector: hasNewCounts ? (counts.l2_resolved || counts.l2 || 0) : (stats.layer_2_vector || 0),
          L3_llm: hasNewCounts ? (counts.l3_resolved || counts.l3 || 0) : (stats.layer_3_llm || 0),
          L4_human_review: hasNewCounts ? (counts.l4_flagged || counts.l4 || 0) : (stats.layer_4_human || 0)
        }
      };
      const euAiActJson = JSON.stringify(euAiActTransparency, null, 2);
      const euAiActHash = await computeSHA256(euAiActJson);
      complianceZip.file('EU_AI_Act_Transparency.json', euAiActJson);

      // 3. Generate Model_Governance.json
      const modelGovernance = {
        framework: 'Model Governance Documentation',
        generated_at: generatedAt.toISOString(),
        trace_id: batch.trace_id,
        config_version: configVersion,
        models: {
          L1_deterministic: {
            name: 'Exact Match + Normalization',
            version: 'builtin',
            type: 'Rule-based',
            deterministic: true,
            description: 'Case-insensitive exact match and text normalization'
          },
          L2_vector: {
            name: 'Embedding Similarity',
            version: 'text-embedding-3-small',
            type: 'Vector Search',
            deterministic: true,
            threshold: 0.55,
            description: 'OpenAI embeddings with cosine similarity'
          },
          L3_llm: {
            name: 'LLM Judge',
            version: 'gpt-4o-mini',
            type: 'Large Language Model',
            deterministic: false,
            temperature: 0,
            threshold: 0.70,
            description: 'GPT-4o-mini for semantic entity resolution',
            determinism_note: 'Temperature=0 for maximum reproducibility; minor variations possible'
          }
        },
        thresholds: {
          L2_similarity_threshold: 0.55,
          L3_confidence_threshold: 0.70,
          L4_escalation: 'Records below L3 threshold flagged for human review'
        },
        processing_stats: {
          L0_garbage: hasNewCounts ? (counts.l0_quarantined || counts.l0 || 0) : (stats.layer_0_garbage || 0),
          L1_exact: hasNewCounts ? (counts.l1_exact || 0) : (stats.layer_1_exact || 0),
          L1_normalized: hasNewCounts ? (counts.l1_norm || 0) : (stats.layer_1_norm || 0),
          L1_person: hasNewCounts ? (counts.l1_person || 0) : 0,
          L1_org: hasNewCounts ? (counts.l1_org || 0) : 0,
          L1_vessel: hasNewCounts ? (counts.l1_vessel || 0) : 0,
          L2_vector: hasNewCounts ? (counts.l2_resolved || counts.l2 || 0) : (stats.layer_2_vector || 0),
          L3_llm: hasNewCounts ? (counts.l3_resolved || counts.l3 || 0) : (stats.layer_3_llm || 0),
          L4_human: hasNewCounts ? (counts.l4_flagged || counts.l4 || 0) : (stats.layer_4_human || 0),
          total_cost_usd: stats.total_cost || batch.cost || 0
        },
        reproducibility: {
          manifest_version: '1.2',
          sha256_hashing: true,
          signed_manifest: 'RSA-SHA256',
          deterministic_ordering: 'Stable row_index ordering',
          config_version_tracked: true
        }
      };
      const modelGovJson = JSON.stringify(modelGovernance, null, 2);
      const modelGovHash = await computeSHA256(modelGovJson);
      complianceZip.file('Model_Governance.json', modelGovJson);

      // 4. Generate nested Evidence_Pack.zip
      const evidenceZip = new JSZip();
      const evidenceManifest = {
        manifest_version: '1.2',
        app_version: '8.2.2',
        trace_id: batch.trace_id,
        config_version: configVersion,
        generated_at: generatedAt.toISOString(),
        files: [],
        hashes: {},
        batch_hash: null,
        signature: null,
        signature_algorithm: null
      };

      // 4a. Fetch audit data for results.csv
      const auditResult = await fetchAudit(batch.trace_id, 10000);
      if (!auditResult.ok || !auditResult.data?.events) {
        throw new Error(auditResult.error || 'Failed to fetch audit data');
      }
      const events = auditResult.data.events;
      const sortedEvents = [...events].sort((a, b) => (a.row_index || 0) - (b.row_index || 0));

      const csvRows = [
        ['row_index', 'original', 'resolved', 'layer', 'decision_path', 'confidence', 'reason'].join(',')
      ];
      for (const e of sortedEvents) {
        csvRows.push([
          e.row_index ?? '',
          `"${(e.original || '').replace(/"/g, '""')}"`,
          `"${(e.resolved || '').replace(/"/g, '""')}"`,
          e.layer || '',
          mapLayerToDecisionPath(e.layer),
          e.confidence ?? '',
          `"${(e.reason || '').replace(/"/g, '""')}"`
        ].join(','));
      }
      const csvContent = csvRows.join('\n');
      const csvHash = await computeSHA256(csvContent);
      evidenceZip.file('results.csv', csvContent);
      evidenceManifest.files.push('results.csv');
      evidenceManifest.hashes['results.csv'] = csvHash;

      // 4b. Add audit.json
      const summary = getAuditSummary(batch);
      const auditJson = JSON.stringify(summary, Object.keys(summary).sort(), 2);
      const auditHash = await computeSHA256(auditJson);
      evidenceZip.file('audit.json', auditJson);
      evidenceManifest.files.push('audit.json');
      evidenceManifest.hashes['audit.json'] = auditHash;

      // 4c. Try to add certificate.pdf
      try {
        const certResult = await downloadCertificate(batch.trace_id);
        if (certResult.ok && certResult.blob) {
          const certBytes = await certResult.blob.arrayBuffer();
          const certHash = await computeSHA256(certBytes);
          evidenceZip.file('certificate.pdf', certBytes);
          evidenceManifest.files.push('certificate.pdf');
          evidenceManifest.hashes['certificate.pdf'] = certHash;
        }
      } catch (certErr) {
        console.warn('Certificate not available:', certErr.message);
      }

      // 4d. Compute batch hash
      const batchHash = await computeBatchHash(batch);
      evidenceManifest.batch_hash = batchHash;

      // 4e. Sign manifest
      let evidenceSignature = null;
      try {
        const manifestForSigning = { ...evidenceManifest };
        delete manifestForSigning.signature;
        delete manifestForSigning.signature_algorithm;
        const manifestJsonForSigning = JSON.stringify(manifestForSigning, null, 2);

        const signResult = await signManifest(manifestJsonForSigning);
        if (signResult.ok && signResult.data?.signature) {
          evidenceManifest.signature = signResult.data.signature;
          evidenceManifest.signature_algorithm = signResult.data.algorithm;
          evidenceSignature = signResult.data.signature;
          evidenceZip.file('manifest.sig', signResult.data.signature);
          evidenceManifest.files.push('manifest.sig');

          const pkResult = await fetchManifestPublicKey();
          if (pkResult.ok && pkResult.data?.public_key_pem) {
            evidenceZip.file('public_key.pem', pkResult.data.public_key_pem);
            evidenceManifest.files.push('public_key.pem');
          }
        }
      } catch (signErr) {
        console.warn('Manifest signing not available:', signErr.message);
      }

      // 4f. Add manifest.json to evidence ZIP
      const evidenceManifestJson = JSON.stringify(evidenceManifest, null, 2);
      evidenceZip.file('manifest.json', evidenceManifestJson);

      // 4g. Generate Evidence_Pack.zip blob
      const evidenceZipBlob = await evidenceZip.generateAsync({ type: 'blob' });
      const evidenceZipBytes = await evidenceZipBlob.arrayBuffer();
      const evidenceZipHash = await computeSHA256(evidenceZipBytes);
      complianceZip.file('Evidence_Pack.zip', evidenceZipBytes);

      // 5. Generate Compliance_Manifest.json
      const complianceManifest = {
        package_version: '1.0',
        generated_at: generatedAt.toISOString(),
        trace_id: batch.trace_id,
        tenant_id_hash: tenantIdHash,
        files: {
          'SOC2_Evidence.json': { hash: soc2Hash },
          'EU_AI_Act_Transparency.json': { hash: euAiActHash },
          'Model_Governance.json': { hash: modelGovHash },
          'Evidence_Pack.zip': { hash: evidenceZipHash }
        },
        evidence_pack_reference: {
          manifest_version: '1.2',
          batch_hash: batchHash,
          signature: evidenceSignature ? evidenceSignature.slice(0, 32) + '...' : null,
          signature_algorithm: evidenceSignature ? 'RSA-SHA256' : null
        }
      };
      const complianceManifestJson = JSON.stringify(complianceManifest, null, 2);
      complianceZip.file('Compliance_Manifest.json', complianceManifestJson);

      // 6. Download the compliance package
      const complianceZipBlob = await complianceZip.generateAsync({ type: 'blob' });
      const url = URL.createObjectURL(complianceZipBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `IA_CompliancePackage_${batch.trace_id}_${dateStr}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

    } catch (err) {
      setEvidenceError(err.message || 'Failed to build compliance package');
    } finally {
      setBuildingComplianceZip(false);
    }
  };

  // --- SHARE LINK HANDLER ---
  const handleCopyShareLink = async (batch) => {
    if (!batch?.trace_id) return;
    setCreatingShareLink(true);
    setShareSuccess(null);
    setEvidenceError(null);

    try {
      const result = await createShareLink(batch.trace_id);
      if (!result.ok || !result.data?.url) {
        throw new Error(result.error || 'Failed to create share link');
      }

      // Copy to clipboard
      await navigator.clipboard.writeText(result.data.url);
      setShareSuccess('Share link copied to clipboard');

      // Clear success message after 3 seconds
      setTimeout(() => setShareSuccess(null), 3000);

    } catch (err) {
      setEvidenceError(err.message || 'Failed to create share link');
    } finally {
      setCreatingShareLink(false);
    }
  };

  // --- COPY VERIFICATION LINK (PUBLIC) ---
  const handleCopyVerifyLink = async (batch) => {
    if (!batch?.trace_id) return;
    try {
      const verifyUrl = getPublicVerifyUrl(batch.trace_id);
      await navigator.clipboard.writeText(verifyUrl);
      setVerifyLinkCopied(true);
      setTimeout(() => setVerifyLinkCopied(false), 3000);
    } catch (err) {
      console.error('Failed to copy verification link:', err);
    }
  };

  // --- LOAD RESULTS (paginated, 250 per page) ---
  const RESULTS_PAGE_SIZE = 250;

  const handleLoadResults = async (batch, append = false) => {
    if (!batch?.trace_id) return;

    setResultsLoading(true);
    setResultsError(null);

    const offset = append && resultsPreview ? resultsPreview.length : 0;

    try {
      const result = await fetchBatchResults(batch.trace_id, RESULTS_PAGE_SIZE, offset);
      if (!result.ok || !result.data?.results) {
        const errMsg = result.error || 'Failed to fetch results';
        console.error(`[LoadResults] ${batch.trace_id}: ${errMsg}`);
        if (errMsg.includes('403')) {
          throw new Error('Access denied — you may not have permission to view this batch.');
        }
        if (errMsg.includes('401') || errMsg.includes('token')) {
          throw new Error('Authentication required — please sign in again.');
        }
        throw new Error(errMsg);
      }

      const incoming = result.data.results;
      const monolithTotal = result.data.total || 0;
      setResultsTotal(monolithTotal);

      // Shadow: PRE results + audit parity check (first page only, fire-and-forget)
      if (!append) {
        shadowPreBatchResults(batch.trace_id, monolithTotal);
        shadowPreAudit(batch.trace_id);
      }

      if (append && resultsPreview) {
        setResultsPreview([...resultsPreview, ...incoming]);
      } else {
        setResultsPreview(incoming);
      }
    } catch (err) {
      console.error('[LoadResults] Error:', err);
      setResultsError(err.message || 'Failed to load results');
    } finally {
      setResultsLoading(false);
    }
  };

  // --- ABORT BATCH HANDLER ---
  const handleAbortBatch = async (batch, e) => {
    if (e) e.stopPropagation();
    if (!batch?.trace_id) return;

    const status = batch.status || '';
    if (status !== 'queued' && status !== 'processing') {
      return; // Can only abort queued or processing batches
    }

    setAbortingBatchId(batch.trace_id);

    try {
      const result = await abortBatch(batch.trace_id);
      if (!result.ok) {
        throw new Error(result.error || 'Failed to abort batch');
      }

      // Immediate UI update: optimistically set status to aborted
      setBatches(prev => (prev || []).map(b =>
        b.trace_id === batch.trace_id ? { ...b, status: 'aborted' } : b
      ));

      // Also update selectedBatch if it's the one being aborted
      if (selectedBatch?.trace_id === batch.trace_id) {
        setSelectedBatch(prev => prev ? { ...prev, status: 'aborted' } : null);
      }

      // Short delay for Firestore propagation, then refresh to confirm server state
      setTimeout(() => loadHistory(), 500);

    } catch (err) {
      console.error('[abort] Error:', err);
      setHistoryError(err.message || 'Failed to abort batch');
    } finally {
      setAbortingBatchId(null);
    }
  };

  if (!isClient) return <div className="bg-[#050b14] min-h-screen" />;

  const resultStats = processingResults?.stats || null;

  return (
    <div style={{ backgroundColor: '#050b14', color: '#f1f5f9', minHeight: '100vh' }} className="font-sans antialiased selection:bg-cyan-900 selection:text-[#f1f5f9]">
      
      {/* Navigation */}
      <nav className="fixed top-0 inset-x-0 z-50 border-b border-[#1e293b] bg-[#050b14]/95 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-cyan-950 to-slate-900 border border-[#1e293b] flex items-center justify-center ">
              <BrainCircuit className="text-cyan-500" size={20} />
            </div>
            <div className="leading-tight text-left">
              <div className="font-bold text-[#f1f5f9] tracking-tight text-lg uppercase">Intelligent Analyst</div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-cyan-500/70 font-mono tracking-widest uppercase">Enterprise v8.2.2</span>
                {/* Environment Badge (read-only, build-time) */}
                <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${ENV_BADGE_STYLES[CURRENT_ENVIRONMENT].bg} ${ENV_BADGE_STYLES[CURRENT_ENVIRONMENT].border} ${ENV_BADGE_STYLES[CURRENT_ENVIRONMENT].text}`}>
                  {ENV_BADGE_STYLES[CURRENT_ENVIRONMENT].label}
                </span>
                {/* Region Badge */}
                {tenantRegion && (
                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${REGION_BADGE_STYLES[tenantRegion]?.bg || 'bg-slate-500/20'} ${REGION_BADGE_STYLES[tenantRegion]?.border || 'border-slate-500/40'} ${REGION_BADGE_STYLES[tenantRegion]?.text || 'text-gray-200'}`}>
                    {REGION_BADGE_STYLES[tenantRegion]?.label || tenantRegion.toUpperCase()}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex gap-1 items-center">
            {/* Primary Nav: UPLOAD → HISTORY → AUDIT LOG */}
            <NavItem active={activeTab === 'upload'} onClick={() => setActiveTab('upload')} label="Upload" icon={Upload} />
            <NavItem active={activeTab === 'history'} onClick={() => setActiveTab('history')} label="History" icon={History} />
            <NavItem active={activeTab === 'auditlog'} onClick={() => setActiveTab('auditlog')} label="Audit Log" icon={FileText} />

            {/* Tenant Switcher (Platform Admin Only) */}
            <TenantSwitcher
              onTenantChange={(tenantId) => {
                // Refresh data when tenant changes
                loadHistory();
              }}
              className="ml-2"
            />

            {/* Command Palette Trigger */}
            <button
              onClick={() => { setCmdPaletteOpen(true); setCmdQuery(''); }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono text-gray-200 hover:text-[#f1f5f9] bg-[#1e293b]/30 hover:bg-[#1e293b]/60 border border-[#1e293b] rounded transition-colors ml-2"
              title="Command Palette (Cmd+K)"
            >
              <kbd className="text-[9px]">⌘K</kbd>
            </button>

            {/* Admin Section */}
            <div className="w-px bg-[#1e293b] mx-2" />
            {isAdmin && <NavItem active={activeTab === 'config'} onClick={() => setActiveTab('config')} label="Config" icon={Terminal} />}
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 text-[10px] font-mono uppercase tracking-widest text-gray-200 hover:text-red-400 transition-colors border-b-2 border-transparent"
              title="Logout"
            >
              <LogOut size={14} />
              Logout
            </button>
          </div>
        </div>
      </nav>

      {/* Demo Mode Banner */}
      {isDemoMode && (
        <div className="fixed top-20 inset-x-0 z-40 bg-amber-500/20 border-b border-amber-500/40 py-2 px-6">
          <div className="max-w-7xl mx-auto flex items-center justify-center gap-2">
            <AlertTriangle size={14} className="text-amber-400" />
            <span className="text-amber-400 text-xs font-mono uppercase tracking-wider">
              Demo Mode — uploads disabled. Use TEST (localhost:5173) to upload.
            </span>
          </div>
        </div>
      )}

      <main className="pb-20 max-w-7xl mx-auto px-6 pt-40">

        {/* AUDIT LOG TAB */}
        {activeTab === 'auditlog' && (
          <AuditLog
            batches={historyData?.batches || []}
            loading={historyLoading}
          />
        )}

        {/* UPLOAD TAB */}
        {activeTab === 'upload' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="mb-8">
              <div className="flex items-center gap-3">
                <Badge>Entity Resolution</Badge>
                {isReadOnly && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-widest bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    <Lock size={10} /> Read-only (Auditor)
                  </span>
                )}
                {isDemoMode && !isReadOnly && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-widest bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    <AlertTriangle size={10} /> Demo Mode
                  </span>
                )}
              </div>
              <h2 className="text-3xl font-bold text-[#f1f5f9] mt-6 mb-4 uppercase tracking-tight">Upload & Process</h2>
              <p className="text-[#cbd5e1] max-w-3xl text-lg font-semibold leading-relaxed">
                {isDemoMode
                  ? "Demo mode — uploads disabled. View sample batch history and download evidence packs."
                  : isReadOnly
                    ? "You have read-only access. View batch history and download evidence packs."
                    : "Upload a CSV or text file with company names for batch resolution through the 4-layer waterfall."
                }
              </p>
            </div>

            {isUploadDisabled ? (
              <div
                className="border-2 border-dashed border-amber-500/30 bg-amber-500/5 p-12 text-center rounded-none"
                title={isDemoMode ? "Uploads disabled in Demo Mode" : "Uploads disabled for auditors"}
              >
                <Lock className="mx-auto text-amber-500/50 mb-4" size={48} />
                <p className="text-lg text-amber-400 font-semibold mb-2">Upload Disabled</p>
                <p className="text-sm text-gray-200">
                  {isDemoMode
                    ? "Demo Mode — uploads and destructive actions disabled."
                    : "Auditors have read-only access. Go to History to view batches and download evidence."
                  }
                </p>
                <button
                  onClick={() => setActiveTab('history')}
                  className="mt-4 px-4 py-2 bg-amber-500/10 text-amber-400 border border-amber-500/30 rounded text-xs font-mono uppercase hover:bg-amber-500/20 transition-colors"
                >
                  Go to History
                </button>
              </div>
            ) : (
              <>
                {/* Unified Resolution — mode selector removed */}
                <div className="mb-4 flex items-center gap-4">
                  <span className="text-gray-200 text-sm font-mono uppercase tracking-wider">Unified Resolution</span>
                  <span className="text-cyan-400 text-sm font-mono">(Auto Semantic Detection)</span>
                </div>

                {/* Schema Guidance */}
                <div className="mb-6 bg-[#0b1220] border border-[#1e293b] p-4">
                  <h4 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-2">Accepted Formats</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div>
                      <span className="text-gray-200 font-mono text-[10px] uppercase block mb-1">File Types</span>
                      <span className="text-[#cbd5e1]">.csv, .xlsx, .xls, .json, .txt</span>
                    </div>
                    <div>
                      <span className="text-gray-200 font-mono text-[10px] uppercase block mb-1">Recognized Column Names</span>
                      <span className="text-[#cbd5e1] text-[11px]">name, company_name, company, account, organization, entity, vendor, supplier, customer, input_text, full_name, subject ...</span>
                    </div>
                  </div>
                  <p className="text-[10px] text-gray-200 mt-2">Your file must contain a column with one of these names. The system auto-detects the correct column.</p>
                </div>

                <FileUploadZone
                  onFileSelect={handleFileSelect}
                  isProcessing={isProcessing}
                  uploadProgress={uploadProgress}
                  uploadPhase={uploadPhase}
                  preflightError={preflightError}
                  fileInfo={preflightFileInfo}
                  limits={backendLimits}
                />
              </>
            )}

            {/* Processing Error */}
            {processingError && (
              <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
                <XCircle className="text-red-400 shrink-0" size={20} />
                <div>
                  <p className="text-red-400 font-semibold">Processing Failed</p>
                  <p className="text-red-400/70 text-sm">{processingError}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* HISTORY TAB */}
        {activeTab === 'history' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="mb-8">
              <div className="flex items-center gap-3">
                <Badge color="violet">Batch History</Badge>
                {isAdmin && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-widest bg-red-500/10 text-red-400 border border-red-500/30">
                    <Shield size={10} /> Admin Mode
                  </span>
                )}
              </div>
              <h2 className="text-3xl font-bold text-[#f1f5f9] mt-6 mb-4 uppercase tracking-tight">Operations Console</h2>
            </div>

            {/* Latest Run Panel */}
            {(() => {
              const latestBatch = (historyData?.batches || [])[0];
              if (!latestBatch) return null;
              const { level: latestLevel, anomalies: latestAnomalies } = detectBatchAnomalies(latestBatch);
              const isAnomaly = latestLevel === 'anomaly' || latestLevel === 'failed';
              return (
                <div className={`bg-[#0b1220] border ${isAnomaly ? 'border-amber-500/50' : 'border-[#1e293b]'} p-6`}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest flex items-center gap-2">
                      <Zap size={12} />
                      Latest Run
                      {isAnomaly && (
                        <span className="ml-2 px-2 py-0.5 bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-[9px]">
                          ATTENTION
                        </span>
                      )}
                    </h3>
                    <button
                      onClick={() => setSelectedBatch(latestBatch)}
                      className="text-[10px] font-mono text-gray-200 hover:text-cyan-400 transition-colors flex items-center gap-1"
                    >
                      Inspect <ChevronRight size={12} />
                    </button>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div>
                      <span className="text-[10px] text-gray-200 font-mono uppercase block">Trace ID</span>
                      <code className="text-cyan-400 text-xs">{latestBatch.trace_id?.slice(0, 16)}</code>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-200 font-mono uppercase block">Status</span>
                      <div className="mt-0.5">{getStatusBadge(latestBatch)}</div>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-200 font-mono uppercase block">Records</span>
                      <span className="text-[#f1f5f9] text-lg font-bold font-mono">{latestBatch.total || latestBatch.total_records || 0}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-200 font-mono uppercase block">Auto-Resolved</span>
                      <span className={`text-lg font-bold font-mono ${isAnomaly ? 'text-amber-400' : 'text-cyan-400'}`}>
                        {latestBatch.auto_resolved_pct?.toFixed(1) || 0}%
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-200 font-mono uppercase block">Filename</span>
                      <span className="text-[#cbd5e1] text-xs truncate block" title={latestBatch.filename}>{latestBatch.filename}</span>
                    </div>
                  </div>
                  {/* Inline anomaly reasons */}
                  {isAnomaly && latestAnomalies.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-amber-500/20 flex items-start gap-2">
                      <AlertTriangle size={12} className="text-amber-400 mt-0.5 shrink-0" />
                      <span className="text-amber-400/80 text-xs">{latestAnomalies.join(' · ')}</span>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Admin: Compact Tenant Filter */}
            {isAdmin && (
              <div className="flex items-center gap-3 p-3 bg-[#0b1220] border border-red-500/20 rounded">
                <Shield size={14} className="text-red-400 shrink-0" />
                <span className="text-[10px] font-mono text-red-400 uppercase tracking-widest whitespace-nowrap">Admin</span>
                <select
                  value={selectedTenantFilter}
                  onChange={(e) => { setSelectedTenantFilter(e.target.value); loadHistory(e.target.value); }}
                  className="flex-1 bg-[#0b1220] border border-[#1e293b] text-[#f1f5f9] px-2 py-1.5 text-xs font-mono focus:border-red-500 outline-none rounded"
                >
                  <option value="">All Tenants</option>
                  {adminTenants.map((tenant) => (
                    <option key={tenant.tenant_id_hash} value={tenant.tenant_id_hash}>
                      {tenant.tenant_id_hash} ({tenant.batch_count_30d} batches)
                    </option>
                  ))}
                </select>
                <button
                  onClick={loadAdminTenants}
                  disabled={adminTenantsLoading}
                  className="text-[10px] font-mono text-gray-200 hover:text-red-400 transition-colors whitespace-nowrap"
                >
                  {adminTenantsLoading ? 'Loading...' : 'Refresh'}
                </button>
              </div>
            )}

            {/* Batch Details Slide-over Panel */}
            {selectedBatch && (
              <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setSelectedBatch(null)}>
                <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
                <div
                  className="relative w-full max-w-lg bg-[#0b1220] border-l border-[#1e293b] h-full overflow-y-auto animate-in slide-in-from-right duration-300"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="sticky top-0 bg-[#0b1220] border-b border-[#1e293b] p-4 flex items-center justify-between">
                    <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Batch Details</h3>
                    <div className="flex items-center gap-3">
                      {/* TrustSeal - Public Verification Badge */}
                      {selectedBatch.status === 'completed' && (
                        <TrustSeal
                          batchId={selectedBatch.trace_id}
                          href={getPublicVerifyUrl(selectedBatch.trace_id)}
                          label="Verified by IA"
                          size="small"
                        />
                      )}
                      <button onClick={() => setSelectedBatch(null)} className="text-gray-200 hover:text-[#f1f5f9] transition-colors">
                        <X size={18} />
                      </button>
                    </div>
                  </div>
                  <div className="p-6 space-y-6">
                    {/* Trace ID */}
                    <div>
                      <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Trace ID</label>
                      <div className="flex items-center gap-2 mt-1">
                        <code className="text-cyan-400 font-mono text-sm bg-[#1e293b]/50 px-2 py-1 rounded flex-1 truncate">
                          {selectedBatch.trace_id}
                        </code>
                        <button
                          onClick={() => copyToClipboard(selectedBatch.trace_id)}
                          className="p-1.5 hover:bg-[#1e293b] rounded transition-colors"
                          title="Copy Trace ID"
                        >
                          {copiedId === selectedBatch.trace_id ? (
                            <Check size={14} className="text-emerald-400" />
                          ) : (
                            <Copy size={14} className="text-gray-200" />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Status */}
                    <div>
                      <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Status</label>
                      <div className="mt-1">{getStatusBadge(selectedBatch)}</div>
                      {/* Processing state progress indicator */}
                      {(selectedBatch.status === 'queued' || selectedBatch.status === 'processing' || selectedBatch.status === 'uploading') && (
                        <div className="mt-3 bg-[#1e293b]/30 border border-[#1e293b] rounded p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Loader2 size={14} className="text-cyan-400 animate-spin" />
                            <span className="text-xs text-[#cbd5e1]">
                              {selectedBatch.status === 'uploading' ? 'File is being uploaded...' :
                               selectedBatch.status === 'queued' ? 'Batch is queued. Processing will begin shortly.' :
                               'Batch is being processed through the waterfall...'}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-[10px] font-mono text-gray-200">
                            <span className={selectedBatch.status === 'uploading' ? 'text-cyan-400' : 'text-emerald-400'}>Upload</span>
                            <span className="text-gray-200">-</span>
                            <span className={selectedBatch.status === 'queued' ? 'text-cyan-400' : selectedBatch.status === 'processing' ? 'text-emerald-400' : 'text-gray-200'}>Queued</span>
                            <span className="text-gray-200">-</span>
                            <span className={selectedBatch.status === 'processing' ? 'text-cyan-400' : 'text-gray-200'}>Processing</span>
                            <span className="text-gray-200">-</span>
                            <span className="text-gray-200">Complete</span>
                          </div>
                          <p className="text-[10px] text-gray-200 mt-2">Refresh history to check for updates.</p>
                        </div>
                      )}
                    </div>

                    {/* Filename */}
                    <div>
                      <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Filename</label>
                      <p className="text-[#f1f5f9] mt-1">{selectedBatch.filename}</p>
                    </div>

                    {/* Timestamp */}
                    <div>
                      <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Processed At</label>
                      <p className="text-[#cbd5e1] mt-1">{formatTimestamp(selectedBatch.timestamp)}</p>
                    </div>

                    {/* Pipeline Mode (auto-routed) */}
                    {(selectedBatch.classification_meta?.routing || selectedBatch.effective_mode || selectedBatch.dataset_type) && (
                      <div className="pt-4 border-t border-[#1e293b]">
                        <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Pipeline</label>
                        <div className="mt-1 flex items-center gap-2">
                          <span className={`text-xs font-mono px-2 py-0.5 border rounded ${
                            (selectedBatch.classification_meta?.mode || selectedBatch.dataset_type) === 'company'
                              ? 'text-cyan-400 border-cyan-500/40 bg-cyan-500/10'
                              : 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10'
                          }`}>
                            {(selectedBatch.classification_meta?.mode || selectedBatch.dataset_type) === 'company' ? 'Waterfall (L0–L4)' : 'Sanitize + Attest'}
                          </span>
                          {selectedBatch.classification_meta?.requested_mode === 'auto' && (
                            <span className="text-[10px] text-gray-200 font-mono">auto-routed</span>
                          )}
                        </div>
                        {selectedBatch.classification_meta?.routing?.routing_reason && (
                          <p className="text-[10px] text-gray-200 mt-1">{selectedBatch.classification_meta.routing.routing_reason}</p>
                        )}
                      </div>
                    )}

                    {/* Stats Grid */}
                    <div className="grid grid-cols-2 gap-4 pt-4 border-t border-[#1e293b]">
                      <div>
                        <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Total Records</label>
                        <p className="text-2xl text-[#f1f5f9] font-bold font-mono mt-1">{selectedBatch.total || selectedBatch.total_records || 0}</p>
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Auto-Resolved</label>
                        <p className="text-2xl text-cyan-400 font-bold font-mono mt-1">{selectedBatch.auto_resolved_pct?.toFixed(1) || 0}%</p>
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Flagged for Review</label>
                        <p className="text-2xl text-amber-400 font-bold font-mono mt-1">{selectedBatch.flagged_count || 0}</p>
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Duration</label>
                        <p className="text-2xl text-[#cbd5e1] font-bold font-mono mt-1">{(() => {
                          const ms = selectedBatch.duration_ms || (selectedBatch.duration_seconds ? selectedBatch.duration_seconds * 1000 : 0);
                          if (ms > 0) return `${(ms / 1000).toFixed(1)}s`;
                          // Fallback: compute from timestamps
                          if (selectedBatch.finished_at && selectedBatch.timestamp) {
                            const diff = (new Date(selectedBatch.finished_at) - new Date(selectedBatch.timestamp)) / 1000;
                            if (diff > 0) return `${diff.toFixed(1)}s`;
                          }
                          return selectedBatch.status === 'completed' ? '—' : '0.0s';
                        })()}</p>
                      </div>
                    </div>

                    {/* Cost */}
                    <div className="pt-4 border-t border-[#1e293b]">
                      <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">API Cost</label>
                      <p className="text-2xl text-emerald-400 font-bold font-mono mt-1">
                        ${(selectedBatch.stats?.total_cost || selectedBatch.cost || 0).toFixed(4)}
                      </p>
                    </div>

                    {/* Anomaly Explanation */}
                    {(() => {
                      const { level, anomalies } = detectBatchAnomalies(selectedBatch);
                      if (level !== 'anomaly') return null;
                      return (
                        <div className="pt-4 border-t border-amber-500/30">
                          <label className="text-[10px] font-mono text-amber-400 uppercase tracking-widest flex items-center gap-2">
                            <AlertTriangle size={12} /> Anomalies Detected
                          </label>
                          <ul className="mt-2 space-y-1">
                            {anomalies.map((a, i) => (
                              <li key={i} className="text-amber-400/80 text-xs flex items-start gap-2">
                                <span className="text-amber-500 mt-0.5">-</span>
                                {a}
                              </li>
                            ))}
                          </ul>
                        </div>
                      );
                    })()}

                    {/* Waterfall Distribution */}
                    {(() => {
                      const stats = selectedBatch.stats || {};
                      const counts = selectedBatch.counts || {};
                      const total = selectedBatch.total || selectedBatch.total_records || 1;
                      const layers = [
                        { key: 'L0', label: 'L0 Garbage', count: counts.l0_quarantined || counts.l0 || stats.layer_0_garbage || 0, color: 'text-gray-200', bg: 'bg-gray-200/20' },
                        { key: 'L1', label: 'L1 Deterministic', count: counts.l1_resolved || counts.l1 || ((stats.layer_1_exact || 0) + (stats.layer_1_norm || 0) + (stats.layer_1_mixed_person || 0) + (stats.layer_1_mixed_org || 0) + (stats.layer_1_mixed_vessel || 0)), color: 'text-emerald-400', bg: 'bg-emerald-500/20' },
                        { key: 'L2', label: 'L2 Vector', count: counts.l2_resolved || counts.l2 || stats.layer_2_vector || 0, color: 'text-cyan-400', bg: 'bg-cyan-500/20' },
                        { key: 'L3', label: 'L3 LLM', count: counts.l3_resolved || counts.l3 || stats.layer_3_llm || 0, color: 'text-violet-400', bg: 'bg-violet-500/20' },
                        { key: 'L4', label: 'L4 Human Review', count: counts.l4_flagged || counts.l4 || stats.layer_4_human || 0, color: 'text-amber-400', bg: 'bg-amber-500/20' },
                      ];
                      const hasData = layers.some(l => l.count > 0);
                      if (!hasData) return null;
                      return (
                        <div className="pt-4 border-t border-[#1e293b]">
                          <label className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-3 block">Waterfall Distribution</label>
                          <div className="space-y-2">
                            {layers.map(l => (
                              <div key={l.key} className="flex items-center gap-2">
                                <span className={`text-[10px] font-mono w-28 ${l.color}`}>{l.label}</span>
                                <div className="flex-1 h-4 bg-[#1e293b]/50 rounded overflow-hidden">
                                  <div
                                    className={`h-full ${l.bg} rounded`}
                                    style={{ width: `${Math.max((l.count / total) * 100, l.count > 0 ? 2 : 0)}%` }}
                                  />
                                </div>
                                <span className={`text-xs font-mono w-16 text-right ${l.color}`}>
                                  {l.count} <span className="text-gray-200">({((l.count / total) * 100).toFixed(0)}%)</span>
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}

                    {/* Schema / Input Column */}
                    {(selectedBatch.detected_column || selectedBatch.schema_info) && (
                      <div className="pt-4 border-t border-[#1e293b]">
                        <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Detected Schema</label>
                        <p className="text-[#cbd5e1] text-xs font-mono mt-1">
                          Column: <span className="text-cyan-400">{selectedBatch.detected_column || selectedBatch.schema_info?.column || 'name'}</span>
                          {selectedBatch.schema_info?.total_columns && (
                            <span className="text-gray-200 ml-2">({selectedBatch.schema_info.total_columns} columns total)</span>
                          )}
                        </p>
                      </div>
                    )}

                    {/* Config Version */}
                    {selectedBatch.config_version && (
                      <div className="pt-4 border-t border-[#1e293b]">
                        <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Config Version</label>
                        <p className="text-gray-200 font-mono text-sm mt-1">{selectedBatch.config_version}</p>
                      </div>
                    )}

                    {/* Batch Label */}
                    <div className="pt-4 border-t border-[#1e293b]">
                      <label className="text-[10px] font-mono text-gray-200 uppercase tracking-widest">Label</label>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {BATCH_LABEL_OPTIONS.map(lbl => {
                          const active = batchLabels[selectedBatch.trace_id] === lbl;
                          return (
                            <button
                              key={lbl}
                              onClick={() => setBatchLabel(selectedBatch.trace_id, active ? null : lbl)}
                              className={`px-2 py-0.5 text-[9px] font-mono uppercase border rounded transition-colors ${active ? BATCH_LABEL_COLORS[lbl] : 'bg-[#1e293b]/30 text-gray-200 border-[#1e293b] hover:border-gray-400'}`}
                            >
                              {lbl}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* Fast Actions */}
                    <div className="pt-4 border-t border-[#1e293b]">
                      <div className="grid grid-cols-4 gap-2">
                        <button
                          onClick={() => handleLoadResults(selectedBatch)}
                          disabled={resultsLoading}
                          className="flex flex-col items-center gap-1 p-2 bg-[#1e293b]/30 hover:bg-[#1e293b]/60 border border-[#1e293b] rounded transition-colors text-[9px] font-mono uppercase text-gray-200 hover:text-cyan-400"
                        >
                          <FileText size={14} />
                          Results
                        </button>
                        <button
                          onClick={() => setShowAuditSummary(true)}
                          className="flex flex-col items-center gap-1 p-2 bg-[#1e293b]/30 hover:bg-[#1e293b]/60 border border-[#1e293b] rounded transition-colors text-[9px] font-mono uppercase text-gray-200 hover:text-violet-400"
                        >
                          <FileJson size={14} />
                          Audit
                        </button>
                        <button
                          onClick={() => handleDownloadEvidencePack(selectedBatch)}
                          disabled={buildingZip}
                          className="flex flex-col items-center gap-1 p-2 bg-[#1e293b]/30 hover:bg-[#1e293b]/60 border border-[#1e293b] rounded transition-colors text-[9px] font-mono uppercase text-gray-200 hover:text-emerald-400 disabled:opacity-50"
                        >
                          <Package size={14} />
                          Evidence
                        </button>
                        <button
                          onClick={() => setCompareMode(true)}
                          className="flex flex-col items-center gap-1 p-2 bg-[#1e293b]/30 hover:bg-[#1e293b]/60 border border-[#1e293b] rounded transition-colors text-[9px] font-mono uppercase text-gray-200 hover:text-amber-400"
                        >
                          <Sliders size={14} />
                          Compare
                        </button>
                      </div>
                    </div>

                    {/* Forensic Verification Panel (Days 11-13) */}
                    <ForensicPanel
                      batch={selectedBatch}
                      verificationData={forensicData}
                      loading={forensicLoading}
                      className="mt-6"
                    />

                    {/* Results Explorer */}
                    <div className="pt-6 border-t border-[#1e293b] space-y-3">
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] font-mono text-emerald-400 uppercase tracking-widest">Results Explorer</label>
                        <div className="flex items-center gap-2">
                          {resultsPreview && (
                            <button
                              onClick={() => setResultsPreview(null)}
                              className="text-[10px] font-mono text-gray-200 hover:text-[#f1f5f9]"
                            >
                              Close
                            </button>
                          )}
                          {!resultsPreview && (
                            <button
                              onClick={() => handleLoadResults(selectedBatch)}
                              disabled={resultsLoading}
                              className="text-xs text-cyan-400 hover:text-cyan-300 disabled:opacity-50 font-mono"
                            >
                              {resultsLoading ? 'Loading...' : 'Load Results'}
                            </button>
                          )}
                        </div>
                      </div>

                      {resultsError && (
                        <div className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 p-2 rounded">
                          {resultsError}
                        </div>
                      )}

                      {resultsLoading && (
                        <div className="flex items-center justify-center py-8">
                          <Loader2 className="text-cyan-400 animate-spin" size={24} />
                        </div>
                      )}

                      {resultsPreview && resultsPreview.length > 0 && (() => {
                        // Filter logic
                        const layerBadge = (layer) => {
                          const l = layer || '';
                          if (l.startsWith('L0')) return 'bg-red-500/20 text-red-400';
                          if (l.startsWith('L1')) return 'bg-emerald-500/20 text-emerald-400';
                          if (l.startsWith('L2')) return 'bg-cyan-500/20 text-cyan-400';
                          if (l.startsWith('L3')) return 'bg-violet-500/20 text-violet-400';
                          if (l.startsWith('L4')) return 'bg-amber-500/20 text-amber-400';
                          return 'bg-slate-500/20 text-gray-200';
                        };

                        let filtered = resultsPreview;

                        // Layer filter
                        if (resultsLayerFilter) {
                          filtered = filtered.filter(r => (r.layer || '').toUpperCase().startsWith(resultsLayerFilter));
                        }

                        // Confidence bucket filter
                        if (resultsConfFilter) {
                          filtered = filtered.filter(r => {
                            const conf = r.confidence ?? r.sanitization_confidence ?? null;
                            if (conf === null || !isFinite(conf)) return resultsConfFilter === 'none';
                            if (resultsConfFilter === 'high') return conf >= 0.8;
                            if (resultsConfFilter === 'medium') return conf >= 0.5 && conf < 0.8;
                            if (resultsConfFilter === 'low') return conf > 0 && conf < 0.5;
                            if (resultsConfFilter === 'none') return conf === 0 || conf === null;
                            return true;
                          });
                        }

                        // Anomaly/garbage/review filter
                        if (resultsAnomalyFilter) {
                          filtered = filtered.filter(r => {
                            const l = (r.layer || '').toUpperCase();
                            if (resultsAnomalyFilter === 'garbage') return l.startsWith('L0');
                            if (resultsAnomalyFilter === 'review') return l.startsWith('L4');
                            if (resultsAnomalyFilter === 'unresolved') return !r.resolved && !r.sanitized_name && !r.canonical_name;
                            return true;
                          });
                        }

                        // Text search
                        if (resultsTextSearch.trim()) {
                          const q = resultsTextSearch.trim().toLowerCase();
                          filtered = filtered.filter(r =>
                            (r.original || r.company_raw || '').toLowerCase().includes(q) ||
                            (r.resolved || r.sanitized_name || r.canonical_name || '').toLowerCase().includes(q) ||
                            (r.layer || '').toLowerCase().includes(q) ||
                            (r.reason || r.match_reason || '').toLowerCase().includes(q)
                          );
                        }

                        return (
                          <div className="space-y-2">
                            {/* Filter bar */}
                            <div className="flex flex-wrap items-center gap-2 pb-2 border-b border-[#1e293b]/50">
                              <input
                                type="text"
                                value={resultsTextSearch}
                                onChange={(e) => setResultsTextSearch(e.target.value)}
                                placeholder="Search rows..."
                                className="bg-[#0b1220] border border-[#1e293b] text-[#f1f5f9] text-[10px] font-mono px-2 py-1 rounded outline-none focus:border-cyan-500 w-28"
                              />
                              <select
                                value={resultsLayerFilter}
                                onChange={(e) => setResultsLayerFilter(e.target.value)}
                                className="bg-[#0b1220] border border-[#1e293b] text-[#f1f5f9] text-[10px] font-mono px-1.5 py-1 rounded outline-none focus:border-cyan-500"
                              >
                                <option value="">All Layers</option>
                                <option value="L0">L0 Garbage</option>
                                <option value="L1">L1 Deterministic</option>
                                <option value="L2">L2 Vector</option>
                                <option value="L3">L3 LLM</option>
                                <option value="L4">L4 Review</option>
                              </select>
                              <select
                                value={resultsConfFilter}
                                onChange={(e) => setResultsConfFilter(e.target.value)}
                                className="bg-[#0b1220] border border-[#1e293b] text-[#f1f5f9] text-[10px] font-mono px-1.5 py-1 rounded outline-none focus:border-cyan-500"
                              >
                                <option value="">All Confidence</option>
                                <option value="high">{"High (\u22650.8)"}</option>
                                <option value="medium">{"Medium (0.5\u20130.8)"}</option>
                                <option value="low">{"Low (<0.5)"}</option>
                                <option value="none">No score</option>
                              </select>
                              <select
                                value={resultsAnomalyFilter}
                                onChange={(e) => setResultsAnomalyFilter(e.target.value)}
                                className="bg-[#0b1220] border border-[#1e293b] text-[#f1f5f9] text-[10px] font-mono px-1.5 py-1 rounded outline-none focus:border-cyan-500"
                              >
                                <option value="">All Rows</option>
                                <option value="garbage">Garbage (L0)</option>
                                <option value="review">Review Queue (L4)</option>
                                <option value="unresolved">Unresolved</option>
                              </select>
                              {(resultsLayerFilter || resultsConfFilter || resultsTextSearch || resultsAnomalyFilter) && (
                                <button
                                  onClick={() => { setResultsLayerFilter(''); setResultsConfFilter(''); setResultsTextSearch(''); setResultsAnomalyFilter(''); }}
                                  className="text-[10px] font-mono text-gray-200 hover:text-[#f1f5f9]"
                                >
                                  Clear
                                </button>
                              )}
                              <span className="text-[10px] font-mono text-gray-200 ml-auto">
                                {filtered.length}{filtered.length !== resultsPreview.length ? ` / ${resultsPreview.length}` : ''}{resultsTotal > resultsPreview.length ? ` of ${resultsTotal}` : ''} rows
                              </span>
                            </div>

                            {/* Results table */}
                            <div className="max-h-[500px] overflow-y-auto border border-[#1e293b] rounded">
                              <table className="w-full text-xs">
                                <thead className="bg-[#1e293b]/50 sticky top-0">
                                  <tr>
                                    <th className="text-left p-2 text-gray-200 font-mono w-8">#</th>
                                    <th className="text-left p-2 text-gray-200 font-mono">Original</th>
                                    <th className="text-left p-2 text-gray-200 font-mono">Resolved</th>
                                    <th className="text-left p-2 text-gray-200 font-mono w-20">Layer</th>
                                    <th className="text-left p-2 text-gray-200 font-mono w-14">Conf</th>
                                    <th className="text-left p-2 text-gray-200 font-mono">Reason</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-[#1e293b]/50">
                                  {filtered.length === 0 ? (
                                    <tr>
                                      <td colSpan={6} className="p-4 text-center text-gray-200 text-xs">
                                        No rows match filters
                                      </td>
                                    </tr>
                                  ) : (
                                    filtered.map((row, idx) => {
                                      const original = row.original || row.company_raw || '—';
                                      const resolved = row.resolved || row.sanitized_name || row.canonical_name || '—';
                                      const layer = row.layer || '?';
                                      const conf = row.confidence ?? row.sanitization_confidence ?? null;
                                      const reason = row.reason || row.match_reason || row.garbage_reason || '';
                                      const isGarbage = layer.toUpperCase().startsWith('L0');
                                      const isReview = layer.toUpperCase().startsWith('L4');
                                      const isUnresolved = resolved === '—';

                                      return (
                                        <tr
                                          key={idx}
                                          className={`hover:bg-[#1e293b]/30 cursor-pointer ${isGarbage ? 'bg-red-500/[0.03]' : isReview ? 'bg-amber-500/[0.03]' : ''}`}
                                          onClick={() => setSelectedRow(row)}
                                        >
                                          <td className="p-2 text-gray-200 font-mono text-[10px]">{row.row_index ?? idx}</td>
                                          <td className="p-2 text-[#cbd5e1] max-w-[100px] truncate" title={original}>
                                            {original}
                                          </td>
                                          <td className={`p-2 max-w-[100px] truncate ${isUnresolved ? 'text-gray-200 italic' : 'text-emerald-400'}`} title={resolved}>
                                            {resolved}
                                          </td>
                                          <td className="p-2">
                                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${layerBadge(layer)}`}>
                                              {layer}
                                            </span>
                                          </td>
                                          <td className="p-2 font-mono text-[10px]">
                                            {conf !== null ? (
                                              <span className={conf >= 0.8 ? 'text-emerald-400' : conf >= 0.5 ? 'text-amber-400' : 'text-red-400'}>
                                                {(conf * 100).toFixed(0)}%
                                              </span>
                                            ) : (
                                              <span className="text-gray-200">—</span>
                                            )}
                                          </td>
                                          <td className="p-2 text-gray-200 text-[10px] max-w-[120px] truncate" title={reason}>
                                            {reason || '—'}
                                          </td>
                                        </tr>
                                      );
                                    })
                                  )}
                                </tbody>
                              </table>
                            </div>

                            {/* Load More — shown when more pages are available */}
                            {resultsTotal > resultsPreview.length && (
                              <div className="flex items-center justify-center pt-3">
                                <button
                                  onClick={() => handleLoadResults(selectedBatch, true)}
                                  disabled={resultsLoading}
                                  className="text-xs text-cyan-400 hover:text-cyan-300 disabled:opacity-50 font-mono border border-cyan-500/30 px-3 py-1.5 rounded hover:bg-cyan-500/10 transition-colors"
                                >
                                  {resultsLoading ? 'Loading...' : `Load next ${Math.min(RESULTS_PAGE_SIZE, resultsTotal - resultsPreview.length)} rows`}
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })()}

                      {resultsPreview && resultsPreview.length === 0 && (
                        <div className="text-gray-200 text-xs bg-[#1e293b]/30 p-3 rounded">
                          <p className="font-semibold text-gray-200">No row data available</p>
                          <p className="mt-1">This batch may have been aborted before results were saved, or processing is still in progress.</p>
                        </div>
                      )}
                    </div>

                    {/* Row Forensic Drilldown Modal */}
                    {selectedRow && (
                      <div className="fixed inset-0 z-[60] flex items-center justify-center" onClick={() => setSelectedRow(null)}>
                        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
                        <div
                          className="relative bg-[#0b1220] border border-[#1e293b] rounded-lg max-w-md w-full mx-4 max-h-[80vh] overflow-y-auto animate-in zoom-in-95 duration-150"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="sticky top-0 bg-[#0b1220] border-b border-[#1e293b] p-4 flex items-center justify-between">
                            <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Row Forensic Detail</h3>
                            <button onClick={() => setSelectedRow(null)} className="text-gray-200 hover:text-[#f1f5f9]">
                              <X size={16} />
                            </button>
                          </div>
                          <div className="p-4 space-y-4">
                            {(() => {
                              const r = selectedRow;
                              const original = r.original || r.company_raw || '—';
                              const resolved = r.resolved || r.sanitized_name || r.canonical_name || '—';
                              const layer = r.layer || '?';
                              const conf = r.confidence ?? r.sanitization_confidence ?? null;
                              const reason = r.reason || r.match_reason || r.garbage_reason || '';
                              const isGarbage = layer.toUpperCase().startsWith('L0');
                              const isReview = layer.toUpperCase().startsWith('L4');
                              const decisionPath = mapLayerToDecisionPath(layer);

                              const fields = [
                                { label: 'Original Value', value: original, mono: false, full: true },
                                { label: 'Resolved Value', value: resolved, mono: false, full: true, color: resolved === '—' ? 'text-gray-200' : 'text-emerald-400' },
                                { label: 'Layer', value: layer, mono: true, badge: true },
                                { label: 'Decision Path', value: decisionPath, mono: true },
                                { label: 'Confidence', value: conf !== null ? `${(conf * 100).toFixed(1)}%` : 'No score', mono: true, color: conf === null ? 'text-gray-200' : conf >= 0.8 ? 'text-emerald-400' : conf >= 0.5 ? 'text-amber-400' : 'text-red-400' },
                                { label: 'Reason', value: reason || 'Not provided', mono: false, full: true, color: reason ? 'text-[#cbd5e1]' : 'text-gray-200' },
                              ];

                              // Add optional backend metadata fields
                              if (r.org_category) fields.push({ label: 'Entity Category', value: r.org_category, mono: true });
                              if (r.org_name) fields.push({ label: 'Organization Name', value: r.org_name, mono: false });
                              if (r.match_type) fields.push({ label: 'Match Type', value: r.match_type, mono: true });
                              if (r.matched_canonical) fields.push({ label: 'Matched Canonical', value: r.matched_canonical, mono: false });
                              if (r.similarity_score != null) fields.push({ label: 'Similarity Score', value: r.similarity_score.toFixed(4), mono: true });
                              if (r.row_index != null) fields.push({ label: 'Row Index', value: String(r.row_index), mono: true });
                              if (r.trace_id || selectedBatch?.trace_id) fields.push({ label: 'Batch Trace ID', value: r.trace_id || selectedBatch?.trace_id, mono: true });

                              return (
                                <>
                                  {/* Anomaly flags */}
                                  {(isGarbage || isReview) && (
                                    <div className={`flex items-center gap-2 p-2 rounded ${isGarbage ? 'bg-red-500/10 border border-red-500/20' : 'bg-amber-500/10 border border-amber-500/20'}`}>
                                      <AlertTriangle size={14} className={isGarbage ? 'text-red-400' : 'text-amber-400'} />
                                      <span className={`text-xs ${isGarbage ? 'text-red-400' : 'text-amber-400'}`}>
                                        {isGarbage ? 'Quarantined as garbage (L0)' : 'Flagged for human review (L4)'}
                                      </span>
                                    </div>
                                  )}

                                  {/* Fields */}
                                  <div className="space-y-3">
                                    {fields.map((f, i) => (
                                      <div key={i} className={f.full ? '' : 'inline-block mr-6'}>
                                        <label className="text-[9px] font-mono text-gray-200 uppercase tracking-widest block">{f.label}</label>
                                        {f.badge ? (
                                          <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-mono mt-1 ${
                                            layer.startsWith('L0') ? 'bg-red-500/20 text-red-400' :
                                            layer.startsWith('L1') ? 'bg-emerald-500/20 text-emerald-400' :
                                            layer.startsWith('L2') ? 'bg-cyan-500/20 text-cyan-400' :
                                            layer.startsWith('L3') ? 'bg-violet-500/20 text-violet-400' :
                                            layer.startsWith('L4') ? 'bg-amber-500/20 text-amber-400' :
                                            'bg-slate-500/20 text-gray-200'
                                          }`}>{f.value}</span>
                                        ) : (
                                          <p className={`mt-0.5 text-sm ${f.color || 'text-[#f1f5f9]'} ${f.mono ? 'font-mono text-xs' : ''} break-all`}>
                                            {f.value}
                                          </p>
                                        )}
                                      </div>
                                    ))}
                                  </div>

                                  {/* Raw JSON (collapsed) */}
                                  <details className="pt-3 border-t border-[#1e293b]">
                                    <summary className="text-[9px] font-mono text-gray-200 uppercase tracking-widest cursor-pointer hover:text-[#f1f5f9]">
                                      Raw Row Data
                                    </summary>
                                    <pre className="mt-2 text-[9px] font-mono text-[#cbd5e1] bg-[#1e293b]/30 p-2 rounded overflow-x-auto max-h-[200px]">
                                      {JSON.stringify(r, null, 2)}
                                    </pre>
                                  </details>
                                </>
                              );
                            })()}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Actions — Share & Evidence consolidated */}
                    <div className="pt-6 border-t border-[#1e293b] space-y-3">
                      <label className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Actions</label>

                      {shareSuccess && (
                        <div className="text-emerald-400 text-xs bg-emerald-500/10 border border-emerald-500/20 p-2 rounded flex items-center gap-2">
                          <Check size={12} /> {shareSuccess}
                        </div>
                      )}

                      {evidenceError && (
                        <div className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 p-2 rounded">
                          {evidenceError}
                        </div>
                      )}

                      {/* Primary: Download results */}
                      <div className="grid grid-cols-2 gap-2">
                        {selectedBatch?.mode !== 'person' && (
                          <button
                            onClick={() => handleExportCSV(selectedBatch)}
                            disabled={exportingCSV}
                            className="flex items-center justify-center gap-2 px-3 py-2.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded hover:bg-cyan-500/20 transition-colors text-xs font-mono uppercase tracking-wider disabled:opacity-50 disabled:cursor-wait"
                          >
                            {exportingCSV ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />}
                            {exportingCSV ? 'Exporting...' : 'Export CSV'}
                          </button>
                        )}
                        {selectedBatch?.mode === 'person' && (
                          <button
                            onClick={() => handleDownloadSanitizedOutput(selectedBatch)}
                            disabled={downloadingSanitized}
                            className="flex items-center justify-center gap-2 px-3 py-2.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded hover:bg-emerald-500/20 transition-colors text-xs font-mono uppercase tracking-wider disabled:opacity-50 disabled:cursor-wait"
                          >
                            {downloadingSanitized ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                            {downloadingSanitized ? 'Downloading...' : 'Sanitized CSV'}
                          </button>
                        )}
                        <button
                          onClick={() => setShowAuditSummary(true)}
                          className="flex items-center justify-center gap-2 px-3 py-2.5 bg-violet-500/10 text-violet-400 border border-violet-500/30 rounded hover:bg-violet-500/20 transition-colors text-xs font-mono uppercase tracking-wider"
                        >
                          <FileJson size={14} />
                          Audit Summary
                        </button>
                      </div>

                      {/* Secondary: Evidence packages */}
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          onClick={() => handleDownloadCertificate(selectedBatch)}
                          disabled={downloadingCert}
                          className="flex items-center justify-center gap-2 px-3 py-2.5 bg-amber-500/10 text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/20 transition-colors text-xs font-mono uppercase tracking-wider disabled:opacity-50 disabled:cursor-wait"
                        >
                          {downloadingCert ? <Loader2 size={14} className="animate-spin" /> : <Award size={14} />}
                          Certificate
                        </button>
                        <button
                          onClick={() => handleDownloadEvidencePack(selectedBatch)}
                          disabled={buildingZip}
                          className="flex items-center justify-center gap-2 px-3 py-2.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded hover:bg-emerald-500/20 transition-colors text-xs font-mono uppercase tracking-wider disabled:opacity-50 disabled:cursor-wait"
                        >
                          {buildingZip ? <Loader2 size={14} className="animate-spin" /> : <Package size={14} />}
                          Evidence ZIP
                        </button>
                      </div>

                      <button
                        onClick={() => handleDownloadCompliancePackage(selectedBatch)}
                        disabled={buildingComplianceZip}
                        className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-violet-500/10 text-violet-400 border border-violet-500/30 rounded hover:bg-violet-500/20 transition-colors text-xs font-mono uppercase tracking-wider disabled:opacity-50 disabled:cursor-wait"
                      >
                        {buildingComplianceZip ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                        {buildingComplianceZip ? 'Building...' : 'Compliance Package'}
                      </button>

                      {/* Share & Verify links */}
                      <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[#1e293b]/50">
                        <button
                          onClick={() => handleCopyShareLink(selectedBatch)}
                          disabled={creatingShareLink}
                          className="flex items-center justify-center gap-2 px-3 py-2 bg-[#1e293b]/30 text-gray-200 hover:text-[#f1f5f9] border border-[#1e293b] rounded hover:bg-[#1e293b]/50 transition-colors text-[10px] font-mono uppercase tracking-wider disabled:opacity-50"
                        >
                          {creatingShareLink ? <Loader2 size={12} className="animate-spin" /> : <Share2 size={12} />}
                          Share Link
                        </button>
                        {selectedBatch.status === 'completed' && (
                          <button
                            onClick={() => handleCopyVerifyLink(selectedBatch)}
                            className="flex items-center justify-center gap-2 px-3 py-2 bg-[#1e293b]/30 text-gray-200 hover:text-emerald-400 border border-[#1e293b] rounded hover:bg-[#1e293b]/50 transition-colors text-[10px] font-mono uppercase tracking-wider"
                          >
                            {verifyLinkCopied ? <Check size={12} /> : <ShieldCheck size={12} />}
                            Verify Link
                          </button>
                        )}
                      </div>

                      {/* Trust Seal */}
                      {selectedBatch.status === 'completed' && (
                        <div className="flex items-center justify-between px-3 py-2 bg-emerald-500/5 border border-emerald-500/20 rounded">
                          <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400">Trust Seal</span>
                          <TrustSeal
                            batchId={selectedBatch.trace_id}
                            href={getPublicVerifyUrl(selectedBatch.trace_id)}
                            variant="compact"
                            label="View"
                          />
                        </div>
                      )}
                    </div>

                    {/* Reproducibility Hashes */}
                    <div className="pt-6 border-t border-[#1e293b] space-y-3">
                      <label className="text-[10px] font-mono text-emerald-400 uppercase tracking-widest flex items-center gap-2">
                        <Hash size={12} /> Reproducibility
                      </label>

                      {/* Cryptographic Signature Status - Always at TOP */}
                      {artifactHashes[selectedBatch.trace_id]?.signed && (
                        <div className="flex items-center gap-2 py-2 px-3 bg-emerald-500/10 border border-emerald-500/30 rounded">
                          <ShieldCheck size={16} className="text-emerald-400" />
                          <div>
                            <span className="text-emerald-400 font-semibold text-sm">
                              Cryptographically Signed — Verified
                            </span>
                            <p className="text-[10px] text-gray-200">
                              Manifest verified using system public key (RSA-SHA256)
                            </p>
                          </div>
                        </div>
                      )}

                      {/* Signature Invalid State */}
                      {artifactHashes[selectedBatch.trace_id]?.signatureFailed && (
                        <div className="flex items-center gap-2 py-2 px-3 bg-red-500/10 border border-red-500/30 rounded">
                          <XCircle size={16} className="text-red-400" />
                          <div>
                            <span className="text-red-400 font-semibold text-sm">
                              Signature Invalid
                            </span>
                            <p className="text-[10px] text-gray-200">
                              Manifest signature verification failed
                            </p>
                          </div>
                        </div>
                      )}

                      {/* Batch Hash */}
                      <div className="space-y-2">
                        <div className="text-[10px] text-gray-200 uppercase">Batch Hash</div>
                        <BatchHashDisplay batch={selectedBatch} computeBatchHash={computeBatchHash} copyToClipboard={copyToClipboard} copiedId={copiedId} />
                      </div>

                      {/* Artifact Hashes */}
                      {artifactHashes[selectedBatch.trace_id] && (
                        <div className="space-y-2 pt-2">
                          <div className="text-[10px] text-gray-200 uppercase">Artifact Hashes</div>

                          {artifactHashes[selectedBatch.trace_id].csv && (
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-gray-200 w-12">CSV:</span>
                              <code className="text-[9px] text-cyan-400 bg-[#1e293b]/50 px-1.5 py-0.5 rounded flex-1 truncate font-mono">
                                {artifactHashes[selectedBatch.trace_id].csv.slice(0, 16)}...
                              </code>
                              <button
                                onClick={() => copyToClipboard(artifactHashes[selectedBatch.trace_id].csv)}
                                className="p-1 hover:bg-[#334155] rounded transition-colors"
                                title="Copy full hash"
                              >
                                {copiedId === artifactHashes[selectedBatch.trace_id].csv ? (
                                  <Check size={10} className="text-emerald-400" />
                                ) : (
                                  <Copy size={10} className="text-gray-200" />
                                )}
                              </button>
                            </div>
                          )}

                          {artifactHashes[selectedBatch.trace_id].audit && (
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-gray-200 w-12">Audit:</span>
                              <code className="text-[9px] text-violet-400 bg-[#1e293b]/50 px-1.5 py-0.5 rounded flex-1 truncate font-mono">
                                {artifactHashes[selectedBatch.trace_id].audit.slice(0, 16)}...
                              </code>
                              <button
                                onClick={() => copyToClipboard(artifactHashes[selectedBatch.trace_id].audit)}
                                className="p-1 hover:bg-[#334155] rounded transition-colors"
                                title="Copy full hash"
                              >
                                {copiedId === artifactHashes[selectedBatch.trace_id].audit ? (
                                  <Check size={10} className="text-emerald-400" />
                                ) : (
                                  <Copy size={10} className="text-gray-200" />
                                )}
                              </button>
                            </div>
                          )}

                          {artifactHashes[selectedBatch.trace_id].cert && (
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-gray-200 w-12">Cert:</span>
                              <code className="text-[9px] text-amber-400 bg-[#1e293b]/50 px-1.5 py-0.5 rounded flex-1 truncate font-mono">
                                {artifactHashes[selectedBatch.trace_id].cert.slice(0, 16)}...
                              </code>
                              <button
                                onClick={() => copyToClipboard(artifactHashes[selectedBatch.trace_id].cert)}
                                className="p-1 hover:bg-[#334155] rounded transition-colors"
                                title="Copy full hash"
                              >
                                {copiedId === artifactHashes[selectedBatch.trace_id].cert ? (
                                  <Check size={10} className="text-emerald-400" />
                                ) : (
                                  <Copy size={10} className="text-gray-200" />
                                )}
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {!artifactHashes[selectedBatch.trace_id] && (
                        <p className="text-[10px] text-gray-200 italic">Download artifacts to see hashes</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Audit Summary Modal */}
            {showAuditSummary && selectedBatch && (
              <div className="fixed inset-0 z-[60] flex items-center justify-center" onClick={() => setShowAuditSummary(false)}>
                <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
                <div
                  className="relative bg-[#0b1220] border border-[#1e293b] rounded-lg max-w-md w-full mx-4 max-h-[80vh] overflow-y-auto animate-in zoom-in-95 duration-200"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="sticky top-0 bg-[#0b1220] border-b border-[#1e293b] p-4 flex items-center justify-between">
                    <h3 className="text-[10px] font-mono text-violet-400 uppercase tracking-widest">Audit Summary</h3>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleDownloadAuditJSON(selectedBatch)}
                        className="p-1.5 hover:bg-[#1e293b] rounded transition-colors text-gray-200 hover:text-[#f1f5f9]"
                        title="Download JSON"
                      >
                        <Download size={14} />
                      </button>
                      <button onClick={() => setShowAuditSummary(false)} className="text-gray-200 hover:text-[#f1f5f9] transition-colors">
                        <X size={18} />
                      </button>
                    </div>
                  </div>
                  <div className="p-4 space-y-4 font-mono text-xs">
                    {(() => {
                      const summary = getAuditSummary(selectedBatch);
                      if (!summary) return null;
                      return (
                        <>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <span className="text-gray-200">Trace ID</span>
                              <p className="text-cyan-400 truncate" title={summary.trace_id}>{summary.trace_id}</p>
                            </div>
                            <div>
                              <span className="text-gray-200">Timestamp</span>
                              <p className="text-[#cbd5e1]">{formatTimestamp(summary.timestamp)}</p>
                            </div>
                          </div>

                          <div className="border-t border-[#1e293b] pt-3">
                            <span className="text-gray-200">Filename</span>
                            <p className="text-[#f1f5f9]">{summary.filename}</p>
                          </div>

                          <div className="grid grid-cols-3 gap-3 border-t border-[#1e293b] pt-3">
                            <div>
                              <span className="text-gray-200">Total</span>
                              <p className="text-[#f1f5f9] text-lg font-bold">{summary.total_records}</p>
                            </div>
                            <div>
                              <span className="text-gray-200">Auto-Resolved</span>
                              <p className="text-cyan-400 text-lg font-bold">{summary.auto_resolved_pct?.toFixed(1)}%</p>
                            </div>
                            <div>
                              <span className="text-gray-200">Flagged</span>
                              <p className="text-amber-400 text-lg font-bold">{summary.flagged_count}</p>
                            </div>
                          </div>

                          {/* ═══ VISUAL LOCK: Layer Counts (bound to backend counts) ═══ */}
                          <div className="border-t border-[#1e293b] pt-3">
                            <span className="text-gray-200 block mb-2 flex items-center gap-2">
                              Layer Counts
                              <span className="text-[8px] text-emerald-500/60 font-mono">[BACKEND]</span>
                            </span>
                            <div className="grid grid-cols-2 gap-2 text-[10px]">
                              <div className="flex justify-between"><span className="text-gray-200">L0 Quarantined:</span><span className="text-gray-200">{summary.layer_counts.L0_garbage}</span></div>
                              <div className="flex justify-between"><span className="text-gray-200">L1 Resolved:</span><span className="text-cyan-400">{summary.layer_counts.L1_exact + summary.layer_counts.L1_normalized}</span></div>
                              <div className="flex justify-between pl-3"><span className="text-gray-200">└ Exact:</span><span className="text-cyan-400/70">{summary.layer_counts.L1_exact}</span></div>
                              <div className="flex justify-between pl-3"><span className="text-gray-200">└ Normalized:</span><span className="text-cyan-400/70">{summary.layer_counts.L1_normalized}</span></div>
                              <div className="flex justify-between"><span className="text-gray-200">L2 Vector:</span><span className="text-violet-400">{summary.layer_counts.L2_vector}</span></div>
                              <div className="flex justify-between"><span className="text-gray-200">L3 Resolved:</span><span className="text-amber-400">{summary.layer_counts.L3_llm}</span></div>
                              <div className="flex justify-between"><span className="text-gray-200">L4 Flagged:</span><span className="text-red-400">{summary.layer_counts.L4_human}</span></div>
                            </div>
                          </div>

                          {/* ═══ VISUAL LOCK: L3 Instrumentation (attempted vs skipped) ═══ */}
                          {summary.l3_metrics && (
                            <div className="border-t border-[#1e293b] pt-3">
                              <span className="text-gray-200 block mb-2 flex items-center gap-2">
                                L3 Instrumentation
                                <span className="text-[8px] text-emerald-500/60 font-mono">[BACKEND]</span>
                              </span>
                              <div className="grid grid-cols-2 gap-2 text-[10px]">
                                <div className="flex justify-between"><span className="text-gray-200">Eligible:</span><span className="text-amber-400">{summary.l3_metrics.eligible}</span></div>
                                <div className="flex justify-between"><span className="text-gray-200">Attempted:</span><span className="text-amber-400">{summary.l3_metrics.attempted}</span></div>
                                <div className="flex justify-between pl-3"><span className="text-gray-200">└ Succeeded:</span><span className="text-emerald-400">{summary.l3_metrics.succeeded}</span></div>
                                <div className="flex justify-between pl-3"><span className="text-gray-200">└ Failed:</span><span className="text-red-400">{summary.l3_metrics.failed}</span></div>
                                <div className="flex justify-between"><span className="text-gray-200">Skipped (Budget):</span><span className="text-gray-200">{summary.l3_metrics.skipped_budget}</span></div>
                                <div className="flex justify-between"><span className="text-gray-200">Skipped (Rate Limit):</span><span className="text-gray-200">{summary.l3_metrics.skipped_rate_limit}</span></div>
                              </div>
                              <div className="mt-2 text-[9px] flex items-center gap-1">
                                <span className="text-gray-200">Invariant:</span>
                                <code className="text-gray-200">{summary.l3_metrics.eligible} = {summary.l3_metrics.attempted} + {summary.l3_metrics.skipped_budget} + {summary.l3_metrics.skipped_rate_limit}</code>
                                <span className={summary.l3_metrics.invariant_valid ? 'text-emerald-400' : 'text-red-400'}>
                                  {summary.l3_metrics.invariant_valid ? '✓' : '✗'}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* ═══ VISUAL LOCK: LLM Budget Section ═══ */}
                          {summary.llm_budget && summary.llm_budget.budget_usd > 0 && (
                            <div className="border-t border-[#1e293b] pt-3">
                              <span className="text-gray-200 block mb-2 flex items-center gap-2">
                                Cost Summary
                                <span className="text-[8px] text-emerald-500/60 font-mono">[BACKEND]</span>
                              </span>
                              <div className="grid grid-cols-2 gap-2 text-[10px]">
                                <div className="flex justify-between"><span className="text-gray-200">Budget:</span><span className="text-gray-200">${summary.llm_budget.budget_usd}</span></div>
                                <div className="flex justify-between"><span className="text-gray-200">Spent:</span><span className="text-amber-400">${summary.llm_budget.spent_usd?.toFixed(4) || 0}</span></div>
                                <div className="flex justify-between"><span className="text-gray-200">Calls:</span><span className="text-amber-400">{summary.llm_budget.calls}</span></div>
                                <div className="flex justify-between"><span className="text-gray-200">Avg/Call:</span><span className="text-gray-200">${summary.llm_budget.avg_cost_per_call?.toFixed(6) || 0}</span></div>
                              </div>
                              {(summary.llm_budget.budget_exhausted || summary.llm_budget.call_cap_reached) && (
                                <p className="text-[9px] text-red-400/70 mt-1">
                                  {summary.llm_budget.budget_exhausted ? 'Budget exhausted' : 'Call cap reached'} → remaining routed to L4
                                </p>
                              )}
                            </div>
                          )}

                          {/* ═══ VISUAL LOCK: Lifecycle Timestamps ═══ */}
                          <div className="border-t border-[#1e293b] pt-3">
                            <span className="text-gray-200 block mb-2 flex items-center gap-2">
                              Lifecycle
                              <span className="text-[8px] text-emerald-500/60 font-mono">[BACKEND]</span>
                            </span>
                            <div className="grid grid-cols-2 gap-2 text-[10px]">
                              {summary.lifecycle.started_at && (
                                <div className="flex justify-between"><span className="text-gray-200">Started:</span><span className="text-[#cbd5e1]">{formatTimestamp(summary.lifecycle.started_at, 'time')}</span></div>
                              )}
                              {summary.lifecycle.finished_at && (
                                <div className="flex justify-between"><span className="text-gray-200">Finished:</span><span className="text-[#cbd5e1]">{formatTimestamp(summary.lifecycle.finished_at, 'time')}</span></div>
                              )}
                              <div className="flex justify-between"><span className="text-gray-200">Duration:</span><span className="text-[#cbd5e1]">{summary.lifecycle.duration_seconds.toFixed(2)}s</span></div>
                              <div className="flex justify-between"><span className="text-gray-200">Total Cost:</span><span className="text-emerald-400">${summary.total_cost.toFixed(4)}</span></div>
                            </div>
                          </div>

                          <div className="border-t border-[#1e293b] pt-3">
                            <span className="text-gray-200">Config Version</span>
                            <p className="text-gray-200">{summary.config_version}</p>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              </div>
            )}

            <div className="bg-[#0b1220] border border-[#1e293b]">
               <div className="p-4 border-b border-[#1e293b] flex justify-between items-center">
                 <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">
                   {isAdmin && selectedTenantFilter ? `Batches for ${selectedTenantFilter}` : 'Recent Batches'}
                 </h3>
                 <button onClick={() => loadHistory(selectedTenantFilter)} className="text-[10px] font-mono text-gray-200 hover:text-cyan-400 transition-colors">
                   {historyLoading ? 'Loading...' : 'Refresh'}
                 </button>
               </div>

               {/* Auth/API Error Display */}
               {historyError && (
                 <div className="p-4 bg-amber-500/10 border-b border-amber-500/30">
                   <div className="flex items-center gap-3">
                     <AlertTriangle className="text-amber-400 flex-shrink-0" size={20} />
                     <div>
                       <p className="text-amber-400 text-sm font-semibold">Unable to load batches</p>
                       <p className="text-amber-400/70 text-xs mt-1">{historyError}</p>
                     </div>
                     <button
                       onClick={() => loadHistory(selectedTenantFilter)}
                       className="ml-auto px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 text-xs font-mono rounded transition-colors"
                     >
                       Retry
                     </button>
                   </div>
                 </div>
               )}

               {!historyError && (historyData?.batches || []).length === 0 && (
                 <div className="p-12 text-center">
                   <FileText className="mx-auto text-gray-200 mb-4" size={32} />
                   <p className="text-gray-200 text-sm">No batches for this workspace yet.</p>
                   <p className="text-gray-200 text-xs mt-2">Upload a file to get started.</p>
                 </div>
               )}

               {!historyError && (historyData?.batches || []).length > 0 && (
                 <div className="overflow-x-auto">
                   <table className="w-full text-left font-mono text-[11px] font-semibold">
                     <thead>
                       <tr className="text-[#94a3b8] border-b border-[#334155] bg-[#0a101e]">
                         <th className="p-4">Trace ID</th>
                         <th className="p-4">Filename</th>
                         <th className="p-4">Status</th>
                         <th className="p-4">Timestamp</th>
                         <th className="p-4 text-right">Records</th>
                         <th className="p-4 text-right">Duration</th>
                         <th className="p-4 text-right">Auto-Resolved</th>
                         <th className="p-4 w-10"></th>
                       </tr>
                     </thead>
                     <tbody className="divide-y divide-[#1e293b]">
                       {(historyData?.batches || []).map((batch, i) => {
                         const { level: batchLevel, anomalies: batchAnomalies } = detectBatchAnomalies(batch);
                         const isAnomalous = batchLevel === 'anomaly' || batchLevel === 'failed';
                         const rowBorderClass = isAnomalous ? 'border-l-2 border-l-amber-500/60' : '';
                         return (
                         <tr
                           key={batch.trace_id || i}
                           className={`hover:bg-[#0f1a33] cursor-pointer group transition-colors ${rowBorderClass} ${isAnomalous ? 'bg-amber-500/[0.03]' : ''}`}
                           onClick={() => setSelectedBatch(batch)}
                         >
                           <td className="p-4">
                             <div className="flex items-center gap-2">
                               <code className="text-cyan-400 text-[10px] bg-[#1e293b]/50 px-1.5 py-0.5 rounded">
                                 {batch.trace_id?.slice(0, 16) || 'N/A'}
                               </code>
                               <button
                                 onClick={(e) => { e.stopPropagation(); copyToClipboard(batch.trace_id); }}
                                 className="p-1 hover:bg-[#334155] rounded transition-colors"
                                 title="Copy Trace ID"
                               >
                                 {copiedId === batch.trace_id ? (
                                   <Check size={12} className="text-emerald-400" />
                                 ) : (
                                   <Copy size={12} className="text-gray-200" />
                                 )}
                               </button>
                             </div>
                           </td>
                           <td className="p-4 max-w-[200px]">
                             <div className="flex items-center gap-2">
                               <span className="text-[#f1f5f9] font-semibold truncate" title={batch.filename}>{batch.filename}</span>
                               {batchLabels[batch.trace_id] && (
                                 <span className={`shrink-0 px-1.5 py-0.5 text-[8px] font-mono uppercase border rounded ${BATCH_LABEL_COLORS[batchLabels[batch.trace_id]] || 'bg-slate-500/20 text-gray-200 border-slate-500/30'}`}>
                                   {batchLabels[batch.trace_id]}
                                 </span>
                               )}
                             </div>
                           </td>
                           <td className="p-4">
                            <div className="flex items-center gap-2">
                              {getStatusBadge(batch)}
                              {(batch.status === 'queued' || batch.status === 'processing') && (
                                <button
                                  onClick={(e) => handleAbortBatch(batch, e)}
                                  disabled={abortingBatchId === batch.trace_id}
                                  className="p-1 hover:bg-red-900/50 rounded transition-colors text-red-400 hover:text-red-300 disabled:opacity-50"
                                  title="Abort batch"
                                >
                                  {abortingBatchId === batch.trace_id ? (
                                    <Loader2 size={14} className="animate-spin" />
                                  ) : (
                                    <StopCircle size={14} />
                                  )}
                                </button>
                              )}
                            </div>
                          </td>
                           <td className="p-4 text-[#64748b]">{formatTimestampShort(batch.timestamp)}</td>
                           <td className="p-4 text-right text-[#cbd5e1] font-semibold">{batch.total || batch.total_records || 0}</td>
                           <td className="p-4 text-right">{(() => {
                             const secs = batch.duration_seconds || (batch.duration_ms ? batch.duration_ms / 1000 : 0);
                             const durationStr = secs > 0 ? `${secs.toFixed(1)}s` :
                               (batch.finished_at && batch.timestamp) ?
                                 (() => { const d = (new Date(batch.finished_at) - new Date(batch.timestamp)) / 1000; return d > 0 ? `${d.toFixed(1)}s` : '—'; })() :
                               (batch.status === 'completed' ? '—' : '0.0s');
                             // Flag suspicious duration
                             const isSlow = secs > 1800 || ((batch.total || 0) < 1000 && secs > 300);
                             return <span className={isSlow ? 'text-amber-400' : 'text-emerald-400'}>{durationStr}</span>;
                           })()}</td>
                           <td className="p-4 text-right">
                             {(() => {
                               const pct = batch.auto_resolved_pct;
                               const val = pct?.toFixed(1) || '0';
                               const color = pct === 0 ? 'text-red-400 font-bold' : pct < 20 ? 'text-amber-400' : 'text-cyan-400';
                               return <span className={color}>{val}%</span>;
                             })()}
                           </td>
                           <td className="p-4">
                             <ChevronRight size={14} className="text-gray-200 group-hover:text-cyan-400 transition-colors" />
                           </td>
                         </tr>
                         );
                       })}
                     </tbody>
                   </table>
                 </div>
               )}
            </div>
          </div>
        )}

        {/* CONFIG TAB (RESTORED) */}
        {activeTab === 'config' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="mb-8">
              <Badge color="amber">Admin</Badge>
              <h2 className="text-3xl font-bold text-[#f1f5f9] mt-6 mb-4 uppercase tracking-tight">Configuration</h2>
            </div>
            <AdminPanel />
          </div>
        )}
      </main>


      {/* Batch Comparison Modal */}
      {compareMode && selectedBatch && (
        <BatchComparisonModal
          selectedBatch={selectedBatch}
          compareBatch={compareBatch}
          setCompareBatch={setCompareBatch}
          historyData={historyData}
          batchLabels={batchLabels}
          detectBatchAnomalies={detectBatchAnomalies}
          onClose={() => { setCompareMode(false); setCompareBatch(null); }}
        />
      )}

      {/* Command Palette (Cmd/Ctrl+K) */}
      {cmdPaletteOpen && (
        <CommandPalette
          query={cmdQuery}
          setQuery={setCmdQuery}
          commands={cmdPaletteCommands()}
          onClose={() => setCmdPaletteOpen(false)}
        />
      )}

      <footer className="bg-[#060c18] border-t border-[#1e293b] py-12 px-6 mt-20 pb-24">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <p className="text-[10px] font-mono uppercase tracking-widest text-gray-200">Intelligent Analyst 2026</p>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-gray-200">System Nominal</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
