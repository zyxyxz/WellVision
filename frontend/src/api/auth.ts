import { apiClient } from "./client";
import type { MeResponse, TokenResponse } from "../auth/types";

export async function switchTenant(tenant_id: string) {
  const { data } = await apiClient.post<TokenResponse>("/auth/switch-tenant", { tenant_id });
  return data;
}

export async function fetchMe() {
  const { data } = await apiClient.get<MeResponse>("/auth/me");
  return data;
}
