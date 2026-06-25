import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchFavorites, removeFavorite } from "../api/favorites";
import { useAuthStore } from "../lib/store";
import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { format } from "date-fns";

export default function FavoritesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
    <div className="max-w-md mx-auto min-h-screen bg-white">
      <header className="p-4 border-b flex justify-between items-center">
        <h1 className="text-xl font-bold">My Favorite Horses</h1>
        <button onClick={() => navigate("/")} className="text-blue-600 text-sm">Home</button>
      </header>
      
      <div className="p-4 space-y-3">
        {favorites?.items?.length === 0 ? (
          <div className="text-center text-gray-500 mt-10">You have no favorite horses yet.</div>
        ) : (
          favorites?.items?.map((fav: any) => (
            <div key={fav.horse.id} className="flex justify-between items-center border p-4 rounded-xl shadow-sm">
              <div>
                <div className="font-bold text-lg">{fav.horse.name}</div>
                <div className="text-xs text-gray-400">Favorited on {format(new Date(fav.created_at), "yyyy-MM-dd")}</div>
              </div>
              <button 
                onClick={() => removeFav.mutate(fav.horse.id)}
                className="text-red-500 p-2 hover:bg-red-50 rounded"
              >
                <Trash2 size={20} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
