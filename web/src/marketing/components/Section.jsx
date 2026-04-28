import React from 'react';

export function SectionHeader({ eyebrow, title, subtitle }) {
  return (
    <div className="text-center mb-12">
      {eyebrow && (
        <p className="text-sm font-semibold text-cyan-500 uppercase tracking-wider mb-2">
          {eyebrow}
        </p>
      )}
      {title && (
        <h2 className="text-3xl font-bold text-white mb-4">{title}</h2>
      )}
      {subtitle && (
        <p className="text-lg text-slate-400 max-w-2xl mx-auto">{subtitle}</p>
      )}
    </div>
  );
}

export default function Section({ id, className = '', children, dark = false }) {
  return (
    <section
      id={id}
      className={`py-16 px-4 ${dark ? 'bg-slate-900 text-white' : 'bg-slate-950 text-white'} ${className}`}
    >
      <div className="max-w-6xl mx-auto">{children}</div>
    </section>
  );
}
