import { apiClient } from './client';

export interface MLStatus {
  status: string;
  models: Record<string, {
    version: string;
    last_trained_at: string;
    ece_drift_4w: number;
  }>;
  last_predict_run: string;
}

export async function fetchMLStatus(): Promise<MLStatus> {
  const response = await apiClient.get<MLStatus>('/ml/status');
  return response.data;
}
