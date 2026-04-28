/**
 * Marketing-only PMC public API client.
 *
 * Consumes ONLY unauthenticated public endpoints.
 * No auth headers. No tenant headers. No dashboard dependencies.
 */

/**
 * @typedef {Object} PublicSample
 * @property {string} public_sample_id
 * @property {string} sample_type
 * @property {string} status
 * @property {string} headline
 * @property {string} summary
 * @property {string} outcome_class
 * @property {string[]} workflow_stages
 * @property {string[]} public_spec_anchors
 * @property {string} proof_summary
 * @property {string} redaction_profile_version
 * @property {string} source_kind
 * @property {string} integrity_hash
 * @property {string} emitted_at
 */

/**
 * Fetch all published authority samples from the public trust feed.
 * @returns {Promise<{samples: PublicSample[], count: number}>}
 */
export async function fetchPublicTrustFeed({ limit = 20, offset = 0 } = {}) {
  const res = await fetch(`/v1/public-metadata/feed?limit=${limit}&offset=${offset}`);
  if (!res.ok) {
    throw new Error(`Trust feed failed (${res.status})`);
  }
  const data = await res.json();
  return {
    samples: Array.isArray(data.samples) ? data.samples : [],
    count: typeof data.count === 'number' ? data.count : 0,
    total: typeof data.total === 'number' ? data.total : 0,
    limit: data.limit || limit,
    offset: data.offset || offset,
  };
}

/**
 * Fetch a single published sample by ID.
 * @param {string} publicSampleId
 * @returns {Promise<PublicSample>}
 */
export async function fetchPublicSample(publicSampleId) {
  const res = await fetch(`/v1/public-metadata/sample/${encodeURIComponent(publicSampleId)}`);
  if (!res.ok) {
    throw new Error(`Sample not found (${res.status})`);
  }
  return res.json();
}

/**
 * Public anchor allowlist — only these may be rendered.
 */
export const PUBLIC_ANCHOR_ALLOWLIST = new Set(['INV-002', 'INV-005', 'INV-006']);

export const ANCHOR_LABELS = {
  'INV-002': 'Evidence Lineage',
  'INV-005': 'Tenant Isolation',
  'INV-006': 'PII Protection',
};
