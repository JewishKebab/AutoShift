// src/lib/api.ts
export const API_BASE = import.meta.env.VITE_API_BASE ?? ""; //  default to Vite proxy (/api -> localhost:5000)

async function json<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      (data as any)?.error ||
      (data as any)?.msg ||
      `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data as T;
}

async function fetchWithTimeout(
  input: RequestInfo,
  init: RequestInit & { timeoutMs?: number } = {}
) {
  const { timeoutMs = 60_000, ...rest } = init;
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, { ...rest, signal: controller.signal });
  } catch (e: any) {
    //  turn AbortError into a useful error message
    if (e?.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw e;
  } finally {
    clearTimeout(t);
  }
}

// ---- timeouts tuned to your flow ----
const T = {
  short: 60_000,       // 60s
  medium: 120_000,     // 2m
  long: 10 * 60_000,   // 10m (VM start + SSH ready + write file)
};

export async function ensurePolicyExemption(clusterName: string) {
  const res = await fetchWithTimeout(`${API_BASE}/api/policy/exemptions/ensure`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ clusterName }),
    timeoutMs: T.short,
  });
  return json<{ ok: boolean; created?: boolean; expiresOn?: string; error?: string }>(res);
}

export async function createSubnets(payload: {
  clusterName: string;
  masterCidr: string;
  workerCidr: string;
}) {
  const res = await fetchWithTimeout(`${API_BASE}/api/subnets/create`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: T.long, //  Azure subnet create can take longer
  });
  return json<{ ok: boolean; error?: string }>(res);
}

export async function pushInstallConfig(payload: {
  clusterName: string;
  masterCidr: string;
  workerCidr: string;
  masterVmSize: string;
  workerVmSize: string;
  masterReplicas: number;
  workerReplicas: number;
}) {
  //  this one must be long because it may start VM + wait SSH + write file
  const res = await fetchWithTimeout(`${API_BASE}/api/install-config/push`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: T.long,
  });

  const data = await res.json().catch(() => ({} as any));
  if (!res.ok || !data.ok) {
    throw new Error(data?.error || "Failed to push install-config");
  }
  return data;
}

export async function startInstaller(clusterName: string) {
  //  keep medium/long if the backend might do SSH work here too
  const res = await fetchWithTimeout(`${API_BASE}/api/installer/start`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ clusterName }),
    timeoutMs: T.medium,
  });

  const data = await res.json().catch(() => ({} as any));
  if (!res.ok || !data.ok) throw new Error(data?.error || "Failed to start installer");
  return data as { ok: true; jobId: string };
}

export async function destroyCluster(clusterName: string) {
  const res = await fetchWithTimeout(`${API_BASE}/api/clusters/destroy`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ clusterName }),
    timeoutMs: T.long, // destroy can take a long time
  });

  const data = await res.json().catch(() => ({} as any));
  if (!res.ok || !data.ok) throw new Error(data?.error || "Failed to start destroy");
  return data as { ok: true; jobId: string };
}
