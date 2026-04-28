import React from 'react';
import { cx } from '../theme';

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

/**
 * SectionHeader — Page/section title with optional meta and actions
 * Clear visual hierarchy for operator dashboard
 */
export function SectionHeader({
  title,
  subtitle,
  badge,
  actions,
  className,
}: SectionHeaderProps) {
  return (
    <div className={cx('ia-section-header', className)}>
      <div className="ia-section-header__left">
        {badge && <div className="ia-section-header__badge">{badge}</div>}
        <h2 className="ia-section-header__title">{title}</h2>
        {subtitle && (
          <p className="ia-section-header__subtitle">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="ia-section-header__actions">{actions}</div>
      )}
    </div>
  );
}

export default SectionHeader;
