import React, { useEffect, useState, useCallback } from 'react';
import { Shield, CheckCircle, AlertCircle } from 'lucide-react';
import { fetchPublicTrustFeed, PUBLIC_ANCHOR_ALLOWLIST, ANCHOR_LABELS } from '../lib/pmc-public-api';

const RENDER_FIELDS = new Set([
  'public_sample_id', 'headline', 'summary', 'outcome_class',
  'workflow_stages', 'public_spec_anchors', 'proof_summary',
  'integrity_hash', 'emitted_at', 'status',
]);

const PAGE_SIZE = 20;

export default function PublicTrustFeed({ limit = 0 }) {
  const [samples, setSamples] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  // If limit > 0, this is the homepage capped version — no pagination
  const capped = limit > 0;
  const fetchLimit = capped ? limit : PAGE_SIZE;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPublicTrustFeed({ limit: fetchLimit, offset: 0 })
      .then((data) => {
        if (!cancelled) {
          setSamples(data.samples);
          setTotal(data.total);
          setError(null);
        }
      })
      .catch(() => { if (!cancelled) setError('Unable to load trust feed.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fetchLimit]);

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

  if (error) {
    return (
      <div className="text-center py-8">
        <AlertCircle className="mx-auto mb-2 text-slate-500" size={20} />
        <p className="text-sm text-slate-500">{error}</p>
      </div>
    );
  }

  if (samples.length === 0) {
    return (
      <div className="border border-slate-800 rounded-lg p-8 text-center bg-slate-900/50">
        <Shield className="mx-auto mb-3 text-slate-600" size={24} />
        <p className="text-sm text-slate-500">No published authority samples yet.</p>
        <p className="text-xs text-slate-600 mt-1">Verified resolutions will appear here once approved and published.</p>
      </div>
    );
  }

  const hasMore = !capped && samples.length < total;

  return (
    <div className="space-y-4">
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
