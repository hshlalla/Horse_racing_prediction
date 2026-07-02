import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  Filter,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";

const trackNameMap: Record<string, string> = { SEOUL: "서울", BUSAN: "부산", JEJU: "제주" };

const EDGE_PRESETS = [
  { label: "전체", value: 0.0 },
  { label: "에지 2%+", value: 0.02 },
  { label: "에지 5%+", value: 0.05 },
  { label: "에지 10%+", value: 0.1 },
];

function EdgeBadge({ edge }: { edge: number }) {
  const pct = (edge * 100).toFixed(1);
  if (edge >= 0.1)
    return (
      <span className="text-[11px] font-black px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
        +{pct}%
      </span>
    );
  if (edge >= 0.05)
    return (
      <span className="text-[11px] font-black px-2 py-0.5 rounded-full bg-teal-500/20 text-teal-400 border border-teal-500/30">
        +{pct}%
      </span>
    );
  if (edge >= 0.02)
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-400 border border-sky-500/30">
        +{pct}%
      </span>
    );
  if (edge >= 0)
    return (
      <span className="text-[11px] px-2 py-0.5 rounded-full bg-white/5 text-slate-500 border border-white/5">
        +{pct}%
      </span>
    );
  return (
    <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20">
      {pct}%
    </span>
  );
}

function RaceCard({ race, defaultOpen }: { race: any; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const top = race.picks?.[0];
  const qualified = race.ev_qualified;

  return (
    <div
      className={`rounded-2xl border transition-all ${
        qualified
          ? "bg-emerald-500/5 border-emerald-500/20 shadow-[0_0_12px_rgba(16,185,129,0.06)]"
          : "bg-white/[0.03] border-white/8"
      }`}
    >
      {/* Header row */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 p-4 text-left"
      >
        {qualified ? (
          <CheckCircle2 size={18} className="text-emerald-400 shrink-0" />
        ) : (
          <AlertCircle size={18} className="text-slate-600 shrink-0" />
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-xs font-bold px-2 py-0.5 rounded border ${
                race.track === "SEOUL"
                  ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
                  : "text-slate-400 bg-slate-800 border-white/10"
              }`}
            >
              {race.track === "SEOUL" ? "✓ " : ""}
              {trackNameMap[race.track] || race.track}
            </span>
            {qualified && race.track !== "SEOUL" && (
              <span className="text-[10px] text-amber-500/80 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">
                백테스트 손실 트랙
              </span>
            )}
            <span className="font-semibold text-slate-100 text-sm">
              제{race.race_number}경주
            </span>
            {race.distance_m && (
              <span className="text-[11px] text-slate-500">{race.distance_m}m</span>
            )}
            {race.post_time && (
              <span className="text-[11px] text-slate-600">
                {race.post_time.slice(11, 16)}
              </span>
            )}
          </div>
          {top && (
            <p className="text-xs text-slate-400 mt-0.5">
              추천:{" "}
              <span className="font-semibold text-slate-200">
                {top.program_number}번 {top.horse_name}
              </span>{" "}
              · 배당{" "}
              <span className="text-amber-300 font-bold">{top.morning_odds}배</span>
            </p>
          )}
        </div>

        {top && <EdgeBadge edge={top.edge_score} />}
        <span className="text-slate-600 ml-1">
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>

      {/* Expanded detail */}
      {open && race.picks?.length > 0 && (
        <div className="px-4 pb-4 space-y-2">
          <div className="grid grid-cols-7 text-[10px] uppercase tracking-widest text-slate-600 px-2 pb-1 border-b border-white/5">
            <span className="col-span-2">말</span>
            <span className="text-right">AI확률</span>
            <span className="text-right">시장확률</span>
            <span className="text-right">에지</span>
            <span className="text-right">배당</span>
            <span className="text-right">역배</span>
          </div>
          {race.picks.map((pick: any, idx: number) => (
            <div
              key={pick.horse_id}
              className={`grid grid-cols-7 items-center text-sm py-1.5 px-2 rounded-xl ${
                idx === 0
                  ? "bg-white/5 border border-white/10"
                  : "text-slate-500"
              }`}
            >
              <div className="col-span-2 flex items-center gap-2">
                <span
                  className={`text-[11px] font-bold w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${
                    idx === 0
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-white/5 text-slate-500"
                  }`}
                >
                  {pick.program_number}
                </span>
                <span
                  className={`truncate text-xs ${idx === 0 ? "text-slate-100 font-semibold" : ""}`}
                >
                  {pick.horse_name}
                </span>
              </div>
              <span className="text-right text-xs font-mono">
                {(pick.win_prob * 100).toFixed(1)}%
              </span>
              <span className="text-right text-xs font-mono text-slate-500">
                {(pick.market_prob * 100).toFixed(1)}%
              </span>
              <span className="text-right">
                <EdgeBadge edge={pick.edge_score} />
              </span>
              <span
                className={`text-right text-xs font-bold ${
                  idx === 0 ? "text-amber-300" : "text-slate-600"
                }`}
              >
                {pick.morning_odds > 0 ? `${pick.morning_odds}x` : "-"}
              </span>
              {/* 역배 확률: 배당 5배 이상 말에게만 의미 있음 */}
              <span className="text-right">
                {pick.upset_probability > 0 && pick.morning_odds >= 5.0 ? (
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                    pick.upset_probability >= 0.05
                      ? "bg-fuchsia-500/20 text-fuchsia-400 border border-fuchsia-500/30"
                      : "text-slate-600"
                  }`}>
                    {(pick.upset_probability * 100).toFixed(1)}%
                  </span>
                ) : (
                  <span className="text-slate-700 text-[10px]">-</span>
                )}
              </span>
            </div>
          ))}

          {/* 추천 이유 */}
          {race.picks[0]?.top_reasons?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-1 pt-2 border-t border-white/5">
              {race.picks[0].top_reasons.map((r: any) => (
                <span
                  key={r.feature}
                  className={`text-[10px] px-2 py-0.5 rounded-full border ${
                    r.direction > 0
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                  }`}
                >
                  {r.direction > 0 ? "▲" : "▼"} {r.label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function InvestmentPage() {
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  // 기본값 5% — 백테스트상 서울 복승/단승이 에지 5%+에서 수익 전환되는 스윗스팟
  const [minEdge, setMinEdge] = useState(0.05);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["today-bets", date, minEdge],
    queryFn: async () => {
      const res = await fetch(
        `/api/reports/today-bets?date=${date}&min_edge=${minEdge}`
      );
      if (!res.ok) throw new Error("fetch failed");
      return res.json();
    },
  });

  // 백테스트상 서울만 수익 트랙 → 추천 목록에서 서울을 앞으로 정렬
  const seoulFirst = (a: any, b: any) =>
    (a.track === "SEOUL" ? 0 : 1) - (b.track === "SEOUL" ? 0 : 1);
  const qualified = (data?.races?.filter((r: any) => r.ev_qualified) ?? []).slice().sort(seoulFirst);
  const others = (data?.races?.filter((r: any) => !r.ev_qualified) ?? []).slice().sort(seoulFirst);

  return (
    <div className="max-w-3xl mx-auto min-h-screen bg-slate-950 text-slate-200 pb-28">
      {/* Header */}
      <header className="p-4 border-b border-white/10 sticky top-0 bg-slate-950/90 backdrop-blur-md z-10 shadow-lg shadow-black/20">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent flex items-center gap-2">
            <TrendingUp size={20} className="text-emerald-400" />
            투자 추천
          </h1>
          <div className="ml-auto flex items-center gap-2">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500/50 text-slate-300 [color-scheme:dark]"
            />
          </div>
        </div>

        {/* Edge filter */}
        <div className="flex items-center gap-2 mt-3">
          <Filter size={13} className="text-slate-500" />
          <span className="text-[11px] text-slate-500 mr-1">에지 필터</span>
          {EDGE_PRESETS.map((p) => (
            <button
              key={p.value}
              onClick={() => setMinEdge(p.value)}
              className={`text-[11px] px-2.5 py-1 rounded-full border font-semibold transition-colors ${
                minEdge === p.value
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                  : "bg-white/5 text-slate-500 border-white/10 hover:border-white/20"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </header>

      <div className="p-4 space-y-5">
        {/* Summary */}
        {data && (
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white/5 border border-white/10 rounded-2xl p-4 text-center">
              <p className="text-2xl font-black text-slate-100">{data.total_races}</p>
              <p className="text-[10px] text-slate-500 mt-0.5 uppercase tracking-wider">전체 경주</p>
            </div>
            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-2xl p-4 text-center">
              <p className="text-2xl font-black text-emerald-400">{data.qualified_races}</p>
              <p className="text-[10px] text-emerald-600 mt-0.5 uppercase tracking-wider">추천 경주</p>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-2xl p-4 text-center">
              <p className="text-2xl font-black text-amber-300">
                {data.qualified_races > 0
                  ? `${(data.qualified_races / data.total_races * 100).toFixed(0)}%`
                  : "0%"}
              </p>
              <p className="text-[10px] text-slate-500 mt-0.5 uppercase tracking-wider">베팅 선택률</p>
            </div>
          </div>
        )}

        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 bg-white/5 rounded-2xl border border-white/5 animate-pulse" />
            ))}
          </div>
        )}

        {isError && (
          <div className="flex flex-col items-center gap-3 py-16 text-sm text-rose-400">
            <p>데이터를 불러올 수 없습니다.</p>
            <button
              onClick={() => refetch()}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-slate-300 hover:bg-white/10 transition-colors text-xs font-semibold"
            >
              <RefreshCw size={13} />
              다시 시도
            </button>
          </div>
        )}

        {!isLoading && !isError && data?.total_races === 0 && (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
            <span className="text-4xl">📊</span>
            <p className="text-slate-400">해당 날짜에 경주 데이터가 없습니다.</p>
          </div>
        )}

        {/* Qualified races */}
        {qualified.length > 0 && (
          <div>
            <h2 className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-3 flex items-center gap-2">
              <CheckCircle2 size={14} /> 추천 베팅 ({qualified.length}경주)
            </h2>
            <div className="space-y-2.5">
              {qualified.map((race: any) => (
                <RaceCard key={race.race_id} race={race} defaultOpen />
              ))}
            </div>
          </div>
        )}

        {/* Others */}
        {others.length > 0 && (
          <div>
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
              <AlertCircle size={14} /> 에지 부족 ({others.length}경주)
            </h2>
            <div className="space-y-2">
              {others.map((race: any) => (
                <RaceCard key={race.race_id} race={race} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
