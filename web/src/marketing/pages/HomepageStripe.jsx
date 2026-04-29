import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Shield, Lock, Database, Check } from 'lucide-react';
import { FadeIn } from '../components/AnimatedSection';
import ResolutionWaterfall from '../components/ResolutionWaterfall';
import ReceiptValidator from '../components/ReceiptValidator';
import SilentTax from '../components/SilentTax';
import TransparencyManifesto from '../components/TransparencyManifesto';
import CookieConsent from '../components/CookieConsent';
import SEO from '../components/SEO';

const signInHref = '/app';

/**
 * Stripe/Benchling-inspired Homepage
 *
 * Design inspiration:
 * - Benchling: Clean white/blue, modern typography, subtle animations
 * - Siege Media: Light gray backgrounds, minimalist, functional
 *
 * - Fully light theme with cohesive gray backgrounds
 * - Dashboard preview components styled to match light theme
 * - All original sections preserved for SEO
 */

// Scoped styles for Stripe theme
const stripeStyles = `
  /* Override global dark theme when stripe-page is present */
  body:has(.stripe-page) {
    background: #ffffff !important;
    color: #0a2540 !important;
  }

  .stripe-page {
    background: #ffffff !important;
    min-height: 100vh;
  }
  .stripe-section {
    background: #ffffff;
    color: #0a2540;
  }
  .stripe-section-alt {
    background: #f8fafc;
    color: #0a2540;
  }
  .stripe-section-gray {
    background: #f1f5f9;
    color: #0a2540;
  }
  .stripe-section * {
    border-radius: revert !important;
  }
  .stripe-section .rounded-lg { border-radius: 8px !important; }
  .stripe-section .rounded-xl { border-radius: 12px !important; }
  .stripe-section .rounded-full { border-radius: 9999px !important; }

  /* Navigation */
  .stripe-nav {
    background: rgba(255, 255, 255, 0.95) !important;
    backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid #e3e8ee !important;
  }
  .stripe-nav a, .stripe-nav span {
    color: #425466 !important;
  }
  .stripe-nav a:hover {
    color: #0a2540 !important;
  }
  .stripe-nav .logo-text {
    color: #0a2540 !important;
  }

  /* Buttons */
  .stripe-btn-primary {
    background: #0073e6 !important;
    color: white !important;
    border-radius: 8px !important;
    border: none !important;
  }
  .stripe-btn-primary:hover {
    background: #005bb5 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 115, 230, 0.3);
  }
  .stripe-btn-secondary {
    background: transparent !important;
    color: #0a2540 !important;
    border: 1px solid #e3e8ee !important;
    border-radius: 8px !important;
  }
  .stripe-btn-secondary:hover {
    background: #f6f9fc !important;
    border-color: #0a2540 !important;
  }

  /* Badge */
  .stripe-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.875rem;
    background: #e8f4fd !important;
    color: #0073e6 !important;
    font-weight: 500;
    font-size: 0.8125rem;
    border-radius: 100px !important;
    border: none !important;
  }

  /* Cards */
  .stripe-card {
    background: #ffffff !important;
    border: 1px solid #e3e8ee !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    transition: all 0.2s ease;
  }
  .stripe-card:hover {
    border-color: #0073e6 !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transform: translateY(-2px);
  }

  /* Text colors */
  .stripe-text { color: #0a2540 !important; }
  .stripe-text-secondary { color: #425466 !important; }
  .stripe-text-muted { color: #6b7c93 !important; }
  .stripe-accent { color: #0073e6 !important; }

  /* Gradient text */
  .stripe-gradient-text {
    background: linear-gradient(135deg, #0073e6 0%, #00d4aa 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
  }

  /* Stats cards */
  .stripe-stat-card {
    background: #f6f9fc !important;
    border: 1px solid #e3e8ee !important;
    border-radius: 12px !important;
    padding: 1.5rem !important;
  }

  /* Trust badges */
  .stripe-trust-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    background: #e6faf5 !important;
    color: #0d7d6a !important;
    font-weight: 500;
    font-size: 0.75rem;
    border-radius: 6px !important;
  }

  /* Footer - keep dark */
  .stripe-footer {
    background: #0a2540 !important;
    color: white !important;
  }
  .stripe-footer a {
    color: rgba(255,255,255,0.7) !important;
  }
  .stripe-footer a:hover {
    color: white !important;
  }

  /* Dashboard preview wrapper - LIGHT GRAY for cohesion */
  .dashboard-preview-wrapper {
    background: #f8fafc !important;
    color: #0a2540 !important;
    /* Override CSS variables for light theme */
    --forensic-bg: #f8fafc;
    --forensic-surface: #ffffff;
    --forensic-border: #e2e8f0;
    --forensic-accent: #0073e6;
    --forensic-success: #059669;
    --forensic-text: #0a2540;
    --forensic-muted: #64748b;
    --forensic-glow: rgba(0, 115, 230, 0.3);
    --grid-color: rgba(226, 232, 240, 0.8);
  }
  .dashboard-preview-wrapper .bg-slate-950,
  .dashboard-preview-wrapper .bg-slate-900 {
    background: #ffffff !important;
  }
  .dashboard-preview-wrapper .text-white,
  .dashboard-preview-wrapper .text-slate-100 {
    color: #0a2540 !important;
  }
  .dashboard-preview-wrapper .text-slate-400,
  .dashboard-preview-wrapper .text-slate-500 {
    color: #64748b !important;
  }
  .dashboard-preview-wrapper .text-cyan-400,
  .dashboard-preview-wrapper .text-cyan-500 {
    color: #0073e6 !important;
  }
  .dashboard-preview-wrapper .border-slate-700,
  .dashboard-preview-wrapper .border-slate-800 {
    border-color: #e2e8f0 !important;
  }
  .dashboard-preview-wrapper .bg-cyan-950,
  .dashboard-preview-wrapper .bg-cyan-900 {
    background: #e8f4fd !important;
  }
  .dashboard-preview-wrapper .forensic-badge {
    background: #e8f4fd !important;
    border-color: #0073e6 !important;
    color: #0073e6 !important;
  }
  /* Keep some elements with accent styling */
  .dashboard-preview-wrapper .bg-emerald-950 {
    background: #d1fae5 !important;
  }
  .dashboard-preview-wrapper .text-emerald-500,
  .dashboard-preview-wrapper .text-emerald-400 {
    color: #059669 !important;
  }
  .dashboard-preview-wrapper .text-amber-500,
  .dashboard-preview-wrapper .text-amber-400 {
    color: #d97706 !important;
  }
  .dashboard-preview-wrapper .text-blue-400,
  .dashboard-preview-wrapper .text-blue-500 {
    color: #2563eb !important;
  }
  .dashboard-preview-wrapper .text-green-400,
  .dashboard-preview-wrapper .text-green-500 {
    color: #16a34a !important;
  }
  /* Terminal/code blocks stay slightly darker for contrast */
  .dashboard-preview-wrapper .terminal-frame,
  .dashboard-preview-wrapper .hash-display,
  .dashboard-preview-wrapper pre,
  .dashboard-preview-wrapper code {
    background: #f1f5f9 !important;
    border-color: #e2e8f0 !important;
    color: #334155 !important;
  }
  /* Gate scanner - adjust for light bg */
  .dashboard-preview-wrapper .gate-scanner {
    background: linear-gradient(90deg, transparent 0%, #0073e6 30%, #00d4aa 50%, #0073e6 70%, transparent 100%) !important;
    box-shadow: 0 0 8px rgba(0, 115, 230, 0.5) !important;
  }
  /* Waterfall gates */
  .dashboard-preview-wrapper .waterfall-gate {
    border-left-color: #e2e8f0 !important;
  }
  .dashboard-preview-wrapper .waterfall-gate.active {
    border-left-color: #0073e6 !important;
    background: rgba(0, 115, 230, 0.03) !important;
  }
  .dashboard-preview-wrapper .waterfall-gate.active::before {
    background: #0073e6 !important;
    box-shadow: 0 0 8px rgba(0, 115, 230, 0.5) !important;
  }
  /* Blueprint grid for light mode */
  .dashboard-preview-wrapper .blueprint-grid {
    background-image:
      linear-gradient(rgba(226, 232, 240, 0.6) 1px, transparent 1px),
      linear-gradient(90deg, rgba(226, 232, 240, 0.6) 1px, transparent 1px) !important;
  }
  /* Section borders for visual separation */
  .dashboard-preview-wrapper > section,
  .dashboard-preview-wrapper > div > section {
    border-bottom: 1px solid #e2e8f0;
  }
  /* Inline style overrides for active states */
  .dashboard-preview-wrapper [style*="rgba(8, 145, 178"] {
    background: rgba(0, 115, 230, 0.05) !important;
  }
`;

export default function HomepageStripe() {
  useEffect(() => {
    // Inject scoped styles
    const style = document.createElement('style');
    style.id = 'stripe-theme-styles';
    style.textContent = stripeStyles;
    document.head.appendChild(style);

    // Add class to body for fallback styling
    document.body.classList.add('stripe-theme-active');
    document.body.style.backgroundColor = '#ffffff';
    document.body.style.color = '#0a2540';

    return () => {
      const existingStyle = document.getElementById('stripe-theme-styles');
      if (existingStyle) {
        document.head.removeChild(existingStyle);
      }
      document.body.classList.remove('stripe-theme-active');
      // Restore dark theme
      document.body.style.backgroundColor = '#020617';
      document.body.style.color = '#e2e8f0';
    };
  }, []);

  const proofCards = [
    { label: 'Cryptographic Signatures', detail: 'ECDSA P-256', href: '/security#ecdsa-p256' },
    { label: 'Audit Retention', detail: '7 Years WORM', href: '/security#worm-retention' },
    { label: 'Batch Capacity', detail: '100K+ Records', href: null },
  ];

  const modules = [
    {
      icon: Database,
      title: 'Entity Resolution',
      description: 'Match messy records to canonical entities with configurable thresholds.',
      href: '/platform',
    },
    {
      icon: Shield,
      title: 'Forensic Audit',
      description: 'Cryptographic proof for every decision. Hash-chain integrity.',
      href: '/security',
    },
    {
      icon: Lock,
      title: 'Compliance Export',
      description: 'Regulator-ready evidence packages with legal hold support.',
      href: '/trust-architecture',
    },
  ];

  const useCases = [
    { title: 'Regulatory Compliance', description: 'Audit trails for examinations.', href: '/use-cases/regulatory-compliance' },
    { title: 'Clinical Data', description: 'HIPAA-aligned entity matching.', href: '/use-cases/clinical-data-governance' },
    { title: 'Master Data', description: 'Unify records across systems.', href: '/use-cases/master-data-management' },
    { title: 'Supply Chain', description: 'Verify supplier identity.', href: '/use-cases/supply-chain' },
  ];

  const securityFeatures = [
    'PII Masking',
    'Circuit Breaker',
    'Persistent Audit',
    'ECDSA Signatures',
    'SHA-256 Hash Chains',
    '7-year WORM Retention',
  ];

  const complianceFrameworks = [
    { label: 'SOC 2', status: 'Aligned' },
    { label: 'GDPR Article 28', status: 'Aligned' },
    { label: 'HIPAA', status: 'Aligned' },
    { label: 'FedRAMP', status: 'Pathway' },
  ];

  return (
    <div className="stripe-page min-h-screen">
      <SEO
        path="/"
        description="The Identity Attestation Layer for the Regulated Enterprise. Every entity resolved. Every decision signed. Every audit trail immutable."
      />

      {/* Navigation */}
      <nav className="stripe-nav fixed top-0 left-0 right-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 flex items-center justify-center" style={{ background: '#0073e6', borderRadius: '8px' }}>
              <span className="text-white font-bold text-sm">IA</span>
            </div>
            <span className="logo-text font-semibold text-lg">Intelligent Analyst</span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <Link to="/product" className="text-sm font-medium">Product</Link>
            <Link to="/platform" className="text-sm font-medium">Platform</Link>
            <Link to="/security" className="text-sm font-medium">Security</Link>
            <Link to="/resources" className="text-sm font-medium">Resources</Link>
            <Link to="/company" className="text-sm font-medium">Company</Link>
          </div>

          <div className="flex items-center gap-4">
            <a href={signInHref} className="hidden sm:block text-sm font-medium">Sign in</a>
            <Link
              to="/request-demo"
              className="stripe-btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold"
            >
              Request Demo
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="stripe-section pt-32 pb-20 md:pt-40 md:pb-28">
        <div className="max-w-7xl mx-auto px-6">
          <FadeIn direction="up" duration={800}>
            <div className="max-w-4xl">
              <div className="stripe-badge mb-6">
                <span className="w-2 h-2 rounded-full" style={{ background: '#0073e6' }} />
                Identity Infrastructure
              </div>

              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-[1.1] mb-6 stripe-text" style={{ letterSpacing: '-0.03em' }}>
                The Identity Attestation Layer
                <br />
                <span className="stripe-gradient-text">for the Regulated Enterprise</span>
              </h1>

              <p className="text-xl md:text-2xl leading-relaxed mb-10 stripe-text-secondary font-light">
                Bringing absolute transparency to the new AI world.
                <br />
                Every entity resolved. Every decision signed. Every audit trail immutable.
              </p>

              <div className="flex flex-col sm:flex-row gap-4 mb-16">
                <Link
                  to="/request-demo"
                  className="stripe-btn-primary inline-flex items-center justify-center gap-2 h-14 px-8 text-base font-semibold"
                >
                  Request Demo
                  <ArrowRight size={18} />
                </Link>
                <Link
                  to="/product"
                  className="stripe-btn-secondary inline-flex items-center justify-center gap-2 h-14 px-8 text-base font-medium"
                >
                  Product Tour
                </Link>
              </div>

              {/* Proof Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {proofCards.map((card, index) => (
                  <FadeIn key={card.label} delay={index * 100} direction="up">
                    <div className="stripe-stat-card">
                      <div className="stripe-accent font-semibold text-lg mb-1">{card.detail}</div>
                      <div className="stripe-text-muted text-sm">{card.label}</div>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </FadeIn>
        </div>
      </section>

      {/* Trust Strip */}
      <section className="stripe-section-alt py-6 border-y" style={{ borderColor: '#e3e8ee' }}>
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-wrap items-center justify-center gap-8">
            <span className="stripe-text-muted text-sm font-medium">Built for:</span>
            {['Financial Institutions', 'Life Sciences', 'Enterprise MDM', 'Supply Chain'].map((item) => (
              <span key={item} className="stripe-text-secondary text-sm">{item}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Resolution Waterfall - KEEP DARK (Dashboard Preview) */}
      <div className="dashboard-preview-wrapper">
        <ResolutionWaterfall />
      </div>

      {/* Live Receipt Validator - KEEP DARK (Dashboard Preview) */}
      <div className="dashboard-preview-wrapper">
        <ReceiptValidator />
      </div>

      {/* Silent Tax Section */}
      <div className="dashboard-preview-wrapper">
        <SilentTax />
      </div>

      {/* Transparency Manifesto */}
      <div className="dashboard-preview-wrapper">
        <TransparencyManifesto />
      </div>

      {/* 3 Module Cards */}
      <section className="stripe-section py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <div className="stripe-badge mb-4">Platform</div>
            <h2 className="text-3xl md:text-4xl font-bold stripe-text mb-4">Three core modules</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {modules.map((mod, index) => (
              <FadeIn key={mod.title} delay={index * 100} direction="up">
                <Link to={mod.href} className="stripe-card block p-8 h-full">
                  <div
                    className="w-12 h-12 flex items-center justify-center mb-6"
                    style={{ background: '#e8f4fd', borderRadius: '12px' }}
                  >
                    <mod.icon size={24} style={{ color: '#0073e6' }} />
                  </div>
                  <h3 className="text-xl font-semibold stripe-text mb-3">{mod.title}</h3>
                  <p className="stripe-text-secondary text-sm leading-relaxed">{mod.description}</p>
                </Link>
              </FadeIn>
            ))}
          </div>
        </div>
      </section>

      {/* Use Cases */}
      <section className="stripe-section-alt py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <div className="stripe-badge mb-4">Use Cases</div>
            <h2 className="text-3xl md:text-4xl font-bold stripe-text mb-4">Built for regulated industries</h2>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {useCases.map((useCase, index) => (
              <FadeIn key={useCase.title} delay={index * 75} direction="up">
                <Link
                  to={useCase.href}
                  className="stripe-card block p-5 h-full"
                >
                  <h3 className="text-sm font-semibold stripe-text mb-2">{useCase.title}</h3>
                  <p className="stripe-text-muted text-xs leading-relaxed">{useCase.description}</p>
                </Link>
              </FadeIn>
            ))}
          </div>
        </div>
      </section>

      {/* Security Section */}
      <section className="stripe-section py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-2 gap-16 items-center">
            <FadeIn direction="right">
              <div>
                <div className="stripe-badge mb-5">Security</div>
                <h2 className="text-3xl md:text-4xl font-bold stripe-text mb-6 leading-tight">
                  Zero-trust by design
                </h2>
                <p className="stripe-text-secondary text-lg leading-relaxed mb-4">
                  Per-tenant encryption, cryptographic signatures, and WORM retention.
                  Public verification exposes no PII.
                </p>
                <p className="stripe-text-secondary leading-relaxed mb-8">
                  Security is not only about protection. It is about transparency.
                  Our public verification endpoint enables third-party audit without exposing PII.
                </p>

                <div className="grid grid-cols-2 gap-3 mb-8">
                  {securityFeatures.map((item) => (
                    <div key={item} className="flex items-center gap-3">
                      <div className="w-5 h-5 flex items-center justify-center" style={{ background: '#e6faf5', borderRadius: '50%' }}>
                        <Check size={12} style={{ color: '#00d4aa' }} />
                      </div>
                      <span className="stripe-text-secondary text-sm">{item}</span>
                    </div>
                  ))}
                </div>

                <Link
                  to="/security"
                  className="inline-flex items-center gap-2 stripe-accent font-medium hover:underline"
                >
                  Security details
                  <ArrowRight size={16} />
                </Link>
              </div>
            </FadeIn>

            <FadeIn direction="left" delay={150}>
              <div className="stripe-card p-8">
                <div className="space-y-4">
                  {complianceFrameworks.map((fw) => (
                    <div key={fw.label} className="flex items-center justify-between py-3 border-b last:border-0" style={{ borderColor: '#e3e8ee' }}>
                      <span className="stripe-text font-medium">{fw.label}</span>
                      <span className="stripe-trust-badge">
                        <Check size={12} />
                        {fw.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </FadeIn>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="stripe-section-alt py-20">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <h2 className="text-3xl md:text-4xl font-bold stripe-text mb-4">
            See it with your data
          </h2>
          <p className="stripe-text-secondary text-lg mb-8">
            Schedule a demo. Bring your own records.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/request-demo"
              className="stripe-btn-primary inline-flex items-center justify-center gap-2 h-14 px-8 text-base font-semibold"
            >
              Request Demo
              <ArrowRight size={18} />
            </Link>
            <Link
              to="/resources"
              className="stripe-btn-secondary inline-flex items-center justify-center gap-2 h-14 px-8 text-base font-medium"
            >
              Documentation
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="stripe-footer py-16">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-8 mb-12">
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 flex items-center justify-center bg-white/10" style={{ borderRadius: '8px' }}>
                  <span className="text-white font-bold text-sm">IA</span>
                </div>
                <span className="font-semibold text-white">Intelligent Analyst</span>
              </div>
              <p className="text-sm text-white/60">
                Enterprise entity resolution with cryptographic audit trails.
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-white mb-4 text-sm">Platform</h4>
              <div className="space-y-3">
                <Link to="/product" className="block text-sm">Product Tour</Link>
                <Link to="/platform" className="block text-sm">Overview</Link>
                <Link to="/security" className="block text-sm">Security</Link>
              </div>
            </div>

            <div>
              <h4 className="font-semibold text-white mb-4 text-sm">Use Cases</h4>
              <div className="space-y-3">
                <Link to="/use-cases/regulatory-compliance" className="block text-sm">Compliance</Link>
                <Link to="/use-cases/clinical-data-governance" className="block text-sm">Clinical Data</Link>
                <Link to="/use-cases/master-data-management" className="block text-sm">Master Data</Link>
              </div>
            </div>

            <div>
              <h4 className="font-semibold text-white mb-4 text-sm">Resources</h4>
              <div className="space-y-3">
                <Link to="/resources" className="block text-sm">Documentation</Link>
                <Link to="/trust-architecture" className="block text-sm">Trust Architecture</Link>
                <Link to="/security" className="block text-sm">Forensic Audit</Link>
              </div>
            </div>

            <div>
              <h4 className="font-semibold text-white mb-4 text-sm">Company</h4>
              <div className="space-y-3">
                <Link to="/company" className="block text-sm">About</Link>
                <Link to="/privacy" className="block text-sm">Privacy</Link>
                <Link to="/terms" className="block text-sm">Terms</Link>
              </div>
            </div>
          </div>

          <div className="pt-8 border-t border-white/10 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-sm text-white/60">
              © {new Date().getFullYear()} Intelligent Analyst, Inc. All rights reserved.
            </p>
            <p className="text-sm text-white/40">Delaware, USA</p>
          </div>
        </div>
      </footer>

      <CookieConsent />
    </div>
  );
}
