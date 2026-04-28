import React, { useState } from 'react';

/**
 * ScreenshotWithCallouts
 *
 * Renders a screenshot with positioned callout overlays.
 * Design: Institutional, restrained, no heavy animation.
 *
 * @param {string} image - Path to the screenshot
 * @param {string} alt - Alt text for accessibility
 * @param {Array} callouts - Array of callout objects with:
 *   - id: unique identifier
 *   - label: uppercase label text
 *   - description: short description
 *   - x: horizontal position as percentage (0-100)
 *   - y: vertical position as percentage (0-100)
 *   - align: 'left' | 'right' (which side the callout appears)
 */
export default function ScreenshotWithCallouts({ image, alt, callouts = [] }) {
  const [activeCallout, setActiveCallout] = useState(null);

  return (
    <div className="relative">
      {/* Screenshot container */}
      <div className="relative bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <picture>
          <source srcSet={`${image}.webp`} type="image/webp" />
          <img
            src={`${image}.png`}
            alt={alt}
            className="w-full block"
            loading="lazy"
          />
        </picture>

        {/* Callout markers */}
        {callouts.map((callout) => (
          <div
            key={callout.id}
            className="absolute"
            style={{
              left: `${callout.x}%`,
              top: `${callout.y}%`,
              transform: 'translate(-50%, -50%)',
            }}
          >
            {/* Marker dot */}
            <button
              className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all duration-150 ${
                activeCallout === callout.id
                  ? 'bg-cyan-500 border-cyan-400 scale-110'
                  : 'bg-slate-900/80 border-cyan-500/60 hover:border-cyan-400 hover:bg-slate-800'
              }`}
              onMouseEnter={() => setActiveCallout(callout.id)}
              onMouseLeave={() => setActiveCallout(null)}
              onClick={() => setActiveCallout(activeCallout === callout.id ? null : callout.id)}
              aria-label={callout.label}
            >
              <span className="text-cyan-400 text-xs font-bold">
                {callout.marker || '+'}
              </span>
            </button>

            {/* Callout tooltip */}
            <div
              className={`absolute z-20 w-56 transition-opacity duration-150 ${
                activeCallout === callout.id ? 'opacity-100' : 'opacity-0 pointer-events-none'
              } ${
                callout.align === 'left'
                  ? 'right-full mr-3 top-1/2 -translate-y-1/2'
                  : 'left-full ml-3 top-1/2 -translate-y-1/2'
              }`}
            >
              <div className="bg-slate-950 border border-cyan-900/50 p-3 shadow-xl">
                <div className="text-cyan-500 text-[10px] font-mono uppercase tracking-wider mb-1">
                  {callout.label}
                </div>
                <div className="text-slate-300 text-xs leading-relaxed">
                  {callout.description}
                </div>
              </div>
              {/* Arrow */}
              <div
                className={`absolute top-1/2 -translate-y-1/2 w-2 h-2 bg-slate-950 border-cyan-900/50 transform rotate-45 ${
                  callout.align === 'left'
                    ? '-right-1 border-r border-t'
                    : '-left-1 border-l border-b'
                }`}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Callout legend (mobile-friendly) */}
      <div className="mt-4 lg:hidden">
        <div className="grid gap-2">
          {callouts.map((callout) => (
            <div
              key={callout.id}
              className="bg-slate-900 border border-slate-800 p-3"
            >
              <div className="text-cyan-500 text-[10px] font-mono uppercase tracking-wider mb-1">
                {callout.label}
              </div>
              <div className="text-slate-400 text-xs">
                {callout.description}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * CalloutLegend
 *
 * Side panel showing all callouts for a screenshot.
 * Use when you want callouts displayed as a list instead of overlays.
 */
export function CalloutLegend({ callouts = [] }) {
  return (
    <div className="space-y-3">
      {callouts.map((callout, index) => (
        <div
          key={callout.id}
          className="flex items-start gap-3"
        >
          <div className="w-6 h-6 bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0 text-xs text-slate-500 font-mono">
            {index + 1}
          </div>
          <div>
            <div className="text-cyan-500 text-[10px] font-mono uppercase tracking-wider mb-0.5">
              {callout.label}
            </div>
            <div className="text-slate-400 text-sm">
              {callout.description}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
