import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';

const COOKIE_CONSENT_KEY = 'ia_cookie_consent';

/**
 * CookieConsent
 *
 * GDPR-compliant cookie consent banner.
 * - No pre-ticked boxes
 * - Clear opt-in/opt-out options
 * - Persists choice in localStorage
 */
export default function CookieConsent() {
  const [showBanner, setShowBanner] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    // Check if user has already made a choice
    const consent = localStorage.getItem(COOKIE_CONSENT_KEY);
    if (!consent) {
      // Small delay to not block initial render
      const timer = setTimeout(() => setShowBanner(true), 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleAcceptAll = () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify({
      essential: true,
      analytics: true,
      marketing: false, // We don't use marketing cookies
      timestamp: new Date().toISOString(),
    }));
    setShowBanner(false);
  };

  const handleAcceptEssential = () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify({
      essential: true,
      analytics: false,
      marketing: false,
      timestamp: new Date().toISOString(),
    }));
    setShowBanner(false);
  };

  const handleDeclineAll = () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify({
      essential: true, // Essential cookies are always needed
      analytics: false,
      marketing: false,
      timestamp: new Date().toISOString(),
    }));
    setShowBanner(false);
  };

  if (!showBanner) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 p-3 md:p-6" role="region" aria-label="Cookie preferences">
      <div className="max-w-3xl mx-auto bg-slate-900 border border-slate-700 shadow-2xl rounded-lg">
        <div className="p-4">
          <div className="flex items-start justify-between gap-4 mb-3">
            <div>
              <h3 className="text-white font-semibold mb-1">Cookie Preferences</h3>
              <p className="text-slate-400 text-xs md:text-sm leading-relaxed">
                Essential cookies keep the site working. Optional analytics help us improve it.
              </p>
            </div>
            <button
              type="button"
              onClick={handleDeclineAll}
              className="text-slate-500 hover:text-white transition-colors p-1"
              aria-label="Close"
            >
              <X size={20} />
            </button>
          </div>

          {showDetails && (
            <div className="mb-4 p-4 bg-slate-950 rounded border border-slate-800">
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-white font-medium">Essential Cookies</span>
                    <p className="text-slate-500 text-xs">Required for site functionality</p>
                  </div>
                  <span className="text-slate-500 text-xs">Always Active</span>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-white font-medium">Analytics Cookies</span>
                    <p className="text-slate-500 text-xs">Help us improve our site</p>
                  </div>
                  <span className="text-slate-500 text-xs">Optional</span>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-col sm:flex-row items-center gap-3">
            <button
              type="button"
              onClick={() => setShowDetails(!showDetails)}
              className="text-cyan-500 text-sm hover:text-cyan-400 transition-colors"
            >
              {showDetails ? 'Hide Details' : 'Cookie Details'}
            </button>

            <div className="flex-1" />

            <div className="grid grid-cols-2 sm:flex gap-2 w-full sm:w-auto">
              <button
                type="button"
                onClick={handleAcceptEssential}
                className="px-4 py-2 text-sm text-slate-400 border border-slate-700 rounded hover:bg-slate-800 transition-colors"
              >
                Essential Only
              </button>
              <button
                type="button"
                onClick={handleAcceptAll}
                className="px-4 py-2 text-sm bg-cyan-500 text-slate-950 font-medium rounded hover:bg-cyan-400 transition-colors"
              >
                Accept All
              </button>
            </div>
          </div>

          <div className="mt-3 text-center sm:text-left">
            <Link to="/privacy" className="text-slate-500 text-xs hover:text-slate-400">
              Read our Privacy Policy
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
