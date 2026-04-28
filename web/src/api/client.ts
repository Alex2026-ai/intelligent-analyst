/**
 * API Client for Intelligent Analyst Enterprise
 *
 * Region-aware routing: same-region calls use relative /api/* paths,
 * cross-region calls use absolute URLs from VITE_API_BASE_URL_{REGION}.
 */

import { auth } from '../firebase';
import { resolveApiUrl } from './region';

// ============================================================================
// TYPES
// ============================================================================

export interface ApiHeaders {
  'Authorization'?: string;
  'X-Tenant-ID'?: string;
}

export interface HealthResponse {
  status: string;
  version?: string;
  service?: string;
  [key: string]: unknown;
}

export interface AuditEvent {
  row_index: number;
  company_raw: string;
  canonical_name: string;
  layer_used: number;
  confidence: number;
  latency_ms: number;
  flag?: string;
  pii_detected?: string[];
}

export interface AuditResponse {
  trace_id: string;
  events: AuditEvent[];
  count: number;
  source?: string;
}

export interface PaginatedAuditResponse {
  trace_id: string;
  events: AuditEvent[];
  count: number;
  has_more: boolean;
  next_cursor: number | null;
  source?: string;
  config_version?: string;
  timestamp?: string;
  total?: number;
  auto_resolved?: number;
  flagged_count?: number;
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
}

export interface UploadResult {
  ok: boolean;
  status: number;
  traceId: string | null;
  error: string | null;
  data: unknown;
}

// ============================================================================
// CONSTANTS
// ============================================================================

export const API_TIMEOUTS = {
  HEALTH_MS: 30_000,      // Increased from 10s for cold starts
  AUDIT_MS: 60_000,       // Increased from 30s for large batch operations
  UPLOAD_MS: 15 * 60 * 1000,
} as const;

export const API_LIMITS = {
  MAX_JSON_SIZE: 10 * 1024 * 1024,
  MAX_ERROR_LENGTH: 300,
  MAX_TRACE_ID_LENGTH: 100,
  AUDIT_FETCH_LIMIT: 5000,
} as const;

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Decode JWT payload without verification (for client-side assertion only).
 * The backend performs real verification via Firebase Admin SDK.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

const EXPECTED_ISS_PREFIX = 'https://securetoken.google.com/';

// Derived from VITE_FIREBASE_PROJECT_ID at build time — must match the Firebase project
// for this deployment. Fail-closed: if not set, token injection is blocked entirely.
const EXPECTED_AUD: string | undefined = import.meta.env.VITE_FIREBASE_PROJECT_ID;

/**
 * Get Firebase ID token if user is signed in.
 * Hard assertion: token MUST be a Firebase ID token (not gcloud, not OAuth).
 */
async function getIdToken(forceRefresh: boolean = false): Promise<string | null> {
  // Fail-closed: VITE_FIREBASE_PROJECT_ID must be set at build time
  if (!EXPECTED_AUD) {
    console.error('[AUTH] BLOCKED: VITE_FIREBASE_PROJECT_ID is not set. Cannot validate token audience.');
    return null;
  }

  const user = auth?.currentUser;
  if (!user) return null;
  try {
    const token = await user.getIdToken(forceRefresh);
    if (!token) return null;

    // Hard assertion: validate this is a Firebase ID token, not a gcloud/OAuth token
    const claims = decodeJwtPayload(token);
    if (claims) {
      const iss = String(claims.iss || '');
      const aud = String(claims.aud || '');

      if (!iss.startsWith(EXPECTED_ISS_PREFIX)) {
        console.error('[AUTH] REJECTED: token issuer is not Firebase.', { iss, expected: EXPECTED_ISS_PREFIX });
        return null;
      }
      if (aud !== EXPECTED_AUD) {
        console.error(`[AUTH] REJECTED: AUD mismatch: got "${aud}" expected "${EXPECTED_AUD}"`);
        return null;
      }

      // Dev-only: log token validation result
      if (import.meta.env.DEV || import.meta.env.VITE_ENVIRONMENT === 'TEST') {
        console.debug('[AUTH] Firebase ID token validated', {
          iss,
          aud,
          sub: claims.sub,
          email: claims.email,
          exp: claims.exp,
          iat: claims.iat,
        });
      }
    }

    return token;
  } catch {
    return null;
  }
}

// ============================================================================
// TENANT CONTEXT (Days 14-16)
// ============================================================================

// Active tenant ID for platform admin context switching
// This is set by TenantSwitcher component
let _activeTenantId: string | null = null;

/**
 * Set the active tenant ID for API requests.
 * Used by TenantSwitcher when platform admin switches context.
 */
export function setActiveTenantId(tenantId: string | null): void {
  console.log(`[API] Tenant context changed: ${_activeTenantId} -> ${tenantId}`);
  _activeTenantId = tenantId;
}

/**
 * Get the current active tenant ID.
 */
export function getActiveTenantId(): string | null {
  return _activeTenantId;
}

// Listen for tenant switch events from AuthContext
if (typeof window !== 'undefined') {
  window.addEventListener('tenantSwitched', ((event: CustomEvent<{ newTenant: string }>) => {
    setActiveTenantId(event.detail.newTenant);
  }) as EventListener);
}

/**
 * Build headers for API requests with Firebase auth and tenant context.
 *
 * SECURITY:
 * - X-Tenant-ID is only sent if explicitly set (platform admin mode)
 * - Server still enforces authorization - this header is advisory
 */
export async function buildHeaders(): Promise<ApiHeaders> {
  const token = await getIdToken(true);
  if (!token) {
    throw new Error("Firebase ID token missing");
  }
  const headers: ApiHeaders = {};
  headers['Authorization'] = `Bearer ${token}`;

  // Inject tenant context if set (platform admin switching)
  if (_activeTenantId) {
    (headers as Record<string, string>)['X-Tenant-ID'] = _activeTenantId;
  }

  return headers;
}

/**
 * Safe JSON parse with size limit
 */
function safeJsonParse<T>(text: string, fallback: T): T {
  if (!text || text.length > API_LIMITS.MAX_JSON_SIZE) return fallback;
  try {
    const parsed = JSON.parse(text);
    if (parsed === null || typeof parsed !== 'object') return fallback;
    return parsed as T;
  } catch {
    return fallback;
  }
}

/**
 * Strip HTML tags and collapse whitespace from error text.
 * Prevents raw upstream error pages from leaking into the UI.
 */
function stripHtml(s: string): string {
  return s.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
}

/**
 * Extract error message from response
 */
function extractError(json: unknown, text: string, status: number): string {
  const detail = (json as Record<string, unknown>)?.detail;
  const msg = typeof detail === 'string' ? detail : stripHtml(text);
  return `HTTP ${status}: ${msg.slice(0, API_LIMITS.MAX_ERROR_LENGTH)}`;
}

/**
 * Fetch with 401 retry (token refresh)
 */
async function fetchWithRetry(
  url: string,
  options: RequestInit
): Promise<Response> {
  const resolvedUrl = resolveApiUrl(url);
  const headers = await buildHeaders();
  const res = await fetch(resolvedUrl, {
    ...options,
    headers: { ...options.headers, ...headers } as HeadersInit,
  });

  // Handle 403 REGION_MISMATCH from backend
  if (res.status === 403) {
    try {
      const cloned = res.clone();
      const body = await cloned.json();
      if (body?.error === 'REGION_MISMATCH') {
        window.dispatchEvent(new CustomEvent('regionMismatch', { detail: body }));
        throw new Error(`Region mismatch: ${body.detail || 'Tenant is bound to a different region'}`);
      }
    } catch (e) {
      if ((e as Error)?.message?.startsWith('Region mismatch')) throw e;
      // Not JSON or not a region mismatch — fall through to normal handling
    }
  }

  if (res.status === 401 && auth?.currentUser) {
    // Refresh token and retry once
    const newToken = await getIdToken(true);
    if (newToken) {
      const retryHeaders: ApiHeaders = {
        'Authorization': `Bearer ${newToken}`,
      };
      return fetch(resolvedUrl, {
        ...options,
        headers: { ...options.headers, ...retryHeaders } as HeadersInit,
      });
    }
  }

  return res;
}

// ============================================================================
// API CLIENT (Same-origin paths only)
// ============================================================================

/**
 * Check demo mode status (no auth required)
 */
export async function fetchDemoStatus(
  signal?: AbortSignal
): Promise<{ ok: boolean; demoMode: boolean; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.HEALTH_MS);

    const res = await fetch(resolveApiUrl('/api/demo/status'), {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      return { ok: false, demoMode: false, error: `HTTP ${res.status}` };
    }

    const json = await res.json();
    return { ok: true, demoMode: json.demo_mode === true, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, demoMode: false, error: 'Request aborted' };
    }
    return { ok: false, demoMode: false, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Check API health
 */
export async function checkHealth(
  signal?: AbortSignal
): Promise<{ ok: boolean; data: HealthResponse | null; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.HEALTH_MS);

    const res = await fetchWithRetry('/api/health', {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<HealthResponse>(text, { status: 'unknown' });

    if (res.ok) {
      return { ok: true, data: json, error: null };
    }
    return { ok: false, data: null, error: extractError(json, text, res.status) };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Shadow PRE health check — fire-and-forget.
 *
 * Calls the PRE ia-api /health/ready endpoint through the /health/** rewrite.
 * Result is logged to console only — does NOT affect dashboard behavior.
 * This is the first dashboard→PRE traffic path, used to validate the
 * routing seam before migrating any business-critical reads.
 */
export async function shadowPreHealth(): Promise<void> {
  try {
    const res = await fetch('/health/ready', {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
    });
    const data = await res.json();
    const status = data?.status || 'unknown';
    const degraded = data?.degraded_modes || [];
    console.info(
      `[PRE shadow] health/ready: ${status}` +
      (degraded.length > 0 ? ` (degraded: ${degraded.join(', ')})` : '')
    );
  } catch (err) {
    console.warn('[PRE shadow] health/ready failed:', (err as Error)?.message || 'unknown');
  }
}

/**
 * Shadow PRE batch list — fire-and-forget (called once on first load).
 *
 * Calls PRE GET /v1/batches through the /v1/batches/** rewrite.
 * Compares count against monolith count for parity telemetry.
 */
export async function shadowPreBatchList(monolithCount: number): Promise<void> {
  try {
    const headers = await buildHeaders();
    const res = await fetch('/v1/batches/?limit=50', {
      method: 'GET',
      headers: { ...headers, 'Accept': 'application/json' },
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      const data = await res.json();
      const preCount = data?.batches?.length ?? 0;
      const preTotal = data?.total ?? 0;
      console.info(
        `[PRE shadow] batch list: ${preCount} batches (total=${preTotal}), monolith=${monolithCount}`
      );
    } else {
      console.info(`[PRE shadow] batch list: HTTP ${res.status}`);
    }
  } catch (err) {
    console.warn('[PRE shadow] batch list failed:', (err as Error)?.message || 'unknown');
  }
}

/**
 * Shadow PRE batch results — fire-and-forget (called once per results load).
 *
 * Calls PRE GET /v1/batches/{trace_id}/results through the /v1/batches/** rewrite.
 * Compares row count against monolith for parity telemetry.
 */
export async function shadowPreBatchResults(traceId: string, monolithTotal: number): Promise<void> {
  if (!traceId) return;
  try {
    const headers = await buildHeaders();
    const res = await fetch(`/v1/batches/${encodeURIComponent(traceId)}/results?limit=1&offset=0`, {
      method: 'GET',
      headers: { ...headers, 'Accept': 'application/json' },
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      const data = await res.json();
      console.info(
        `[PRE shadow] results ${traceId}: total=${data?.total}, monolith=${monolithTotal}`
      );
    } else {
      console.info(`[PRE shadow] results ${traceId}: HTTP ${res.status}`);
    }
  } catch (err) {
    console.warn('[PRE shadow] results failed:', (err as Error)?.message || 'unknown');
  }
}

/**
 * Shadow PRE audit event count — fire-and-forget.
 *
 * Calls PRE GET /v1/batches/{trace_id}/audit to compare audit event count.
 * Triggered once alongside results shadow for parity telemetry.
 */
export async function shadowPreAudit(traceId: string): Promise<void> {
  if (!traceId) return;
  try {
    const headers = await buildHeaders();
    const res = await fetch(`/v1/batches/${encodeURIComponent(traceId)}/audit?limit=1`, {
      method: 'GET',
      headers: { ...headers, 'Accept': 'application/json' },
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      const data = await res.json();
      console.info(`[PRE shadow] audit ${traceId}: ${data?.total ?? 0} events`);
    } else {
      console.info(`[PRE shadow] audit ${traceId}: HTTP ${res.status}`);
    }
  } catch (err) {
    console.warn('[PRE shadow] audit failed:', (err as Error)?.message || 'unknown');
  }
}

/**
 * Shadow PRE batch fetch — fire-and-forget.
 *
 * Calls PRE GET /v1/batches/{trace_id} through the /v1/batches/** rewrite.
 * Sends the dashboard's Firebase auth token so we can validate the full
 * auth pathway. Result is logged to console only — dashboard continues
 * using monolith data regardless of PRE response.
 */
export async function shadowPreForensic(traceId: string): Promise<void> {
  if (!traceId) return;
  try {
    const headers = await buildHeaders();
    const res = await fetch(`/v1/batches/${encodeURIComponent(traceId)}/forensic`, {
      method: 'GET',
      headers: { ...headers, 'Accept': 'application/json' },
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const data = await res.json();
      const s = data?.summary || {};
      console.info(
        `[PRE shadow] forensic ${traceId}: sig=${s.signature_present}, chain=${s.hash_chain_present}, anchor=${s.anchor_present}, hold=${s.legal_hold_active}`
      );
    } else {
      console.info(`[PRE shadow] forensic ${traceId}: HTTP ${res.status}`);
    }
  } catch (err) {
    console.warn('[PRE shadow] forensic failed:', (err as Error)?.message || 'unknown');
  }
}

export async function shadowPreBatch(traceId: string): Promise<void> {
  if (!traceId) return;
  try {
    const headers = await buildHeaders();
    const res = await fetch(`/v1/batches/${encodeURIComponent(traceId)}`, {
      method: 'GET',
      headers: { ...headers, 'Accept': 'application/json' },
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const data = await res.json();
      console.info(
        `[PRE shadow] batch ${traceId}: status=${data?.status}, total=${data?.total}`
      );
    } else {
      const text = await res.text().catch(() => '');
      console.info(
        `[PRE shadow] batch ${traceId}: HTTP ${res.status} (auth/routing gap — expected during migration)`
      );
    }
  } catch (err) {
    console.warn('[PRE shadow] batch fetch failed:', (err as Error)?.message || 'unknown');
  }
}

/**
 * Fetch audit trail for a trace ID
 */
export async function fetchAudit(
  traceId: string,
  limit: number = API_LIMITS.AUDIT_FETCH_LIMIT,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: AuditResponse | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  const url = `/api/audit/${encodeURIComponent(safeTraceId)}?limit=${limit}`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<AuditResponse>(text, { trace_id: '', events: [], count: 0 });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Fetch audit trail page with cursor-based pagination
 */
export async function fetchAuditPage(
  traceId: string,
  limit: number = 200,
  cursor?: number | null,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: PaginatedAuditResponse | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  let url = `/api/audit/${encodeURIComponent(safeTraceId)}?limit=${limit}`;
  if (cursor !== null && cursor !== undefined) {
    url += `&cursor=${cursor}`;
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<PaginatedAuditResponse>(text, {
      trace_id: '',
      events: [],
      count: 0,
      has_more: false,
      next_cursor: null,
    });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

// ============================================================================
// BATCH RESULTS (reads from results_chunks, not audit_events)
// ============================================================================

export interface BatchResultRecord {
  original?: string;
  resolved?: string;
  match_type?: string;
  match_id?: string;
  confidence?: number;
  layer?: string;
  decision?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface BatchResultsResponse {
  trace_id: string;
  total: number;
  offset: number;
  limit: number;
  count: number;
  results: BatchResultRecord[];
}

/**
 * Fetch batch results (paginated) from results_chunks subcollection.
 * This is the correct data source — audit_events only has META events.
 *
 * FIRST PRE DIRECT CUTOVER (dashboard-test only):
 * On TEST environment, reads from PRE ia-api via /v1/batches/{id}/results.
 * On PROD, continues using monolith /api/batches/{id}/results.
 * Response contract is identical — same fields, same pagination shape.
 * Rollback: remove the TEST branch below.
 */
export async function fetchBatchResults(
  traceId: string,
  limit: number = 100,
  offset: number = 0,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: BatchResultsResponse | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  // PRE direct cutover: dashboard-test uses PRE, all others use monolith.
  // Runtime detection — same build deployed to all targets.
  const isTestDashboard = window.location.hostname === 'intelligentanalyst-dashboard-test.web.app'
    || window.location.hostname === 'localhost';
  const url = isTestDashboard
    ? `/v1/batches/${encodeURIComponent(safeTraceId)}/results?limit=${limit}&offset=${offset}`
    : `/api/batches/${encodeURIComponent(safeTraceId)}/results?limit=${limit}&offset=${offset}`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<BatchResultsResponse>(text, {
      trace_id: '',
      total: 0,
      offset: 0,
      limit: 0,
      count: 0,
      results: [],
    });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Export batch results as CSV blob via backend export endpoint.
 * Reads from results_chunks (same source as working sanitized export).
 */
export async function fetchBatchExportCSV(
  traceId: string,
  format: string = 'csv',
  signal?: AbortSignal
): Promise<{ ok: boolean; blob: Blob | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, blob: null, error: 'Invalid trace ID' };
  }

  const url = `/api/batches/${encodeURIComponent(safeTraceId)}/export?format=${encodeURIComponent(format)}`;

  try {
    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      return { ok: false, blob: null, error: `HTTP ${res.status}: ${stripHtml(text).slice(0, 200)}` };
    }

    const blob = await res.blob();
    return { ok: true, blob, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, blob: null, error: 'Request aborted' };
    }
    return { ok: false, blob: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Download transparency certificate as blob
 */
export async function downloadCertificate(
  traceId: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; blob: Blob | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, blob: null, error: 'Invalid trace ID' };
  }

  const url = `/api/audit/${encodeURIComponent(safeTraceId)}/certificate`;

  try {
    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      return { ok: false, blob: null, error: `HTTP ${res.status}: ${stripHtml(text).slice(0, 200)}` };
    }

    const blob = await res.blob();
    return { ok: true, blob, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, blob: null, error: 'Request aborted' };
    }
    return { ok: false, blob: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Fetch batch history
 *
 * Fetch batch history — currently uses monolith on all targets.
 *
 * PRE batch list cutover was ROLLED BACK due to ia-api OOM:
 * PRE GET /v1/batches/ loads all batch docs into memory via .stream(),
 * which exceeds Cloud Run's 1GB limit under polling load. Restore
 * after PRE implements paginated Firestore query (not full collection scan).
 */
export async function fetchBatches(
  signal?: AbortSignal,
  tenantFilter?: string
): Promise<{ ok: boolean; status?: number; data: { batches: unknown[] } | null; role: string | null; demoMode: boolean; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    let url = '/api/batches';
    if (tenantFilter) {
      url += `?tenant=${encodeURIComponent(tenantFilter)}`;
    }

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<unknown>(text, {});

    if (!res.ok) {
      return { ok: false, status: res.status, data: null, role: null, demoMode: false, error: extractError(json, text, res.status) };
    }

    // Return the full response object with batches array
    const responseObj = json as Record<string, unknown>;
    const batches = Array.isArray(responseObj?.batches) ? responseObj.batches : [];
    const role = responseObj?.role as string ?? 'user';
    const demoMode = responseObj?.demo_mode === true;
    return { ok: true, status: res.status, data: { batches }, role, demoMode, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, role: null, demoMode: false, error: 'Request aborted' };
    }
    return { ok: false, data: null, role: null, demoMode: false, error: (err as Error)?.message || 'Unknown error' };
  }
}

// ============================================================================
// ADMIN CONSOLE API (Admin-only endpoints)
// ============================================================================

export interface TenantSummary {
  tenant_id_hash: string;
  batch_count_30d: number;
  last_batch_timestamp: string | null;
}

export interface AdminTenantsResponse {
  tenants: TenantSummary[];
  count: number;
  message: string;
}

/**
 * Fetch tenant list (admin only)
 */
export async function fetchAdminTenants(
  signal?: AbortSignal
): Promise<{ ok: boolean; data: TenantSummary[] | null; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry('/api/admin/tenants', {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<AdminTenantsResponse>(text, { tenants: [], count: 0, message: '' });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json.tenants, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

// ============================================================================
// EVIDENCE PACK v1.2 - MANIFEST SIGNING
// ============================================================================

export interface ManifestPublicKeyResponse {
  public_key_pem: string;
  algorithm: string;
  key_source: string;
}

export interface SignManifestResponse {
  signature: string;
  algorithm: string;
  encoding: string;
}

/**
 * Fetch the public key for manifest signature verification
 */
export async function fetchManifestPublicKey(
  signal?: AbortSignal
): Promise<{ ok: boolean; data: ManifestPublicKeyResponse | null; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.HEALTH_MS);

    const res = await fetchWithRetry('/api/security/manifest-public-key', {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<ManifestPublicKeyResponse>(text, { public_key_pem: '', algorithm: '', key_source: '' });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Sign a manifest JSON string with RSA-SHA256
 */
export async function signManifest(
  manifestJson: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: SignManifestResponse | null; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry('/api/sign-manifest', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ manifest_json: manifestJson }),
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<SignManifestResponse>(text, { signature: '', algorithm: '', encoding: '' });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Upload batch file via XHR (supports progress tracking)
 * Uses same-origin /api/batch-upload path
 */
export function uploadBatch(
  file: File,
  filename: string,
  _mode: string = 'mixed', // Deprecated: Semantic Unification — always auto-detect
  onProgress?: (progress: UploadProgress) => void,
  onProcessing?: () => void
): { abort: () => void; promise: Promise<UploadResult> } {
  const xhr = new XMLHttpRequest();

  const abort = () => {
    try {
      xhr.abort();
    } catch {
      // ignore
    }
  };

  const promise = (async (): Promise<UploadResult> => {
    const form = new FormData();
    try {
      form.append('file', file, filename.slice(0, 255));
    } catch (err) {
      return { ok: false, status: 0, traceId: null, error: `FormData: ${(err as Error)?.message}`, data: null };
    }

    // Get token before starting XHR
    const token = await getIdToken();

    return new Promise<UploadResult>((resolve) => {
      try {
        xhr.open('POST', resolveApiUrl('/api/batch-upload?mode=mixed'), true);
        xhr.timeout = API_TIMEOUTS.UPLOAD_MS;
        xhr.withCredentials = false;
        if (token) {
          xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        }
      } catch (err) {
        resolve({ ok: false, status: 0, traceId: null, error: `XHR setup: ${(err as Error)?.message}`, data: null });
        return;
      }

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress({
            loaded: e.loaded,
            total: e.total,
            percent: e.total > 0 ? Math.min(100, Math.round((e.loaded / e.total) * 100)) : 0,
          });
        }
      };

      xhr.upload.onload = () => {
        if (onProcessing) onProcessing();
      };

      xhr.onerror = () => {
        resolve({ ok: false, status: 0, traceId: null, error: 'Network error', data: null });
      };

      xhr.ontimeout = () => {
        resolve({ ok: false, status: 0, traceId: null, error: `Timeout (${API_TIMEOUTS.UPLOAD_MS / 60000}m)`, data: null });
      };

      xhr.onabort = () => {
        resolve({ ok: false, status: 0, traceId: null, error: 'Aborted', data: null });
      };

      xhr.onload = async () => {
        const status = xhr.status;
        const ok = status >= 200 && status < 300;
        let text = '';
        try {
          text = xhr.responseText || '';
        } catch {
          text = '';
        }

        // Handle 401 with token refresh and retry
        if (status === 401 && auth?.currentUser) {
          const newToken = await getIdToken(true);
          if (newToken) {
            // Retry with refreshed token
            const retryXhr = new XMLHttpRequest();
            retryXhr.open('POST', `/api/batch-upload?mode=${mode}`, true);
            retryXhr.timeout = API_TIMEOUTS.UPLOAD_MS;
            retryXhr.setRequestHeader("Authorization", `Bearer ${newToken}`);

            retryXhr.onload = () => {
              const retryStatus = retryXhr.status;
              const retryOk = retryStatus >= 200 && retryStatus < 300;
              let retryText = '';
              try {
                retryText = retryXhr.responseText || '';
              } catch {
                retryText = '';
              }

              const retryJson = safeJsonParse<Record<string, unknown>>(retryText, {});
              const retryTraceId = (
                retryJson.trace_id ?? retryJson.traceId ??
                (retryJson.data as unknown[])?.[0]?.['trace_id'] ??
                (retryJson.results as unknown[])?.[0]?.['trace_id'] ??
                null
              ) as string | null;

              if (!retryOk) {
                const detail = typeof retryJson.detail === 'string' ? retryJson.detail : stripHtml(retryText);
                resolve({
                  ok: false,
                  status: retryStatus,
                  traceId: retryTraceId?.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH) ?? null,
                  error: `HTTP ${retryStatus}: ${detail.slice(0, API_LIMITS.MAX_ERROR_LENGTH)}`,
                  data: retryJson,
                });
                return;
              }

              resolve({
                ok: true,
                status: retryStatus,
                traceId: retryTraceId?.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH) ?? null,
                error: null,
                data: retryJson,
              });
            };

            retryXhr.onerror = () => resolve({ ok: false, status: 0, traceId: null, error: 'Network error on retry', data: null });
            retryXhr.send(form);
            return;
          }
        }

        const json = safeJsonParse<Record<string, unknown>>(text, {});
        const traceId = (
          json.trace_id ?? json.traceId ??
          (json.data as unknown[])?.[0]?.['trace_id'] ??
          (json.results as unknown[])?.[0]?.['trace_id'] ??
          null
        ) as string | null;

        if (!ok) {
          const detail = typeof json.detail === 'string' ? json.detail : stripHtml(text);
          resolve({
            ok: false,
            status,
            traceId: traceId?.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH) ?? null,
            error: `HTTP ${status}: ${detail.slice(0, API_LIMITS.MAX_ERROR_LENGTH)}`,
            data: json,
          });
          return;
        }

        resolve({
          ok: true,
          status,
          traceId: traceId?.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH) ?? null,
          error: null,
          data: json,
        });
      };

      try {
        xhr.send(form);
      } catch (err) {
        resolve({ ok: false, status: 0, traceId: null, error: `Send: ${(err as Error)?.message}`, data: null });
      }
    });
  })();

  return { abort, promise };
}

// ============================================================================
// SHAREABLE BATCH LINKS
// ============================================================================

export interface ShareLinkResponse {
  share_token: string;
  url: string;
  expires_at: string;
  trace_id: string;
}

export interface SharedBatchResponse {
  batch: {
    trace_id: string;
    filename: string;
    timestamp: string;
    total: number;
    auto_resolved: number;
    auto_resolved_pct: number;
    flagged_count: number;
    duration_ms: number;
    config_version: string;
    stats: Record<string, unknown>;
  };
  events: unknown[];
  events_count: number;
  share_info: {
    created_at: string;
    expires_at: string;
    tenant_id_hash: string;
  };
  readonly: boolean;
}

/**
 * Create a share link for a batch
 */
export async function createShareLink(
  traceId: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: ShareLinkResponse | null; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(`/api/share/batch/${encodeURIComponent(traceId)}`, {
      method: 'POST',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<ShareLinkResponse>(text, { share_token: '', url: '', expires_at: '', trace_id: '' });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Resolve a share token (no auth required)
 */
export async function resolveShareLink(
  shareToken: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: SharedBatchResponse | null; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    // Note: This endpoint doesn't require auth, so we use plain fetch
    const res = await fetch(`/api/share/${encodeURIComponent(shareToken)}`, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<SharedBatchResponse>(text, {
      batch: { trace_id: '', filename: '', timestamp: '', total: 0, auto_resolved: 0, auto_resolved_pct: 0, flagged_count: 0, duration_ms: 0, config_version: '', stats: {} },
      events: [],
      events_count: 0,
      share_info: { created_at: '', expires_at: '', tenant_id_hash: '' },
      readonly: true
    });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Abort a batch (queued or processing)
 */
export async function abortBatch(
  traceId: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: { status: string; trace_id: string; message: string } | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(`/api/batches/${encodeURIComponent(safeTraceId)}/abort`, {
      method: 'POST',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<{ status: string; trace_id: string; message: string }>(text, { status: '', trace_id: '', message: '' });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Revoke a share link
 */
export async function revokeShareLink(
  shareToken: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; error: string | null }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(`/api/share/${encodeURIComponent(shareToken)}/revoke`, {
      method: 'POST',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const text = await res.text();
      const json = safeJsonParse<Record<string, unknown>>(text, {});
      return { ok: false, error: extractError(json, text, res.status) };
    }

    return { ok: true, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, error: 'Request aborted' };
    }
    return { ok: false, error: (err as Error)?.message || 'Unknown error' };
  }
}

// ============================================================================
// FORENSIC VERIFICATION APIs (Days 11-13)
// ============================================================================

export interface ForensicVerificationResponse {
  trace_id: string;
  status?: string;             // "PASS", "FAIL", or "NOT_AVAILABLE" (legacy)
  message?: string;            // Human-readable (legacy batches)
  signature_verified?: boolean;
  signature?: {
    evidence_hash_sha256: string;
    signature: string | null;
    signature_alg: string | null;
    signing_key_id: string | null;
    signing_key_version: string | null;
    signed_at_utc: string;
    signature_error?: string;
    service_identity?: {
      cloud_run_service: string;
      service_account_email: string;
      code_version: string;
      revision: string;
    };
  };
  hash_chain?: {
    chain_enabled: boolean;
    chain_length: number;
    batch_root_hash: string;
    verified: boolean;
  };
  anchor?: {
    anchored: boolean;
    anchor_target: string;
    anchored_at?: string;
    verified: boolean;
  };
}

export interface LegalHoldResponse {
  trace_id: string;
  legal_hold_enabled: boolean;
  hold_status: string;
  hold_record?: {
    hold_id: string;
    status: string;
    requested_by: string;
    requested_at_utc: string;
    reason: string;
    vault_objects_written_count: number;
    expires_at?: string;
  };
}

export interface RetentionStatusResponse {
  trace_id: string;
  retention_policy_enabled: boolean;
  evaluation?: {
    status: string;
    age_days: number;
    action: string;
    protected: boolean;
    reason: string;
    days_until_cold?: number;
    days_until_purge?: number;
  };
}

/**
 * Fetch batch verification data (signature, hash chain, anchor)
 */
export async function fetchBatchVerification(
  traceId: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: ForensicVerificationResponse | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  const url = `/api/batches/${encodeURIComponent(safeTraceId)}/verify`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<ForensicVerificationResponse>(text, {
      trace_id: '',
    });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Fetch legal hold status for a batch
 */
export async function fetchLegalHold(
  traceId: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: LegalHoldResponse | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  const url = `/api/audit/${encodeURIComponent(safeTraceId)}/hold`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<LegalHoldResponse>(text, {
      trace_id: '',
      legal_hold_enabled: false,
      hold_status: 'NONE',
    });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Place a legal hold on a batch
 */
export async function placeLegalHold(
  traceId: string,
  reason: string,
  expiresAt?: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: Record<string, unknown> | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  if (!reason || reason.length < 10) {
    return { ok: false, data: null, error: 'Reason must be at least 10 characters' };
  }

  const url = `/api/audit/${encodeURIComponent(safeTraceId)}/hold`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const body: Record<string, string> = { reason };
    if (expiresAt) {
      body.expires_at = expiresAt;
    }

    const res = await fetchWithRetry(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<Record<string, unknown>>(text, {});

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Release a legal hold on a batch
 */
export async function releaseLegalHold(
  traceId: string,
  reason: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: Record<string, unknown> | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  const url = `/api/audit/${encodeURIComponent(safeTraceId)}/release-hold`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ reason }),
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<Record<string, unknown>>(text, {});

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Fetch retention status for a batch
 */
export async function fetchRetentionStatus(
  traceId: string,
  signal?: AbortSignal
): Promise<{ ok: boolean; data: RetentionStatusResponse | null; error: string | null }> {
  const safeTraceId = traceId.slice(0, API_LIMITS.MAX_TRACE_ID_LENGTH).trim();
  if (!safeTraceId) {
    return { ok: false, data: null, error: 'Invalid trace ID' };
  }

  const url = `/api/batches/${encodeURIComponent(safeTraceId)}/retention`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.AUDIT_MS);

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<RetentionStatusResponse>(text, {
      trace_id: '',
      retention_policy_enabled: false,
    });

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

/**
 * Fetch security/integrity status
 */
export async function fetchIntegrityStatus(
  signal?: AbortSignal
): Promise<{ ok: boolean; data: Record<string, unknown> | null; error: string | null }> {
  const url = '/api/security/integrity';

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUTS.HEALTH_MS);

    const res = await fetchWithRetry(url, {
      method: 'GET',
      signal: signal ?? controller.signal,
    });

    clearTimeout(timeoutId);

    const text = await res.text();
    const json = safeJsonParse<Record<string, unknown>>(text, {});

    if (!res.ok) {
      return { ok: false, data: null, error: extractError(json, text, res.status) };
    }

    return { ok: true, data: json, error: null };
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { ok: false, data: null, error: 'Request aborted' };
    }
    return { ok: false, data: null, error: (err as Error)?.message || 'Unknown error' };
  }
}

// =============================================================================
// EVIDENCE PACK DOWNLOAD (Days 17-20)
// =============================================================================

/**
 * Download Nostrum-Grade Evidence Pack.
 *
 * Returns a ZIP file containing:
 * - results.csv
 * - certificate.pdf (with KMS signature and ESG metrics)
 * - manifest.json (SHA-256 hashes for integrity)
 * - audit_events.json
 * - evidence_summary.json
 */
export async function downloadEvidencePack(
  batchId: string,
  includeRaw: boolean = false
): Promise<{ ok: boolean; blob: Blob | null; error: string | null; metadata: Record<string, string> }> {
  const url = `/api/batches/${encodeURIComponent(batchId)}/evidence-pack?include_raw=${includeRaw}`;

  try {
    const headers = await buildHeaders();

    const res = await fetch(url, {
      method: 'GET',
      headers: headers as Record<string, string>,
    });

    if (!res.ok) {
      const text = await res.text();
      const json = safeJsonParse<Record<string, unknown>>(text, {});
      return {
        ok: false,
        blob: null,
        error: extractError(json, text, res.status),
        metadata: {},
      };
    }

    // Extract metadata from headers
    const metadata: Record<string, string> = {
      manifestHash: res.headers.get('X-Manifest-Hash') || '',
      certificateHash: res.headers.get('X-Certificate-Hash') || '',
      fileCount: res.headers.get('X-File-Count') || '',
    };

    // Get blob
    const blob = await res.blob();

    return {
      ok: true,
      blob,
      error: null,
      metadata,
    };
  } catch (err) {
    console.error('[API] Evidence pack download failed:', err);
    return {
      ok: false,
      blob: null,
      error: (err as Error)?.message || 'Download failed',
      metadata: {},
    };
  }
}
