import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Activity, ArrowUpRight, ArrowDownRight, CheckCircle, XCircle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

const trackNameMap: Record<string, string> = { SEOUL: "서울", BUSAN: "부산", JEJU: "제주" };

const BET_TOP_COLOR: Record<string, string> = {
  indigo: "bg-indigo-500",
  purple: "bg-purple-500",
  pink:   "bg-pink-500",
};

export default function ROIReportPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [date, setDate] = useState(() => {
    return searchParams.get("date") || new Date().toISOString().split("T")[0];
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

  const { data: trendData } = useQuery({
    queryKey: ["roi-trend"],
    queryFn: async () => {
      const res = await fetch(`/api/reports/roi`);
      if (!res.ok) return null;
      const json = await res.json();
      if (!json.monthly?.length) return null;

      let cumInv = 0;
      let cumRet = 0;
      return json.monthly.map((m: any) => {
        const inv = (m.stats?.WIN?.investment ?? 0) + (m.stats?.QUINELLA?.investment ?? 0) + (m.stats?.TRIO?.investment ?? 0);
        const ret = (m.stats?.WIN?.return ?? 0) + (m.stats?.QUINELLA?.return ?? 0) + (m.stats?.TRIO?.return ?? 0);
        cumInv += inv;
        cumRet += ret;
        return {
          month: m.month,
          roi: cumInv > 0 ? parseFloat(((cumRet - cumInv) / cumInv * 100).toFixed(1)) : 0,
        };
      });
    },
  });

  const formatMoney = (val: number) => new Intl.NumberFormat("ko-KR").format(Math.round(val)) + "원";
  const calcROI = (ret: number, inv: number) =>
    inv > 0 ? (((ret - inv) / inv) * 100).toFixed(1) : "0.0";

  const latestROI = trendData?.length ? trendData[trendData.length - 1].roi : null;

  // 경주를 트랙별로 그룹화
  const groupedRaces: Record<string, any[]> = {};
  if (data?.races) {
    for (const race of data.races) {
      if (!groupedRaces[race.track]) groupedRaces[race.track] = [];
      groupedRaces[race.track].push(race);
    }
  }
  const trackOrder = ["SEOUL", "BUSAN", "JEJU"];

  return (
    <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 text-slate-200 pb-28">
      {/* Sticky header */}
      <header className="p-4 border-b border-white/10 sticky top-0 bg-slate-950/90 backdrop-blur-md z-10 shadow-lg shadow-black/20">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-full hover:bg-white/10 transition-colors text-slate-400 hover:text-white"
          >
            <ArrowLeft size={20} />
          </button>
          <h1 className="text-xl font-bold bg-gradient-to-r from-emerald-400 to-indigo-400 bg-clip-text text-transparent flex items-center gap-2">
            <Activity size={20} className="text-emerald-400" />
            모의투자 리포트
          </h1>
          <div className="ml-auto flex items-center gap-3">
            {latestROI !== null && (
              <span className={`text-sm font-black ${latestROI >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                누적 ROI {latestROI >= 0 ? "+" : ""}{latestROI}%
              </span>
            )}
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/50 text-slate-300 [color-scheme:dark]"
            />
          </div>
        </div>
      </header>

      <div className="p-4 space-y-6">
        {/* Trend chart */}
        {trendData && trendData.length > 0 && (
          <div className="bg-slate-900 border border-white/10 rounded-2xl p-5 shadow-xl">
            <h2 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-1">월별 누적 수익률</h2>
            <p className="text-[10px] text-slate-600 mb-4">배당 데이터 있는 경주만 집계</p>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="month" stroke="#475569" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#475569" tick={{ fontSize: 11 }} unit="%" />
                  <ReferenceLine y={0} stroke="#475569" strokeDasharray="4 2" />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "10px", fontSize: 12 }}
                    formatter={(v: any) => [`${v}%`, "누적 ROI"]}
                  />
                  <Line
                    type="monotone"
                    dataKey="roi"
                    stroke="#34d399"
                    strokeWidth={3}
                    dot={{ r: 3, fill: "#34d399", strokeWidth: 2, stroke: "#0f172a" }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Subtitle */}
        <p className="text-sm text-slate-500">
          📅 <span className="text-slate-300 font-semibold">{date}</span> 경기에 AI가 베팅했다면?
          {data && (
            <span className="ml-2 text-slate-600 text-xs">
              전체 {data.total_races}경주 중 배당 데이터: {data.races_with_payout ?? 0}경주
            </span>
          )}
        </p>

        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-32 bg-white/5 rounded-2xl border border-white/5 animate-pulse" />
            ))}
          </div>
        )}

        {error && (
          <div className="text-center text-rose-400 py-12 text-sm">
            데이터를 불러올 수 없습니다. 날짜를 다시 선택해보세요.
          </div>
        )}

        {data?.total_races === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
            <span className="text-4xl">📊</span>
            <p className="text-slate-400">해당 날짜에 경주 데이터가 없습니다.</p>
          </div>
        )}

        {data && data.total_races > 0 && (() => {
          const hasResults = data.races.some((r: any) => r.actual_results?.length > 0);
          const hasPayouts = (data.races_with_payout ?? 0) > 0;

          return (
            <>
              {!hasResults ? (
                /* Simulator mode */
                <div className="bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/30 rounded-2xl p-5 shadow-[0_0_20px_rgba(99,102,241,0.1)]">
                  <p className="text-base font-bold text-slate-100 mb-1 flex items-center gap-2">🔮 오늘의 시뮬레이터</p>
                  <p className="text-xs text-slate-400 mb-4 leading-relaxed">
                    아직 결과가 확정되지 않았습니다. AI 1순위에 전 경기 1만원씩 베팅하면 필요한 시드:
                  </p>
                  <div className="grid grid-cols-3 gap-3 text-center text-xs">
                    {[
                      { label: "단승", val: data.total_races * 1000, c: "text-indigo-300" },
                      { label: "복승", val: data.total_races * 1000, c: "text-purple-300" },
                      { label: "삼복승", val: data.total_races * 1000, c: "text-pink-300" },
                    ].map(({ label, val, c }) => (
                      <div key={label} className="bg-white/5 border border-white/10 rounded-xl p-3">
                        <div className="text-slate-500 mb-1">{label}</div>
                        <div className={`font-bold ${c}`}>{formatMoney(val)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : hasPayouts ? (
                /* Past race summary cards - 배당 데이터 있는 경주만 */
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {[
                    { key: "win", label: "단승식", sub: "1착 맞추기", color: "indigo" },
                    { key: "quinella", label: "복승식", sub: "1·2착 맞추기", color: "purple" },
                    { key: "trio", label: "삼복승식", sub: "1·2·3착 맞추기", color: "pink" },
                  ].map(({ key, label, sub, color }) => {
                    const s = data.totals[key];
                    const roi = parseFloat(calcROI(s.return, s.investment));
                    const pos = roi >= 0;
                    const racesWithPayout = s.races_with_payout ?? 0;
                    return (
                      <div key={key} className="relative overflow-hidden bg-white/5 border border-white/10 rounded-2xl p-5 shadow-lg">
                        <div className={`absolute top-0 left-0 w-full h-1 ${BET_TOP_COLOR[color]}`} />
                        <div className="flex justify-between items-start mb-3">
                          <div>
                            <p className="text-sm font-bold text-slate-200">{label}</p>
                            <p className="text-xs text-slate-500">{sub}</p>
                          </div>
                          <span className={`flex items-center gap-0.5 text-sm font-black px-2 py-0.5 rounded-lg ${pos ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"}`}>
                            {pos ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                            {pos ? "+" : ""}{roi}%
                          </span>
                        </div>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-slate-500">투자</span>
                            <span className="text-slate-300">{formatMoney(s.investment)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-500">회수</span>
                            <span className={`font-bold ${pos ? "text-emerald-400" : "text-rose-400"}`}>{formatMoney(s.return)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-500">적중</span>
                            <span className="text-indigo-300 font-semibold">{s.hits} / {racesWithPayout}경기</span>
                          </div>
                        </div>
                        {data.total_races > racesWithPayout && (
                          <p className="text-[10px] text-slate-600 mt-2">
                            배당 미확인 {data.total_races - racesWithPayout}경주 제외
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                /* 결과는 있지만 배당 데이터 없음 */
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 text-sm text-amber-300">
                  결과 데이터는 있으나 배당 데이터가 아직 수집되지 않았습니다. 배당 업데이트 후 다시 확인해주세요.
                </div>
              )}

              {/* Per-race list - 트랙별 그룹화 */}
              <div>
                <h2 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-3">경주별 결과</h2>
                {trackOrder
                  .filter((track) => groupedRaces[track]?.length > 0)
                  .map((track) => (
                    <div key={track} className="mb-4">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-bold text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-white/10">
                          {trackNameMap[track] || track}
                        </span>
                        <span className="text-xs text-slate-600">{groupedRaces[track].length}경주</span>
                      </div>
                      <div className="space-y-2.5">
                        {groupedRaces[track].map((race: any) => (
                          <div key={race.race_id} className="bg-white/5 border border-white/10 rounded-2xl p-4 hover:bg-white/[0.07] transition-all">
                            <div className="flex justify-between items-center mb-3">
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-slate-100 text-sm">제{race.race_number}경주</span>
                                {!race.has_payout && race.actual_results?.length > 0 && (
                                  <span className="text-[10px] text-amber-500 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">배당미확인</span>
                                )}
                              </div>
                              <button
                                onClick={() => navigate(`/races/${date}/${race.race_id}`)}
                                className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                              >
                                상세 →
                              </button>
                            </div>

                            <div className="grid grid-cols-2 gap-4 text-xs">
                              <div>
                                <p className="text-[10px] uppercase tracking-widest font-bold text-slate-600 mb-2">🤖 AI 예측</p>
                                {race.ai_picks.length > 0 ? (
                                  <div className="space-y-1">
                                    {race.ai_picks.map((pick: any) => (
                                      <div key={pick.rank} className="flex items-center gap-2 text-slate-300">
                                        <span className="w-4 text-slate-500 font-bold">{pick.rank}</span>
                                        <span className="bg-slate-800 px-2 py-0.5 rounded font-mono border border-white/5">{pick.program_number}번</span>
                                        <span className="text-slate-600">{(pick.win_prob * 100).toFixed(1)}%</span>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-slate-600 italic">예측 데이터 없음</span>
                                )}
                              </div>
                              <div>
                                <p className="text-[10px] uppercase tracking-widest font-bold text-slate-600 mb-2">🏆 실제 결과</p>
                                {race.actual_results?.length > 0 ? (
                                  <div className="space-y-1">
                                    {race.actual_results.map((r: any) => (
                                      <div key={r.finish_position} className="flex items-center gap-2 text-slate-300">
                                        <span>{r.finish_position === 1 ? "🥇" : r.finish_position === 2 ? "🥈" : "🥉"}</span>
                                        <span className="bg-slate-800 px-2 py-0.5 rounded font-mono border border-white/5">{r.program_number}번</span>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-slate-600 italic text-xs">결과 대기 중...</span>
                                )}
                              </div>
                            </div>

                            {race.actual_results?.length > 0 && race.ai_picks.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-white/5">
                                {[
                                  { key: "win",      label: "단승",   hit: race.bets.win.hit,      ret: race.bets.win.return },
                                  { key: "quinella", label: "복승",   hit: race.bets.quinella.hit, ret: race.bets.quinella.return },
                                  { key: "trio",     label: "삼복승", hit: race.bets.trio.hit,      ret: race.bets.trio.return },
                                ].map(({ key, label, hit, ret }) => (
                                  <span
                                    key={key}
                                    className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border font-semibold ${
                                      hit
                                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.15)]"
                                        : "bg-white/5 text-slate-600 border-white/5"
                                    }`}
                                  >
                                    {hit ? <CheckCircle size={11} /> : <XCircle size={11} />}
                                    {label}
                                    {hit && race.has_payout && ret > 0 && (
                                      <span className="font-black ml-0.5">+{formatMoney(ret - 1000)}</span>
                                    )}
                                    {hit && !race.has_payout && (
                                      <span className="ml-0.5 text-amber-400 text-[10px]">배당미확인</span>
                                    )}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </>
          );
        })()}
      </div>
    </div>
  );
}
