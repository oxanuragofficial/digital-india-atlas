// MapLibre GL JS 6 locates its web worker relative to `import.meta.url`. Bundlers (including
// Next.js) rewrite that URL, so the worker is not found at runtime ("Worker failed to load").
// We copy the worker from node_modules into /public and tell MapLibre where it is (see
// src/lib/map-config.ts and AtlasMap.tsx). Copying from node_modules keeps the worker version
// identical to the installed maplibre-gl. The copy is generated, so it is git-ignored.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "node_modules", "maplibre-gl", "dist", "maplibre-gl-worker.mjs");
const targetDir = path.join(root, "public");
const target = path.join(targetDir, "maplibre-gl-worker.mjs");

if (!existsSync(source)) {
  console.error(`copy-maplibre-worker: not found: ${source}\nRun "npm install" first.`);
  process.exit(1);
}
mkdirSync(targetDir, { recursive: true });
copyFileSync(source, target);
console.log("copy-maplibre-worker: copied maplibre-gl-worker.mjs to public/");
