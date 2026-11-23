/** Minimal API client. Only the health endpoints exist so far. */

export type ApiState = "online" | "degraded" | "offline";

export interface ApiStatus {
  state: ApiState;
  /** Short human-readable detail; never contains secrets. */
  detail: string;
}

export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8000";
  return raw.replace(/\/+$/, "");
}

/**
 * Check the API liveness endpoint.
 * - online:   /health answered 200 with status "ok"
 * - degraded: reachable but returned something unexpected
 * - offline:  network error, timeout or non-2xx
 */
export async function fetchApiStatus(
  baseUrl: string = getApiBaseUrl(),
  timeoutMs = 4000,
  fetchImpl: typeof fetch = fetch,
): Promise<ApiStatus> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(`${baseUrl}/health`, {
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) {
      return { state: "offline", detail: `API responded with HTTP ${response.status}` };
    }
    const body: unknown = await response.json();
    if (isRecord(body) && body.status === "ok") {
      return { state: "online", detail: "API is reachable" };
    }
    return { state: "degraded", detail: "API responded with an unexpected payload" };
  } catch {
    return { state: "offline", detail: "API is not reachable" };
  } finally {
    clearTimeout(timer);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
