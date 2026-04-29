import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Mail, MapPin, BrainCircuit } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';

export default function Company() {
  useEffect(() => {
    document.title = 'Company | Intelligent Analyst';
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />
      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-3xl mx-auto px-6">
          <h1 className="text-3xl font-bold text-white mb-6">Company</h1>

          <div className="space-y-8">
            <div>
              <h2 className="text-lg font-semibold text-slate-200 mb-3">About Intelligent Analyst</h2>
              <p className="text-sm text-slate-400 leading-relaxed">
                Intelligent Analyst provides enterprise entity resolution with cryptographic audit trails.
                We help organizations resolve, verify, and attest company and person identities across
                data sources with full forensic transparency.
              </p>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-slate-200 mb-3">Our Approach</h2>
              <p className="text-sm text-slate-400 leading-relaxed">
                Every resolution decision is signed, chained, and anchored. The IAVP (Intelligent Analyst
                Verification Protocol) ensures that no result can be silently altered after the fact.
                Operators see exactly what happened, when, and why.
              </p>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-slate-200 mb-3">Contact</h2>
              <div className="space-y-3 text-sm text-slate-400">
                <div className="flex items-center gap-2">
                  <Mail size={14} className="text-slate-500" />
                  <a href="mailto:info@intelligentanalyst.com" className="text-cyan-500 hover:text-cyan-400">
                    info@intelligentanalyst.com
                  </a>
                </div>
                <div className="flex items-center gap-2">
                  <MapPin size={14} className="text-slate-500" />
                  <span>Intelligent Analyst, Inc. &middot; Delaware, USA</span>
                </div>
              </div>
            </div>

            <div className="pt-6">
              <Link
                to="/request-demo"
                className="inline-flex h-10 px-6 bg-cyan-500 text-slate-950 text-sm font-semibold items-center justify-center hover:bg-cyan-400 transition-colors"
              >
                Request Demo
              </Link>
            </div>
          </div>
        </div>
      </section>
      <Footer />
    </div>
  );
}
