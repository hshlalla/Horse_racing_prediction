import { X } from "lucide-react";
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from "recharts";

interface HorseDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  horseName: string;
  features: {
    win_probability: number;
    place_probability: number;
    distance_win_rate: number;
    jockey_horse_win_rate: number;
    horse_win_rate: number;
    past_avg_start_rank?: number;
    past_avg_mid_rank?: number;
    past_avg_finish_rank?: number;
    past_avg_g3f_time?: number;
    carry_weight_kg?: number;
  } | null;
}

function StatRow({ label, value, unit = "%", color = "text-slate-200" }: { label: string; value: number; unit?: string; color?: string }) {
  const pct = Math.round(value * (unit === "%" ? 100 : 1));
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <div className="flex items-center gap-2">
        <div className="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
        </div>
        <span className={`text-sm font-bold tabular-nums ${color}`}>{pct}{unit}</span>
      </div>
    </div>
  );
}

export function HorseDetailDrawer({ isOpen, onClose, horseName, features }: HorseDetailDrawerProps) {
  if (!isOpen || !features) return null;

  const radarData = [
    { subject: '단승 예측', A: Math.round(features.win_probability * 100), fullMark: 100 },
    { subject: '연승 예측', A: Math.round(features.place_probability * 100), fullMark: 100 },
    { subject: '거리 승률', A: Math.round((features.distance_win_rate || 0) * 100), fullMark: 100 },
    { subject: '기수 궁합', A: Math.round((features.jockey_horse_win_rate || 0) * 100), fullMark: 100 },
    { subject: '마필 승률', A: Math.round((features.horse_win_rate || 0) * 100), fullMark: 100 },
  ];

  return (
    <>
      <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-40" onClick={onClose} />
      <div className="fixed bottom-0 left-0 right-0 max-w-7xl mx-auto z-50 bg-slate-900 border-t border-white/10 rounded-t-3xl shadow-[0_-10px_40px_rgba(0,0,0,0.6)]">
        <div className="p-5 pb-28">
          {/* Handle */}
          <div className="w-10 h-1 bg-white/20 rounded-full mx-auto mb-5" />

          <div className="flex justify-between items-center mb-4">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🐎</span>
              <h2 className="text-xl font-black bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
                {horseName}
              </h2>
            </div>
            <button onClick={onClose} className="p-2 rounded-full bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors">
              <X size={20} />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Radar chart */}
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                  <PolarGrid stroke="#334155" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 11, fontWeight: 'bold' }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                  <Radar name={horseName} dataKey="A" stroke="#818cf8" fill="#6366f1" fillOpacity={0.45} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Stat rows */}
            <div className="flex flex-col justify-center">
              <p className="text-xs uppercase tracking-widest font-bold text-slate-500 mb-3">상세 지표</p>
              <StatRow label="🏆 AI 단승 확률" value={features.win_probability} color="text-indigo-400" />
              <StatRow label="🥈 AI 연승 확률" value={features.place_probability} color="text-teal-400" />
              <StatRow label="📏 거리별 승률" value={features.distance_win_rate || 0} color="text-emerald-400" />
              <StatRow label="🤝 기수 궁합 승률" value={features.jockey_horse_win_rate || 0} color="text-amber-400" />
              <StatRow label="🐎 마필 전체 승률" value={features.horse_win_rate || 0} color="text-slate-300" />
              
              <div className="mt-4 pt-4 border-t border-white/5 flex flex-wrap gap-2 text-[10px] uppercase font-bold tracking-wider text-slate-400">
                {features.past_avg_start_rank !== undefined && features.past_avg_mid_rank !== undefined && (
                  (() => {
                    const s = features.past_avg_start_rank;
                    const m = features.past_avg_mid_rank;
                    let style = { label: "추입 (Closer)", icon: "🚀", color: "text-purple-400 border-purple-400/30 bg-purple-400/10" };
                    if (s <= 3.5 && m <= 3.5) style = { label: "선행 (Front)", icon: "🏃‍♂️💨", color: "text-red-400 border-red-400/30 bg-red-400/10" };
                    else if (s > 3.5 && m <= 5.0) style = { label: "선입 (Stalker)", icon: "🐎", color: "text-blue-400 border-blue-400/30 bg-blue-400/10" };
                    
                    return (
                      <span className={`px-2 py-1 rounded border ${style.color}`}>
                        {style.icon} {style.label}
                      </span>
                    );
                  })()
                )}
                {features.carry_weight_kg !== undefined && features.carry_weight_kg > 0 && (
                  <span className="bg-slate-800 text-slate-300 px-2 py-1 rounded border border-white/5">
                    부중 {features.carry_weight_kg}kg
                  </span>
                )}
                {features.past_avg_g3f_time !== undefined && (
                  <span className="bg-slate-800 px-2 py-1 rounded border border-white/5">
                    ⚡ G3F: {features.past_avg_g3f_time.toFixed(1)}s
                  </span>
                )}
                {features.past_avg_start_rank !== undefined && (
                  <span className="bg-slate-800 px-2 py-1 rounded border border-white/5">
                    🏁 출발순위: {features.past_avg_start_rank.toFixed(1)}
                  </span>
                )}
                {features.past_avg_finish_rank !== undefined && (
                  <span className="bg-slate-800 px-2 py-1 rounded border border-white/5">
                    🏆 도착순위: {features.past_avg_finish_rank.toFixed(1)}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
