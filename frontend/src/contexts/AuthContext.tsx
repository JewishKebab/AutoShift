import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

type User = {
  name: string;
  email: string;
  role?: string;
  azure_roles?: string[];
};

type AuthContextType = {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshIdentity: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:5000";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    credentials: "include", // IMPORTANT: cookie auth
    headers: { "Accept": "application/json" },
  });

  // If backend redirects (rare here), browser will follow automatically
  const contentType = res.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await res.json() : null;

  if (!res.ok) {
    const msg = (data && (data.error || data.message)) || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data as T;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = !!user;

  const refreshIdentity = async () => {
    try {
      // You should implement /api/identity on the backend (jwt_required)
      const me = await apiGet<User>("/api/identity");
      setUser(me);
    } catch {
      setUser(null);
    }
  };

  const login = async () => {
    setIsLoading(true);
    try {
      const data = await apiGet<{ auth_url: string }>("/api/login/azure");
      // Full-page redirect into Azure login flow
      window.location.href = data.auth_url;
    } finally {
      // Not really reached in success case (redirect). Keep for completeness.
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await fetch(`${import.meta.env.VITE_API_BASE || "http://localhost:5000"}/api/logout`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      });
    } finally {
      setUser(null);
      setIsLoading(false);
      window.location.href = "/login";
    }
};


  useEffect(() => {
    // On app load, try to discover current session (JWT cookies)
    (async () => {
      await refreshIdentity();
      setIsLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({ user, isAuthenticated, isLoading, login, logout, refreshIdentity }),
    [user, isAuthenticated, isLoading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
