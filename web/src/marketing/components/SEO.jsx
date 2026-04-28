import React from 'react';
import { Helmet } from 'react-helmet-async';

const BASE_URL = 'https://intelligentanalyst.com';

/**
 * SEO Component
 *
 * Handles per-route meta tags, canonical URLs, and Open Graph tags.
 * Uses react-helmet-async for SSR-compatible head management.
 */
export default function SEO({
  title,
  description,
  path = '/',
  type = 'website',
  image = '/og-image.png',
  noIndex = false,
}) {
  const fullUrl = `${BASE_URL}${path}`;
  const fullImageUrl = image.startsWith('http') ? image : `${BASE_URL}${image}`;
  const fullTitle = title
    ? `${title} | Intelligent Analyst`
    : 'Deterministic AI Governance | Intelligent Analyst';

  const defaultDescription = 'Regulator-ready AI decision infrastructure with deterministic replay, cryptographic attestation, and audit-defensible outputs.';

  return (
    <Helmet>
      {/* Primary Meta Tags */}
      <title>{fullTitle}</title>
      <meta name="title" content={fullTitle} />
      <meta name="description" content={description || defaultDescription} />

      {/* Canonical URL */}
      <link rel="canonical" href={fullUrl} />

      {/* Hreflang */}
      <link rel="alternate" hreflang="en" href={fullUrl} />
      <link rel="alternate" hreflang="x-default" href={fullUrl} />

      {/* Open Graph / Facebook */}
      <meta property="og:type" content={type} />
      <meta property="og:url" content={fullUrl} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description || defaultDescription} />
      <meta property="og:image" content={fullImageUrl} />
      <meta property="og:site_name" content="Intelligent Analyst" />

      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:url" content={fullUrl} />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description || defaultDescription} />
      <meta name="twitter:image" content={fullImageUrl} />

      {/* Robots */}
      {noIndex && <meta name="robots" content="noindex, nofollow" />}
    </Helmet>
  );
}
