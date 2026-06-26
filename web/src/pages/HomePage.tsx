import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchRaces } from "../api/races";
import { format } from "date-fns";

export default function HomePage() {
  const { date } = useParams();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["races", date],
    queryFn: () => fetchRaces(date!),
    enabled: !!date,
  });

  if (isLoading) return <div className="p-4 flex justify-center mt-10 text-slate-400">Loading races...</div>;

  return (
    <div className="max-w-md mx-auto min-h-screen bg-slate-950 text-slate-200">
      <header className="p-4 border-b border-white/10 flex justify-between items-center sticky top-0 bg-slate-950/80 backdrop-blur-md z-10">
        <h1 className="text-xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">KRA Quant</h1>
        <input 
          type="date" 
          value={date} 
          onChange={(e) => navigate(`/races/${e.target.value}`)}
          className="bg-white/5 border border-white/10 rounded-lg p-1.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all text-slate-300 color-scheme-dark"
        />
      </header>
      
      <div className="p-4 space-y-4">
        {data?.items?.length === 0 ? (
          <div className="text-center text-slate-500 mt-10">No races found for {date}</div>
        ) : (
          data?.items?.map((race: any) => (
            <div 
              key={race.id} 
              onClick={() => navigate(`/races/${date}/${race.id}`)}
              className="group relative bg-white/5 border border-white/10 rounded-2xl p-4 shadow-lg active:scale-95 transition-all duration-300 cursor-pointer hover:bg-white/10 hover:border-indigo-500/50 hover:shadow-indigo-500/20 overflow-hidden"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 to-purple-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
              <div className="relative z-10">
                <div className="flex justify-between items-start mb-3">
                  <div className="flex items-center gap-3">
                    <span className="bg-indigo-500/20 text-indigo-300 text-xs px-2.5 py-1 rounded-md font-bold tracking-wide border border-indigo-500/30">
                      {race.track} R{race.race_number}
                    </span>
                    <span className="font-semibold text-slate-100">{race.race_name || `Race ${race.race_number}`}</span>
                  </div>
                  <span className="text-sm font-medium text-slate-400 bg-slate-900/50 px-2 py-0.5 rounded-full border border-white/5">
                    {race.post_time ? format(new Date(race.post_time), "HH:mm") : ""}
                  </span>
                </div>
                <div className="text-sm text-slate-400 flex gap-4 font-medium">
                  <span className="flex items-center gap-1">📏 {race.distance_m}m</span>
                  <span className="flex items-center gap-1">🛣️ {race.surface}</span>
                  <span className="flex items-center gap-1">🐎 {race.field_size} Horses</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
