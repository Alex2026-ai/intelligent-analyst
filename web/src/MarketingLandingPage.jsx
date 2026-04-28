'use client';

import React, { useState, useEffect } from 'react';
import { 
  Shield, Zap, Lock, Globe, CheckCircle2, 
  Scale, Key, X, BrainCircuit, FileText, 
  Fingerprint, Activity, ChevronRight, Layers, Cpu, Users,
  Terminal, History, ShieldAlert
} from "lucide-react";

/**
 * INTELLIGENT ANALYST — ENTERPRISE v8.2.2
 * ----------------------------------------------------------------------
 * FIXES: SVG noise removed, nav always visible, L0 Garbage layer added
 */

const SHELL_STYLE = { backgroundColor: "#050814", minHeight: '100vh', color: '#e2e8f0' };
const cn = (...classes) => classes.filter(Boolean).join(" ");

const Section = ({ id, className, children }) => (
  <section id={id} className={cn("py-24 relative border-t border-slate-900/50 scroll-mt-24", className)}>
    <div className="max-w-7xl mx-auto px-6 relative z-10">{children}</div>
  </section>
);

const Badge = ({ children, color = "cyan" }) => {
  const colors = {
    cyan: "border-cyan-500/20 bg-cyan-950/30 text-cyan-400",
    violet: "border-violet-500/20 bg-violet-950/30 text-violet-400",
    amber: "border-amber-500/20 bg-amber-950/30 text-amber-400"
  };
  return (
    <span className={cn("inline-flex items-center gap-2 px-3 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-widest", colors[color])}>
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      {children}
    </span>
  );
};

const Button = ({ children, variant = "primary", onClick, className }) => {
  const base = "h-12 px-8 rounded-none border text-sm font-medium transition-all flex items-center justify-center gap-2 uppercase tracking-widest cursor-pointer";
  const styles = {
    primary: "bg-cyan-500 text-slate-950 hover:bg-cyan-400 border-transparent shadow-[0_0_20px_rgba(34,211,238,0.1)]",
    secondary: "bg-transparent border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white",
  };
  return <button onClick={onClick} className={cn(base, styles[variant], className)}>{children}</button>;
};

// --- Page Components ---

const Navbar = () => (
  <nav className="fixed top-0 inset-x-0 z-50 border-b border-slate-700 bg-[#0B1220]/95 backdrop-blur-md">
    <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-gradient-to-br from-cyan-950 to-slate-900 border border-slate-700 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.15)]">
          <BrainCircuit className="text-cyan-500" size={20} />
        </div>
        <div className="leading-tight text-left">
          <div className="font-bold text-slate-100 tracking-tight text-lg uppercase">Intelligent Analyst</div>
          <div className="text-[10px] text-cyan-500/70 font-mono tracking-widest uppercase">Autonomous Integrity</div>
        </div>
      </div>
      <div className="flex items-center gap-8 text-[10px] font-mono text-slate-400 uppercase tracking-widest">
        <a href="#waterfall" className="hover:text-cyan-400 transition-colors cursor-pointer">Architecture</a>
        <a href="#forensic" className="hover:text-cyan-400 transition-colors cursor-pointer">Forensic Trace</a>
        <a href="#governance" className="hover:text-cyan-400 transition-colors cursor-pointer">Governance</a>
      </div>
      <Button variant="primary" className="h-9 px-6 text-xs">Customer Portal</Button>
    </div>
  </nav>
);

const Hero = () => (
  <section className="pt-48 pb-32 px-6 text-center">
    <Badge>v8.2.2 Hardened Architecture</Badge>
    <h1 className="mt-8 text-6xl md:text-8xl font-bold text-white tracking-tighter leading-[0.9] uppercase">
      AUTONOMOUS <br />
      <span className="text-transparent bg-clip-text bg-gradient-to-b from-slate-200 to-slate-600">DATA INTEGRITY</span>
    </h1>
    <p className="mt-8 text-xl text-slate-400 max-w-3xl mx-auto font-light leading-relaxed">
      Designed for auditability with deterministic controls that produce sanitized, traceable outputs for high-volume entity resolution.
    </p>
    <p className="mt-4 text-[11px] font-mono text-slate-500 uppercase tracking-widest italic">
      Assists with entity resolution; final decisions remain with your organization.
    </p>
    <div className="mt-12 flex justify-center gap-6">
      <Button variant="primary">Initialize Pilot Protocol</Button>
      <Button variant="secondary" onClick={() => alert('v8.2 Specification: Deterministic-first routing • Traceable audit outputs • Tenant-isolated operation.')}>
        Technical Spec
      </Button>
    </div>
  </section>
);

const Waterfall = () => (
  <Section id="waterfall" className="bg-[#020408]">
    <div className="mb-16 text-left">
      <Badge color="violet">The Architecture</Badge>
      <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">The 5-Layer Resolution Waterfall</h2>
      <p className="text-slate-400 max-w-3xl text-lg font-light leading-relaxed">
        Our "AI-Last" strategy starts with garbage detection, then prioritizes deterministic controls before escalating to assisted disambiguation.
      </p>
    </div>
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 text-left">
      {[
        { title: "Layer 0: Data Quarantine", rate: "~5%", icon: ShieldAlert, desc: "Garbage detection filters corrupted data, nulls, and file artifacts." },
        { title: "Layer 1: Deterministic", rate: "84.5%", icon: Shield, desc: "Exact match and normalized cache." },
        { title: "Layer 2: Semantic Vector", rate: "8.4%", icon: Cpu, desc: "Similarity handling typos and variants." },
        { title: "Layer 3: LLM Judge", rate: "2.1%", icon: BrainCircuit, desc: "LLM-assisted disambiguation." },
        { title: "Layer 4: Quality Gate", rate: "5.0%", icon: Users, desc: "Final validation queue for outliers." }
      ].map((layer, idx) => (
        <div key={idx} className="bg-[#0B0F19] border border-slate-800 p-8 hover:border-violet-500/50 transition-colors group">
          <layer.icon className="text-cyan-500 mb-6 group-hover:scale-110 transition-transform" size={28} />
          <div className="text-3xl text-white font-bold mb-2 font-mono tracking-tighter">{layer.rate}</div>
          <h4 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-4 border-b border-slate-800 pb-2">{layer.title}</h4>
          <p className="text-xs text-slate-500 leading-relaxed font-light">{layer.desc}</p>
        </div>
      ))}
    </div>
  </Section>
);

const ForensicSection = () => (
  <Section id="forensic">
    <div className="grid lg:grid-cols-2 gap-16 items-center text-left">
      <div>
        <Badge>Forensic Trace</Badge>
        <h2 className="mt-6 text-4xl font-bold text-white mb-6 uppercase tracking-tight leading-tight">Immutable Audit Outputs</h2>
        <p className="text-slate-400 text-lg leading-relaxed mb-8 font-light leading-relaxed">
          Cryptographically verifiable <strong>chain-of-custody</strong> signals per record, designed to support regulated audit workflows.
        </p>
        <div className="space-y-4">
          <div className="border-l-2 border-cyan-500/30 pl-6 py-2 bg-slate-900/20">
            <div className="text-cyan-400 text-[10px] font-mono uppercase mb-1 text-left">Evidence Generation</div>
            <div className="text-slate-400 text-sm font-light text-left">Audit-ready evidence pack generation stored in tenant-isolated secure nodes.</div>
          </div>
        </div>
      </div>
      <div className="bg-[#0B0F19] border border-slate-800 p-8 font-mono text-[11px] text-slate-500 shadow-2xl relative">
        <div className="flex justify-between items-center border-b border-slate-800 pb-4 mb-4">
          <Fingerprint className="text-cyan-500 animate-pulse" size={20} />
          <span className="text-cyan-500/50 uppercase tracking-widest text-[9px]">Trace_Mode: ACTIVE</span>
        </div>
        <div className="space-y-3">
          <div className="flex gap-4"><span className="text-slate-700 font-bold">[16:44:01]</span> <span className="text-slate-300">HQ_LOC: MIAMI_FL_USA</span></div>
          <div className="flex gap-4"><span className="text-slate-700 font-bold">[16:44:02]</span> <span className="text-emerald-500">DETERMINISTIC_CHECK: PASSED</span></div>
          <div className="flex gap-4"><span className="text-slate-700 font-bold">[16:44:03]</span> <span className="text-cyan-500 font-bold">TRACE_ID: MIAMI_82_2026</span></div>
        </div>
      </div>
    </div>
  </Section>
);

const Governance = () => (
  <Section id="governance">
    <div className="mb-14 text-left">
      <Badge color="amber">Trust Signal</Badge>
      <h2 className="text-3xl font-bold text-white mt-6 mb-4 uppercase tracking-tight">Governance & Oversight</h2>
    </div>
    
    <div className="grid lg:grid-cols-2 gap-8 text-left mb-12">
      <div className="p-10 bg-[#0B0F19] border border-slate-800">
        <div className="text-[10px] font-mono text-cyan-500 mb-3 uppercase tracking-widest font-bold">Architecture & Execution</div>
        <h3 className="text-2xl font-bold text-white mb-6 tracking-tight">Alejandro Garcia Escobedo</h3>
        <p className="text-slate-400 text-sm leading-relaxed font-light">
          Visionary behind the deterministic engine, focusing on operational scrutiny for enterprise data environments.
        </p>
      </div>
      <div className="p-10 bg-[#0B0F19] border border-slate-800">
        <div className="text-[10px] font-mono text-violet-500 mb-3 uppercase tracking-widest font-bold">Global Strategy</div>
        <h3 className="text-2xl font-bold text-white mb-6 tracking-tight">Dominic Suszek</h3>
        <p className="text-slate-400 text-sm leading-relaxed font-light">
          Veteran of regulated enterprise workflows ensuring technical strategy aligns with global market requirements.
        </p>
      </div>
    </div>

    {/* Functional Governance Points */}
    <div className="grid md:grid-cols-3 gap-8 pt-8 border-t border-slate-800/50">
      <div className="flex gap-4">
        <History className="text-cyan-500 shrink-0" size={20} />
        <div className="text-[11px] font-mono text-slate-300 uppercase tracking-wider leading-relaxed">
          Immutable audit trail + evidence packs
        </div>
      </div>
      <div className="flex gap-4">
        <ShieldAlert className="text-cyan-500 shrink-0" size={20} />
        <div className="text-[11px] font-mono text-slate-300 uppercase tracking-wider leading-relaxed">
          Config drift logging
        </div>
      </div>
      <div className="flex gap-4">
        <Terminal className="text-cyan-500 shrink-0" size={20} />
        <div className="text-[11px] font-mono text-slate-300 uppercase tracking-wider leading-relaxed">
          Break-glass access with full logging
        </div>
      </div>
    </div>
  </Section>
);

const Footer = () => (
  <footer className="bg-[#02040a] border-t border-slate-900 py-24 px-6 text-left">
    <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-start gap-16">
      <div className="max-w-md">
        <div className="flex items-center gap-3 mb-8">
          <BrainCircuit className="text-cyan-500" size={32} />
          <span className="font-bold text-white uppercase tracking-tighter text-2xl">Intelligent Analyst</span>
        </div>
        <p className="text-slate-600 text-[11px] leading-relaxed uppercase tracking-widest font-mono border-l border-slate-800 pl-6">
          Miami HQ · Florida 33131 <br/>
          The Standard for Autonomous Data Integrity. <br/>
          IP Strategy in Progress.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-20 text-[10px] uppercase tracking-widest text-slate-500 font-mono">
        <div className="space-y-6">
          <span className="text-white border-b border-slate-800 pb-3 block font-bold">US Operations</span>
          <a href="#" className="hover:text-white block transition-colors">Privacy Policy</a>
          <a href="#" className="hover:text-white block transition-colors">Terms of Service</a>
        </div>
        <div className="space-y-6">
          <span className="text-white border-b border-slate-800 pb-3 block font-bold">Global</span>
          <a href="#" className="hover:text-white block transition-colors">GDPR Commit</a>
          <a href="#" className="hover:text-white block transition-colors">Audit Spec</a>
        </div>
      </div>
    </div>
  </footer>
);

export default function App() {
  const [isClient, setIsClient] = useState(false);
  useEffect(() => setIsClient(true), []);
  if (!isClient) return <div className="bg-[#050814] min-h-screen" />;

  return (
    <div style={SHELL_STYLE} className="font-sans antialiased selection:bg-cyan-900 selection:text-white">
      <Navbar />
      <Hero />
      <Waterfall />
      <ForensicSection />
      <Governance />
      <Footer />
    </div>
  );
}
