import { apiClient } from "./client";

export interface TrackModelInfo {
  track: string;
  model_version: string | null;
  log_loss: number | null;
  roi: number | null;
  promoted_at: string | null;
}

export interface AdminMlStatus {
  tracks: TrackModelInfo[];
  last_updated: string;
}

export interface CrawlStateInfo {
  track: string;
  last_crawled_date: string | null;
  last_status: string | null;
  next_scheduled: string;
}

export interface CrawlFailureInfo {
  id: number;
  track: string;
  failed_date: string;
  error_message: string | null;
  retry_count: number;
}

export interface DbSummary {
  total_races: number;
  total_horses: number;
  total_jockeys: number;
  latest_race_date: string | null;
}

export interface AdminDataStatus {
  crawl_states: CrawlStateInfo[];
  failures: CrawlFailureInfo[];
  db_summary: DbSummary;
}

export interface RetryResult {
  ok: boolean;
  track: string;
  date: string;
  result: { races_upserted: number; failures: string[] };
}

export async function fetchMlStatus(): Promise<AdminMlStatus> {
  const res = await apiClient.get("/admin/ml/status");
  return res.data;
}

export async function fetchDataStatus(): Promise<AdminDataStatus> {
  const res = await apiClient.get("/admin/data/status");
  return res.data;
}

export async function retryDate(track: string, date: string): Promise<RetryResult> {
  const res = await apiClient.post("/admin/data/retry", { track, date });
  return res.data;
}

export async function updateDate(date?: string): Promise<{ ok: boolean; message: string }> {
  const res = await apiClient.post("/admin/update-date", date ? { date } : {});
  return res.data;
}
