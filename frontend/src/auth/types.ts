export type LoginPayload = {
  email: string;
  password: string;
  tenant_id?: string | null;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  tenant_id?: string | null;
  roles: string[];
};

export type MeResponse = {
  user: {
    id: string;
    email: string;
    full_name?: string | null;
    is_platform_admin: boolean;
  };
  tenant_id?: string | null;
  roles: string[];
  context: {
    tenants: Array<{
      tenant_id: string;
      role: string;
    }>;
  };
};
