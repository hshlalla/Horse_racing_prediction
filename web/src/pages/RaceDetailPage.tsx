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

  if (!race) return <div className="p-4">Loading race details...</div>;

  const predMap = new Map(predictions?.items?.map((p: any) => [p.horse_id, p]));

  return (
    <div className="max-w-md mx-auto min-h-screen bg-gray-50 pb-10">
      <header className="bg-slate-900 text-white p-4 sticky top-0 z-10 shadow-md">
        <div className="flex items-center gap-3 mb-2">
          <button onClick={() => navigate(`/races/${date}`)}><ArrowLeft size={20}/></button>
          <h1 className="text-xl font-bold">{race.track} R{race.race_number}</h1>
        </div>
        <div className="text-sm text-slate-300">
          {race.distance_m}m • {race.surface} • {race.track_condition || "Unknown"}
        </div>
      </header>
      
      <div className="p-2 space-y-2 mt-2">
        {race.entries?.sort((a: any, b: any) => a.program_number - b.program_number).map((entry: any) => {
          const pred = predMap.get(entry.horse_id) as any;
          const isFav = favSet.has(entry.horse_id);
          
          return (
            <div key={entry.id} className="bg-white p-3 rounded-lg shadow-sm border flex flex-col gap-2 relative">
              <div className="flex justify-between items-start">
                <div className="flex gap-3 items-center">
                  <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-800 flex items-center justify-center font-bold">
                    {entry.program_number}
                  </div>
                  <div>
                    <div className="font-bold text-gray-900 text-lg leading-tight">{entry.horse_name}</div>
                    <div className="text-xs text-gray-500">
                      J: {entry.jockey_name || "-"} • T: {entry.trainer_name || "-"}
                    </div>
                  </div>
                </div>
                <button 
                  onClick={() => toggleFavorite.mutate({ horseId: entry.horse_id, isFav })}
                  className={`p-2 rounded-full transition-colors ${isFav ? 'text-yellow-500 bg-yellow-50' : 'text-gray-300 hover:bg-gray-100'}`}
                >
                  <Star fill={isFav ? "currentColor" : "none"} size={20}/>
                </button>
              </div>
              
              {pred && (
                <div className="mt-2 pl-11">
                  <div className="text-xs font-semibold text-gray-500 mb-1">Win Probability</div>
                  <ProbabilityBar probability={pred.win_probability} color="bg-blue-600" />
                  <div className="text-xs font-semibold text-gray-500 mt-2 mb-1">Place Probability</div>
                  <ProbabilityBar probability={pred.place_probability} color="bg-teal-500" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
