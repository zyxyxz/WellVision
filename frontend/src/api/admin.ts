import { apiClient } from "./client";

type TenantResponse = {
  id: string;
  name: string;
  slug: string;
};

type UserResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  is_active: boolean;
  is_platform_admin: boolean;
};

type TenantCreatePayload = {
  name: string;
  slug: string;
};

type UserCreatePayload = {
  email: string;
  password: string;
  full_name?: string;
  is_platform_admin?: boolean;
};

type MembershipAssignPayload = {
  user_id: string;
  tenant_id: string;
  role: string;
};

type AdminChatSession = {
  id: string;
  tenant_id: string;
  user_id?: string | null;
  warehouse_id?: string | null;
  title?: string | null;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type AdminChatMessage = {
  id: string;
  role: string;
  content: string;
  created_at: string;
};

export async function listTenants() {
  const { data } = await apiClient.get<TenantResponse[]>("/admin/tenants");
  return data;
}

export async function createTenant(payload: TenantCreatePayload) {
  const { data } = await apiClient.post<TenantResponse>("/admin/tenants", payload);
  return data;
}

export async function listUsers() {
  const { data } = await apiClient.get<UserResponse[]>("/admin/users");
  return data;
}

export async function createUser(payload: UserCreatePayload) {
  const { data } = await apiClient.post<UserResponse>("/admin/users", payload);
  return data;
}

export async function assignMembership(payload: MembershipAssignPayload) {
  const { data } = await apiClient.post("/admin/memberships", payload);
  return data as { id: string; user_id: string; tenant_id: string; role: string };
}

export async function listAdminChatSessions(params?: { limit?: number; offset?: number }) {
  const { data } = await apiClient.get<AdminChatSession[]>("/admin/ai-chat/sessions", { params });
  return data;
}

export async function listAdminChatMessages(sessionId: string) {
  const { data } = await apiClient.get<AdminChatMessage[]>(`/admin/ai-chat/sessions/${sessionId}/messages`);
  return data;
}

export type { TenantResponse, UserResponse, AdminChatSession, AdminChatMessage };
