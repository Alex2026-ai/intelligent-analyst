import React, { useEffect } from 'react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section, { SectionHeader } from '../components/Section';
import PublicTrustFeed from '../components/PublicTrustFeed';

export default function TrustFeedPage() {
  useEffect(() => {
    document.title = 'Public Trust Feed | Intelligent Analyst';
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      <Section>
        <SectionHeader
          eyebrow="Live Proof"
          title="Public Trust Feed"
          subtitle="Every published authority sample — verified through deterministic analysis, policy-controlled derivation, and cryptographic integrity."
        />
        <PublicTrustFeed />
      </Section>

      <Footer />
    </div>
  );
}
