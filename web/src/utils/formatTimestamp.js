/**
 * Timestamp formatter for dashboard display.
 *
 * Backend stores timestamps as naive ISO strings (no "Z" suffix),
 * but they are always UTC. JavaScript's Date() treats naive strings
 * as LOCAL time, causing a +5h shift in ET. This module normalises
 * every timestamp to UTC before formatting.
 */

const TZ = 'America/New_York';

/** Ensure the ISO string is treated as UTC. */
function toUTCDate(value) {
  if (!value) return null;
  const s = String(value);
  // Already has Z or offset → parse as-is
  if (s.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(s)) {
    return new Date(s);
  }
  // Naive string → append Z so Date() interprets as UTC
  return new Date(s + 'Z');
}

/**
 * Format a timestamp for display.
 *
 * @param {string|number|null} value  ISO string, epoch ms, or null
 * @param {'datetime'|'date'|'time'} mode  What to show
 * @returns {string}  Formatted string with " ET" suffix, or "—"
 */
export function formatTimestamp(value, mode = 'datetime') {
  const d = toUTCDate(value);
  if (!d || isNaN(d.getTime())) return '\u2014';

  const opts = {
    timeZone: TZ,
    ...(mode === 'date'
      ? { dateStyle: 'medium' }
      : mode === 'time'
        ? { timeStyle: 'short' }
        : { dateStyle: 'medium', timeStyle: 'short' }),
  };

  return new Intl.DateTimeFormat('en-US', opts).format(d) + ' ET';
}

/**
 * Format a timestamp for table cells (compact).
 *
 * @param {string|number|null} value
 * @returns {string}
 */
export function formatTimestampShort(value) {
  const d = toUTCDate(value);
  if (!d || isNaN(d.getTime())) return '\u2014';

  return new Intl.DateTimeFormat('en-US', {
    timeZone: TZ,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(d) + ' ET';
}
