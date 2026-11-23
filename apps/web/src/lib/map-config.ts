/**
 * Map configuration.
 *
 * Basemap: OpenFreeMap "Liberty" vector style (no API key). See docs/MAP_BASEMAP.md for the
 * attribution and usage requirements.
 */

/** Public style URL. Override with NEXT_PUBLIC_MAP_STYLE_URL to self-host or switch providers. */
export const DEFAULT_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

export function getMapStyleUrl(): string {
  const override = process.env.NEXT_PUBLIC_MAP_STYLE_URL?.trim();
  return override ? override : DEFAULT_STYLE_URL;
}

/**
 * Public path of the MapLibre web worker, copied into /public by scripts/copy-maplibre-worker.mjs.
 * Needed because bundlers break MapLibre's default `import.meta.url` worker lookup.
 */
export const MAP_WORKER_URL = "/maplibre-gl-worker.mjs";

/** [west, south, east, north] in WGS84. */
export type LngLatBoundsArray = [number, number, number, number];

/**
 * Approximate framing for the first view of India.
 *
 * This is a viewport convenience ONLY. It is not an administrative or legal boundary and must
 * not be used for clipping, area calculations, or deciding what is inside India.
 */
export const INDIA_VIEWPORT: LngLatBoundsArray = [67.5, 5.5, 98.5, 37.5];

export const INDIA_CENTER: [number, number] = [82.5, 22.5];
export const INITIAL_ZOOM = 3.6;
export const MIN_ZOOM = 2;
export const MAX_ZOOM = 18;

/** Credits that must remain visible wherever the basemap is shown. */
export const BASEMAP_CREDITS = [
  { label: "OpenFreeMap", href: "https://openfreemap.org" },
  { label: "© OpenMapTiles", href: "https://www.openmaptiles.org/" },
  { label: "Data © OpenStreetMap contributors", href: "https://www.openstreetmap.org/copyright" },
] as const;
