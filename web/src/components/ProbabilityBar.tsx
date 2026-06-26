export function ProbabilityBar({ probability, color = "from-indigo-500 to-purple-500" }: { probability: number, color?: string }) {
  const percent = Math.round(probability * 100);
  return (
    <div className="flex items-center gap-3 w-full">
      <div className="flex-grow bg-slate-800/50 rounded-full h-3 border border-white/5 overflow-hidden">
        <div 
          className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(99,102,241,0.4)]`} 
          style={{ width: `${percent}%` }}
        ></div>
      </div>
      <span className="text-sm font-bold text-slate-300 w-9 text-right tabular-nums tracking-tight">{percent}%</span>
    </div>
  );
}
