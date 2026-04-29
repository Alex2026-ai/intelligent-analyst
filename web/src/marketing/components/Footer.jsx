import React from 'react';
import { Link } from 'react-router-dom';
import { Mail, MapPin, BrainCircuit } from 'lucide-react';

export default function Footer() {
  const footerLinks = {
    platform: [
      { name: 'Product Tour', href: '/product' },
      { name: 'Platform Overview', href: '/platform' },
      { name: 'Security', href: '/security' },
      { name: 'Trust Architecture', href: '/trust-architecture' },
    ],
    useCases: [
      { name: 'Regulatory Compliance', href: '/use-cases/regulatory-compliance' },
      { name: 'Clinical Data Governance', href: '/use-cases/clinical-data-governance' },
      { name: 'Master Data Management', href: '/use-cases/master-data-management' },
      { name: 'Supply Chain', href: '/use-cases/supply-chain' },
    ],
    resources: [
      { name: 'Documentation', href: '/resources' },
      { name: 'Solution Brief', href: '/resources' },
      { name: 'Request Demo', href: '/request-demo' },
    ],
    company: [
      { name: 'About', href: '/company' },
      { name: 'Contact', href: '/request-demo' },
    ],
    legal: [
      { name: 'Privacy Policy', href: '/privacy' },
      { name: 'Terms of Service', href: '/terms' },
      { name: 'Data Processing Addendum', href: '/dpa' },
      { name: 'Do Not Sell My Info', href: '/privacy#ccpa' },
      { name: 'IAVP v1.0', href: '/protocol/iavp/v1' },
    ],
  };

  return (
    <footer className="bg-slate-950 border-t border-slate-800">
      <div className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-8 lg:gap-12">
          {/* Logo & Contact Column */}
          <div className="col-span-2">
            <Link to="/" className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 bg-gradient-to-br from-cyan-950 to-slate-900 border border-slate-700 flex items-center justify-center">
                <BrainCircuit className="text-cyan-500" size={16} />
              </div>
              <span className="font-bold text-white uppercase tracking-tight">Intelligent Analyst</span>
            </Link>
            <p className="text-sm text-slate-500 mb-6">
              Enterprise entity resolution with cryptographic audit trails.
            </p>

            {/* Contact Information */}
            <div className="space-y-3 text-sm">
              <div className="flex items-start gap-2 text-slate-400">
                <Mail size={14} className="mt-1 text-slate-500" />
                <div>
                  <a href="mailto:info@intelligentanalyst.com" className="hover:text-cyan-400 transition-colors">
                    info@intelligentanalyst.com
                  </a>
                </div>
              </div>
              <div className="flex items-start gap-2 text-slate-500">
                <MapPin size={14} className="mt-1" />
                <div className="text-xs leading-relaxed">
                  Intelligent Analyst, Inc.<br />
                  Delaware, USA
                </div>
              </div>
            </div>
          </div>

          {/* Platform */}
          <div>
            <h3 className="text-sm font-semibold text-white mb-4">Platform</h3>
            <ul className="space-y-3">
              {footerLinks.platform.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-sm text-slate-400 hover:text-cyan-400 transition-colors"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Use Cases */}
          <div>
            <h3 className="text-sm font-semibold text-white mb-4">Use Cases</h3>
            <ul className="space-y-3">
              {footerLinks.useCases.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-sm text-slate-400 hover:text-cyan-400 transition-colors"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources & Company */}
          <div>
            <h3 className="text-sm font-semibold text-white mb-4">Resources</h3>
            <ul className="space-y-3">
              {footerLinks.resources.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-sm text-slate-400 hover:text-cyan-400 transition-colors"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
            <h3 className="text-sm font-semibold text-white mt-6 mb-4">Company</h3>
            <ul className="space-y-3">
              {footerLinks.company.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-sm text-slate-400 hover:text-cyan-400 transition-colors"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="text-sm font-semibold text-white mb-4">Legal</h3>
            <ul className="space-y-3">
              {footerLinks.legal.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-sm text-slate-400 hover:text-cyan-400 transition-colors"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Regulatory Disclosures */}
        <div className="mt-12 pt-8 border-t border-slate-800">
          <div className="bg-slate-900/50 border border-slate-800 p-6 space-y-6">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Important Disclosures &amp; Regulatory Information
            </h4>

            {/* Service Boundaries */}
            <div className="space-y-2">
              <h5 className="text-xs font-semibold text-slate-300">Service Boundaries</h5>
              <div className="text-xs text-slate-500 leading-relaxed space-y-2">
                <p>
                  Intelligent Analyst provides entity resolution and identity attestation services
                  for enterprise customers only. This service is <strong className="text-slate-400">not</strong> a
                  consumer credit reporting agency, does not provide consumer reports as defined by the
                  Fair Credit Reporting Act (FCRA), and is not intended for use in making decisions about
                  consumer credit, employment, insurance, tenant screening, or any other purpose covered by the FCRA.
                </p>
                <p>
                  This service is <strong className="text-slate-400">not</strong> a sanctions screening provider
                  and does not provide OFAC, EU sanctions, or UN sanctions list screening. Entity resolution
                  results are provided for data quality and master data management purposes only. Customers
                  requiring sanctions screening must use a dedicated sanctions screening provider.
                </p>
              </div>
            </div>

            {/* Governing Law */}
            <div className="space-y-2">
              <h5 className="text-xs font-semibold text-slate-300">Governing Law &amp; Jurisdiction</h5>
              <div className="text-xs text-slate-500 leading-relaxed">
                <p>
                  Services are provided by Intelligent Analyst, Inc., a Delaware corporation.
                  All agreements are governed by the laws of the State of Delaware, USA, without
                  regard to conflict of law principles. Disputes shall be resolved in the state
                  or federal courts located in Delaware.
                </p>
              </div>
            </div>

            {/* Data Privacy */}
            <div className="space-y-2">
              <h5 className="text-xs font-semibold text-slate-300">Data Privacy</h5>
              <div className="text-xs text-slate-500 leading-relaxed space-y-2">
                <p>
                  <strong className="text-slate-400">GDPR (EU/EEA Users):</strong> We process personal data
                  in accordance with the General Data Protection Regulation. You have rights to access,
                  rectify, erase, restrict processing, data portability, and object to processing.
                  We act as a data processor for customer data and as a data controller for website analytics.
                  See our <Link to="/privacy" className="text-cyan-500 hover:text-cyan-400">Privacy Policy</Link> and{' '}
                  <Link to="/dpa" className="text-cyan-500 hover:text-cyan-400">Data Processing Addendum</Link> for
                  details on data subject rights and international transfers.
                </p>
                <p>
                  <strong className="text-slate-400">CCPA (California Residents):</strong> Under the California
                  Consumer Privacy Act, you have the right to know what personal information we collect,
                  request deletion, and opt out of sale. We do not sell personal information.
                  See <Link to="/privacy#ccpa" className="text-cyan-500 hover:text-cyan-400">"Do Not Sell My Info"</Link>.
                </p>
                <p>
                  <strong className="text-slate-400">Cookie Consent:</strong> We use essential cookies for
                  site functionality and optional analytics cookies with your consent. No pre-checked consent
                  boxes. You may withdraw consent at any time via our cookie preferences.
                </p>
              </div>
            </div>

            {/* Availability */}
            <div className="space-y-2">
              <h5 className="text-xs font-semibold text-slate-300">Service Availability</h5>
              <div className="text-xs text-slate-500 leading-relaxed">
                <p>
                  Services are currently available to enterprise customers in the United States, European
                  Economic Area, United Kingdom, Canada, Australia, and select other jurisdictions.
                  Services are not available in sanctioned countries or to sanctioned persons.
                  Contact us for availability in other regions.
                </p>
              </div>
            </div>

            {/* No Advice */}
            <div className="space-y-2">
              <h5 className="text-xs font-semibold text-slate-300">Disclaimer</h5>
              <div className="text-xs text-slate-500 leading-relaxed">
                <p>
                  Intelligent Analyst does not provide legal, tax, regulatory, or compliance advice.
                  Customers are responsible for their own compliance with applicable laws and regulations.
                  Results provided by the service are informational and do not constitute a legal opinion
                  or regulatory determination.
                </p>
              </div>
            </div>

            {/* Contact */}
            <div className="pt-4 border-t border-slate-800">
              <h5 className="text-xs font-semibold text-slate-300 mb-2">Contact Information</h5>
              <div className="text-xs text-slate-500 space-y-1">
                <p>Intelligent Analyst, Inc.</p>
                <p>Registered in Delaware, USA</p>
                <p>
                  Email:{' '}
                  <a href="mailto:info@intelligentanalyst.com" className="text-cyan-500 hover:text-cyan-400">
                    info@intelligentanalyst.com
                  </a>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="mt-8 pt-8 border-t border-slate-800 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-slate-500">
            &copy; {new Date().getFullYear()} Intelligent Analyst, Inc. All rights reserved.
          </p>
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              SOC 2-Aligned Design
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              GDPR-Oriented Controls
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              CCPA-Oriented Controls
            </span>
          </div>
        </div>

        {/* Doctrine Line */}
        <div className="mt-8 text-center">
          <p className="text-xs text-slate-600 font-mono">
            Intelligent Analyst exists to make AI accountable.
          </p>
        </div>
      </div>
    </footer>
  );
}
