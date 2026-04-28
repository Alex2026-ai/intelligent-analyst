import { describe, it, expect } from 'vitest';
import { calculateEnergyEfficiency } from './energyEfficiency';
import { isLegacyBatch as checkLegacy, computeDurationDisplay } from './uiHelpers';

describe('calculateEnergyEfficiency', () => {
  it('returns unavailable for null stats', () => {
    expect(calculateEnergyEfficiency(null)).toEqual({
      rating: 'unavailable', ratio: 0, badge: 'N/A',
    });
  });

  it('returns unavailable for zero total', () => {
    expect(calculateEnergyEfficiency({ total: 0 })).toEqual({
      rating: 'unavailable', ratio: 0, badge: 'N/A',
    });
  });

  // ---------------------------------------------------------------
  // REGRESSION: mixed-mode batches use layer_1_total, not exact+norm
  // ---------------------------------------------------------------
  it('uses layer_1_total for mixed-mode batches (exact+norm are 0)', () => {
    // Real data from BATCH-03FDE446 (mixed mode, 285 records)
    const stats = {
      total: 285,
      layer_1_exact: 0,
      layer_1_norm: 0,
      layer_1_total: 270,       // mixed_org(185) + mixed_person(85)
      layer_1_mixed_org: 185,
      layer_1_mixed_person: 85,
      layer_2_vector: 0,
      layer_2_total: 0,
      layer_3_llm: 0,
    };
    const result = calculateEnergyEfficiency(stats);
    // 270/285 = 94.7% → MODERATE (>= 80%, < 95%)
    expect(result.rating).toBe('warning');
    expect(result.badge).toBe('MODERATE');
    expect(result.ratio).toBeCloseTo(0.9474, 3);
  });

  it('falls back to exact+norm when layer_1_total is absent (legacy)', () => {
    // Legacy batch without layer_1_total
    const stats = {
      total: 100,
      layer_1_exact: 10,
      layer_1_norm: 85,
      layer_2_vector: 3,
      layer_3_llm: 2,
    };
    const result = calculateEnergyEfficiency(stats);
    // (10+85+3)/100 = 98% → LOW CARBON (>= 95%)
    expect(result.rating).toBe('verified');
    expect(result.badge).toBe('LOW CARBON');
    expect(result.ratio).toBeCloseTo(0.98, 2);
  });

  it('uses layer_1_total for company batches (consistent with exact+norm)', () => {
    // Real data from BATCH-0F1FB391 (company mode, 1010 records)
    const stats = {
      total: 1010,
      layer_1_exact: 11,
      layer_1_norm: 786,
      layer_1_total: 797,
      layer_2_vector: 139,
      layer_2_total: 139,
      layer_3_llm: 4,
    };
    const result = calculateEnergyEfficiency(stats);
    // (797+139)/1010 = 92.7% → MODERATE
    expect(result.rating).toBe('warning');
    expect(result.badge).toBe('MODERATE');
  });

  it('rates HIGH ENERGY when most records go to L3/L4', () => {
    const stats = {
      total: 100,
      layer_1_exact: 5,
      layer_1_norm: 5,
      layer_1_total: 10,
      layer_2_vector: 10,
      layer_2_total: 10,
      layer_3_llm: 50,
      layer_4_human: 30,
    };
    const result = calculateEnergyEfficiency(stats);
    // (10+10)/100 = 20% → HIGH ENERGY (< 80%)
    expect(result.rating).toBe('failed');
    expect(result.badge).toBe('HIGH ENERGY');
  });

  it('rates LOW CARBON at exactly 95%', () => {
    const stats = {
      total: 100,
      layer_1_total: 90,
      layer_2_total: 5,
    };
    const result = calculateEnergyEfficiency(stats);
    // 95/100 = 95% → LOW CARBON (>= 95%)
    expect(result.rating).toBe('verified');
    expect(result.badge).toBe('LOW CARBON');
  });
});

// ============================================================================
// LEGACY BATCH DETECTION
// ============================================================================

describe('isLegacyBatch (checkLegacy)', () => {
  it('returns false for batch with forensic fields even if verificationData is null', () => {
    const batch = { hash_chain: { chain_enabled: true }, attestation: { signature_b64: 'abc' } };
    expect(checkLegacy({ batch, verificationData: null, loading: false })).toBe(false);
  });

  it('returns false for batch with iavp_manifest even if verificationData is null', () => {
    const batch = { iavp_manifest: { artifact_type: 'BATCH_ATTESTATION' } };
    expect(checkLegacy({ batch, verificationData: null, loading: false })).toBe(false);
  });

  it('returns true when explicit is_legacy flag is set', () => {
    const batch = { is_legacy: true };
    expect(checkLegacy({ batch, verificationData: null, loading: false })).toBe(true);
  });

  it('returns true when verify returns NOT_AVAILABLE and batch has no forensic fields', () => {
    const batch = {};
    const verificationData = { status: 'NOT_AVAILABLE' };
    expect(checkLegacy({ batch, verificationData, loading: false })).toBe(true);
  });

  it('returns false when verify returns NOT_AVAILABLE but batch HAS forensic fields', () => {
    const batch = { signature: { signed_at_utc: '2026-02-24' } };
    const verificationData = { status: 'NOT_AVAILABLE' };
    expect(checkLegacy({ batch, verificationData, loading: false })).toBe(false);
  });

  it('returns false while still loading', () => {
    const batch = {};
    expect(checkLegacy({ batch, verificationData: null, loading: true })).toBe(false);
  });

  it('returns false for verified batch with full verificationData', () => {
    const batch = { hash_chain: { chain_enabled: true } };
    const verificationData = { signature_verified: true, hash_chain: { verified: true } };
    expect(checkLegacy({ batch, verificationData, loading: false })).toBe(false);
  });
});

// ============================================================================
// DURATION DISPLAY
// ============================================================================

describe('computeDurationDisplay', () => {
  it('uses duration_ms when available', () => {
    expect(computeDurationDisplay({ duration_ms: 604937, status: 'completed' })).toBe('604.9s');
  });

  it('uses duration_seconds when duration_ms missing', () => {
    expect(computeDurationDisplay({ duration_seconds: 42.5, status: 'completed' })).toBe('42.5s');
  });

  it('falls back to timestamp diff when both missing', () => {
    const batch = {
      timestamp: '2026-02-24T16:51:01.000Z',
      finished_at: '2026-02-24T17:01:05.000Z',
      status: 'completed',
    };
    expect(computeDurationDisplay(batch)).toBe('604.0s');
  });

  it('returns dash for completed batch with no duration info', () => {
    expect(computeDurationDisplay({ status: 'completed' })).toBe('—');
  });

  it('returns 0.0s for non-completed batch with no duration', () => {
    expect(computeDurationDisplay({ status: 'processing' })).toBe('0.0s');
  });
});
