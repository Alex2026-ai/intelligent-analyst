import { useState } from 'react';
import { Sliders, Terminal } from 'lucide-react';
import { Panel } from './VisualPrimitives';

export default function AdminPanel() {
  const [vectorThreshold, setVectorThreshold] = useState(0.55);
  const [llmConfidence, setLlmConfidence] = useState(0.70);

  return (
    <div className="space-y-6 animate-in fade-in">
       <div className="flex items-center justify-between border-b border-[#1e293b] pb-4 mb-8">
           <h2 className="text-xl text-[#f1f5f9] font-mono uppercase font-bold">System Configuration</h2>
           <span className="text-emerald-400 text-xs font-mono border border-emerald-500/30 px-2 py-1 bg-emerald-500/10 flex items-center gap-2">
             <Sliders size={12} /> SIMULATION MODE
           </span>
       </div>

       <div className="grid md:grid-cols-2 gap-8">
         <Panel title="Sensitivity Controls" icon={Terminal}>
            <div className="space-y-6">
                <div>
                    <div className="flex justify-between mb-2">
                        <label className="text-gray-200 text-xs font-mono uppercase">L2 Vector Strictness</label>
                        <span className="text-cyan-400 font-mono">{vectorThreshold}</span>
                    </div>
                    <input
                        type="range" min="0.1" max="0.9" step="0.05"
                        value={vectorThreshold}
                        onChange={(e) => setVectorThreshold(parseFloat(e.target.value))}
                        className="w-full accent-cyan-500"
                    />
                </div>
                <div>
                    <div className="flex justify-between mb-2">
                        <label className="text-gray-200 text-xs font-mono uppercase">L3 LLM Confidence</label>
                        <span className="text-amber-400 font-mono">{llmConfidence}</span>
                    </div>
                    <input
                        type="range" min="0.5" max="0.99" step="0.01"
                        value={llmConfidence}
                        onChange={(e) => setLlmConfidence(parseFloat(e.target.value))}
                        className="w-full accent-amber-500"
                    />
                </div>
            </div>
            <p className="text-[10px] text-gray-200 mt-6 border-t border-[#1e293b] pt-4">
                * Note: In this MVP, these controls simulate configuration changes. Production environments enforce these via backend environment variables.
            </p>
         </Panel>
       </div>
    </div>
  );
}
