export const NavItem = ({ active, onClick, label, icon: Icon }) => (
  <button
    onClick={onClick}
    type="button"
    className={`flex items-center gap-2 px-4 py-2 text-[10px] font-mono uppercase tracking-widest transition-colors ${
      active ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-gray-200 hover:text-[#f1f5f9] border-b-2 border-transparent'
    }`}
  >
    <Icon size={14} />
    {label}
  </button>
);

export const Panel = ({ title, icon: Icon, children }) => (
  <div className="bg-[#0b1220] border border-[#1e293b] p-8">
    <div className="flex items-center justify-between mb-8">
      <h3 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest flex items-center gap-2 border-b border-[#1e293b] pb-2">
        {Icon ? <Icon size={14} className="text-cyan-500" /> : null}
        {title}
      </h3>
    </div>
    {children}
  </div>
);

export const MetricCard = ({ label, value, subtext, icon: Icon }) => (
  <div className="bg-[#0b1220] border border-[#1e293b] p-8 hover:border-cyan-500/50 transition-colors group">
    {Icon ? <Icon className="text-cyan-500 mb-6 group-hover:scale-110 transition-transform" size={28} /> : null}
    <div className="text-3xl text-[#f1f5f9] font-bold mb-2 font-mono tracking-tighter">{value}</div>
    <h4 className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-4 border-b border-[#1e293b] pb-2">{label}</h4>
    <p className="text-xs text-[#cbd5e1] leading-relaxed font-semibold">{subtext}</p>
  </div>
);

export const Badge = ({ children, color = "cyan" }) => {
  const colors = {
    cyan: "border-cyan-500/20 bg-cyan-950/30 text-cyan-400",
    violet: "border-violet-500/20 bg-violet-950/30 text-violet-400",
    amber: "border-amber-500/20 bg-amber-950/30 text-amber-400",
  };
  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-widest ${colors[color]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      {children}
    </span>
  );
};
