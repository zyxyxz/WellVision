import { apiClient } from "./client";

export type EventResponse = {
  id: string;
  tenant_id: string;
  warehouse_id?: string | null;
  received_by_user_id?: string | null;
  source: string;
  topic?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export async function listEvents(params?: { source?: string; topic?: string; limit?: number; warehouse_id?: string }) {
  const { data } = await apiClient.get<EventResponse[]>("/ingestion/events", { params });
  return data;
}

export async function ingestEvent(input: {
  source: string;
  topic?: string;
  payload: Record<string, unknown>;
  warehouse_id?: string;
}) {
  const { data } = await apiClient.post<EventResponse>("/ingestion/events", input);
  return data;
}
