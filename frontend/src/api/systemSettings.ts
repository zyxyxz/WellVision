import { apiClient } from "./client";

export type SystemSetting = {
  key: string;
  value: Record<string, unknown>;
  updated_at?: string | null;
  updated_by_user_id?: string | null;
};

export async function listSystemSettings() {
  const { data } = await apiClient.get<SystemSetting[]>("/admin/system-settings");
  return data;
}

export async function getSystemSetting(key: string) {
  const { data } = await apiClient.get<SystemSetting>(`/admin/system-settings/${key}`);
  return data;
}

export async function upsertSystemSetting(key: string, value: Record<string, unknown>) {
  const { data } = await apiClient.put<SystemSetting>(`/admin/system-settings/${key}`, { value });
  return data;
}
