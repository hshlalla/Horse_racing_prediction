import { useState } from "react";
import { format } from "date-fns";
import { parseRaceTime } from "../lib/time";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRaceDetail, fetchPredictions, fetchRaceResults } from "../api/races";
import { fetchFavorites, addFavorite, removeFavorite } from "../api/favorites";
import { ProbabilityBar } from "../components/ProbabilityBar";
import { Toast } from "../components/Toast";
import { HorseDetailDrawer } from "../components/HorseDetailDrawer";
import { BettingSuggestion } from "../components/BettingSuggestion";
import { ArrowLeft, Star, RefreshCw } from "lucide-react";
import { useAuthStore } from "../lib/store";

const trackNameMap: Record<string, string> = { SEOUL: "서울", BUSAN: "부산", JEJU: "제주" };

export default function RaceDetailPage() {
  const { date, raceId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isAuth = !!useAuthStore((state) => state.accessToken);
  const [toastMessage, setToastMessage] = useState<{msg: string, type: "success"|"info"|"error"} | null>(null);
  const [drawerHorse, setDrawerHorse] = useState<{name: string, features: any} | null>(null);

  const { data: race } = useQuery({
    queryKey: ["race", raceId],
    queryFn: () => fetchRaceDetail(Number(raceId)),
    enabled: !!raceId,
  });

  const { data: predictions } = useQuery({
    queryKey: ["predictions", raceId],
    queryFn: () => fetchPredictions(Number(raceId)),
    enabled: !!raceId,
  });

  const { data: favorites } = useQuery({
    queryKey: ["favorites"],
    queryFn: () => fetchFavorites(),
    enabled: isAuth,
  });

  const favSet = new Set(favorites?.items?.map((f: any) => f.horse.id) || []);

  const fetchResults = useMutation({
    mutationFn: () => fetchRaceResults(Number(raceId)),
    onSuccess: (data) => {
      if (data.ok) {
        queryClient.invalidateQueries({ queryKey: ["race", raceId] });
        queryClient.invalidateQueries({ queryKey: ["predictions", raceId] });
        setToastMessage({ msg: "결과를 가져왔습니다!", type: "success" });
      } else {
        setToastMessage({ msg: data.message || "결과를 가져올 수 없습니다.", type: "error" });
      }
    },
    onError: () => {
      setToastMessage({ msg: "오류가 발생했습니다. 잠시 후 다시 시도해주세요.", type: "error" });
    },
  });

  const toggleFavorite = useMutation({
    mutationFn: async ({ horseId, isFav }: { horseId: number, isFav: boolean }) => {
      if (!isAuth) {
        navigate("/login");
        throw new Error("Not logged in");
      }
      if (isFav) {
        await removeFavorite(horseId);
      } else {
        await addFavorite(horseId);
      }
    },
    onSuccess: (_, { isFav }) => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      setToastMessage({ 
        msg: isFav ? "관심 마필에서 해제되었습니다." : "⭐ 관심 마필로 등록되었습니다!", 
        type: isFav ? "info" : "success" 
      });
    }
  });

  if (!race) return (
    <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 p-4">
      <div className="animate-pulse">
        <div className="h-20 bg-white/5 rounded-2xl mb-4 border border-white/5"></div>
        <div className="h-16 bg-white/5 rounded-xl mb-4 border border-white/5 max-w-sm"></div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-48 bg-white/5 rounded-2xl border border-white/5 shadow-lg"></div>)}
        </div>
      </div>
    </div>
  );

  const predMap = new Map(predictions?.items?.map((p: any) => [p.horse_id, p]));
  const hasResults = race.entries?.some((e: any) => e.finish_position != null);
  const isPastRace = hasResults;
  const isRaceDatePast = race.race_date <= new Date().toISOString().split("T")[0];
  const canFetchResults = !hasResults && isRaceDatePast;

  // Latest odds update time from predictions
  const latestComputedAt = predictions?.items?.reduce((latest: string | null, p: any) => {
    if (!latest) return p.computed_at;
    return p.computed_at > latest ? p.computed_at : latest;
  }, null as string | null);

  // Determine medal colors
  const getMedalBadge = (pos: number | null) => {
    if (pos === 1) return { emoji: "🥇", label: "1착", cls: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" };
    if (pos === 2) return { emoji: "🥈", label: "2착", cls: "bg-slate-400/20 text-slate-300 border-slate-400/40" };
    if (pos === 3) return { emoji: "🥉", label: "3착", cls: "bg-amber-600/20 text-amber-400 border-amber-600/40" };
    return null;
  };

  return (
    <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 text-slate-200 pb-28">
      <header className="p-4 border-b border-white/10 sticky top-0 bg-slate-950/80 backdrop-blur-md z-20 shadow-lg shadow-black/20">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => navigate(`/races/${date}`)}
              className="p-2 -ml-2 rounded-full hover:bg-white/10 transition-colors text-slate-400 hover:text-white"
            >
              <ArrowLeft size={20}/>
            </button>
            <h1 className="text-xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent tracking-tight">
              {trackNameMap[race.track] || race.track} 제{race.race_number}경주
            </h1>
          </div>
          <div className="flex items-center gap-2">
            {isPastRace && (
              <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                결과 확정
              </span>
            )}
            {canFetchResults && (
              <button
                onClick={() => fetchResults.mutate()}
                disabled={fetchResults.isPending}
                className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-500/30 transition-all disabled:opacity-50"
              >
                <RefreshCw size={12} className={fetchResults.isPending ? "animate-spin" : ""} />
                {fetchResults.isPending ? "가져오는 중..." : "결과 가져오기"}
              </button>
            )}
            <div className="text-sm font-semibold bg-white/10 px-3 py-1 rounded-full border border-white/5 shadow-inner">
              {race.distance_m}m
            </div>
          </div>
        </div>
        <div className="flex gap-2 text-xs font-medium text-slate-400 mt-2">
          <span className="bg-slate-900 px-2 py-1 rounded border border-white/5">🌤️ {race.track_condition || "Unknown"}</span>
          {race.humidity && (
            <span className="bg-slate-900 px-2 py-1 rounded border border-white/5">💧 습도 {race.humidity}%</span>
          )}
          <span className="bg-gradient-to-r from-indigo-500/20 to-purple-500/20 text-indigo-300 border border-indigo-500/30 px-2 py-1 rounded-full flex items-center gap-1 shadow-[0_0_10px_rgba(99,102,241,0.2)]">
            ✨ Ensemble AI
          </span>
          {latestComputedAt && (
            <span className="bg-slate-900 px-2 py-1 rounded border border-white/5 text-slate-500">
              🕐 배당 {format(parseRaceTime(latestComputedAt)!, "HH:mm")} 기준
            </span>
          )}
        </div>
      </header>
      
      {race.video_url && (
        <div className="px-4 py-4 border-b border-white/5 bg-slate-900/30">
          <a href={race.video_url} target="_blank" rel="noreferrer" className="flex items-center justify-center gap-2 bg-red-600/20 text-red-400 border border-red-500/30 px-4 py-3 rounded-xl font-bold hover:bg-red-600/30 transition-colors shadow-lg shadow-red-900/20">
            <span className="text-xl">▶</span> YouTube 경주 영상 시청
          </a>
        </div>
      )}

      {/* Payouts section for past races */}
      {isPastRace && race.payouts && (
        <div className="px-4 py-4 border-b border-white/5 bg-slate-900/30">
          <h3 className="text-sm font-bold text-slate-300 mb-2">💰 배당률</h3>
          <div className="flex flex-wrap gap-2 text-xs">
            {race.payouts.win?.map((p: any, i: number) => (
              <span key={`w${i}`} className="bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 px-2 py-1 rounded">
                단승 {p.numbers}번 — {p.odds}배
              </span>
            ))}
            {race.payouts.place?.map((p: any, i: number) => (
              <span key={`p${i}`} className="bg-teal-500/10 text-teal-300 border border-teal-500/30 px-2 py-1 rounded">
                연승 {p.numbers}번 — {p.odds}배
              </span>
            ))}
            {race.payouts.quinella?.map((p: any, i: number) => (
              <span key={`q${i}`} className="bg-purple-500/10 text-purple-300 border border-purple-500/30 px-2 py-1 rounded">
                복승 {p.numbers} — {p.odds}배
              </span>
            ))}
            {race.payouts.trio?.map((p: any, i: number) => (
              <span key={`t${i}`} className="bg-pink-500/10 text-pink-300 border border-pink-500/30 px-2 py-1 rounded">
                삼복승 {p.numbers} — {p.odds}배
              </span>
            ))}
          </div>
        </div>
      )}

      {(() => {
        // Compute betting suggestions
        const horses = race.entries?.map((e: any) => {
          const pred = predMap.get(e.horse_id) as any;
          const winProb = pred?.win_probability || 0;
          const placeProb = pred?.place_probability || 0;
          const odds = e.morning_odds || 0;
          const winEv = winProb * odds;
          const placeEv = placeProb * odds;
          return {
            horse_id: e.horse_id,
            program_number: e.program_number,
            horse_name: e.horse_name,
            winProb,
            placeProb,
            odds,
            winEv,
            placeEv
          };
        }) || [];

        const hFmt = (h: any) => ({ program_number: h.program_number, horse_name: h.horse_name });

        // Sorting
        const winSorted = [...horses].sort((a, b) => b.winProb - a.winProb);
        const placeSorted = [...horses].sort((a, b) => b.placeProb - a.placeProb);
        const winEvSorted = [...horses].sort((a, b) => b.winEv - a.winEv);
        const placeEvSorted = [...horses].sort((a, b) => b.placeEv - a.placeEv);

        const w1 = winSorted[0], w2 = winSorted[1], w3 = winSorted[2];
        const p1 = placeSorted[0], p2 = placeSorted[1];
        const we1 = winEvSorted[0];
        const pe1 = placeEvSorted[0];

        const aggressiveWin2nd = winSorted.find(h => h.horse_id !== we1?.horse_id) || w2;
        const aggressiveWin3rd = winSorted.find(h => h.horse_id !== we1?.horse_id && h.horse_id !== aggressiveWin2nd?.horse_id) || w3;
        const aggressivePlace2nd = placeSorted.find(h => h.horse_id !== pe1?.horse_id) || p2;

        const stable = {
          win: w1 && w1.winProb > 0 ? {
            horses: [hFmt(w1)],
            reason: `AI 우승 확률 1위 (${(w1.winProb * 100).toFixed(1)}%)`,
            badge: "가장 확실한 픽"
          } : null,
          place: p1 && p1.placeProb > 0 ? {
            horses: [hFmt(p1)],
            reason: `AI 연승 확률 1위 (${(p1.placeProb * 100).toFixed(1)}%)`,
            badge: "안전 자산"
          } : null,
          quinella: w1 && w2 ? {
            horses: [hFmt(w1), hFmt(w2)],
            reason: "승률 1위 + 2위 조합"
          } : null,
          exacta: w1 && w2 ? {
            horses: [hFmt(w1), hFmt(w2)],
            reason: "승률 1위 ➔ 승률 2위 정배당",
            badge: "정배당의 정석"
          } : null,
          quinellaPlace: p1 && p2 ? {
            horses: [hFmt(p1), hFmt(p2)],
            reason: "연승 확률 1위 + 2위 조합"
          } : null,
          trio: w1 && w2 && w3 ? {
            horses: [hFmt(w1), hFmt(w2), hFmt(w3)],
            reason: "승률 1위 + 2위 + 3위 조합"
          } : null,
          trifecta: w1 && w2 && w3 ? {
            horses: [hFmt(w1), hFmt(w2), hFmt(w3)],
            reason: "승률 1위 ➔ 2위 ➔ 3위",
            badge: "가장 안정적인 삼쌍승"
          } : null
        };

        const aggressive = {
          win: we1 && we1.winEv > 0 ? {
            horses: [hFmt(we1)],
            reason: `기대수익(EV) 1위 (배당 ${we1.odds}배)`,
            badge: "한방 역배당"
          } : null,
          place: pe1 && pe1.placeEv > 0 ? {
            horses: [hFmt(pe1)],
            reason: `연승 기대수익 1위 (배당 ${pe1.odds}배)`,
            badge: "가성비 연승픽"
          } : null,
          quinella: we1 && aggressiveWin2nd ? {
            horses: [hFmt(we1), hFmt(aggressiveWin2nd)],
            reason: "가치마 + 승률 1위 조합"
          } : null,
          exacta: we1 && aggressiveWin2nd ? {
            horses: [hFmt(we1), hFmt(aggressiveWin2nd)],
            reason: "가치마 1착 ➔ 정배당 2착 콤보",
            badge: "고배당 쌍승 노리기"
          } : null,
          quinellaPlace: pe1 && aggressivePlace2nd ? {
            horses: [hFmt(pe1), hFmt(aggressivePlace2nd)],
            reason: "연승 가치마 + 정배당 연승 1위"
          } : null,
          trio: we1 && aggressiveWin2nd && aggressiveWin3rd ? {
            horses: [hFmt(we1), hFmt(aggressiveWin2nd), hFmt(aggressiveWin3rd)],
            reason: "역배당 1두 + 정배당 2두 조합"
          } : null,
          trifecta: we1 && aggressiveWin2nd && aggressiveWin3rd ? {
            horses: [hFmt(we1), hFmt(aggressiveWin2nd), hFmt(aggressiveWin3rd)],
            reason: "가치마 1착 ➔ 정배당 2, 3착",
            badge: "역대급 배당 노리기"
          } : null
        };

        return (
          <div className="p-4 pt-6">
            <BettingSuggestion stable={stable} aggressive={aggressive} />
          </div>
        );
      })()}

      <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {race.entries?.sort((a: any, b: any) => {
          // ALWAYS sort by AI prediction probability, so the top card is AI's #1 pick
          const probA = (predMap.get(a.horse_id) as any)?.win_probability || 0;
          const probB = (predMap.get(b.horse_id) as any)?.win_probability || 0;
          return probB - probA;
        }).map((entry: any, index: number) => {
          const pred = predMap.get(entry.horse_id) as any;
          const isFav = favSet.has(entry.horse_id);
          const isTopPick = index === 0;
          const medal = getMedalBadge(entry.finish_position);
          // edge_score > 0.05: model sees 5%+ more chance than market implies
          const edgeScore: number = pred?.edge_score ?? 0;
          const isValueBet = edgeScore >= 0.05;
          const edgePct = Math.round(edgeScore * 100);
          
          return (
            <div 
              key={entry.id} 
              onClick={() => {
                if (pred) {
                  setDrawerHorse({
                    name: entry.horse_name,
                    features: {
                      win_probability: pred.win_probability,
                      place_probability: pred.place_probability,
                      edge_score: pred.edge_score ?? 0,
                      market_prob: pred.market_prob ?? 0,
                      top_reasons: pred.top_reasons ?? [],
                      distance_win_rate: pred.features_snapshot?.distance_win_rate,
                      jockey_horse_win_rate: pred.features_snapshot?.jockey_horse_win_rate,
                      horse_win_rate: pred.features_snapshot?.horse_win_rate,
                      past_avg_start_rank: pred.features_snapshot?.past_avg_start_rank,
                      past_avg_mid_rank: pred.features_snapshot?.past_avg_mid_rank,
                      past_avg_finish_rank: pred.features_snapshot?.past_avg_finish_rank,
                      past_avg_g3f_time: pred.features_snapshot?.past_avg_g3f_time,
                      carry_weight_kg: entry.carry_weight_kg,
                    }
                  });
                }
              }}
              className={`relative cursor-pointer bg-white/5 border rounded-2xl p-4 shadow-lg transition-all duration-300 hover:bg-white/10 ${
                isTopPick ? 'border-indigo-500/50 shadow-[0_0_15px_rgba(99,102,241,0.2)]' : 'border-white/10 hover:border-white/20'
              } ${isValueBet ? 'ring-2 ring-rose-500/50' : ''}`}
            >
              {isValueBet && (
                <div className="absolute -top-3 right-4 bg-gradient-to-r from-rose-500 to-pink-500 text-white text-[10px] font-bold px-3 py-0.5 rounded-full shadow-lg shadow-rose-500/40 whitespace-nowrap z-10 animate-pulse">
                  🔥 시장 대비 +{edgePct}%
                </div>
              )}
              {!isValueBet && edgeScore < -0.05 && (
                <div className="absolute -top-3 right-4 bg-slate-700/80 text-slate-400 text-[10px] font-bold px-3 py-0.5 rounded-full whitespace-nowrap z-10">
                  시장 대비 {edgePct}%
                </div>
              )}
              {isTopPick && (
                <div className="absolute -top-px -left-px -right-px h-px bg-gradient-to-r from-transparent via-indigo-500 to-transparent opacity-50"></div>
              )}
              {isTopPick && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-500 text-white text-[10px] font-bold px-3 py-0.5 rounded-full shadow-lg shadow-indigo-500/30 whitespace-nowrap">
                  🤖 AI 1순위 추천
                </div>
              )}
              <div className="flex justify-between items-start mt-2">
                <div className="flex gap-4 items-center">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center font-black text-lg shadow-inner ${
                    medal && medal.emoji === '🥇' ? 'bg-gradient-to-br from-yellow-500 to-amber-600 text-white shadow-yellow-500/30' :
                    isTopPick ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white' : 
                    'bg-slate-800 text-slate-300 border border-white/5'
                  }`}>
                    {entry.program_number}
                  </div>
                  <div>
                    <div className="font-bold text-slate-100 text-lg leading-tight flex items-center gap-2">
                      {entry.horse_name}
                      {medal && (
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${medal.cls} shadow-sm`}>
                          {medal.emoji} 실제 {medal.label}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 font-medium mt-0.5">
                      기수: <span className="text-slate-300">{entry.jockey_name || "-"}</span> • 조교사: <span className="text-slate-300">{entry.trainer_name || "-"}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {entry.morning_odds > 0 && (
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${isValueBet ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-slate-800 text-emerald-400 border-white/5'}`}>
                          배당 {entry.morning_odds}배
                        </span>
                      )}
                      {pred?.market_prob > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded border bg-slate-800/60 text-slate-400 border-white/5">
                          시장 {Math.round(pred.market_prob * 100)}%
                        </span>
                      )}
                    </div>
                    {entry.finish_time_s && (
                      <div className="text-xs text-slate-500 mt-1">
                        ⏱️ {entry.finish_time_s.toFixed(1)}초
                      </div>
                    )}
                  </div>
                </div>
                <button 
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleFavorite.mutate({ horseId: entry.horse_id, isFav });
                  }}
                  className={`p-2 rounded-full transition-all duration-300 ${isFav ? 'text-yellow-400 bg-yellow-400/10 shadow-[0_0_15px_rgba(250,204,21,0.2)]' : 'text-slate-600 hover:bg-white/10 hover:text-slate-300'}`}
                >
                  <Star fill={isFav ? "currentColor" : "none"} size={20}/>
                </button>
              </div>
              
              {pred && (
                <div className="mt-5 pl-14 space-y-3">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1.5">
                      <span>우승 확률</span>
                    </div>
                    <ProbabilityBar probability={pred.win_probability} color="from-indigo-500 to-purple-500" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1.5">
                      <span>연승 확률</span>
                    </div>
                    <ProbabilityBar probability={pred.place_probability} color="from-teal-400 to-emerald-500" />
                  </div>
                  {pred.top_reasons?.length > 0 && (
                    <div className="pt-1">
                      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1.5">AI 분석 근거</div>
                      <div className="flex flex-wrap gap-1">
                        {pred.top_reasons.map((r: any, i: number) => (
                          <span
                            key={i}
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                              r.direction > 0
                                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                            }`}
                          >
                            {r.direction > 0 ? '↑' : '↓'} {r.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {toastMessage && (
        <Toast 
          message={toastMessage.msg} 
          type={toastMessage.type} 
          onClose={() => setToastMessage(null)} 
        />
      )}

      <HorseDetailDrawer 
        isOpen={!!drawerHorse} 
        onClose={() => setDrawerHorse(null)} 
        horseName={drawerHorse?.name || ""} 
        features={drawerHorse?.features || null} 
      />
    </div>
  );
}
