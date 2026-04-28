import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X, BrainCircuit } from 'lucide-react';

const signInHref = '/app';

export default function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  const navigation = [
    { name: 'Product', href: '/product' },
    { name: 'Platform', href: '/platform' },
    { name: 'Use Cases', href: '/use-cases/regulatory-compliance' },
    { name: 'Trust Center', href: '/protocol' },
    { name: 'Resources', href: '/resources' },
  ];

  const isActive = (href) => location.pathname.startsWith(href);

  return (
    <header className="fixed top-0 inset-x-0 z-50 bg-slate-950/95 backdrop-blur-md border-b border-slate-800">
      <nav className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
        {/* Logo - matches dashboard branding */}
        <Link to="/" className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-cyan-950 to-slate-900 border border-slate-700 flex items-center justify-center">
            <BrainCircuit className="text-cyan-500" size={20} />
          </div>
          <div className="leading-tight text-left">
            <div className="font-bold text-slate-100 tracking-tight text-lg uppercase">Intelligent Analyst</div>
            <div className="text-[10px] text-cyan-500/70 font-mono tracking-widest uppercase">Enterprise</div>
          </div>
        </Link>

        {/* Desktop Navigation */}
        <div className="hidden lg:flex items-center gap-8">
          {navigation.map((item) => (
            <Link
              key={item.name}
              to={item.href}
              className={`text-sm font-medium transition-colors ${
                isActive(item.href)
                  ? 'text-cyan-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {item.name}
            </Link>
          ))}
        </div>

        {/* CTA Button */}
        <div className="hidden lg:flex items-center gap-4">
          <a
            href={signInHref}
            className="text-sm text-slate-400 hover:text-white transition-colors"
          >
            Sign In
          </a>
          <Link
            to="/request-demo"
            className="h-10 px-6 bg-cyan-500 text-slate-950 text-sm font-semibold flex items-center justify-center hover:bg-cyan-400 transition-colors"
          >
            Request Demo
          </Link>
        </div>

        {/* Mobile menu button */}
        <button
          type="button"
          aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={mobileMenuOpen}
          aria-controls="mobile-navigation"
          className="lg:hidden p-2 text-slate-400 hover:text-white"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </nav>

      {/* Mobile Navigation */}
      {mobileMenuOpen && (
        <div id="mobile-navigation" className="lg:hidden bg-slate-950 border-t border-slate-800 px-6 py-4">
          {navigation.map((item) => (
            <Link
              key={item.name}
              to={item.href}
              className="block py-3 text-slate-300 hover:text-cyan-400"
              onClick={() => setMobileMenuOpen(false)}
            >
              {item.name}
            </Link>
          ))}
          <div className="pt-4 mt-4 border-t border-slate-800 flex flex-col gap-3">
            <a href={signInHref} className="text-slate-400 hover:text-white">
              Sign In
            </a>
            <Link
              to="/request-demo"
              className="h-10 px-6 bg-cyan-500 text-slate-950 text-sm font-semibold flex items-center justify-center"
            >
              Request Demo
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
