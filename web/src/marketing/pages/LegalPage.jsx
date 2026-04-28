import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import Header from '../components/Header';
import Footer from '../components/Footer';

const LEGAL_CONTENT = {
  privacy: {
    title: 'Privacy Policy',
    lastUpdated: 'March 2026',
    sections: [
      {
        heading: 'Overview',
        body: 'Intelligent Analyst, Inc. ("we", "us", "our") is committed to protecting the privacy of our enterprise customers and website visitors. This Privacy Policy describes how we collect, use, and share personal information.',
      },
      {
        heading: 'Data We Collect',
        body: 'We collect information you provide directly (name, email, company) when requesting a demo or creating an account. We collect usage data (pages visited, features used) through essential and optional analytics cookies. We process customer-uploaded data (company names, entity records) solely to provide entity resolution services.',
      },
      {
        heading: 'How We Use Data',
        body: 'We use personal information to provide and improve our services, communicate with customers, ensure security, and comply with legal obligations. Customer-uploaded data is processed exclusively for entity resolution and is never used for advertising, profiling, or sold to third parties.',
      },
      {
        heading: 'Data Retention',
        body: 'Account data is retained while your account is active. Batch processing data is retained according to your subscription terms and applicable legal hold requirements. You may request deletion at any time, subject to legal retention obligations.',
      },
      {
        heading: 'GDPR (EU/EEA)',
        body: 'For EU/EEA users: we act as a data processor for customer data and a data controller for website analytics. You have rights to access, rectify, erase, restrict processing, data portability, and object to processing. Contact privacy@intelligentanalyst.com to exercise these rights.',
      },
      {
        id: 'ccpa',
        heading: 'CCPA (California)',
        body: 'For California residents: you have the right to know what personal information we collect, request deletion, and opt out of sale. We do not sell personal information. To exercise your rights, contact privacy@intelligentanalyst.com.',
      },
      {
        heading: 'Contact',
        body: 'For privacy inquiries, contact privacy@intelligentanalyst.com. Intelligent Analyst, Inc., Delaware, USA.',
      },
    ],
  },
  terms: {
    title: 'Terms of Service',
    lastUpdated: 'March 2026',
    sections: [
      {
        heading: 'Agreement',
        body: 'By accessing or using Intelligent Analyst services, you agree to be bound by these Terms of Service. If you are using the services on behalf of an organization, you represent that you have authority to bind that organization.',
      },
      {
        heading: 'Services',
        body: 'Intelligent Analyst provides enterprise entity resolution with cryptographic audit trails. Services are provided "as is" for enterprise data quality and master data management purposes. We are not a credit reporting agency, sanctions screening provider, or legal advisor.',
      },
      {
        heading: 'Customer Responsibilities',
        body: 'You are responsible for the accuracy and legality of data you upload. You must comply with all applicable laws and regulations, including data protection laws. You must not use the services to process data you are not authorized to process.',
      },
      {
        heading: 'Intellectual Property',
        body: 'All intellectual property in the services, including the IAVP protocol, resolution algorithms, and documentation, remains the property of Intelligent Analyst, Inc. Customer data remains the property of the customer.',
      },
      {
        heading: 'Limitation of Liability',
        body: 'To the maximum extent permitted by law, Intelligent Analyst shall not be liable for indirect, incidental, special, or consequential damages. Our total liability shall not exceed the fees paid by you in the twelve months preceding the claim.',
      },
      {
        heading: 'Governing Law',
        body: 'These terms are governed by the laws of the State of Delaware, USA, without regard to conflict of law principles. Disputes shall be resolved in the state or federal courts located in Delaware.',
      },
    ],
  },
  dpa: {
    title: 'Data Processing Addendum',
    lastUpdated: 'March 2026',
    sections: [
      {
        heading: 'Scope',
        body: 'This Data Processing Addendum ("DPA") supplements the Terms of Service and applies to all processing of personal data by Intelligent Analyst on behalf of the customer. This DPA incorporates the Standard Contractual Clauses for international data transfers where required.',
      },
      {
        heading: 'Roles',
        body: 'The customer is the data controller. Intelligent Analyst acts as a data processor, processing personal data solely on the customer\'s documented instructions for the purpose of providing entity resolution services.',
      },
      {
        heading: 'Security Measures',
        body: 'We implement appropriate technical and organizational measures including: encryption at rest and in transit (AES-256-GCM, TLS 1.3), KMS-based cryptographic signing, per-tenant data isolation, role-based access control, and immutable audit trails with 7-year WORM retention capability.',
      },
      {
        heading: 'Sub-processors',
        body: 'We use Google Cloud Platform (US and EU regions) for infrastructure. Anthropic (Claude) is used for L3 LLM resolution with no data retention. We maintain an up-to-date list of sub-processors and notify customers of changes.',
      },
      {
        heading: 'Data Subject Rights',
        body: 'We assist the customer in responding to data subject requests (access, rectification, erasure, portability). Requests should be directed to your account representative or privacy@intelligentanalyst.com.',
      },
      {
        heading: 'International Transfers',
        body: 'For transfers outside the EU/EEA, we rely on Standard Contractual Clauses (Module 2: Controller to Processor). EU-sovereign processing is available via our europe-west3 deployment. Contact us for the full executed SCCs.',
      },
      {
        heading: 'Contact',
        body: 'Data protection inquiries: privacy@intelligentanalyst.com. For EU-specific requests, our representative can be reached at the same address.',
      },
    ],
  },
};

export default function LegalPage({ type }) {
  const content = LEGAL_CONTENT[type];

  useEffect(() => {
    document.title = `${content?.title || 'Legal'} | Intelligent Analyst`;
  }, [content]);

  if (!content) {
    return null;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />
      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-3xl mx-auto px-6">
          <div className="mb-12">
            <h1 className="text-3xl font-bold text-white mb-3">{content.title}</h1>
            <p className="text-sm text-slate-500 font-mono">Last updated: {content.lastUpdated}</p>
          </div>

          <div className="space-y-10">
            {content.sections.map((section, idx) => (
              <div key={idx} id={section.id || undefined}>
                <h2 className="text-lg font-semibold text-slate-200 mb-3">{section.heading}</h2>
                <p className="text-sm text-slate-400 leading-relaxed">{section.body}</p>
              </div>
            ))}
          </div>

          <div className="mt-16 pt-8 border-t border-slate-800">
            <p className="text-xs text-slate-600">
              Intelligent Analyst, Inc. &middot; Delaware, USA &middot;{' '}
              <a href="mailto:legal@intelligentanalyst.com" className="text-cyan-600 hover:text-cyan-400">
                legal@intelligentanalyst.com
              </a>
            </p>
          </div>
        </div>
      </section>
      <Footer />
    </div>
  );
}
