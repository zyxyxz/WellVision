import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { apiClient, setAuthToken } from "../api/client";
import { fetchMe, switchTenant } from "../api/auth";
import type { LoginPayload, MeResponse, TokenResponse } from "./types";

type AuthState = {
  token: string | null;
  me: MeResponse | null;
  loading: boolean;
};

type AuthContextValue = AuthState & {
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
  switchTenant: (tenantId: string) => Promise<void>;
};

const TOKEN_KEY = "wellvision_token";

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshMe = useCallback(async () => {
    if (!token) {
      setMe(null);
      return;
    }
    setAuthToken(token);
    const meResponse = await fetchMe();
    setMe(meResponse);
  }, [token]);

  useEffect(() => {
    let active = true;

    async function init() {
      try {
        if (token) {
          setAuthToken(token);
          const meResponse = await fetchMe();
          if (active) {
            setMe(meResponse);
          }
        }
      } catch (error) {
        localStorage.removeItem(TOKEN_KEY);
        setAuthToken(null);
        if (active) {
          setToken(null);
          setMe(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    init();
    return () => {
      active = false;
    };
  }, [token]);

  const login = useCallback(async (payload: LoginPayload) => {
    const response = await apiClient.post<TokenResponse>("/auth/login", payload);
    const nextToken = response.data.access_token;
    localStorage.setItem(TOKEN_KEY, nextToken);
    setAuthToken(nextToken);
    setToken(nextToken);
    const meResponse = await fetchMe();
    setMe(meResponse);
  }, []);

  const handleSwitchTenant = useCallback(
    async (tenantId: string) => {
      const response = await switchTenant(tenantId);
      const nextToken = response.access_token;
      localStorage.setItem(TOKEN_KEY, nextToken);
      setAuthToken(nextToken);
      setToken(nextToken);
      const meResponse = await fetchMe();
      setMe(meResponse);
    },
    []
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setAuthToken(null);
    setToken(null);
    setMe(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ token, me, loading, login, logout, refreshMe, switchTenant: handleSwitchTenant }),
    [token, me, loading, login, logout, refreshMe, handleSwitchTenant]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
