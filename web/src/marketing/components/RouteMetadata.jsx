import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const BASE_URL = 'https://intelligentanalyst.com';
const DEFAULT_TITLE = 'Deterministic AI Governance | Intelligent Analyst';
const DEFAULT_DESCRIPTION =
  'Regulator-ready AI decision infrastructure with deterministic replay, cryptographic attestation, and audit-defensible outputs.';
const DEFAULT_IMAGE = '/og-image.png';

const ROUTE_META = {
  '/': {
    title: DEFAULT_TITLE,
    description: DEFAULT_DESCRIPTION,
  },
  '/product': {
    title: 'Product Tour | Intelligent Analyst',
    description:
      'See how Intelligent Analyst turns entity resolution into signed, hash-chained, independently verifiable evidence.',
  },
  '/platform': {
    title: 'Platform | Intelligent Analyst',
    description:
      'A deterministic entity resolution platform for canonical matching, audit trails, and cryptographic decision evidence.',
  },
  '/security': {
    title: 'Forensic Audit | Intelligent Analyst',
    description:
      'Reconstruct decision lineage with deterministic replay, signed receipts, hash chains, and examination-ready evidence.',
  },
  '/forensic-audit': {
    title: 'Forensic Audit | Intelligent Analyst',
    description:
      'Reconstruct decision lineage with deterministic replay, signed receipts, hash chains, and examination-ready evidence.',
  },
  '/trust-architecture': {
    title: 'Trust Architecture | Intelligent Analyst',
    description:
      'Explore the trust architecture behind Intelligent Analyst: tenant isolation, deterministic replay, attestation, retention, and public verification.',
  },
  '/protocol': {
    title: 'IAVP v1.0 - The Verification Protocol | Intelligent Analyst',
    description:
      'The Intelligent Analyst Verification Protocol proves AI decisions are reproducible, signed, and tamper-evident.',
  },
  '/verify': {
    title: 'Verification Walkthrough | Intelligent Analyst',
    description:
      'Learn how to verify Intelligent Analyst batch attestations, hash chains, signatures, ordering, and external anchors.',
  },
  '/compliance': {
    title: 'Compliance & Governance | Intelligent Analyst',
    description:
      'Governance and compliance controls for regulated AI decision infrastructure, including audit trails, retention, and reliance tiers.',
  },
  '/trust-feed': {
    title: 'Public Trust Feed | Intelligent Analyst',
    description:
      'Published, policy-controlled samples of deterministic resolutions and cryptographic evidence.',
  },
  '/resources': {
    title: 'Resources Hub | Institutional Data Governance Standards | Intelligent Analyst',
    description:
      'Directory of published verification standards, forensic dossiers, and audit instruments from Intelligent Analyst.',
  },
  '/protocol/iavp/v1': {
    title: 'IAVP v1.0 Specification | Intelligent Analyst',
    description:
      'Public IAVP v1.0 specification for canonical serialization, record hashing, stable ordering, signatures, and replay verification.',
  },
  '/samples/evidence-pack': {
    title: 'Forensic Resolution Dossier Sample | Intelligent Analyst',
    description:
      'Sample evidence pack demonstrating IAVP v1.0 manifest fields, hash chain root, signature block, and verification instructions.',
  },
  '/glossary': {
    title: 'Glossary of Institutional Data Integrity Terms | Intelligent Analyst',
    description:
      'Definitions for deterministic replay, attestation, stable input ordering, hash chains, evidence packs, and governance controls.',
  },
  '/company': {
    title: 'Company | Intelligent Analyst',
    description:
      'Learn about Intelligent Analyst and its approach to deterministic AI governance for regulated enterprises.',
  },
  '/request-demo': {
    title: 'Request Demo | Intelligent Analyst',
    description:
      'Request a governance audit walkthrough of Intelligent Analyst using your entity resolution and compliance workflow.',
  },
  '/use-cases': {
    title: 'Use Cases | Intelligent Analyst',
    description:
      'Use cases for deterministic entity resolution across compliance, clinical data governance, master data, and supply chain workflows.',
  },
  '/use-cases/regulatory-compliance': {
    title: 'Regulatory Compliance | Intelligent Analyst',
    description:
      'Create examination-ready audit trails with reproducible entity resolution and signed decision evidence.',
  },
  '/use-cases/clinical-data-governance': {
    title: 'Clinical Data Governance | Intelligent Analyst',
    description:
      'HIPAA-aligned entity matching with tenant isolation, PII protection, and verifiable decision history.',
  },
  '/use-cases/master-data-management': {
    title: 'Master Data Management | Intelligent Analyst',
    description:
      'Unify records across systems with deterministic canonical matching and auditable resolution evidence.',
  },
  '/use-cases/supply-chain': {
    title: 'Supply Chain Verification | Intelligent Analyst',
    description:
      'Verify supplier and counterparty identity with signed, reproducible entity resolution evidence.',
  },
  '/transparency-manifesto': {
    title: 'Transparency Manifesto | Intelligent Analyst',
    description:
      'The Intelligent Analyst position on deterministic governance, attestation, and ending black-box AI decisions.',
  },
  '/privacy': {
    title: 'Privacy Policy | Intelligent Analyst',
    description:
      'Privacy policy for Intelligent Analyst website, customer data processing, GDPR, and CCPA rights.',
  },
  '/terms': {
    title: 'Terms of Service | Intelligent Analyst',
    description: 'Terms of service for Intelligent Analyst enterprise software and verification services.',
  },
  '/dpa': {
    title: 'Data Processing Addendum | Intelligent Analyst',
    description:
      'Data processing addendum for Intelligent Analyst customer data, security measures, and processor obligations.',
  },
  '/app': {
    title: 'Sign In | Intelligent Analyst',
    description: 'Sign in to the Intelligent Analyst dashboard.',
    noIndex: true,
  },
  '/preview': {
    title: 'Dashboard Preview | Intelligent Analyst',
    description: 'Visual preview of the Intelligent Analyst dashboard using sample data only.',
    noIndex: true,
  },
};

function upsertMeta(selector, createAttrs, updateAttrs) {
  let tag = document.head.querySelector(selector);
  if (!tag) {
    tag = document.createElement('meta');
    Object.entries(createAttrs).forEach(([key, value]) => tag.setAttribute(key, value));
    document.head.appendChild(tag);
  }
  Object.entries(updateAttrs).forEach(([key, value]) => tag.setAttribute(key, value));
}

function upsertLink(selector, createAttrs, updateAttrs) {
  let tag = document.head.querySelector(selector);
  if (!tag) {
    tag = document.createElement('link');
    Object.entries(createAttrs).forEach(([key, value]) => tag.setAttribute(key, value));
    document.head.appendChild(tag);
  }
  Object.entries(updateAttrs).forEach(([key, value]) => tag.setAttribute(key, value));
}

function getRouteMeta(pathname) {
  if (ROUTE_META[pathname]) return ROUTE_META[pathname];
  if (pathname.startsWith('/s/')) {
    return {
      title: 'Shared Batch Evidence | Intelligent Analyst',
      description: 'A shared Intelligent Analyst batch evidence view.',
      noIndex: true,
    };
  }
  return {
    title: '404 | Intelligent Analyst',
    description: 'The requested Intelligent Analyst page could not be found.',
    noIndex: true,
  };
}

export default function RouteMetadata() {
  const { pathname } = useLocation();

  useEffect(() => {
    const meta = getRouteMeta(pathname);
    const canonicalPath = ROUTE_META[pathname] ? pathname : '/';
    const canonicalUrl = `${BASE_URL}${canonicalPath}`;
    const imageUrl = `${BASE_URL}${meta.image || DEFAULT_IMAGE}`;
    const description = meta.description || DEFAULT_DESCRIPTION;

    document.title = meta.title || DEFAULT_TITLE;

    upsertMeta('meta[name="title"]', { name: 'title' }, { content: document.title });
    upsertMeta('meta[name="description"]', { name: 'description' }, { content: description });
    upsertMeta('meta[property="og:type"]', { property: 'og:type' }, { content: 'website' });
    upsertMeta('meta[property="og:url"]', { property: 'og:url' }, { content: canonicalUrl });
    upsertMeta('meta[property="og:title"]', { property: 'og:title' }, { content: document.title });
    upsertMeta('meta[property="og:description"]', { property: 'og:description' }, { content: description });
    upsertMeta('meta[property="og:image"]', { property: 'og:image' }, { content: imageUrl });
    upsertMeta('meta[property="og:image:width"]', { property: 'og:image:width' }, { content: '1200' });
    upsertMeta('meta[property="og:image:height"]', { property: 'og:image:height' }, { content: '630' });
    upsertMeta('meta[property="og:site_name"]', { property: 'og:site_name' }, { content: 'Intelligent Analyst' });
    upsertMeta('meta[name="twitter:card"]', { name: 'twitter:card' }, { content: 'summary_large_image' });
    upsertMeta('meta[name="twitter:url"]', { name: 'twitter:url' }, { content: canonicalUrl });
    upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title' }, { content: document.title });
    upsertMeta('meta[name="twitter:description"]', { name: 'twitter:description' }, { content: description });
    upsertMeta('meta[name="twitter:image"]', { name: 'twitter:image' }, { content: imageUrl });

    if (meta.noIndex) {
      upsertMeta('meta[name="robots"]', { name: 'robots' }, { content: 'noindex, nofollow' });
    } else {
      document.head.querySelector('meta[name="robots"]')?.remove();
    }

    upsertLink('link[rel="canonical"]', { rel: 'canonical' }, { href: canonicalUrl });
  }, [pathname]);

  return null;
}
