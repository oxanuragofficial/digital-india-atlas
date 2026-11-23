import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchApiStatus, getApiBaseUrl } from "./api";

afterEach(() => vi.unstubAllEnvs());

function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("getApiBaseUrl", () => {
  it("defaults to localhost:8000", () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    expect(getApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("strips trailing slashes", () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test///");
    expect(getApiBaseUrl()).toBe("https://api.example.test");
  });
});

describe("fetchApiStatus", () => {
  it("reports online when /health returns status ok", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    const result = await fetchApiStatus("http://api.test", 1000, fetchMock);
    expect(result.state).toBe("online");
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/health");
  });

  it("reports degraded for an unexpected payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "weird" }));
    expect((await fetchApiStatus("http://api.test", 1000, fetchMock)).state).toBe("degraded");
  });

  it("reports offline for a non-2xx response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, { status: 500 }));
    const result = await fetchApiStatus("http://api.test", 1000, fetchMock);
    expect(result.state).toBe("offline");
    expect(result.detail).toContain("500");
  });

  it("reports offline on network failure without leaking the error", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("connect ECONNREFUSED secret-host"));
    const result = await fetchApiStatus("http://api.test", 1000, fetchMock);
    expect(result.state).toBe("offline");
    expect(result.detail).not.toContain("secret-host");
  });

  it("reports offline when the request times out", async () => {
    const hangingFetch = ((_url: string, init?: RequestInit) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
      })) as unknown as typeof fetch;
    const result = await fetchApiStatus("http://api.test", 20, hangingFetch);
    expect(result.state).toBe("offline");
  });
});
