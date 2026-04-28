/**
 * PMC API client — typed access to public metadata endpoints.
 * Public read: no auth. Admin actions: require auth token.
 */

export interface PublicSample {
  public_sample_id: string
  sample_type: string
  status: 'draft' | 'approved' | 'published' | 'revoked'
  headline: string
  summary: string
  outcome_class: string
  workflow_stages: string[]
  public_spec_anchors: string[]
  proof_summary: string
  redaction_profile_version: string
  source_kind: string
  integrity_hash: string
  emitted_at: string
}

export interface FeedResponse {
  samples: PublicSample[]
  count: number
  total: number
  limit: number
  offset: number
}

// --- Public read (no auth) ---

export async function fetchPublicFeed(limit = 20, offset = 0): Promise<FeedResponse> {
  const res = await fetch(`/v1/public-metadata/feed?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error(`Feed failed (${res.status})`)
  return res.json()
}

export async function fetchAdminSamples(
  status?: string, token?: string, limit = 20, offset = 0,
): Promise<FeedResponse> {
  const qp = new URLSearchParams()
  if (status) qp.set('status', status)
  qp.set('limit', String(limit))
  qp.set('offset', String(offset))
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`/v1/public-metadata/admin/samples?${qp}`, { headers })
  if (!res.ok) throw new Error(`Admin list failed (${res.status})`)
  return res.json()
}

export async function fetchPublicSample(sampleId: string): Promise<PublicSample> {
  const res = await fetch(`/v1/public-metadata/sample/${sampleId}`)
  if (!res.ok) throw new Error(`Sample not found (${res.status})`)
  return res.json()
}

// --- Admin actions (require auth) ---

function adminHeaders(token?: string): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

export async function approveSample(sampleId: string, token?: string): Promise<void> {
  const res = await fetch(`/v1/public-metadata/approve/${sampleId}`, {
    method: 'POST', headers: adminHeaders(token),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Approve failed (${res.status}): ${text}`)
  }
}

export async function publishSample(sampleId: string, token?: string): Promise<void> {
  const res = await fetch(`/v1/public-metadata/publish/${sampleId}`, {
    method: 'POST', headers: adminHeaders(token),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Publish failed (${res.status}): ${text}`)
  }
}

export async function revokeSample(sampleId: string, token?: string): Promise<void> {
  const res = await fetch(`/v1/public-metadata/revoke/${sampleId}`, {
    method: 'POST', headers: adminHeaders(token),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Revoke failed (${res.status}): ${text}`)
  }
}
