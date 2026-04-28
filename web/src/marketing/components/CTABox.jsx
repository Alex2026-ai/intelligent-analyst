import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export default function CTABox({
  title = 'Ready to see it in action?',
  description = 'Request a personalized demo with your own data.',
  primaryText = 'Request Demo',
  primaryHref = '/request-demo',
  secondaryText,
  secondaryHref,
  variant = 'default',
}) {
  if (variant === 'minimal') {
    return (
      <div className="text-center">
        <Link
          to={primaryHref}
          className="action-block inline-flex items-center gap-2 h-12 px-8 bg-cyan-600 text-white font-semibold hover:bg-cyan-500 transition-colors"
        >
          {primaryText}
          <ArrowRight size={18} />
        </Link>
      </div>
    );
  }

  return (
    <div className="action-block bg-gradient-to-br from-cyan-950/50 to-slate-900 p-8 md:p-12">
      <div className="max-w-2xl mx-auto text-center">
        <h3 className="text-2xl md:text-3xl font-bold text-white mb-4">
          {title}
        </h3>
        <p className="text-slate-400 mb-8">{description}</p>
        <div className="flex flex-col sm:flex-row justify-center gap-4">
          <Link
            to={primaryHref}
            className="action-block inline-flex items-center justify-center gap-2 h-12 px-8 bg-cyan-600 text-white font-semibold hover:bg-cyan-500 transition-colors"
          >
            {primaryText}
            <ArrowRight size={18} />
          </Link>
          {secondaryText && secondaryHref && (
            <Link
              to={secondaryHref}
              className="action-block inline-flex items-center justify-center gap-2 h-12 px-8 border border-slate-700 text-white font-medium hover:bg-slate-800 transition-colors"
            >
              {secondaryText}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
