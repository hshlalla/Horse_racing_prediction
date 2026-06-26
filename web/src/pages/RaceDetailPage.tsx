import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRaceDetail, fetchPredictions } from "../api/races";
import { fetchFavorites, addFavorite, removeFavorite } from "../api/favorites";
import { ProbabilityBar } from "../components/ProbabilityBar";
import { ArrowLeft, Star } from "lucide-react";
import { useAuthStore } from "../lib/store";

export default function RaceDetailPage() {
  const { date, raceId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isAuth = !!useAuthStore((state) => state.accessToken);

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    }
  });

  if (!race) return <div className="p-4 flex justify-center mt-10 text-slate-400">Loading race details...</div>;

  const predMap = new Map(predictions?.items?.map((p: any) => [p.horse_id, p]));

  return (
    <div className="max-w-md mx-auto min-h-screen bg-slate-950 text-slate-200 pb-10">
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
              {race.track} R{race.race_number}
            </h1>
          </div>
          <div className="text-sm font-semibold bg-white/10 px-3 py-1 rounded-full border border-white/5 shadow-inner">
            {race.distance_m}m
          </div>
        </div>
        <div className="flex gap-2 text-xs font-medium text-slate-400">
          <span className="bg-slate-900 px-2 py-1 rounded border border-white/5">🛣️ {race.surface}</span>
          <span className="bg-slate-900 px-2 py-1 rounded border border-white/5">🌤️ {race.track_condition || "Unknown"}</span>
        </div>
      </header>
      
      <div className="p-4 space-y-4">
        {race.entries?.sort((a: any, b: any) => a.program_number - b.program_number).map((entry: any) => {
          const pred = predMap.get(entry.horse_id) as any;
          const isFav = favSet.has(entry.horse_id);
          const isTopPick = pred && pred.win_probability > 0.2; // highlight if high prob
          
          return (
            <div 
              key={entry.id} 
              className={`relative bg-white/5 border rounded-2xl p-4 shadow-lg transition-all duration-300 hover:bg-white/10 ${isTopPick ? 'border-indigo-500/50 shadow-indigo-500/10' : 'border-white/10 hover:border-white/20'}`}
            >
              {isTopPick && (
                <div className="absolute -top-px -left-px -right-px h-px bg-gradient-to-r from-transparent via-indigo-500 to-transparent opacity-50"></div>
              )}
              <div className="flex justify-between items-start">
                <div className="flex gap-4 items-center">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center font-black text-lg shadow-inner ${isTopPick ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white' : 'bg-slate-800 text-slate-300 border border-white/5'}`}>
                    {entry.program_number}
                  </div>
                  <div>
                    <div className="font-bold text-slate-100 text-lg leading-tight flex items-center gap-2">
                      {entry.horse_name}
                      {isTopPick && <span className="flex h-2 w-2 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.8)]"></span>}
                    </div>
                    <div className="text-xs text-slate-400 font-medium mt-0.5">
                      J: <span className="text-slate-300">{entry.jockey_name || "-"}</span> • T: <span className="text-slate-300">{entry.trainer_name || "-"}</span>
                    </div>
                  </div>
                </div>
                <button 
                  onClick={() => toggleFavorite.mutate({ horseId: entry.horse_id, isFav })}
                  className={`p-2 rounded-full transition-all duration-300 ${isFav ? 'text-yellow-400 bg-yellow-400/10 shadow-[0_0_15px_rgba(250,204,21,0.2)]' : 'text-slate-600 hover:bg-white/10 hover:text-slate-300'}`}
                >
                  <Star fill={isFav ? "currentColor" : "none"} size={20}/>
                </button>
              </div>
              
              {pred && (
                <div className="mt-5 pl-14 space-y-3">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1.5 flex justify-between">
                      <span>Win Probability</span>
                    </div>
                    <ProbabilityBar probability={pred.win_probability} color="from-indigo-500 to-purple-500" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1.5 flex justify-between">
                      <span>Place Probability</span>
                    </div>
                    <ProbabilityBar probability={pred.place_probability} color="from-teal-400 to-emerald-500" />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
