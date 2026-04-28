import { useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';

export default function BatchHashDisplay({ batch, computeBatchHash, copyToClipboard, copiedId }) {
  const [batchHash, setBatchHash] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    computeBatchHash(batch).then(hash => {
      if (mounted) {
        setBatchHash(hash);
        setLoading(false);
      }
    });
    return () => { mounted = false; };
  }, [batch, computeBatchHash]);

  if (loading) {
    return <span className="text-[10px] text-gray-200 italic">Computing...</span>;
  }

  if (!batchHash) {
    return <span className="text-[10px] text-gray-200 italic">Unable to compute</span>;
  }

  return (
    <div className="flex items-center gap-2">
      <code className="text-[9px] text-emerald-400 bg-[#1e293b]/50 px-1.5 py-0.5 rounded flex-1 truncate font-mono">
        {batchHash.slice(0, 16)}...
      </code>
      <button
        onClick={() => copyToClipboard(batchHash)}
        className="p-1 hover:bg-[#334155] rounded transition-colors"
        title="Copy full hash"
      >
        {copiedId === batchHash ? (
          <Check size={10} className="text-emerald-400" />
        ) : (
          <Copy size={10} className="text-gray-200" />
        )}
      </button>
    </div>
  );
}
