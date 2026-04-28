import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Package, ClipboardCheck, ExternalLink, BookOpen } from 'lucide-react';

const resources = [
  {
    id: 'IA-VP-1.0',
    title: 'IAVP v1.0 Protocol Specification',
    type: 'Protocol',
    description: 'Intelligent Analyst Verification Protocol. Defines hash chain construction, canonical serialization, signature requirements, and replay verification.',
    href: '/protocol/iavp/v1',
    external: false,
    icon: FileText,
  },
  {
    id: 'IA-FRD-1.0',
    title: 'Forensic Resolution Dossier (Sample)',
    type: 'Evidence Pack',
    description: 'Sample evidence pack demonstrating IAVP v1.0 compliance. Includes manifest fields, hash chain root, signature block, and verification instructions.',
    href: '/samples/evidence-pack',
    external: false,
    icon: Package,
  },
  {
    id: 'IA-RRFC-1.0',
    title: 'Regulator-Ready Forensic Checklist',
    type: 'Audit Instrument',
    description: '27 controls across 5 domains. Data Retention, Chain Attestation, Operational Integrity, Forensic Export, and Regulatory Governance.',
    href: '/resources/Regulator_Ready_Forensic_Checklist_v1.0.pdf',
    external: true,
    icon: ClipboardCheck,
  },
  {
    id: 'IA-GOT-1.0',
    title: 'Glossary of Institutional Terms',
    type: 'Glossary',
    description: 'Definitions aligned to IAVP v1.0 terminology for deterministic replay, attestation, ordering, and governance controls.',
    href: '/glossary',
    external: false,
    icon: BookOpen,
  },
];

export default function ResourcesHub() {
  useEffect(() => {
    document.title = 'Resources Hub | Institutional Data Governance Standards | Intelligent Analyst';

    // Set meta description
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      metaDesc.setAttribute('content', 'Directory of published verification standards, forensic dossiers, and audit instruments.');
    }
  }, []);

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-gray-200 py-4 px-8">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Link to="/" className="text-sm text-gray-500 hover:text-gray-700">
            Intelligent Analyst, Inc.
          </Link>
          <span className="text-xs text-gray-400 font-mono">Resources Hub</span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-8 py-12">
        {/* Title Block */}
        <div className="border border-gray-300 mb-10">
          <div className="bg-gray-50 px-6 py-4 border-b border-gray-300">
            <h1 className="text-xl font-bold text-gray-900">
              Resources Hub
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Published verification standards, forensic dossiers, and audit instruments.
            </p>
          </div>
        </div>

        {/* Resource Cards */}
        <div className="space-y-6">
          {resources.map((resource) => {
            const Icon = resource.icon;
            const CardWrapper = resource.external ? 'a' : Link;
            const cardProps = resource.external
              ? { href: resource.href, target: '_blank', rel: 'noopener noreferrer' }
              : { to: resource.href };

            return (
              <CardWrapper
                key={resource.id}
                {...cardProps}
                className="block border border-gray-200 hover:border-amber-400 transition-colors"
              >
                <div className="p-6">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-10 h-10 bg-gray-100 border border-gray-200 flex items-center justify-center">
                      <Icon size={20} className="text-gray-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-gray-400">{resource.id}</span>
                        <span className="text-xs text-gray-400">|</span>
                        <span className="text-xs text-gray-500">{resource.type}</span>
                        {resource.external && (
                          <ExternalLink size={12} className="text-gray-400" />
                        )}
                      </div>
                      <h2 className="text-base font-semibold text-gray-900 mb-2">
                        {resource.title}
                      </h2>
                      <p className="text-sm text-gray-600 leading-relaxed">
                        {resource.description}
                      </p>
                    </div>
                  </div>
                </div>
              </CardWrapper>
            );
          })}
        </div>

        {/* Footer Note */}
        <div className="mt-12 pt-8 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            All documents follow IAVP v1.0 structural conventions. Sample artifacts are labeled DEMO_SIMULATED and do not represent production-retained WORM data.
          </p>
        </div>
      </main>

      {/* Page Footer */}
      <footer className="border-t border-gray-200 py-6 px-8 mt-16">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs text-gray-400">
            &copy; {new Date().getFullYear()} Intelligent Analyst, Inc.
          </p>
        </div>
      </footer>
    </div>
  );
}
