import { apiClient } from "./client";
import { useAuthStore } from "../lib/store";

export async function login(email: string, password: string) {
  const res = await apiClient.post("/auth/login", { email, password });
  useAuthStore.getState().setAccessToken(res.data.access_token);
  return res.data;
}

export async function register(email: string, password: string) {
  const res = await apiClient.post("/auth/register", { email, password });
  useAuthStore.getState().setAccessToken(res.data.access_token);
  return res.data;
}

export async function logout() {
  await apiClient.post("/auth/logout");
  useAuthStore.getState().logout();
}
