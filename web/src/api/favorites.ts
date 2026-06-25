import { apiClient } from "./client";

export async function fetchFavorites() {
  const res = await apiClient.get("/favorites");
  return res.data;
}

export async function addFavorite(horseId: number) {
  const res = await apiClient.post("/favorites", { horse_id: horseId });
  return res.data;
}

export async function removeFavorite(horseId: number) {
  const res = await apiClient.delete(`/favorites/${horseId}`);
  return res.data;
}
