import { apiClient } from "./client";

export type AlgorithmDefinition = {
  id: string;
  tenant_id: string;
  created_by_user_id?: string | null;
  key: string;
  name: string;
  kind: "python" | "http" | "workflow";
  description?: string | null;
  config: Record<string, unknown>;
  enabled: boolean;
  params: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
};

export type AlgorithmDefinitionCreate = {
  name: string;
  key?: string;
  kind: "python" | "http" | "workflow";
  description?: string;
  config: Record<string, unknown>;
  enabled?: boolean;
};

export type AlgorithmDefinitionUpdate = {
  name?: string;
  key?: string;
  kind?: "python" | "http" | "workflow";
  description?: string | null;
  config?: Record<string, unknown>;
  enabled?: boolean;
};

export async function listAlgorithmDefinitions() {
  const { data } = await apiClient.get<AlgorithmDefinition[]>("/algorithms");
  return data;
}

export async function getAlgorithmDefinition(id: string) {
  const { data } = await apiClient.get<AlgorithmDefinition>(`/algorithms/${id}`);
  return data;
}

export async function createAlgorithmDefinition(payload: AlgorithmDefinitionCreate) {
  const { data } = await apiClient.post<AlgorithmDefinition>("/algorithms", payload);
  return data;
}

export async function updateAlgorithmDefinition(id: string, payload: AlgorithmDefinitionUpdate) {
  const { data } = await apiClient.patch<AlgorithmDefinition>(`/algorithms/${id}`, payload);
  return data;
}

export async function deleteAlgorithmDefinition(id: string) {
  await apiClient.delete(`/algorithms/${id}`);
}

export async function generateAlgorithmByAI(payload: { requirement: string; field?: string | null }) {
  const { data } = await apiClient.post<{ code: string; params: Array<Record<string, unknown>> }>(
    "/algorithms/ai-generate",
    payload
  );
  return data;
}
