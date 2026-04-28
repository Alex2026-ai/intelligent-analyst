import React from 'react';
import { cx } from '../theme';

interface NavItemProps {
  active?: boolean;
  onClick?: () => void;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  disabled?: boolean;
}

/**
 * LeftRailNavItem — Vertical nav item for operator shell
 */
export function LeftRailNavItem({ active, onClick, label, icon: Icon, disabled }: NavItemProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      type="button"
      className={cx(
        'ia-nav-rail__item',
        active && 'ia-nav-rail__item--active',
        disabled && 'ia-nav-rail__item--disabled'
      )}
    >
      <Icon size={16} className="ia-nav-rail__icon" />
      <span className="ia-nav-rail__label">{label}</span>
    </button>
  );
}

interface OperatorShellProps {
  /** Left rail navigation content */
  nav?: React.ReactNode;
  /** Header bar content (right side) */
  headerRight?: React.ReactNode;
  /** Main content area */
  children: React.ReactNode;
  /** Optional right drawer content (Assisted Analysis) */
  drawer?: React.ReactNode;
  /** Whether the drawer is open */
  drawerOpen?: boolean;
  /** App title */
  appTitle?: string;
  /** App subtitle/version */
  appSubtitle?: string;
  /** Logo icon component */
  logoIcon?: React.ComponentType<{ size?: number; className?: string }>;
  /** Optional banner (e.g., Demo Mode) */
  banner?: React.ReactNode;
}

/**
 * OperatorShell — Enterprise operator console layout
 *
 * Structure:
 * - Fixed left rail (nav)
 * - Fixed top header bar
 * - Main content canvas
 * - Optional right drawer slot
 */
export function OperatorShell({
  nav,
  headerRight,
  children,
  drawer,
  drawerOpen = false,
  appTitle = 'Intelligent Analyst',
  appSubtitle = 'Enterprise',
  logoIcon: LogoIcon,
  banner,
}: OperatorShellProps) {
  return (
    <div className="ia-shell">
      {/* Left Rail */}
      <aside className="ia-shell__rail">
        <div className="ia-shell__rail-header">
          {LogoIcon && (
            <div className="ia-shell__logo">
              <LogoIcon size={18} />
            </div>
          )}
          <div className="ia-shell__brand">
            <div className="ia-shell__brand-title">{appTitle}</div>
            <div className="ia-shell__brand-subtitle">{appSubtitle}</div>
          </div>
        </div>
        <nav className="ia-shell__nav">
          {nav}
        </nav>
      </aside>

      {/* Main Area (Header + Content) */}
      <div className="ia-shell__main">
        {/* Top Header Bar */}
        <header className="ia-shell__header">
          <div className="ia-shell__header-left">
            {/* Can show breadcrumb or context here */}
          </div>
          <div className="ia-shell__header-right">
            {headerRight}
          </div>
        </header>

        {/* Banner (e.g., Demo Mode) */}
        {banner && (
          <div className="ia-shell__banner">
            {banner}
          </div>
        )}

        {/* Content Canvas */}
        <main className={cx('ia-shell__content', banner && 'ia-shell__content--with-banner')}>
          {children}
        </main>
      </div>

      {/* Right Drawer (Assisted Analysis) */}
      {drawer && (
        <aside className={cx('ia-shell__drawer', drawerOpen && 'ia-shell__drawer--open')}>
          {drawer}
        </aside>
      )}
    </div>
  );
}

export default OperatorShell;
