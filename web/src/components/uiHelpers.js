/**
 * UI helper functions for batch display logic.
 * Extracted for testability.
 */

/**
 * Determine if a batch should be classified as "legacy" (pre-forensic attestation).
 *
 * A batch is legacy ONLY if:
 *   1. Explicit is_legacy flag is true, OR
 *   2. /verify returned NOT_AVAILABLE AND batch doc lacks forensic fields, OR
 *   3. verificationData is present but has no forensic fields AND batch doc also lacks them
 *
 * A batch with hash_chain/attestation/signature/iavp_manifest in its Firestore doc
 * is definitively non-legacy, even if /verify times out.
 */
export function isLegacyBatch({ batch, verificationData, loading }) {
  if (batch?.is_legacy === true) return true;

  const batchHasForensicFields = !!(
    batch?.hash_chain || batch?.attestation || batch?.signature || batch?.iavp_manifest
  );

  if (verificationData?.status === 'NOT_AVAILABLE' && !batchHasForensicFields) {
    return true;
  }

  if (
    !loading && verificationData && !batchHasForensicFields &&
    !verificationData?.signature_verified &&
    !verificationData?.hash_chain && !verificationData?.signature
  ) {
    return true;
  }

  return false;
}

/**
 * Compute duration display string with fallback chain:
 *   1. duration_ms → seconds
 *   2. duration_seconds
 *   3. finished_at - timestamp (created_at)
 *   4. "—" for completed, "0.0s" otherwise
 */
export function computeDurationDisplay(batch) {
  const ms = batch?.duration_ms || (batch?.duration_seconds ? batch.duration_seconds * 1000 : 0);
  if (ms > 0) return `${(ms / 1000).toFixed(1)}s`;

  if (batch?.finished_at && batch?.timestamp) {
    const diff = (new Date(batch.finished_at) - new Date(batch.timestamp)) / 1000;
    if (diff > 0) return `${diff.toFixed(1)}s`;
  }

  return batch?.status === 'completed' ? '—' : '0.0s';
}
