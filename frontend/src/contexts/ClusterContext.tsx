import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

export type AzureClusterStatus = "running" | "deploying" | "pending" | "failed";

export type AzureCluster = {
  id: string;
  name: string;
  infra: string;
  resourceGroup: string;
  subscriptionId: string;
  status: AzureClusterStatus;
  dnsZone: string;
  dnsZoneFound: boolean;
};

type ClustersApiResponse =
  | { ok: true; clusters: AzureCluster[] }
  | { ok: false; error?: string; missing?: string[] };

type ClusterContextValue = {
  azureClusters: AzureCluster[];
  isInitialLoading: boolean;
  isRefreshing: boolean;
  lastUpdatedAt: number | null;
  refresh: () => Promise<void>;
};

const ClusterContext = createContext<ClusterContextValue | null>(null);

function fetchWithTimeout(url: string, opts: RequestInit & { timeoutMs?: number } = {}) {
  const { timeoutMs = 15000, ...init } = opts;

  const controller = new AbortController();
  const t = window.setTimeout(() => controller.abort(), timeoutMs);

  return fetch(url, { ...init, signal: controller.signal })
    .finally(() => window.clearTimeout(t));
}

export function ClusterProvider({ children }: { children: React.ReactNode }) {
  const [azureClusters, setAzureClusters] = useState<AzureCluster[]>([]);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  // prevent overlapping refreshes
  const inFlightRef = useRef<Promise<void> | null>(null);

  // IMPORTANT: keep '' if you are using Vite proxy to /api
  const API_BASE = "";

  const refresh = async () => {
    if (inFlightRef.current) return inFlightRef.current;

    const p = (async () => {
      setIsRefreshing(true);

      try {
        const res = await fetchWithTimeout(`${API_BASE}/api/clusters`, {
          method: "GET",
          // keep this if auth uses cookies
          credentials: "include",
          headers: { Accept: "application/json" },
          timeoutMs: 15000,
        });

        const data = (await res.json()) as ClustersApiResponse;

        if (!res.ok || !data.ok) {
          const msg =
            (data as any)?.error ||
            `Failed to load clusters (HTTP ${res.status})`;

          throw new Error(msg);
        }

        //  This is the key: API returns "clusters"
        setAzureClusters(data.clusters || []);
        setLastUpdatedAt(Date.now());
      } catch (err: any) {
        const msg = err?.name === "AbortError"
          ? "Request timed out (15s)"
          : (err?.message || String(err));

        console.error("[clusters] refresh failed:", err);

        toast.error("Failed to load clusters", { description: msg });
      } finally {
        setIsRefreshing(false);
        setIsInitialLoading(false);
      }
    })();

    inFlightRef.current = p;
    try {
      await p;
    } finally {
      inFlightRef.current = null;
    }
  };

  useEffect(() => {
    refresh();
    // Optional polling every 30s:
    const intervalMs = 30000;
    const t = window.setInterval(() => refresh(), intervalMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({ azureClusters, isInitialLoading, isRefreshing, refresh, lastUpdatedAt }),
    [azureClusters, isInitialLoading, isRefreshing, lastUpdatedAt]
  );

  return <ClusterContext.Provider value={value}>{children}</ClusterContext.Provider>;
}

export function useClusters() {
  const ctx = useContext(ClusterContext);
  if (!ctx) throw new Error("useClusters must be used within ClusterProvider");
  return ctx;
}
