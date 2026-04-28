import { Fragment } from 'react';
import { ChevronRight } from 'lucide-react';

function commandMatchesQuery(command, query) {
  return command.keys.some(key => key.includes(query)) || command.label.toLowerCase().includes(query);
}

export default function CommandPalette({ query, setQuery, commands, onClose }) {
  const normalizedQuery = query.toLowerCase().trim();
  const filtered = normalizedQuery ? commands.filter(command => commandMatchesQuery(command, normalizedQuery)) : commands;
  let lastGroup = '';

  const runCommand = (command) => {
    command.action();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[20vh]" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[#0b1220] border border-[#1e293b] rounded-lg w-full max-w-lg mx-4 shadow-2xl animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#1e293b]">
          <span className="text-gray-200 text-xs font-mono">&gt;</span>
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command..."
            className="flex-1 bg-transparent text-[#f1f5f9] text-sm font-mono outline-none placeholder-gray-200"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const match = commands.find(command => commandMatchesQuery(command, normalizedQuery));
                if (match) runCommand(match);
              }
            }}
          />
          <kbd className="text-[9px] text-gray-200 font-mono bg-[#1e293b] px-1.5 py-0.5 rounded">ESC</kbd>
        </div>
        <div className="max-h-[360px] overflow-y-auto">
          {filtered.map((command) => {
            const showGroup = command.group !== lastGroup;
            lastGroup = command.group;
            return (
              <Fragment key={command.label}>
                {showGroup && (
                  <div className="px-4 pt-3 pb-1 text-[9px] font-mono text-gray-200 uppercase tracking-widest">{command.group}</div>
                )}
                <button
                  className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-[#1e293b]/50 transition-colors text-left"
                  onClick={() => runCommand(command)}
                >
                  <div>
                    <span className="text-[#f1f5f9] text-sm font-mono">{command.label}</span>
                    <span className="text-gray-200 text-xs ml-3">{command.desc}</span>
                  </div>
                  <ChevronRight size={14} className="text-gray-200" />
                </button>
              </Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}
