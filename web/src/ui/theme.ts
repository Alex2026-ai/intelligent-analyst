/**
 * Intelligent Analyst — Design System Theme
 * Palantir-style operator console
 */

// Utility: Concatenate class names (filters falsy values)
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}

// Spacing scale (matches tokens.css)
export const spacing = {
  1: 'var(--pad-1)',  // 6px
  2: 'var(--pad-2)',  // 10px
  3: 'var(--pad-3)',  // 14px
  4: 'var(--pad-4)',  // 18px
  6: 'var(--pad-6)',  // 24px
} as const;

// Row heights
export const rowHeight = {
  compact: 'var(--row-compact)',   // 30px
  standard: 'var(--row-standard)', // 36px
} as const;

// Semantic status variants
export const statusVariants = {
  pass: 'status-pill--pass',
  warn: 'status-pill--warn',
  fail: 'status-pill--fail',
  info: 'status-pill--info',
} as const;

// Layer color variants (L0-L4)
export const layerVariants = {
  0: 'layer-tag--l0',
  1: 'layer-tag--l1',
  2: 'layer-tag--l2',
  3: 'layer-tag--l3',
  4: 'layer-tag--l4',
} as const;

// Common class compositions
export const classes = {
  // Panel styles
  panel: 'ia-panel',
  panelDense: 'ia-panel ia-panel--dense',
  panelHeader: 'ia-panel__header',

  // Table styles
  table: 'ia-table',
  tableStriped: 'ia-table ia-table--striped',

  // Section header
  sectionHeader: 'ia-section-header',
  sectionTitle: 'ia-section-header__title',
  sectionMeta: 'ia-section-header__meta',

  // Text utilities
  monoId: 'ia-mono-id',
  textMuted: 'ia-text-muted',
  textAccent: 'ia-text-accent',

  // Layout
  shell: 'ia-shell',
  shellNav: 'ia-shell__nav',
  shellMain: 'ia-shell__main',
  shellRail: 'ia-shell__rail',
} as const;
