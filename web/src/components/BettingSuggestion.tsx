import { useState } from "react";
import { ShieldCheck, Flame, Trophy, Medal, Layers, Flag, CircleDot, Target, Zap } from "lucide-react";

export interface BasicHorse {
  program_number: number;
  horse_name: string;
}

export interface SuggestionType {
  horses: BasicHorse[];
  reason: string;
  badge?: string;
}

export interface BettingSuggestionProps {
  stable: Record<string, SuggestionType | null>;
  aggressive: Record<string, SuggestionType | null>;
}

type BetKey = "win" | "place" | "quinella" | "exacta" | "quinellaPlace" | "trio" | "trifecta";
type FormatType = "single" | "unordered" | "ordered";

const BET_CONFIG: Record<BetKey, {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  format: FormatType;
  accent: string;       // tailwind color token for text/border
  glow: string;         // bg glow
  badge_bg: string;
}> = {
  win:          { title: "단승",   subtitle: "1착 단독",          icon: <Trophy size={14}/>,    format: "single",    accent: "text-indigo-400",  glow: "from-indigo-500/12 border-indigo-500/25",  badge_bg: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30" },
  place:        { title: "연승",   subtitle: "1~3착 내 적중",      icon: <Medal size={14}/>,     format: "single",    accent: "text-teal-400",    glow: "from-teal-500/12 border-teal-500/25",      badge_bg: "bg-teal-500/20 text-teal-300 border-teal-500/30" },
  quinella:     { title: "복승",   subtitle: "1·2착 순서 무관",    icon: <Layers size={14}/>,    format: "unordered", accent: "text-sky-400",     glow: "from-sky-500/12 border-sky-500/25",        badge_bg: "bg-sky-500/20 text-sky-300 border-sky-500/30" },
  exacta:       { title: "쌍승",   subtitle: "1→2착 순서 적중",   icon: <Flag size={14}/>,      format: "ordered",   accent: "text-purple-400",  glow: "from-purple-500/12 border-purple-500/25",  badge_bg: "bg-purple-500/20 text-purple-300 border-purple-500/30" },
  quinellaPlace:{ title: "복연승", subtitle: "1~3착 중 2마리",    icon: <CircleDot size={14}/>, format: "unordered", accent: "text-amber-400",   glow: "from-amber-500/12 border-amber-500/25",    badge_bg: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  trio:         { title: "삼복승", subtitle: "1·2·3착 순서 무관", icon: <Target size={14}/>,    format: "unordered", accent: "text-rose-400",    glow: "from-rose-500/12 border-rose-500/25",      badge_bg: "bg-rose-500/20 text-rose-300 border-rose-500/30" },
  trifecta:     { title: "삼쌍승", subtitle: "1→2→3착 순서 적중", icon: <Zap size={14}/>,       format: "ordered",   accent: "text-fuchsia-400", glow: "from-fuchsia-500/12 border-fuchsia-500/25",badge_bg: "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/30" },
};

const BET_ORDER: BetKey[] = ["win", "place", "quinella", "exacta", "quinellaPlace", "trio", "trifecta"];

function HorseChip({ horse, accent, format, index, total }: {
  horse: BasicHorse;
  accent: string;
  format: FormatType;
  index: number;
  total: number;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex flex-col items-center">
        {format === "ordered" && (
          <span className="text-[9px] text-slate-500 font-bold mb-0.5 leading-none">{index + 1}착</span>
        )}
        <div className={`w-9 h-9 rounded-xl font-black text-lg flex items-center justify-center bg-white/8 border border-white/10 text-slate-100`}>
          {horse.program_number}
        </div>
      </div>
      {index < total - 1 && (
        <span className={`text-xs font-bold ${accent} ${format === "ordered" ? "" : "opacity-60"}`}>
          {format === "ordered" ? "→" : "+"}
        </span>
      )}
    </div>
  );
}

function BetCard({ betKey, data }: { betKey: BetKey; data: SuggestionType | null }) {
  const cfg = BET_CONFIG[betKey];

  return (
    <div className={`relative bg-gradient-to-b ${cfg.glow} to-transparent border rounded-2xl p-3.5 flex flex-col gap-3 min-h-[148px]`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className={cfg.accent}>{cfg.icon}</span>
          <div>
            <span className={`font-black text-sm ${cfg.accent}`}>{cfg.title}</span>
            <span className="text-[10px] text-slate-500 ml-1.5 font-medium">{cfg.subtitle}</span>
          </div>
        </div>
        {data?.badge && (
          <span className={`text-[9px] font-bold px-2 py-0.5 rounded border ${cfg.badge_bg} whitespace-nowrap`}>
            {data.badge}
          </span>
        )}
      </div>

      {/* Horses */}
      <div className="flex-1 flex items-center">
        {!data || data.horses.length === 0 ? (
          <p className="text-xs text-slate-600 italic">데이터 부족</p>
        ) : cfg.format === "single" ? (
          <div className="flex items-end gap-2">
            <span className={`text-4xl font-black ${cfg.accent}`}>{data.horses[0].program_number}</span>
            <span className="text-base font-bold text-slate-200 pb-1 leading-tight">{data.horses[0].horse_name}</span>
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5 items-center">
            {data.horses.map((h, i) => (
              <HorseChip
                key={h.horse_name}
                horse={h}
                accent={cfg.accent}
                format={cfg.format}
                index={i}
                total={data.horses.length}
              />
            ))}
          </div>
        )}
      </div>

      {/* Reason */}
      {data && (
        <p className={`text-[10px] font-semibold ${cfg.accent} opacity-80 leading-tight`}>
          {data.reason}
        </p>
      )}
    </div>
  );
}

export function BettingSuggestion({ stable, aggressive }: BettingSuggestionProps) {
  const [activeTab, setActiveTab] = useState<"stable" | "aggressive">("stable");
  const current = activeTab === "stable" ? stable : aggressive;

  return (
    <div className="mb-6">
      {/* Section header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-bold text-slate-200 flex items-center gap-2">
          💡 AI 배팅 제안
          <span className="text-xs font-normal text-slate-500">7종 맞춤형</span>
        </h2>

        {/* Tab toggle */}
        <div className="flex items-center bg-slate-900 border border-white/10 rounded-xl p-1 gap-1">
          <button
            onClick={() => setActiveTab("stable")}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
              activeTab === "stable"
                ? "bg-indigo-500 text-white shadow-lg shadow-indigo-500/25"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <ShieldCheck size={13} />
            안정
          </button>
          <button
            onClick={() => setActiveTab("aggressive")}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
              activeTab === "aggressive"
                ? "bg-rose-500 text-white shadow-lg shadow-rose-500/25"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <Flame size={13} />
            공격
          </button>
        </div>
      </div>

      {/* Cards grid: 2 cols on mobile → 4 on md → natural wrap to 4+3 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
        {BET_ORDER.map((key) => (
          <BetCard key={key} betKey={key} data={(current as any)[key] ?? null} />
        ))}
      </div>
    </div>
  );
}
