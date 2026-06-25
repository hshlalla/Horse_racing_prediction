import { apiClient } from './client';

export interface HorsePrediction {
  horse_id: number;
  horse_name: string;
  program_number: number;
  win_probability: number;
  place_probability: number;
  model_versions: Record<string, string>;
  features_snapshot: Record<string, any>;
  computed_at: string;
}

export async function fetchPredictions(raceId: number): Promise<{ items: HorsePrediction[] }> {
  const response = await apiClient.get<{ items: HorsePrediction[] }>(`/races/${raceId}/predictions`);
  return response.data;
}
