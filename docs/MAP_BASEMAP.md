# Basemap: attribution and usage

The atlas currently shows a **general-purpose basemap only**. It is not an official map of India and carries no Indian administrative datasets.

## Provider

| Item | Value |
|---|---|
| Provider | [OpenFreeMap](https://openfreemap.org) |
| Style | Liberty |
| Style URL | `https://tiles.openfreemap.org/styles/liberty` |
| API key | None required (per the provider's quick-start page) |
| Rendering | [MapLibre GL JS](https://maplibre.org/) |

The style URL is set in `apps/web/src/lib/map-config.ts` and can be overridden at build time with `NEXT_PUBLIC_MAP_STYLE_URL` (see `apps/web/.env.example`).

## Required attribution

The credits shown with the provider's own map are:

- [OpenFreeMap](https://openfreemap.org)
- [© OpenMapTiles](https://www.openmaptiles.org/)
- Data from [OpenStreetMap](https://www.openstreetmap.org/copyright) (© OpenStreetMap contributors)

**These must stay visible wherever the basemap is shown. Do not remove them.** The app shows them in two places:

1. **On the map**, by MapLibre's attribution control, which displays whatever attribution the style declares (`AtlasMap.tsx` keeps this control enabled).
2. **In the side panel**, as a fixed credit line (`BASEMAP_CREDITS` in `map-config.ts`, rendered by `Sidebar.tsx`). On small screens the panel is collapsed by default, so the on-map control is the one visible there.

If you change the style provider, update both places and this document to match the new provider's terms.

## Usage notes

Taken from the provider's quick-start page (the only provider page reviewed):

- No API key is needed.
- The page states **no general limit on tile requests**, but it does set limits for *offline bulk downloads*: at most 3,000 tiles or 50 MB per download, at most 4 parallel requests, and a unique User-Agent. Do not bulk-download tiles with this app.
- If you **modify a style**, you must host the modified style JSON yourself and point MapLibre at your copy.
- The page does **not address commercial use or service guarantees**. Before any commercial or high-traffic deployment, read the provider's current terms and consider self-hosting tiles.
- The provider asks users to consider sponsoring the project to cover server costs.

OpenStreetMap data is available under the [Open Database Licence (ODbL)](https://www.openstreetmap.org/copyright).

## Boundaries and place names

Borders and names on the basemap come from OpenStreetMap contributors. They are for **orientation only** and may differ from official Government of India depictions. This notice is shown in the app's side panel. Authoritative boundary data will be added as separate, clearly sourced layers in a later milestone.

## Technical note: MapLibre worker

MapLibre 6 finds its web worker relative to `import.meta.url`, which bundlers rewrite, producing `Worker failed to load` in the Next.js build. The fix is in this repository:

- `apps/web/scripts/copy-maplibre-worker.mjs` copies `maplibre-gl-worker.mjs` from `node_modules` to `apps/web/public/` on `npm install`, `npm run dev` and `npm run build` (the copy is generated and git-ignored).
- `AtlasMap.tsx` calls `setWorkerUrl("/maplibre-gl-worker.mjs")` before creating the map.

If the app is ever served under a sub-path, update `MAP_WORKER_URL` in `map-config.ts` accordingly.

## Verification status

| Check | Status |
|---|---|
| Map initialises, fills its container and renders in headless Chromium (desktop and mobile widths) using a **stub blank style** | Verified |
| Attribution control displays a style-declared attribution on desktop and mobile (stub style) | Verified |
| Web worker loads from the production build | Verified |
| Live OpenFreeMap tiles render | **Not verified.** The build environment could not reach `tiles.openfreemap.org` (network allowlist). Check this on your own machine. |
| The real Liberty style declares the three credits above in its sources | **Not verified** for the same reason. The side-panel credit line is independent of it. |
