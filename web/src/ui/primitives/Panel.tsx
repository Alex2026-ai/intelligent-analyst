import React from 'react';
import { cx } from '../theme';

interface PanelProps {
  children: React.ReactNode;
  title?: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  dense?: boolean;
  className?: string;
  headerRight?: React.ReactNode;
}

/**
 * Panel — Bordered container for content sections
 * Operator console aesthetic: subtle border, no shadows
 */
export function Panel({
  children,
  title,
  icon: Icon,
  dense = false,
  className,
  headerRight,
}: PanelProps) {
  return (
    <div className={cx('ia-panel', dense && 'ia-panel--dense', className)}>
      {title && (
        <div className="ia-panel__header">
          <div className="ia-panel__header-left">
            {Icon && <Icon size={12} />}
            <span>{title}</span>
          </div>
          {headerRight && (
            <div className="ia-panel__header-right">{headerRight}</div>
          )}
        </div>
      )}
      {children}
    </div>
  );
}

export default Panel;
