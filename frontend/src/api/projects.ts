import { apiClient } from "./client";

export type ProjectResponse = {
  id: string;
  tenant_id: string;
  name: string;
  code: string;
  description?: string | null;
  background?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ProjectCreate = {
  name: string;
  code?: string;
  description?: string;
  background?: string;
  status?: string;
};

export type ProjectUpdate = {
  name?: string;
  code?: string;
  description?: string;
  background?: string;
  status?: string;
};

export async function listProjects() {
  const { data } = await apiClient.get<ProjectResponse[]>("/projects");
  return data;
}

export async function createProject(payload: ProjectCreate) {
  const { data } = await apiClient.post<ProjectResponse>("/projects", payload);
  return data;
}

export async function updateProject(id: string, payload: ProjectUpdate) {
  const { data } = await apiClient.patch<ProjectResponse>(`/projects/${id}`, payload);
  return data;
}

export async function deleteProject(id: string) {
  await apiClient.delete(`/projects/${id}`);
}
