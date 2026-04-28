import React from 'react';
import { cx, statusVariants, layerVariants } from '../theme';

type StatusType = 'pass' | 'warn' | 'fail' | 'info';

interface StatusPillProps {
  status: StatusType;
  children: React.ReactNode;
  className?: string;
}

/**
 * StatusPill — Semantic status indicator
 * Colors: pass (green), warn (amber), fail (red), info (cyan)
 */
export function StatusPill({ status, children, className }: StatusPillProps) {
  return (
    <span className={cx('ia-status-pill', statusVariants[status], className)}>
      {children}
    </span>
  );
}

interface LayerTagProps {
  layer: 0 | 1 | 2 | 3 | 4 | string;
  className?: string;
}

/**
 * LayerTag — Resolution layer indicator (L0-L4)
 */
export function LayerTag({ layer, className }: LayerTagProps) {
  const layerNum = typeof layer === 'string'
    ? parseInt(layer.replace(/\D/g, ''), 10) || 1
    : layer;
  const variant = layerVariants[layerNum as keyof typeof layerVariants] || layerVariants[1];

  return (
    <span className={cx('ia-layer-tag', variant, className)}>
      L{layerNum}
    </span>
  );
}

interface BadgeProps {
  variant?: 'info' | 'warn' | 'accent';
  children: React.ReactNode;
  pulse?: boolean;
  className?: string;
}

/**
 * Badge — Inline label/tag
 */
export function Badge({ variant = 'info', children, pulse = false, className }: BadgeProps) {
  const variantClass = {
    info: 'ia-badge--info',
    warn: 'ia-badge--warn',
    accent: 'ia-badge--accent',
  }[variant];

  return (
    <span className={cx('ia-badge', variantClass, className)}>
      {pulse && <span className="ia-badge__pulse" />}
      {children}
    </span>
  );
}

export default StatusPill;
