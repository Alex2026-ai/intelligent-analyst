import { describe, it, expect } from 'vitest';
import { formatTimestamp, formatTimestampShort } from './formatTimestamp';

describe('formatTimestamp', () => {
  // Core regression: naive UTC string must NOT shift by local offset
  it('treats naive ISO string as UTC, displays in ET', () => {
    // Backend stores "2026-02-21T20:07:00" meaning 20:07 UTC
    // ET = UTC-5 in winter → 3:07 PM ET
    const result = formatTimestamp('2026-02-21T20:07:00');
    expect(result).toContain('3:07');
    expect(result).toContain('PM');
    expect(result).toContain('ET');
  });

  it('handles Z-suffixed string correctly', () => {
    const result = formatTimestamp('2026-02-21T20:07:00Z');
    expect(result).toContain('3:07');
    expect(result).toContain('PM');
    expect(result).toContain('ET');
  });

  it('handles offset-suffixed string correctly', () => {
    const result = formatTimestamp('2026-02-22T01:53:18.736511+00:00');
    expect(result).toContain('8:53');
    expect(result).toContain('PM');
    expect(result).toContain('ET');
  });

  it('returns dash for null/empty', () => {
    expect(formatTimestamp(null)).toBe('\u2014');
    expect(formatTimestamp('')).toBe('\u2014');
    expect(formatTimestamp(undefined)).toBe('\u2014');
  });

  it('date-only mode omits time', () => {
    const result = formatTimestamp('2026-02-21T20:07:00', 'date');
    expect(result).toContain('Feb');
    expect(result).toContain('21');
    expect(result).toContain('2026');
    expect(result).toContain('ET');
  });

  it('time-only mode omits date', () => {
    const result = formatTimestamp('2026-02-21T20:07:00', 'time');
    expect(result).toContain('3:07');
    expect(result).toContain('PM');
    expect(result).not.toContain('2026');
  });
});

describe('formatTimestampShort', () => {
  it('formats compactly for table cells', () => {
    const result = formatTimestampShort('2026-02-21T20:07:00');
    expect(result).toContain('Feb');
    expect(result).toContain('21');
    expect(result).toContain('3:07');
    expect(result).toContain('ET');
  });

  it('returns dash for invalid input', () => {
    expect(formatTimestampShort(null)).toBe('\u2014');
  });
});
