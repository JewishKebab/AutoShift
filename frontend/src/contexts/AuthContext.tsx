import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

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

/**
 * No config.js. No hardcoded backend host.
 * Single source of truth: API is always same-origin under /api
 *
 * - Local dev: Vite proxy forwards /api -> http://localhost:5000
 * - VM/prod: Nginx forwards /api -> backend container
 */
function buildApiUrl(path: string) {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `/api${p}`;
}

async function apiRequest<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(buildApiUrl(path), {
    method,
    credentials: "include", // IMPORTANT: cookie auth
    headers: {
      Accept: "application/json",
      ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
    },
    body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
  });

  const contentType = res.headers.get("content-type") || "";
  const raw = await res.text();

  let data: any = null;
  if (contentType.includes("application/json") && raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const msg =
      (data && (data.error || data.message)) ||
      raw ||
      `Request failed (${res.status})`;
    throw new Error(msg);
  }

  // Fail loudly if backend didn't return JSON (helps debug nginx/html responses)
  if (!data) {
    throw new Error(
      `Expected JSON but got ${contentType || "unknown content-type"}`
    );
  }

  return data as T;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = !!user;

  const refreshIdentity = async () => {
    try {
      // Backend should implement /api/identity (jwt_required)
      const me = await apiRequest<User>("GET", "/identity");
      setUser(me);
    } catch {
      setUser(null);
    }
  };

  const login = async () => {
    setIsLoading(true);
    try {
      const data = await apiRequest<{ auth_url: string }>("GET", "/login/azure");
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
      await apiRequest("POST", "/logout", {});
    } catch {
      // Even if logout fails, clear local state and continue
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

