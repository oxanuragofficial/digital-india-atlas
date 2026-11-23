import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BASEMAP_CREDITS,
  DEFAULT_STYLE_URL,
  INDIA_CENTER,
  INDIA_VIEWPORT,
  getMapStyleUrl,
} from "./map-config";

afterEach(() => vi.unstubAllEnvs());

describe("getMapStyleUrl", () => {
  it("defaults to the OpenFreeMap Liberty style", () => {
    vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "");
    expect(getMapStyleUrl()).toBe(DEFAULT_STYLE_URL);
    expect(DEFAULT_STYLE_URL).toBe("https://tiles.openfreemap.org/styles/liberty");
  });

  it("uses a trimmed override when provided", () => {
    vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "  https://example.test/style.json ");
    expect(getMapStyleUrl()).toBe("https://example.test/style.json");
  });
});

describe("viewport constants", () => {
  it("is a well-formed [west, south, east, north] box", () => {
    const [w, s, e, n] = INDIA_VIEWPORT;
    expect(w).toBeLessThan(e);
    expect(s).toBeLessThan(n);
    expect(Math.abs(w)).toBeLessThanOrEqual(180);
    expect(Math.abs(s)).toBeLessThanOrEqual(90);
  });

  it("centre lies inside the viewport", () => {
    const [w, s, e, n] = INDIA_VIEWPORT;
    const [lng, lat] = INDIA_CENTER;
    expect(lng).toBeGreaterThan(w);
    expect(lng).toBeLessThan(e);
    expect(lat).toBeGreaterThan(s);
    expect(lat).toBeLessThan(n);
  });
});

describe("basemap credits", () => {
  it("include OpenFreeMap, OpenMapTiles and OpenStreetMap", () => {
    const text = BASEMAP_CREDITS.map((c) => c.label).join(" | ");
    expect(text).toContain("OpenFreeMap");
    expect(text).toContain("OpenMapTiles");
    expect(text).toContain("OpenStreetMap");
    expect(BASEMAP_CREDITS.every((c) => c.href.startsWith("https://"))).toBe(true);
  });
});
