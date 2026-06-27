import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchFavorites, removeFavorite } from "../api/favorites";
import { useAuthStore } from "../lib/store";
import { useNavigate } from "react-router-dom";
import { Star, Trash2 } from "lucide-react";
import { format } from "date-fns";

export default function FavoritesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isAuth = !!useAuthStore((state) => state.accessToken);

  const { data: favorites, isLoading } = useQuery({
    queryKey: ["favorites"],
    queryFn: fetchFavorites,
    enabled: isAuth,
  });

  const removeFav = useMutation({
    mutationFn: (id: number) => removeFavorite(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["favorites"] }),
  });

  if (!isAuth) {
    return (
      <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 text-slate-200 flex flex-col items-center justify-center gap-4 pb-24">
        <Star size={48} className="text-slate-600" />
        <p className="text-lg font-semibold text-slate-300">로그인이 필요합니다</p>
        <button
          onClick={() => navigate("/login")}
          className="bg-indigo-500 hover:bg-indigo-600 text-white font-bold px-6 py-2.5 rounded-xl transition-colors"
        >
          로그인
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 text-slate-200 pb-24">
      <header className="p-4 border-b border-white/10 sticky top-0 bg-slate-950/90 backdrop-blur-md z-10 shadow-lg shadow-black/20">
        <h1 className="text-xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
          즐겨찾기
        </h1>
      </header>

      {isLoading ? (
        <div className="p-4 space-y-3 mt-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-white/5 rounded-2xl border border-white/5 animate-pulse" />
          ))}
        </div>
      ) : !favorites?.items || favorites.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center mt-32 gap-4 text-center px-8">
          <Star size={48} className="text-slate-700" />
          <p className="text-lg font-semibold text-slate-400">아직 즐겨찾기한 말이 없습니다</p>
          <p className="text-sm text-slate-600">경주 상세 화면에서 ⭐를 눌러 추가하세요.</p>
        </div>
      ) : (
        <div className="p-4 space-y-3">
          {favorites.items.map((fav: any) => (
            <div
              key={fav.horse_id}
              className="flex items-center justify-between bg-white/5 border border-white/10 rounded-2xl p-4 hover:bg-white/8 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-yellow-500/20 to-amber-500/20 border border-yellow-500/20 flex items-center justify-center">
                  <Star size={20} className="text-yellow-400" fill="currentColor" />
                </div>
                <div>
                  <p className="font-bold text-slate-100 text-base">{fav.horse?.name}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    등록일 {format(new Date(fav.created_at), "yyyy.MM.dd")}
                  </p>
                </div>
              </div>
              <button
                onClick={() => removeFav.mutate(fav.horse_id)}
                className="p-2 rounded-full text-slate-600 hover:text-rose-400 hover:bg-rose-500/10 transition-all"
              >
                <Trash2 size={18} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
