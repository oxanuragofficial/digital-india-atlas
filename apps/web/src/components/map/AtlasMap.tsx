"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { NavigationControl, ScaleControl, Map as MapLibreMap, setWorkerUrl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import {
  INDIA_CENTER,
  INDIA_VIEWPORT,
  INITIAL_ZOOM,
  MAP_WORKER_URL,
  MAX_ZOOM,
  MIN_ZOOM,
  getMapStyleUrl,
} from "@/lib/map-config";

type MapStatus = "loading" | "ready" | "error";

export default function AtlasMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [status, setStatus] = useState<MapStatus>("loading");

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    let map: MapLibreMap;
    try {
      setWorkerUrl(MAP_WORKER_URL);
      map = new MapLibreMap({
        container,
        style: getMapStyleUrl(),
        center: INDIA_CENTER,
        zoom: INITIAL_ZOOM,
        minZoom: MIN_ZOOM,
        maxZoom: MAX_ZOOM,
        // The style's own attribution (OpenFreeMap / OpenMapTiles / OSM) is shown by the
        // default attribution control. Do not remove it.
        attributionControl: { compact: true },
      });
    } catch {
      // WebGL unavailable or invalid options.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStatus("error");
      return;
    }

    mapRef.current = map;
    map.addControl(new NavigationControl({ visualizePitch: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    map.fitBounds(INDIA_VIEWPORT, { padding: 24, duration: 0 });

    map.on("load", () => setStatus("ready"));
    map.on("error", (event) => {
      // Tile/style fetch failures surface here. Keep the map; show a notice only if the
      // style itself never loaded.
      if (!map.isStyleLoaded()) setStatus("error");
      console.warn("Map error:", event.error?.message ?? event);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div className="relative h-full w-full" data-testid="atlas-map-wrapper">
      <div
        ref={containerRef}
        // Sized with h-full/w-full, NOT absolute/inset-0: MapLibre's own CSS sets
        // `.maplibregl-map { position: relative }` and would override it, collapsing the
        // container to zero height.
        className="h-full w-full"
        role="region"
        aria-label="Interactive map of India"
      />
      {status === "loading" && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center bg-slate-100/70 text-sm text-slate-600">
          Loading map…
        </div>
      )}
      {status === "error" && (
        <div
          role="alert"
          className="absolute inset-x-4 top-4 z-10 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 shadow"
        >
          The basemap could not be loaded. Check your internet connection and that WebGL is
          enabled in your browser.
        </div>
      )}
    </div>
  );
}
