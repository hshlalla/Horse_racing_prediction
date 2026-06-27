import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Activity, ArrowUpRight, ArrowDownRight, CheckCircle, XCircle } from "lucide-react";

const trackNameMap: Record<string, string> = { SEOUL: "서울", BUSAN: "부산", JEJU: "제주" };

export default function ROIReportPage() {
  const navigate = useNavigate();
  const [date, setDate] = useState(() => {
    const d = new Date();
    return d.toISOString().split("T")[0];
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["backtest", date],
    queryFn: async () => {
      const res = await fetch(`/api/reports/backtest?date=${date}`);
      if (!res.ok) throw new Error("Failed to fetch backtest");
      return res.json();
    },
    enabled: !!date,
  });

  const formatMoney = (val: number) => new Intl.NumberFormat("ko-KR").format(val) + "원";
  const calcROI = (ret: number, inv: number) => (inv > 0 ? (((ret - inv) / inv) * 100).toFixed(1) : "0.0");

  return (
    <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 text-slate-200 p-4 md:p-8">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <button onClick={() => navigate(-1)} className="p-2 rounded-full hover:bg-white/10 transition-colors text-slate-400 hover:text-white">
            <ArrowLeft size={20} />
          </button>
          <h1 className="text-2xl md:text-3xl font-extrabold bg-gradient-to-r from-emerald-400 via-teal-400 to-indigo-400 bg-clip-text text-transparent flex items-center gap-3">
            <Activity className="text-emerald-400" size={28} />
            모의투자 리포트
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/50 text-slate-300 color-scheme-dark"
          />
          <p className="text-sm text-slate-400">
            {date} 경기에 AI가 베팅했다면?
          </p>
        </div>
      </header>

      {isLoading && <div className="text-center text-slate-400 mt-10">분석 중...</div>}
      {error && <div className="text-center text-red-400 mt-10">데이터를 불러올 수 없습니다</div>}

      {data && data.total_races === 0 && (
        <div className="text-center text-slate-500 mt-20">
          <p className="text-lg">해당 날짜에 경주 데이터가 없습니다.</p>
          <p className="text-sm mt-2">날짜를 변경해주세요.</p>
        </div>
      )}

      {data && data.total_races > 0 && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            {[
              { key: "win", label: "단승식 (1착 맞추기)", color: "indigo" },
              { key: "quinella", label: "복승식 (1,2착 맞추기)", color: "purple" },
              { key: "trio", label: "삼복승식 (1,2,3착 맞추기)", color: "pink" },
            ].map(({ key, label, color }) => {
              const s = data.totals[key];
              const roi = parseFloat(calcROI(s.return, s.investment));
              const isPositive = roi >= 0;
              return (
                <div key={key} className="relative overflow-hidden bg-white/5 border border-white/10 rounded-2xl p-5 shadow-xl backdrop-blur-md">
                  <div className={`absolute top-0 left-0 w-full h-1 bg-${color}-500`}></div>
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-sm font-bold text-slate-300">{label}</h3>
                    <div className={`flex items-center gap-1 text-sm font-bold px-2 py-0.5 rounded-md ${isPositive ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"}`}>
                      {isPositive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {isPositive ? "+" : ""}{roi}%
                    </div>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-400">투자금</span>
                      <span className="text-slate-200">{formatMoney(s.investment)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">회수금</span>
                      <span className={isPositive ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>{formatMoney(s.return)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">적중</span>
                      <span className="text-indigo-300">{s.hits} / {data.total_races}경기</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Per-race cards */}
          <h2 className="text-lg font-bold text-slate-100 mb-4">📋 경주별 모의투자 결과</h2>
          <div className="space-y-3">
            {data.races.map((race: any) => (
              <div key={race.race_id} className="bg-white/5 border border-white/10 rounded-xl p-4 hover:bg-white/8 transition-all">
                <div className="flex justify-between items-center mb-3">
                  <div className="flex items-center gap-3">
                    <span className="bg-indigo-500/20 text-indigo-300 text-xs px-2 py-1 rounded font-bold border border-indigo-500/30">
                      {trackNameMap[race.track] || race.track}
                    </span>
                    <span className="font-semibold text-slate-100">제{race.race_number}경주</span>
                  </div>
                  <button
                    onClick={() => navigate(`/races/${date}/${race.race_id}`)}
                    className="text-xs text-indigo-400 hover:text-indigo-300 underline"
                  >
                    상세보기 →
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-4 text-xs">
                  {/* AI Picks */}
                  <div>
                    <p className="text-slate-500 font-bold mb-1.5 uppercase tracking-wider">🤖 AI 예측</p>
                    <div className="space-y-1">
                      {race.ai_picks.map((pick: any) => (
                        <div key={pick.rank} className="flex items-center gap-2 text-slate-300">
                          <span className="w-4 text-center font-bold">{pick.rank}</span>
                          <span className="bg-slate-800 px-2 py-0.5 rounded font-mono">{pick.program_number}번</span>
                          <span className="text-slate-500">({(pick.win_prob * 100).toFixed(1)}%)</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* Actual Results */}
                  <div>
                    <p className="text-slate-500 font-bold mb-1.5 uppercase tracking-wider">🏆 실제 결과</p>
                    <div className="space-y-1">
                      {race.actual_results.map((r: any) => (
                        <div key={r.finish_position} className="flex items-center gap-2 text-slate-300">
                          <span className="w-4 text-center font-bold">
                            {r.finish_position === 1 ? "🥇" : r.finish_position === 2 ? "🥈" : "🥉"}
                          </span>
                          <span className="bg-slate-800 px-2 py-0.5 rounded font-mono">{r.program_number}번</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Bet results */}
                <div className="flex gap-2 mt-3 pt-3 border-t border-white/5">
                  {[
                    { key: "win", label: "단승", hit: race.bets.win.hit, ret: race.bets.win.return },
                    { key: "quinella", label: "복승", hit: race.bets.quinella.hit, ret: race.bets.quinella.return },
                    { key: "trio", label: "삼복승", hit: race.bets.trio.hit, ret: race.bets.trio.return },
                  ].map(({ key, label, hit, ret }) => (
                    <div key={key} className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border ${hit ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" : "bg-slate-900 text-slate-500 border-white/5"}`}>
                      {hit ? <CheckCircle size={12} /> : <XCircle size={12} />}
                      {label}
                      {hit && <span className="font-bold">+{formatMoney(ret - 1000)}</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
