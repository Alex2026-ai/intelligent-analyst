/**
 * Region-Aware API Routing
 *
 * Resolves API URLs based on the active tenant region.
 *
 * Routing logic (in order):
 * 1. If the active region has an absolute URL configured → use it (direct call)
 * 2. If activeRegion == DEFAULT_REGION and no URL → relative path (same-origin proxy)
 * 3. If cross-region and no URL configured → throw RegionConfigError (fail-closed)
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

const REGION_URLS: Record<string, string> = {
  us: import.meta.env.VITE_API_BASE_URL_US || '',
  eu: import.meta.env.VITE_API_BASE_URL_EU || '',
};

const DEFAULT_REGION: string = import.meta.env.VITE_DEFAULT_REGION || 'us';

/** When true, same-region calls use the absolute URL instead of relative paths */
const USE_DIRECT_URL: boolean = import.meta.env.VITE_USE_DIRECT_API === 'true';

// ============================================================================
// MODULE STATE
// ============================================================================

let _activeRegion: string = DEFAULT_REGION;

// ============================================================================
// ERROR
// ============================================================================

export class RegionConfigError extends Error {
  constructor(region: string) {
    super(
      `Cross-region API call to "${region}" but VITE_API_BASE_URL_${region.toUpperCase()} is not configured. ` +
      `Set the environment variable or ensure the tenant is in the default region (${DEFAULT_REGION}).`
    );
    this.name = 'RegionConfigError';
  }
}

// ============================================================================
// EXPORTS
// ============================================================================

/** Called by AuthContext on login / tenant switch */
export function setActiveRegion(region: string): void {
  _activeRegion = region.toLowerCase();
}

/** Read current active region */
export function getActiveRegion(): string {
  return _activeRegion;
}

/** Read build-time default region */
export function getDefaultRegion(): string {
  return DEFAULT_REGION;
}

/**
 * Check whether a region's cross-region URL is configured.
 * Same-region always returns true (uses relative paths).
 */
export function isRegionConfigured(region: string): boolean {
  const r = region.toLowerCase();
  if (r === DEFAULT_REGION) return true;
  return !!REGION_URLS[r];
}

/**
 * Resolve an API path to the correct URL.
 *
 * 1. If active region has an absolute URL AND (cross-region OR USE_DIRECT_URL) → absolute URL
 * 2. If activeRegion == DEFAULT_REGION and no direct flag → relative path (same-origin proxy)
 * 3. If cross-region and no URL configured → throw RegionConfigError (fail-closed)
 */
export function resolveApiUrl(path: string): string {
  const baseUrl = REGION_URLS[_activeRegion];

  // Same-region: use relative paths unless direct mode is enabled
  if (_activeRegion === DEFAULT_REGION && !USE_DIRECT_URL) {
    return path;
  }

  // Same-region with direct mode, or cross-region: need absolute URL
  if (!baseUrl) {
    throw new RegionConfigError(_activeRegion);
  }

  // Strip trailing slash from base, ensure path starts with /
  const base = baseUrl.replace(/\/+$/, '');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}
