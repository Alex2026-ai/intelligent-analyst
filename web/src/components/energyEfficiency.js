/**
 * Energy Efficiency Calculator
 *
 * Measures operational cost profile: what fraction of records resolved
 * via deterministic (L1) or vector (L2) layers vs expensive LLM (L3).
 *
 * Thresholds:
 *   >= 95%  LOW CARBON  (verified)
 *   >= 80%  MODERATE    (warning)
 *   <  80%  HIGH ENERGY (failed)
 */
export const calculateEnergyEfficiency = (stats) => {
  if (!stats) return { rating: 'unavailable', ratio: 0, badge: 'N/A' };

  const total = stats.total || 0;
  // Use layer_1_total when available (covers mixed-mode: org + person + vessel)
  // Fall back to exact + norm for company-only batches
  const l1Resolved = stats.layer_1_total || ((stats.layer_1_exact || 0) + (stats.layer_1_norm || 0));
  const l2Resolved = stats.layer_2_total || stats.layer_2_vector || 0;

  if (total === 0) return { rating: 'unavailable', ratio: 0, badge: 'N/A' };

  // Energy efficiency = (L1 + L2) / Total
  // Higher ratio = better (less LLM calls)
  const efficientRatio = (l1Resolved + l2Resolved) / total;

  if (efficientRatio >= 0.95) {
    return { rating: 'verified', ratio: efficientRatio, badge: 'LOW CARBON' };
  } else if (efficientRatio >= 0.80) {
    return { rating: 'warning', ratio: efficientRatio, badge: 'MODERATE' };
  } else {
    return { rating: 'failed', ratio: efficientRatio, badge: 'HIGH ENERGY' };
  }
};
