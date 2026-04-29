import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Mail } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Section from '../components/Section';

export default function RequestDemo() {
  useEffect(() => {
    document.title = 'Request Demo | Intelligent Analyst';
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-2xl mx-auto text-center">
            <div className="forensic-badge mb-6">Contact</div>
            <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
              Request a demo
            </h1>
            <p className="text-xl text-slate-400 leading-relaxed mb-12">
              See the platform with your own data. We will walk you through
              entity resolution, forensic audit, and compliance export.
            </p>

            <div className="bg-slate-900/80 border border-slate-800 p-6 mb-8">
              <div className="grid sm:grid-cols-3 gap-4 text-left">
                <div>
                  <div className="text-xs font-mono text-cyan-400 mb-1">01</div>
                  <div className="text-sm font-semibold text-white">Workflow review</div>
                  <p className="text-xs text-slate-500 mt-1">Map your entity-resolution process.</p>
                </div>
                <div>
                  <div className="text-xs font-mono text-cyan-400 mb-1">02</div>
                  <div className="text-sm font-semibold text-white">Evidence walkthrough</div>
                  <p className="text-xs text-slate-500 mt-1">Review replay, signatures, and hash chains.</p>
                </div>
                <div>
                  <div className="text-xs font-mono text-cyan-400 mb-1">03</div>
                  <div className="text-sm font-semibold text-white">Governance fit</div>
                  <p className="text-xs text-slate-500 mt-1">Identify audit and retention requirements.</p>
                </div>
              </div>
            </div>

            <a
              href="mailto:info@intelligentanalyst.com?subject=Governance%20Audit%20Request"
              className="inline-flex w-full sm:w-auto items-center justify-center gap-3 min-h-14 px-6 sm:px-8 bg-cyan-600 text-white font-semibold hover:bg-cyan-500 transition-colors text-base sm:text-lg"
            >
              <Mail size={20} />
              <span className="sm:hidden">Email Enterprise</span>
              <span className="hidden sm:inline">info@intelligentanalyst.com</span>
            </a>

            <p className="text-slate-500 text-sm mt-8">
              Or try the platform now:
            </p>
            <div className="flex justify-center gap-4 mt-4">
              <Link
                to="/preview"
                className="inline-flex items-center gap-2 h-10 px-6 border border-slate-700 text-slate-300 text-sm font-medium hover:bg-slate-800/50 hover:border-slate-600 transition-all"
              >
                Live Preview
                <ArrowRight size={14} />
              </Link>
              <Link
                to="/product"
                className="inline-flex items-center gap-2 h-10 px-6 border border-slate-700 text-slate-300 text-sm font-medium hover:bg-slate-800/50 hover:border-slate-600 transition-all"
              >
                Product Tour
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
