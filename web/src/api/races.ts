import { apiClient } from "./client";

export async function fetchLatestRaceDate(): Promise<string> {
  const res = await apiClient.get<{ date: string }>("/races/latest-date");
  return res.data.date;
}

export async function fetchRaces(date: string, track?: string) {
  const params = track ? { date, track } : { date };
  const res = await apiClient.get("/races", { params });
  return res.data;
}

export async function fetchRaceDetail(raceId: number) {
  const res = await apiClient.get(`/races/${raceId}`);
  return res.data;
}

export async function fetchPredictions(raceId: number) {
  const res = await apiClient.get(`/races/${raceId}/predictions`);
  return res.data;
}

export async function fetchRaceResults(raceId: number) {
  const res = await apiClient.post(`/races/${raceId}/fetch-results`);
  return res.data;
}
