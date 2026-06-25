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

  if (isLoading) return <div className="p-4">Loading races...</div>;

  return (
    <div className="max-w-md mx-auto min-h-screen bg-white">
      <header className="p-4 border-b flex justify-between items-center sticky top-0 bg-white z-10">
        <h1 className="text-xl font-bold">Horse Racing</h1>
        <input 
          type="date" 
          value={date} 
          onChange={(e) => navigate(`/races/${e.target.value}`)}
          className="border rounded p-1"
        />
      </header>
      
      <div className="p-4 space-y-4">
        {data?.items?.length === 0 ? (
          <div className="text-center text-gray-500 mt-10">No races found for {date}</div>
        ) : (
          data?.items?.map((race: any) => (
            <div 
              key={race.id} 
              onClick={() => navigate(`/races/${date}/${race.id}`)}
              className="border rounded-xl p-4 shadow-sm active:scale-95 transition-transform cursor-pointer hover:border-blue-300"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                  <span className="bg-slate-800 text-white text-xs px-2 py-1 rounded font-bold">{race.track} R{race.race_number}</span>
                  <span className="font-semibold">{race.race_name || `Race ${race.race_number}`}</span>
                </div>
                <span className="text-sm text-gray-500">
                  {race.post_time ? format(new Date(race.post_time), "HH:mm") : ""}
                </span>
              </div>
              <div className="text-sm text-gray-600 flex gap-3">
                <span>{race.distance_m}m</span>
                <span>{race.surface}</span>
                <span>{race.field_size} Horses</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
