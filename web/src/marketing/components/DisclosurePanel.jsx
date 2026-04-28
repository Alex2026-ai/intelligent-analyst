import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';

/**
 * DisclosurePanel
 *
 * Regulated disclosure pattern: click-to-expand inline panel.
 * No modals. No popovers. Keyboard accessible. Deep-link support.
 */
export default function DisclosurePanel({
  id,
  title,
  subtitle,
  icon: Icon,
  iconColor = '#0891b2',
  bullets = [],
  why,
  ctaLabel,
  ctaHref,
  defaultOpen = false,
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const panelRef = useRef(null);

  // Handle hash navigation on mount and hash change
  useEffect(() => {
    const checkHash = () => {
      if (window.location.hash === `#${id}`) {
        setIsOpen(true);
        // Scroll into view after a brief delay
        setTimeout(() => {
          panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 100);
      }
    };

    checkHash();
    window.addEventListener('hashchange', checkHash);
    return () => window.removeEventListener('hashchange', checkHash);
  }, [id]);

  const handleToggle = () => {
    const newState = !isOpen;
    setIsOpen(newState);

    // Update hash when opening
    if (newState) {
      window.history.pushState(null, '', `#${id}`);
    } else {
      // Clear hash when closing (optional - keep for navigation history)
      window.history.pushState(null, '', window.location.pathname);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleToggle();
    }
  };

  return (
    <div
      ref={panelRef}
      id={id}
      className="border border-slate-800 bg-slate-900/50 transition-all duration-200"
    >
      {/* Header Button */}
      <button
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        aria-expanded={isOpen}
        aria-controls={`${id}-content`}
        className="w-full p-5 flex items-center justify-between text-left focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:ring-inset transition-colors hover:bg-slate-800/30"
      >
        <div className="flex items-center gap-4">
          {Icon && (
            <div
              className="w-10 h-10 border flex items-center justify-center flex-shrink-0"
              style={{
                borderColor: iconColor,
                backgroundColor: `${iconColor}10`,
              }}
            >
              <Icon size={18} style={{ color: iconColor }} />
            </div>
          )}
          <div>
            <div className="flex items-center gap-3">
              <span className="font-semibold text-white">{title}</span>
              <span className="text-slate-500 text-sm font-mono">/ {subtitle}</span>
            </div>
          </div>
        </div>

        {/* Expand indicator */}
        <ChevronDown
          size={20}
          className={`text-slate-500 transition-transform duration-200 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Expandable Content */}
      <div
        id={`${id}-content`}
        role="region"
        aria-labelledby={id}
        className={`overflow-hidden transition-all duration-300 ${
          isOpen ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="px-5 pb-5 pt-2 border-t border-slate-800">
          {/* Bullets */}
          <ul className="space-y-3 mb-6">
            {bullets.map((bullet, index) => (
              <li key={index} className="flex items-start gap-3 text-sm text-slate-400">
                <span
                  className="w-1.5 h-1.5 mt-2 flex-shrink-0"
                  style={{ backgroundColor: iconColor }}
                />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>

          {/* Why statement */}
          {why && (
            <div className="mb-4 p-3 border-l-2 bg-slate-950/50" style={{ borderColor: iconColor }}>
              <p className="text-sm text-slate-300 font-medium italic">{why}</p>
            </div>
          )}

          {/* CTA */}
          {ctaLabel && ctaHref && (
            <Link
              to={ctaHref}
              className="inline-flex items-center gap-2 text-sm font-mono uppercase tracking-wider transition-colors"
              style={{ color: iconColor }}
            >
              {ctaLabel}
              <span className="text-slate-500">→</span>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * DisclosureGroup
 *
 * Container for multiple disclosure panels.
 */
export function DisclosureGroup({ children }) {
  return <div className="space-y-3">{children}</div>;
}
