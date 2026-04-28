import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';

export default function NotFound() {
  useEffect(() => {
    document.title = '404 | Intelligent Analyst';
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />
      <section className="pt-32 pb-16 md:pt-40 md:pb-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-lg mx-auto text-center">
            <div className="font-mono text-6xl text-slate-700 mb-6">404</div>
            <h1 className="text-2xl font-bold text-white mb-4">Page not found</h1>
            <p className="text-slate-400 mb-8">
              The page you requested does not exist or has been moved.
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 h-10 px-6 bg-cyan-600 text-white text-sm font-semibold hover:bg-cyan-500 transition-colors"
            >
              <ArrowLeft size={16} />
              Back to home
            </Link>
          </div>
        </div>
      </section>
      <Footer />
    </div>
  );
}
