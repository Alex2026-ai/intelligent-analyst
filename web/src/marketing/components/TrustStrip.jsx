import React from 'react';
import { Shield, Lock, FileCheck } from 'lucide-react';

export default function TrustStrip() {
  const items = [
    { icon: Shield, text: 'SOC 2-Aligned Design' },
    { icon: Lock, text: 'WORM Retention' },
    { icon: FileCheck, text: 'Cryptographic Audit Trail' },
  ];

  return (
    <div className="bg-slate-900 border-y border-slate-800 py-4">
      <div className="max-w-6xl mx-auto px-4 flex flex-wrap justify-center gap-8">
        {items.map((item, idx) => (
          <div key={idx} className="flex items-center gap-2 text-slate-400 text-sm">
            <item.icon size={16} className="text-cyan-500" />
            <span>{item.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
