import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// `vi.mock` is hoisted above imports, so shared state must come from `vi.hoisted`.
const h = vi.hoisted(() => {
  const setWorkerUrl = vi.fn();
  const instances: Array<{
    options: Record<string, unknown>;
    controls: unknown[];
    workerWasSetAtConstruction: boolean;
    fitBounds: ReturnType<typeof import("vitest").vi.fn>;
    remove: ReturnType<typeof import("vitest").vi.fn>;
  }> = [];
  return { instances, setWorkerUrl };
});

vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
vi.mock("maplibre-gl", () => {
  class FakeMap {
    options: Record<string, unknown>;
    controls: unknown[] = [];
    workerWasSetAtConstruction = h.setWorkerUrl.mock.calls.length > 0;
    fitBounds = vi.fn();
    remove = vi.fn();
    isStyleLoaded = vi.fn(() => true);
    constructor(options: Record<string, unknown>) {
      this.options = options;
      h.instances.push(this);
    }
    addControl(control: unknown) {
      this.controls.push(control);
    }
    on() {}
  }
  return {
    Map: FakeMap,
    NavigationControl: class {},
    ScaleControl: class {},
    setWorkerUrl: h.setWorkerUrl,
  };
});

import AtlasMap from "./AtlasMap";

beforeEach(() => {
  h.instances.length = 0;
  h.setWorkerUrl.mockClear();
});

describe("AtlasMap", () => {
  it("creates one map with the OpenFreeMap style and keeps attribution enabled", () => {
    render(<AtlasMap />);
    expect(h.instances).toHaveLength(1);
    const [map] = h.instances;
    expect(map.options.style).toBe("https://tiles.openfreemap.org/styles/liberty");
    expect(map.options.attributionControl).toBeTruthy();
    expect(map.controls).toHaveLength(2);
    expect(map.fitBounds).toHaveBeenCalledOnce();
  });

  it("points MapLibre at the self-hosted worker before creating the map", () => {
    render(<AtlasMap />);
    expect(h.setWorkerUrl).toHaveBeenCalledWith("/maplibre-gl-worker.mjs");
    expect(h.instances[0].workerWasSetAtConstruction).toBe(true);
  });

  it("removes the map on unmount", () => {
    const { unmount } = render(<AtlasMap />);
    unmount();
    expect(h.instances[0].remove).toHaveBeenCalledOnce();
  });
});
