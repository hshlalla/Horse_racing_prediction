import { Link } from "react-router-dom";
import { format } from "date-fns";

export interface Race {
  id: number;
  race_date: string;
  track: string;
  race_number: number;
  race_name: string;
  post_time: string;
  distance: number;
  surface: string;
  weather: string;
  track_condition: string;
  grade: string;
  class_level: string;
  field_size: number;
}

export function RaceCard({ race }: { race: Race }) {
  return (
    <Link to={`/races/${race.race_date}/${race.id}`} className="block">
      <div className="bg-white border rounded-xl shadow-sm p-4 mb-3 hover:shadow-md transition-shadow">
        <div className="flex justify-between items-start mb-2">
          <div>
            <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded">R{race.race_number}</span>
            <span className="ml-2 font-bold text-slate-900">{race.race_name || `Race ${race.race_number}`}</span>
          </div>
          <div className="text-sm font-semibold text-gray-600">
            {format(new Date(race.post_time), "HH:mm")}
          </div>
        </div>
        <div className="text-xs text-gray-500 flex gap-2">
          <span>{race.track}</span>
          <span>•</span>
          <span>{race.distance}m</span>
          <span>•</span>
          <span>{race.surface}</span>
        </div>
      </div>
    </Link>
  );
}
