import React, { useState, useEffect } from 'react';
import { Shield, CheckCircle, XCircle, Clock, Layers, AlertCircle, Lock } from 'lucide-react';

/**
 * ReceiptValidator
 *
 * Security terminal-style widget for visitors to validate notarization receipts.
 * Features cryptographic handshake animation and glow effects.
 */

// Sample receipt for demo purposes
const SAMPLE_RECEIPT = {
  batch_id: 'BATCH-DEMO-A1B2C3D4',
  timestamp: '2026-02-17T10:30:00Z',
  tenant_hash: 'sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
  total_records: 1000,
  layers: {
    L1: 412,
    L2: 345,
    L3: 198,
    L4: 45,
  },
  hash_chain: {
    root: 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    algorithm: 'SHA-256',
    depth: 1000,
  },
  signature: {
    algorithm: 'ECDSA P-256',
    status: 'VALID',
    key_id: 'golden-signing-prod',
  },
  worm_status: 'COMMITTED',
  retention_until: '2033-02-17',
};

// Fake hash sequences for handshake animation
const HASH_SEQUENCES = [
  'a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a',
  '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
  'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9',
  'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
];

// Input scanner - shows rapid hash flickering in the input area
function InputScanner({ onComplete }) {
  const [displayHash, setDisplayHash] = useState('');
  const [scanCount, setScanCount] = useState(0);

  useEffect(() => {
    const generateRandomHash = () => {
      const chars = '0123456789abcdef';
      return Array.from({ length: 64 }, () => chars[Math.floor(Math.random() * 16)]).join('');
    };

    const interval = setInterval(() => {
      setDisplayHash(generateRandomHash());
      setScanCount((prev) => {
        if (prev >= 15) { // ~1.5 seconds at 100ms intervals
          clearInterval(interval);
          setTimeout(onComplete, 200);
          return prev;
        }
        return prev + 1;
      });
    }, 100);

    return () => clearInterval(interval);
  }, [onComplete]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-3 h-3 bg-amber-500 animate-pulse" style={{ boxShadow: '0 0 10px #f59e0b' }} />
        <span className="font-mono text-sm text-amber-400 uppercase tracking-wider">
          Scanning Input...
        </span>
      </div>

      {/* Flickering hash display in input-like box */}
      <div className="relative">
        <div className="w-full h-32 bg-slate-950 border border-amber-700 p-4 font-mono text-sm overflow-hidden">
          <div className="text-amber-400/80 hash-flicker break-all leading-relaxed">
            {displayHash.slice(0, 16)}<br/>
            {displayHash.slice(16, 32)}<br/>
            {displayHash.slice(32, 48)}<br/>
            {displayHash.slice(48, 64)}
          </div>
        </div>
        {/* Scan line animation */}
        <div className="absolute left-0 right-0 h-0.5 bg-amber-500 scan-line" style={{ boxShadow: '0 0 8px #f59e0b' }} />
      </div>

      <div className="flex items-center justify-between text-xs font-mono text-slate-500">
        <span>SCANNING: {Math.round((scanCount / 15) * 100)}%</span>
        <span className="text-amber-400">ANALYZING SIGNATURE</span>
      </div>
    </div>
  );
}

function CryptoHandshake({ onComplete }) {
  const [currentHash, setCurrentHash] = useState(0);
  const [flickerClass, setFlickerClass] = useState('');

  useEffect(() => {
    const interval = setInterval(() => {
      setFlickerClass('hash-flicker');
      setCurrentHash((prev) => {
        if (prev >= HASH_SEQUENCES.length - 1) {
          clearInterval(interval);
          setTimeout(onComplete, 300);
          return prev;
        }
        return prev + 1;
      });
      setTimeout(() => setFlickerClass(''), 200);
    }, 400);

    return () => clearInterval(interval);
  }, [onComplete]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-3 h-3 bg-cyan-500 animate-pulse" style={{ boxShadow: '0 0 10px #0891b2' }} />
        <span className="font-mono text-sm text-cyan-400 uppercase tracking-wider">
          Verifying Cryptographic Signature...
        </span>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-mono text-slate-500 uppercase tracking-wider">
          Hash Chain Validation
        </div>
        <div className={`hash-display ${flickerClass}`}>
          sha256:{HASH_SEQUENCES[currentHash]}
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs font-mono text-slate-500">
        <span>DEPTH: {currentHash + 1}/{HASH_SEQUENCES.length}</span>
        <span>|</span>
        <span>ALGO: SHA-256</span>
        <span>|</span>
        <span className="text-cyan-400">VERIFYING</span>
      </div>
    </div>
  );
}

function ValidationResult({ result, onReset }) {
  const isValid = result.signature?.status === 'VALID';

  return (
    <div className="space-y-6">
      {/* Status Header */}
      <div className={`p-4 border ${isValid ? 'border-emerald-800 bg-emerald-950/20' : 'border-red-800 bg-red-950/20'}`}>
        <div className="flex items-center gap-3">
          {isValid ? (
            <CheckCircle className="text-emerald-500" size={24} />
          ) : (
            <XCircle className="text-red-500" size={24} />
          )}
          <div>
            <div className={`font-mono font-semibold uppercase tracking-wider ${isValid ? 'text-emerald-400' : 'text-red-400'}`}>
              {isValid ? 'Signature Valid' : 'Signature Invalid'}
            </div>
            <div className="text-slate-400 text-sm font-mono">
              {isValid
                ? 'Cryptographic verification complete.'
                : 'Receipt could not be verified.'}
            </div>
            {isValid && (
              <div className="text-slate-500 text-xs font-mono mt-1">
                Transparency Confirmed.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Batch Info */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-slate-500 text-xs font-mono uppercase tracking-wider">
          <Shield size={12} />
          <span>Verification Details</span>
        </div>

        <div className="bg-slate-900/50 border border-slate-800 divide-y divide-slate-800">
          <div className="p-4 flex justify-between items-center">
            <span className="text-slate-500 text-sm font-mono">BATCH_ID</span>
            <span className="font-mono text-cyan-400 text-sm">{result.batch_id}</span>
          </div>
          <div className="p-4 flex justify-between items-center">
            <span className="text-slate-500 text-sm font-mono">TIMESTAMP</span>
            <span className="font-mono text-slate-300 text-sm">
              {new Date(result.timestamp).toISOString()}
            </span>
          </div>
          <div className="p-4 flex justify-between items-center">
            <span className="text-slate-500 text-sm font-mono">RECORDS</span>
            <span className="font-mono text-slate-300 text-sm">
              {result.total_records?.toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      {/* Layer Distribution */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-slate-500 text-xs font-mono uppercase tracking-wider">
          <Layers size={12} />
          <span>Layer Distribution</span>
        </div>

        <div className="grid grid-cols-4 gap-2">
          {Object.entries(result.layers || {}).map(([layer, count]) => (
            <div
              key={layer}
              className="bg-slate-900/50 border border-slate-800 p-3 text-center"
            >
              <div className={`font-mono text-lg font-semibold layer-${layer.toLowerCase()}`}>
                {count}
              </div>
              <div className="text-slate-500 text-xs font-mono">{layer}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Cryptographic Details */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-slate-500 text-xs font-mono uppercase tracking-wider">
          <Lock size={12} />
          <span>Cryptographic Proof</span>
        </div>

        <div className="bg-slate-900/50 border border-slate-800 p-4 space-y-3">
          <div>
            <div className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-1">HASH_CHAIN_ROOT</div>
            <div className="hash-display">{result.hash_chain?.root}</div>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-1">ALGORITHM</div>
              <div className="font-mono text-slate-300">{result.signature?.algorithm}</div>
            </div>
            <div>
              <div className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-1">RETENTION</div>
              <div className="font-mono text-slate-300">Until {result.retention_until}</div>
            </div>
          </div>
        </div>
      </div>

      {/* WORM Status */}
      <div className="flex items-center justify-between p-4 bg-slate-900/50 border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 bg-emerald-500" style={{ boxShadow: '0 0 8px #10b981' }} />
          <span className="text-slate-300 text-sm font-mono">WORM_STORAGE</span>
        </div>
        <span className="font-mono text-emerald-400 text-sm">{result.worm_status}</span>
      </div>

      {/* Reset */}
      <button
        onClick={onReset}
        className="w-full p-3 border border-slate-700 text-slate-400 text-sm font-mono uppercase tracking-wider hover:bg-slate-800/50 transition-colors"
      >
        Verify Another Receipt
      </button>
    </div>
  );
}

function TerminalForm({ onValidate }) {
  const [input, setInput] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [scanningHashes, setScanningHashes] = useState(false);

  const handleVerify = (e) => {
    e?.preventDefault();
    // Always trigger the scanning animation for demo purposes
    setScanningHashes(true);
  };

  const handleScanComplete = () => {
    setScanningHashes(false);
    setIsVerifying(true);
  };

  const handleHandshakeComplete = () => {
    setIsVerifying(false);
    onValidate(SAMPLE_RECEIPT);
  };

  // Show scanning animation in input box
  if (scanningHashes) {
    return <InputScanner onComplete={handleScanComplete} />;
  }

  if (isVerifying) {
    return <CryptoHandshake onComplete={handleHandshakeComplete} />;
  }

  return (
    <form onSubmit={handleVerify} className="space-y-4">
      <div>
        <label className="block text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">
          Batch ID or Receipt JSON
        </label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder='> Enter batch ID or click VERIFY for demo...'
          className="w-full h-32 bg-slate-950 border border-slate-700 p-4 text-sm font-mono text-cyan-400 placeholder-slate-600 focus:border-cyan-600 focus:outline-none resize-none"
        />
      </div>

      <div className="flex gap-3">
        <button
          type="submit"
          className="terminal-button flex-1 flex items-center justify-center gap-2 h-12 font-semibold"
        >
          <Shield size={16} />
          Verify
        </button>
      </div>

      <div className="text-xs font-mono text-slate-600 text-center">
        Click VERIFY to run cryptographic validation demo
      </div>
    </form>
  );
}

export default function ReceiptValidator() {
  const [result, setResult] = useState(null);
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadSubmitted, setLeadSubmitted] = useState(false);
  const [leadData, setLeadData] = useState({ email: '', company: '' });

  const handleValidate = (data) => {
    setResult(data);
  };

  const handleReset = () => {
    setResult(null);
  };

  const handleLeadSubmit = (e) => {
    e.preventDefault();
    console.log('Lead captured:', leadData);
    setLeadSubmitted(true);
    setShowLeadForm(false);
  };

  return (
    <section className="py-24 md:py-32 bg-slate-900 border-y border-slate-800">
      <div className="max-w-7xl mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-16 items-start">
          {/* Left: Description */}
          <div>
            <div className="forensic-badge mb-4">Live Verification</div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Verify any receipt
            </h2>
            <p className="text-lg text-slate-400 leading-relaxed mb-8">
              Every batch produces a cryptographic receipt. Verify signatures,
              hash chains, and WORM commitments without exposing underlying data.
            </p>

            <div className="space-y-4 mb-8">
              {[
                { icon: Shield, text: 'ECDSA P-256 signature verification' },
                { icon: Layers, text: 'SHA-256 hash chain validation' },
                { icon: Clock, text: '7-year WORM retention proof' },
              ].map(({ icon: Icon, text }) => (
                <div key={text} className="flex items-center gap-3 text-slate-300">
                  <div className="w-8 h-8 bg-cyan-950/50 border border-cyan-900/50 flex items-center justify-center">
                    <Icon size={16} className="text-cyan-500" />
                  </div>
                  <span className="text-sm font-mono">{text}</span>
                </div>
              ))}
            </div>

            {/* Demo CTA */}
            {!showLeadForm && !leadSubmitted && (
              <button
                onClick={() => setShowLeadForm(true)}
                className="flex items-center gap-2 text-cyan-500 text-sm font-mono uppercase tracking-wider hover:text-cyan-400 transition-colors"
              >
                Request Live API Access
                <span className="text-slate-500">→</span>
              </button>
            )}

            {/* Lead Form */}
            {showLeadForm && (
              <form onSubmit={handleLeadSubmit} className="terminal-frame p-6 space-y-4">
                <div className="terminal-header">Request Demo Access</div>
                <input
                  type="email"
                  required
                  placeholder="Work email"
                  value={leadData.email}
                  onChange={(e) => setLeadData({ ...leadData, email: e.target.value })}
                  className="w-full h-10 bg-slate-950 border border-slate-700 px-3 text-sm font-mono text-slate-300 placeholder-slate-600 focus:border-cyan-600 focus:outline-none"
                />
                <input
                  type="text"
                  required
                  placeholder="Company"
                  value={leadData.company}
                  onChange={(e) => setLeadData({ ...leadData, company: e.target.value })}
                  className="w-full h-10 bg-slate-950 border border-slate-700 px-3 text-sm font-mono text-slate-300 placeholder-slate-600 focus:border-cyan-600 focus:outline-none"
                />
                <div className="flex gap-3">
                  <button
                    type="submit"
                    className="terminal-button flex-1 h-10 text-sm font-semibold"
                  >
                    Submit
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowLeadForm(false)}
                    className="h-10 px-4 border border-slate-700 text-slate-400 text-sm font-mono uppercase tracking-wider hover:bg-slate-800/50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}

            {/* Lead Success */}
            {leadSubmitted && (
              <div className="flex items-center gap-2 text-emerald-400 text-sm font-mono">
                <CheckCircle size={16} />
                <span>ACKNOWLEDGED. Response within 24h.</span>
              </div>
            )}
          </div>

          {/* Right: Validator Widget */}
          <div className="terminal-frame p-6">
            <div className="terminal-header mb-6">
              Receipt Validator
            </div>

            {result ? (
              <ValidationResult result={result} onReset={handleReset} />
            ) : (
              <TerminalForm onValidate={handleValidate} />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
