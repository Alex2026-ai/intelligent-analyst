import React, { useEffect, useState, useCallback } from 'react';
import { Shield, CheckCircle } from 'lucide-react';
import { fetchPublicTrustFeed, PUBLIC_ANCHOR_ALLOWLIST, ANCHOR_LABELS } from '../lib/pmc-public-api';

const PAGE_SIZE = 20;

const PUBLIC_DEMO_SAMPLES = [
  {
    public_sample_id: 'PUBLIC-DEMO-SOLAR-001',
    status: 'published',
    headline: 'Solar supplier resolved across unseen domain data',
    summary: 'A renewable-energy supplier name was resolved through deterministic normalization and replayed three times with zero variance.',
    outcome_class: 'resolved',
    workflow_stages: ['L1 normalized', 'replay verified', 'signed receipt'],
    public_spec_anchors: ['INV-002', 'INV-006'],
    proof_summary: 'Bundled public demo sample. No customer records, private prompts, or tenant identifiers are exposed.',
    integrity_hash: 'sha256:8f4d2c91a7b0d62e4f5319ad0c661e44c2f0b6a60d61d01d5a9a04b1f001',
    emitted_at: '2026-04-27T12:00:05Z',
  },
  {
    public_sample_id: 'PUBLIC-DEMO-SUPPLIER-002',
    status: 'published',
    headline: 'Supplier alias matched with auditable fuzzy evidence',
    summary: 'A marketplace alias was linked to a canonical supplier using a bounded fuzzy layer and a public-safe evidence summary.',
    outcome_class: 'resolved',
    workflow_stages: ['L2 vector fuzzy', 'confidence bounded', 'evidence exported'],
    public_spec_anchors: ['INV-002', 'INV-005'],
    proof_summary: 'Public demo confidence: 0.92. The full sample CSV is bundled with the preview dashboard.',
    integrity_hash: 'sha256:19f064bc2a0d5d1fefcad1a54812c80fbf7f030bb7b0ffae6b7f6ca540ec7331',
    emitted_at: '2026-04-27T12:00:06Z',
  },
  {
    public_sample_id: 'PUBLIC-DEMO-REVIEW-003',
    status: 'published',
    headline: 'Low-confidence vendor routed to human review',
    summary: 'A deliberately ambiguous vendor input was not auto-resolved. The system preserved the decision path and marked it for review.',
    outcome_class: 'human_review_required',
    workflow_stages: ['L4 review', 'auto-resolution blocked', 'audit trail retained'],
    public_spec_anchors: ['INV-005', 'INV-006'],
    proof_summary: 'Public demo sample showing that low-confidence records are controlled instead of forced into an answer.',
    integrity_hash: 'sha256:3d8438c81c65fb7637eb6c4e4c2ce78f41ffdf5ae1c9b43bb8c4f71244aa1829',
    emitted_at: '2026-04-27T12:00:07Z',
  },
];

const fallbackSamplesFor = (limit) => (
  limit > 0 ? PUBLIC_DEMO_SAMPLES.slice(0, limit) : PUBLIC_DEMO_SAMPLES
);

export default function PublicTrustFeed({ limit = 0 }) {
  const [samples, setSamples] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [usingFallback, setUsingFallback] = useState(false);

  // If limit > 0, this is the homepage capped version — no pagination
  const capped = limit > 0;
  const fetchLimit = capped ? limit : PAGE_SIZE;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPublicTrustFeed({ limit: fetchLimit, offset: 0 })
      .then((data) => {
        if (!cancelled) {
          const liveSamples = Array.isArray(data.samples) ? data.samples : [];
          if (liveSamples.length > 0) {
            setSamples(liveSamples);
            setTotal(data.total);
            setUsingFallback(false);
          } else {
            const fallbackSamples = fallbackSamplesFor(limit);
            setSamples(fallbackSamples);
            setTotal(fallbackSamples.length);
            setUsingFallback(true);
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          const fallbackSamples = fallbackSamplesFor(limit);
          setSamples(fallbackSamples);
          setTotal(fallbackSamples.length);
          setUsingFallback(true);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fetchLimit, limit]);

  const loadMore = useCallback(() => {
    if (capped || loadingMore || samples.length >= total) return;
    setLoadingMore(true);
    fetchPublicTrustFeed({ limit: PAGE_SIZE, offset: samples.length })
      .then((data) => {
        setSamples((prev) => [...prev, ...data.samples]);
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }, [capped, loadingMore, samples.length, total]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
      </div>
    );
  }

  if (samples.length === 0) {
    return (
      <div className="border border-slate-800 rounded-lg p-8 text-center bg-slate-900/50">
        <Shield className="mx-auto mb-3 text-slate-600" size={24} />
        <p className="text-sm text-slate-500">Public sample feed is being prepared.</p>
        <p className="text-xs text-slate-600 mt-1">Bundled verified samples are available in the dashboard preview.</p>
      </div>
    );
  }

  const hasMore = !capped && samples.length < total;

  return (
    <div className="space-y-4">
      {usingFallback && (
        <div className="border border-cyan-900/40 bg-cyan-950/20 p-4">
          <div className="flex items-start gap-3">
            <Shield className="text-cyan-400 shrink-0 mt-0.5" size={18} />
            <div>
              <p className="text-sm font-semibold text-slate-200">Public demo feed</p>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                Live trust-feed publishing is not connected in this public demo. These bundled samples show the shape of verified, redacted authority records without exposing customer data.
              </p>
            </div>
          </div>
        </div>
      )}
      {samples.map((sample) => (
        <TrustFeedCard key={sample.public_sample_id} sample={sample} />
      ))}
      {hasMore && (
        <div className="text-center pt-2">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-cyan-500 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            {loadingMore ? (
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
            ) : null}
            {loadingMore ? 'Loading...' : `Load more (${total - samples.length} remaining)`}
          </button>
        </div>
      )}
    </div>
  );
}


function TrustFeedCard({ sample }) {
  const anchors = (sample.public_spec_anchors || []).filter(
    (a) => PUBLIC_ANCHOR_ALLOWLIST.has(a)
  );
  const hashPreview = sample.integrity_hash ? sample.integrity_hash.slice(0, 12) + '...' : '';
  const emittedDate = sample.emitted_at
    ? new Date(sample.emitted_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    : '';

  return (
    <div className="border border-slate-800 rounded-lg bg-slate-900/60 overflow-hidden">
      <div className="p-5 space-y-3">
        <h3 className="text-sm font-semibold text-white leading-snug">{sample.headline}</h3>
        <p className="text-sm text-slate-400 leading-relaxed">{sample.summary}</p>
        {sample.proof_summary && (
          <p className="text-xs text-slate-500 italic">{sample.proof_summary}</p>
        )}
        {anchors.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {anchors.map((anchorId) => (
              <AnchorBadge key={anchorId} anchorId={anchorId} />
            ))}
          </div>
        )}
        {sample.workflow_stages && sample.workflow_stages.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {sample.workflow_stages.map((stage, i) => (
              <span key={i} className="text-[10px] text-slate-500 bg-slate-800/80 rounded px-1.5 py-0.5">
                {stage}
              </span>
            ))}
          </div>
        )}
        <div className="flex items-center justify-between border-t border-slate-800 pt-3 mt-1">
          <div className="flex items-center gap-1.5">
            <CheckCircle size={12} className="text-emerald-500" />
            <span className="text-[10px] text-slate-500">Verified</span>
            {hashPreview && (
              <code className="text-[9px] font-mono text-slate-600" title={`Integrity: ${sample.integrity_hash}`}>
                {hashPreview}
              </code>
            )}
          </div>
          {emittedDate && <span className="text-[10px] text-slate-600">{emittedDate}</span>}
        </div>
      </div>
    </div>
  );
}


function AnchorBadge({ anchorId }) {
  const label = ANCHOR_LABELS[anchorId];
  if (!label) return null;
  return (
    <span
      className="inline-flex items-center gap-1 rounded bg-cyan-950/60 border border-cyan-900/40 px-1.5 py-0.5 text-[10px] font-mono text-cyan-400"
      title={label}
    >
      <Shield size={9} />
      {anchorId}
    </span>
  );
}
