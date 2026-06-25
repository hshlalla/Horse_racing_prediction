import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchFavorites, removeFavorite } from "../api/favorites";
import { useAuthStore } from "../lib/store";
import { useNavigate } from "react-router-dom";
import { Trash2, Bell, BellOff } from "lucide-react";
import { format } from "date-fns";
import { useTranslation } from "../hooks/useTranslation";

// Mock countdown hook for next race
function useNextRaceCountdown(targetDateStr: string) {
  const [timeLeft, setTimeLeft] = useState("");

  useEffect(() => {
    const target = new Date(targetDateStr).getTime();
    const interval = setInterval(() => {
      const now = new Date().getTime();
      const diff = target - now;
      if (diff <= 0) {
        setTimeLeft("Started");
      } else {
        const h = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        setTimeLeft(`Starts in ${h}h ${m}m`);
      }
    }, 60000); // update every minute
    return () => clearInterval(interval);
  }, [targetDateStr]);

  return timeLeft || "Calculating...";
}

function FavoriteRow({ fav, removeFav }: { fav: any, removeFav: any }) {
  const [reminder, setReminder] = useState(false);
  const countdown = useNextRaceCountdown(fav.next_race_time || new Date(Date.now() + 86400000).toISOString()); // dummy 24h
  
  return (
    <div className="flex justify-between items-center border p-4 rounded-xl shadow-sm bg-white">
      <div>
        <div className="font-bold text-lg">{fav.horse?.name || "Mock Horse"}</div>
        <div className="text-xs text-gray-500 mb-2">Favorited on {format(new Date(fav.created_at), "yyyy-MM-dd")}</div>
        <div className="text-sm font-semibold text-blue-600">
          Next: {countdown}
        </div>
      </div>
      <div className="flex gap-2">
        <button 
          onClick={() => setReminder(!reminder)}
          className={`p-2 rounded-full ${reminder ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'}`}
        >
          {reminder ? <Bell size={20} /> : <BellOff size={20} />}
        </button>
        <button 
          onClick={() => removeFav.mutate(fav.horse_id)}
          className="text-red-500 p-2 hover:bg-red-50 rounded-full"
        >
          <Trash2 size={20} />
        </button>
      </div>
    </div>
  );
}

export default function FavoritesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const isAuth = !!useAuthStore((state) => state.accessToken);

  if (!isAuth) {
    navigate("/login");
    return null;
  }

  const { data: favorites, isLoading } = useQuery({
    queryKey: ["favorites"],
    queryFn: fetchFavorites,
  });

  const removeFav = useMutation({
    mutationFn: (id: number) => removeFavorite(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    }
  });

  if (isLoading) return <div className="p-4">Loading favorites...</div>;

  return (
    <div className="max-w-md mx-auto min-h-screen bg-gray-50">
      <header className="p-4 border-b bg-white flex justify-between items-center sticky top-0 z-10">
        <h1 className="text-xl font-bold text-slate-900">{t("app.favorites")}</h1>
        <button onClick={() => navigate("/")} className="text-blue-600 text-sm font-medium">Home</button>
      </header>
      
      <div className="p-4 space-y-3">
        {!favorites?.items || favorites.items.length === 0 ? (
          <div className="text-center text-gray-500 mt-10 p-6 bg-white rounded-xl border border-dashed">
            You have no favorite horses yet.
          </div>
        ) : (
          favorites.items.map((fav: any) => (
            <FavoriteRow key={fav.horse_id} fav={fav} removeFav={removeFav} />
          ))
        )}
      </div>
    </div>
  );
}
